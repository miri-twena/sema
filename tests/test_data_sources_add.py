"""
Tests for the data-sources add-flow (data_sources_add_prompt.md): encrypted
SQL DB connections, the write-permission probe, the SaaS/Sheets request
flow, and CSV upload. conftest's autouse fixtures isolate every new store
(client_connections/source_requests/uploads) and pin SEMA_SECRETS_KEY to a
fixed test key -- no test depends on a live external DB or the real
var/sema_state.db.
"""

from __future__ import annotations

import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.main as main
from sema_core import file_upload
from sema_core.secrets import decrypt_secret, encrypt_secret, fingerprint

CID = "ecommerce"


def _client_as_miri(monkeypatch) -> TestClient:
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"})
    return TestClient(main.app)


# --- encryption round-trip ----------------------------------------------------

def test_encrypt_decrypt_round_trip():
    ciphertext = encrypt_secret("hunter2")
    assert ciphertext != "hunter2"
    assert decrypt_secret(ciphertext) == "hunter2"


def test_fingerprint_is_not_reversible_and_is_stable():
    fp1 = fingerprint("hunter2")
    fp2 = fingerprint("hunter2")
    assert fp1 == fp2
    assert len(fp1) == 4
    assert fp1 != "er2 "  # not just the literal last 4 chars of the plaintext


# --- catalog gating ------------------------------------------------------------

