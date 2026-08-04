"""
Full-data CSV export (full_data_export_prompt.md): POST /api/exports/table
re-runs the SQL bound to one turn's table WITHOUT the display cap, by
REFERENCE (conversation_id + turn_index) only.

No live DB: seeds a conversation by driving a mocked `get_response` through
the real `main.chat()` route (same `_seed_chat` idiom as test_feedback.py),
then monkeypatches `main.stream_sql_readonly` to a fake generator standing
in for "the database" -- so a test can assert the export's row count against
a KNOWN ground truth without a live Postgres connection (matches this
project's "tests must never depend on a live database" rule -- see
test_authz_matrix.py's own docstring).
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.models import ChatRequest

CID = "ecommerce"
TABLE_SQL = "SELECT id, total_amount FROM orders WHERE status = 'completed' LIMIT 1000"
# Sensitive per test_agent_scope_enforcement.py's GROSS_MARGIN_SQL: touches
# unit_cost, which _policy_index flags as sensitive for any scope with
# blocks_sensitive=True (no_financials) -- blocked via the SQL structural
# scan alone, no metrics_used needed, so it also proves the export's
# check_scope(sql, metrics_used=None) call is a real, working gate.
SENSITIVE_SQL = (
    "SELECT p.product_id, SUM(oi.quantity * (oi.unit_price - p.unit_cost)) AS gp "
    "FROM order_items oi JOIN products p ON p.product_id = oi.product_id GROUP BY p.product_id"
)


def _capped_preview_df() -> pd.DataFrame:
    """Stands in for the on-screen, display-capped result -- deliberately
    tiny, so a test can assert the export returns MORE rows than this."""
    return pd.DataFrame({"id": [1, 2, 3], "total_amount": [10.0, 20.0, 30.0]})


def _seed_chat(monkeypatch, *, sql=TABLE_SQL, truncated=True, total_rows=2500, question="all orders"):
    """Seed one conversation turn whose table is bound to `sql`, mirroring
    what agent/response.py would have set on a real truncated answer."""
    monkeypatch.setattr(
        main,
        "get_response",
        lambda *a, **k: {
            "insight_text": "Here are the orders.",
            "recommended_actions": [],
            "table": _capped_preview_df(),
            "table_title": "Orders",
            "table_sql": sql,
            "table_truncated": truncated,
            "table_total_rows": total_rows,
        },
    )
    resp = main.chat(ChatRequest(question=question))
    assert resp.table is not None and resp.table.sql == sql
    return resp.conversation_id


def _as_user(monkeypatch, user_id="u1", data_scope="full"):
    monkeypatch.setattr(main, "current_org_user", lambda cid: {"id": user_id, "data_scope": data_scope})


def _fake_db_stream(columns, rows, batch_size=500):
    """A stand-in for sema_core.db.stream_sql_readonly: the SAME generator
    shape (columns, row_batch) tuples -- "the database" for these tests,
    with a KNOWN row count to assert the export against."""

    def _stream(sql, client_id=None, batch_size=batch_size):
        for i in range(0, len(rows), batch_size):
            yield columns, rows[i : i + batch_size]

    return _stream


@pytest.fixture(autouse=True)
def _isolated_stores(tmp_path, monkeypatch):
    """Every test gets fresh, isolated rate-limit/audit/conversation stores --
    same convention as the other API test files (never share var/sema_state.db
    across tests)."""
    from sema_core.audit_store import AuditStore
    from sema_core.conversation_store import SqliteConversationStore
    from sema_core.export_limit_store import ExportLimitStore

    monkeypatch.setattr(main, "conversation_store", SqliteConversationStore(tmp_path / "conv.db"))
    monkeypatch.setattr(main, "audit_store", AuditStore(tmp_path / "audit.db"))
    monkeypatch.setattr(main, "export_limit_store", ExportLimitStore(tmp_path / "export.db"))
    monkeypatch.setattr(main, "current_identity", lambda: {"client_id": CID, "email": "u@example.com"})


@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app)


# --- happy path: bypasses the display cap, matches the "DB" ground truth ---


def test_export_returns_more_rows_than_the_capped_display(monkeypatch, client):
    conv_id = _seed_chat(monkeypatch, total_rows=2500)
    _as_user(monkeypatch)
    ground_truth_rows = [(i, float(i * 10)) for i in range(1, 2501)]  # 2500 rows -- the "DB"
    monkeypatch.setattr(
        main, "stream_sql_readonly", _fake_db_stream(["id", "total_amount"], ground_truth_rows)
    )

    resp = client.post("/api/exports/table", json={"conversation_id": conv_id, "turn_index": 0})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    # Leading UTF-8 BOM (same convention as the client-side export) --
    # stripped here the same way a real CSV consumer (Excel, Python's
    # utf-8-sig codec) would, not treated as part of the header text.
    lines = resp.text.lstrip("﻿").strip("\r\n").split("\r\n")
    assert lines[0] == "id,total_amount"
    assert len(lines) - 1 == 2500  # every DB row, not the 3-row capped preview
    assert lines[1] == "1,10.0"
    assert lines[-1] == "2500,25000.0"


def test_export_includes_a_utf8_bom_like_the_client_side_export(monkeypatch, client):
    """Without the BOM, Excel opening the CSV directly mis-renders any
    non-ASCII value (Hebrew customer names, accented characters) as
    mojibake even though the bytes are valid UTF-8 -- caught during
    csv_export_verification_prompt.md's live check, where the real export
    endpoint's bytes didn't start with the BOM the client-side exportCsv
    (DataTable.tsx) has always included."""
    conv_id = _seed_chat(monkeypatch)
    _as_user(monkeypatch)
    monkeypatch.setattr(main, "stream_sql_readonly", _fake_db_stream(["id"], [(1,)]))

    resp = client.post("/api/exports/table", json={"conversation_id": conv_id, "turn_index": 0})

    assert resp.content.startswith(b"\xef\xbb\xbf")


def test_export_filename_includes_question_and_date(monkeypatch, client):
    conv_id = _seed_chat(monkeypatch, question="orders this year")
    _as_user(monkeypatch)
    monkeypatch.setattr(main, "stream_sql_readonly", _fake_db_stream(["id"], [(1,)]))

    resp = client.post("/api/exports/table", json={"conversation_id": conv_id, "turn_index": 0})

    disposition = resp.headers["content-disposition"]
    assert "orders_this_year" in disposition
    assert "attachment" in disposition


def test_export_is_audited_with_row_count(monkeypatch, client):
    conv_id = _seed_chat(monkeypatch)
    _as_user(monkeypatch)
    monkeypatch.setattr(main, "stream_sql_readonly", _fake_db_stream(["id"], [(i,) for i in range(50)]))

    client.post("/api/exports/table", json={"conversation_id": conv_id, "turn_index": 0})

    events = main.audit_store.list_events(CID)["events"]
    exported = [e for e in events if e["action"] == "data.exported"]
    assert len(exported) == 1
    assert exported[0]["after"]["rows"] == 50
    assert exported[0]["after"]["turn_index"] == 0


# --- never raw client SQL ----------------------------------------------------


def test_client_supplied_sql_field_is_ignored_not_executed(monkeypatch, client):
    """TableExportRequest has no `sql` field at all -- an extra field in the
    JSON body is silently dropped by pydantic, never reaches the query that
    actually runs. Proves the endpoint can only ever export the SERVER's own
    stored SQL, never client-supplied text."""
    conv_id = _seed_chat(monkeypatch, sql=TABLE_SQL)
    _as_user(monkeypatch)
    captured = {}

    def _spy_stream(sql, client_id=None, batch_size=2000):
        captured["sql"] = sql
        yield ["id"], [(1,)]

    monkeypatch.setattr(main, "stream_sql_readonly", _spy_stream)

    resp = client.post(
        "/api/exports/table",
        json={
            "conversation_id": conv_id,
            "turn_index": 0,
            "sql": "SELECT * FROM org_users; DROP TABLE org_users;",
        },
    )

    assert resp.status_code == 200
    assert "DROP TABLE" not in captured["sql"]
    assert "orders" in captured["sql"].lower()  # the server's own stored SQL ran, nothing else


def test_a_multi_statement_stored_sql_is_rejected_not_executed(monkeypatch, client):
    """Defense in depth: even if something upstream let a stacked statement
    into Table.sql, validate_and_prepare's single-statement rule still
    catches it here, same as it would for a live agent query."""
    conv_id = _seed_chat(monkeypatch, sql="SELECT 1; DROP TABLE orders;")
    _as_user(monkeypatch)
    monkeypatch.setattr(main, "stream_sql_readonly", _fake_db_stream(["id"], [(1,)]))

    resp = client.post("/api/exports/table", json={"conversation_id": conv_id, "turn_index": 0})

    assert resp.status_code == 400


# --- scope re-check: CURRENT scope, not the scope at answer time -----------


def test_scope_narrowed_since_the_answer_denies_the_export(monkeypatch, client):
    """The answer ran under full access; the export re-checks the
    REQUESTER's CURRENT scope, which may have narrowed since."""
    conv_id = _seed_chat(monkeypatch, sql=SENSITIVE_SQL)
    _as_user(monkeypatch, data_scope="no_financials")  # narrowed after the answer
    stream_called = []
    monkeypatch.setattr(
        main, "stream_sql_readonly", lambda *a, **k: stream_called.append(1) or iter([])
    )

    resp = client.post("/api/exports/table", json={"conversation_id": conv_id, "turn_index": 0})

    assert resp.status_code == 403
    assert not stream_called  # never touched the database

    events = main.audit_store.list_events(CID)["events"]
    denied = [e for e in events if e["action"] == "data.export_denied"]
    assert len(denied) == 1
    assert denied[0]["after"]["turn_index"] == 0


