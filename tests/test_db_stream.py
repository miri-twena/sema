"""
sema_core.db.stream_sql_readonly -- the named-cursor streaming path the
full-data CSV export uses (full_data_export_prompt.md item 1).

Deliberately hits the REAL docker-compose 'ecommerce' Postgres, unlike the
mocked-stream tests in tests/test_export_table.py: a named (server-side)
psycopg2 cursor behaves differently from a plain one in ways a mock can't
catch (its `.description` is None until the first fetch -- this module hit
exactly that bug once already), so this is the one place that must exercise
the real driver. Same "real DB for run_sql-adjacent code" convention as
test_safety.py/test_agent_scope_enforcement.py.
"""

from __future__ import annotations

import pytest

from sema_core.client_registry import set_active_client_override
from sema_core.db import run_sql_readonly, stream_sql_readonly

CID = "ecommerce"


@pytest.fixture(autouse=True)
def _active_client():
    set_active_client_override(CID)
    yield
    set_active_client_override(None)


def test_columns_and_rows_match_a_plain_query():
    plain = run_sql_readonly("SELECT order_id, status FROM orders ORDER BY order_id LIMIT 25")

    batches = list(stream_sql_readonly("SELECT order_id, status FROM orders ORDER BY order_id LIMIT 25"))
    columns = batches[0][0]
    rows = [r for _, batch in batches for r in batch]

    assert columns == list(plain.columns)
    assert len(rows) == len(plain)
    assert list(rows[0]) == list(plain.iloc[0])


def test_batches_respect_batch_size_and_cover_every_row():
    total = int(run_sql_readonly("SELECT COUNT(*) AS n FROM orders")["n"].iloc[0])
    assert total > 30  # sanity: the seeded demo data actually has enough rows

    batches = list(stream_sql_readonly("SELECT order_id FROM orders", batch_size=10))
    sizes = [len(rows) for _, rows in batches if rows]
    assert all(s <= 10 for s in sizes)
    assert sum(sizes) == total


def test_empty_result_yields_columns_and_no_rows():
    batches = list(stream_sql_readonly("SELECT order_id FROM orders WHERE order_id < 0"))
    all_rows = [r for _, batch in batches for r in batch]
    assert all_rows == []
    assert batches[0][0] == ["order_id"]  # columns still resolved, even with zero rows


def test_stream_does_not_leak_the_pooled_connection():
    """Draining the generator must return its connection to the pool -- a
    named cursor that leaked its connection would eventually exhaust the
    pool. Running it many times in a row is the cheapest proxy for that
    without reaching into the pool's internals."""
    for _ in range(30):
        list(stream_sql_readonly("SELECT order_id FROM orders LIMIT 5"))