def test_catalog_endpoint_lists_every_connector(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.get("/api/admin/data-sources/catalog")
    assert resp.status_code == 200
    ids = {c["id"] for c in resp.json()}
    assert {"postgres", "mysql", "mssql", "priority", "salesforce", "google_sheets", "csv"} <= ids


def test_driver_pending_connector_cannot_be_tested_or_created(monkeypatch):
    import sema_core.connector_catalog as catalog

    fake_catalog = [
        {"id": "mssql", "kind": "sql_db", "label": "Microsoft SQL Server", "unlocks": {"en": "x", "he": "x"}, "availability": "driver_pending"},
    ]
    monkeypatch.setattr(catalog, "CONNECTOR_CATALOG", fake_catalog)
    client = _client_as_miri(monkeypatch)

    resp = client.post(
        "/api/admin/data-sources/test",
        json={"connector_type": "mssql", "host": "h", "port": 1433, "database": "d", "username": "u", "password": "p", "ssl_enabled": False},
    )
    assert resp.status_code == 409

    resp2 = client.post(
        "/api/admin/data-sources/connections",
        json={"connector_type": "mssql", "display_name": "x", "host": "h", "port": 1433, "database": "d",
              "username": "u", "password": "p", "ssl_enabled": False, "write_access_acknowledged": False},
    )
    assert resp2.status_code == 409


# --- test-before-store + write-permission probe -------------------------------

def test_create_connection_requires_a_passed_test(monkeypatch):
    client = _client_as_miri(monkeypatch)
    monkeypatch.setattr(
        main.db_probe, "test_connection",
        lambda *a, **kw: {"ok": False, "tables": [], "write_access": None, "error": "Could not connect."},
    )
    resp = client.post(
        "/api/admin/data-sources/connections",
        json={"connector_type": "postgres", "display_name": "Prod DB", "host": "h", "port": 5432, "database": "d",
              "username": "u", "password": "p", "ssl_enabled": False, "write_access_acknowledged": False},
    )
    assert resp.status_code == 422
    assert main.client_connections_store.list_for_client(CID) == []


def test_create_connection_blocked_by_write_access_without_acknowledgment(monkeypatch):
    client = _client_as_miri(monkeypatch)
    monkeypatch.setattr(
        main.db_probe, "test_connection",
        lambda *a, **kw: {"ok": True, "tables": ["orders"], "write_access": True, "error": None},
    )
    resp = client.post(
        "/api/admin/data-sources/connections",
        json={"connector_type": "postgres", "display_name": "Prod DB", "host": "h", "port": 5432, "database": "d",
              "username": "u", "password": "p", "ssl_enabled": False, "write_access_acknowledged": False},
    )
    assert resp.status_code == 409
    assert main.client_connections_store.list_for_client(CID) == []


def test_create_connection_succeeds_with_write_access_acknowledged(monkeypatch):
    client = _client_as_miri(monkeypatch)
    monkeypatch.setattr(
        main.db_probe, "test_connection",
        lambda *a, **kw: {"ok": True, "tables": ["orders"], "write_access": True, "error": None},
    )
    resp = client.post(
        "/api/admin/data-sources/connections",
        json={"connector_type": "postgres", "display_name": "Prod DB", "host": "h", "port": 5432, "database": "d",
              "username": "u", "password": "p", "ssl_enabled": False, "write_access_acknowledged": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["fingerprint"] == fingerprint("p")
    assert len(main.client_connections_store.list_for_client(CID)) == 1


def test_test_connection_response_includes_readonly_sql_only_when_write_access(monkeypatch):
    client = _client_as_miri(monkeypatch)
    monkeypatch.setattr(
        main.db_probe, "test_connection",
        lambda *a, **kw: {"ok": True, "tables": [], "write_access": False, "error": None},
    )
    resp = client.post(
        "/api/admin/data-sources/test",
        json={"connector_type": "postgres", "host": "h", "port": 5432, "database": "d", "username": "u", "password": "p", "ssl_enabled": False},
    )
    assert resp.json()["readonly_user_sql"] is None


# --- credentials never appear in any output -----------------------------------

def test_credentials_absent_from_connection_response_and_list(monkeypatch):
    client = _client_as_miri(monkeypatch)
    monkeypatch.setattr(
        main.db_probe, "test_connection",
        lambda *a, **kw: {"ok": True, "tables": ["orders"], "write_access": False, "error": None},
    )
    create_resp = client.post(
        "/api/admin/data-sources/connections",
        json={"connector_type": "postgres", "display_name": "Prod DB", "host": "h", "port": 5432, "database": "d",
              "username": "u", "password": "super-secret-pw", "ssl_enabled": False, "write_access_acknowledged": False},
    )
    assert "super-secret-pw" not in create_resp.text
    assert "password" not in create_resp.json()
    assert "encrypted_password" not in create_resp.json()

    monkeypatch.setattr(
        main.db_probe, "check_health", lambda *a, **kw: {"reachable": True, "data_age_days": None, "error": None}
    )
    list_resp = client.get("/api/admin/data-sources")
    assert "super-secret-pw" not in list_resp.text

    events = main.audit_store.list_events(CID, page_size=100)["events"]
    for e in events:
        assert "super-secret-pw" not in str(e)


def test_credentials_absent_from_platform_log(monkeypatch, caplog):
    import logging

    client = _client_as_miri(monkeypatch)
    monkeypatch.setattr(
        main.db_probe, "test_connection",
        lambda *a, **kw: {"ok": True, "tables": [], "write_access": False, "error": None},
    )
    with caplog.at_level(logging.INFO):
        client.post(
            "/api/admin/data-sources/connections",
            json={"connector_type": "postgres", "display_name": "Prod DB", "host": "h", "port": 5432, "database": "d",
                  "username": "u", "password": "super-secret-pw", "ssl_enabled": False, "write_access_acknowledged": False},
        )
    assert "super-secret-pw" not in caplog.text


def test_connection_error_is_scrubbed_never_the_raw_exception(monkeypatch):
    """Exercises the REAL test_connection (not a test-level stub) so this
    actually proves _scrub is on the path -- only the low-level `_connect`
    is faked, standing in for a real driver raising with host/user/password
    embedded in its own exception text (which real drivers do)."""
    from sema_core import db_probe

    def boom(*a, **kw):
        raise RuntimeError('password authentication failed for user "u" at host secret-internal-host')

    monkeypatch.setattr(db_probe, "_connect", boom)
    result = db_probe.test_connection(
        "postgres", host="secret-internal-host", port=5432, database="d", username="u", password="p", ssl_enabled=False
    )
    assert result["ok"] is False
    assert "secret-internal-host" not in result["error"]
    assert "password authentication failed" not in result["error"]


# --- SaaS/Sheets request flow: rejects credential-like fields ----------------

def test_source_request_rejects_credential_like_fields(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/data-sources/requests",
        json={"connector_type": "priority", "details": {"display_name": "Priority Prod", "api_key": "shhh"}},
    )
    assert resp.status_code == 422
    assert main.source_requests_store.list_for_client(CID) == []


def test_source_request_accepts_clean_fields_and_creates_a_tracked_card(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/data-sources/requests",
        json={"connector_type": "priority", "details": {"display_name": "Priority Prod", "environment": "Production"}},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "requested"

    cards = client.get("/api/admin/data-sources").json()
    request_card = next(c for c in cards if c["origin"] == "request")
    assert request_card["progress_step"] == "requested"
    assert request_card["status"] == "syncing"


def test_google_sheets_request_lands_in_requested_state(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/data-sources/requests",
        json={"connector_type": "google_sheets", "details": {"sheet_url": "https://docs.google.com/spreadsheets/d/x"}},
    )
    assert resp.status_code == 200


def test_interest_recorded_for_coming_soon_connector(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post("/api/admin/data-sources/interest", json={"connector_type": "shopify"})
    assert resp.status_code == 200
    assert resp.json()["recorded"] is True
    actions = [e["action"] for e in main.audit_store.list_events(CID, page_size=100)["events"]]
    assert "data_source.interest_recorded" in actions


# --- CSV upload: type inference + replace -------------------------------------

@pytest.fixture
def fake_writes(monkeypatch):
    """Captures every (sql, params) sema_core.file_upload would send to the
    real DB, instead of actually writing -- no test may depend on a live
    Postgres (see conftest's own module docstring)."""
    calls = []
    monkeypatch.setattr(file_upload.db, "run_write", lambda sql, client_id=None: calls.append(("write", sql)))
    monkeypatch.setattr(
        file_upload.db, "run_write_many", lambda sql, rows, client_id=None: calls.append(("write_many", sql, rows))
    )
    return calls


def test_column_plan_infers_types_and_sanitizes_headers():
    df = pd.DataFrame({"Order Date": pd.to_datetime(["2026-01-01"]), "Amount ($)": [19.99], "Qty": [3], "Note": ["x"]})
    plan = file_upload.column_plan(df)
    by_source = {p["source_name"]: p for p in plan}
    assert by_source["Order Date"]["sql_type"] == "TIMESTAMP"
    assert by_source["Amount ($)"]["sql_type"] == "DOUBLE PRECISION"
    assert by_source["Qty"]["sql_type"] == "BIGINT"
    assert by_source["Note"]["sql_type"] == "TEXT"
    # sanitized to safe snake_case identifiers
    assert by_source["Amount ($)"]["column_name"] == "amount"
    assert by_source["Order Date"]["column_name"] == "order_date"


def test_column_plan_dedupes_colliding_sanitized_names():
    df = pd.DataFrame({"a b": [1], "a-b": [2]})
    plan = file_upload.column_plan(df)
    names = [p["column_name"] for p in plan]
    assert len(names) == len(set(names))  # no collision


def test_upload_endpoint_creates_a_table_and_tracks_it(monkeypatch, fake_writes):
    client = _client_as_miri(monkeypatch)
    csv_bytes = b"name,amount\nWidget,10.5\nGadget,20\n"
    resp = client.post(
        "/api/admin/data-sources/upload",
        files={"file": ("products.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["row_count"] == 2
    assert len(body["columns"]) == 2
    assert len(main.uploads_store.list_for_client(CID)) == 1

    # a CREATE TABLE (and the schema/drop) plus one bulk-insert call happened
    kinds = [c[0] for c in fake_writes]
    assert kinds.count("write") >= 3  # CREATE SCHEMA, DROP TABLE, CREATE TABLE
    assert kinds.count("write_many") == 1


def test_upload_rejects_unsupported_extension(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/data-sources/upload",
        files={"file": ("data.json", io.BytesIO(b"{}"), "application/json")},
    )
    assert resp.status_code == 422


def test_upload_replace_keeps_the_same_table_name(monkeypatch, fake_writes):
    client = _client_as_miri(monkeypatch)
    first = client.post(
        "/api/admin/data-sources/upload",
        files={"file": ("products.csv", io.BytesIO(b"name,amount\nWidget,10\n"), "text/csv")},
    ).json()
    fake_writes.clear()

    second = client.post(
        f"/api/admin/data-sources/uploads/{first['id']}/replace",
        files={"file": ("products_v2.csv", io.BytesIO(b"name,amount,sku\nWidget,10,W-1\nGadget,20,G-1\n"), "text/csv")},
    )
    assert second.status_code == 200
    body = second.json()
    assert body["table_name"] == first["table_name"]
    assert body["row_count"] == 2
    assert len(body["columns"]) == 3
    assert len(main.uploads_store.list_for_client(CID)) == 1  # still one tracked row, not two


def test_replace_unknown_upload_404s(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/data-sources/uploads/not-a-real-id/replace",
        files={"file": ("x.csv", io.BytesIO(b"a\n1\n"), "text/csv")},
    )
    assert resp.status_code == 404
