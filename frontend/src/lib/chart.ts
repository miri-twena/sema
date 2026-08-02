// Pure chart logic extracted from ChartRenderer so it's testable without
// mounting Recharts: pivoting long rows into per-series columns, deriving an
// optional period subtitle from the data actually returned, deciding how
// crowded an x-axis is, locating the (real, backend-chosen) point to
// highlight, and shaping tooltip payloads into label/value/series rows.

import { formatCell } from "./format";
import { CHART_PALETTE, CHART_PALETTE_TEXT } from "./tokens";

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

/** Vertical shift (px) applied to a bar's value-label text, above the bar
 * top -- one shared constant so every bar chart (main answer, drill answer)
 * gets the same breathing room instead of a per-chart tweak. NOTE: this is
 * applied manually to the label's `y` in the custom LabelList `content`
 * renderer -- `LabelList`'s own `offset` prop only affects its BUILT-IN label
 * renderer's position math and is silently ignored once a custom `content`
 * function is supplied (verified: bumping `offset` alone produced zero
 * visual change), which is why the bars-glued-to-labels bug survived an
 * earlier `offset={7}` that looked like it should have fixed it. */
export const BAR_VALUE_LABEL_OFFSET = 8;

// More points than this on a single-series line/area chart and per-point
// labels start colliding (a daily series over a few months is the motivating
// case) -- past the threshold only first/last/min/max survive, mirroring the
// x-axis's own DENSE_TICK_THRESHOLD idea of "past a point, show the
// meaningful ones instead of everything." The screenshot's 13 monthly points
// stay under this, so they all get labels.
export const LINE_LABEL_DENSITY_THRESHOLD = 16;

/** Which point indices get a value label on a single-series line/area chart.
 * At or under the threshold every point does; past it, only the first, last,
 * min, and max survive (a flat/short series can make these overlap in index,
 * which is fine -- it's a Set). */
export function lineLabelIndices(values: number[]): Set<number> {
  if (values.length <= LINE_LABEL_DENSITY_THRESHOLD) {
    return new Set(values.map((_, i) => i));
  }
  let minI = 0;
  let maxI = 0;
  values.forEach((v, i) => {
    if (v < values[minI]) minI = i;
    if (v > values[maxI]) maxI = i;
  });
  return new Set([0, values.length - 1, minI, maxI]);
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

/** A "nice" rounded Y-axis domain + evenly-spaced ticks for a single-series
 * bar chart, leaving headroom above the tallest bar for its value label
 * (answer-screen redesign: with a 99.4%-tall bar there's no room left for a
 * label inside the plot box). Standard nice-numbers algorithm: round the raw
 * per-tick step up to the nearest 1/2/5 x 10^n, e.g. 3,381 -> max 4,000,
 * ticks [0, 1000, 2000, 3000, 4000]. */
export function niceAxis(maxValue: number, tickCount = 4): { max: number; ticks: number[] } {
  if (!(maxValue > 0)) return { max: 0, ticks: [0] };
  const rawStep = maxValue / tickCount;
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const normalized = rawStep / magnitude;
  const niceNormalized = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  const step = niceNormalized * magnitude;
  const max = step * tickCount;
  return { max, ticks: Array.from({ length: tickCount + 1 }, (_, i) => Math.round(i * step)) };
}

/** True when `value` is the backend's chosen highlight_x, by loose string
 * equality (mirrors highlightPoint's own matching rule above) -- shared by
 * the bar chart's per-bar emphasis and DataTable's per-row emphasis, so a
 * chart and its table below it can never disagree about which entity is
 * highlighted. Absent/unmatched highlight_x is always silently "no match". */
export function matchesHighlight(value: unknown, highlightX: unknown): boolean {
  if (highlightX === undefined || highlightX === null) return false;
  return String(value) === String(highlightX);
}

/** In-bar annotation for the category highlight_x points to, dir-keyed like
 * AssistantResponseCard's own SUMMARY_HEADING (this describes THIS answer's
 * language, not the chrome's -- see AGENTS.md's answer- vs chrome-language
 * split). Pre-split into its authored two lines rather than left to wrap:
 * SVG text has no CSS wrapping, and the mockup's own line break is a
 * deliberate two-line phrase, not an overflow accident. */
export const HIGHLIGHT_ANNOTATION: Record<"rtl" | "ltr", readonly [string, string]> = {
  rtl: ["מה שהתשובה", "מסבירה"],
  ltr: ["What this answer", "explains"],
};

export interface BarVisualState {
  fill: string;
  categoryColor: string;
  categoryWeight: number;
  valueColor: string;
}

/** All per-bar color/weight decisions for the single-series bar chart's
 * highlight treatment (answer-screen redesign), as a pure function of two
 * booleans -- testable without mounting Recharts. `hasHighlight` is whether
 * highlight_x matched ANY row in the data; `isMatch` is whether THIS row is
 * the one it matched. No highlight at all -> every bar gets the same
 * baseline (solid fill, mid-gray labels); a highlight present but this bar
 * isn't it -> dims to 24% fill and grayed-out labels; this bar IS the
 * match -> full fill, ink category label, and the chart's text-safe accent
 * on the value label. */
export function barVisualState(isMatch: boolean, hasHighlight: boolean): BarVisualState {
  if (!hasHighlight) {
    return { fill: CHART_PALETTE[0], categoryColor: "#475569", categoryWeight: 500, valueColor: "#334155" };
  }
  if (isMatch) {
    return { fill: CHART_PALETTE[0], categoryColor: "#1E293B", categoryWeight: 600, valueColor: CHART_PALETTE_TEXT[0] };
  }
  return { fill: `${CHART_PALETTE[0]}3D`, categoryColor: "#94A3B8", categoryWeight: 500, valueColor: "#94A3B8" };
}
