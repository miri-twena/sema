"""
GET /healthz (deployment_prep_prompt.md item 5): the platform-facing liveness
probe -- no auth, root path (not /api), minimal payload. Distinct from the
existing GET /api/health, which stays API-key-gated (it's the frontend's own
richer status poll).
"""

from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

import api.main as main


def test_healthz_returns_expected_shape():
    client = TestClient(main.app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "db_connected" in body
    assert "version" in body


def test_healthz_requires_no_api_key_even_when_one_is_configured(monkeypatch):
    """The whole point of /healthz: a platform's health-check prober can't be
    expected to send X-API-Key, so it must work even when SEMA_API_KEY is
    set (which would 401 every other route)."""
    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, api_key="super-secret"))
    client = TestClient(main.app)
    resp = client.get("/healthz")  # deliberately no X-API-Key header
    assert resp.status_code == 200


def test_other_routes_still_require_the_api_key_when_configured(monkeypatch):
    """Sanity check alongside the exemption above: /healthz being exempt
    must not accidentally exempt every other route too."""
    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, api_key="super-secret"))
    client = TestClient(main.app)
    assert client.get("/api/clients").status_code == 401
    assert client.get("/api/clients", headers={"X-API-Key": "super-secret"}).status_code == 200
    assert client.get("/api/clients", headers={"X-API-Key": "wrong-key"}).status_code == 401


def test_healthz_reports_db_connectivity(monkeypatch):
    client = TestClient(main.app)

    monkeypatch.setattr(main, "check_connection", lambda cid: True)
    assert client.get("/healthz").json()["db_connected"] is True

    monkeypatch.setattr(main, "check_connection", lambda cid: False)
    assert client.get("/healthz").json()["db_connected"] is False


def test_healthz_reports_version_from_env(monkeypatch):
    monkeypatch.setenv("SEMA_VERSION", "abc1234")
    client = TestClient(main.app)
    assert client.get("/healthz").json()["version"] == "abc1234"


def test_healthz_version_defaults_to_unknown(monkeypatch):
    monkeypatch.delenv("SEMA_VERSION", raising=False)
    client = TestClient(main.app)
    assert client.get("/healthz").json()["version"] == "unknown"


def test_healthz_not_in_openapi_schema():
    """include_in_schema=False -- it's an infra probe, not part of the
    documented public API surface."""
    client = TestClient(main.app)
    schema = client.get("/openapi.json").json()
    assert "/healthz" not in schema["paths"]
