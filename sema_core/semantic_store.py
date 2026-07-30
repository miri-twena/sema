"""
SEMA: semantic-model drafts and version history.

Backs the client admin panel's "Semantic model" screen: a Draft -> Validate ->
Publish workflow over the YAML files sema_core/agent/semantic.py loads. Lives
in the SAME small SQLite metadata store as conversation_store.py and
org_user_store.py (var/sema_state.db) -- app-owned state, not tenant data.

Two tables:
  - semantic_drafts: one row per (client_id, section, item_key) an admin is
    currently editing. The YAML on disk is untouched until Publish; this is
    the ONLY place an in-progress edit lives.
  - semantic_versions: one row per publish (or restore, which is itself a new
    publish per the spec). `snapshot` is the FULL raw text of every semantic
    YAML file for that client at that point -- not just the changed one --
    so a restore is a byte-exact rewrite, never a partial reconstruction.

Mirrors org_user_store.py's conventions on purpose: one connection per call,
parameterized SQL, uuid4 hex ids, ISO-UTC timestamps, a client_id ownership
check on every method, and a guarded-ALTER `_migrate` seam for future columns.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class SemanticDraftNotFoundError(Exception):
    """Raised for a missing draft OR one owned by a different client_id --
    same indistinguishable-404 rule as OrgUserNotFoundError."""


class SemanticVersionNotFoundError(Exception):
    """Raised for a missing version OR one owned by a different client_id."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SemanticStore:
    """SQLite-backed store for semantic-model drafts and version history.

    A fresh connection is opened per call, same rationale as the other stores
    in this codebase (sqlite3 connections aren't safe to share across threads;
    FastAPI runs sync endpoints in a threadpool).
    """

    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS semantic_drafts ("
                "id TEXT PRIMARY KEY, client_id TEXT NOT NULL, section TEXT NOT NULL, "
                "item_key TEXT NOT NULL, data TEXT NOT NULL, action TEXT NOT NULL, "
                "validated INTEGER NOT NULL DEFAULT 0, "
                "updated_at TEXT NOT NULL, updated_by TEXT)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_semantic_drafts_key "
                "ON semantic_drafts(client_id, section, item_key)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS semantic_versions ("
                "id TEXT PRIMARY KEY, client_id TEXT NOT NULL, version INTEGER NOT NULL, "
                "snapshot TEXT NOT NULL, changed_items TEXT NOT NULL, "
                "author TEXT, created_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_semantic_versions_num "
                "ON semantic_versions(client_id, version)"
            )
            self._migrate(conn)

    @staticmethod
    def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Guarded-ALTER seam for future schema evolution -- both tables are
        new, so there's nothing to migrate yet."""
        _ = self._columns(conn, "semantic_drafts")
        _ = self._columns(conn, "semantic_versions")

    # --- drafts --------------------------------------------------------

    _DRAFT_COLS = "id, client_id, section, item_key, data, action, validated, updated_at, updated_by"

    @staticmethod
    def _draft_row_to_dict(r: tuple) -> dict:
        return {
            "id": r[0],
            "client_id": r[1],
            "section": r[2],
            "item_key": r[3],
            "data": json.loads(r[4]),
            "action": r[5],
            "validated": bool(r[6]),
            "updated_at": r[7],
            "updated_by": r[8],
        }

    def list_drafts(self, client_id: str, section: str | None = None) -> list[dict]:
        sql = f"SELECT {self._DRAFT_COLS} FROM semantic_drafts WHERE client_id = ?"
        params: list = [client_id]
        if section:
            sql += " AND section = ?"
            params.append(section)
        with closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._draft_row_to_dict(r) for r in rows]

    def get_draft(self, client_id: str, section: str, item_key: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._DRAFT_COLS} FROM semantic_drafts "
                "WHERE client_id = ? AND section = ? AND item_key = ?",
                (client_id, section, item_key),
            ).fetchone()
        return self._draft_row_to_dict(row) if row else None

    def save_draft(
        self,
        client_id: str,
        section: str,
        item_key: str,
        data: dict,
        action: str = "edit",
        author: str | None = None,
    ) -> dict:
        """Upsert a draft. Any save resets `validated` to False -- a draft is
        only as validated as its CURRENT content; editing it again means it
        must be re-validated before it can be published."""
        now = _now()
        draft_id = uuid.uuid4().hex
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO semantic_drafts "
                "(id, client_id, section, item_key, data, action, validated, updated_at, updated_by) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?) "
                "ON CONFLICT(client_id, section, item_key) DO UPDATE SET "
                "data = excluded.data, action = excluded.action, validated = 0, "
                "updated_at = excluded.updated_at, updated_by = excluded.updated_by",
                (draft_id, client_id, section, item_key, json.dumps(data), action, now, author),
            )
        return self.get_draft(client_id, section, item_key)

    def mark_validated(self, client_id: str, section: str, item_key: str, ok: bool) -> None:
        with closing(self._connect()) as conn, conn:
            if self.get_draft(client_id, section, item_key) is None:
                raise SemanticDraftNotFoundError(item_key)
            conn.execute(
                "UPDATE semantic_drafts SET validated = ? "
                "WHERE client_id = ? AND section = ? AND item_key = ?",
                (1 if ok else 0, client_id, section, item_key),
            )

    def discard_draft(self, client_id: str, section: str, item_key: str) -> None:
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "DELETE FROM semantic_drafts WHERE client_id = ? AND section = ? AND item_key = ?",
                (client_id, section, item_key),
            )
            if cur.rowcount == 0:
                raise SemanticDraftNotFoundError(item_key)

    def clear_drafts(self, client_id: str, items: list[tuple[str, str]]) -> None:
        """Remove drafts that were just published (they're live now)."""
        with closing(self._connect()) as conn, conn:
            for section, item_key in items:
                conn.execute(
                    "DELETE FROM semantic_drafts WHERE client_id = ? AND section = ? AND item_key = ?",
                    (client_id, section, item_key),
                )

    # --- versions --------------------------------------------------------

    _VERSION_COLS = "id, client_id, version, snapshot, changed_items, author, created_at"

    @staticmethod
    def _version_row_to_dict(r: tuple) -> dict:
        return {
            "id": r[0],
            "client_id": r[1],
            "version": r[2],
            "snapshot": json.loads(r[3]),
            "changed_items": json.loads(r[4]),
            "author": r[5],
            "created_at": r[6],
        }

    def latest_version(self, client_id: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._VERSION_COLS} FROM semantic_versions "
                "WHERE client_id = ? ORDER BY version DESC LIMIT 1",
                (client_id,),
            ).fetchone()
        return self._version_row_to_dict(row) if row else None

    def list_versions(self, client_id: str) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {self._VERSION_COLS} FROM semantic_versions "
                "WHERE client_id = ? ORDER BY version DESC",
                (client_id,),
            ).fetchall()
        return [self._version_row_to_dict(r) for r in rows]

    def get_version(self, client_id: str, version_id: str) -> dict:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._VERSION_COLS} FROM semantic_versions "
                "WHERE client_id = ? AND id = ?",
                (client_id, version_id),
            ).fetchone()
        if row is None:
            raise SemanticVersionNotFoundError(version_id)
        return self._version_row_to_dict(row)

    def record_version(
        self, client_id: str, snapshot: dict[str, str], changed_items: list[str], author: str | None
    ) -> dict:
        """Insert the next version for this client. `snapshot` is {filename:
        raw_text} for every semantic YAML file, captured AFTER the write this
        version represents."""
        latest = self.latest_version(client_id)
        next_version = (latest["version"] + 1) if latest else 1
        version_id = uuid.uuid4().hex
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO semantic_versions "
                "(id, client_id, version, snapshot, changed_items, author, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (version_id, client_id, next_version, json.dumps(snapshot),
                 json.dumps(changed_items), author, now),
            )
        return self.get_version(client_id, version_id)

    def ensure_baseline(self, client_id: str, current_files: dict[str, str]) -> dict:
        """Seed version 1 from whatever's on disk today, if this client has no
        version history yet -- so there's always something to restore to, even
        before any admin has published an edit. Idempotent: a no-op once a v1
        exists."""
        existing = self.latest_version(client_id)
        if existing is not None:
            return existing
        return self.record_version(client_id, current_files, changed_items=[], author=None)
