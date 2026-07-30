"""
Tests for the organization-settings store and the admin API (spec §2).

Store-level tests use a local `store` fixture, mirroring test_org_users.py.
Route-level tests use an inline TestClient and monkeypatch the mocked
identity, same pattern as test_org_users.py's route-level section.

conftest's autouse fixtures keep every test off the real var/sema_state.db
and off the real Anthropic network.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.models import ChatRequest
from sema_core.org_settings_store import InvalidSettingError, OrgSettingsStore

CID = "ecommerce"


@pytest.fixture
def store(tmp_path) -> OrgSettingsStore:
    return OrgSettingsStore(tmp_path / "org_settings.db")


# --- get_or_create ------------------------------------------------------------

def test_get_or_create_seeds_sensible_defaults(store):
    row = store.get_or_create(CID, default_name="E-Commerce", default_timezone="Asia/Jerusalem")
    assert row["name"] == "E-Commerce"
    assert row["timezone"] == "Asia/Jerusalem"
    assert row["currency"] == "USD"
    assert row["number_format"] == "1,234.56"
    assert row["default_language"] == "en"
    assert row["retention_policy"] == "forever"
    assert row["logo_path"] is None


def test_get_or_create_falls_back_to_utc_for_an_invalid_default_timezone(store):
    row = store.get_or_create(CID, default_name="X", default_timezone="Not/AZone")
    assert row["timezone"] == "UTC"


def test_get_or_create_never_overwrites_an_existing_row(store):
    store.get_or_create(CID, default_name="E-Commerce")
    store.update(CID, {"name": "Renamed Co"})
    row_again = store.get_or_create(CID, default_name="E-Commerce")
    assert row_again["name"] == "Renamed Co"  # not reset back to the default


def test_get_returns_none_before_any_row_exists(store):
    assert store.get(CID) is None


# --- update: validation --------------------------------------------------------

@pytest.mark.parametrize(
    "field,value",
    [
        ("timezone", "Not/AZone"),
        ("currency", "XYZ"),
        ("number_format", "1 234.56"),
        ("default_language", "fr"),
        ("retention_policy", "60d"),
        ("name", ""),
        ("name", "   "),
        ("unknown_field", "anything"),
    ],
)
def test_update_rejects_invalid_values(store, field, value):
    store.get_or_create(CID, default_name="E-Commerce")
    with pytest.raises(InvalidSettingError):
        store.update(CID, {field: value})


def test_update_rejects_the_whole_patch_if_any_field_is_bad(store):
    """One bad field fails the whole call rather than partially applying."""
    store.get_or_create(CID, default_name="E-Commerce")
    with pytest.raises(InvalidSettingError):
        store.update(CID, {"currency": "ILS", "timezone": "Not/AZone"})
    assert store.get(CID)["currency"] == "USD"  # unchanged -- nothing partial


def test_update_accepts_every_valid_field(store):
    store.get_or_create(CID, default_name="E-Commerce")
    updated = store.update(
        CID,
        {
            "name": "New Name",
            "timezone": "Asia/Jerusalem",
            "currency": "ILS",
            "number_format": "1.234,56",
            "default_language": "he",
            "retention_policy": "90d",
        },
    )
    assert updated["name"] == "New Name"
    assert updated["timezone"] == "Asia/Jerusalem"
    assert updated["currency"] == "ILS"
    assert updated["number_format"] == "1.234,56"
    assert updated["default_language"] == "he"
    assert updated["retention_policy"] == "90d"


# --- update: concurrency (last-write-wins + conflict flag) --------------------

def test_update_with_no_expected_updated_at_never_conflicts(store):
    store.get_or_create(CID, default_name="E-Commerce")
    updated = store.update(CID, {"currency": "EUR"})
    assert updated["_conflict"] is False


def test_update_flags_conflict_when_stale_but_still_applies(store):
    row = store.get_or_create(CID, default_name="E-Commerce")
    # Someone else changes it first...
    store.update(CID, {"currency": "EUR"})
    # ...then this caller writes using the ORIGINAL (now-stale) updated_at.
    result = store.update(CID, {"currency": "GBP"}, expected_updated_at=row["updated_at"])
    assert result["_conflict"] is True
    assert result["currency"] == "GBP"  # last-write-wins: still applied


def test_update_with_matching_expected_updated_at_has_no_conflict(store):
    row = store.get_or_create(CID, default_name="E-Commerce")
    result = store.update(CID, {"currency": "EUR"}, expected_updated_at=row["updated_at"])
    assert result["_conflict"] is False


# --- set_logo_path -------------------------------------------------------------

def test_set_logo_path(store):
    store.get_or_create(CID, default_name="E-Commerce")
    updated = store.set_logo_path(CID, "/api/admin/org-settings/logo/ecommerce")
    assert updated["logo_path"] == "/api/admin/org-settings/logo/ecommerce"


# --- schema migration (guarded ALTER, mirrors OrgUserStore's own test) --------

def test_store_creates_fresh_table_from_scratch(tmp_path):
    path = tmp_path / "fresh.db"
    store = OrgSettingsStore(path)  # first-ever open must not raise
    assert store.get(CID) is None
    OrgSettingsStore(path)  # re-open: idempotent, no error


# --- route-level: auth + CRUD -------------------------------------------------

def _client_as_miri(monkeypatch) -> TestClient:
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    return TestClient(main.app)


def test_admin_get_org_settings_seeds_on_first_access(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.get("/api/admin/org-settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["client_id"] == CID
    assert body["retention_policy"] == "forever"


def test_admin_org_settings_requires_admin(monkeypatch):
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity",
        lambda: {"client_id": CID, "email": "avi.peretz@ecommerce-demo.com"},  # a viewer
    )
    client = TestClient(main.app)
    assert client.get("/api/admin/org-settings").status_code == 403
    assert client.patch("/api/admin/org-settings", json={"currency": "EUR"}).status_code == 403


def test_admin_patch_org_settings_updates_and_audits(monkeypatch, caplog):
    client = _client_as_miri(monkeypatch)
    client.get("/api/admin/org-settings")  # ensure seeded
    resp = client.patch("/api/admin/org-settings", json={"currency": "ILS", "timezone": "Asia/Jerusalem"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["currency"] == "ILS"
    assert body["timezone"] == "Asia/Jerusalem"
    assert '"event": "admin_org_settings_updated"' in caplog.text
    assert '"action": "org_settings.updated"' in caplog.text

    # The durable audit trail (spec §3) is the SQLite table, not the stderr
    # line -- one row per changed field, with before/after values.
    events = main.audit_store.list_events(CID, category="org_settings")["events"]
    by_target = {e["target_id"]: e for e in events}
    assert by_target["currency"]["before"] == {"currency": "USD"}
    assert by_target["currency"]["after"] == {"currency": "ILS"}
    assert by_target["timezone"]["after"] == {"timezone": "Asia/Jerusalem"}


def test_admin_patch_org_settings_rejects_invalid_value(monkeypatch):
    client = _client_as_miri(monkeypatch)
    client.get("/api/admin/org-settings")
    resp = client.patch("/api/admin/org-settings", json={"currency": "NOPE"})
    assert resp.status_code == 422


def test_admin_patch_with_no_fields_is_a_no_op(monkeypatch):
    client = _client_as_miri(monkeypatch)
    before = client.get("/api/admin/org-settings").json()
    resp = client.patch("/api/admin/org-settings", json={})
    assert resp.status_code == 200
    assert resp.json()["updated_at"] == before["updated_at"]


def test_admin_org_settings_currencies_catalog(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.get("/api/admin/org-settings/currencies")
    assert resp.status_code == 200
    codes = {c["code"] for c in resp.json()}
    assert {"USD", "EUR", "GBP", "ILS"} <= codes


def test_admin_org_settings_timezones_catalog(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.get("/api/admin/org-settings/timezones")
    assert resp.status_code == 200
    zones = resp.json()
    assert "Asia/Jerusalem" in zones
    assert zones == sorted(zones)  # stable, scannable order


def test_admin_retention_preview(monkeypatch):
    client = _client_as_miri(monkeypatch)
    client.get("/api/admin/org-settings")
    resp = client.get("/api/admin/org-settings/retention-preview", params={"policy": "90d"})
    assert resp.status_code == 200
    assert resp.json() == {"policy": "90d", "conversations_to_delete": 0}


def test_admin_retention_preview_rejects_bad_policy(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.get("/api/admin/org-settings/retention-preview", params={"policy": "60d"})
    assert resp.status_code == 422


# --- route-level: logo upload --------------------------------------------------

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 50
_SVG_BYTES = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"></svg>'


def test_admin_upload_logo_png(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/org-settings/logo", files={"file": ("logo.png", _PNG_BYTES, "image/png")}
    )
    assert resp.status_code == 200
    assert resp.json()["logo_path"] == f"/api/admin/org-settings/logo/{CID}"


def test_admin_upload_logo_svg(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/org-settings/logo", files={"file": ("logo.svg", _SVG_BYTES, "image/svg+xml")}
    )
    assert resp.status_code == 200


def test_admin_upload_logo_rejects_fake_png(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/org-settings/logo",
        files={"file": ("logo.png", b"not a real png", "image/png")},
    )
    assert resp.status_code == 422


def test_admin_upload_logo_rejects_oversized_file(monkeypatch):
    client = _client_as_miri(monkeypatch)
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024)
    resp = client.post(
        "/api/admin/org-settings/logo", files={"file": ("logo.png", big, "image/png")}
    )
    assert resp.status_code == 422


def test_admin_upload_logo_requires_admin(monkeypatch):
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity",
        lambda: {"client_id": CID, "email": "avi.peretz@ecommerce-demo.com"},
    )
    client = TestClient(main.app)
    resp = client.post(
        "/api/admin/org-settings/logo", files={"file": ("logo.png", _PNG_BYTES, "image/png")}
    )
    assert resp.status_code == 403


def test_get_org_logo_serves_uploaded_file_and_is_not_admin_gated(monkeypatch):
    client = _client_as_miri(monkeypatch)
    client.post("/api/admin/org-settings/logo", files={"file": ("logo.png", _PNG_BYTES, "image/png")})

    # A totally different (non-admin, even unauthenticated-feeling) identity
    # can still fetch the logo -- the sidebar is visible to everyone.
    monkeypatch.setattr(main, "current_identity", lambda: {"client_id": CID, "email": "nobody@x.com"})
    resp = client.get(f"/api/admin/org-settings/logo/{CID}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


def test_get_org_logo_404s_when_none_uploaded(monkeypatch):
    client = _client_as_miri(monkeypatch)
    client.get("/api/admin/org-settings")  # seed the row, but no logo
    resp = client.get(f"/api/admin/org-settings/logo/{CID}")
    assert resp.status_code == 404


def test_uploading_svg_after_png_removes_the_stale_png_file(monkeypatch, tmp_path):
    client = _client_as_miri(monkeypatch)
    client.post("/api/admin/org-settings/logo", files={"file": ("logo.png", _PNG_BYTES, "image/png")})
    client.post("/api/admin/org-settings/logo", files={"file": ("logo.svg", _SVG_BYTES, "image/svg+xml")})
    resp = client.get(f"/api/admin/org-settings/logo/{CID}")
    assert resp.headers["content-type"] == "image/svg+xml"  # svg wins, not a stale png


# --- route-level: public (non-admin) org-settings endpoint --------------------

def test_public_org_settings_does_not_require_admin(monkeypatch):
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(main, "current_identity", lambda: {"client_id": CID, "email": "nobody@x.com"})
    client = TestClient(main.app)
    resp = client.get("/api/org-settings", params={"client_id": CID})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "name", "logo_path", "currency", "currency_symbol", "currency_position", "number_format", "language",
    }
    assert body["language"] == "en"  # org_settings_store's default


def test_public_org_settings_reflects_the_configured_language(monkeypatch):
    main.org_settings_store.get_or_create(CID, default_name="E-Commerce")
    main.org_settings_store.update(CID, {"default_language": "he"})
    client = TestClient(main.app)
    resp = client.get("/api/org-settings", params={"client_id": CID})
    assert resp.json()["language"] == "he"


def test_public_org_settings_unknown_client_404s(monkeypatch):
    client = TestClient(main.app)
    resp = client.get("/api/org-settings", params={"client_id": "ghost-tenant"})
    assert resp.status_code == 404


# --- timezone feeds the governed analytics config (client_registry) ----------

def test_org_settings_timezone_feeds_analytics_config(monkeypatch):
    """The chat prompt's [SEMA-CONTEXT] tenant block must reflect an
    admin-set timezone, not just the static clients.yaml value -- 'ecommerce'
    already configures 'Asia/Jerusalem' in clients.yaml, so this deliberately
    picks a DIFFERENT zone to prove the override actually wins, not that the
    YAML default happened to match."""
    client = _client_as_miri(monkeypatch)
    client.patch("/api/admin/org-settings", json={"timezone": "America/New_York"})

    ctx = main._internal_context(ChatRequest(question="hi"), CID, "full")  # noqa: SLF001
    assert "America/New_York" in ctx
    assert "Asia/Jerusalem" not in ctx
