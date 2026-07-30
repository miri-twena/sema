"""
SEMA: template-based alert engine (alert_templates_prompt.md).

Turns "metric + template type + parameters" into a live breach reading, or a
90-day historical dry-run, WITHOUT hand-writing SQL per alert or re-scoping
an arbitrary certified metric to a new date range (that's the agent's job,
via the LLM -- see sema_core.home_config's module docstring for the same
argument re: the KPI catalog). Instead:

  1. ONE fixed, parameterized SQL query per supported metric (revenue/
     orders/aov/churn_risk -- the exact same set sema_core.home_config's
     KPI_CATALOG exposes) fetches a plain daily (date, numerator,
     denominator) series from the read-only role. No per-template SQL, no
     dynamic identifiers, no user text anywhere in the query text -- the
     only bind parameters are the two server-computed anchor dates.
  2. Everything template-specific (percent change, anomaly z-score, streak
     detection, week/month bucketing) is plain pandas over that series --
     ordinary numeric post-processing, not a new SQL-generation surface per
     template. This is also why there is no injection surface for a
     template's own params (threshold_pct, value, n_sigma, n_days): none of
     them ever reach SQL text, so a non-numeric string is rejected by
     Pydantic at the API boundary, long before this module runs.
  3. The result (a single current value + a "<column> <op> <number>"
     condition string) is shaped to plug directly into
     sema_core.alerts_engine's existing _passes/_triggered_from_readings
     pipeline -- unchanged, so org-defined and YAML-defined alerts evaluate
     through the exact same code path (spec accept criterion).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

import pandas as pd

from sema_core.db import run_sql_readonly
from sema_core.home_config import KPI_CATALOG

# ---------------------------------------------------------------------------
# Supported metrics: the fixed KPI_CATALOG set, no open metric picker. `kind`
# controls how a bucket's value is recomputed when re-grouping the daily
# series to a coarser grain (week/month) for pct_change:
#   flow  -- additive across days (revenue, orders): bucket value = sum(num)
#   ratio -- a true average, not an average-of-daily-averages (aov):
#            bucket value = sum(num) / sum(den)
#   stock -- a snapshot, not additive (churn_risk's at-risk count): bucket
#            value = the LAST day's value in that bucket
# ---------------------------------------------------------------------------
_METRIC_SQL = {
    "revenue": {
        "kind": "flow",
        "sql": """
            SELECT DATE_TRUNC('day', order_date)::date AS d, SUM(total_amount) AS num, 1 AS den
            FROM orders
            WHERE status = 'completed' AND order_date >= %(start)s AND order_date <= %(end)s
            GROUP BY 1
        """,
    },
    "orders": {
        "kind": "flow",
        "sql": """
            SELECT DATE_TRUNC('day', order_date)::date AS d, COUNT(*) AS num, 1 AS den
            FROM orders
            WHERE status = 'completed' AND order_date >= %(start)s AND order_date <= %(end)s
            GROUP BY 1
        """,
    },
    "aov": {
        "kind": "ratio",
        "sql": """
            SELECT DATE_TRUNC('day', order_date)::date AS d, SUM(total_amount) AS num, COUNT(*) AS den
            FROM orders
            WHERE status = 'completed' AND order_date >= %(start)s AND order_date <= %(end)s
            GROUP BY 1
        """,
    },
    "churn_risk": {
        "kind": "stock",
        # As-of-day snapshot (same 90-day inactivity definition as
        # churn_risk.yaml), re-evaluated for every day in the fetch window --
        # NOT an additive quantity, so bucketing to week/month later must
        # take the last day's value, never a sum.
        "sql": """
            WITH last_order AS (
                SELECT customer_id, MAX(order_date) AS last_order_date
                FROM orders WHERE status = 'completed'
                GROUP BY customer_id
            ),
            days AS (
                SELECT generate_series(%(start)s::date, %(end)s::date, INTERVAL '1 day')::date AS d
            )
            SELECT days.d AS d, COUNT(last_order.customer_id) AS num, 1 AS den
            FROM days
            LEFT JOIN last_order ON last_order.last_order_date <= days.d - INTERVAL '90 days'
            GROUP BY days.d
        """,
    },
}

SUPPORTED_METRICS = tuple(KPI_CATALOG.keys())  # ("revenue", "orders", "aov", "churn_risk")
assert set(SUPPORTED_METRICS) == set(_METRIC_SQL)

_ANCHOR_SQL = "SELECT MAX(order_date) AS anchor FROM orders WHERE status = 'completed'"

BASELINE_DAYS = 28  # anomaly's fixed lookback (spec item 1)
_FETCH_DAYS_BACK = 460  # comfortably covers a mom/wow lookback + a 90-day dry-run history

TemplateType = Literal["pct_change", "absolute_threshold", "anomaly", "streak"]

TEMPLATE_DEFS: dict[str, dict] = {
    "pct_change": {
        "label": "Percent change",
        "label_he": "שינוי באחוזים",
        "description": "Fires when the metric moves more than X% vs. the same period before.",
        "description_he": 'מופעל כאשר המדד משתנה ביותר מ-X% לעומת התקופה הקודמת.',
        "params": ["window", "direction", "threshold_pct"],
    },
    "absolute_threshold": {
        "label": "Absolute threshold",
        "label_he": "סף מוחלט",
        "description": "Fires when the metric's latest value crosses a fixed number.",
        "description_he": "מופעל כאשר הערך העדכני של המדד חוצה מספר קבוע.",
        "params": ["operator", "value"],
    },
    "anomaly": {
        "label": "Anomaly",
        "label_he": "חריגה",
        "description": "Fires when the metric departs unusually far from its recent 28-day baseline.",
        "description_he": "מופעל כאשר המדד סוטה באופן חריג מהבסיס של 28 הימים האחרונים.",
        "params": ["n_sigma"],
    },
    "streak": {
        "label": "Streak",
        "label_he": "רצף",
        "description": "Fires after N consecutive days moving in the same direction.",
        "description_he": "מופעל לאחר N ימים רצופים בכיוון זהה.",
        "params": ["n_days", "direction"],
    },
}


class AlertTemplateError(Exception):
    """Raised for an unsupported metric/template or malformed params."""


def _require_metric(metric: str) -> None:
    if metric not in SUPPORTED_METRICS:
        raise AlertTemplateError(
            f"Unsupported metric '{metric}'. Alert templates only support: {', '.join(SUPPORTED_METRICS)}."
        )


def _anchor_date(client_id: str) -> date:
    df = run_sql_readonly(_ANCHOR_SQL, client_id=client_id)
    if df.empty or pd.isna(df.iloc[0, 0]):
        raise AlertTemplateError("No order data available to evaluate alerts against.")
    value = df.iloc[0, 0]
    return value.date() if hasattr(value, "date") else value


def _daily_series(client_id: str, metric: str, anchor: date) -> pd.DataFrame:
    """Raw (d, num, den) rows for [anchor - _FETCH_DAYS_BACK, anchor], one row
    per day that has data (days with zero activity are simply absent -- the
    reindex below fills them with 0 so a quiet day never breaks a streak/
    rolling-window computation)."""
    _require_metric(metric)
    start = anchor - timedelta(days=_FETCH_DAYS_BACK)
    df = run_sql_readonly(
        _METRIC_SQL[metric]["sql"], params={"start": start, "end": anchor}, client_id=client_id
    )
    if df.empty:
        return df
    df["d"] = pd.to_datetime(df["d"])
    df = df.set_index("d").sort_index()
    full_index = pd.date_range(start=start, end=anchor, freq="D")
    df = df.reindex(full_index, fill_value=0)
    df.index.name = "d"
    return df.reset_index()


_GRAIN_FREQ = {"dod": "D", "wow": "W", "mom": "MS"}


def _bucketed_value(df: pd.DataFrame, kind: str, freq: str) -> pd.Series:
    """Resample the daily (num, den) series to `freq`, returning ONE value
    per bucket per this metric's `kind` (see module docstring)."""
    g = df.set_index("d").resample(freq)
    if kind == "flow":
        return g["num"].sum()
    if kind == "ratio":
        summed = g[["num", "den"]].sum().astype(float)
        return summed["num"] / summed["den"].mask(summed["den"] == 0)
    # stock: last day's value in the bucket
    return g["num"].last()


