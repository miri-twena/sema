"""
P0 item 1: the schema cache must be keyed per client_id.

The bug: _introspect_schema used @lru_cache(maxsize=1) with no client argument,
so after switching clients the agent kept getting the FIRST client's schema.
These tests fake db.run_query (no live DB) and prove the cache now returns the
right schema per client and introspects each client exactly once.
"""

from __future__ import annotations

import pandas as pd
import pytest

from sema_core.agent import tools


def _fake_run_query_factory(calls: list[str]):
    """Return a run_query stub that yields a distinct schema per client_id."""

    def fake_run_query(sql, params=None, client_id=None):
        calls.append(client_id)
        if "information_schema.columns" in sql:
            # One table named "<client_id>_table" so each client is identifiable.
            return pd.DataFrame(
                [
                    {
                        "table_name": f"{client_id}_table",
                        "column_name": "id",
                        "data_type": "integer",
                        "ordinal_position": 1,
                    }
                ]
            )
        # FK query: return an empty (but correctly-shaped) frame.
        return pd.DataFrame(
            columns=["from_table", "from_column", "to_table", "to_column"]
        )

    return fake_run_query


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    tools._introspect_schema.cache_clear()
    yield
    tools._introspect_schema.cache_clear()


def test_schema_is_keyed_per_client(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(tools, "run_query", _fake_run_query_factory(calls))

    schema_a = tools._introspect_schema("alpha")
    schema_b = tools._introspect_schema("beta")

    assert schema_a["tables"][0]["name"] == "alpha_table"
    assert schema_b["tables"][0]["name"] == "beta_table"
    # No cross-tenant bleed: alpha never sees beta's table.
    assert schema_a != schema_b


def test_each_client_introspected_once(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(tools, "run_query", _fake_run_query_factory(calls))

    tools._introspect_schema("alpha")
    tools._introspect_schema("alpha")  # served from cache
    tools._introspect_schema("beta")

    # 2 queries (cols + fks) for alpha's first call, 0 for the cached repeat,
    # 2 for beta -> alpha appears twice, beta twice; alpha not re-queried.
    assert calls.count("alpha") == 2
    assert calls.count("beta") == 2


def test_get_schema_uses_active_client(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(tools, "run_query", _fake_run_query_factory(calls))
    monkeypatch.setattr(tools, "active_client_id", lambda: "gamma")

    result = tools.AgentTools().get_schema()
    assert result["tables"][0]["name"] == "gamma_table"
