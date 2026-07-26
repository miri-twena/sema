"""
sema_core.daily_brief: the two-layer (pulse + insights) Daily Brief.

Pure functions are exercised directly with constructed DataFrames -- no live
DB needed. The orchestration tests (_build / the cached build_daily_brief)
monkeypatch queries.* the same way test_api_overview.py monkeypatches
overview_mod.queries.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from sema_core import daily_brief


@pytest.fixture(autouse=True)
def _clear_cache():
    """build_daily_brief is cached per client for a day -- without clearing it
    between tests, one test's monkeypatched queries would leak into the next."""
    daily_brief.build_daily_brief.cache_clear()
    yield
    daily_brief.build_daily_brief.cache_clear()


def _orders(rows: dict[str, tuple[int, float]]) -> pd.DataFrame:
    """{"2026-07-01": (order_count, revenue)} -> a get_daily_orders()-shaped frame."""
    return pd.DataFrame(
        {
            "day": pd.to_datetime(list(rows.keys())),
            "order_count": [v[0] for v in rows.values()],
            "revenue": [v[1] for v in rows.values()],
        }
    )


def _sessions(rows: dict[str, tuple[int, int]]) -> pd.DataFrame:
    """{"2026-07-01": (session_count, converted_count)}."""
    return pd.DataFrame(
        {
            "day": pd.to_datetime(list(rows.keys())),
            "session_count": [v[0] for v in rows.values()],
            "converted_count": [v[1] for v in rows.values()],
        }
    )


def _merged(order_rows: dict, session_rows: dict | None = None) -> pd.DataFrame:
    sessions = _sessions(session_rows) if session_rows is not None else None
    return daily_brief._merged_daily(_orders(order_rows), sessions)


def _by_metric(items) -> dict:
    return {i["metric"] if "metric" in i else i.get("_metric_group"): i for i in items}


# --- _deviation (same-weekday baseline) --------------------------------------
def test_deviation_above_threshold():
    rows = {"2026-07-13": (200, 20000.0)}  # Monday
    for n in range(1, 5):
        d = date(2026, 7, 13) - timedelta(days=7 * n)
        rows[d.isoformat()] = (100, 10000.0)
    daily = _merged(rows)
    status, dev = daily_brief._deviation(daily, "order_count", date(2026, 7, 13))
    assert status == "above"
    assert dev == 100.0


def test_deviation_below_threshold_is_normal():
    rows = {"2026-07-13": (110, 11000.0)}  # +10%, under the 20% bar
    for n in range(1, 5):
        d = date(2026, 7, 13) - timedelta(days=7 * n)
        rows[d.isoformat()] = (100, 10000.0)
    daily = _merged(rows)
    status, dev = daily_brief._deviation(daily, "order_count", date(2026, 7, 13))
    assert status == "normal"
    assert dev == 10.0


def test_deviation_boundary_at_exactly_20_percent_is_above():
    rows = {"2026-07-13": (120, 12000.0)}
    for n in range(1, 5):
        d = date(2026, 7, 13) - timedelta(days=7 * n)
        rows[d.isoformat()] = (100, 10000.0)
    daily = _merged(rows)
    status, dev = daily_brief._deviation(daily, "order_count", date(2026, 7, 13))
    assert status == "above" and dev == 20.0


def test_deviation_needs_at_least_two_historical_samples():
    rows = {"2026-07-13": (200, 20000.0), "2026-07-06": (100, 10000.0)}  # only 1 prior Monday
    daily = _merged(rows)
    status, dev = daily_brief._deviation(daily, "order_count", date(2026, 7, 13))
    assert status == "normal" and dev is None


def test_deviation_can_go_below():
    rows = {"2026-07-13": (40, 4000.0)}
    for n in range(1, 5):
        d = date(2026, 7, 13) - timedelta(days=7 * n)
        rows[d.isoformat()] = (100, 10000.0)
    daily = _merged(rows)
    status, dev = daily_brief._deviation(daily, "order_count", date(2026, 7, 13))
    assert status == "below" and dev == -60.0


