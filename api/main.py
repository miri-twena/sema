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

import csv
import io
import json
import queue
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse

# The backend modules (db, wiring, client_registry, ...) resolve via the
# editable install (pip install -e ., see pyproject.toml) -- no sys.path hack.
from sema_core import client_registry
from sema_core.agent import agent
from sema_core.agent.agent import generate_title
from sema_core.agent.prompts import (
    build_drill_context,
    build_pulse_context,
    build_scope_context,
    build_tenant_context,
)
from sema_core import alerts_engine
from sema_core.conversation_store import (
    ConversationNotFoundError,
    SqliteConversationStore,
    ThreadNotFoundError,
    truncate_by_tokens,
)
from sema_core.current_user import current_identity
from sema_core import data_scope
from sema_core.org_user_store import (
    AdminScopeError,
    DuplicateEmailError,
    InvalidDataScopeError,
    LastAdminError,
    OrgUserNotFoundError,
    OrgUserStore,
)
from sema_core.org_settings_store import (
    CURRENCIES,
    VALID_TIMEZONES,
    InvalidSettingError,
    OrgSettingsStore,
)
from sema_core import retention
from sema_core import data_sources
from sema_core.agent.semantic import (
    get_metric,
    load_glossary,
    load_knowledge,
    load_rules,
    load_semantic_layer,
    semantic_dir,
)
from sema_core.semantic_store import (
    SemanticDraftNotFoundError,
    SemanticStore,
    SemanticVersionNotFoundError,
)
from sema_core.semantic_editor import (
    apply_draft_to_files,
    build_model_view,
    read_all_files,
    write_atomic,
)
from sema_core.semantic_validate import validate_item
from sema_core.db import check_connection, run_query
from sema_core.obs import get_logger, log_admin_event, log_event, new_request_id
from sema_core.audit_store import AuditStore
from sema_core import home_config
from sema_core.home_config_store import HomeConfigNotFoundError, HomeConfigStore
from sema_core.daily_brief import build_daily_brief
from sema_core.daily_brief import filter_for_scope as daily_brief_filter_for_scope
from sema_core.overview import build_overview
from sema_core.settings import settings
from sema_core.wiring import get_response

from api.models import (
    AdminInviteRequest,
    AdminUser,
    AdminUserList,
    AdminUserUpdate,
    AlertCatalogItem,
    AuditEvent,
    AuditEventList,
    CurrencyInfo,
    DataSource,
    ReportProblemResponse,
    HomeConfig,
    HomeConfigPreview,
    HomeConfigResponse,
    DataScopeInfo,
    OrgSettings,
    OrgSettingsUpdate,
    PublicOrgSettings,
    RetentionPolicy,
    RetentionPreview,
    RoleInfo,
    SemanticDraftSave,
    SemanticGlossaryItem,
    SemanticKnowledgeItem,
    SemanticMetricItem,
    SemanticModelResponse,
    SemanticPublishRequest,
    SemanticRuleItem,
    SemanticValidateRequest,
    SemanticValidateResult,
    SemanticVersion,
    Alert,
    BriefInsight,
    DailyBriefResponse,
    PulseMetric,
    ChatRequest,
    ChatResponse,
    Client,
    ClientChangeRequest,
    ConversationDetail,
    ConversationMessage,
    ConversationSummary,
    ConversationUpdate,
    Health,
    Kpi,
    Overview,
    PopularQuestion,
    SchemaResponse,
    ThreadDetail,
    ThreadSummary,
)
from api.serialize import build_schema, to_chat_response

logger = get_logger("api")

# The app's own conversation metadata store (SQLite) -- separate from the
# tenant analytics databases in db.py. Module-level singleton; tests
# monkeypatch this attribute with an isolated store pointed at a temp file.
conversation_store = SqliteConversationStore(settings.conversation_db_path)

# Organization users store (admin panel) -- same SQLite metadata DB, separate
# table. Module-level singleton; tests monkeypatch this attribute with an
# isolated store pointed at a temp file, same as conversation_store above.
org_user_store = OrgUserStore(settings.conversation_db_path)

# Semantic-model drafts + version history (admin panel) -- same SQLite
# metadata DB, separate tables. Module-level singleton; tests monkeypatch this
# attribute with an isolated store pointed at a temp file.
semantic_store = SemanticStore(settings.conversation_db_path)

# Organization settings (admin panel) -- same SQLite metadata DB, separate
# table. Module-level singleton; tests monkeypatch this attribute with an
# isolated store pointed at a temp file, same as the stores above.
org_settings_store = OrgSettingsStore(settings.conversation_db_path)

# Append-only admin-action audit log (spec §3) -- same SQLite metadata DB,
# separate table. Module-level singleton; tests monkeypatch this attribute
# with an isolated store pointed at a temp file, same as the stores above.
audit_store = AuditStore(settings.conversation_db_path)

# Home screen configuration (spec §1) -- same SQLite metadata DB, separate
# table. Module-level singleton; tests monkeypatch this attribute with an
# isolated store pointed at a temp file, same as the stores above.
home_config_store = HomeConfigStore(settings.conversation_db_path)


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


def require_client_admin() -> dict:
    """Admin-panel auth: resolve the current identity to a real org_users row
    and require an active client_admin. Applied per-route (via Depends) to the
    /api/admin/* endpoints only -- NOT globally like require_api_key.

    Built as real middleware even though the identity is mocked for now (see
    sema_core.current_user): when login lands, current_identity() starts
    reading a verified session and this check keeps working unchanged. Returns
    the resolved user dict so endpoints know who "self" is (to tag is_self and
    to scope every query to the admin's own client_id -- a client admin manages
    only their own organization).
    """
    identity = current_identity()
    try:
        user = org_user_store.get_user(identity["client_id"], _identity_user_id(identity))
    except OrgUserNotFoundError:
        raise HTTPException(status_code=403, detail="not authorized") from None
    if user["role"] != "client_admin" or user["status"] != "active":
        raise HTTPException(status_code=403, detail="not authorized")
    return user


def _identity_user_id(identity: dict) -> str:
    """Resolve the mock identity (client_id + email) to its user id. Raises
    OrgUserNotFoundError if the identity has no row for that client, which
    require_client_admin turns into a 403."""
    row = org_user_store.get_by_email(identity["client_id"], identity["email"])
    if row is None:
        raise OrgUserNotFoundError(identity["email"])
    return row["id"]


# A synthetic "no scoping installed" user: full access, no real id. Returned
# whenever the current identity doesn't resolve for the requested client --
# either a demo client with no admin panel/users seeded yet (e.g. the
# insurance client), or (once real auth lands) any tenant this feature hasn't
# been enabled for. Chat/overview/brief/alerts/popular-questions must all
# keep working unrestricted in that case, exactly as they did before this
# feature shipped.
_UNSCOPED_USER = {"id": None, "data_scope": "full"}


def current_org_user(cid: str) -> dict:
    """The current (mocked) identity resolved to its org_users row for
    client `cid` -- used by data-serving endpoints (chat, overview, brief,
    alerts, popular-questions) to read the requester's data_scope WITHOUT
    requiring client_admin (contrast require_client_admin, which also
    enforces the admin role and always resolves against the identity's OWN
    client_id). The mock identity only has a home client (see
    current_user.py); for any OTHER client_id (or one where the identity
    doesn't resolve to a real row) this returns _UNSCOPED_USER rather than
    raising, since scoping is only meaningful for the client the admin panel
    actually manages."""
    identity = current_identity()
    if identity["client_id"] != cid:
        return _UNSCOPED_USER
    try:
        return org_user_store.get_user(cid, _identity_user_id(identity))
    except OrgUserNotFoundError:
        return _UNSCOPED_USER


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


def _effective_home_config(cid: str, which: str = "published") -> tuple[dict, list[str]]:
    """This client's effective home config (sema_core.home_config) merged
    over the defaults, plus any deprecated-metric warnings -- `which` is
    "published" for every public-facing endpoint (a client with nothing
    published gets home_config.DEFAULT_CONFIG, reproducing pre-feature
    behavior exactly) or "draft" for the admin preview endpoint."""
    row = home_config_store.get_or_create(cid)
    stored = row["published"] if which == "published" else row["draft"] or row["published"]
    return home_config.effective_config(cid, stored)


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


