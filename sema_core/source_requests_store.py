"""
SEMA: tracked "being set up" data-source requests (data_sources_add_prompt.md
Path B: Priority/Salesforce SaaS requests; Path C: Google Sheets before a
platform-level service account is configured). Both share the same shape --
a non-secret request that shows a status card with a progress rail until a
human on the platform side finishes configuring it. Lives in the SAME small
SQLite metadata store as the other admin-panel stores (var/sema_state.db).

Status transitions (requested -> configuring -> testing -> active, or
rejected) are PLATFORM-side only per spec -- this store exposes
`set_status` for that, but no route in api/main.py calls it from the client
admin panel; it's for an internal/dev tool once real platform auth exists.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

VALID_STATUSES = frozenset({"requested", "configuring", "testing", "active", "rejected"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourceRequestNotFoundError(Exception):
    pass


class SourceRequestsStore:
    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS source_requests ("
                "id TEXT PRIMARY KEY, client_id TEXT NOT NULL, connector_type TEXT NOT NULL, "
                "details TEXT NOT NULL, status TEXT NOT NULL, created_by TEXT, "
                "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_source_requests_client ON source_requests(client_id)"
            )

    _COLS = "id, client_id, connector_type, details, status, created_by, created_at, updated_at"

    @staticmethod
    def _row_to_dict(r: tuple) -> dict:
        return {
            "id": r[0],
            "client_id": r[1],
            "connector_type": r[2],
            "details": json.loads(r[3]),
            "status": r[4],
            "created_by": r[5],
            "created_at": r[6],
            "updated_at": r[7],
        }

    def create(self, client_id: str, *, connector_type: str, details: dict, created_by: str | None) -> dict:
        req_id = uuid.uuid4().hex
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                f"INSERT INTO source_requests ({self._COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (req_id, client_id, connector_type, json.dumps(details), "requested", created_by, now, now),
            )
        return self.get(client_id, req_id)

    def list_for_client(self, client_id: str) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {self._COLS} FROM source_requests WHERE client_id = ? ORDER BY created_at", (client_id,)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get(self, client_id: str, request_id: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._COLS} FROM source_requests WHERE client_id = ? AND id = ?", (client_id, request_id)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def set_status(self, client_id: str, request_id: str, status: str) -> dict:
        """Platform-side only (see module docstring) -- not reachable from
        any client-admin-gated route today."""
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid status: {status!r}")
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "UPDATE source_requests SET status = ?, updated_at = ? WHERE client_id = ? AND id = ?",
                (status, _now(), client_id, request_id),
            )
            if cur.rowcount == 0:
                raise SourceRequestNotFoundError(request_id)
        return self.get(client_id, request_id)
