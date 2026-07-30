"""
SEMA: org-alert orchestration (alert_templates_prompt.md items 3 and 5).

Sits between the API layer and org_alerts_store/alert_templates:
  - ensure_migrated(): one-time, idempotent seeding of the 3 existing YAML
    alerts that ARE expressible as a template (revenue_mom_drop, aov_drop,
    churn_risk_count -- see MIGRATION_MAP). The other 2 existing YAML alerts
    (active_customers_drop -- its metric isn't in the fixed KPI_CATALOG at
    all; churn_risk_high_value -- its SQL computes a VIP-filtered subset,
    not the churn_risk metric's own value) stay YAML/system-driven, per the
    prompt's explicit fallback. `alerts_engine.MIGRATED_YAML_ALERT_IDS`
    imports MIGRATION_MAP from here so the two lists can never drift apart.
  - list_effective(): read-time deprecated-metric auto-disable, mirroring
    sema_core.home_config's KPI-drift handling for the same fixed catalog.
  - readings_for_alerts_engine(): the enabled, effective alerts' CURRENT
    readings, shaped to merge into alerts_engine's existing pipeline.
"""

from __future__ import annotations

from sema_core import alert_templates
from sema_core.home_config import KPI_CATALOG, _metric, _metric_is_usable
from sema_core.org_alerts_store import OrgAlertsStore

# metric key (KPI_CATALOG) -> domain, for the KPI_CATALOG entries with no
# backing semantic-layer metric ("orders") -- for revenue/aov/churn_risk the
# real metric's own `domain` (read via home_config._metric) is used instead.
_FALLBACK_DOMAIN = {"orders": "sales"}

# The 3 existing YAML alerts (sql/semantic/{revenue,aov,churn_risk}.yaml)
# that ARE cleanly expressible as a template, seeded once per client as
# editable org_alerts rows. Each is only actually seeded for a client whose
# semantic layer defines that YAML alert id (home_config.known_alert_ids) --
# the insurance demo tenant defines none of these, so migration is a no-op
# there, exactly as it should be.
MIGRATION_MAP = [
    {
        "yaml_alert_id": "revenue_mom_drop",
        "name": "Revenue Drop",
        "metric": "revenue",
        "template": "pct_change",
        "params": {"window": "mom", "direction": "drop", "threshold_pct": 8},
        "severity": "critical",
    },
    {
        "yaml_alert_id": "aov_drop",
        "name": "AOV Drop",
        "metric": "aov",
        "template": "pct_change",
        "params": {"window": "mom", "direction": "drop", "threshold_pct": 5},
        "severity": "warning",
    },
    {
        "yaml_alert_id": "churn_risk_count",
        "name": "At-Risk Customers",
        "metric": "churn_risk",
        "template": "absolute_threshold",
        "params": {"operator": "above", "value": 300},
        "severity": "warning",
    },
]

MIGRATED_YAML_ALERT_IDS = frozenset(row["yaml_alert_id"] for row in MIGRATION_MAP)


def ensure_migrated(client_id: str, store: OrgAlertsStore) -> None:
    """Seed MIGRATION_MAP rows this client's semantic layer actually defines,
    exactly once. A client that already has (or once had, then deleted) its
    migrated rows is never re-seeded -- has_migrated/mark_migrated is a
    permanent marker, not "seed if currently empty"."""
    if store.has_migrated(client_id):
        return
    from sema_core.home_config import known_alert_ids  # local import: same-module convenience, no cycle risk

    known = known_alert_ids(client_id)
    for row in MIGRATION_MAP:
        if row["yaml_alert_id"] not in known:
            continue
        try:
            store.create(
                client_id,
                name=row["name"],
                metric=row["metric"],
                template=row["template"],
                params=row["params"],
                severity=row["severity"],
                created_by=None,
            )
        except Exception:
            continue  # a UNIQUE clash or the 12-limit must never block startup
    store.mark_migrated(client_id)


