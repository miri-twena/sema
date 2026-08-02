"""
Per-user daily LLM query soft cap (backend_qa_prompt.md item 5).

sema_core/query_limit_store.py counts server-side per (client_id,
org_user_id, UTC day); api/main.py's _check_daily_query_limit gates
/api/chat + /api/chat/stream before calling get_response, returning a plain
response dict (mode="access_denied", same quiet pattern as a data-scope
refusal) that flows through the EXACT SAME persistence/streaming code every
other answer does -- no route-level special casing.
"""

from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

import api.main as main
from sema_core.query_limit_store import QueryLimitStore

CID = "ecommerce"


def _client(monkeypatch, limit: int = 3) -> TestClient:
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, daily_query_limit=limit))
    monkeypatch.setattr(
        main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"}
    )
    monkeypatch.setattr(
        main, "get_response",
        lambda q, history=None, request_id=None, on_progress=None, **kw: {
            "insight_text": "Real answer.", "recommended_actions": [],
        },
    )
    return TestClient(main.app)


# --- store-level ---------------------------------------------------------------


def test_increment_and_get_counts_up_from_one(tmp_path):
    store = QueryLimitStore(tmp_path / "q.db")
    assert store.increment_and_get(CID, "u1", "2026-08-02") == 1
    assert store.increment_and_get(CID, "u1", "2026-08-02") == 2
    assert store.increment_and_get(CID, "u1", "2026-08-02") == 3


def test_counter_is_isolated_per_user_and_per_day(tmp_path):
    store = QueryLimitStore(tmp_path / "q.db")
    store.increment_and_get(CID, "u1", "2026-08-02")
    store.increment_and_get(CID, "u1", "2026-08-02")
    assert store.get_count(CID, "u2", "2026-08-02") == 0  # different user
    assert store.get_count(CID, "u1", "2026-08-03") == 0  # different day
    assert store.get_count(CID, "u1", "2026-08-02") == 2


def test_mark_notified_once_fires_exactly_once_per_user_per_day(tmp_path):
    store = QueryLimitStore(tmp_path / "q.db")
    store.increment_and_get(CID, "u1", "2026-08-02")  # real usage always counts first
    assert store.mark_notified_once(CID, "u1", "2026-08-02") is True
    assert store.mark_notified_once(CID, "u1", "2026-08-02") is False
    assert store.mark_notified_once(CID, "u1", "2026-08-02") is False
    # A new day gets its own fresh notification slot.
    store.increment_and_get(CID, "u1", "2026-08-03")
    assert store.mark_notified_once(CID, "u1", "2026-08-03") is True


# --- API-level: under / at / over the cap ---------------------------------------


