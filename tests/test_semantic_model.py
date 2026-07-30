"""
Tests for the semantic-model admin feature (Draft -> Validate -> Publish).

Three layers, mirroring test_org_users.py:
  - loader backward-compat (sema_core.agent.semantic)
  - store-level guards (sema_core.semantic_store, via a local `store` fixture)
  - route-level (inline TestClient + monkeypatched identity)

conftest's autouse fixtures isolate the SQLite drafts/versions store from the
real var/sema_state.db. That does NOT cover the semantic YAML files
themselves (sql/semantic/*.yaml) -- this file's own autouse fixture
(`_isolated_semantic_dir`) copies them into a temp dir and redirects every
module-level `semantic_dir` binding there, so nothing here ever touches the
real files on disk.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

import api.main as main
import sema_core.agent.semantic as semantic
import sema_core.semantic_editor as semantic_editor
from sema_core.client_registry import PROJECT_ROOT
from sema_core.semantic_store import (
    SemanticDraftNotFoundError,
    SemanticStore,
    SemanticVersionNotFoundError,
)
from sema_core.semantic_validate import validate_item

CID = "ecommerce"


@pytest.fixture(autouse=True)
def _isolated_semantic_dir(tmp_path, monkeypatch):
    """Copy the real ecommerce semantic YAML files into a temp dir and
    redirect every module that imported `semantic_dir` by reference there --
    Publish/Restore in these tests must never touch sql/semantic/*.yaml."""
    fake_dir = tmp_path / "semantic"
    shutil.copytree(PROJECT_ROOT / "sql" / "semantic", fake_dir)

    def fake_semantic_dir(client_id: str | None = None) -> Path:
        return fake_dir

    monkeypatch.setattr(semantic, "semantic_dir", fake_semantic_dir)
    monkeypatch.setattr(semantic_editor, "semantic_dir", fake_semantic_dir)
    monkeypatch.setattr(main, "semantic_dir", fake_semantic_dir)
    return fake_dir


@pytest.fixture
def store(tmp_path) -> SemanticStore:
    return SemanticStore(tmp_path / "semantic_store.db")


def _as_admin(monkeypatch):
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    main.org_user_store.seed_demo_users(CID)
    return TestClient(main.app)


# --- loader backward-compat -------------------------------------------------

def test_existing_metrics_still_load_unchanged(_isolated_semantic_dir):
    metrics = semantic.load_semantic_layer(CID)
    assert len(metrics) == 10
    assert {m["name"] for m in metrics} >= {"aov", "revenue", "vip_customers"}


def test_reserved_files_are_not_treated_as_metrics(_isolated_semantic_dir):
    """A client with no rules/knowledge/glossary files (every client before
    this feature shipped) must keep loading exactly as before. The real
    ecommerce semantic dir now ships these files with real content, so this
    test removes them from its isolated copy to exercise the true
    no-reserved-files case rather than relying on production having none."""
    for reserved in ("rules.yaml", "knowledge.yaml", "glossary.yaml"):
        (_isolated_semantic_dir / reserved).unlink()
    assert semantic.load_rules(CID) == []
    assert semantic.load_knowledge(CID) == []
    assert semantic.load_glossary(CID) == []
    # And once one of those files DOES exist, it's excluded from the metrics glob.
    (_isolated_semantic_dir / "rules.yaml").write_text(
        yaml.dump([{"name": "r1", "definition": "x", "status": "certified"}]), encoding="utf-8"
    )
    metrics = semantic.load_semantic_layer(CID)
    assert len(metrics) == 10  # unchanged -- rules.yaml wasn't parsed as a metric
    assert [r["name"] for r in semantic.load_rules(CID)] == ["r1"]


# --- store: drafts -----------------------------------------------------------

def test_save_draft_resets_validated_on_every_edit(store):
    d = store.save_draft(CID, "metric", "aov", {"description": "x", "sql": "SELECT 1"})
    assert d["validated"] is False
    store.mark_validated(CID, "metric", "aov", True)
    assert store.get_draft(CID, "metric", "aov")["validated"] is True
    d2 = store.save_draft(CID, "metric", "aov", {"description": "y", "sql": "SELECT 2"})
    assert d2["validated"] is False  # editing again invalidates the old pass


def test_discard_create_draft_removes_it(store):
    store.save_draft(CID, "rule", "new_rule", {"definition": "x"}, action="create")
    store.discard_draft(CID, "rule", "new_rule")
    assert store.get_draft(CID, "rule", "new_rule") is None


def test_discard_missing_draft_raises(store):
    with pytest.raises(SemanticDraftNotFoundError):
        store.discard_draft(CID, "rule", "nope")


def test_versions_seed_baseline_then_increment(store):
    assert store.latest_version(CID) is None
    v1 = store.ensure_baseline(CID, {"aov.yaml": "original"})
    assert v1["version"] == 1
    assert store.ensure_baseline(CID, {"aov.yaml": "ignored, baseline already exists"}) == v1
    v2 = store.record_version(CID, {"aov.yaml": "edited"}, ["metric:aov"], "miri")
    assert v2["version"] == 2
    assert store.get_version(CID, v2["id"])["snapshot"] == {"aov.yaml": "edited"}


def test_get_version_wrong_client_is_not_found(store):
    v1 = store.ensure_baseline(CID, {"aov.yaml": "x"})
    with pytest.raises(SemanticVersionNotFoundError):
        store.get_version("other", v1["id"])


# --- validate: SQL dry run ---------------------------------------------------

def test_validate_good_metric_sql_returns_a_real_value(_isolated_semantic_dir):
    result = validate_item(
        CID, "metric", "aov",
        {"sql": "SELECT ROUND(AVG(total_amount), 2) AS aov FROM orders WHERE status = 'completed'"},
    )
    assert result["ok"] is True
    assert isinstance(result["value"], (int, float))
    assert result["row_count"] == 1
    assert result["duration_ms"] is not None


def test_validate_syntax_error_returns_ok_false(_isolated_semantic_dir):
    result = validate_item(CID, "metric", "aov", {"sql": "SELEKT this is not sql"})
    assert result["ok"] is False
    assert "error" in result and result["error"]


def test_validate_rejects_multi_statement_injection(_isolated_semantic_dir):
    """A multi-statement injection must be rejected by the safety layer
    BEFORE the date-scoping step ever sees it (see semantic_validate.py's
    safety-ordering note) -- not silently truncated and half-run."""
    result = validate_item(CID, "metric", "aov", {"sql": "SELECT 1; DROP TABLE orders"})
    assert result["ok"] is False
    assert "single sql statement" in result["error"].lower()


def test_validate_rejects_non_select(_isolated_semantic_dir):
    result = validate_item(CID, "metric", "aov", {"sql": "DELETE FROM orders"})
    assert result["ok"] is False


def test_validate_knowledge_schema_only(_isolated_semantic_dir):
    ok = validate_item(
        CID, "knowledge", "black_friday",
        {"type": "recurring_event", "name": "Black Friday", "description": "annual spike",
         "date_range": {"start": "2026-11-27", "end": "2026-11-30"}},
    )
    assert ok["ok"] is True
    bad = validate_item(
        CID, "knowledge", "bad", {"type": "not_a_type", "name": "x", "description": "y"}
    )
    assert bad["ok"] is False


def test_validate_glossary_requires_maps_to(_isolated_semantic_dir):
    """`term` comes from item_key (the URL), not `data` -- only maps_to is
    checked here."""
    assert validate_item(CID, "glossary", "רווח", {"maps_to": "revenue"})["ok"] is True
    assert validate_item(CID, "glossary", "רווח", {"maps_to": ""})["ok"] is False


# --- route-level: auth -------------------------------------------------------

def test_semantic_endpoints_reject_non_admin(monkeypatch):
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity",
        lambda: {"client_id": CID, "email": "avi.peretz@ecommerce-demo.com"},  # a viewer
    )
    client = TestClient(main.app)
    assert client.get("/api/admin/semantic").status_code == 403


# --- route-level: full edit -> validate -> publish -> restore round-trip ----

def test_edit_validate_publish_updates_file_and_bumps_version(monkeypatch, _isolated_semantic_dir):
    client = _as_admin(monkeypatch)
    original_text = (_isolated_semantic_dir / "aov.yaml").read_text(encoding="utf-8")

    body = client.get("/api/admin/semantic")
    assert body.status_code == 200
    assert body.json()["published_version"] == 0

    aov = next(m for m in body.json()["metrics"] if m["name"] == "aov")
    put = client.put(
        "/api/admin/semantic/metric/aov",
        json={"data": {"description": "New definition for testing.", "sql": aov["sql"]}},
    )
    assert put.status_code == 200
    aov_draft = next(m for m in put.json()["metrics"] if m["name"] == "aov")
    assert aov_draft["is_draft"] is True
    assert aov_draft["description"] == "New definition for testing."

    val = client.post("/api/admin/semantic/validate", json={"section": "metric", "item_key": "aov"})
    assert val.status_code == 200
    assert val.json()["ok"] is True

    pub = client.post("/api/admin/semantic/publish", json={"items": [{"section": "metric", "item_key": "aov"}]})
    assert pub.status_code == 200
    assert pub.json()["published_version"] == 2  # 1 = seeded baseline, 2 = this publish
    aov_published = next(m for m in pub.json()["metrics"] if m["name"] == "aov")
    assert aov_published["is_draft"] is False
    assert aov_published["description"] == "New definition for testing."

    on_disk = (_isolated_semantic_dir / "aov.yaml").read_text(encoding="utf-8")
    assert "New definition for testing." in on_disk
    assert on_disk != original_text

    versions = client.get("/api/admin/semantic/versions").json()
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[0]["changed_items"] == ["metric:aov"]

    v1_id = next(v["id"] for v in versions if v["version"] == 1)
    restore = client.post(f"/api/admin/semantic/versions/{v1_id}/restore")
    assert restore.status_code == 200
    assert restore.json()["version"] == 3
    restored_text = (_isolated_semantic_dir / "aov.yaml").read_text(encoding="utf-8")
    assert restored_text == original_text  # byte-exact


def test_publish_blocked_without_validation(monkeypatch, _isolated_semantic_dir):
    client = _as_admin(monkeypatch)
    aov = next(m for m in client.get("/api/admin/semantic").json()["metrics"] if m["name"] == "aov")
    client.put("/api/admin/semantic/metric/aov", json={"data": {"description": "x", "sql": aov["sql"]}})
    # No validate call in between.
    pub = client.post("/api/admin/semantic/publish", json={"items": [{"section": "metric", "item_key": "aov"}]})
    assert pub.status_code == 409
    assert "not passed validation" in pub.json()["detail"]["failures"][0]["error"]


def test_publish_blocked_when_edited_after_validating(monkeypatch, _isolated_semantic_dir):
    client = _as_admin(monkeypatch)
    aov = next(m for m in client.get("/api/admin/semantic").json()["metrics"] if m["name"] == "aov")
    client.put("/api/admin/semantic/metric/aov", json={"data": {"description": "x", "sql": aov["sql"]}})
    client.post("/api/admin/semantic/validate", json={"section": "metric", "item_key": "aov"})
    client.put("/api/admin/semantic/metric/aov", json={"data": {"description": "y", "sql": aov["sql"]}})
    pub = client.post("/api/admin/semantic/publish", json={"items": [{"section": "metric", "item_key": "aov"}]})
    assert pub.status_code == 409


def test_publish_bad_sql_is_rejected_and_writes_nothing(monkeypatch, _isolated_semantic_dir):
    client = _as_admin(monkeypatch)
    original_text = (_isolated_semantic_dir / "aov.yaml").read_text(encoding="utf-8")
    client.put("/api/admin/semantic/metric/aov", json={"data": {"description": "x", "sql": "SELECT 1; DROP TABLE orders"}})
    val = client.post("/api/admin/semantic/validate", json={"section": "metric", "item_key": "aov"})
    assert val.json()["ok"] is False
    pub = client.post("/api/admin/semantic/publish", json={"items": [{"section": "metric", "item_key": "aov"}]})
    assert pub.status_code == 409
    assert (_isolated_semantic_dir / "aov.yaml").read_text(encoding="utf-8") == original_text


def test_create_rule_publish_and_appear_in_agent_tool(monkeypatch, _isolated_semantic_dir):
    client = _as_admin(monkeypatch)
    put = client.put(
        "/api/admin/semantic/rule/vip_definition",
        json={
            "data": {"definition": "VIP = top 5% of customers by lifetime revenue.",
                      "applies_to": ["vip_customers"], "status": "certified"},
            "action": "create",
        },
    )
    assert put.status_code == 200
    rule_draft = next(r for r in put.json()["rules"] if r["name"] == "vip_definition")
    assert rule_draft["is_new"] is True

    val = client.post("/api/admin/semantic/validate", json={"section": "rule", "item_key": "vip_definition"})
    assert val.json()["ok"] is True  # no `logic` SQL -- schema check only

    pub = client.post("/api/admin/semantic/publish", json={"items": [{"section": "rule", "item_key": "vip_definition"}]})
    assert pub.status_code == 200
    assert (_isolated_semantic_dir / "rules.yaml").exists()

    # sema_core.agent.tools.get_semantic_layer reads via the (patched) semantic_dir.
    from sema_core.agent.tools import AgentTools

    layer = AgentTools().get_semantic_layer()
    assert any(r["name"] == "vip_definition" for r in layer["business_rules"])


def test_archive_published_rule_removes_it_from_agent_view_after_publish(monkeypatch, _isolated_semantic_dir):
    client = _as_admin(monkeypatch)
    client.put(
        "/api/admin/semantic/rule/temp_rule",
        json={"data": {"definition": "temporary", "status": "certified"}, "action": "create"},
    )
    client.post("/api/admin/semantic/validate", json={"section": "rule", "item_key": "temp_rule"})
    client.post("/api/admin/semantic/publish", json={"items": [{"section": "rule", "item_key": "temp_rule"}]})

    # Now archive it: no draft exists for a purely-published item -> DELETE creates a deprecate draft.
    delete = client.delete("/api/admin/semantic/rule/temp_rule")
    assert delete.status_code == 200
    rule_after_delete = next(r for r in delete.json()["rules"] if r["name"] == "temp_rule")
    assert rule_after_delete["status"] == "deprecated"
    assert rule_after_delete["is_draft"] is True  # not yet published

    client.post("/api/admin/semantic/validate", json={"section": "rule", "item_key": "temp_rule"})
    pub = client.post("/api/admin/semantic/publish", json={"items": [{"section": "rule", "item_key": "temp_rule"}]})
    assert pub.status_code == 200

    from sema_core.agent.tools import AgentTools

    layer = AgentTools().get_semantic_layer()
    assert not any(r["name"] == "temp_rule" for r in layer["business_rules"])


def test_resaving_a_new_unpublished_item_without_action_stays_create(monkeypatch, _isolated_semantic_dir):
    """Regression: the editor's "Run validation" re-saves the draft on every
    click but doesn't always know to keep sending action="create" for an
    item that was never published. The server must derive create-vs-edit
    itself (from whether the item is published), not trust a client-supplied
    default of "edit" -- otherwise a not-yet-published item silently vanishes
    from the merged view the moment it's re-saved without an explicit action."""
    client = _as_admin(monkeypatch)
    client.put(
        "/api/admin/semantic/rule/new_rule",
        json={"data": {"definition": "first draft", "status": "certified"}, "action": "create"},
    )
    # Re-save WITHOUT specifying action (mirrors RuleCard.runValidation's
    # request body) -- the server must still treat this as "create".
    resp = client.put(
        "/api/admin/semantic/rule/new_rule",
        json={"data": {"definition": "second draft", "status": "certified"}},
    )
    assert resp.status_code == 200
    rule = next((r for r in resp.json()["rules"] if r["name"] == "new_rule"), None)
    assert rule is not None, "the rule vanished from the merged view after a re-save"
    assert rule["is_new"] is True
    assert rule["is_draft"] is True
    assert rule["definition"] == "second draft"


def test_incident_overlap_adds_caveat_to_evidence(monkeypatch, _isolated_semantic_dir):
    client = _as_admin(monkeypatch)
    client.put(
        "/api/admin/semantic/knowledge/payment_outage",
        json={
            "data": {"type": "incident", "description": "Stripe outage caused a checkout dip.",
                      "date_range": {"start": "2026-06-10", "end": "2026-06-12"}},
            "action": "create",
        },
    )
    client.post("/api/admin/semantic/validate", json={"section": "knowledge", "item_key": "payment_outage"})
    pub = client.post(
        "/api/admin/semantic/publish", json={"items": [{"section": "knowledge", "item_key": "payment_outage"}]}
    )
    assert pub.status_code == 200

    from sema_core.agent.response import _knowledge_caveats

    overlapping = _knowledge_caveats({"start": "2026-06-01", "end": "2026-06-30"})
    assert len(overlapping) == 1
    assert "checkout dip" in overlapping[0]
    assert _knowledge_caveats({"start": "2026-01-01", "end": "2026-01-31"}) == []
