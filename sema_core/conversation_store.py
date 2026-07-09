"""
SEMA: server-side conversation store.

Replaces client-shipped chat history with a conversation_id the server
resolves against its OWN small metadata store (SQLite here) -- entirely
separate from the tenant analytics databases in db.py. Turns are plain
{"role", "content"} dicts, the same shape agent.run()'s `history` argument
already expects, so there's no translation layer between the store and the
agent loop.

SqliteConversationStore is one implementation of the informal ConversationStore
interface below; a Postgres-backed one can replace it later without touching
callers (api/main.py codes against the interface, not sqlite3).
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


class ConversationNotFoundError(Exception):
    """Raised for a missing conversation OR one owned by a different
    client_id. Callers must not be able to tell the two apart -- that would
    leak that a conversation id exists under another tenant."""


class ConversationStore(Protocol):
    def create(self, client_id: str) -> str: ...
    def append(self, conversation_id: str, client_id: str, role: str, content: str) -> None: ...
    def get_turns(self, conversation_id: str, client_id: str) -> list[dict]: ...


class SqliteConversationStore:
    """SQLite-backed ConversationStore.

    A fresh connection is opened per call -- sqlite3 connections aren't safe
    to share across threads, and FastAPI runs sync endpoints in a threadpool.
    Metadata writes here (a couple of short rows per chat turn) are small and
    infrequent enough that the per-call open/close cost is negligible.
    """

    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS conversations ("
                "id TEXT PRIMARY KEY, client_id TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS messages ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, "
                "role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)"
            )

    def _owner(self, conn: sqlite3.Connection, conversation_id: str) -> str | None:
        row = conn.execute(
            "SELECT client_id FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        return row[0] if row else None

    def create(self, client_id: str) -> str:
        conv_id = uuid.uuid4().hex
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO conversations (id, client_id, created_at) VALUES (?, ?, ?)",
                (conv_id, client_id, datetime.now(timezone.utc).isoformat()),
            )
        return conv_id

    def append(self, conversation_id: str, client_id: str, role: str, content: str) -> None:
        with closing(self._connect()) as conn, conn:
            if self._owner(conn, conversation_id) != client_id:
                raise ConversationNotFoundError(conversation_id)
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (conversation_id, role, content, datetime.now(timezone.utc).isoformat()),
            )

    def get_turns(self, conversation_id: str, client_id: str) -> list[dict]:
        with closing(self._connect()) as conn:
            if self._owner(conn, conversation_id) != client_id:
                raise ConversationNotFoundError(conversation_id)
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id ASC",
                (conversation_id,),
            ).fetchall()
        return [{"role": role, "content": content} for role, content in rows]


def truncate_by_tokens(
    turns: list[dict], budget_tokens: int, chars_per_token: float = 4.0
) -> list[dict]:
    """Keep the most recent turns within an approximate token budget.

    Walks from the newest turn backward (~4 chars/token is a rough but
    dependency-free estimate -- good enough for a soft context budget),
    stopping once adding another turn would exceed it. The single most recent
    turn is always kept even if it alone is over budget, so one long
    question/answer never empties the context. Finally drops any leading
    non-"user" turn, since the Claude API requires messages to start on "user".
    """
    budget_chars = budget_tokens * chars_per_token
    kept: list[dict] = []
    used = 0.0
    for turn in reversed(turns):
        cost = len(turn.get("content", ""))
        if kept and used + cost > budget_chars:
            break
        kept.append(turn)
        used += cost
    kept.reverse()
    while kept and kept[0].get("role") != "user":
        kept.pop(0)
    return kept