def test_under_the_cap_answers_normally(monkeypatch):
    client = _client(monkeypatch, limit=3)
    for _ in range(2):  # 2 requests against a limit of 3 -- still under
        resp = client.post("/api/chat", json={"question": "how is revenue?"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["answer"] == "Real answer."
        assert body["mode"] == "answer"


def test_at_the_cap_still_answers_normally(monkeypatch):
    """The Nth request against a limit of N is still allowed -- "at" the cap,
    not yet "over" it."""
    client = _client(monkeypatch, limit=3)
    for _ in range(3):
        resp = client.post("/api/chat", json={"question": "how is revenue?"})
        assert resp.json()["answer"] == "Real answer."


def test_over_the_cap_returns_the_quota_message_not_a_real_answer(monkeypatch):
    client = _client(monkeypatch, limit=3)
    for _ in range(3):
        client.post("/api/chat", json={"question": "how is revenue?"})

    resp = client.post("/api/chat", json={"question": "and orders?"})
    assert resp.status_code == 200  # never an error/5xx -- a normal policy response
    body = resp.json()
    assert body["status"] == "ok"
    assert body["mode"] == "access_denied"
    assert body["answer"] != "Real answer."
    assert "daily" in body["answer"].lower() or "מכסה" in body["answer"]
    assert body["kpis"] == []
    assert body["chart"] is None
    assert body["actions"] == []


def test_the_over_cap_turn_is_still_persisted_like_any_other_answer(monkeypatch):
    client = _client(monkeypatch, limit=1)
    r1 = client.post("/api/chat", json={"question": "q1"})
    conv_id = r1.json()["conversation_id"]
    client.post("/api/chat", json={"question": "q2", "conversation_id": conv_id})

    messages = main.conversation_store.get_messages(conv_id, client_id=CID)
    assert len(messages) == 4  # both exchanges, including the capped one
    assert messages[2]["content"] == "q2"
    assert messages[3]["role"] == "assistant"


def test_limit_zero_disables_the_cap_entirely(monkeypatch):
    client = _client(monkeypatch, limit=0)
    for _ in range(10):
        resp = client.post("/api/chat", json={"question": "how is revenue?"})
        assert resp.json()["answer"] == "Real answer."


def test_stream_endpoint_enforces_the_same_cap(monkeypatch):
    import json as json_mod

    client = _client(monkeypatch, limit=1)
    with client.stream("POST", "/api/chat/stream", json={"question": "q1"}) as resp:
        "".join(resp.iter_text())
    with client.stream("POST", "/api/chat/stream", json={"question": "q2"}) as resp:
        raw = "".join(resp.iter_text())

    last_frame = [f for f in raw.split("\n\n") if f.strip()][-1]
    event = last_frame.splitlines()[0]
    data = json_mod.loads(last_frame.splitlines()[1].removeprefix("data: "))
    assert event == "event: answer"  # a policy response, not an "error" event
    assert data["mode"] == "access_denied"


# --- audit: once per user per day, not per request ------------------------------


def test_audit_event_fires_once_per_user_per_day_not_per_request(monkeypatch):
    client = _client(monkeypatch, limit=1)
    client.post("/api/chat", json={"question": "q1"})  # consumes the 1 allowed query
    for _ in range(3):  # 3 more over-the-cap requests, same day
        client.post("/api/chat", json={"question": "another one"})

    events = main.audit_store.list_events(CID)["events"]
    limit_events = [e for e in events if e["action"] == "usage.limit_reached"]
    assert len(limit_events) == 1


# --- language follows the QUESTION, per AGENTS.md's own rule --------------------


def test_quota_message_is_hebrew_for_a_hebrew_question(monkeypatch):
    client = _client(monkeypatch, limit=1)
    client.post("/api/chat", json={"question": "מה המכירות החודש?"})
    resp = client.post("/api/chat", json={"question": "וההזמנות?"})
    assert "מכסה" in resp.json()["answer"]


def test_quota_message_is_english_for_an_english_question(monkeypatch):
    client = _client(monkeypatch, limit=1)
    client.post("/api/chat", json={"question": "how is revenue?"})
    resp = client.post("/api/chat", json={"question": "and orders?"})
    assert "daily" in resp.json()["answer"].lower()


# --- reset next day --------------------------------------------------------------


def test_cap_resets_on_a_new_day(monkeypatch):
    client = _client(monkeypatch, limit=1)
    monkeypatch.setattr(main, "query_limit_today", lambda: "2026-08-01")
    client.post("/api/chat", json={"question": "q1"})
    over = client.post("/api/chat", json={"question": "q2"})
    assert over.json()["mode"] == "access_denied"

    monkeypatch.setattr(main, "query_limit_today", lambda: "2026-08-02")
    fresh_day = client.post("/api/chat", json={"question": "q3"})
    assert fresh_day.json()["answer"] == "Real answer."


# --- no cap applied when identity doesn't resolve to a real org_user ------------


def test_no_cap_when_identity_does_not_resolve(monkeypatch):
    """current_org_user falls back to _UNSCOPED_USER (id=None) for an
    unresolvable identity -- there's no per-user row to count against, so the
    cap is a no-op, same "unscoped = unrestricted" rule every other
    identity-gated feature already applies."""
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, daily_query_limit=1))
    monkeypatch.setattr(main, "current_identity", lambda: {"client_id": CID, "email": "ghost@nowhere.com"})
    monkeypatch.setattr(
        main, "get_response",
        lambda q, history=None, request_id=None, on_progress=None, **kw: {
            "insight_text": "Real answer.", "recommended_actions": [],
        },
    )
    client = TestClient(main.app)
    for _ in range(5):
        resp = client.post("/api/chat", json={"question": "how is revenue?"})
        assert resp.json()["answer"] == "Real answer."
