import type { ReactNode } from "react";
import type { Alert } from "../lib/api";
import { SEVERITY } from "../lib/tokens";

/**
 * One alert row -- same visual language wherever a triggered alert appears
 * (the executive-brief chip dropdowns, and the Daily Brief's "new alerts"
 * list). Clicking it asks SEMA about the alert (via onInvestigate).
 */
export function AlertItem({
  alert,
  onInvestigate,
  badge,
}: {
  alert: Alert;
  onInvestigate?: (a: Alert) => void;
  /** e.g. a "New" pill for an alert that appeared since the user's last visit. */
  badge?: ReactNode;
}) {
  const c = SEVERITY[alert.severity] ?? SEVERITY.warning;
  return (
    <button
      onClick={onInvestigate ? () => onInvestigate(alert) : undefined}
      disabled={!onInvestigate}
      aria-label={onInvestigate ? `Ask about ${alert.alert_label}` : undefined}
      className={`w-full text-start rounded-xl px-3 py-2.5 transition ${
        onInvestigate
          ? "cursor-pointer hover:brightness-[0.97] focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          : "cursor-default"
      }`}
      style={{ background: c.bg, borderInlineStart: `3px solid ${c.fg}` }}
    >
      <div className="flex items-center gap-2">
        <div className="text-sm font-semibold" style={{ color: c.fg }}>
          {alert.alert_label}
        </div>
        {badge}
      </div>
      <div className="text-[0.82rem] text-ink mt-0.5 leading-snug" style={{ unicodeBidi: "plaintext" }}>
        {alert.message}
      </div>
      <div className="text-[0.7rem] text-muted mt-1">{alert.metric_label}</div>
    </button>
  );
}
