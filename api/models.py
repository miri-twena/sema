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
    # Anchor for a persisted drill-down THREAD: the turn (within
    # `conversation_id`, the PARENT conversation) whose answer this widget
    # belongs to. Only meaningful together with drill_context and
    # conversation_id -- when all three are present the turn is persisted into
    # that widget's thread (creating it on the first turn) instead of into
    # `conversation_id` itself. A drill request with no turn_index (e.g. a
    # home-dashboard widget, which has no parent conversation) falls back to
    # the ordinary conversation flow unchanged.
    turn_index: int | None = None


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
    # 1-2 sentence executive takeaway rendered above the answer. Produced by the
    # agent as a STRUCTURED field -- the client must never derive it by slicing
    # or parsing `answer`. None for non-'answer' modes and for responses (or
    # stored payloads) recorded before this field existed, which is also what
    # keeps older persisted conversations valid.
    summary: str | None = None
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
    # Set only when this turn was persisted into a drill-down thread (see
    # ChatRequest.turn_index) -- the thread this turn actually landed in.
    # `conversation_id` above still carries the PARENT conversation unchanged,
    # so a thread turn never looks like it switched the client's main chat.
    thread_id: str | None = None


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


class ThreadSummary(BaseModel):
    """One drill-down thread's badge info: its anchor (which turn, which
    widget) plus how many follow-up questions have been asked in it. Threads
    are never listed in the sidebar -- this is the only place a thread's
    existence is surfaced, purely so the client can badge the widget it
    belongs to."""

    id: str
    turn_index: int
    widget_kind: Literal["kpi", "chart", "table", "action"]
    widget_title: str
    turn_count: int  # user-asked questions in this thread ("N follow-ups")
    updated_at: str


class ThreadDetail(BaseModel):
    """A thread plus its full transcript -- what reopening a widget's
    drill-down needs to resume instead of starting over. `messages` is the
    same shape as ConversationDetail's, so the client's existing
    turnsFromDetail() reads either one unchanged."""

    id: str
    conversation_id: str
    turn_index: int
    widget_kind: Literal["kpi", "chart", "table", "action"]
    widget_title: str
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


class PulseMetric(BaseModel):
    """One tile in the Daily Brief's pulse strip -- ALWAYS renders (unlike
    insights below), so the section changes every day even on a quiet one.
    `spark` is the trailing 14 daily values ending at `value` (yesterday's) --
    raw numbers, not a rendered path, so the client draws its own polyline
    with no charting library. `status` is yesterday's deviation vs the same
    weekday's average over the prior 4 weeks; `above`/`below` past ±20%,
    `normal` otherwise (the common case, and the whole point of the pulse:
    most days should read as unremarkable, not manufactured as interesting).
    """

    metric: Literal["revenue", "orders", "conversion"]
    label: str
    value: float
    format: Literal["currency", "number", "percent"]
    spark: list[float]
    status: Literal["above", "below", "normal"]
    status_label: str


class BriefInsight(BaseModel):
    """One attention card -- rendered only when its generator's threshold is
    actually cleared (see daily_brief.py's 6 generators). `icon` is a stable
    key the client maps to a lucide icon + colour, never a raw icon name from
    the server. `severity` is the ranking key (top 3, most severe first) and
    isn't shown to the user directly.
    """

    kind: Literal[
        "yesterday_anomaly",
        "campaign_negative_roi",
        "vip_inactive",
        "record_day",
        "product_rank_shift",
        "mtd_pace",
    ]
    id: str  # stable for the day this card describes -- a fine React key
    icon: Literal["warning", "customers", "trending_up", "trending_down", "record", "product"]
    headline: str
    detail: str
    severity: float
    follow_up_question: str


class DailyBriefResponse(BaseModel):
    """The home dashboard's Daily Brief: a pulse strip (always renders) plus
    up to 3 ranked attention cards (event-driven -- an empty `insights` list
    is a normal, quiet-day response, not an error). Computed deterministically
    -- no model call -- so it can run on page load.
    """

    client_id: str
    as_of: str | None = None  # ISO date: the dataset's last complete day
    pulse: list[PulseMetric] = []
    insights: list[BriefInsight] = []


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
