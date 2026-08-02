# Task: Line charts — value labels above the points

User request (August 2026): line charts show a data label above each point, aligned consistently.

1. Every point on a line chart renders its value label centered ABOVE the point, using the SAME shared vertical-offset constant created for bar labels (`bugfix_batch_prompt.md` §3) — one spacing convention for all chart types. Formatting via the existing `formatValue` (currency symbol/position, thousands separators — matching org number-format settings).
2. Top clipping: the tallest point's label must never clip — extend the chart's top margin/domain padding if needed (same approach as bars).
3. Density guard: when a series has more than ~16 points (daily series over months), labels would collide — in that case label only first / last / min / max points (implement as a simple threshold; document the constant). The screenshot's 13 monthly points get all labels.
4. Overlap nuance: when two adjacent points are near-equal, labels must not overlap the line or each other — nudge above consistently; do NOT alternate above/below (messy).
5. Applies everywhere line charts render: main answers, drill answers. Sparklines (brief pulse) explicitly EXCLUDED — they stay minimal by design.
6. Verify with currency values (₪/$), Hebrew answer context (digits stay LTR), and a dense daily series (density guard kicks in). `npm run lint`, `npm run build`, vitest green; before/after screenshot.

Accept: [ ] Monthly revenue line shows labels above every point, evenly offset, no clipping; dense series shows first/last/min/max only; bars unchanged.