def _resolve_persist_target(cid: str, req: ChatRequest) -> tuple[str, list[dict], bool]:
    """Where this turn's history comes from and where it will be persisted:
    either the MAIN conversation (existing behavior, unchanged) or a
    drill-down THREAD anchored at (conversation_id, turn_index, drill_context).
    Returns (target_id, token-budgeted history, is_thread).

    A request only takes the thread path when conversation_id, turn_index AND
    drill_context are ALL present. A drill-down with no turn_index -- the
    home-dashboard's KPI cards, which have no parent conversation to anchor
    to -- falls through to the ordinary conversation path unchanged, exactly
    as every drill-down worked before threads existed.
    """
    if req.conversation_id is not None and req.turn_index is not None and req.drill_context is not None:
        dc = req.drill_context
        try:
            thread_id = conversation_store.get_or_create_thread(
                req.conversation_id, cid, req.turn_index, dc.kind, dc.title
            )
            history = conversation_store.get_thread_turns(thread_id, cid)
        except ConversationNotFoundError:
            raise HTTPException(status_code=404, detail="unknown conversation_id") from None
        return thread_id, truncate_by_tokens(history, settings.history_token_budget), True

    conv_id, history = _resolve_conversation(cid, req)
    return conv_id, history, False


def _persist_turn(
    cid: str,
    target_id: str,
    is_thread: bool,
    parent_conversation_id: str | None,
    question: str,
    resp: dict,
    out: ChatResponse,
) -> None:
    """Persist one user+assistant turn and set the id(s) the client should
    send on its NEXT request. A thread turn echoes the PARENT conversation_id
    back UNCHANGED (so the client never mistakes a drill turn for having
    switched its main chat) and additionally reports thread_id; a main-chat
    turn sets conversation_id as it always has."""
    payload = out.model_dump_json()
    if is_thread:
        conversation_store.append_thread_message(target_id, cid, "user", question)
        conversation_store.append_thread_message(
            target_id, cid, "assistant", resp.get("insight_text", ""), payload=payload
        )
        out.conversation_id = parent_conversation_id
        out.thread_id = target_id
    else:
        conversation_store.append(target_id, cid, "user", question)
        conversation_store.append(target_id, cid, "assistant", resp.get("insight_text", ""), payload=payload)
        out.conversation_id = target_id


def _pulse_context(client_id: str, scope_id: str) -> str:
    """The "Recent business signals" block (sema_core.agent.prompts.
    build_pulse_context): today's daily-brief insight headlines plus other
    users' trending questions, both scope-filtered exactly like their own
    endpoints -- grounds an off-topic redirect (or any follow-up suggestion)
    in something real instead of a generic guess. Never lets a brief/
    trending failure break the chat request itself: any error just yields no
    pulse block, same fail-open philosophy as build_daily_brief itself."""
    try:
        brief = daily_brief_filter_for_scope(build_daily_brief(), scope_id)
        headlines = [i["headline"] for i in brief.get("insights", [])]
    except Exception:
        headlines = []
    try:
        metrics = load_semantic_layer(client_id) if scope_id != "full" else []
        trending = [
            q["question"]
            for q in conversation_store.top_questions(client_id)
            if scope_id == "full" or not _question_is_blocked(q["question"], metrics, scope_id)
        ]
    except Exception:
        trending = []
    return build_pulse_context(headlines, trending)


def _internal_context(req: ChatRequest, client_id: str, scope_id: str) -> str | None:
    """Server-side construction of the [SEMA-CONTEXT] block.

    Always carries the client's governed analytics defaults (build_tenant_context),
    the requester's data-access scope (build_scope_context), and ambient business
    signals (_pulse_context) so the clarification flow, the access-scope decline,
    and off-topic redirects are all driven deterministically by real context on
    BOTH the main chat and drill-downs. When the question came from a widget, the
    drill-down focus is appended -- all SERVER-built from structured inputs, so
    no client free text ever reaches the model as instructions.
    """
    # An admin-set org_settings.timezone (spec §2) wins over the client's
    # static YAML timezone -- see get_analytics_config's timezone_override.
    org_tz = (org_settings_store.get(client_id) or {}).get("timezone")
    tenant = build_tenant_context(
        client_registry.get_analytics_config(client_id, timezone_override=org_tz)
    )
    scope = build_scope_context(scope_id, load_semantic_layer(client_id))
    parts = [tenant, scope]
    pulse = _pulse_context(client_id, scope_id)
    if pulse:
        parts.append(pulse)
    if req.drill_context is not None:
        dc = req.drill_context
        parts.append(build_drill_context(dc.kind, dc.title, dc.detail))
    return "\n\n".join(parts)


# Best-effort keyword classifier for /api/popular-questions -- unlike chat
# (which the agent pipeline enforces deterministically) a past question's
# TEXT has no metric binding to check, so this is a heuristic, not a hard
# guarantee: only 4+ letter words from a metric's own label, matched as a
# substring. A question is dropped ONLY when every metric it matched is
# blocked -- if it matches nothing (including non-English text this simple
# check can't classify) or matches at least one ALLOWED metric too, it's
# kept, since silently hiding a question we can't confidently classify would
# be worse than occasionally showing one that's actually out of scope (chat
# itself still enforces the real gate when it's tapped).
_LABEL_WORD_RE = re.compile(r"[a-z]{4,}")


def _question_is_blocked(question: str, metrics: list[dict], scope_id: str) -> bool:
    q = question.lower()
    matched_any = False
    for m in metrics:
        words = _LABEL_WORD_RE.findall(m["label"].lower())
        if any(w in q for w in words):
            matched_any = True
            if data_scope.metric_allowed(m, scope_id):
                return False  # matched an ALLOWED metric too -- keep it
    return matched_any


