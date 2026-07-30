"""
SEMA: CSV/Excel upload -> a real queryable table (data_sources_add_prompt.md
Path C, item 8). Parses with pandas (the project's existing stack, plus
openpyxl for .xlsx -- see requirements.txt), infers a SQL type per column,
and lands the data in a dedicated `uploads` schema in the CLIENT'S OWN
analytics Postgres -- the same database the agent already queries, so an
uploaded table becomes available to the semantic model like any other (the
Semantic model screen owns mapping it in, out of scope here).

Every identifier (table name, column names) is built with psycopg2.sql,
never raw string interpolation -- an uploaded file's column headers are
untrusted input and must never be concatenated directly into SQL.
"""

from __future__ import annotations

import io
import re
import uuid

import pandas as pd
from psycopg2 import sql

from sema_core import db

UPLOAD_SCHEMA = "uploads"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = frozenset({".csv", ".xlsx"})


class FileUploadError(Exception):
    """User-facing (already-safe-to-show) error: bad extension, too large,
    unparseable, or empty."""


def _sanitize_identifier(raw: str, fallback: str) -> str:
    """A safe, lowercase snake_case SQL identifier from arbitrary (possibly
    non-Latin, possibly empty) input -- a filename or a column header. Never
    used to build SQL directly (psycopg2.sql.Identifier still quotes it),
    this just keeps the generated names readable and collision-resistant."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", raw.strip()).strip("_").lower()
    if not cleaned or not re.search(r"[a-z]", cleaned):
        return fallback
    if cleaned[0].isdigit():
        cleaned = f"c_{cleaned}"
    return cleaned[:63]  # Postgres identifier length limit


def table_name_for_filename(filename: str) -> str:
    """A unique-enough table name derived from the upload's filename, so two
    uploads named "orders.csv" don't collide -- a short random suffix, not a
    timestamp (keeps it stable-looking without needing Date.now-style
    concerns)."""
    stem = filename.rsplit(".", 1)[0]
    base = _sanitize_identifier(stem, "upload")
    return f"{base}_{uuid.uuid4().hex[:8]}"


def _infer_sql_type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(series):
        return "BIGINT"
    if pd.api.types.is_float_dtype(series):
        return "DOUBLE PRECISION"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "TIMESTAMP"
    return "TEXT"


def parse_file(filename: str, data: bytes) -> pd.DataFrame:
    """CSV or .xlsx bytes -> a DataFrame, with pandas' own type inference
    (its dtype-sniffing is exactly what _infer_sql_type reads from below)."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise FileUploadError("Only .csv and .xlsx files are supported.")
    try:
        if ext == ".csv":
            df = pd.read_csv(io.BytesIO(data))
        else:
            df = pd.read_excel(io.BytesIO(data), engine="openpyxl")
    except Exception as e:
        raise FileUploadError(f"Couldn't read the file: {e}") from None
    if df.empty or len(df.columns) == 0:
        raise FileUploadError("The file has no rows or columns to import.")
    return df


def column_plan(df: pd.DataFrame) -> list[dict]:
    """{"source_name", "column_name", "sql_type"} per column -- the preview
    the wizard shows before committing, and the exact plan create_table_from_
    dataframe follows."""
    plan = []
    seen: set[str] = set()
    for i, col in enumerate(df.columns):
        name = _sanitize_identifier(str(col), f"col_{i}")
        # A collision (e.g. two headers that sanitize to the same name)
        # gets a numeric suffix rather than silently overwriting a column.
        candidate = name
        n = 2
        while candidate in seen:
            candidate = f"{name}_{n}"
            n += 1
        seen.add(candidate)
        plan.append({"source_name": str(col), "column_name": candidate, "sql_type": _infer_sql_type(df[col])})
    return plan


def create_table_from_dataframe(client_id: str, table_name: str, df: pd.DataFrame) -> list[dict]:
    """Creates (or replaces) `uploads.<table_name>` in the client's own
    analytics DB and bulk-loads every row. Returns the column plan used."""
    plan = column_plan(df)
    schema_ident = sql.Identifier(UPLOAD_SCHEMA)
    table_ident = sql.Identifier(UPLOAD_SCHEMA, table_name)

    db.run_write(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(schema_ident), client_id=client_id)
    db.run_write(sql.SQL("DROP TABLE IF EXISTS {}").format(table_ident), client_id=client_id)

    columns_sql = sql.SQL(", ").join(
        sql.SQL("{} {}").format(sql.Identifier(c["column_name"]), sql.SQL(c["sql_type"])) for c in plan
    )
    create_stmt = sql.SQL("CREATE TABLE {} ({})").format(table_ident, columns_sql)
    db.run_write(create_stmt, client_id=client_id)

    if len(df) > 0:
        insert_stmt = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            table_ident,
            sql.SQL(", ").join(sql.Identifier(c["column_name"]) for c in plan),
            sql.SQL(", ").join(sql.Placeholder() for _ in plan),
        )
        # NaN/NaT -> None so Postgres gets a real NULL, not the literal string "nan".
        rows = [tuple(None if pd.isna(v) else v for v in row) for row in df.itertuples(index=False, name=None)]
        db.run_write_many(insert_stmt, rows, client_id=client_id)

    return plan


def drop_upload_table(client_id: str, table_name: str) -> None:
    table_ident = sql.Identifier(UPLOAD_SCHEMA, table_name)
    db.run_write(sql.SQL("DROP TABLE IF EXISTS {}").format(table_ident), client_id=client_id)
