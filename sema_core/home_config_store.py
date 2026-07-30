"""
SEMA: server-side Home screen configuration store (spec §1).

Backs the client admin panel's "Home screen" screen: a Draft -> Publish ->
Revert workflow over ONE JSON blob per client (unlike the semantic model's
many independently-versioned items, the home screen is edited as a whole --
see sema_core.home_config for the shape and defaults).

Lives in the SAME small SQLite metadata store as the other admin-panel
stores (var/sema_state.db). Mirrors OrgSettingsStore's conventions on
purpose: one connection per call, parameterized SQL, ISO-UTC timestamps, a
client_id ownership check on every method, one row per client auto-created
on first read.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HomeConfigNotFoundError(Exception):
    """Raised when publish/revert is attempted with no draft to act on."""


class HomeConfigStore:
    """SQLite-backed store for one home-config row per client."""

    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS org_home_config ("
                "client_id TEXT PRIMARY KEY, draft TEXT, published TEXT, "
                "version INTEGER NOT NULL DEFAULT 0, "
                "published_by TEXT, published_at TEXT, updated_at TEXT NOT NULL)"
            )

    @staticmethod
    def _row_to_dict(r: tuple) -> dict:
        return {
            "client_id": r[0],
            "draft": json.loads(r[1]) if r[1] is not None else None,
            "published": json.loads(r[2]) if r[2] is not None else None,
            "version": r[3],
            "published_by": r[4],
            "published_at": r[5],
            "updated_at": r[6],
        }

    _COLS = "client_id, draft, published, version, published_by, published_at, updated_at"

    def get(self, client_id: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._COLS} FROM org_home_config WHERE client_id = ?", (client_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_or_create(self, client_id: str) -> dict:
        """The row every read starts from -- self-healing, same spirit as
        OrgSettingsStore.get_or_create. A brand-new client has no draft and
        no published config; callers fall back to home_config.DEFAULT_CONFIG."""
        existing = self.get(client_id)
        if existing is not None:
            return existing
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO org_home_config "
                "(client_id, draft, published, version, published_by, published_at, updated_at) "
                "VALUES (?, NULL, NULL, 0, NULL, NULL, ?)",
                (client_id, now),
            )
        return self.get(client_id)

    def save_draft(self, client_id: str, config: dict) -> dict:
        """Upsert the whole draft blob (autosave, per field-group or the
        whole form -- the caller decides the granularity, this just stores
        whatever JSON-able dict it's given). No validation here: deep
        validation (metrics exist/certified, KPI count in range, ...) only
        runs at Publish, same "save freely, validate on the gate" pattern as
        the semantic model's draft/validate/publish split."""
        self.get_or_create(client_id)
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE org_home_config SET draft = ?, updated_at = ? WHERE client_id = ?",
                (json.dumps(config), now, client_id),
            )
        return self.get(client_id)

    def publish(self, client_id: str, published_by: str | None) -> dict:
        """Promote the current draft to published, bump the version, and
        clear the draft (it's live now). Raises HomeConfigNotFoundError if
        there's no draft to publish -- callers validate the draft's CONTENT
        before calling this (see home_config_validate), so by the time this
        runs the config is already known-good."""
        row = self.get_or_create(client_id)
        if row["draft"] is None:
            raise HomeConfigNotFoundError(client_id)
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE org_home_config SET published = draft, draft = NULL, "
                "version = version + 1, published_by = ?, published_at = ?, updated_at = ? "
                "WHERE client_id = ?",
                (published_by, now, now, client_id),
            )
        return self.get(client_id)

    def revert(self, client_id: str) -> dict:
        """Discard the in-progress draft, resetting the editor back to the
        last published config (or to no draft at all if nothing was ever
        published) -- the simple undo the spec's "Revert" button performs,
        distinct from the semantic model's full version-history restore."""
        row = self.get_or_create(client_id)
        if row["draft"] is None:
            raise HomeConfigNotFoundError(client_id)
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE org_home_config SET draft = NULL, updated_at = ? WHERE client_id = ?",
                (now, client_id),
            )
        return self.get(client_id)