def _client_model(c: dict) -> Client:
    cfg, _warnings = _effective_home_config(c["id"])
    override = cfg["suggested_questions"]["questions"]
    return Client(
        id=c["id"],
        label=c["label"],
        semantic_dir=c.get("semantic_dir", ""),
        # An empty override means "nothing published yet" -- keep the
        # client's static config/clients.yaml list unchanged.
        suggested_questions=override or c.get("suggested_questions", []),
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


@app.get("/api/org-settings", response_model=PublicOrgSettings)
def public_org_settings(client_id: str | None = None) -> PublicOrgSettings:
    """The subset of org settings every user needs (sidebar name/logo, shared
    KPI/table/chart formatting) -- NOT admin-gated, same visibility rule as
    /api/clients: the whole organization sees the sidebar, not just admins."""
    cid = _resolve_client(client_id)
    label = client_registry.get_client_by_id(cid).get("label", cid)
    row = org_settings_store.get_or_create(cid, default_name=label)
    symbol, position = CURRENCIES.get(row["currency"], ("$", "prefix"))
    return PublicOrgSettings(
        name=row["name"],
        logo_path=row["logo_path"],
        currency=row["currency"],
        currency_symbol=symbol,
        currency_position=position,
        number_format=row["number_format"],
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    request_id = new_request_id()
    cid = _resolve_client(req.client_id)  # 404 before we touch any tenant's DB
    # Captured before persisting: a brand-new conversation (no conversation_id
    # sent) gets an LLM-generated topic title once its first turn succeeds.
    is_new_conversation = req.conversation_id is None
    # 404 on a bad conversation_id, whether resolving the main chat or a
    # drill-down thread's parent.
    target_id, history, is_thread = _resolve_persist_target(cid, req)
    scope_id = current_org_user(cid)["data_scope"]
    # Point the whole agent run (db + semantic) at this request's client.
    client_registry.set_active_client_override(cid)
    started = time.perf_counter()
    try:
        resp = get_response(
            req.question,
            history=history,
            request_id=request_id,
            internal_context=_internal_context(req, cid, scope_id),
            scope_id=scope_id,
        )
        out = to_chat_response(resp)
        # Persist this turn only on success -- a failed run leaves the
        # conversation/thread as it was, rather than recording a broken
        # exchange. Store the RENDERED answer alongside its text: reopening
        # this chat (or widget drill-down) restores KPI cards/charts/tables,
        # instead of degrading a rich answer to a paragraph. The agent still
        # reads only the text (get_turns/get_thread_turns), so this costs the
        # prompt nothing.
        _persist_turn(cid, target_id, is_thread, req.conversation_id, req.question, resp, out)
        if is_new_conversation:
            # Overwrites the instant trim-based title append() already set.
            # generate_title has its own fallback, so this can't fail the request.
            conversation_store.rename(target_id, cid, generate_title(req.question))
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
    # Captured before persisting: a brand-new conversation (no conversation_id
    # sent) gets an LLM-generated topic title once its first turn succeeds.
    is_new_conversation = req.conversation_id is None
    # 404 on a bad conversation_id, whether resolving the main chat or a
    # drill-down thread's parent.
    target_id, history, is_thread = _resolve_persist_target(cid, req)
    scope_id = current_org_user(cid)["data_scope"]

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
                # The agent emits {"stage": ..., "index"/"rows"/"tables": ...}.
                # A bare string is still accepted so any caller (and the older
                # tests) that reports prose keeps working.
                on_progress=lambda ev: q.put(
                    ("status", ev if isinstance(ev, dict) else {"message": ev})
                ),
                internal_context=_internal_context(req, cid, scope_id),
                scope_id=scope_id,
            )
            out = to_chat_response(resp)
            # Must persist exactly like the non-streaming /api/chat above --
            # without it the answer is stored as bare text (or not at all),
            # and reopening the chat/thread has no rendered response to show.
            _persist_turn(cid, target_id, is_thread, req.conversation_id, req.question, resp, out)
            if is_new_conversation:
                # Overwrites the instant trim-based title append() already
                # set. generate_title has its own fallback, so this can't
                # fail the stream.
                conversation_store.rename(target_id, cid, generate_title(req.question))
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


@app.get("/api/conversations", response_model=list[ConversationSummary])
def list_conversations(
    client_id: str | None = None, include_archived: bool = False
) -> list[ConversationSummary]:
    """This client's chat history for the sidebar: pinned first, then most
    recently updated. Archived chats are hidden unless asked for."""
    cid = _resolve_client(client_id)
    return [
        ConversationSummary(**c)
        for c in conversation_store.list_conversations(cid, include_archived=include_archived)
    ]


def _conversation_or_404(conversation_id: str, cid: str) -> dict:
    """Look up one conversation's metadata, 404ing exactly like the chat
    routes do -- unknown and wrong-tenant are indistinguishable on purpose."""
    for c in conversation_store.list_conversations(cid, include_archived=True):
        if c["id"] == conversation_id:
            return c
    raise HTTPException(status_code=404, detail="unknown conversation_id")


@app.get("/api/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str, client_id: str | None = None) -> ConversationDetail:
    """One conversation with its full transcript -- what "reopen this chat" needs."""
    cid = _resolve_client(client_id)
    meta = _conversation_or_404(conversation_id, cid)
    try:
        raw = conversation_store.get_messages(conversation_id, client_id=cid)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="unknown conversation_id") from None

    messages: list[ConversationMessage] = []
    for m in raw:
        payload = None
        if m.get("payload"):
            try:
                payload = ChatResponse.model_validate_json(m["payload"])
            except Exception:
                # A payload written by an older//changed contract shouldn't
                # make the whole chat unopenable -- fall back to text only.
                logger.warning(
                    "unreadable payload in conversation %s; falling back to text", conversation_id
                )
        messages.append(
            ConversationMessage(role=m["role"], content=m["content"], payload=payload)
        )

    return ConversationDetail(
        id=meta["id"],
        title=meta["title"],
        pinned=meta["pinned"],
        archived=meta["archived"],
        messages=messages,
    )


@app.patch("/api/conversations/{conversation_id}", response_model=ConversationSummary)
def update_conversation(
    conversation_id: str, req: ConversationUpdate, client_id: str | None = None
) -> ConversationSummary:
    """Rename / pin / archive. Only the fields present in the body change."""
    cid = _resolve_client(client_id)
    _conversation_or_404(conversation_id, cid)
    try:
        if req.title is not None:
            conversation_store.rename(conversation_id, cid, req.title)
        if req.pinned is not None:
            conversation_store.set_pinned(conversation_id, cid, req.pinned)
        if req.archived is not None:
            conversation_store.set_archived(conversation_id, cid, req.archived)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="unknown conversation_id") from None
    return ConversationSummary(**_conversation_or_404(conversation_id, cid))


@app.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, client_id: str | None = None) -> None:
    cid = _resolve_client(client_id)
    _conversation_or_404(conversation_id, cid)
    try:
        conversation_store.delete(conversation_id, cid)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="unknown conversation_id") from None


@app.get("/api/conversations/{conversation_id}/threads", response_model=list[ThreadSummary])
def list_threads(conversation_id: str, client_id: str | None = None) -> list[ThreadSummary]:
    """Thread summaries for one conversation's widgets: anchor + how many
    follow-up questions were asked in each, so the client can badge them.
    Threads never appear in the sidebar's conversation list -- this is the
    only place their existence is surfaced."""
    cid = _resolve_client(client_id)
    _conversation_or_404(conversation_id, cid)
    return [ThreadSummary(**t) for t in conversation_store.list_threads(conversation_id, cid)]


@app.get(
    "/api/conversations/{conversation_id}/threads/{thread_id}", response_model=ThreadDetail
)
def get_thread(conversation_id: str, thread_id: str, client_id: str | None = None) -> ThreadDetail:
    """One thread's full transcript -- what reopening a widget's drill-down
    needs in order to resume it instead of starting over."""
    cid = _resolve_client(client_id)
    _conversation_or_404(conversation_id, cid)
    meta = conversation_store.get_thread_meta(conversation_id, cid, thread_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="unknown thread_id")
    try:
        raw = conversation_store.get_thread_messages(thread_id, cid)
    except ThreadNotFoundError:
        raise HTTPException(status_code=404, detail="unknown thread_id") from None

    messages: list[ConversationMessage] = []
    for m in raw:
        payload = None
        if m.get("payload"):
            try:
                payload = ChatResponse.model_validate_json(m["payload"])
            except Exception:
                # Same belt-and-braces as get_conversation: an unreadable
                # payload degrades to text rather than making the whole
                # thread unopenable.
                logger.warning(
                    "unreadable payload in thread %s; falling back to text", thread_id
                )
        messages.append(ConversationMessage(role=m["role"], content=m["content"], payload=payload))

    return ThreadDetail(
        id=thread_id,
        conversation_id=conversation_id,
        turn_index=meta["turn_index"],
        widget_kind=meta["widget_kind"],
        widget_title=meta["widget_title"],
        messages=messages,
    )


# --- admin: users and permissions (spec §6.1) ------------------------------
# Every route requires an active client_admin (require_client_admin) and is
# scoped to that admin's OWN client_id -- resolved from the mocked identity,
# never a query param, so a client admin can only ever manage their own org.

# A pragmatic email check: exactly one @, non-empty local part, and a dotted
# domain. Deliberately permissive (not RFC 5322) -- it rejects obvious typos
# without falsely rejecting valid addresses. Client-side validation mirrors it.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _admin_user(row: dict, me: dict) -> AdminUser:
    """Wrap a store row as an AdminUser, tagging is_self against the viewer."""
    return AdminUser(**row, is_self=(row["id"] == me["id"]))


def _audit(event: str, *, client_id: str, actor: dict, action: str, **kw) -> dict:
    """Thin wrapper around log_admin_event pre-bound to this module's
    audit_store singleton -- the ONE call site every admin-mutation route
    uses (spec §3 item 7), so no route has to remember to pass the store.
    Returns the persisted audit row (most callers ignore it; report-problem
    needs the generated event id)."""
    return log_admin_event(
        logger, event, audit_store=audit_store, client_id=client_id, actor=actor, action=action, **kw
    )


@app.get("/api/admin/me", response_model=AdminUser)
def admin_me(me: dict = Depends(require_client_admin)) -> AdminUser:
    """The current (mocked) user, resolved live from the org_users table."""
    return _admin_user(me, me)