def _metric_kind(metric: str) -> str:
    return _METRIC_SQL[metric]["kind"]


def _pct_change_series(client_id: str, metric: str, window: str, anchor: date) -> pd.Series:
    if window not in _GRAIN_FREQ:
        raise AlertTemplateError(f"Unsupported window '{window}'. Use dod, wow, or mom.")
    daily = _daily_series(client_id, metric, anchor)
    if daily.empty:
        return pd.Series(dtype=float)
    bucketed = _bucketed_value(daily, _metric_kind(metric), _GRAIN_FREQ[window])
    return (bucketed.pct_change() * 100).round(1)


def _absolute_series(client_id: str, metric: str, anchor: date) -> pd.Series:
    daily = _daily_series(client_id, metric, anchor)
    if daily.empty:
        return pd.Series(dtype=float)
    return _bucketed_value(daily, _metric_kind(metric), "D")


def _anomaly_series(client_id: str, metric: str, anchor: date) -> pd.Series:
    values = _absolute_series(client_id, metric, anchor)
    if values.empty:
        return pd.Series(dtype=float)
    baseline_mean = values.shift(1).rolling(BASELINE_DAYS).mean()
    baseline_std = values.shift(1).rolling(BASELINE_DAYS).std()
    z = (values - baseline_mean) / baseline_std.mask(baseline_std == 0)
    return z.abs().round(2)


