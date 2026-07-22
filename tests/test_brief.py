"""
sema_core.brief: the home dashboard's Daily Brief.

The saved-report functions are monkeypatched (same pattern as
test_api_overview.py), so no live DB is needed. Every assertion here is about
DETERMINISTIC behaviour -- the brief must never call a model, so the same data
must always produce the same insights in the same order.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from sema_core import brief as brief_mod
from sema_core import overview as overview_mod


def _fake_reports(monkeypatch, months: dict[str, tuple[int, float]], max_date: date | None):
    """Install a fake revenue_by_month + data_bounds for `months`
    ({"2026-05": (order_count, revenue)})."""
    df = pd.DataFrame(
        {
            "month": pd.to_datetime([f"{m}-01" for m in months]),
            "order_count": [v[0] for v in months.values()],
            "revenue": [v[1] for v in months.values()],
        }
    )
    bounds = pd.DataFrame({"min_order_date": [date(2025, 6, 1)], "max_order_date": [max_date]})
    monkeypatch.setattr(overview_mod.queries, "get_revenue_by_month", lambda: df)
    monkeypatch.setattr(overview_mod.queries, "get_data_bounds", lambda: bounds)
    # build_overview (used by the cross-check test) also reads this one; stub it
    # so no test in this module can reach a live database.
    monkeypatch.setattr(
        overview_mod.queries,
        "get_at_risk_customers",
        lambda: pd.DataFrame({"customer_id": [1, 2, 3]}),
    )


def _by_metric(out: dict) -> dict[str, dict]:
    return {i["metric"]: i for i in out["insights"]}


# --- metric computation ------------------------------------------------------
def test_computes_revenue_orders_and_aov_against_the_prior_month(monkeypatch):
    # Revenue +50%, Orders +20%, AOV +25% -- all three clear the noise floor.
    _fake_reports(
        monkeypatch,
        {"2026-04": (100, 1000.0), "2026-05": (120, 1500.0)},
        max_date=date(2026, 5, 31),
    )
    out = brief_mod.build_brief()
    assert out["comparison_available"] is True
    assert out["period"] == {"start": "2026-05", "end": "2026-05"}
    assert out["comparison_period"] == {"start": "2026-04", "end": "2026-04"}

    by_metric = _by_metric(out)
    assert by_metric["revenue"]["change_pct"] == 50.0
    assert by_metric["revenue"]["current_value"] == 1500.0
    assert by_metric["revenue"]["previous_value"] == 1000.0
    assert by_metric["orders"]["change_pct"] == 20.0
    assert by_metric["aov"]["change_pct"] == 25.0  # 12.5 vs 10.0


def test_multi_month_window_compares_to_an_equal_length_prior_window(monkeypatch):
    _fake_reports(
        monkeypatch,
        {
            "2026-01": (100, 1000.0),
            "2026-02": (100, 1000.0),  # prior window: 2000
            "2026-03": (150, 1500.0),
            "2026-04": (150, 1500.0),  # selected window: 3000 -> +50%
        },
        max_date=date(2026, 4, 30),
    )
    out = brief_mod.build_brief(start="2026-03", end="2026-04")
    assert out["comparison_period"] == {"start": "2026-01", "end": "2026-02"}
    assert _by_metric(out)["revenue"]["change_pct"] == 50.0


def test_custom_range_resolves_like_the_overview(monkeypatch):
    """The brief must describe exactly the window the KPI cards describe."""
    months = {
        "2025-12": (100, 1000.0),
        "2026-01": (100, 1000.0),
        "2026-02": (100, 1000.0),
        "2026-03": (200, 2000.0),
        "2026-04": (200, 2000.0),
        "2026-05": (200, 2000.0),
    }
    _fake_reports(monkeypatch, months, max_date=date(2026, 5, 31))
    out = brief_mod.build_brief(start="2026-03", end="2026-05")
    overview_out = overview_mod.build_overview(start="2026-03", end="2026-05")

    assert out["period"] == {"start": overview_out["start"], "end": overview_out["end"]}
    assert out["comparison_period"] == {"start": "2025-12", "end": "2026-02"}


# --- ranking -----------------------------------------------------------------
def test_ranks_by_magnitude_of_relative_change(monkeypatch):
    # Revenue +8%, Orders +80% -> orders must lead despite being second in
    # METRICS order. AOV falls 40% (1.08/1.8).
    _fake_reports(
        monkeypatch,
        {"2026-04": (100, 1000.0), "2026-05": (180, 1080.0)},
        max_date=date(2026, 5, 31),
    )
    out = brief_mod.build_brief()
    scores = [i["rank_score"] for i in out["insights"]]
    assert scores == sorted(scores, reverse=True)
    assert out["insights"][0]["metric"] == "orders"


def test_negligible_changes_are_not_shown(monkeypatch):
    # Every metric moves under the 5% noise floor -> nothing worth reporting.
    _fake_reports(
        monkeypatch,
        {"2026-04": (100, 1000.0), "2026-05": (102, 1020.0)},
        max_date=date(2026, 5, 31),
    )
    out = brief_mod.build_brief()
    assert out["insights"] == []
    assert out["comparison_available"] is True  # a baseline existed; nothing moved


def test_at_most_three_insights(monkeypatch):
    _fake_reports(
        monkeypatch,
        {"2026-04": (100, 1000.0), "2026-05": (500, 9000.0)},
        max_date=date(2026, 5, 31),
    )
    assert len(brief_mod.build_brief()["insights"]) <= brief_mod.MAX_INSIGHTS


def test_ranking_is_stable_for_equal_magnitudes(monkeypatch):
    # Revenue and orders both +50% -> AOV is flat and drops out; the tie
    # resolves by METRICS order, and repeated runs must not reorder.
    _fake_reports(
        monkeypatch,
        {"2026-04": (100, 1000.0), "2026-05": (150, 1500.0)},
        max_date=date(2026, 5, 31),
    )
    first = [i["metric"] for i in brief_mod.build_brief()["insights"]]
    assert first == ["revenue", "orders"]
    assert first == [i["metric"] for i in brief_mod.build_brief()["insights"]]


# --- edge cases --------------------------------------------------------------
def test_zero_previous_value_yields_no_misleading_percentage(monkeypatch):
    # April had no orders and no revenue: percent change is undefined, so
    # neither metric may appear rather than reporting an infinite rise.
    _fake_reports(
        monkeypatch,
        {"2026-04": (0, 0.0), "2026-05": (120, 1500.0)},
        max_date=date(2026, 5, 31),
    )
    out = brief_mod.build_brief()
    assert out["insights"] == []


def test_zero_current_orders_does_not_divide_by_zero(monkeypatch):
    # No orders this month -> AOV is undefined now; revenue/orders still report.
    _fake_reports(
        monkeypatch,
        {"2026-04": (100, 1000.0), "2026-05": (0, 0.0)},
        max_date=date(2026, 5, 31),
    )
    out = brief_mod.build_brief()
    assert "aov" not in _by_metric(out)
    assert _by_metric(out)["revenue"]["change_pct"] == -100.0


def test_insufficient_history_returns_structured_metadata(monkeypatch):
    _fake_reports(monkeypatch, {"2026-05": (100, 1000.0)}, max_date=date(2026, 5, 31))
    out = brief_mod.build_brief()
    assert out["insights"] == []
    assert out["comparison_available"] is False
    assert out["unavailable_reason"] == "insufficient_history"
    assert out["comparison_period"] is None


def test_partial_baseline_is_not_used(monkeypatch):
    # A 2-month window with only 1 prior month must not compare against it --
    # the same rule the overview cards follow.
    _fake_reports(
        monkeypatch,
        {"2026-02": (100, 1000.0), "2026-03": (150, 1500.0), "2026-04": (150, 1500.0)},
        max_date=date(2026, 4, 30),
    )
    out = brief_mod.build_brief(start="2026-03", end="2026-04")
    assert out["comparison_available"] is False


def test_unavailable_report_returns_empty_brief_not_an_error(monkeypatch):
    def boom():
        raise RuntimeError("relation 'orders' does not exist")

    monkeypatch.setattr(overview_mod.queries, "get_revenue_by_month", boom)
    monkeypatch.setattr(overview_mod.queries, "get_data_bounds", boom)
    out = brief_mod.build_brief()
    assert out["insights"] == []
    assert out["unavailable_reason"] == "no_period_data"


def test_one_failing_metric_does_not_empty_the_brief(monkeypatch):
    """A metric that blows up mid-computation costs only itself."""
    _fake_reports(
        monkeypatch,
        {"2026-04": (100, 1000.0), "2026-05": (180, 1800.0)},
        max_date=date(2026, 5, 31),
    )
    real_aggregate = brief_mod._aggregate

    def partial(frame):
        values = real_aggregate(frame)

        class Sabotaged(dict):
            def get(self, key, default=None):
                if key == "orders":
                    raise RuntimeError("orders unavailable")
                return super().get(key, default)

        return Sabotaged(values)

    monkeypatch.setattr(brief_mod, "_aggregate", partial)
    out = brief_mod.build_brief()
    metrics = {i["metric"] for i in out["insights"]}
    assert "orders" not in metrics
    assert "revenue" in metrics  # the healthy metrics survived


# --- phrasing / contract -----------------------------------------------------
def test_sentiment_follows_metric_meaning_not_direction(monkeypatch):
    _fake_reports(
        monkeypatch,
        {"2026-04": (100, 1000.0), "2026-05": (50, 500.0)},
        max_date=date(2026, 5, 31),
    )
    revenue = _by_metric(brief_mod.build_brief())["revenue"]
    assert revenue["direction"] == "down"
    assert revenue["sentiment"] == "negative"  # falling revenue is bad news


def test_insight_ids_are_stable_across_runs(monkeypatch):
    _fake_reports(
        monkeypatch,
        {"2026-04": (100, 1000.0), "2026-05": (180, 1800.0)},
        max_date=date(2026, 5, 31),
    )
    ids = [i["id"] for i in brief_mod.build_brief()["insights"]]
    assert ids == [i["id"] for i in brief_mod.build_brief()["insights"]]
    assert all(i.endswith("-2026-05-2026-05") for i in ids)


@pytest.mark.parametrize("metric", ["revenue", "orders", "aov"])
def test_follow_up_is_an_analytical_question_naming_the_period(monkeypatch, metric):
    _fake_reports(
        monkeypatch,
        {"2026-04": (100, 1000.0), "2026-05": (180, 2500.0)},
        max_date=date(2026, 5, 31),
    )
    insight = _by_metric(brief_mod.build_brief())[metric]
    question = insight["follow_up_question"]
    assert question.endswith("?")
    assert "May 2026" in question
    # Must be answerable from data -- never a recommended ACTION.
    assert not any(
        verb in question.lower() for verb in ("send", "launch", "email", "campaign", "call")
    )


def test_every_insight_carries_the_full_contract(monkeypatch):
    _fake_reports(
        monkeypatch,
        {"2026-04": (100, 1000.0), "2026-05": (180, 2500.0)},
        max_date=date(2026, 5, 31),
    )
    required = {
        "id", "metric", "metric_label", "headline", "detail", "current_value",
        "previous_value", "change_pct", "direction", "sentiment", "value_format",
        "rank_score", "importance", "follow_up_question", "period", "comparison_period",
    }
    for insight in brief_mod.build_brief()["insights"]:
        assert required <= set(insight)


def test_importance_bands_high_and_medium(monkeypatch):
    # Revenue +30% (>=20 -> high); orders +15% and AOV +13.0% (>=10 -> medium).
    _fake_reports(
        monkeypatch,
        {"2026-04": (100, 1000.0), "2026-05": (115, 1300.0)},
        max_date=date(2026, 5, 31),
    )
    by_metric = _by_metric(brief_mod.build_brief())
    assert by_metric["revenue"]["importance"] == "high"
    assert by_metric["orders"]["importance"] == "medium"
    assert by_metric["aov"]["importance"] == "medium"


def test_importance_band_low_is_still_above_the_noise_floor(monkeypatch):
    # Orders +7%: past the 5% floor so it IS reported, but only as low
    # importance. AOV moves ~+4.7% and is filtered out entirely.
    _fake_reports(
        monkeypatch,
        {"2026-04": (100, 1000.0), "2026-05": (107, 1120.0)},
        max_date=date(2026, 5, 31),
    )
    by_metric = _by_metric(brief_mod.build_brief())
    assert by_metric["orders"]["importance"] == "low"
    assert by_metric["revenue"]["importance"] == "medium"  # +12%
    assert "aov" not in by_metric
