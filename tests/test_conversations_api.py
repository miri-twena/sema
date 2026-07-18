"""
Conversation-management endpoints: list / get / patch / delete, plus the
tenant-isolation 404 rule they share with the chat routes. The store is
pointed at a temp file so no shared state leaks between tests.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import api.main as main
from api.models import ChatRequest, ConversationUpdate
from sema_core.conversation_store import SqliteConversationStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = SqliteConversationStore(tmp_path / "conv.db")
    monkeypatch.setattr(main, "conversation_store", s)
    return s


def _seed_chat(monkeypatch, question="How is revenue?"):
    """Drive one turn through the real chat route so a conversation (with a
    title and a stored answer payload) exists to manage."""
    monkeypatch.setattr(
        main,
        "get_response",
        lambda *a, **k: {"insight_text": "Revenue is up 12%.", "recommended_actions": []},
    )
    return main.chat(ChatRequest(question=question))


def test_list_reflects_a_new_chat(store, monkeypatch):
    _seed_chat(monkeypatch)
    rows = main.list_conversations()
    assert len(rows) == 1
    assert rows[0].title == "How is revenue?"
    assert rows[0].message_count == 2  # user + assistant


def test_get_conversation_restores_transcript_with_payload(store, monkeypatch):
    resp = _seed_chat(monkeypatch)
    detail = main.get_conversation(resp.conversation_id)

    assert [m.role for m in detail.messages] == ["user", "assistant"]
    # The assistant turn carries the rendered answer, so reopen isn't text-only.
    assert detail.messages[1].payload is not None
    assert detail.messages[1].payload.answer == "Revenue is up 12%."


def test_rename_pin_archive_via_patch(store, monkeypatch):
    resp = _seed_chat(monkeypatch)
    cid = resp.conversation_id

    renamed = main.update_conversation(cid, ConversationUpdate(title="Q2 revenue"))
    assert renamed.title == "Q2 revenue"

    pinned = main.update_conversation(cid, ConversationUpdate(pinned=True))
    assert pinned.pinned is True

    main.update_conversation(cid, ConversationUpdate(archived=True))
    assert main.list_conversations() == []  # archived drops out of the default list
    assert len(main.list_conversations(include_archived=True)) == 1


def test_delete_removes_the_conversation(store, monkeypatch):
    resp = _seed_chat(monkeypatch)
    main.delete_conversation(resp.conversation_id)
    assert main.list_conversations(include_archived=True) == []
    with pytest.raises(HTTPException) as exc:
        main.get_conversation(resp.conversation_id)
    assert exc.value.status_code == 404


def test_unknown_conversation_is_404(store):
    for call in (
        lambda: main.get_conversation("nope"),
        lambda: main.update_conversation("nope", ConversationUpdate(title="x")),
        lambda: main.delete_conversation("nope"),
    ):
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == 404


def test_other_tenant_cannot_touch_a_conversation(store, monkeypatch):
    resp = _seed_chat(monkeypatch)  # created under the default client (ecommerce)
    cid = resp.conversation_id
    # Same id, wrong client -> 404, indistinguishable from "unknown".
    for call in (
        lambda: main.get_conversation(cid, client_id="insurance"),
        lambda: main.update_conversation(cid, ConversationUpdate(pinned=True), client_id="insurance"),
        lambda: main.delete_conversation(cid, client_id="insurance"),
    ):
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == 404
    # Untouched for the real owner.
    assert len(main.list_conversations()) == 1


def test_unknown_client_is_404(store):
    with pytest.raises(HTTPException) as exc:
        main.list_conversations(client_id="ghost-tenant")
    assert exc.value.status_code == 404
