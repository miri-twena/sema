"""
sema_core.alert_templates: the SQL/pandas template engine (alert_templates_
prompt.md). Per the project's "no live DB in tests" rule, every test here
monkeypatches _daily_series/_anchor_date with synthetic (hand-computed) data
-- the ACTUAL generated SQL was verified live against the real demo Postgres
during this task (see PROMPT_QUEUE.md's evidence entry), which is what a
live DB would additionally buy us here.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from sema_core import alert_templates
from sema_core.agent.safety import is_safe


# --- SQL safety: every metric query is a single, system-catalog-free SELECT
def test_every_metric_sql_is_a_safe_single_select():
    for metric, spec in alert_templates._METRIC_SQL.items():
        filled = spec["sql"].replace("%(start)s", "'2026-01-01'").replace("%(end)s", "'2026-06-01'")
        assert is_safe(filled), f"{metric}'s query failed the safety validator"


def test_anchor_sql_is_a_safe_single_select():
    assert is_safe(alert_templates._ANCHOR_SQL)


def test_metric_sql_has_no_semicolons_or_string_formatted_params():
    for metric, spec in alert_templates._METRIC_SQL.items():
        assert ";" not in spec["sql"], f"{metric}'s query must be a single statement"
        assert "%(start)s" in spec["sql"] and "%(end)s" in spec["sql"], (
            f"{metric}'s query must bind its date range via placeholders, not string formatting"
        )


# --- validate_params: type/range checks, the injection-rejection surface
def test_pct_change_params_round_trip():
    p = alert_templates.validate_params("pct_change", {"window": "mom", "direction": "drop", "threshold_pct": 8})
    assert p == {"window": "mom", "direction": "drop", "threshold_pct": 8.0}


@pytest.mark.parametrize(
    "template,params",
    [
        ("pct_change", {"window": "quarterly", "direction": "drop", "threshold_pct": 8}),
        ("pct_change", {"window": "mom", "direction": "sideways", "threshold_pct": 8}),
        ("pct_change", {"window": "mom", "direction": "drop", "threshold_pct": 0}),
        ("absolute_threshold", {"operator": "sideways", "value": 100}),
        ("anomaly", {"n_sigma": 0}),
        ("streak", {"n_days": 1, "direction": "drop"}),
        ("streak", {"n_days": 3, "direction": "sideways"}),
    ],
)
def test_invalid_params_are_rejected(template, params):
    with pytest.raises(alert_templates.AlertTemplateError):
        alert_templates.validate_params(template, params)


def test_injection_attempt_in_value_is_rejected_by_type_validation():
    """The one place a param ever reaches SQL-adjacent code (absolute_threshold's
    `value`) never sees a raw string -- float() conversion rejects it long
    before any condition string or SQL is built."""
    with pytest.raises(alert_templates.AlertTemplateError):
        alert_templates.validate_params("absolute_threshold", {"operator": "above", "value": "1; DROP TABLE orders;--"})


def test_injection_attempt_in_n_days_is_rejected():
    with pytest.raises(alert_templates.AlertTemplateError):
        alert_templates.validate_params("streak", {"n_days": "3; DROP TABLE orders;--", "direction": "drop"})


def test_unsupported_metric_is_rejected():
    with pytest.raises(alert_templates.AlertTemplateError):
        alert_templates._require_metric("active_customers")


# --- _bucketed_value: flow/ratio/stock resampling correctness
def _daily(rows: list[tuple]) -> pd.DataFrame:
    """rows: list of (date_str, num, den)."""
    df = pd.DataFrame(rows, columns=["d", "num", "den"])
    df["d"] = pd.to_datetime(df["d"])
    return df


def test_flow_bucket_sums_across_the_bucket():
    df = _daily([("2026-01-01", 100, 1), ("2026-01-02", 200, 1), ("2026-02-01", 50, 1)])
    monthly = alert_templates._bucketed_value(df, "flow", "MS")
    assert monthly.loc["2026-01-01"] == 300
    assert monthly.loc["2026-02-01"] == 50


def test_ratio_bucket_is_a_true_weighted_average_not_average_of_averages():
    # Day 1: 9 orders totalling 900 (avg 100). Day 2: 1 order totalling 300 (avg 300).
    # True AOV for the 2 days combined = 1200 / 10 = 120, NOT (100+300)/2 = 200.
    df = _daily([("2026-01-01", 900, 9), ("2026-01-02", 300, 1)])
    weekly = alert_templates._bucketed_value(df, "ratio", "D")
    assert weekly.iloc[0] == 100.0
    assert weekly.iloc[1] == 300.0
    monthly = alert_templates._bucketed_value(df, "ratio", "MS")
    assert monthly.iloc[0] == 120.0


def test_ratio_bucket_with_zero_orders_is_nan_not_a_crash():
    df = _daily([("2026-01-01", 0, 0), ("2026-01-02", 300, 1)])
    daily_vals = alert_templates._bucketed_value(df, "ratio", "D")
    assert pd.isna(daily_vals.iloc[0])
    assert daily_vals.iloc[1] == 300.0


def test_stock_bucket_takes_the_last_days_value_not_a_sum():
    # churn_risk is a snapshot: the month's value is the LAST day's count, not
    # a sum of all days' counts (which would double-count the same customers).
    df = _daily([("2026-01-01", 300, 1), ("2026-01-15", 310, 1), ("2026-01-31", 320, 1)])
    monthly = alert_templates._bucketed_value(df, "stock", "MS")
    assert monthly.loc["2026-01-01"] == 320


# --- template evaluators, with _daily_series monkeypatched (synthetic data)
def _patch_daily_series(monkeypatch, df: pd.DataFrame):
    monkeypatch.setattr(alert_templates, "_daily_series", lambda client_id, metric, anchor: df)
    monkeypatch.setattr(alert_templates, "_anchor_date", lambda client_id: date(2026, 6, 30))


def test_pct_change_dod_drop_breaches(monkeypatch):
    df = _daily([("2026-06-29", 100, 1), ("2026-06-30", 80, 1)])
    _patch_daily_series(monkeypatch, df)
    reading = alert_templates.evaluate_current(
        "ecommerce", "revenue", "pct_change", {"window": "dod", "direction": "drop", "threshold_pct": 15}
    )
    assert reading["value"] == -20.0
    from sema_core.alerts_engine import _passes

    assert _passes(reading["condition"], reading["value"]) is True


def test_pct_change_below_threshold_does_not_breach(monkeypatch):
    df = _daily([("2026-06-29", 100, 1), ("2026-06-30", 90, 1)])  # -10%, threshold is 15%
    _patch_daily_series(monkeypatch, df)
    reading = alert_templates.evaluate_current(
        "ecommerce", "revenue", "pct_change", {"window": "dod", "direction": "drop", "threshold_pct": 15}
    )
    from sema_core.alerts_engine import _passes

    assert _passes(reading["condition"], reading["value"]) is False


def test_absolute_threshold_below_breaches(monkeypatch):
    df = _daily([("2026-06-30", 50, 1)])
    _patch_daily_series(monkeypatch, df)
    reading = alert_templates.evaluate_current(
        "ecommerce", "orders", "absolute_threshold", {"operator": "below", "value": 100}
    )
    assert reading["value"] == 50.0
    from sema_core.alerts_engine import _passes

    assert _passes(reading["condition"], reading["value"]) is True


def test_anomaly_flags_a_clear_outlier(monkeypatch):
    # 28 CONTIGUOUS baseline days (mean=100, std>0) ending the day before the
    # anchor, then one final day way outside that baseline.
    dates = pd.date_range(end=pd.Timestamp("2026-06-29"), periods=28, freq="D")
    values = [95.0, 105.0] * 14
    df = pd.DataFrame({"d": dates, "num": values, "den": 1})
    df = pd.concat([df, pd.DataFrame({"d": [pd.Timestamp("2026-06-30")], "num": [400.0], "den": [1]})], ignore_index=True)
    _patch_daily_series(monkeypatch, df)
    reading = alert_templates.evaluate_current("ecommerce", "revenue", "anomaly", {"n_sigma": 2})
    assert reading["value"] > 2
    from sema_core.alerts_engine import _passes

    assert _passes(reading["condition"], reading["value"]) is True


def test_streak_of_consecutive_drops_hits(monkeypatch):
    df = _daily(
        [("2026-06-26", 100, 1), ("2026-06-27", 90, 1), ("2026-06-28", 80, 1), ("2026-06-29", 70, 1), ("2026-06-30", 60, 1)]
    )
    _patch_daily_series(monkeypatch, df)
    reading = alert_templates.evaluate_current("ecommerce", "revenue", "streak", {"n_days": 3, "direction": "drop"})
    assert reading["value"] == 1.0


def test_streak_broken_by_an_uptick_does_not_hit(monkeypatch):
    df = _daily(
        [("2026-06-26", 100, 1), ("2026-06-27", 90, 1), ("2026-06-28", 95, 1), ("2026-06-29", 70, 1), ("2026-06-30", 60, 1)]
    )
    _patch_daily_series(monkeypatch, df)
    reading = alert_templates.evaluate_current("ecommerce", "revenue", "streak", {"n_days": 3, "direction": "drop"})
    assert reading["value"] == 0.0


def test_evaluate_current_returns_none_value_when_series_is_empty(monkeypatch):
    _patch_daily_series(monkeypatch, pd.DataFrame(columns=["d", "num", "den"]))
    reading = alert_templates.evaluate_current(
        "ecommerce", "revenue", "pct_change", {"window": "mom", "direction": "drop", "threshold_pct": 8}
    )
    assert reading["value"] is None


# --- dry_run: historical fire counting
def test_dry_run_counts_every_breaching_day_in_the_window(monkeypatch):
    # 5 days: last 2 are below the threshold of 100.
    df = _daily([("2026-06-26", 150, 1), ("2026-06-27", 150, 1), ("2026-06-28", 150, 1), ("2026-06-29", 50, 1), ("2026-06-30", 50, 1)])
    _patch_daily_series(monkeypatch, df)
    result = alert_templates.dry_run("ecommerce", "orders", "absolute_threshold", {"operator": "below", "value": 100}, days=90)
    assert result["ok"] is True
    assert result["fire_count"] == 2
    assert result["fire_dates"] == ["2026-06-29", "2026-06-30"]


def test_dry_run_respects_the_days_window(monkeypatch):
    # A dense, fully-populated 200-day series (matching what the real
    # reindexed daily_series always looks like) at a comfortable 500, with
    # exactly 2 days dropped to a breaching 50: one 100 days before the
    # anchor (outside a 90-day window), one 10 days before (inside it).
    dates = pd.date_range(end=pd.Timestamp("2026-06-30"), periods=200, freq="D")
    values = [500] * len(dates)
    values[dates.get_loc(pd.Timestamp("2026-03-22"))] = 50  # 100 days before the anchor
    values[dates.get_loc(pd.Timestamp("2026-06-20"))] = 50  # 10 days before the anchor
    df = pd.DataFrame({"d": dates, "num": values, "den": 1})
    _patch_daily_series(monkeypatch, df)
    result = alert_templates.dry_run("ecommerce", "orders", "absolute_threshold", {"operator": "below", "value": 100}, days=90)
    assert result["ok"] is True
    assert result["fire_dates"] == ["2026-06-20"]


def test_dry_run_reports_ok_false_for_an_unsupported_metric():
    result = alert_templates.dry_run("ecommerce", "active_customers", "absolute_threshold", {"operator": "above", "value": 1})
    assert result["ok"] is False
    assert result["fire_count"] == 0
    assert "Unsupported metric" in result["error"]
