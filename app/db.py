"""
SEMA: database access layer (multi-client).

Each client has its own database. The connections are cached with
@st.cache_resource **keyed by client_id** -- Streamlit keeps a separate cache
entry per distinct argument value, so every client gets its own persistent
connection and switching clients never reuses the wrong one (the old bug where
a single cached connection stuck to the first DB). Think of it as one pooled
connection per data model, looked up by name.

Public helpers (run_query / run_sql_readonly / check_connection) resolve the
active client from session state by default, so the agent and UI don't have to
thread the id through every call.
"""

from __future__ import annotations

import os
import warnings

import pandas as pd
import psycopg2
import streamlit as st
from dotenv import load_dotenv

from client_registry import active_client_id, get_client_by_id

load_dotenv()

# pandas warns when given a raw DBAPI (psycopg2) connection instead of a
# SQLAlchemy engine. It still works correctly for read queries -- we accept
# that trade-off here to avoid adding a SQLAlchemy dependency for this phase.
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

READONLY_TIMEOUT_MS = 5000  # kill any read-only query running longer than 5s


def _db_name(client_id: str) -> str:
    """Resolve a client's database name from its db_env var (fallback <id>_db)."""
    client = get_client_by_id(client_id)
    return os.environ.get(client.get("db_env", ""), f"{client_id}_db")


# ---------------------------------------------------------------------------
# Full-access connection (app introspection + predefined queries).
# Cached per client_id: get_connection("ecommerce") and ("insurance") are two
# separate cached connections.
# ---------------------------------------------------------------------------
@st.cache_resource
def get_connection(client_id: str) -> "psycopg2.extensions.connection":
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=_db_name(client_id),
        user=os.environ.get("POSTGRES_USER", "sema_user"),
        password=os.environ.get("POSTGRES_PASSWORD", "sema_password"),
    )


def run_query(sql: str, params: dict | None = None, client_id: str | None = None) -> pd.DataFrame:
    """Run a read-only SELECT against the active (or given) client's DB.

    If the cached connection has gone stale (e.g. the DB container restarted),
    reconnect once and retry.
    """
    cid = client_id or active_client_id()
    try:
        return pd.read_sql_query(sql, get_connection(cid), params=params)
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        get_connection.clear()
        return pd.read_sql_query(sql, get_connection(cid), params=params)


def check_connection(client_id: str | None = None) -> bool:
    """True if the active (or given) client's database is reachable."""
    try:
        run_query("SELECT 1", client_id=client_id)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Read-only connection for the agent's run_sql tool.
#
# Uses the sema_readonly role (sql/create_readonly_role.sql), which can ONLY
# SELECT, plus a statement_timeout so any runaway query is killed. Cached per
# client_id, like get_connection. autocommit=True keeps each query in its own
# transaction so one failure doesn't poison the next.
# ---------------------------------------------------------------------------
@st.cache_resource
def get_readonly_connection(client_id: str) -> "psycopg2.extensions.connection":
    conn = psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=_db_name(client_id),
        user=os.environ.get("POSTGRES_READONLY_USER", "sema_readonly"),
        password=os.environ.get("POSTGRES_READONLY_PASSWORD", "sema_readonly_pw"),
        options=f"-c statement_timeout={READONLY_TIMEOUT_MS}",
    )
    conn.autocommit = True
    return conn


def run_sql_readonly(sql: str, client_id: str | None = None) -> pd.DataFrame:
    """Run already-validated SQL through the active client's read-only connection.

    Validation/sanitization happens in agent/safety.py BEFORE this is called.
    This function is the last hop to the database.
    """
    cid = client_id or active_client_id()
    try:
        return pd.read_sql_query(sql, get_readonly_connection(cid))
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        get_readonly_connection.clear()
        return pd.read_sql_query(sql, get_readonly_connection(cid))
