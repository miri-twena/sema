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
    data_freshness: str | None = None  # ISO timestamp: when the backing query ran
    records_used: int | None = None  # total rows returned by the SQL that backs this answer


class ChatResponse(BaseModel):
    answer: str
    kpis: list[Kpi] = []
    chart: Chart | None = None
    table: Table | None = None
    actions: list[str] = []
    sql_used: str | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    evidence: Evidence | None = None
    status: Literal["ok", "error"] = "ok"
    error: str | None = None
    conversation_id: str | None = None


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
