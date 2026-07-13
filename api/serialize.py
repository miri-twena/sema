"""
SEMA API: serialization between the existing backend and the API contract.

The backend's response dict (from wiring.get_response) carries pandas
DataFrames inside charts/table -- not JSON-serializable. Here we convert them
to {columns, rows} and map field names to the ChatResponse contract. This is
the ONE place DataFrame -> JSON happens, so the contract stays stable.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from api.models import (
    Chart,
    ChatResponse,
    DateRange,
    Evidence,
    Kpi,
    SchemaColumn,
    SchemaResponse,
    SchemaTable,
    Table,
)


def _columns(df: pd.DataFrame) -> list[str]:
    return [str(c) for c in df.columns]


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """JSON-safe rows: to_json handles dates/Decimals, then back to objects."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


def to_chat_response(resp: dict, sql_used: str | None = None) -> ChatResponse:
    """Map the backend response dict to the API ChatResponse contract."""
    kpis = [Kpi(**k) for k in resp.get("kpis", [])]

    chart: Chart | None = None
    charts = resp.get("charts") or []
    if charts:
        spec = charts[0]  # contract exposes a single chart; first wins
        df = spec.get("df")
        chart = Chart(
            kind=spec.get("kind") or "bar",  # contract requires a valid kind
            title=spec.get("title", ""),
            x=spec.get("x"),
            y=spec.get("y"),
            color=spec.get("color"),
            names=spec.get("names"),
            values=spec.get("values"),
            y_format=spec.get("y_format"),
            highlight_x=spec.get("highlight_x"),
            columns=_columns(df) if df is not None else [],
            rows=_records(df) if df is not None else [],
        )

    table: Table | None = None
    t = resp.get("table")
    if t is not None and not t.empty:
        table = Table(title=resp.get("table_title"), columns=_columns(t), rows=_records(t))

    evidence: Evidence | None = None
    raw_evidence = resp.get("evidence")
    if raw_evidence:
        date_range = raw_evidence.get("date_range")
        evidence = Evidence(
            semantic_definitions=raw_evidence.get("semantic_definitions", []),
            date_range=DateRange(**date_range) if date_range else None,
            filters_applied=raw_evidence.get("filters_applied", []),
            data_sources=raw_evidence.get("data_sources", []),
            data_freshness=raw_evidence.get("data_freshness"),
            records_used=raw_evidence.get("records_used"),
        )

    return ChatResponse(
        answer=resp.get("insight_text", ""),
        kpis=kpis,
        chart=chart,
        table=table,
        actions=list(resp.get("recommended_actions", [])),
        sql_used=resp.get("sql_used") or sql_used,
        confidence=resp.get("confidence"),
        evidence=evidence,
        status="ok",
    )


# --- schema introspection (per client) -------------------------------------
# Same queries tools._introspect_schema uses, but parameterized by client so
# the API can return any client's schema (that helper is client-agnostic).
_COLS_SQL = """
    SELECT table_name, column_name, data_type, ordinal_position
    FROM information_schema.columns
    WHERE table_schema = 'public'
    ORDER BY table_name, ordinal_position
"""
_FKS_SQL = """
    SELECT tc.table_name AS from_table, kcu.column_name AS from_column,
           ccu.table_name AS to_table, ccu.column_name AS to_column
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
        ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
    JOIN information_schema.constraint_column_usage ccu
        ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
"""


def build_schema(client_id: str, run_query) -> SchemaResponse:
    """Introspect a client's public schema into the SchemaResponse contract.

    `run_query` is injected (db.run_query) to keep this module DB-agnostic.
    """
    cols = run_query(_COLS_SQL, client_id=client_id)
    fks = run_query(_FKS_SQL, client_id=client_id)

    tables: list[SchemaTable] = []
    for table_name, group in cols.groupby("table_name", sort=True):
        tables.append(
            SchemaTable(
                name=str(table_name),
                columns=[SchemaColumn(name=r.column_name, type=r.data_type) for r in group.itertuples()],
            )
        )
    relationships = [
        {"from": f"{r.from_table}.{r.from_column}", "to": f"{r.to_table}.{r.to_column}"}
        for r in fks.itertuples()
    ]
    return SchemaResponse(client_id=client_id, tables=tables, relationships=relationships)
