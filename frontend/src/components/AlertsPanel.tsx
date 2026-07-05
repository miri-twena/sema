import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { Alert } from "../lib/api";
import { SEVERITY as SEV } from "../lib/tokens";

// Right-hand alerts rail. Collapses horizontally: closing slides it to the
// right down to a thin strip (and the main content widens to fill the space);
// opening expands it back to the left. Critical alerts in red, warnings amber.
// Clicking an alert seeds the chat with a question about it (onAlertClick).
export function AlertsPanel({ alerts, onAlertClick }: { alerts: Alert[]; onAlertClick?: (a: Alert) => void }) {
  const [open, setOpen] = useState(true);
  if (!alerts?.length) return null;

  const criticalCount = alerts.filter((a) => a.severity === "critical").length;
  const badgeColor = criticalCount > 0 ? SEV.critical.fg : SEV.warning.fg;

  const badge = (
    <span
      className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-xs font-bold text-white"
      style={{ background: badgeColor }}
    >
      {alerts.length}
    </span>
  );

  return (
    <aside
      className={`shrink-0 h-full border-l border-line bg-surface flex flex-col transition-[width] duration-200 ease-in-out ${
        open ? "w-80" : "w-12"
      }`}
    >
      {open ? (
        <>
          <button
            onClick={() => setOpen(false)}
            className="flex items-center justify-between px-4 py-4 border-b border-line hover:bg-surfaceAlt/50 transition shrink-0"
            aria-label="Collapse alerts"
          >
            <span className="flex items-center gap-2 text-sm font-semibold text-ink">
              Alerts
              {badge}
            </span>
            <ChevronRight size={18} className="text-muted" />
          </button>

          <div className="flex-1 overflow-auto sema-scroll p-3 flex flex-col gap-2">
            {alerts.map((a) => {
              const c = SEV[a.severity] ?? SEV.warning;
              return (
                <button
                  key={a.id}
                  onClick={onAlertClick ? () => onAlertClick(a) : undefined}
                  disabled={!onAlertClick}
                  aria-label={onAlertClick ? `Ask about ${a.alert_label}` : undefined}
                  className={`text-start rounded-xl px-3 py-2.5 transition ${
                    onAlertClick ? "cursor-pointer hover:brightness-[0.97] focus:outline-none focus-visible:ring-2 focus-visible:ring-primary" : "cursor-default"
                  }`}
                  style={{ background: c.bg, borderInlineStart: `3px solid ${c.fg}` }}
                >
                  <div className="text-sm font-semibold" style={{ color: c.fg }}>
                    {a.alert_label}
                  </div>
                  <div className="text-[0.82rem] text-ink mt-0.5 leading-snug" style={{ unicodeBidi: "plaintext" }}>
                    {a.message}
                  </div>
                  <div className="text-[0.7rem] text-muted mt-1">{a.metric_label}</div>
                </button>
              );
            })}
          </div>
        </>
      ) : (
        <button
          onClick={() => setOpen(true)}
          className="flex-1 flex flex-col items-center gap-3 pt-4 hover:bg-surfaceAlt/50 transition"
          aria-label="Open alerts"
          title="Open alerts"
        >
          <ChevronLeft size={18} className="text-muted" />
          {badge}
          <span className="text-xs font-semibold text-muted tracking-wide" style={{ writingMode: "vertical-rl" }}>
            Alerts
          </span>
        </button>
      )}
    </aside>
  );
}
