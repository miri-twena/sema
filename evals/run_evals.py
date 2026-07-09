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

    return results


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
    return 0 if n_pass == len(rows) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run SEMA's golden-question eval set.")
    parser.add_argument("client_id", nargs="?", default="ecommerce")
    sys.exit(run(parser.parse_args().client_id))
