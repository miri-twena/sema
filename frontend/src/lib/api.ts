// Typed client for the SEMA FastAPI layer. Types mirror api/models.py (the
// Pydantic contract) -- the single source of truth for the response shape.

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export interface Message {
  role: "user" | "assistant";
  content: string;
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
}

export interface ChatResponse {
  answer: string;
  kpis: Kpi[];
  chart: Chart | null;
  table: DataTableModel | null;
  actions: string[];
  sql_used: string | null;
  confidence: string | null;
  status: "ok" | "error";
  error: string | null;
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

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => getJSON<Health>("/api/health"),
  clients: () => getJSON<Client[]>("/api/clients"),
  alerts: (clientId: string) => getJSON<Alert[]>(`/api/alerts?client_id=${encodeURIComponent(clientId)}`),
  chat: (question: string, history: Message[], clientId: string) =>
    postJSON<ChatResponse>("/api/chat", { question, history, client_id: clientId }),
};
