import { type ForwardedRef, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  Lightbulb,
  MessageSquareText,
  ShieldAlert,
  TrendingUp,
} from "lucide-react";
import type { Alert, DailyBrief as DailyBriefResponse, Overview, PopularQuestion } from "../lib/api";
import type { DrillContext } from "./DrillChat";
import { AlertItem } from "./AlertItem";
import { ChatInput } from "./ChatInput";
import { DailyBrief } from "./DailyBrief";
import { KpiCards } from "./KpiCards";
import { QuestionChip } from "./QuestionChip";
import { Card } from "./ui/Card";
import { usePopoverMenu } from "../hooks/usePopoverMenu";
import { useCyclingPlaceholder } from "../hooks/useCyclingPlaceholder";
import { useT } from "../locales";
import type { TranslationKeys } from "../locales";
import { PopoverMenu } from "./PopoverMenu";
import { dirOf } from "../lib/rtl";
import { useUiLang, type UiLang } from "../lib/useUiLang";
import { KPI_TINTS, SEVERITY } from "../lib/tokens";

/** Static Hebrew UI headings (home_hebrew_polish_prompt.md item 2) get
 * dir="rtl" so trailing punctuation/mixed content shape correctly (the same
 * class of bug item 6 names for the guidance line) and right-align via the
 * browser's own direction-relative default (text-align's initial value is
 * "start", not a hardcoded "left" -- no extra className needed). English
 * stays dir="ltr", left-aligned, unchanged. This is a TEXT-level concern
 * only -- it never touches page/card/grid layout (AGENTS.md's "layout is
 * anchored" rule), which is why it's just a `dir` attribute, not a mirrored
 * flex direction anywhere. */
function headingDir(lang: UiLang): "rtl" | "ltr" {
  return lang === "he" ? "rtl" : "ltr";
}

function greeting(t: TranslationKeys): string {
  const h = new Date().getHours();
  if (h < 12) return t.home.greeting.morning;
  if (h < 18) return t.home.greeting.afternoon;
  return t.home.greeting.evening;
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

/** A section heading (DAILY BRIEF / BUSINESS OVERVIEW / etc.). Reads the
 * chrome language itself (home_hebrew_polish_prompt.md item 2) so every
 * call site gets correct Hebrew direction/alignment for free. */
function SectionLabel({ children, className }: { children: ReactNode; className?: string }) {
  const lang = useUiLang();
  return (
    <div
      dir={headingDir(lang)}
      className={`text-[0.7rem] font-semibold uppercase tracking-wide text-muted ${className ?? "mb-2"}`}
    >
      {children}
    </div>
  );
}

const BRIEF_CHIP_WIDTH = 320; // w-80
const BRIEF_CHIP_EST_HEIGHT = 220;

/** Executive-brief chip: a pill button that toggles a dropdown with the
 * details behind its number (alert list / system status). Owns its own
 * popover independently (each chip can open without closing its siblings --
 * a minor, intentional simplification from the pre-portal version, which
 * forced mutual exclusion via one shared dismiss ref on the whole row; that
 * constraint added no real value and would have fought the portal's
 * per-trigger position calculation). `children` is a render-prop so content
 * (e.g. an alert's "Investigate" action) can close THIS chip's own popover
 * before navigating, without the parent needing to track which chip is
 * open. */
function BriefChip({
  bg,
  fg,
  icon,
  label,
  children,
}: {
  bg: string;
  fg: string;
  icon: ReactNode;
  label: ReactNode;
  children: (close: () => void) => ReactNode; // dropdown content
}) {
  const { open, close, toggle, triggerRef, menuRef, pos } = usePopoverMenu<HTMLButtonElement>({
    width: BRIEF_CHIP_WIDTH,
    estHeight: BRIEF_CHIP_EST_HEIGHT,
    align: "start",
  });
  return (
    <span className="relative inline-block">
      <button
        ref={triggerRef}
        type="button"
        onClick={toggle}
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
        <PopoverMenu pos={pos} menuRef={menuRef} className="rounded-xl2 max-w-[80vw] p-2 flex flex-col gap-2">
          {children(close)}
        </PopoverMenu>
      )}
    </span>
  );
}

const PRESET_MONTHS = [1, 3, 6, 12];

