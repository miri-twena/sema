"""
SEMA: self-service SQL DB connections store (data_sources_add_prompt.md
Path A). Backs the "add a data source" wizard's credential storage. Lives
in the SAME small SQLite metadata store as the other admin-panel stores
(var/sema_state.db) -- mirrors org_settings_store.py's conventions: one
connection per call, parameterized SQL, ISO-UTC timestamps.

Security invariant this whole module exists to enforce: `password` is
NEVER stored in plaintext (sema_core.secrets.encrypt_secret handles that
before it reaches here) and this store's own read methods NEVER return the
decrypted password -- only `get_password_for_test` does, and that method is
for internal server-side use (opening a real connection), never serialized
into an API response.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from sema_core.secrets import decrypt_secret

VALID_CONNECTOR_TYPES = frozenset({"postgres", "mysql", "mssql"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConnectionNotFoundError(Exception):
    pass


class ClientConnectionsStore:
    """SQLite-backed store for self-service SQL DB connections, one row per
    connection. A client can have more than one (e.g. two Postgres DBs)."""

    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS client_connections ("
                "id TEXT PRIMARY KEY, client_id TEXT NOT NULL, connector_type TEXT NOT NULL, "
                "display_name TEXT NOT NULL, host TEXT NOT NULL, port INTEGER NOT NULL, "
                "database_name TEXT NOT NULL, username TEXT NOT NULL, "
                "encrypted_password TEXT NOT NULL, ssl_enabled INTEGER NOT NULL, "
                "fingerprint TEXT NOT NULL, primary_table TEXT, primary_date_field TEXT, "
                "status TEXT NOT NULL, created_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_client_connections_client "
                "ON client_connections(client_id)"
            )

    _COLS = (
        "id, client_id, connector_type, display_name, host, port, database_name, username, "
        "encrypted_password, ssl_enabled, fingerprint, primary_table, primary_date_field, "
        "status, created_by, created_at, updated_at"
    )

    @staticmethod
    def _row_to_dict(r: tuple, *, include_encrypted: bool = False) -> dict:
        d = {
            "id": r[0],
            "client_id": r[1],
            "connector_type": r[2],
            "display_name": r[3],
            "host": r[4],
            "port": r[5],
            "database_name": r[6],
            "username": r[7],
            "ssl_enabled": bool(r[9]),
            "fingerprint": r[10],
            "primary_table": r[11],
            "primary_date_field": r[12],
            "status": r[13],
            "created_by": r[14],
            "created_at": r[15],
            "updated_at": r[16],
        }
        if include_encrypted:
            d["encrypted_password"] = r[8]
        return d

    def create(
        self,
        client_id: str,
        *,
        connector_type: str,
        display_name: str,
        host: str,
        port: int,
        database_name: str,
        username: str,
        encrypted_password: str,
        ssl_enabled: bool,
        fingerprint: str,
        primary_table: str | None,
        primary_date_field: str | None,
        created_by: str | None,
    ) -> dict:
        conn_id = uuid.uuid4().hex
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                f"INSERT INTO client_connections ({self._COLS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    conn_id, client_id, connector_type, display_name, host, port, database_name,
                    username, encrypted_password, int(ssl_enabled), fingerprint,
                    primary_table, primary_date_field, "healthy", created_by, now, now,
                ),
            )
        return self.get(client_id, conn_id)

    def list_for_client(self, client_id: str) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {self._COLS} FROM client_connections WHERE client_id = ? ORDER BY created_at",
                (client_id,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get(self, client_id: str, connection_id: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._COLS} FROM client_connections WHERE client_id = ? AND id = ?",
                (client_id, connection_id),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def decrypted_password_for_test(self, client_id: str, connection_id: str) -> str:
        """The plaintext password, for internal use ONLY (opening a real
        connection for a health check) -- never serialize this into an API
        response. Raises ConnectionNotFoundError if the connection doesn't
        belong to this client."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._COLS} FROM client_connections WHERE client_id = ? AND id = ?",
                (client_id, connection_id),
            ).fetchone()
        if row is None:
            raise ConnectionNotFoundError(connection_id)
        d = self._row_to_dict(row, include_encrypted=True)
        return decrypt_secret(d["encrypted_password"])

    def update_credentials(
        self,
        client_id: str,
        connection_id: str,
        *,
        host: str,
        port: int,
        database_name: str,
        username: str,
        encrypted_password: str,
        ssl_enabled: bool,
        fingerprint: str,
    ) -> dict:
        """Re-entering credentials is the ONLY way to edit a connection
        (data_sources_add_prompt.md item 3) -- there is no partial-field
        edit that could leave a stale, unverified credential in place."""
        now = _now()
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "UPDATE client_connections SET host = ?, port = ?, database_name = ?, "
                "username = ?, encrypted_password = ?, ssl_enabled = ?, fingerprint = ?, "
                "status = 'healthy', updated_at = ? WHERE client_id = ? AND id = ?",
                (host, port, database_name, username, encrypted_password, int(ssl_enabled),
                 fingerprint, now, client_id, connection_id),
            )
            if cur.rowcount == 0:
                raise ConnectionNotFoundError(connection_id)
        return self.get(client_id, connection_id)

    def set_status(self, client_id: str, connection_id: str, status: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE client_connections SET status = ?, updated_at = ? WHERE client_id = ? AND id = ?",
                (status, _now(), client_id, connection_id),
            )
