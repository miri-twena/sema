"""
LLM-generated short topic titles for new conversations.

sema_core.agent.agent.generate_title asks the small/fast model for a 2-5 word
topic title (in whatever language the question is in), falling back to the
instant derive_title() trim whenever no API key is configured or the call
errors -- title generation must never be able to break a conversation. At the
API boundary, /api/chat and /api/chat/stream call it exactly once, right after
a brand-new conversation's first turn persists, overwriting the trim-based
title append() already set.

conftest.py's autouse _no_real_anthropic_key fixture keeps every test here
(and everywhere else) off the real network even though the developer's local
.env carries a real ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

import api.main as main
from sema_core.agent import agent
from sema_core.conversation_store import derive_title


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _response(text: str):
    return SimpleNamespace(content=[_text_block(text)])


class FakeClient:
    def __init__(self, text: str | None = None, error: Exception | None = None):
        self._text = text
        self._error = error
        self.calls = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        if self._error:
            raise self._error
        return _response(self._text)


# --- agent.generate_title (unit) ---------------------------------------------


def test_no_api_key_falls_back_to_trimmed_title():
    # conftest strips ANTHROPIC_API_KEY for every test, so this is the
    # no-client, no-key path -- must not attempt any network call.
    assert agent.generate_title("Why did revenue drop in March?") == derive_title(
        "Why did revenue drop in March?"
    )


def test_uses_the_fake_client_s_title():
    fake = FakeClient(text="Revenue drop analysis")
    assert agent.generate_title("Why did revenue drop in March?", client=fake) == "Revenue drop analysis"
    assert fake.calls == 1


def test_hebrew_question_keeps_a_hebrew_title_untranslated():
    fake = FakeClient(text="ירידת הכנסות")
    assert agent.generate_title("למה ההכנסות ירדו במרץ?", client=fake) == "ירידת הכנסות"


def test_api_error_falls_back_to_trimmed_title_not_a_crash():
    fake = FakeClient(error=RuntimeError("Anthropic is down"))
    question = "Why did revenue drop in March?"
    assert agent.generate_title(question, client=fake) == derive_title(question)


def test_blank_model_reply_falls_back_to_trimmed_title():
    fake = FakeClient(text="   ")
    question = "Why did revenue drop in March?"
    assert agent.generate_title(question, client=fake) == derive_title(question)


def test_overlong_reply_is_still_capped_like_any_other_title():
    fake = FakeClient(text="word " * 40)
    out = agent.generate_title("some question", client=fake)
    assert len(out) <= 80 and out.endswith("…")


# --- API wiring (chat / chat/stream) ------------------------------------------


def test_new_conversation_gets_the_generated_title(monkeypatch):
    monkeypatch.setattr(
        main, "get_response", lambda *a, **k: {"insight_text": "ok", "recommended_actions": []}
    )
    monkeypatch.setattr(main, "generate_title", lambda question: "Revenue drop analysis")

    from api.models import ChatRequest

    resp = main.chat(ChatRequest(question="Why did revenue drop in March?"))

    (row,) = main.conversation_store.list_conversations("ecommerce")
    assert row["id"] == resp.conversation_id
    assert row["title"] == "Revenue drop analysis"


def test_followup_question_does_not_regenerate_the_title(monkeypatch):
    monkeypatch.setattr(
        main, "get_response", lambda *a, **k: {"insight_text": "ok", "recommended_actions": []}
    )
    calls = []
    monkeypatch.setattr(main, "generate_title", lambda question: calls.append(question) or "Topic A")

    from api.models import ChatRequest

    first = main.chat(ChatRequest(question="Why did revenue drop in March?"))
    main.chat(ChatRequest(question="And by channel?", conversation_id=first.conversation_id))

    assert len(calls) == 1  # only the FIRST turn of a new conversation titles it
    (row,) = main.conversation_store.list_conversations("ecommerce")
    assert row["title"] == "Topic A"


def test_manual_rename_survives_a_later_followup(monkeypatch):
    monkeypatch.setattr(
        main, "get_response", lambda *a, **k: {"insight_text": "ok", "recommended_actions": []}
    )
    monkeypatch.setattr(main, "generate_title", lambda question: "Auto title")

    from api.models import ChatRequest, ConversationUpdate

    first = main.chat(ChatRequest(question="Why did revenue drop in March?"))
    main.update_conversation(first.conversation_id, ConversationUpdate(title="My renamed chat"))

    main.chat(ChatRequest(question="And by channel?", conversation_id=first.conversation_id))

    (row,) = main.conversation_store.list_conversations("ecommerce")
    assert row["title"] == "My renamed chat"


def test_stream_new_conversation_gets_the_generated_title(monkeypatch):
    monkeypatch.setattr(
        main,
        "get_response",
        lambda question, history=None, request_id=None, on_progress=None, **kw: {
            "insight_text": "ok",
            "recommended_actions": [],
        },
    )
    monkeypatch.setattr(main, "generate_title", lambda question: "Streamed topic")
    client = TestClient(main.app)

    with client.stream("POST", "/api/chat/stream", json={"question": "Why did revenue drop?"}) as resp:
        raw = "".join(resp.iter_text())

    last_frame = [f for f in raw.split("\n\n") if f.strip()][-1]
    conv_id = json.loads(last_frame.splitlines()[1].removeprefix("data: "))["conversation_id"]

    (row,) = main.conversation_store.list_conversations("ecommerce")
    assert row["id"] == conv_id
    assert row["title"] == "Streamed topic"
