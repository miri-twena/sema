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

import streamlit as st

from agent.semantic import load_semantic_layer
from client_registry import active_client_id
from db import run_sql_readonly

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


def evaluate_all_alerts() -> list[dict]:
    """Triggered alerts for the currently-active client (critical first)."""
    return _evaluate(active_client_id())


@st.cache_data(ttl=120)
def _evaluate(client_id: str) -> list[dict]:
    try:
        metrics = load_semantic_layer(client_id)
    except Exception as exc:  # missing/invalid semantic layer -> no alerts
        print(f"[alerts] could not load semantic layer for {client_id}: {exc}", file=sys.stderr)
        return []

    triggered: list[dict] = []
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
                if not _passes(alert.get("condition", ""), value):
                    continue
                message = alert.get("message_template", "").replace("{value}", _format_value(value))
                triggered.append(
                    {
                        "id": alert["id"],
                        "metric_label": metric.get("label", metric.get("name", "")),
                        "alert_label": alert.get("label", alert["id"]),
                        "severity": alert.get("severity", "warning"),
                        "message": message,
                        "value": value,
                    }
                )
            except Exception as exc:
                print(f"[alerts] alert '{alert.get('id')}' failed: {exc}", file=sys.stderr)
                continue

    triggered.sort(key=lambda a: _SEVERITY_ORDER.get(a["severity"], 99))
    return triggered
