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
    assert resp["follow_up_questions"] == []  # defaults to empty, never missing


def test_follow_up_questions_cleaned():
    resp = build_response(
        {
            "insight_text": "t",
            "recommended_actions": [],
            "follow_up_questions": ["  Break this down by category  ", "", "   ", "Which customers?"],
        },
        FakeTools([]),
    )
    # Trimmed, and blank entries dropped.
    assert resp["follow_up_questions"] == ["Break this down by category", "Which customers?"]


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
    assert len(resp["table"]) == 20  # full result: no display-side cap
    assert resp["table_title"] == "Top rows"
    assert resp["sql_used"] == "SELECT 0;\n\nSELECT 1"


def test_table_is_not_truncated_for_large_results():
    """A "list all 406 customers" answer must reach the UI whole -- the SQL
    safety cap is the only thing allowed to bound a result set."""
    tools = FakeTools([_df(406)])
    resp = build_response(
        {"insight_text": "t", "recommended_actions": [], "table": {"result_index": 0, "title": "VIPs"}},
        tools,
    )
    assert len(resp["table"]) == 406


# --- KPI data binding ---------------------------------------------------------
def _kpi_input(**kpi) -> dict:
    return {"insight_text": "t", "recommended_actions": [], "kpis": [{"label": "Rev", "format": "currency", **kpi}]}


def test_bound_kpi_reads_value_from_sql_result():
    df = pd.DataFrame({"revenue": [824068.05, 979975.44]})
    tools = FakeTools([df])
    resp = build_response(_kpi_input(value=999999, result_index=0, column="revenue", row=1), tools)
    assert resp["kpis"][0]["value"] == 979975.44  # SQL value wins over the model's 999999


def test_bound_kpi_mismatch_is_logged(caplog):
    import logging

    df = pd.DataFrame({"revenue": [824068.05]})
    with caplog.at_level(logging.INFO, logger="sema.agent"):
        build_response(_kpi_input(value=999999, result_index=0, column="revenue"), FakeTools([df]))
    assert any("kpi_value_mismatch" in r.message for r in caplog.records)


def test_bound_kpi_close_value_not_logged(caplog):
    import logging

    df = pd.DataFrame({"rate": [9.07]})
    with caplog.at_level(logging.INFO, logger="sema.agent"):
        resp = build_response(_kpi_input(value=9.1, result_index=0, column="rate"), FakeTools([df]))
    # Ordinary model rounding: SQL value still wins, but no mismatch noise.
    assert resp["kpis"][0]["value"] == 9.07
    assert not any("kpi_value_mismatch" in r.message for r in caplog.records)


def test_unresolvable_binding_falls_back_to_model_value():
    df = pd.DataFrame({"revenue": [1.0]})
    tools = FakeTools([df])
    for bad in (
        {"result_index": 99, "column": "revenue"},  # index out of range
        {"result_index": 0, "column": "nope"},  # unknown column
        {"result_index": 0, "column": "revenue", "row": 5},  # row out of range
    ):
        resp = build_response(_kpi_input(value=42, **bad), tools)
        assert resp["kpis"][0]["value"] == 42


def test_unbound_kpi_unchanged():
    # A result must exist or the grounding gate downgrades to cannot_answer and
    # strips the cards; the point here is that an UNBOUND kpi keeps its value.
    resp = build_response(_kpi_input(value=52.3), FakeTools([_df()]))
    assert resp["kpis"][0]["value"] == 52.3


def test_bound_kpi_numpy_value_coerced_to_python():
    df = pd.DataFrame({"orders": [1191]})  # int64 column
    resp = build_response(_kpi_input(value=1191, result_index=0, column="orders"), FakeTools([df]))
    assert type(resp["kpis"][0]["value"]) is int  # not numpy.int64 -- JSON-safe


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
