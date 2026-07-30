"""
SEMA: the home dashboard's Daily Brief -- two layers, separating freshness
from insight.

  Layer 1 (pulse): revenue/orders/conversion for yesterday, with a 14-day
  spark and a same-weekday-vs-prior-4-weeks status. ALWAYS renders -- this is
  what makes the brief change every day, even when nothing is notable.

  Layer 2 (insights): up to 3 ranked attention cards, one from each of 6
  deterministic SQL-backed generators, each independently gated by its own
  threshold. An empty list is a normal, quiet-day response -- the whole point
  of gating is that most days should say nothing extra.

Diversity rule: at most one insight per underlying business metric (revenue,
orders, conversion, campaign ROI, VIP customers, product mix) -- if two
generators both clear their threshold for the same metric on the same day
(e.g. a revenue anomaly AND a revenue MTD pace), only the more severe one
survives; the two are the same "story" from the user's point of view.

Deterministic by design: no model call anywhere in this module, so it's cheap
enough to run on every home-screen load (and is cached a day at a time -- see
build_daily_brief).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Literal

import pandas as pd

from sema_core import data_scope, queries
from sema_core.cache import ttl_cache
from sema_core.client_registry import active_client_id
from sema_core.obs import get_logger

logger = get_logger("daily_brief")

# A yesterday-vs-typical-weekday (or MTD-vs-same-days-last-month) deviation
# smaller than this is normal noise, not news.
ANOMALY_THRESHOLD_PCT = 20.0
# mtd_pace is only an INSIGHT (not just the always-there pulse tiles) once the
# pace is notable -- a quieter bar than the pulse's own ±20%, since "on pace"
# is the expected state for most of a month.
MTD_NOTABLE_PCT = 10.0
# First N days of a month produce a pacing comparison too noisy to trust.
MIN_DAYS_INTO_MONTH = 3
# Need at least this many of the last 4 same-weekday data points to trust the
# average as "typical" rather than a fluke.
MIN_ANOMALY_SAMPLES = 2
# A "record" day needs this many PRIOR days on record, or "best/worst since
# records began three days ago" would be a meaningless claim.
RECORD_LOOKBACK_DAYS = 60
# A campaign has to have been running at least this long before a negative
# ROI is a story rather than early noise.
CAMPAIGN_MIN_DAYS_ACTIVE = 14
MAX_INSIGHTS = 3

_WEEKDAYS_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_WEEKDAYS_FULL = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

_METRIC_LABEL = {"revenue": "Revenue", "orders": "Orders", "conversion": "Conversion"}
_METRIC_FORMAT = {"revenue": "currency", "orders": "number", "conversion": "percent"}


def _days_in_month(d: date) -> int:
    return calendar.monthrange(d.year, d.month)[1]


def _safe(fn: Callable[[], pd.DataFrame], label: str) -> pd.DataFrame | None:
    """A report that can't be computed for this client costs it ONE
    generator, never the whole brief."""
    try:
        df = fn()
        return None if df is None or df.empty else df
    except Exception:
        logger.warning("daily_brief: %s unavailable for this client", label, exc_info=True)
        return None


def _max_date() -> date | None:
    """The dataset's own "today": the newest completed-order date. Reuses
    /api/overview's own data source (get_data_bounds), so the brief and the
    overview can never disagree about what day it is."""
    try:
        df = queries.get_data_bounds()
        if df is None or df.empty:
            return None
        value = df.iloc[0]["max_order_date"]
        return None if pd.isna(value) else pd.Timestamp(value).date()
    except Exception:
        logger.warning("daily_brief: data bounds unavailable for this client", exc_info=True)
        return None


def _merged_daily(orders_df: pd.DataFrame | None, sessions_df: pd.DataFrame | None) -> pd.DataFrame | None:
    """One frame keyed by day: revenue, order_count, and a conversion_pct
    derived from sessions. Outer-joined since the two reports are independent
    queries; missing revenue/orders on a day are real zeros, but a day with no
    session data at all has no conversion rate to report (NaN, not 0)."""
    if orders_df is None and sessions_df is None:
        return None
    if sessions_df is None:
        df = orders_df.copy()
        df["conversion_pct"] = float("nan")
        return df
    if orders_df is None:
        orders_df = pd.DataFrame(columns=["day", "revenue", "order_count"])

    df = orders_df.merge(sessions_df, on="day", how="outer").sort_values("day")
    df["revenue"] = df["revenue"].fillna(0.0)
    df["order_count"] = df["order_count"].fillna(0)
    df["conversion_pct"] = (100.0 * df["converted_count"] / df["session_count"]).where(df["session_count"] > 0)
    return df


def _series(daily: pd.DataFrame, col: str, max_date: date, days: int = 14) -> list[float] | None:
    """The trailing `days` calendar days ending at max_date, as a plain
    number list (the sparkline's raw data) -- None if max_date itself isn't
    in the data (nothing to anchor the tile on) or the column is all-NaN in
    that window (e.g. no session data at all -- conversion has nothing to
    show). Gaps within the window fill to 0 so the sparkline reads as "quiet
    that day", not a broken line."""
    start = max_date - timedelta(days=days - 1)
    idx = [start + timedelta(days=n) for n in range(days)]
    window = daily[(daily["day"].dt.date >= start) & (daily["day"].dt.date <= max_date)]
    if window.empty or col not in window.columns:
        return None
    by_day = window.set_index(window["day"].dt.date)[col]
    if max_date not in by_day.index or pd.isna(by_day.get(max_date)):
        return None
    if by_day.dropna().empty:
        return None
    return [0.0 if pd.isna(by_day.get(d)) else round(float(by_day.get(d)), 2) for d in idx]


def _same_weekday_history(daily: pd.DataFrame, col: str, target: date, weeks: int = 4) -> list[float]:
    """Up to `weeks` values of `col` from the same weekday, in the weeks
    BEFORE `target` -- target itself is what's being compared, not part of
    its own baseline."""
    dates = [target - timedelta(days=7 * n) for n in range(1, weeks + 1)]
    by_day = daily.set_index(daily["day"].dt.date)[col]
    return [float(by_day[d]) for d in dates if d in by_day.index and pd.notna(by_day[d])]


def _deviation(
    daily: pd.DataFrame, col: str, target: date, threshold_pct: float = ANOMALY_THRESHOLD_PCT
) -> tuple[Literal["above", "below", "normal"], float | None]:
    """Yesterday's (or any day's) value vs. the average of the same weekday
    over the prior weeks. "normal" (with no deviation figure) whenever there
    isn't enough history to call it anything else -- silence is correct when
    we can't actually tell. `threshold_pct` is home config's sensitivity
    dial (sema_core.home_config.SENSITIVITY_MULTIPLIER x the default)."""
    by_day = daily.set_index(daily["day"].dt.date)[col]
    if target not in by_day.index or pd.isna(by_day[target]):
        return "normal", None
    history = _same_weekday_history(daily, col, target)
    if len(history) < MIN_ANOMALY_SAMPLES:
        return "normal", None
    typical = sum(history) / len(history)
    if not typical:
        return "normal", None
    deviation_pct = round((float(by_day[target]) - typical) / typical * 100, 1)
    if deviation_pct >= threshold_pct:
        return "above", deviation_pct
    if deviation_pct <= -threshold_pct:
        return "below", deviation_pct
    return "normal", deviation_pct


@dataclass(frozen=True)
class PulseResult:
    """Internal pulse representation -- carries `deviation_pct` so the
    yesterday_anomaly generator can reuse this exact computation instead of
    redoing it; `deviation_pct` is NOT part of the public PulseMetric
    contract (see .to_dict)."""

    metric: str
    label: str
    value: float
    value_format: str
    spark: list[float]
    status: Literal["above", "below", "normal"]
    status_label: str
    deviation_pct: float | None

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "label": self.label,
            "value": self.value,
            "format": self.value_format,
            "spark": self.spark,
            "status": self.status,
            "status_label": self.status_label,
        }


