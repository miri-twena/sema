"""
GET /api/brief: the home dashboard's two-layer (pulse + insights) Daily Brief
route. Route tests monkeypatch build_daily_brief (the same pattern
test_api_overview.py uses with build_overview); the generator/pulse math
itself is covered in test_daily_brief.py. No live DB, API key, or model call
is needed.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import api.main as main
from sema_core import client_registry


def _fake_daily_brief(**over) -> dict:
    data = {
        "as_of": "2026-06-30",
        "pulse": [
            {
                "metric": "revenue",
                "label": "Yesterday revenue",
                "value": 54885.0,
                "format": "currency",
                "spark": [41200.0, 39800.0] + [40000.0] * 12,
                "status": "above",
                "status_label": "+25% vs typical Tue",
            },
            {
                "metric": "orders",
                "label": "Orders",
                "value": 89.0,
                "format": "number",
                "spark": [80.0] * 14,
                "status": "normal",
                "status_label": "In normal range",
            },
        ],
        "insights": [
            {
                "kind": "campaign_negative_roi",
                "id": "campaign_negative_roi-1-2026-06-30",
                "icon": "warning",
                "headline": "Summer Sale campaign has run at negative ROI for 14 days",
                "detail": "Spend $8,400 against $6,100 attributed revenue since it started.",
                "severity": 27.4,
                "follow_up_question": "Why is the Summer Sale campaign underperforming?",
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
    monkeypatch.setattr(main, "build_daily_brief", lambda sensitivity="balanced": _fake_daily_brief())
    resp = main.brief()

    assert resp.client_id
    assert resp.as_of == "2026-06-30"

    revenue = resp.pulse[0]
    assert revenue.metric == "revenue"
    assert revenue.status == "above"
    assert len(revenue.spark) == 14

    insight = resp.insights[0]
    assert insight.kind == "campaign_negative_roi"
    assert insight.icon == "warning"
    assert insight.follow_up_question.endswith("?")


def test_no_start_end_params_are_accepted_or_needed():
    """The brief is not period-scoped -- it always describes "since
    yesterday", not a selectable month range."""
    import inspect

    params = inspect.signature(main.brief).parameters
    assert set(params) == {"client_id"}


def test_empty_insights_with_pulse_is_a_normal_quiet_day_response(monkeypatch):
    monkeypatch.setattr(main, "build_daily_brief", lambda sensitivity="balanced": _fake_daily_brief(insights=[]))
    resp = main.brief()
    assert resp.insights == []
    assert len(resp.pulse) == 2  # the pulse still has content on a quiet day


def test_fully_empty_response_when_there_is_no_data(monkeypatch):
    monkeypatch.setattr(
        main, "build_daily_brief", lambda sensitivity="balanced": {"as_of": None, "pulse": [], "insights": []}
    )
    resp = main.brief()
    assert resp.pulse == []
    assert resp.insights == []
    assert resp.as_of is None


def test_tenant_is_active_while_the_brief_is_built(monkeypatch):
    """The saved reports resolve the client from a ContextVar, so the override
    must be in place during build_daily_brief -- otherwise one tenant's cached
    report could answer another tenant's request."""
    seen = {}

    def spy(sensitivity="balanced"):
        seen["active"] = client_registry.active_client_id()
        return _fake_daily_brief(insights=[])

    monkeypatch.setattr(main, "build_daily_brief", spy)
    resp = main.brief(client_id="insurance")

    assert seen["active"] == "insurance"
    assert resp.client_id == "insurance"


def test_override_is_cleared_even_when_the_build_fails(monkeypatch):
    """A leaked override would silently mis-scope every later request on this
    thread."""

    def boom(sensitivity="balanced"):
        raise RuntimeError("report unavailable")

    monkeypatch.setattr(main, "build_daily_brief", boom)
    with pytest.raises(RuntimeError):
        main.brief(client_id="insurance")

    assert client_registry.active_client_id() != "insurance"
