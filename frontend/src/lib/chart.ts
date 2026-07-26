// Pure chart logic extracted from ChartRenderer so it's testable without
// mounting Recharts: pivoting long rows into per-series columns, deriving an
// optional period subtitle from the data actually returned, deciding how
// crowded an x-axis is, locating the (real, backend-chosen) point to
// highlight, and shaping tooltip payloads into label/value/series rows.

import { formatCell } from "./format";

type Row = Record<string, unknown>;

/** Pivot long rows ({x, color, y}) into wide rows ({x, series1, series2, ...}). */
export function pivot(rows: Row[], x: string, color: string, y: string) {
  const xValues = [...new Set(rows.map((r) => r[x] as string))];
  const series = [...new Set(rows.map((r) => String(r[color])))];
  const data = xValues.map((xv) => {
    const obj: Row = { [x]: xv };
    rows.filter((r) => r[x] === xv).forEach((r) => {
      obj[String(r[color])] = r[y];
    });
    return obj;
  });
  return { data, series };
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}/;

/** "Jan 2025 – Jun 2026" derived from the chart's OWN first/last rows -- never
 * a separate backend field, so there's nothing new to keep in sync with the
 * response contract. Only when x is a date column with more than one distinct
 * value; otherwise there's no meaningful period to show. */
export function periodSubtitle(rows: Row[], x?: string | null): string | null {
  if (!x || rows.length < 2) return null;
  const first = rows[0]?.[x];
  const last = rows[rows.length - 1]?.[x];
  if (typeof first !== "string" || typeof last !== "string") return null;
  if (!ISO_DATE.test(first) || !ISO_DATE.test(last) || first === last) return null;
  return `${formatCell(first)} – ${formatCell(last)}`;
}

export interface XAxisTickStyle {
  angle: number;
  textAnchor: "middle" | "end";
  /** Extra bottom margin/height Recharts needs to fit angled labels. */
  height: number;
}

// More categories than this and horizontal month/category labels start
// crowding each other (13 monthly ticks is the motivating case) -- angling
// them is the standard fix that keeps every tick visible AND readable,
// rather than dropping ticks.
const DENSE_TICK_THRESHOLD = 8;

export function xAxisTickStyle(pointCount: number): XAxisTickStyle {
  if (pointCount > DENSE_TICK_THRESHOLD) return { angle: -35, textAnchor: "end", height: 46 };
  return { angle: 0, textAnchor: "middle", height: 24 };
}

/** The (x, y) coordinate of the backend's chosen `highlight_x`, if the data
 * actually contains it -- never a guessed or invented point. `highlight_x`
 * is line-only per the schema (see agent/response.py), so callers should only
 * use this for single-series line/area charts. */
export function highlightPoint(
  rows: Row[],
  x?: string | null,
  y?: string | null,
  highlightX?: unknown,
): { x: unknown; y: number } | null {
  if (!x || !y || highlightX === undefined || highlightX === null) return null;
  const row = rows.find((r) => String(r[x]) === String(highlightX));
  if (!row) return null;
  const yv = row[y];
  return typeof yv === "number" ? { x: row[x], y: yv } : null;
}

export interface TooltipEntry {
  name: string;
  value: string;
  color: string;
}

export interface TooltipShape {
  label: string;
  entries: TooltipEntry[];
}

/** Recharts' tooltip payload, loosely typed -- library ships its own (large,
 * generic) type, and every existing formatter in this file already casts
 * around it the same way. */
interface RechartsTooltipEntry {
  name?: string | number;
  dataKey?: string | number;
  value?: unknown;
  color?: string;
}

/** Full dimension label (dates expand to "Jun 2026", not the axis's short
 * "Jun 26") + each series' formatted value and name -- the "polished tooltip"
 * requirement, kept out of the component so the label/value shaping is
 * testable without rendering a chart. */
export function tooltipContent(
  label: unknown,
  payload: RechartsTooltipEntry[] | undefined,
  fmt: (v: unknown) => string,
): TooltipShape {
  const asString = typeof label === "string" ? label : String(label ?? "");
  const fullLabel = ISO_DATE.test(asString) ? formatCell(asString) : asString;
  const entries = (payload ?? []).map((p) => ({
    name: String(p.name ?? p.dataKey ?? ""),
    value: fmt(p.value),
    color: p.color ?? "#7C8CFF",
  }));
  return { label: fullLabel, entries };
}

/** False during SSR/tests with no matchMedia, and whenever the OS-level
 * setting is on -- entrance/hover animation must be skippable, not just
 * shorter, to respect it. Reads the bare global (identical to `window.
 * matchMedia` in a real browser) so it doesn't depend on `window` existing,
 * which this project's non-jsdom test environment doesn't provide. */
export function prefersReducedMotion(): boolean {
  if (typeof matchMedia !== "function") return false;
  return matchMedia("(prefers-reduced-motion: reduce)").matches;
}