# --- pulse ---------------------------------------------------------------
def test_pulse_always_includes_all_three_metrics_when_data_exists():
    order_rows = {f"2026-07-{d:02d}": (10, 1000.0) for d in range(1, 14)}
    session_rows = {f"2026-07-{d:02d}": (200, 20) for d in range(1, 14)}
    daily = _merged(order_rows, session_rows)
    pulse = daily_brief._pulse(daily, date(2026, 7, 13))
    assert {p.metric for p in pulse} == {"revenue", "orders", "conversion"}


def test_pulse_spark_has_14_points_ending_at_the_value():
    order_rows = {f"2026-07-{d:02d}": (10, 1000.0 * d) for d in range(1, 14)}
    daily = _merged(order_rows)
    pulse = daily_brief._pulse(daily, date(2026, 7, 13))
    revenue = next(p for p in pulse if p.metric == "revenue")
    assert len(revenue.spark) == 14
    assert revenue.spark[-1] == revenue.value == 13000.0


def test_pulse_status_label_is_in_normal_range_when_quiet():
    order_rows = {f"2026-07-{d:02d}": (10, 1000.0) for d in range(1, 14)}
    order_rows.update({(date(2026, 7, 13) - timedelta(days=7 * n)).isoformat(): (10, 1000.0) for n in range(1, 5)})
    daily = _merged(order_rows)
    pulse = daily_brief._pulse(daily, date(2026, 7, 13))
    revenue = next(p for p in pulse if p.metric == "revenue")
    assert revenue.status == "normal"
    assert revenue.status_label == "In normal range"


def test_pulse_status_label_uses_short_weekday_and_sign_when_above():
    order_rows = {"2026-07-13": (20, 20000.0)}  # Monday, double the typical
    order_rows.update({(date(2026, 7, 13) - timedelta(days=7 * n)).isoformat(): (10, 10000.0) for n in range(1, 5)})
    daily = _merged(order_rows)
    pulse = daily_brief._pulse(daily, date(2026, 7, 13))
    revenue = next(p for p in pulse if p.metric == "revenue")
    assert revenue.status == "above"
    assert revenue.status_label == "+100% vs typical Mon"


def test_pulse_omits_conversion_tile_when_there_is_no_session_data():
    order_rows = {f"2026-07-{d:02d}": (10, 1000.0) for d in range(1, 14)}
    daily = _merged(order_rows, session_rows=None)
    pulse = daily_brief._pulse(daily, date(2026, 7, 13))
    assert "conversion" not in {p.metric for p in pulse}
    assert "revenue" in {p.metric for p in pulse}  # the OTHER metrics still show


# --- yesterday_anomaly insight ------------------------------------------
def test_yesterday_anomaly_insight_mirrors_the_pulse_status():
    pulse = [
        daily_brief.PulseResult("revenue", "Revenue", 20000.0, "currency", [0] * 14, "above", "+100% vs typical Mon", 100.0),
        daily_brief.PulseResult("orders", "Orders", 100.0, "number", [0] * 14, "normal", "In normal range", 5.0),
    ]
    candidates = daily_brief._yesterday_anomaly_candidates(pulse, "2026-07-13")
    assert len(candidates) == 1  # only the "above" one -- normal produces nothing
    assert candidates[0]["_metric_group"] == "revenue"
    assert candidates[0]["severity"] == 100.0


# --- campaign_negative_roi -------------------------------------------------
def _campaign_row(**over) -> pd.DataFrame:
    base = {
        "campaign_id": 1,
        "campaign_name": "Summer Sale",
        "channel": "Meta",
        "spend": 8400.0,
        "attributed_revenue": 6100.0,
        "roas": 6100.0 / 8400.0,
        "days_active": 20,
        "is_active": True,
    }
    base.update(over)
    return pd.DataFrame([base])


def test_campaign_negative_roi_fires_when_running_long_enough():
    out = daily_brief._campaign_negative_roi_candidates(_campaign_row(), "2026-07-13")
    assert len(out) == 1
    assert "Summer Sale" in out[0]["headline"]
    assert "20 days" in out[0]["headline"]