# The role catalog's single source of truth (spec §3) -- the UI's header
# legend and per-row tooltip both read this via GET /api/admin/roles rather
# than hardcoding the copy, so it only has to be written once. Analyst and
# Viewer are explicitly called out as identical today: the data-scope split
# between them is reserved for V2, not implemented yet.
_ROLE_CATALOG = (
    RoleInfo(
        id="client_admin",
        label="Admin",
        description="Full access to the organization: manage users and roles, plus "
        "everything an Analyst or Viewer can do.",
    ),
    RoleInfo(
        id="analyst",
        label="Analyst",
        description="Can ask SEMA questions, view all business data, and drill into "
        "results. Identical to Viewer today -- a data-scope distinction between the "
        "two is reserved for a future release.",
    ),
    RoleInfo(
        id="viewer",
        label="Viewer",
        description="Can ask SEMA questions and view all business data. Identical to "
        "Analyst today -- a data-scope distinction between the two is reserved for a "
        "future release.",
    ),
)


@app.get("/api/admin/roles", response_model=list[RoleInfo])
def admin_roles(me: dict = Depends(require_client_admin)) -> list[RoleInfo]:
    """The role catalog backing the UI's legend/tooltip. Gated by
    require_client_admin like every other admin route, even though the
    content itself isn't sensitive -- consistent with spec item 4 ("ALL
    admin endpoints enforce ... client_admin")."""
    return list(_ROLE_CATALOG)


@app.get("/api/admin/data-scopes", response_model=list[DataScopeInfo])
def admin_data_scopes(me: dict = Depends(require_client_admin)) -> list[DataScopeInfo]:
    """The data-scope catalog backing the "Data access" column's legend and
    the scope editor -- sema_core.data_scope is the single source of truth,
    so this is a thin wrapper, same pattern as admin_roles above."""
    return [DataScopeInfo(**d) for d in data_scope.catalog()]


@app.get("/api/admin/users", response_model=AdminUserList)
def admin_list_users(
    q: str | None = None,
    role: str | None = None,
    me: dict = Depends(require_client_admin),
) -> AdminUserList:
    """This org's users, with optional search (name/email) and role filter.
    The two counts are of the whole org, not the filtered view, so the subtitle
    stays stable while searching."""
    cid = me["client_id"]
    rows = org_user_store.list_users(cid, q=q, role=role)
    everyone = org_user_store.list_users(cid)
    pending = sum(1 for u in everyone if u["status"] == "invited")
    return AdminUserList(
        users=[_admin_user(r, me) for r in rows],
        member_count=len(everyone) - pending,
        pending_count=pending,
    )


@app.post("/api/admin/users/invite", response_model=AdminUser, status_code=201)
def admin_invite_user(
    req: AdminInviteRequest, me: dict = Depends(require_client_admin)
) -> AdminUser:
    """Invite a user by email (status=invited, expires in 7 days). No email is
    actually sent yet -- it's logged. 422 on a malformed email, 409 if the
    email already exists in this org."""
    email = req.email.strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    cid = me["client_id"]
    try:
        row = org_user_store.invite(
            cid, email, req.role, invited_by=me["id"], data_scope=req.data_scope
        )
    except DuplicateEmailError:
        raise HTTPException(
            status_code=409, detail="A user with this email already exists."
        ) from None
    except InvalidDataScopeError:
        raise HTTPException(
            status_code=422, detail="That data-access scope isn't available yet."
        ) from None
    # No mail transport yet -- record the intent so it's observable (and so the
    # swap to a real sender later is a one-line change here).
    _audit(
        "admin_invite", client_id=cid, actor=me, action="user.invited",
        target_type="user", target_id=row["id"], target_label=email,
        after={"role": req.role, "data_scope": row["data_scope"]},
    )
    return _admin_user(row, me)


@app.patch("/api/admin/users/{user_id}", response_model=AdminUser)
def admin_update_user(
    user_id: str, req: AdminUserUpdate, me: dict = Depends(require_client_admin)
) -> AdminUser:
    """Change a user's role/status/data_scope. Only the fields present in the
    body change. 409 if the change would remove the last active admin (or
    tries to give an admin a non-'full' scope), 403 if an admin tries to
    change their OWN data_scope, 422 for an unrecognized/unselectable
    ('custom') scope, 404 if the user isn't in this org."""
    cid = me["client_id"]
    if req.data_scope is not None and user_id == me["id"]:
        raise HTTPException(status_code=403, detail="You can't change your own data access.")
    try:
        before = org_user_store.get_user(cid, user_id)
        if req.role is not None:
            org_user_store.set_role(cid, user_id, req.role)
        if req.status is not None:
            org_user_store.set_status(cid, user_id, req.status)
        if req.data_scope is not None:
            org_user_store.set_data_scope(cid, user_id, req.data_scope)
    except LastAdminError:
        raise HTTPException(
            status_code=409, detail="An organization must keep at least one active admin."
        ) from None
    except AdminScopeError:
        raise HTTPException(
            status_code=409, detail="An admin's data access is always full."
        ) from None
    except InvalidDataScopeError:
        raise HTTPException(
            status_code=422, detail="That data-access scope isn't available yet."
        ) from None
    except OrgUserNotFoundError:
        raise HTTPException(status_code=404, detail="unknown user_id") from None

    after = org_user_store.get_user(cid, user_id)
    label = after["name"] or after["email"]
    # One audit event per field that actually changed -- a role promotion can
    # silently reset data_scope too (see OrgUserStore.set_role), so this
    # compares before/after rather than trusting which fields the request sent.
    if before["role"] != after["role"]:
        _audit(
            "admin_update_user", client_id=cid, actor=me, action="user.role_changed",
            target_type="user", target_id=user_id, target_label=label,
            before={"role": before["role"]}, after={"role": after["role"]},
        )
    if before["status"] != after["status"]:
        action = "user.suspended" if after["status"] == "suspended" else "user.reactivated"
        _audit(
            "admin_update_user", client_id=cid, actor=me, action=action,
            target_type="user", target_id=user_id, target_label=label,
            before={"status": before["status"]}, after={"status": after["status"]},
        )
    if before["data_scope"] != after["data_scope"]:
        _audit(
            "admin_update_user", client_id=cid, actor=me, action="user.data_scope_changed",
            target_type="user", target_id=user_id, target_label=label,
            before={"data_scope": before["data_scope"]}, after={"data_scope": after["data_scope"]},
        )
    return _admin_user(after, me)


@app.delete("/api/admin/users/{user_id}", status_code=204)
def admin_delete_user(user_id: str, me: dict = Depends(require_client_admin)) -> None:
    """Remove a user. 409 if it's the last active admin, 404 if not in this org."""
    cid = me["client_id"]
    try:
        before = org_user_store.get_user(cid, user_id)
        org_user_store.delete(cid, user_id)
    except LastAdminError:
        raise HTTPException(
            status_code=409, detail="An organization must keep at least one active admin."
        ) from None
    except OrgUserNotFoundError:
        raise HTTPException(status_code=404, detail="unknown user_id") from None
    _audit(
        "admin_delete_user", client_id=cid, actor=me, action="user.removed",
        target_type="user", target_id=user_id, target_label=before["name"] or before["email"],
        before={"role": before["role"], "status": before["status"]},
    )


@app.post("/api/admin/users/{user_id}/resend-invite", response_model=AdminUser)
def admin_resend_invite(user_id: str, me: dict = Depends(require_client_admin)) -> AdminUser:
    """Reset an invited user's expiry to 7 days from now. No email is sent --
    logged, like the original invite."""
    cid = me["client_id"]
    try:
        row = org_user_store.resend_invite(cid, user_id)
    except OrgUserNotFoundError:
        raise HTTPException(status_code=404, detail="unknown user_id") from None
    _audit(
        "admin_resend_invite", client_id=cid, actor=me, action="user.invite_resent",
        target_type="user", target_id=user_id, target_label=row["name"] or row["email"],
    )
    return _admin_user(row, me)


# --- admin: semantic model (Draft -> Validate -> Publish) ------------------
# Every route requires an active client_admin and is scoped to that admin's
# OWN client_id, same rule as the users section above. The YAML on disk
# (sql/semantic/*.yaml) is the published source of truth; drafts live only in
# `semantic_store` until Publish writes them.

# Which fields a draft must carry to be savable at all (deeper validation --
# does the SQL actually run? -- happens in semantic_validate.validate_item,
# not here). A "deprecate" draft is exempt: it carries no edits, just intent.
_SEMANTIC_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "metric": ("description", "sql"),
    "rule": ("definition",),
    "knowledge": ("type", "description"),
    "glossary": ("maps_to",),
}


