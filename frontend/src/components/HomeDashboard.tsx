import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  Lightbulb,
  MessageSquareText,
  ShieldAlert,
} from "lucide-react";
import type { Alert, Overview } from "../lib/api";
import type { DrillContext } from "./DrillChat";
import { KpiCards } from "./KpiCards";
import { Card } from "./ui/Card";
import { KPI_TINTS, SEVERITY } from "../lib/tokens";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

/** "2026-05" -> "May 2026". Month keys are UTC-safe by construction. */
function monthLabel(key: string): string {
  const [y, m] = key.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function periodLabel(start: string, end: string): string {
  return start === end ? monthLabel(end) : `${monthLabel(start)} – ${monthLabel(end)}`;
}

/** Close-on-outside-click + Escape for a popover. Returns the ref to put on
 * the popover's wrapper (trigger + panel together). */
function useDismiss(active: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!active) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [active, onClose]);
  return ref;
}

function SectionLabel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={`text-[0.7rem] font-semibold uppercase tracking-wide text-muted ${className ?? "mb-2"}`}>
      {children}
    </div>
  );
}

/** Executive-brief chip: a pill button that toggles a dropdown with the
 * details behind its number (alert list / system status). */
function BriefChip({
  bg,
  fg,
  icon,
  label,
  open,
  onToggle,
  children,
}: {
  bg: string;
  fg: string;
  icon: ReactNode;
  label: ReactNode;
  open: boolean;
  onToggle: () => void;
  children: ReactNode; // dropdown content
}) {
  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-haspopup="true"
        className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition hover:brightness-[0.97] focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        style={{ background: bg, color: fg }}
      >
        {icon}
        {label}
        <ChevronDown size={12} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute start-0 top-full mt-2 w-80 max-w-[80vw] z-20 rounded-xl2 border border-line bg-surface shadow-pop p-2 flex flex-col gap-2">
          {children}
        </div>
      )}
    </span>
  );
}

/** One alert inside a chip dropdown -- same visual language as the alerts
 * rail; clicking it asks SEMA about the alert (via onInvestigate). */
function AlertItem({ alert, onInvestigate }: { alert: Alert; onInvestigate?: (a: Alert) => void }) {
  const c = SEVERITY[alert.severity] ?? SEVERITY.warning;
  return (
    <button
      onClick={onInvestigate ? () => onInvestigate(alert) : undefined}
      disabled={!onInvestigate}
      aria-label={onInvestigate ? `Ask about ${alert.alert_label}` : undefined}
      className={`text-start rounded-xl px-3 py-2.5 transition ${
        onInvestigate
          ? "cursor-pointer hover:brightness-[0.97] focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          : "cursor-default"
      }`}
      style={{ background: c.bg, borderInlineStart: `3px solid ${c.fg}` }}
    >
      <div className="text-sm font-semibold" style={{ color: c.fg }}>
        {alert.alert_label}
      </div>
      <div className="text-[0.82rem] text-ink mt-0.5 leading-snug" style={{ unicodeBidi: "plaintext" }}>
        {alert.message}
      </div>
      <div className="text-[0.7rem] text-muted mt-1">{alert.metric_label}</div>
    </button>
  );
}

const PRESETS = [
  { label: "Last month", months: 1 },
  { label: "Last 3 months", months: 3 },
  { label: "Last 6 months", months: 6 },
  { label: "Last 12 months", months: 12 },
];

function MonthSelect({
  value,
  options,
  onChange,
  label,
}: {
  value: string;
  options: string[];
  onChange: (v: string) => void;
  label: string;
}) {
  return (
    <select
      value={value}
      aria-label={label}
      onChange={(e) => onChange(e.target.value)}
      className="flex-1 min-w-0 rounded-lg border border-line bg-surface px-2 py-1.5 text-xs text-ink outline-none focus:border-primary transition"
    >
      {options.map((m) => (
        <option key={m} value={m}>
          {monthLabel(m)}
        </option>
      ))}
    </select>
  );
}

/**
 * Period control for the Business Overview. Months are the grain because the
 * underlying report is monthly, and only complete months are offered (the
 * server filters those). Presets are derived from the available list, so a
 * client with 4 months of data is never offered "Last 12 months".
 */
