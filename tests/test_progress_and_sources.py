"""
Analysis progress & data-source transparency.

Two guarantees are under test:
  1. Every progress stage the client can render corresponds to a real tool
     dispatch (no timers, no invented stages, no fake row counts).
  2. Nothing private -- system prompt text, raw model messages, credentials --
     ever reaches the streamed payload.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.serialize import to_chat_response
from sema_core.agent import agent
from sema_core.agent.response import build_response


# --- harness -----------------------------------------------------------------
def _tool_block(name: str, tool_input: dict, block_id: str = "tu"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=block_id)


def _resp(stop_reason: str, content: list):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=content,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


class FakeClient:
    def __init__(self, responses):
        self._r = list(responses)

        self.messages = SimpleNamespace(create=lambda **kw: self._r.pop(0) if len(self._r) > 1 else self._r[0])


class FakeTools:
    def __init__(self, dfs, failures=None):
        self.results = [{"sql": s, "df": d} for s, d in dfs]
        self.failures = list(failures or [])


def _df(n=3):
    return pd.DataFrame({"month": [f"2026-0{i + 1}" for i in range(n)], "revenue": range(1, n + 1)})


def _capture(responses, question="What was revenue in March 2026?"):
    """Run the agent loop with a scripted model, collecting progress events."""
    events: list[dict] = []
    fake = FakeClient(responses)
    resp = agent.run(question, client=fake, on_progress=events.append)
    return resp, events


ANSWER = {
    "mode": "answer",
    "insight_text": "Revenue grew.",
    "recommended_actions": [],
    "evidence": {"semantic_definitions": ["revenue"], "filters_applied": ["status = 'completed'"]},
}


# --- 1. single query: real stages + real source metadata ---------------------
def test_single_query_emits_real_stages_and_sources(monkeypatch):
    monkeypatch.setattr(
        agent.AgentTools,
        "dispatch",
        lambda self, name, ti: (
            self.results.append({"sql": "SELECT 1 FROM orders", "df": _df(2)})
            or {"row_count": 2, "sql_executed": "SELECT 1 FROM orders"}
        ),
    )
    resp, events = _capture(
        [
            _resp("tool_use", [_tool_block("run_sql", {"query": "SELECT 1 FROM orders"})]),
            _resp("tool_use", [_tool_block("present_answer", ANSWER)]),
        ]
    )
    stages = [e["stage"] for e in events]
    assert stages == ["run_sql", "run_sql_done", "writing"]
    done = events[1]
    assert done["index"] == 1
    assert done["rows"] == 2  # the REAL row count, straight from the tool result
    assert done["tables"] == ["orders"]
    ev = resp["evidence"]
    assert ev["query_status"] == "ok" and ev["queries_run"] == 1
    assert ev["data_sources"] == ["orders"]


# --- 2. multi-query: ordered, correctly numbered ------------------------------
def test_multi_query_progress_is_ordered_and_numbered(monkeypatch):
    def dispatch(self, name, ti):
        i = len(self.results) + 1
        self.results.append({"sql": f"SELECT {i} FROM orders", "df": _df(i)})
        return {"row_count": i, "sql_executed": f"SELECT {i} FROM orders"}

    monkeypatch.setattr(agent.AgentTools, "dispatch", dispatch)
    _, events = _capture(
        [
            _resp(
                "tool_use",
                [
                    _tool_block("run_sql", {"query": "a"}, "t1"),
                    _tool_block("run_sql", {"query": "b"}, "t2"),
                ],
            ),
            _resp("tool_use", [_tool_block("present_answer", ANSWER)]),
        ]
    )
    runs = [e for e in events if e["stage"] == "run_sql"]
    dones = [e for e in events if e["stage"] == "run_sql_done"]
    assert [e["index"] for e in runs] == [1, 2]
    assert [e["index"] for e in dones] == [1, 2]
    assert [e["rows"] for e in dones] == [1, 2]  # distinct, real counts
    assert events.index(runs[0]) < events.index(dones[0]) < events.index(runs[1])


# --- 3. clarification: no SQL stages at all ----------------------------------
def test_clarification_emits_no_query_stages(monkeypatch):
    monkeypatch.setattr(agent.AgentTools, "dispatch", lambda self, n, ti: {})
    resp, events = _capture(
        [
            _resp(
                "tool_use",
                [
                    _tool_block(
                        "present_answer",
                        {
                            "mode": "clarification",
                            "insight_text": "Which revenue?",
                            "clarification_options": ["Gross", "Net"],
                        },
                    )
                ],
            )
        ]
    )
    assert resp["mode"] == "clarification"
    assert not [e for e in events if str(e.get("stage", "")).startswith("run_sql")]


# --- 4. cannot_answer: no fabricated sources --------------------------------
def test_cannot_answer_reports_no_sources_and_no_verification():
    resp = build_response(
        {
            "mode": "cannot_answer",
            "reason_code": "missing_data_source",
            "insight_text": "Support tickets aren't connected.",
            "recommended_actions": [],
        },
        FakeTools([]),
    )
    ev = resp["evidence"]
    assert ev is None or (ev["data_sources"] == [] and ev["query_status"] == "none")


# --- 5. SQL failure surfaces truthfully -------------------------------------
def test_failed_query_emits_error_stage_and_failed_status(monkeypatch):
    def dispatch(self, name, ti):
        self.failures.append({"stage": "execution", "error": "syntax error"})
        return {"error": "Query failed: syntax error"}

    monkeypatch.setattr(agent.AgentTools, "dispatch", dispatch)
    resp, events = _capture(
        [
            _resp("tool_use", [_tool_block("run_sql", {"query": "SELEC 1"})]),
            _resp("tool_use", [_tool_block("present_answer", ANSWER)]),
        ]
    )
    stages = [e["stage"] for e in events]
    assert "run_sql_error" in stages
    assert "run_sql_done" not in stages  # never a false success
    # Nothing executed successfully, so the grounding gate refuses to answer and
    # there is no evidence to show. The failure stays visible through the
    # progress stages (and "Analysis details"), not through a trust panel that
    # would imply something was verified.
    assert resp["mode"] == "cannot_answer"
    assert resp["evidence"] is None


def test_failed_query_alongside_a_successful_one_is_reported_in_evidence():
    """A partial failure must not disappear: the answer is grounded in the query
    that worked, and the panel still discloses the one that didn't."""
    resp = build_response(
        ANSWER,
        FakeTools(
            [("SELECT 1 FROM orders", _df(2))],
            failures=[{"stage": "execution", "error": "syntax error"}],
        ),
    )
    ev = resp["evidence"]
    assert ev["query_status"] == "ok" and ev["queries_run"] == 1
    assert ev["queries_failed"] == 1
    assert {"op": "failed_queries", "count": 1} in ev["analysis_steps"]


