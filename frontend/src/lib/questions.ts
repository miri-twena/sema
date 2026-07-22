// Which question to offer the user next. Pure decision logic, kept out of the
// components so it can be tested directly -- both rules here are correctness
// rules (see AGENTS.md), not styling preferences.

import type { ChatResponse, PopularQuestion } from "./api";

// Backstop for the follow-up suggestion: SEMA can analyze data, but it cannot
// send email, launch campaigns, spend money, or contact people. The agent is
// already told to keep such actions out of follow_up_questions, but a stray one
// must never reach the composer -- when accepted it would just get "I can't do
// that". Any candidate mentioning real-world execution is dropped (safe: no
// suggestion beats an un-answerable one). Covers English and Hebrew.
const NOT_ANSWERABLE = [
  "launch", "send", "email", "e-mail", "campaign", "contact", "call ", "phone",
  "offer", "discount", "coupon", "promo", "invest", "budget", "spend", "hire",
  "advertise", "retarget", "notify", "reach out", "outreach", "onboard",
  "incentiv", "roll out", "deploy", "negotiate", "text ", "sms", "newsletter",
  "שלח", "שיגור", "מייל", "אימייל", "קמפיין", "השק", "השיק", "צור קשר",
  "התקשר", "הצע", "הנחה", "קופון", "השקע", "תקציב", "הוצא", "גייס",
  "פרסם", "רימרקטינג", "פנה", "מבצע", "מסר",
];

export function isAnswerable(q: string): boolean {
  const s = q.toLowerCase();
  return !NOT_ANSWERABLE.some((w) => s.includes(w));
}

/** The contextual follow-up to offer after an answer: the first of the agent's
 * dedicated follow-up QUESTIONS (things it can answer from the data), filtered
 * so nothing un-answerable slips through. Returns null when nothing qualifies,
 * so the composer shows no suggestion rather than one SEMA can't act on.
 *
 * Deliberately reads `follow_up_questions` and never `actions`: the latter is
 * business advice that often needs systems SEMA doesn't control.
 */
export function pickFollowUp(resp: ChatResponse): string | null {
  const q = resp.follow_up_questions?.find((x) => x.trim().length > 0 && isAnswerable(x));
  return q ? q.trim() : null;
}

export const MAX_OTHERS = 3;

function normalize(q: string): string {
  return q.trim().toLowerCase();
}

/** Up to MAX_OTHERS popular questions to offer under one answer, excluding the
 * one just asked.
 *
 * Consecutive answers get DIFFERENT chips by taking a window that advances with
 * the turn index, wrapping when the list runs out. Derived rather than tracked:
 * a module-level "already shown" set looks equivalent but silently fails, since
 * every card in a restored transcript mounts in the same render pass and would
 * all read the set while it is still empty.
 */
export function pickOthers(
  popular: PopularQuestion[],
  asked: string,
  turnIndex: number,
): string[] {
  const askedKey = normalize(asked);
  const candidates = popular.map((p) => p.question).filter((q) => normalize(q) !== askedKey);
  if (candidates.length === 0) return [];

  const start = (turnIndex * MAX_OTHERS) % candidates.length;
  const picked: string[] = [];
  for (let i = 0; i < Math.min(MAX_OTHERS, candidates.length); i++) {
    picked.push(candidates[(start + i) % candidates.length]);
  }
  return picked;
}
