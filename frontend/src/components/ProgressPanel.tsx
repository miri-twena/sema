import { useEffect, useState } from "react";
import { Check, ChevronDown, Loader2, X } from "lucide-react";
import { mergeEvents, type MergedStage, type ProgressEvent } from "../lib/progress";

const EXPANDED_KEY = "sema:progress:expanded";
const REVEAL_DELAY_MS = 1500; // a stage shorter than this never gets shown at all

function loadExpanded(): boolean {
  try {
    return localStorage.getItem(EXPANDED_KEY) === "true";
  } catch {
    return false;
  }
}

/**
 * Debounces which merged stage is actually shown: a NEW stage only replaces
 * the displayed one once it's been active for REVEAL_DELAY_MS, so a query
 * that resolves in 200ms never flashes onto the line and off again. While
 * waiting out that delay, the PREVIOUS stage's key stays "revealed" so its
 * (settled) row keeps showing rather than the line going blank.
 *
 * Tracks only the stable string KEY, not the stage object -- mergeEvents
 * builds a fresh array of new objects on every render, so storing the object
 * itself in state would retrigger this effect (new reference) every render
 * and update state every time, an infinite render loop. The caller looks the
 * live stage back up from `stages` by this key, so content updates (e.g. a
 * doneCount ticking up) still show immediately without re-arming the timer.
 */
function useRevealedKey(activeKey: string | null): string | null {
  const [revealedKey, setRevealedKey] = useState<string | null>(null);

  useEffect(() => {
    if (activeKey === null) {
      setRevealedKey(null);
      return;
    }
    if (activeKey === revealedKey) return; // already revealed, nothing to schedule
    const timer = setTimeout(() => setRevealedKey(activeKey), REVEAL_DELAY_MS);
    return () => clearTimeout(timer);
    // revealedKey is intentionally excluded: it's read only to short-circuit
    // an already-revealed key, not to resubscribe when it changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeKey]);

  return revealedKey;
}

function StageIcon({ state }: { state: MergedStage["state"] }) {
  if (state === "failed") return <X size={13} />;
  if (state === "done") return <Check size={13} className="text-emerald-600" />;
  // "active" and "retrying" both read as in-progress -- the label text is
  // what tells them apart.
  return <Loader2 size={13} className="animate-spin text-primary" />;
}

function stageTextClass(state: MergedStage["state"]): string {
  if (state === "failed") return "text-orange-700";
  if (state === "done") return "text-muted";
  return "text-ink";
}

/**
 * Live view of the agent's REAL stages, merged so a retried or repeated query
 * reads as ONE line changing state rather than a stacked row per backend
 * event (see lib/progress.ts#mergeEvents). Default view is a single status
 * line; a chevron expands the full merged log, remembered across turns.
 */
export function ProgressPanel({
  events,
  dir,
}: {
  events: ProgressEvent[];
  dir: "rtl" | "ltr";
}) {
  const lang = dir === "rtl" ? "he" : "en";
  const stages = mergeEvents(events, lang);
  const activeKey = stages.length ? stages[stages.length - 1].key : null;
  const revealedKey = useRevealedKey(activeKey);
  const current = revealedKey ? stages.find((s) => s.key === revealedKey) ?? null : null;
  const [expanded, setExpanded] = useState(loadExpanded);

  useEffect(() => {
    try {
      localStorage.setItem(EXPANDED_KEY, String(expanded));
    } catch {
      /* storage unavailable */
    }
  }, [expanded]);

  if (!current) return null; // nothing has survived the reveal delay yet

  return (
    <div dir={dir} className="px-1 py-3">
      <div className="flex items-center gap-2 text-sm">
        <span className="shrink-0 w-4 flex items-center justify-center">
          <StageIcon state={current.state} />
        </span>
        <span className={`flex-1 ${stageTextClass(current.state)}`}>{current.label}</span>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          aria-label={expanded ? "Hide progress details" : "Show progress details"}
          className="shrink-0 w-5 h-5 rounded-md flex items-center justify-center text-faint hover:text-ink hover:bg-surfaceAlt transition"
        >
          <ChevronDown size={14} className={`transition-transform ${expanded ? "rotate-180" : ""}`} />
        </button>
      </div>

      {expanded && (
        <ul className="flex flex-col gap-1.5 mt-2 ps-6">
          {stages.map((s) => (
            <li key={s.key} className={`flex items-center gap-2 text-sm ${stageTextClass(s.state)}`}>
              <span className="shrink-0 w-4 flex items-center justify-center">
                <StageIcon state={s.state} />
              </span>
              <span>{s.label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