# --- 6. fallback (prose) answer ---------------------------------------------
def test_prose_fallback_reports_no_execution(monkeypatch):
    monkeypatch.setattr(agent.AgentTools, "dispatch", lambda self, n, ti: {})
    resp, events = _capture([_resp("end_turn", [SimpleNamespace(type="text", text="Plain answer.")])])
    assert resp["insight_text"] == "Plain answer."
    assert not [e for e in events if str(e.get("stage", "")).startswith("run_sql")]
    assert resp.get("evidence") in (None, {}) or resp["evidence"].get("query_status") == "none"


# --- 8. multiple tables are all reported ------------------------------------
def test_multiple_tables_all_listed():
    resp = build_response(
        {**ANSWER, "kpis": []},
        FakeTools(
            [
                ("SELECT 1 FROM orders JOIN customers c ON c.id = orders.customer_id", _df(2)),
                ("SELECT 1 FROM campaigns", _df(1)),
            ]
        ),
    )
    assert resp["evidence"]["data_sources"] == ["campaigns", "customers", "orders"]
    assert resp["evidence"]["records_used"] == 3


# --- 9. missing metadata is omitted, never invented -------------------------
def test_absent_metadata_is_omitted_not_faked():
    resp = build_response(
        {"mode": "answer", "insight_text": "x", "recommended_actions": []},
        FakeTools([("SELECT 1 FROM orders", _df(1))]),
    )
    ev = resp["evidence"]
    assert ev["semantic_definitions"] == []  # not invented
    assert ev["date_range"] is None
    assert ev["filters_applied"] == []
    assert ev["assumptions"] == []
    # But the deterministic facts ARE present.
    assert ev["query_status"] == "ok" and ev["records_used"] == 1


