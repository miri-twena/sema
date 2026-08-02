"""
Systematic multi-tenant isolation sweep (backend_qa_prompt.md item 2).

Pattern for every surface: create an artifact scoped to tenant A
(client_id="ecommerce"), then prove it is INVISIBLE from tenant B
(client_id="insurance") on every read path -- list AND direct-id fetch. A
direct-id fetch across tenants must 404, never 403 -- an existence leak (403
tells an attacker the row exists; 404 doesn't) is exactly as real a bug as
returning the row itself.

Known, intentional limitation (documented, not silently papered over): admin
routes resolve `client_id` from the MOCKED identity (sema_core.current_user),
which today only has one real home tenant (ecommerce/Miri). To exercise these
guarantees from "the insurance side" we seed a parallel org-user roster under
client_id="insurance" and monkeypatch `current_identity` to point at it --
this is exactly the pattern tests/test_org_users.py already established for
admin-route identity switching. When real auth (auth_login_prompt.md Parts
A+B) lands, current_identity() will read a verified session per-request
instead of a hardcoded mock, but every guarantee proven here rests on
`client_id` plumbing through the STORE layer (WHERE client_id = ?), which is
identity-mechanism-agnostic -- these tests do not need to change when that
lands. The one route that is DELIBERATELY not tenant-scoped at all --
GET /api/admin/org-settings/logo/{client_id} -- is exercised here too, as a
documented public exception, not a leak.

The non-admin conversation routes take `client_id` as a plain query
parameter (no login yet -- see api/main.py's _resolve_client), not from the
identity, so those tests pass the WRONG client_id explicitly rather than
switching identity.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.main as main

ECOM = "ecommerce"
INSURANCE = "insurance"
ECOM_ADMIN_EMAIL = "miri1988@gmail.com"
INSURANCE_ADMIN_EMAIL = "miri1988@gmail.com"  # seed_demo_users reuses the same roster shape per client


@pytest.fixture()
def client() -> TestClient:
    return TestClient(main.app)


def _as(monkeypatch, client_id: str, email: str = ECOM_ADMIN_EMAIL) -> None:
    monkeypatch.setattr(main, "current_identity", lambda: {"client_id": client_id, "email": email})


def _seed_both_tenants() -> None:
    main.org_user_store.seed_demo_users(ECOM)
    main.org_user_store.seed_demo_users(INSURANCE)


# --- conversations + threads + feedback (client_id is a query param) -------


def test_conversation_invisible_via_wrong_client_id(client, monkeypatch):
    conv_id = main.conversation_store.create(ECOM)
    main.conversation_store.append(conv_id, ECOM, "user", "how did revenue do this month?")

    assert conv_id not in [c["id"] for c in main.conversation_store.list_conversations(INSURANCE)]

    resp = client.get(f"/api/conversations/{conv_id}", params={"client_id": INSURANCE})
    assert resp.status_code == 404  # not 403 -- existence must not leak either

    # Own tenant can still read it -- proves the 404 above is real scoping,
    # not a generally-broken route.
    ok = client.get(f"/api/conversations/{conv_id}", params={"client_id": ECOM})
    assert ok.status_code == 200


def test_conversation_patch_and_delete_reject_wrong_client_id(client):
    conv_id = main.conversation_store.create(ECOM)
    main.conversation_store.append(conv_id, ECOM, "user", "hi")

    patch_resp = client.patch(
        f"/api/conversations/{conv_id}", params={"client_id": INSURANCE}, json={"title": "hijacked"}
    )
    assert patch_resp.status_code == 404

    delete_resp = client.delete(f"/api/conversations/{conv_id}", params={"client_id": INSURANCE})
    assert delete_resp.status_code == 404

    # Untouched: still readable and unrenamed from its real tenant.
    meta = client.get(f"/api/conversations/{conv_id}", params={"client_id": ECOM})
    assert meta.status_code == 200


def test_threads_invisible_via_wrong_client_id(client):
    conv_id = main.conversation_store.create(ECOM)
    main.conversation_store.append(conv_id, ECOM, "user", "hi")
    thread_id = main.conversation_store.get_or_create_thread(
        conversation_id=conv_id, client_id=ECOM, turn_index=0,
        widget_kind="kpi", widget_title="Revenue",
    )

    resp = client.get(f"/api/conversations/{conv_id}/threads", params={"client_id": INSURANCE})
    assert resp.status_code == 404

    resp2 = client.get(
        f"/api/conversations/{conv_id}/threads/{thread_id}", params={"client_id": INSURANCE}
    )
    assert resp2.status_code == 404


def test_feedback_store_itself_does_not_filter_by_client_id():
    """Documents a real trust boundary, doesn't silently paper over it
    (backend_qa_prompt.md's own instruction): TurnFeedbackStore.get()/
    get_for_conversation() take NO client_id at all -- they trust that the
    conversation_id itself is already tenant-safe. This is fine ONLY because
    every caller in api/main.py validates conversation ownership via
    conversation_store first (see test_feedback_route_rejects_wrong_client_id
    below, which locks in that the route-layer guard stays in place). If a
    future route ever calls these methods without that upstream check, this
    test documents exactly why that would be a cross-tenant leak."""
    conv_id = main.conversation_store.create(ECOM)
    main.feedback_store.set(conv_id, ECOM, turn_index=0, rating="up", comment=None, user_id=None)

    # The store answers for ANY caller who knows the conversation_id -- no
    # client_id filtering happens at this layer, by construction.
    leaked = main.feedback_store.get_for_conversation(conv_id)
    assert leaked  # proves the leak surface is real, not a no-op call


def test_feedback_route_rejects_wrong_client_id(client):
    """The route-layer guard that makes the store-level gap above safe in
    practice: POST /api/feedback validates conversation ownership via
    conversation_store BEFORE ever touching feedback_store."""
    conv_id = main.conversation_store.create(ECOM)
    main.conversation_store.append(conv_id, ECOM, "user", "hi")

    resp = client.post(
        "/api/feedback",
        json={"conversation_id": conv_id, "turn_index": 0, "rating": "up", "client_id": INSURANCE},
    )
    assert resp.status_code == 404
    assert main.feedback_store.get(conv_id, 0) is None  # never written


# --- audit log ---------------------------------------------------------------


def test_audit_events_scoped_to_client(client, monkeypatch):
    _seed_both_tenants()
    main.audit_store.record(
        ECOM, actor_id="u1", actor_name="Miri", actor_role="client_admin", action="org_settings.updated"
    )
    _as(monkeypatch, INSURANCE)
    body = client.get("/api/admin/audit").json()
    assert body["events"] == []
    assert body["total"] == 0


# --- org settings + retention -------------------------------------------------


def test_org_settings_isolated_per_client():
    ecom = main.org_settings_store.get_or_create(ECOM, default_name="E-Commerce Co")
    ins = main.org_settings_store.get_or_create(INSURANCE, default_name="Insurance Co")
    assert ecom["name"] == "E-Commerce Co"
    assert ins["name"] == "Insurance Co"
    assert ecom["client_id"] != ins["client_id"]


def test_org_settings_route_reflects_only_own_tenant(client, monkeypatch):
    _seed_both_tenants()
    main.org_settings_store.get_or_create(ECOM, default_name="E-Commerce Co")
    main.org_settings_store.get_or_create(INSURANCE, default_name="Insurance Co")

    _as(monkeypatch, INSURANCE)
    body = client.get("/api/admin/org-settings").json()
    assert body["name"] == "Insurance Co"


def test_retention_runs_isolated_per_client():
    main.retention_run_store.record(ECOM, deleted_count=42, status="ok")
    assert main.retention_run_store.get(INSURANCE) is None
    assert main.retention_run_store.get(ECOM)["deleted_count"] == 42


def test_org_logo_route_is_intentionally_public_not_a_leak(client):
    """GET /api/admin/org-settings/logo/{client_id} is NOT admin-gated by
    design (api/main.py's own docstring: the sidebar shows every user in the
    org the logo, not just admins) -- so this is a documented exception, not
    a bug. Confirm it exposes nothing beyond the logo image itself: with no
    logo uploaded for either tenant it 404s regardless of which tenant is
    requested, never falling back to serving a DIFFERENT tenant's logo."""
    resp_a = client.get(f"/api/admin/org-settings/logo/{ECOM}")
    resp_b = client.get(f"/api/admin/org-settings/logo/{INSURANCE}")
    assert resp_a.status_code == 404
    assert resp_b.status_code == 404


# --- home config ---------------------------------------------------------------


def test_home_config_isolated_per_client():
    main.home_config_store.save_draft(ECOM, {"kpis": {"order": ["revenue"]}})
    ins_row = main.home_config_store.get(INSURANCE)
    assert ins_row is None or ins_row.get("draft") is None


def test_home_config_route_scoped_to_admins_own_tenant(client, monkeypatch):
    _seed_both_tenants()
    main.home_config_store.save_draft(ECOM, {"kpis": {"order": ["revenue"]}})

    _as(monkeypatch, INSURANCE)
    body = client.get("/api/admin/home-config").json()
    assert body["draft"] is None  # insurance's own (untouched) draft, not ecommerce's


# --- org alerts ----------------------------------------------------------------


def test_org_alert_invisible_and_unpatchable_cross_tenant(client, monkeypatch):
    _seed_both_tenants()
    alert = main.org_alerts_store.create(
        ECOM, name="Orders below 10", metric="orders", template="absolute_threshold",
        params={"operator": "below", "value": 10}, severity="warning", created_by=None,
    )
    assert main.org_alerts_store.get(INSURANCE, alert["id"]) is None
    assert alert["id"] not in [a["id"] for a in main.org_alerts_store.list_for_client(INSURANCE)]

    _as(monkeypatch, INSURANCE)
    patch_resp = client.patch(f"/api/admin/alerts/{alert['id']}", json={"name": "hijacked"})
    assert patch_resp.status_code == 404
    delete_resp = client.delete(f"/api/admin/alerts/{alert['id']}")
    assert delete_resp.status_code == 404

    # Untouched from its real tenant's point of view.
    assert main.org_alerts_store.get(ECOM, alert["id"])["name"] == "Orders below 10"


# --- semantic model: drafts + versions -----------------------------------------


def test_semantic_draft_isolated_per_client():
    main.semantic_store.save_draft(ECOM, "metric", "revenue", {"sql": "select 1"})
    assert main.semantic_store.get_draft(INSURANCE, "metric", "revenue") is None


def test_semantic_version_invisible_and_unrestorable_cross_tenant(client, monkeypatch):
    _seed_both_tenants()
    version = main.semantic_store.record_version(
        ECOM, snapshot={"metrics.yaml": "metrics: []\n"}, changed_items=["metric:revenue"], author="Miri"
    )
    from sema_core.semantic_store import SemanticVersionNotFoundError

    with pytest.raises(SemanticVersionNotFoundError):
        main.semantic_store.get_version(INSURANCE, version["id"])

    _as(monkeypatch, INSURANCE)
    resp = client.post(f"/api/admin/semantic/versions/{version['id']}/restore")
    assert resp.status_code == 404  # 404s on the store lookup, before any file write


# --- data sources: connections, requests, uploads -------------------------------


def _dummy_connection_body() -> dict:
    return {
        "connector_type": "postgres", "display_name": "Warehouse", "host": "db.internal",
        "port": 5432, "database": "warehouse", "username": "ro_user", "password": "x",
        "ssl_enabled": False,
    }


def test_client_connection_invisible_and_unpatchable_cross_tenant(client, monkeypatch):
    _seed_both_tenants()
    conn = main.client_connections_store.create(
        ECOM, connector_type="postgres", display_name="Warehouse", host="db.internal",
        port=5432, database_name="warehouse", username="ro_user", encrypted_password="enc",
        ssl_enabled=False, fingerprint="fp1", primary_table=None, primary_date_field=None,
        created_by=None,
    )
    assert main.client_connections_store.get(INSURANCE, conn["id"]) is None

    _as(monkeypatch, INSURANCE)
    resp = client.patch(
        f"/api/admin/data-sources/connections/{conn['id']}", json=_dummy_connection_body()
    )
    assert resp.status_code == 404  # 404s on the ownership check, before any real connection test


def test_source_request_and_upload_isolated_per_client():
    req = main.source_requests_store.create(
        ECOM, connector_type="priority", details={"contact_email": "a@x.com"}, created_by=None
    )
    assert main.source_requests_store.get(INSURANCE, req["id"]) is None
    assert req["id"] not in [r["id"] for r in main.source_requests_store.list_for_client(INSURANCE)]

    upload = main.uploads_store.create(
        ECOM, table_name="orders_upload", original_filename="orders.csv",
        column_count=4, row_count=100, uploaded_by=None,
    )
    assert main.uploads_store.get(INSURANCE, upload["id"]) is None


def test_data_sources_list_route_scoped_to_admins_own_tenant(client, monkeypatch):
    _seed_both_tenants()
    main.uploads_store.create(
        ECOM, table_name="orders_upload", original_filename="orders.csv",
        column_count=4, row_count=100, uploaded_by=None,
    )
    _as(monkeypatch, INSURANCE)
    cards = client.get("/api/admin/data-sources").json()
    assert not any(c.get("id") for c in cards if "orders_upload" in str(c))


# --- org users -----------------------------------------------------------------


def test_admin_users_list_scoped_to_admins_own_tenant(client, monkeypatch):
    _seed_both_tenants()
    _as(monkeypatch, INSURANCE)
    body = client.get("/api/admin/users").json()
    emails = {u["email"] for u in body["users"]}
    # The seeded roster reuses the same demo names/emails per client (see
    # OrgUserStore.seed_demo_users) -- the guarantee under test is COUNT and
    # SHAPE match the insurance roster alone, not a disjoint email set.
    assert body["total"] == 10
    assert emails  # sanity: not accidentally empty

    # No GET-by-id route exists for a single user; PATCH is the closest --
    # prove editing an id from the OTHER tenant's roster 404s.
    ecom_user = main.org_user_store.list_users(ECOM)[0]
    patch_resp = client.patch(f"/api/admin/users/{ecom_user['id']}", json={"title": "hijacked"})
    assert patch_resp.status_code == 404
