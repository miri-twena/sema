// Shared formatting helpers. Single source of truth for numbers/dates across
// KPI cards, charts, and tables (previously duplicated in three components).

/** How a value should read. `count` and `currency` differ deliberately:
 * money abbreviates (K/M) because magnitude is what matters at a glance,
 * counts never do because "1.2K customers" hides whether it's 1,200 or 1,249. */
export type MetricType = "currency" | "count" | "id" | "percent" | "ratio" | "text";

/** "1.30" -> "1.3", "600.0" -> "600"; keeps "2.85" intact. */
function trimZeros(s: string): string {
  return s.includes(".") ? s.replace(/\.?0+$/, "") : s;
}

/** 1,672,356 -> "1.67M", 824,068 -> "824.1K", 600,000 -> "600K".
 * Currency only -- counts never abbreviate, see MetricType. */
export function compact(n: number): string {
  const a = Math.abs(n);
  if (a >= 1_000_000) return `${trimZeros((n / 1_000_000).toFixed(2))}M`;
  if (a >= 1_000) return `${trimZeros((n / 1_000).toFixed(1))}K`;
  return n.toLocaleString();
}

/** Columns whose values identify an entity. Such values are TEXT even when
 * they parse as numbers -- customer 1047 must never render as "1,047".
 * Anchored to a word boundary so "paid"/"valid"/"void" don't match "id". */
const ID_COLUMN = /(^|_)(id|ids|sku|upc|ean|isbn|uuid|guid|code)$/;

export function isIdColumn(name: string): boolean {
  return ID_COLUMN.test(name.trim().toLowerCase().replace(/\s+/g, "_"));
}

/** Single source of truth for rendering a metric. Every card, chart, tooltip
 * and table cell goes through here so the count/currency/id rules can't drift. */
export function formatMetric(value: unknown, type: MetricType): string {
  if (value === null || value === undefined) return "";

  // Identifiers are stringified verbatim -- no separators, no abbreviation.
  // String() also normalizes the 1047.0 that JSON/pandas can hand back for an
  // integer id down to "1047".
  if (type === "id") return String(value);

  if (typeof value !== "number" || !Number.isFinite(value)) return String(value);

  switch (type) {
    case "currency":
      return `$${compact(value)}`;
    case "count":
      // Always full precision with thousands separators: "1,247", never "1.2K".
      return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
    case "percent":
      return `${value.toFixed(1)}%`;
    case "ratio":
      return `${value.toFixed(2)}x`;
    default:
      return String(value);
  }
}

/** Maps the backend's declared KPI format onto a MetricType. The backend's
 * "number" means "numeric, non-monetary" -- i.e. a count. */
const KPI_FORMATS: Record<string, MetricType> = {
  currency: "currency",
  percent: "percent",
  number: "count",
  ratio: "ratio",
  text: "text",
};

/** KPI value per its declared format. */
export function formatValue(value: number | string, fmt: string): string {
  return formatMetric(value, KPI_FORMATS[fmt] ?? "text");
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
 *  thousands separators, everything else passes through. Pass `column` so
 *  id-like columns render as plain text rather than formatted numbers. */
export function formatCell(v: unknown, column?: string): string {
  if (v === null || v === undefined) return "";
  if (column && isIdColumn(column)) return formatMetric(v, "id");
  if (typeof v === "number") return formatMetric(v, "count");
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

/** Chart y-axis / tooltip tick formatter, aware of the metric type. Routes
 * through formatMetric so axes and tooltips match the KPI cards exactly. */
export function makeAxisTickFormatter(yFormat?: string | null) {
  const type: MetricType = yFormat ? (KPI_FORMATS[yFormat] ?? "count") : "count";
  return (v: unknown): string => formatMetric(v, type);
}
