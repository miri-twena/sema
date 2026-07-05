// Runtime design tokens for values used in inline styles / chart libraries
// (which can't read Tailwind utility classes). Consolidates palettes that were
// previously hardcoded across KpiCards, ChartRenderer, and AlertsPanel.

/** (background, label color) pairs cycled across KPI cards. */
export const KPI_TINTS: readonly [string, string][] = [
  ["#FBEEEA", "#9A6A58"],
  ["#EAF5FF", "#5A7894"],
  ["#EEF0FF", "#5B5F9F"],
  ["#EAFBF4", "#1B7A5E"],
];

/** Ordered series colors for charts (lavender, mint, sky, coral, gold, violet). */
export const CHART_PALETTE = ["#7C8CFF", "#7EE6C3", "#9ED8FF", "#FFB4A2", "#F2C94C", "#C9A0FF"];

/** Alert severity -> (background tint, accent). */
export const SEVERITY: Record<string, { bg: string; fg: string }> = {
  critical: { bg: "#FEE2E2", fg: "#DC2626" },
  warning: { bg: "#FEF9C3", fg: "#CA8A04" },
};
