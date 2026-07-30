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


class FeedbackRequest(BaseModel):
    """POST /api/feedback body. `rating: null` clears an existing rating
    (sema_core.feedback_store.clear) -- `comment` is ignored in that case.
    `turn_index` is the same 0-based "which user question" index ChatRequest
    already uses for thread anchoring, NOT a raw message-row id."""

    conversation_id: str
    turn_index: int = Field(ge=0)
    rating: Literal["up", "down"] | None
    comment: str | None = Field(default=None, max_length=500)
    client_id: str | None = None


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


class RecommendedAction(BaseModel):
    """One advisor-grade recommendation (sema_core.agent.response._clean_action
    already validated/defaulted these fields server-side). `why`/
    `expected_impact`/`effort` are optional -- an off_topic nudge carries only
    `action` since it isn't data-derived."""

    action: str
    why: str | None = None
    expected_impact: str | None = None
    effort: Literal["low", "medium", "high"] | None = None


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
    # from the rule-based insight_builder stay valid unchanged. 'access_denied'
    # is a data-access-scope refusal (sema_core.data_scope): the question
    # touched a domain/metric outside the requester's scope, so no SQL ran.
    mode: Literal[
        "answer", "clarification", "cannot_answer", "off_topic", "access_denied"
    ] = "answer"
    reason_code: str | None = None
    # mode="clarification": 2-4 tappable choices that resolve the ambiguity.
    clarification_options: list[str] = []
    # mode="cannot_answer": the specific data/definition gap.
    missing: str | None = None
    kpis: list[Kpi] = []
    chart: Chart | None = None
    table: Table | None = None
    # Structured advisor recommendations going forward (action/why/
    # expected_impact/effort). `str` stays in the union ONLY so a conversation
    # persisted before this field existed (a plain string array) still
    # validates when reopened -- the agent itself always emits the object
    # shape now (see sema_core.agent.response._clean_action).
    actions: list[str | RecommendedAction] = []
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


class TurnFeedback(BaseModel):
    """A user's thumbs up/down on one answer, plus an optional follow-up
    comment (only ever collected on a thumbs-down) -- see
    sema_core.feedback_store. Never present on user-role messages."""

    rating: Literal["up", "down"]
    comment: str | None = None


class ConversationMessage(BaseModel):
    """One stored turn. `payload` carries the assistant turn's rendered answer
    (a ChatResponse as JSON) so reopening a chat restores its KPI cards and
    charts rather than degrading to plain text. None for user turns and for
    turns recorded before payloads were stored. `feedback` is populated only
    on ConversationDetail's messages (a real, persisted conversation) -- never
    on ThreadDetail's, since drill/thread turns are out of scope for feedback
    (answer_feedback_prompt.md item 5)."""

    role: Literal["user", "assistant"]
    content: str
    payload: ChatResponse | None = None
    feedback: TurnFeedback | None = None


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


class AlertCatalogItem(BaseModel):
    """One POSSIBLE alert this client's semantic layer defines -- unlike
    Alert (only today's triggered breaches), this backs the admin Home-config
    editor's per-alert toggle/threshold picker (spec item 11)."""

    id: str
    label: str
    metric_label: str
    severity: Literal["critical", "warning"]


# --- alert_templates_prompt.md: template-based alert builder ---------------
class AlertTemplateParam(BaseModel):
    """One template's declared param keys -- purely descriptive (drives the
    builder's param form); the actual validation happens server-side in
    sema_core.alert_templates.validate_params."""

    key: str


class AlertTemplateCatalogItem(BaseModel):
    template: Literal["pct_change", "absolute_threshold", "anomaly", "streak"]
    label: str
    label_he: str
    description: str
    description_he: str
    params: list[str]


class AlertMetricCatalogItem(BaseModel):
    """One of the fixed KPI_CATALOG metrics this builder may target --
    mirrors home_config's own KPI picker, not an open certified-metric pick
    (see sema_core.alert_templates' module docstring)."""

    metric: str
    label: str


