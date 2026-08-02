"""
SEMA: per-user daily LLM query soft cap (backend_qa_prompt.md item 5).

One row per (client_id, org_user_id, day) in the SAME small SQLite metadata
store as the other app-owned stores (var/sema_state.db) -- mirrors
retention_store.py's conventions on purpose: one connection per call,
parameterized SQL, ISO-UTC timestamps, an atomic upsert.

`increment_and_get` is the ONE write path: it atomically bumps the day's
count and returns the new value in a single statement (SQLite serializes
writers regardless of WAL mode, so there is no separate read-then-write race
to worry about here). The caller decides what "over the cap" means (compare
the returned count to the configured limit) -- this store only counts.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from sema_core import sqlite_utils


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def today() -> str:
    """The current UTC calendar day, as the cap's reset boundary -- matches
    the ISO-UTC convention every other timestamp in these stores already
    uses, so a cap resets at UTC midnight regardless of the org's own
    timezone setting (a v2 refinement, not needed for a soft cost guardrail)."""
    return datetime.now(timezone.utc).date().isoformat()


class QueryLimitStore:
    """SQLite-backed store for the daily per-user query counter."""

    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite_utils.connect(self._path)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS query_usage ("
                "client_id TEXT NOT NULL, org_user_id TEXT NOT NULL, day TEXT NOT NULL, "
                "count INTEGER NOT NULL DEFAULT 0, notified INTEGER NOT NULL DEFAULT 0, "
                "updated_at TEXT NOT NULL, "
                "PRIMARY KEY (client_id, org_user_id, day))"
            )

    def increment_and_get(self, client_id: str, org_user_id: str, day: str) -> int:
        """Bump today's count for this user and return the NEW total (1 on
        the first call of the day)."""
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO query_usage (client_id, org_user_id, day, count, notified, updated_at) "
                "VALUES (?, ?, ?, 1, 0, ?) "
                "ON CONFLICT(client_id, org_user_id, day) DO UPDATE SET "
                "count = count + 1, updated_at = excluded.updated_at",
                (client_id, org_user_id, day, _now()),
            )
            (count,) = conn.execute(
                "SELECT count FROM query_usage WHERE client_id = ? AND org_user_id = ? AND day = ?",
                (client_id, org_user_id, day),
            ).fetchone()
        return count

    def get_count(self, client_id: str, org_user_id: str, day: str) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT count FROM query_usage WHERE client_id = ? AND org_user_id = ? AND day = ?",
                (client_id, org_user_id, day),
            ).fetchone()
        return row[0] if row else 0

    def mark_notified_once(self, client_id: str, org_user_id: str, day: str) -> bool:
        """Flips today's row to notified=1 and returns True -- but ONLY the
        first time this is called for a given (user, day); every later call
        that same day returns False. This is what makes the
        usage.limit_reached audit event fire exactly once per user per day
        rather than once per over-the-cap request."""
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "UPDATE query_usage SET notified = 1 "
                "WHERE client_id = ? AND org_user_id = ? AND day = ? AND notified = 0",
                (client_id, org_user_id, day),
            )
            return cur.rowcount > 0
