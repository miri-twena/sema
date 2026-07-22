"""
SEMA: the home dashboard's Daily Brief.

Turns the period-over-period movement already computed for the Business
Overview into 2-3 phrased insights, so the user sees what changed before
asking anything. Deterministic by design: no Claude call happens on page
load, which is what keeps the home screen fast and its output stable.

Relationship to overview.py:
  - The period and its comparison baseline come from overview.resolve_period,
    the SINGLE definition both features share. This module never re-derives
    "the prior window" -- if it did, the cards and the brief could disagree
    about which months they describe.
  - The overview's KPI cards are built separately (overview._period_kpis) and
    are not affected by anything here.

Number FORMATTING deliberately stays out of this module. The frontend's
format.ts is the single source of truth for rendering values (and documents
having been de-duplicated once already), so insights carry raw values plus a
`value_format` tag and the UI renders them. The phrased sentence therefore
describes the movement without restating the numbers.

The three stages are kept apart so each can be tested on its own:
    _metric_changes()  -- data:     what moved, by how much
    _rank()            -- judgment: which movements are worth showing
    _phrase()          -- wording:  how one movement reads
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from sema_core.obs import get_logger
from sema_core.overview import ResolvedPeriod, resolve_period

logger = get_logger("brief")

# A move smaller than this is noise, not news -- showing it would train the
# user to ignore the brief.
NEGLIGIBLE_PCT = 5.0
# Importance bands. Thresholds, not magic: they only bucket what is already
# ranked, so a wrong band never reorders the list.
HIGH_PCT = 20.0
MEDIUM_PCT = 10.0
MAX_INSIGHTS = 3


@dataclass(frozen=True)
class MetricSpec:
    """One metric the brief can talk about.

    `higher_is_better` is what decides positive/negative wording. It is a
    property of the METRIC, not of the colour on a card -- a future metric
    like refund rate flips it by changing this one flag, with no other edits.
    """

    key: Literal["revenue", "orders", "aov"]
    label: str
    value_format: Literal["currency", "number"]  # the Kpi format vocabulary
    higher_is_better: bool
    follow_up: str  # "{period}" is substituted with the period label


# Order matters: it is the deterministic tie-break when two metrics moved by
# exactly the same amount (Python's sort is stable).
METRICS: tuple[MetricSpec, ...] = (
    MetricSpec(
        key="revenue",
        label="Revenue",
        value_format="currency",
        higher_is_better=True,
        follow_up="What drove the revenue change in {period}?",
    ),
    MetricSpec(
        key="orders",
        label="Orders",
        value_format="number",
        higher_is_better=True,
        follow_up="Which categories contributed most to the change in orders in {period}?",
    ),
    MetricSpec(
        key="aov",
        label="AOV",
        value_format="currency",
        higher_is_better=True,
        follow_up="Why did AOV change in {period}?",
    ),
)


@dataclass(frozen=True)
class MetricChange:
    spec: MetricSpec
    current: float
    previous: float
    change_pct: float


def _aggregate(frame: pd.DataFrame) -> dict[str, float | None]:
    """Revenue / Orders / AOV totals for one month window.

    Mirrors the arithmetic overview._period_kpis performs for the cards; AOV is
    None when there were no orders, so it is simply left out of the brief
    rather than dividing by zero.
    """
    revenue = float(frame["revenue"].sum())
    orders = int(frame["order_count"].sum())
    return {
        "revenue": revenue,
        "orders": float(orders),
        "aov": revenue / orders if orders else None,
    }


def _metric_changes(period: ResolvedPeriod) -> list[MetricChange]:
    """What moved between the selected window and its baseline.

    Returns [] when there is no full baseline window -- the caller turns that
    into structured "no comparison available" metadata rather than showing a
    comparison the data can't support.

    A metric whose previous value is missing or ZERO is skipped: percent change
    is undefined against a zero baseline, and "up from nothing" is not a
    proportional story. Each metric is computed defensively so one bad metric
    cannot empty the whole brief.
    """
    if period.baseline is None or period.window.empty:
        return []

    current = _aggregate(period.window)
    previous = _aggregate(period.baseline)

    changes: list[MetricChange] = []
    for spec in METRICS:
        try:
            cur, prev = current.get(spec.key), previous.get(spec.key)
            if cur is None or not prev:  # missing, or a zero baseline
                continue
            changes.append(
                MetricChange(
                    spec=spec,
                    current=cur,
                    previous=prev,
                    change_pct=round((cur - prev) / prev * 100, 1),
                )
            )
        except Exception:
            # One uncomputable metric must not cost the user the other two.
            logger.warning("brief: could not compute %s", spec.key, exc_info=True)
    return changes


def _rank(changes: list[MetricChange]) -> list[MetricChange]:
    """The movements worth showing, strongest first.

    Deterministic: sorted purely by the size of the relative move, with METRICS
    order as a stable tie-break. Negligible moves are dropped entirely, so a
    quiet month yields fewer insights (or none) instead of filler.
    """
    significant = [c for c in changes if abs(c.change_pct) >= NEGLIGIBLE_PCT]
    return sorted(significant, key=lambda c: -abs(c.change_pct))[:MAX_INSIGHTS]


def _importance(change_pct: float) -> Literal["high", "medium", "low"]:
    magnitude = abs(change_pct)
    if magnitude >= HIGH_PCT:
        return "high"
    if magnitude >= MEDIUM_PCT:
        return "medium"
    return "low"


def _phrase(change: MetricChange, period: ResolvedPeriod) -> dict:
    """One movement -> the rendered insight contract.

    The sentence states the movement and what it is measured against, without
    restating the values: the client formats `current_value`/`previous_value`
    through format.ts so money and counts follow the same rules as everywhere
    else in the product.
    """
    spec = change.spec
    rising = change.change_pct > 0
    direction: Literal["up", "down", "flat"] = "up" if rising else "down"
    magnitude = abs(change.change_pct)
    against = period.baseline_label or "the prior period"

    return {
        # Stable across reloads for the same client/metric/window, so React
        # keys and any future dismissal state have something durable to hold.
        "id": f"{spec.key}-{period.start}-{period.end}",
        "metric": spec.key,
        "metric_label": spec.label,
        "headline": f"{spec.label} {direction} {magnitude}%",
        "detail": (
            f"{spec.label} {'rose' if rising else 'fell'} {magnitude}% "
            f"in {period.label}, compared with {against}."
        ),
        "current_value": round(change.current, 2),
        "previous_value": round(change.previous, 2),
        "change_pct": change.change_pct,
        "direction": direction,
        # Meaning of the metric decides the tone, never the colour of a card.
        "sentiment": "positive" if rising == spec.higher_is_better else "negative",
        "value_format": spec.value_format,
        "rank_score": magnitude,
        "importance": _importance(change.change_pct),
        # An ANALYTICAL question SEMA can actually answer from the data -- never
        # a recommended action, which would need systems SEMA doesn't control.
        "follow_up_question": spec.follow_up.format(period=period.label),
        "period": {"start": period.start, "end": period.end},
        "comparison_period": {
            "start": period.baseline_start,
            "end": period.baseline_end,
        },
    }


def build_brief(start: str | None = None, end: str | None = None) -> dict:
    """2-3 phrased insights about the selected period, for the home dashboard.

    `start`/`end` are month keys ("2026-05"), the same ones /api/overview takes;
    omit both for the latest complete month. Never raises for data reasons: a
    client with no reports, no history, or a quiet month gets an empty
    `insights` list plus metadata explaining why.
    """
    period: ResolvedPeriod | None = None
    try:
        period = resolve_period(start, end)
    except Exception:
        logger.warning("brief: revenue_by_month unavailable for this client", exc_info=True)

    if period is None:
        return {
            "period": {"start": None, "end": None},
            "comparison_period": None,
            "comparison_available": False,
            "unavailable_reason": "no_period_data",
            "insights": [],
        }

    insights = [_phrase(c, period) for c in _rank(_metric_changes(period))]
    has_baseline = period.baseline is not None

    return {
        "period": {"start": period.start, "end": period.end},
        "comparison_period": (
            {"start": period.baseline_start, "end": period.baseline_end}
            if has_baseline
            else None
        ),
        "comparison_available": has_baseline,
        # Structured, not prose: the client decides the wording (and the
        # language) of the empty state from this key.
        "unavailable_reason": None if has_baseline else "insufficient_history",
        "insights": insights,
    }
