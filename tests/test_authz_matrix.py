"""
Systematic authorization matrix (backend_qa_prompt.md item 1).

Auto-discovers EVERY registered FastAPI route and asserts it against an
explicit classification table below -- "admin" (must require an active
client_admin; analyst/viewer get 403) or "open" (chat/product endpoints,
reachable by every role, including a completely public/unauthenticated
caller). The classification is a manually-maintained allowlist, not derived
from what the code happens to do (Depends(require_client_admin) presence) --
that's the whole point: a new route that FORGETS to add the admin dependency
would still "auto-classify" as fine if we inferred it from the code, which is
exactly the bug class this test exists to catch. `test_every_route_is_classified`
fails loudly the moment a new route is added without a matching entry here.

We only assert the AUTH-BOUNDARY status code (401/403 vs. not), never full
request success -- a 404/422/409/500 downstream of a passed auth check is
still proof the auth check passed, and asserting anything stronger would
couple this file to every route's business logic and its own live-DB/session
state. Bodies are sent as `{}` (or omitted) for every mutating call: every
route's Pydantic request model either 422s on the missing required fields
(before any handler code runs -- see the `require_client_admin`-runs-first
proof below) or is safely all-default, so no destructive side effect ever
happens here.

Per-route business logic that WOULD otherwise hit a real Postgres connection
(the four deterministic "product" endpoints, plus /api/health's connectivity
probe) is monkeypatched to trivial fixtures, same convention as
test_api_overview.py/test_api_brief.py/test_api_alerts.py -- this project's
tests must never depend on a live database.

No SEMA_ENV=production-gated dev-only route exists in the app today (audited
during deployment_prep_prompt.md and reconfirmed here via the same route
walk) -- so there is no "prod_gated -> 404" bucket to populate yet. If one is
ever added, give it a third classification value here and a dedicated test.
"""

from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import api.main as main
from api.models import SchemaResponse

CID = "ecommerce"
ADMIN_EMAIL = "miri1988@gmail.com"  # client_admin
ANALYST_EMAIL = "noa.berman@ecommerce-demo.com"  # analyst, active
VIEWER_EMAIL = "avi.peretz@ecommerce-demo.com"  # viewer, active

