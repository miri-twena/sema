# Task: Responsive wide-screen layout

On wide monitors most of the screen is empty: all content is locked to `max-w-3xl`. Principle: prose stays narrow for readability; data widgets expand. Files: `frontend/src/App.tsx`, `AssistantResponseCard.tsx`, `HomeDashboard.tsx`, `ChartRenderer.tsx`, `DataTable.tsx`, `KpiCards.tsx`, `DrillChat.tsx`. Follow `AGENTS.md`.

## 1. Tiered container width

Every `max-w-3xl mx-auto` wrapper in `App.tsx` (chat scroll area, input row) becomes `max-w-3xl xl:max-w-5xl 2xl:max-w-6xl mx-auto`. Header content aligns to the same width.

## 2. Prose narrow, widgets wide

Inside `AssistantResponseCard.tsx` and `HomeDashboard.tsx`:

- Markdown prose (`.sema-prose`), summary block, notices, badges: cap at `max-w-3xl` (add e.g. `xl:max-w-3xl`) regardless of container.
- Full width of the container: `ChartRenderer` (charts gain real detail from width), `DataTable`, `KpiCards` (allow up to 6 columns at `2xl` via the existing dynamic grid — keep mobile behavior intact), `RecommendedActions` may span but each action's text caps at ~`max-w-3xl`.
- Chart height may step up modestly at `xl` (e.g. 280px → 340px).

## 3. Drill panel side-by-side on 2xl+

In `DrillChat.tsx`: at `2xl` and up, render the panel as a static side column (`2xl:static 2xl:h-auto` within a flex row in `App.tsx`) instead of fixed overlay — no backdrop, main chat stays interactive and shrinks to share the row. Below `2xl`, current overlay behavior unchanged (including animations, expand toggle — the expand toggle can hide at `2xl`). Escape/close still works in both modes.

## Constraints

- Logical properties only (RTL-safe). No new deps.
- Mobile/laptop (< xl) renders pixel-identical to today.
- `npm run lint` && `npm run build` pass.

## Accept

- [ ] 1440px: container ~1024px; charts/tables full width; prose still ~65-75ch lines.
- [ ] 1920px+: container ~1152px; drill opens beside the chat, both usable simultaneously.
- [ ] < 1280px: nothing changed.
