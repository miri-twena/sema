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

export type Lang = "he" | "en";

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

// Labels for the MERGED "queries" stage (see mergeEvents below) -- these never
// name a specific query index or row count. A single query in flight reads as
// plain "fetching"; more than one collapses to a done/total counter instead of
// naming each one, which is exactly the noise the merge exists to remove.
const QUERY_GROUP_LABELS: Record<
  Lang,
  { fetching: string; running: (done: number, total: number) => string; retrying: string; failed: string }
> = {
  en: {
    fetching: "Fetching data…",
    running: (done, total) => `Running queries (${done}/${total})`,
    retrying: "retrying…",
    failed: "Couldn't fetch the data",
  },
  he: {
    fetching: "שולפת נתונים…",
    running: (done, total) => `מריצה שאילתות (${done}/${total})`,
    retrying: "מנסה שוב…",
    failed: "לא הצלחתי לשלוף את הנתונים",
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

// --- merged stages (compact progress indicator) ------------------------------

export type StageState = "active" | "retrying" | "done" | "failed";

export interface MergedStage {
  /** Stable across re-renders of the SAME logical stage (used as a React key
   * and to detect "this is still the stage that was active a moment ago"). */
  key: string;
  state: StageState;
  label: string;
}

const QUERY_FAMILY = new Set(["run_sql", "run_sql_done", "run_sql_error"]);

/** Per-query-index bookkeeping for the run_sql family while it's the group
 * currently being merged -- reset whenever a different stage interrupts it. */
interface QueryGroup {
  seenIndices: Set<number>;
  doneIndices: Set<number>;
  failedIndices: Set<number>; // latest event for this index was an error
  everFailedIndices: Set<number>; // failed at LEAST once (drives "retrying")
  runningIndex: number | null; // latest event was run_sql (still in flight)
}

function newQueryGroup(): QueryGroup {
  return {
    seenIndices: new Set(),
    doneIndices: new Set(),
    failedIndices: new Set(),
    everFailedIndices: new Set(),
    runningIndex: null,
  };
}

function applyQueryEvent(group: QueryGroup, e: ProgressEvent): void {
  const idx = e.index ?? 1;
  group.seenIndices.add(idx);
  if (e.stage === "run_sql") {
    group.runningIndex = idx;
    group.failedIndices.delete(idx); // a retry (or first run) is now in flight
  } else if (e.stage === "run_sql_done") {
    group.doneIndices.add(idx);
    group.failedIndices.delete(idx);
    if (group.runningIndex === idx) group.runningIndex = null;
  } else if (e.stage === "run_sql_error") {
    group.failedIndices.add(idx);
    group.everFailedIndices.add(idx);
    if (group.runningIndex === idx) group.runningIndex = null;
  }
}

function queryGroupStage(group: QueryGroup, lang: Lang): { state: StageState; label: string } {
  const t = QUERY_GROUP_LABELS[lang];
  const unresolvedFailure = group.failedIndices.size > 0 && group.runningIndex === null;
  if (unresolvedFailure) return { state: "failed", label: t.failed };
  if (group.runningIndex !== null && group.everFailedIndices.has(group.runningIndex)) {
    return { state: "retrying", label: t.retrying };
  }
  const total = group.seenIndices.size;
  if (total > 1) return { state: "active", label: t.running(group.doneIndices.size, total) };
  return { state: "active", label: t.fetching };
}

/**
 * Collapses the raw, one-row-per-backend-event stream into a short sequence
 * of STAGES: every run/complete/fail of the same query merges into a single
 * "queries" stage (a retry replays as the same stage flipping between
 * retrying/failed/done, never a new row), and a run of several DIFFERENT
 * queries collapses into one "Running queries (n/total)" stage instead of a
 * line per query. Non-query stages (understanding, semantic, schema, writing)
 * still merge consecutive repeats of themselves, but otherwise pass through.
 *
 * Only the LAST entry can still be "active"/"retrying"/"failed" -- every
 * earlier entry is settled to "done" the moment a different stage begins,
 * since we now know that stage is finished.
 */
export function mergeEvents(events: ProgressEvent[], lang: Lang): MergedStage[] {
  const merged: MergedStage[] = [];
  let group: QueryGroup | null = null; // non-null while merging a run of query events
  let plainKey: string | null = null; // non-null while merging a run of the SAME plain stage

  function settleLast(): void {
    const last = merged[merged.length - 1];
    if (last && last.state === "active") last.state = "done";
  }

  for (const e of events) {
    if (e.stage && QUERY_FAMILY.has(e.stage)) {
      if (!group) {
        settleLast();
        group = newQueryGroup();
        plainKey = null;
        merged.push({ key: `queries-${merged.length}`, state: "active", label: "" });
      }
      applyQueryEvent(group, e);
      const { state, label } = queryGroupStage(group, lang);
      const entry = merged[merged.length - 1];
      entry.state = state;
      entry.label = label;
      continue;
    }

    const key = e.stage ?? "message";
    if (key !== plainKey) {
      settleLast();
      group = null;
      plainKey = key;
      merged.push({ key: `${key}-${merged.length}`, state: "active", label: "" });
    }
    const label = stageLabel(e, lang);
    if (label) merged[merged.length - 1].label = label;
  }

  return merged;
}
