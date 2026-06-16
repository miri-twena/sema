"""
SEMA agent: structured response assembler.

The agent finishes by calling a special `present_answer` tool. Instead of
executing like the data tools, that call carries the *structured* final
answer, which this module turns into the exact response dict the UI already
renders (the same shape insight_builder produces). That's how an agent
answer looks identical to a curated one -- chat.py can't tell them apart.

Accuracy guarantee: KPI numbers are small values the model read from query
previews, but CHARTS and TABLES are bound to real query results by index
(`result_index` into AgentTools.results) -- the model never re-types row
data, so a chart can't drift from the SQL that produced it.

No dependency on the Claude API key.
"""

from __future__ import annotations

import pandas as pd

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


def _clean_kpi(raw: dict) -> dict:
    kpi = {
        "label": raw.get("label", ""),
        "value": raw.get("value", ""),
        "format": raw.get("format", "text"),
    }
    if "delta" in raw and raw["delta"] is not None:
        kpi["delta"] = raw["delta"]
        kpi["delta_label"] = raw.get("delta_label", "")
    return kpi


def build_response(tool_input: dict, tools) -> dict:
    """Turn a present_answer payload into the UI's response dict."""
    resp = _empty_response()
    resp["insight_text"] = tool_input.get("insight_text", "")
    resp["recommended_actions"] = list(tool_input.get("recommended_actions", []))
    resp["kpis"] = [_clean_kpi(k) for k in tool_input.get("kpis", [])]

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

    return resp
