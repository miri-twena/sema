"""
SqliteConversationStore's drill-down thread methods: one thread per widget
anchor, its own independent history, and cascade delete with the parent
conversation. Mirrors test_conversation_store.py's style; no live DB, LLM, or
FastAPI needed.
"""

from __future__ import annotations

import pytest

from sema_core.conversation_store import (
    ConversationNotFoundError,
    SqliteConversationStore,
    ThreadNotFoundError,
)


@pytest.fixture
def store(tmp_path):
    return SqliteConversationStore(tmp_path / "conversations.db")


@pytest.fixture
def conv(store):
    """A parent conversation with one turn, ready to anchor threads to."""
    conv_id = store.create("ecommerce")
    store.append(conv_id, "ecommerce", "user", "Why did revenue drop in March?")
    store.append(conv_id, "ecommerce", "assistant", "Because Electronics fell.")
    return conv_id


# --- one thread per anchor ----------------------------------------------------
def test_get_or_create_thread_creates_once_then_resumes(store, conv):
    first = store.get_or_create_thread(conv, "ecommerce", 0, "kpi", "Revenue")
    second = store.get_or_create_thread(conv, "ecommerce", 0, "kpi", "Revenue")
    assert first == second


def test_different_anchors_get_different_threads(store, conv):
    revenue = store.get_or_create_thread(conv, "ecommerce", 0, "kpi", "Revenue")
    orders = store.get_or_create_thread(conv, "ecommerce", 0, "kpi", "Orders")
    same_kpi_other_turn = store.get_or_create_thread(conv, "ecommerce", 1, "kpi", "Revenue")
    assert len({revenue, orders, same_kpi_other_turn}) == 3


def test_unknown_parent_conversation_raises(store):
    with pytest.raises(ConversationNotFoundError):
        store.get_or_create_thread("does-not-exist", "ecommerce", 0, "kpi", "Revenue")


def test_wrong_tenant_cannot_anchor_to_another_clients_conversation(store, conv):
    with pytest.raises(ConversationNotFoundError):
        store.get_or_create_thread(conv, "insurance", 0, "kpi", "Revenue")


# --- turns: independent of the parent conversation's history ------------------
def test_thread_has_its_own_turns(store, conv):
    thread_id = store.get_or_create_thread(conv, "ecommerce", 0, "kpi", "Revenue")
    store.append_thread_message(thread_id, "ecommerce", "user", "Why is this KPI down?")
    store.append_thread_message(thread_id, "ecommerce", "assistant", "Electronics drove it.")

    turns = store.get_thread_turns(thread_id, "ecommerce")
    assert turns == [
        {"role": "user", "content": "Why is this KPI down?"},
        {"role": "assistant", "content": "Electronics drove it."},
    ]
    # The thread's history is its OWN -- it does not inherit the parent
    # conversation's turns (a focused side-conversation, not a continuation).
    assert store.get_turns(conv, "ecommerce") != turns


def test_thread_messages_include_rendered_payload(store, conv):
    thread_id = store.get_or_create_thread(conv, "ecommerce", 0, "kpi", "Revenue")
    store.append_thread_message(thread_id, "ecommerce", "user", "why?")
    store.append_thread_message(
        thread_id, "ecommerce", "assistant", "because X", payload='{"answer":"because X"}'
    )

    msgs = store.get_thread_messages(thread_id, "ecommerce")
    assert msgs[0]["payload"] is None
    assert msgs[1]["payload"] == '{"answer":"because X"}'


def test_append_to_unknown_thread_raises(store):
    with pytest.raises(ThreadNotFoundError):
        store.append_thread_message("nope", "ecommerce", "user", "x")
    with pytest.raises(ThreadNotFoundError):
        store.get_thread_turns("nope", "ecommerce")
    with pytest.raises(ThreadNotFoundError):
        store.get_thread_messages("nope", "ecommerce")


def test_wrong_tenant_cannot_read_or_write_a_thread(store, conv):
    thread_id = store.get_or_create_thread(conv, "ecommerce", 0, "kpi", "Revenue")
    with pytest.raises(ThreadNotFoundError):
        store.append_thread_message(thread_id, "insurance", "user", "snooping")
    with pytest.raises(ThreadNotFoundError):
        store.get_thread_turns(thread_id, "insurance")
    with pytest.raises(ThreadNotFoundError):
        store.get_thread_messages(thread_id, "insurance")


# --- listing / metadata (badges) -----------------------------------------------
def test_list_threads_reports_the_anchor_and_turn_count(store, conv):
    thread_id = store.get_or_create_thread(conv, "ecommerce", 0, "kpi", "Revenue")
    store.append_thread_message(thread_id, "ecommerce", "user", "why?")
    store.append_thread_message(thread_id, "ecommerce", "assistant", "because X")
    store.append_thread_message(thread_id, "ecommerce", "user", "and by channel?")
    store.append_thread_message(thread_id, "ecommerce", "assistant", "channel Y drove it")

    (summary,) = store.list_threads(conv, "ecommerce")
    assert summary["id"] == thread_id
    assert summary["turn_index"] == 0
    assert summary["widget_kind"] == "kpi"
    assert summary["widget_title"] == "Revenue"
    assert summary["turn_count"] == 2  # counts user QUESTIONS, not all messages


