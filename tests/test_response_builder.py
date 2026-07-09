"""
Item 10: response.build_response -- binding charts/tables to run_sql results
by result_index, out-of-range indices, and missing optional fields.
"""

from __future__ import annotations

import pandas as pd

from agent.response import build_response


class FakeTools:
    """Stand-in for AgentTools: just carries the results list."""

    def __init__(self, dfs: list[pd.DataFrame]):
        self.results = [{"sql": f"SELECT {i}", "df": df} for i, df in enumerate(dfs)]


def _df(n: int = 3) -> pd.DataFrame:
    return pd.DataFrame({"month": [f"2026-0{i+1}" for i in range(n)], "revenue": range(n)})


def test_chart_bound_by_result_index():
    tools = FakeTools([_df(2), _df(5)])
    resp = build_response(
        {
            "insight_text": "hi",
            "recommended_actions": ["a"],
            "chart": {"result_index": 1, "kind": "line", "title": "Trend", "x": "month", "y": "revenue"},
        },
        tools,
    )
    assert len(resp["charts"]) == 1
    assert len(resp["charts"][0]["df"]) == 5  # bound to the SECOND result
    assert resp["charts"][0]["kind"] == "line"


def test_out_of_range_index_yields_no_chart_or_table():
    tools = FakeTools([_df()])
    resp = build_response(
        {
            "insight_text": "hi",
            "recommended_actions": [],
            "chart": {"result_index": 99, "kind": "bar", "title": "x"},
            "table": {"result_index": -1},
        },
        tools,
    )
    assert resp["charts"] == []
    assert resp["table"] is None


def test_missing_optional_fields_still_builds():
    resp = build_response({"insight_text": "only text", "recommended_actions": []}, FakeTools([]))
    assert resp["insight_text"] == "only text"
    assert resp["kpis"] == []
    assert resp["charts"] == []
    assert resp["table"] is None
    assert resp["sql_used"] is None


def test_table_bound_and_sql_used_joined():
    tools = FakeTools([_df(20), _df(2)])
    resp = build_response(
        {
            "insight_text": "t",
            "recommended_actions": [],
            "table": {"result_index": 0, "title": "Top rows"},
        },
        tools,
    )
    assert len(resp["table"]) == 15  # head(15) cap
    assert resp["table_title"] == "Top rows"
    assert resp["sql_used"] == "SELECT 0;\n\nSELECT 1"
