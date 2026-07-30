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
from dataclasses import dataclass
from datetime import date

import pandas as pd

from sema_core import data_scope, queries
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


def _resolve_window(
    start: str | None, end: str | None, selectable: list[str], default_months: int = 1
) -> tuple[str, str]:
    """Resolve the requested period against the months we actually have.

    Unknown or inverted input falls back to the default -- the latest
    `default_months` complete months (spec §1's home-config
    "default_period_months") -- rather than erroring: a stale bookmark or a
    hand-edited query string must not break the page.
    """
    valid = set(selectable)
    s = start if start in valid else None
    e = end if end in valid else None
    if s is None and e is None:
        span = max(1, min(default_months, len(selectable)))
        return selectable[-span], selectable[-1]
    s = s or e
    e = e or s
    return (e, s) if s > e else (s, e)  # type: ignore[return-value]


@dataclass(frozen=True)
class ResolvedPeriod:
    """The selected month window plus its comparison baseline.

    THE single definition of "the selected period" and "the prior window" for
    the Business Overview's KPI cards (the Daily Brief, sema_core/daily_brief.py,
    is day-grained and computes its own windows independently).

    `baseline` is None unless the FULL prior window exists -- a partial
    baseline would understate the comparison and produce a misleading delta.
    """

    start: str
    end: str
    label: str
    months: int
    selectable: list[str]
    window: pd.DataFrame
    baseline: pd.DataFrame | None
    baseline_start: str | None
    baseline_end: str | None
    baseline_label: str | None


def resolve_period(
    start: str | None = None, end: str | None = None, default_months: int = 1
) -> ResolvedPeriod | None:
    """Resolve a requested month range against the data this client actually has.

    Returns None when the revenue-by-month report is empty or unavailable --
    callers decide whether that means "no cards" or "no brief". `start`/`end`
    are month keys ("2026-05"); omit both for the default window, the latest
    `default_months` complete months (1 unless a home config says otherwise).
    """
    df = queries.get_revenue_by_month()
    if df is None or df.empty:
        return None

    df = df.copy()
    df["key"] = df["month"].map(_month_key)
    df = df.sort_values("key")
    # Fall back to every month if none is provably complete, rather than
    # resolving to an empty period.
    selectable = _complete_months(list(df["key"]), _max_order_date()) or list(df["key"])
    resolved_start, resolved_end = _resolve_window(start, end, selectable, default_months)

    window = df[(df["key"] >= resolved_start) & (df["key"] <= resolved_end)]
    months = len(window)
    prior = df[df["key"] < resolved_start].tail(months) if months else df.iloc[0:0]
    baseline = prior if months and len(prior) == months else None

    baseline_start = str(prior["key"].iloc[0]) if baseline is not None else None
    baseline_end = str(prior["key"].iloc[-1]) if baseline is not None else None

    return ResolvedPeriod(
        start=resolved_start,
        end=resolved_end,
        label=_period_label(resolved_start, resolved_end),
        months=months,
        selectable=selectable,
        window=window,
        baseline=baseline,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        baseline_label=(
            _period_label(baseline_start, baseline_end)
            if baseline_start and baseline_end
            else None
        ),
    )


def _period_kpis(period: ResolvedPeriod, deltas: dict[str, bool]) -> dict[str, dict]:
    """Revenue / Orders / AOV for the selected window, vs the prior window,
    keyed by their home_config.KPI_CATALOG id. `deltas` (home config's
    per-KPI delta toggle) suppresses the delta/delta_label fields for a KPI
    the admin chose to show as a bare number."""
    window, baseline = period.window, period.baseline
    if window.empty:
        return {}

    months = period.months
    revenue = float(window["revenue"].sum())
    orders = int(window["order_count"].sum())
    prev_revenue = float(baseline["revenue"].sum()) if baseline is not None else None
    prev_orders = int(baseline["order_count"].sum()) if baseline is not None else None

    period_label = period.label
    delta_label = "vs prior month" if months == 1 else f"vs prior {months} months"

    out = {
        "revenue": {
            "label": f"Revenue · {period_label}",
            "value": round(revenue, 2),
            "format": "currency",
            "delta": _pct_change(revenue, prev_revenue) if deltas.get("revenue", True) else None,
            "delta_label": delta_label if deltas.get("revenue", True) else None,
        },
        "orders": {
            "label": f"Orders · {period_label}",
            "value": orders,
            "format": "number",
            "delta": _pct_change(orders, prev_orders) if deltas.get("orders", True) else None,
            "delta_label": delta_label if deltas.get("orders", True) else None,
        },
    }
    if orders:
        aov = revenue / orders
        prev_aov = prev_revenue / prev_orders if prev_revenue and prev_orders else None
        out["aov"] = {
            "label": f"AOV · {period_label}",
            "value": round(aov, 2),
            "format": "currency",
            "delta": _pct_change(aov, prev_aov) if deltas.get("aov", True) else None,
            "delta_label": delta_label if deltas.get("aov", True) else None,
        }
    return out


def build_overview(
    start: str | None = None, end: str | None = None, scope_id: str = "full", config: dict | None = None
) -> dict:
    """Headline KPIs for the active client's home dashboard.

    `start`/`end` are month keys ("2026-05"); omit both for the default
    window (the latest complete month, or `config`'s default_period_months).
    Returns the KPIs plus the resolved window and the months a user may
    select, so the UI's period picker can only offer periods that actually
    have complete data.

    `scope_id` (sema_core.data_scope) drops KPIs outside the requester's data
    access: Revenue/Orders/AOV are the `sales` domain, At-Risk Customers is
    `customers`. 'full' (the default) never drops anything.

    `config` is the client's effective home config (sema_core.home_config) --
    which KPIs to show, in what order, with or without a delta. None (every
    caller before this feature shipped, and any client with nothing
    published) falls back to home_config.DEFAULT_CONFIG, reproducing the
    exact original behavior: Revenue, Orders, AOV, At-Risk Customers, all
    four, all with deltas where meaningful.
    """
    from sema_core import home_config

    cfg = config or home_config.DEFAULT_CONFIG
    kpi_order = cfg["kpis"]["order"]
    kpi_deltas = cfg["kpis"]["deltas"]

    resolved_start: str | None = None
    resolved_end: str | None = None
    selectable: list[str] = []
    kpi_by_id: dict[str, dict] = {}

    try:
        period = resolve_period(start, end, cfg["default_period_months"])
        if period is not None:
            selectable = period.selectable
            resolved_start, resolved_end = period.start, period.end
            if data_scope.domain_allowed("sales", scope_id):
                kpi_by_id.update(_period_kpis(period, kpi_deltas))
    except Exception:
        logger.warning("overview: revenue_by_month unavailable for this client", exc_info=True)

    # Churn risk is a right-now snapshot (customers with no completed order in
    # the last 90 days), so it isn't scoped by the selected period.
    if "churn_risk" in kpi_order:
        try:
            at_risk = queries.get_at_risk_customers()
            if at_risk is not None and data_scope.domain_allowed("customers", scope_id):
                kpi_by_id["churn_risk"] = {
                    "label": "At-Risk Customers",
                    "value": int(len(at_risk)),
                    "format": "number",
                }
        except Exception:
            logger.warning("overview: at_risk_customers unavailable for this client", exc_info=True)

    # Preserve the admin's chosen order; silently drop an id whose data isn't
    # available (report failed, scope blocked it, ...) rather than erroring.
    kpis = [kpi_by_id[k] for k in kpi_order if k in kpi_by_id]

    return {
        "kpis": kpis,
        "start": resolved_start,
        "end": resolved_end,
        "available_months": selectable,
    }
