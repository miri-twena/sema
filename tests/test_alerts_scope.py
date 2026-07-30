"""
sema_core.alerts_engine.filter_for_scope: dropping alerts outside a
requester's data-access scope (sema_core.data_scope). Pure function, tested
with synthetic alert dicts -- evaluate_all_alerts itself needs a live DB and
is exercised implicitly by the rest of the suite (e.g. via /api/alerts).
"""

from __future__ import annotations

from sema_core import alerts_engine


def _alert(alert_id: str, domain: str, sensitive: str | None = None) -> dict:
    return {
        "id": alert_id,
        "metric_label": alert_id,
        "alert_label": alert_id,
        "severity": "warning",
        "message": "x",
        "value": 1,
        "_domain": domain,
        "_sensitive": sensitive,
    }


ALERTS = [
    _alert("revenue_drop", "sales"),
    _alert("vip_churn", "customers"),
    _alert("campaign_roi_neg", "marketing"),
    _alert("margin_drop", "finance", sensitive="financials"),
]


def test_full_keeps_every_alert_and_strips_internal_keys():
    out = alerts_engine.filter_for_scope(ALERTS, "full")
    assert {a["id"] for a in out} == {a["id"] for a in ALERTS}
    assert all("_domain" not in a and "_sensitive" not in a for a in out)


def test_no_financials_drops_only_the_sensitive_alert():
    out = alerts_engine.filter_for_scope(ALERTS, "no_financials")
    assert {a["id"] for a in out} == {"revenue_drop", "vip_churn", "campaign_roi_neg"}


def test_sales_only_keeps_only_sales_domain_alerts():
    out = alerts_engine.filter_for_scope(ALERTS, "sales_only")
    assert {a["id"] for a in out} == {"revenue_drop"}


def test_custom_drops_everything():
    assert alerts_engine.filter_for_scope(ALERTS, "custom") == []
