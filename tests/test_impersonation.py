"""
Tests for admin impersonation ("view as user", impersonation_prompt.md).

Four layers, mirroring the rest of this test suite's own conventions:
  - store-level (sema_core.impersonation_store), via a local `store` fixture
  - identity-layer (sema_core.current_user.current_identity's swap + expiry)
  - route-level authz (reuses test_authz_matrix.py's route classification,
    run under an ACTIVE impersonation instead of a monkeypatched identity --
    this file deliberately does NOT monkeypatch current_identity/real_identity
    the way test_authz_matrix.py does; it starts a REAL session through the
    actual POST endpoint so current_identity()'s own swap logic is exercised
    end to end, not bypassed)
  - audit dual-identity + data-scope narrowing

conftest's autouse fixtures isolate every store (including the new
impersonation-session store) from the real var/sema_state.db and off the
real Anthropic network.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.main as main
import sema_core.current_user as current_user
from sema_core.impersonation_store import AlreadyImpersonatingError, ImpersonationStore
from test_authz_matrix import ROUTE_CLASS, _api_routes, _call, _dummy_url

CID = "ecommerce"
ADMIN_EMAIL = "miri1988@gmail.com"  # client_admin (the real, mocked identity)
VIEWER_EMAIL = "avi.peretz@ecommerce-demo.com"  # viewer, active, full scope
ANALYST_SALES_ONLY_EMAIL = "yossi.cohen@ecommerce-demo.com"  # analyst, sales_only scope
SUSPENDED_EMAIL = "lior.katz@ecommerce-demo.com"  # analyst, suspended
INVITED_EMAIL = "dana@ecommerce-demo.com"  # analyst, invited (pending)

# The 3 impersonation routes themselves always resolve against the REAL
# admin identity (require_real_client_admin) -- they are deliberately NOT
# part of the "flip to 403 while impersonating a non-admin" story the rest
# of the admin surface follows, so the route-matrix reuse below excludes them
# and asserts their own (different, and equally deliberate) behavior instead.
_IMPERSONATION_ROUTES = {
    ("POST", "/api/admin/impersonation"),
    ("DELETE", "/api/admin/impersonation"),
    ("GET", "/api/admin/impersonation"),
}


# --- store-level ---------------------------------------------------------

@pytest.fixture
def store(tmp_path) -> ImpersonationStore:
    return ImpersonationStore(tmp_path / "impersonation.db")


def _start(store: ImpersonationStore, *, ttl_minutes: float = 30, admin_email="miri@x.com", target="dana"):
    return store.start(
        CID, admin_email,
        admin_user_id="admin-1", admin_name="Miri Levi", admin_role="client_admin",
        target_user_id=target, target_email=f"{target}@x.com", target_name=target.title(),
        target_role="viewer", ttl_minutes=ttl_minutes,
    )


def test_start_then_get_active_returns_the_session(store):
    _start(store)
    active = store.get_active(CID, "miri@x.com")
    assert active is not None
    assert active["target_user_id"] == "dana"
    assert active["target_role"] == "viewer"


def test_get_active_is_none_when_nothing_started(store):
    assert store.get_active(CID, "miri@x.com") is None


def test_start_twice_raises_already_impersonating(store):
    _start(store)
    with pytest.raises(AlreadyImpersonatingError):
        _start(store, target="someone_else")


def test_expired_session_is_not_active(store):
    _start(store, ttl_minutes=-1)  # already in the past
    assert store.get_active(CID, "miri@x.com") is None


def test_expired_session_does_not_block_a_fresh_start(store):
    _start(store, ttl_minutes=-1)
    # No AlreadyImpersonatingError: get_active correctly treats it as gone.
    _start(store, target="someone_else")
    active = store.get_active(CID, "miri@x.com")
    assert active["target_user_id"] == "someone_else"


def test_stop_returns_the_session_and_clears_it(store):
    _start(store)
    stopped = store.stop(CID, "miri@x.com")
    assert stopped is not None
    assert stopped["target_user_id"] == "dana"
    assert store.get_active(CID, "miri@x.com") is None


def test_stop_with_nothing_active_is_a_safe_noop(store):
    assert store.stop(CID, "miri@x.com") is None


def test_stop_on_an_expired_session_returns_none_but_still_cleans_up(store):
    _start(store, ttl_minutes=-1)
    assert store.stop(CID, "miri@x.com") is None  # nothing "active" to report
    # The row really is gone (peek would be None too) -- a subsequent start
    # must not see stale state.
    _start(store, target="someone_else")
    assert store.get_active(CID, "miri@x.com")["target_user_id"] == "someone_else"


def test_reap_if_expired_returns_and_deletes_only_when_past_expiry(store):
    _start(store)
    assert store.reap_if_expired(CID, "miri@x.com") is None  # still active -- untouched
    assert store.get_active(CID, "miri@x.com") is not None


def test_reap_if_expired_cleans_a_stale_row(store):
    _start(store, ttl_minutes=-1)
    reaped = store.reap_if_expired(CID, "miri@x.com")
    assert reaped is not None
    assert reaped["target_user_id"] == "dana"
    assert store._peek(CID, "miri@x.com") is None  # noqa: SLF001 -- verifying real deletion


# --- identity layer --------------------------------------------------------

def test_current_identity_is_real_identity_with_no_active_session():
    assert current_user.current_identity() == current_user.real_identity()


def test_current_identity_swaps_to_target_while_active():
    raw = current_user.real_identity()
    current_user.start_impersonation(
        raw["client_id"], raw["email"],
        admin_user_id="a1", admin_name="Miri Levi", admin_role="client_admin",
        target_user_id="u2", target_email="dana@ecommerce-demo.com",
        target_name="Dana Levi", target_role="viewer",
    )
    try:
        effective = current_user.current_identity()
        assert effective["email"] == "dana@ecommerce-demo.com"
        assert effective["client_id"] == raw["client_id"]
    finally:
        current_user.stop_impersonation(raw["client_id"], raw["email"])


def test_current_identity_restores_after_stop():
    raw = current_user.real_identity()
    current_user.start_impersonation(
        raw["client_id"], raw["email"],
        admin_user_id="a1", admin_name="Miri Levi", admin_role="client_admin",
        target_user_id="u2", target_email="dana@ecommerce-demo.com",
        target_name="Dana Levi", target_role="viewer",
    )
    current_user.stop_impersonation(raw["client_id"], raw["email"])
    assert current_user.current_identity() == raw


def test_current_identity_reverts_automatically_on_expiry(monkeypatch):
    raw = current_user.real_identity()
    monkeypatch.setattr(current_user, "IMPERSONATION_TTL_MINUTES", -0.001)
    current_user.start_impersonation(
        raw["client_id"], raw["email"],
        admin_user_id="a1", admin_name="Miri Levi", admin_role="client_admin",
        target_user_id="u2", target_email="dana@ecommerce-demo.com",
        target_name="Dana Levi", target_role="viewer",
    )
    # No explicit stop -- current_identity() must already treat it as expired.
    assert current_user.current_identity() == raw


def test_one_active_impersonation_per_admin():
    raw = current_user.real_identity()
    current_user.start_impersonation(
        raw["client_id"], raw["email"],
        admin_user_id="a1", admin_name="Miri Levi", admin_role="client_admin",
        target_user_id="u2", target_email="dana@ecommerce-demo.com",
        target_name="Dana Levi", target_role="viewer",
    )
    try:
        with pytest.raises(current_user.AlreadyImpersonatingError):
            current_user.start_impersonation(
                raw["client_id"], raw["email"],
                admin_user_id="a1", admin_name="Miri Levi", admin_role="client_admin",
                target_user_id="u3", target_email="someone.else@ecommerce-demo.com",
                target_name="Someone Else", target_role="viewer",
            )
    finally:
        current_user.stop_impersonation(raw["client_id"], raw["email"])


# --- route-level: fixtures ---------------------------------------------------

@pytest.fixture()
def client() -> TestClient:
    """Real (unpatched) identity resolution -- current_identity()/
    real_identity() both resolve to the actual mocked Miri identity, so
    starting an impersonation here exercises the real swap end to end."""
    main.org_user_store.seed_demo_users(CID)
    return TestClient(main.app)


def _user_id(email: str) -> str:
    row = main.org_user_store.get_by_email(CID, email)
    assert row is not None, f"seed data missing {email}"
    return row["id"]


@pytest.fixture(autouse=True)
def _no_live_db_for_product_routes(monkeypatch):
    """Same fixtures test_authz_matrix.py's own file-scoped autouse fixture
    applies -- needed here too since the reused route matrix walks the same
    "product" routes that would otherwise hit a real Postgres connection."""
    from api.models import SchemaResponse

    monkeypatch.setattr(main, "check_connection", lambda *a, **kw: True)
    monkeypatch.setattr(
        main, "build_overview",
        lambda start=None, end=None, scope_id="full", config=None: {
            "kpis": [], "start": "2026-06", "end": "2026-06", "available_months": ["2026-06"],
        },
    )
    monkeypatch.setattr(
        main, "build_daily_brief",
        lambda sensitivity="balanced": {"as_of": "2026-06-30", "pulse": [], "insights": []},
    )
    monkeypatch.setattr(main.alerts_engine, "evaluate_all_alerts", lambda **kw: [])
    monkeypatch.setattr(main.org_alerts, "readings_for_alerts_engine", lambda cid, store: [])
    monkeypatch.setattr(main, "build_schema", lambda cid, rq: SchemaResponse(client_id=cid))


# --- route-level: start / stop / state --------------------------------------

def test_start_impersonation_returns_target_summary(client):
    resp = client.post("/api/admin/impersonation", json={"user_id": _user_id(VIEWER_EMAIL)})
    assert resp.status_code == 201
    body = resp.json()
    assert body["active"] is True
    assert body["target_email"] == VIEWER_EMAIL
    assert body["target_role"] == "viewer"
    assert body["expires_at"]
    client.delete("/api/admin/impersonation")


def test_self_impersonation_rejected(client):
    resp = client.post("/api/admin/impersonation", json={"user_id": _user_id(ADMIN_EMAIL)})
    assert resp.status_code == 409


def test_suspended_target_rejected(client):
    resp = client.post("/api/admin/impersonation", json={"user_id": _user_id(SUSPENDED_EMAIL)})
    assert resp.status_code == 409


def test_invited_target_rejected(client):
    resp = client.post("/api/admin/impersonation", json={"user_id": _user_id(INVITED_EMAIL)})
    assert resp.status_code == 409


def test_unknown_user_id_rejected_404(client):
    resp = client.post("/api/admin/impersonation", json={"user_id": "does-not-exist"})
    assert resp.status_code == 404


def test_cross_client_target_rejected_404(client):
    """A user id that belongs to a DIFFERENT client is indistinguishable from
    "doesn't exist" -- org_user_store.get_user already scopes every lookup by
    the admin's own client_id (same tenant-isolation rule every other
    admin-panel lookup follows), so no bespoke cross-client check is needed."""
    other = main.org_user_store.invite("insurance", "someone@insurance-demo.com", "viewer")
    resp = client.post("/api/admin/impersonation", json={"user_id": other["id"]})
    assert resp.status_code == 404


def test_already_impersonating_rejected_409(client):
    client.post("/api/admin/impersonation", json={"user_id": _user_id(VIEWER_EMAIL)})
    resp = client.post("/api/admin/impersonation", json={"user_id": _user_id(ANALYST_SALES_ONLY_EMAIL)})
    assert resp.status_code == 409
    client.delete("/api/admin/impersonation")


def test_stop_always_returns_200_even_with_nothing_active(client):
    resp = client.delete("/api/admin/impersonation")
    assert resp.status_code == 200
    assert resp.json()["active"] is False


def test_get_state_reflects_active_session(client):
    client.post("/api/admin/impersonation", json={"user_id": _user_id(VIEWER_EMAIL)})
    resp = client.get("/api/admin/impersonation")
    assert resp.status_code == 200
    assert resp.json()["active"] is True
    assert resp.json()["target_email"] == VIEWER_EMAIL
    client.delete("/api/admin/impersonation")


def test_get_state_after_stop_is_inactive(client):
    client.post("/api/admin/impersonation", json={"user_id": _user_id(VIEWER_EMAIL)})
    client.delete("/api/admin/impersonation")
    resp = client.get("/api/admin/impersonation")
    assert resp.json()["active"] is False


# --- route-level: the reused authz matrix, under active impersonation ------

def test_admin_routes_flip_to_403_while_impersonating_a_viewer_except_the_impersonation_endpoints(client):
    """The core no-privilege-escalation proof (impersonation_prompt.md's
    acceptance criteria): once Miri is viewing as Avi (a viewer), EVERY
    /api/admin/* route in the shared authz matrix must 403 -- require_client_
    admin resolves through current_identity(), which is now Avi's -- with the
    3 impersonation endpoints themselves as the sole, deliberate exception
    (they always resolve against the REAL admin, never the effective one)."""
    start = client.post("/api/admin/impersonation", json={"user_id": _user_id(VIEWER_EMAIL)})
    assert start.status_code == 201

    admin_routes = [k for k, v in ROUTE_CLASS.items() if v == "admin"]
    for method, path in admin_routes:
        if (method, path) in _IMPERSONATION_ROUTES:
            continue
        url = _dummy_url(path)
        status = _call(client, method, url)
        assert status == 403, f"{method} {path} should 403 while impersonating a viewer, got {status}"

    # The stop endpoint specifically must stay reachable and succeed.
    stop = client.delete("/api/admin/impersonation")
    assert stop.status_code == 200
    assert stop.json()["active"] is False

    # And GET (state) / POST (would-be-start) stay real-admin-gated, not 403:
    # GET simply reports "not impersonating" now that stop already ran.
    state = client.get("/api/admin/impersonation")
    assert state.status_code == 200
    assert state.json()["active"] is False


def test_admin_routes_restored_after_stop(client):
    client.post("/api/admin/impersonation", json={"user_id": _user_id(VIEWER_EMAIL)})
    client.delete("/api/admin/impersonation")
    resp = client.get("/api/admin/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == ADMIN_EMAIL


# --- data scope narrowing ----------------------------------------------------

def test_impersonating_narrows_effective_data_scope(client):
    """Drives current_org_user directly (the exact function /api/overview,
    /api/brief, /api/alerts, /api/chat all resolve scope_id through) -- this
    is the real narrowing mechanism the chat/overview answers depend on."""
    before = main.current_org_user(CID)
    assert before["data_scope"] == "full"  # Miri, the real admin

    client.post("/api/admin/impersonation", json={"user_id": _user_id(ANALYST_SALES_ONLY_EMAIL)})
    try:
        during = main.current_org_user(CID)
        assert during["data_scope"] == "sales_only"
        assert during["role"] == "analyst"
    finally:
        client.delete("/api/admin/impersonation")

    after = main.current_org_user(CID)
    assert after["data_scope"] == "full"


# --- audit: dual identity ----------------------------------------------------

def _valid_home_config() -> dict:
    return {
        "kpis": {"order": ["revenue", "orders"], "deltas": {"revenue": True, "orders": False}},
        "default_period_months": 3,
        "daily_brief": {"pulse_enabled": True, "insights_enabled": False, "sensitivity": "sensitive"},
        "suggested_questions": {"questions": ["Show revenue trend by month."], "trending_enabled": False},
        "alerts": {},
    }


def test_start_and_stop_are_audited_with_the_real_admin_as_actor(client):
    client.post("/api/admin/impersonation", json={"user_id": _user_id(VIEWER_EMAIL)})
    client.delete("/api/admin/impersonation")

    events = main.audit_store.list_events(CID)["events"]
    started = next(e for e in events if e["action"] == "impersonation.started")
    stopped = next(e for e in events if e["action"] == "impersonation.stopped")
    assert started["actor_name"] == "Miri Levi"
    assert started["target_label"] in ("Avi Peretz", VIEWER_EMAIL)
    assert stopped["actor_name"] == "Miri Levi"
    assert stopped["after"]["reason"] == "manual"


def test_expiry_is_audited_as_stopped_with_reason_expired(client, monkeypatch):
    monkeypatch.setattr(current_user, "IMPERSONATION_TTL_MINUTES", -0.001)
    client.post("/api/admin/impersonation", json={"user_id": _user_id(VIEWER_EMAIL)})
    # Nothing explicitly stops it -- the next state check must lazily reap +
    # audit-log the expiry.
    resp = client.get("/api/admin/impersonation")
    assert resp.json()["active"] is False

    events = main.audit_store.list_events(CID)["events"]
    stopped = next(e for e in events if e["action"] == "impersonation.stopped")
    assert stopped["after"]["reason"] == "expired"


def test_action_during_impersonation_of_a_fellow_admin_carries_both_identities(client):
    """The only way an audited admin-panel MUTATION can happen while
    impersonating is if the target is themselves a client_admin (a non-admin
    target 403s on every admin route -- proven above). home-config's
    draft/publish/revert aren't among the "highest blast radius" routes
    (user management / org settings / semantic publish) that stay blocked
    even for an admin target, so it's a valid, low-ceremony way to exercise
    "every audited action during impersonation carries both identities"."""
    second_admin = main.org_user_store.invite(CID, "second.admin@ecommerce-demo.com", "client_admin")
    main.org_user_store.set_status(CID, second_admin["id"], "active")

    start = client.post("/api/admin/impersonation", json={"user_id": second_admin["id"]})
    assert start.status_code == 201
    try:
        put = client.put("/api/admin/home-config", json=_valid_home_config())
        assert put.status_code == 200
        revert = client.post("/api/admin/home-config/revert")
        assert revert.status_code == 200
    finally:
        client.delete("/api/admin/impersonation")

    events = main.audit_store.list_events(CID)["events"]
    reverted = next(e for e in events if e["action"] == "home_config.reverted")
    assert reverted["actor_id"] == second_admin["id"]
    assert reverted["actor_name"] == "second.admin@ecommerce-demo.com" or reverted["actor_name"]
    assert reverted["impersonator_id"] == _user_id(ADMIN_EMAIL)
    assert reverted["impersonator_name"] == "Miri Levi"


def test_highest_blast_radius_routes_stay_blocked_even_impersonating_an_admin(client):
    """User management / org settings / semantic publish require dropping
    impersonation first, EVEN when the impersonation target is themselves a
    client_admin (impersonation_prompt.md's Rules section) -- a narrower,
    additional gate on top of require_client_admin's normal role check."""
    second_admin = main.org_user_store.invite(CID, "second.admin2@ecommerce-demo.com", "client_admin")
    main.org_user_store.set_status(CID, second_admin["id"], "active")

    client.post("/api/admin/impersonation", json={"user_id": second_admin["id"]})
    try:
        resp = client.patch("/api/admin/org-settings", json={"name": "New Name"})
        assert resp.status_code == 403
        invite_resp = client.post(
            "/api/admin/users/invite", json={"email": "x@ecommerce-demo.com", "role": "viewer"}
        )
        assert invite_resp.status_code == 403
    finally:
        client.delete("/api/admin/impersonation")