def _semantic_author(me: dict) -> str:
    return me.get("name") or me["email"]


def _item_exists_published(cid: str, section: str, item_key: str) -> bool:
    """Whether this item is in the published YAML today -- the ONLY source of
    truth for create-vs-edit. Never trust the client's claimed action here: a
    client that re-saves a not-yet-published draft (e.g. re-running Validate
    after an edit) without remembering to keep sending action="create" would
    otherwise silently turn it into an "edit" of nothing, and the item would
    vanish from the merged view (there's nothing published to overlay it onto)."""
    if section == "metric":
        return get_metric(item_key, cid) is not None
    if section == "rule":
        return any(r["name"] == item_key for r in load_rules(cid))
    if section == "knowledge":
        return any(k["name"] == item_key for k in load_knowledge(cid))
    if section == "glossary":
        return any(g["term"] == item_key for g in load_glossary(cid))
    return False


def _semantic_model_response(cid: str) -> SemanticModelResponse:
    drafts = semantic_store.list_drafts(cid)
    view = build_model_view(cid, drafts)
    version = semantic_store.latest_version(cid)
    return SemanticModelResponse(
        published_version=version["version"] if version else 0,
        draft_count=len(drafts),
        metrics=[SemanticMetricItem(**m) for m in view["metrics"]],
        rules=[SemanticRuleItem(**r) for r in view["rules"]],
        knowledge=[SemanticKnowledgeItem(**k) for k in view["knowledge"]],
        glossary=[SemanticGlossaryItem(**g) for g in view["glossary"]],
    )


@app.get("/api/admin/semantic", response_model=SemanticModelResponse)
def admin_get_semantic(me: dict = Depends(require_client_admin)) -> SemanticModelResponse:
    """The full model: published metrics/rules/knowledge/glossary, overlaid
    with this admin's own in-progress drafts, plus the header chip's numbers."""
    return _semantic_model_response(me["client_id"])


@app.put("/api/admin/semantic/{section}/{item_key}", response_model=SemanticModelResponse)
def admin_save_semantic_draft(
    section: str, item_key: str, req: SemanticDraftSave, me: dict = Depends(require_client_admin)
) -> SemanticModelResponse:
    """Save (upsert) a draft. Editing an existing metric requires the metric to
    already exist (metrics can't be created in this slice); rules/knowledge/
    glossary may be brand new. Resets the draft's `validated` flag -- see
    semantic_store.save_draft.

    `req.action` is honored ONLY for "deprecate" (an explicit archive intent
    the server can't infer). For anything else, create-vs-edit is derived
    server-side from whether the item is currently published -- see
    _item_exists_published for why the client's own claim can't be trusted.
    """
    cid = me["client_id"]
    if section not in _SEMANTIC_REQUIRED_FIELDS:
        raise HTTPException(status_code=404, detail=f"unknown section: {section}")
    published = _item_exists_published(cid, section, item_key)
    if section == "metric" and not published:
        raise HTTPException(status_code=404, detail="unknown metric")
    action = "deprecate" if req.action == "deprecate" else ("edit" if published else "create")
    if action != "deprecate":
        missing = [f for f in _SEMANTIC_REQUIRED_FIELDS[section] if not req.data.get(f)]
        if missing:
            raise HTTPException(
                status_code=422, detail=f"missing required field(s): {', '.join(missing)}"
            )
    semantic_store.save_draft(cid, section, item_key, req.data, action, author=_semantic_author(me))
    return _semantic_model_response(cid)


@app.delete("/api/admin/semantic/{section}/{item_key}", response_model=SemanticModelResponse)
def admin_delete_semantic_item(
    section: str, item_key: str, me: dict = Depends(require_client_admin)
) -> SemanticModelResponse:
    """Discard the in-progress draft if one exists (this is what the editor's
    "Discard" button calls); otherwise this is a purely-published item, so
    archive it -- create a "deprecate" draft. Publish still has to run for the
    archive to take effect; nothing on disk changes here, and nothing is ever
    hard-deleted."""
    cid = me["client_id"]
    if section not in _SEMANTIC_REQUIRED_FIELDS:
        raise HTTPException(status_code=404, detail=f"unknown section: {section}")
    if semantic_store.get_draft(cid, section, item_key) is not None:
        semantic_store.discard_draft(cid, section, item_key)
    else:
        semantic_store.save_draft(cid, section, item_key, {}, action="deprecate", author=_semantic_author(me))
    return _semantic_model_response(cid)


@app.post("/api/admin/semantic/validate", response_model=SemanticValidateResult)
def admin_validate_semantic_draft(
    req: SemanticValidateRequest, me: dict = Depends(require_client_admin)
) -> SemanticValidateResult:
    """Dry-run the CURRENTLY SAVED draft for (section, item_key) -- not
    whatever the request body might claim -- so what gets validated is
    exactly what Publish would apply. Never 4xxs on a bad query: a rejected
    or failing SQL is a normal `ok: False` result, not a request error."""
    cid = me["client_id"]
    draft = semantic_store.get_draft(cid, req.section, req.item_key)
    if draft is None:
        raise HTTPException(status_code=404, detail="no draft to validate")
    if draft["action"] == "deprecate":
        semantic_store.mark_validated(cid, req.section, req.item_key, True)
        return SemanticValidateResult(ok=True, message="Archiving requires no validation.")
    result = validate_item(cid, req.section, req.item_key, draft["data"])
    semantic_store.mark_validated(cid, req.section, req.item_key, result["ok"])
    return SemanticValidateResult(**result)


@app.post("/api/admin/semantic/publish", response_model=SemanticModelResponse)
def admin_publish_semantic(
    req: SemanticPublishRequest, me: dict = Depends(require_client_admin)
) -> SemanticModelResponse:
    """Re-validate every requested draft server-side (defense in depth -- a
    client-side "already validated" flag is never trusted alone), then write
    the YAML atomically, snapshot the new state as the next version, and clear
    the published drafts. All-or-nothing: if ANY draft fails re-validation,
    nothing is written."""
    cid = me["client_id"]
    author = _semantic_author(me)

    drafts = []
    for ref in req.items:
        draft = semantic_store.get_draft(cid, ref.section, ref.item_key)
        if draft is None:
            raise HTTPException(
                status_code=404, detail=f"no draft for {ref.section}/{ref.item_key}"
            )
        drafts.append(draft)

    failures = []
    for draft in drafts:
        if draft["action"] == "deprecate":
            continue
        # Enforce the workflow rule server-side, not just as a disabled
        # button: a draft that was edited after it was last validated (or
        # never validated at all) resets `validated` to False on save, so
        # this alone catches "skipped validation" without re-running SQL.
        if not draft["validated"]:
            failures.append(
                {"section": draft["section"], "item_key": draft["item_key"],
                 "error": "This draft has not passed validation."}
            )
            continue
        # Re-validate anyway -- defense in depth against a stale `validated`
        # flag (e.g. the underlying data changed between calls).
        result = validate_item(cid, draft["section"], draft["item_key"], draft["data"])
        if not result["ok"]:
            failures.append(
                {"section": draft["section"], "item_key": draft["item_key"], "error": result.get("error")}
            )
    if failures:
        raise HTTPException(
            status_code=409,
            detail={"message": "One or more drafts failed validation.", "failures": failures},
        )

    original_files = read_all_files(cid)
    semantic_store.ensure_baseline(cid, original_files)  # seeds v1 from pre-publish disk, once

    current_files = dict(original_files)
    changed_filenames: set[str] = set()
    changed_items: list[str] = []
    for draft in drafts:
        changed = apply_draft_to_files(
            cid, current_files, draft["section"], draft["item_key"], draft["data"], draft["action"]
        )
        current_files.update(changed)
        changed_filenames.update(changed.keys())
        changed_items.append(f"{draft['section']}:{draft['item_key']}")

    folder = semantic_dir(cid)
    for filename in changed_filenames:
        write_atomic(folder / filename, current_files[filename])

    version = semantic_store.record_version(cid, current_files, changed_items, author)
    semantic_store.clear_drafts(cid, [(d["section"], d["item_key"]) for d in drafts])
    _audit(
        "admin_publish_semantic", client_id=cid, actor=me, action="semantic.published",
        target_type="semantic_version", target_id=str(version["version"]),
        target_label=f"v{version['version']}", after={"changed_items": changed_items},
    )
    return _semantic_model_response(cid)