def test_list_threads_empty_for_a_conversation_with_no_drills(store, conv):
    assert store.list_threads(conv, "ecommerce") == []


def test_list_threads_scoped_per_conversation(store, conv):
    other_conv = store.create("ecommerce")
    store.append(other_conv, "ecommerce", "user", "different chat")
    store.get_or_create_thread(conv, "ecommerce", 0, "kpi", "Revenue")
    store.get_or_create_thread(other_conv, "ecommerce", 0, "kpi", "Orders")

    assert [t["widget_title"] for t in store.list_threads(conv, "ecommerce")] == ["Revenue"]
    assert [t["widget_title"] for t in store.list_threads(other_conv, "ecommerce")] == ["Orders"]


def test_get_thread_meta_scoped_to_its_real_parent_and_tenant(store, conv):
    thread_id = store.get_or_create_thread(conv, "ecommerce", 0, "kpi", "Revenue")

    meta = store.get_thread_meta(conv, "ecommerce", thread_id)
    assert meta["turn_index"] == 0
    assert meta["widget_kind"] == "kpi"
    assert meta["widget_title"] == "Revenue"

    # None (not an exception) for a wrong conversation_id, wrong tenant, or an
    # unknown thread_id -- all three read as "doesn't exist" to the caller.
    other_conv = store.create("ecommerce")
    assert store.get_thread_meta(other_conv, "ecommerce", thread_id) is None
    assert store.get_thread_meta(conv, "insurance", thread_id) is None
    assert store.get_thread_meta(conv, "ecommerce", "nope") is None


# --- threads never appear in the sidebar ---------------------------------------
def test_threads_are_invisible_to_list_conversations(store, conv):
    store.get_or_create_thread(conv, "ecommerce", 0, "kpi", "Revenue")
    ids = [c["id"] for c in store.list_conversations("ecommerce", include_archived=True)]
    assert ids == [conv]  # only the real conversation, never a thread row


# --- archive is non-destructive: only delete() cascades to threads ------------
def test_archiving_the_conversation_preserves_its_threads(store, conv):
    thread_id = store.get_or_create_thread(conv, "ecommerce", 0, "kpi", "Revenue")
    store.append_thread_message(thread_id, "ecommerce", "user", "why?")
    store.append_thread_message(thread_id, "ecommerce", "assistant", "because X")

    store.set_archived(conv, "ecommerce", True)

    # Archiving is a reversible visibility flag everywhere else in this store;
    # cascading a delete from it would make unarchiving silently lose data.
    (summary,) = store.list_threads(conv, "ecommerce")
    assert summary["id"] == thread_id
    assert store.get_thread_turns(thread_id, "ecommerce") == [
        {"role": "user", "content": "why?"},
        {"role": "assistant", "content": "because X"},
    ]

    # Unarchiving must not need to "restore" anything -- it was never touched.
    store.set_archived(conv, "ecommerce", False)
    assert store.get_thread_meta(conv, "ecommerce", thread_id) is not None


# --- cascade delete -------------------------------------------------------------
def test_deleting_the_conversation_deletes_its_threads(store, conv):
    thread_id = store.get_or_create_thread(conv, "ecommerce", 0, "kpi", "Revenue")
    store.append_thread_message(thread_id, "ecommerce", "user", "why?")

    store.delete(conv, "ecommerce")

    assert store.list_threads(conv, "ecommerce") == []
    with pytest.raises(ThreadNotFoundError):
        store.get_thread_turns(thread_id, "ecommerce")
    assert store.get_thread_meta(conv, "ecommerce", thread_id) is None


def test_deleting_one_conversation_does_not_touch_another_conversations_threads(store, conv):
    other_conv = store.create("ecommerce")
    store.append(other_conv, "ecommerce", "user", "unrelated chat")
    other_thread = store.get_or_create_thread(other_conv, "ecommerce", 0, "kpi", "Orders")

    store.delete(conv, "ecommerce")

    assert store.get_thread_meta(other_conv, "ecommerce", other_thread) is not None


def test_wrong_tenant_delete_cannot_cascade_into_another_clients_threads(store, conv):
    """delete() checks ownership BEFORE issuing any DELETE -- a rejected
    cross-tenant call must leave the real owner's thread completely intact,
    not partially cascade before raising."""
    thread_id = store.get_or_create_thread(conv, "ecommerce", 0, "kpi", "Revenue")
    store.append_thread_message(thread_id, "ecommerce", "user", "why?")

    with pytest.raises(ConversationNotFoundError):
        store.delete(conv, "insurance")

    assert store.get_thread_meta(conv, "ecommerce", thread_id) is not None
    assert store.get_thread_turns(thread_id, "ecommerce") == [
        {"role": "user", "content": "why?"},
    ]
