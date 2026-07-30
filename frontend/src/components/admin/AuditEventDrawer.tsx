import { useEffect } from "react";
import { X } from "lucide-react";
import type { AuditEvent } from "../../lib/api";
import { useDismiss } from "../../hooks/useDismiss";
import { useFocusTrap } from "../../hooks/useFocusTrap";
import { initials, pastelFor } from "../../lib/avatar";
import { auditCategoryLabel, auditSentence, isImpersonationEvent } from "./auditSentences";

function prettify(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** Field-by-field before/after diff (spec §3 item 9). Renders the union of
 * keys across both sides -- a create-only event (e.g. user.invited) has no
 * `before`, so that column just reads "—" throughout. */
function DiffTable({ before, after }: { before: AuditEvent["before"]; after: AuditEvent["after"] }) {
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]));
  if (keys.length === 0) {
    return <p className="text-[0.82rem] text-muted">No field-level details recorded for this event.</p>;
  }
  return (
    <table className="w-full text-[0.8rem]">
      <thead>
        <tr className="text-[0.68rem] font-semibold uppercase tracking-wide text-faint border-b border-line">
          <th className="text-start py-1.5 pe-2 font-semibold">Field</th>
          <th className="text-start py-1.5 pe-2 font-semibold">Before</th>
          <th className="text-start py-1.5 font-semibold">After</th>
        </tr>
      </thead>
      <tbody>
        {keys.map((k) => (
          <tr key={k} className="border-b border-lineSoft last:border-0">
            <td className="py-1.5 pe-2 text-muted align-top">{prettify(k)}</td>
            <td className="py-1.5 pe-2 text-ink align-top" dir="auto">
              {formatValue(before?.[k])}
            </td>
            <td className="py-1.5 text-ink align-top" dir="auto">
              {formatValue(after?.[k])}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * Row-detail drawer for one audit event: sentence header, actor/category
 * metadata, and the field-by-field before/after diff. Same edge-anchored
 * overlay skeleton as UserDetailDrawer.tsx (backdrop + useDismiss + Escape +
 * useFocusTrap). Impersonation events get an amber start-side bar (spec §3
 * item 9) -- the event type exists even though nothing emits it yet.
 */
export function AuditEventDrawer({ event, onClose }: { event: AuditEvent; onClose: () => void }) {
  const ref = useDismiss<HTMLElement>(true, onClose);
  useFocusTrap(ref, true);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const [bg, fg] = pastelFor(event.actor_id || event.actor_name || "system");
  const impersonation = isImpersonationEvent(event.action);
  const when = new Date(event.created_at);
  const whenLabel = Number.isNaN(when.getTime())
    ? event.created_at
    : when.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

  return (
    <>
      <div
        className="fixed inset-0 bg-ink/20 z-40 animate-[sema-fade-in_0.2s_ease-out]"
        onClick={onClose}
        aria-hidden
      />
      <aside
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="audit-detail-sentence"
        className={`fixed top-0 end-0 h-full w-[420px] max-w-[92vw] bg-bg border-s ${
          impersonation ? "border-s-4 border-s-warning-fg" : ""
        } border-line shadow-pop z-50 flex flex-col animate-[sema-slide-in-end_0.2s_ease-out]`}
      >
        <header className="flex items-center justify-between gap-3 px-5 py-4 border-b border-line bg-surface shrink-0">
          <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">
            Audit event
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 w-8 h-8 rounded-lg text-muted hover:bg-surfaceAlt hover:text-ink flex items-center justify-center transition"
          >
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-auto sema-scroll px-5 py-5">
          <div className="flex items-center gap-3">
            <span
              aria-hidden
              className="shrink-0 inline-flex items-center justify-center w-10 h-10 rounded-full text-[0.85rem] font-semibold"
              style={{ background: bg, color: fg }}
            >
              {initials(event.actor_name || "?")}
            </span>
            <div className="min-w-0">
              <div className="text-[0.85rem] font-semibold text-ink truncate" dir="auto">
                {event.actor_name || "System"}
              </div>
              <div className="text-[0.75rem] text-muted">{whenLabel}</div>
            </div>
          </div>

          <p id="audit-detail-sentence" className="mt-4 text-[0.9rem] text-ink leading-snug" dir="auto">
            {auditSentence(event, "ltr")}
          </p>

          <div className="mt-3 flex items-center gap-2 flex-wrap">
            <span className="inline-flex items-center rounded-full bg-surfaceAlt px-2 py-0.5 text-[0.68rem] font-medium text-muted">
              {auditCategoryLabel(event.action, "ltr")}
            </span>
            {impersonation && (
              <span className="inline-flex items-center rounded-full bg-warning-bg px-2 py-0.5 text-[0.68rem] font-semibold text-warning-fg">
                Impersonation
              </span>
            )}
            <span className="text-[0.7rem] text-faint font-mono">{event.action}</span>
          </div>

          {event.target_label && (
            <div className="mt-4">
              <div className="text-[0.68rem] font-semibold uppercase tracking-wide text-faint mb-1">
                Target
              </div>
              <div className="text-[0.85rem] text-ink" dir="auto">
                {event.target_label}
                {event.target_type && <span className="text-muted"> ({event.target_type})</span>}
              </div>
            </div>
          )}

          <div className="mt-5">
            <div className="text-[0.68rem] font-semibold uppercase tracking-wide text-faint mb-2">
              What changed
            </div>
            <DiffTable before={event.before} after={event.after} />
          </div>
        </div>
      </aside>
    </>
  );
}