def test_campaign_negative_roi_is_silent_before_14_days():
    out = daily_brief._campaign_negative_roi_candidates(_campaign_row(days_active=10), "2026-07-13")
    assert out == []


def test_campaign_negative_roi_is_silent_for_a_profitable_campaign():
    out = daily_brief._campaign_negative_roi_candidates(_campaign_row(roas=1.5), "2026-07-13")
    assert out == []


def test_campaign_negative_roi_is_silent_for_an_ended_campaign():
    out = daily_brief._campaign_negative_roi_candidates(_campaign_row(is_active=False), "2026-07-13")
    assert out == []


# --- vip_inactive ------------------------------------------------------------
def test_vip_inactive_includes_count_and_highlights_the_most_inactive():
    df = pd.DataFrame(
        [
            {"customer_id": 1, "customer_name": "Sarah Chen", "days_inactive": 74, "revenue_12mo": 3200.0},
            {"customer_id": 2, "customer_name": "Alex Kim", "days_inactive": 61, "revenue_12mo": 1800.0},
        ]
    )
    out = daily_brief._vip_inactive_candidates(df, "2026-07-13")
    assert len(out) == 1
    assert "2 VIP customers" in out[0]["headline"]
    assert "Sarah Chen" in out[0]["detail"]
    assert "$3,200" in out[0]["detail"]


def test_vip_inactive_is_silent_when_none_qualify():
    assert daily_brief._vip_inactive_candidates(None, "2026-07-13") == []


# --- record_day --------------------------------------------------------------
def test_record_day_fires_on_a_new_best():
    # 74 days of flat history before "yesterday" (Apr 1 - Jun 13) -- comfortably
    # past the 60-day guard.
    rows = {f"2026-04-{d:02d}": (10, 1000.0) for d in range(1, 31)}
    rows.update({f"2026-05-{d:02d}": (10, 1000.0) for d in range(1, 32)})
    rows.update({f"2026-06-{d:02d}": (10, 1000.0) for d in range(1, 14)})
    rows["2026-06-14"] = (10, 5000.0)  # yesterday, a clear new best
    daily = _merged(rows)
    out = daily_brief._record_day_candidates(daily, date(2026, 6, 14), "2026-06-14")
    revenue_records = [c for c in out if c["_metric_group"] == "revenue"]
    assert len(revenue_records) == 1
    assert "best" in revenue_records[0]["headline"]


def test_record_day_needs_60_prior_days():
    rows = {f"2026-06-{d:02d}": (10, 1000.0) for d in range(1, 14)}
    rows["2026-06-14"] = (10, 5000.0)
    daily = _merged(rows)
    assert daily_brief._record_day_candidates(daily, date(2026, 6, 14), "2026-06-14") == []


def test_record_day_is_silent_for_an_unremarkable_day():
    rows = {f"2026-05-{d:02d}": (10, 1000.0) for d in range(1, 32)}
    rows.update({f"2026-06-{d:02d}": (10, 1000.0) for d in range(1, 15)})  # yesterday = typical
    daily = _merged(rows)
    assert daily_brief._record_day_candidates(daily, date(2026, 6, 14), "2026-06-14") == []