_PULSE_METRICS = (
    ("revenue", "Yesterday revenue", "revenue"),
    ("orders", "Orders", "order_count"),
    ("conversion", "Conversion", "conversion_pct"),
)


def _pulse(daily: pd.DataFrame, max_date: date, anomaly_threshold_pct: float = ANOMALY_THRESHOLD_PCT) -> list[PulseResult]:
    weekday = _WEEKDAYS_SHORT[max_date.weekday()]
    results = []
    for key, label, col in _PULSE_METRICS:
        spark = _series(daily, col, max_date)
        if spark is None:
            continue  # no usable data for this metric -- omit its tile, don't fake one
        status, deviation = _deviation(daily, col, max_date, anomaly_threshold_pct)
        if status == "normal":
            status_label = "In normal range"
        else:
            sign = "+" if status == "above" else ""
            status_label = f"{sign}{deviation:.0f}% vs typical {weekday}"
        results.append(
            PulseResult(
                metric=key,
                label=label,
                value=spark[-1],
                value_format=_METRIC_FORMAT[key],
                spark=spark,
                status=status,
                status_label=status_label,
                deviation_pct=deviation,
            )
        )
    return results


# --- insight generators -------------------------------------------------


def _yesterday_anomaly_candidates(pulse: list[PulseResult], as_of: str) -> list[dict]:
    out = []
    for p in pulse:
        if p.status == "normal" or p.deviation_pct is None:
            continue
        rising = p.status == "above"
        out.append(
            {
                "kind": "yesterday_anomaly",
                "id": f"yesterday_anomaly-{p.metric}-{as_of}",
                "icon": "trending_up" if rising else "trending_down",
                "headline": f"{p.label} was {p.status_label.lstrip('+')} yesterday",
                "detail": (
                    f"{_METRIC_LABEL[p.metric]} came in {'above' if rising else 'below'} "
                    f"the typical value for the day of the week by {abs(p.deviation_pct):.0f}%."
                ),
                "severity": abs(p.deviation_pct),
                "follow_up_question": f"Why was {_METRIC_LABEL[p.metric].lower()} {'higher' if rising else 'lower'} than usual yesterday?",
                "_metric_group": p.metric,
            }
        )
    return out


