"""
SEMA: append-only admin-action audit log.

Backs the client admin panel's "Audit log" screen (spec §3): every mutating
admin action -- inviting/removing a user, changing a role or data scope,
publishing the semantic model, editing organization settings -- lands here as
one immutable row. Lives in the SAME small SQLite metadata store as the other
admin-panel stores (var/sema_state.db).

Append-only is enforced at the DATABASE level, not just by convention: this
module exposes no update/delete method, and two triggers make an UPDATE or
DELETE against audit_events fail outright even from a raw SQL statement.

Mirrors semantic_store.py's conventions on purpose: one connection per call,
parameterized SQL, uuid4 hex ids, ISO-UTC timestamps, a client_id ownership
check on every method.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from sema_core import sqlite_utils

PAGE_SIZE = 50
EXPORT_ROW_CAP = 10_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditStore:
    """SQLite-backed store for the append-only admin audit log.

    A fresh connection is opened per call, same rationale as the other stores
    in this codebase (sqlite3 connections aren't safe to share across
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
                "CREATE TABLE IF NOT EXISTS audit_events ("
                "id TEXT PRIMARY KEY, client_id TEXT NOT NULL, "
                "actor_id TEXT, actor_name TEXT, actor_role TEXT, "
                "action TEXT NOT NULL, "
                "target_type TEXT, target_id TEXT, target_label TEXT, "
                "before TEXT, after TEXT, "
                "created_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_events_client_created "
                "ON audit_events(client_id, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_events_client_actor "
                "ON audit_events(client_id, actor_id)"
            )
            # Append-only, enforced at the DATABASE level: a raw UPDATE or
            # DELETE against this table fails even if some future code path
            # tries it directly, not just "no store method calls it".
            conn.execute(
                "CREATE TRIGGER IF NOT EXISTS audit_events_no_update "
                "BEFORE UPDATE ON audit_events BEGIN "
                "SELECT RAISE(ABORT, 'audit_events is append-only'); END"
            )
            conn.execute(
                "CREATE TRIGGER IF NOT EXISTS audit_events_no_delete "
                "BEFORE DELETE ON audit_events BEGIN "
                "SELECT RAISE(ABORT, 'audit_events is append-only'); END"
            )

    # --- row mapping ---------------------------------------------------

    _COLS = (
        "id, client_id, actor_id, actor_name, actor_role, action, "
        "target_type, target_id, target_label, before, after, created_at"
    )

    @staticmethod
    def _row_to_dict(r: tuple) -> dict:
        return {
            "id": r[0],
            "client_id": r[1],
            "actor_id": r[2],
            "actor_name": r[3],
            "actor_role": r[4],
            "action": r[5],
            "target_type": r[6],
            "target_id": r[7],
            "target_label": r[8],
            "before": json.loads(r[9]) if r[9] is not None else None,
            "after": json.loads(r[10]) if r[10] is not None else None,
            "created_at": r[11],
        }

    # --- writes --------------------------------------------------------

    def record(
        self,
        client_id: str,
        *,
        actor_id: str | None,
        actor_name: str | None,
        actor_role: str | None,
        action: str,
        target_type: str | None = None,
        target_id: str | None = None,
        target_label: str | None = None,
        before: dict | None = None,
        after: dict | None = None,
    ) -> dict:
        """Append one audit event. `action` is a canonical dotted id
        (e.g. "user.role_changed", "semantic.published") -- the frontend
        keys its human-readable sentence templates off it."""
        event_id = uuid.uuid4().hex
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                f"INSERT INTO audit_events ({self._COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id, client_id, actor_id, actor_name, actor_role, action,
                    target_type, target_id, target_label,
                    json.dumps(before) if before is not None else None,
                    json.dumps(after) if after is not None else None,
                    now,
                ),
            )
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._COLS} FROM audit_events WHERE id = ?", (event_id,)
            ).fetchone()
        return self._row_to_dict(row)

    # --- reads -----------------------------------------------------------

    @staticmethod
    def _where_clause(
        client_id: str,
        actor_id: str | None,
        category: str | None,
        start: str | None,
        end: str | None,
        q: str | None,
    ) -> tuple[str, list]:
        clauses = ["client_id = ?"]
        params: list = [client_id]
        if actor_id:
            clauses.append("actor_id = ?")
            params.append(actor_id)
        if category:
            # Prefix match on the dotted action id, e.g. "user" matches
            # "user.role_changed", "user.invited", ... -- the category tag.
            clauses.append("action LIKE ?")
            params.append(f"{category}%")
        if start:
            clauses.append("created_at >= ?")
            params.append(start)
        if end:
            clauses.append("created_at <= ?")
            params.append(end)
        if q:
            clauses.append("LOWER(target_label) LIKE ?")
            params.append(f"%{q.lower()}%")
        return " AND ".join(clauses), params

    def list_events(
        self,
        client_id: str,
        *,
        actor_id: str | None = None,
        category: str | None = None,
        start: str | None = None,
        end: str | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = PAGE_SIZE,
    ) -> dict:
        """One page of events, newest first, plus the total matching count
        (for pagination controls)."""
        where, params = self._where_clause(client_id, actor_id, category, start, end, q)
        page = max(1, page)
        with closing(self._connect()) as conn:
            (total,) = conn.execute(
                f"SELECT COUNT(*) FROM audit_events WHERE {where}", params
            ).fetchone()
            rows = conn.execute(
                f"SELECT {self._COLS} FROM audit_events WHERE {where} "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
        return {
            "events": [self._row_to_dict(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def export_rows(
        self,
        client_id: str,
        *,
        actor_id: str | None = None,
        category: str | None = None,
        start: str | None = None,
        end: str | None = None,
        q: str | None = None,
        limit: int = EXPORT_ROW_CAP,
    ) -> list[dict]:
        """Every matching event (capped at `limit`), newest first -- for CSV
        export. No pagination: the whole filtered set in one shot."""
        where, params = self._where_clause(client_id, actor_id, category, start, end, q)
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {self._COLS} FROM audit_events WHERE {where} "
                "ORDER BY created_at DESC LIMIT ?",
                [*params, limit],
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]
