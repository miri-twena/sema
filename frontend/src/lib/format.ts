// Shared formatting helpers. Single source of truth for numbers/dates across
// KPI cards, charts, and tables (previously duplicated in three components).

/** 1,672,356 -> "1.67M", 824,068 -> "824.1K" -- for glanceable KPI cards. */
export function compact(n: number): string {
  const a = Math.abs(n);
  if (a >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (a >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

/** KPI value per its declared format. */
export function formatValue(value: number | string, fmt: string): string {
  if (typeof value !== "number") return String(value);
  switch (fmt) {
    case "currency":
      return `$${compact(value)}`;
    case "percent":
      return `${value.toFixed(1)}%`;
    case "number":
      return compact(value);
    case "ratio":
      return `${value.toFixed(2)}x`;
    default:
      return String(value);
  }
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}/;

/** Parse a date/month column value as UTC midnight, regardless of local
 * timezone. The backend serializes these as e.g. "2026-01-01T00:00:00.000"
 * (pandas Timestamps have no timezone info) -- `new Date(...)` on a
 * date-TIME string with no "Z"/offset is parsed as LOCAL time per spec, so
 * reading it back with getUTCDate() etc. shifts the displayed date by a day
 * in any positive-UTC-offset timezone. Truncating to the YYYY-MM-DD prefix
 * sidesteps this: a date-ONLY string IS guaranteed to parse as UTC midnight. */
function parseIsoDateUTC(v: string): Date {
  return new Date(v.slice(0, 10));
}

function isoToLabel(v: string): string {
  const d = parseIsoDateUTC(v);
  if (isNaN(d.getTime())) return v;
  // Month buckets (day === 1) read better as "Jun 2025"; otherwise full date.
  const opts: Intl.DateTimeFormatOptions =
    d.getUTCDate() === 1
      ? { month: "short", year: "numeric" }
      : { month: "short", day: "numeric", year: "numeric" };
  return d.toLocaleDateString("en", { ...opts, timeZone: "UTC" });
}

/** A raw table cell -> human string: ISO dates become "Jun 2025", numbers get
 *  thousands separators, everything else passes through. */
export function formatCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "number") return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (typeof v === "string" && ISO_DATE.test(v)) return isoToLabel(v);
  return String(v);
}

/** Chart x-axis tick: ISO date -> "Jul 25", else pass through. */
export function formatX(v: unknown): string {
  if (typeof v === "string" && ISO_DATE.test(v)) {
    const d = parseIsoDateUTC(v);
    if (!isNaN(d.getTime()))
      return d.toLocaleDateString("en", { month: "short", year: "2-digit", timeZone: "UTC" });
  }
  return String(v ?? "");
}

/** Chart y-axis / tooltip tick formatter, aware of the metric type. */
export function makeAxisTickFormatter(yFormat?: string | null) {
  return (v: unknown): string => {
    if (typeof v !== "number") return String(v ?? "");
    if (yFormat === "currency") {
      const a = Math.abs(v);
      if (a >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
      if (a >= 1_000) return `$${(v / 1_000).toFixed(0)}k`;
      return `$${v}`;
    }
    if (yFormat === "percent") return `${v}%`;
    return v.toLocaleString();
  };
}
