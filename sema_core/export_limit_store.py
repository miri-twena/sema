"""
SEMA: per-user hourly CSV-export rate limit (full_data_export_prompt.md
item 5, "rate-limit exports per user per hour ... against abuse").

Same SQLite metadata store as query_limit_store.py, same atomic-upsert
`increment_and_get` pattern -- deliberately a SEPARATE table/counter, not a
reuse of query_usage, because an export never calls the (billed) Anthropic
API at all: it re-runs a query that was already paid for once, against the
already-generous daily_query_limit. This counts a different kind of cost
(DB load from a re-run, potentially large, query) on its own clock (rolling
hour, not calendar day), so the two caps can't interfere with each other.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from sema_core import sqlite_utils


def current_hour() -> str:
    """The current UTC hour bucket ("2026-08-04T14"), as the limit's reset
    boundary -- a rolling-hour approximation via fixed clock-hour buckets
    (simpler than a true sliding window, and fine for an abuse guardrail
    rather than a precise rate limiter)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")


class ExportLimitStore:
    """SQLite-backed store for the hourly per-user export counter."""

    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite_utils.connect(self._path)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS export_usage ("
                "client_id TEXT NOT NULL, org_user_id TEXT NOT NULL, hour TEXT NOT NULL, "
                "count INTEGER NOT NULL DEFAULT 0, notified INTEGER NOT NULL DEFAULT 0, "
                "updated_at TEXT NOT NULL, "
                "PRIMARY KEY (client_id, org_user_id, hour))"
            )

    def increment_and_get(self, client_id: str, org_user_id: str, hour: str) -> int:
        """Bump this hour's count for this user and return the NEW total (1
        on the first export attempt of the hour)."""
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO export_usage (client_id, org_user_id, hour, count, notified, updated_at) "
                "VALUES (?, ?, ?, 1, 0, ?) "
                "ON CONFLICT(client_id, org_user_id, hour) DO UPDATE SET "
                "count = count + 1, updated_at = excluded.updated_at",
                (client_id, org_user_id, hour, now),
            )
            (count,) = conn.execute(
                "SELECT count FROM export_usage WHERE client_id = ? AND org_user_id = ? AND hour = ?",
                (client_id, org_user_id, hour),
            ).fetchone()
        return count

    def get_count(self, client_id: str, org_user_id: str, hour: str) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT count FROM export_usage WHERE client_id = ? AND org_user_id = ? AND hour = ?",
                (client_id, org_user_id, hour),
            ).fetchone()
        return row[0] if row else 0

    def mark_notified_once(self, client_id: str, org_user_id: str, hour: str) -> bool:
        """Same one-shot pattern as QueryLimitStore.mark_notified_once: True
        only the first time this fires for a given (user, hour), so the
        export.rate_limited audit event logs once per breach, not once per
        over-the-cap request."""
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "UPDATE export_usage SET notified = 1 "
                "WHERE client_id = ? AND org_user_id = ? AND hour = ? AND notified = 0",
                (client_id, org_user_id, hour),
            )
            return cur.rowcount > 0
