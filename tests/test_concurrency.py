"""
Concurrency + SQLite contention (backend_qa_prompt.md item 4).

Three things under test: (1) a burst of parallel /api/chat requests (mocked
LLM, real stores) all complete with no cross-request data bleed, (2) parallel
writes across the app's own SQLite-backed metadata stores (which in
production all share ONE file, settings.conversation_db_path -- conftest.py
isolates each into its own tmp file per test for OTHER tests' sake, but that
isolation would hide the exact contention this section exists to catch, so
this file deliberately points several stores at the SAME shared tmp file,
matching production) never raise "database is locked" now that WAL mode is
on (sema_core/sqlite_utils.py), and (3) the real finding this section
surfaced: a burst of concurrent requests for the SAME cached report no longer
each independently hit Postgres (sema_core/cache.py's single-flight fix) --
see test_cache.py for the primitive itself; the test here proves it on the
actual app function (queries.get_data_bounds) that was implicated.
"""

from __future__ import annotations

import sqlite3
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import api.main as main
from sema_core import queries
from sema_core import sqlite_utils
from sema_core.audit_store import AuditStore
from sema_core.feedback_store import TurnFeedbackStore
from sema_core.semantic_store import SemanticStore

CID = "ecommerce"
N = 20  # matches the prompt's own "15-20 parallel" ask


def test_wal_mode_is_actually_enabled(tmp_path):
    conn = sqlite_utils.connect(tmp_path / "wal_check.db")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode.lower() == "wal"


# --- 1. parallel /api/chat requests -------------------------------------------


