"""
Item 10: response.build_response -- binding charts/tables to run_sql results
by result_index, out-of-range indices, and missing optional fields.
"""

from __future__ import annotations

import pandas as pd

from sema_core.agent.response import build_response


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


# --- trust layer: confidence + evidence -------------------------------------
def test_confidence_and_evidence_pass_through(monkeypatch):
    tools = FakeTools([_df(3)])
    resp = build_response(
        {
            "insight_text": "t",
            "recommended_actions": [],
            "confidence": "high",
            "evidence": {
                "semantic_definitions": ["revenue"],
                "date_range": {"start": "2025-06-01", "end": "2026-05-31"},
                "filters_applied": ["status = 'completed'"],
            },
        },
        tools,
    )
    assert resp["confidence"] == "high"
    assert resp["evidence"]["semantic_definitions"] == ["revenue"]
    assert resp["evidence"]["date_range"] == {"start": "2025-06-01", "end": "2026-05-31"}
    assert resp["evidence"]["filters_applied"] == ["status = 'completed'"]
    # Deterministic fields: computed from tools.results, not model-asserted.
    assert resp["evidence"]["records_used"] == 3
    assert resp["evidence"]["data_freshness"] is not None


def test_evidence_records_used_sums_across_queries():
    tools = FakeTools([_df(3), _df(5)])
    resp = build_response({"insight_text": "t", "recommended_actions": []}, tools)
    assert resp["evidence"]["records_used"] == 8


def test_evidence_none_when_no_query_and_no_model_report():
    resp = build_response({"insight_text": "prose only", "recommended_actions": []}, FakeTools([]))
    assert resp["confidence"] is None
    assert resp["evidence"] is None


def test_evidence_present_when_query_ran_even_without_model_report():
    # A query ran, so there's grounded evidence to show, even if the model
    # didn't self-report semantic_definitions/date_range/filters.
    tools = FakeTools([_df(4)])
    resp = build_response({"insight_text": "t", "recommended_actions": []}, tools)
    assert resp["evidence"] is not None
    assert resp["evidence"]["semantic_definitions"] == []
    assert resp["evidence"]["records_used"] == 4


def test_evidence_data_sources_parsed_from_executed_sql():
    class SqlTools:
        results = [
            {
                "sql": (
                    "WITH customer_revenue AS (SELECT customer_id, SUM(total_amount) AS revenue "
                    "FROM orders WHERE status = 'completed' GROUP BY customer_id) "
                    "SELECT c.customer_id, c.segment, cr.revenue FROM customers c "
                    "JOIN customer_revenue cr ON cr.customer_id = c.customer_id"
                ),
                "df": _df(2),
            }
        ]

    resp = build_response({"insight_text": "t", "recommended_actions": []}, SqlTools())
    # Real tables only, alphabetized -- the CTE name "customer_revenue" must
    # NOT appear, even though it's referenced via `FROM customer_revenue` in
    # the outer query.
    assert resp["evidence"]["data_sources"] == ["customers", "orders"]


def test_evidence_data_sources_dedupes_across_queries():
    class SqlTools:
        results = [
            {"sql": "SELECT * FROM orders", "df": _df(1)},
            {"sql": "SELECT * FROM orders o JOIN customers c ON c.customer_id = o.customer_id", "df": _df(1)},
        ]

    resp = build_response({"insight_text": "t", "recommended_actions": []}, SqlTools())
    assert resp["evidence"]["data_sources"] == ["customers", "orders"]


def test_evidence_data_sources_empty_on_unparsable_sql():
    class SqlTools:
        results = [{"sql": "not valid sql at all (((", "df": _df(1)}]

    resp = build_response({"insight_text": "t", "recommended_actions": []}, SqlTools())
    assert resp["evidence"]["data_sources"] == []


def test_evidence_missing_date_range_is_none():
    tools = FakeTools([_df(1)])
    resp = build_response(
        {
            "insight_text": "t",
            "recommended_actions": [],
            "evidence": {"semantic_definitions": ["aov"]},
        },
        tools,
    )
    assert resp["evidence"]["date_range"] is None
