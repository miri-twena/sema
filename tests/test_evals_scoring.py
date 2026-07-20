"""
Unit tests for the eval harness's PURE scoring/diff logic (evals/run_evals.py).

The full eval suite needs a live DB + billed API key, but its scoring functions
are pure (they operate on a response dict), so the logic that decides PASS/FAIL
-- and the run-to-run diff that gates CI -- can and should be tested here with
no DB and no network.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

# Load evals/run_evals.py as a module (evals/ isn't an importable package).
_EVALS = Path(__file__).resolve().parent.parent / "evals" / "run_evals.py"
_spec = importlib.util.spec_from_file_location("run_evals", _EVALS)
run_evals = importlib.util.module_from_spec(_spec)
sys.modules["run_evals"] = run_evals
_spec.loader.exec_module(run_evals)


def _resp(**over) -> dict:
    base = {"insight_text": "", "kpis": [], "charts": [], "table": None}
    base.update(over)
    return base


# --- faithfulness -----------------------------------------------------------
def test_faithful_flags_ungrounded_large_number():
    # Prose claims $2,500,000 but no KPI/table backs it -> hallucination.
    resp = _resp(
        insight_text="Revenue hit $2,500,000 last month.",
        kpis=[{"label": "Revenue", "value": 1698041, "format": "currency"}],
    )
    assert 2_500_000.0 in run_evals._faithfulness_failures(resp)


def test_faithful_passes_when_number_is_grounded():
    resp = _resp(
        insight_text="Revenue hit $1,698,041 last month.",
        kpis=[{"label": "Revenue", "value": 1698041, "format": "currency"}],
    )
    assert run_evals._faithfulness_failures(resp) == []


def test_faithful_ignores_small_numbers_and_years():
    # 13% and 2026 are below the large-number threshold -> never flagged.
    resp = _resp(insight_text="In 2026 revenue fell 13%.", kpis=[])
    assert run_evals._faithfulness_failures(resp) == []


def test_grounded_numbers_include_table_cells():
    df = pd.DataFrame({"revenue": [1698041, 1236000]})
    resp = _resp(table=df)
    grounded = run_evals._grounded_numbers(resp)
    assert 1698041.0 in grounded and 1236000.0 in grounded


# --- components -------------------------------------------------------------
def test_has_component():
    df = pd.DataFrame({"x": [1]})
    assert run_evals._has_component(_resp(kpis=[{"label": "a", "value": 1}]), "kpi")
    assert run_evals._has_component(_resp(charts=[{"kind": "line"}]), "chart")
    assert run_evals._has_component(_resp(table=df), "table")
    assert not run_evals._has_component(_resp(), "table")
    assert not run_evals._has_component(_resp(table=pd.DataFrame()), "table")  # empty df


# --- kpi format guard -------------------------------------------------------
def test_kpi_format_ok():
    resp = _resp(kpis=[{"label": "Customer ID", "value": "10234", "format": "text"}])
    assert run_evals._kpi_format_ok(resp, {"label_contains": "id", "format": "text"})
    # Same KPI but wrongly typed as a number (would render with commas) -> fail.
    bad = _resp(kpis=[{"label": "Customer ID", "value": 10234, "format": "number"}])
    assert not run_evals._kpi_format_ok(bad, {"label_contains": "id", "format": "text"})
    # No matching KPI at all -> fail (we expected one to exist).
    assert not run_evals._kpi_format_ok(_resp(), {"label_contains": "id", "format": "text"})


# --- run-to-run diff --------------------------------------------------------
def test_diff_runs_classifies_changes():
    prev = {"a": True, "b": True, "c": False, "gone": True}
    current = {"a": True, "b": False, "c": True, "new": True}
    diff = run_evals.diff_runs(prev, current)
    assert diff["regressions"] == ["b"]  # was passing, now failing
    assert diff["fixes"] == ["c"]  # was failing, now passing
    assert diff["added"] == ["new"]
    assert diff["removed"] == ["gone"]


# --- _score integration -----------------------------------------------------
def test_score_component_and_faithful_assertions():
    df = pd.DataFrame({"rev": [1698041]})
    resp = _resp(
        insight_text="Revenue was $1,698,041.",
        table=df,
        charts=[{"kind": "line"}],
        sql_used="SELECT 1",
    )
    checks = dict(
        (name, ok)
        for name, ok, _ in run_evals._score(
            resp,
            {"expects_components": ["chart", "table"], "faithful": True, "expects_sql": True},
        )
    )
    assert checks["component:chart"] and checks["component:table"]
    assert checks["faithful"] and checks["expects_sql"]
