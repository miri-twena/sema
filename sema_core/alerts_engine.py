"""
SEMA: alerts engine.

Scans the active client's semantic YAML for `alerts` entries, runs each
alert's SQL, evaluates its condition, and returns the list of triggered
alerts.

Decoupled from the agent: it runs directly against the read-only connection,
not through Claude. Think of it like a set of scheduled CHECK queries that
return rows (the breaches) instead of blocking writes.

Cached per client for 2 minutes so it runs once every couple of minutes, not
on every chat message / rerun.
"""

from __future__ import annotations

import operator
import re
import sys

from sema_core import data_scope
from sema_core.agent.semantic import load_semantic_layer
from sema_core.cache import ttl_cache
from sema_core.client_registry import active_client_id
from sema_core.db import run_sql_readonly

# Supported comparison operators for an alert `condition`. Longer tokens first
# so "<=" / ">=" are matched before "<" / ">".
_OPS = {
    "<=": operator.le,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
}

# A condition is "<column> <op> <number>", e.g. "mom_pct_change < -8".
_COND_RE = re.compile(r"^\s*(\w+)\s*(<=|>=|==|!=|<|>)\s*(-?\d+(?:\.\d+)?)\s*$")

# Sort key: critical alerts first, then warnings, then anything else.
_SEVERITY_ORDER = {"critical": 0, "warning": 1}


def _passes(condition: str, value) -> bool:
    """True if `value` satisfies the alert's condition string."""
    match = _COND_RE.match(condition or "")
    if not match or value is None:
        return False
    _column, op_token, threshold = match.groups()
    try:
        return _OPS[op_token](float(value), float(threshold))
    except (TypeError, ValueError):
        return False


def _format_value(value) -> str:
    """Render the breach value for the message: 300.0 -> "300", -16.3 -> "-16.3"."""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def _override_threshold(condition: str, new_threshold: float) -> str:
    """Rebuild an alert's "<column> <op> <number>" condition string with a
    different threshold, keeping the column and comparison operator as
    authored (home config only overrides the number, spec item 11)."""
    match = _COND_RE.match(condition or "")
    if not match:
        return condition
    column, op_token, _old = match.groups()
    return f"{column} {op_token} {new_threshold}"


def catalog(client_id: str | None = None) -> list[dict]:
    """Every alert this client's semantic layer defines, metadata only (no
    SQL execution) -- backs the admin Home-config editor's alert picker
    (spec item 11), which needs every POSSIBLE alert, not just today's
    triggered subset."""
    try:
        metrics = load_semantic_layer(client_id or active_client_id())
    except Exception:
        return []
    out = []
    for metric in metrics:
        for alert in metric.get("alerts") or []:
            out.append(
                {
                    "id": alert["id"],
                    "label": alert.get("label", alert["id"]),
                    "metric_label": metric.get("label", metric.get("name", "")),
                    "severity": alert.get("severity", "warning") if alert.get("severity") in ("critical", "warning") else "warning",
                }
            )
    return out


def evaluate_all_alerts(client_id: str | None = None, alert_config: dict | None = None) -> list[dict]:
    """Triggered alerts for the given (or currently-active) client, critical
    first. Each dict carries internal `_domain`/`_sensitive` keys for
    filter_for_scope; strip them (or call filter_for_scope, which does) before
    handing a raw dict to the API's Alert model.

    `alert_config` is home config's per-alert-id `{"enabled": bool,
    "threshold": float | None}` map -- None (every caller before this
    feature shipped, and any client with nothing published) reproduces
    today's behavior exactly: every alert enabled at its metric-file default
    threshold. Applied AFTER the cached raw readings (_raw_alert_readings),
    so a threshold change never needs to bust or bypass that cache."""
    readings = _raw_alert_readings(client_id or active_client_id())
    return _triggered_from_readings(readings, alert_config or {})


