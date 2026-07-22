"""
Drill-down threads at the API boundary: /api/chat(-stream) resolving/creating a
thread when the request carries an anchor (conversation_id + turn_index +
drill_context), and the /api/conversations/{id}/threads(/{id}) read routes.

Routes are called directly (main.chat / main.list_threads / ...), same
pattern as test_conversations_api.py -- no live DB, LLM, or API key needed.
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api.main as main
from api.models import ChatRequest, ConversationUpdate, DrillContextRequest


def _events(raw: str) -> list[tuple[str, dict]]:
    """Split raw SSE text into (event_name, parsed_json_data) pairs -- same
    parsing test_api_chat_stream.py uses; kept local since test files in this
    suite are self-contained (no cross-file imports)."""
    out = []
    for frame in raw.split("\n\n"):
        if not frame.strip():
            continue
        lines = frame.splitlines()
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        out.append((event, data))
    return out


def _fake_get_response(insight_text="An answer.", **over):
    def fn(question, history=None, request_id=None, on_progress=None, **kw):
        return {"insight_text": insight_text, "recommended_actions": [], **over}

    return fn


def _seed_conversation(monkeypatch, question="How is revenue?"):
    monkeypatch.setattr(main, "get_response", _fake_get_response("Revenue is up 12%."))
    return main.chat(ChatRequest(question=question))


def _drill_request(conv_id, turn_index=0, question="Why?", kind="kpi", title="Revenue"):
    return ChatRequest(
        question=question,
        conversation_id=conv_id,
        turn_index=turn_index,
        drill_context=DrillContextRequest(kind=kind, title=title, detail="current value $1.2M"),
    )


# --- a drill turn creates/resumes a thread, not a new main conversation -------
def test_drill_turn_does_not_create_a_new_main_conversation(monkeypatch):
    seed = _seed_conversation(monkeypatch)
    before = len(main.list_conversations())

    monkeypatch.setattr(main, "get_response", _fake_get_response("Electronics drove it."))
    resp = main.chat(_drill_request(seed.conversation_id))

    assert len(main.list_conversations()) == before  # no new sidebar row
    assert resp.conversation_id == seed.conversation_id  # parent echoed back, unchanged
    assert resp.thread_id is not None


def test_reopening_the_same_widget_resumes_the_same_thread(monkeypatch):
    seed = _seed_conversation(monkeypatch)
    monkeypatch.setattr(main, "get_response", _fake_get_response("first drill answer"))
    first = main.chat(_drill_request(seed.conversation_id, question="Why is this down?"))

    monkeypatch.setattr(main, "get_response", _fake_get_response("second drill answer"))
    second = main.chat(_drill_request(seed.conversation_id, question="Any other factors?"))

    assert first.thread_id == second.thread_id
    detail = main.get_thread(seed.conversation_id, first.thread_id)
    questions = [m.content for m in detail.messages if m.role == "user"]
    assert questions == ["Why is this down?", "Any other factors?"]


def test_different_widgets_on_the_same_turn_get_different_threads(monkeypatch):
    seed = _seed_conversation(monkeypatch)
    monkeypatch.setattr(main, "get_response", _fake_get_response("x"))
    revenue = main.chat(_drill_request(seed.conversation_id, kind="kpi", title="Revenue"))
    orders = main.chat(_drill_request(seed.conversation_id, kind="kpi", title="Orders"))
    assert revenue.thread_id != orders.thread_id


def test_thread_turn_persists_the_rendered_payload(monkeypatch):
    seed = _seed_conversation(monkeypatch)
    monkeypatch.setattr(main, "get_response", _fake_get_response("Electronics drove it."))
    resp = main.chat(_drill_request(seed.conversation_id))

    detail = main.get_thread(seed.conversation_id, resp.thread_id)
    answer = [m for m in detail.messages if m.role == "assistant"][0]
    assert answer.payload is not None
    assert answer.payload.answer == "Electronics drove it."


# --- a drill with no anchor still behaves as before (home-dashboard case) -----
def test_drill_without_turn_index_still_creates_an_ordinary_conversation(monkeypatch):
    monkeypatch.setattr(main, "get_response", _fake_get_response("An answer."))
    req = ChatRequest(
        question="Why is this KPI trending down?",
        drill_context=DrillContextRequest(kind="kpi", title="Revenue", detail="$1.2M"),
        # No conversation_id, no turn_index -- e.g. a home-dashboard widget.
    )
    resp = main.chat(req)
    assert resp.thread_id is None
    assert resp.conversation_id is not None
    assert len(main.list_conversations()) == 1


# --- listing / reading threads -------------------------------------------------
def test_list_threads_reflects_a_drill(monkeypatch):
    seed = _seed_conversation(monkeypatch)
    monkeypatch.setattr(main, "get_response", _fake_get_response("x"))
    main.chat(_drill_request(seed.conversation_id, kind="kpi", title="Revenue"))

    (summary,) = main.list_threads(seed.conversation_id)
    assert summary.widget_kind == "kpi"
    assert summary.widget_title == "Revenue"
    assert summary.turn_count == 1


def test_list_threads_unknown_conversation_is_404():
    with pytest.raises(HTTPException) as exc:
        main.list_threads("nope")
    assert exc.value.status_code == 404


def test_get_thread_unknown_thread_is_404(monkeypatch):
    seed = _seed_conversation(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        main.get_thread(seed.conversation_id, "nope")
    assert exc.value.status_code == 404


def test_get_thread_wrong_parent_conversation_is_404(monkeypatch):
    seed = _seed_conversation(monkeypatch)
    monkeypatch.setattr(main, "get_response", _fake_get_response("x"))
    resp = main.chat(_drill_request(seed.conversation_id))

    other = _seed_conversation(monkeypatch, question="unrelated chat")
    with pytest.raises(HTTPException) as exc:
        main.get_thread(other.conversation_id, resp.thread_id)
    assert exc.value.status_code == 404


def test_other_tenant_cannot_read_a_thread(monkeypatch):
    seed = _seed_conversation(monkeypatch)
    monkeypatch.setattr(main, "get_response", _fake_get_response("x"))
    resp = main.chat(_drill_request(seed.conversation_id))

    with pytest.raises(HTTPException) as exc:
        main.list_threads(seed.conversation_id, client_id="insurance")
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        main.get_thread(seed.conversation_id, resp.thread_id, client_id="insurance")
    assert exc.value.status_code == 404


# --- archive is non-destructive: only delete() cascades to threads ------------
def test_archiving_the_conversation_preserves_its_threads(monkeypatch):
    seed = _seed_conversation(monkeypatch)
    monkeypatch.setattr(main, "get_response", _fake_get_response("x"))
    drilled = main.chat(_drill_request(seed.conversation_id))

    main.update_conversation(seed.conversation_id, ConversationUpdate(archived=True))

    # The thread is untouched by archiving -- still listed, still readable.
    (summary,) = main.list_threads(seed.conversation_id)
    assert summary.id == drilled.thread_id
    detail = main.get_thread(seed.conversation_id, drilled.thread_id)
    assert len(detail.messages) == 2

    # Unarchiving needs nothing to restore -- archiving never removed anything.
    main.update_conversation(seed.conversation_id, ConversationUpdate(archived=False))
    assert main.get_thread(seed.conversation_id, drilled.thread_id) is not None


# --- cascade delete -------------------------------------------------------------
def test_deleting_the_conversation_removes_its_threads(monkeypatch):
    seed = _seed_conversation(monkeypatch)
    monkeypatch.setattr(main, "get_response", _fake_get_response("x"))
    main.chat(_drill_request(seed.conversation_id))

    main.delete_conversation(seed.conversation_id)

    with pytest.raises(HTTPException) as exc:
        main.list_threads(seed.conversation_id)
    assert exc.value.status_code == 404


def test_wrong_tenant_cannot_delete_a_conversation_or_its_threads(monkeypatch):
    seed = _seed_conversation(monkeypatch)
    monkeypatch.setattr(main, "get_response", _fake_get_response("x"))
    drilled = main.chat(_drill_request(seed.conversation_id))

    with pytest.raises(HTTPException) as exc:
        main.delete_conversation(seed.conversation_id, client_id="insurance")
    assert exc.value.status_code == 404

    # The real owner's conversation AND thread are completely untouched.
    assert len(main.list_conversations()) == 1
    (summary,) = main.list_threads(seed.conversation_id)
    assert summary.id == drilled.thread_id


# --- /api/chat and /api/chat/stream share the anchor/thread logic -------------
# (via _resolve_persist_target / _persist_turn in api/main.py) -- these tests
# exercise the ACTUAL streaming endpoint end-to-end (TestClient + real SSE
# parsing), not just main.chat(), which is the only path the tests above cover.
def test_stream_drill_turn_creates_a_thread_not_a_new_conversation(monkeypatch):
    seed = _seed_conversation(monkeypatch)
    before = len(main.list_conversations())

    monkeypatch.setattr(main, "get_response", _fake_get_response("Electronics drove it."))
    client = TestClient(main.app)
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "question": "Why?",
            "conversation_id": seed.conversation_id,
            "turn_index": 0,
            "drill_context": {"kind": "kpi", "title": "Revenue", "detail": "current value $1.2M"},
        },
    ) as resp:
        raw = "".join(resp.iter_text())

    answer = _events(raw)[-1][1]
    assert len(main.list_conversations()) == before  # no new sidebar row
    assert answer["conversation_id"] == seed.conversation_id  # parent, unchanged
    assert answer["thread_id"] is not None


def test_chat_and_stream_resolve_the_same_anchor_to_the_same_thread(monkeypatch):
    """The regression this guards against: /api/chat and /api/chat/stream once
    persisted main-chat turns differently (one endpoint forgot payload=) until
    a shared helper was introduced. Same risk here if _resolve_persist_target
    were ever duplicated instead of shared -- this proves it isn't: the SAME
    anchor asked through EITHER endpoint must land in the SAME thread."""
    seed = _seed_conversation(monkeypatch)

    monkeypatch.setattr(main, "get_response", _fake_get_response("via /api/chat"))
    via_chat = main.chat(_drill_request(seed.conversation_id, question="Q1"))

    monkeypatch.setattr(main, "get_response", _fake_get_response("via /api/chat/stream"))
    client = TestClient(main.app)
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "question": "Q2",
            "conversation_id": seed.conversation_id,
            "turn_index": 0,
            "drill_context": {"kind": "kpi", "title": "Revenue", "detail": "current value $1.2M"},
        },
    ) as resp:
        raw = "".join(resp.iter_text())
    via_stream = _events(raw)[-1][1]

    assert via_stream["thread_id"] == via_chat.thread_id
    detail = main.get_thread(seed.conversation_id, via_chat.thread_id)
    assert [m.content for m in detail.messages if m.role == "user"] == ["Q1", "Q2"]
