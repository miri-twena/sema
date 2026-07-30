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

import sqlglot
from sqlglot import expressions as exp

from sema_core import data_scope
from sema_core.agent.safety import SQLSafetyError, validate_and_prepare
from sema_core.agent.semantic import load_glossary, load_knowledge, load_rules, load_semantic_layer
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
            "again with corrected SQL. If the query touches a metric or "
            "domain outside the requester's data-access scope (see the "
            "governed context), you will instead get a 'policy_blocked' "
            "result -- the query does NOT run. Do not retry with different "
            "SQL in that case; call present_answer with mode='access_denied' "
            "instead (see the system prompt)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A single SELECT statement (PostgreSQL dialect).",
                },
                "metrics_used": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Name(s) of the get_semantic_layer metric(s) this query "
                        "computes or is grounded in, e.g. ['revenue']. Optional "
                        "for ad-hoc exploratory SQL, but ALWAYS include it when "
                        "the query implements a named metric -- it lets the "
                        "server check your question against the requester's "
                        "data-access scope before running anything."
                    ),
                },
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


# --- data-access-scope enforcement (sema_core.data_scope) -------------------
#
# OLS-style (metric/object-level), not RLS: which semantic-layer DOMAINS and
# metrics a question may touch, never which rows. The primary defense is
# get_semantic_layer() only ever showing the model metrics its scope allows
# (a scoped model never even sees gross_margin's SQL to imitate). run_sql is
# the BACKSTOP for a model that computes something blocked anyway via raw
# get_schema knowledge -- the LLM is untrusted, so this check is independent
# of anything the model self-reports and runs on every call regardless of
# scope-blind self-report drift.


def _sql_tables_and_columns(sql: str) -> tuple[set[str], set[str]]:
    """Real table names and column names referenced by one SQL statement
    (lowercased), excluding CTE aliases. Best-effort: unparsable SQL yields
    empty sets rather than raising -- the safety layer (safety.py) is what
    actually rejects malformed SQL; this is a policy signal on top of SQL
    that will otherwise be allowed to run."""
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except Exception:
        return set(), set()
    cte_names: set[str] = set()
    tables: set[str] = set()
    columns: set[str] = set()
    for statement in statements:
        if statement is None:
            continue
        for cte in statement.find_all(exp.CTE):
            if cte.alias:
                cte_names.add(cte.alias.lower())
        for table in statement.find_all(exp.Table):
            if table.name and table.name.lower() not in cte_names:
                tables.add(table.name.lower())
        for column in statement.find_all(exp.Column):
            if column.name:
                columns.add(column.name.lower())
    return tables, columns


@lru_cache(maxsize=None)
def _policy_index(client_id: str) -> dict:
    """Derived, per-client policy signals for the run_sql backstop --
    computed ONCE from the semantic YAML (the single source of truth), never
    hardcoded, so this stays correct as the semantic layer evolves:

    - sensitive_columns: column names referenced ONLY by `sensitive`-tagged
      metrics' own canonical SQL, never by any non-sensitive metric (e.g.
      gross_margin's use of `unit_cost`). The set DIFFERENCE against every
      non-sensitive metric's columns matters: a sensitive metric's SQL also
      references ordinary join/filter columns (order_id, status, quantity,
      unit_price...) that legitimate non-financial metrics use too -- only
      the columns unique to computing the sensitive figure are a reliable
      signal, or nearly any query touching orders/order_items would false-
      positive.
    - domain_exclusive_tables: {table: domain} for tables used by metrics of
      EXACTLY ONE domain. A table shared across domains (e.g. `customers` and
      `orders`, joined by nearly every metric) can't gate on its own -- only
      an unambiguous, single-domain table is a reliable structural signal.
    """
    metrics = load_semantic_layer(client_id)
    sensitive_cols_raw: set[str] = set()
    non_sensitive_cols: set[str] = set()
    tables_by_domain: dict[str, set[str]] = {}
    for m in metrics:
        tables, columns = _sql_tables_and_columns(m.get("sql", ""))
        if m.get("sensitive"):
            sensitive_cols_raw |= columns
        else:
            non_sensitive_cols |= columns
        tables_by_domain.setdefault(m["domain"], set()).update(tables)
    sensitive_columns = sensitive_cols_raw - non_sensitive_cols

    table_domains: dict[str, set[str]] = {}
    for domain, tables in tables_by_domain.items():
        for t in tables:
            table_domains.setdefault(t, set()).add(domain)
    domain_exclusive_tables = {
        t: next(iter(doms)) for t, doms in table_domains.items() if len(doms) == 1
    }
    return {"sensitive_columns": sensitive_columns, "domain_exclusive_tables": domain_exclusive_tables}