def filter_for_scope(alerts: list[dict], scope_id: str) -> list[dict]:
    """Drop alerts whose owning metric is outside this requester's
    data-access scope (sema_core.data_scope), and strip the internal
    `_domain`/`_sensitive` keys from what's kept -- applied AFTER
    evaluate_all_alerts's per-client cache, so one user's scope never leaks
    into another's cached alert list."""
    preset = data_scope.preset(scope_id)
    out = []
    for a in alerts:
        if a.get("_sensitive") and preset.blocks_sensitive:
            continue
        if not preset.domain_allowed(a.get("_domain")):
            continue
        out.append({k: v for k, v in a.items() if not k.startswith("_")})
    return out


# Framework-neutral TTL cache (was @st.cache_data): keyed by client_id arg.
# Returns EVERY alert's raw reading, breach or not, at its metric-file
# DEFAULT condition -- config-independent and therefore safe to cache
# (a dict, unlike a home-config override, is never part of this cache key).
# Deciding which readings are actual breaches (_triggered_from_readings)
# happens outside the cache, so a threshold override or enabled/disabled
# toggle never needs to invalidate it.
@ttl_cache(ttl=120)
def _raw_alert_readings(client_id: str) -> list[dict]:
    try:
        metrics = load_semantic_layer(client_id)
    except Exception as exc:  # missing/invalid semantic layer -> no alerts
        print(f"[alerts] could not load semantic layer for {client_id}: {exc}", file=sys.stderr)
        return []

    readings: list[dict] = []
    for metric in metrics:
        for alert in metric.get("alerts") or []:
            # One bad alert must never take down the whole panel.
            try:
                df = run_sql_readonly(alert["sql"], client_id=client_id)
                if df is None or df.empty:
                    continue
                value = df.iloc[0, 0]
                if hasattr(value, "item"):  # numpy scalar -> python scalar
                    value = value.item()
                # Normalize so the API contract's Literal["critical","warning"]
                # can't be broken by a typo in a metric YAML.
                severity = alert.get("severity", "warning")
                if severity not in ("critical", "warning"):
                    severity = "warning"
                readings.append(
                    {
                        "id": alert["id"],
                        "metric_label": metric.get("label", metric.get("name", "")),
                        "alert_label": alert.get("label", alert["id"]),
                        "severity": severity,
                        "condition": alert.get("condition", ""),
                        "message_template": alert.get("message_template", ""),
                        "value": value,
                        # Internal-only (sema_core.data_scope): stripped by
                        # filter_for_scope before an alert reaches the API's
                        # Alert model, which has no domain/sensitive fields.
                        "_domain": metric.get("domain"),
                        "_sensitive": metric.get("sensitive"),
                    }
                )
            except Exception as exc:
                print(f"[alerts] alert '{alert.get('id')}' failed: {exc}", file=sys.stderr)
                continue
    return readings


def _triggered_from_readings(readings: list[dict], alert_config: dict) -> list[dict]:
    """Decide which raw readings are actual breaches: skip an alert home
    config disabled, apply its threshold override (if any) before the
    pass/fail check, then build the same public shape _evaluate used to
    return directly."""
    triggered: list[dict] = []
    for r in readings:
        cfg = alert_config.get(r["id"], {})
        if cfg.get("enabled") is False:
            continue
        condition = r["condition"]
        threshold = cfg.get("threshold")
        if threshold is not None:
            condition = _override_threshold(condition, threshold)
        if not _passes(condition, r["value"]):
            continue
        message = r["message_template"].replace("{value}", _format_value(r["value"]))
        triggered.append(
            {
                "id": r["id"],
                "metric_label": r["metric_label"],
                "alert_label": r["alert_label"],
                "severity": r["severity"],
                "message": message,
                "value": r["value"],
                "_domain": r["_domain"],
                "_sensitive": r["_sensitive"],
            }
        )
    triggered.sort(key=lambda a: _SEVERITY_ORDER.get(a["severity"], 99))
    return triggered
