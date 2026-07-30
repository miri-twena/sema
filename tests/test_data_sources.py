"""
Tests for the data-sources registry (client panel spec §4, view-only slice).

conftest's `_isolated_data_source_health` autouse fixture keeps every test off
a real Postgres connection by default (status "healthy", unknown data age);
tests here that need the error path re-patch `check_connection` explicitly.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.main as main
from sema_core import data_sources

CID = "ecommerce"


# --- entities + dependent metrics --------------------------------------------

def test_ecommerce_entities_cover_every_table_metrics_touch():
    entities = data_sources.entities_for_client("ecommerce")
    # Every core table (see data/load_data.py's TABLES_IN_LOAD_ORDER), found
    # either via a metric's main query or a dimension's requires_join.
    assert set(entities) >= {
        "orders", "order_items", "customers", "products", "marketing_campaigns", "website_sessions",
    }


def test_ecommerce_dependent_metrics_include_the_real_metric_names():
    dep = data_sources.dependent_metrics_by_entity("ecommerce")
    assert "revenue" in dep["orders"]
    # revenue_by_category joins order_items/products via a dimension's
    # requires_join -- not the metric's own base query.
    assert "revenue_by_category" in dep["order_items"]
    assert "revenue_by_category" in dep["products"]


def test_insurance_entities_include_dimension_only_joins():
    """policyholders/agents/vehicles/drivers never appear in a metric's base
    `sql`, only in a dimension's requires_join -- proves that path is walked,
    not just the main query."""
    dep = data_sources.dependent_metrics_by_entity("insurance")
    assert "policies_in_force" in dep["policyholders"]
    assert "policies_in_force" in dep["agents"]
    assert "claims_frequency" in dep["drivers"]
    assert "claims_frequency" in dep["vehicles"]
    assert "policies" in dep and "claims" in dep


def test_source_for_entity_defaults_to_the_client_single_source():
    assert data_sources.source_for_entity("orders", "ecommerce") == "postgres_main"
    assert data_sources.source_for_entity("policies", "insurance") == "postgres_main"


def test_source_type_for_entity_is_the_connector_type_not_the_instance_id():
    """spec §4.4: every semantic entity gets a `source` field valued
    postgres/priority/salesforce -- the connector TYPE, distinct from the
    source instance id ("postgres_main") used elsewhere."""
    assert data_sources.source_type_for_entity("orders", "ecommerce") == "postgres"
    assert data_sources.source_type_for_entity("policies", "insurance") == "postgres"


def test_client_with_no_configured_sources_gets_an_implicit_postgres_default(monkeypatch):
    bare_client = {"id": "bare", "label": "Bare", "semantic_dir": "sql/semantic"}
    monkeypatch.setattr(data_sources, "get_client_by_id", lambda cid: bare_client)
    sources = data_sources.client_sources("bare")
    assert len(sources) == 1
    assert sources[0]["type"] == "postgres"
    assert sources[0]["id"] == "postgres_main"


# --- health --------------------------------------------------------------

def test_source_health_reachable_is_healthy_with_a_duration():
    source = data_sources.client_sources(CID)[0]
    health = data_sources.source_health(source, CID)
    assert health["status"] == "healthy"
    assert health["last_sync_at"] is not None
    assert health["sync_duration_ms"] is not None


def test_source_health_unreachable_is_error_and_skips_the_age_query(monkeypatch):
    source = data_sources.client_sources(CID)[0]
    monkeypatch.setattr(data_sources.db, "check_connection", lambda **kw: False)

    def boom(*a, **kw):
        raise AssertionError("must not query for data age when unreachable")

    monkeypatch.setattr(data_sources.db, "run_query", boom)
    health = data_sources.source_health(source, CID)
    assert health["status"] == "error"
    assert health["last_sync_at"] is None
    assert health["data_age_days"] is None


def test_source_health_computes_real_data_age(monkeypatch):
    import datetime as dt

    source = data_sources.client_sources(CID)[0]
    ten_days_ago = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)
    monkeypatch.setattr(data_sources.db, "check_connection", lambda **kw: True)
    monkeypatch.setattr(
        data_sources.db, "run_query", lambda sql, client_id=None: pd.DataFrame({"max_date": [ten_days_ago]})
    )
    health = data_sources.source_health(source, CID)
    assert health["status"] == "healthy"
    assert 9.9 < health["data_age_days"] < 10.1


def test_unimplemented_connector_type_reports_paused():
    fake_source = {"id": "priority_main", "type": "priority", "display_name": "Priority ERP"}
    health = data_sources.source_health(fake_source, CID)
    assert health["status"] == "paused"
    assert health["last_sync_at"] is None


# --- full payload ------------------------------------------------------------

def test_get_data_sources_payload_shape():
    cards = data_sources.get_data_sources(CID)
    assert len(cards) == 1
    card = cards[0]
    assert card["id"] == "postgres_main"
    assert card["status"] == "healthy"
    names = {e["name"] for e in card["entities"]}
    assert "orders" in names
    orders_entity = next(e for e in card["entities"] if e["name"] == "orders")
    assert "revenue" in orders_entity["dependent_metrics"]


# --- evidence-panel caveat ----------------------------------------------------

def test_stale_source_caveat_empty_when_healthy():
    assert data_sources.stale_source_caveat({"orders"}, CID) == []


def test_stale_source_caveat_empty_when_no_entities_touched():
    assert data_sources.stale_source_caveat(set(), CID) == []


def test_stale_source_caveat_fires_when_source_errors(monkeypatch):
    monkeypatch.setattr(data_sources.db, "check_connection", lambda **kw: False)
    caveats = data_sources.stale_source_caveat({"orders"}, CID)
    assert len(caveats) == 1
    assert "PostgreSQL" in caveats[0]
    # Unreachable-now means source_health never ran the age query (see
    # test_source_health_unreachable_is_error_and_skips_the_age_query) -- the
    # caveat falls back to "currently unreachable" rather than a fabricated
    # day count.
    assert "unreachable" in caveats[0]


def test_evidence_panel_surfaces_the_caveat_end_to_end(monkeypatch):
    """The same mechanism as the incident-overlap caveat (response._knowledge_
    caveats): a real data-source failure becomes a server-computed assumption
    the model can't reason away by omission."""
    from sema_core.agent.response import build_response

    monkeypatch.setattr(data_sources.db, "check_connection", lambda **kw: False)

    class FakeTools:
        results = [{"sql": "SELECT 1 FROM orders", "df": pd.DataFrame({"x": [1]})}]
        failures: list = []

    resp = build_response(
        {"mode": "answer", "insight_text": "x", "recommended_actions": []}, FakeTools()
    )
    assumptions = resp["evidence"]["assumptions"]
    assert any("PostgreSQL" in a for a in assumptions)


