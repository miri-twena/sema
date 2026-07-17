"""
/api/overview: headline KPIs for the home dashboard.

Route tests monkeypatch build_overview (the same pattern the chat tests use
with get_response); the sema_core.overview unit tests monkeypatch the
saved-report functions. No live DB is needed anywhere.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from fastapi import HTTPException

import api.main as main
from sema_core import overview as overview_mod


# --- route ------------------------------------------------------------------
def test_unknown_client_returns_404():
    with pytest.raises(HTTPException) as excinfo:
        main.overview(client_id="ghost-tenant")
    assert excinfo.value.status_code == 404


def test_overview_maps_contract_fields(monkeypatch):
    monkeypatch.setattr(
        main,
        "build_overview",
        lambda start=None, end=None: {
            "kpis": [
                {
                    "label": "Revenue · May 2026",
                    "value": 824068.05,
                    "format": "currency",
                    "delta": -15.9,
                    "delta_label": "vs prior month",
                }
            ],
            "start": "2026-05",
            "end": "2026-05",
            "available_months": ["2026-04", "2026-05"],
        },
    )
    resp = main.overview()
    assert resp.client_id
    assert resp.as_of  # freshness stamp always present
    assert (resp.start, resp.end) == ("2026-05", "2026-05")
    assert resp.available_months == ["2026-04", "2026-05"]
    assert len(resp.kpis) == 1
    assert resp.kpis[0].delta == -15.9


def test_route_forwards_the_requested_window(monkeypatch):
    seen = {}

    def spy(start=None, end=None):
        seen["window"] = (start, end)
        return {"kpis": [], "start": start, "end": end, "available_months": []}

    monkeypatch.setattr(main, "build_overview", spy)
    main.overview(start="2026-03", end="2026-05")
    assert seen["window"] == ("2026-03", "2026-05")


# --- KPI computation ---------------------------------------------------------
def _fake_reports(monkeypatch, months: dict[str, tuple[int, float]], max_date: date | None):
    """Install a fake revenue_by_month + data_bounds for `months`
    ({"2026-05": (order_count, revenue)}), plus a 3-row at-risk report."""
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
    monkeypatch.setattr(
        overview_mod.queries,
        "get_at_risk_customers",
        lambda: pd.DataFrame({"customer_id": [1, 2, 3]}),
    )


def test_default_period_is_the_latest_complete_month(monkeypatch):
    # Data runs through May 31 -> May is complete -> May is the default.
    _fake_reports(
        monkeypatch,
        {"2026-03": (1191, 824068.05), "2026-04": (1492, 1206000.0), "2026-05": (1509, 1144142.93)},
        max_date=date(2026, 5, 31),
    )
    out = overview_mod.build_overview()
    assert (out["start"], out["end"]) == ("2026-05", "2026-05")


def test_month_still_in_progress_is_never_the_default(monkeypatch):
    # Data stops mid-July: July is partial, so the default is June -- and July
    # is not even offered as a choice.
    _fake_reports(
        monkeypatch,
        {"2026-05": (1509, 1144142.93), "2026-06": (1400, 1000000.0), "2026-07": (600, 420000.0)},
        max_date=date(2026, 7, 14),
    )
    out = overview_mod.build_overview()
    assert (out["start"], out["end"]) == ("2026-06", "2026-06")
    assert out["available_months"] == ["2026-05", "2026-06"]


def test_single_month_kpis_and_mom_deltas(monkeypatch):
    _fake_reports(
        monkeypatch,
        {"2026-04": (1350, 980000.0), "2026-05": (1191, 824068.05)},
        max_date=date(2026, 5, 31),
    )
    by_label = {k["label"]: k for k in overview_mod.build_overview()["kpis"]}

    revenue = by_label["Revenue · May 2026"]
    assert revenue["value"] == 824068.05
    assert revenue["delta"] == -15.9
    assert revenue["delta_label"] == "vs prior month"

    assert by_label["Orders · May 2026"]["delta"] == -11.8
    assert by_label["AOV · May 2026"]["value"] == round(824068.05 / 1191, 2)
    assert by_label["At-Risk Customers"]["value"] == 3  # snapshot, not period-scoped


def test_multi_month_window_sums_and_compares_to_prior_window(monkeypatch):
    _fake_reports(
        monkeypatch,
        {
            "2026-01": (100, 1000.0),
            "2026-02": (100, 1000.0),  # prior window: 2000 total
            "2026-03": (150, 1500.0),
            "2026-04": (150, 1500.0),  # selected window: 3000 total -> +50%
        },
        max_date=date(2026, 4, 30),
    )
    by_label = {k["label"]: k for k in overview_mod.build_overview(start="2026-03", end="2026-04")["kpis"]}

    revenue = by_label["Revenue · Mar 2026 – Apr 2026"]
    assert revenue["value"] == 3000.0
    assert revenue["delta"] == 50.0
    assert revenue["delta_label"] == "vs prior 2 months"
    assert by_label["Orders · Mar 2026 – Apr 2026"]["value"] == 300


def test_no_baseline_window_yields_no_delta(monkeypatch):
    # Only one month of data -> nothing to compare against.
    _fake_reports(monkeypatch, {"2026-05": (1509, 1144142.93)}, max_date=date(2026, 5, 31))
    kpis = overview_mod.build_overview()["kpis"]
    assert all(k.get("delta") is None for k in kpis)


def test_partial_baseline_is_not_used(monkeypatch):
    # A 2-month window with only 1 prior month must not report a delta against
    # that single month -- it would understate the baseline.
    _fake_reports(
        monkeypatch,
        {"2026-02": (100, 1000.0), "2026-03": (150, 1500.0), "2026-04": (150, 1500.0)},
        max_date=date(2026, 4, 30),
    )
    kpis = overview_mod.build_overview(start="2026-03", end="2026-04")["kpis"]
    by_label = {k["label"]: k for k in kpis}
    assert by_label["Revenue · Mar 2026 – Apr 2026"]["delta"] is None


@pytest.mark.parametrize(
    "start, end",
    [
        ("1999-01", "1999-02"),  # months we don't have
        ("nonsense", None),  # unparseable
        ("2026-05", "2026-03"),  # inverted -> swapped, not an error
    ],
)
def test_bad_window_never_errors(monkeypatch, start, end):
    _fake_reports(
        monkeypatch,
        {"2026-03": (100, 1000.0), "2026-04": (100, 1000.0), "2026-05": (100, 1000.0)},
        max_date=date(2026, 5, 31),
    )
    out = overview_mod.build_overview(start=start, end=end)
    assert out["start"] in out["available_months"]
    assert out["end"] in out["available_months"]
    assert out["start"] <= out["end"]


def test_unknown_bounds_treats_every_month_as_selectable(monkeypatch):
    # Without a max date we can't prove a month is partial -- better to show
    # the data than to hide it.
    _fake_reports(monkeypatch, {"2026-04": (100, 1000.0), "2026-05": (100, 1000.0)}, max_date=None)
    out = overview_mod.build_overview()
    assert out["available_months"] == ["2026-04", "2026-05"]
    assert out["end"] == "2026-05"


def test_failed_report_hides_its_kpis_not_the_endpoint(monkeypatch):
    def boom():
        raise RuntimeError("relation 'orders' does not exist")

    monkeypatch.setattr(overview_mod.queries, "get_revenue_by_month", boom)
    monkeypatch.setattr(overview_mod.queries, "get_data_bounds", boom)
    monkeypatch.setattr(
        overview_mod.queries,
        "get_at_risk_customers",
        lambda: pd.DataFrame({"customer_id": [1]}),
    )
    out = overview_mod.build_overview()
    assert [k["label"] for k in out["kpis"]] == ["At-Risk Customers"]
    assert out["available_months"] == []
    assert out["start"] is None


def test_all_reports_failing_yields_empty_overview(monkeypatch):
    def boom():
        raise RuntimeError("no tables here")

    for name in ("get_revenue_by_month", "get_data_bounds", "get_at_risk_customers"):
        monkeypatch.setattr(overview_mod.queries, name, boom)
    out = overview_mod.build_overview()
    assert out["kpis"] == []
    assert out["available_months"] == []
