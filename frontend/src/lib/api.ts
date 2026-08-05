// Typed client for the SEMA FastAPI layer. Types mirror api/models.py (the
// Pydantic contract) -- the single source of truth for the response shape.

import type { ProgressEvent } from "./progress";
import type { AnalysisStep } from "./evidence";
import { revokeAccess, withAccessKeyHeader } from "./pilotAccess";

// Falls back to localhost:8000 only when VITE_API_URL is truly UNSET (bare
// `npm run dev` outside docker-compose, which always sets it explicitly) --
// checked via `!== undefined` rather than truthiness so a deliberately EMPTY
// value (the production single-service build, where the API serves the
// built frontend from its own origin) is honored as "same-origin, call
// relative paths" instead of being coerced back to the dev default.
const BASE = import.meta.env.VITE_API_URL !== undefined ? import.meta.env.VITE_API_URL : "http://localhost:8000";

/** A server-relative path (e.g. PublicOrgSettings.logo_path, "/api/admin/
 * org-settings/logo/ecommerce") -> a fully-qualified URL an <img> tag can
 * load directly. Null in, null out. */
export function resolveApiUrl(path: string | null): string | null {
  return path ? `${BASE}${path}` : null;
}

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
  /** Rows the backing query returned -- the TRUE total when `truncated`
   * (server-computed via a COUNT(*), see api/serialize.py), not just
   * rows.length. Older persisted turns lack it, so the table falls back to
   * rows.length. */
  total_rows?: number;
  /** True when the SQL safety cap trimmed the result set. */
  truncated?: boolean;
  /** Present only when this table is bound to a single agent SQL result
   * (never for the rule-based insight_builder path) -- its presence, not
   * its content, is what the client reads: it's what makes "Export all N
   * rows" (exportTableCsv, by conversation/turn reference) available at
   * all. The client never inspects or sends the SQL itself. */
  sql?: string | null;
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
  /** How an ambiguous part of the question was interpreted (governed default or
   * resolved clarification), as {label, value} pairs. The transparency line of
   * the clarification flow; empty when nothing was ambiguous. */
  resolved_interpretation?: { label: string; value: string }[];
}

/** A disclosed degradation on one answer (mirrors api/models.py Notice).
 * `kind` is a stable key the UI localizes into an amber badge; `attempts`
 * carries detail for sql_retried. */
export interface Notice {
  kind: string;
  attempts?: number | null;
}

/** One advisor-grade recommendation (mirrors api/models.py RecommendedAction).
 * `why`/`expected_impact`/`effort` are optional -- an off_topic nudge carries
 * only `action` since it isn't data-derived. Server-cleaned/defaulted, so
 * every field the server sends is already trustworthy. */
export interface RecommendedAction {
  action: string;
  why?: string | null;
  expected_impact?: string | null;
  effort?: "low" | "medium" | "high" | null;
}

export interface ChatResponse {
  answer: string;
  /** 1-2 sentence executive takeaway rendered above the answer. A STRUCTURED
   * field from the agent -- never derive it here by slicing, truncating or
   * parsing `answer`. Optional so conversations persisted before this field
   * still parse; absent/null means render no summary block. */
  summary?: string | null;
  /** How SEMA responded. Render by this, never by sniffing the prose.
   * Optional so conversations persisted before this field still parse.
   * 'access_denied': the question touched a domain/metric outside the
   * requester's data-access scope (sema_core.data_scope) -- policy, not an
   * error, so it renders with the same quiet, non-alarming treatment. */
  mode?: "answer" | "clarification" | "cannot_answer" | "off_topic" | "access_denied";
  reason_code?: string | null;
  /** mode="clarification": tappable choices that resolve the ambiguity. */
  clarification_options?: string[];
  /** mode="cannot_answer": the specific data/definition gap. */
  missing?: string | null;
  kpis: Kpi[];
  chart: Chart | null;
  table: DataTableModel | null;
  /** Structured advisor recommendations going forward. `string` stays in the
   * union ONLY so a conversation persisted before this field existed (a
   * plain string array) still renders when reopened. */
  actions: (string | RecommendedAction)[];
  /** Short follow-up questions the agent can answer from the data (distinct
   * from `actions`). Source for the composer's one-tap suggestion. */
  follow_up_questions: string[];
  sql_used: string | null;
  confidence: "high" | "medium" | "low" | null;
  evidence: Evidence | null;
  /** Disclosed fallbacks/degradations for this answer (usually empty).
   * Optional so conversations persisted before this field still parse. */
  notices?: Notice[];
  status: "ok" | "error";
  error: string | null;
  conversation_id?: string | null;
  /** Set only when this turn was persisted into a drill-down thread --
   * `conversation_id` above still carries the PARENT conversation unchanged. */
  thread_id?: string | null;
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
  /** Total drill-down follow-up questions across every thread anchored to
   * this conversation -- powers the sidebar's per-row badge. */
  drill_count: number;
}

/** A user's thumbs up/down on one answer (answer_feedback_prompt.md), plus an
 * optional follow-up comment (only ever collected on a thumbs-down). */
export interface TurnFeedback {
  rating: "up" | "down";
  comment: string | null;
}

/** A stored turn; `payload` is the rendered answer for assistant turns.
 * `feedback` is populated only on a real conversation's assistant turns
 * (never on a drill/thread turn -- see MessageActions/lib/conversations.ts). */
export interface ConversationMessage {
  role: "user" | "assistant";
  content: string;
  payload: ChatResponse | null;
  feedback?: TurnFeedback | null;
}

