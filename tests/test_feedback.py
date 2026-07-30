"""
Tests for per-answer thumbs up/down feedback (answer_feedback_prompt.md).

Store-level tests use a local `store` fixture (a fresh temp-file
TurnFeedbackStore per test). Route-level tests seed a real conversation by
driving one turn through the actual chat route (same `_seed_chat` idiom as
test_conversations_api.py), then call the feedback route directly or via
TestClient (needed for the JSON-level 422 validation tests).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api.main as main
from api.models import ChatRequest, FeedbackRequest
from sema_core.feedback_store import InvalidRatingError, TurnFeedbackStore

CID = "ecommerce"


@pytest.fixture
def store(tmp_path) -> TurnFeedbackStore:
    return TurnFeedbackStore(tmp_path / "feedback.db")


def _seed_chat(monkeypatch, question="How is revenue?"):
    monkeypatch.setattr(
        main, "get_response", lambda *a, **k: {"insight_text": "Revenue is up 12%.", "recommended_actions": []}
    )
    return main.chat(ChatRequest(question=question))


# --- store --------------------------------------------------------------------
def test_set_and_get(store):
    store.set("c1", CID, 0, "up", None, "u1")
    row = store.get("c1", 0)
    assert row["rating"] == "up"
    assert row["comment"] is None
    assert row["user_id"] == "u1"


def test_resubmitting_a_rating_updates_the_same_row_not_a_new_one(store):
    first = store.set("c1", CID, 0, "up", None, "u1")
    store.set("c1", CID, 0, "down", None, "u1")
    second = store.get("c1", 0)
    assert second["id"] == first["id"]  # same row, upserted
    assert second["rating"] == "down"


def test_adding_a_comment_as_a_follow_up_update_keeps_the_rating(store):
    store.set("c1", CID, 0, "down", None, "u1")
    store.set("c1", CID, 0, "down", "The SQL was wrong", "u1")
    row = store.get("c1", 0)
    assert row["rating"] == "down"
    assert row["comment"] == "The SQL was wrong"


def test_clear_deletes_the_row(store):
    store.set("c1", CID, 0, "up", None, "u1")
    store.clear("c1", 0)
    assert store.get("c1", 0) is None


def test_clear_on_a_nonexistent_row_is_a_silent_noop(store):
    store.clear("c1", 0)  # nothing to clear -- must not raise


def test_invalid_rating_is_rejected(store):
    with pytest.raises(InvalidRatingError):
        store.set("c1", CID, 0, "sideways", None, "u1")


def test_feedback_is_scoped_per_conversation_and_turn(store):
    store.set("c1", CID, 0, "up", None, "u1")
    store.set("c1", CID, 1, "down", None, "u1")
    store.set("c2", CID, 0, "up", None, "u2")
    assert store.get("c1", 0)["rating"] == "up"
    assert store.get("c1", 1)["rating"] == "down"
    assert store.get("c2", 0)["user_id"] == "u2"


def test_get_for_conversation_returns_everything_keyed_by_turn_index(store):
    store.set("c1", CID, 0, "up", None, "u1")
    store.set("c1", CID, 2, "down", "bad math", "u1")
    by_turn = store.get_for_conversation("c1")
    assert set(by_turn) == {0, 2}
    assert by_turn[2]["comment"] == "bad math"


# --- route: submit / update / clear ---------------------------------------------
def test_submit_feedback_route_creates_a_rating(monkeypatch):
    resp = _seed_chat(monkeypatch)
    result = main.submit_feedback(FeedbackRequest(conversation_id=resp.conversation_id, turn_index=0, rating="up"))
    assert result.rating == "up"
    assert result.comment is None


def test_submit_feedback_route_upserts_on_resubmit(monkeypatch):
    resp = _seed_chat(monkeypatch)
    main.submit_feedback(FeedbackRequest(conversation_id=resp.conversation_id, turn_index=0, rating="up"))
    result = main.submit_feedback(
        FeedbackRequest(conversation_id=resp.conversation_id, turn_index=0, rating="down", comment="Wrong numbers")
    )
    assert result.rating == "down"
    assert result.comment == "Wrong numbers"


def test_submit_feedback_route_with_null_rating_clears_it(monkeypatch):
    resp = _seed_chat(monkeypatch)
    main.submit_feedback(FeedbackRequest(conversation_id=resp.conversation_id, turn_index=0, rating="up"))
    cleared = main.submit_feedback(FeedbackRequest(conversation_id=resp.conversation_id, turn_index=0, rating=None))
    assert cleared is None
    assert main.feedback_store.get(resp.conversation_id, 0) is None


def test_submit_feedback_for_unknown_conversation_404s(monkeypatch):
    with pytest.raises(HTTPException) as excinfo:
        main.submit_feedback(FeedbackRequest(conversation_id="ghost-conversation", turn_index=0, rating="up"))
    assert excinfo.value.status_code == 404


# --- transcript hydration --------------------------------------------------------
def test_get_conversation_includes_feedback_on_the_assistant_message(monkeypatch):
    resp = _seed_chat(monkeypatch)
    main.submit_feedback(FeedbackRequest(conversation_id=resp.conversation_id, turn_index=0, rating="down", comment="Meh"))

    detail = main.get_conversation(resp.conversation_id)
    assert detail.messages[0].role == "user"
    assert detail.messages[0].feedback is None  # never on the user turn
    assert detail.messages[1].role == "assistant"
    assert detail.messages[1].feedback.rating == "down"
    assert detail.messages[1].feedback.comment == "Meh"


def test_get_conversation_with_no_feedback_leaves_it_null(monkeypatch):
    resp = _seed_chat(monkeypatch)
    detail = main.get_conversation(resp.conversation_id)
    assert detail.messages[1].feedback is None


def test_feedback_attaches_to_the_right_turn_across_multiple_turns(monkeypatch):
    resp1 = _seed_chat(monkeypatch, question="How is revenue?")
    monkeypatch.setattr(
        main, "get_response", lambda *a, **k: {"insight_text": "AOV is $85.", "recommended_actions": []}
    )
    resp2 = main.chat(
        ChatRequest(question="What about AOV?", conversation_id=resp1.conversation_id)
    )
    assert resp2.conversation_id == resp1.conversation_id

    main.submit_feedback(FeedbackRequest(conversation_id=resp1.conversation_id, turn_index=1, rating="up"))
    detail = main.get_conversation(resp1.conversation_id)
    # messages: [user0, assistant0, user1, assistant1]
    assert detail.messages[1].feedback is None
    assert detail.messages[3].feedback.rating == "up"


# --- HTTP-level validation (needs real request parsing, not a direct call) ------
@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app)


def test_bad_rating_value_is_rejected_with_422(client, monkeypatch):
    resp = _seed_chat(monkeypatch)
    r = client.post(
        "/api/feedback", json={"conversation_id": resp.conversation_id, "turn_index": 0, "rating": "sideways"}
    )
    assert r.status_code == 422


def test_comment_over_500_chars_is_rejected_with_422(client, monkeypatch):
    resp = _seed_chat(monkeypatch)
    r = client.post(
        "/api/feedback",
        json={"conversation_id": resp.conversation_id, "turn_index": 0, "rating": "down", "comment": "x" * 501},
    )
    assert r.status_code == 422


def test_negative_turn_index_is_rejected_with_422(client, monkeypatch):
    resp = _seed_chat(monkeypatch)
    r = client.post("/api/feedback", json={"conversation_id": resp.conversation_id, "turn_index": -1, "rating": "up"})
    assert r.status_code == 422


def test_valid_submission_via_http_round_trips(client, monkeypatch):
    resp = _seed_chat(monkeypatch)
    r = client.post("/api/feedback", json={"conversation_id": resp.conversation_id, "turn_index": 0, "rating": "up"})
    assert r.status_code == 200
    assert r.json() == {"rating": "up", "comment": None}