# --- product_rank_shift -------------------------------------------------
def _products(rows: list[tuple[str, int, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["month", "product_id", "product_name", "revenue"])


def test_product_rank_shift_fires_for_a_new_top3_entrant():
    products = _products(
        [
            ("2026-05-01", 1, "Widget A", 500),
            ("2026-05-01", 2, "Widget B", 400),
            ("2026-05-01", 3, "Widget C", 300),
            ("2026-05-01", 4, "Widget D", 100),
            ("2026-06-01", 1, "Widget A", 500),
            ("2026-06-01", 2, "Widget B", 400),
            ("2026-06-01", 4, "Widget D", 900),  # jumped into the top 3
        ]
    )
    out = daily_brief._product_rank_shift_candidates(products, date(2026, 6, 14), "2026-06-14")
    assert len(out) == 1
    assert "Widget D" in out[0]["headline"]


def test_product_rank_shift_is_silent_when_the_top3_is_unchanged():
    products = _products(
        [
            ("2026-05-01", 1, "Widget A", 500),
            ("2026-05-01", 2, "Widget B", 400),
            ("2026-06-01", 1, "Widget A", 600),
            ("2026-06-01", 2, "Widget B", 500),
        ]
    )
    assert daily_brief._product_rank_shift_candidates(products, date(2026, 6, 14), "2026-06-14") == []


def test_product_rank_shift_needs_a_prior_month():
    products = _products([("2026-06-01", 1, "Widget A", 500)])
    assert daily_brief._product_rank_shift_candidates(products, date(2026, 6, 14), "2026-06-14") == []


# --- mtd_pace ------------------------------------------------------------
def test_mtd_pace_fires_past_the_10_percent_bar():
    rows = {f"2026-07-{d:02d}": (10, 1200.0) for d in range(1, 13)}
    rows.update({f"2026-06-{d:02d}": (8, 1000.0) for d in range(1, 13)})
    daily = _merged(rows)
    out = daily_brief._mtd_pace_candidates(daily, date(2026, 7, 12), "2026-07-12")
    assert len(out) == 2  # revenue + orders both clear 10%


def test_mtd_pace_is_silent_below_the_10_percent_bar():
    rows = {f"2026-07-{d:02d}": (10, 1040.0) for d in range(1, 13)}  # +4%
    rows.update({f"2026-06-{d:02d}": (10, 1000.0) for d in range(1, 13)})
    daily = _merged(rows)
    assert daily_brief._mtd_pace_candidates(daily, date(2026, 7, 12), "2026-07-12") == []


def test_mtd_pace_guards_the_first_two_days_of_a_month():
    rows = {"2026-07-01": (10, 2000.0), "2026-06-01": (8, 900.0)}
    assert daily_brief._mtd_pace_candidates(_merged(rows), date(2026, 7, 1), "2026-07-01") == []
    rows["2026-07-02"] = (10, 2000.0)
    assert daily_brief._mtd_pace_candidates(_merged(rows), date(2026, 7, 2), "2026-07-02") == []


def test_mtd_pace_day_three_is_not_guarded():
    rows = {f"2026-07-{d:02d}": (10, 2000.0) for d in (1, 2, 3)}
    rows.update({f"2026-06-{d:02d}": (8, 900.0) for d in (1, 2, 3)})
    out = daily_brief._mtd_pace_candidates(_merged(rows), date(2026, 7, 3), "2026-07-03")
    assert len(out) == 2


def test_mtd_pace_caps_the_prior_window_at_a_shorter_months_length():
    rows = {f"2026-03-{d:02d}": (5, 2000.0) for d in range(1, 32)}
    rows.update({f"2026-02-{d:02d}": (4, 400.0) for d in range(1, 29)})
    out = daily_brief._mtd_pace_candidates(_merged(rows), date(2026, 3, 31), "2026-03-31")
    revenue = next(c for c in out if c["_metric_group"] == "revenue")
    assert "February" in revenue["detail"]


# --- diversity rule + ranking ---------------------------------------------
def test_diversity_rule_keeps_only_the_more_severe_candidate_per_metric():
    candidates = [
        {"_metric_group": "revenue", "severity": 20.0, "id": "a"},
        {"_metric_group": "revenue", "severity": 45.0, "id": "b"},  # same metric, more severe
        {"_metric_group": "orders", "severity": 30.0, "id": "c"},
    ]
    out = daily_brief._rank_and_diversify(candidates)
    ids = {c["id"] for c in out}
    assert ids == {"b", "c"}  # "a" is dropped -- "b" already tells the revenue story


def test_ranking_caps_at_max_insights():
    candidates = [{"_metric_group": str(i), "severity": float(i), "id": str(i)} for i in range(5)]
    out = daily_brief._rank_and_diversify(candidates)
    assert len(out) == daily_brief.MAX_INSIGHTS
    assert [c["severity"] for c in out] == [4.0, 3.0, 2.0]  # most severe first


def test_output_dicts_never_leak_the_internal_metric_group_key():
    candidates = [{"_metric_group": "revenue", "severity": 50.0, "id": "a"}]
    out = daily_brief._rank_and_diversify(candidates)
    assert "_metric_group" not in out[0]


# --- orchestration -------------------------------------------------------
def _stub_data_bounds(monkeypatch, max_date: date | None):
    bounds = pd.DataFrame({"min_order_date": [date(2025, 6, 1)], "max_order_date": [max_date]})
    monkeypatch.setattr(daily_brief.queries, "get_data_bounds", lambda: bounds)


def _stub_empty_sources(monkeypatch):
    monkeypatch.setattr(daily_brief.queries, "get_daily_sessions", lambda: pd.DataFrame())
    monkeypatch.setattr(daily_brief.queries, "get_campaign_roi_status", lambda: pd.DataFrame())
    monkeypatch.setattr(daily_brief.queries, "get_vip_inactive", lambda: pd.DataFrame())
    monkeypatch.setattr(daily_brief.queries, "get_product_revenue_by_month", lambda: pd.DataFrame())


def test_build_returns_a_quiet_day_with_pulse_but_no_insights(monkeypatch):
    _stub_data_bounds(monkeypatch, date(2026, 7, 13))
    order_rows = {f"2026-07-{d:02d}": (10, 1000.0) for d in range(1, 14)}
    order_rows.update({(date(2026, 7, 13) - timedelta(days=7 * n)).isoformat(): (10, 1000.0) for n in range(1, 5)})
    monkeypatch.setattr(daily_brief.queries, "get_daily_orders", lambda: _orders(order_rows))
    _stub_empty_sources(monkeypatch)

    out = daily_brief._build()
    assert out["as_of"] == "2026-07-13"
    assert len(out["pulse"]) >= 2  # revenue + orders (no session data -> no conversion tile)
    assert out["insights"] == []


def test_build_surfaces_an_insight_when_something_is_notable(monkeypatch):
    _stub_data_bounds(monkeypatch, date(2026, 7, 13))
    order_rows = {"2026-07-13": (20, 20000.0)}
    order_rows.update({(date(2026, 7, 13) - timedelta(days=7 * n)).isoformat(): (10, 10000.0) for n in range(1, 5)})
    monkeypatch.setattr(daily_brief.queries, "get_daily_orders", lambda: _orders(order_rows))
    _stub_empty_sources(monkeypatch)

    out = daily_brief._build()
    assert len(out["insights"]) >= 1
    assert out["insights"][0]["kind"] == "yesterday_anomaly"


def test_build_returns_empty_response_when_there_is_no_data_at_all(monkeypatch):
    _stub_data_bounds(monkeypatch, None)
    monkeypatch.setattr(daily_brief.queries, "get_daily_orders", lambda: pd.DataFrame())
    _stub_empty_sources(monkeypatch)

    out = daily_brief._build()
    assert out == {"as_of": None, "pulse": [], "insights": []}


def test_build_survives_a_query_failure(monkeypatch):
    _stub_data_bounds(monkeypatch, date(2026, 7, 13))

    def boom():
        raise RuntimeError("relation does not exist")

    monkeypatch.setattr(daily_brief.queries, "get_daily_orders", boom)
    _stub_empty_sources(monkeypatch)

    out = daily_brief.build_daily_brief()
    assert out == {"as_of": "2026-07-13", "pulse": [], "insights": []}


def test_build_daily_brief_is_cached_per_client(monkeypatch):
    _stub_data_bounds(monkeypatch, date(2026, 7, 13))
    calls = {"n": 0}

    def counting_orders():
        calls["n"] += 1
        return _orders({f"2026-07-{d:02d}": (10, 1000.0) for d in range(1, 14)})

    monkeypatch.setattr(daily_brief.queries, "get_daily_orders", counting_orders)
    _stub_empty_sources(monkeypatch)

    daily_brief.build_daily_brief()
    daily_brief.build_daily_brief()
    assert calls["n"] == 1
