import { ShieldCheck } from "lucide-react";
import type { Evidence } from "../lib/api";

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
export function EvidencePanel({ evidence }: { evidence: Evidence | null | undefined }) {
  if (!evidence) return null;
  const { semantic_definitions, date_range, filters_applied, data_sources, data_freshness, records_used } = evidence;
  const hasDateRange = date_range && (date_range.start || date_range.end);
  const hasAnything =
    semantic_definitions.length > 0 ||
    data_sources.length > 0 ||
    hasDateRange ||
    filters_applied.length > 0 ||
    data_freshness ||
    records_used != null;
  if (!hasAnything) return null;

  return (
    <details className="mt-4">
      <summary className="cursor-pointer list-none flex items-center gap-1.5 text-xs font-medium text-muted hover:text-primary transition w-fit">
        <ShieldCheck size={14} /> Evidence
      </summary>
      <div className="mt-2 rounded-lg border border-line bg-surfaceAlt p-3 text-[0.78rem] leading-relaxed">
        {semantic_definitions.length > 0 && (
          <Row label="Definition">{semantic_definitions.join(", ")}</Row>
        )}
        {data_sources.length > 0 && <Row label="Data sources">{data_sources.join(", ")}</Row>}
        {hasDateRange && (
          <Row label="Date range">
            {date_range?.start ?? "?"} – {date_range?.end ?? "?"}
          </Row>
        )}
        {filters_applied.length > 0 && <Row label="Filters">{filters_applied.join("; ")}</Row>}
        {records_used != null && <Row label="Records used">{records_used.toLocaleString()}</Row>}
        {data_freshness && <Row label="As of">{formatFreshness(data_freshness)}</Row>}
      </div>
    </details>
  );
}