def _campaign_negative_roi_candidates(campaigns: pd.DataFrame | None, as_of: str) -> list[dict]:
    if campaigns is None:
        return []
    eligible = campaigns[
        campaigns["roas"].notna()
        & (campaigns["roas"] < 1)
        & (campaigns["days_active"] >= CAMPAIGN_MIN_DAYS_ACTIVE)
        & campaigns["is_active"]
    ]
    if eligible.empty:
        return []
    worst = eligible.sort_values("roas").iloc[0]
    loss = float(worst["spend"]) - float(worst["attributed_revenue"])
    severity = round((1 - float(worst["roas"])) * 100, 1)  # 0-100: how far below break-even
    return [
        {
            "kind": "campaign_negative_roi",
            "id": f"campaign_negative_roi-{int(worst['campaign_id'])}-{as_of}",
            "icon": "warning",
            "headline": f"{worst['campaign_name']} campaign has run at negative ROI for {int(worst['days_active'])} days",
            "detail": (
                f"Spend ${float(worst['spend']):,.0f} against "
                f"${float(worst['attributed_revenue']):,.0f} attributed revenue since it started."
            ),
            "severity": severity,
            "follow_up_question": f"Why is the {worst['campaign_name']} campaign underperforming?",
            "_metric_group": "campaign_roi",
        }
    ]