# --- the classification table -----------------------------------------------
# (method, raw FastAPI path template) -> "admin" | "open"
ROUTE_CLASS: dict[tuple[str, str], str] = {
    ("GET", "/healthz"): "open",
    ("GET", "/api/health"): "open",
    ("GET", "/api/clients"): "open",
    ("POST", "/api/client"): "open",
    ("GET", "/api/org-settings"): "open",
    ("POST", "/api/chat"): "open",
    ("POST", "/api/chat/stream"): "open",
    ("GET", "/api/conversations"): "open",
    ("GET", "/api/conversations/{conversation_id}"): "open",
    ("POST", "/api/feedback"): "open",
    ("POST", "/api/exports/table"): "open",
    ("PATCH", "/api/conversations/{conversation_id}"): "open",
    ("DELETE", "/api/conversations/{conversation_id}"): "open",
    ("GET", "/api/conversations/{conversation_id}/threads"): "open",
    ("GET", "/api/conversations/{conversation_id}/threads/{thread_id}"): "open",
    ("GET", "/api/admin/me"): "admin",
    ("GET", "/api/admin/roles"): "admin",
    ("GET", "/api/admin/data-scopes"): "admin",
    ("GET", "/api/admin/users"): "admin",
    ("POST", "/api/admin/users/invite"): "admin",
    ("PATCH", "/api/admin/users/{user_id}"): "admin",
    ("DELETE", "/api/admin/users/{user_id}"): "admin",
    ("POST", "/api/admin/users/{user_id}/resend-invite"): "admin",
    ("GET", "/api/admin/semantic"): "admin",
    ("PUT", "/api/admin/semantic/{section}/{item_key}"): "admin",
    ("DELETE", "/api/admin/semantic/{section}/{item_key}"): "admin",
    ("POST", "/api/admin/semantic/validate"): "admin",
    ("POST", "/api/admin/semantic/publish"): "admin",
    ("GET", "/api/admin/semantic/versions"): "admin",
    ("POST", "/api/admin/semantic/versions/{version_id}/restore"): "admin",
    ("GET", "/api/admin/org-settings"): "admin",
    ("PATCH", "/api/admin/org-settings"): "admin",
    ("GET", "/api/admin/org-settings/currencies"): "admin",
    ("GET", "/api/admin/org-settings/timezones"): "admin",
    ("GET", "/api/admin/org-settings/retention-preview"): "admin",
    ("POST", "/api/admin/org-settings/logo"): "admin",
    # Intentionally NOT admin-gated -- the sidebar shows the org logo to every
    # user, not just admins (same visibility rule as /api/clients). See its
    # own docstring in api/main.py.
    ("GET", "/api/admin/org-settings/logo/{client_id}"): "open",
    ("GET", "/api/admin/audit"): "admin",
    ("GET", "/api/admin/audit/export"): "admin",
    ("GET", "/api/admin/alerts-catalog"): "admin",
    ("GET", "/api/admin/alerts/templates"): "admin",
    ("GET", "/api/admin/alerts/metrics"): "admin",
    ("GET", "/api/admin/alerts"): "admin",
    ("POST", "/api/admin/alerts/test"): "admin",
    ("POST", "/api/admin/alerts"): "admin",
    ("PATCH", "/api/admin/alerts/{alert_id}"): "admin",
    ("DELETE", "/api/admin/alerts/{alert_id}"): "admin",
    ("GET", "/api/admin/home-config"): "admin",
    ("PUT", "/api/admin/home-config"): "admin",
    ("POST", "/api/admin/home-config/publish"): "admin",
    ("POST", "/api/admin/home-config/revert"): "admin",
    ("POST", "/api/admin/home-config/preview"): "admin",
    ("GET", "/api/admin/data-sources"): "admin",
    ("GET", "/api/admin/data-sources/catalog"): "admin",
    ("POST", "/api/admin/data-sources/test"): "admin",
    ("POST", "/api/admin/data-sources/connections"): "admin",
    ("PATCH", "/api/admin/data-sources/connections/{connection_id}"): "admin",
    ("GET", "/api/admin/data-sources/sheets-info"): "admin",
    ("POST", "/api/admin/data-sources/requests"): "admin",
    ("POST", "/api/admin/data-sources/interest"): "admin",
    ("POST", "/api/admin/data-sources/upload"): "admin",
    ("POST", "/api/admin/data-sources/uploads/{upload_id}/replace"): "admin",
    ("POST", "/api/admin/data-sources/{source_id}/report-problem"): "admin",
    ("GET", "/api/overview"): "open",
    ("GET", "/api/brief"): "open",
    ("GET", "/api/alerts"): "open",
    ("GET", "/api/popular-questions"): "open",
    ("GET", "/api/schema"): "open",
    # Prod-only SPA catch-all (present only when frontend/dist exists -- the
    # prod Docker build's output). Public by design: serves static assets /
    # index.html for the client-side router, no identity involved.
    ("GET", "/{full_path:path}"): "open",
}

# FastAPI's own auto-generated routes -- never part of the app's own surface.
_FRAMEWORK_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}

_PATH_PARAM = re.compile(r"\{[^}]+\}")


def _dummy_url(path_template: str) -> str:
    """Fill every {param} segment with a harmless placeholder that can never
    collide with a real id, so every request 404s/422s on "not found", not on
    a routing mismatch."""
    return _PATH_PARAM.sub("does-not-exist", path_template)


def _api_routes() -> list[APIRoute]:
    return [
        r
        for r in main.app.routes
        if isinstance(r, APIRoute) and r.path not in _FRAMEWORK_PATHS
    ]


def test_every_registered_route_is_classified():
    """The safety net itself: a new route with no entry here fails the suite
    immediately, forcing a conscious authz decision instead of a silent gap."""
    unclassified = []
    for route in _api_routes():
        for method in sorted(route.methods - {"HEAD"}):
            if (method, route.path) not in ROUTE_CLASS:
                unclassified.append((method, route.path))
    assert not unclassified, (
        f"New route(s) added without an authz classification in "
        f"tests/test_authz_matrix.py's ROUTE_CLASS: {unclassified}"
    )


