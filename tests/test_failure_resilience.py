"""
Failure-mode resilience (backend_qa_prompt.md item 3).

LLM timeout/429/500 failover and the /api/chat + /api/chat/stream error
shapes are already covered elsewhere (tests/test_agent_run.py's
test_both_models_down_is_unavailable_without_false_notice --
anthropic.APIError is the base class both RateLimitError and
InternalServerError/APITimeoutError subclass, so one fake covers all three;
tests/test_api_chat.py's test_backend_exception_does_not_leak_internals;
tests/test_api_chat_stream.py's test_stream_emits_error_event_on_failure).
This file covers the angles the QA sweep asks for that aren't exercised
anywhere yet: a truncated/malformed model response, that a FAILED turn never
corrupts a conversation (the next question still works), Postgres
connection failures at the tool layer, /healthz recovery without a restart,
and that conversation state survives a simulated API process restart.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from types import SimpleNamespace

import api.main as main
from sema_core.agent import agent
from sema_core.agent.tools import AgentTools
from sema_core.conversation_store import SqliteConversationStore


def _events(raw: str) -> list[tuple[str, dict]]:
    out = []
    for frame in raw.split("\n\n"):
        if not frame.strip():
            continue
        lines = frame.splitlines()
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        out.append((event, data))
    return out


# --- 1. malformed / truncated model response ---------------------------------


def test_truncated_response_with_no_text_never_crashes_the_loop():
    """stop_reason="max_tokens" with content that never got to a text block
    (a real truncation shape, not scripted intentionally by us) must degrade
    to SOME response, never raise -- response.stop_reason != "tool_use" falls
    into the prose-answer branch (agent.py:403-409), which joins whatever
    text blocks exist (zero, here)."""
    fake = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **kw: SimpleNamespace(
                stop_reason="max_tokens", content=[], usage=None,
            )
        )
    )
    resp = agent.run("How is revenue?", client=fake)
    # The real assertion is simply that this line was reached at all --
    # a truncated response must never raise out of agent.run().
    assert resp["insight_text"] == ""


def test_present_answer_with_missing_fields_degrades_not_crashes():
    """A present_answer tool call with most fields missing (SDK-guaranteed by
    the tool schema in real life, but defend anyway) must still produce a
    valid response via build_response's .get()-with-defaults, not a
    KeyError."""
    fake = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **kw: SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    SimpleNamespace(
                        type="tool_use", name="present_answer", input={}, id="tu_1"
                    )
                ],
                usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            )
        )
    )
    resp = agent.run("How is revenue?", client=fake)
    assert resp["insight_text"] == ""
    assert resp["recommended_actions"] == []


# --- 2. a failed turn never corrupts the conversation -------------------------


def test_chat_conversation_survives_a_failed_turn(monkeypatch):
    """The route persists a turn ONLY on success (api/main.py's own comment:
    "a failed run leaves the conversation/thread as it was"). Prove that
    end-to-end: a first successful question, a second question whose
    get_response raises, then a third successful question -- the failed
    middle turn must leave no trace and not block the conversation."""
    client = TestClient(main.app)

    monkeypatch.setattr(
        main, "get_response",
        lambda q, history=None, request_id=None, on_progress=None, **kw: {
            "insight_text": "First answer.", "recommended_actions": [],
        },
    )
    r1 = client.post("/api/chat", json={"question": "how is revenue?"})
    assert r1.status_code == 200
    conv_id = r1.json()["conversation_id"]

    def boom(*a, **k):
        raise RuntimeError("simulated LLM/DB outage")

    monkeypatch.setattr(main, "get_response", boom)
    r2 = client.post("/api/chat", json={"question": "and orders?", "conversation_id": conv_id})
    assert r2.status_code == 200  # never a 500 -- graceful error shape
    assert r2.json()["status"] == "error"

    # The failed turn left NO trace: still exactly the one successful exchange.
    messages = main.conversation_store.get_messages(conv_id, client_id="ecommerce")
    assert len(messages) == 2  # user + assistant, from the FIRST question only
    assert messages[0]["content"] == "how is revenue?"

    monkeypatch.setattr(
        main, "get_response",
        lambda q, history=None, request_id=None, on_progress=None, **kw: {
            "insight_text": "Third answer.", "recommended_actions": [],
        },
    )
    r3 = client.post("/api/chat", json={"question": "and AOV?", "conversation_id": conv_id})
    assert r3.status_code == 200
    assert r3.json()["status"] == "ok"
    assert r3.json()["answer"] == "Third answer."

    messages_after = main.conversation_store.get_messages(conv_id, client_id="ecommerce")
    assert len(messages_after) == 4  # the first exchange, plus the third (not the failed second)


def test_chat_stream_conversation_survives_a_failed_turn(monkeypatch):
    """Same guarantee, streaming variant."""
    client = TestClient(main.app)

    monkeypatch.setattr(
        main, "get_response",
        lambda q, history=None, request_id=None, on_progress=None, **kw: {
            "insight_text": "First answer.", "recommended_actions": [],
        },
    )
    with client.stream("POST", "/api/chat/stream", json={"question": "how is revenue?"}) as resp:
        raw = "".join(resp.iter_text())
    conv_id = _events(raw)[-1][1]["conversation_id"]

    monkeypatch.setattr(main, "get_response", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with client.stream(
        "POST", "/api/chat/stream", json={"question": "and orders?", "conversation_id": conv_id}
    ) as resp:
        raw2 = "".join(resp.iter_text())
    events2 = _events(raw2)
    assert events2[-1][0] == "error"  # terminal state reached, stream ends cleanly

    messages = main.conversation_store.get_messages(conv_id, client_id="ecommerce")
    assert len(messages) == 2  # the failed turn left no trace


# --- 3. Postgres unavailable at the tool layer --------------------------------


def test_run_sql_survives_a_connection_failure(monkeypatch):
    """A real Postgres outage surfaces as some exception from run_sql_readonly
    (OperationalError in production; any Exception here, since the tool's own
    except-clause is intentionally broad -- see its comment "timeout, SQL
    error caught by Postgres, etc."). Must degrade to a structured {"error":
    ...} tool result, never raise into the agent loop."""
    import sema_core.agent.tools as tools_mod

    def boom(sql):
        raise ConnectionError("could not connect to server: Connection refused\nsecond line detail")

    monkeypatch.setattr(tools_mod, "run_sql_readonly", boom)
    monkeypatch.setattr(tools_mod, "validate_and_prepare", lambda q: q)

    t = AgentTools(scope_id="full")
    result = t.run_sql("SELECT 1")

    assert "error" in result
    assert "Query failed" in result["error"]
    # Only the first line of the driver error is surfaced -- no multi-line
    # internal detail leak.
    assert "second line detail" not in result["error"]
    assert t.failures and t.failures[0]["stage"] == "execution"


def test_healthz_recovers_without_restart(monkeypatch):
    """The exact inverse direction of test_healthz.py's own down-detection
    test -- explicit proof of the QA prompt's own "recovery works without
    restart once DB returns" criterion, all within one running process."""
    client = TestClient(main.app)

    monkeypatch.setattr(main, "check_connection", lambda cid: False)
    assert client.get("/healthz").json()["db_connected"] is False

    monkeypatch.setattr(main, "check_connection", lambda cid: True)
    assert client.get("/healthz").json()["db_connected"] is True


