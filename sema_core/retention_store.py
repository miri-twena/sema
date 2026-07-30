"""
SEMA: retention-sweep run tracking (org_settings_gapfix_prompt.md Part 1).

Backs the "last cleanup" status line in the org-settings screen and the
20-hour idempotency guard on the daily background sweep. One row per client
in the SAME small SQLite metadata store as the other admin-panel stores
(var/sema_state.db) -- mirrors org_settings_store.py's conventions on
purpose: one connection per call, parameterized SQL, ISO-UTC timestamps.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

# A restart loop (or an overlapping manual + scheduled run) must never
# re-sweep a client whose last run is still fresh -- 20h leaves headroom
# under the 24h schedule for a slightly-early wakeup without re-running.
SKIP_WINDOW_HOURS = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RetentionRunStore:
    """SQLite-backed store for one retention-sweep run record per client."""

    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS retention_runs ("
                "client_id TEXT PRIMARY KEY, last_run_at TEXT NOT NULL, "
                "deleted_count INTEGER NOT NULL, status TEXT NOT NULL, error TEXT)"
            )

    @staticmethod
    def _row_to_dict(r: tuple) -> dict:
        return {
            "client_id": r[0],
            "last_run_at": r[1],
            "deleted_count": r[2],
            "status": r[3],
            "error": r[4],
        }

    _SELECT_SQL = "SELECT client_id, last_run_at, deleted_count, status, error FROM retention_runs"

    def get(self, client_id: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(f"{self._SELECT_SQL} WHERE client_id = ?", (client_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def should_skip(self, client_id: str, now: datetime | None = None) -> bool:
        """True when this client's last run is still within the skip window
        -- a restart loop (or an overlapping manual + scheduled trigger)
        must never sweep the same client twice in quick succession."""
        existing = self.get(client_id)
        if existing is None:
            return False
        last_run = datetime.fromisoformat(existing["last_run_at"])
        base = now or datetime.now(timezone.utc)
        return base - last_run < timedelta(hours=SKIP_WINDOW_HOURS)

    def record(
        self, client_id: str, *, deleted_count: int, status: str, error: str | None = None
    ) -> dict:
        """Upsert this client's run record -- one row per client, always the
        MOST RECENT run (no history; V2 concern, same as the audit log's own
        retention-policy note)."""
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO retention_runs (client_id, last_run_at, deleted_count, status, error) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(client_id) DO UPDATE SET "
                "last_run_at = excluded.last_run_at, deleted_count = excluded.deleted_count, "
                "status = excluded.status, error = excluded.error",
                (client_id, now, deleted_count, status, error),
            )
        return self.get(client_id)
