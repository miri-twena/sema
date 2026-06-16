"""
Load the generated CSV files (data/output/*.csv) into PostgreSQL.

What this script does:
  1. Connects to PostgreSQL using settings from .env
  2. Runs sql/schema.sql to (re)create all tables (this DROPs and recreates
     them, so it's safe to re-run after regenerating data)
  3. Loads each CSV into its matching table using PostgreSQL's COPY command
     (COPY is the fast, bulk-loading equivalent of INSERT -- much quicker
     than inserting row by row)
  4. Updates each table's auto-increment sequence so future inserts (if
     any) continue from the right number

How to run:
    python data/load_data.py

Requires:
  - PostgreSQL running and reachable (see docker-compose.yml)
  - .env file with connection settings (copy .env.example -> .env)
  - data/output/*.csv already generated (run data/generate_data.py first)
"""

from __future__ import annotations

import os

import psycopg2
from dotenv import load_dotenv

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "sql", "schema.sql")

# Tables in an order that respects foreign keys: a table only appears after
# every table it references.
TABLES_IN_LOAD_ORDER = [
    "products",
    "marketing_campaigns",
    "customers",
    "orders",
    "order_items",
    "website_sessions",
]


def get_connection():
    load_dotenv()
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ.get("POSTGRES_DB", "sema_db"),
        user=os.environ.get("POSTGRES_USER", "sema_user"),
        password=os.environ.get("POSTGRES_PASSWORD", "sema_password"),
    )


def run_schema(conn) -> None:
    print(f"Applying schema from {SCHEMA_PATH} ...")
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()


def load_table(conn, table_name: str) -> int:
    csv_path = os.path.join(OUTPUT_DIR, f"{table_name}.csv")
    with open(csv_path, "r", encoding="utf-8") as f:
        with conn.cursor() as cur:
            cur.copy_expert(
                f"COPY {table_name} FROM STDIN WITH (FORMAT csv, HEADER true)",
                f,
            )
            row_count = cur.rowcount
    conn.commit()
    return row_count


def fix_sequence(conn, table_name: str, id_column: str) -> None:
    """
    The CSVs include explicit primary key values (1, 2, 3, ...), so
    PostgreSQL's auto-increment sequence for that column doesn't move.
    This resets the sequence to MAX(id) so any future INSERTs continue
    from the right number instead of colliding with existing rows.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence(%s, %s), "
            f"COALESCE((SELECT MAX({id_column}) FROM {table_name}), 1))",
            (table_name, id_column),
        )
    conn.commit()


def main() -> None:
    conn = get_connection()
    try:
        run_schema(conn)

        for table in TABLES_IN_LOAD_ORDER:
            print(f"Loading {table} ...")
            row_count = load_table(conn, table)
            print(f"  -> {row_count:,} rows")

        print("Resetting sequences...")
        fix_sequence(conn, "products", "product_id")
        fix_sequence(conn, "marketing_campaigns", "campaign_id")
        fix_sequence(conn, "customers", "customer_id")
        fix_sequence(conn, "orders", "order_id")
        fix_sequence(conn, "order_items", "order_item_id")
        fix_sequence(conn, "website_sessions", "session_id")

        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
