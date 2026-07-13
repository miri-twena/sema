"""
Item 10: serialize.to_chat_response -- DataFrame -> {columns, rows} with
JSON-safe dates and Decimals, chart/table mapping, error-free defaults.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pandas as pd

from api.serialize import to_chat_response


def _resp_dict(**overrides) -> dict:
    base = {
        "insight_text": "answer",
        "kpis": [],
        "charts": [],
        "table": None,
        "table_title": None,
        "recommended_actions": [],
    }
    base.update(overrides)
    return base


def test_table_dates_and_decimals_are_json_safe():
    df = pd.DataFrame(
        {
            "month": [dt.date(2026, 3, 1)],
            "revenue": [Decimal("1234.56")],
        }
    )
    out = to_chat_response(_resp_dict(table=df, table_title="Rev"))
    assert out.table is not None
    assert out.table.columns == ["month", "revenue"]
    row = out.table.rows[0]
    assert isinstance(row["month"], str) and row["month"].startswith("2026-03-01")
    assert float(row["revenue"]) == 1234.56


def test_chart_spec_maps_to_contract():
    df = pd.DataFrame({"month": ["2026-01"], "revenue": [10]})
    out = to_chat_response(
        _resp_dict(
            charts=[{"kind": "line", "df": df, "title": "Trend", "x": "month", "y": "revenue", "y_format": "currency"}]
        )
    )
    assert out.chart is not None
    assert out.chart.kind == "line"
    assert out.chart.columns == ["month", "revenue"]
    assert out.chart.rows == [{"month": "2026-01", "revenue": 10}]


def test_empty_response_serializes_clean():
    out = to_chat_response(_resp_dict())
    assert out.answer == "answer"
    assert out.chart is None and out.table is None
    assert out.status == "ok"


def test_kpis_and_actions_pass_through():
    out = to_chat_response(
        _resp_dict(
            kpis=[{"label": "AOV", "value": 52.3, "format": "currency"}],
            recommended_actions=["Do X", "Do Y"],
            sql_used="SELECT 1",
        )
    )
    assert out.kpis[0].label == "AOV"
    assert out.actions == ["Do X", "Do Y"]
    assert out.sql_used == "SELECT 1"


def test_confidence_and_evidence_map_to_contract():
    out = to_chat_response(
        _resp_dict(
            confidence="medium",
            evidence={
                "semantic_definitions": ["revenue"],
                "date_range": {"start": "2025-06-01", "end": "2026-05-31"},
                "filters_applied": ["status = 'completed'"],
                "data_freshness": "2026-07-13T10:00:00+00:00",
                "records_used": 42,
            },
        )
    )
    assert out.confidence == "medium"
    assert out.evidence is not None
    assert out.evidence.semantic_definitions == ["revenue"]
    assert out.evidence.date_range.start == "2025-06-01"
    assert out.evidence.date_range.end == "2026-05-31"
    assert out.evidence.filters_applied == ["status = 'completed'"]
    assert out.evidence.records_used == 42


def test_missing_confidence_and_evidence_default_none():
    out = to_chat_response(_resp_dict())
    assert out.confidence is None
    assert out.evidence is None