@app.get("/api/admin/semantic/versions", response_model=list[SemanticVersion])
def admin_list_semantic_versions(me: dict = Depends(require_client_admin)) -> list[SemanticVersion]:
    versions = semantic_store.list_versions(me["client_id"])
    return [
        SemanticVersion(id=v["id"], version=v["version"], changed_items=v["changed_items"],
                         author=v["author"], created_at=v["created_at"])
        for v in versions
    ]


@app.post("/api/admin/semantic/versions/{version_id}/restore", response_model=SemanticVersion)
def admin_restore_semantic_version(
    version_id: str, me: dict = Depends(require_client_admin)
) -> SemanticVersion:
    """Rewrite every semantic YAML file to exactly match an old version's
    snapshot (removing any file that didn't exist back then), then record
    THAT as a new version -- a restore never rewrites history, it publishes
    the old content again, per the spec."""
    cid = me["client_id"]
    try:
        target = semantic_store.get_version(cid, version_id)
    except SemanticVersionNotFoundError:
        raise HTTPException(status_code=404, detail="unknown version_id") from None

    folder = semantic_dir(cid)
    current_filenames = {p.name for p in folder.glob("*.yaml")} if folder.exists() else set()
    target_filenames = set(target["snapshot"].keys())
    for filename in current_filenames - target_filenames:
        (folder / filename).unlink(missing_ok=True)
    for filename, text in target["snapshot"].items():
        write_atomic(folder / filename, text)

    new_version = semantic_store.record_version(
        cid, target["snapshot"], [f"restore:v{target['version']}"], _semantic_author(me)
    )
    _audit(
        "admin_restore_semantic", client_id=cid, actor=me, action="semantic.restored",
        target_type="semantic_version", target_id=str(new_version["version"]),
        target_label=f"v{new_version['version']}",
        before={"version": target["version"]}, after={"version": new_version["version"]},
    )
    return SemanticVersion(
        id=new_version["id"], version=new_version["version"],
        changed_items=new_version["changed_items"], author=new_version["author"],
        created_at=new_version["created_at"],
    )


# --- admin: organization settings (spec §2) ---------------------------------

_LOGO_MAX_BYTES = 1 * 1024 * 1024  # 1MB
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Human-readable audit target_label per settings field -- falls back to the
# raw field name for anything not called out here.
_ORG_SETTINGS_FIELD_LABELS = {
    "name": "Organization name",
    "logo_path": "Logo",
    "timezone": "Timezone",
    "currency": "Currency",
    "number_format": "Number format",
    "default_language": "Default language",
    "retention_policy": "Data retention",
}


def _sniff_logo_format(filename: str, data: bytes) -> str:
    """Return 'png' or 'svg' by SNIFFING the actual bytes (never trusting the
    filename/content-type alone -- a renamed .exe with a .png extension must
    still be rejected). Raises ValueError with a user-facing detail message
    on anything else."""
    name = (filename or "").lower()
    if data[:8] == _PNG_MAGIC:
        return "png"
    if name.endswith(".png"):
        raise ValueError("That file has a .png extension but isn't a real PNG image.")
    head = data[:1024].lstrip(b"\xef\xbb\xbf \t\r\n")
    if (head.startswith(b"<?xml") or head.startswith(b"<svg")) and b"<svg" in data[:4096]:
        return "svg"
    raise ValueError("Only PNG or SVG logo files are supported.")


def _logos_dir() -> Path:
    return settings.conversation_db_path.parent / "logos"


@app.get("/api/admin/org-settings", response_model=OrgSettings)
def admin_get_org_settings(me: dict = Depends(require_client_admin)) -> OrgSettings:
    cid = me["client_id"]
    label = client_registry.get_client_by_id(cid).get("label", cid)
    row = org_settings_store.get_or_create(cid, default_name=label)
    return OrgSettings(**row, conflict=False)


@app.patch("/api/admin/org-settings", response_model=OrgSettings)
def admin_update_org_settings(
    req: OrgSettingsUpdate, me: dict = Depends(require_client_admin)
) -> OrgSettings:
    """Per-field partial update. Every changed field is audit-logged with its
    before/after value (one log_event call per field, spec §2/§3). Never
    rejects on a stale `expected_updated_at` -- last-write-wins; the response's
    `conflict` flag tells the CALLER (not the server) to warn the user."""
    cid = me["client_id"]
    label = client_registry.get_client_by_id(cid).get("label", cid)
    org_settings_store.get_or_create(cid, default_name=label)  # ensure a row exists
    patch = req.model_dump(exclude={"expected_updated_at"}, exclude_none=True)

    before = org_settings_store.get(cid) or {}
    if not patch:
        return OrgSettings(**before, conflict=False)
    try:
        updated = org_settings_store.update(cid, patch, expected_updated_at=req.expected_updated_at)
    except InvalidSettingError as e:
        raise HTTPException(status_code=422, detail=f"invalid value for {e.field}") from None

    conflict = updated.pop("_conflict")
    for field in patch:
        _audit(
            "admin_org_settings_updated", client_id=cid, actor=me, action="org_settings.updated",
            target_type="org_settings", target_id=field,
            target_label=_ORG_SETTINGS_FIELD_LABELS.get(field, field),
            before={field: before.get(field)}, after={field: updated.get(field)},
        )
    return OrgSettings(**updated, conflict=conflict)


@app.get("/api/admin/org-settings/currencies", response_model=list[CurrencyInfo])
def admin_org_settings_currencies(me: dict = Depends(require_client_admin)) -> list[CurrencyInfo]:
    """The currency catalog backing the settings form's picker -- single
    source of truth, same pattern as GET /api/admin/roles."""
    return [CurrencyInfo(code=code, symbol=symbol, position=pos) for code, (symbol, pos) in CURRENCIES.items()]


@app.get("/api/admin/org-settings/timezones", response_model=list[str])
def admin_org_settings_timezones(me: dict = Depends(require_client_admin)) -> list[str]:
    """The IANA timezone list backing the settings form's picker -- pytz's
    own curated ~450-zone list (VALID_TIMEZONES), sorted for a stable,
    scannable dropdown."""
    return sorted(VALID_TIMEZONES)


@app.get("/api/admin/org-settings/retention-preview", response_model=RetentionPreview)
def admin_retention_preview(
    policy: RetentionPolicy, me: dict = Depends(require_client_admin)
) -> RetentionPreview:
    """"N conversations will be deleted on next run" -- called before the user
    confirms a retention_policy change (spec §2). Read-only."""
    cid = me["client_id"]
    count = retention.preview_deletion_count(conversation_store, cid, policy)
    return RetentionPreview(policy=policy, conversations_to_delete=count)


