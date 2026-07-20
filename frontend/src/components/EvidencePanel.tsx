import { CalendarDays, Info, ShieldCheck } from "lucide-react";
import type { DateRange, Evidence, Notice } from "../lib/api";
import { EV_LABELS, noticeText, sqlStatusText, stepText, type AnalysisStep, type Lang } from "../lib/evidence";

const CONFIDENCE_STYLE: Record<string, { bg: string; fg: string; label: string }> = {
  high: { bg: "#EAFBF4", fg: "#1B7A5E", label: "High confidence" },
  medium: { bg: "#FEF9C3", fg: "#CA8A04", label: "Medium confidence" },
  low: { bg: "#FEE2E2", fg: "#DC2626", label: "Low confidence" },
};

/** Small always-visible pill -- confidence is a one-glance trust signal, so
 * it isn't buried inside the collapsible Evidence section. */
export function ConfidenceBadge({ confidence }: { confidence: string | null }) {
  const style = confidence ? CONFIDENCE_STYLE[confidence] : null;
  if (!style) return null;
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[0.68rem] font-semibold"
      style={{ background: style.bg, color: style.fg }}
    >
      {style.label}
    </span>
  );
}

/** Row of subtle amber "we degraded" badges -- fallback model, self-corrected
 * SQL, or a built-in report standing in for the agent. Informative, not
 * alarming: muted amber + a small info icon, with the full explanation in the
 * native tooltip. Localized from the question's direction (Hebrew answer ->
 * Hebrew badge). Renders nothing when there are no notices (the common case). */
export function NoticeBadges({
  notices,
  dir = "ltr",
}: {
  notices: Notice[] | null | undefined;
  dir?: "rtl" | "ltr";
}) {
  if (!notices || notices.length === 0) return null;
  const lang: Lang = dir === "rtl" ? "he" : "en";
  const rendered = notices
    .map((notice) => ({ notice, text: noticeText(notice.kind, lang) }))
    .filter((x): x is { notice: Notice; text: { label: string; tip: string } } => x.text !== null);
  if (rendered.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5 mb-2">
      {rendered.map(({ notice, text }, i) => (
        <span
          key={i}
          title={text.tip}
          className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[0.68rem] font-semibold cursor-help"
          style={{ background: "#FEF3C7", color: "#B45309" }}
        >
          <Info size={11} className="shrink-0" />
          {text.label}
          {notice.kind === "sql_retried" && notice.attempts ? ` (${notice.attempts})` : ""}
        </span>
      ))}
    </div>
  );
}

/** Structural (not prose) period indicator, shown above the answer text
 * whenever the model reported a date_range -- deterministic positioning and
 * formatting beats relying on the model to remember to state it in prose.
 * Renders nothing when the question wasn't about a specific period (the
 * model is instructed to omit date_range in that case). */
export function PeriodBanner({ dateRange }: { dateRange: DateRange | null | undefined }) {
  if (!dateRange || (!dateRange.start && !dateRange.end)) return null;
  const label =
    dateRange.start && dateRange.end && dateRange.start !== dateRange.end
      ? `${dateRange.start} – ${dateRange.end}`
      : dateRange.start || dateRange.end;
  return (
    <div className="flex items-center gap-1.5 mb-2 text-[0.8rem] font-medium text-primary-dark">
      <CalendarDays size={14} className="shrink-0" />
      <span>Period: {label}</span>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 py-1">
      <span className="text-muted">{label}</span>
      <span className="text-ink">{children}</span>
    </div>
  );
}