def _vip_inactive_candidates(vip: pd.DataFrame | None, as_of: str) -> list[dict]:
    if vip is None:
        return []
    count = len(vip)
    worst = vip.sort_values("days_inactive", ascending=False).iloc[0]
    severity = min(count * 20.0, 150.0)
    return [
        {
            "kind": "vip_inactive",
            "id": f"vip_inactive-{as_of}",
            "icon": "customers",
            "headline": f"{count} VIP customer{'s' if count != 1 else ''} inactive 60+ days",
            "detail": (
                f"{worst['customer_name']} hasn't ordered in {int(worst['days_inactive'])} days -- "
                f"${float(worst['revenue_12mo']):,.0f} in trailing 12-month revenue."
            ),
            "severity": severity,
            "follow_up_question": "Which VIP customers have gone quiet and what should we do about it?",
            "_metric_group": "vip_customers",
        }
    ]


def _record_day_candidates(daily: pd.DataFrame, max_date: date, as_of: str) -> list[dict]:
    history = daily[daily["day"].dt.date < max_date]
    if len(history) < RECORD_LOOKBACK_DAYS:
        return []
    window = history.sort_values("day").tail(RECORD_LOOKBACK_DAYS)
    today_row = daily[daily["day"].dt.date == max_date]
    if today_row.empty:
        return []

    out = []
    for key, col in (("revenue", "revenue"), ("orders", "order_count")):
        today_val = float(today_row[col].iloc[0])
        best, worst = float(window[col].max()), float(window[col].min())
        if today_val > best and best > 0:
            kind, extreme, base = "best", today_val, best
        elif today_val < worst:
            kind, extreme, base = "worst", today_val, worst
        else:
            continue
        change_pct = abs((extreme - base) / base * 100) if base else 0.0
        label = _METRIC_LABEL[key]
        fmt = _METRIC_FORMAT[key]
        out.append(
            {
                "kind": "record_day",
                "id": f"record_day-{key}-{as_of}",
                "icon": "record",
                "headline": f"Yesterday was the {kind} day for {label.lower()} in {RECORD_LOOKBACK_DAYS}+ days",
                "detail": f"{label} of {_fmt(today_val, fmt)} vs. the prior {kind} of {_fmt(base, fmt)}.",
                "severity": round(change_pct, 1),
                "follow_up_question": f"What drove yesterday's {kind}-ever {label.lower()}?",
                "_metric_group": key,
            }
        )
    return out


def _product_rank_shift_candidates(products: pd.DataFrame | None, max_date: date, as_of: str) -> list[dict]:
    if products is None:
        return []
    df = products.copy()
    df["month_key"] = pd.to_datetime(df["month"]).dt.strftime("%Y-%m")
    months = sorted(df["month_key"].unique())
    cur_key = max_date.strftime("%Y-%m")
    if cur_key not in months:
        return []
    idx = months.index(cur_key)
    if idx == 0:
        return []  # no prior month to compare against
    prev_key = months[idx - 1]

    cur_top3 = df[df["month_key"] == cur_key].nlargest(3, "revenue")
    prev_top3_ids = set(df[df["month_key"] == prev_key].nlargest(3, "revenue")["product_id"])
    new_entrants = cur_top3[~cur_top3["product_id"].isin(prev_top3_ids)]
    if new_entrants.empty:
        return []

    top = new_entrants.sort_values("revenue", ascending=False).iloc[0]
    return [
        {
            "kind": "product_rank_shift",
            "id": f"product_rank_shift-{int(top['product_id'])}-{as_of}",
            "icon": "product",
            "headline": f"{top['product_name']} entered the top 3 sellers this month",
            "detail": f"${float(top['revenue']):,.0f} in revenue this month -- wasn't in the top 3 last month.",
            "severity": 35.0,  # a rank event, not a continuous magnitude -- fixed mid-tier severity
            "follow_up_question": f"What's driving demand for {top['product_name']}?",
            "_metric_group": "product_mix",
        }
    ]


