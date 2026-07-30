"""
Tests for the append-only admin audit log (spec §3).

Store-level tests use a local `store` fixture (a fresh temp-file AuditStore
per test), mirroring test_org_users.py. Route-level tests use an inline
TestClient and monkeypatch the mocked identity, mirroring
test_org_settings.py's `_client_as_miri` pattern.

conftest's autouse fixtures keep every test off the real var/sema_state.db
and off the real Anthropic network.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

import api.main as main
from sema_core.audit_store import AuditStore

CID = "ecommerce"


@pytest.fixture
def store(tmp_path) -> AuditStore:
    return AuditStore(tmp_path / "audit.db")


def _record(store: AuditStore, **overrides) -> dict:
    kw = {
        "client_id": CID,
        "actor_id": "u1",
        "actor_name": "Miri Levi",
        "actor_role": "client_admin",
        "action": "user.role_changed",
        "target_type": "user",
        "target_id": "u2",
        "target_label": "Lior Katz",
        "before": {"role": "viewer"},
        "after": {"role": "analyst"},
    }
    kw.update(overrides)
    return store.record(kw.pop("client_id"), **kw)


# --- store: persistence + append-only ---------------------------------------

def test_record_persists_actor_action_and_before_after(store):
    row = _record(store)
    assert row["client_id"] == CID
    assert row["actor_name"] == "Miri Levi"
    assert row["action"] == "user.role_changed"
    assert row["before"] == {"role": "viewer"}
    assert row["after"] == {"role": "analyst"}
    assert row["created_at"]  # stamped


def test_events_are_scoped_per_client(store):
    _record(store, client_id=CID)
    _record(store, client_id="insurance")
    assert len(store.list_events(CID)["events"]) == 1
    assert len(store.list_events("insurance")["events"]) == 1


def test_table_is_append_only_update_fails(store):
    row = _record(store)
    with sqlite3.connect(store._path) as conn:  # noqa: SLF001 -- test reaches for the raw file on purpose
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE audit_events SET action = 'tampered' WHERE id = ?", (row["id"],))


def test_table_is_append_only_delete_fails(store):
    row = _record(store)
    with sqlite3.connect(store._path) as conn:  # noqa: SLF001
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM audit_events WHERE id = ?", (row["id"],))
    # The row really is still there -- the trigger aborted the statement, not
    # just raised alongside a silent partial delete.
    assert len(store.list_events(CID)["events"]) == 1


# --- store: filters + pagination ---------------------------------------------

def test_filter_by_actor(store):
    _record(store, actor_id="u1")
    _record(store, actor_id="u2")
    events = store.list_events(CID, actor_id="u1")["events"]
    assert len(events) == 1
    assert events[0]["actor_id"] == "u1"


def test_filter_by_category_is_a_prefix_match_on_action(store):
    _record(store, action="user.role_changed")
    _record(store, action="user.invited")
    _record(store, action="semantic.published")
    events = store.list_events(CID, category="user")["events"]
    assert {e["action"] for e in events} == {"user.role_changed", "user.invited"}


def test_filter_by_date_range(store):
    # record() always stamps "now", and the table is append-only (an UPDATE
    # would be rejected, per the test right above), so insert an old row
    # directly to give the range filter something to exclude.
    with sqlite3.connect(store._path) as conn, conn:
        conn.execute(
            "INSERT INTO audit_events (id, client_id, action, created_at) VALUES (?, ?, ?, ?)",
            ("old-row", CID, "user.invited", "2020-01-01T00:00:00+00:00"),
        )
    recent = _record(store)
    events = store.list_events(CID, start="2021-01-01T00:00:00+00:00")["events"]
    assert len(events) == 1
    assert events[0]["id"] == recent["id"]


def test_filter_by_target_label_free_text(store):
    _record(store, target_label="Lior Katz")
    _record(store, target_label="Noa Berman")
    events = store.list_events(CID, q="lior")["events"]
    assert len(events) == 1
    assert events[0]["target_label"] == "Lior Katz"


def test_pagination(store):
    for i in range(5):
        _record(store, target_id=str(i))
    page1 = store.list_events(CID, page=1, page_size=2)
    page2 = store.list_events(CID, page=2, page_size=2)
    assert page1["total"] == 5
    assert len(page1["events"]) == 2
    assert len(page2["events"]) == 2
    assert {e["id"] for e in page1["events"]}.isdisjoint({e["id"] for e in page2["events"]})


def test_export_rows_ignores_pagination_and_respects_cap(store):
    for i in range(5):
        _record(store, target_id=str(i))
    rows = store.export_rows(CID, limit=3)
    assert len(rows) == 3


# --- route: every wired admin action lands in the log ------------------------

def _client_as_miri(monkeypatch) -> TestClient:
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    return TestClient(main.app)


def test_invite_role_change_suspend_and_remove_are_all_audited(monkeypatch):
    client = _client_as_miri(monkeypatch)

    invited = client.post(
        "/api/admin/users/invite", json={"email": "new.hire@x.com", "role": "analyst"}
    ).json()
    client.patch(f"/api/admin/users/{invited['id']}", json={"role": "viewer"})
    client.patch(f"/api/admin/users/{invited['id']}", json={"status": "suspended"})
    client.post(f"/api/admin/users/{invited['id']}/resend-invite")
    other = client.get("/api/admin/users").json()["users"][1]["id"]
    client.delete(f"/api/admin/users/{other}")

    actions = {e["action"] for e in main.audit_store.list_events(CID, page_size=100)["events"]}
    assert actions >= {
        "user.invited", "user.role_changed", "user.suspended",
        "user.invite_resent", "user.removed",
    }


def test_semantic_publish_and_restore_are_audited(monkeypatch, tmp_path):
    """Isolates semantic_dir like test_semantic_model.py's own fixture does,
    so Publish/Restore never touch the real sql/semantic/*.yaml files."""
    import shutil

    import sema_core.agent.semantic as semantic
    import sema_core.semantic_editor as semantic_editor
    from sema_core.client_registry import PROJECT_ROOT

    fake_dir = tmp_path / "semantic"
    shutil.copytree(PROJECT_ROOT / "sql" / "semantic", fake_dir)
    monkeypatch.setattr(semantic, "semantic_dir", lambda client_id=None: fake_dir)
    monkeypatch.setattr(semantic_editor, "semantic_dir", lambda client_id=None: fake_dir)
    monkeypatch.setattr(main, "semantic_dir", lambda client_id=None: fake_dir)

    client = _client_as_miri(monkeypatch)
    aov = next(m for m in client.get("/api/admin/semantic").json()["metrics"] if m["name"] == "aov")
    client.put(
        "/api/admin/semantic/metric/aov",
        json={"data": {"description": "Updated for the audit test.", "sql": aov["sql"]}},
    )
    client.post("/api/admin/semantic/validate", json={"section": "metric", "item_key": "aov"})
    client.post("/api/admin/semantic/publish", json={"items": [{"section": "metric", "item_key": "aov"}]})

    versions = client.get("/api/admin/semantic/versions").json()
    v1_id = next(v["id"] for v in versions if v["version"] == 1)
    client.post(f"/api/admin/semantic/versions/{v1_id}/restore")

    actions = [e["action"] for e in main.audit_store.list_events(CID, page_size=100)["events"]]
    assert "semantic.published" in actions
    assert "semantic.restored" in actions


def test_semantic_draft_save_discard_and_archive_are_each_audited_once(monkeypatch, tmp_path):
    """org_settings_gapfix_prompt.md Part 3: draft save/discard/archive each
    get exactly one audit event (previously only publish/restore were
    wired)."""
    import shutil

    import sema_core.agent.semantic as semantic
    import sema_core.semantic_editor as semantic_editor
    from sema_core.client_registry import PROJECT_ROOT

    fake_dir = tmp_path / "semantic"
    shutil.copytree(PROJECT_ROOT / "sql" / "semantic", fake_dir)
    monkeypatch.setattr(semantic, "semantic_dir", lambda client_id=None: fake_dir)
    monkeypatch.setattr(semantic_editor, "semantic_dir", lambda client_id=None: fake_dir)
    monkeypatch.setattr(main, "semantic_dir", lambda client_id=None: fake_dir)

    client = _client_as_miri(monkeypatch)
    aov = next(m for m in client.get("/api/admin/semantic").json()["metrics"] if m["name"] == "aov")

    # Save a draft edit -> exactly one semantic.draft_saved event.
    client.put(
        "/api/admin/semantic/metric/aov",
        json={"data": {"description": "Draft edit for the audit test.", "sql": aov["sql"]}},
    )
    events = main.audit_store.list_events(CID, category="semantic", page_size=100)["events"]
    saved = [e for e in events if e["action"] == "semantic.draft_saved"]
    assert len(saved) == 1
    assert saved[0]["target_id"] == "aov"
    assert saved[0]["after"]["description"] == "Draft edit for the audit test."
    # No prior draft existed yet, so there's nothing to diff against --
    # the FULL submitted data is the "after" (see _diff_fields's None-either-
    # side case). A second save on top of an existing draft would instead
    # be limited to just the fields that changed between the two drafts.
    assert saved[0]["before"] == {}

    # Discard that same draft -> exactly one semantic.draft_discarded event.
    client.delete("/api/admin/semantic/metric/aov")
    events = main.audit_store.list_events(CID, category="semantic", page_size=100)["events"]
    discarded = [e for e in events if e["action"] == "semantic.draft_discarded"]
    assert len(discarded) == 1
    assert discarded[0]["target_id"] == "aov"

    # No draft exists now (just discarded) -> DELETE archives the published
    # item instead, producing exactly one semantic.draft_archived event.
    client.delete("/api/admin/semantic/metric/aov")
    events = main.audit_store.list_events(CID, category="semantic", page_size=100)["events"]
    archived = [e for e in events if e["action"] == "semantic.draft_archived"]
    assert len(archived) == 1
    assert archived[0]["target_id"] == "aov"


def test_org_settings_and_logo_updates_are_audited(monkeypatch):
    client = _client_as_miri(monkeypatch)
    client.get("/api/admin/org-settings")
    client.patch("/api/admin/org-settings", json={"currency": "ILS"})
    events = main.audit_store.list_events(CID, category="org_settings")["events"]
    assert any(e["target_id"] == "currency" for e in events)


# --- route: list + export endpoints ------------------------------------------

def test_admin_audit_list_endpoint_filters_and_paginates(monkeypatch):
    client = _client_as_miri(monkeypatch)
    client.post("/api/admin/users/invite", json={"email": "a@x.com", "role": "analyst"})
    client.post("/api/admin/users/invite", json={"email": "b@x.com", "role": "viewer"})

    resp = client.get("/api/admin/audit", params={"category": "user"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2
    assert all(e["action"].startswith("user.") for e in body["events"])

    resp_q = client.get("/api/admin/audit", params={"q": "a@x.com"})
    assert resp_q.json()["total"] == 1


def test_admin_audit_requires_admin(monkeypatch):
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(
        main, "current_identity",
        lambda: {"client_id": CID, "email": "avi.peretz@ecommerce-demo.com"},  # a viewer
    )
    client = TestClient(main.app)
    assert client.get("/api/admin/audit").status_code == 403
    assert client.get("/api/admin/audit/export").status_code == 403


def test_admin_audit_export_returns_csv(monkeypatch):
    client = _client_as_miri(monkeypatch)
    client.post("/api/admin/users/invite", json={"email": "csv-test@x.com", "role": "analyst"})

    resp = client.get("/api/admin/audit/export", params={"q": "csv-test"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    text = resp.text
    assert "csv-test@x.com" in text
    # Leading BOM (Excel/Hebrew compatibility, same convention as the
    # frontend's own CSV export) -- strip it before checking the header row.
    assert text.lstrip("﻿").splitlines()[0].startswith("created_at,")
