"""
sema_core.org_alerts / org_alerts_store: migration of the 3 expressible YAML
alerts into editable org_alerts rows, deprecated-metric auto-disable, and the
12-enabled-alert limit. No live DB needed -- ensure_migrated/list_effective
only read the semantic YAML (sema_core.agent.semantic), never Postgres;
readings_for_alerts_engine's DB-touching step (alert_templates.evaluate_current)
is monkeypatched where exercised.
"""

from __future__ import annotations

import pytest

from sema_core import org_alerts
from sema_core.org_alerts_store import OrgAlertLimitExceededError, OrgAlertNotFoundError, OrgAlertsStore

ECOMMERCE = "ecommerce"
INSURANCE = "insurance"


@pytest.fixture
def store(tmp_path) -> OrgAlertsStore:
    return OrgAlertsStore(tmp_path / "org_alerts.db")


# --- migration ---------------------------------------------------------------
def test_migration_seeds_exactly_the_three_expressible_yaml_alerts(store):
    org_alerts.ensure_migrated(ECOMMERCE, store)
    rows = store.list_for_client(ECOMMERCE)
    assert {r["name"] for r in rows} == {"Revenue Drop", "AOV Drop", "At-Risk Customers"}


def test_migration_preserves_the_original_thresholds_and_severities(store):
    org_alerts.ensure_migrated(ECOMMERCE, store)
    rows = {r["name"]: r for r in store.list_for_client(ECOMMERCE)}
    assert rows["Revenue Drop"]["params"] == {"window": "mom", "direction": "drop", "threshold_pct": 8}
    assert rows["Revenue Drop"]["severity"] == "critical"
    assert rows["AOV Drop"]["params"] == {"window": "mom", "direction": "drop", "threshold_pct": 5}
    assert rows["AOV Drop"]["severity"] == "warning"
    assert rows["At-Risk Customers"]["params"] == {"operator": "above", "value": 300}
    assert rows["At-Risk Customers"]["severity"] == "warning"


def test_migration_is_a_noop_for_a_client_with_no_expressible_yaml_alerts(store):
    """insurance defines no `alerts:` blocks at all -- migration must not
    invent org_alerts rows out of nothing."""
    org_alerts.ensure_migrated(INSURANCE, store)
    assert store.list_for_client(INSURANCE) == []
    assert store.has_migrated(INSURANCE) is True


def test_migration_runs_exactly_once_even_if_the_seeded_row_is_deleted(store):
    org_alerts.ensure_migrated(ECOMMERCE, store)
    rows = store.list_for_client(ECOMMERCE)
    store.delete(ECOMMERCE, next(r["id"] for r in rows if r["name"] == "AOV Drop"))

    org_alerts.ensure_migrated(ECOMMERCE, store)  # second call: must NOT re-seed the deleted row
    names = {r["name"] for r in store.list_for_client(ECOMMERCE)}
    assert names == {"Revenue Drop", "At-Risk Customers"}


def test_list_effective_triggers_migration_lazily(store):
    """No explicit ensure_migrated call -- list_effective must still migrate
    on first access (the API layer never calls ensure_migrated directly)."""
    assert store.has_migrated(ECOMMERCE) is False
    rows = org_alerts.list_effective(ECOMMERCE, store)
    assert len(rows) == 3
    assert store.has_migrated(ECOMMERCE) is True


# --- deprecated-metric auto-disable -------------------------------------------
def test_deprecated_metric_auto_disables_with_a_persisted_reason(store, monkeypatch):
    org_alerts.ensure_migrated(ECOMMERCE, store)

    monkeypatch.setattr(org_alerts, "_metric_is_usable", lambda cid, name: name != "aov")
    rows = {r["name"]: r for r in org_alerts.list_effective(ECOMMERCE, store)}
    assert rows["AOV Drop"]["enabled"] is False
    assert "aov" in rows["AOV Drop"]["disabled_reason"]
    assert rows["Revenue Drop"]["enabled"] is True  # unaffected

    # And it's PERSISTED, not just computed for this one call.
    persisted = store.get(ECOMMERCE, rows["AOV Drop"]["id"])
    assert persisted["enabled"] is False


def test_metric_coming_back_clears_the_stale_disabled_reason_but_does_not_reenable(store, monkeypatch):
    org_alerts.ensure_migrated(ECOMMERCE, store)
    monkeypatch.setattr(org_alerts, "_metric_is_usable", lambda cid, name: name != "aov")
    org_alerts.list_effective(ECOMMERCE, store)  # auto-disables AOV Drop

    monkeypatch.setattr(org_alerts, "_metric_is_usable", lambda cid, name: True)  # metric republished
    rows = {r["name"]: r for r in org_alerts.list_effective(ECOMMERCE, store)}
    assert rows["AOV Drop"]["enabled"] is False  # stays off -- never auto-re-enabled
    assert rows["AOV Drop"]["disabled_reason"] is None  # but the stale note is cleared


