"""
SEMA: database access layer (multi-client, framework-free).

No Streamlit here anymore: connections come from psycopg2's own
ThreadedConnectionPool -- one pool per (client_id, role) -- so both Streamlit
and FastAPI share the same core, and concurrent FastAPI request threads never
share a single connection (psycopg2 connections are not safe for concurrent
queries). Think of it like a BI gateway's connection pool: each query checks a
connection out, uses it, and returns it.

Roles:
  "full"     -- the app user (schema introspection + predefined queries).
  "readonly" -- the sema_readonly role for the agent's run_sql tool, with a
                statement_timeout so runaway queries are killed.

Public helpers (run_query / run_sql_readonly / check_connection) resolve the
active client from context by default, so the agent and UI don't have to
thread the id through every call.
"""

from __future__ import annotations

import os
import threading
import warnings

import pandas as pd
import psycopg2
from psycopg2 import pool as pg_pool
from dotenv import load_dotenv

from client_registry import active_client_id, get_client_by_id
from settings import settings

load_dotenv()

# pandas warns when given a raw DBAPI (psycopg2) connection instead of a
# SQLAlchemy engine. It still works correctly for read queries -- we accept
# that trade-off here to avoid adding a SQLAlchemy dependency for this phase.
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

# Kill any read-only query running longer than this (SEMA_STATEMENT_TIMEOUT_MS).
READONLY_TIMEOUT_MS = settings.statement_timeout_ms


def _db_name(client_id: str) -> str:
    """Resolve a client's database name from its db_env var (fallback <id>_db)."""
    client = get_client_by_id(client_id)
    return os.environ.get(client.get("db_env", ""), f"{client_id}_db")


# ---------------------------------------------------------------------------
# Connection pools: one ThreadedConnectionPool per (client_id, role), created
# lazily on first use. The dict + lock replace @st.cache_resource with plain
# Python, so this module imports and works identically under Streamlit,
# FastAPI, tests, and scripts.
# ---------------------------------------------------------------------------
_pools: dict[tuple[str, str], pg_pool.ThreadedConnectionPool] = {}
_pools_lock = threading.Lock()


def _make_pool(client_id: str, role: str) -> pg_pool.ThreadedConnectionPool:
    common = {
        "host": settings.db_host,
        "port": settings.db_port,
        "dbname": _db_name(client_id),
    }
    if role == "readonly":
        common.update(
            user=settings.db_readonly_user,
            password=settings.db_readonly_password,
            options=f"-c statement_timeout={READONLY_TIMEOUT_MS}",
        )
    else:
        common.update(user=settings.db_user, password=settings.db_password)
    return pg_pool.ThreadedConnectionPool(minconn=1, maxconn=settings.db_pool_max, **common)


def _get_pool(client_id: str, role: str) -> pg_pool.ThreadedConnectionPool:
    key = (client_id, role)
    with _pools_lock:
        existing = _pools.get(key)
        if existing is None or existing.closed:
            _pools[key] = _make_pool(client_id, role)
        return _pools[key]


def close_all_pools() -> None:
    """Close every pool (used by tests and graceful shutdown)."""
    with _pools_lock:
        for p in _pools.values():
            if not p.closed:
                p.closeall()
        _pools.clear()


def _query_pooled(client_id: str, role: str, sql: str, params: dict | None) -> pd.DataFrame:
    """Check a connection out of the pool, run the query, return it clean.

    A broken connection (server restarted, network drop) is discarded instead
    of being put back, so the pool heals itself.
    """
    p = _get_pool(client_id, role)
    conn = p.getconn()
    broken = False
    try:
        # The agent's read-only queries run in autocommit so one failed query
        # never leaves an aborted transaction behind for the next checkout.
        if role == "readonly" and not conn.autocommit:
            conn.autocommit = True
        df = pd.read_sql_query(sql, conn, params=params)
        if not conn.autocommit:
            conn.rollback()  # end the implicit read transaction; conn goes back clean
        return df
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        broken = True  # connection-level failure: drop it from the pool
        raise
    except Exception:
        # SQL-level failure: the transaction may be aborted; roll it back so
        # the connection is reusable. If even that fails, discard it.
        if not conn.autocommit:
            try:
                conn.rollback()
            except Exception:
                broken = True
        raise
    finally:
        p.putconn(conn, close=broken)


def _run(sql: str, params: dict | None, client_id: str | None, role: str) -> pd.DataFrame:
    """Resolve the client, run via the pool, retrying once on a stale connection."""
    cid = client_id or active_client_id()
    try:
        return _query_pooled(cid, role, sql, params)
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        # e.g. the DB container restarted: the bad conn was discarded above,
        # so one retry gets a fresh connection.
        return _query_pooled(cid, role, sql, params)


def run_query(sql: str, params: dict | None = None, client_id: str | None = None) -> pd.DataFrame:
    """Run a read-only SELECT against the active (or given) client's DB."""
    return _run(sql, params, client_id, role="full")


def run_sql_readonly(sql: str, client_id: str | None = None) -> pd.DataFrame:
    """Run already-validated SQL through the active client's read-only role.

    Validation/sanitization happens in agent/safety.py BEFORE this is called.
    This function is the last hop to the database.
    """
    return _run(sql, None, client_id, role="readonly")


def check_connection(client_id: str | None = None) -> bool:
    """True if the active (or given) client's database is reachable."""
    try:
        run_query("SELECT 1", client_id=client_id)
        return True
    except Exception:
        return False