def list_effective(client_id: str, store: OrgAlertsStore) -> list[dict]:
    """This client's org alerts, migrating on first access and auto-disabling
    (persisted, with a reason) any enabled alert whose metric has since been
    deprecated or removed -- mirrors home_config.effective_config's KPI-drift
    handling for the same fixed catalog."""
    ensure_migrated(client_id, store)
    out = []
    for row in store.list_for_client(client_id):
        metric_name = KPI_CATALOG[row["metric"]]["metric"]
        usable = metric_name is None or _metric_is_usable(client_id, metric_name)
        if row["enabled"] and not usable:
            row = store.update(
                client_id, row["id"],
                {"enabled": False, "disabled_reason": f"Its '{metric_name}' metric was deprecated or removed."},
            )
        elif row["disabled_reason"] and usable:
            # The metric came back (re-published) -- clear a stale auto-disable
            # note so it doesn't shadow a manual re-enable. Does not re-enable.
            row = store.update(client_id, row["id"], {"disabled_reason": None})
        out.append(row)
    return out


_METRIC_LABEL_HE = {
    "revenue": "הכנסות",
    "orders": "הזמנות",
    "aov": "שווי הזמנה ממוצע",
    "churn_risk": "לקוחות בסיכון נטישה",
}


def summary_sentence(metric: str, template: str, params: dict) -> str:
    """English one-line description built from stored params, never stored
    text -- summary_sentence_he is the Hebrew counterpart, built from the
    same params (not translated FROM this string)."""
    label = KPI_CATALOG[metric]["label"]
    if template == "pct_change":
        window_label = {"dod": "day-over-day", "wow": "week-over-week", "mom": "month-over-month"}[params["window"]]
        verb = "drops" if params["direction"] == "drop" else "rises"
        return f"{label} {verb} more than {params['threshold_pct']:g}% {window_label}"
    if template == "absolute_threshold":
        op = "above" if params["operator"] == "above" else "below"
        return f"{label} goes {op} {params['value']:g}"
    if template == "anomaly":
        return f"{label} moves more than {params['n_sigma']:g} standard deviations from its 28-day baseline"
    return f"{label} moves in the same direction for {params['n_days']} days in a row"


def summary_sentence_he(metric: str, template: str, params: dict) -> str:
    """Hebrew counterpart to summary_sentence -- see its docstring."""
    label = _METRIC_LABEL_HE.get(metric, KPI_CATALOG[metric]["label"])
    if template == "pct_change":
        window_label = {"dod": "יום מול יום", "wow": "שבוע מול שבוע", "mom": "חודש מול חודש"}[params["window"]]
        verb = "יורד/ת" if params["direction"] == "drop" else "עולה"
        return f"{label} {verb} ביותר מ-{params['threshold_pct']:g}% {window_label}"
    if template == "absolute_threshold":
        op = "מעל" if params["operator"] == "above" else "מתחת ל"
        return f"{label} {op} {params['value']:g}"
    if template == "anomaly":
        return f"{label} סוטה ביותר מ-{params['n_sigma']:g} סטיות תקן מהבסיס של 28 הימים האחרונים"
    return f"{label} נע באותו כיוון במשך {params['n_days']} ימים ברציפות"


def readings_for_alerts_engine(client_id: str, store: OrgAlertsStore) -> list[dict]:
    """Current readings for every enabled, effective org alert, shaped
    exactly like alerts_engine._raw_alert_readings' YAML-sourced dicts so
    both merge through the same _triggered_from_readings/filter_for_scope
    pipeline. One alert's evaluation failure never drops the others."""
    readings = []
    for row in list_effective(client_id, store):
        if not row["enabled"]:
            continue
        try:
            current = alert_templates.evaluate_current(client_id, row["metric"], row["template"], row["params"])
        except Exception:
            continue
        if current["value"] is None:
            continue
        metric_name = KPI_CATALOG[row["metric"]]["metric"]
        meta = _metric(client_id, metric_name) if metric_name else None
        domain = (meta or {}).get("domain") or _FALLBACK_DOMAIN.get(row["metric"])
        sentence = summary_sentence(row["metric"], row["template"], row["params"])
        readings.append(
            {
                "id": row["id"],
                "metric_label": KPI_CATALOG[row["metric"]]["label"],
                "alert_label": row["name"],
                "severity": row["severity"],
                "condition": current["condition"],
                "message_template": f"{sentence} (currently {{value}})",
                "value": current["value"],
                "_domain": domain,
                "_sensitive": (meta or {}).get("sensitive"),
            }
        )
    return readings
