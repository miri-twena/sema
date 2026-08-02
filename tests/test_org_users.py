"""
Tests for the organization-users store and the admin API (spec §6.1).

Store-level tests use a local `store` fixture (a fresh temp-file OrgUserStore
per test), mirroring test_conversation_store.py. Guards raise domain
exceptions, asserted via pytest.raises. Route-level tests use an inline
TestClient and monkeypatch the mocked identity, mirroring
test_title_generation.py.

conftest's autouse fixtures keep every test off the real var/sema_state.db and
off the real Anthropic network.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import api.main as main
from sema_core.org_user_store import (
    AdminScopeError,
    DuplicateEmailError,
    InvalidDataScopeError,
    LastAdminError,
    OrgUserNotFoundError,
    OrgUserStore,
)

CID = "ecommerce"


@pytest.fixture
def store(tmp_path) -> OrgUserStore:
    return OrgUserStore(tmp_path / "org_users.db")


def _admin(store: OrgUserStore, email="admin@x.com") -> dict:
    """Insert an active client_admin (via invite + activate) and return it."""
    u = store.invite(CID, email, "client_admin")
    return store.set_status(CID, u["id"], "active")


# --- last-admin guard ------------------------------------------------------

def test_cannot_delete_last_active_admin(store):
    admin = _admin(store)
    with pytest.raises(LastAdminError):
        store.delete(CID, admin["id"])


def test_cannot_downgrade_last_active_admin(store):
    admin = _admin(store)
    with pytest.raises(LastAdminError):
        store.set_role(CID, admin["id"], "analyst")


def test_cannot_suspend_last_active_admin(store):
    admin = _admin(store)
    with pytest.raises(LastAdminError):
        store.set_status(CID, admin["id"], "suspended")


def test_can_remove_admin_when_a_second_active_admin_exists(store):
    first = _admin(store, "a@x.com")
    _admin(store, "b@x.com")  # a second active admin
    # Now downgrading / suspending / deleting the first is allowed.
    assert store.set_role(CID, first["id"], "analyst")["role"] == "analyst"


def test_suspended_admin_does_not_count_as_active(store):
    active = _admin(store, "a@x.com")
    other = _admin(store, "b@x.com")
    store.set_status(CID, other["id"], "suspended")  # now only `active` is active
    with pytest.raises(LastAdminError):
        store.delete(CID, active["id"])  # can't remove the last ACTIVE admin


# --- duplicate invite ------------------------------------------------------

def test_duplicate_invite_rejected(store):
    store.invite(CID, "dup@x.com", "analyst")
    with pytest.raises(DuplicateEmailError):
        store.invite(CID, "dup@x.com", "viewer")


def test_duplicate_invite_is_case_insensitive(store):
    store.invite(CID, "Mixed@X.com", "analyst")
    with pytest.raises(DuplicateEmailError):
        store.invite(CID, "mixed@x.com", "analyst")


def test_duplicate_against_an_active_user_rejected(store):
    _admin(store, "person@x.com")  # active, not invited
    with pytest.raises(DuplicateEmailError):
        store.invite(CID, "person@x.com", "viewer")


def test_same_email_allowed_under_a_different_client(store):
    store.invite(CID, "shared@x.com", "analyst")
    # A different client is a different org -- the email is free there.
    assert store.invite("other", "shared@x.com", "analyst")["email"] == "shared@x.com"


# --- invite expiry ---------------------------------------------------------

def test_fresh_invite_is_not_expired(store):
    u = store.invite(CID, "new@x.com", "analyst")
    assert u["status"] == "invited"
    assert u["invite_expired"] is False


def test_past_expiry_surfaces_as_expired(store):
    u = store.invite(CID, "old@x.com", "analyst")
    # Force the expiry into the past directly in the DB.
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with store._connect() as conn:  # noqa: SLF001 -- test reaches into the store
        conn.execute(
            "UPDATE org_users SET invite_expires_at = ? WHERE id = ?", (past, u["id"])
        )
    assert store.get_user(CID, u["id"])["invite_expired"] is True


def test_resend_invite_clears_expiry(store):
    u = store.invite(CID, "old@x.com", "analyst")
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with store._connect() as conn:  # noqa: SLF001
        conn.execute(
            "UPDATE org_users SET invite_expires_at = ? WHERE id = ?", (past, u["id"])
        )
    refreshed = store.resend_invite(CID, u["id"])
    assert refreshed["invite_expired"] is False
    assert refreshed["invite_expires_at"] > datetime.now(timezone.utc).isoformat()


# --- not-found / tenant isolation ------------------------------------------

def test_get_user_wrong_client_is_indistinguishable_from_missing(store):
    u = store.invite(CID, "x@x.com", "analyst")
    with pytest.raises(OrgUserNotFoundError):
        store.get_user("other", u["id"])
    with pytest.raises(OrgUserNotFoundError):
        store.get_user(CID, "nope")


def test_mutations_require_ownership(store):
    u = store.invite(CID, "x@x.com", "analyst")
    for op in (
        lambda: store.set_role("other", u["id"], "viewer"),
        lambda: store.set_status("other", u["id"], "suspended"),
        lambda: store.delete("other", u["id"]),
        lambda: store.resend_invite("other", u["id"]),
    ):
        with pytest.raises(OrgUserNotFoundError):
            op()


# --- search / filter -------------------------------------------------------

def test_search_matches_name_and_email(store):
    store.invite(CID, "noa.berman@x.com", "analyst", name="Noa Berman")
    store.invite(CID, "yossi@x.com", "analyst", name="Yossi Cohen")
    assert [u["email"] for u in store.list_users(CID, q="berman")] == ["noa.berman@x.com"]
    assert [u["name"] for u in store.list_users(CID, q="yossi")] == ["Yossi Cohen"]


def test_role_filter(store):
    _admin(store, "admin@x.com")
    store.invite(CID, "an@x.com", "analyst")
    assert {u["role"] for u in store.list_users(CID, role="analyst")} == {"analyst"}


# --- pagination (users_pagination_prompt.md) --------------------------------

def test_list_users_paging_returns_the_right_slice(store):
    # 5 analysts, alphabetical within a role (list_users' own ordering) --
    # name them so alpha order is predictable: A, B, C, D, E.
    for letter in "ABCDE":
        store.invite(CID, f"{letter.lower()}@x.com", "analyst", name=f"{letter} User")
    page1 = store.list_users(CID, page=1, page_size=2)
    page2 = store.list_users(CID, page=2, page_size=2)
    page3 = store.list_users(CID, page=3, page_size=2)
    assert [u["name"] for u in page1] == ["A User", "B User"]
    assert [u["name"] for u in page2] == ["C User", "D User"]
    assert [u["name"] for u in page3] == ["E User"]  # partial last page


def test_list_users_unpaged_when_page_args_omitted(store):
    for letter in "ABC":
        store.invite(CID, f"{letter.lower()}@x.com", "analyst", name=f"{letter} User")
    assert len(store.list_users(CID)) == 3  # no page/page_size -> everyone, one call


def test_count_users_matches_the_same_filters_as_list_users(store):
    _admin(store, "admin@x.com")
    store.invite(CID, "noa.berman@x.com", "analyst", name="Noa Berman")
    store.invite(CID, "yossi@x.com", "analyst", name="Yossi Cohen")
    assert store.count_users(CID) == 3
    assert store.count_users(CID, role="analyst") == 2
    assert store.count_users(CID, q="berman") == 1
    # The filtered COUNT must agree with the filtered LIST's length -- the
    # pager's total has to describe the same set list_users actually returns.
    assert store.count_users(CID, role="analyst") == len(store.list_users(CID, role="analyst"))


# --- seed ------------------------------------------------------------------

def test_seed_inserts_ten_users_with_expected_shape(store):
    n = store.seed_demo_users(CID)
    assert n == 10
    users = store.list_users(CID)
    assert len(users) == 10
    assert sum(1 for u in users if u["status"] == "suspended") == 1
    assert sum(1 for u in users if u["status"] == "invited") == 1
    admins = [u for u in users if u["role"] == "client_admin"]
    assert len(admins) == 1 and admins[0]["email"] == "miri1988@gmail.com"


def test_seed_is_idempotent(store):
    assert store.seed_demo_users(CID) == 10
    assert store.seed_demo_users(CID) == 0  # no-op the second time
    assert len(store.list_users(CID)) == 10


def test_seed_marks_founding_members_and_invited_provenance(store):
    """Miri, Dan, and Demo User are founding members (no inviter); everyone
    else was invited by Miri; the pending invite has an inviter but hasn't
    joined."""
    store.seed_demo_users(CID)
    users = {u["email"]: u for u in store.list_users(CID)}

    founding_emails = {"miri1988@gmail.com", "dan.avrahami@ecommerce-demo.com",
                        "demo.user@ecommerce-demo.com"}
    for email in founding_emails:
        u = users[email]
        assert u["invited_by"] is None
        assert u["invited_by_name"] is None
        assert u["joined_at"] is not None

    miri_id = users["miri1988@gmail.com"]["id"]
    invited_emails = set(users) - founding_emails
    for email in invited_emails:
        u = users[email]
        assert u["invited_by"] == miri_id
        assert u["invited_by_name"] == "Miri Levi"

    pending = users["dana@ecommerce-demo.com"]
    assert pending["status"] == "invited"
    assert pending["invited_by"] == miri_id
    assert pending["joined_at"] is None


# --- invited_by / joined_at --------------------------------------------------

def test_invite_stamps_invited_by(store):
    admin = _admin(store)
    invited = store.invite(CID, "new@x.com", "analyst", invited_by=admin["id"])
    assert invited["invited_by"] == admin["id"]
    assert invited["invited_by_name"] == admin["name"]
    assert invited["joined_at"] is None


def test_invite_without_invited_by_is_a_founding_member(store):
    u = store.invite(CID, "founder@x.com", "client_admin")
    assert u["invited_by"] is None
    assert u["invited_by_name"] is None


# --- schema migration --------------------------------------------------------

def test_migration_adds_invited_by_and_joined_at_columns(tmp_path):
    """A pre-existing org_users table (shipped before this feature) gets both
    new columns added via the guarded ALTER, without disturbing existing
    rows -- same pattern as test_conversation_store.py's legacy-schema test."""
    import sqlite3

    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE org_users ("
            "id TEXT PRIMARY KEY, client_id TEXT NOT NULL, "
            "name TEXT, email TEXT NOT NULL, title TEXT, "
            "role TEXT NOT NULL, status TEXT NOT NULL, "
            "invited_at TEXT, invite_expires_at TEXT, last_active_at TEXT, "
            "created_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO org_users (id, client_id, name, email, title, role, status, "
            "created_at) VALUES ('u1', 'ecommerce', 'Old User', 'old@x.com', 'CEO', "
            "'client_admin', 'active', '2025-01-01T00:00:00+00:00')"
        )

    store = OrgUserStore(path)  # opening runs the migration
    u = store.get_user("ecommerce", "u1")
    assert u["name"] == "Old User"  # pre-existing data untouched
    assert u["invited_by"] is None
    assert u["joined_at"] is None

    OrgUserStore(path)  # re-open: idempotent, no error


