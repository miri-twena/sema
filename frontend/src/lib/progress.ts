// Progress stages arrive from the backend as KEYS plus real numbers -- never
// prose -- so the label can be rendered in the user's language and every line
// stays traceable to an actual tool dispatch.

export interface ProgressEvent {
  stage?: string;
  index?: number;
  rows?: number;
  tables?: string[];
  /** Legacy/prose fallback: rendered as-is when no stage key is present. */
  message?: string;
}

type Lang = "he" | "en";

const LABELS: Record<Lang, Record<string, (e: ProgressEvent) => string>> = {
  en: {
    semantic: () => "Matching approved metric definitions",
    schema: () => "Checking available data sources",
    run_sql: (e) => (e.index ? `Running query ${e.index}` : "Running query"),
    run_sql_done: (e) =>
      `Query ${e.index ?? 1} completed — ${(e.rows ?? 0).toLocaleString()} rows returned`,
    run_sql_error: (e) => `Query ${e.index ?? 1} failed`,
    writing: () => "Preparing the answer",
    tool: () => "Working",
  },
  he: {
    semantic: () => "מתאימה הגדרות מדדים מאושרות",
    schema: () => "בודקת אילו מקורות נתונים זמינים",
    run_sql: (e) => (e.index ? `מריצה שאילתה ${e.index}` : "מריצה שאילתה"),
    run_sql_done: (e) =>
      `שאילתה ${e.index ?? 1} הושלמה — ${(e.rows ?? 0).toLocaleString()} שורות`,
    run_sql_error: (e) => `שאילתה ${e.index ?? 1} נכשלה`,
    writing: () => "מנסחת את התשובה",
    tool: () => "עובדת",
  },
};

/** The one stage the client raises itself: the request is genuinely in flight
 * before any tool has dispatched, so this reports a real state, not a guess. */
export const UNDERSTANDING: ProgressEvent = { stage: "understanding" };

const OPENING: Record<Lang, string> = {
  en: "Understanding the business question",
  he: "מבינה את השאלה העסקית",
};

export function stageLabel(e: ProgressEvent, lang: Lang): string {
  if (e.stage === "understanding") return OPENING[lang];
  const fn = e.stage ? LABELS[lang][e.stage] : undefined;
  if (fn) return fn(e);
  // Unknown stage: fall back to any prose the server sent, else stay silent
  // rather than inventing a label for something we can't describe.
  return e.message ?? "";
}

/** A failed stage must not read as completed. */
export function isFailure(e: ProgressEvent): boolean {
  return e.stage === "run_sql_error";
}

/** Distinct data sources named across the run, in first-seen order. */
export function sourcesFrom(events: ProgressEvent[]): string[] {
  const seen: string[] = [];
  for (const e of events) for (const t of e.tables ?? []) if (!seen.includes(t)) seen.push(t);
  return seen;
}