def _mtd_pace_candidates(
    daily: pd.DataFrame, max_date: date, as_of: str, notable_pct: float = MTD_NOTABLE_PCT
) -> list[dict]:
    day_of_month = max_date.day
    if day_of_month < MIN_DAYS_INTO_MONTH:
        return []

    cur_month_start = max_date.replace(day=1)
    prev_month_end = cur_month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    prev_days = min(day_of_month, _days_in_month(prev_month_start))
    prev_window_end = prev_month_start + timedelta(days=prev_days - 1)

    def _sum(col: str, start: date, end: date) -> float | None:
        mask = (daily["day"].dt.date >= start) & (daily["day"].dt.date <= end)
        window = daily[mask]
        return None if window.empty else float(window[col].sum())

    cur_month_name, prev_month_name = max_date.strftime("%B"), prev_month_end.strftime("%B")
    out = []
    for key, col in (("revenue", "revenue"), ("orders", "order_count")):
        cur_val = _sum(col, cur_month_start, max_date)
        prev_val = _sum(col, prev_month_start, prev_window_end)
        if cur_val is None or not prev_val:
            continue
        change_pct = round((cur_val - prev_val) / prev_val * 100, 1)
        if abs(change_pct) < notable_pct:
            continue  # on-pace is the expected state -- only notable moves are insights
        rising = change_pct > 0
        label, fmt = _METRIC_LABEL[key], _METRIC_FORMAT[key]
        out.append(
            {
                "kind": "mtd_pace",
                "id": f"mtd_pace-{key}-{as_of}",
                "icon": "trending_up" if rising else "trending_down",
                "headline": (
                    f"{label} {'are' if key == 'orders' else 'is'} pacing {abs(change_pct):.1f}% "
                    f"{'above' if rising else 'below'} {prev_month_name}"
                ),
                "detail": (
                    f"{day_of_month} days into {cur_month_name}: {_fmt(cur_val, fmt)} vs "
                    f"{_fmt(prev_val, fmt)} in the same days of {prev_month_name}."
                ),
                "severity": abs(change_pct),
                "follow_up_question": f"What's driving the {'increase' if rising else 'decrease'} in {label.lower()} pace this month?",
                "_metric_group": key,
            }
        )
    return out


def _fmt(v: float, value_format: str) -> str:
    return f"${v:,.0f}" if value_format == "currency" else f"{v:,.0f}"


def _rank_and_diversify(candidates: list[dict], max_n: int = MAX_INSIGHTS) -> list[dict]:
    """Keep only the most severe candidate per metric group (two generators
    agreeing on the same story is not two stories), then the top N overall."""
    best_per_group: dict[str, dict] = {}
    for c in candidates:
        group = c["_metric_group"]
        if group not in best_per_group or c["severity"] > best_per_group[group]["severity"]:
            best_per_group[group] = c
    ranked = sorted(best_per_group.values(), key=lambda c: -c["severity"])[:max_n]
    return [{k: v for k, v in c.items() if k != "_metric_group"} for c in ranked]


def _build(
    anomaly_threshold_pct: float = ANOMALY_THRESHOLD_PCT, mtd_notable_pct: float = MTD_NOTABLE_PCT
) -> dict:
    max_date = _max_date()
    if max_date is None:
        return {"as_of": None, "pulse": [], "insights": []}
    as_of = max_date.isoformat()

    orders_df = _safe(queries.get_daily_orders, "daily_orders")
    sessions_df = _safe(queries.get_daily_sessions, "daily_sessions")
    daily = _merged_daily(orders_df, sessions_df)
    pulse = _pulse(daily, max_date, anomaly_threshold_pct) if daily is not None else []
    if not pulse:
        return {"as_of": as_of, "pulse": [], "insights": []}

    candidates: list[dict] = []
    candidates += _yesterday_anomaly_candidates(pulse, as_of)
    candidates += _campaign_negative_roi_candidates(_safe(queries.get_campaign_roi_status, "campaign_roi_status"), as_of)
    candidates += _vip_inactive_candidates(_safe(queries.get_vip_inactive, "vip_inactive"), as_of)
    candidates += _record_day_candidates(daily, max_date, as_of)
    candidates += _product_rank_shift_candidates(
        _safe(queries.get_product_revenue_by_month, "product_revenue_by_month"), max_date, as_of
    )
    candidates += _mtd_pace_candidates(daily, max_date, as_of, mtd_notable_pct)

    return {
        "as_of": as_of,
        "pulse": [p.to_dict() for p in pulse],
        "insights": _rank_and_diversify(candidates),
    }


