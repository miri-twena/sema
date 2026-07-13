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

import json
import queue
import secrets
import threading
import time

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# The backend modules (db, wiring, client_registry, ...) resolve via the
# editable install (pip install -e ., see pyproject.toml) -- no sys.path hack.
from sema_core import client_registry
from sema_core.agent import agent
from sema_core import alerts_engine
from sema_core.conversation_store import ConversationNotFoundError, SqliteConversationStore, truncate_by_tokens
from sema_core.db import check_connection, run_query
from sema_core.obs import get_logger, log_event, new_request_id
from sema_core.settings import settings
from sema_core.wiring import get_response

from api.models import (
    Alert,
    ChatRequest,
    ChatResponse,
    Client,
    ClientChangeRequest,
    Health,
    PopularQuestion,
    SchemaResponse,
)
from api.serialize import build_schema, to_chat_response

logger = get_logger("api")

# The app's own conversation metadata store (SQLite) -- separate from the
# tenant analytics databases in db.py. Module-level singleton; tests
# monkeypatch this attribute with an isolated store pointed at a temp file.
conversation_store = SqliteConversationStore(settings.conversation_db_path)


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


def _resolve_conversation(cid: str, req: ChatRequest) -> tuple[str, list[dict]]:
    """Resolve the conversation for this request and return (conversation_id,
    token-budgeted history to send the agent).

    conversation_id wins over client-sent history when both are present. With
    no conversation_id, a new conversation is created now (seeded from any
    legacy `history` the client sent) so every response -- not just resumed
    ones -- carries an id the client can reuse on the next turn.

    Raises HTTPException(404) if conversation_id is unknown OR belongs to a
    different client_id -- indistinguishable on purpose, so a bad id can't be
    used to probe whether it exists under another tenant.
    """
    if req.conversation_id:
        try:
            history = conversation_store.get_turns(req.conversation_id, client_id=cid)
        except ConversationNotFoundError:
            raise HTTPException(status_code=404, detail="unknown conversation_id") from None
        conv_id = req.conversation_id
    else:
        conv_id = conversation_store.create(cid)
        history = [m.model_dump() for m in req.history]
        for m in req.history:
            conversation_store.append(conv_id, cid, m.role, m.content)

    return conv_id, truncate_by_tokens(history, settings.history_token_budget)


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
    conv_id, history = _resolve_conversation(cid, req)  # 404 on a bad conversation_id
    # Point the whole agent run (db + semantic) at this request's client.
    client_registry.set_active_client_override(cid)
    started = time.perf_counter()
    try:
        resp = get_response(req.question, history=history, request_id=request_id)
        out = to_chat_response(resp)
        out.conversation_id = conv_id
        # Persist this turn only on success -- a failed run leaves the
        # conversation as it was, rather than recording a broken exchange.
        conversation_store.append(conv_id, cid, "user", req.question)
        conversation_store.append(conv_id, cid, "assistant", resp.get("insight_text", ""))
        log_event(
            logger,
            "api_chat",
            request_id=request_id,
            client_id=cid,
            question_len=len(req.question),
            history_len=len(history),
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


def _sse(event: str, data: dict) -> str:
    """Hand-rolled SSE frame: an `event:` line, a `data:` line (JSON), then a
    blank line -- the wire format a browser EventSource parses."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@app.post("/api/chat/stream", response_class=StreamingResponse)
def chat_stream(req: ChatRequest) -> StreamingResponse:
    """SSE variant of /api/chat: streams progress ("Running query 2...")
    before the final answer, so the UI isn't frozen for the 20-30s a
    multi-round agent run can take. Same get_response() call as /api/chat --
    only the progress callback and the event framing differ, so the two
    endpoints can never drift out of sync with each other.

    Events: zero or more `status` ({"message": str}), then exactly one of
    `answer` (the full ChatResponse, JSON) or `error` ({"error", "request_id"}).
    """
    request_id = new_request_id()
    cid = _resolve_client(req.client_id)  # 404 before we open the stream
    conv_id, history = _resolve_conversation(cid, req)  # 404 on a bad conversation_id

    def worker(q: "queue.Queue") -> None:
        # The ContextVar override is set INSIDE this worker thread -- a new
        # OS thread does not inherit the caller's contextvars context, so
        # setting it here (not in the request thread) is what makes this
        # thread's DB/semantic-layer calls resolve to the right tenant.
        client_registry.set_active_client_override(cid)
        started = time.perf_counter()
        try:
            resp = get_response(
                req.question,
                history=history,
                request_id=request_id,
                on_progress=lambda msg: q.put(("status", {"message": msg})),
            )
            out = to_chat_response(resp)
            out.conversation_id = conv_id
            conversation_store.append(conv_id, cid, "user", req.question)
            conversation_store.append(conv_id, cid, "assistant", resp.get("insight_text", ""))
            log_event(
                logger,
                "api_chat_stream",
                request_id=request_id,
                client_id=cid,
                question_len=len(req.question),
                history_len=len(history),
                duration_ms=round((time.perf_counter() - started) * 1000),
                status=out.status,
            )
            q.put(("answer", out.model_dump()))
        except Exception:
            logger.exception(
                "api_chat_stream failed (request_id=%s, client_id=%s)", request_id, cid
            )
            q.put(
                (
                    "error",
                    {
                        "error": (
                            "Something went wrong while answering your question. "
                            f"Please try again. Reference: {request_id}"
                        ),
                        "request_id": request_id,
                    },
                )
            )
        finally:
            client_registry.set_active_client_override(None)
            q.put(None)  # sentinel: no more events

    def event_stream():
        q: "queue.Queue" = queue.Queue()
        threading.Thread(target=worker, args=(q,), daemon=True).start()
        while True:
            item = q.get()
            if item is None:
                break
            event, payload = item
            yield _sse(event, payload)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/alerts", response_model=list[Alert])
def alerts(client_id: str | None = None) -> list[Alert]:
    cid = _resolve_client(client_id)
    return [Alert(**a) for a in alerts_engine.evaluate_all_alerts(client_id=cid)]


@app.get("/api/popular-questions", response_model=list[PopularQuestion])
def popular_questions(client_id: str | None = None) -> list[PopularQuestion]:
    """Most-asked questions for this client, aggregated across every
    conversation (no login yet, so this is server-wide, not per-person)."""
    cid = _resolve_client(client_id)
    return [PopularQuestion(**q) for q in conversation_store.top_questions(cid)]


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