# --- API routes ---------------------------------------------------------------

def _client_as_miri(monkeypatch) -> TestClient:
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    return TestClient(main.app)


def test_admin_data_sources_endpoint_returns_the_status_card(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.get("/api/admin/data-sources")
    assert resp.status_code == 200
    cards = resp.json()
    assert len(cards) == 1
    assert cards[0]["id"] == "postgres_main"
    assert cards[0]["status"] == "healthy"
    assert any(e["name"] == "orders" for e in cards[0]["entities"])


def test_admin_data_sources_requires_admin(monkeypatch):
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity",
        lambda: {"client_id": CID, "email": "avi.peretz@ecommerce-demo.com"},  # a viewer
    )
    client = TestClient(main.app)
    assert client.get("/api/admin/data-sources").status_code == 403


def test_report_problem_creates_an_audit_event(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post("/api/admin/data-sources/postgres_main/report-problem")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reported"] is True
    assert body["source_id"] == "postgres_main"

    events = main.audit_store.list_events(CID, category="data_source")["events"]
    assert len(events) == 1
    assert events[0]["action"] == "data_source.problem_reported"
    assert events[0]["target_id"] == "postgres_main"


def test_report_problem_unknown_source_is_404(monkeypatch):
    client = _client_as_miri(monkeypatch)
    resp = client.post("/api/admin/data-sources/not-a-real-source/report-problem")
    assert resp.status_code == 404


# --- schema introspection: every table carries a source ----------------------

def test_build_schema_tags_every_table_with_its_source():
    """Unit-tests api.serialize.build_schema with a fake run_query (same
    injection pattern the function itself uses) -- no real database, mirrors
    how the rest of the suite avoids a live Postgres dependency."""
    from api.serialize import build_schema

    cols = pd.DataFrame(
        [
            {"table_name": "orders", "column_name": "id", "data_type": "integer", "ordinal_position": 1},
            {"table_name": "orders", "column_name": "order_date", "data_type": "date", "ordinal_position": 2},
            {"table_name": "customers", "column_name": "id", "data_type": "integer", "ordinal_position": 1},
        ]
    )
    fks = pd.DataFrame(columns=["from_table", "from_column", "to_table", "to_column"])

    def fake_run_query(sql, client_id=None):
        return cols if "information_schema.columns" in sql else fks

    result = build_schema(CID, fake_run_query)
    by_name = {t.name: t for t in result.tables}
    assert by_name["orders"].source == "postgres"
    assert by_name["customers"].source == "postgres"
