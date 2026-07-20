"""
SEMA: golden-question eval harness.

Runs each question in evals/golden/<client>.yaml through the SAME code path a
real chat request takes (sema_core.wiring.get_response) and scores the answer
against hand-written assertions. This is the regression suite for
prompt/model changes: if a prompt tweak breaks the "why did revenue drop"
story, this catches it before a person notices in the UI.

Needs a live database and ANTHROPIC_API_KEY. NOT part of `pytest` -- it makes
real, billed LLM calls (see evals/README.md). Run:

    .venv\\Scripts\\python.exe evals\\run_evals.py [client_id]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import uuid
from pathlib import Path

import yaml

from sema_core import client_registry, wiring
from sema_core.obs import get_logger

EVALS_DIR = Path(__file__).resolve().parent
GOLDEN_DIR = EVALS_DIR / "golden"

# Rough Anthropic per-million-token rates for the cost estimate below -- EDIT
# THESE to match your actual model/plan. Not a billing source of truth, just
# a ballpark so a prompt change that balloons token usage is visible here.
USD_PER_M_INPUT_TOKENS = 3.00
USD_PER_M_OUTPUT_TOKENS = 15.00

_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")
_UP_WORDS = ("up", "increase", "grew", "grow", "rose", "rise", "higher", "peak", "growth")
_DOWN_WORDS = (
    "down", "decrease", "declin", "dropped", "drop", "fell", "fall",
    "lower", "dip", "slowdown", "softness",
)


def _extract_numbers(text: str) -> list[float]:
    out = []
    for raw in _NUMBER_RE.findall(text):
        try:
            out.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return out


# Faithfulness only inspects LARGE numbers (revenue, order/customer counts):
# years (2025) and percentages (13%) fall below this, so they don't create
# noise. A large number in the prose that matches no grounded value is the
# signature of a hallucinated figure.
_FAITHFUL_MIN = 10_000


def _grounded_numbers(resp: dict) -> set[float]:
    """Every number the answer is ALLOWED to state: KPI values (already bound to
    real query results server-side) plus every numeric cell of the result
    table. Rounded so 1698041.0 and 1698041 compare equal."""
    grounded: set[float] = set()
    for kpi in resp.get("kpis", []):
        try:
            grounded.add(round(float(kpi["value"]), 2))
        except (TypeError, ValueError, KeyError):
            pass
    table = resp.get("table")
    if table is not None and hasattr(table, "columns"):
        for col in table.columns:
            for v in table[col].tolist():
                try:
                    grounded.add(round(float(v), 2))
                except (TypeError, ValueError):
                    pass
    return grounded


def _faithfulness_failures(resp: dict, tolerance_pct: float = 1.0) -> list[float]:
    """Large numbers stated in the prose that match NO grounded value (KPI or
    table cell) within tolerance -- i.e. likely hallucinated. Returns the
    offending numbers (empty = faithful)."""
    grounded = _grounded_numbers(resp)
    offenders: list[float] = []
    for num in _extract_numbers(resp.get("insight_text", "") or ""):
        if abs(num) < _FAITHFUL_MIN:
            continue  # skip years/percentages/small counts -- too noisy to judge
        tol = abs(num) * (tolerance_pct / 100) or 0.01
        if not any(abs(num - g) <= tol for g in grounded):
            offenders.append(num)
    return offenders


def _has_component(resp: dict, kind: str) -> bool:
    """Whether the answer rendered a given component type."""
    if kind == "kpi":
        return len(resp.get("kpis") or []) > 0
    if kind == "chart":
        return len(resp.get("charts") or []) > 0
    if kind == "table":
        table = resp.get("table")
        return table is not None and getattr(table, "empty", True) is False
    return False


def _kpi_format_ok(resp: dict, spec: dict) -> bool:
    """A KPI whose label contains `label_contains` must carry `format`. Guards
    the data-level side of formatting fixes -- e.g. an ID metric must be
    format='text' so the UI never renders it with thousands separators. (The
    actual comma/K rendering is a frontend concern, tested in frontend/.)"""
    needle = str(spec.get("label_contains", "")).lower()
    want = spec.get("format")
    matches = [k for k in resp.get("kpis", []) if needle in str(k.get("label", "")).lower()]
    if not matches:
        return False  # expected such a KPI to exist
    return all(k.get("format") == want for k in matches)


class _TokenCapture(logging.Handler):
    """Pulls token usage for one request out of the agent's existing
    structured "agent_run" log line (obs.py) -- reusing the observability
    path production already has, instead of adding a second eval-only return
    value to agent.run()."""

    def __init__(self, request_id: str):
        super().__init__()
        self.request_id = request_id
        self.usage: dict | None = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            data = json.loads(record.getMessage())
        except (TypeError, ValueError):
            return
        if data.get("event") == "agent_run" and data.get("request_id") == self.request_id:
            self.usage = data


def _score(resp: dict, assertions: dict) -> list[tuple[str, bool, str]]:
    """Return (assertion_name, passed, detail) for every assertion on one question."""
    text = resp.get("insight_text", "") or ""
    haystack = " ".join([text, " ".join(resp.get("recommended_actions", []))]).lower()
    results: list[tuple[str, bool, str]] = []

    if "contains_any" in assertions:
        phrases = assertions["contains_any"]
        hit = next((p for p in phrases if p.lower() in haystack), None)
        results.append(("contains_any", hit is not None, f"looked for any of {phrases}"))

    if "direction" in assertions:
        words = _UP_WORDS if assertions["direction"] == "up" else _DOWN_WORDS
        hit = any(w in haystack for w in words)
        results.append(("direction", hit, f"expected direction={assertions['direction']}"))

    for spec in assertions.get("numeric_within", []):
        expected = spec["value"]
        tolerance = expected * (spec.get("tolerance_pct", 10) / 100)
        numbers = _extract_numbers(text)
        for kpi in resp.get("kpis", []):
            try:
                numbers.append(float(kpi["value"]))
            except (TypeError, ValueError, KeyError):
                pass
        hit = any(abs(n - expected) <= tolerance for n in numbers)
        results.append(("numeric_within", hit, f"expected ~{expected} (+/-{tolerance:.1f})"))

    if assertions.get("expects_sql"):
        results.append(("expects_sql", bool(resp.get("sql_used")), "expected run_sql to be called"))

    # Component types the answer should render (table / chart / kpi card).
    for kind in assertions.get("expects_components", []):
        results.append(
            (f"component:{kind}", _has_component(resp, kind), f"expected a {kind} in the answer")
        )

    # Data-level formatting guard (e.g. IDs must be format='text', not number).
    for spec in assertions.get("kpi_formats", []):
        results.append(
            (
                f"kpi_format:{spec.get('label_contains')}",
                _kpi_format_ok(resp, spec),
                f"expected KPI ~'{spec.get('label_contains')}' to be format={spec.get('format')}",
            )
        )

    # Faithfulness: no large hallucinated number in the prose.
    if assertions.get("faithful"):
        offenders = _faithfulness_failures(resp)
        results.append(
            ("faithful", not offenders, f"ungrounded numbers in prose: {offenders}")
        )

    # Mode gate: e.g. an ambiguous question should ask, not guess.
    if "mode" in assertions:
        results.append(
            ("mode", resp.get("mode") == assertions["mode"], f"expected mode={assertions['mode']}")
        )

    return results


# Where each run stashes its per-case PASS/FAIL, so the NEXT run can show what
# changed. Gitignored working state, one file per client.
RESULTS_DIR = EVALS_DIR / ".last_run"


def _load_previous(client_id: str) -> dict[str, bool] | None:
    """The previous run's {case_id: passed}, or None if there isn't one."""
    path = RESULTS_DIR / f"{client_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("cases", {})
    except (ValueError, OSError):
        return None


def _save_current(client_id: str, current: dict[str, bool]) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / f"{client_id}.json").write_text(
        json.dumps({"cases": current}, indent=2, sort_keys=True), encoding="utf-8"
    )


def diff_runs(prev: dict[str, bool], current: dict[str, bool]) -> dict[str, list[str]]:
    """Compare two runs' results. Regressions (was passing, now failing) are the
    ones that fail a build; fixes/added/removed are shown for context."""
    return {
        "regressions": sorted(c for c, ok in current.items() if not ok and prev.get(c) is True),
        "fixes": sorted(c for c, ok in current.items() if ok and prev.get(c) is False),
        "added": sorted(c for c in current if c not in prev),
        "removed": sorted(c for c in prev if c not in current),
    }


def _print_diff(diff: dict[str, list[str]]) -> None:
    labels = [
        ("regressions", "REGRESSED (was passing)"),
        ("fixes", "FIXED (was failing)"),
        ("added", "NEW cases"),
        ("removed", "REMOVED cases"),
    ]
    if not any(diff[k] for k, _ in labels):
        print("diff vs last run: no changes")
        return
    print("diff vs last run:")
    for key, label in labels:
        if diff[key]:
            print(f"  {label}: {', '.join(diff[key])}")


def run(client_id: str) -> int:
    golden_path = GOLDEN_DIR / f"{client_id}.yaml"
    if not golden_path.exists():
        print(f"No golden file for client '{client_id}': {golden_path}")
        return 1

    with golden_path.open(encoding="utf-8") as f:
        cases = yaml.safe_load(f)["questions"]

    client_registry.set_active_client_override(client_id)
    agent_logger = get_logger("agent")

    total_input = total_output = 0
    rows: list[tuple[str, bool, list]] = []

    try:
        for case in cases:
            request_id = uuid.uuid4().hex[:12]
            capture = _TokenCapture(request_id)
            agent_logger.addHandler(capture)
            try:
                resp = wiring.get_response(case["question"], request_id=request_id)
            finally:
                agent_logger.removeHandler(capture)

            checks = _score(resp, case.get("assertions", {}))
            rows.append((case["id"], all(ok for _, ok, _ in checks), checks))

            if capture.usage:
                total_input += capture.usage.get("input_tokens", 0)
                total_output += capture.usage.get("output_tokens", 0)
    finally:
        client_registry.set_active_client_override(None)

    print(f"\nSEMA golden-question eval -- client={client_id}\n" + "=" * 60)
    for case_id, passed, checks in rows:
        print(f"[{'PASS' if passed else 'FAIL'}] {case_id}")
        for name, ok, detail in checks:
            if not ok:
                print(f"       - {name}: FAILED ({detail})")

    n_pass = sum(1 for _, p, _ in rows if p)
    cost = (
        total_input / 1_000_000 * USD_PER_M_INPUT_TOKENS
        + total_output / 1_000_000 * USD_PER_M_OUTPUT_TOKENS
    )
    print("=" * 60)
    print(f"{n_pass}/{len(rows)} passed")
    print(
        f"tokens: {total_input} in / {total_output} out "
        f"(~${cost:.4f} at ${USD_PER_M_INPUT_TOKENS}/M in, "
        f"${USD_PER_M_OUTPUT_TOKENS}/M out -- edit rates at the top of this file)"
    )

    # Run-to-run diff: compare against the previous run, then persist this one.
    current = {case_id: passed for case_id, passed, _ in rows}
    prev = _load_previous(client_id)
    regressions: list[str] = []
    if prev is not None:
        diff = diff_runs(prev, current)
        regressions = diff["regressions"]
        _print_diff(diff)
    _save_current(client_id, current)

    # Fail the build on any regression (a case that used to pass now fails), or
    # if not every case passes. Regressions are called out separately so CI
    # shows exactly what a prompt/model change broke.
    if regressions:
        print(f"FAILED: {len(regressions)} regression(s): {', '.join(regressions)}")
        return 1
    return 0 if n_pass == len(rows) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run SEMA's golden-question eval set.")
    parser.add_argument("client_id", nargs="?", default="ecommerce")
    sys.exit(run(parser.parse_args().client_id))
