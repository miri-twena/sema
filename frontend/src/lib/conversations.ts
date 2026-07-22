// Pure conversation logic: turning a STORED conversation back into renderable
// turns, and bucketing the sidebar list by time. Kept out of the components so
// both can be tested without a DOM.

import type { ChatResponse, ConversationMessage, ConversationSummary, Message } from "./api";
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
    });
    history.push({ role: "user", content: m.content });
    if (answer) history.push({ role: "assistant", content: answer.content });
  }
  return { turns, history };
}

// --- sidebar time grouping ---------------------------------------------------

export type GroupId = "pinned" | "today" | "week" | "older";

export const GROUP_LABELS: Record<GroupId, string> = {
  pinned: "Pinned",
  today: "Today",
  week: "Last 7 days",
  older: "Older",
};

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
