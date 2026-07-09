"""
SEMA agent: SQL safety.

The middle safety net (the database read-only role is the strongest one,
and the statement timeout is the third). Here we parse the agent's SQL with
sqlglot -- a real SQL parser, not regex -- and:

  1. Reject anything that isn't a single read-only SELECT (or WITH...SELECT,
     or a UNION of SELECTs).
  2. Reject multiple statements (e.g. "SELECT ...; DROP TABLE ...").
  3. Auto-add a LIMIT if the query doesn't have one, so a query can never
     return millions of rows.

Why a parser instead of keyword matching: keyword blacklists are easy to
fool (comments, casing, sneaky strings). Parsing the query into a syntax
tree and checking the *root statement type* is far more reliable.

This module has NO dependency on the Claude API key.
"""

from __future__ import annotations

import sqlglot
from sqlglot import expressions as exp

from sema_core.settings import settings

DEFAULT_ROW_LIMIT = settings.row_limit  # SEMA_ROW_LIMIT, default 1000

# Root expression types we consider safe (all read-only).
_ALLOWED_ROOTS = (exp.Select, exp.Union)

# System catalogs are off-limits for agent SQL: schema questions must go
# through the get_schema tool, and catalog probing is a recon vector.
_BLOCKED_SCHEMAS = {"pg_catalog", "information_schema"}


class SQLSafetyError(Exception):
    """Raised when a query is rejected by the safety layer."""


def validate_and_prepare(sql: str, max_rows: int = DEFAULT_ROW_LIMIT) -> str:
    """Validate `sql` and return a safe, LIMIT-capped version.

    Raises SQLSafetyError if the query is not a single read-only SELECT.
    """
    if not sql or not sql.strip():
        raise SQLSafetyError("Empty query.")

    # Parse into a list of statements (postgres dialect). Invalid SQL raises.
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except Exception as e:  # sqlglot.errors.ParseError and friends
        raise SQLSafetyError(f"Could not parse SQL: {e}") from e

    # Exactly one statement allowed (blocks "SELECT ...; DELETE ...").
    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise SQLSafetyError("Only a single SQL statement is allowed.")

    statement = statements[0]

    # The root must be a SELECT or UNION. This is what blocks INSERT, UPDATE,
    # DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, etc. -- they parse to
    # other expression types and are rejected here.
    if not isinstance(statement, _ALLOWED_ROOTS):
        kind = type(statement).__name__.upper()
        raise SQLSafetyError(f"Only SELECT queries are allowed (got {kind}).")

    # Block system-catalog access (schema comes from the get_schema tool).
    # `pg_stat_activity` etc. resolve via the search_path without a schema
    # prefix, so unqualified pg_* names are rejected too.
    for table in statement.find_all(exp.Table):
        schema_name = (table.db or "").lower()
        if schema_name in _BLOCKED_SCHEMAS or (
            not schema_name and table.name.lower().startswith("pg_")
        ):
            raise SQLSafetyError(
                "Queries against system catalogs are not allowed; "
                "use the get_schema tool instead."
            )

    # Cap result size: add a LIMIT if missing, and REPLACE any model-supplied
    # LIMIT larger than max_rows (a huge LIMIT must not bypass the cap).
    limit_expr = statement.args.get("limit")
    current_limit: int | None = None
    if limit_expr is not None:
        try:
            current_limit = int(limit_expr.expression.name)
        except (AttributeError, TypeError, ValueError):
            current_limit = None  # non-literal LIMIT (e.g. expression): re-cap
    if current_limit is None or current_limit > max_rows:
        statement = statement.limit(max_rows)

    return statement.sql(dialect="postgres")


def is_safe(sql: str) -> bool:
    """Convenience boolean check (does not return the prepared SQL)."""
    try:
        validate_and_prepare(sql)
        return True
    except SQLSafetyError:
        return False