@pytest.fixture(autouse=True)
def _no_live_db_for_product_routes(monkeypatch):
    """The handful of routes that call real Postgres-backed report/schema
    functions get trivial, deterministic fixtures instead -- same convention
    as test_api_overview.py/test_api_brief.py/test_api_alerts.py. Every other
    route in this file is SQLite-only (the app's own metadata stores, already
    isolated by conftest.py) or pure config/logic, so nothing else needs it."""
    monkeypatch.setattr(main, "check_connection", lambda *a, **kw: True)
    monkeypatch.setattr(
        main,
        "build_overview",
        lambda start=None, end=None, scope_id="full", config=None: {
            "kpis": [], "start": "2026-06", "end": "2026-06", "available_months": ["2026-06"],
        },
    )
    monkeypatch.setattr(
        main,
        "build_daily_brief",
        lambda sensitivity="balanced": {"as_of": "2026-06-30", "pulse": [], "insights": []},
    )
    monkeypatch.setattr(main.alerts_engine, "evaluate_all_alerts", lambda **kw: [])
    # org_alerts.readings_for_alerts_engine evaluates every migrated org
    # alert's CURRENT reading via alert_templates.evaluate_current, which
    # runs a real SQL query against Postgres -- unlike evaluate_all_alerts
    # (the YAML-alert path), this one is a genuine, by-design live-DB call
    # inside /api/alerts and the home-config preview route, so it needs its
    # own mock rather than being covered by the one above.
    monkeypatch.setattr(main.org_alerts, "readings_for_alerts_engine", lambda cid, store: [])
    monkeypatch.setattr(main, "build_schema", lambda cid, rq: SchemaResponse(client_id=cid))


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    main.org_user_store.seed_demo_users(CID)
    return TestClient(main.app)


def _as(monkeypatch, email: str) -> None:
    monkeypatch.setattr(main, "current_identity", lambda: {"client_id": CID, "email": email})


def _call(client: TestClient, method: str, url: str) -> int:
    if method == "GET":
        return client.get(url).status_code
    if method == "DELETE":
        return client.delete(url).status_code
    # POST/PUT/PATCH: an empty JSON body either 422s on missing required
    # fields (before any handler code runs) or is a harmless all-default
    # payload -- see the module docstring.
    return client.request(method, url, json={}).status_code


@pytest.mark.parametrize(
    "route_key",
    [k for k, v in ROUTE_CLASS.items() if v == "admin"],
    ids=lambda k: f"{k[0]} {k[1]}",
)
def test_admin_route_rejects_non_admin_roles(route_key, client, monkeypatch):
    method, path = route_key
    url = _dummy_url(path)
    for email in (ANALYST_EMAIL, VIEWER_EMAIL):
        _as(monkeypatch, email)
        status = _call(client, method, url)
        assert status == 403, (
            f"{method} {path} must reject a non-admin identity ({email}) with 403, got {status}"
        )


@pytest.mark.parametrize(
    "route_key",
    [k for k, v in ROUTE_CLASS.items() if v == "admin"],
    ids=lambda k: f"{k[0]} {k[1]}",
)
def test_admin_route_accepts_the_admin_role(route_key, client, monkeypatch):
    method, path = route_key
    url = _dummy_url(path)
    _as(monkeypatch, ADMIN_EMAIL)
    status = _call(client, method, url)
    assert status not in (401, 403), (
        f"{method} {path} wrongly rejected the client_admin identity with {status}"
    )


@pytest.mark.parametrize(
    "route_key",
    [k for k, v in ROUTE_CLASS.items() if v == "open"],
    ids=lambda k: f"{k[0]} {k[1]}",
)
def test_open_route_accepts_every_role(route_key, client, monkeypatch):
    method, path = route_key
    url = _dummy_url(path)
    for email in (ADMIN_EMAIL, ANALYST_EMAIL, VIEWER_EMAIL):
        _as(monkeypatch, email)
        status = _call(client, method, url)
        assert status not in (401, 403), (
            f"{method} {path} must be reachable by every role ({email}), got {status}"
        )


@pytest.mark.parametrize(
    "route_key",
    [k for k, v in ROUTE_CLASS.items() if v == "open"],
    ids=lambda k: f"{k[0]} {k[1]}",
)
def test_open_route_accepts_an_unresolvable_identity(route_key, client, monkeypatch):
    """Product/chat routes must keep working for whoever the mocked identity
    resolves to -- including "doesn't resolve at all" (current_org_user's
    _UNSCOPED_USER fallback), since there is no login yet and these routes
    are the ones a not-yet-onboarded caller can still legitimately reach."""
    method, path = route_key
    url = _dummy_url(path)
    _as(monkeypatch, "ghost@nowhere.com")
    status = _call(client, method, url)
    assert status not in (401, 403), (
        f"{method} {path} must not gate on identity resolution, got {status}"
    )
