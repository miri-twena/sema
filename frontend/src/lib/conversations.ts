// Pure conversation logic: turning a STORED conversation back into renderable
// turns, and bucketing the sidebar list by time. Kept out of the components so
// both can be tested without a DOM.

import type { ChatResponse, ConversationMessage, ConversationSummary, Message, TurnFeedback } from "./api";
import type { ProgressEvent } from "./progress";
import { dirOf } from "./rtl";

export interface ChatTurn {
  question: string;
  response: ChatResponse | null; // null while loading / stopped
  dir: "rtl" | "ltr";
  stopped?: boolean;
  /** REAL backend progress stages, in the order the server emitted them.
   * Every entry corresponds to an actual tool dispatch -- there are no
   * timer-driven or invented stages. Drives the live ProgressPanel shown while
   * the answer is streaming (cleared from view once the answer lands). */
  progress?: ProgressEvent[];
  /** This answer's thumbs up/down (answer_feedback_prompt.md), hydrated from
   * the stored transcript on reopen; undefined for a fresh (unrated, not yet
   * loaded) turn, null once explicitly cleared. */
  feedback?: TurnFeedback | null;
}

/** An answer stored before payloads were persisted (or whose payload failed to
 * parse) -> a minimal renderable response. `response: null` means "still
 * loading" to TurnView, so returning null for a turn that HAS an answer leaves
 * it spinning forever; degrading to text-only is the correct fallback. */
export function textOnlyResponse(text: string): ChatResponse {
  return {
    answer: text,
    kpis: [],
    chart: null,
    table: null,
    actions: [],
    follow_up_questions: [],
    sql_used: null,
    confidence: null,
    evidence: null,
    status: "ok",
    error: null,
  };
}

/** A stored conversation OR thread -- both are `{messages: [...]}` shaped --
 * -> the in-memory shapes the chat view renders. Pairs each user turn with the
 * assistant turn that follows it; a user turn with no answer yet still renders
 * as pending. */
export function turnsFromDetail(
  detail: { messages: ConversationMessage[] },
): { turns: ChatTurn[]; history: Message[] } {
  const turns: ChatTurn[] = [];
  const history: Message[] = [];
  const msgs = detail.messages;
  for (let i = 0; i < msgs.length; i++) {
    const m = msgs[i];
    if (m.role !== "user") continue;
    const next = msgs[i + 1];
    const answer = next && next.role === "assistant" ? next : null;
    turns.push({
      question: m.content,
      response: answer ? (answer.payload ?? textOnlyResponse(answer.content)) : null,
      dir: dirOf(m.content),
      feedback: answer?.feedback ?? null,
    });
    history.push({ role: "user", content: m.content });
    if (answer) history.push({ role: "assistant", content: answer.content });
  }
  return { turns, history };
}

/** The FIRST user question in a conversation's transcript -- what "Rerun"
 * (rerun_conversation_prompt.md) resubmits fresh in a brand-new conversation.
 * MVP scope is deliberately just this one message, not the whole turn
 * sequence: later turns often depend on earlier answers and would drift.
 * Undefined for a broken/empty conversation (no user message at all) -- the
 * caller treats that as "nothing to rerun." */
export function firstUserMessage(detail: { messages: ConversationMessage[] }): string | undefined {
  return detail.messages.find((m) => m.role === "user")?.content;
}

// --- sidebar time grouping ---------------------------------------------------

export type GroupId = "pinned" | "today" | "week" | "older";

// Display labels for these live in locales/en.ts + he.ts (sidebar.groups) --
// this module stays presentation-free, same as before, just without its own
// English-only copy now that the app has a real i18n mechanism.

export const GROUP_ORDER: GroupId[] = ["pinned", "today", "week", "older"];

/** Start of the local day, so "Today" means the calendar day the user is in,
 * not the last 24 hours. Injectable for tests. */
export function startOfToday(now: Date = new Date()): number {
  const d = new Date(now);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

/**
 * Which time bucket a conversation belongs to, from `updated_at`. Pinned wins
 * over any time bucket, so a pinned chat appears exactly once.
 *
 * An unparseable or missing timestamp falls into "Older" rather than being
 * dropped -- a chat must never vanish from the list because of a bad date.
 */
export function groupOf(c: ConversationSummary, dayStart: number): GroupId {
  if (c.pinned) return "pinned";
  const t = new Date(c.updated_at).getTime();
  if (isNaN(t)) return "older";
  if (t >= dayStart) return "today";
  if (t >= dayStart - 6 * 24 * 60 * 60 * 1000) return "week";
  return "older";
}

/** The full list split into its time buckets, preserving the server's order
 * within each (pinned first, then most recently updated). */
export function bucketConversations(
  conversations: ConversationSummary[],
  dayStart: number = startOfToday(),
): Record<GroupId, ConversationSummary[]> {
  const buckets: Record<GroupId, ConversationSummary[]> = {
    pinned: [],
    today: [],
    week: [],
    older: [],
  };
  for (const c of conversations) buckets[groupOf(c, dayStart)].push(c);
  return buckets;
}

// --- sidebar row filtering / preview cap -------------------------------------

/** Case-insensitive title match for the sidebar's client-side search box.
 * Order is preserved, so a pinned match still sorts first. */
export function filterByTitle(
  conversations: ConversationSummary[],
  query: string,
): ConversationSummary[] {
  const q = query.trim().toLowerCase();
  if (!q) return conversations;
  return conversations.filter((c) => c.title.toLowerCase().includes(q));
}

/** Default row count shown before "Show all N" -- applied to the Previous 7
 * days group only; Pinned and Today are always shown in full. */
export const PREVIEW_LIMIT = 4;

/** Which rows a capped group should render: `expanded` (user clicked "Show
 * all") always returns everything, otherwise the first `limit` rows. */
export function previewSplit<T>(
  items: T[],
  expanded: boolean,
  limit: number = PREVIEW_LIMIT,
): { shown: T[]; remaining: number } {
  if (expanded || items.length <= limit) return { shown: items, remaining: 0 };
  return { shown: items.slice(0, limit), remaining: items.length - limit };
}
