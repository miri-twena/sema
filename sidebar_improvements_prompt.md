# Task: Sidebar batch — resizable width, kebab-menu z-order bug, drill-count indicator

Three user requests (July 2026, screenshots provided for #2). Follow `AGENTS.md`. Reminder: the sidebar is ALWAYS on the left (anchored layout) — "resize" means dragging its right edge.

## 1. Resizable sidebar

- Drag handle on the sidebar's right edge (`cursor: col-resize`, a few px wide hit area, subtle hover affordance). Drag adjusts width live.
- Sensible clamps: min ≈ 220px (titles still readable, no icon-rail mode in this task), max ≈ 420px (beyond that it steals from the chat). Double-click on the handle resets to the default width.
- Persist the chosen width in localStorage (`sema:sidebar:width`) and restore on load. Content must reflow gracefully at both extremes: title truncation/ellipsis keeps working, the pinned/section headers and footer rows (workspace + user) don't break.
- No new deps — pointer events, not a dnd library.

Accept: [ ] Width drags smoothly within clamps, survives reload, double-click resets; no layout breakage at min or max.

## 2. Kebab (⋯) menu renders behind other elements — fix stacking

Screenshot: the conversation item's ⋯ menu (Rename / Pin chat / Archive) is partially hidden behind later sidebar elements (e.g. the Archived row). Classic stacking/clipping issue — the menu is rendered inside the scrolling list where `overflow` and stacking contexts clip it.

- Fix properly: render the menu in a portal (document.body level) positioned to the trigger, or restructure z-index/stacking so it always paints above ALL sidebar content and the main pane. Prefer the portal — it also survives the scroll-container clipping.
- Must keep existing behavior: `useDismiss` (outside click + Escape), keyboard navigation, and correct position when the item is near the bottom of the viewport (flip upward if no room below).
- Verify: menu opened on the last visible conversation, on a pinned item, mid-scroll, and while the sidebar is at min width (#1).

Accept: [ ] Menu is never clipped or overlapped in any of the verified positions.

## 3. Drill-down count indicator on conversation titles

When a conversation has drill-down threads (widget-anchored follow-ups), show a small indicator next to its title in the sidebar with the TOTAL number of drill follow-up questions asked across all its threads (count of user turns in drill threads, not thread count).

- Backend: the conversations-list payload gains `drill_count` (single aggregated COUNT over the threads store grouped by conversation — no N+1).
- UI: tiny muted badge after the title (e.g. the existing badge/pill pattern, ~10-11px) showing the number; hidden entirely when 0; tooltip/aria-label "N drill-down follow-ups" / "N שאלות המשך בדריל". Must not push long titles into wrapping — it sits inside the same truncation row, title ellipsis shortens first.
- Updates when a new drill question is asked (same refresh path that already updates the sidebar; no polling).

Accept: [ ] Conversation with drill threads shows the correct total; asking another drill question updates it; conversations without drills show nothing.

## Constraints

`npm run lint`, `npm run build`, `pytest` (for the list-payload change) green; RTL-safe (Hebrew titles + badge coexist correctly); before/after screenshots for #2.
