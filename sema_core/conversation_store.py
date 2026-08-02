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

from sema_core import sqlite_utils

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


class ThreadNotFoundError(Exception):
    """Raised for a missing drill-down thread OR one owned by a different
    client_id -- same indistinguishable-404 rule as ConversationNotFoundError,
    and for the same reason (a bad id must never reveal whether it exists
    under another tenant)."""


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
        return sqlite_utils.connect(self._path)

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
            # Drill-down threads: brand-new tables, so unlike conversations/
            # messages above there is no pre-existing schema to migrate --
            # CREATE TABLE IF NOT EXISTS alone covers a fresh store and an
            # older one equally.
            conn.execute(
                "CREATE TABLE IF NOT EXISTS threads ("
                "id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, client_id TEXT NOT NULL, "
                "turn_index INTEGER NOT NULL, widget_kind TEXT NOT NULL, widget_title TEXT NOT NULL, "
                "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            # Enforces "one thread per anchor" at the data layer, not just in
            # application logic -- two concurrent first-turns on the same
            # widget would otherwise both pass the "does it exist yet" check
            # and race to create duplicate threads.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_threads_anchor ON threads("
                "conversation_id, turn_index, widget_kind, widget_title)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_threads_conversation ON threads(conversation_id)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS thread_messages ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT NOT NULL, "
                "role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_thread_messages_thread ON thread_messages(thread_id)"
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

        if "deleted_at" not in conv_cols:
            # Retention-policy soft-delete (org_settings.retention_policy,
            # see sema_core.retention) -- distinct from the hard delete()
            # below (an explicit user action) and from `archived` (a
            # reversible visibility flag, not a lifecycle state). NULL means
            # "alive"; every visibility-facing read (list_conversations)
            # excludes a set row, same as a hard delete would look to the
            # user, but the data itself survives for audit/debugging.
            conn.execute("ALTER TABLE conversations ADD COLUMN deleted_at TEXT")

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
            "  (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count, "
            # Total drill-down follow-up questions asked across EVERY thread
            # anchored to this conversation (sidebar_improvements_prompt.md
            # item 3) -- one aggregated subquery, same shape as message_count
            # above, so listing conversations stays a single query with no
            # N+1 per-thread lookup.
            "  (SELECT COUNT(*) FROM thread_messages tm "
            "   JOIN threads t ON t.id = tm.thread_id "
            "   WHERE t.conversation_id = c.id AND tm.role = 'user') AS drill_count "
            "FROM conversations c "
            "WHERE c.client_id = ? AND c.deleted_at IS NULL "
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
                "drill_count": r[7],
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
        """Deletes the conversation AND every drill-down thread anchored to
        it. This is the ONLY thing that removes a thread -- set_archived()
        deliberately does not touch them (archiving is a reversible visibility
        flag elsewhere in this store, and unarchiving a conversation with its
        threads silently gone would be a surprising, irreversible side effect
        of what looks like a reversible action). Threads have no independent
        lifecycle beyond that: no separate archive/pin of their own, nothing
        that outlives a hard delete of the parent."""
        with closing(self._connect()) as conn, conn:
            if self._owner(conn, conversation_id) != client_id:
                raise ConversationNotFoundError(conversation_id)
            conn.execute(
                "DELETE FROM thread_messages WHERE thread_id IN "
                "(SELECT id FROM threads WHERE conversation_id = ?)",
                (conversation_id,),
            )
            conn.execute("DELETE FROM threads WHERE conversation_id = ?", (conversation_id,))
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    # --- retention-policy soft-delete (sema_core.retention) -----------------

    def count_active_older_than(self, client_id: str, cutoff_iso: str) -> int:
        """How many not-yet-deleted conversations were CREATED before
        `cutoff_iso` -- the retention screen's preview count ("N conversations
        will be deleted on next run"). Read-only; never mutates."""
        with closing(self._connect()) as conn:
            (n,) = conn.execute(
                "SELECT COUNT(*) FROM conversations "
                "WHERE client_id = ? AND deleted_at IS NULL AND created_at < ?",
                (client_id, cutoff_iso),
            ).fetchone()
        return n

    def soft_delete_older_than(self, client_id: str, cutoff_iso: str) -> int:
        """The retention sweep's actual mutation: stamp `deleted_at` on every
        not-yet-deleted conversation created before `cutoff_iso`. Returns the
        count affected. Once set, list_conversations excludes the row (same
        as a hard delete looks to the user), but nothing is actually erased."""
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "UPDATE conversations SET deleted_at = ? "
                "WHERE client_id = ? AND deleted_at IS NULL AND created_at < ?",
                (now, client_id, cutoff_iso),
            )
            return cur.rowcount

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


    # --- drill-down threads (widget-anchored, never in the sidebar) --------

    def get_or_create_thread(
        self,
        conversation_id: str,
        client_id: str,
        turn_index: int,
        widget_kind: str,
        widget_title: str,
    ) -> str:
        """One thread per (conversation, turn, widget) anchor: reopening the
        same widget resumes the same thread instead of starting a new one.

        Raises ConversationNotFoundError if the PARENT conversation is unknown
        or owned by a different client -- the same 404 the main chat's own
        conversation_id gets, so a thread can never be anchored to (or read
        from) a conversation this client_id doesn't own.
        """
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn, conn:
            if self._owner(conn, conversation_id) != client_id:
                raise ConversationNotFoundError(conversation_id)
            row = conn.execute(
                "SELECT id FROM threads WHERE conversation_id = ? AND turn_index = ? "
                "AND widget_kind = ? AND widget_title = ?",
                (conversation_id, turn_index, widget_kind, widget_title),
            ).fetchone()
            if row:
                return row[0]
            thread_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO threads (id, conversation_id, client_id, turn_index, widget_kind, "
                "widget_title, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (thread_id, conversation_id, client_id, turn_index, widget_kind, widget_title, now, now),
            )
            return thread_id

    def _thread_owner(self, conn: sqlite3.Connection, thread_id: str) -> str | None:
        row = conn.execute("SELECT client_id FROM threads WHERE id = ?", (thread_id,)).fetchone()
        return row[0] if row else None

    def append_thread_message(
        self,
        thread_id: str,
        client_id: str,
        role: str,
        content: str,
        payload: str | None = None,
    ) -> None:
        """Record one turn in a thread. Same payload convention as append():
        the rendered answer as JSON on assistant turns, so reopening a widget's
        drill-down restores its KPI cards/charts too, not just plain text."""
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn, conn:
            if self._thread_owner(conn, thread_id) != client_id:
                raise ThreadNotFoundError(thread_id)
            conn.execute(
                "INSERT INTO thread_messages (thread_id, role, content, created_at, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (thread_id, role, content, now, payload),
            )
            conn.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now, thread_id))

    def get_thread_turns(self, thread_id: str, client_id: str) -> list[dict]:
        """The agent's view: {role, content} only -- same shape get_turns
        returns for the main chat. A thread's history is its OWN turns, not
        the parent conversation's -- it is a focused side-conversation about
        one widget, not a continuation of the whole transcript."""
        with closing(self._connect()) as conn:
            if self._thread_owner(conn, thread_id) != client_id:
                raise ThreadNotFoundError(thread_id)
            rows = conn.execute(
                "SELECT role, content FROM thread_messages WHERE thread_id = ? ORDER BY id ASC",
                (thread_id,),
            ).fetchall()
        return [{"role": role, "content": content} for role, content in rows]

    def get_thread_messages(self, thread_id: str, client_id: str) -> list[dict]:
        """The UI's view: adds each assistant turn's rendered payload, mirror
        of get_messages()."""
        with closing(self._connect()) as conn:
            if self._thread_owner(conn, thread_id) != client_id:
                raise ThreadNotFoundError(thread_id)
            rows = conn.execute(
                "SELECT role, content, payload FROM thread_messages "
                "WHERE thread_id = ? ORDER BY id ASC",
                (thread_id,),
            ).fetchall()
        return [{"role": r, "content": c, "payload": p} for r, c, p in rows]

    def get_thread_meta(self, conversation_id: str, client_id: str, thread_id: str) -> dict | None:
        """Anchor metadata for one thread, scoped to its claimed parent
        conversation AND client_id. None (not an exception) for a thread that
        doesn't exist, belongs to a different conversation, or a different
        tenant -- all three are indistinguishable to the caller, which 404s
        uniformly on None, same policy as everywhere else in this store."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT id, conversation_id, client_id, turn_index, widget_kind, widget_title, updated_at "
                "FROM threads WHERE id = ?",
                (thread_id,),
            ).fetchone()
        if row is None or row[1] != conversation_id or row[2] != client_id:
            return None
        return {
            "id": row[0],
            "conversation_id": row[1],
            "turn_index": row[3],
            "widget_kind": row[4],
            "widget_title": row[5],
            "updated_at": row[6],
        }

    def list_threads(self, conversation_id: str, client_id: str) -> list[dict]:
        """Thread summaries for one conversation's widgets: anchor + how many
        follow-up questions were asked, so the client can badge them. Scoped by
        BOTH conversation_id and client_id -- belt-and-braces alongside the
        caller's own conversation-ownership check."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT t.id, t.turn_index, t.widget_kind, t.widget_title, t.updated_at, "
                "  (SELECT COUNT(*) FROM thread_messages m "
                "   WHERE m.thread_id = t.id AND m.role = 'user') AS turn_count "
                "FROM threads t WHERE t.conversation_id = ? AND t.client_id = ? "
                "ORDER BY t.updated_at DESC",
                (conversation_id, client_id),
            ).fetchall()
        return [
            {
                "id": r[0],
                "turn_index": r[1],
                "widget_kind": r[2],
                "widget_title": r[3],
                "updated_at": r[4],
                "turn_count": r[5],
            }
            for r in rows
        ]


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
