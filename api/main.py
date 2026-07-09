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

import secrets
import time

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# The backend modules (db, wiring, client_registry, ...) resolve via the
# editable install (pip install -e ., see pyproject.toml) -- no sys.path hack.
import client_registry
from agent import agent
from components import alerts_engine
from db import check_connection, run_query
from obs import get_logger, log_event, new_request_id
from settings import settings
from wiring import get_response

from api.models import (
    Alert,
    ChatRequest,
    ChatResponse,
    Client,
    ClientChangeRequest,
    Health,
    SchemaResponse,
)
from api.serialize import build_schema, to_chat_response

logger = get_logger("api")


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Auth scaffold: every route requires X-API-Key matching SEMA_API_KEY.

    Empty SEMA_API_KEY = auth disabled (local dev). Structured as a FastAPI
    dependency so swapping in real auth (JWT, per-tenant keys) later means
    replacing this one function. compare_digest avoids timing side-channels.
    """
    if not settings.api_key:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="invalid or missing API key")


app = FastAPI(
    title="SEMA API",
    version="0.1.0",
    dependencies=[Depends(require_api_key)],  # applied to ALL routes
)

# CORS for local React dev (origins configurable via SEMA_CORS_ORIGINS).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_client(client_id: str | None) -> str:
    """Resolve to a KNOWN client id or raise 404 -- never fall back to another
    tenant. Called at the top of every client-scoped endpoint."""
    cid = client_id or client_registry.DEFAULT_CLIENT_ID
    try:
        client_registry.get_client_by_id(cid)
    except client_registry.ClientConfigError:
        raise HTTPException(status_code=404, detail=f"unknown client: {cid}") from None
    return cid


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
    request_id = new_request_id()
    cid = _resolve_client(req.client_id)  # 404 before we touch any tenant's DB
    # Point the whole agent run (db + semantic) at this request's client.
    client_registry.set_active_client_override(cid)
    started = time.perf_counter()
    try:
        history = [m.model_dump() for m in req.history]
        resp = get_response(req.question, history=history, request_id=request_id)
        out = to_chat_response(resp)
        log_event(
            logger,
            "api_chat",
            request_id=request_id,
            client_id=cid,
            question_len=len(req.question),
            history_len=len(req.history),
            duration_ms=round((time.perf_counter() - started) * 1000),
            status=out.status,
        )
        return out
    except Exception:
        # Log the full traceback server-side; return only a generic message and
        # the request_id so internal details (paths, SQL, driver errors) can't
        # leak to the client but support can still find the log line.
        logger.exception(
            "api_chat failed (request_id=%s, client_id=%s)", request_id, cid
        )
        return ChatResponse(
            answer="",
            status="error",
            error=(
                "Something went wrong while answering your question. "
                f"Please try again. Reference: {request_id}"
            ),
        )
    finally:
        client_registry.set_active_client_override(None)


@app.get("/api/alerts", response_model=list[Alert])
def alerts(client_id: str | None = None) -> list[Alert]:
    cid = _resolve_client(client_id)
    return [Alert(**a) for a in alerts_engine.evaluate_all_alerts(client_id=cid)]


@app.get("/api/schema", response_model=SchemaResponse)
def schema(client_id: str | None = None) -> SchemaResponse:
    cid = _resolve_client(client_id)
    request_id = new_request_id()
    try:
        return build_schema(cid, run_query)
    except Exception:
        logger.exception(
            "api_schema failed (request_id=%s, client_id=%s)", request_id, cid
        )
        raise HTTPException(
            status_code=500,
            detail=f"Could not load the schema. Reference: {request_id}",
        ) from None