function PeriodPicker({
  available,
  start,
  end,
  onChange,
}: {
  available: string[];
  start: string;
  end: string;
  onChange: (start: string, end: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState(false);
  const close = useCallback(() => {
    setOpen(false);
    setCustom(false);
  }, []);
  const ref = useDismiss(open, close);

  const n = available.length;
  const presets = PRESETS.filter((p) => p.months <= n);

  // Which preset (if any) the current window matches -- a range must end on
  // the newest month to count as "Last N months".
  const endsAtLatest = end === available[n - 1];
  const span = available.indexOf(end) - available.indexOf(start) + 1;
  const activePreset = endsAtLatest && !custom ? span : null;

  const pick = (months: number) => {
    onChange(available[n - months], available[n - 1]);
    close();
  };

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="true"
        aria-label={`Change period (currently ${periodLabel(start, end)})`}
        className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 py-1 text-xs font-medium text-ink hover:border-primary transition focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <CalendarDays size={12} className="text-muted" />
        {periodLabel(start, end)}
        <ChevronDown size={12} className={`text-muted transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute end-0 top-full mt-2 w-60 max-w-[80vw] z-20 rounded-xl2 border border-line bg-surface shadow-pop p-1.5">
          {presets.map((p) => (
            <button
              key={p.label}
              onClick={() => pick(p.months)}
              className={`w-full text-start rounded-lg px-2.5 py-2 text-sm hover:bg-surfaceAlt transition ${
                activePreset === p.months ? "text-primary font-semibold" : "text-ink"
              }`}
            >
              {p.label}
            </button>
          ))}
          <button
            onClick={() => setCustom((c) => !c)}
            aria-expanded={custom}
            className={`w-full text-start rounded-lg px-2.5 py-2 text-sm hover:bg-surfaceAlt transition ${
              custom ? "text-primary font-semibold" : "text-ink"
            }`}
          >
            Custom range…
          </button>
          {custom && (
            <div className="mt-1.5 border-t border-line pt-2.5 px-1 pb-1">
              <div className="flex items-center gap-1.5">
                <MonthSelect
                  label="From month"
                  value={start}
                  options={available}
                  onChange={(v) => onChange(v, v > end ? v : end)}
                />
                <span className="text-xs text-muted shrink-0">–</span>
                <MonthSelect
                  label="To month"
                  value={end}
                  options={available}
                  onChange={(v) => onChange(v < start ? v : start, v)}
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** One system-status row in the health chip's dropdown. */
function StatusRow({ ok, label, detail }: { ok: boolean; label: string; detail: string }) {
  return (
    <div className="flex items-center gap-2 rounded-xl bg-surfaceAlt px-3 py-2.5">
      <span className={`w-2 h-2 rounded-full shrink-0 ${ok ? "bg-emerald-500" : "bg-red-500"}`} />
      <span className="text-sm font-medium text-ink">{label}</span>
      <span className={`ms-auto text-xs font-medium ${ok ? "text-emerald-600" : "text-red-500"}`}>{detail}</span>
    </div>
  );
}

const HEALTHY_TINT = KPI_TINTS[3]; // mint -- same pair the KPI cards use

/**
 * Proactive landing page shown while the conversation is empty: greeting,
 * executive brief (from the already-fetched alerts + health), headline KPIs
 * (from /api/overview -- the saved report library, not the agent), the top
 * alert as a recommendation centerpiece, and large conversation starters.
 * Every section hides itself when its data isn't available for this client.
 */
export function HomeDashboard({
  clientLabel,
  suggested,
  alerts,
  overview,
  dbConnected,
  agentConfigured,
  onPick,
  onDrill,
  onInvestigate,
  onPeriodChange,
}: {
  clientLabel: string;
  suggested: string[];
  alerts: Alert[];
  overview: Overview | null; // null while loading
  dbConnected: boolean;
  agentConfigured: boolean;
  onPick: (q: string) => void;
  onDrill?: (ctx: DrillContext) => void;
  onInvestigate?: (a: Alert) => void;
  onPeriodChange?: (start: string, end: string) => void;
}) {
  const criticalAlerts = alerts.filter((a) => a.severity === "critical");
  const warningAlerts = alerts.filter((a) => a.severity !== "critical");
  const top = alerts[0]; // backend sorts critical-first
  const healthy = dbConnected && agentConfigured;

  // Which brief chip's dropdown is open; closes on outside click or Escape.
  const [openChip, setOpenChip] = useState<"critical" | "watch" | "health" | null>(null);
  const closeChips = useCallback(() => setOpenChip(null), []);
  const briefRef = useDismiss(openChip !== null, closeChips);

  const toggleChip = (id: "critical" | "watch" | "health") =>
    setOpenChip((cur) => (cur === id ? null : id));
  const investigate = onInvestigate
    ? (a: Alert) => {
        setOpenChip(null);
        onInvestigate(a);
      }
    : undefined;

  return (
    <div className="py-6">
      {/* 1 — executive greeting */}
      <h2 className="text-3xl font-semibold tracking-tight text-ink">
        {greeting()}
        {clientLabel ? `, ${clientLabel}` : ""}
      </h2>
      <p className="text-sm text-muted mt-1.5">Here's what needs your attention today.</p>

      {/* 2 — today's executive brief (each chip opens a details dropdown) */}
      <div ref={briefRef} className="flex flex-wrap gap-2 mt-5">
        {criticalAlerts.length > 0 && (
          <BriefChip
            bg={SEVERITY.critical.bg}
            fg={SEVERITY.critical.fg}
            icon={<ShieldAlert size={13} />}
            label={`${criticalAlerts.length} critical alert${criticalAlerts.length > 1 ? "s" : ""}`}
            open={openChip === "critical"}
            onToggle={() => toggleChip("critical")}
          >
            {criticalAlerts.map((a) => (
              <AlertItem key={a.id} alert={a} onInvestigate={investigate} />
            ))}
          </BriefChip>
        )}
        {warningAlerts.length > 0 && (
          <BriefChip
            bg={SEVERITY.warning.bg}
            fg={SEVERITY.warning.fg}
            icon={<AlertTriangle size={13} />}
            label={`${warningAlerts.length} to watch`}
            open={openChip === "watch"}
            onToggle={() => toggleChip("watch")}
          >
            {warningAlerts.map((a) => (
              <AlertItem key={a.id} alert={a} onInvestigate={investigate} />
            ))}
          </BriefChip>
        )}
        <BriefChip
          bg={healthy ? HEALTHY_TINT[0] : dbConnected ? SEVERITY.warning.bg : SEVERITY.critical.bg}
          fg={healthy ? HEALTHY_TINT[1] : dbConnected ? SEVERITY.warning.fg : SEVERITY.critical.fg}
          icon={healthy ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
          label={healthy ? "All systems live" : dbConnected ? "AI agent offline" : "Database disconnected"}
          open={openChip === "health"}
          onToggle={() => toggleChip("health")}
        >
          <StatusRow ok={dbConnected} label="Database" detail={dbConnected ? "Connected" : "Disconnected"} />
          <StatusRow ok={agentConfigured} label="AI agent" detail={agentConfigured ? "Ready" : "Offline"} />
        </BriefChip>
      </div>

      {/* 3 — business overview (period picker in the header, so it never
          collides with a KPI card's own drill-down click) */}
      {overview === null ? (
        <section className="mt-8" aria-busy="true">
          <SectionLabel>Business overview</SectionLabel>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-24 rounded-xl bg-surfaceAlt animate-pulse" />
            ))}
          </div>
        </section>
      ) : (
        overview.kpis.length > 0 && (
          <section className="mt-8">
            <div className="flex items-center justify-between gap-3 mb-2">
              <SectionLabel className="">Business overview</SectionLabel>
              {onPeriodChange && overview.start && overview.end && overview.available_months.length > 0 && (
                <PeriodPicker
                  available={overview.available_months}
                  start={overview.start}
                  end={overview.end}
                  onChange={onPeriodChange}
                />
              )}
            </div>
            <KpiCards kpis={overview.kpis} onDrill={onDrill} />
          </section>
        )
      )}

      {/* 4 — top recommendation (centerpiece) */}
      {top && (
        <section className="mt-8">
          <SectionLabel>Top recommendation</SectionLabel>
          <Card className="relative overflow-hidden p-5">
            <div className="absolute inset-y-0 start-0 w-1 bg-gradient-to-b from-primary to-mint" />
            <div className="flex items-start gap-3.5">
              <span className="mt-0.5 shrink-0 inline-flex items-center justify-center w-9 h-9 rounded-xl bg-primary/10 text-primary">
                <Lightbulb size={18} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-ink">{top.alert_label}</div>
                <div className="text-sm text-ink mt-1 leading-relaxed" style={{ unicodeBidi: "plaintext" }}>
                  {top.message}
                </div>
                <div className="text-[0.72rem] text-muted mt-1.5">{top.metric_label}</div>
                {onInvestigate && (
                  <button
                    onClick={() => onInvestigate(top)}
                    className="mt-3.5 inline-flex items-center gap-1.5 rounded-xl bg-primary text-white text-sm font-medium px-4 py-2 hover:bg-primary/90 transition"
                  >
                    Ask SEMA why <ArrowRight size={15} />
                  </button>
                )}
              </div>
            </div>
          </Card>
        </section>
      )}

      {/* 5 — start a conversation */}
      {suggested.length > 0 && (
        <section className="mt-8">
          <SectionLabel>Start a conversation</SectionLabel>
          <p className="text-sm text-muted mb-3">Ask anything about your business — or start from one of these:</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {suggested.map((q) => (
              <button
                key={q}
                onClick={() => onPick(q)}
                className="group text-start flex items-start gap-3 rounded-xl border border-line bg-surface shadow-card px-4 py-3.5 hover:border-primary hover:-translate-y-px transition-all"
              >
                <span className="mt-0.5 shrink-0 inline-flex items-center justify-center w-6 h-6 rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-white">
                  <MessageSquareText size={13} />
                </span>
                <span className="text-sm text-ink leading-snug" dir="auto">
                  {q}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
