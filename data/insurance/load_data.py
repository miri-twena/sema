"""
Load the generated insurance CSVs (data/insurance/output/*.csv) into the
`insurance_db` PostgreSQL database.

Mirrors data/load_data.py (ecommerce), but for the auto-insurance client:
  1. Connects to insurance_db (must already exist -- see the project README /
     the create step that runs CREATE DATABASE insurance_db).
  2. Applies sql/insurance/schema.sql (drops + recreates all tables).
  3. Bulk-loads each CSV with COPY, in FK-safe order.
  4. Resets each table's id sequence.

How to run:
    python data/insurance/load_data.py
"""

from __future__ import annotations

import os

import psycopg2
from dotenv import load_dotenv

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "sql", "insurance", "schema.sql")

# FK-safe load order: a table only appears after everything it references.
TABLES_IN_LOAD_ORDER = [
    "products",
    "agents",
    "policyholders",
    "vehicles",
    "drivers",
    "policies",          # self-ref previous_policy_id is satisfied in-file (ids ascending)
    "premium_payments",
    "claims",
]

# Primary-key column per table, for resetting sequences after the bulk load.
PK_COLUMNS = {
    "products": "product_id",
    "agents": "agent_id",
    "policyholders": "policyholder_id",
    "vehicles": "vehicle_id",
    "drivers": "driver_id",
    "policies": "policy_id",
    "premium_payments": "payment_id",
    "claims": "claim_id",
}


def get_connection():
    load_dotenv()
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ.get("POSTGRES_DB_INSURANCE", "insurance_db"),
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
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence(%s, %s), "
            f"COALESCE((SELECT MAX({id_column}) FROM {table_name}), 1))",
            (table_name, id_column),
        )
    conn.commit()


def grant_readonly(conn) -> None:
    """Grant the agent's read-only role SELECT on the freshly created tables."""
    role = os.environ.get("POSTGRES_READONLY_USER", "sema_readonly")
    with conn.cursor() as cur:
        cur.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
        cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {role}")
    conn.commit()


def main() -> None:
    conn = get_connection()
    try:
        run_schema(conn)
        for table in TABLES_IN_LOAD_ORDER:
            print(f"Loading {table} ...")
            print(f"  -> {load_table(conn, table):,} rows")
        print("Resetting sequences...")
        for table, pk in PK_COLUMNS.items():
            fix_sequence(conn, table, pk)
        print("Granting read-only access for the agent...")
        grant_readonly(conn)
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
