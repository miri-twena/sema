"""
Shared pytest setup for the SEMA backend tests.

`sema_core` and `api` resolve via the editable install (pip install -e .,
see pyproject.toml) -- no path manipulation needed. Tests require neither a
live database, an API key, nor Streamlit.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Redirect the conversation store BEFORE anything imports sema_core.settings
# (a module-level singleton, read once at import time) -- otherwise importing
# api.main during test collection would eagerly create the real
# var/sema_state.db as a side effect, before any fixture gets a chance to
# monkeypatch it away. pytest loads conftest.py before collecting test
# modules, so this always wins the race.
os.environ.setdefault(
    "SEMA_CONVERSATION_DB", str(Path(tempfile.mkdtemp(prefix="sema_test_")) / "conversations.db")
)

import pytest


@pytest.fixture(autouse=True)
def _isolated_conversation_store(tmp_path, monkeypatch):
    """Every test gets its own throwaway SQLite conversation store, so tests
    never read or write the app's real var/sema_state.db."""
    import api.main as main
    from sema_core.conversation_store import SqliteConversationStore

    monkeypatch.setattr(
        main, "conversation_store", SqliteConversationStore(tmp_path / "test_conversations.db")
    )
