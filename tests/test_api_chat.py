"""
P0 items 2 & 3 at the API boundary:
  - unknown client_id -> HTTP 404 (never a cross-tenant fallback);
  - an agent/backend exception -> generic message + request_id, with NO
    internal details (paths, SQL, driver errors) leaked to the client.

The chat route is called directly with a monkeypatched get_response, so no
live DB, LLM, or API key is needed.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import api.main as main
from api.models import ChatRequest


def test_unknown_client_returns_404(monkeypatch):
    with pytest.raises(HTTPException) as excinfo:
        main.chat(ChatRequest(question="hi", client_id="ghost-tenant"))
    assert excinfo.value.status_code == 404


def test_backend_exception_does_not_leak_internals(monkeypatch):
    secret = r"psycopg2 error at C:\secret\path.py; DROP TABLE orders"

    def boom(*args, **kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(main, "get_response", boom)

    resp = main.chat(ChatRequest(question="hi"))  # default client

    assert resp.status == "error"
    assert resp.answer == ""
    # The raw exception text must not reach the client...
    assert secret not in (resp.error or "")
    assert "DROP TABLE" not in (resp.error or "")
    assert "path.py" not in (resp.error or "")
    # ...but a correlation reference must, so support can find the log line.
    assert "Reference:" in (resp.error or "")


def test_successful_chat_passes_through(monkeypatch):
    monkeypatch.setattr(
        main,
        "get_response",
        lambda *a, **k: {"insight_text": "All good", "recommended_actions": []},
    )
    resp = main.chat(ChatRequest(question="hi"))
    assert resp.status == "ok"
    assert resp.answer == "All good"


# --- contract validation (item 9) -------------------------------------------
def test_oversized_history_rejected():
    with pytest.raises(Exception):  # pydantic ValidationError -> FastAPI 422
        ChatRequest(
            question="hi",
            history=[{"role": "user", "content": "x"}] * 21,  # cap is 20
        )


def test_bad_role_rejected():
    with pytest.raises(Exception):
        ChatRequest(question="hi", history=[{"role": "system", "content": "x"}])


# --- auth scaffold (item 12) -------------------------------------------------
def test_api_key_dependency(monkeypatch):
    import dataclasses

    from fastapi.testclient import TestClient

    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, api_key="sekret"))
    client = TestClient(main.app)

    assert client.get("/api/clients").status_code == 401  # no header
    assert client.get("/api/clients", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/api/clients", headers={"X-API-Key": "sekret"}).status_code == 200


def test_auth_disabled_when_no_key_configured(monkeypatch):
    import dataclasses

    from fastapi.testclient import TestClient

    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, api_key=""))
    client = TestClient(main.app)
    assert client.get("/api/clients").status_code == 200


# --- popular questions --------------------------------------------------------
def test_popular_questions_endpoint(monkeypatch):
    monkeypatch.setattr(
        main, "get_response", lambda *a, **k: {"insight_text": "ok", "recommended_actions": []}
    )
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    client.post("/api/chat", json={"question": "Show revenue trend", "client_id": "ecommerce"})
    client.post("/api/chat", json={"question": "Show revenue trend", "client_id": "ecommerce"})

    resp = client.get("/api/popular-questions?client_id=ecommerce")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0] == {"question": "Show revenue trend", "times_asked": 2}


def test_popular_questions_unknown_client_404():
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    assert client.get("/api/popular-questions?client_id=ghost").status_code == 404