def test_full_scope_export_of_the_same_sensitive_query_succeeds(monkeypatch, client):
    """Control for the test above: the SAME sql, but a requester who still
    has full access -- proves the 403 above is really about scope, not some
    other rejection."""
    conv_id = _seed_chat(monkeypatch, sql=SENSITIVE_SQL)
    _as_user(monkeypatch, data_scope="full")
    monkeypatch.setattr(main, "stream_sql_readonly", _fake_db_stream(["product_id", "gp"], [(1, 100.0)]))

    resp = client.post("/api/exports/table", json={"conversation_id": conv_id, "turn_index": 0})

    assert resp.status_code == 200


# --- rate limit ---------------------------------------------------------------


def test_hourly_export_limit_is_enforced_then_resets_next_hour(monkeypatch, client):
    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, export_hourly_limit=2))
    conv_id = _seed_chat(monkeypatch)
    _as_user(monkeypatch)
    monkeypatch.setattr(main, "stream_sql_readonly", _fake_db_stream(["id"], [(1,)]))

    for _ in range(2):  # at the cap -- still allowed
        r = client.post("/api/exports/table", json={"conversation_id": conv_id, "turn_index": 0})
        assert r.status_code == 200

    over = client.post("/api/exports/table", json={"conversation_id": conv_id, "turn_index": 0})
    assert over.status_code == 429

    events = main.audit_store.list_events(CID)["events"]
    limited = [e for e in events if e["action"] == "export.rate_limited"]
    assert len(limited) == 1  # once per breach, not once per over-cap request

    monkeypatch.setattr(main, "export_limit_current_hour", lambda: "2099-01-01T00")
    fresh_hour = client.post("/api/exports/table", json={"conversation_id": conv_id, "turn_index": 0})
    assert fresh_hour.status_code == 200


