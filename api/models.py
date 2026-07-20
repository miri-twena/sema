"""
SEMA API: Pydantic request/response models -- the stable contract.

This is the boundary between the existing Python backend (which returns plain
dicts with pandas DataFrames inside) and any frontend. The React app codes
against THESE shapes, not against Streamlit internals. DataFrames are
serialized to {columns, rows} in serialize.py before they reach here.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# --- chat -------------------------------------------------------------------
class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class DrillContextRequest(BaseModel):
    """Structured drill-down reference: WHICH widget the user clicked, as data
    fields. The server builds the actual prompt framing from these (see
    sema_core.agent.prompts.build_drill_context) -- free-text context blocks
    from the client are never trusted or forwarded to the model as framing."""

    kind: Literal["kpi", "chart", "table", "action"]
    title: str = Field(max_length=200)
    detail: str = Field(default="", max_length=2000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    # Legacy path: the client ships its own history. Cap matches the agent's
    # MAX_HISTORY_TURNS * 2; oversized histories are rejected with 422 rather
    # than silently truncated. Superseded by conversation_id when both are sent.
    history: list[Message] = Field(default_factory=list, max_length=20)
    # Preferred path: the server holds history server-side (see
    # conversation_store.py). Omit on the first message; the response returns
    # one to reuse on follow-ups.
    conversation_id: str | None = None
    client_id: str | None = None  # which client's DB + semantic layer to use
    # Set when the question comes from a widget drill-down panel.
    drill_context: DrillContextRequest | None = None


class Kpi(BaseModel):
    label: str
    value: Any  # number or string
    format: Literal["currency", "percent", "number", "ratio", "text"] = "text"
    delta: float | None = None
    delta_label: str | None = None


class Chart(BaseModel):
    kind: Literal["line", "bar", "grouped_bar", "donut"]
    title: str = ""
    x: str | None = None
    y: str | None = None
    color: str | None = None
    names: str | None = None
    values: str | None = None
    y_format: Literal["currency", "number", "percent"] | None = None
    highlight_x: Any | None = None
    # The data is serialized from the bound run_sql result, so the frontend
    # (Recharts) renders straight from columns/rows -- no DataFrame leaks out.
    columns: list[str] = []
    rows: list[dict[str, Any]] = []


class Table(BaseModel):
    title: str | None = None
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    # Rows the backing query actually returned. Equals len(rows) unless the SQL
    # safety cap (SEMA_ROW_LIMIT) trimmed the result -- the UI shows this as
    # "Showing 1-50 of 406" and warns when `truncated` is set, so a capped list
    # can never masquerade as a complete one.
    total_rows: int = 0
    truncated: bool = False


class DateRange(BaseModel):
    start: str | None = None
    end: str | None = None


class Evidence(BaseModel):
    """Trust-layer metadata for one answer: what grounded it, and how much of
    it is a model self-report vs. a deterministic fact about the query that
    ran. `semantic_definitions`/`date_range`/`filters_applied` are what the
    agent reports it used; `data_freshness`/`records_used` are computed
    server-side from the actual query results, not model-asserted, so they
    can't be hallucinated."""

    semantic_definitions: list[str] = []
    date_range: DateRange | None = None
    filters_applied: list[str] = []
    data_sources: list[str] = []  # DB tables the backing SQL actually queried (parsed, not asserted)
    data_engine: str | None = None  # e.g. "PostgreSQL" -- only when a query ran
    database: str | None = None  # database NAME only; never host/user/credentials
    data_freshness: str | None = None  # ISO timestamp: when the backing query ran
    # Deterministic execution facts (server-computed, never model-asserted).
    query_status: Literal["ok", "failed", "none"] = "none"
    queries_run: int = 0
    queries_failed: int = 0
    # Short factual statements about the operations performed -- built from
    # executed tools and result metadata, never from model reasoning.
    analysis_steps: list[dict[str, Any]] = []
    # Model self-report, shown verbatim when an assumption was required.
    assumptions: list[str] = []
    # How an ambiguous part of the question was interpreted (governed default or
    # resolved clarification), as {label, value} pairs -- the transparency line
    # of the clarification flow. Empty when nothing was ambiguous.
    resolved_interpretation: list[dict[str, str]] = []
    records_used: int | None = None  # total rows returned by the SQL that backs this answer


