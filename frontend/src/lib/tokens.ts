// Runtime design tokens for values used in inline styles / chart libraries
// (which can't read Tailwind utility classes). Consolidates palettes that were
// previously hardcoded across KpiCards, ChartRenderer, and AlertsPanel.

/** (background, label color) pairs cycled across KPI cards -- since the
 * dashboard palette pass, KpiCards.tsx itself only uses the second value
 * (as a small accent dot's color, cards are white now); the first value
 * lives on as HomeDashboard's HEALTHY_TINT background. */
export const KPI_TINTS: readonly [string, string][] = [
  ["#F0EFFD", "#4E4BB3"],
  ["#E9F1FD", "#2A6493"],
  ["#E7F4F6", "#12656F"],
  ["#E9F5EE", "#176B4C"],
];

/** Ordered series colors for charts (lavender, mint, sky, coral, gold, violet). */
export const CHART_PALETTE = ["#7C8CFF", "#7EE6C3", "#9ED8FF", "#FFB4A2", "#F2C94C", "#C9A0FF"];

/** Text-safe counterparts to CHART_PALETTE, same order -- for labels/values
 * that must pass AA on white. Never used as a fill. */
export const CHART_PALETTE_TEXT = ["#5B62DE", "#159C77", "#2E86C8", "#D6644A", "#A97C09", "#8E5CD9"];

/** Alert severity -> (background tint, accent). */
export const SEVERITY: Record<string, { bg: string; fg: string }> = {
  critical: { bg: "#FEE2E2", fg: "#DC2626" },
  warning: { bg: "#FEF9C3", fg: "#CA8A04" },
};

/** Brand mark palette (Logo.tsx) -- same lavender as tailwind's `primary`
 * token (#6C74F0), duplicated here because inline SVG fill/stroke attributes
 * can't read Tailwind classes, same reasoning as the rest of this file. */
export const BRAND = {
  lavender: "#6C74F0",
  lavender400: "#949CFF",
  lavender200: "#C7CDFF",
  lavender700: "#5B62C4",
  coral: "#F2887C",
  ink: "#15161C",
} as const;
