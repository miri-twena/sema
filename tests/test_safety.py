"""
Item 10/11: table-driven tests for the SQL safety layer.

Covers: allowed shapes (SELECT / WITH / UNION), auto-LIMIT added + preserved +
capped, and rejected queries (writes, DDL, multi-statement, empty, unparsable,
system catalogs). No DB needed -- this layer is pure parsing.
"""

from __future__ import annotations

import pytest

from agent.safety import DEFAULT_ROW_LIMIT, SQLSafetyError, is_safe, validate_and_prepare


# --- allowed ----------------------------------------------------------------
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM orders",
        "SELECT customer_id, SUM(total) FROM orders GROUP BY customer_id",
        "WITH t AS (SELECT 1 AS x) SELECT * FROM t",
        "SELECT 1 AS a UNION SELECT 2",
    ],
)
def test_allowed_queries_pass(sql):
    prepared = validate_and_prepare(sql)
    assert "LIMIT" in prepared.upper()  # auto-limit always present
    assert is_safe(sql)


def test_auto_limit_added_when_missing():
    prepared = validate_and_prepare("SELECT * FROM orders")
    assert f"LIMIT {DEFAULT_ROW_LIMIT}" in prepared


def test_existing_small_limit_preserved():
    prepared = validate_and_prepare("SELECT * FROM orders LIMIT 10")
    assert "LIMIT 10" in prepared


def test_oversized_limit_is_capped():
    # A model-supplied huge LIMIT must not bypass the row cap.
    prepared = validate_and_prepare(f"SELECT * FROM orders LIMIT {DEFAULT_ROW_LIMIT * 100}")
    assert f"LIMIT {DEFAULT_ROW_LIMIT}" in prepared
    assert str(DEFAULT_ROW_LIMIT * 100) not in prepared


# --- rejected ---------------------------------------------------------------
@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO orders VALUES (1)",
        "UPDATE orders SET total = 0",
        "DELETE FROM orders",
        "DROP TABLE orders",
        "TRUNCATE orders",
        "CREATE TABLE evil (id int)",
        "SELECT 1; DROP TABLE orders",  # multi-statement
        "",
        "   ",
        "SELECT FROM WHERE",  # unparsable
    ],
)
def test_rejected_queries_raise(sql):
    with pytest.raises(SQLSafetyError):
        validate_and_prepare(sql)
    assert not is_safe(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM pg_catalog.pg_tables",
        "SELECT * FROM information_schema.columns",
        "SELECT * FROM pg_stat_activity",  # unqualified pg_* via search_path
        "SELECT o.* FROM orders o JOIN pg_catalog.pg_class c ON true",
    ],
)
def test_system_catalogs_rejected(sql):
    # Schema questions must go through the get_schema tool, not raw SQL.
    with pytest.raises(SQLSafetyError):
        validate_and_prepare(sql)
