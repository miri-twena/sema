"""
sema_core.retention: the retention_policy -> cutoff-date resolution, preview
count, and the sweep itself. No live DB or API key needed -- pure SQLite
stores + datetime math.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sema_core import retention
from sema_core.audit_store import AuditStore
from sema_core.conversation_store import SqliteConversationStore
from sema_core.org_settings_store import OrgSettingsStore
from sema_core.retention_store import RetentionRunStore


@pytest.fixture
def conversation_store(tmp_path):
    return SqliteConversationStore(tmp_path / "conversations.db")


@pytest.fixture
def org_settings_store(tmp_path):
    return OrgSettingsStore(tmp_path / "settings.db")


@pytest.fixture
def retention_run_store(tmp_path):
    return RetentionRunStore(tmp_path / "retention_runs.db")


@pytest.fixture
def audit_store(tmp_path):
    return AuditStore(tmp_path / "audit.db")


def _backdate(store: SqliteConversationStore, conv_id: str, days_ago: int) -> None:
    past = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    with store._connect() as conn:  # noqa: SLF001
        conn.execute("UPDATE conversations SET created_at = ? WHERE id = ?", (past, conv_id))


# --- cutoff_for_policy --------------------------------------------------------

def test_forever_has_no_cutoff():
    assert retention.cutoff_for_policy("forever") is None


def test_unknown_policy_has_no_cutoff():
    assert retention.cutoff_for_policy("not-a-real-policy") is None


def test_90d_cutoff_is_90_days_back():
    now = datetime(2026, 4, 1, tzinfo=timezone.utc)
    cutoff = retention.cutoff_for_policy("90d", now=now)
    assert cutoff == (now - timedelta(days=90)).isoformat()


def test_30d_cutoff_is_30_days_back():
    now = datetime(2026, 4, 1, tzinfo=timezone.utc)
    cutoff = retention.cutoff_for_policy("30d", now=now)
    assert cutoff == (now - timedelta(days=30)).isoformat()


# --- preview_deletion_count ---------------------------------------------------

def test_preview_forever_is_always_zero(conversation_store):
    conv_id = conversation_store.create("ecommerce")
    conversation_store.append(conv_id, "ecommerce", "user", "hi")
    _backdate(conversation_store, conv_id, days_ago=1000)
    assert retention.preview_deletion_count(conversation_store, "ecommerce", "forever") == 0


def test_preview_counts_eligible_conversations(conversation_store):
    old = conversation_store.create("ecommerce")
    conversation_store.append(old, "ecommerce", "user", "hi")
    _backdate(conversation_store, old, days_ago=100)

    new = conversation_store.create("ecommerce")
    conversation_store.append(new, "ecommerce", "user", "hi")

    assert retention.preview_deletion_count(conversation_store, "ecommerce", "90d") == 1
    assert retention.preview_deletion_count(conversation_store, "ecommerce", "30d") == 1


# --- run_sweep_for_client ------------------------------------------------------

def test_sweep_does_nothing_for_a_client_with_no_settings_row(conversation_store, org_settings_store):
    conv_id = conversation_store.create("ecommerce")
    conversation_store.append(conv_id, "ecommerce", "user", "hi")
    _backdate(conversation_store, conv_id, days_ago=1000)

    deleted = retention.run_sweep_for_client(conversation_store, org_settings_store, "ecommerce")
    assert deleted == 0
    assert conv_id in {c["id"] for c in conversation_store.list_conversations("ecommerce")}


def test_sweep_respects_forever_policy(conversation_store, org_settings_store):
    org_settings_store.get_or_create("ecommerce", default_name="E-Commerce")  # defaults to 'forever'
    conv_id = conversation_store.create("ecommerce")
    conversation_store.append(conv_id, "ecommerce", "user", "hi")
    _backdate(conversation_store, conv_id, days_ago=1000)

    deleted = retention.run_sweep_for_client(conversation_store, org_settings_store, "ecommerce")
    assert deleted == 0


def test_sweep_deletes_eligible_conversations_under_90d_policy(conversation_store, org_settings_store):
    org_settings_store.get_or_create("ecommerce", default_name="E-Commerce")
    org_settings_store.update("ecommerce", {"retention_policy": "90d"})

    old = conversation_store.create("ecommerce")
    conversation_store.append(old, "ecommerce", "user", "hi")
    _backdate(conversation_store, old, days_ago=100)

    new = conversation_store.create("ecommerce")
    conversation_store.append(new, "ecommerce", "user", "hi")

    deleted = retention.run_sweep_for_client(conversation_store, org_settings_store, "ecommerce")
    assert deleted == 1
    remaining = {c["id"] for c in conversation_store.list_conversations("ecommerce")}
    assert old not in remaining
    assert new in remaining


def test_sweep_is_scoped_per_client(conversation_store, org_settings_store):
    org_settings_store.get_or_create("ecommerce", default_name="E-Commerce")
    org_settings_store.update("ecommerce", {"retention_policy": "30d"})

    other_conv = conversation_store.create("other-client")
    conversation_store.append(other_conv, "other-client", "user", "hi")
    _backdate(conversation_store, other_conv, days_ago=100)

    deleted = retention.run_sweep_for_client(conversation_store, org_settings_store, "ecommerce")
    assert deleted == 0
    assert other_conv in {c["id"] for c in conversation_store.list_conversations("other-client")}


# --- run_all_clients_sweep_tracked ---------------------------------------

def test_tracked_sweep_records_a_run_for_every_configured_client(
    conversation_store, org_settings_store, retention_run_store, audit_store
):
    org_settings_store.get_or_create("ecommerce", default_name="E-Commerce")
    org_settings_store.update("ecommerce", {"retention_policy": "30d"})

    old = conversation_store.create("ecommerce")
    conversation_store.append(old, "ecommerce", "user", "hi")
    _backdate(conversation_store, old, days_ago=100)

    results = retention.run_all_clients_sweep_tracked(
        conversation_store, org_settings_store, retention_run_store, audit_store
    )
    assert results["ecommerce"]["deleted_count"] == 1
    assert results["ecommerce"]["status"] == "ok"
    stored = retention_run_store.get("ecommerce")
    assert stored["deleted_count"] == 1
    # insurance has no settings/conversations in this temp store, but the
    # real client registry still lists it -- it gets a zero-deletion run too.
    assert "insurance" in results


def test_tracked_sweep_skips_a_client_run_within_the_skip_window(
    conversation_store, org_settings_store, retention_run_store, audit_store
):
    org_settings_store.get_or_create("ecommerce", default_name="E-Commerce")
    org_settings_store.update("ecommerce", {"retention_policy": "30d"})
    retention_run_store.record("ecommerce", deleted_count=0, status="ok")

    old = conversation_store.create("ecommerce")
    conversation_store.append(old, "ecommerce", "user", "hi")
    _backdate(conversation_store, old, days_ago=100)

    retention.run_all_clients_sweep_tracked(
        conversation_store, org_settings_store, retention_run_store, audit_store
    )
    # The just-recorded run is well within the 20h skip window, so the
    # eligible conversation must NOT have been swept this time.
    remaining = {c["id"] for c in conversation_store.list_conversations("ecommerce")}
    assert old in remaining


def test_tracked_sweep_runs_again_once_the_skip_window_has_passed(
    conversation_store, org_settings_store, retention_run_store, audit_store
):
    org_settings_store.get_or_create("ecommerce", default_name="E-Commerce")
    org_settings_store.update("ecommerce", {"retention_policy": "30d"})

    old = conversation_store.create("ecommerce")
    conversation_store.append(old, "ecommerce", "user", "hi")
    _backdate(conversation_store, old, days_ago=100)

    stale = (datetime.now(timezone.utc) - timedelta(hours=21)).isoformat()
    with retention_run_store._connect() as conn:  # noqa: SLF001 -- test backdates the run record directly
        conn.execute(
            "INSERT INTO retention_runs (client_id, last_run_at, deleted_count, status, error) "
            "VALUES (?, ?, 0, 'ok', NULL)",
            ("ecommerce", stale),
        )

    results = retention.run_all_clients_sweep_tracked(
        conversation_store, org_settings_store, retention_run_store, audit_store
    )
    assert results["ecommerce"]["deleted_count"] == 1


def test_tracked_sweep_audits_only_non_zero_deletions(
    conversation_store, org_settings_store, retention_run_store, audit_store
):
    org_settings_store.get_or_create("ecommerce", default_name="E-Commerce")
    org_settings_store.update("ecommerce", {"retention_policy": "30d"})

    old = conversation_store.create("ecommerce")
    conversation_store.append(old, "ecommerce", "user", "hi")
    _backdate(conversation_store, old, days_ago=100)

    retention.run_all_clients_sweep_tracked(
        conversation_store, org_settings_store, retention_run_store, audit_store
    )
    events = audit_store.list_events("ecommerce", page_size=100)["events"]
    assert len(events) == 1
    assert events[0]["action"] == "org.retention_swept"
    assert events[0]["actor_id"] is None  # system actor, no human triggered this

    # insurance had nothing to delete -- no audit event for it.
    assert audit_store.list_events("insurance", page_size=100)["total"] == 0


def test_tracked_sweep_records_an_error_and_never_blocks_other_clients(
    conversation_store, org_settings_store, retention_run_store, audit_store, monkeypatch
):
    org_settings_store.get_or_create("ecommerce", default_name="E-Commerce")
    org_settings_store.update("ecommerce", {"retention_policy": "30d"})
    org_settings_store.get_or_create("insurance", default_name="Auto Insurance")
    org_settings_store.update("insurance", {"retention_policy": "30d"})

    old = conversation_store.create("insurance")
    conversation_store.append(old, "insurance", "user", "hi")
    _backdate(conversation_store, old, days_ago=100)

    real_sweep = retention.run_sweep_for_client

    def boom_for_ecommerce(conv_store, settings_store, client_id):
        if client_id == "ecommerce":
            raise RuntimeError("boom")
        return real_sweep(conv_store, settings_store, client_id)

    monkeypatch.setattr(retention, "run_sweep_for_client", boom_for_ecommerce)

    results = retention.run_all_clients_sweep_tracked(
        conversation_store, org_settings_store, retention_run_store, audit_store
    )
    assert results["ecommerce"]["status"] == "error"
    assert "boom" in results["ecommerce"]["error"]
    # The OTHER client's sweep still ran and actually deleted its conversation.
    assert results["insurance"]["status"] == "ok"
    assert results["insurance"]["deleted_count"] == 1
    remaining = {c["id"] for c in conversation_store.list_conversations("insurance")}
    assert old not in remaining