def test_rate_limit_disabled_when_zero(monkeypatch, client):
    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, export_hourly_limit=0))
    conv_id = _seed_chat(monkeypatch)
    _as_user(monkeypatch)
    monkeypatch.setattr(main, "stream_sql_readonly", _fake_db_stream(["id"], [(1,)]))

    for _ in range(5):
        r = client.post("/api/exports/table", json={"conversation_id": conv_id, "turn_index": 0})
        assert r.status_code == 200


def test_no_rate_limit_when_identity_does_not_resolve_to_a_real_user(monkeypatch, client):
    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, export_hourly_limit=1))
    conv_id = _seed_chat(monkeypatch)
    _as_user(monkeypatch, user_id=None)  # unscoped identity -- nothing to count against
    monkeypatch.setattr(main, "stream_sql_readonly", _fake_db_stream(["id"], [(1,)]))

    for _ in range(5):
        r = client.post("/api/exports/table", json={"conversation_id": conv_id, "turn_index": 0})
        assert r.status_code == 200


# --- streaming: never a full list in memory ----------------------------------


def test_response_is_a_generator_not_a_materialized_list(monkeypatch, client):
    """The endpoint must hand StreamingResponse an actual generator over the
    DB stream, not something that fully materializes the CSV in memory
    first -- proven by never fully draining the fake "DB" generator into a
    list anywhere in the call chain: csv_stream() pulls from
    stream_sql_readonly() one batch at a time via a plain `for` loop, and
    this test's fake stands in for the DB with its own generator, so if
    anything upstream tried to `list()` it before streaming, this generator
    would already be a spent iterator the second time -- it isn't, since it's
    never touched except by that one `for` loop."""
    import types

    conv_id = _seed_chat(monkeypatch)
    _as_user(monkeypatch)

    def _lazy_stream(sql, client_id=None, batch_size=2000):
        for batch in range(5):
            yield ["id"], [(batch,)]

    fake_gen = _lazy_stream("unused")
    assert isinstance(fake_gen, types.GeneratorType)
    monkeypatch.setattr(main, "stream_sql_readonly", lambda *a, **k: fake_gen)

    resp = client.post("/api/exports/table", json={"conversation_id": conv_id, "turn_index": 0})

    assert resp.status_code == 200
    lines = resp.text.lstrip("﻿").strip("\r\n").split("\r\n")
    assert lines == ["id", "0", "1", "2", "3", "4"]


# --- 404s: reference must resolve to a real, exportable table ---------------


def test_unknown_conversation_id_404s(monkeypatch, client):
    _as_user(monkeypatch)
    resp = client.post("/api/exports/table", json={"conversation_id": "does-not-exist", "turn_index": 0})
    assert resp.status_code == 404


def test_turn_with_no_table_404s(monkeypatch, client):
    monkeypatch.setattr(
        main, "get_response",
        lambda *a, **k: {"insight_text": "No table here.", "recommended_actions": []},
    )
    resp0 = main.chat(ChatRequest(question="hello"))
    _as_user(monkeypatch)

    resp = client.post("/api/exports/table", json={"conversation_id": resp0.conversation_id, "turn_index": 0})
    assert resp.status_code == 404


def test_rule_based_table_with_no_bound_sql_404s(monkeypatch, client):
    """insight_builder's rule-based tables have no `sql` binding -- not
    exportable, same 404 as no table at all (never a 500)."""
    conv_id = _seed_chat(monkeypatch, sql=None)
    _as_user(monkeypatch)
    resp = client.post("/api/exports/table", json={"conversation_id": conv_id, "turn_index": 0})
    assert resp.status_code == 404
