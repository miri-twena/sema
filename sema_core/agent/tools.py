"""
SEMA agent: tools.

These are the only actions the agent can take. In LLM terms each tool has a
JSON schema (its "menu entry") that we send to the model; the model then
*requests* a call, we execute it here, and we feed the result back.

  get_schema()          -> tables, columns, relationships (facts about the DB)
  get_semantic_layer()  -> the business metric definitions (the grounding)
  run_sql(query)        -> runs a SELECT through the safety layer

Design choices:
- run_sql NEVER raises on a bad query; it returns {"error": "..."} so the
  agent can read the problem and rewrite its SQL on the next turn. That
  self-correction loop is the whole point of an agent.
- We keep the full result DataFrames in `self.results` so the final response
  builder (step 5) can turn them into tables/charts -- the model only sees a
  small preview, to save tokens.

No dependency on the Claude API key.
"""

from __future__ import annotations

import json
from functools import lru_cache

from sema_core.agent.safety import SQLSafetyError, validate_and_prepare
from sema_core.agent.semantic import load_semantic_layer
from sema_core.client_registry import active_client_id
from sema_core.db import run_query, run_sql_readonly

# How many rows of a query result we show the model (the full result is kept
# separately for rendering). Keeps token cost bounded.
PREVIEW_ROWS = 50


# --- JSON schemas: the "menu" we send to the model -------------------------
TOOL_SCHEMAS = [
    {
        "name": "get_schema",
        "description": (
            "Return the database schema: every table, its columns and types, "
            "and the foreign-key relationships between tables. Call this when "
            "you need a column or join that the semantic layer did not give you."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_semantic_layer",
        "description": (
            "Return the business metric definitions (Revenue, AOV, VIP "
            "Customers, Active Customers, Conversion Rate, Churn Risk, "
            "Campaign ROI, Returning Customers, Revenue by Category). Each "
            "includes a description, the canonical SQL to compute it, its "
            "dimensions, and example questions. ALWAYS consult this first and "
            "reuse these definitions rather than inventing your own."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_sql",
        "description": (
            "Execute a single read-only SELECT query against the PostgreSQL "
            "database and return the columns and a preview of the rows. Only "
            "SELECT is allowed; a LIMIT is added automatically. If the query "
            "is invalid you will get an 'error' field back -- read it and try "
            "again with corrected SQL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A single SELECT statement (PostgreSQL dialect).",
                }
            },
            "required": ["query"],
        },
    },
]


# Cached PER client_id (maxsize=None = unbounded, one entry per client). The
# earlier @lru_cache(maxsize=1) had no client argument, so after switching
# clients the agent kept getting the FIRST client's schema -- a tenant-safety
# bug. Keying the cache on client_id fixes it: each client caches its own.
@lru_cache(maxsize=None)
def _introspect_schema(client_id: str) -> dict:
    """Read tables/columns/relationships from a client's DB catalog (cached)."""
    cols = run_query(
        """
        SELECT table_name, column_name, data_type, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
        """,
        client_id=client_id,
    )
    fks = run_query(
        """
        SELECT
            tc.table_name      AS from_table,
            kcu.column_name    AS from_column,
            ccu.table_name     AS to_table,
            ccu.column_name    AS to_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON kcu.constraint_name = tc.constraint_name
           AND kcu.table_schema = tc.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
           AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
        """,
        client_id=client_id,
    )

    tables: list[dict] = []
    for table_name, group in cols.groupby("table_name", sort=True):
        tables.append(
            {
                "name": table_name,
                "columns": [
                    {"name": r.column_name, "type": r.data_type}
                    for r in group.itertuples()
                ],
            }
        )

    relationships = [
        {
            "from": f"{r.from_table}.{r.from_column}",
            "to": f"{r.to_table}.{r.to_column}",
        }
        for r in fks.itertuples()
    ]

    return {"tables": tables, "relationships": relationships}


class AgentTools:
    """Per-question tool executor. Holds the result DataFrames for rendering."""

    def __init__(self) -> None:
        # Each entry: {"sql": str, "df": pd.DataFrame}. Used later to build
        # the table/chart in the final response.
        self.results: list[dict] = []

    # --- the three tools ---------------------------------------------------
    def get_schema(self) -> dict:
        # Resolve the active client explicitly and pass it in, so the cache is
        # keyed correctly per tenant (never serves another client's schema).
        return _introspect_schema(active_client_id())

    def get_semantic_layer(self) -> dict:
        metrics = load_semantic_layer()
        # Return everything the agent needs to ground its SQL.
        return {
            "metrics": [
                {
                    "name": m["name"],
                    "label": m["label"],
                    "description": m["description"],
                    "grain": m["grain"],
                    "sql": m["sql"],
                    "dimensions": m["dimensions"],
                    "examples": m["examples"],
                    **(
                        {"alternative_definition": m["alternative_definition"]}
                        if "alternative_definition" in m
                        else {}
                    ),
                }
                for m in metrics
            ]
        }

    def run_sql(self, query: str) -> dict:
        # Layer 2 of safety: validate + auto-limit before touching the DB.
        try:
            safe_sql = validate_and_prepare(query)
        except SQLSafetyError as e:
            return {"error": f"Rejected by safety check: {e}"}

        # Layer 1 + 3: read-only role + statement timeout.
        try:
            df = run_sql_readonly(safe_sql)
        except Exception as e:  # timeout, SQL error caught by Postgres, etc.
            return {"error": f"Query failed: {str(e).splitlines()[0]}"}

        self.results.append({"sql": safe_sql, "df": df})

        preview = df.head(PREVIEW_ROWS)
        # to_json handles dates/decimals safely, then back to Python objects.
        preview_rows = json.loads(preview.to_json(orient="records", date_format="iso"))

        return {
            "sql_executed": safe_sql,
            "columns": list(df.columns),
            "row_count": int(len(df)),
            "preview_rows": preview_rows,
            "preview_truncated": bool(len(df) > PREVIEW_ROWS),
        }

    # --- dispatch ----------------------------------------------------------
    def dispatch(self, name: str, tool_input: dict) -> dict:
        """Route a tool call from the model to the right method."""
        if name == "get_schema":
            return self.get_schema()
        if name == "get_semantic_layer":
            return self.get_semantic_layer()
        if name == "run_sql":
            return self.run_sql(tool_input.get("query", ""))
        return {"error": f"Unknown tool: {name}"}
