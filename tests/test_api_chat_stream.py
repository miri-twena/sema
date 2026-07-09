"""
Step 3: POST /api/chat/stream (SSE).

get_response is monkeypatched to call on_progress a couple of times before
returning -- proving the event sequence (status*, then answer) and that the
final event parses into a valid ChatResponse. No live DB, LLM, or API key.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

import api.main as main
from api.models import ChatResponse


def _events(raw: str) -> list[tuple[str, dict]]:
    """Split raw SSE text into (event_name, parsed_json_data) pairs."""
    out = []
    for frame in raw.split("\n\n"):
        if not frame.strip():
            continue
        lines = frame.splitlines()
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        out.append((event, data))
    return out


def test_stream_emits_status_then_answer(monkeypatch):
    def fake_get_response(question, history=None, request_id=None, on_progress=None):
        on_progress("Consulting the semantic layer")
        on_progress("Running query 1")
        return {"insight_text": "Revenue is up.", "recommended_actions": ["Do X"]}

    monkeypatch.setattr(main, "get_response", fake_get_response)
    client = TestClient(main.app)

    with client.stream("POST", "/api/chat/stream", json={"question": "hi"}) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        raw = "".join(resp.iter_text())

    events = _events(raw)
    kinds = [e for e, _ in events]
    assert kinds == ["status", "status", "answer"]
    assert events[0][1] == {"message": "Consulting the semantic layer"}
    assert events[1][1] == {"message": "Running query 1"}

    # The final event must parse into the same contract /api/chat returns.
    parsed = ChatResponse(**events[2][1])
    assert parsed.answer == "Revenue is up."
    assert parsed.actions == ["Do X"]


def test_stream_emits_error_event_on_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError(r"leaky C:\secret\path.py detail")

    monkeypatch.setattr(main, "get_response", boom)
    client = TestClient(main.app)

    with client.stream("POST", "/api/chat/stream", json={"question": "hi"}) as resp:
        raw = "".join(resp.iter_text())

    events = _events(raw)
    assert events[-1][0] == "error"
    assert "secret" not in events[-1][1]["error"]
    assert "Reference:" in events[-1][1]["error"]
    assert "request_id" in events[-1][1]


def test_stream_unknown_client_returns_404_not_a_stream():
    client = TestClient(main.app)
    resp = client.post("/api/chat/stream", json={"question": "hi", "client_id": "ghost"})
    assert resp.status_code == 404
