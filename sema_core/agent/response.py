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
from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
import sqlglot
from sqlglot import expressions as exp

from sema_core.obs import get_logger, log_event

logger = get_logger("agent")

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
            "insight_text": {
                "type": "string",
                "description": "The narrative answer in markdown. Lead with the "
                "direct answer and key numbers; quantify drivers.",
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
                "items": {"type": "string"},
                "description": "2-3 concrete next steps.",
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
                },
            },
        },
        "required": ["insight_text", "recommended_actions"],
    },
}


def _empty_response() -> dict:
    return {
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

    return {
        "semantic_definitions": list(raw.get("semantic_definitions", [])),
        "date_range": (
            {"start": date_range.get("start"), "end": date_range.get("end")}
            if isinstance(date_range, dict)
            else None
        ),
        "filters_applied": list(raw.get("filters_applied", [])),
        "data_sources": sorted(data_sources),
        "data_freshness": datetime.now(timezone.utc).isoformat(),
        "records_used": sum(len(r["df"]) for r in results if r.get("df") is not None),
    }


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


def build_response(tool_input: dict, tools) -> dict:
    """Turn a present_answer payload into the UI's response dict."""
    resp = _empty_response()
    resp["insight_text"] = tool_input.get("insight_text", "")
    resp["recommended_actions"] = list(tool_input.get("recommended_actions", []))
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
            spec = {"kind": chart.get("kind", "bar"), "df": df, "title": chart.get("title", "")}
            for key in ("x", "y", "color", "names", "values", "y_format", "highlight_x"):
                if chart.get(key) is not None:
                    spec[key] = chart[key]
            resp["charts"].append(spec)

    table = tool_input.get("table")
    if isinstance(table, dict) and "result_index" in table:
        df = _df_at(tools, table["result_index"])
        if df is not None and not df.empty:
            resp["table"] = df.head(15)
            resp["table_title"] = table.get("title", "Result")

    # Surface the SQL the agent actually ran (for the UI's "View SQL" trust
    # feature). Joined when several queries were run to build the answer.
    if getattr(tools, "results", None):
        resp["sql_used"] = ";\n\n".join(r["sql"] for r in tools.results if r.get("sql"))

    resp["confidence"] = tool_input.get("confidence")
    resp["evidence"] = _clean_evidence(tool_input.get("evidence"), tools)

    return resp