@app.post("/api/admin/org-settings/logo", response_model=OrgSettings)
async def admin_upload_logo(
    file: UploadFile = File(...), me: dict = Depends(require_client_admin)
) -> OrgSettings:
    cid = me["client_id"]
    data = await file.read(_LOGO_MAX_BYTES + 1)
    if len(data) > _LOGO_MAX_BYTES:
        raise HTTPException(status_code=422, detail="Logo must be 1MB or smaller.")
    try:
        ext = _sniff_logo_format(file.filename or "", data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    label = client_registry.get_client_by_id(cid).get("label", cid)
    org_settings_store.get_or_create(cid, default_name=label)  # ensure a row exists
    before = org_settings_store.get(cid)

    logos_dir = _logos_dir()
    logos_dir.mkdir(parents=True, exist_ok=True)
    # Drop any previous logo in the OTHER format first, so switching png<->svg
    # never leaves a stale file that would still get served.
    for old_ext in ("png", "svg"):
        if old_ext != ext:
            (logos_dir / f"{cid}.{old_ext}").unlink(missing_ok=True)
    (logos_dir / f"{cid}.{ext}").write_bytes(data)

    updated = org_settings_store.set_logo_path(cid, f"/api/admin/org-settings/logo/{cid}")
    _audit(
        "admin_org_settings_updated", client_id=cid, actor=me, action="org_settings.updated",
        target_type="org_settings", target_id="logo_path",
        target_label=_ORG_SETTINGS_FIELD_LABELS["logo_path"],
        before={"logo_path": before.get("logo_path") if before else None},
        after={"logo_path": updated["logo_path"]},
    )
    return OrgSettings(**updated, conflict=False)


@app.get("/api/admin/org-settings/logo/{client_id}")
def get_org_logo(client_id: str) -> FileResponse:
    """Serves the uploaded logo -- NOT admin-gated: the sidebar renders it for
    every user in the organization, not just admins (same visibility rule as
    /api/clients, which isn't admin-gated either)."""
    row = org_settings_store.get(client_id)
    if not row or not row.get("logo_path"):
        raise HTTPException(status_code=404, detail="no logo uploaded")
    for ext, media_type in (("png", "image/png"), ("svg", "image/svg+xml")):
        path = _logos_dir() / f"{client_id}.{ext}"
        if path.exists():
            return FileResponse(path, media_type=media_type)
    raise HTTPException(status_code=404, detail="logo file missing")


# --- admin: audit log (spec §3) ---------------------------------------------

_AUDIT_CSV_COLUMNS = (
    "created_at", "actor_name", "actor_role", "action",
    "target_type", "target_label", "before", "after",
)


@app.get("/api/admin/audit", response_model=AuditEventList)
def admin_list_audit(
    actor: str | None = None,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = None,
    page: int = 1,
    me: dict = Depends(require_client_admin),
) -> AuditEventList:
    """Paginated, filtered view of this org's append-only audit log.
    `category` is a prefix match on the dotted action id ("user" matches
    every "user.*" action); `q` free-texts target_label; `date_from`/
    `date_to` are ISO timestamps, inclusive."""
    cid = me["client_id"]
    result = audit_store.list_events(
        cid, actor_id=actor, category=category, start=date_from, end=date_to, q=q, page=page,
    )
    return AuditEventList(
        events=[AuditEvent(**e) for e in result["events"]],
        total=result["total"], page=result["page"], page_size=result["page_size"],
    )


@app.get("/api/admin/audit/export")
def admin_export_audit(
    actor: str | None = None,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = None,
    me: dict = Depends(require_client_admin),
) -> Response:
    """CSV of the CURRENT filter (same params as the list endpoint), capped
    at 10K rows server-side (spec §3 item 8) -- unlike the list endpoint this
    ignores pagination and returns every matching row up to the cap."""
    cid = me["client_id"]
    rows = audit_store.export_rows(cid, actor_id=actor, category=category, start=date_from, end=date_to, q=q)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_AUDIT_CSV_COLUMNS)
    for e in rows:
        writer.writerow([
            e["created_at"], e["actor_name"] or "", e["actor_role"] or "", e["action"],
            e["target_type"] or "", e["target_label"] or "",
            json.dumps(e["before"]) if e["before"] is not None else "",
            json.dumps(e["after"]) if e["after"] is not None else "",
        ])
    # BOM so Excel reads it as UTF-8 (Hebrew actor names/labels) -- same
    # convention the frontend's own CSV export uses (lib/clipboard.ts).
    csv_text = "﻿" + buf.getvalue()
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="audit-log-{cid}.csv"'},
    )


# --- admin: home screen customization (spec §1) -----------------------------


def _home_config_response(row: dict, warnings: list[str]) -> HomeConfigResponse:
    return HomeConfigResponse(
        draft=HomeConfig(**row["draft"]) if row["draft"] is not None else None,
        published=HomeConfig(**row["published"]) if row["published"] is not None else None,
        version=row["version"],
        published_by=row["published_by"],
        published_at=row["published_at"],
        updated_at=row["updated_at"],
        warnings=warnings,
    )


@app.get("/api/admin/alerts-catalog", response_model=list[AlertCatalogItem])
def admin_alerts_catalog(me: dict = Depends(require_client_admin)) -> list[AlertCatalogItem]:
    """Every alert this client's semantic layer defines, metadata only --
    backs the Home-config editor's Alerts accordion (spec item 11), which
    needs every POSSIBLE alert, not just /api/alerts's triggered-today
    subset."""
    return [AlertCatalogItem(**a) for a in alerts_engine.catalog(me["client_id"])]


@app.get("/api/admin/home-config", response_model=HomeConfigResponse)
def admin_get_home_config(me: dict = Depends(require_client_admin)) -> HomeConfigResponse:
    """The editor's full state: draft (if any), published (if any), and
    deprecated-metric warnings against the PUBLISHED config (spec item 13's
    editor warning badge)."""
    cid = me["client_id"]
    row = home_config_store.get_or_create(cid)
    _cfg, warnings = home_config.effective_config(cid, row["published"])
    return _home_config_response(row, warnings)


@app.put("/api/admin/home-config", response_model=HomeConfigResponse)
def admin_save_home_config_draft(
    body: HomeConfig, me: dict = Depends(require_client_admin)
) -> HomeConfigResponse:
    """Autosave the whole draft blob. No validation here -- deep validation
    (metrics exist/certified, KPI count in range, ...) only runs at Publish,
    same "save freely, validate on the gate" pattern as the semantic model's
    draft/validate/publish split."""
    cid = me["client_id"]
    row = home_config_store.save_draft(cid, body.model_dump())
    _cfg, warnings = home_config.effective_config(cid, row["published"])
    return _home_config_response(row, warnings)


@app.post("/api/admin/home-config/publish", response_model=HomeConfigResponse)
def admin_publish_home_config(me: dict = Depends(require_client_admin)) -> HomeConfigResponse:
    """Validate the current draft server-side (spec item 10 -- defense in
    depth, never trust a client-side "looks fine" alone), then promote it to
    published. All-or-nothing: any validation error blocks the whole publish,
    same rule the semantic model's Publish enforces."""
    cid = me["client_id"]
    row = home_config_store.get_or_create(cid)
    if row["draft"] is None:
        raise HTTPException(status_code=409, detail="Nothing to publish -- no unsaved changes.")
    errors = home_config.validate(cid, row["draft"])
    if errors:
        raise HTTPException(
            status_code=409, detail={"message": "The draft has validation errors.", "errors": errors}
        )
    try:
        row = home_config_store.publish(cid, published_by=_semantic_author(me))
    except HomeConfigNotFoundError:
        raise HTTPException(status_code=409, detail="Nothing to publish -- no unsaved changes.") from None
    _audit(
        "admin_publish_home_config", client_id=cid, actor=me, action="home_config.published",
        target_type="home_config", target_id=str(row["version"]), target_label=f"v{row['version']}",
    )
    _cfg, warnings = home_config.effective_config(cid, row["published"])
    return _home_config_response(row, warnings)


@app.post("/api/admin/home-config/revert", response_model=HomeConfigResponse)
def admin_revert_home_config(me: dict = Depends(require_client_admin)) -> HomeConfigResponse:
    """Discard the in-progress draft, resetting the editor back to the last
    published config -- the simple undo the spec's "Revert" button performs."""
    cid = me["client_id"]
    try:
        row = home_config_store.revert(cid)
    except HomeConfigNotFoundError:
        raise HTTPException(status_code=409, detail="Nothing to revert -- no unsaved changes.") from None
    _audit(
        "admin_revert_home_config", client_id=cid, actor=me, action="home_config.reverted",
        target_type="home_config", target_id=str(row["version"]), target_label=f"v{row['version']}",
    )
    _cfg, warnings = home_config.effective_config(cid, row["published"])
    return _home_config_response(row, warnings)


