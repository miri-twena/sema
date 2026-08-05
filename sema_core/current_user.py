"""
SEMA: the current user's identity, plus admin impersonation ("view as user").

There is no authentication yet (login is a later slice). Until then, a single
mock identity stands in for "who is making this request" -- hardcoded here,
server-side, as the e-commerce client's admin (Miri). The admin panel resolves
this identity against the real org_users table, so the screen operates on live
data even though the identity itself is mocked.

This module is the ONE place that decides "who is the current user" --
`current_identity()`. When real auth arrives it replaces `real_identity()`
(reading a verified session/JWT) without touching any endpoint -- the
require_client_admin dependency in api/main.py already routes every admin
request through here.

Impersonation (impersonation_prompt.md) is implemented as a layer INSIDE this
same resolution rather than scattered per-route overrides, per the same
design constraint: `current_identity()` returns the impersonation TARGET's
identity whenever the real admin has an active "view as" session, and the
REAL identity otherwise -- everything downstream (require_client_admin,
current_org_user's data-scope lookup, the daily query counter, ...) already
resolves the caller by calling `current_identity()`, so the swap needs no
other code change anywhere else. `real_identity()` is the escape hatch used
ONLY by the impersonation start/stop/state endpoints themselves, so
starting/stopping/checking impersonation always acts on the actual signed-in
admin, never the (possibly impersonated) effective identity -- this is what
guarantees Stop always works for the real admin even while impersonating a
non-admin (api/main.py's require_real_client_admin).
"""

from __future__ import annotations

from sema_core.impersonation_store import AlreadyImpersonatingError, ImpersonationStore
from sema_core.settings import settings

# The mocked signed-in user. Miri is seeded as a client_admin of the e-commerce
# client (see OrgUserStore.seed_demo_users), so resolving this identity against
# the store yields a real, admin-role row.
MOCK_IDENTITY = {
    "client_id": "ecommerce",
    "email": "miri1988@gmail.com",
}

# 30 minutes (impersonation_prompt.md). Read via the module global at CALL
# time (never bound as a function default) so a test can monkeypatch this
# constant to a tiny value and immediately affect the next start_impersonation
# call -- a default argument would freeze the value at function-definition
# time instead.
IMPERSONATION_TTL_MINUTES: float = 30

# Module-level singleton, same convention every other sema_core store uses
# (see e.g. query_limit_store) -- tests monkeypatch this attribute directly
# (see tests/conftest.py's _isolated_impersonation_store) to point it at an
# isolated temp-file store, same isolation every other admin-panel store gets.
_impersonation_store = ImpersonationStore(settings.conversation_db_path)


def real_identity() -> dict:
    """The actual signed-in identity as {client_id, email} -- UNAFFECTED by
    any active impersonation. Used only by the impersonation start/stop/state
    endpoints (api/main.py's require_real_client_admin) so they always act on
    the real admin. Mocked for now (returns MOCK_IDENTITY); the swap point for
    real auth -- a future version reads the authenticated session instead."""
    return dict(MOCK_IDENTITY)


def current_identity() -> dict:
    """Return the EFFECTIVE current request's identity as {client_id, email}.

    This is the single swap point every other part of the backend resolves
    "who is making this request" through (require_client_admin,
    current_org_user, ...). While the real admin has an active "view as"
    session, this returns the TARGET user's identity instead of the real
    one -- so role, data scope, and every downstream lookup automatically
    become the target's, with no other code change. Otherwise, identical to
    `real_identity()`.
    """
    raw = real_identity()
    active = _impersonation_store.get_active(raw["client_id"], raw["email"])
    if active is not None:
        return {"client_id": raw["client_id"], "email": active["target_email"]}
    return raw


def start_impersonation(
    admin_client_id: str,
    admin_email: str,
    *,
    admin_user_id: str,
    admin_name: str | None,
    admin_role: str | None,
    target_user_id: str,
    target_email: str,
    target_name: str | None,
    target_role: str | None,
) -> dict:
    """Start a "view as" session for the real admin. Raises
    AlreadyImpersonatingError if one is already active (callers should
    `reap_expired_impersonation` first). Returns the session dict (see
    ImpersonationStore._row_to_dict)."""
    return _impersonation_store.start(
        admin_client_id,
        admin_email,
        admin_user_id=admin_user_id,
        admin_name=admin_name,
        admin_role=admin_role,
        target_user_id=target_user_id,
        target_email=target_email,
        target_name=target_name,
        target_role=target_role,
        ttl_minutes=IMPERSONATION_TTL_MINUTES,
    )


def stop_impersonation(admin_client_id: str, admin_email: str) -> dict | None:
    """Explicitly stop. Always safe to call (constraint: Stop must always
    work for the real admin). Returns the stopped session dict only if one
    was genuinely active, else None (nothing to stop)."""
    return _impersonation_store.stop(admin_client_id, admin_email)


def get_impersonation_state(admin_client_id: str, admin_email: str) -> dict | None:
    """The admin's current active session, or None. Never mutates anything --
    see ImpersonationStore.get_active."""
    return _impersonation_store.get_active(admin_client_id, admin_email)


def reap_expired_impersonation(admin_client_id: str, admin_email: str) -> dict | None:
    """Lazy expiry cleanup: if the admin's session has passed its expiry,
    delete it and return it (so the caller can log the one-time
    "impersonation.stopped (reason=expired)" audit event); else None."""
    return _impersonation_store.reap_if_expired(admin_client_id, admin_email)


__all__ = [
    "AlreadyImpersonatingError",
    "IMPERSONATION_TTL_MINUTES",
    "MOCK_IDENTITY",
    "current_identity",
    "get_impersonation_state",
    "reap_expired_impersonation",
    "real_identity",
    "start_impersonation",
    "stop_impersonation",
]
