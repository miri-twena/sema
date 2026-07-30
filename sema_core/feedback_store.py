"""
SEMA: per-answer thumbs up/down feedback (answer_feedback_prompt.md).

One row per (conversation_id, turn_index) in the same small SQLite metadata
store as the other admin-panel stores (var/sema_state.db) -- resubmitting a
rating (switching up<->down, or adding/editing a comment) upserts the SAME
row via ON CONFLICT, mirroring sema_core.semantic_store.save_draft's
composite-key upsert. Clearing a rating (clicking the same thumb again)
deletes the row outright rather than storing rating=NULL, so "no feedback"
and "feedback was explicitly cleared" aren't distinguishable states worth
keeping -- there is nothing else on the row worth retaining once the rating
is gone.

Drill/thread turns are out of scope (answer_feedback_prompt.md item 5): this
store only ever gets called with a real conversation_id + turn_index, never
a thread id.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

VALID_RATINGS = frozenset({"up", "down"})


class InvalidRatingError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TurnFeedbackStore:
    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS turn_feedback ("
                "id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, client_id TEXT NOT NULL, "
                "turn_index INTEGER NOT NULL, rating TEXT NOT NULL, comment TEXT, "
                "user_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
                "UNIQUE(conversation_id, turn_index))"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_turn_feedback_conversation ON turn_feedback(conversation_id)"
            )

    @staticmethod
    def _row_to_dict(r: tuple) -> dict:
        return {
            "id": r[0],
            "conversation_id": r[1],
            "client_id": r[2],
            "turn_index": r[3],
            "rating": r[4],
            "comment": r[5],
            "user_id": r[6],
            "created_at": r[7],
            "updated_at": r[8],
        }

    _COLS = "id, conversation_id, client_id, turn_index, rating, comment, user_id, created_at, updated_at"

    def set(
        self,
        conversation_id: str,
        client_id: str,
        turn_index: int,
        rating: str,
        comment: str | None,
        user_id: str | None,
    ) -> dict:
        if rating not in VALID_RATINGS:
            raise InvalidRatingError(f"invalid rating: {rating!r}")
        now = _now()
        row_id = uuid.uuid4().hex
        with closing(self._connect()) as conn, conn:
            conn.execute(
                f"INSERT INTO turn_feedback ({self._COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(conversation_id, turn_index) DO UPDATE SET "
                "rating = excluded.rating, comment = excluded.comment, "
                "user_id = excluded.user_id, updated_at = excluded.updated_at",
                (row_id, conversation_id, client_id, turn_index, rating, comment, user_id, now, now),
            )
        return self.get(conversation_id, turn_index)

    def clear(self, conversation_id: str, turn_index: int) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "DELETE FROM turn_feedback WHERE conversation_id = ? AND turn_index = ?",
                (conversation_id, turn_index),
            )

    def get(self, conversation_id: str, turn_index: int) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._COLS} FROM turn_feedback WHERE conversation_id = ? AND turn_index = ?",
                (conversation_id, turn_index),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_for_conversation(self, conversation_id: str) -> dict[int, dict]:
        """turn_index -> feedback row, for hydrating a whole transcript at once."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {self._COLS} FROM turn_feedback WHERE conversation_id = ?", (conversation_id,)
            ).fetchall()
        return {r["turn_index"]: r for r in (self._row_to_dict(row) for row in rows)}
