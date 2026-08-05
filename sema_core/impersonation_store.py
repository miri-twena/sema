"""
SEMA: admin "view as user" impersonation -- server-side session state.

Backs the client admin panel's "View as user" action (impersonation_prompt.md):
a client_admin can temporarily act AS another active user in their own org to
see exactly what that user sees. Lives in the SAME small SQLite metadata store
as the other admin-panel stores (var/sema_state.db).

There is no login yet (sema_core.current_user's identity is mocked), so this
state can't live in a session cookie -- it's held server-side, keyed by the
REAL (admin) identity's (client_id, email). One row per admin: starting a new
impersonation while one is already active is rejected (AlreadyImpersonatingError),
matching the "one active impersonation per admin" rule. When real auth lands,
the state keying moves from "mock identity" to "session identity" with no
other change -- this store only ever deals in (client_id, email) pairs, never
imports sema_core.current_user itself (current_user is the one that imports
THIS module, not the other way around -- keeps the dependency direction the
same as every other store the identity layer might one day read).

Mirrors query_limit_store.py's conventions on purpose: one connection per
call, parameterized SQL, ISO-UTC timestamps, no framework.

Expiry is LAZY (spec: "expired = not active, lazily cleaned"): `get_active`
never mutates the table, so it's cheap to call on every request (current_
identity() calls it on effectively every request once impersonation is
wired in) -- it just treats a past-expiry row as if it were absent. The row
itself is only physically removed by `stop` (explicit Stop) or
`reap_if_expired` (lazy cleanup -- called by the impersonation endpoints so
an expired session gets its `impersonation.stopped` audit event exactly once,
the next time anything asks about impersonation state).
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sema_core import sqlite_utils


class AlreadyImpersonatingError(Exception):
    """Raised by `start` when the admin already has an active (non-expired)
    impersonation session -- one active impersonation per admin."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_expired(expires_at: str) -> bool:
    try:
        return datetime.fromisoformat(expires_at) < datetime.now(timezone.utc)
    except ValueError:
        # Malformed timestamp should never happen (we always write our own
        # isoformat() output) -- fail toward "expired" rather than wedging an
        # unreadable row into "active" forever.
        return True


class ImpersonationStore:
    """SQLite-backed store for active "view as user" sessions.

    A fresh connection is opened per call, same rationale as every other
    store in this codebase (sqlite3 connections aren't safe to share across
    threads; FastAPI runs sync endpoints in a threadpool).
    """

    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite_utils.connect(self._path)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS impersonation_sessions ("
                "admin_client_id TEXT NOT NULL, admin_email TEXT NOT NULL, "
                "admin_user_id TEXT NOT NULL, admin_name TEXT, admin_role TEXT, "
                "target_user_id TEXT NOT NULL, target_email TEXT NOT NULL, "
                "target_name TEXT, target_role TEXT, "
                "started_at TEXT NOT NULL, expires_at TEXT NOT NULL, "
                "PRIMARY KEY (admin_client_id, admin_email))"
            )

    # --- row mapping ---------------------------------------------------

    _COLS = (
        "admin_client_id, admin_email, admin_user_id, admin_name, admin_role, "
        "target_user_id, target_email, target_name, target_role, "
        "started_at, expires_at"
    )

    @staticmethod
    def _row_to_dict(r: tuple) -> dict:
        return {
            "admin_client_id": r[0],
            "admin_email": r[1],
            "admin_user_id": r[2],
            "admin_name": r[3],
            "admin_role": r[4],
            "target_user_id": r[5],
            "target_email": r[6],
            "target_name": r[7],
            "target_role": r[8],
            "started_at": r[9],
            "expires_at": r[10],
        }

    def _peek(self, admin_client_id: str, admin_email: str) -> dict | None:
        """The raw row regardless of expiry, or None if this admin has never
        started a session (or it was already stopped/reaped)."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._COLS} FROM impersonation_sessions "
                "WHERE admin_client_id = ? AND admin_email = ?",
                (admin_client_id, admin_email),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    # --- reads -----------------------------------------------------------

    def get_active(self, admin_client_id: str, admin_email: str) -> dict | None:
        """The admin's active session, or None if there isn't one -- INCLUDING
        one that's simply expired (never mutates the row; see module
        docstring). This is what current_identity() consults on every
        request, so it must stay a cheap, side-effect-free read."""
        row = self._peek(admin_client_id, admin_email)
        if row is None or _is_expired(row["expires_at"]):
            return None
        return row

    # --- writes ------------------------------------------------------------

    def start(
        self,
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
        ttl_minutes: float,
    ) -> dict:
        """Start (or restart, once any prior session has ended/expired) an
        impersonation session for this admin. Raises AlreadyImpersonatingError
        if one is already active -- callers should `reap_if_expired` first so
        a genuinely stale row never falsely blocks a fresh start."""
        if self.get_active(admin_client_id, admin_email) is not None:
            raise AlreadyImpersonatingError(admin_email)
        now = datetime.now(timezone.utc)
        started_at = now.isoformat()
        expires_at = (now + timedelta(minutes=ttl_minutes)).isoformat()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT OR REPLACE INTO impersonation_sessions "
                f"({self._COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    admin_client_id, admin_email, admin_user_id, admin_name, admin_role,
                    target_user_id, target_email, target_name, target_role,
                    started_at, expires_at,
                ),
            )
        return self._peek(admin_client_id, admin_email)  # type: ignore[return-value]

    def stop(self, admin_client_id: str, admin_email: str) -> dict | None:
        """Explicitly stop. Always deletes any row for this admin (cleanup),
        but only returns the session dict when it was genuinely ACTIVE at the
        moment of the call -- so the route layer can tell "I just stopped a
        real session" (log impersonation.stopped) from "there was nothing to
        stop / it had already expired" (no spurious audit event, and this
        stays a safe no-op to call at any time -- constraint: stop must
        always work for the real admin)."""
        row = self.get_active(admin_client_id, admin_email)
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "DELETE FROM impersonation_sessions WHERE admin_client_id = ? AND admin_email = ?",
                (admin_client_id, admin_email),
            )
        return row

    def reap_if_expired(self, admin_client_id: str, admin_email: str) -> dict | None:
        """Lazy cleanup: if this admin has a row that's PAST expiry, delete it
        and return it (so the caller can log the "stopped (reason=expired)"
        audit event exactly once); otherwise a no-op returning None (nothing
        there, or it's still active -- untouched)."""
        row = self._peek(admin_client_id, admin_email)
        if row is None or not _is_expired(row["expires_at"]):
            return None
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "DELETE FROM impersonation_sessions WHERE admin_client_id = ? AND admin_email = ?",
                (admin_client_id, admin_email),
            )
        return row