class AgentTools:
    """Per-question tool executor. Holds the result DataFrames for rendering."""

    def __init__(self, scope_id: str = "full") -> None:
        # Each entry: {"sql": str, "df": pd.DataFrame}. Used later to build
        # the table/chart in the final response.
        self.results: list[dict] = []
        # Failed run_sql attempts, kept SEPARATE from `results` so the model's
        # result_index bindings stay aligned with the successful queries. Used
        # only for truthful execution status in the evidence panel.
        self.failures: list[dict] = []
        # The requester's data-access scope (sema_core.data_scope) -- 'full'
        # (the default) never blocks anything, so every non-scoped caller
        # (tests, the fallback router) is unaffected.
        self.scope_id = scope_id
        # Set to the FIRST policy_blocked reason encountered this run, if
        # any. response.py's deterministic mode gate reads this to force
        # mode='access_denied' even if the model's final answer doesn't
        # cooperate -- so a blocked question can never quietly slip through
        # as a normal answer just because the model mislabeled it.
        self.access_denied: dict | None = None

    # --- the three tools ---------------------------------------------------
    def get_schema(self) -> dict:
        # Resolve the active client explicitly and pass it in, so the cache is
        # keyed correctly per tenant (never serves another client's schema).
        return _introspect_schema(active_client_id())

    def get_semantic_layer(self) -> dict:
        metrics = data_scope.allowed_metrics(load_semantic_layer(), self.scope_id)
        # Return everything the agent needs to ground its SQL. Deprecated
        # rules/knowledge are excluded -- an archived item shouldn't still
        # steer the agent, even though it's kept (not hard-deleted) on disk.
        # Metrics outside the requester's data-access scope are filtered out
        # entirely (never sent to the model) -- the primary enforcement
        # mechanism; run_sql's independent check below is the backstop.
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
                    **({"status": m["status"]} if "status" in m else {}),
                    **({"synonyms": m["synonyms"]} if m.get("synonyms") else {}),
                }
                for m in metrics
            ],
            "business_rules": [
                {"name": r["name"], "definition": r["definition"], "applies_to": r.get("applies_to", [])}
                for r in load_rules()
                if r.get("status") != "deprecated"
            ],
            # NOT filtered by date here -- this tool runs before the agent
            # knows the answer's date range. It sees every recurring event /
            # incident / note and decides relevance itself; a deterministic
            # incident-overlap caveat is added separately, after the answer,
            # in response.py (can't be reasoned away by the model).
            "knowledge": [
                {
                    "type": k["type"],
                    "name": k["name"],
                    **({"date_range": k["date_range"]} if k.get("date_range") else {}),
                    **({"recurrence": k["recurrence"]} if k.get("recurrence") else {}),
                    "description": k["description"],
                    "affects": k.get("affects", []),
                }
                for k in load_knowledge()
                if k.get("status") != "deprecated"
            ],
            "glossary": load_glossary(),
        }

    def run_sql(self, query: str, metrics_used: list[str] | None = None) -> dict:
        # Data-access-scope gate: runs BEFORE the SQL safety layer and before
        # anything touches the DB. A blocked query is never executed -- not
        # even to validate it -- so a scoped-down user's SQL never reaches
        # the database at all when it's off-limits.
        blocked = self._scope_block(query, metrics_used)
        if blocked is not None:
            if self.access_denied is None:
                self.access_denied = blocked
            return blocked

        # Layer 2 of safety: validate + auto-limit before touching the DB.
        try:
            safe_sql = validate_and_prepare(query)
        except SQLSafetyError as e:
            self.failures.append({"stage": "validation", "error": str(e)})
            return {"error": f"Rejected by safety check: {e}"}

        # Layer 1 + 3: read-only role + statement timeout.
        try:
            df = run_sql_readonly(safe_sql)
        except Exception as e:  # timeout, SQL error caught by Postgres, etc.
            self.failures.append({"stage": "execution", "error": str(e).splitlines()[0]})
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

    def _scope_block(self, query: str, metrics_used: list[str] | None) -> dict | None:
        """None if `query` is allowed under self.scope_id; otherwise a
        structured `policy_blocked` result (never executed). Two independent
        signals, either one blocks:

        1. The model's OWN declared `metrics_used` -- checked against each
           metric's domain/sensitivity. Primary signal for domains that share
           tables (e.g. `customers`/`orders` are joined by nearly every
           metric, so no table-only check can tell "list VIP customers" apart
           from "AOV by segment" -- only the metric identity can).
        2. An independent structural scan of the ACTUAL SQL -- sensitive
           columns and domain-exclusive tables, derived from the semantic
           YAML (_policy_index). This is the untrusted-LLM backstop: it fires
           regardless of what metrics_used claims (or omits), so a model that
           mislabels or skips its self-report still can't slip a blocked
           financial or marketing/customers-exclusive query through.

        Either signal blocking is enough to refuse -- deliberately
        conservative for a permissions feature (over-blocking is a UX
        annoyance; under-blocking is a real leak).
        """
        if self.scope_id == "full":
            return None  # nothing to check -- full access never blocks

        client_id = active_client_id()
        preset = data_scope.preset(self.scope_id)
        metrics_by_name = {m["name"]: m for m in load_semantic_layer(client_id)}

        for name in metrics_used or []:
            metric = metrics_by_name.get(name)
            if metric is None:
                continue
            reason = data_scope.blocked_reason(metric, self.scope_id)
            if reason:
                return self._policy_blocked(reason, metric["domain"])

        index = _policy_index(client_id)
        tables, columns = _sql_tables_and_columns(query)

        if preset.blocks_sensitive and columns & index["sensitive_columns"]:
            return self._policy_blocked(
                "This touches financial/profitability data, which isn't part of your data access.",
                "finance",
            )
        for table in tables:
            domain = index["domain_exclusive_tables"].get(table)
            if domain and not preset.domain_allowed(domain):
                domain_label = data_scope.DOMAIN_LABELS.get(domain, domain)
                return self._policy_blocked(
                    f"This touches the {domain_label} domain, which isn't part of your data access.",
                    domain,
                )
        return None

    def _policy_blocked(self, reason: str, domain: str) -> dict:
        return {
            "policy_blocked": True,
            "reason": reason,
            "domain": domain,
            "can_ask_about": data_scope.can_ask_about_summary(
                load_semantic_layer(active_client_id()), self.scope_id
            ),
        }

    # --- dispatch ----------------------------------------------------------
    def dispatch(self, name: str, tool_input: dict) -> dict:
        """Route a tool call from the model to the right method."""
        if name == "get_schema":
            return self.get_schema()
        if name == "get_semantic_layer":
            return self.get_semantic_layer()
        if name == "run_sql":
            return self.run_sql(tool_input.get("query", ""), tool_input.get("metrics_used"))
        return {"error": f"Unknown tool: {name}"}