class Notice(BaseModel):
    """A disclosed degradation on one answer -- the agent fell back or
    self-corrected. `kind` is a stable key the client localizes into an amber
    badge (fallback_model / sql_retried / router_fallback); params like
    `attempts` carry the detail. Structured, not prose, so a Hebrew answer
    gets a Hebrew badge (same pattern as evidence analysis_steps)."""

    kind: str
    attempts: int | None = None  # sql_retried: how many run_sql calls failed first


class ChatResponse(BaseModel):
    answer: str
    # How SEMA responded. Explicit on the contract so the client renders by
    # mode rather than sniffing the prose. Defaults to "answer" so responses
    # from the rule-based insight_builder stay valid unchanged.
    mode: Literal["answer", "clarification", "cannot_answer", "off_topic"] = "answer"
    reason_code: str | None = None
    # mode="clarification": 2-4 tappable choices that resolve the ambiguity.
    clarification_options: list[str] = []
    # mode="cannot_answer": the specific data/definition gap.
    missing: str | None = None
    kpis: list[Kpi] = []
    chart: Chart | None = None
    table: Table | None = None
    actions: list[str] = []
    # Short follow-up QUESTIONS the agent can answer from the data (distinct
    # from `actions`, which are business advice). Drive the composer's
    # one-tap suggestion, so they must never contain un-answerable actions.
    follow_up_questions: list[str] = []
    sql_used: str | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    evidence: Evidence | None = None
    # Disclosed fallbacks/degradations for this answer (usually empty). Default
    # keeps older persisted payloads valid without the field.
    notices: list[Notice] = []
    status: Literal["ok", "error"] = "ok"
    error: str | None = None
    conversation_id: str | None = None


# --- conversation management (the sidebar) ----------------------------------
class ConversationSummary(BaseModel):
    """One row in the chat-history sidebar."""

    id: str
    title: str
    pinned: bool = False
    archived: bool = False
    created_at: str
    updated_at: str
    message_count: int = 0


class ConversationMessage(BaseModel):
    """One stored turn. `payload` carries the assistant turn's rendered answer
    (a ChatResponse as JSON) so reopening a chat restores its KPI cards and
    charts rather than degrading to plain text. None for user turns and for
    turns recorded before payloads were stored."""

    role: Literal["user", "assistant"]
    content: str
    payload: ChatResponse | None = None


class ConversationDetail(BaseModel):
    """A conversation plus its full transcript -- what "reopen this chat" needs."""

    id: str
    title: str
    pinned: bool = False
    archived: bool = False
    messages: list[ConversationMessage] = []


class ConversationUpdate(BaseModel):
    """PATCH body. Every field is optional: send only what changed."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    pinned: bool | None = None
    archived: bool | None = None


# --- home dashboard ----------------------------------------------------------
class Overview(BaseModel):
    """Headline KPIs for the home dashboard (computed from the saved report
    library, not the agent -- fast enough to run on page load)."""

    client_id: str
    kpis: list[Kpi] = []
    as_of: str | None = None  # ISO timestamp: when these numbers were computed
    # The period the KPIs cover, as month keys ("2026-05"). Resolved by the
    # server: omitting start/end on the request yields the latest COMPLETE month.
    start: str | None = None
    end: str | None = None
    # Months a client may select -- complete months only, oldest first, so the
    # picker can't offer a period that's still in progress.
    available_months: list[str] = []


# --- alerts / clients / schema / health ------------------------------------
class Alert(BaseModel):
    id: str
    metric_label: str
    alert_label: str
    severity: Literal["critical", "warning"]
    message: str
    value: Any


class Client(BaseModel):
    id: str
    label: str
    semantic_dir: str = ""
    suggested_questions: list[str] = []


class ClientChangeRequest(BaseModel):
    client_id: str


class SchemaColumn(BaseModel):
    name: str
    type: str


class SchemaTable(BaseModel):
    name: str
    columns: list[SchemaColumn] = []


class SchemaResponse(BaseModel):
    client_id: str
    tables: list[SchemaTable] = []
    relationships: list[dict[str, Any]] = []


class PopularQuestion(BaseModel):
    question: str
    times_asked: int


class Health(BaseModel):
    status: str
    db_connected: bool
    agent_configured: bool
    active_client: str
