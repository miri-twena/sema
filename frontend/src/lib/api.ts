// Typed client for the SEMA FastAPI layer. Types mirror api/models.py (the
// Pydantic contract) -- the single source of truth for the response shape.

import type { ProgressEvent } from "./progress";
import type { AnalysisStep } from "./evidence";

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export interface Message {
  role: "user" | "assistant";
  content: string;
}

/** Structured drill-down reference (mirrors DrillContextRequest). The server
 * builds the prompt framing from these fields -- the client never sends
 * free-text context blocks. */
export interface DrillContextPayload {
  kind: "kpi" | "chart" | "table" | "action";
  title: string;
  detail: string;
}

export interface Kpi {
  label: string;
  value: number | string;
  format: "currency" | "percent" | "number" | "ratio" | "text";
  delta?: number | null;
  delta_label?: string | null;
}

export interface Chart {
  kind: "line" | "bar" | "grouped_bar" | "donut";
  title: string;
  x?: string | null;
  y?: string | null;
  color?: string | null;
  names?: string | null;
  values?: string | null;
  y_format?: string | null;
  highlight_x?: unknown;
  columns: string[];
  rows: Record<string, unknown>[];
}

export interface DataTableModel {
  title?: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
  /** Rows the backing query returned. Older persisted turns lack it, so the
   * table falls back to rows.length. */
  total_rows?: number;
  /** True when the SQL safety cap trimmed the result set. */
  truncated?: boolean;
}

export interface DateRange {
  start?: string | null;
  end?: string | null;
}

/** Trust-layer metadata for one answer. `semantic_definitions`/`date_range`/
 * `filters_applied` are the model's own self-report; `data_sources`/
 * `data_freshness`/`records_used` are computed server-side from the actual
 * query results, so they can't be hallucinated. */
export interface Evidence {
  semantic_definitions: string[];
  date_range: DateRange | null;
  filters_applied: string[];
  data_sources: string[];
  /** The connection the tables came from -- engine + database NAME only,
   * never host/user/credentials. Present only when a query really ran. */
  data_engine?: string | null;
  database?: string | null;
  data_freshness: string | null;
  records_used: number | null;
  /** Deterministic execution facts. Optional so conversations persisted
   * before these fields still parse. */
  query_status?: "ok" | "failed" | "none";
  queries_run?: number;
  queries_failed?: number;
  /** Structured operations ({op, ...params}); the client renders the wording
   * in the user's language. See lib/evidence.ts. */
  analysis_steps?: AnalysisStep[];
  assumptions?: string[];
}

export interface ChatResponse {
  answer: string;
  /** How SEMA responded. Render by this, never by sniffing the prose.
   * Optional so conversations persisted before this field still parse. */
  mode?: "answer" | "clarification" | "cannot_answer" | "off_topic";
  reason_code?: string | null;
  /** mode="clarification": tappable choices that resolve the ambiguity. */
  clarification_options?: string[];
  /** mode="cannot_answer": the specific data/definition gap. */
  missing?: string | null;
  kpis: Kpi[];
  chart: Chart | null;
  table: DataTableModel | null;
  actions: string[];
  /** Short follow-up questions the agent can answer from the data (distinct
   * from `actions`). Source for the composer's one-tap suggestion. */
  follow_up_questions: string[];
  sql_used: string | null;
  confidence: "high" | "medium" | "low" | null;
  evidence: Evidence | null;
  status: "ok" | "error";
  error: string | null;
  conversation_id?: string | null;
}

/** One row in the chat-history sidebar (mirrors api/models.py ConversationSummary). */
export interface ConversationSummary {
  id: string;
  title: string;
  pinned: boolean;
  archived: boolean;
  created_at: string;
  updated_at: string;
  message_count: number;
}

/** A stored turn; `payload` is the rendered answer for assistant turns. */
export interface ConversationMessage {
  role: "user" | "assistant";
  content: string;
  payload: ChatResponse | null;
}

/** A conversation plus its transcript -- what "reopen this chat" returns. */
export interface ConversationDetail {
  id: string;
  title: string;
  pinned: boolean;
  archived: boolean;
  messages: ConversationMessage[];
}

export interface Alert {
  id: string;
  metric_label: string;
  alert_label: string;
  severity: "critical" | "warning";
  message: string;
  value: number | string;
}

export interface Client {
  id: string;
  label: string;
  semantic_dir: string;
  suggested_questions: string[];
}

