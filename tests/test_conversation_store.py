"""
Step 4: SqliteConversationStore CRUD + tenant isolation, and the
token-budget truncation helper. No live DB, LLM, or FastAPI needed.
"""

from __future__ import annotations

import pytest

from sema_core.conversation_store import (
    ConversationNotFoundError,
    SqliteConversationStore,
    truncate_by_tokens,
)


@pytest.fixture
def store(tmp_path):
    return SqliteConversationStore(tmp_path / "conversations.db")


# --- CRUD --------------------------------------------------------------------
def test_create_then_append_then_get_turns(store):
    conv_id = store.create("ecommerce")
    store.append(conv_id, "ecommerce", "user", "How is revenue?")
    store.append(conv_id, "ecommerce", "assistant", "Revenue is up 12%.")

    turns = store.get_turns(conv_id, "ecommerce")
    assert turns == [
        {"role": "user", "content": "How is revenue?"},
        {"role": "assistant", "content": "Revenue is up 12%."},
    ]


def test_unknown_conversation_raises(store):
    with pytest.raises(ConversationNotFoundError):
        store.get_turns("does-not-exist", "ecommerce")
    with pytest.raises(ConversationNotFoundError):
        store.append("does-not-exist", "ecommerce", "user", "x")


# --- tenant isolation ---------------------------------------------------------
def test_wrong_tenant_cannot_read_or_write(store):
    conv_id = store.create("ecommerce")
    store.append(conv_id, "ecommerce", "user", "secret question")

    # A different client_id gets the SAME error as an unknown id -- it must
    # not be able to tell "wrong tenant" apart from "doesn't exist".
    with pytest.raises(ConversationNotFoundError):
        store.get_turns(conv_id, "insurance")
    with pytest.raises(ConversationNotFoundError):
        store.append(conv_id, "insurance", "user", "trying to read client A's chat")

    # The original tenant's data is untouched.
    assert len(store.get_turns(conv_id, "ecommerce")) == 1


# --- popular questions --------------------------------------------------------
def test_top_questions_ranks_by_distinct_conversations(store):
    c1 = store.create("ecommerce")
    store.append(c1, "ecommerce", "user", "Show revenue trend")
    c2 = store.create("ecommerce")
    store.append(c2, "ecommerce", "user", "Show revenue trend")  # same question, 2nd conversation
    c3 = store.create("ecommerce")
    store.append(c3, "ecommerce", "user", "Who are our VIPs?")

    top = store.top_questions("ecommerce")
    assert top[0] == {"question": "Show revenue trend", "times_asked": 2}
    assert top[1] == {"question": "Who are our VIPs?", "times_asked": 1}


def test_top_questions_dedupes_case_and_whitespace(store):
    c1 = store.create("ecommerce")
    store.append(c1, "ecommerce", "user", "  Show revenue trend  ")
    c2 = store.create("ecommerce")
    store.append(c2, "ecommerce", "user", "show revenue trend")

    top = store.top_questions("ecommerce")
    assert len(top) == 1
    assert top[0]["times_asked"] == 2


def test_top_questions_repeated_row_in_one_conversation_counts_once(store):
    # A single conversation re-inserting the same question (the history
    # backfill in api/main.py) must not inflate the count past 1.
    conv_id = store.create("ecommerce")
    store.append(conv_id, "ecommerce", "user", "Show revenue trend")
    store.append(conv_id, "ecommerce", "user", "Show revenue trend")

    top = store.top_questions("ecommerce")
    assert top[0]["times_asked"] == 1


def test_top_questions_scoped_per_tenant(store):
    c1 = store.create("ecommerce")
    store.append(c1, "ecommerce", "user", "Ecommerce-only question")
    c2 = store.create("insurance")
    store.append(c2, "insurance", "user", "Insurance-only question")

    assert [q["question"] for q in store.top_questions("ecommerce")] == ["Ecommerce-only question"]
    assert [q["question"] for q in store.top_questions("insurance")] == ["Insurance-only question"]


def test_top_questions_respects_limit(store):
    conv_id = store.create("ecommerce")
    for i in range(10):
        store.append(conv_id, "ecommerce", "user", f"Question {i}")
        conv_id = store.create("ecommerce")  # each needs its own conversation to count

    assert len(store.top_questions("ecommerce", limit=3)) == 3


def test_top_questions_ignores_blank_and_assistant_rows(store):
    conv_id = store.create("ecommerce")
    store.append(conv_id, "ecommerce", "user", "   ")
    store.append(conv_id, "ecommerce", "assistant", "Real answer")

    assert store.top_questions("ecommerce") == []


# --- token-budget truncation ---------------------------------------------------
def test_truncate_drops_oldest_first():
    turns = [
        {"role": "user", "content": "a" * 100},
        {"role": "assistant", "content": "b" * 100},
        {"role": "user", "content": "c" * 2},
        {"role": "assistant", "content": "d" * 2},
    ]
    # Budget (5 chars at 1 char/token) fits only the last two short turns.
    kept = truncate_by_tokens(turns, budget_tokens=5, chars_per_token=1.0)
    assert kept == turns[2:]


def test_truncate_stays_user_anchored():
    # If truncation would cut mid-pair, the leading assistant turn is dropped
    # too, since Claude requires messages to start on "user".
    turns = [
        {"role": "user", "content": "x" * 5},
        {"role": "assistant", "content": "y" * 5},
        {"role": "assistant", "content": "orphaned"},  # pretend this is now oldest kept
    ]
    kept = truncate_by_tokens(turns[1:], budget_tokens=100, chars_per_token=1.0)
    assert kept == [] or kept[0]["role"] == "user"


def test_truncate_always_keeps_most_recent_turn_even_if_over_budget():
    turns = [{"role": "user", "content": "x" * 1000}]
    kept = truncate_by_tokens(turns, budget_tokens=1, chars_per_token=1.0)
    assert kept == turns


def test_truncate_empty_input():
    assert truncate_by_tokens([], budget_tokens=100) == []
