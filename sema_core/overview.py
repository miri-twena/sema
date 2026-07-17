"""
SEMA: home-dashboard overview KPIs.

Computes the headline numbers for the React app's Business Overview section
by reusing the saved report library (queries.py) -- no new business logic,
just windowing and period-over-period math on reports that already exist.

Period rules:
  - Months are the grain, because that's the grain revenue_by_month.sql has.
  - The default period is the latest COMPLETE month: a month still in progress
    (the data stops before its last day) is never the default and is never
    offered as a choice, so the dashboard can't open on a half-empty month.
  - "Complete" is judged against the newest order date in the DATA, not the
    wall clock -- the same convention at_risk_customers.sql and the churn_risk
    alerts already use for "now". A lagging data feed therefore shows the last
    real month instead of an empty current one.
  - The comparison baseline is the window of equal length immediately before
    the selected one (one month -> prior month; three months -> prior three).

Each block is computed independently and skipped on failure, so a client whose
database doesn't have these reports (e.g. the insurance demo client) gets fewer
cards instead of an error. The KPI dicts match the API's Kpi contract, so the
frontend renders them with the same KpiCards component it uses for chat answers.
"""

from __future__ import annotations

import calendar
from datetime import date

import pandas as pd

from sema_core import queries
from sema_core.obs import get_logger

logger = get_logger("overview")


def _month_key(value) -> str:
    """A month bucket -> its sortable key, e.g. "2026-05"."""
    return pd.Timestamp(value).strftime("%Y-%m")


def _month_label(key: str) -> str:
    """"2026-05" -> "May 2026"."""
    return pd.Timestamp(f"{key}-01").strftime("%b %Y")


def _month_end(key: str) -> date:
    """The last calendar day of a month key."""
    year, month = int(key[:4]), int(key[5:7])
    return date(year, month, calendar.monthrange(year, month)[1])


def _period_label(start: str, end: str) -> str:
    return _month_label(end) if start == end else f"{_month_label(start)} – {_month_label(end)}"


def _pct_change(current: float, previous: float | None) -> float | None:
    """Period-over-period % change, or None when there's no baseline window."""
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def _max_order_date() -> date | None:
    """Newest order date in the data -- the dataset's own "today"."""
    try:
        df = queries.get_data_bounds()
        if df is None or df.empty:
            return None
        value = df.iloc[0]["max_order_date"]
        return None if pd.isna(value) else pd.Timestamp(value).date()
    except Exception:
        logger.warning("overview: data bounds unavailable for this client", exc_info=True)
        return None


def _complete_months(keys: list[str], max_date: date | None) -> list[str]:
    """Months the data covers in full. Without a known max date we can't tell a
    partial month from a complete one, so every month is treated as complete
    rather than hiding real data."""
    if max_date is None:
        return list(keys)
    return [k for k in keys if _month_end(k) <= max_date]


def _resolve_window(start: str | None, end: str | None, selectable: list[str]) -> tuple[str, str]:
    """Resolve the requested period against the months we actually have.

    Unknown or inverted input falls back to the default (the latest complete
    month) rather than erroring -- a stale bookmark or a hand-edited query
    string must not break the page.
    """
    valid = set(selectable)
    s = start if start in valid else None
    e = end if end in valid else None
    if s is None and e is None:
        latest = selectable[-1]
        return latest, latest
    s = s or e
    e = e or s
    return (e, s) if s > e else (s, e)  # type: ignore[return-value]


def _period_kpis(df: pd.DataFrame, start: str, end: str) -> list[dict]:
    """Revenue / Orders / AOV for the selected window, vs the prior window."""
    window = df[(df["key"] >= start) & (df["key"] <= end)]
    if window.empty:
        return []

    months = len(window)
    # Baseline: the same number of months immediately before the window. Only
    # used when ALL of them are present, so a partial baseline can't produce a
    # misleading delta.
    prior = df[df["key"] < start].tail(months)
    baseline = prior if len(prior) == months else None

    revenue = float(window["revenue"].sum())
    orders = int(window["order_count"].sum())
    prev_revenue = float(baseline["revenue"].sum()) if baseline is not None else None
    prev_orders = int(baseline["order_count"].sum()) if baseline is not None else None

    period = _period_label(start, end)
    delta_label = "vs prior month" if months == 1 else f"vs prior {months} months"

    kpis = [
        {
            "label": f"Revenue · {period}",
            "value": round(revenue, 2),
            "format": "currency",
            "delta": _pct_change(revenue, prev_revenue),
            "delta_label": delta_label,
        },
        {
            "label": f"Orders · {period}",
            "value": orders,
            "format": "number",
            "delta": _pct_change(orders, prev_orders),
            "delta_label": delta_label,
        },
    ]
    if orders:
        aov = revenue / orders
        prev_aov = prev_revenue / prev_orders if prev_revenue and prev_orders else None
        kpis.append(
            {
                "label": f"AOV · {period}",
                "value": round(aov, 2),
                "format": "currency",
                "delta": _pct_change(aov, prev_aov),
                "delta_label": delta_label,
            }
        )
    return kpis


def build_overview(start: str | None = None, end: str | None = None) -> dict:
    """Headline KPIs for the active client's home dashboard.

    `start`/`end` are month keys ("2026-05"); omit both for the default (the
    latest complete month). Returns the KPIs plus the resolved window and the
    months a user may select, so the UI's period picker can only offer periods
    that actually have complete data.
    """
    resolved_start: str | None = None
    resolved_end: str | None = None
    selectable: list[str] = []
    kpis: list[dict] = []

    try:
        df = queries.get_revenue_by_month()
        if df is not None and not df.empty:
            df = df.copy()
            df["key"] = df["month"].map(_month_key)
            df = df.sort_values("key")
            # Fall back to every month if none is provably complete, rather
            # than rendering an empty overview.
            selectable = _complete_months(list(df["key"]), _max_order_date()) or list(df["key"])
            resolved_start, resolved_end = _resolve_window(start, end, selectable)
            kpis.extend(_period_kpis(df, resolved_start, resolved_end))
    except Exception:
        logger.warning("overview: revenue_by_month unavailable for this client", exc_info=True)

    # Churn risk is a right-now snapshot (customers with no completed order in
    # the last 90 days), so it isn't scoped by the selected period.
    try:
        at_risk = queries.get_at_risk_customers()
        if at_risk is not None:
            kpis.append(
                {
                    "label": "At-Risk Customers",
                    "value": int(len(at_risk)),
                    "format": "number",
                }
            )
    except Exception:
        logger.warning("overview: at_risk_customers unavailable for this client", exc_info=True)

    return {
        "kpis": kpis,
        "start": resolved_start,
        "end": resolved_end,
        "available_months": selectable,
    }