export interface Health {
  status: string;
  db_connected: boolean;
  agent_configured: boolean;
  active_client: string;
}

export interface PopularQuestion {
  question: string;
  times_asked: number;
}

/** Headline KPIs for the home dashboard (mirrors api/models.py Overview).
 * `start`/`end` are month keys ("2026-05") resolved by the server;
 * `available_months` lists only months with complete data. */
export interface Overview {
  client_id: string;
  kpis: Kpi[];
  as_of: string | null;
  start: string | null;
  end: string | null;
  available_months: string[];
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function postJSON<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal, // lets the caller abort the request (stop button)
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function sendJSON<T>(method: "PATCH" | "DELETE", path: string, body?: unknown): Promise<T | null> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.status === 204 ? null : ((await res.json()) as T);
}

function clientQuery(clientId: string, extra?: Record<string, string>): string {
  return new URLSearchParams({ client_id: clientId, ...extra }).toString();
}

export const api = {
  health: () => getJSON<Health>("/api/health"),
  clients: () => getJSON<Client[]>("/api/clients"),
  alerts: (clientId: string) => getJSON<Alert[]>(`/api/alerts?client_id=${encodeURIComponent(clientId)}`),
  popularQuestions: (clientId: string) =>
    getJSON<PopularQuestion[]>(`/api/popular-questions?client_id=${encodeURIComponent(clientId)}`),
  overview: (clientId: string, start?: string, end?: string) => {
    const params = new URLSearchParams({ client_id: clientId });
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    return getJSON<Overview>(`/api/overview?${params}`);
  },
  chat: (
    question: string,
    history: Message[],
    clientId: string,
    signal?: AbortSignal,
    drillContext?: DrillContextPayload,
    conversationId?: string | null,
  ) =>
    postJSON<ChatResponse>(
      "/api/chat",
      {
        question,
        history,
        client_id: clientId,
        drill_context: drillContext ?? null,
        // When set, the server appends to this conversation instead of
        // minting a new one per turn -- what makes chats reopenable.
        conversation_id: conversationId ?? null,
      },
      signal,
    ),

  /**
   * Streaming variant: emits the agent's REAL progress stages as they happen,
   * then the final answer. Same server call as `chat` -- only the framing
   * differs -- so the two can't drift apart.
   */
  chatStream: async (
    question: string,
    history: Message[],
    clientId: string,
    onStatus: (e: ProgressEvent) => void,
    signal?: AbortSignal,
    drillContext?: DrillContextPayload,
    conversationId?: string | null,
  ): Promise<ChatResponse> => {
    const res = await fetch(`${BASE}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        history,
        client_id: clientId,
        drill_context: drillContext ?? null,
        conversation_id: conversationId ?? null,
      }),
      signal,
    });
    if (!res.ok || !res.body) throw new Error(`${res.status} ${res.statusText}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let answer: ChatResponse | null = null;

    // SSE frames are separated by a blank line; each carries `event:` + `data:`.
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const frames = buf.split("\n\n");
      buf = frames.pop() ?? ""; // keep the trailing partial frame
      for (const frame of frames) {
        let event = "message";
        const dataLines: string[] = [];
        for (const line of frame.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
        }
        if (!dataLines.length) continue;
        const payload = JSON.parse(dataLines.join("\n"));
        if (event === "status") onStatus(payload as ProgressEvent);
        else if (event === "answer") answer = payload as ChatResponse;
        else if (event === "error") throw new Error(payload.error ?? "stream error");
      }
    }
    if (!answer) throw new Error("stream ended without an answer");
    return answer;
  },

  // --- conversation history (the sidebar) ---
  conversations: (clientId: string) =>
    getJSON<ConversationSummary[]>(`/api/conversations?${clientQuery(clientId)}`),
  conversation: (id: string, clientId: string) =>
    getJSON<ConversationDetail>(`/api/conversations/${id}?${clientQuery(clientId)}`),
  updateConversation: (
    id: string,
    clientId: string,
    patch: { title?: string; pinned?: boolean; archived?: boolean },
  ) => sendJSON<ConversationSummary>("PATCH", `/api/conversations/${id}?${clientQuery(clientId)}`, patch),
  deleteConversation: (id: string, clientId: string) =>
    sendJSON<null>("DELETE", `/api/conversations/${id}?${clientQuery(clientId)}`),
};