# --- 4. API restart mid-conversation -------------------------------------------


def test_conversation_survives_a_simulated_process_restart(tmp_path):
    """Conversation state lives in a SQLite FILE, not process memory -- a
    fresh Store instance pointed at the same path (standing in for a new
    process after a restart) must see exactly what was there before,
    including mid-conversation. No API-level orphaned in-flight state exists
    to lose: /api/chat only ever persists a turn AFTER get_response returns
    (see the turn-integrity tests above), so there is no partial-turn state
    a restart could strand."""
    db_path = tmp_path / "restart_test.db"
    before_restart = SqliteConversationStore(db_path)
    conv_id = before_restart.create("ecommerce")
    before_restart.append(conv_id, "ecommerce", "user", "how is revenue?")
    before_restart.append(conv_id, "ecommerce", "assistant", "Revenue is up 12%.")

    # Simulate a process restart: a brand-new Store instance, same file, no
    # shared Python state with the one above.
    after_restart = SqliteConversationStore(db_path)
    messages = after_restart.get_messages(conv_id, client_id="ecommerce")
    assert [m["content"] for m in messages] == ["how is revenue?", "Revenue is up 12%."]

    # And it's still fully usable afterward -- not read-only/stale.
    after_restart.append(conv_id, "ecommerce", "user", "and orders?")
    assert len(after_restart.get_messages(conv_id, client_id="ecommerce")) == 3


# --- 5. explicit timeouts exist for LLM calls ----------------------------------


def test_anthropic_client_is_constructed_with_explicit_timeout_and_retries(monkeypatch):
    """Structural check backing the findings report: a slow/flaky Anthropic
    call must not hang a request indefinitely. agent.run() builds its own
    client from settings when none is injected (agent.py ~line 260)."""
    captured = {}

    class FakeAnthropic:
        def __init__(self, **kw):
            captured.update(kw)
            self.messages = SimpleNamespace(
                create=lambda **kw: SimpleNamespace(
                    stop_reason="tool_use",
                    content=[SimpleNamespace(type="tool_use", name="present_answer", input={}, id="tu_1")],
                    usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                )
            )

    monkeypatch.setattr(agent, "api_key_configured", lambda: True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    import sys
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=FakeAnthropic))

    agent.run("How is revenue?", client=None)

    assert captured.get("timeout") == agent.settings.anthropic_timeout_s
    assert captured.get("max_retries") == agent.settings.anthropic_max_retries
    assert captured["timeout"] and captured["timeout"] > 0


def test_sql_statement_timeout_is_configured():
    """Structural check: the read-only Postgres role's session sets
    statement_timeout from settings, so a runaway query can't hang a request
    indefinitely either. sema_core/db.py wires this into the read-only pool's
    connection options."""
    from sema_core import db as db_mod

    assert db_mod.READONLY_TIMEOUT_MS > 0
    assert db_mod.READONLY_TIMEOUT_MS == db_mod.settings.statement_timeout_ms
