"""
SEMA: one-off connection testing for the self-service SQL DB wizard
(data_sources_add_prompt.md Path A). Deliberately separate from
sema_core.db's pooled connections: those are keyed by (client_id, role)
against THIS project's own configured tenant databases, whereas this module
opens a single throwaway connection to whatever ARBITRARY host/credentials
an admin just typed into the wizard, purely to test them.

Security invariants:
  - Every returned error is a SCRUBBED, generic message -- host/user/password
    (and the raw driver exception, which often echoes them back) never reach
    the caller. See _scrub().
  - The write-permission probe is 100% read-only: it queries privilege
    catalogs (information_schema / has_*_privilege), never attempts an
    actual INSERT/CREATE/DROP. Nothing is ever written to the target DB by
    this module.
  - Nothing here persists anything -- the wizard only stores credentials
    AFTER this test reports ok=True (sema_core.client_connections_store).
"""

from __future__ import annotations

CONNECT_TIMEOUT_S = 5


class ProbeError(Exception):
    """A scrubbed, user-safe error message -- never wraps the raw driver
    exception's own text (which can include host/user/password)."""


def _scrub(connector_type: str) -> str:
    """A generic, safe message for ANY connection failure. Deliberately
    doesn't distinguish "wrong password" from "host unreachable" from "DB
    doesn't exist": those distinctions are exactly the kind of detail an
    attacker probing a host they don't own could use, and the admin
    testing their OWN connection already knows what they typed."""
    labels = {"postgres": "PostgreSQL", "mysql": "MySQL", "mssql": "SQL Server"}
    label = labels.get(connector_type, "the database")
    return f"Could not connect to {label}. Check the host, port, and credentials."


def _postgres_probe(host, port, database, username, password, ssl_enabled) -> tuple[list[str], bool]:
    import psycopg2

    conn = psycopg2.connect(
        host=host, port=port, dbname=database, user=username, password=password,
        connect_timeout=CONNECT_TIMEOUT_S, sslmode="require" if ssl_enabled else "prefer",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
            tables = [r[0] for r in cur.fetchall()]
            # Read-only, catalog-only check -- never attempts a real write.
            cur.execute(
                "SELECT has_schema_privilege(current_user, 'public', 'CREATE') "
                "OR has_database_privilege(current_user, current_database(), 'CREATE')"
            )
            write_access = bool(cur.fetchone()[0])
        return tables, write_access
    finally:
        conn.close()


def _mysql_probe(host, port, database, username, password, ssl_enabled) -> tuple[list[str], bool]:
    import pymysql

    conn = pymysql.connect(
        host=host, port=port, database=database, user=username, password=password,
        connect_timeout=CONNECT_TIMEOUT_S,
        ssl={"ssl": {}} if ssl_enabled else None,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s ORDER BY table_name",
                (database,),
            )
            tables = [r[0] for r in cur.fetchall()]
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.SCHEMA_PRIVILEGES "
                "WHERE TABLE_SCHEMA = %s AND PRIVILEGE_TYPE IN ('INSERT', 'UPDATE', 'CREATE', 'DROP') "
                "AND GRANTEE LIKE CONCAT('%%', %s, '%%')",
                (database, username),
            )
            write_access = cur.fetchone()[0] > 0
        return tables, write_access
    finally:
        conn.close()


def _mssql_probe(host, port, database, username, password, ssl_enabled) -> tuple[list[str], bool]:
    import pymssql

    conn = pymssql.connect(
        server=host, port=str(port), database=database, user=username, password=password,
        login_timeout=CONNECT_TIMEOUT_S, timeout=CONNECT_TIMEOUT_S,
    )
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"
        )
        tables = [r[0] for r in cur.fetchall()]
        # has_perms_by_name is read-only -- asks SQL Server to evaluate the
        # CURRENT user's own permission, never attempts to exercise it.
        cur.execute(
            "SELECT has_perms_by_name(DB_NAME(), 'DATABASE', 'INSERT') "
            "+ has_perms_by_name(DB_NAME(), 'DATABASE', 'CREATE TABLE')"
        )
        write_access = (cur.fetchone()[0] or 0) > 0
        return tables, write_access
    finally:
        conn.close()


_PROBES = {"postgres": _postgres_probe, "mysql": _mysql_probe, "mssql": _mssql_probe}