@app.post("/api/admin/home-config/preview", response_model=HomeConfigPreview)
def admin_preview_home_config(body: HomeConfig, me: dict = Depends(require_client_admin)) -> HomeConfigPreview:
    """The live preview pane's payload (spec item 11): the SAME shapes the
    real home dashboard consumes, computed from the config IN THE REQUEST
    BODY (the editor's current in-memory draft, not necessarily saved yet --
    a GET reading the stored draft would race the separate autosave debounce
    and could preview stale data) and the admin's OWN data scope -- a note
    in `warnings` when that scope would hide part of it."""
    cid = me["client_id"]
    cfg, warnings = home_config.effective_config(cid, body.model_dump())
    scope_id = me["data_scope"]
    if scope_id != "full":
        warnings.append("Your own data-access scope hides parts of this preview from you.")

    client_registry.set_active_client_override(cid)
    try:
        overview_data = build_overview(scope_id=scope_id, config=cfg)
        brief_data = daily_brief_filter_for_scope(
            build_daily_brief(sensitivity=cfg["daily_brief"]["sensitivity"]), scope_id
        )
        if not cfg["daily_brief"]["pulse_enabled"]:
            brief_data = {**brief_data, "pulse": []}
        if not cfg["daily_brief"]["insights_enabled"]:
            brief_data = {**brief_data, "insights": []}
        raw_alerts = alerts_engine.evaluate_all_alerts(client_id=cid, alert_config=cfg["alerts"])
        alerts_data = alerts_engine.filter_for_scope(raw_alerts, scope_id)
        popular = [] if not cfg["suggested_questions"]["trending_enabled"] else conversation_store.top_questions(cid)
        if scope_id != "full" and popular:
            metrics = load_semantic_layer(cid)
            popular = [q for q in popular if not _question_is_blocked(q["question"], metrics, scope_id)]
    finally:
        client_registry.set_active_client_override(None)

    client_cfg = client_registry.get_client_by_id(cid)
    suggested = cfg["suggested_questions"]["questions"] or client_cfg.get("suggested_questions", [])

    return HomeConfigPreview(
        overview=Overview(
            client_id=cid, kpis=[Kpi(**k) for k in overview_data["kpis"]],
            as_of=datetime.now(timezone.utc).isoformat(),
            start=overview_data["start"], end=overview_data["end"],
            available_months=overview_data["available_months"],
        ),
        brief=DailyBriefResponse(
            client_id=cid, as_of=brief_data["as_of"],
            pulse=[PulseMetric(**p) for p in brief_data["pulse"]],
            insights=[BriefInsight(**i) for i in brief_data["insights"]],
        ),
        alerts=[Alert(**a) for a in alerts_data],
        suggested_questions=suggested,
        popular_questions=[PopularQuestion(**q) for q in popular],
        warnings=warnings,
    )


# --- admin: data sources (spec §4, view-only slice) -------------------------


@app.get("/api/admin/data-sources", response_model=list[DataSource])
def admin_list_data_sources(me: dict = Depends(require_client_admin)) -> list[DataSource]:
    """Status cards for every data source configured for this client (today:
    always exactly one, PostgreSQL) -- read-only, no credentials, no manual
    sync trigger (all platform-level, spec §4.3)."""
    return [DataSource(**s) for s in data_sources.get_data_sources(me["client_id"])]


@app.post("/api/admin/data-sources/{source_id}/report-problem", response_model=ReportProblemResponse)
def admin_report_data_source_problem(
    source_id: str, me: dict = Depends(require_client_admin)
) -> ReportProblemResponse:
    """"Report a problem" (spec §4.3): opens a ticket with the source's
    current status auto-attached, logged as both an audit event (durable,
    per-org record) and a platform notification (Admin Platform sees sync
    failures across every client -- no email in the MVP)."""
    cid = me["client_id"]
    sources = {s["id"]: s for s in data_sources.get_data_sources(cid)}
    source = sources.get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="unknown data source")

    event = _audit(
        "admin_data_source_problem_reported", client_id=cid, actor=me,
        action="data_source.problem_reported",
        target_type="data_source", target_id=source_id, target_label=source["display_name"],
        after={"status": source["status"], "data_age_days": source["data_age_days"]},
    )
    log_event(
        logger, "platform_notification", client_id=cid, kind="data_source_problem",
        source_id=source_id, source_type=source["type"], status=source["status"],
    )
    return ReportProblemResponse(reported=True, source_id=source_id, audit_event_id=event["id"])


@app.get("/api/overview", response_model=Overview)
def overview(
    client_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> Overview:
    """Headline KPIs for the home dashboard. Computed from the saved report
    library (no agent call), so it's fast enough to run on page load.

    `start`/`end` are month keys ("2026-05"); omit both for the default (the
    latest complete month). An unknown or inverted range resolves back to the
    default rather than erroring. KPIs that can't be computed for this client
    are omitted, never an error.
    """
    cid = _resolve_client(client_id)
    scope_id = current_org_user(cid)["data_scope"]
    cfg, _warnings = _effective_home_config(cid)
    # The saved reports resolve the active client via the same ContextVar
    # override the chat endpoints use, so caches stay keyed per tenant.
    client_registry.set_active_client_override(cid)
    try:
        data = build_overview(start=start, end=end, scope_id=scope_id, config=cfg)
    finally:
        client_registry.set_active_client_override(None)
    return Overview(
        client_id=cid,
        kpis=[Kpi(**k) for k in data["kpis"]],
        as_of=datetime.now(timezone.utc).isoformat(),
        start=data["start"],
        end=data["end"],
        available_months=data["available_months"],
    )


@app.get("/api/brief", response_model=DailyBriefResponse)
def brief(client_id: str | None = None) -> DailyBriefResponse:
    """The home dashboard's Daily Brief: two layers. `pulse` (revenue/orders/
    conversion for yesterday, with a 14-day spark) ALWAYS has content and is
    what makes the brief change every day; `insights` is up to 3 ranked
    attention cards, gated by their own thresholds -- an empty list is a
    normal, quiet-day response, not an error. Deterministic and agent-free,
    so it runs on page load. `as_of` is the dataset's own last complete day,
    not a request timestamp.
    """
    cid = _resolve_client(client_id)
    scope_id = current_org_user(cid)["data_scope"]
    cfg, _warnings = _effective_home_config(cid)
    # Same ContextVar override as /api/overview, so the saved reports resolve
    # this tenant and its caches stay keyed per client.
    client_registry.set_active_client_override(cid)
    try:
        # build_daily_brief's cache is per-(CLIENT, sensitivity), not per-
        # requester, so the scope filter runs AFTER the (possibly shared)
        # cached result comes back -- never baked into the cache itself.
        data = daily_brief_filter_for_scope(
            build_daily_brief(sensitivity=cfg["daily_brief"]["sensitivity"]), scope_id
        )
    finally:
        client_registry.set_active_client_override(None)
    # Layer visibility toggles: cheap request-time filters, not part of the
    # cached computation (unlike sensitivity, which changes what candidates
    # exist at all -- see build_daily_brief's docstring).
    if not cfg["daily_brief"]["pulse_enabled"]:
        data = {**data, "pulse": []}
    if not cfg["daily_brief"]["insights_enabled"]:
        data = {**data, "insights": []}
    return DailyBriefResponse(
        client_id=cid,
        as_of=data["as_of"],
        pulse=[PulseMetric(**p) for p in data["pulse"]],
        insights=[BriefInsight(**i) for i in data["insights"]],
    )


@app.get("/api/alerts", response_model=list[Alert])
def alerts(client_id: str | None = None) -> list[Alert]:
    cid = _resolve_client(client_id)
    scope_id = current_org_user(cid)["data_scope"]
    cfg, _warnings = _effective_home_config(cid)
    # evaluate_all_alerts's raw-readings cache is per-CLIENT too (config-
    # independent by design -- see its docstring), same reasoning as the
    # brief above, filter_for_scope runs on the cached (unfiltered) result.
    raw = alerts_engine.evaluate_all_alerts(client_id=cid, alert_config=cfg["alerts"])
    return [Alert(**a) for a in alerts_engine.filter_for_scope(raw, scope_id)]


@app.get("/api/popular-questions", response_model=list[PopularQuestion])
def popular_questions(client_id: str | None = None) -> list[PopularQuestion]:
    """Most-asked questions for this client, aggregated across every
    conversation (no login yet, so this is server-wide, not per-person)."""
    cid = _resolve_client(client_id)
    scope_id = current_org_user(cid)["data_scope"]
    cfg, _warnings = _effective_home_config(cid)
    if not cfg["suggested_questions"]["trending_enabled"]:
        return []
    questions = conversation_store.top_questions(cid)
    if scope_id != "full":
        metrics = load_semantic_layer(cid)
        questions = [q for q in questions if not _question_is_blocked(q["question"], metrics, scope_id)]
    return [PopularQuestion(**q) for q in questions]


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