function presetLabel(t: TranslationKeys, months: number): string {
  switch (months) {
    case 1:
      return t.home.period.lastMonth;
    case 3:
      return t.home.period.last3Months;
    case 6:
      return t.home.period.last6Months;
    default:
      return t.home.period.last12Months;
  }
}

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
  const t = useT();
  const [custom, setCustom] = useState(false);
  const { open, close: closePopover, toggle, triggerRef, menuRef, pos } = usePopoverMenu<HTMLButtonElement>({
    width: 240, // w-60
    estHeight: 400, // generous: accounts for the "custom range" expansion
  });
  const close = () => {
    closePopover();
    setCustom(false);
  };

  const n = available.length;
  const presetMonths = PRESET_MONTHS.filter((m) => m <= n);

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
    <div className="relative shrink-0">
      <button
        ref={triggerRef}
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-haspopup="true"
        aria-label={t.home.period.changeLabel(periodLabel(start, end))}
        className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 py-1 text-xs font-medium text-ink hover:border-primary transition focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <CalendarDays size={12} className="text-muted" />
        {periodLabel(start, end)}
        <ChevronDown size={12} className={`text-muted transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <PopoverMenu pos={pos} menuRef={menuRef} className="rounded-xl2 max-w-[80vw] p-1.5">
          {presetMonths.map((months) => (
            <button
              key={months}
              onClick={() => pick(months)}
              className={`w-full text-start rounded-lg px-2.5 py-2 text-sm hover:bg-surfaceAlt transition ${
                activePreset === months ? "text-primary font-semibold" : "text-ink"
              }`}
            >
              {presetLabel(t, months)}
            </button>
          ))}
          <button
            onClick={() => setCustom((c) => !c)}
            aria-expanded={custom}
            className={`w-full text-start rounded-lg px-2.5 py-2 text-sm hover:bg-surfaceAlt transition ${
              custom ? "text-primary font-semibold" : "text-ink"
            }`}
          >
            {t.home.period.customRange}
          </button>
          {custom && (
            <div className="mt-1.5 border-t border-line pt-2.5 px-1 pb-1">
              <div className="flex items-center gap-1.5">
                <MonthSelect
                  label={t.home.period.fromMonth}
                  value={start}
                  options={available}
                  onChange={(v) => onChange(v, v > end ? v : end)}
                />
                <span className="text-xs text-muted shrink-0">–</span>
                <MonthSelect
                  label={t.home.period.toMonth}
                  value={end}
                  options={available}
                  onChange={(v) => onChange(v < start ? v : start, v)}
                />
              </div>
            </div>
          )}
        </PopoverMenu>
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
  userName,
  suggested,
  alerts,
  overview,
  brief,
  popularQuestions,
  dbConnected,
  agentConfigured,
  onPick,
  onDrill,
  onInvestigate,
  onPeriodChange,
  onAsk,
  onStopAsk,
  asking,
  askInputRef,
  autoFocusAsk,
}: {
  clientLabel: string;
  /** Signed-in person's first name (greeting_user_name_prompt.md) -- greets
   * the PERSON, not the org. Null falls back to clientLabel below (identity
   * hasn't resolved, or has no name set). */
  userName: string | null;
  suggested: string[];
  alerts: Alert[];
  overview: Overview | null; // null while loading
  brief: DailyBriefResponse | null; // null while loading; loads independently of `overview`
  /** Most-asked questions across the company; drives the trending chips. */
  popularQuestions: PopularQuestion[];
  dbConnected: boolean;
  agentConfigured: boolean;
  onPick: (q: string) => void;
  onDrill?: (ctx: DrillContext) => void;
  onInvestigate?: (a: Alert) => void;
  onPeriodChange?: (start: string, end: string) => void;
  /** Submits the prominent top-of-page ask input (home_ask_bar_top_prompt.md)
   * -- the SAME send path as the discovery chips below (`onPick`) and the
   * in-conversation composer; kept as a separate prop only because it also
   * needs `asking`/`onStopAsk` wired for the loading/stop affordance the
   * static chips don't. */
  onAsk: (q: string) => void;
  onStopAsk?: () => void;
  asking?: boolean;
  /** Imperative focus target for the "/" shortcut, owned by App.tsx (it also
   * has to know about the drill panel/mobile drawer to suppress the
   * shortcut while either is open, which this component doesn't track). */
  askInputRef?: ForwardedRef<HTMLTextAreaElement>;
  /** Focus the ask input on mount. Default false: the ONLY caller that wants
   * this is the real home screen (App.tsx) -- the admin Home-config screen's
   * read-only live preview renders this same component and must never steal
   * focus from the admin's own form fields every time the draft changes. */
  autoFocusAsk?: boolean;
}) {
  const t = useT();
  const lang = useUiLang();
  const dir = headingDir(lang);
  const criticalAlerts = alerts.filter((a) => a.severity === "critical");
  const warningAlerts = alerts.filter((a) => a.severity !== "critical");
  const top = alerts[0]; // backend sorts critical-first
  const healthy = dbConnected && agentConfigured;
  const cycling = useCyclingPlaceholder(suggested);

  return (
    <div className="py-6">
      {/* 1 — executive greeting: greets the PERSON, org name only as a
          fallback (greeting_user_name_prompt.md) -- the org still appears in
          the sidebar's own org row, never dropped, just not duplicated here. */}
      <h2 dir={dir} className="text-3xl font-semibold tracking-tight text-ink">
        {greeting(t)}
        {userName || clientLabel ? (
          <>
            {", "}
            <span dir="auto">{userName || clientLabel}</span>
          </>
        ) : (
          ""
        )}
      </h2>

      {/* 1a — guidance line (home_hebrew_polish_prompt.md item 3): tells a
          first-time user what the input right below is for. */}
      <p dir={dir} className="text-sm text-muted mt-1.5">
        {t.home.askGuidance}
      </p>

      {/* 1b — the prominent ask input (home_ask_bar_top_prompt.md): the
          SECOND thing on the page, full content width. Placeholder cycles
          through real suggested questions (never invented copy) until the
          user focuses it, at which point it stops permanently. */}
      <div className="mt-4">
        <ChatInput
          ref={askInputRef}
          onSend={onAsk}
          onStop={onStopAsk}
          loading={asking}
          variant="hero"
          autoFocus={autoFocusAsk}
          placeholder={cycling.text}
          placeholderDir={cycling.text ? dirOf(cycling.text) : undefined}
          onFocus={cycling.stop}
        />
      </div>

      {/* 1c — "Start a conversation": curated starter questions, moved here
          (home_hebrew_polish_prompt.md item 5) so a first-time user reads
          "here's what you can ask" right under the input, before the more
          operational brief/overview numbers below. Trending (what colleagues
          actually ask) stays separate, further down -- see section 6. */}
      {suggested.length > 0 && (
        <section id="home-preview-questions" className="mt-8">
          <SectionLabel>{t.home.startConversation}</SectionLabel>
          <p dir={dir} className="text-sm text-muted mb-3">
            {t.home.askAnythingPrompt}
          </p>
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

      {/* 1d — the attention line ("Here's what needs your attention today"),
          moved below the input + starter questions (home_hebrew_polish_
          prompt.md item 1) so it introduces the brief/overview cluster that
          follows it, instead of sitting disconnected above the ask input. */}
      <p dir={dir} className="text-sm text-muted mt-8">
        {t.home.subtitle}
      </p>

      {/* 2 — today's executive brief (each chip opens a details dropdown).
          `dir` on the row itself (not just its text) so the chips visually
          start from the right in Hebrew, per direct user feedback on the
          live result -- flex's own flex-start/flex-end already resolve
          against the container's direction, so this is enough to mirror the
          row without any manual reordering. */}
      <div id="home-preview-alerts" dir={dir} className="flex flex-wrap gap-2 mt-3">
        {criticalAlerts.length > 0 && (
          <BriefChip
            bg={SEVERITY.critical.bg}
            fg={SEVERITY.critical.fg}
            icon={<ShieldAlert size={13} />}
            label={t.home.briefChip.criticalAlert(criticalAlerts.length)}
          >
            {(close) =>
              criticalAlerts.map((a) => (
                <AlertItem
                  key={a.id}
                  alert={a}
                  onInvestigate={
                    onInvestigate
                      ? (alert) => {
                          close();
                          onInvestigate(alert);
                        }
                      : undefined
                  }
                />
              ))
            }
          </BriefChip>
        )}
        {warningAlerts.length > 0 && (
          <BriefChip
            bg={SEVERITY.warning.bg}
            fg={SEVERITY.warning.fg}
            icon={<AlertTriangle size={13} />}
            label={t.home.briefChip.toWatch(warningAlerts.length)}
          >
            {(close) =>
              warningAlerts.map((a) => (
                <AlertItem
                  key={a.id}
                  alert={a}
                  onInvestigate={
                    onInvestigate
                      ? (alert) => {
                          close();
                          onInvestigate(alert);
                        }
                      : undefined
                  }
                />
              ))
            }
          </BriefChip>
        )}
        <BriefChip
          bg={healthy ? HEALTHY_TINT[0] : dbConnected ? SEVERITY.warning.bg : SEVERITY.critical.bg}
          fg={healthy ? HEALTHY_TINT[1] : dbConnected ? SEVERITY.warning.fg : SEVERITY.critical.fg}
          icon={healthy ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
          label={
            healthy
              ? t.home.briefChip.allSystemsLive
              : dbConnected
                ? t.home.briefChip.aiAgentOffline
                : t.home.briefChip.databaseDisconnected
          }
        >
          {() => (
            <>
              <StatusRow
                ok={dbConnected}
                label={t.home.briefChip.database}
                detail={dbConnected ? t.workspace.connected : t.workspace.disconnected}
              />
              <StatusRow
                ok={agentConfigured}
                label={t.home.briefChip.aiAgent}
                detail={agentConfigured ? t.home.briefChip.ready : t.home.briefChip.offline}
              />
            </>
          )}
        </BriefChip>
      </div>

      {/* 3 — daily brief: a pulse strip (always-fresh yesterday numbers) plus
          up to 3 ranked attention cards -- independent of the Business
          overview's period picker below, deliberately. */}
      <div id="home-preview-daily-brief">
        <DailyBrief brief={brief} onAsk={onPick} />
      </div>

      {/* 4 — business overview (period picker in the header, so it never
          collides with a KPI card's own drill-down click) */}
      {overview === null ? (
        <section id="home-preview-overview" className="mt-8" aria-busy="true">
          <SectionLabel>{t.home.businessOverview}</SectionLabel>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-24 rounded-xl bg-surfaceAlt animate-pulse" />
            ))}
          </div>
        </section>
      ) : (
        overview.kpis.length > 0 && (
          <section id="home-preview-overview" className="mt-8">
            <div dir={dir} className="flex items-center justify-between gap-3 mb-2">
              <SectionLabel className="">{t.home.businessOverview}</SectionLabel>
              {onPeriodChange && overview.start && overview.end && overview.available_months.length > 0 && (
                <PeriodPicker
                  available={overview.available_months}
                  start={overview.start}
                  end={overview.end}
                  onChange={onPeriodChange}
                />
              )}
            </div>
            {/* No `anchor`/`threadCount` here, deliberately: these KPIs come
                from /api/overview, not from a turn in a server conversation --
                there is no conversation_id or turn_index to anchor a thread
                to. Their drill-downs stay ephemeral (no persistence, no
                badge), same as every other widget before drill-down threads
                existed. Do NOT invent a synthetic conversation for them. */}
            <KpiCards kpis={overview.kpis} onDrill={onDrill} />
          </section>
        )
      )}

      {/* 5 — top recommendation (centerpiece) */}
      {top && (
        <section className="mt-8">
          <SectionLabel>{t.home.topRecommendation}</SectionLabel>
          <Card className="relative overflow-hidden p-5">
            <div className="absolute inset-y-0 start-0 w-1 bg-gradient-to-b from-primary to-mint" />
            <div className="flex items-start gap-3.5">
              <span className="mt-0.5 shrink-0 inline-flex items-center justify-center w-9 h-9 rounded-xl bg-primary/10 text-primary">
                <Lightbulb size={18} />
              </span>
              <div className="min-w-0 flex-1 max-w-3xl">
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
                    {t.home.askSemaWhy} <ArrowRight size={15} />
                  </button>
                )}
              </div>
            </div>
          </Card>
        </section>
      )}

      {/* 6 — trending: what colleagues actually ask. Split out from the
          curated starters above (home_hebrew_polish_prompt.md item 5 moved
          only the "Start a conversation" block up front; trending stays
          down here, alongside the rest of the "what's happening" content). */}
      {popularQuestions.length > 0 && (
        <section className="mt-8">
          <div dir={dir} className="flex items-center gap-1.5 mb-2">
            <TrendingUp size={13} className="text-primary" aria-hidden />
            <SectionLabel className="mb-0">{t.home.trendingInCompany}</SectionLabel>
          </div>
          <div dir={dir} className="flex flex-wrap gap-2">
            {popularQuestions.map((p) => (
              <QuestionChip
                key={p.question}
                question={p.question}
                count={p.times_asked}
                onPick={onPick}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
