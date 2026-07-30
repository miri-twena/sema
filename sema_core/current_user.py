"""
SEMA: the current user's identity.

There is no authentication yet (login is a later slice). Until then, a single
mock identity stands in for "who is making this request" -- hardcoded here,
server-side, as the e-commerce client's admin (Miri). The admin panel resolves
this identity against the real org_users table, so the screen operates on live
data even though the identity itself is mocked.

This module is the ONE place that decides "who is the current user". When real
auth arrives it replaces current_identity() (reading a verified session/JWT)
without touching any endpoint -- the require_client_admin dependency in
api/main.py already routes every admin request through here.
"""

from __future__ import annotations

# The mocked signed-in user. Miri is seeded as a client_admin of the e-commerce
# client (see OrgUserStore.seed_demo_users), so resolving this identity against
# the store yields a real, admin-role row.
MOCK_IDENTITY = {
    "client_id": "ecommerce",
    "email": "miri1988@gmail.com",
}


def current_identity() -> dict:
    """Return the current request's identity as {client_id, email}.

    Mocked for now (returns MOCK_IDENTITY). The swap point for real auth: a
    future version reads the authenticated session instead, and every admin
    endpoint keeps working unchanged.
    """
    return dict(MOCK_IDENTITY)