/** A conversation plus its transcript -- what "reopen this chat" returns. */
export interface ConversationDetail {
  id: string;
  title: string;
  pinned: boolean;
  archived: boolean;
  messages: ConversationMessage[];
}

/** One drill-down thread's badge info (mirrors api/models.py ThreadSummary):
 * its anchor (which turn, which widget) plus how many follow-up questions
 * have been asked in it. Threads never appear in the sidebar -- this is the
 * only place their existence is surfaced. */
export interface ThreadSummary {
  id: string;
  turn_index: number;
  widget_kind: "kpi" | "chart" | "table" | "action";
  widget_title: string;
  turn_count: number;
  updated_at: string;
}

/** A thread plus its full transcript -- what reopening a widget's drill-down
 * needs to resume it. Same `messages` shape as ConversationDetail, so
 * turnsFromDetail() reads either one. */
export interface ThreadDetail {
  id: string;
  conversation_id: string;
  turn_index: number;
  widget_kind: "kpi" | "chart" | "table" | "action";
  widget_title: string;
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

/** The subset of org settings every user needs (mirrors api/models.py
 * PublicOrgSettings) -- sidebar name/logo + the shared display-formatting
 * config. Never timezone/retention_policy, which are admin-only. */
export interface PublicOrgSettings {
  name: string;
  logo_path: string | null;
  currency: string;
  currency_symbol: string;
  currency_position: "prefix" | "suffix";
  number_format: string;
  // UI chrome language ONLY -- the agent's answer language always mirrors
  // the question regardless of this setting (org_settings_gapfix_prompt.md
  // Part 2; see AGENTS.md's Agent Voice section).
  language: "en" | "he";
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

/** One tile in the Daily Brief's pulse strip (mirrors api/models.py
 * PulseMetric) -- ALWAYS present (unlike insights below), so the section
 * changes every day even on a quiet one. `spark` is the trailing 14 daily
 * values ending at `value` (yesterday's), raw numbers for a hand-drawn
 * polyline -- no charting library. `status` is yesterday's deviation vs the
 * same weekday's average over the prior 4 weeks. */
export interface PulseMetric {
  metric: "revenue" | "orders" | "conversion";
  label: string;
  value: number;
  format: "currency" | "number" | "percent";
  spark: number[];
  status: "above" | "below" | "normal";
  status_label: string;
}

/** One attention card (mirrors api/models.py BriefInsight) -- rendered only
 * when its generator's threshold is cleared. `icon` is a stable key the
 * client maps to a lucide icon + colour. */
export interface BriefInsight {
  kind:
    | "yesterday_anomaly"
    | "campaign_negative_roi"
    | "vip_inactive"
    | "record_day"
    | "product_rank_shift"
    | "mtd_pace";
  id: string;
  icon: "warning" | "customers" | "trending_up" | "trending_down" | "record" | "product";
  headline: string;
  detail: string;
  severity: number;
  follow_up_question: string;
}

/** The home dashboard's Daily Brief (mirrors api/models.py DailyBriefResponse):
 * a pulse strip (always renders) plus up to 3 ranked attention cards
 * (event-driven -- an empty `insights` list is a normal, quiet-day response). */
export interface DailyBrief {
  client_id: string;
  as_of: string | null;
  pulse: PulseMetric[];
  insights: BriefInsight[];
}

// --- admin: home screen customization (spec §1) -----------------------------
// Mirrors api/models.py's HomeConfig section. The KPI id catalog is the
// small, fixed set this app already knows how to compute (see
// sema_core.home_config's module docstring) -- not an arbitrary metric name.
export type HomeConfigKpiId = "revenue" | "orders" | "aov" | "churn_risk";
export type HomeSensitivity = "conservative" | "balanced" | "sensitive";

export interface HomeConfigKpis {
  order: HomeConfigKpiId[];
  deltas: Partial<Record<HomeConfigKpiId, boolean>>;
}

export interface HomeConfigDailyBrief {
  pulse_enabled: boolean;
  insights_enabled: boolean;
  sensitivity: HomeSensitivity;
}

export interface HomeConfigSuggestedQuestions {
  /** Empty means "use this client's static suggested_questions from
   * config/clients.yaml" -- publishing an empty list is a deliberate no-op. */
  questions: string[];
  trending_enabled: boolean;
}

export interface HomeConfigAlertSetting {
  enabled: boolean;
  threshold: number | null;
}

export interface HomeConfig {
  kpis: HomeConfigKpis;
  default_period_months: 1 | 3 | 6 | 12;
  daily_brief: HomeConfigDailyBrief;
  suggested_questions: HomeConfigSuggestedQuestions;
  alerts: Record<string, HomeConfigAlertSetting>;
}

export interface HomeConfigResponse {
  draft: HomeConfig | null;
  published: HomeConfig | null;
  version: number;
  published_by: string | null;
  published_at: string | null;
  updated_at: string;
  /** Deprecated-metric warnings against the PUBLISHED config (spec item 13) --
   * drives the editor's warning badge. */
  warnings: string[];
}

/** One POSSIBLE alert (mirrors api/models.py AlertCatalogItem) -- unlike
 * Alert (today's triggered breaches), backs the editor's alert picker. */
export interface AlertCatalogItem {
  id: string;
  label: string;
  metric_label: string;
  severity: "critical" | "warning";
}

// --- alert_templates_prompt.md: template-based alert builder ---------------
export type AlertTemplateType = "pct_change" | "absolute_threshold" | "anomaly" | "streak";

export interface AlertTemplateCatalogItem {
  template: AlertTemplateType;
  label: string;
  label_he: string;
  description: string;
  description_he: string;
  params: string[];
}

export interface AlertMetricCatalogItem {
  metric: string;
  label: string;
}

export interface AlertTestRequest {
  metric: string;
  template: AlertTemplateType;
  params: Record<string, unknown>;
}

export interface AlertTestResult {
  ok: boolean;
  fire_count: number;
  fire_dates: string[];
  error: string | null;
}

export interface CreateAlertRequest {
  name: string;
  metric: string;
  template: AlertTemplateType;
  params: Record<string, unknown>;
  severity: "critical" | "warning";
}

export interface UpdateAlertRequest {
  name?: string;
  metric?: string;
  template?: AlertTemplateType;
  params?: Record<string, unknown>;
  severity?: "critical" | "warning";
  enabled?: boolean;
}

export interface AlertRuleInfo {
  id: string;
  name: string;
  metric: string;
  metric_label: string;
  template: string;
  params: Record<string, unknown>;
  severity: "critical" | "warning";
  enabled: boolean;
  system: boolean;
  disabled_reason: string | null;
  summary_en: string;
  summary_he: string;
  created_by: string | null;
  updated_at: string;
}

export interface HomeConfigPreview {
  overview: Overview;
  brief: DailyBrief;
  alerts: Alert[];
  suggested_questions: string[];
  popular_questions: PopularQuestion[];
  warnings: string[];
}

export const DEFAULT_HOME_CONFIG: HomeConfig = {
  kpis: { order: ["revenue", "orders", "aov", "churn_risk"], deltas: { revenue: true, orders: true, aov: true } },
  default_period_months: 1,
  daily_brief: { pulse_enabled: true, insights_enabled: true, sensitivity: "balanced" },
  suggested_questions: { questions: [], trending_enabled: true },
  alerts: {},
};

/** Every /api/* route is gated by the internal-pilot access key (see
 * lib/pilotAccess.ts) -- a 401 here specifically means that key is
 * missing/wrong/expired, so it's the ONE status code every fetch helper
 * below reacts to by clearing it and telling the gate to reappear. */
function checkUnauthorized(res: Response): void {
  if (res.status === 401) revokeAccess();
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: withAccessKeyHeader() });
  if (!res.ok) {
    checkUnauthorized(res);
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

async function postJSON<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: withAccessKeyHeader({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
    signal, // lets the caller abort the request (stop button)
  });
  if (!res.ok) {
    checkUnauthorized(res);
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

async function sendJSON<T>(method: "PATCH" | "DELETE", path: string, body?: unknown): Promise<T | null> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: withAccessKeyHeader(body ? { "Content-Type": "application/json" } : undefined),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    checkUnauthorized(res);
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return res.status === 204 ? null : ((await res.json()) as T);
}

function clientQuery(clientId: string, extra?: Record<string, string>): string {
  return new URLSearchParams({ client_id: clientId, ...extra }).toString();
}

// --- admin: users and permissions (spec §6.1) ------------------------------
// The admin panel surfaces server-side error messages inline (duplicate email,
// last-admin, bad email), which the generic helpers above discard. ApiError
// carries the HTTP status plus the server's `detail` string so the UI can show
// the specific message rather than a generic failure.
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function adminRequest<T>(
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T | null> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: withAccessKeyHeader(body ? { "Content-Type": "application/json" } : undefined),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    checkUnauthorized(res);
    // FastAPI puts the message under `detail` -- usually a string, but the
    // semantic-model publish endpoint sends a structured
    // {message, failures} object on a 409; fall back to the status text for
    // anything else.
    let detail = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") detail = data.detail;
      else if (typeof data?.detail?.message === "string") detail = data.detail.message;
    } catch {
      // non-JSON error body -- keep the status-text fallback
    }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? null : ((await res.json()) as T);
}

export type AdminRole = "client_admin" | "analyst" | "viewer";
export type AdminStatus = "active" | "suspended" | "invited";
/** Data-access scope (mirrors api/models.py AdminDataScope /
 * sema_core.data_scope): WHICH semantic-layer domains/metrics a user's
 * questions may touch -- a second axis alongside role. 'custom' is reserved
 * for V2: the type allows it so the UI can render it disabled, but nothing
 * may actually select it. */
export type AdminDataScope = "full" | "no_financials" | "sales_only" | "custom";

/** One org user in the admin panel (mirrors api/models.py AdminUser). `is_self`
 * and `invite_expired` are server-derived flags, never stored. */
export interface AdminUser {
  id: string;
  client_id: string;
  name: string | null;
  email: string;
  title: string | null;
  role: AdminRole;
  status: AdminStatus;
  invited_at: string | null;
  invite_expires_at: string | null;
  /** Null for founding members (never invited). */
  invited_by: string | null;
  /** Resolved inviter name -- null when `invited_by` is null (founding
   * member) OR when it's set but the inviter no longer resolves (removed). */
  invited_by_name: string | null;
  /** Null until an invite is accepted -- there's no accept-invite flow yet
   * (no real auth), so today this is only set by seed data. */
  joined_at: string | null;
  last_active_at: string | null;
  created_at: string;
  is_self: boolean;
  invite_expired: boolean;
  /** Always 'full' for a client_admin (enforced server-side). */
  data_scope: AdminDataScope;
}

// --- admin: impersonation ("view as user", impersonation_prompt.md) --------
/** Mirrors api/models.py ImpersonationState -- the shape of GET/POST/DELETE
 * /api/admin/impersonation's response. `active: false` means every other
 * field is null (no session running). `expires_at` is an ISO timestamp; the
 * banner computes its own live "ends in Nm" countdown from it rather than
 * trusting a server-rendered string that would go stale between polls. */
export interface ImpersonationState {
  active: boolean;
  target_id: string | null;
  target_name: string | null;
  target_email: string | null;
  target_role: AdminRole | null;
  started_at: string | null;
  expires_at: string | null;
}

export interface AdminUserList {
  users: AdminUser[];
  member_count: number;
  pending_count: number;
  active_admin_count: number;
  total: number;
  page: number;
  page_size: number;
}

/** One entry in the role catalog (mirrors api/models.py RoleInfo) -- the
 * single copy source for the role legend/tooltip; never hardcode this text
 * in a component. */
export interface RoleInfo {
  id: AdminRole;
  label: string;
  description: string;
}

/** One entry in the data-scope catalog (mirrors api/models.py DataScopeInfo)
 * -- the single copy source for the "Data access" column's legend and the
 * scope editor; never hardcode this text in a component. `selectable` is
 * false only for `custom` (V2). */
export interface DataScopeInfo {
  id: AdminDataScope;
  label: string;
  description: string;
  included_domains: string[];
  excluded_domains: string[];
  selectable: boolean;
}

// --- admin: organization settings (spec §2) --------------------------------
export type RetentionPolicy = "forever" | "90d" | "30d";

/** The full editable settings row (mirrors api/models.py OrgSettings) --
 * admin-only view; regular users get PublicOrgSettings instead. `conflict`
 * is true when this response's write clobbered a change the caller hadn't
 * seen yet (last-write-wins still applies the write; the UI toasts). */
export interface OrgSettings {
  client_id: string;
  name: string;
  logo_path: string | null;
  timezone: string;
  currency: string;
  number_format: string;
  default_language: "en" | "he";
  retention_policy: RetentionPolicy;
  updated_at: string;
  conflict: boolean;
  // The retention sweep's last run for this client -- null when it has
  // never run yet (fresh install).
  last_retention_run_at: string | null;
  last_retention_deleted_count: number | null;
  last_retention_status: "ok" | "error" | null;
  last_retention_error: string | null;
}

export interface OrgSettingsUpdatePatch {
  name?: string;
  timezone?: string;
  currency?: string;
  number_format?: string;
  default_language?: "en" | "he";
  retention_policy?: RetentionPolicy;
  expected_updated_at?: string;
}

/** One entry in the currency catalog (mirrors api/models.py CurrencyInfo). */
export interface CurrencyInfo {
  code: string;
  symbol: string;
  position: "prefix" | "suffix";
}

export interface RetentionPreview {
  policy: RetentionPolicy;
  conversations_to_delete: number;
}

// --- admin: semantic model (Draft -> Validate -> Publish) ------------------
// Mirrors api/models.py's semantic-model section. `is_draft`/`is_new` are
// server-derived: an item overlaid with the caller's own in-progress draft.
export type SemanticStatus = "certified" | "draft" | "deprecated";
export type SemanticSection = "metric" | "rule" | "knowledge" | "glossary";
export type SemanticFormat = "currency" | "number" | "percent" | "text";

export interface SemanticMetricItem {
  name: string;
  label: string;
  description: string;
  sql: string;
  status: SemanticStatus;
  synonyms: string[];
  format: SemanticFormat | null;
  is_draft: boolean;
  is_new: boolean;
  validated: boolean;
}

export interface SemanticRuleItem {
  name: string;
  definition: string;
  logic: string | null;
  applies_to: string[];
  status: SemanticStatus;
  is_draft: boolean;
  is_new: boolean;
  validated: boolean;
}

export interface SemanticDateRange {
  start: string | null;
  end: string | null;
}

export interface SemanticKnowledgeItem {
  name: string;
  type: "recurring_event" | "incident" | "note";
  date_range: SemanticDateRange | null;
  recurrence: string | null;
  description: string;
  affects: string[];
  is_draft: boolean;
  is_new: boolean;
  validated: boolean;
}

export interface SemanticGlossaryItem {
  term: string;
  maps_to: string;
  language: string | null;
  is_draft: boolean;
  is_new: boolean;
  validated: boolean;
}

export interface SemanticModelResponse {
  published_version: number;
  draft_count: number;
  metrics: SemanticMetricItem[];
  rules: SemanticRuleItem[];
  knowledge: SemanticKnowledgeItem[];
  glossary: SemanticGlossaryItem[];
}

export interface SemanticValidateResult {
  ok: boolean;
  value: unknown;
  row_count: number | null;
  duration_ms: number | null;
  period_label: string | null;
  message: string | null;
  error: string | null;
}

export interface SemanticVersion {
  id: string;
  version: number;
  changed_items: string[];
  author: string | null;
  created_at: string;
}

/** Loose payload shape for a draft's edited fields -- deliberately not typed
 * per-section (metric vs rule vs knowledge vs glossary all differ); the
 * server validates required fields per section. */
export type SemanticDraftData = Record<string, unknown>;

// --- schema (mirrors api/models.py SchemaResponse) -- backs the admin
// panel's read-only Entities tab, which is derived entirely from this rather
// than a hand-authored entities.yaml.
export interface SchemaColumn {
  name: string;
  type: string;
}

export type DataSourceType = "postgres" | "priority" | "salesforce";

export interface SchemaTable {
  name: string;
  columns: SchemaColumn[];
  /** Which connector type this entity's rows come from (spec §4.4) -- shown
   * as a badge in the Entities tab. */
  source: DataSourceType;
}

export interface SchemaResponse {
  client_id: string;
  tables: SchemaTable[];
  relationships: Record<string, unknown>[];
}

// --- admin: data sources (spec §4, view-only slice) -------------------------
export interface DataSourceEntity {
  name: string;
  dependent_metrics: string[];
}

export type DataSourceStatus = "healthy" | "error" | "syncing" | "paused";

/** One status card (mirrors api/models.py DataSource). Read-only: no
 * credentials, no connection editing, no manual sync trigger. */
export interface DataSource {
  id: string;
  /** Any connector catalog id (not just the original 3) once the add-flow
   * (data_sources_add_prompt.md) is live. */
  type: string;
  display_name: string;
  status: DataSourceStatus;
  last_sync_at: string | null;
  sync_duration_ms: number | null;
  data_age_days: number | null;
  primary_table: string | null;
  primary_date_field: string | null;
  entities: DataSourceEntity[];
  origin: "config" | "connection" | "request" | "upload";
  progress_step: "requested" | "configuring" | "testing" | "active" | "rejected" | null;
  fingerprint: string | null;
}

export interface ReportProblemResponse {
  reported: boolean;
  source_id: string;
  audit_event_id: string;
}

// --- admin: data sources add-flow (data_sources_add_prompt.md) --------------
export interface ConnectorCatalogItem {
  id: string;
  kind: "sql_db" | "saas_request" | "light";
  label: string;
  unlocks: Record<string, string>;
  availability: "available" | "coming_soon" | "driver_pending";
}

export type SqlConnectorType = "postgres" | "mysql" | "mssql";

export interface TestConnectionRequest {
  connector_type: SqlConnectorType;
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
  ssl_enabled: boolean;
}

export interface TestConnectionResponse {
  ok: boolean;
  tables: string[];
  write_access: boolean | null;
  error: string | null;
  readonly_user_sql: string | null;
}

export interface CreateConnectionRequest extends TestConnectionRequest {
  display_name: string;
  primary_table?: string | null;
  primary_date_field?: string | null;
  write_access_acknowledged: boolean;
}

export interface ClientConnectionInfo {
  id: string;
  connector_type: string;
  display_name: string;
  host: string;
  port: number;
  database_name: string;
  username: string;
  ssl_enabled: boolean;
  fingerprint: string;
  primary_table: string | null;
  primary_date_field: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface SourceRequestCreate {
  connector_type: string;
  details: Record<string, string>;
}

export interface SourceRequestInfo {
  id: string;
  connector_type: string;
  details: Record<string, unknown>;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface InterestResponse {
  recorded: boolean;
  connector_type: string;
}

export interface UploadColumnPlan {
  source_name: string;
  column_name: string;
  sql_type: string;
}

export interface UploadInfo {
  id: string;
  table_name: string;
  original_filename: string;
  columns: UploadColumnPlan[];
  row_count: number;
}

export interface SheetsInfo {
  sa_email: string | null;
}

// --- admin: audit log (spec §3) ---------------------------------------------
/** One append-only row (mirrors api/models.py AuditEvent). `action` is a
 * canonical dotted id ("user.role_changed", "semantic.published", ...) --
 * see lib/auditSentences.ts for how it becomes the table's human-readable
 * sentence + category tag. `before`/`after` back the drawer's diff. */
export interface AuditEvent {
  id: string;
  client_id: string;
  actor_id: string | null;
  actor_name: string | null;
  actor_role: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  target_label: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
  /** Set only when this action happened while the real admin was
   * impersonating `actor_name` (impersonation_prompt.md) -- e.g. rendered as
   * "Dana Levi (via Miri Levi)". Null for every event outside impersonation. */
  impersonator_id: string | null;
  impersonator_name: string | null;
}

export interface AuditEventList {
  events: AuditEvent[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditFilters {
  actor?: string;
  category?: string;
  date_from?: string;
  date_to?: string;
  q?: string;
  page?: number;
}

function auditQuery(filters: AuditFilters): string {
  const params = new URLSearchParams();
  if (filters.actor) params.set("actor", filters.actor);
  if (filters.category) params.set("category", filters.category);
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  if (filters.q) params.set("q", filters.q);
  if (filters.page) params.set("page", String(filters.page));
  return params.toString();
}

export const api = {
  health: () => getJSON<Health>("/api/health"),
  clients: () => getJSON<Client[]>("/api/clients"),
  /** Public (non-admin) org settings: sidebar name/logo + shared display
   * formatting -- every user fetches this, not just admins. */
  orgSettings: (clientId: string) =>
    getJSON<PublicOrgSettings>(`/api/org-settings?client_id=${encodeURIComponent(clientId)}`),
  alerts: (clientId: string) => getJSON<Alert[]>(`/api/alerts?client_id=${encodeURIComponent(clientId)}`),
  popularQuestions: (clientId: string) =>
    getJSON<PopularQuestion[]>(`/api/popular-questions?client_id=${encodeURIComponent(clientId)}`),
  overview: (clientId: string, start?: string, end?: string) => {
    const params = new URLSearchParams({ client_id: clientId });
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    return getJSON<Overview>(`/api/overview?${params}`);
  },
  /** Unlike overview(), NOT period-scoped: the brief always describes "since
   * yesterday", independent of whatever month range the KPI cards show. */
  brief: (clientId: string) => getJSON<DailyBrief>(`/api/brief?client_id=${encodeURIComponent(clientId)}`),
  chat: (
    question: string,
    history: Message[],
    clientId: string,
    signal?: AbortSignal,
    drillContext?: DrillContextPayload,
    conversationId?: string | null,
    // Anchor for a drill-down THREAD: the turn (within conversationId, the
    // PARENT conversation) this widget's answer belongs to. Only meaningful
    // together with drillContext + conversationId; omit for the main chat and
    // for anchor-less drills (the home dashboard).
    turnIndex?: number,
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
        turn_index: turnIndex ?? null,
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
    turnIndex?: number,
  ): Promise<ChatResponse> => {
    const res = await fetch(`${BASE}/api/chat/stream`, {
      method: "POST",
      headers: withAccessKeyHeader({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        question,
        history,
        client_id: clientId,
        drill_context: drillContext ?? null,
        conversation_id: conversationId ?? null,
        turn_index: turnIndex ?? null,
      }),
      signal,
    });
    if (!res.ok || !res.body) {
      checkUnauthorized(res);
      throw new Error(`${res.status} ${res.statusText}`);
    }

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
  conversations: (clientId: string, includeArchived = false) =>
    getJSON<ConversationSummary[]>(
      `/api/conversations?${clientQuery(clientId, includeArchived ? { include_archived: "true" } : undefined)}`,
    ),
  conversation: (id: string, clientId: string) =>
    getJSON<ConversationDetail>(`/api/conversations/${id}?${clientQuery(clientId)}`),
  updateConversation: (
    id: string,
    clientId: string,
    patch: { title?: string; pinned?: boolean; archived?: boolean },
  ) => sendJSON<ConversationSummary>("PATCH", `/api/conversations/${id}?${clientQuery(clientId)}`, patch),
  deleteConversation: (id: string, clientId: string) =>
    sendJSON<null>("DELETE", `/api/conversations/${id}?${clientQuery(clientId)}`),

  // --- per-answer feedback (answer_feedback_prompt.md) ---
  // `rating: null` clears an existing rating and resolves to `null`.
  sendFeedback: (req: { conversation_id: string; turn_index: number; rating: "up" | "down" | null; comment?: string; client_id: string }) =>
    postJSON<TurnFeedback | null>("/api/feedback", req),

  // --- full-data CSV export (full_data_export_prompt.md) ---
  // Re-runs the query bound to one turn's table on the server, WITHOUT the
  // on-screen display cap -- by reference (conversation + turn) only, never
  // by sending SQL. Returns the CSV as a Blob plus the server-chosen
  // filename (parsed from Content-Disposition, question-derived + dated) so
  // the caller only has to trigger the browser download, same as the
  // existing client-side exportCsv already does for the capped case.
  exportTableCsv: async (
    conversationId: string,
    turnIndex: number,
    clientId: string,
  ): Promise<{ blob: Blob; filename: string; ceilingHit: boolean; rowCeiling: number | null }> => {
    const res = await fetch(`${BASE}/api/exports/table`, {
      method: "POST",
      headers: withAccessKeyHeader({ "Content-Type": "application/json" }),
      body: JSON.stringify({ conversation_id: conversationId, turn_index: turnIndex, client_id: clientId }),
    });
    if (!res.ok) {
      checkUnauthorized(res);
      let detail = `${res.status} ${res.statusText}`;
      try {
        const data = await res.json();
        if (typeof data?.detail === "string") detail = data.detail;
      } catch {
        // non-JSON error body -- keep the status-text fallback
      }
      throw new ApiError(res.status, detail);
    }
    const disposition = res.headers.get("content-disposition") ?? "";
    const starMatch = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
    const plainMatch = /filename="([^"]+)"/i.exec(disposition);
    const filename = starMatch
      ? decodeURIComponent(starMatch[1])
      : (plainMatch?.[1] ?? "sema-export.csv");
    const ceilingHit = res.headers.get("x-export-ceiling-hit") === "true";
    const rowCeilingHeader = res.headers.get("x-export-row-ceiling");
    const rowCeiling = rowCeilingHeader ? Number(rowCeilingHeader) : null;
    const blob = await res.blob();
    return { blob, filename, ceilingHit, rowCeiling };
  },

  // --- drill-down threads (widget-anchored, never in the sidebar) ---
  threads: (conversationId: string, clientId: string) =>
    getJSON<ThreadSummary[]>(
      `/api/conversations/${conversationId}/threads?${clientQuery(clientId)}`,
    ),
  thread: (conversationId: string, threadId: string, clientId: string) =>
    getJSON<ThreadDetail>(
      `/api/conversations/${conversationId}/threads/${threadId}?${clientQuery(clientId)}`,
    ),

  // Raw tables/columns/relationships. Backs the admin panel's Entities tab
  // (read-only, derived from the schema rather than a hand-authored file).
  // No client_id: the admin panel always acts on the mocked identity's own
  // client, which is also the server's default.
  schema: () => getJSON<SchemaResponse>("/api/schema"),

  // --- admin: users and permissions ---
  // No client_id param: the server derives the org from the current identity,
  // so a client admin can only ever act on their own organization. Mutations
  // throw ApiError (with status + detail) so the UI can show inline messages.
  admin: {
    me: () => getJSON<AdminUser>("/api/admin/me"),
    users: (opts?: { q?: string; role?: string; page?: number; page_size?: number }) => {
      const params = new URLSearchParams();
      if (opts?.q) params.set("q", opts.q);
      if (opts?.role) params.set("role", opts.role);
      if (opts?.page) params.set("page", String(opts.page));
      if (opts?.page_size) params.set("page_size", String(opts.page_size));
      const qs = params.toString();
      return getJSON<AdminUserList>(`/api/admin/users${qs ? `?${qs}` : ""}`);
    },
    invite: (email: string, role: AdminRole, dataScope?: AdminDataScope) =>
      adminRequest<AdminUser>("POST", "/api/admin/users/invite", {
        email,
        role,
        data_scope: dataScope ?? null,
      }) as Promise<AdminUser>,
    updateUser: (
      id: string,
      patch: { role?: AdminRole; status?: AdminStatus; data_scope?: AdminDataScope },
    ) => adminRequest<AdminUser>("PATCH", `/api/admin/users/${id}`, patch) as Promise<AdminUser>,
    deleteUser: (id: string) => adminRequest<null>("DELETE", `/api/admin/users/${id}`),
    resendInvite: (id: string) =>
      adminRequest<AdminUser>("POST", `/api/admin/users/${id}/resend-invite`) as Promise<AdminUser>,
    roles: () => getJSON<RoleInfo[]>("/api/admin/roles"),
    dataScopes: () => getJSON<DataScopeInfo[]>("/api/admin/data-scopes"),

    // --- admin: impersonation ("view as user") ---
    impersonation: {
      state: () => getJSON<ImpersonationState>("/api/admin/impersonation"),
      start: (userId: string) =>
        adminRequest<ImpersonationState>("POST", "/api/admin/impersonation", {
          user_id: userId,
        }) as Promise<ImpersonationState>,
      stop: () => adminRequest<ImpersonationState>("DELETE", "/api/admin/impersonation") as Promise<ImpersonationState>,
    },

    // --- admin: organization settings (spec §2) ---
    orgSettings: {
      get: () => getJSON<OrgSettings>("/api/admin/org-settings"),
      update: (patch: OrgSettingsUpdatePatch) =>
        adminRequest<OrgSettings>("PATCH", "/api/admin/org-settings", patch) as Promise<OrgSettings>,
      currencies: () => getJSON<CurrencyInfo[]>("/api/admin/org-settings/currencies"),
      timezones: () => getJSON<string[]>("/api/admin/org-settings/timezones"),
      retentionPreview: (policy: RetentionPolicy) =>
        getJSON<RetentionPreview>(`/api/admin/org-settings/retention-preview?policy=${policy}`),
      /** Multipart upload -- deliberately bypasses adminRequest, which always
       * sets Content-Type: application/json (wrong for FormData; the browser
       * must set its own multipart boundary). */
      uploadLogo: async (file: File): Promise<OrgSettings> => {
        const form = new FormData();
        form.append("file", file);
        const res = await fetch(`${BASE}/api/admin/org-settings/logo`, {
          method: "POST",
          headers: withAccessKeyHeader(),
          body: form,
        });
        if (!res.ok) {
          checkUnauthorized(res);
          let detail = `${res.status} ${res.statusText}`;
          try {
            const data = await res.json();
            if (typeof data?.detail === "string") detail = data.detail;
          } catch {
            // non-JSON error body -- keep the status-text fallback
          }
          throw new ApiError(res.status, detail);
        }
        return (await res.json()) as OrgSettings;
      },
    },

    // --- admin: semantic model (Draft -> Validate -> Publish) ---
    // No client_id here either -- same "identity implies scope" contract.
    semantic: {
      get: () => getJSON<SemanticModelResponse>("/api/admin/semantic"),
      saveDraft: (
        section: SemanticSection,
        itemKey: string,
        data: SemanticDraftData,
        action: "edit" | "create" | "deprecate" = "edit",
      ) =>
        adminRequest<SemanticModelResponse>(
          "PUT",
          `/api/admin/semantic/${section}/${encodeURIComponent(itemKey)}`,
          { data, action },
        ) as Promise<SemanticModelResponse>,
      discard: (section: SemanticSection, itemKey: string) =>
        adminRequest<SemanticModelResponse>(
          "DELETE",
          `/api/admin/semantic/${section}/${encodeURIComponent(itemKey)}`,
        ) as Promise<SemanticModelResponse>,
      validate: (section: SemanticSection, itemKey: string) =>
        adminRequest<SemanticValidateResult>("POST", "/api/admin/semantic/validate", {
          section,
          item_key: itemKey,
        }) as Promise<SemanticValidateResult>,
      publish: (items: Array<{ section: SemanticSection; item_key: string }>) =>
        adminRequest<SemanticModelResponse>("POST", "/api/admin/semantic/publish", { items }) as Promise<SemanticModelResponse>,
      versions: () => getJSON<SemanticVersion[]>("/api/admin/semantic/versions"),
      restore: (versionId: string) =>
        adminRequest<SemanticVersion>(
          "POST",
          `/api/admin/semantic/versions/${versionId}/restore`,
        ) as Promise<SemanticVersion>,
    },

    // --- admin: audit log (spec §3) ---
    audit: {
      list: (filters: AuditFilters) => {
        const qs = auditQuery(filters);
        return getJSON<AuditEventList>(`/api/admin/audit${qs ? `?${qs}` : ""}`);
      },
      /** Fetches the CSV WITH the access-key header and triggers the browser
       * download from a blob URL -- a plain `<a href>` to a protected /api/*
       * route can't carry X-API-Key, which is why this isn't just a URL the
       * caller navigates to (same rationale as exportTableCsv above). */
      download: async (filters: AuditFilters): Promise<void> => {
        const qs = auditQuery(filters);
        const res = await fetch(`${BASE}/api/admin/audit/export${qs ? `?${qs}` : ""}`, {
          headers: withAccessKeyHeader(),
        });
        if (!res.ok) {
          checkUnauthorized(res);
          throw new ApiError(res.status, `${res.status} ${res.statusText}`);
        }
        const disposition = res.headers.get("content-disposition") ?? "";
        const match = /filename="([^"]+)"/i.exec(disposition);
        const filename = match?.[1] ?? "audit-log.csv";
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      },
    },

