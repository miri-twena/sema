"""
Tests for Home screen customization (spec §1).

Store-level tests use a local `store` fixture, mirroring test_org_settings.py.
`home_config` module-level tests validate/resolve against the REAL ecommerce
semantic layer (sql/semantic/*.yaml) -- same "just read the real files"
approach test_semantic_model.py's loader tests use, since aov/revenue/
churn_risk really are defined there (churn_risk is intentionally 'draft'
status, not 'certified' -- validate() only requires "exists and isn't
deprecated" for this fixed KPI catalog, see home_config.py's docstring, so
that's still true even for churn_risk). Route-level tests use an inline
TestClient and monkeypatch the mocked identity, mirroring
test_org_settings.py's `_client_as_miri` pattern.

conftest's autouse fixtures keep every test off the real var/sema_state.db
and off the real Anthropic network.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.main as main
from sema_core import home_config
from sema_core.home_config_store import HomeConfigNotFoundError, HomeConfigStore

CID = "ecommerce"


@pytest.fixture
def store(tmp_path) -> HomeConfigStore:
    return HomeConfigStore(tmp_path / "home_config.db")


def _valid_config(**overrides) -> dict:
    cfg = {
        "kpis": {"order": ["revenue", "orders"], "deltas": {"revenue": True, "orders": False}},
        "default_period_months": 3,
        "daily_brief": {"pulse_enabled": True, "insights_enabled": False, "sensitivity": "sensitive"},
        "suggested_questions": {"questions": ["Show revenue trend by month."], "trending_enabled": False},
        "alerts": {"revenue_mom_drop": {"enabled": False, "threshold": -12}},
    }
    cfg.update(overrides)
    return cfg


# --- store -------------------------------------------------------------------

def test_get_or_create_starts_with_no_draft_or_published(store):
    row = store.get_or_create(CID)
    assert row["draft"] is None
    assert row["published"] is None
    assert row["version"] == 0


def test_save_draft_then_publish_bumps_version_and_clears_draft(store):
    store.save_draft(CID, _valid_config())
    row = store.publish(CID, published_by="Miri Levi")
    assert row["draft"] is None
    assert row["published"]["default_period_months"] == 3
    assert row["version"] == 1
    assert row["published_by"] == "Miri Levi"
    assert row["published_at"]


def test_publish_with_no_draft_raises(store):
    with pytest.raises(HomeConfigNotFoundError):
        store.publish(CID, published_by="Miri Levi")


def test_revert_discards_draft_without_touching_published(store):
    store.save_draft(CID, _valid_config())
    store.publish(CID, published_by="Miri Levi")
    store.save_draft(CID, _valid_config(default_period_months=12))
    row = store.revert(CID)
    assert row["draft"] is None
    assert row["published"]["default_period_months"] == 3  # unchanged


def test_revert_with_no_draft_raises(store):
    with pytest.raises(HomeConfigNotFoundError):
        store.revert(CID)


def test_second_publish_increments_version_again(store):
    store.save_draft(CID, _valid_config())
    store.publish(CID, published_by="Miri Levi")
    store.save_draft(CID, _valid_config(default_period_months=6))
    row = store.publish(CID, published_by="Miri Levi")
    assert row["version"] == 2
    assert row["published"]["default_period_months"] == 6


# --- home_config.validate() ---------------------------------------------------

def test_valid_config_has_no_errors():
    assert home_config.validate(CID, _valid_config()) == []


def test_rejects_too_many_kpis():
    cfg = _valid_config(kpis={"order": ["revenue", "orders", "aov", "churn_risk", "revenue"], "deltas": {}})
    errors = home_config.validate(CID, cfg)
    assert any("KPI" in e for e in errors)


def test_rejects_zero_kpis():
    cfg = _valid_config(kpis={"order": [], "deltas": {}})
    errors = home_config.validate(CID, cfg)
    assert any("KPI" in e for e in errors)


def test_rejects_unknown_kpi_id():
    cfg = _valid_config(kpis={"order": ["not_a_real_kpi"], "deltas": {}})
    errors = home_config.validate(CID, cfg)
    assert any("Unknown KPI" in e for e in errors)


def test_valid_config_accepts_a_draft_status_metric_backed_kpi():
    """churn_risk is intentionally 'draft' status in the seeded demo content
    -- it must still be a valid, publishable KPI choice (this fixed catalog
    isn't gated on 'certified', only on "exists and isn't deprecated")."""
    assert home_config.validate(CID, _valid_config(kpis={"order": ["churn_risk"], "deltas": {}})) == []


def test_rejects_a_deprecated_metric_backed_kpi(monkeypatch):
    monkeypatch.setattr(home_config, "_metric_is_usable", lambda cid, name: False)
    errors = home_config.validate(CID, _valid_config(kpis={"order": ["aov"], "deltas": {}}))
    assert any("deprecated" in e for e in errors)


def test_rejects_bad_sensitivity():
    cfg = _valid_config(daily_brief={"pulse_enabled": True, "insights_enabled": True, "sensitivity": "extreme"})
    errors = home_config.validate(CID, cfg)
    assert any("sensitivity" in e for e in errors)


def test_rejects_bad_default_period_months():
    cfg = _valid_config(default_period_months=5)
    errors = home_config.validate(CID, cfg)
    assert any("period" in e for e in errors)


def test_rejects_too_many_suggested_questions():
    cfg = _valid_config(suggested_questions={"questions": [f"Q{i}?" for i in range(10)], "trending_enabled": True})
    errors = home_config.validate(CID, cfg)
    assert any("suggested questions" in e for e in errors)


def test_rejects_unknown_alert_id():
    cfg = _valid_config(alerts={"not_a_real_alert": {"enabled": True, "threshold": None}})
    errors = home_config.validate(CID, cfg)
    assert any("Unknown alert" in e for e in errors)


def test_rejects_non_numeric_alert_threshold():
    cfg = _valid_config(alerts={"revenue_mom_drop": {"enabled": True, "threshold": "a lot"}})
    errors = home_config.validate(CID, cfg)
    assert any("threshold" in e for e in errors)


# --- home_config.effective_config() -- deprecated-metric drop (spec item 13) -

def test_effective_config_merges_over_defaults():
    cfg, warnings = home_config.effective_config(CID, {"default_period_months": 6})
    assert cfg["default_period_months"] == 6
    assert cfg["kpis"]["order"] == home_config.DEFAULT_KPI_ORDER  # untouched key falls back to default
    assert warnings == []


def test_effective_config_drops_deprecated_metric_kpi_with_warning(monkeypatch):
    monkeypatch.setattr(home_config, "_metric_is_usable", lambda cid, name: name != "aov")
    stored = {"kpis": {"order": ["revenue", "aov", "churn_risk"], "deltas": {}}}
    cfg, warnings = home_config.effective_config(CID, stored)
    assert "aov" not in cfg["kpis"]["order"]
    assert cfg["kpis"]["order"] == ["revenue", "churn_risk"]
    assert any("AOV" in w for w in warnings)


def test_effective_config_never_renders_zero_kpis(monkeypatch):
    monkeypatch.setattr(home_config, "_metric_is_usable", lambda cid, name: False)
    stored = {"kpis": {"order": ["revenue", "aov"], "deltas": {}}}
    cfg, warnings = home_config.effective_config(CID, stored)
    assert cfg["kpis"]["order"] == home_config.DEFAULT_KPI_ORDER
    assert len(warnings) == 2


# --- route ---------------------------------------------------------------------

def _client_as_miri(monkeypatch) -> TestClient:
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    return TestClient(main.app)


def test_admin_home_config_requires_admin(monkeypatch):
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity",
        lambda: {"client_id": CID, "email": "avi.peretz@ecommerce-demo.com"},  # a viewer
    )
    client = TestClient(main.app)
    assert client.get("/api/admin/home-config").status_code == 403
    assert client.put("/api/admin/home-config", json=_valid_config()).status_code == 403
    assert client.post("/api/admin/home-config/publish").status_code == 403
    assert client.post("/api/admin/home-config/revert").status_code == 403
    assert client.post("/api/admin/home-config/preview", json=_valid_config()).status_code == 403