function formatFreshness(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

/** Compact, collapsible "why should I trust this" panel -- same <details>
 * pattern as the existing "View SQL" block, so trust affordances read as one
 * family of UI rather than a bolt-on. Renders nothing if there's no evidence
 * to show (e.g. a pure-prose answer that ran no query). */
export function EvidencePanel({
  evidence,
  dir = "ltr",
}: {
  evidence: Evidence | null | undefined;
  /** Direction of the QUESTION -- drives the panel's language too, so a
   * Hebrew answer never shows an English trust panel. */
  dir?: "rtl" | "ltr";
}) {
  if (!evidence) return null;
  const lang: Lang = dir === "rtl" ? "he" : "en";
  const L = EV_LABELS[lang];
  const {
    semantic_definitions,
    date_range,
    filters_applied,
    data_sources,
    data_engine,
    database,
    data_freshness,
    records_used,
    query_status,
    queries_run,
    queries_failed,
    analysis_steps,
    assumptions,
    resolved_interpretation,
  } = evidence;
  const hasDateRange = date_range && (date_range.start || date_range.end);
  const steps = analysis_steps ?? [];
  const interpretation = resolved_interpretation ?? [];
  const hasAnything =
    semantic_definitions.length > 0 ||
    data_sources.length > 0 ||
    hasDateRange ||
    filters_applied.length > 0 ||
    data_freshness ||
    steps.length > 0 ||
    interpretation.length > 0;
  if (!hasAnything) return null;

  // Only claim execution when a query actually ran.
  const ran = query_status === "ok";
  const failed = query_status === "failed";

  return (
    <details className="mt-4">
      <summary className="cursor-pointer list-none flex items-center gap-1.5 text-xs font-medium text-muted hover:text-primary transition w-fit">
        <ShieldCheck size={14} /> {L.evidence}
      </summary>
      <div
        dir={dir}
        className="mt-2 rounded-lg border border-line bg-surfaceAlt p-3 text-[0.78rem] leading-relaxed"
      >
        {semantic_definitions.length > 0 && (
          <Row label={L.definition}>{semantic_definitions.join(", ")}</Row>
        )}

        {/* The actual connection the tables came from. Engine + database NAME
         * only -- host, user and credentials must never reach the UI. */}
        {(data_engine || database) && (
          <Row label={L.connection}>
            <span dir="ltr">{[data_engine, database].filter(Boolean).join(" · ")}</span>
          </Row>
        )}
        {data_sources.length > 0 ? (
          <Row label={L.sources}>
            <span dir="ltr">{data_sources.join(", ")}</span>
          </Row>
        ) : (
          ran && <Row label={L.sources}>{L.unavailable}</Row>
        )}

        {hasDateRange && (
          <Row label={L.dateRange}>
            <span dir="ltr">
              {date_range?.start ?? "?"} – {date_range?.end ?? "?"}
            </span>
          </Row>
        )}
        {filters_applied.length > 0 && (
          <Row label={L.filters}>
            <span dir="ltr">{filters_applied.join("; ")}</span>
          </Row>
        )}

        {/* Transparency line of the clarification flow: how an otherwise-
         * ambiguous part of the question was read (governed default or a
         * resolved clarification), so the user can verify it. Labels/values
         * arrive already in the user's language from the model. */}
        {interpretation.length > 0 && (
          <div className="mt-2 pt-2 border-t border-lineSoft">
            <div className="text-muted mb-1">{L.interpretation}</div>
            {interpretation.map((it, i) => (
              <Row key={`interp-${i}`} label={it.label}>
                {it.value}
              </Row>
            ))}
          </div>
        )}

        {/* Execution facts -- server-computed, never model-asserted. */}
        {query_status && query_status !== "none" && (
          <Row label={L.sqlStatus}>
            <span className={failed ? "text-orange-700" : "text-emerald-700"}>
              {sqlStatusText(query_status, queries_run ?? 0, queries_failed ?? 0, lang)}
            </span>
          </Row>
        )}
        {ran && typeof records_used === "number" && (
          <Row label={L.rows}>{records_used.toLocaleString()}</Row>
        )}

        {/* Labelled as query time, not "last refresh" -- SEMA has no warehouse
         * refresh signal and must not imply one. */}
        {data_freshness && <Row label={L.queriedAt}>{formatFreshness(data_freshness)}</Row>}

        <Row label={L.assumptions}>
          {assumptions && assumptions.length > 0 ? assumptions.join("; ") : L.noAssumptions}
        </Row>

        {steps.length > 0 && (
          <div className="mt-2 pt-2 border-t border-lineSoft">
            <div className="text-muted mb-1">{L.checked}</div>
            <ol className="list-decimal ps-4 text-ink flex flex-col gap-0.5">
              {steps.map((s, i) => {
                const text = stepText(s as AnalysisStep, lang);
                return text ? <li key={i}>{text}</li> : null;
              })}
            </ol>
          </div>
        )}
      </div>
    </details>
  );
}
