"""
GET /api/brief: the home dashboard's Daily Brief route.

Route tests monkeypatch build_brief (the same pattern test_api_overview.py uses
with build_overview); the insight math itself is covered in test_brief.py. No
live DB, API key, or model call is needed.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import api.main as main
from sema_core import client_registry


def _fake_brief(**over) -> dict:
    data = {
        "period": {"start": "2026-06", "end": "2026-06"},
        "comparison_period": {"start": "2026-05", "end": "2026-05"},
        "comparison_available": True,
        "unavailable_reason": None,
        "insights": [
            {
                "id": "orders-2026-06-2026-06",
                "metric": "orders",
                "metric_label": "Orders",
                "headline": "Orders up 30.2%",
                "detail": "Orders rose 30.2% in Jun 2026, compared with May 2026.",
                "current_value": 1951.0,
                "previous_value": 1498.0,
                "change_pct": 30.2,
                "direction": "up",
                "sentiment": "positive",
                "value_format": "number",
                "rank_score": 30.2,
                "importance": "high",
                "follow_up_question": "Which categories drove orders in Jun 2026?",
                "period": {"start": "2026-06", "end": "2026-06"},
                "comparison_period": {"start": "2026-05", "end": "2026-05"},
            }
        ],
    }
    data.update(over)
    return data


def test_unknown_client_returns_404():
    with pytest.raises(HTTPException) as excinfo:
        main.brief(client_id="ghost-tenant")
    assert excinfo.value.status_code == 404


def test_brief_maps_contract_fields(monkeypatch):
    monkeypatch.setattr(main, "build_brief", lambda start=None, end=None: _fake_brief())
    resp = main.brief()

    assert resp.client_id
    assert resp.as_of  # freshness stamp always present
    assert (resp.period.start, resp.period.end) == ("2026-06", "2026-06")
    assert resp.comparison_period is not None
    assert (resp.comparison_period.start, resp.comparison_period.end) == ("2026-05", "2026-05")
    assert resp.comparison_available is True

    insight = resp.insights[0]
    assert insight.metric == "orders"
    assert insight.change_pct == 30.2
    assert insight.direction == "up"
    assert insight.sentiment == "positive"
    assert insight.importance == "high"
    assert insight.follow_up_question.endswith("?")


def test_route_forwards_the_requested_window(monkeypatch):
    """The brief must receive the SAME start/end the overview route gets, or it
    would describe a different period than the KPI cards on screen."""
    seen = {}

    def spy(start=None, end=None):
        seen["window"] = (start, end)
        return _fake_brief(insights=[])

    monkeypatch.setattr(main, "build_brief", spy)
    main.brief(start="2026-03", end="2026-05")
    assert seen["window"] == ("2026-03", "2026-05")


def test_default_window_is_left_to_the_backend(monkeypatch):
    seen = {}

    def spy(start=None, end=None):
        seen["window"] = (start, end)
        return _fake_brief(insights=[])

    monkeypatch.setattr(main, "build_brief", spy)
    main.brief()
    assert seen["window"] == (None, None)


def test_no_comparison_window_is_reported_as_structured_metadata(monkeypatch):
    monkeypatch.setattr(
        main,
        "build_brief",
        lambda start=None, end=None: _fake_brief(
            comparison_period=None,
            comparison_available=False,
            unavailable_reason="insufficient_history",
            insights=[],
        ),
    )
    resp = main.brief()
    assert resp.insights == []
    assert resp.comparison_available is False
    assert resp.comparison_period is None
    assert resp.unavailable_reason == "insufficient_history"


def test_tenant_is_active_while_the_brief_is_built(monkeypatch):
    """The saved reports resolve the client from a ContextVar, so the override
    must be in place during build_brief -- otherwise one tenant's cached report
    could answer another tenant's request."""
    seen = {}

    def spy(start=None, end=None):
        seen["active"] = client_registry.active_client_id()
        return _fake_brief(insights=[])

    monkeypatch.setattr(main, "build_brief", spy)
    resp = main.brief(client_id="insurance")

    assert seen["active"] == "insurance"
    assert resp.client_id == "insurance"


def test_override_is_cleared_even_when_the_build_fails(monkeypatch):
    """A leaked override would silently mis-scope every later request on this
    thread."""

    def boom(start=None, end=None):
        raise RuntimeError("report unavailable")

    monkeypatch.setattr(main, "build_brief", boom)
    with pytest.raises(RuntimeError):
        main.brief(client_id="insurance")

    assert client_registry.active_client_id() != "insurance"
