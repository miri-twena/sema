"""
SEMA REST API (FastAPI) -- a thin layer over the existing Python backend.

It reuses the Streamlit app's backend modules unchanged (the agent, tools,
safety, semantic layer, db, alerts engine, client registry). Streamlit is NOT
touched and keeps working in parallel; this just exposes the same logic over
REST so a React frontend can consume it.

Run:
    .venv\\Scripts\\python.exe -m uvicorn api.main:app --reload --port 8000
Then open http://localhost:8000/docs (Swagger).
"""

from __future__ import annotations

import sys
from pathlib import Path

# The backend modules import as top-level (from db import ..., import
# client_registry, ...). They live in app/, so put it on the path -- the same
# thing PYTHONPATH=app does for Streamlit.
_APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

import client_registry  # noqa: E402
from agent import agent  # noqa: E402
from components import alerts_engine  # noqa: E402
from db import check_connection, run_query  # noqa: E402
from wiring import get_response  # noqa: E402

from api.models import (  # noqa: E402
    Alert,
    ChatRequest,
    ChatResponse,
    Client,
    ClientChangeRequest,
    Health,
    SchemaResponse,
)
from api.serialize import build_schema, to_chat_response  # noqa: E402

app = FastAPI(title="SEMA API", version="0.1.0")

# CORS for local React dev (Vite default 5173; CRA/other 3000).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_client(client_id: str | None) -> str:
    return client_id or client_registry.DEFAULT_CLIENT_ID


def _client_model(c: dict) -> Client:
    return Client(
        id=c["id"],
        label=c["label"],
        semantic_dir=c.get("semantic_dir", ""),
        suggested_questions=c.get("suggested_questions", []),
    )


@app.get("/api/health", response_model=Health)
def health() -> Health:
    cid = client_registry.DEFAULT_CLIENT_ID
    return Health(
        status="ok",
        db_connected=check_connection(cid),
        agent_configured=agent.api_key_configured(),
        active_client=cid,
    )


@app.get("/api/clients", response_model=list[Client])
def list_clients() -> list[Client]:
    return [_client_model(c) for c in client_registry.load_clients()]


@app.post("/api/client", response_model=Client)
def set_client(req: ClientChangeRequest) -> Client:
    """Validate a client selection and return its config. The API is stateless:
    the frontend holds the active client and sends client_id with each request."""
    for c in client_registry.load_clients():
        if c["id"] == req.client_id:
            return _client_model(c)
    raise HTTPException(status_code=404, detail=f"unknown client: {req.client_id}")


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    cid = _resolve_client(req.client_id)
    # Point the whole agent run (db + semantic) at this request's client.
    client_registry.set_active_client_override(cid)
    try:
        history = [m.model_dump() for m in req.history]
        resp = get_response(req.question, history=history)
        return to_chat_response(resp)
    except Exception as exc:  # never leak a 500 with a stack trace to the UI
        return ChatResponse(answer="", status="error", error=str(exc))
    finally:
        client_registry.set_active_client_override(None)


@app.get("/api/alerts", response_model=list[Alert])
def alerts(client_id: str | None = None) -> list[Alert]:
    cid = _resolve_client(client_id)
    return [Alert(**a) for a in alerts_engine.evaluate_all_alerts(client_id=cid)]


@app.get("/api/schema", response_model=SchemaResponse)
def schema(client_id: str | None = None) -> SchemaResponse:
    cid = _resolve_client(client_id)
    try:
        return build_schema(cid, run_query)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