def test_orders_kpi_has_no_backing_metric_and_is_never_auto_disabled(store):
    """'orders' has no semantic-layer metric at all (KPI_CATALOG['orders']['metric']
    is None) -- an org alert on it must never be treated as deprecated."""
    row = store.create(
        ECOMMERCE, name="Orders Below 5", metric="orders", template="absolute_threshold",
        params={"operator": "below", "value": 5}, severity="warning", created_by=None,
    )
    effective = {r["id"]: r for r in org_alerts.list_effective(ECOMMERCE, store)}
    assert effective[row["id"]]["enabled"] is True
    assert effective[row["id"]]["disabled_reason"] is None


# --- 12-enabled-alert limit ----------------------------------------------------
def test_create_beyond_the_limit_is_rejected(store):
    for i in range(12):
        store.create(
            ECOMMERCE, name=f"Alert {i}", metric="revenue", template="absolute_threshold",
            params={"operator": "above", "value": i}, severity="warning", created_by=None,
        )
    with pytest.raises(OrgAlertLimitExceededError):
        store.create(
            ECOMMERCE, name="One Too Many", metric="revenue", template="absolute_threshold",
            params={"operator": "above", "value": 99}, severity="warning", created_by=None,
        )
    assert len(store.list_for_client(ECOMMERCE)) == 12


def test_a_disabled_alert_does_not_count_toward_the_limit(store):
    for i in range(12):
        store.create(
            ECOMMERCE, name=f"Alert {i}", metric="revenue", template="absolute_threshold",
            params={"operator": "above", "value": i}, severity="warning", created_by=None, enabled=(i > 0),
        )
    # 11 enabled, 1 disabled -- creating one more enabled alert must succeed.
    row = store.create(
        ECOMMERCE, name="Room For One More", metric="revenue", template="absolute_threshold",
        params={"operator": "above", "value": 99}, severity="warning", created_by=None,
    )
    assert row["enabled"] is True


def test_enabling_a_toggle_past_the_limit_is_rejected(store):
    for i in range(12):  # 12 already enabled -- at the cap
        store.create(
            ECOMMERCE, name=f"Alert {i}", metric="revenue", template="absolute_threshold",
            params={"operator": "above", "value": i}, severity="warning", created_by=None,
        )
    extra = store.create(
        ECOMMERCE, name="Extra Disabled", metric="revenue", template="absolute_threshold",
        params={"operator": "above", "value": 99}, severity="warning", created_by=None, enabled=False,
    )
    with pytest.raises(OrgAlertLimitExceededError):
        store.update(ECOMMERCE, extra["id"], {"enabled": True})


# --- basic CRUD ----------------------------------------------------------------
def test_delete_unknown_alert_raises(store):
    with pytest.raises(OrgAlertNotFoundError):
        store.delete(ECOMMERCE, "ghost-id")


def test_duplicate_name_for_the_same_client_is_rejected(store):
    store.create(
        ECOMMERCE, name="Dup", metric="revenue", template="absolute_threshold",
        params={"operator": "above", "value": 1}, severity="warning", created_by=None,
    )
    with pytest.raises(Exception):  # sqlite3.IntegrityError -- UNIQUE(client_id, name)
        store.create(
            ECOMMERCE, name="Dup", metric="revenue", template="absolute_threshold",
            params={"operator": "above", "value": 2}, severity="warning", created_by=None,
        )


def test_alerts_are_scoped_per_client(store):
    store.create(
        ECOMMERCE, name="Ecom Alert", metric="revenue", template="absolute_threshold",
        params={"operator": "above", "value": 1}, severity="warning", created_by=None,
    )
    store.create(
        INSURANCE, name="Insurance Alert", metric="revenue", template="absolute_threshold",
        params={"operator": "above", "value": 1}, severity="warning", created_by=None,
    )
    assert len(store.list_for_client(ECOMMERCE)) == 1
    assert len(store.list_for_client(INSURANCE)) == 1


# --- summary sentences ----------------------------------------------------------
def test_summary_sentences_are_bilingual_and_reflect_params():
    en = org_alerts.summary_sentence("revenue", "pct_change", {"window": "mom", "direction": "drop", "threshold_pct": 8})
    he = org_alerts.summary_sentence_he("revenue", "pct_change", {"window": "mom", "direction": "drop", "threshold_pct": 8})
    assert "8%" in en and "month-over-month" in en
    assert "8%" in he
    assert en != he