# --- route-level: auth + identity ------------------------------------------

def test_admin_endpoints_reject_non_admin(monkeypatch):
    """A viewer identity must get 403 from admin routes."""
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity",
        lambda: {"client_id": CID, "email": "avi.peretz@ecommerce-demo.com"},  # a viewer
    )
    client = TestClient(main.app)
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/admin/me").status_code == 403


def test_admin_endpoints_reject_unknown_identity(monkeypatch):
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "ghost@nowhere.com"}
    )
    client = TestClient(main.app)
    assert client.get("/api/admin/users").status_code == 403


def test_admin_me_returns_the_mocked_admin(monkeypatch):
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    client = TestClient(main.app)
    resp = client.get("/api/admin/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "miri1988@gmail.com"
    assert body["role"] == "client_admin"
    assert body["is_self"] is True


def test_admin_list_reports_member_and_pending_counts(monkeypatch):
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    client = TestClient(main.app)
    body = client.get("/api/admin/users").json()
    assert body["pending_count"] == 1
    assert body["member_count"] == 9
    assert len(body["users"]) == 10
    # 10 seeded < the 25 default page_size -> one page, filtered total == 10.
    assert body["total"] == 10
    assert body["page"] == 1
    assert body["page_size"] == 25


def test_admin_list_users_page_2_returns_remaining_slice(monkeypatch):
    """Filtered total AND page slicing, combined -- page_size below the seed
    count so there's a real second page to check."""
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    client = TestClient(main.app)
    page1 = client.get("/api/admin/users", params={"page_size": 6}).json()
    page2 = client.get("/api/admin/users", params={"page": 2, "page_size": 6}).json()
    assert page1["total"] == page2["total"] == 10
    assert len(page1["users"]) == 6
    assert len(page2["users"]) == 4  # remaining 10 - 6
    # No row appears on both pages.
    assert {u["id"] for u in page1["users"]}.isdisjoint({u["id"] for u in page2["users"]})


def test_admin_list_users_total_reflects_the_current_filter(monkeypatch):
    """total must be the FILTERED count, not the whole org -- otherwise the
    pager would offer pages that don't exist under the active filter."""
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    client = TestClient(main.app)
    all_body = client.get("/api/admin/users").json()
    role_body = client.get("/api/admin/users", params={"role": "viewer"}).json()
    assert role_body["total"] < all_body["total"]
    assert role_body["total"] == len(role_body["users"])  # under 25, so total == this page's rows
    assert all(u["role"] == "viewer" for u in role_body["users"])


def test_admin_invite_duplicate_returns_409(monkeypatch):
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    client = TestClient(main.app)
    resp = client.post(
        "/api/admin/users/invite", json={"email": "miri1988@gmail.com", "role": "viewer"}
    )
    assert resp.status_code == 409


def test_admin_invite_bad_email_returns_422(monkeypatch):
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    client = TestClient(main.app)
    resp = client.post("/api/admin/users/invite", json={"email": "not-an-email", "role": "viewer"})
    assert resp.status_code == 422


def test_admin_last_admin_downgrade_returns_409(monkeypatch):
    """Miri is the only admin in the seed -- downgrading her via the API is 409."""
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    client = TestClient(main.app)
    me = client.get("/api/admin/me").json()
    resp = client.patch(f"/api/admin/users/{me['id']}", json={"role": "analyst"})
    assert resp.status_code == 409


def test_admin_invite_stamps_invited_by_with_current_identity(monkeypatch):
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    client = TestClient(main.app)
    me = client.get("/api/admin/me").json()
    resp = client.post(
        "/api/admin/users/invite", json={"email": "newhire@ecommerce-demo.com", "role": "viewer"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["invited_by"] == me["id"]
    assert body["invited_by_name"] == "Miri Levi"


def test_admin_roles_catalog(monkeypatch):
    """The role catalog is the single copy source for the UI's legend/tooltip:
    3 roles, and the analyst/viewer parity note is present so the UI never has
    to hardcode it."""
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    client = TestClient(main.app)
    resp = client.get("/api/admin/roles")
    assert resp.status_code == 200
    roles = {r["id"]: r for r in resp.json()}
    assert set(roles) == {"client_admin", "analyst", "viewer"}
    assert all(r["label"] and r["description"] for r in roles.values())
    assert "identical" in roles["analyst"]["description"].lower()
    assert "identical" in roles["viewer"]["description"].lower()


def test_admin_roles_requires_admin(monkeypatch):
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity",
        lambda: {"client_id": CID, "email": "avi.peretz@ecommerce-demo.com"},  # a viewer
    )
    client = TestClient(main.app)
    assert client.get("/api/admin/roles").status_code == 403


# --- data_scope: store-level guards ------------------------------------------

def test_admin_invite_is_always_full_scope_regardless_of_request(store):
    admin = store.invite(CID, "admin@x.com", "client_admin", data_scope="sales_only")
    assert admin["data_scope"] == "full"


def test_non_admin_invite_defaults_to_no_financials(store):
    u = store.invite(CID, "analyst@x.com", "analyst")
    assert u["data_scope"] == "no_financials"


def test_non_admin_invite_honors_explicit_scope(store):
    u = store.invite(CID, "sales@x.com", "analyst", data_scope="sales_only")
    assert u["data_scope"] == "sales_only"


def test_invite_rejects_custom_scope(store):
    with pytest.raises(InvalidDataScopeError):
        store.invite(CID, "x@x.com", "analyst", data_scope="custom")


def test_set_data_scope_rejects_custom(store):
    u = store.invite(CID, "x@x.com", "analyst")
    with pytest.raises(InvalidDataScopeError):
        store.set_data_scope(CID, u["id"], "custom")


def test_set_data_scope_rejects_unknown_id(store):
    u = store.invite(CID, "x@x.com", "analyst")
    with pytest.raises(InvalidDataScopeError):
        store.set_data_scope(CID, u["id"], "not-a-real-scope")


def test_cannot_give_an_admin_a_non_full_scope(store):
    admin = _admin(store)
    with pytest.raises(AdminScopeError):
        store.set_data_scope(CID, admin["id"], "sales_only")


def test_admin_can_be_explicitly_set_to_full(store):
    admin = _admin(store)
    assert store.set_data_scope(CID, admin["id"], "full")["data_scope"] == "full"


def test_promoting_to_admin_resets_scope_to_full(store):
    u = store.invite(CID, "x@x.com", "analyst", data_scope="sales_only")
    promoted = store.set_role(CID, u["id"], "client_admin")
    assert promoted["data_scope"] == "full"


def test_downgrading_an_admin_leaves_their_scope_full(store):
    """set_role only forces 'full' on PROMOTION; downgrading doesn't need to
    touch data_scope at all since 'full' is always a valid value."""
    first = _admin(store, "a@x.com")
    _admin(store, "b@x.com")  # second admin so the downgrade isn't blocked
    downgraded = store.set_role(CID, first["id"], "analyst")
    assert downgraded["data_scope"] == "full"


def test_set_data_scope_on_a_non_admin_user_succeeds(store):
    u = store.invite(CID, "x@x.com", "analyst")
    updated = store.set_data_scope(CID, u["id"], "sales_only")
    assert updated["data_scope"] == "sales_only"


# --- data_scope: seed values --------------------------------------------------

def test_seed_data_scopes_match_spec(store):
    store.seed_demo_users(CID)
    by_email = {u["email"]: u for u in store.list_users(CID)}
    assert by_email["miri1988@gmail.com"]["data_scope"] == "full"
    assert by_email["dan.avrahami@ecommerce-demo.com"]["data_scope"] == "full"
    assert by_email["avi.peretz@ecommerce-demo.com"]["data_scope"] == "full"
    assert by_email["yossi.cohen@ecommerce-demo.com"]["data_scope"] == "sales_only"
    assert by_email["yossi.cohen@ecommerce-demo.com"]["title"] == "Sales Analyst"
    for email in (
        "demo.user@ecommerce-demo.com",
        "noa.berman@ecommerce-demo.com",
        "tamar.golan@ecommerce-demo.com",
        "lior.katz@ecommerce-demo.com",
        "dana@ecommerce-demo.com",
    ):
        assert by_email[email]["data_scope"] == "no_financials"


# --- data_scope: route-level ---------------------------------------------------

def test_admin_data_scopes_catalog(monkeypatch):
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    client = TestClient(main.app)
    resp = client.get("/api/admin/data-scopes")
    assert resp.status_code == 200
    scopes = {s["id"]: s for s in resp.json()}
    assert set(scopes) == {"full", "no_financials", "sales_only", "custom"}
    assert scopes["custom"]["selectable"] is False
    assert scopes["sales_only"]["included_domains"] == ["sales"]


def test_admin_data_scopes_requires_admin(monkeypatch):
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity",
        lambda: {"client_id": CID, "email": "avi.peretz@ecommerce-demo.com"},
    )
    client = TestClient(main.app)
    assert client.get("/api/admin/data-scopes").status_code == 403


def _client_as_miri(monkeypatch) -> TestClient:
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    return TestClient(main.app)


def test_admin_can_patch_a_users_data_scope(monkeypatch):
    client = _client_as_miri(monkeypatch)
    users = {u["email"]: u for u in client.get("/api/admin/users").json()["users"]}
    yossi = users["yossi.cohen@ecommerce-demo.com"]
    resp = client.patch(f"/api/admin/users/{yossi['id']}", json={"data_scope": "full"})
    assert resp.status_code == 200
    assert resp.json()["data_scope"] == "full"


def test_admin_cannot_change_own_data_scope(monkeypatch):
    client = _client_as_miri(monkeypatch)
    me = client.get("/api/admin/me").json()
    resp = client.patch(f"/api/admin/users/{me['id']}", json={"data_scope": "sales_only"})
    assert resp.status_code == 403


def test_patch_rejects_custom_scope(monkeypatch):
    client = _client_as_miri(monkeypatch)
    users = {u["email"]: u for u in client.get("/api/admin/users").json()["users"]}
    yossi = users["yossi.cohen@ecommerce-demo.com"]
    resp = client.patch(f"/api/admin/users/{yossi['id']}", json={"data_scope": "custom"})
    assert resp.status_code == 422


def test_patch_rejects_non_full_scope_on_an_admin(monkeypatch):
    client = _client_as_miri(monkeypatch)
    # Promote someone else to admin first, then try to scope them down.
    users = {u["email"]: u for u in client.get("/api/admin/users").json()["users"]}
    tamar = users["tamar.golan@ecommerce-demo.com"]
    client.patch(f"/api/admin/users/{tamar['id']}", json={"role": "client_admin"})
    resp = client.patch(f"/api/admin/users/{tamar['id']}", json={"data_scope": "no_financials"})
    assert resp.status_code == 409


def test_invite_with_explicit_data_scope(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/users/invite",
        json={"email": "newsales@ecommerce-demo.com", "role": "analyst", "data_scope": "sales_only"},
    )
    assert resp.status_code == 201
    assert resp.json()["data_scope"] == "sales_only"


def test_invite_without_data_scope_defaults_to_no_financials(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/users/invite",
        json={"email": "newanalyst@ecommerce-demo.com", "role": "analyst"},
    )
    assert resp.status_code == 201
    assert resp.json()["data_scope"] == "no_financials"


def test_invite_admin_ignores_requested_scope(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post(
        "/api/admin/users/invite",
        json={
            "email": "newadmin@ecommerce-demo.com",
            "role": "client_admin",
            "data_scope": "sales_only",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["data_scope"] == "full"
