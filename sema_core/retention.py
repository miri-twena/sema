"""
SEMA: conversation-retention sweep (org settings §2, "retention_policy").

An org's `retention_policy` ("forever" / "90d" / "30d") governs how long its
CHAT conversations are kept before being soft-deleted (see
conversation_store.soft_delete_older_than). This module is the policy ->
cutoff-date resolution plus the sweep itself; it holds no state of its own.

There is no OS-level scheduler in this project (no Celery/cron) -- the same
"manual script" convention data/load_data.py already uses. Run this file
directly (or import run_all_clients_sweep from a future scheduled job) to
execute one sweep across every configured client:

    .venv\\Scripts\\python.exe -m sema_core.retention
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sema_core.client_registry import load_clients
from sema_core.conversation_store import SqliteConversationStore
from sema_core.obs import get_logger, log_event
from sema_core.org_settings_store import OrgSettingsStore

logger = get_logger("retention")

# "forever" has no entry -- a policy of "forever" simply never sweeps.
RETENTION_DAYS: dict[str, int] = {"90d": 90, "30d": 30}


def cutoff_for_policy(policy: str, now: datetime | None = None) -> str | None:
    """The ISO cutoff timestamp for a policy -- conversations CREATED before
    this are eligible for deletion. None for 'forever' (or any policy with no
    entry in RETENTION_DAYS), meaning "nothing is ever swept"."""
    days = RETENTION_DAYS.get(policy)
    if days is None:
        return None
    base = now or datetime.now(timezone.utc)
    return (base - timedelta(days=days)).isoformat()


def preview_deletion_count(
    conversation_store: SqliteConversationStore, client_id: str, policy: str
) -> int:
    """"N conversations will be deleted on next run" -- shown before a policy
    change is confirmed (org settings UI). Read-only."""
    cutoff = cutoff_for_policy(policy)
    if cutoff is None:
        return 0
    return conversation_store.count_active_older_than(client_id, cutoff)


def run_sweep_for_client(
    conversation_store: SqliteConversationStore, org_settings_store: OrgSettingsStore, client_id: str
) -> int:
    """Soft-delete every conversation this ONE client's current policy makes
    eligible. Returns the count affected (0 for 'forever' or nothing to do)."""
    settings = org_settings_store.get(client_id)
    if settings is None:
        return 0
    cutoff = cutoff_for_policy(settings["retention_policy"])
    if cutoff is None:
        return 0
    deleted = conversation_store.soft_delete_older_than(client_id, cutoff)
    if deleted:
        log_event(
            logger, "retention_sweep", client_id=client_id,
            policy=settings["retention_policy"], deleted=deleted,
        )
    return deleted


def run_all_clients_sweep(
    conversation_store: SqliteConversationStore, org_settings_store: OrgSettingsStore
) -> dict[str, int]:
    """The actual daily job: sweep every configured client. A single client's
    failure (e.g. malformed settings) is logged and skipped rather than
    aborting the whole run -- one tenant's bad state must never block
    another's retention sweep."""
    results: dict[str, int] = {}
    for client in load_clients():
        cid = client["id"]
        try:
            results[cid] = run_sweep_for_client(conversation_store, org_settings_store, cid)
        except Exception:
            logger.warning("retention sweep failed for client %s", cid, exc_info=True)
            results[cid] = 0
    return results


if __name__ == "__main__":
    from sema_core.settings import settings as app_settings

    _conversation_store = SqliteConversationStore(app_settings.conversation_db_path)
    _org_settings_store = OrgSettingsStore(app_settings.conversation_db_path)
    summary = run_all_clients_sweep(_conversation_store, _org_settings_store)
    for cid, count in summary.items():
        print(f"{cid}: {count} conversation(s) soft-deleted")
