"""
SEMA: server-side organization-users store.

Backs the client admin panel's "Users and permissions" screen (spec §6.1).
Lives in the SAME small SQLite metadata store as the conversation store
(var/sema_state.db) -- app-owned state, entirely separate from the tenant
analytics databases in db.py, which are read-only for the agent and dropped/
recreated on every data load. This is the first notion of a "user" in SEMA:
there is no real auth yet, so a mock identity (see sema_core.current_user)
names the current user, but the rows themselves are real DB data.

Mirrors SqliteConversationStore's conventions on purpose (one connection per
call, parameterized SQL, uuid4 ids, ISO-UTC timestamps, guarded ALTER
migrations, and a client_id ownership check on every method so one tenant can
never see or touch another's users).

The role/status "enums" are plain TEXT here; the allowed values are enforced
at the API boundary via Pydantic Literal[...] (api/models.py), exactly as the
conversation store does for role/widget_kind.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sema_core import sqlite_utils
from sema_core.data_scope import DEFAULT_INVITE_SCOPE, SCOPE_PRESETS

# How long an invite link stays valid. Surfaced in the UI hint ("valid for 7
# days") and used to compute invite_expires_at on invite / resend.
INVITE_TTL_DAYS = 7

ROLES = ("client_admin", "analyst", "viewer")
STATUSES = ("active", "suspended", "invited")
# client_admin is always this scope -- see the admin-always-full guard below.
ADMIN_DATA_SCOPE = "full"


class OrgUserNotFoundError(Exception):
    """Raised for a missing user OR one owned by a different client_id.
    Callers must not be able to tell the two apart -- that would leak that a
    user id exists under another tenant (same rule as ConversationNotFoundError).
    """


class DuplicateEmailError(Exception):
    """Raised when inviting an email that already exists for the client (in any
    status). Email is unique per client."""


class LastAdminError(Exception):
    """Raised when an operation would leave the client with no active
    client_admin (delete / downgrade / suspend the last one). An organization
    must always keep at least one admin who can manage it."""


class InvalidDataScopeError(Exception):
    """Raised when setting a data_scope that isn't selectable -- either
    unrecognized or `custom` (V2: the schema allows it, the UI disables it,
    and this is the server-side half of that rejection)."""


class AdminScopeError(Exception):
    """Raised when trying to give a client_admin any data_scope other than
    'full'. An organization admin always has full data access -- enforced
    here so it can never drift out of sync via a PATCH or a role promotion."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_selectable_scope(data_scope: str) -> None:
    """Raise InvalidDataScopeError unless `data_scope` is a real, selectable
    preset -- rejects both typos/unknown ids and `custom` (V2: the schema
    allows the value, but nothing may actually select it yet)."""
    p = SCOPE_PRESETS.get(data_scope)
    if p is None or not p.selectable:
        raise InvalidDataScopeError(data_scope)


def _is_expired(invite_expires_at: str | None) -> bool:
    """An invite is expired once its expiry timestamp is in the past. Only
    meaningful for invited users; active/suspended users have no expiry."""
    if not invite_expires_at:
        return False
    try:
        return datetime.fromisoformat(invite_expires_at) < datetime.now(timezone.utc)
    except ValueError:
        return False


