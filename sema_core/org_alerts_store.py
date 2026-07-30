"""
SEMA: org-owned template-based alerts (alert_templates_prompt.md item 2).

Unlike the semantic-layer YAML alerts (owned by the platform, hand-authored
per metric file), org_alerts belongs to the org: one row per admin-created
alert, keyed by (client_id, name). Lives in the same small SQLite metadata
store as the other admin-panel stores (var/sema_state.db) -- one table per
concern, same conventions as source_requests_store.py.

A second tiny table, org_alerts_migrations, is a one-row-per-client
idempotency marker (same pattern as retention_store.RetentionRunStore) so
the one-time YAML-alert migration (sema_core.org_alerts.ensure_migrated)
never re-seeds rows a client has since edited or deleted.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

MAX_ENABLED_PER_CLIENT = 12


class OrgAlertNotFoundError(Exception):
    pass


class OrgAlertLimitExceededError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrgAlertsStore:
    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS org_alerts ("
                "id TEXT PRIMARY KEY, client_id TEXT NOT NULL, name TEXT NOT NULL, "
                "metric TEXT NOT NULL, template TEXT NOT NULL, params TEXT NOT NULL, "
                "severity TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, "
                "disabled_reason TEXT, created_by TEXT, created_at TEXT NOT NULL, "
                "updated_at TEXT NOT NULL, "
                "UNIQUE(client_id, name))"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_org_alerts_client ON org_alerts(client_id)")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS org_alerts_migrations ("
                "client_id TEXT PRIMARY KEY, migrated_at TEXT NOT NULL)"
            )

    _COLS = (
        "id, client_id, name, metric, template, params, severity, enabled, "
        "disabled_reason, created_by, created_at, updated_at"
    )

    @staticmethod
    def _row_to_dict(r: tuple) -> dict:
        return {
            "id": r[0],
            "client_id": r[1],
            "name": r[2],
            "metric": r[3],
            "template": r[4],
            "params": json.loads(r[5]),
            "severity": r[6],
            "enabled": bool(r[7]),
            "disabled_reason": r[8],
            "created_by": r[9],
            "created_at": r[10],
            "updated_at": r[11],
        }

    def list_for_client(self, client_id: str) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {self._COLS} FROM org_alerts WHERE client_id = ? ORDER BY created_at", (client_id,)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get(self, client_id: str, alert_id: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._COLS} FROM org_alerts WHERE client_id = ? AND id = ?", (client_id, alert_id)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def count_enabled(self, client_id: str) -> int:
        with closing(self._connect()) as conn:
            (n,) = conn.execute(
                "SELECT COUNT(*) FROM org_alerts WHERE client_id = ? AND enabled = 1", (client_id,)
            ).fetchone()
        return n

    def create(
        self,
        client_id: str,
        *,
        name: str,
        metric: str,
        template: str,
        params: dict,
        severity: str,
        created_by: str | None,
        enabled: bool = True,
        alert_id: str | None = None,
    ) -> dict:
        if enabled and self.count_enabled(client_id) >= MAX_ENABLED_PER_CLIENT:
            raise OrgAlertLimitExceededError(
                f"This organization already has {MAX_ENABLED_PER_CLIENT} enabled alerts -- "
                "disable or delete one before adding another."
            )
        row_id = alert_id or uuid.uuid4().hex
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                f"INSERT INTO org_alerts ({self._COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row_id, client_id, name, metric, template, json.dumps(params), severity,
                    1 if enabled else 0, None, created_by, now, now,
                ),
            )
        return self.get(client_id, row_id)

    def update(self, client_id: str, alert_id: str, patch: dict) -> dict:
        """Partial update. `patch` may include name/metric/template/params/
        severity/enabled/disabled_reason -- unknown keys are ignored."""
        existing = self.get(client_id, alert_id)
        if existing is None:
            raise OrgAlertNotFoundError(alert_id)

        wants_enabled = patch.get("enabled", existing["enabled"])
        if wants_enabled and not existing["enabled"] and self.count_enabled(client_id) >= MAX_ENABLED_PER_CLIENT:
            raise OrgAlertLimitExceededError(
                f"This organization already has {MAX_ENABLED_PER_CLIENT} enabled alerts -- "
                "disable or delete one before enabling another."
            )

        fields = {**existing, **{k: v for k, v in patch.items() if k in (
            "name", "metric", "template", "params", "severity", "enabled", "disabled_reason"
        )}}
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE org_alerts SET name=?, metric=?, template=?, params=?, severity=?, "
                "enabled=?, disabled_reason=?, updated_at=? WHERE client_id=? AND id=?",
                (
                    fields["name"], fields["metric"], fields["template"], json.dumps(fields["params"]),
                    fields["severity"], 1 if fields["enabled"] else 0, fields["disabled_reason"], _now(),
                    client_id, alert_id,
                ),
            )
        return self.get(client_id, alert_id)

    def delete(self, client_id: str, alert_id: str) -> None:
        with closing(self._connect()) as conn, conn:
            cur = conn.execute("DELETE FROM org_alerts WHERE client_id = ? AND id = ?", (client_id, alert_id))
            if cur.rowcount == 0:
                raise OrgAlertNotFoundError(alert_id)

    def has_migrated(self, client_id: str) -> bool:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM org_alerts_migrations WHERE client_id = ?", (client_id,)
            ).fetchone()
        return row is not None

    def mark_migrated(self, client_id: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT OR IGNORE INTO org_alerts_migrations (client_id, migrated_at) VALUES (?, ?)",
                (client_id, _now()),
            )