# --- analysis steps are deterministic + factual ------------------------------
def test_analysis_steps_are_built_from_real_execution():
    resp = build_response(
        {
            **ANSWER,
            "kpis": [{"label": "Revenue", "value": 1, "format": "currency", "delta": 4.4}],
            "table": {"result_index": 0, "title": "Rows"},
        },
        FakeTools([("SELECT 1 FROM orders", _df(3))]),
    )
    steps = resp["evidence"]["analysis_steps"]
    ops = [s["op"] for s in steps]
    # Structured, language-neutral operations -- the client renders the wording,
    # so a Hebrew answer gets a Hebrew trust panel from the same payload.
    assert all(isinstance(s, dict) and "op" in s for s in steps)
    assert {"op": "metric", "name": "revenue"} in steps  # the cited metric
    assert {"op": "filter", "value": "status = 'completed'"} in steps  # reported filter
    q = next(s for s in steps if s["op"] == "queries")
    assert q["count"] == 1 and q["sources"] == ["orders"]  # the real table
    assert {"op": "rows", "count": 3} in steps  # the real row count
    assert "comparison" in ops  # a delta really was computed
    assert "table_rows" in ops


def test_evidence_names_the_real_connection():
    """Engine + database name come from the live per-client DB config, and only
    when a query actually ran -- never a hardcoded or guessed source."""
    grounded = build_response(ANSWER, FakeTools([("SELECT 1 FROM orders", _df(1))]))
    ev = grounded["evidence"]
    assert ev["data_engine"] == "PostgreSQL"
    assert ev["database"]  # resolved from db config, not invented

    # Nothing executed -> no connection claimed.
    nothing = _clean_evidence_only({"semantic_definitions": ["revenue"]}, FakeTools([]))
    assert nothing["data_engine"] is None and nothing["database"] is None


def _clean_evidence_only(raw, tools):
    from sema_core.agent.response import _clean_evidence

    return _clean_evidence(raw, tools)


def test_evidence_never_exposes_credentials_or_host():
    """The panel may name the database; it must never carry connection secrets."""
    ev = build_response(ANSWER, FakeTools([("SELECT 1 FROM orders", _df(1))]))["evidence"]
    blob = json.dumps(ev).lower()
    for secret in ("password", "sema_readonly_pw", "@", "5432", "host="):
        assert secret not in blob


def test_no_steps_claim_execution_when_nothing_ran():
    resp = build_response(
        {"mode": "off_topic", "insight_text": "🍝", "recommended_actions": []}, FakeTools([])
    )
    assert resp["evidence"] is None  # nothing to show, nothing invented


# --- 10. nothing private reaches the stream ---------------------------------
@pytest.mark.parametrize("leak", ["SEMA-CONTEXT", "You are SEMA", "ANTHROPIC_API_KEY", "system prompt"])
def test_stream_payload_contains_no_prompt_or_secret(monkeypatch, leak):
    """The SSE body must carry only stage keys, numbers and the final answer."""

    def fake_get_response(question, history=None, request_id=None, on_progress=None, **kw):
        on_progress({"stage": "run_sql", "index": 1})
        on_progress({"stage": "run_sql_done", "index": 1, "rows": 7, "tables": ["orders"]})
        return {"mode": "answer", "insight_text": "Revenue grew.", "recommended_actions": []}

    monkeypatch.setattr(main, "get_response", fake_get_response)
    with TestClient(main.app) as c:
        body = c.post("/api/chat/stream", json={"question": "revenue?"}).text
    assert leak not in body


def test_stream_status_frames_are_structured_stages(monkeypatch):
    def fake_get_response(question, history=None, request_id=None, on_progress=None, **kw):
        on_progress({"stage": "run_sql", "index": 1})
        on_progress({"stage": "run_sql_done", "index": 1, "rows": 7, "tables": ["orders"]})
        return {"mode": "answer", "insight_text": "ok", "recommended_actions": []}

    monkeypatch.setattr(main, "get_response", fake_get_response)
    with TestClient(main.app) as c:
        body = c.post("/api/chat/stream", json={"question": "revenue?"}).text

    statuses = [
        json.loads(f.split("data:", 1)[1].strip())
        for f in body.split("\n\n")
        if f.startswith("event: status")
    ]
    assert statuses[0]["stage"] == "run_sql"
    assert statuses[1] == {"stage": "run_sql_done", "index": 1, "rows": 7, "tables": ["orders"]}
    # Stage keys only -- no server-rendered prose to mis-localize.
    assert all("message" not in s for s in statuses)
