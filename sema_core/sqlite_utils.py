"""
SEMA: one shared sqlite3 connection helper for the app's own metadata stores
(conversations, org users, audit log, semantic drafts, etc. -- all the small
SQLite-backed stores in sema_core/, as distinct from the tenant analytics
databases in db.py).

Every store used to open connections via its own copy-pasted
`sqlite3.connect(self._path, timeout=5)`, in WAL journal mode is a per-file
setting written once into the database header -- it needs to be requested
on connect, and every one of those stores had never requested it, leaving
sqlite3's default rollback-journal mode active. Under concurrent writers
(FastAPI runs sync endpoints in a threadpool, so parallel requests really do
open parallel connections) rollback-journal mode takes a database-wide lock
for the duration of a write, so a slow write can make a completely unrelated
store's write see "database is locked" -- even though every store already
uses short-lived, one-per-call connections. WAL mode lets readers and a
writer proceed concurrently instead (see backend_qa_prompt.md item 4).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(path: Path, timeout: float = 5) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
