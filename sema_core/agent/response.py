"""
SEMA agent: structured response assembler.

The agent finishes by calling a special `present_answer` tool. Instead of
executing like the data tools, that call carries the *structured* final
answer, which this module turns into the exact response dict the UI already
renders (the same shape insight_builder produces). That's how an agent
answer looks identical to a curated one -- chat.py can't tell them apart.

Accuracy guarantee: CHARTS and TABLES are bound to real query results by
index (`result_index` into AgentTools.results), and KPIs may bind a
(result_index, column, row) reference the same way -- when bound, the value
shown is read from the actual query result and the model-typed value is only
a logged fallback. The model never re-types row data, so what the user sees
can't drift from the SQL that produced it.

No dependency on the Claude API key.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone
from decimal import Decimal

import pandas as pd
import sqlglot
from sqlglot import expressions as exp

from sema_core.agent.semantic import load_knowledge
from sema_core.client_registry import active_client_id
from sema_core.data_sources import stale_source_caveat
from sema_core.obs import get_logger, log_event

logger = get_logger("agent")

# --- line-vs-bar safety net (trend_line_charts_prompt.md item 3) -----------
# The system prompt/tool schema ASK the model to pick kind='line' whenever
# the x-axis is a time/period sequence, but that instruction can't be
# trusted alone -- this coerces it deterministically at bind time too.
_DATE_COLUMN_NAME_RE = re.compile(r"^(date|day|week|month|quarter|year)(_|$)", re.IGNORECASE)
# Matches a bare year, a year-month, or a full ISO date -- covers both a raw
# ::date/timestamp column (see below) and a TO_CHAR(...)-formatted label
# like "2026-01" or "2026" (the semantic layer's own SQL sometimes buckets
# this way rather than returning a real date type).
_DATE_VALUE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
# How much of a (potentially large) column to sample when checking value
# shapes -- cheap and sufficient, since a chart's x-axis is never more than
# a few dozen distinct points in practice.
_DATE_SAMPLE_SIZE = 20


def _looks_like_date_axis(df: pd.DataFrame, column: str | None) -> bool:
    """Whether `column` in `df` is a time/period sequence (day, week, month,
    quarter, year) rather than a categorical dimension. Checks the column
    NAME first (the semantic layer's own convention: a dimension literally
    named "month"/"day" is always time), then falls back to the VALUES for a
    differently-named date column -- either real `datetime.date`/`datetime`
    objects (how psycopg2 returns a Postgres ::date/timestamp column) or an
    ISO-shaped string (how a TO_CHAR(...)-formatted label comes back).
    """
    if not column or column not in df.columns:
        return False
    if _DATE_COLUMN_NAME_RE.match(column):
        return True
    series = df[column].dropna()
    if series.empty:
        return False
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    sample = series.iloc[:_DATE_SAMPLE_SIZE]
    if all(isinstance(v, (date, datetime)) for v in sample):
        return True
    if all(isinstance(v, str) and _DATE_VALUE_RE.match(v) for v in sample):
        return True
    return False

# The "menu entry" for the finishing tool. Added to the tool list in agent.py.
PRESENT_ANSWER_TOOL = {
    "name": "present_answer",
    "description": (
        "Call this ONCE when you have enough evidence, to deliver your final "
        "answer to the user. Provide the narrative insight, KPI cards, an "
        "optional chart and table (each bound to a previous run_sql result by "
        "its 0-based index in call order), and 2-3 recommended actions. Do "
        "not call any other tool in the same turn."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "answer", "clarification", "cannot_answer", "off_topic", "access_denied",
                ],
                "description": (
                    "How you are responding. 'answer': the result is grounded in "
                    "executed queries. 'clarification': business question you COULD "
                    "answer, but one detail is materially ambiguous -- ask instead of "
                    "guessing. 'cannot_answer': the connected data cannot reliably "
                    "support an answer. 'off_topic': not about this business at all. "
                    "'access_denied': the question touches a domain or metric outside "
                    "the requester's data-access scope (see the governed context) -- "
                    "use this whenever a data tool returns a 'policy_blocked' result, "
                    "or you can tell upfront from the scope summary that the question "
                    "is out of bounds; never silently answer with just the allowed "
                    "part of a multi-metric question instead. Default to 'answer' "
                    "only when genuinely grounded."
                ),
            },
            "reason_code": {
                "type": "string",
                "enum": [
                    "ambiguous_metric",
                    "missing_date_range",
                    # Clarification ambiguity taxonomy -- the specific axis that
                    # was unresolved (see the system prompt / governed config).
                    "calendar_vs_fiscal",
                    "business_vs_calendar_days",
                    "ambiguous_date_range",
                    "ambiguous_comparison",
                    "ambiguous_scope",
                    "ambiguous_inclusion_rule",
                    "missing_timezone",
                    "missing_data_source",
                    "empty_result",
                    "unsupported_prediction",
                    "off_topic",
                    "insufficient_grounding",
                    "data_scope_blocked",
                ],
                "description": "Machine-readable reason for a non-'answer' mode. "
                "For mode='clarification' it names the specific ambiguity axis.",
            },
            "clarification_options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "For mode='clarification': 2-4 SHORT selectable "
                "options that resolve the ambiguity (e.g. ['Gross revenue', 'Net "
                "revenue']). The user taps one and it continues this same "
                "analysis, so each must be a complete, self-contained choice.",
            },
            "missing": {
                "type": "string",
                "description": "For mode='cannot_answer': the specific data, table "
                "or business definition that is missing. One short sentence.",
            },
            "summary": {
                "type": "string",
                "description": "For mode='answer' ONLY: a 1-2 sentence executive "
                "summary shown above the full answer. State the central "
                "CONCLUSION with its key numbers -- not an introduction like "
                "'Here is a summary of campaign performance'. Explain the main "
                "relationship between the metrics rather than listing the KPIs "
                "again, and make it understandable without reading further. "
                "Plain text only (no markdown), same language as the question, "
                "and substantially shorter than insight_text -- never the same "
                "sentences. Omit for non-'answer' modes.",
            },
            "insight_text": {
                "type": "string",
                "description": "The narrative answer in markdown. Lead with the "
                "direct answer and key numbers; quantify drivers. For "
                "clarification/cannot_answer/off_topic this is the message itself "
                "-- for off_topic keep it to 1-2 light, friendly sentences that "
                "redirect to business analysis, in the user's language.",
            },
            "kpis": {
                "type": "array",
                "description": "2-4 headline numbers to show as cards.",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "value": {"type": ["number", "string"]},
                        "format": {
                            "type": "string",
                            "enum": ["currency", "percent", "number", "ratio", "text"],
                        },
                        "result_index": {
                            "type": "integer",
                            "description": "When this KPI's value comes from a "
                            "run_sql result, the 0-based index of that run_sql "
                            "call. The UI then reads the EXACT value from the "
                            "query result (with `column` and `row`) instead of "
                            "your typed `value` -- always bind when possible.",
                        },
                        "column": {
                            "type": "string",
                            "description": "Column in that result holding the value.",
                        },
                        "row": {
                            "type": "integer",
                            "description": "0-based row in that result (default 0).",
                        },
                        "delta": {
                            "type": "number",
                            "description": "Optional % change vs a baseline.",
                        },
                        "delta_label": {"type": "string"},
                    },
                    "required": ["label", "value", "format"],
                },
            },
            "chart": {
                "type": "object",
                "description": "Optional chart bound to a run_sql result.",
                "properties": {
                    "result_index": {
                        "type": "integer",
                        "description": "0-based index of the run_sql call whose "
                        "result to chart.",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["line", "bar", "grouped_bar", "donut"],
                        "description": "Pick by what the x-axis actually IS, "
                        "not by whether the question says 'trend': if x is a "
                        "date/period sequence (day, week, month, quarter, "
                        "year -- e.g. 'revenue by month'), use 'line', even "
                        "for a single category ('Accessories revenue by "
                        "month' is still a line chart, x=month). If x is "
                        "categorical/entities with no inherent order (by "
                        "category, product, channel, customer), use 'bar' "
                        "(single series) or 'grouped_bar' (one series per "
                        "category via `color`). 'donut' is for a share-of-"
                        "whole breakdown (names/values), not a comparison. "
                        "A server-side check enforces the time-axis case "
                        "regardless of what you pick here, so getting this "
                        "wrong still renders correctly -- but picking right "
                        "the first time avoids a silent correction.",
                    },
                    "title": {"type": "string"},
                    "x": {"type": "string", "description": "x column (line/bar)."},
                    "y": {"type": "string", "description": "y column (line/bar)."},
                    "color": {"type": "string", "description": "series column (grouped_bar)."},
                    "names": {"type": "string", "description": "label column (donut)."},
                    "values": {"type": "string", "description": "value column (donut)."},
                    "y_format": {
                        "type": "string",
                        "enum": ["currency", "number", "percent"],
                        "description": "How to format the y-axis and hover "
                        "(line/bar): 'currency' for money ($1.6M), 'percent', "
                        "or 'number' for counts. Set this whenever y is money.",
                    },
                    "highlight_x": {
                        "type": ["string", "number"],
                        "description": "Optional x value to spotlight with a "
                        "coral marker (line only) -- e.g. the month of a dip "
                        "you're explaining, to draw the eye to it.",
                    },
                },
                "required": ["result_index", "kind", "title"],
            },
            "table": {
                "type": "object",
                "description": "Optional supporting table bound to a run_sql result.",
                "properties": {
                    "result_index": {"type": "integer"},
                    "title": {"type": "string"},
                },
                "required": ["result_index"],
            },
            "recommended_actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "Imperative, specific, parameterized "
                            "from the actual data in this answer -- never a "
                            "generic truism.",
                        },
                        "why": {
                            "type": "string",
                            "description": "One sentence tying it to evidence "
                            "from THIS answer (the same numbers/segment names "
                            "already cited). Omit for mode='off_topic'.",
                        },
                        "expected_impact": {
                            "type": "string",
                            "description": "Order-of-magnitude estimate when "
                            "derivable from the data, phrased as an estimate "
                            "(e.g. 'Est. annual value ~$180K'). Omit rather "
                            "than invent one.",
                        },
                        "effort": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "description": "Rough proxy for what to tackle first.",
                        },
                    },
                    "required": ["action"],
                },
                "description": "1-3 advisor-grade recommendations for "
                "mode='answer' (see the system prompt's quality bar: sorted "
                "by impact-to-effort, evidence-backed, root cause not "
                "symptom); 1-2 generic efficiency nudges (action only) for "
                "mode='off_topic'.",
            },
            "follow_up_questions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "0-3 SHORT follow-up QUESTIONS the user could ask "
                "next that YOU can answer from THIS company's database -- e.g. "
                "'Break this down by category', 'Which customers are affected?', "
                "'Compare this to last month'. These become one-tap suggestions "
                "in the input box, so each must be a data question you could "
                "actually run a query for. NEVER include an action that needs an "
                "external system or real-world execution (sending email, "
                "launching a campaign, spending budget, contacting people) -- "
                "those belong in recommended_actions, not here, because the app "
                "would send this text straight back to you as a question. Phrase "
                "them in the user's language. Omit entirely if nothing fits.",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "Your confidence in this answer: 'high' when the "
                "semantic layer directly defines the metric and the data is "
                "complete; 'medium' when you had to combine/derive it or the "
                "sample is small; 'low' when the data is sparse, ambiguous, or "
                "you had to guess at intent.",
            },
            "evidence": {
                "type": "object",
                "description": "Trust-layer metadata about how this answer was "
                "grounded -- shown to the user in a collapsible 'Evidence' "
                "section. Optional, but include it whenever you ran a query.",
                "properties": {
                    "semantic_definitions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Name(s) of the semantic-layer metric(s) "
                        "(from get_semantic_layer) you actually applied, e.g. "
                        "['revenue', 'vip_customers'].",
                    },
                    "date_range": {
                        "type": "object",
                        "description": "The date range your query covered.",
                        "properties": {
                            "start": {"type": "string", "description": "e.g. '2025-06-01'."},
                            "end": {"type": "string", "description": "e.g. '2026-05-31'."},
                        },
                    },
                    "filters_applied": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Human-readable filters your SQL applied, "
                        "e.g. [\"status = 'completed'\", \"segment = 'VIP'\"].",
                    },
                    "assumptions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Any assumption you had to make that the "
                        "data did not state outright (e.g. 'treated NULL channel "
                        "as Direct'). Shown to the user verbatim. Omit when there "
                        "were none -- never invent one.",
                    },
                    "resolved_interpretation": {
                        "type": "array",
                        "description": "How you read an otherwise-ambiguous part of "
                        "the question -- the interpretation you APPLIED, whether "
                        "from the governed config or a resolved clarification. Each "
                        "item is a short {label, value} pair shown to the user so "
                        "they can verify it (e.g. {'label': 'Quarter type', 'value': "
                        "'Fiscal'}, {'label': 'Timezone', 'value': 'Asia/Jerusalem'}). "
                        "Phrase both in the user's language. Omit when nothing was "
                        "ambiguous.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "value": {"type": "string"},
                            },
                            "required": ["label", "value"],
                        },
                    },
                },
            },
        },
        "required": ["mode", "insight_text"],
    },
}

VALID_MODES = ("answer", "clarification", "cannot_answer", "off_topic", "access_denied")
# Modes that must never carry analytical furniture (KPI cards, charts, tables,
# confidence badges, evidence). Enforced server-side in _apply_mode_policy so a
# model slip can't render a confident-looking card on an unanswered question.
NON_ANSWER_MODES = ("clarification", "cannot_answer", "off_topic", "access_denied")


def _empty_response() -> dict:
    return {
        "mode": "answer",
        "reason_code": None,
        "clarification_options": [],
        "missing": None,
        "summary": None,
        "insight_text": "",
        "kpis": [],
        "charts": [],
        "table": None,
        "table_title": None,
        "recommended_actions": [],
        "follow_up_questions": [],
        "sql_used": None,
        "confidence": None,
        "evidence": None,
    }


def _df_at(tools, index) -> pd.DataFrame | None:
    """Fetch the DataFrame from the run_sql result at `index`, safely."""
    try:
        i = int(index)
    except (TypeError, ValueError):
        return None
    if 0 <= i < len(tools.results):
        return tools.results[i]["df"]
    return None


def _database_name() -> str | None:
    """The database this client's queries actually ran against. Name only --
    never host, user or password, which must not reach the UI."""
    try:
        from sema_core.db import _db_name

        return _db_name(active_client_id())
    except Exception:
        return None  # unavailable -> the UI omits it rather than guessing


def tables_in_sql(sql: str) -> list[str]:
    """Public alias -- the agent loop uses this to name real data sources in
    progress events while a run is still in flight."""
    return _tables_in(sql)


def _tables_in(sql: str) -> list[str]:
    """Real table names referenced by one SQL statement -- excludes CTE
    aliases (a `WITH x AS (...)` name isn't a real table). Best-effort:
    unparsable SQL yields no tables rather than raising, since this is
    metadata for the trust panel, not a safety gate (the SQL was already
    validated by safety.py before it ran)."""
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except Exception:
        return []
    cte_names = set()
    tables: list[str] = []
    for statement in statements:
        if statement is None:
            continue
        for cte in statement.find_all(exp.CTE):
            if cte.alias:
                cte_names.add(cte.alias.lower())
        for table in statement.find_all(exp.Table):
            name = table.name
            if name and name.lower() not in cte_names and name not in tables:
                tables.append(name)
    return tables


def _parse_date(s) -> date | None:
    """Best-effort ISO-date parse. None (not an error) for anything that
    isn't a clean YYYY-MM-DD -- the model is asked for that format but isn't
    guaranteed to comply, and a caveat is worth skipping, not worth crashing
    over."""
    if not isinstance(s, str) or not s.strip():
        return None
    try:
        return datetime.fromisoformat(s.strip()).date()
    except ValueError:
        return None


def _knowledge_caveats(clean_date_range: dict | None) -> list[str]:
    """Deterministic, server-computed caveats when the answer's date range
    overlaps a known incident (knowledge.yaml, type="incident").

    Unlike `assumptions` above, this is NEVER something the model reports --
    it's computed here from data the model doesn't control, so an incident
    can't be reasoned away by omission the way a self-reported assumption
    could be. Silently adds nothing when there's no date range, it doesn't
    parse, or no incident overlaps -- this is a bonus caveat, not a
    correctness gate.
    """
    if not clean_date_range:
        return []
    start = _parse_date(clean_date_range.get("start"))
    end = _parse_date(clean_date_range.get("end"))
    if start is None and end is None:
        return []
    range_start, range_end = start or end, end or start

    caveats: list[str] = []
    for item in load_knowledge(active_client_id()):
        if item.get("type") != "incident" or item.get("status") == "deprecated":
            continue
        dr = item.get("date_range") or {}
        inc_start = _parse_date(dr.get("start"))
        inc_end = _parse_date(dr.get("end"))
        if inc_start is None and inc_end is None:
            continue
        inc_start, inc_end = inc_start or inc_end, inc_end or inc_start
        if inc_start <= range_end and range_start <= inc_end:
            caveats.append(
                f"{item.get('name', 'Incident')} ({dr.get('start', '?')} to "
                f"{dr.get('end', '?')}) overlaps this period -- {item.get('description', '')}".strip()
            )
    return caveats


def _clean_evidence(raw: dict | None, tools) -> dict | None:
    """Build the trust-layer evidence dict for one answer.

    `semantic_definitions`/`date_range`/`filters_applied` are the model's own
    self-report (from present_answer's optional `evidence` field) -- they
    reflect the model's reasoning, which only the model has access to.
    `data_freshness`/`records_used`/`data_sources` are computed HERE from
    `tools.results` (the actual executed SQL and its row counts), independent
    of anything the model claims, so those three fields can't be hallucinated.

    Returns None when no query ran and the model reported nothing either --
    there's no evidence to show for a pure-prose answer.
    """
    raw = raw or {}
    results = getattr(tools, "results", None) or []
    if not raw and not results:
        return None

    date_range = raw.get("date_range")
    data_sources: set[str] = set()
    for r in results:
        data_sources.update(_tables_in(r.get("sql", "")))

    failures = list(getattr(tools, "failures", None) or [])
    # Factual execution status -- "ok" only if a query actually ran and
    # returned. Never claim verification when nothing was executed.
    if results:
        status = "ok"
    elif failures:
        status = "failed"
    else:
        status = "none"

    clean_date_range = (
        {"start": date_range.get("start"), "end": date_range.get("end")}
        if isinstance(date_range, dict)
        else None
    )

    return {
        "semantic_definitions": list(raw.get("semantic_definitions", [])),
        "date_range": clean_date_range,
        "filters_applied": list(raw.get("filters_applied", [])),
        "data_sources": sorted(data_sources),
        # The connection the tables actually came from. Resolved from the real
        # per-client DB config -- shown only when a query ran, so it can never
        # imply a source that wasn't touched.
        "data_engine": "PostgreSQL" if results else None,
        "database": _database_name() if results else None,
        # NOTE: this is when the backing query RAN, not when the warehouse last
        # refreshed -- SEMA has no refresh signal, so the UI labels it as such
        # rather than implying a freshness it cannot know.
        "data_freshness": datetime.now(timezone.utc).isoformat(),
        "records_used": sum(len(r["df"]) for r in results if r.get("df") is not None),
        "query_status": status,
        "queries_run": len(results),
        "queries_failed": len(failures),
        # Model self-report, same trust level as filters_applied, PLUS any
        # deterministic incident-overlap caveats appended after it (see
        # _knowledge_caveats) -- those are server-computed from knowledge.yaml,
        # never something the model could hallucinate away by omitting it.
        "assumptions": [
            a.strip() for a in (raw.get("assumptions") or []) if isinstance(a, str) and a.strip()
        ] + _knowledge_caveats(clean_date_range) + stale_source_caveat(data_sources, active_client_id()),
        # How an ambiguous part of the question was read (governed default or
        # resolved clarification). Model self-report, kept only as clean
        # {label, value} string pairs so a malformed entry can't reach the UI.
        "resolved_interpretation": _clean_interpretation(raw.get("resolved_interpretation")),
    }


def _clean_interpretation(raw) -> list[dict]:
    """Keep only well-formed {label, value} string pairs from the model's
    resolved_interpretation self-report -- so the trust panel never renders a
    half-empty or wrongly-typed row."""
    out: list[dict] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        value = item.get("value")
        if isinstance(label, str) and label.strip() and isinstance(value, str) and value.strip():
            out.append({"label": label.strip(), "value": value.strip()})
    return out


def _analysis_steps(resp: dict, tools) -> list[dict]:
    """What actually happened, as STRUCTURED operations -- never prose.

    Each entry is {"op": <key>, ...params}: the client renders the sentence in
    the user's language, exactly like progress stages. Emitting English strings
    here would make a Hebrew answer's trust panel read in English.

    Every entry is backed by something observable: a semantic metric the model
    cited, a filter it reported, tables parsed out of the executed SQL, real
    row counts, and widgets actually bound to a result.
    """
    ev = resp.get("evidence") or {}
    results = _executed_results(tools)
    steps: list[dict] = []

    for metric in ev.get("semantic_definitions", []):
        steps.append({"op": "metric", "name": metric})

    dr = ev.get("date_range") or {}
    if dr.get("start") or dr.get("end"):
        steps.append({"op": "date_range", "start": dr.get("start"), "end": dr.get("end")})

    for f in ev.get("filters_applied", []):
        steps.append({"op": "filter", "value": f})

    if results:
        steps.append(
            {"op": "queries", "count": len(results), "sources": ev.get("data_sources") or []}
        )
        steps.append({"op": "rows", "count": ev.get("records_used", 0)})

    # A delta only exists when the model computed one against a baseline, so
    # this is evidence of a real comparison rather than an assumed one.
    if any(k.get("delta") is not None for k in resp.get("kpis", [])):
        steps.append({"op": "comparison"})

    for spec in resp.get("charts", []):
        by = spec.get("x") or spec.get("names")
        if by:
            steps.append({"op": "breakdown", "by": by})

    if resp.get("table") is not None:
        steps.append({"op": "table_rows", "count": len(resp["table"])})

    failed = ev.get("queries_failed") or 0
    if failed:
        steps.append({"op": "failed_queries", "count": failed})

    return steps


def _coerce_scalar(v):
    """DataFrame cell -> plain Python scalar (numpy ints/floats, Decimals) so
    the API layer can JSON-encode it like any model-typed value."""
    if hasattr(v, "item"):  # numpy scalar
        v = v.item()
    if isinstance(v, Decimal):
        v = float(v)
    return v


_UNBOUND = object()  # sentinel: binding absent or unresolvable


def _bound_kpi_value(raw: dict, tools):
    """Resolve a KPI's (result_index, column, row) binding against the actual
    run_sql results. Returns _UNBOUND when the KPI has no binding or the
    reference doesn't resolve (bad index/column/row)."""
    if "result_index" not in raw or not raw.get("column"):
        return _UNBOUND
    df = _df_at(tools, raw["result_index"])
    if df is None or raw["column"] not in df.columns:
        return _UNBOUND
    try:
        row = int(raw.get("row", 0))
    except (TypeError, ValueError):
        return _UNBOUND
    if not 0 <= row < len(df):
        return _UNBOUND
    return _coerce_scalar(df[raw["column"]].iloc[row])


def _values_differ(model_value, sql_value) -> bool:
    """True when the model-typed value meaningfully differs from the SQL one.
    Numeric comparison uses a 1% relative tolerance so ordinary model rounding
    (9.07 -> 9.1) doesn't spam the mismatch log; real transcription errors do."""
    try:
        a, b = float(model_value), float(sql_value)
    except (TypeError, ValueError):
        return str(model_value) != str(sql_value)
    return not math.isclose(a, b, rel_tol=0.01, abs_tol=1e-9)


def _clean_kpi(raw: dict, tools) -> dict:
    kpi = {
        "label": raw.get("label", ""),
        "value": raw.get("value", ""),
        "format": raw.get("format", "text"),
    }

    # KPI data binding: when the model bound this KPI to a run_sql result,
    # the value shown to the user is read from the ACTUAL query result --
    # the model-typed `value` is only a fallback for unbound KPIs. A model
    # transcription error therefore can't reach the screen; it's logged.
    sql_value = _bound_kpi_value(raw, tools)
    if sql_value is not _UNBOUND:
        if _values_differ(kpi["value"], sql_value):
            log_event(
                logger,
                "kpi_value_mismatch",
                label=kpi["label"],
                model_value=kpi["value"],
                sql_value=sql_value,
                result_index=raw.get("result_index"),
                column=raw.get("column"),
                row=raw.get("row", 0),
            )
        kpi["value"] = sql_value

    if "delta" in raw and raw["delta"] is not None:
        kpi["delta"] = raw["delta"]
        kpi["delta_label"] = raw.get("delta_label", "")
    return kpi


_VALID_EFFORT = ("low", "medium", "high")


def _clean_action(raw) -> dict | None:
    """Validate one recommended_actions entry into the structured
    {action, why, expected_impact, effort} shape. `raw` is normally the
    object the model returned, but a model that ignores the schema and sends
    a bare string is still accepted (as `action` with no why/impact/effort)
    rather than dropped -- a slightly under-filled recommendation beats
    silently losing it. Returns None for an entry with no usable `action`
    text, so a truly empty/malformed item never reaches the API as a blank
    card."""
    if isinstance(raw, str):
        raw = {"action": raw}
    if not isinstance(raw, dict):
        return None
    action = raw.get("action")
    if not isinstance(action, str) or not action.strip():
        return None
    why = raw.get("why")
    impact = raw.get("expected_impact")
    effort = raw.get("effort")
    return {
        "action": action.strip(),
        "why": why.strip() if isinstance(why, str) and why.strip() else None,
        "expected_impact": impact.strip() if isinstance(impact, str) and impact.strip() else None,
        "effort": effort if effort in _VALID_EFFORT else None,
    }


def _executed_results(tools) -> list:
    """The run_sql results this answer could be grounded in."""
    return list(getattr(tools, "results", None) or [])


def _apply_mode_policy(resp: dict, tools) -> dict:
    """Deterministic grounding gate, applied AFTER the model has spoken.

    The model proposes a mode; this decides whether the evidence actually
    supports it. Self-reported confidence is deliberately NOT a factor -- the
    signals here are observable facts about what ran:

      * mode='answer' with no executed SQL      -> insufficient_grounding
      * mode='answer' with only empty results   -> empty_result

    Both downgrade to cannot_answer, so an ungrounded claim can never reach the
    user wearing a confidence badge. Non-answer modes get their analytical
    furniture stripped, since a KPI card or chart next to "I can't answer this"
    is exactly the false-confidence signal this flow exists to remove.

    Data-access-scope gate: if ANY run_sql call this turn was policy_blocked
    (tools.access_denied is set -- see sema_core.agent.tools), the mode is
    forced to 'access_denied' NO MATTER what the model claims. This is the
    "never trust the LLM" backstop for the whole feature -- a model that
    mislabels a blocked query, ignores the policy_blocked result, or answers
    from only the allowed part of a multi-metric question (silently dropping
    the blocked part) can never produce anything but this refusal. Deliberately
    blunt: a partial "answer" next to a blocked metric is exactly the silent-
    trim outcome this gate exists to prevent, so there's no partial-answer
    carve-out here. Fallback copy fills in whatever the model itself didn't
    already provide, so a cooperative model's own (better) phrasing still wins.
    """
    denied = getattr(tools, "access_denied", None)
    if denied:
        resp["mode"] = "access_denied"
        resp["reason_code"] = "data_scope_blocked"
        # Fallback copy for when the model didn't cooperate (didn't call
        # present_answer with mode='access_denied' itself, or left insight_text
        # empty) -- combines the blocked-topic reason and the "what you CAN
        # ask about" summary into one message. follow_up_questions is left
        # alone: it holds concrete, tappable QUESTIONS, and a category summary
        # like "You can ask about Sales topics" isn't one -- only a
        # cooperating model (guided by the scope context) can offer real
        # alternative questions there.
        if not resp.get("insight_text"):
            reason = denied.get("reason", "That's outside your data access.")
            can_ask = denied.get("can_ask_about")
            resp["insight_text"] = f"{reason} {can_ask}".strip() if can_ask else reason
        resp["missing"] = None

    results = _executed_results(tools)
    ran_sql = len(results) > 0
    any_rows = any(
        r.get("df") is not None and not r["df"].empty for r in results
    )

    if resp["mode"] == "answer":
        if not ran_sql:
            resp["mode"] = "cannot_answer"
            resp["reason_code"] = "insufficient_grounding"
            resp["missing"] = resp["missing"] or (
                "No query was executed, so there is no data behind this answer."
            )
        elif not any_rows:
            resp["mode"] = "cannot_answer"
            resp["reason_code"] = "empty_result"
            resp["missing"] = resp["missing"] or (
                "The query ran but returned no rows for the requested scope."
            )

    if resp["mode"] in NON_ANSWER_MODES:
        # No analytical furniture and no trust signals on a non-answer. The
        # executive summary belongs to that furniture: an "In short" takeaway
        # above a question we did NOT answer is exactly the false-confidence
        # signal this gate exists to remove.
        resp["summary"] = None
        resp["kpis"] = []
        resp["charts"] = []
        resp["table"] = None
        resp["table_title"] = None
        resp["confidence"] = None
        resp["evidence"] = None
        if resp["mode"] != "cannot_answer":
            # Clarification never runs speculative SQL, and off-topic must not
            # touch business tools at all -- so neither shows a query.
            resp["sql_used"] = None
        if resp["mode"] == "off_topic":
            resp["reason_code"] = "off_topic"
            # recommended_actions and follow_up_questions DO pass through for
            # off_topic (the witty-redirect-plus-value flow) -- only the
            # analytical furniture above (KPIs/charts/table/confidence/
            # evidence) is nonsensical for a non-answer and stays stripped.
    else:
        resp["clarification_options"] = []

    if resp["mode"] != "clarification":
        resp["clarification_options"] = []

    log_event(
        logger,
        "response_mode",
        client_id=active_client_id(),
        mode=resp["mode"],
        reason_code=resp["reason_code"],
        tools_executed=ran_sql,
        sql_statements=len(results),
        returned_rows=any_rows,
        # Whether the model cited a semantic-layer metric it actually applied.
        semantic_match=bool((resp.get("evidence") or {}).get("semantic_definitions")),
    )
    return resp


def build_response(tool_input: dict, tools) -> dict:
    """Turn a present_answer payload into the UI's response dict."""
    resp = _empty_response()

    mode = tool_input.get("mode")
    resp["mode"] = mode if mode in VALID_MODES else "answer"
    reason = tool_input.get("reason_code")
    resp["reason_code"] = reason if isinstance(reason, str) and reason else None
    missing = tool_input.get("missing")
    resp["missing"] = missing.strip() if isinstance(missing, str) and missing.strip() else None
    resp["clarification_options"] = [
        o.strip()
        for o in (tool_input.get("clarification_options") or [])
        if isinstance(o, str) and o.strip()
    ][:4]
    # Executive summary shown above the answer. Whitespace-only is treated as
    # absent so the UI never renders an empty tinted block.
    summary = tool_input.get("summary")
    resp["summary"] = summary.strip() if isinstance(summary, str) and summary.strip() else None
    resp["insight_text"] = tool_input.get("insight_text", "")
    resp["recommended_actions"] = [
        a for a in (_clean_action(raw) for raw in tool_input.get("recommended_actions", [])) if a
    ]
    # Answerable follow-up questions -- kept only if they're non-empty strings;
    # the agent is instructed to omit execution actions here (see the tool
    # schema), and the frontend applies a final safety filter.
    resp["follow_up_questions"] = [
        q.strip() for q in tool_input.get("follow_up_questions", []) if isinstance(q, str) and q.strip()
    ]
    resp["kpis"] = [_clean_kpi(k, tools) for k in tool_input.get("kpis", [])]

    chart = tool_input.get("chart")
    if isinstance(chart, dict) and "result_index" in chart:
        df = _df_at(tools, chart["result_index"])
        if df is not None and not df.empty:
            kind = chart.get("kind", "bar")
            x_col = chart.get("x")
            # Deterministic safety net: a bar/grouped_bar chart whose x-axis
            # is actually a time/period sequence gets coerced to a line chart
            # regardless of what the model picked -- see _looks_like_date_axis.
            # 'donut' is never coerced (it has no x-axis concept at all).
            if kind in ("bar", "grouped_bar") and _looks_like_date_axis(df, x_col):
                log_event(
                    logger, "chart_kind_coerced",
                    from_kind=kind, to_kind="line", x_column=x_col,
                )
                kind = "line"
            spec = {"kind": kind, "df": df, "title": chart.get("title", "")}
            for key in ("x", "y", "color", "names", "values", "y_format", "highlight_x"):
                if chart.get(key) is not None:
                    spec[key] = chart[key]
            resp["charts"].append(spec)

    table = tool_input.get("table")
    if isinstance(table, dict) and "result_index" in table:
        df = _df_at(tools, table["result_index"])
        if df is not None and not df.empty:
            # Pass the FULL result through. It is already bounded by the SQL
            # safety layer's row cap (SEMA_ROW_LIMIT), and the UI paginates --
            # so a "list all 406 VIP customers" answer must not be silently
            # cut to a preview here.
            resp["table"] = df
            resp["table_title"] = table.get("title", "Result")

    # Surface the SQL the agent actually ran (for the UI's "View SQL" trust
    # feature). Joined when several queries were run to build the answer.
    if getattr(tools, "results", None):
        resp["sql_used"] = ";\n\n".join(r["sql"] for r in tools.results if r.get("sql"))

    resp["confidence"] = tool_input.get("confidence")
    resp["evidence"] = _clean_evidence(tool_input.get("evidence"), tools)
    if resp["evidence"] is not None:
        resp["evidence"]["analysis_steps"] = _analysis_steps(resp, tools)

    return _apply_mode_policy(resp, tools)