def _streak_series(client_id: str, metric: str, anchor: date, n_days: int, direction: str) -> pd.Series:
    values = _absolute_series(client_id, metric, anchor)
    if values.empty:
        return pd.Series(dtype=float)
    delta = values.diff()
    qualifies = (delta < 0) if direction == "drop" else (delta > 0)
    hit = qualifies.rolling(n_days, min_periods=n_days).apply(lambda w: 1.0 if w.all() else 0.0)
    return hit


def _pct_condition(direction: str, threshold_pct: float) -> str:
    if direction == "drop":
        return f"value < {-abs(threshold_pct)}"
    return f"value > {abs(threshold_pct)}"


def _abs_condition(operator_: str, value: float) -> str:
    return f"value > {value}" if operator_ == "above" else f"value < {value}"


def validate_params(template: str, params: dict) -> dict:
    """Type/range-check params for a template, returning a normalized dict.
    Raises AlertTemplateError with a human message on anything invalid --
    this is the ONE place a bad `value`/`threshold_pct`/`n_days`/`n_sigma`
    (e.g. a non-numeric injection attempt) gets rejected, before any of it
    is used to build a condition string or touch SQL."""
    if template not in TEMPLATE_DEFS:
        raise AlertTemplateError(f"Unknown template '{template}'.")
    try:
        if template == "pct_change":
            window = str(params["window"])
            direction = str(params["direction"])
            threshold_pct = float(params["threshold_pct"])
            if window not in _GRAIN_FREQ:
                raise AlertTemplateError("window must be dod, wow, or mom.")
            if direction not in ("drop", "rise"):
                raise AlertTemplateError("direction must be drop or rise.")
            if not (0 < threshold_pct <= 100):
                raise AlertTemplateError("threshold_pct must be between 0 and 100.")
            return {"window": window, "direction": direction, "threshold_pct": threshold_pct}
        if template == "absolute_threshold":
            operator_ = str(params["operator"])
            value = float(params["value"])
            if operator_ not in ("above", "below"):
                raise AlertTemplateError("operator must be above or below.")
            return {"operator": operator_, "value": value}
        if template == "anomaly":
            n_sigma = float(params.get("n_sigma", 2))
            if not (0 < n_sigma <= 10):
                raise AlertTemplateError("n_sigma must be between 0 and 10.")
            return {"n_sigma": n_sigma}
        # streak
        n_days = int(params["n_days"])
        direction = str(params["direction"])
        if not (1 < n_days <= 30):
            raise AlertTemplateError("n_days must be between 2 and 30.")
        if direction not in ("drop", "rise"):
            raise AlertTemplateError("direction must be drop or rise.")
        return {"n_days": n_days, "direction": direction}
    except (KeyError, TypeError, ValueError) as exc:
        raise AlertTemplateError(f"Invalid parameters for template '{template}': {exc}") from None


