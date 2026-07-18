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

# A chat's title is the first question asked in it, trimmed to something that
# fits a sidebar row. No LLM call: the first question is already a good label,
# and users can rename.
TITLE_MAX_CHARS = 80


def derive_title(text: str) -> str:
    """First-question -> a concise chat title."""
    collapsed = " ".join((text or "").split())
    if not collapsed:
        return "New chat"
    if len(collapsed) <= TITLE_MAX_CHARS:
        return collapsed
    return collapsed[: TITLE_MAX_CHARS - 1].rstrip() + "…"


class ConversationNotFoundError(Exception):
    """Raised for a missing conversation OR one owned by a different
    client_id. Callers must not be able to tell the two apart -- that would
    leak that a conversation id exists under another tenant."""


class ConversationStore(Protocol):
    def create(self, client_id: str) -> str: ...
    def append(
        self,
        conversation_id: str,
        client_id: str,
        role: str,
        content: str,
        payload: str | None = None,
    ) -> None: ...
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
                "id TEXT PRIMARY KEY, client_id TEXT NOT NULL, created_at TEXT NOT NULL, "
                "updated_at TEXT, title TEXT, "
                "pinned INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS messages ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, "
                "role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL, "
                "payload TEXT)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)"
            )
            self._migrate(conn)

    @staticmethod
    def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Bring an existing database up to the current schema.

        CREATE TABLE IF NOT EXISTS above is a no-op on a database that already
        has the tables, so a store created before conversation management
        existed still has only (id, client_id, created_at). Each ALTER is
        guarded by a column check, so this is idempotent and runs at most once
        per column. There's no migration framework in the project (and this is
        the only stateful app-owned table), so a few guarded ALTERs beat adding
        one for a single table.
        """
        conv_cols = self._columns(conn, "conversations")

        if "updated_at" not in conv_cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN updated_at TEXT")
            # Backfill from the newest message, falling back to creation time.
            conn.execute(
                "UPDATE conversations SET updated_at = COALESCE("
                "  (SELECT MAX(m.created_at) FROM messages m WHERE m.conversation_id = conversations.id),"
                "  created_at)"
            )

        if "title" not in conv_cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN title TEXT")
            # Backfill each chat's title from its first question, the same rule
            # new chats use. Done in SQL (rather than reading every row into
            # Python) since it is a one-shot pass over a small metadata table.
            conn.execute(
                "UPDATE conversations SET title = ("
                "  SELECT SUBSTR(TRIM(m.content), 1, ?) FROM messages m"
                "  WHERE m.conversation_id = conversations.id AND m.role = 'user'"
                "  ORDER BY m.id ASC LIMIT 1)",
                (TITLE_MAX_CHARS,),
            )

        if "pinned" not in conv_cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")

        if "archived" not in conv_cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
            # Everything predating this column is an artifact of the old
            # client behavior: the frontend never sent conversation_id back, so
            # the API minted a FRESH conversation per turn, each re-seeded with
            # the whole running history. Those rows are near-duplicates of a
            # handful of real sessions and would flood the new sidebar.
            # Archiving (not deleting) hides them while keeping them reachable.
            # Runs exactly once -- the column check gates it.
            conn.execute("UPDATE conversations SET archived = 1")

        if "payload" not in self._columns(conn, "messages"):
            # The rendered answer (KPI cards, chart, table, actions) as JSON,
            # so reopening a chat restores it fully instead of degrading to
            # plain text. NULL for user turns and for pre-existing rows.
            conn.execute("ALTER TABLE messages ADD COLUMN payload TEXT")

    def _owner(self, conn: sqlite3.Connection, conversation_id: str) -> str | None:
        row = conn.execute(
            "SELECT client_id FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        return row[0] if row else None

    def create(self, client_id: str) -> str:
        conv_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO conversations (id, client_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (conv_id, client_id, now, now),
            )
        return conv_id

    def append(
        self,
        conversation_id: str,
        client_id: str,
        role: str,
        content: str,
        payload: str | None = None,
    ) -> None:
        """Record one turn. `payload` is the rendered answer as JSON (assistant
        turns only) so the chat can be reopened with its charts intact."""
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn, conn:
            if self._owner(conn, conversation_id) != client_id:
                raise ConversationNotFoundError(conversation_id)
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (conversation_id, role, content, now, payload),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
            )
            if role == "user":
                # First question titles the chat. Later questions leave it
                # alone, and so does a manual rename (title is non-empty).
                conn.execute(
                    "UPDATE conversations SET title = ? WHERE id = ? "
                    "AND (title IS NULL OR title = '')",
                    (derive_title(content), conversation_id),
                )

    def get_turns(self, conversation_id: str, client_id: str) -> list[dict]:
        """The agent's view: {role, content} only, ready for agent.run(history=)."""
        with closing(self._connect()) as conn:
            if self._owner(conn, conversation_id) != client_id:
                raise ConversationNotFoundError(conversation_id)
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id ASC",
                (conversation_id,),
            ).fetchall()
        return [{"role": role, "content": content} for role, content in rows]

    # --- conversation management (the sidebar's API) -----------------------

    def get_messages(self, conversation_id: str, client_id: str) -> list[dict]:
        """The UI's view: adds each assistant turn's rendered `payload`, which
        get_turns deliberately omits (the agent only needs text)."""
        with closing(self._connect()) as conn:
            if self._owner(conn, conversation_id) != client_id:
                raise ConversationNotFoundError(conversation_id)
            rows = conn.execute(
                "SELECT role, content, payload FROM messages "
                "WHERE conversation_id = ? ORDER BY id ASC",
                (conversation_id,),
            ).fetchall()
        return [{"role": r, "content": c, "payload": p} for r, c, p in rows]

    def list_conversations(self, client_id: str, include_archived: bool = False) -> list[dict]:
        """This client's chats, pinned first, then most-recently-updated.

        Conversations with no messages are omitted: the API creates the row on
        the first question, so an empty one only exists if that request failed
        before its turn was recorded -- a ghost, not a chat.
        """
        sql = (
            "SELECT c.id, c.title, c.pinned, c.archived, c.created_at, c.updated_at, "
            "  (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count "
            "FROM conversations c "
            "WHERE c.client_id = ? "
            "  AND EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id) "
        )
        if not include_archived:
            sql += "AND c.archived = 0 "
        sql += "ORDER BY c.pinned DESC, COALESCE(c.updated_at, c.created_at) DESC"
        with closing(self._connect()) as conn:
            rows = conn.execute(sql, (client_id,)).fetchall()
        return [
            {
                "id": r[0],
                "title": r[1] or "New chat",
                "pinned": bool(r[2]),
                "archived": bool(r[3]),
                "created_at": r[4],
                "updated_at": r[5] or r[4],
                "message_count": r[6],
            }
            for r in rows
        ]

    def _update(self, conversation_id: str, client_id: str, column: str, value) -> None:
        """Set one whitelisted column. `column` never comes from user input --
        the callers below pass literals -- so the f-string can't be injected."""
        with closing(self._connect()) as conn, conn:
            if self._owner(conn, conversation_id) != client_id:
                raise ConversationNotFoundError(conversation_id)
            conn.execute(
                f"UPDATE conversations SET {column} = ? WHERE id = ?", (value, conversation_id)
            )

    def rename(self, conversation_id: str, client_id: str, title: str) -> None:
        self._update(conversation_id, client_id, "title", derive_title(title))

    def set_pinned(self, conversation_id: str, client_id: str, pinned: bool) -> None:
        self._update(conversation_id, client_id, "pinned", 1 if pinned else 0)

    def set_archived(self, conversation_id: str, client_id: str, archived: bool) -> None:
        self._update(conversation_id, client_id, "archived", 1 if archived else 0)

    def delete(self, conversation_id: str, client_id: str) -> None:
        with closing(self._connect()) as conn, conn:
            if self._owner(conn, conversation_id) != client_id:
                raise ConversationNotFoundError(conversation_id)
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    def top_questions(self, client_id: str, limit: int = 6) -> list[dict]:
        """Most frequently asked questions for a client, across every
        conversation (there's no login yet, so "popular" can only mean
        server-wide per client, not per-person). Grouped by trimmed/
        lowercased text so trivial casing/whitespace differences still count
        as the same question; the displayed text keeps its original casing.

        Counts DISTINCT conversation_id per question, not raw message rows, so
        one session asking the same thing twice counts once rather than
        inflating it.

        This mattered even more before the frontend tracked conversation_id: a
        caller that omits it gets a FRESH conversation per turn, re-seeded with
        its whole running history (see api/main.py's _resolve_conversation), so
        a single session used to smear its early questions across several
        conversation rows. The React client now returns the id, so each session
        is one row -- but the DISTINCT stays, both for other callers and to cap
        any single chat's contribution at 1.
        """
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT TRIM(m.content) AS question, COUNT(DISTINCT m.conversation_id) AS times_asked
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE m.role = 'user' AND c.client_id = ? AND TRIM(m.content) != ''
                GROUP BY LOWER(TRIM(m.content))
                ORDER BY times_asked DESC, MAX(m.id) DESC
                LIMIT ?
                """,
                (client_id, limit),
            ).fetchall()
        return [{"question": q, "times_asked": n} for q, n in rows]


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