def test_parallel_chat_requests_all_complete_with_no_cross_talk(monkeypatch):
    """N concurrent requests, each a BRAND NEW conversation with a unique
    marker in its question. Every response must echo its OWN marker (proves
    no request's answer/history bled into another's) and every conversation
    must be independently retrievable afterward.

    build_daily_brief is mocked -- /api/chat's own [SEMA-CONTEXT] builder
    (_pulse_context) calls it on EVERY request, and it hits a real, small
    (SEMA_DB_POOL_MAX=5 by default) Postgres connection pool. Leaving it live
    under N=20 concurrent requests genuinely exhausts that pool (confirmed:
    `psycopg2.pool.PoolError: connection pool exhausted`, individual requests
    stalling 10-45s waiting for a slot) -- a REAL, separate finding recorded
    in docs/qa_findings.md, but a Postgres-pool-sizing concern, not the
    SQLite/WAL contention this section is about. Mocking it here isolates
    the claim this test actually makes."""
    monkeypatch.setattr(main, "build_daily_brief", lambda sensitivity="balanced": {
        "as_of": "2026-06-30", "pulse": [], "insights": [],
    })

    def fake_get_response(question, history=None, request_id=None, on_progress=None, **kw):
        # Simulate a little real work so requests genuinely overlap in time
        # rather than trivially interleaving on the GIL.
        time.sleep(0.01)
        return {"insight_text": f"Answer for: {question}", "recommended_actions": []}

    monkeypatch.setattr(main, "get_response", fake_get_response)
    client = TestClient(main.app)

    def _ask(i: int):
        started = time.perf_counter()
        resp = client.post("/api/chat", json={"question": f"marker-{i}"})
        return i, resp, time.perf_counter() - started

    with ThreadPoolExecutor(max_workers=N) as pool:
        results = list(pool.map(_ask, range(N)))

    durations = []
    conv_ids = set()
    for i, resp, duration in results:
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "ok"
        assert body["answer"] == f"Answer for: marker-{i}"  # this request's OWN marker, not another's
        conv_ids.add(body["conversation_id"])
        durations.append(duration)

    assert len(conv_ids) == N  # each request minted its own conversation, none collided/merged

    # No cross-request bleed on the READ side either -- each conversation's
    # stored transcript contains exactly its own question and nothing else.
    for i, resp, _ in results:
        conv_id = resp.json()["conversation_id"]
        messages = main.conversation_store.get_messages(conv_id, client_id=CID)
        assert len(messages) == 2
        assert messages[0]["content"] == f"marker-{i}"

    durations.sort()
    p50 = durations[len(durations) // 2]
    p95 = durations[int(len(durations) * 0.95) - 1]
    # Logged for docs/qa_findings.md's "measure and record simple numbers"
    # ask -- run with `pytest -s` to see it.
    print(f"[concurrency] {N} parallel /api/chat requests: p50={p50*1000:.1f}ms p95={p95*1000:.1f}ms")
    # Not a strict perf assertion (this environment's hardware varies) -- just
    # a sanity ceiling that a lock-contention regression would blow through.
    assert p95 < 5.0, f"p50={p50:.3f}s p95={p95:.3f}s -- looks like lock contention, not concurrency"


# --- 2. parallel writes across stores sharing ONE file (production shape) ----


def test_parallel_writes_across_stores_sharing_one_file_never_lock(tmp_path):
    shared_path = tmp_path / "shared_state.db"
    audit = AuditStore(shared_path)
    feedback = TurnFeedbackStore(shared_path)
    semantic = SemanticStore(shared_path)

    errors: list[Exception] = []

    def _write_audit(i: int):
        try:
            audit.record(
                CID, actor_id="u1", actor_name="Miri", actor_role="client_admin",
                action="org_settings.updated", target_id=str(i),
            )
        except Exception as e:  # pragma: no cover -- only populated on a real failure
            errors.append(e)

    def _write_feedback(i: int):
        try:
            feedback.set(f"conv-{i}", CID, turn_index=0, rating="up", comment=None, user_id=None)
        except Exception as e:
            errors.append(e)

    def _write_draft(i: int):
        try:
            semantic.save_draft(CID, "metric", f"metric_{i}", {"sql": "select 1"})
        except Exception as e:
            errors.append(e)

    jobs = []
    for i in range(N):
        jobs.extend([lambda i=i: _write_audit(i), lambda i=i: _write_feedback(i), lambda i=i: _write_draft(i)])

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        list(pool.map(lambda fn: fn(), jobs))
    elapsed = time.perf_counter() - started
    print(f"[concurrency] {len(jobs)} parallel writes across 3 stores sharing one file: {elapsed*1000:.1f}ms total")

    assert not errors, f"{len(errors)} write(s) failed under concurrency: {errors[:3]}"

    assert audit.list_events(CID, page_size=N + 5)["total"] == N
    assert len(semantic.list_drafts(CID)) == N
    for i in range(N):
        assert feedback.get(f"conv-{i}", 0) is not None


def test_parallel_writes_within_one_store_never_lock(tmp_path):
    """Same guarantee, single-store shape: N threads hammering ONE store's
    file at once (e.g. a burst of feedback clicks across many open tabs)."""
    store = TurnFeedbackStore(tmp_path / "feedback_only.db")
    errors: list[Exception] = []

    def _write(i: int):
        try:
            store.set(f"conv-{i}", CID, turn_index=0, rating="up", comment=f"note {i}", user_id=None)
        except Exception as e:
            errors.append(e)

    with ThreadPoolExecutor(max_workers=N) as pool:
        list(pool.map(_write, range(N)))

    assert not errors, f"{len(errors)} write(s) failed under concurrency: {errors[:3]}"
    for i in range(N):
        assert store.get(f"conv-{i}", 0)["comment"] == f"note {i}"


# --- 3. the actual pool-exhaustion root cause: a thundering herd on a cold report cache ---


def test_concurrent_requests_for_the_same_report_hit_postgres_once_not_n_times(monkeypatch):
    """queries.get_data_bounds is exactly the kind of @ttl_cache-wrapped
    report /api/overview, /api/brief, and every chat request's pulse-context
    block all call -- this is the real function implicated in the
    PoolError/10-45s-latency finding this section's own testing surfaced
    (see docs/qa_findings.md #1). Before sema_core/cache.py's single-flight
    fix, N concurrent callers racing a cold cache each ran run_query
    independently -- N simultaneous pooled-connection checkouts for
    identical data. Proves that's fixed: N concurrent callers now cost
    exactly ONE real query."""
    query_calls = 0
    query_lock = threading.Lock()

    def fake_run_query(sql, params=None, client_id=None):
        nonlocal query_calls
        with query_lock:
            query_calls += 1
        time.sleep(0.15)  # long enough that concurrent callers genuinely overlap
        import pandas as pd
        return pd.DataFrame({"max_date": ["2026-06-30"]})

    monkeypatch.setattr(queries, "run_query", fake_run_query)
    queries.get_data_bounds.cache_clear()

    with ThreadPoolExecutor(max_workers=N) as pool:
        results = list(pool.map(lambda _: queries.get_data_bounds(), range(N)))

    assert query_calls == 1, f"expected 1 real query for {N} concurrent callers, got {query_calls}"
    assert len(results) == N
    for df in results:
        assert df["max_date"].iloc[0] == "2026-06-30"  # every caller got the SAME (correct) result