    // --- admin: home screen customization (spec §1) ---
    homeConfig: {
      get: () => getJSON<HomeConfigResponse>("/api/admin/home-config"),
      saveDraft: (config: HomeConfig) =>
        adminRequest<HomeConfigResponse>("PUT", "/api/admin/home-config", config) as Promise<HomeConfigResponse>,
      publish: () =>
        adminRequest<HomeConfigResponse>("POST", "/api/admin/home-config/publish") as Promise<HomeConfigResponse>,
      revert: () =>
        adminRequest<HomeConfigResponse>("POST", "/api/admin/home-config/revert") as Promise<HomeConfigResponse>,
      /** POSTs the CURRENT in-memory draft (not the last-saved one) so the
       * preview never races the separate autosave debounce -- see the
       * route's own docstring. */
      preview: (config: HomeConfig) =>
        postJSON<HomeConfigPreview>("/api/admin/home-config/preview", config),
    },
    alertsCatalog: () => getJSON<AlertCatalogItem[]>("/api/admin/alerts-catalog"),

    // --- admin: template-based alert builder (alert_templates_prompt.md) ---
    alerts: {
      templates: () => getJSON<AlertTemplateCatalogItem[]>("/api/admin/alerts/templates"),
      metrics: () => getJSON<AlertMetricCatalogItem[]>("/api/admin/alerts/metrics"),
      list: () => getJSON<AlertRuleInfo[]>("/api/admin/alerts"),
      test: (req: AlertTestRequest) => postJSON<AlertTestResult>("/api/admin/alerts/test", req),
      create: (req: CreateAlertRequest) =>
        adminRequest<AlertRuleInfo>("POST", "/api/admin/alerts", req) as Promise<AlertRuleInfo>,
      update: (alertId: string, req: UpdateAlertRequest) =>
        adminRequest<AlertRuleInfo>(
          "PATCH", `/api/admin/alerts/${encodeURIComponent(alertId)}`, req,
        ) as Promise<AlertRuleInfo>,
      remove: (alertId: string) => adminRequest<null>("DELETE", `/api/admin/alerts/${encodeURIComponent(alertId)}`),
    },

