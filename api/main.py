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

import asyncio
import csv
import io
import json
import os
import queue
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse

# The backend modules (db, wiring, client_registry, ...) resolve via the
# editable install (pip install -e ., see pyproject.toml) -- no sys.path hack.
from sema_core import client_registry
from sema_core.agent import agent
from sema_core.agent.agent import generate_title
from sema_core.agent.prompts import (
    _question_script_hint,
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
from sema_core.retention_store import RetentionRunStore
from sema_core.query_limit_store import QueryLimitStore, today as query_limit_today
from sema_core.export_limit_store import ExportLimitStore, current_hour as export_limit_current_hour
from sema_core.agent.tools import AgentTools
from sema_core.agent.safety import SQLSafetyError, strip_limit, validate_and_prepare
from sema_core import data_sources
from sema_core import connector_catalog
from sema_core import db_probe
from sema_core import file_upload
from sema_core.secrets import encrypt_secret, fingerprint as make_fingerprint, SecretsKeyNotConfigured
from sema_core.client_connections_store import ClientConnectionsStore, ConnectionNotFoundError
from sema_core.source_requests_store import SourceRequestsStore
from sema_core.uploads_store import UploadsStore, UploadNotFoundError
from sema_core import alert_templates
from sema_core import org_alerts
from sema_core.org_alerts_store import OrgAlertLimitExceededError, OrgAlertNotFoundError, OrgAlertsStore
from sema_core.feedback_store import InvalidRatingError, TurnFeedbackStore
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
from sema_core.db import check_connection, run_query, stream_sql_readonly
from sema_core.obs import get_logger, log_admin_event, log_event, new_request_id
from sema_core.audit_store import AuditStore
from sema_core import home_config
from sema_core.home_config_store import HomeConfigNotFoundError, HomeConfigStore
from sema_core.daily_brief import build_daily_brief
from sema_core.daily_brief import filter_for_scope as daily_brief_filter_for_scope
from sema_core.overview import build_overview
from sema_core.settings import settings, validate_for_production
from sema_core.wiring import get_response

from api.models import (
    AdminInviteRequest,
    AdminUser,
    AdminUserList,
    AdminUserUpdate,
    AlertCatalogItem,
    AlertMetricCatalogItem,
    AlertRuleInfo,
    AlertTemplateCatalogItem,
    AlertTestRequest,
    AlertTestResult,
    CreateAlertRequest,
    UpdateAlertRequest,
    AuditEvent,
    AuditEventList,
    CurrencyInfo,
    DataSource,
    ReportProblemResponse,
    ConnectorCatalogItem,
    TestConnectionRequest,
    TestConnectionResponse,
    CreateConnectionRequest,
    ClientConnectionInfo,
    SourceRequestCreate,
    SourceRequestInfo,
    InterestRequest,
    InterestResponse,
    UploadColumnPlan,
    UploadInfo,
    SheetsInfo,
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
    FeedbackRequest,
    TableExportRequest,
    TurnFeedback,
    ConversationSummary,
    ConversationUpdate,
    Health,
    HealthzResponse,
    Kpi,
    Overview,
    PopularQuestion,
    SchemaResponse,
    ThreadDetail,
    ThreadSummary,
)
from api.serialize import build_schema, to_chat_response

logger = get_logger("api")

# Fail-fast startup validation (deployment_prep_prompt.md item 2): a
# misconfigured production deploy should crash on boot with every problem
# listed at once, not serve traffic with auth silently disabled or a
# hard-coded dev DB password. Never runs under SEMA_ENV=dev (every test and
# local docker-compose run), so this can never abort an existing test suite.
if settings.env == "production":
    _startup_problems = validate_for_production(settings)
    if _startup_problems:
        raise RuntimeError(
            "SEMA_ENV=production but startup checks failed:\n- "
            + "\n- ".join(_startup_problems)
        )
    # Loud, impossible-to-miss reminder: there is no real authentication yet
    # (sema_core.current_user.current_identity() always resolves to the same
    # hard-coded mock identity, backing every /api/admin/* route and every
    # data-scoped route). Deliberately left ACTIVE in production for now
    # (auth_login_prompt.md Parts A+B are blocked on hosting existing at all,
    # and this deployment is meant to be usable before that lands) -- so this
    # warning is the safeguard against that risk being silently forgotten,
    # not a substitute for shipping real auth as soon as it's unblocked.
    logger.warning(
        "SEMA_ENV=production with NO real authentication: every admin and "
        "data-scoped route resolves identity via a hard-coded mock user "
        "(sema_core.current_user). Treat this deployment as a controlled/"
        "private pilot until auth_login_prompt.md Parts A+B ship."
    )

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

# Retention-sweep run tracking (org_settings_gapfix_prompt.md) -- same SQLite
# metadata DB, separate table. Module-level singleton; tests monkeypatch this
# attribute with an isolated store pointed at a temp file, same as the stores
# above.
retention_run_store = RetentionRunStore(settings.conversation_db_path)

# Data-sources add-flow stores (data_sources_add_prompt.md) -- same SQLite
# metadata DB, separate tables. Module-level singletons; tests monkeypatch
# these attributes with isolated stores pointed at temp files, same as the
# stores above.
client_connections_store = ClientConnectionsStore(settings.conversation_db_path)
source_requests_store = SourceRequestsStore(settings.conversation_db_path)
uploads_store = UploadsStore(settings.conversation_db_path)

# Org-owned template-based alerts (alert_templates_prompt.md) -- same SQLite
# metadata DB, separate tables. Module-level singleton; tests monkeypatch this
# attribute with an isolated store pointed at a temp file, same as the stores
# above.
org_alerts_store = OrgAlertsStore(settings.conversation_db_path)

# Per-answer thumbs up/down feedback (answer_feedback_prompt.md) -- same
# SQLite metadata DB, separate table. Module-level singleton; tests
# monkeypatch this attribute with an isolated store pointed at a temp file,
# same as the stores above.
feedback_store = TurnFeedbackStore(settings.conversation_db_path)

# Per-user daily LLM query soft cap (backend_qa_prompt.md item 5) -- same
# SQLite metadata DB, separate table. Module-level singleton; tests
# monkeypatch this attribute with an isolated store pointed at a temp file,
# same as the stores above.
query_limit_store = QueryLimitStore(settings.conversation_db_path)

# Per-user hourly CSV-export rate limit (full_data_export_prompt.md item 5) --
# same SQLite metadata DB, separate table/clock from query_limit_store above
# (an export never calls the LLM, so it's a different kind of cost on a
# different reset boundary). Module-level singleton; tests monkeypatch this
# attribute with an isolated store pointed at a temp file, same as the
# stores above.
export_limit_store = ExportLimitStore(settings.conversation_db_path)


def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    """Auth scaffold: every route requires X-API-Key matching SEMA_API_KEY.

    Empty SEMA_API_KEY = auth disabled (local dev). Structured as a FastAPI
    dependency so swapping in real auth (JWT, per-tenant keys) later means
    replacing this one function. compare_digest avoids timing side-channels.

    /healthz is exempt: it's the infra platform's own liveness/readiness probe
    (Railway/Render, etc.), which cannot be expected to send an API key, and
    deployment_prep_prompt.md explicitly specs it as "no auth". This is the
    ONLY app-level dependency (applied to every route below via `FastAPI(
    dependencies=...)`), so excluding one path has to happen inside it rather
    than via a per-route override.
    """
    if request.url.path == "/healthz":
        return
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


_RETENTION_INITIAL_DELAY_S = 60
_RETENTION_INTERVAL_S = 24 * 3600


async def _retention_loop() -> None:
    """The scheduled daily sweep (org_settings_gapfix_prompt.md Part 1): runs
    once ~60s after boot (so startup itself is never blocked waiting on it),
    then every 24h thereafter. One iteration's failure is logged and never
    kills the loop -- a bad day's sweep must not silently cancel every future
    day's sweep too. The actual sweep runs in a thread (asyncio.to_thread):
    it's synchronous DB work (psycopg2 + sqlite3), and would otherwise block
    the whole event loop -- every concurrent chat request -- for its duration.
    References the module-level store singletons by NAME (not captured as
    default args) so a test that monkeypatches e.g. `main.conversation_store`
    is still honored if this loop ever runs under test.
    """
    await asyncio.sleep(_RETENTION_INITIAL_DELAY_S)
    while True:
        try:
            await asyncio.to_thread(
                retention.run_all_clients_sweep_tracked,
                conversation_store, org_settings_store, retention_run_store, audit_store,
            )
        except Exception:
            logger.exception("retention loop iteration failed")
        await asyncio.sleep(_RETENTION_INTERVAL_S)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Starts the retention loop as a background task for the life of the
    process. Disableable via SEMA_RETENTION_ENABLED for tests/local runs that
    don't want a scheduled task running against their DB -- FastAPI's
    TestClient only invokes this at all when used as a context manager
    (`with TestClient(app) as client`), which none of this app's tests do, so
    existing tests are unaffected either way."""
    task = asyncio.create_task(_retention_loop()) if settings.retention_enabled else None
    yield
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="SEMA API",
    version="0.1.0",
    dependencies=[Depends(require_api_key)],  # applied to ALL routes
    lifespan=lifespan,
)

# CORS: SEMA_CORS_ORIGINS is the explicit allowlist (defaults to the local
# Vite dev server); SEMA_PUBLIC_URL -- this deployment's own externally-
# reachable origin -- is folded in automatically so a deployer doesn't have
# to repeat the same value in two env vars. `dict.fromkeys` dedupes while
# preserving order (a plain set would make the allowlist's order test-
# unstable and log output non-deterministic).
_cors_origins = list(
    dict.fromkeys(settings.cors_origins + ([settings.public_url] if settings.public_url else []))
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Response headers browsers hide from cross-origin `fetch()`/XHR JS
    # unless explicitly exposed here (the CORS-safelisted set is Content-
    # Type/Content-Length/etc, NOT Content-Disposition or any X- header) --
    # the export endpoint's filename (Content-Disposition) and >250K-rows
    # signal (X-Export-*) would otherwise read as null/missing on every
    # cross-origin call (dev: :5173 -> :8000), silently degrading to the
    # generic fallback filename with no error.
    expose_headers=["Content-Disposition", "X-Export-Ceiling-Hit", "X-Export-Row-Ceiling"],
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


_QUOTA_MESSAGE = {
    "Hebrew": "הגעת למכסת השאלות היומית שלך. פני/ה למנהל/ת המערכת שלך להעלאת המכסה.",
    "English": "You've reached your daily question limit. Contact your admin to raise it.",
}


def _check_daily_query_limit(cid: str, me: dict, question: str) -> dict | None:
    """Cost guardrail (backend_qa_prompt.md item 5): a generous per-(client,
    org_user) soft cap on chat calls per UTC calendar day. Returns a plain
    response dict (same contract as sema_core.wiring.get_response) when the
    cap is hit -- callers do `_check_daily_query_limit(...) or get_response(
    ...)`, so a blocked question flows through the EXACT SAME persistence/
    title-generation/streaming code every other answer does, no special
    casing needed at either call site. Returns None (fall through to a real
    answer) when under the cap, the cap is disabled (limit <= 0), or the
    identity doesn't resolve to a real org_user -- there's no one to count
    against (same "unscoped = unrestricted" rule current_org_user's own
    _UNSCOPED_USER fallback already applies everywhere else).
    """
    limit = settings.daily_query_limit
    if limit <= 0 or me.get("id") is None:
        return None
    day = query_limit_today()
    count = query_limit_store.increment_and_get(cid, me["id"], day)
    if count <= limit:
        return None
    # Over the cap -- log the audit event ONCE per user per day, not once
    # per over-the-cap request (a capped user will keep asking).
    if query_limit_store.mark_notified_once(cid, me["id"], day):
        _audit(
            "usage_limit_reached", client_id=cid, actor=me, action="usage.limit_reached",
            target_type="query_limit", target_label=f"{limit}/day",
            after={"count": count, "limit": limit, "day": day},
        )
    lang = _question_script_hint(question) or "English"
    return agent.quota_exceeded_response(_QUOTA_MESSAGE[lang])


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


def _client_static_suggested_questions(client_cfg: dict, lang: str) -> list[str]:
    """The default (non-admin-overridden) suggested-question list for a
    client (home_ask_bar_top_prompt.md's cycling placeholder is one of its
    consumers, alongside the home screen's discovery cards). config/clients.
    yaml's `suggested_questions` is the language-agnostic default;
    `suggested_questions_he` is an optional Hebrew variant, picked when the
    org's chrome language is Hebrew (org_settings.default_language) -- the
    SAME org-language source every other piece of chrome copy already reads,
    per home_hebrew_polish_prompt.md item 4. Falls back to the English list
    when no Hebrew variant is configured for this client, so an
    unconfigured client degrades exactly like before this existed."""
    if lang == "he":
        he_list = client_cfg.get("suggested_questions_he")
        if he_list:
            return he_list
    return client_cfg.get("suggested_questions", [])


def _client_model(c: dict) -> Client:
    cfg, _warnings = _effective_home_config(c["id"])
    override = cfg["suggested_questions"]["questions"]
    lang = org_settings_store.get_or_create(c["id"], default_name=c.get("label", c["id"]))["default_language"]
    return Client(
        id=c["id"],
        label=c["label"],
        semantic_dir=c.get("semantic_dir", ""),
        # An empty override means "nothing published yet" -- keep the
        # client's static config/clients.yaml list unchanged.
        suggested_questions=override or _client_static_suggested_questions(c, lang),
    )


@app.get("/healthz", response_model=HealthzResponse, include_in_schema=False)
def healthz() -> HealthzResponse:
    """Platform liveness/readiness probe target (Railway/Render/etc.) --
    root-level path (not /api), no auth (see require_api_key's exemption),
    minimal payload. `version` comes from SEMA_VERSION (a deploy-time env var
    the platform/CI can set to a commit SHA or tag); "unknown" when unset,
    which is the expected value for local dev."""
    cid = client_registry.DEFAULT_CLIENT_ID
    return HealthzResponse(
        status="ok",
        db_connected=check_connection(cid),
        version=os.environ.get("SEMA_VERSION", "unknown"),
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
        language=row["default_language"],
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
    me = current_org_user(cid)
    scope_id = me["data_scope"]
    # Point the whole agent run (db + semantic) at this request's client.
    client_registry.set_active_client_override(cid)
    started = time.perf_counter()
    try:
        resp = _check_daily_query_limit(cid, me, req.question) or get_response(
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
    me = current_org_user(cid)
    scope_id = me["data_scope"]

    def worker(q: "queue.Queue") -> None:
        # The ContextVar override is set INSIDE this worker thread -- a new
        # OS thread does not inherit the caller's contextvars context, so
        # setting it here (not in the request thread) is what makes this
        # thread's DB/semantic-layer calls resolve to the right tenant.
        client_registry.set_active_client_override(cid)
        started = time.perf_counter()
        try:
            resp = _check_daily_query_limit(cid, me, req.question) or get_response(
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

    feedback_by_turn = feedback_store.get_for_conversation(conversation_id)
    messages: list[ConversationMessage] = []
    turn_index = -1
    for m in raw:
        if m["role"] == "user":
            turn_index += 1
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
        feedback = None
        if m["role"] == "assistant" and turn_index in feedback_by_turn:
            row = feedback_by_turn[turn_index]
            feedback = TurnFeedback(rating=row["rating"], comment=row["comment"])
        messages.append(
            ConversationMessage(role=m["role"], content=m["content"], payload=payload, feedback=feedback)
        )

    return ConversationDetail(
        id=meta["id"],
        title=meta["title"],
        pinned=meta["pinned"],
        archived=meta["archived"],
        messages=messages,
    )


@app.post("/api/feedback", response_model=TurnFeedback | None)
def submit_feedback(req: FeedbackRequest) -> TurnFeedback | None:
    """Rate (or clear the rating on) one answer. Not admin-gated -- any
    resolvable identity (viewer/analyst/admin/unscoped) may give feedback,
    same tier as the chat endpoints themselves. `rating: null` clears an
    existing rating and returns null; otherwise upserts and returns the
    saved feedback."""
    cid = _resolve_client(req.client_id)
    _conversation_or_404(req.conversation_id, cid)
    me = current_org_user(cid)

    if req.rating is None:
        feedback_store.clear(req.conversation_id, req.turn_index)
        return None

    try:
        row = feedback_store.set(
            req.conversation_id, cid, req.turn_index, req.rating, req.comment, me["id"]
        )
    except InvalidRatingError:
        raise HTTPException(status_code=422, detail="invalid rating") from None
    return TurnFeedback(rating=row["rating"], comment=row["comment"])


_EXPORT_FILENAME_UNSAFE_RE = re.compile(r"[^\w\s-]", re.UNICODE)


def _export_filename(question: str) -> str:
    """`<slugified question>_<date>.csv` -- same spirit as the client-side
    Download CSV's own sanitization (DataTable.tsx's exportCsv), extended to
    keep Hebrew (Python's `\\w` is already Unicode-aware, so this keeps any
    script, not just Latin)."""
    slug = _EXPORT_FILENAME_UNSAFE_RE.sub("", question or "").strip()
    slug = re.sub(r"\s+", "_", slug)[:60].strip("_") or "sema-export"
    date = datetime.now(timezone.utc).date().isoformat()
    return f"{slug}_{date}.csv"


def _csv_row(fields: list) -> str:
    buf = io.StringIO()
    csv.writer(buf).writerow(fields)
    return buf.getvalue()


@app.post("/api/exports/table")
def export_table(req: TableExportRequest) -> StreamingResponse:
    """Full-data CSV export (full_data_export_prompt.md): re-runs the query
    bound to one turn's table WITHOUT the on-screen display cap.

    By REFERENCE only -- conversation_id + turn_index resolve to the SQL the
    agent already ran and persisted on that turn's Table.sql; the client
    never sends SQL (that would bypass the agent's whole safety path). Every
    guardrail the original answer went through runs again here: the
    requester's CURRENT data-access scope (which may have narrowed since the
    answer was given), the same sqlglot safety validation (single read-only
    SELECT, no system catalogs), just with a much higher row ceiling
    (SEMA_EXPORT_ROW_LIMIT) than the display cap. Streamed via a named
    server-side cursor (sema_core.db.stream_sql_readonly) so a 250K-row
    export never sits fully in memory.
    """
    request_id = new_request_id()
    cid = _resolve_client(req.client_id)
    me = current_org_user(cid)

    # Rate limit: counts every export ATTEMPT (same increment-then-check
    # order as _check_daily_query_limit), a no-op for an identity with no
    # real org_user row to count against (same "unscoped = unrestricted"
    # rule the daily query cap already applies).
    limit = settings.export_hourly_limit
    if limit > 0 and me.get("id") is not None:
        hour = export_limit_current_hour()
        count = export_limit_store.increment_and_get(cid, me["id"], hour)
        if count > limit:
            if export_limit_store.mark_notified_once(cid, me["id"], hour):
                _audit(
                    "export_rate_limited", client_id=cid, actor=me, action="export.rate_limited",
                    target_type="export_limit", target_label=f"{limit}/hour",
                    after={"count": count, "limit": limit, "hour": hour},
                )
            raise HTTPException(status_code=429, detail="Export rate limit reached. Try again later.")

    # Resolve conversation_id + turn_index -> the table bound to that turn,
    # the SAME "count user turns" walk get_conversation uses.
    try:
        raw = conversation_store.get_messages(req.conversation_id, client_id=cid)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="unknown conversation_id") from None

    turn_index = -1
    table = None
    question_text = ""
    for m in raw:
        if m["role"] == "user":
            turn_index += 1
            if turn_index == req.turn_index:
                question_text = m["content"]
        elif m["role"] == "assistant" and turn_index == req.turn_index and m.get("payload"):
            try:
                payload = ChatResponse.model_validate_json(m["payload"])
            except Exception:
                payload = None
            table = payload.table if payload is not None else None
            break

    if table is None or not table.sql:
        raise HTTPException(status_code=404, detail="no exportable table for this turn")

    # Point active-client-scoped lookups (the scope check below) at this
    # request's client -- reset in `finally` before returning, since the
    # StreamingResponse body runs AFTER this function returns and must not
    # depend on this override (stream_sql_readonly gets `client_id=cid`
    # explicitly, precisely so it doesn't need to).
    client_registry.set_active_client_override(cid)
    try:
        blocked = AgentTools(scope_id=me["data_scope"]).check_scope(table.sql, metrics_used=None)
        if blocked is not None:
            _audit(
                "export_denied", client_id=cid, actor=me, action="data.export_denied",
                target_type="conversation", target_id=req.conversation_id,
                after={"turn_index": req.turn_index, "reason": blocked["reason"]},
            )
            raise HTTPException(status_code=403, detail=blocked["reason"])

        try:
            export_sql = validate_and_prepare(strip_limit(table.sql), max_rows=settings.export_row_limit)
        except SQLSafetyError:
            raise HTTPException(
                status_code=400, detail="This result can no longer be exported safely."
            ) from None
    finally:
        client_registry.set_active_client_override(None)

    filename = _export_filename(question_text)
    # Known from the answer's own COUNT (agent/response.py's _true_row_count)
    # -- an approximation (the table may have changed since), but enough to
    # flag the rare ">250K rows" case per full_data_export_prompt.md item 5:
    # that's a data-pipeline job, not a chat export, so the file is still
    # delivered (capped at export_row_limit by validate_and_prepare above,
    # same mechanism as the display cap), plus a signal the client can show
    # as a note rather than silently implying the file is the whole result.
    ceiling_hit = bool(table.total_rows and table.total_rows > settings.export_row_limit)

    def csv_stream():
        row_count = 0
        wrote_header = False
        for columns, rows in stream_sql_readonly(export_sql, client_id=cid):
            if not wrote_header:
                yield _csv_row(columns)
                wrote_header = True
            for row in rows:
                yield _csv_row(row)
                row_count += 1
        log_event(
            logger, "api_export_table", request_id=request_id, client_id=cid,
            conversation_id=req.conversation_id, turn_index=req.turn_index,
            rows=row_count, ceiling_hit=ceiling_hit,
        )
        _audit(
            "export_completed", client_id=cid, actor=me, action="data.exported",
            target_type="conversation", target_id=req.conversation_id,
            after={"turn_index": req.turn_index, "rows": row_count, "ceiling_hit": ceiling_hit},
        )

    ascii_fallback = "sema-export.csv"
    return StreamingResponse(
        csv_stream(),
        media_type="text/csv",
        headers={
            "X-Export-Ceiling-Hit": "true" if ceiling_hit else "false",
            "X-Export-Row-Ceiling": str(settings.export_row_limit),
            "Content-Disposition": (
                f'attachment; filename="{ascii_fallback}"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
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


USERS_PAGE_SIZE = 25


@app.get("/api/admin/users", response_model=AdminUserList)
def admin_list_users(
    q: str | None = None,
    role: str | None = None,
    page: int = 1,
    page_size: int = USERS_PAGE_SIZE,
    me: dict = Depends(require_client_admin),
) -> AdminUserList:
    """This org's users, with optional search (name/email) and role filter,
    combined server-side with paging (25/page by default -- denser rows than
    the audit log's 50, spec §8; `page_size` is overridable for callers that
    want the whole roster in one call, e.g. the audit log's actor-filter
    dropdown). member_count/pending_count are of the whole org, not the
    filtered view, so the subtitle stays stable while searching; total is the
    FILTERED count, for the pager."""
    cid = me["client_id"]
    page = max(1, page)
    rows = org_user_store.list_users(cid, q=q, role=role, page=page, page_size=page_size)
    total = org_user_store.count_users(cid, q=q, role=role)
    everyone = org_user_store.list_users(cid)
    pending = sum(1 for u in everyone if u["status"] == "invited")
    return AdminUserList(
        users=[_admin_user(r, me) for r in rows],
        member_count=len(everyone) - pending,
        pending_count=pending,
        active_admin_count=org_user_store.count_active_admins(cid),
        total=total,
        page=page,
        page_size=page_size,
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


def _diff_fields(before: dict | None, after: dict | None) -> tuple[dict, dict]:
    """Only the keys that actually changed between two semantic-item dicts --
    "before/after limited to the changed fields" (org_settings_gapfix_prompt.md
    Part 3), same trust-panel-friendly diffing idea as org-settings' own
    per-field audit, just applied to a whole nested item instead of one
    primitive. `None` on either side (no prior draft / discarded entirely)
    means "everything in the other side is the whole story"."""
    if before is None or after is None:
        return (before or {}), (after or {})
    keys = set(before) | set(after)
    changed = {k for k in keys if before.get(k) != after.get(k)}
    return {k: before.get(k) for k in changed}, {k: after.get(k) for k in changed}


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
    existing_draft = semantic_store.get_draft(cid, section, item_key)
    semantic_store.save_draft(cid, section, item_key, req.data, action, author=_semantic_author(me))
    before, after = _diff_fields(existing_draft["data"] if existing_draft else None, req.data)
    _audit(
        "admin_semantic_draft_saved", client_id=cid, actor=me,
        action="semantic.draft_archived" if action == "deprecate" else "semantic.draft_saved",
        target_type=section, target_id=item_key, target_label=item_key,
        before=before, after=after,
    )
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
    existing_draft = semantic_store.get_draft(cid, section, item_key)
    if existing_draft is not None:
        semantic_store.discard_draft(cid, section, item_key)
        _audit(
            "admin_semantic_draft_discarded", client_id=cid, actor=me, action="semantic.draft_discarded",
            target_type=section, target_id=item_key, target_label=item_key,
            before=existing_draft["data"], after=None,
        )
    else:
        semantic_store.save_draft(cid, section, item_key, {}, action="deprecate", author=_semantic_author(me))
        _audit(
            "admin_semantic_draft_archived", client_id=cid, actor=me, action="semantic.draft_archived",
            target_type=section, target_id=item_key, target_label=item_key,
            before=None, after={"action": "deprecate"},
        )
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


def _org_settings_response(row: dict, cid: str, conflict: bool) -> OrgSettings:
    """Attach this client's last retention-sweep run (if any) to the
    org-settings payload -- one embedded read rather than a separate
    endpoint (org_settings_gapfix_prompt.md Part 1 explicitly allows either)."""
    run = retention_run_store.get(cid)
    return OrgSettings(
        **row, conflict=conflict,
        last_retention_run_at=run["last_run_at"] if run else None,
        last_retention_deleted_count=run["deleted_count"] if run else None,
        last_retention_status=run["status"] if run else None,
        last_retention_error=run["error"] if run else None,
    )


@app.get("/api/admin/org-settings", response_model=OrgSettings)
def admin_get_org_settings(me: dict = Depends(require_client_admin)) -> OrgSettings:
    cid = me["client_id"]
    label = client_registry.get_client_by_id(cid).get("label", cid)
    row = org_settings_store.get_or_create(cid, default_name=label)
    return _org_settings_response(row, cid, conflict=False)


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
        return _org_settings_response(before, cid, conflict=False)
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
    return _org_settings_response(updated, cid, conflict=conflict)


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
    return _org_settings_response(updated, cid, conflict=False)


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


# --- admin: template-based alert builder (alert_templates_prompt.md) -------


@app.get("/api/admin/alerts/templates", response_model=list[AlertTemplateCatalogItem])
def admin_alert_templates(me: dict = Depends(require_client_admin)) -> list[AlertTemplateCatalogItem]:
    """The 4 template types + their param keys -- server-driven so the
    builder's radio cards never hardcode what only sema_core.alert_templates
    should own, same pattern as the data-source connector catalog."""
    return [
        AlertTemplateCatalogItem(template=key, **{k: v for k, v in d.items() if k != "params"}, params=d["params"])
        for key, d in alert_templates.TEMPLATE_DEFS.items()
    ]


@app.get("/api/admin/alerts/metrics", response_model=list[AlertMetricCatalogItem])
def admin_alert_metrics(me: dict = Depends(require_client_admin)) -> list[AlertMetricCatalogItem]:
    """The fixed KPI_CATALOG metrics a template-based alert may target."""
    from sema_core.home_config import KPI_CATALOG

    return [AlertMetricCatalogItem(metric=m, label=KPI_CATALOG[m]["label"]) for m in alert_templates.SUPPORTED_METRICS]


def _alert_rule_info(row: dict, *, system: bool) -> AlertRuleInfo:
    from sema_core.home_config import KPI_CATALOG

    return AlertRuleInfo(
        id=row["id"],
        name=row["name"],
        metric=row["metric"],
        metric_label=KPI_CATALOG[row["metric"]]["label"],
        template=row["template"],
        params=row["params"],
        severity=row["severity"],
        enabled=row["enabled"],
        system=system,
        disabled_reason=row.get("disabled_reason"),
        summary_en=org_alerts.summary_sentence(row["metric"], row["template"], row["params"]),
        summary_he=org_alerts.summary_sentence_he(row["metric"], row["template"], row["params"]),
        created_by=row.get("created_by"),
        updated_at=row["updated_at"],
    )


def _system_alert_as_rule(cat_item: dict) -> AlertRuleInfo:
    """A YAML/system alert has no template/params -- surfaced read-only in
    the unified list with the same fields the OLD catalog already exposed
    (spec accept criterion: 'visibly System'), never editable/deletable."""
    return AlertRuleInfo(
        id=cat_item["id"], name=cat_item["label"], metric=cat_item["id"], metric_label=cat_item["metric_label"],
        template="system", params={}, severity=cat_item["severity"], enabled=True, system=True,
        disabled_reason=None, summary_en=cat_item["label"], summary_he=cat_item["label"],
        created_by=None, updated_at="",
    )


@app.get("/api/admin/alerts", response_model=list[AlertRuleInfo])
def admin_list_alerts(me: dict = Depends(require_client_admin)) -> list[AlertRuleInfo]:
    """The unified alert list: org-owned (editable) + system/YAML-owned
    (view-only) alerts side by side, so an admin sees "everything that can
    fire" in one place even though only org alerts came through this
    builder (spec accept criterion: both kinds visible, one engine path)."""
    cid = me["client_id"]
    org_rows = [_alert_rule_info(r, system=False) for r in org_alerts.list_effective(cid, org_alerts_store)]
    system_rows = [_system_alert_as_rule(a) for a in alerts_engine.catalog(cid)]
    return org_rows + system_rows


@app.post("/api/admin/alerts/test", response_model=AlertTestResult)
def admin_test_alert(req: AlertTestRequest, me: dict = Depends(require_client_admin)) -> AlertTestResult:
    """Dry-run: how many times would this candidate alert have fired in the
    last 90 days. REQUIRED before create/enable -- create/PATCH re-run this
    exact check server-side rather than trusting a client-supplied token, so
    there's no stale-token replay risk."""
    try:
        alert_templates.validate_params(req.template, req.params)
    except alert_templates.AlertTemplateError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    result = alert_templates.dry_run(me["client_id"], req.metric, req.template, req.params)
    return AlertTestResult(**result)


def _require_valid_alert_target(metric: str, template: str, params: dict) -> None:
    if metric not in alert_templates.SUPPORTED_METRICS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported metric '{metric}'. Choose one of: {', '.join(alert_templates.SUPPORTED_METRICS)}.",
        )
    try:
        alert_templates.validate_params(template, params)
    except alert_templates.AlertTemplateError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


def _require_passing_test(client_id: str, metric: str, template: str, params: dict) -> None:
    result = alert_templates.dry_run(client_id, metric, template, params)
    if not result["ok"]:
        raise HTTPException(status_code=422, detail=result.get("error") or "This alert could not be tested.")


@app.post("/api/admin/alerts", response_model=AlertRuleInfo, status_code=201)
def admin_create_alert(req: CreateAlertRequest, me: dict = Depends(require_client_admin)) -> AlertRuleInfo:
    cid = me["client_id"]
    _require_valid_alert_target(req.metric, req.template, req.params)
    _require_passing_test(cid, req.metric, req.template, req.params)
    try:
        row = org_alerts_store.create(
            cid, name=req.name, metric=req.metric, template=req.template, params=req.params,
            severity=req.severity, created_by=_semantic_author(me),
        )
    except OrgAlertLimitExceededError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except Exception as exc:
        if "UNIQUE" in str(exc):
            raise HTTPException(status_code=409, detail=f'An alert named "{req.name}" already exists.') from None
        raise
    _audit(
        "admin_alert_created", client_id=cid, actor=me, action="alert.created",
        target_type="alert", target_id=row["id"], target_label=row["name"],
        after={"metric": row["metric"], "template": row["template"], "params": row["params"], "severity": row["severity"]},
    )
    return _alert_rule_info(row, system=False)


@app.patch("/api/admin/alerts/{alert_id}", response_model=AlertRuleInfo)
def admin_update_alert(alert_id: str, req: UpdateAlertRequest, me: dict = Depends(require_client_admin)) -> AlertRuleInfo:
    cid = me["client_id"]
    before = org_alerts_store.get(cid, alert_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Alert not found.")

    patch = req.model_dump(exclude_unset=True)
    rule_changed = any(k in patch for k in ("metric", "template", "params"))
    if rule_changed:
        metric = patch.get("metric", before["metric"])
        template = patch.get("template", before["template"])
        params = patch.get("params", before["params"])
        _require_valid_alert_target(metric, template, params)
        _require_passing_test(cid, metric, template, params)

    try:
        row = org_alerts_store.update(cid, alert_id, patch)
    except OrgAlertLimitExceededError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except OrgAlertNotFoundError:
        raise HTTPException(status_code=404, detail="Alert not found.") from None

    before_diff, after_diff = _diff_fields(before, row)
    action = "alert.updated" if rule_changed or "name" in patch or "severity" in patch else "alert.toggled"
    _audit(
        "admin_alert_updated", client_id=cid, actor=me, action=action,
        target_type="alert", target_id=row["id"], target_label=row["name"],
        before=before_diff, after=after_diff,
    )
    return _alert_rule_info(row, system=False)


@app.delete("/api/admin/alerts/{alert_id}", status_code=204)
def admin_delete_alert(alert_id: str, me: dict = Depends(require_client_admin)) -> None:
    cid = me["client_id"]
    row = org_alerts_store.get(cid, alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    org_alerts_store.delete(cid, alert_id)
    _audit(
        "admin_alert_deleted", client_id=cid, actor=me, action="alert.deleted",
        target_type="alert", target_id=alert_id, target_label=row["name"],
    )


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
        org_readings = org_alerts.readings_for_alerts_engine(cid, org_alerts_store)
        raw_alerts = alerts_engine.evaluate_all_alerts(
            client_id=cid, alert_config=cfg["alerts"], org_alert_readings=org_readings
        )
        alerts_data = alerts_engine.filter_for_scope(raw_alerts, scope_id)
        popular = [] if not cfg["suggested_questions"]["trending_enabled"] else conversation_store.top_questions(cid)
        if scope_id != "full" and popular:
            metrics = load_semantic_layer(cid)
            popular = [q for q in popular if not _question_is_blocked(q["question"], metrics, scope_id)]
    finally:
        client_registry.set_active_client_override(None)

    client_cfg = client_registry.get_client_by_id(cid)
    preview_lang = org_settings_store.get_or_create(cid, default_name=client_cfg.get("label", cid))["default_language"]
    suggested = cfg["suggested_questions"]["questions"] or _client_static_suggested_questions(client_cfg, preview_lang)

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


_REQUEST_STATUS_TO_CARD_STATUS = {
    "requested": "syncing", "configuring": "syncing", "testing": "syncing",
    "active": "healthy", "rejected": "error",
}


def _connection_to_card(row: dict, cid: str) -> dict:
    """Live-health a stored self-service connection into the shared
    DataSource card shape (same idea as sema_core.data_sources.source_
    health, against an arbitrary stored connection instead of this
    project's own tenant DB)."""
    try:
        password = client_connections_store.decrypted_password_for_test(cid, row["id"])
        health = db_probe.check_health(
            row["connector_type"], host=row["host"], port=row["port"], database=row["database_name"],
            username=row["username"], password=password, ssl_enabled=row["ssl_enabled"],
            primary_table=row["primary_table"], primary_date_field=row["primary_date_field"],
        )
    except Exception:
        health = {"reachable": False, "data_age_days": None}
    return {
        "id": row["id"],
        "type": row["connector_type"],
        "display_name": row["display_name"],
        "status": "healthy" if health["reachable"] else "error",
        "last_sync_at": datetime.now(timezone.utc).isoformat() if health["reachable"] else None,
        "data_age_days": health["data_age_days"],
        "primary_table": row["primary_table"],
        "primary_date_field": row["primary_date_field"],
        "origin": "connection",
        "fingerprint": row["fingerprint"],
    }


def _request_to_card(row: dict) -> dict:
    connector = connector_catalog.get_connector(row["connector_type"])
    label = row["details"].get("display_name") or (connector["label"] if connector else row["connector_type"])
    return {
        "id": row["id"],
        "type": row["connector_type"],
        "display_name": label,
        "status": _REQUEST_STATUS_TO_CARD_STATUS.get(row["status"], "syncing"),
        "origin": "request",
        "progress_step": row["status"],
    }


def _upload_to_card(row: dict) -> dict:
    return {
        "id": row["id"],
        "type": "csv",
        "display_name": row["original_filename"],
        "status": "healthy",
        "last_sync_at": row["updated_at"],
        "primary_table": row["table_name"],
        "origin": "upload",
    }


@app.get("/api/admin/data-sources", response_model=list[DataSource])
def admin_list_data_sources(me: dict = Depends(require_client_admin)) -> list[DataSource]:
    """Status cards for every data source configured for this client: the
    Phase 4 static config source(s), PLUS every self-service connection,
    tracked request, and upload this client has added since (spec §4.4
    v1.6) -- one unified list, no parallel UI path."""
    cid = me["client_id"]
    cards = [DataSource(**s) for s in data_sources.get_data_sources(cid)]
    cards += [DataSource(**_connection_to_card(c, cid)) for c in client_connections_store.list_for_client(cid)]
    cards += [DataSource(**_request_to_card(r)) for r in source_requests_store.list_for_client(cid)]
    cards += [DataSource(**_upload_to_card(u)) for u in uploads_store.list_for_client(cid)]
    return cards


@app.get("/api/admin/data-sources/catalog", response_model=list[ConnectorCatalogItem])
def admin_data_sources_catalog(me: dict = Depends(require_client_admin)) -> list[ConnectorCatalogItem]:
    """The server-driven 'add a data source' gallery catalog (item 1) --
    the frontend renders this rather than hardcoding connector metadata."""
    return [ConnectorCatalogItem(**c) for c in connector_catalog.get_catalog()]


def _require_available_sql_connector(connector_type: str) -> None:
    connector = connector_catalog.get_connector(connector_type)
    if connector is None or connector["kind"] != "sql_db":
        raise HTTPException(status_code=404, detail="unknown SQL connector type")
    if connector["availability"] != "available":
        raise HTTPException(status_code=409, detail="this connector is not available yet")


@app.post("/api/admin/data-sources/test", response_model=TestConnectionResponse)
def admin_test_data_source_connection(
    req: TestConnectionRequest, me: dict = Depends(require_client_admin)
) -> TestConnectionResponse:
    """Path A step 2: connectivity + read probe + write-permission probe.
    Never persists anything -- a passed test is a PRECONDITION for storing
    credentials, not a side effect of testing them. Every failure is
    reported via a scrubbed, generic message (sema_core.db_probe._scrub)."""
    _require_available_sql_connector(req.connector_type)
    result = db_probe.test_connection(
        req.connector_type, host=req.host, port=req.port, database=req.database,
        username=req.username, password=req.password, ssl_enabled=req.ssl_enabled,
    )
    _audit(
        "admin_data_source_test", client_id=me["client_id"], actor=me,
        action="data_source.test_passed" if result["ok"] else "data_source.test_failed",
        target_type="data_source_connection", target_label=f"{req.connector_type}:{req.host}",
        after={"ok": result["ok"], "write_access": result["write_access"]},
    )
    readonly_sql = db_probe.readonly_user_sql(req.connector_type, req.database) if result["write_access"] else None
    return TestConnectionResponse(**result, readonly_user_sql=readonly_sql)


@app.post("/api/admin/data-sources/connections", response_model=ClientConnectionInfo)
def admin_create_data_source_connection(
    req: CreateConnectionRequest, me: dict = Depends(require_client_admin)
) -> ClientConnectionInfo:
    """Path A step 4: re-tests server-side (never trusts a client-reported
    'it passed') before ever encrypting and storing the credentials. If the
    (fresh) test finds write access, the explicit acknowledgment checkbox is
    required -- same all-or-nothing gate the semantic model's publish step
    already uses for a different kind of "don't trust the client" check."""
    cid = me["client_id"]
    _require_available_sql_connector(req.connector_type)
    result = db_probe.test_connection(
        req.connector_type, host=req.host, port=req.port, database=req.database,
        username=req.username, password=req.password, ssl_enabled=req.ssl_enabled,
    )
    if not result["ok"]:
        raise HTTPException(status_code=422, detail=result["error"])
    if result["write_access"] and not req.write_access_acknowledged:
        raise HTTPException(
            status_code=409,
            detail="This user has write access. Acknowledge the warning to continue, or use a read-only user.",
        )

    try:
        encrypted = encrypt_secret(req.password)
    except SecretsKeyNotConfigured as e:
        raise HTTPException(status_code=500, detail=str(e)) from None

    row = client_connections_store.create(
        cid, connector_type=req.connector_type, display_name=req.display_name, host=req.host,
        port=req.port, database_name=req.database, username=req.username, encrypted_password=encrypted,
        ssl_enabled=req.ssl_enabled, fingerprint=make_fingerprint(req.password),
        primary_table=req.primary_table, primary_date_field=req.primary_date_field,
        created_by=_semantic_author(me),
    )
    _audit(
        "admin_data_source_connected", client_id=cid, actor=me, action="data_source.connected",
        target_type="data_source_connection", target_id=row["id"], target_label=req.display_name,
        after={"connector_type": req.connector_type, "host": req.host, "database": req.database},
    )
    return ClientConnectionInfo(**row)


@app.patch("/api/admin/data-sources/connections/{connection_id}", response_model=ClientConnectionInfo)
def admin_update_data_source_connection(
    connection_id: str, req: CreateConnectionRequest, me: dict = Depends(require_client_admin)
) -> ClientConnectionInfo:
    """Editing a connection means re-entering every credential (item 3) --
    there is no partial update that could leave a stale, unverified
    credential in place. Re-tests server-side, exactly like create."""
    cid = me["client_id"]
    if client_connections_store.get(cid, connection_id) is None:
        raise HTTPException(status_code=404, detail="unknown connection")
    _require_available_sql_connector(req.connector_type)
    result = db_probe.test_connection(
        req.connector_type, host=req.host, port=req.port, database=req.database,
        username=req.username, password=req.password, ssl_enabled=req.ssl_enabled,
    )
    if not result["ok"]:
        raise HTTPException(status_code=422, detail=result["error"])
    if result["write_access"] and not req.write_access_acknowledged:
        raise HTTPException(
            status_code=409,
            detail="This user has write access. Acknowledge the warning to continue, or use a read-only user.",
        )
    try:
        encrypted = encrypt_secret(req.password)
    except SecretsKeyNotConfigured as e:
        raise HTTPException(status_code=500, detail=str(e)) from None

    row = client_connections_store.update_credentials(
        cid, connection_id, host=req.host, port=req.port, database_name=req.database,
        username=req.username, encrypted_password=encrypted, ssl_enabled=req.ssl_enabled,
        fingerprint=make_fingerprint(req.password),
    )
    _audit(
        "admin_data_source_connection_updated", client_id=cid, actor=me, action="data_source.connection_updated",
        target_type="data_source_connection", target_id=connection_id, target_label=req.display_name,
        after={"connector_type": req.connector_type, "host": req.host, "database": req.database},
    )
    return ClientConnectionInfo(**row)


# Field names that must never appear in a non-secret request form (Path B) --
# case-insensitive substring match, deliberately broad (better to reject a
# false positive and let the admin rename a field than silently accept a
# real credential into a plaintext, unencrypted JSON blob).
_CREDENTIAL_LIKE_FIELD_NAMES = (
    "password", "passwd", "secret", "token", "api_key", "apikey", "credential",
    "private_key", "access_key", "client_secret",
)


def _reject_credential_like_fields(details: dict) -> None:
    for key in details:
        lowered = key.lower()
        if any(bad in lowered for bad in _CREDENTIAL_LIKE_FIELD_NAMES):
            raise HTTPException(
                status_code=422,
                detail=f"'{key}' looks like a credential field -- this form never accepts secrets.",
            )


@app.get("/api/admin/data-sources/sheets-info", response_model=SheetsInfo)
def admin_data_sources_sheets_info(me: dict = Depends(require_client_admin)) -> SheetsInfo:
    """The Google Sheets flow's 'share this sheet with...' instructions
    (Path C item 7) -- null when no service account is configured yet."""
    return SheetsInfo(sa_email=settings.gsheets_sa_email or None)


@app.post("/api/admin/data-sources/requests", response_model=SourceRequestInfo)
def admin_create_source_request(
    req: SourceRequestCreate, me: dict = Depends(require_client_admin)
) -> SourceRequestInfo:
    """Path B (Priority/Salesforce) and the Google Sheets flow's fallback
    (Path C item 7, when no service account is configured) -- both a
    non-secret request that lands the source in a tracked 'being set up'
    state. Status transitions from here are platform-side only (no route
    in this file moves a request forward)."""
    cid = me["client_id"]
    connector = connector_catalog.get_connector(req.connector_type)
    if connector is None or connector["kind"] not in ("saas_request", "light") or req.connector_type == "csv":
        raise HTTPException(status_code=404, detail="unknown connector type for a request")
    _reject_credential_like_fields(req.details)

    row = source_requests_store.create(
        cid, connector_type=req.connector_type, details=req.details, created_by=_semantic_author(me)
    )
    label = req.details.get("display_name") or connector["label"]
    _audit(
        "admin_source_requested", client_id=cid, actor=me, action="data_source.requested",
        target_type="source_request", target_id=row["id"], target_label=label,
        after={"connector_type": req.connector_type},
    )
    log_event(logger, "platform_notification", client_id=cid, kind="source_request", connector_type=req.connector_type)
    return SourceRequestInfo(**row)


@app.post("/api/admin/data-sources/interest", response_model=InterestResponse)
def admin_record_data_source_interest(
    req: InterestRequest, me: dict = Depends(require_client_admin)
) -> InterestResponse:
    """A 'coming soon' connector card's click (Shopify/Google Analytics/Meta
    Ads, or a driver_pending SQL engine) -- no flow opens, just records
    interest (audit + platform log), per item 1's connector catalog note."""
    cid = me["client_id"]
    connector = connector_catalog.get_connector(req.connector_type)
    label = connector["label"] if connector else req.connector_type
    _audit(
        "admin_data_source_interest", client_id=cid, actor=me, action="data_source.interest_recorded",
        target_type="connector", target_label=label, after={"connector_type": req.connector_type},
    )
    log_event(logger, "platform_notification", client_id=cid, kind="connector_interest", connector_type=req.connector_type)
    return InterestResponse(recorded=True, connector_type=req.connector_type)


@app.post("/api/admin/data-sources/upload", response_model=UploadInfo)
async def admin_upload_data_source_file(
    file: UploadFile = File(...), me: dict = Depends(require_client_admin)
) -> UploadInfo:
    """Path C item 8: CSV/.xlsx -> a real queryable table in the client's own
    analytics DB (uploads schema). 10MB cap, same pattern as the org-settings
    logo upload."""
    cid = me["client_id"]
    data = await file.read(file_upload.MAX_UPLOAD_BYTES + 1)
    if len(data) > file_upload.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=422, detail="File must be 10MB or smaller.")
    filename = file.filename or "upload.csv"
    try:
        df = file_upload.parse_file(filename, data)
        table_name = file_upload.table_name_for_filename(filename)
        plan = file_upload.create_table_from_dataframe(cid, table_name, df)
    except file_upload.FileUploadError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    row = uploads_store.create(
        cid, table_name=table_name, original_filename=filename,
        column_count=len(plan), row_count=len(df), uploaded_by=_semantic_author(me),
    )
    _audit(
        "admin_data_source_uploaded", client_id=cid, actor=me, action="data_source.uploaded",
        target_type="upload", target_id=row["id"], target_label=filename,
        after={"table_name": table_name, "row_count": len(df), "column_count": len(plan)},
    )
    return UploadInfo(
        id=row["id"], table_name=table_name, original_filename=filename,
        columns=[UploadColumnPlan(**c) for c in plan], row_count=len(df),
    )


@app.post("/api/admin/data-sources/uploads/{upload_id}/replace", response_model=UploadInfo)
async def admin_replace_data_source_upload(
    upload_id: str, file: UploadFile = File(...), me: dict = Depends(require_client_admin)
) -> UploadInfo:
    """The upload card's 'replace file' action -- same table name, fresh
    data, same 10MB/.csv/.xlsx rules as the initial upload."""
    cid = me["client_id"]
    existing = uploads_store.get(cid, upload_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="unknown upload")
    data = await file.read(file_upload.MAX_UPLOAD_BYTES + 1)
    if len(data) > file_upload.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=422, detail="File must be 10MB or smaller.")
    filename = file.filename or existing["original_filename"]
    try:
        df = file_upload.parse_file(filename, data)
        plan = file_upload.create_table_from_dataframe(cid, existing["table_name"], df)
    except file_upload.FileUploadError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    row = uploads_store.replace(
        cid, upload_id, original_filename=filename, column_count=len(plan), row_count=len(df)
    )
    _audit(
        "admin_data_source_upload_replaced", client_id=cid, actor=me, action="data_source.upload_replaced",
        target_type="upload", target_id=upload_id, target_label=filename,
        after={"table_name": existing["table_name"], "row_count": len(df), "column_count": len(plan)},
    )
    return UploadInfo(
        id=row["id"], table_name=row["table_name"], original_filename=filename,
        columns=[UploadColumnPlan(**c) for c in plan], row_count=len(df),
    )


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
        target_type="data_source", target_id=source_id, target_label=source.get("display_name", source_id),
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
    org_readings = org_alerts.readings_for_alerts_engine(cid, org_alerts_store)
    raw = alerts_engine.evaluate_all_alerts(client_id=cid, alert_config=cfg["alerts"], org_alert_readings=org_readings)
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


# --- production static frontend (deployment_prep_prompt.md item 1) ---------
# Registered LAST and only a catch-all path route, so every specific /api/*
# and /healthz route above still matches first -- FastAPI/Starlette match
# routes in registration order, and only a request nothing above matched
# falls through to this one. Present only when `frontend/dist` actually
# exists (the prod Docker build's `npm run build` output, copied in by
# api/Dockerfile.prod) -- local dev's docker-compose.yml runs the separate
# Vite dev server instead and never has this directory, so this block is
# simply absent there, not merely inactive.
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_static_or_index(full_path: str) -> FileResponse:
        """Serves a real built asset (JS/CSS/favicon/etc.) by exact path, or
        falls back to index.html for any client-side route (e.g. /login) so
        the SPA's own router handles it -- the standard single-service SPA
        hosting pattern. FileResponse (not a raw read) gets us correct
        Content-Type + conditional/range-request support for free, so a
        dedicated StaticFiles mount isn't needed for this one directory."""
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
