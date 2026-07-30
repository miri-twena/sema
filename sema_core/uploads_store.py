"""
SEMA: CSV/Excel-upload source tracking (data_sources_add_prompt.md Path C).
Metadata only -- lives in the SAME small SQLite metadata store as the other
admin-panel stores (var/sema_state.db). The actual uploaded DATA lands in
the client's own analytics Postgres, in a dedicated `uploads` schema (see
sema_core.file_upload) -- this store just remembers which table backs which
upload, for the source card + "replace file" action.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UploadNotFoundError(Exception):
    pass


class UploadsStore:
    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS uploads ("
                "id TEXT PRIMARY KEY, client_id TEXT NOT NULL, table_name TEXT NOT NULL, "
                "original_filename TEXT NOT NULL, column_count INTEGER NOT NULL, "
                "row_count INTEGER NOT NULL, uploaded_by TEXT, created_at TEXT NOT NULL, "
                "updated_at TEXT NOT NULL)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_uploads_client ON uploads(client_id)")

    _COLS = (
        "id, client_id, table_name, original_filename, column_count, row_count, "
        "uploaded_by, created_at, updated_at"
    )

    @staticmethod
    def _row_to_dict(r: tuple) -> dict:
        return {
            "id": r[0],
            "client_id": r[1],
            "table_name": r[2],
            "original_filename": r[3],
            "column_count": r[4],
            "row_count": r[5],
            "uploaded_by": r[6],
            "created_at": r[7],
            "updated_at": r[8],
        }

    def create(
        self, client_id: str, *, table_name: str, original_filename: str,
        column_count: int, row_count: int, uploaded_by: str | None,
    ) -> dict:
        upload_id = uuid.uuid4().hex
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                f"INSERT INTO uploads ({self._COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (upload_id, client_id, table_name, original_filename, column_count, row_count,
                 uploaded_by, now, now),
            )
        return self.get(client_id, upload_id)

    def list_for_client(self, client_id: str) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {self._COLS} FROM uploads WHERE client_id = ? ORDER BY created_at", (client_id,)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get(self, client_id: str, upload_id: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._COLS} FROM uploads WHERE client_id = ? AND id = ?", (client_id, upload_id)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def replace(self, client_id: str, upload_id: str, *, original_filename: str, column_count: int, row_count: int) -> dict:
        """The table itself is dropped/recreated by sema_core.file_upload;
        this just refreshes the tracked metadata to match."""
        now = _now()
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "UPDATE uploads SET original_filename = ?, column_count = ?, row_count = ?, "
                "updated_at = ? WHERE client_id = ? AND id = ?",
                (original_filename, column_count, row_count, now, client_id, upload_id),
            )
            if cur.rowcount == 0:
                raise UploadNotFoundError(upload_id)
        return self.get(client_id, upload_id)