class OrgUserStore:
    """SQLite-backed store for organization users.

    A fresh connection is opened per call -- sqlite3 connections aren't safe to
    share across threads and FastAPI runs sync endpoints in a threadpool. The
    writes here are small and infrequent, so per-call open/close is negligible.
    """

    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite_utils.connect(self._path)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            # Brand-new table: CREATE TABLE IF NOT EXISTS alone covers a fresh
            # store and (once shipped) an older one equally. Future column
            # additions go through _migrate's guarded-ALTER pattern.
            conn.execute(
                "CREATE TABLE IF NOT EXISTS org_users ("
                "id TEXT PRIMARY KEY, client_id TEXT NOT NULL, "
                "name TEXT, email TEXT NOT NULL, title TEXT, "
                "role TEXT NOT NULL, status TEXT NOT NULL, "
                "invited_at TEXT, invite_expires_at TEXT, last_active_at TEXT, "
                "created_at TEXT NOT NULL)"
            )
            # Email is unique per client (a person is one account in an org);
            # the same email may exist under a different client. Enforced at the
            # data layer so two concurrent invites can't both pass an
            # application-level "does it exist yet" check and race.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_org_users_email "
                "ON org_users(client_id, email)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_org_users_client ON org_users(client_id)"
            )
            self._migrate(conn)

    @staticmethod
    def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Bring an existing database up to the current schema via guarded,
        idempotent ALTERs -- the same no-framework pattern the conversation
        store uses. Each ALTER is guarded by a column check, so this is
        idempotent and runs at most once per column."""
        cols = self._columns(conn, "org_users")
        if "invited_by" not in cols:
            # Holds another row's `id` -- who sent this user's invite. No SQL
            # FOREIGN KEY constraint, matching every other table in this
            # codebase (none enforce FKs); the relationship is logical only.
            conn.execute("ALTER TABLE org_users ADD COLUMN invited_by TEXT")
        if "joined_at" not in cols:
            # When an invite was accepted (there's no accept-invite flow yet,
            # so this is only ever set by seed data until real auth lands) or,
            # for a founding/seeded user, effectively their created_at.
            conn.execute("ALTER TABLE org_users ADD COLUMN joined_at TEXT")
        if "data_scope" not in cols:
            # Which semantic-layer domains/metrics this user's QUESTIONS may
            # touch (sema_core.data_scope) -- a second permission axis
            # alongside role. DEFAULT 'full' backfills every pre-existing row
            # (including every client_admin, which is correct: admins are
            # always full) as a no-op; new rows pick their real value
            # explicitly via invite()/set_data_scope().
            conn.execute(
                "ALTER TABLE org_users ADD COLUMN data_scope TEXT NOT NULL DEFAULT 'full'"
            )

    # --- row mapping -------------------------------------------------------

    # LEFT JOINed to itself to resolve invited_by -> the inviter's name in one
    # query, no N+1. `u.` aliases every column from the joined table's own
    # namespace since both sides of the join share the same column names.
    _SELECT_SQL = (
        "SELECT u.id, u.client_id, u.name, u.email, u.title, u.role, u.status, "
        "u.invited_at, u.invite_expires_at, u.joined_at, u.last_active_at, u.created_at, "
        "u.invited_by, inviter.name AS invited_by_name, u.data_scope "
        "FROM org_users u LEFT JOIN org_users inviter ON u.invited_by = inviter.id"
    )

    @staticmethod
    def _row_to_dict(r: tuple) -> dict:
        """Map a SELECT row to the dict the API wraps in AdminUser. Adds the
        DERIVED invite_expired flag (never stored -- computed from the expiry
        timestamp so it's always current, never stale). `invited_by_name` is
        also derived (via the join above), never stored -- so a renamed or
        removed inviter is always reflected, never stale."""
        return {
            "id": r[0],
            "client_id": r[1],
            "name": r[2],
            "email": r[3],
            "title": r[4],
            "role": r[5],
            "status": r[6],
            "invited_at": r[7],
            "invite_expires_at": r[8],
            "joined_at": r[9],
            "last_active_at": r[10],
            "created_at": r[11],
            "invited_by": r[12],
            "invited_by_name": r[13],
            "data_scope": r[14],
            "invite_expired": r[6] == "invited" and _is_expired(r[8]),
        }

    def _owner(self, conn: sqlite3.Connection, user_id: str) -> str | None:
        row = conn.execute(
            "SELECT client_id FROM org_users WHERE id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else None

    # --- reads -------------------------------------------------------------

    def _filter_clause(
        self, client_id: str, q: str | None, role: str | None
    ) -> tuple[str, list]:
        clause = "u.client_id = ?"
        params: list = [client_id]
        if q:
            clause += " AND (LOWER(u.name) LIKE ? OR LOWER(u.email) LIKE ?)"
            like = f"%{q.lower()}%"
            params += [like, like]
        if role:
            clause += " AND u.role = ?"
            params.append(role)
        return clause, params

    def list_users(
        self,
        client_id: str,
        q: str | None = None,
        role: str | None = None,
        *,
        page: int | None = None,
        page_size: int | None = None,
    ) -> list[dict]:
        """This client's users. Optional case-insensitive search over name+email
        and an optional exact role filter. Ordered admins-first, then by name,
        so the table reads sensibly by default. Pass BOTH page and page_size to
        get one page (1-indexed); omit both for every matching row (unpaged --
        several callers, e.g. the last-active-admin count, need the whole set)."""
        where, params = self._filter_clause(client_id, q, role)
        sql = (
            f"{self._SELECT_SQL} WHERE {where} "
            "ORDER BY CASE u.role WHEN 'client_admin' THEN 0 WHEN 'analyst' THEN 1 ELSE 2 END, "
            "LOWER(COALESCE(u.name, u.email))"
        )
        if page is not None and page_size is not None:
            sql += " LIMIT ? OFFSET ?"
            params = [*params, page_size, (max(1, page) - 1) * page_size]
        with closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count_users(
        self, client_id: str, q: str | None = None, role: str | None = None
    ) -> int:
        """Count of users matching the same filters as list_users -- the
        FILTERED total pagination needs, not the whole org's count."""
        where, params = self._filter_clause(client_id, q, role)
        with closing(self._connect()) as conn:
            (n,) = conn.execute(
                f"SELECT COUNT(*) FROM org_users u WHERE {where}", params
            ).fetchone()
        return n

    def get_user(self, client_id: str, user_id: str) -> dict:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"{self._SELECT_SQL} WHERE u.id = ? AND u.client_id = ?",
                (user_id, client_id),
            ).fetchone()
        if row is None:
            raise OrgUserNotFoundError(user_id)
        return self._row_to_dict(row)

    def get_by_email(self, client_id: str, email: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"{self._SELECT_SQL} WHERE u.client_id = ? AND LOWER(u.email) = LOWER(?)",
                (client_id, email),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def count_active_admins(self, client_id: str) -> int:
        with closing(self._connect()) as conn:
            (n,) = conn.execute(
                "SELECT COUNT(*) FROM org_users "
                "WHERE client_id = ? AND role = 'client_admin' AND status = 'active'",
                (client_id,),
            ).fetchone()
        return n

    # --- writes ------------------------------------------------------------

    def invite(self, client_id: str, email: str, role: str, invited_by: str | None = None,
               name: str | None = None, title: str | None = None,
               data_scope: str | None = None) -> dict:
        """Create an invited user. Raises DuplicateEmailError if the email
        already exists for this client (any status). `invited_by` is the
        inviting user's id (the current mock identity, stamped by the API
        layer) -- `joined_at` stays NULL until the invite is accepted, which
        has no code path yet (no real auth/login in this slice).

        `data_scope` defaults to DEFAULT_INVITE_SCOPE ('no_financials') when
        omitted -- new non-admin users start on the safer side, not `full`.
        A client_admin invite is always ADMIN_DATA_SCOPE ('full') regardless
        of what's passed, same admin-always-full rule set_role/set_data_scope
        enforce. Raises InvalidDataScopeError for an unrecognized or
        unselectable (`custom`) scope."""
        resolved_scope = ADMIN_DATA_SCOPE if role == "client_admin" else (data_scope or DEFAULT_INVITE_SCOPE)
        if role != "client_admin":
            _require_selectable_scope(resolved_scope)
        now = _now()
        expires = (datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)).isoformat()
        user_id = uuid.uuid4().hex
        with closing(self._connect()) as conn, conn:
            existing = conn.execute(
                "SELECT 1 FROM org_users WHERE client_id = ? AND LOWER(email) = LOWER(?)",
                (client_id, email),
            ).fetchone()
            if existing:
                raise DuplicateEmailError(email)
            conn.execute(
                "INSERT INTO org_users (id, client_id, name, email, title, role, status, "
                "invited_at, invite_expires_at, joined_at, invited_by, last_active_at, created_at, "
                "data_scope) "
                "VALUES (?, ?, ?, ?, ?, ?, 'invited', ?, ?, NULL, ?, NULL, ?, ?)",
                (user_id, client_id, name, email, title, role, now, expires, invited_by, now, resolved_scope),
            )
        return self.get_user(client_id, user_id)

    def set_role(self, client_id: str, user_id: str, role: str) -> dict:
        """Change a user's role. Refuses to downgrade the last active admin.
        Promoting to client_admin resets data_scope to 'full' (admins are
        always full access) -- a silent reset, not an error, since the caller
        is deliberately making this user an admin."""
        with closing(self._connect()) as conn, conn:
            current = self._require_row(conn, client_id, user_id)
            if (
                current["role"] == "client_admin"
                and current["status"] == "active"
                and role != "client_admin"
                and self._active_admins(conn, client_id) <= 1
            ):
                raise LastAdminError(user_id)
            if role == "client_admin":
                conn.execute(
                    "UPDATE org_users SET role = ?, data_scope = ? WHERE id = ? AND client_id = ?",
                    (role, ADMIN_DATA_SCOPE, user_id, client_id),
                )
            else:
                conn.execute(
                    "UPDATE org_users SET role = ? WHERE id = ? AND client_id = ?",
                    (role, user_id, client_id),
                )
        return self.get_user(client_id, user_id)

    def set_data_scope(self, client_id: str, user_id: str, data_scope: str) -> dict:
        """Change a user's data-access scope (sema_core.data_scope). Raises
        InvalidDataScopeError for an unrecognized or unselectable (`custom`,
        reserved for V2) scope, and AdminScopeError for any non-'full' value
        on a client_admin -- admins are always full access."""
        _require_selectable_scope(data_scope)
        with closing(self._connect()) as conn, conn:
            current = self._require_row(conn, client_id, user_id)
            if current["role"] == "client_admin" and data_scope != ADMIN_DATA_SCOPE:
                raise AdminScopeError(user_id)
            conn.execute(
                "UPDATE org_users SET data_scope = ? WHERE id = ? AND client_id = ?",
                (data_scope, user_id, client_id),
            )
        return self.get_user(client_id, user_id)

    def set_status(self, client_id: str, user_id: str, status: str) -> dict:
        """Change a user's status. Refuses to suspend the last active admin."""
        with closing(self._connect()) as conn, conn:
            current = self._require_row(conn, client_id, user_id)
            if (
                current["role"] == "client_admin"
                and current["status"] == "active"
                and status != "active"
                and self._active_admins(conn, client_id) <= 1
            ):
                raise LastAdminError(user_id)
            conn.execute(
                "UPDATE org_users SET status = ? WHERE id = ? AND client_id = ?",
                (status, user_id, client_id),
            )
        return self.get_user(client_id, user_id)

    def delete(self, client_id: str, user_id: str) -> None:
        """Remove a user. Refuses to delete the last active admin."""
        with closing(self._connect()) as conn, conn:
            current = self._require_row(conn, client_id, user_id)
            if (
                current["role"] == "client_admin"
                and current["status"] == "active"
                and self._active_admins(conn, client_id) <= 1
            ):
                raise LastAdminError(user_id)
            conn.execute(
                "DELETE FROM org_users WHERE id = ? AND client_id = ?", (user_id, client_id)
            )

    def resend_invite(self, client_id: str, user_id: str) -> dict:
        """Reset an invited user's expiry to now + TTL (the only effect -- no
        email is actually sent; the API logs it). No-ops the expiry reset for a
        non-invited user by leaving status untouched, but still bumps expiry so
        a re-invite flow stays simple; callers only offer this on invited rows."""
        now = _now()
        expires = (datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)).isoformat()
        with closing(self._connect()) as conn, conn:
            self._require_row(conn, client_id, user_id)
            conn.execute(
                "UPDATE org_users SET invited_at = ?, invite_expires_at = ? "
                "WHERE id = ? AND client_id = ?",
                (now, expires, user_id, client_id),
            )
        return self.get_user(client_id, user_id)

    # --- guard helpers (operate on the open write connection) --------------

    def _require_row(self, conn: sqlite3.Connection, client_id: str, user_id: str) -> dict:
        row = conn.execute(
            f"{self._SELECT_SQL} WHERE u.id = ? AND u.client_id = ?",
            (user_id, client_id),
        ).fetchone()
        if row is None:
            raise OrgUserNotFoundError(user_id)
        return self._row_to_dict(row)

    @staticmethod
    def _active_admins(conn: sqlite3.Connection, client_id: str) -> int:
        (n,) = conn.execute(
            "SELECT COUNT(*) FROM org_users "
            "WHERE client_id = ? AND role = 'client_admin' AND status = 'active'",
            (client_id,),
        ).fetchone()
        return n

    # --- seeding -----------------------------------------------------------

    def seed_demo_users(self, client_id: str) -> int:
        """Insert the demo org roster for the e-commerce client. Idempotent: a
        no-op if the client already has any users, so re-running the data seed
        never duplicates or overwrites. Returns the number of users inserted
        (0 when it was already seeded). last_active_at values are varied from
        recent to weeks ago so the "last active" column reads realistically.

        Miri, Dan, and Demo User are FOUNDING members: invited_by=None,
        joined_at set months back. Everyone else was invited by Miri
        (invited_by=Miri's id, freshly generated below so the rest of the
        roster can reference it), with joined_at varied across the org's
        life. The pending `dana` invite has invited_by=Miri's id and
        joined_at=None (hasn't joined yet).

        data_scope (sema_core.data_scope) is seeded per-person: the two
        viewer executives (Dan/CEO, Avi/CFO) and Miri (admin) get 'full';
        Yossi -- retitled Sales Analyst -- gets 'sales_only'; everyone else
        (including the pending dana invite) gets the safer 'no_financials'
        default, same as a real invite with no scope specified."""
        with closing(self._connect()) as conn:
            (existing,) = conn.execute(
                "SELECT COUNT(*) FROM org_users WHERE client_id = ?", (client_id,)
            ).fetchone()
        if existing:
            return 0

        now = datetime.now(timezone.utc)

        def ago(**kw) -> str:
            return (now - timedelta(**kw)).isoformat()

        miri_id = uuid.uuid4().hex

        # (id, name, email, title, role, status, last_active_at, invited_by, joined_at, data_scope)
        roster = [
            (miri_id, "Miri Levi", "miri1988@gmail.com", "Head of Data", "client_admin",
             "active", ago(minutes=5), None, ago(days=400), "full"),
            (uuid.uuid4().hex, "Dan Avrahami", "dan.avrahami@ecommerce-demo.com", "CEO",
             "viewer", "active", ago(hours=2), None, ago(days=400), "full"),
            (uuid.uuid4().hex, "Demo User", "demo.user@ecommerce-demo.com", "Analyst",
             "analyst", "active", ago(days=1), None, ago(days=395), "no_financials"),
            (uuid.uuid4().hex, "Ronit Shapira", "ronit.shapira@ecommerce-demo.com",
             "VP Operations", "viewer", "active", ago(hours=6), miri_id, ago(days=300), "no_financials"),
            (uuid.uuid4().hex, "Noa Berman", "noa.berman@ecommerce-demo.com",
             "Senior Analyst", "analyst", "active", ago(days=2), miri_id, ago(days=250), "no_financials"),
            (uuid.uuid4().hex, "Yossi Cohen", "yossi.cohen@ecommerce-demo.com",
             "Sales Analyst", "analyst", "active", ago(days=4), miri_id, ago(days=180), "sales_only"),
            (uuid.uuid4().hex, "Tamar Golan", "tamar.golan@ecommerce-demo.com",
             "Ecommerce Manager", "analyst", "active", ago(days=9), miri_id, ago(days=120), "no_financials"),
            (uuid.uuid4().hex, "Avi Peretz", "avi.peretz@ecommerce-demo.com", "CFO",
             "viewer", "active", ago(days=16), miri_id, ago(days=90), "full"),
            (uuid.uuid4().hex, "Lior Katz", "lior.katz@ecommerce-demo.com", "Data Analyst",
             "analyst", "suspended", ago(days=23), miri_id, ago(days=60), "no_financials"),
        ]

        created = now.isoformat()
        with closing(self._connect()) as conn, conn:
            for uid, name, email, title, role, status, last_active, invited_by, joined_at, data_scope in roster:
                conn.execute(
                    "INSERT INTO org_users (id, client_id, name, email, title, role, status, "
                    "invited_at, invite_expires_at, joined_at, invited_by, last_active_at, created_at, "
                    "data_scope) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?)",
                    (uid, client_id, name, email, title, role, status,
                     joined_at, invited_by, last_active, created, data_scope),
                )
            # One pending invite, expiring in the future -- invited by Miri,
            # not yet joined.
            expires = (now + timedelta(days=INVITE_TTL_DAYS)).isoformat()
            conn.execute(
                "INSERT INTO org_users (id, client_id, name, email, title, role, status, "
                "invited_at, invite_expires_at, joined_at, invited_by, last_active_at, created_at, "
                "data_scope) "
                "VALUES (?, ?, NULL, ?, ?, 'analyst', 'invited', ?, ?, NULL, ?, NULL, ?, 'no_financials')",
                (uuid.uuid4().hex, client_id, "dana@ecommerce-demo.com",
                 "Operations Analyst", created, expires, miri_id, created),
            )
        return len(roster) + 1
