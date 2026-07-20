import { Check, ChevronRight, Loader2, X } from "lucide-react";
import { useState } from "react";
import { isFailure, stageLabel, type ProgressEvent } from "../lib/progress";

/**
 * Live view of the agent's REAL stages. Every row is a backend event for an
 * action that actually happened -- there are no timers, percentages, or
 * predicted steps, so the panel can never claim work SEMA didn't do.
 */
export function ProgressPanel({
  events,
  dir,
}: {
  events: ProgressEvent[];
  dir: "rtl" | "ltr";
}) {
  const lang = dir === "rtl" ? "he" : "en";
  const rows = events.map((e) => ({ e, label: stageLabel(e, lang) })).filter((r) => r.label);
  if (!rows.length) return null;

  const lastIndex = rows.length - 1;
  return (
    <div dir={dir} className="px-1 py-3">
      <ul className="flex flex-col gap-1.5">
        {rows.map((r, i) => {
          const active = i === lastIndex;
          const failed = isFailure(r.e);
          return (
            <li
              key={i}
              className={`flex items-center gap-2 text-sm ${
                failed ? "text-orange-700" : active ? "text-ink" : "text-muted"
              }`}
            >
              <span className="shrink-0 w-4 flex items-center justify-center">
                {failed ? (
                  <X size={13} />
                ) : active ? (
                  <Loader2 size={13} className="animate-spin text-primary" />
                ) : (
                  <Check size={13} className="text-emerald-600" />
                )}
              </span>
              <span>{r.label}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * The same real stages, collapsed once the answer has landed. Kept separate
 * from "View SQL" -- this is what SEMA DID, not the query text.
 */
export function AnalysisDetails({
  events,
  dir,
}: {
  events: ProgressEvent[];
  dir: "rtl" | "ltr";
}) {
  const [open, setOpen] = useState(false);
  const lang = dir === "rtl" ? "he" : "en";
  const rows = events.map((e) => ({ e, label: stageLabel(e, lang) })).filter((r) => r.label);
  if (!rows.length) return null;

  return (
    <div className="mt-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-xs font-medium text-muted hover:text-primary transition"
      >
        <ChevronRight size={13} className={`transition-transform ${open ? "rotate-90" : ""}`} />
        {lang === "he" ? "פרטי הניתוח" : "Analysis details"}
      </button>
      {open && (
        <ul dir={dir} className="mt-2 flex flex-col gap-1 rounded-lg border border-line bg-surfaceAlt p-3 text-[0.78rem]">
          {rows.map((r, i) => (
            <li
              key={i}
              className={`flex items-center gap-2 ${isFailure(r.e) ? "text-orange-700" : "text-muted"}`}
            >
              <span className="shrink-0 w-3.5 flex items-center justify-center">
                {isFailure(r.e) ? <X size={11} /> : <Check size={11} className="text-emerald-600" />}
              </span>
              {r.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