def _series_and_condition(client_id: str, metric: str, template: str, params: dict, anchor: date) -> tuple[pd.Series, str]:
    """Assumes metric/params were already validated by the caller (before any
    DB call -- see evaluate_current/dry_run)."""
    p = validate_params(template, params)
    if template == "pct_change":
        series = _pct_change_series(client_id, metric, p["window"], anchor)
        condition = _pct_condition(p["direction"], p["threshold_pct"])
    elif template == "absolute_threshold":
        series = _absolute_series(client_id, metric, anchor)
        condition = _abs_condition(p["operator"], p["value"])
    elif template == "anomaly":
        series = _anomaly_series(client_id, metric, anchor)
        condition = f"value > {p['n_sigma']}"
    else:
        series = _streak_series(client_id, metric, anchor, p["n_days"], p["direction"])
        condition = "value == 1"
    return series, condition


def evaluate_current(client_id: str, metric: str, template: str, params: dict) -> dict:
    """The latest reading: {value: float|None, condition: str}. `value` is
    None when there isn't enough history yet (e.g. a fresh dataset without
    28 days for an anomaly baseline) -- callers should treat that as "not
    breaching", never as a breach."""
    _require_metric(metric)  # fail fast on a bad metric/params BEFORE any DB call
    validate_params(template, params)
    anchor = _anchor_date(client_id)
    series, condition = _series_and_condition(client_id, metric, template, params, anchor)
    if series.empty:
        return {"value": None, "condition": condition}
    last = series.iloc[-1]
    value = None if pd.isna(last) else float(last)
    return {"value": value, "condition": condition}


def dry_run(client_id: str, metric: str, template: str, params: dict, days: int = 90) -> dict:
    """Historical dry-run: how many times would this alert have fired in the
    last `days` days, and on which dates. Required before an org alert can be
    created or (re-)enabled (spec item 4)."""
    try:
        _require_metric(metric)  # fail fast on a bad metric/params BEFORE any DB call
        validate_params(template, params)
        anchor = _anchor_date(client_id)
        series, condition = _series_and_condition(client_id, metric, template, params, anchor)
    except AlertTemplateError as exc:
        return {"ok": False, "error": str(exc), "fire_count": 0, "fire_dates": []}
    except Exception:
        return {"ok": False, "error": "Could not evaluate this alert against the client's data.", "fire_count": 0, "fire_dates": []}

    if series.empty:
        return {"ok": True, "fire_count": 0, "fire_dates": []}

    from sema_core.alerts_engine import _passes  # local import: avoid a cycle at module load time

    window_start = anchor - timedelta(days=days)
    fire_dates: list[str] = []
    for idx, value in series.items():
        period_end = idx.date() if hasattr(idx, "date") else idx
        if period_end < window_start or period_end > anchor:
            continue
        if pd.isna(value):
            continue
        if _passes(condition, float(value)):
            fire_dates.append(period_end.isoformat())
    return {"ok": True, "fire_count": len(fire_dates), "fire_dates": fire_dates}
