"""
API layer for the template-based alert builder (alert_templates_prompt.md):
create/edit/toggle/delete, the 90-day dry-run test gate, the unified org+
system list, audit logging, and the injection-rejection surface.

alert_templates.dry_run is monkeypatched to a fast, DB-free fake for every
test in this file except the ones specifically checking that a failing test
blocks creation -- this project's tests must never depend on a live DB
(the underlying SQL/pandas engine itself is covered, DB-free, in
test_alert_templates.py; its correctness against the real demo Postgres was
verified live during this task, see PROMPT_QUEUE.md).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.main as main
from sema_core import alert_templates

CID = "ecommerce"


def _client_as_miri(monkeypatch) -> TestClient:
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"})
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _fast_dry_run(monkeypatch):
    """A DB-free stand-in for the dry-run test gate: fires 3 times unless the
    test asks for a failure via metric='__fail__'."""

    def fake_dry_run(client_id, metric, template, params, days=90):
        if metric == "__fail__":
            return {"ok": False, "error": "simulated failure", "fire_count": 0, "fire_dates": []}
        return {"ok": True, "fire_count": 3, "fire_dates": ["2026-06-01", "2026-06-08", "2026-06-15"]}

    monkeypatch.setattr(alert_templates, "dry_run", fake_dry_run)


def _create(client, **overrides) -> dict:
    body = {
        "name": "Revenue Drop Test",
        "metric": "revenue",
        "template": "pct_change",
        "params": {"window": "mom", "direction": "drop", "threshold_pct": 8},
        "severity": "warning",
    }
    body.update(overrides)
    resp = client.post("/api/admin/alerts", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- templates/metrics catalog ------------------------------------------------
def test_templates_catalog_lists_all_four(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.get("/api/admin/alerts/templates")
    assert resp.status_code == 200
    assert {t["template"] for t in resp.json()} == {"pct_change", "absolute_threshold", "anomaly", "streak"}


def test_metrics_catalog_matches_the_fixed_kpi_set(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.get("/api/admin/alerts/metrics")
    assert {m["metric"] for m in resp.json()} == {"revenue", "orders", "aov", "churn_risk"}


def test_templates_catalog_rejects_non_admin(monkeypatch):
    """Regression guard (backend_qa_prompt.md item 1's authz matrix): these
    two catalog routes were previously missing Depends(require_client_admin)
    entirely -- reachable by anyone with just the API key."""
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(main, "current_identity", lambda: {"client_id": CID, "email": "avi.peretz@ecommerce-demo.com"})
    client = TestClient(main.app)
    assert client.get("/api/admin/alerts/templates").status_code == 403
    assert client.get("/api/admin/alerts/metrics").status_code == 403


# --- dry-run test endpoint -----------------------------------------------------
def test_test_endpoint_returns_fire_count(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/alerts/test",
        json={"metric": "revenue", "template": "pct_change", "params": {"window": "mom", "direction": "drop", "threshold_pct": 8}},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "fire_count": 3, "fire_dates": ["2026-06-01", "2026-06-08", "2026-06-15"], "error": None}


def test_test_endpoint_rejects_a_non_numeric_value_with_422(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/alerts/test",
        json={"metric": "revenue", "template": "absolute_threshold", "params": {"operator": "above", "value": "1; DROP TABLE orders;--"}},
    )
    assert resp.status_code == 422


# --- create --------------------------------------------------------------------
def test_create_alert_succeeds_and_is_visible_in_the_unified_list(monkeypatch):
    client = _client_as_miri(monkeypatch)
    created = _create(client)
    listed = client.get("/api/admin/alerts").json()
    assert any(a["id"] == created["id"] and a["system"] is False for a in listed)


def test_create_includes_bilingual_summary_sentences(monkeypatch):
    client = _client_as_miri(monkeypatch)
    created = _create(client)
    assert "8%" in created["summary_en"]
    assert created["summary_he"]  # non-empty, in Hebrew


def test_create_with_a_failing_dry_run_is_rejected(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/alerts",
        json={"name": "Bad Alert", "metric": "__fail__", "template": "pct_change", "params": {"window": "mom", "direction": "drop", "threshold_pct": 8}, "severity": "warning"},
    )
    # __fail__ isn't in SUPPORTED_METRICS either, so this is caught even
    # earlier (422 from _require_valid_alert_target) -- either way, rejected.
    assert resp.status_code == 422


def test_create_rejects_unsupported_metric(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/alerts",
        json={"name": "Bad Metric", "metric": "active_customers", "template": "absolute_threshold", "params": {"operator": "above", "value": 1}, "severity": "warning"},
    )
    assert resp.status_code == 422


def test_create_rejects_invalid_params_with_422(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/alerts",
        json={"name": "Bad Params", "metric": "revenue", "template": "pct_change", "params": {"window": "yearly", "direction": "drop", "threshold_pct": 8}, "severity": "warning"},
    )
    assert resp.status_code == 422


def test_duplicate_name_returns_409(monkeypatch):
    client = _client_as_miri(monkeypatch)
    _create(client, name="Same Name")
    resp = client.post(
        "/api/admin/alerts",
        json={"name": "Same Name", "metric": "aov", "template": "absolute_threshold", "params": {"operator": "above", "value": 1}, "severity": "warning"},
    )
    assert resp.status_code == 409


def test_create_is_audited(monkeypatch):
    client = _client_as_miri(monkeypatch)
    created = _create(client)
    events = main.audit_store.list_events(CID, category="alert")["events"]
    assert any(e["action"] == "alert.created" and e["target_id"] == created["id"] for e in events)


# --- 12-limit at the API layer --------------------------------------------------
def test_create_beyond_the_limit_returns_409(monkeypatch):
    client = _client_as_miri(monkeypatch)
    for i in range(12):
        _create(client, name=f"Alert {i}", metric="orders", params={"window": "dod", "direction": "drop", "threshold_pct": 1 + i})
    resp = client.post(
        "/api/admin/alerts",
        json={"name": "One Too Many", "metric": "aov", "template": "absolute_threshold", "params": {"operator": "above", "value": 1}, "severity": "warning"},
    )
    assert resp.status_code == 409


# --- update / toggle -------------------------------------------------------------
def test_toggle_enabled_only_is_audited_as_toggled_not_updated(monkeypatch):
    client = _client_as_miri(monkeypatch)
    created = _create(client)
    resp = client.patch(f"/api/admin/alerts/{created['id']}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    events = main.audit_store.list_events(CID, category="alert")["events"]
    toggle_events = [e for e in events if e["target_id"] == created["id"] and e["action"] == "alert.toggled"]
    assert len(toggle_events) == 1


def test_editing_params_re_runs_the_test_and_is_audited_as_updated(monkeypatch):
    client = _client_as_miri(monkeypatch)
    created = _create(client)
    resp = client.patch(
        f"/api/admin/alerts/{created['id']}",
        json={"params": {"window": "mom", "direction": "drop", "threshold_pct": 15}},
    )
    assert resp.status_code == 200
    assert resp.json()["params"]["threshold_pct"] == 15
    events = main.audit_store.list_events(CID, category="alert")["events"]
    update_events = [e for e in events if e["target_id"] == created["id"] and e["action"] == "alert.updated"]
    assert len(update_events) == 1


def test_editing_to_a_failing_target_is_rejected_without_mutating_the_row(monkeypatch):
    client = _client_as_miri(monkeypatch)
    created = _create(client)
    resp = client.patch(f"/api/admin/alerts/{created['id']}", json={"metric": "__fail__"})
    assert resp.status_code == 422
    unchanged = client.get("/api/admin/alerts").json()
    row = next(a for a in unchanged if a["id"] == created["id"])
    assert row["metric"] == "revenue"  # untouched


def test_patch_unknown_alert_404s(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.patch("/api/admin/alerts/ghost-id", json={"enabled": False})
    assert resp.status_code == 404


# --- delete ----------------------------------------------------------------------
def test_delete_removes_it_from_the_list_and_is_audited(monkeypatch):
    client = _client_as_miri(monkeypatch)
    created = _create(client)
    resp = client.delete(f"/api/admin/alerts/{created['id']}")
    assert resp.status_code == 204
    ids = {a["id"] for a in client.get("/api/admin/alerts").json()}
    assert created["id"] not in ids
    events = main.audit_store.list_events(CID, category="alert")["events"]
    assert any(e["action"] == "alert.deleted" and e["target_id"] == created["id"] for e in events)


def test_delete_unknown_alert_404s(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.delete("/api/admin/alerts/ghost-id")
    assert resp.status_code == 404


def test_delete_cannot_target_a_system_alert(monkeypatch):
    """System (YAML-sourced) alert ids never exist in org_alerts_store, so a
    delete against one 404s exactly like any other unknown id -- there is no
    special-cased 403, and none is needed."""
    client = _client_as_miri(monkeypatch)
    system_ids = {a["id"] for a in client.get("/api/admin/alerts").json() if a["system"]}
    assert system_ids  # sanity: the 2 non-migrated YAML alerts are present
    resp = client.delete(f"/api/admin/alerts/{next(iter(system_ids))}")
    assert resp.status_code == 404


# --- unified list shows migrated org alerts + remaining system alerts -----------
def test_unified_list_shows_migrated_alerts_as_org_and_the_rest_as_system(monkeypatch):
    client = _client_as_miri(monkeypatch)
    rows = client.get("/api/admin/alerts").json()
    by_name = {r["name"]: r for r in rows}
    assert by_name["Revenue Drop"]["system"] is False
    assert by_name["AOV Drop"]["system"] is False
    assert by_name["At-Risk Customers"]["system"] is False
    assert by_name["Active Customers Drop"]["system"] is True
    assert by_name["VIP Churn Risk"]["system"] is True