def test_get_starts_empty(monkeypatch):
    client = _client_as_miri(monkeypatch)
    body = client.get("/api/admin/home-config").json()
    assert body["draft"] is None
    assert body["published"] is None
    assert body["version"] == 0


def test_put_saves_draft_without_validating(monkeypatch):
    client = _client_as_miri(monkeypatch)
    # An out-of-range KPI count is invalid, but PUT (autosave) must still accept it.
    bad = _valid_config(kpis={"order": [], "deltas": {}})
    resp = client.put("/api/admin/home-config", json=bad)
    assert resp.status_code == 200
    assert resp.json()["draft"]["kpis"]["order"] == []


def test_publish_blocked_when_draft_invalid(monkeypatch):
    client = _client_as_miri(monkeypatch)
    # Structurally valid (a real list[str]), but fails home_config.validate()'s
    # KPI-count rule -- PUT itself only enforces Pydantic's TYPE shape, not
    # this business rule, so the draft saves fine and Publish is the gate.
    client.put("/api/admin/home-config", json=_valid_config(kpis={"order": [], "deltas": {}}))
    resp = client.post("/api/admin/home-config/publish")
    assert resp.status_code == 409
    assert "errors" in resp.json()["detail"]


def test_publish_with_no_draft_is_409(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post("/api/admin/home-config/publish")
    assert resp.status_code == 409


def test_publish_valid_draft_updates_public_endpoints_and_audits(monkeypatch):
    client = _client_as_miri(monkeypatch)
    client.put(
        "/api/admin/home-config",
        json=_valid_config(
            kpis={"order": ["orders"], "deltas": {"orders": False}},
            suggested_questions={"questions": ["What is our revenue?"], "trending_enabled": False},
        ),
    )
    pub = client.post("/api/admin/home-config/publish")
    assert pub.status_code == 200
    assert pub.json()["version"] == 1

    # /api/clients reflects the published suggested_questions override.
    clients = client.get("/api/clients").json()
    ecommerce = next(c for c in clients if c["id"] == CID)
    assert ecommerce["suggested_questions"] == ["What is our revenue?"]

    # /api/popular-questions is silenced (trending_enabled: False).
    assert client.get("/api/popular-questions", params={"client_id": CID}).json() == []

    # Audited.
    events = main.audit_store.list_events(CID, category="home_config")["events"]
    assert any(e["action"] == "home_config.published" for e in events)


def test_revert_route_restores_previous_published_config(monkeypatch):
    client = _client_as_miri(monkeypatch)
    client.put("/api/admin/home-config", json=_valid_config(default_period_months=3))
    client.post("/api/admin/home-config/publish")
    client.put("/api/admin/home-config", json=_valid_config(default_period_months=12))

    resp = client.post("/api/admin/home-config/revert")
    assert resp.status_code == 200
    body = resp.json()
    assert body["draft"] is None
    assert body["published"]["default_period_months"] == 3

    events = main.audit_store.list_events(CID, category="home_config")["events"]
    assert any(e["action"] == "home_config.reverted" for e in events)


def test_preview_reflects_the_posted_draft_directly(monkeypatch):
    """Preview takes the config in the REQUEST BODY, not whatever's saved
    server-side -- so it never races the editor's separate autosave
    debounce (a GET reading stored state could preview stale data)."""
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/home-config/preview",
        json=_valid_config(kpis={"order": ["orders"], "deltas": {"orders": True}}),
    )
    assert resp.status_code == 200
    body = resp.json()
    labels = [k["label"] for k in body["overview"]["kpis"]]
    assert any("Orders" in label for label in labels)
    assert all("Revenue" not in label for label in labels)

    # Nothing was saved -- preview never touches draft/published state.
    state = client.get("/api/admin/home-config").json()
    assert state["draft"] is None
    assert state["published"] is None