def test_connection(
    connector_type: str, *, host: str, port: int, database: str, username: str, password: str, ssl_enabled: bool
) -> dict:
    """Connect once, list tables, and check (read-only) whether this user
    has write/DDL rights. Returns {"ok", "tables", "write_access", "error"}
    -- `error` is always a scrubbed, generic message (see _scrub), never the
    raw driver exception."""
    probe = _PROBES.get(connector_type)
    if probe is None:
        return {"ok": False, "tables": [], "write_access": None, "error": "Unsupported connector type."}
    try:
        tables, write_access = probe(host, port, database, username, password, ssl_enabled)
        return {"ok": True, "tables": tables, "write_access": write_access, "error": None}
    except Exception:
        return {"ok": False, "tables": [], "write_access": None, "error": _scrub(connector_type)}


# Ready-to-copy read-only-user SQL, shown when the write-permission probe
# finds the tested user has write/DDL rights -- steers the admin toward the
# same "dedicated read-only role" pattern this project's own agent uses
# (sql/create_readonly_role.sql), adapted per engine.
READONLY_USER_SQL: dict[str, str] = {
    "postgres": """-- Run as a superuser / owner on the target database.
CREATE ROLE sema_readonly LOGIN PASSWORD 'choose-a-strong-password';
GRANT CONNECT ON DATABASE {database} TO sema_readonly;
GRANT USAGE ON SCHEMA public TO sema_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sema_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO sema_readonly;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM sema_readonly;""",
    "mysql": """-- Run as a user with GRANT privileges on the target server.
CREATE USER 'sema_readonly'@'%' IDENTIFIED BY 'choose-a-strong-password';
GRANT SELECT ON {database}.* TO 'sema_readonly'@'%';
FLUSH PRIVILEGES;""",
    "mssql": """-- Run as a user with ALTER ANY LOGIN / db_owner rights.
CREATE LOGIN sema_readonly WITH PASSWORD = 'choose-a-strong-password';
USE {database};
CREATE USER sema_readonly FOR LOGIN sema_readonly;
ALTER ROLE db_datareader ADD MEMBER sema_readonly;""",
}


def readonly_user_sql(connector_type: str, database: str) -> str | None:
    template = READONLY_USER_SQL.get(connector_type)
    return template.replace("{database}", database) if template else None


def _connect(connector_type: str, host, port, database, username, password, ssl_enabled):
    if connector_type == "postgres":
        import psycopg2

        return psycopg2.connect(
            host=host, port=port, dbname=database, user=username, password=password,
            connect_timeout=CONNECT_TIMEOUT_S, sslmode="require" if ssl_enabled else "prefer",
        )
    if connector_type == "mysql":
        import pymysql

        return pymysql.connect(
            host=host, port=port, database=database, user=username, password=password,
            connect_timeout=CONNECT_TIMEOUT_S, ssl={"ssl": {}} if ssl_enabled else None,
        )
    if connector_type == "mssql":
        import pymssql

        return pymssql.connect(
            server=host, port=str(port), database=database, user=username, password=password,
            login_timeout=CONNECT_TIMEOUT_S, timeout=CONNECT_TIMEOUT_S,
        )
    raise ValueError(f"unsupported connector type: {connector_type!r}")


def check_health(
    connector_type: str, *, host: str, port: int, database: str, username: str, password: str,
    ssl_enabled: bool, primary_table: str | None = None, primary_date_field: str | None = None,
) -> dict:
    """Live reachability + (if configured) real data age for a self-service
    connection's status card -- same shape/spirit as sema_core.data_sources.
    source_health, but against an arbitrary stored connection instead of
    this project's own tenant DB. Errors are scrubbed the same way as
    test_connection."""
    try:
        conn = _connect(connector_type, host, port, database, username, password, ssl_enabled)
    except Exception:
        return {"reachable": False, "data_age_days": None, "error": _scrub(connector_type)}

    age_days = None
    try:
        if primary_table and primary_date_field:
            # Identifiers here come from the admin's OWN prior schema-review
            # step (Path A item 2), not raw end-user input at request time --
            # still worth keeping to a conservative charset before use.
            import re

            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", primary_table) and re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*", primary_date_field
            ):
                cur = conn.cursor()
                cur.execute(f"SELECT MAX({primary_date_field}) FROM {primary_table}")
                row = cur.fetchone()
                max_date = row[0] if row else None
                if max_date is not None:
                    from datetime import date, datetime, timezone

                    if isinstance(max_date, datetime):
                        dt = max_date if max_date.tzinfo else max_date.replace(tzinfo=timezone.utc)
                    elif isinstance(max_date, date):
                        dt = datetime(max_date.year, max_date.month, max_date.day, tzinfo=timezone.utc)
                    else:
                        dt = None
                    if dt is not None:
                        age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
        return {"reachable": True, "data_age_days": age_days, "error": None}
    except Exception:
        # Reachable but the age query itself failed (e.g. table renamed) --
        # still a healthy connection, just no age reading.
        return {"reachable": True, "data_age_days": None, "error": None}
    finally:
        conn.close()
