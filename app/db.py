"""
SEMA: database access layer.

A single, cached PostgreSQL connection (via psycopg2) used to run every
predefined query in sql/queries/*.sql and return the result as a pandas
DataFrame. Streamlit re-runs main.py on every interaction, so the
connection is cached with st.cache_resource -- think of this like a
connection pool with one connection, kept open across reruns instead of
reconnecting every time (the same idea as a persistent BI tool connection,
vs. opening a fresh ODBC connection per query).
"""

from __future__ import annotations

import os
import warnings

import pandas as pd
import psycopg2
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# pandas warns when given a raw DBAPI (psycopg2) connection instead of a
# SQLAlchemy engine. It still works correctly for read queries -- we accept
# that trade-off here to avoid adding a SQLAlchemy dependency for this phase.
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")


def _db_name() -> str:
    """Which database to connect to, based on the active client.

    SEMA_CLIENT=insurance -> insurance_db; otherwise the default ecommerce DB.
    This is the database half of the multi-client switch (the semantic-layer
    half lives in agent/semantic.py).
    """
    if os.environ.get("SEMA_CLIENT", "").strip().lower() == "insurance":
        return os.environ.get("POSTGRES_DB_INSURANCE", "insurance_db")
    return os.environ.get("POSTGRES_DB", "sema_db")


@st.cache_resource
def get_connection() -> "psycopg2.extensions.connection":
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=_db_name(),
        user=os.environ.get("POSTGRES_USER", "sema_user"),
        password=os.environ.get("POSTGRES_PASSWORD", "sema_password"),
    )


def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run a read-only SELECT and return the result as a DataFrame.

    If the cached connection has gone stale (e.g. the DB container
    restarted), reconnect once and retry.
    """
    try:
        conn = get_connection()
        return pd.read_sql_query(sql, conn, params=params)
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        get_connection.clear()
        conn = get_connection()
        return pd.read_sql_query(sql, conn, params=params)


def check_connection() -> bool:
    """Used by the sidebar to show a real (not hardcoded) connection status."""
    try:
        run_query("SELECT 1")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Read-only access for the agent's run_sql tool.
#
# This uses the sema_readonly role (sql/create_readonly_role.sql), which can
# ONLY SELECT. We also bake a statement_timeout into the connection so any
# runaway query is killed automatically. autocommit=True keeps each query in
# its own transaction, so one failed query doesn't poison the next.
# ---------------------------------------------------------------------------

READONLY_TIMEOUT_MS = 5000  # kill any query running longer than 5 seconds


@st.cache_resource
def get_readonly_connection() -> "psycopg2.extensions.connection":
    conn = psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=_db_name(),
        user=os.environ.get("POSTGRES_READONLY_USER", "sema_readonly"),
        password=os.environ.get("POSTGRES_READONLY_PASSWORD", "sema_readonly_pw"),
        options=f"-c statement_timeout={READONLY_TIMEOUT_MS}",
    )
    conn.autocommit = True
    return conn


def run_sql_readonly(sql: str) -> pd.DataFrame:
    """Run already-validated SQL through the read-only connection.

    Validation/sanitization happens in agent/safety.py BEFORE this is called.
    This function is the last hop to the database.
    """
    try:
        conn = get_readonly_connection()
        return pd.read_sql_query(sql, conn)
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        get_readonly_connection.clear()
        conn = get_readonly_connection()
        return pd.read_sql_query(sql, conn)