class AlertTestRequest(BaseModel):
    metric: str
    template: Literal["pct_change", "absolute_threshold", "anomaly", "streak"]
    params: dict


class AlertTestResult(BaseModel):
    ok: bool
    fire_count: int = 0
    fire_dates: list[str] = []
    error: str | None = None


class CreateAlertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    metric: str
    template: Literal["pct_change", "absolute_threshold", "anomaly", "streak"]
    params: dict
    severity: Literal["critical", "warning"] = "warning"


class UpdateAlertRequest(BaseModel):
    """Every field optional -- a PATCH may just toggle `enabled`, or may
    rewrite the whole rule (metric/template/params), which re-runs the
    dry-run test server-side before saving (spec item 4)."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    metric: str | None = None
    template: Literal["pct_change", "absolute_threshold", "anomaly", "streak"] | None = None
    params: dict | None = None
    severity: Literal["critical", "warning"] | None = None
    enabled: bool | None = None


class AlertRuleInfo(BaseModel):
    """One row of the unified admin alert list -- org-owned (editable) or
    system/YAML-owned (view-only, `system=True`, no edit/delete)."""

    id: str
    name: str
    metric: str
    metric_label: str
    template: str
    params: dict
    severity: Literal["critical", "warning"]
    enabled: bool
    system: bool
    disabled_reason: str | None = None
    summary_en: str
    summary_he: str
    created_by: str | None = None
    updated_at: str


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
    # Which upstream connector TYPE this entity's rows come from (spec §4.4).
    # Defaults to "postgres" -- every client before this feature shipped has
    # exactly one connector, so this never breaks an existing caller.
    source: Literal["postgres", "priority", "salesforce"] = "postgres"


class SchemaResponse(BaseModel):
    client_id: str
    tables: list[SchemaTable] = []
    relationships: list[dict[str, Any]] = []


class DataSourceEntity(BaseModel):
    """One entity (real table) mapped to a data source, plus the certified
    metrics that depend on it -- the "revenue, aov ← PostgreSQL" trust-chain
    expander (spec §4.3)."""

    name: str
    dependent_metrics: list[str] = []


class DataSource(BaseModel):
    """A status card in the client panel's Data sources screen (spec §4.3 +
    §4.4 v1.6's add-flows). `status` mirrors the spec's enum. `origin` says
    which store this card came from -- one unified list/shape either way, no
    parallel UI path: "config" is the original Phase 4 static YAML source,
    "connection" is a self-service SQL DB wizard connection, "request" is a
    tracked SaaS/Sheets request awaiting platform setup, "upload" is a CSV/
    Excel-backed table. Never a credential/password field, at any origin."""

    id: str
    type: str
    display_name: str
    status: Literal["healthy", "error", "syncing", "paused"]
    last_sync_at: str | None = None
    sync_duration_ms: int | None = None
    data_age_days: float | None = None
    primary_table: str | None = None
    primary_date_field: str | None = None
    entities: list[DataSourceEntity] = []
    origin: Literal["config", "connection", "request", "upload"] = "config"
    # Only set for origin="request" -- the "being set up" progress rail.
    progress_step: Literal["requested", "configuring", "testing", "active", "rejected"] | None = None
    # Display-safe credential hint ("last 4 of a hash") -- origin="connection" only.
    fingerprint: str | None = None


class ReportProblemResponse(BaseModel):
    """Ack for POST /api/admin/data-sources/{id}/report-problem -- the audit
    event this call created is the durable record; nothing else to return."""

    reported: bool
    source_id: str
    audit_event_id: str


# --- data sources: add-flow (data_sources_add_prompt.md) --------------------

class ConnectorCatalogItem(BaseModel):
    """One entry in the server-driven 'add a data source' gallery -- the
    frontend renders whatever this returns rather than hardcoding connector
    metadata (spec §4.4 v1.6 item 1)."""

    id: str
    kind: Literal["sql_db", "saas_request", "light"]
    label: str
    unlocks: dict[str, str]
    availability: Literal["available", "coming_soon", "driver_pending"]


class TestConnectionRequest(BaseModel):
    connector_type: Literal["postgres", "mysql", "mssql"]
    host: str
    port: int
    database: str
    username: str
    password: str
    ssl_enabled: bool = False


class TestConnectionResponse(BaseModel):
    """Never persists anything -- credentials are stored only after this
    reports ok=True (item 4: 'never store the credentials before a passed
    test'). `error` is always a scrubbed, generic message."""

    ok: bool
    tables: list[str] = []
    write_access: bool | None = None
    error: str | None = None
    readonly_user_sql: str | None = None


class CreateConnectionRequest(BaseModel):
    connector_type: Literal["postgres", "mysql", "mssql"]
    display_name: str
    host: str
    port: int
    database: str
    username: str
    password: str
    ssl_enabled: bool = False
    primary_table: str | None = None
    primary_date_field: str | None = None
    # Required true when the test reported write_access=True -- the
    # explicit acknowledgment checkbox item 4 requires before continuing.
    write_access_acknowledged: bool = False


class ClientConnectionInfo(BaseModel):
    """A stored self-service connection -- deliberately has NO password or
    encrypted_password field; `fingerprint` is the only credential-adjacent
    value ever returned."""

    id: str
    connector_type: str
    display_name: str
    host: str
    port: int
    database_name: str
    username: str
    ssl_enabled: bool
    fingerprint: str
    primary_table: str | None = None
    primary_date_field: str | None = None
    status: str
    created_at: str
    updated_at: str


class SourceRequestCreate(BaseModel):
    connector_type: str
    details: dict[str, str]


class SourceRequestInfo(BaseModel):
    id: str
    connector_type: str
    details: dict
    status: str
    created_at: str
    updated_at: str


class InterestRequest(BaseModel):
    connector_type: str


class InterestResponse(BaseModel):
    recorded: bool
    connector_type: str


class UploadColumnPlan(BaseModel):
    source_name: str
    column_name: str
    sql_type: str


class UploadInfo(BaseModel):
    id: str
    table_name: str
    original_filename: str
    columns: list[UploadColumnPlan]
    row_count: int


class SheetsInfo(BaseModel):
    """Whether the Google Sheets connector's service account is configured
    (SEMA_GSHEETS_SA_EMAIL) -- when it isn't, the flow still works, it just
    lands the source in a tracked 'setting up' state instead of validating
    access immediately (spec's own documented graceful-degradation path)."""

    sa_email: str | None = None


class PopularQuestion(BaseModel):
    question: str
    times_asked: int


class Health(BaseModel):
    status: str
    db_connected: bool
    agent_configured: bool
    active_client: str


# --- admin: users and permissions (spec §6.1) ------------------------------
AdminRole = Literal["client_admin", "analyst", "viewer"]
AdminStatus = Literal["active", "suspended", "invited"]
# Data-access scope (sema_core.data_scope): WHICH semantic-layer domains and
# metrics a user's questions may touch -- a second axis alongside role.
AdminDataScope = Literal["full", "no_financials", "sales_only", "custom"]


class AdminUser(BaseModel):
    """One organization user in the admin panel. `role`/`status` carry their
    allowed values as Literals here -- the DB stores them as plain TEXT, so
    this boundary is where they're actually validated. DERIVED, non-stored
    fields: `is_self` (this row is the current viewer -- the client protects
    it: no role select, no kebab), `invite_expired` (an invited user past its
    expiry -- computed from the timestamp, never stale), and `invited_by_name`
    (resolved via a join in the store, so a renamed/removed inviter is never
    stale). `invited_by` is null for founding members; `joined_at` is null
    until an invite is accepted -- there's no accept-invite flow yet (no real
    auth), so today it's only ever set by seed data."""

    id: str
    client_id: str
    name: str | None = None
    email: str
    title: str | None = None
    role: AdminRole
    status: AdminStatus
    invited_at: str | None = None
    invite_expires_at: str | None = None
    invited_by: str | None = None
    invited_by_name: str | None = None
    joined_at: str | None = None
    last_active_at: str | None = None
    created_at: str
    is_self: bool = False
    invite_expired: bool = False
    # Which semantic-layer domains/metrics this user may ask about
    # (sema_core.data_scope) -- always 'full' for a client_admin.
    data_scope: AdminDataScope = "full"


class AdminUserList(BaseModel):
    """The users screen's payload: the rows plus the two counts the subtitle
    shows ("N members · N pending invites"). Counts are of the WHOLE org, not
    the filtered view, so they don't jump around as the admin searches."""

    users: list[AdminUser] = []
    member_count: int  # active + suspended (people who have accounts)
    pending_count: int  # invited (not yet accepted)


class AdminInviteRequest(BaseModel):
    """POST body for inviting a user. Email format is validated server-side in
    the endpoint (specific 422) on top of this length guard. `data_scope` is
    optional -- omit it to get the safer DEFAULT_INVITE_SCOPE
    ('no_financials'); a client_admin invite is always 'full' regardless of
    what's sent here (enforced in the store)."""

    email: str = Field(min_length=3, max_length=254)
    role: AdminRole
    data_scope: AdminDataScope | None = None


class AdminUserUpdate(BaseModel):
    """PATCH body. Every field is optional: send only what changed (mirrors
    ConversationUpdate)."""

    role: AdminRole | None = None
    status: AdminStatus | None = None
    data_scope: AdminDataScope | None = None


class RoleInfo(BaseModel):
    """One entry in the role catalog (GET /api/admin/roles) -- the single
    source of truth for the role legend/tooltip copy in the UI. `id` matches
    AdminRole so the client can key off it directly."""

    id: AdminRole
    label: str
    description: str


class DataScopeInfo(BaseModel):
    """One entry in the data-scope catalog (GET /api/admin/data-scopes) --
    the single source of truth for the "Data access" column's legend and the
    scope editor's copy. `id` matches AdminDataScope. `selectable` is False
    only for `custom` (V2: the UI disables it, the server rejects a PATCH
    that tries to set it)."""

    id: AdminDataScope
    label: str
    description: str
    included_domains: list[str]
    excluded_domains: list[str]
    selectable: bool


# --- admin: semantic model (Draft -> Validate -> Publish) ------------------
SemanticStatus = Literal["certified", "draft", "deprecated"]
SemanticSection = Literal["metric", "rule", "knowledge", "glossary"]
SemanticFormat = Literal["currency", "number", "percent", "text"]


class SemanticMetricItem(BaseModel):
    """One metric as the admin screen shows it -- published fields, possibly
    overlaid with the caller's own in-progress draft (`is_draft`)."""

    name: str
    label: str
    description: str
    sql: str
    status: SemanticStatus = "certified"
    synonyms: list[str] = []
    format: SemanticFormat | None = None
    is_draft: bool = False
    is_new: bool = False
    validated: bool = False


class SemanticRuleItem(BaseModel):
    name: str
    definition: str
    logic: str | None = None
    applies_to: list[str] = []
    status: SemanticStatus = "certified"
    is_draft: bool = False
    is_new: bool = False
    validated: bool = False


class SemanticDateRange(BaseModel):
    start: str | None = None
    end: str | None = None


class SemanticKnowledgeItem(BaseModel):
    name: str
    type: Literal["recurring_event", "incident", "note"]
    date_range: SemanticDateRange | None = None
    recurrence: str | None = None
    description: str
    affects: list[str] = []
    is_draft: bool = False
    is_new: bool = False
    validated: bool = False


class SemanticGlossaryItem(BaseModel):
    term: str
    maps_to: str
    language: str | None = None
    is_draft: bool = False
    is_new: bool = False
    validated: bool = False


class SemanticModelResponse(BaseModel):
    """GET /api/admin/semantic's payload: the merged (published + this
    admin's drafts) view of every section, plus the header chip's numbers."""

    published_version: int
    draft_count: int
    metrics: list[SemanticMetricItem] = []
    rules: list[SemanticRuleItem] = []
    knowledge: list[SemanticKnowledgeItem] = []
    glossary: list[SemanticGlossaryItem] = []


class SemanticDraftSave(BaseModel):
    """PUT body: a full draft item. `action` distinguishes editing an existing
    published item from proposing a brand-new one (rules/knowledge/glossary
    only) from archiving one (data may be {} in that case)."""

    data: dict[str, Any] = {}
    action: Literal["edit", "create", "deprecate"] = "edit"


class SemanticValidateRequest(BaseModel):
    section: SemanticSection
    item_key: str


class SemanticValidateResult(BaseModel):
    """Never an error response itself -- a failed dry run is `ok: False` with
    `error` set, not an HTTP error, same philosophy as the agent's run_sql
    tool. `value`/`row_count`/`duration_ms`/`period_label` are set only for a
    SQL dry run that ran; `message` is set for a schema-only check."""

    ok: bool
    value: Any = None
    row_count: int | None = None
    duration_ms: float | None = None
    period_label: str | None = None
    message: str | None = None
    error: str | None = None


class SemanticPublishItemRef(BaseModel):
    section: SemanticSection
    item_key: str


class SemanticPublishRequest(BaseModel):
    items: list[SemanticPublishItemRef] = Field(min_length=1)


class SemanticVersion(BaseModel):
    """One entry in the History slide-over. `snapshot` (the full raw YAML
    text) deliberately isn't part of this model -- the list view only needs
    the metadata; restore reads the snapshot server-side."""

    id: str
    version: int
    changed_items: list[str]
    author: str | None = None
    created_at: str


# --- admin: organization settings (spec §2) --------------------------------
RetentionPolicy = Literal["forever", "90d", "30d"]


class OrgSettings(BaseModel):
    """One organization's settings row (sema_core.org_settings_store).
    `logo_path` is a served URL (or null), never a filesystem path."""

    client_id: str
    name: str
    logo_path: str | None = None
    timezone: str
    currency: str
    number_format: str
    default_language: Literal["en", "he"]
    retention_policy: RetentionPolicy
    updated_at: str
    # True when this response reflects a write that CLOBBERED a change the
    # caller hadn't seen yet (their `expected_updated_at` didn't match) --
    # the write still applied (last-write-wins); the UI shows a toast.
    conflict: bool = False
    # The retention sweep's last run for this client (sema_core.retention_
    # store), embedded here rather than a separate endpoint -- backs the "Last
    # cleanup: 6 hours ago · 12 conversations deleted" status line. All null
    # when the sweep has never run yet for this client (fresh install).
    last_retention_run_at: str | None = None
    last_retention_deleted_count: int | None = None
    last_retention_status: Literal["ok", "error"] | None = None
    last_retention_error: str | None = None


class OrgSettingsUpdate(BaseModel):
    """PATCH body. Every field optional: send only what changed. Sending a
    non-null `expected_updated_at` from the value you last fetched lets the
    server tell you if someone else changed a setting since (see
    OrgSettings.conflict) -- omit it to skip that check."""

    name: str | None = None
    timezone: str | None = None
    currency: str | None = None
    number_format: str | None = None
    default_language: Literal["en", "he"] | None = None
    retention_policy: RetentionPolicy | None = None
    expected_updated_at: str | None = None


class RetentionPreview(BaseModel):
    """"N conversations will be deleted on next run" -- shown before a
    retention_policy change is confirmed."""

    policy: RetentionPolicy
    conversations_to_delete: int


class PublicOrgSettings(BaseModel):
    """The subset of org settings every user (not just admins) needs: the
    sidebar's name/logo and the shared display-formatting config (currency/
    number_format) that drives KPI/table/chart rendering app-wide. Never
    includes timezone/retention_policy -- those are admin-only concerns.

    `language` governs the UI CHROME ONLY (nav, buttons, labels, empty
    states) -- it never governs the agent's answer language, which always
    mirrors the question's own language regardless of this setting
    (org_settings_gapfix_prompt.md Part 2; see AGENTS.md's Agent Voice
    section for the explicit split)."""

    name: str
    logo_path: str | None = None
    currency: str
    currency_symbol: str
    currency_position: Literal["prefix", "suffix"]
    number_format: str
    language: Literal["en", "he"]


# --- admin: audit log (spec §3) ---------------------------------------------
class AuditEvent(BaseModel):
    """One append-only row (sema_core.audit_store). `action` is a canonical
    dotted id ("user.role_changed", "semantic.published", ...) the frontend
    keys its human-readable sentence + category tag off of; `before`/`after`
    back the drawer's field-by-field diff. `actor_id` is null for a system-
    driven event (none exist yet, but the shape allows for one)."""

    id: str
    client_id: str
    actor_id: str | None = None
    actor_name: str | None = None
    actor_role: str | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    target_label: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    created_at: str


class AuditEventList(BaseModel):
    """One page of the audit log plus enough to drive pagination controls."""

    events: list[AuditEvent] = []
    total: int
    page: int
    page_size: int


# --- admin: home screen customization (spec §1) -----------------------------
class HomeConfigKpis(BaseModel):
    """Which of home_config.KPI_CATALOG's ids to show, in order, and whether
    each shows a period-over-period delta (only meaningful for revenue/
    orders/aov -- see sema_core.home_config's module docstring for why this
    isn't a general "any certified metric" picker)."""

    order: list[str] = Field(default_factory=list)
    deltas: dict[str, bool] = Field(default_factory=dict)


class HomeConfigDailyBrief(BaseModel):
    pulse_enabled: bool = True
    insights_enabled: bool = True
    sensitivity: Literal["conservative", "balanced", "sensitive"] = "balanced"


class HomeConfigSuggestedQuestions(BaseModel):
    """`questions` empty means "use this client's static suggested_questions
    from config/clients.yaml" -- so publishing an empty list is a deliberate
    no-op, not a way to hide the section."""

    questions: list[str] = Field(default_factory=list)
    trending_enabled: bool = True


class HomeConfigAlertSetting(BaseModel):
    enabled: bool = True
    threshold: float | None = None


class HomeConfig(BaseModel):
    """The whole home-screen config, draft or published -- one JSON blob
    (sema_core.home_config_store), not many independently-versioned items
    like the semantic model. Every field defaults to the same values as
    sema_core.home_config.DEFAULT_CONFIG, so a bare `{}` round-trips to
    today's unconfigured behavior."""

    kpis: HomeConfigKpis = Field(default_factory=HomeConfigKpis)
    default_period_months: Literal[1, 3, 6, 12] = 1
    daily_brief: HomeConfigDailyBrief = Field(default_factory=HomeConfigDailyBrief)
    suggested_questions: HomeConfigSuggestedQuestions = Field(default_factory=HomeConfigSuggestedQuestions)
    alerts: dict[str, HomeConfigAlertSetting] = Field(default_factory=dict)


class HomeConfigResponse(BaseModel):
    """GET/PUT/publish/revert's shared response shape."""

    draft: HomeConfig | None = None
    published: HomeConfig | None = None
    version: int
    published_by: str | None = None
    published_at: str | None = None
    updated_at: str
    # Deprecated-metric warnings against the PUBLISHED config (spec item 13)
    # -- drives the editor's warning badge. Empty when nothing was dropped.
    warnings: list[str] = []


class HomeConfigPublishError(BaseModel):
    message: str
    errors: list[str]


class HomeConfigPreview(BaseModel):
    """The live preview pane's payload (spec item 11): the SAME shapes the
    real home dashboard consumes, computed from the DRAFT config (or
    published, if there's no draft) and the admin's own data scope."""

    overview: Overview
    brief: DailyBriefResponse
    alerts: list[Alert]
    suggested_questions: list[str]
    popular_questions: list[PopularQuestion]
    warnings: list[str] = []


class CurrencyInfo(BaseModel):
    """One entry in the currency catalog (GET /api/admin/org-settings/currencies)
    -- the single source of truth for the settings form's picker, mirroring
    the role/data-scope catalog pattern."""

    code: str
    symbol: str
    position: Literal["prefix", "suffix"]
