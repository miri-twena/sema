"""
Step 4 at the API boundary: conversation_id round-trips through /api/chat,
a follow-up question gets the prior turn's context, and a conversation from
one tenant is rejected (404) if reused with another client_id. Uses the two
real clients from config/clients.yaml (ecommerce, insurance) so tenant
isolation is exercised against actual client_ids, not fabricated ones.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import api.main as main
from api.models import ChatRequest


def test_first_message_returns_a_conversation_id(monkeypatch):
    monkeypatch.setattr(
        main, "get_response", lambda *a, **k: {"insight_text": "Hi there", "recommended_actions": []}
    )
    resp = main.chat(ChatRequest(question="hello"))
    assert resp.conversation_id  # server assigned one


def test_followup_question_receives_prior_turn_as_history(monkeypatch):
    seen_histories = []

    def fake_get_response(question, history=None, request_id=None, on_progress=None, **kw):
        seen_histories.append(history)
        return {"insight_text": f"answer to: {question}", "recommended_actions": []}

    monkeypatch.setattr(main, "get_response", fake_get_response)

    first = main.chat(ChatRequest(question="How is revenue?"))
    assert seen_histories[0] == []  # nothing before the first turn

    second = main.chat(ChatRequest(question="And by category?", conversation_id=first.conversation_id))
    assert second.conversation_id == first.conversation_id
    # The follow-up call's history includes the FIRST turn's Q and answer.
    assert seen_histories[1] == [
        {"role": "user", "content": "How is revenue?"},
        {"role": "assistant", "content": "answer to: How is revenue?"},
    ]


def test_conversation_id_wins_over_client_sent_history(monkeypatch):
    seen_histories = []

    def fake_get_response(question, history=None, request_id=None, on_progress=None, **kw):
        seen_histories.append(history)
        return {"insight_text": "ok", "recommended_actions": []}

    monkeypatch.setattr(main, "get_response", fake_get_response)

    first = main.chat(ChatRequest(question="Q1"))
    main.chat(
        ChatRequest(
            question="Q2",
            conversation_id=first.conversation_id,
            history=[{"role": "user", "content": "IGNORED - client history"}],
        )
    )
    # The client-sent `history` is ignored; the server's own record wins.
    assert seen_histories[1][0]["content"] != "IGNORED - client history"


def test_conversation_from_other_tenant_is_rejected(monkeypatch):
    monkeypatch.setattr(
        main, "get_response", lambda *a, **k: {"insight_text": "ok", "recommended_actions": []}
    )
    first = main.chat(ChatRequest(question="Q1", client_id="ecommerce"))

    with pytest.raises(HTTPException) as excinfo:
        main.chat(ChatRequest(question="Q2", conversation_id=first.conversation_id, client_id="insurance"))
    assert excinfo.value.status_code == 404


def test_unknown_conversation_id_returns_404(monkeypatch):
    monkeypatch.setattr(
        main, "get_response", lambda *a, **k: {"insight_text": "ok", "recommended_actions": []}
    )
    with pytest.raises(HTTPException) as excinfo:
        main.chat(ChatRequest(question="Q", conversation_id="does-not-exist"))
    assert excinfo.value.status_code == 404