    // --- admin: data sources (spec §4) ---
    dataSources: {
      list: () => getJSON<DataSource[]>("/api/admin/data-sources"),
      reportProblem: (sourceId: string) =>
        adminRequest<ReportProblemResponse>(
          "POST",
          `/api/admin/data-sources/${encodeURIComponent(sourceId)}/report-problem`,
        ) as Promise<ReportProblemResponse>,

      // --- add-flow (data_sources_add_prompt.md) ---
      catalog: () => getJSON<ConnectorCatalogItem[]>("/api/admin/data-sources/catalog"),
      sheetsInfo: () => getJSON<SheetsInfo>("/api/admin/data-sources/sheets-info"),
      test: (req: TestConnectionRequest) =>
        postJSON<TestConnectionResponse>("/api/admin/data-sources/test", req),
      createConnection: (req: CreateConnectionRequest) =>
        adminRequest<ClientConnectionInfo>(
          "POST", "/api/admin/data-sources/connections", req,
        ) as Promise<ClientConnectionInfo>,
      updateConnection: (connectionId: string, req: CreateConnectionRequest) =>
        adminRequest<ClientConnectionInfo>(
          "PATCH", `/api/admin/data-sources/connections/${encodeURIComponent(connectionId)}`, req,
        ) as Promise<ClientConnectionInfo>,
      createRequest: (req: SourceRequestCreate) =>
        adminRequest<SourceRequestInfo>(
          "POST", "/api/admin/data-sources/requests", req,
        ) as Promise<SourceRequestInfo>,
      recordInterest: (connectorType: string) =>
        adminRequest<InterestResponse>(
          "POST", "/api/admin/data-sources/interest", { connector_type: connectorType },
        ) as Promise<InterestResponse>,
      /** Multipart upload -- same rationale as orgSettings.uploadLogo above:
       * bypasses adminRequest so the browser sets its own multipart boundary. */
      upload: (file: File) => uploadFile<UploadInfo>("/api/admin/data-sources/upload", file),
      replaceUpload: (uploadId: string, file: File) =>
        uploadFile<UploadInfo>(`/api/admin/data-sources/uploads/${encodeURIComponent(uploadId)}/replace`, file),
    },
  },
};

async function uploadFile<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}${path}`, { method: "POST", headers: withAccessKeyHeader(), body: form });
  if (!res.ok) {
    checkUnauthorized(res);
    let detail = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      // non-JSON error body -- keep the status-text fallback
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}