@ttl_cache(ttl=86400, vary_on=active_client_id)
def build_daily_brief(sensitivity: str = "balanced") -> dict:
    """The home dashboard's Daily Brief. Reads the ACTIVE client from the same
    ContextVar override /api/overview and /api/alerts already use, so it must
    be set by the caller before this runs. Cached a day at a time per
    (client, sensitivity) -- the underlying data changes at most once a day,
    and `sensitivity` becomes part of the cache key automatically (ttl_cache
    keys on every argument, not just vary_on). Never raises for data reasons:
    a client with no daily data at all still gets a structured (empty)
    response, which the client renders as "hide the section".

    `sensitivity` is home config's dial (sema_core.home_config,
    "conservative"/"balanced"/"sensitive") scaling the anomaly/pace
    thresholds that decide which insight CANDIDATES exist at all -- unlike
    the pulse/insights layer TOGGLES (whole-layer visibility), which the API
    layer applies as a post-filter since they don't change what's computed.

    Deliberately NOT scope-filtered here: the cache is keyed per CLIENT, not
    per requester, so baking one user's data-access scope into a shared cache
    entry would leak into (or wrongly restrict) every other user's brief.
    Call filter_for_scope() on the result instead, per request.
    """
    from sema_core import home_config

    multiplier = home_config.SENSITIVITY_MULTIPLIER.get(sensitivity, 1.0)
    try:
        return _build(ANOMALY_THRESHOLD_PCT * multiplier, MTD_NOTABLE_PCT * multiplier)
    except Exception:
        logger.warning("daily_brief: build failed for this client", exc_info=True)
        return {"as_of": None, "pulse": [], "insights": []}


# Which domain each PULSE metric belongs to (sema_core.data_scope).
_METRIC_DOMAIN = {
    "revenue": "sales",
    "orders": "sales",
    "conversion": "marketing",
}

# Which domain each INSIGHT generator's `kind` belongs to -- unambiguous for
# every kind except "yesterday_anomaly", which fires for any pulse metric
# (revenue/orders -> sales, conversion -> marketing) and is resolved via
# _METRIC_DOMAIN from its id instead (see _insight_domain below). Kept next
# to the generators themselves so a new one is a one-line addition here too.
_KIND_DOMAIN = {
    "campaign_negative_roi": "marketing",
    "vip_inactive": "customers",
    "record_day": "sales",
    "product_rank_shift": "sales",
    "mtd_pace": "sales",
}


def _insight_domain(insight: dict) -> str:
    if insight["kind"] == "yesterday_anomaly":
        # id is f"yesterday_anomaly-{metric}-{as_of}" -- the metric is the
        # one piece of information not otherwise in the (already-stripped)
        # dict; embedding it in a stable id format is a lot cheaper than
        # carrying a separate field just for this one filter.
        parts = insight.get("id", "").split("-")
        metric = parts[1] if len(parts) > 2 else ""
        return _METRIC_DOMAIN.get(metric, "")
    return _KIND_DOMAIN.get(insight["kind"], "")


def filter_for_scope(brief: dict, scope_id: str) -> dict:
    """Drop pulse tiles and insight cards this requester's data-access scope
    doesn't allow (sema_core.data_scope) -- applied AFTER build_daily_brief's
    per-client cache, so one user's scope never leaks into another's cached
    brief. 'full' (the default) is a no-op copy."""
    if scope_id == "full":
        return brief
    pulse = [p for p in brief["pulse"] if data_scope.domain_allowed(_METRIC_DOMAIN.get(p["metric"], ""), scope_id)]
    insights = [i for i in brief["insights"] if data_scope.domain_allowed(_insight_domain(i), scope_id)]
    return {**brief, "pulse": pulse, "insights": insights}
