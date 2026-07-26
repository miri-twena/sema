# Task: Sidebar redesign + popular-questions relocation

## Context

The frontend lives in `frontend/` (React 19 + Tailwind + TypeScript, Vite). Read `AGENTS.md` first and follow its conventions. Key files for this task:

- `frontend/src/components/Sidebar.tsx` — current sidebar (brand, New chat, search, then ONE scroll area mixing ConversationList + Suggested + Popular question cards)
- `frontend/src/components/ConversationList.tsx`, `ConversationItem.tsx`, `SidebarSection.tsx`
- `frontend/src/components/ClientSelector.tsx` — native `<select>`, rendered in the header (compact variant)
- `frontend/src/App.tsx` — header holds the connection dot + ClientSelector; passes `suggested` and `popularQuestions` to both Sidebar and HomeDashboard
- `frontend/src/components/HomeDashboard.tsx` — home screen; section 5 renders `suggested` as cards
- `frontend/src/components/AssistantResponseCard.tsx` — answer card (for part 4)
- `frontend/src/lib/tokens.ts` — KPI_TINTS (pastel pairs currently reused by the sidebar)

## Goal

The sidebar becomes navigation + conversations ONLY. Discovery questions (suggested + popular) live on the home screen. The client selector moves to the sidebar bottom as a workspace switcher. Visual language: calm and neutral; accent color appears ONLY on the active conversation and interactive highlights — remove all pastel tints from the sidebar.

## Part 1 — Sidebar: conversations only, grouped by time

1. Remove the Suggested-questions and Popular-questions sections (and the `QuestionCards` component + its tints) from `Sidebar.tsx`. The sidebar no longer needs `suggested`/`popularQuestions`/`onPick` props.
2. Keep: brand button (home), New chat CTA, search toggle behavior exactly as today.
3. Replace the flat Pinned/Recent split with time-grouped sections: **Pinned** (only if any), **Today**, **Last 7 days**, **Older** — computed from each conversation's `updated_at` (check the `ConversationSummary` type in `lib/api.ts` for the exact field). Empty groups render nothing.
4. Conversation row style: flat, transparent background, `text-ink`, truncated single line. Hover: `bg-surfaceAlt`. Active conversation: `bg-primary/10 text-primary-dark font-medium` — no pastel card backgrounds, no per-category tint colors.
5. Row actions (rename / pin / archive / delete) move into a `⋯` (kebab) menu button that is visible on row hover/focus-within, and always visible on touch (reuse the `.sema-copy-affordance` pattern from `index.css` for hover-reveal). Keep all existing `ConversationActions` wiring.
6. Keep section collapse state + localStorage persistence if `ConversationList` already has it; otherwise don't add collapsing to the new time groups.

## Part 2 — Workspace switcher at the sidebar bottom

1. New bottom block in the sidebar (border-t, `shrink-0`): avatar circle with the client's initials (bg `primary/10`, text `primary-dark`), client label, connection status line (small dot + "Connected"/"Disconnected"), and a chevron.
2. Clicking opens a popover listing all clients (reuse the `useDismiss` outside-click/Escape pattern from `HomeDashboard.tsx`); picking one calls the existing `switchClient`. Style the popover like the existing ones (rounded-xl2, border-line, shadow-pop).
3. This REPLACES: the native `<select>` ClientSelector in the header AND the connection dot in the header. Remove both from `App.tsx`'s header. `dbConnected` now feeds the sidebar block (health details remain available via the home-screen health chip).
4. Delete `ClientSelector.tsx` if nothing else uses it.
5. The mobile drawer gets the same sidebar, so the switcher must work there too.

## Part 3 — Home screen: one discovery section

In `HomeDashboard.tsx`, section 5 ("Start a conversation"):

1. Keep the suggested-question cards as they are.
2. Below them, add a "Trending in your company" sub-block (small `TrendingUp` lucide icon + SectionLabel): `popularQuestions` rendered as pill chips — rounded-full, border-line, bg-surface, text-sm — each with a small count badge (`bg-primary/10 text-primary-dark rounded-full`, e.g. "14×"). Clicking a chip calls `onPick(question)`.
3. `HomeDashboard` gains a `popularQuestions: PopularQuestion[]` prop; `App.tsx` passes it (it already fetches them). Hide the sub-block when the list is empty.

## Part 4 — "Others also asked" under answers (small, optional if time allows)

In `AssistantResponseCard.tsx`, after `RecommendedActions`: if the app has popular questions, show up to 3 as the same pill-chip style under a "Others also asked" label. Clicking sends the question via the existing `onAsk` prop (same conversation). Simple client-side relevance is fine for now: exclude the question just asked, prefer chips not shown yet this session. Do NOT add a backend endpoint for this.

## Part 5 — Fix forced auto-scroll + "back to bottom" button

Today both chat views force-scroll to the bottom on every turn/loading update, yanking the user away if they scrolled up to read: `App.tsx` (~line 86, `scrollRef` effect) and `DrillChat.tsx` (~line 89, same pattern).

1. Extract a shared hook `frontend/src/hooks/useStickToBottom.ts`:
   - Owns the scroll container ref and an `atBottom` state, updated in an `onScroll` handler: `scrollHeight - scrollTop - clientHeight < 80` counts as "at bottom".
   - Auto-scrolls (smooth) on content changes ONLY while `atBottom` is true. A user scrolling up detaches; scrolling back down re-attaches. No timers.
   - Sending a NEW question always re-attaches and scrolls (the user expects to see their own message), including retry.
2. When `atBottom` is false and content changed since detaching, show a floating "back to bottom" button: circular, `bg-surface border border-line shadow-pop`, lucide `ArrowDown`, positioned sticky/absolute near the bottom-center of the scroll area (logical properties only). Click → smooth scroll to bottom + re-attach. Give it `aria-label="Scroll to latest"`.
3. Use the hook in both `App.tsx` and `DrillChat.tsx`; remove the two old effects.
4. Streaming-safe: while `chat.loading` with progress events arriving, the same rule applies — pinned follows, detached stays put.

Acceptance: scrolling up mid-answer never gets interrupted; the button appears only when detached with new content below; clicking it or sending a message returns to live-follow. Works in the drill panel too.

## Constraints

- RTL: use logical properties/classes only (`start`/`end`, `ps`/`pe`, `border-s`) — the app supports Hebrew. No `left`/`right` physical CSS.
- Accessibility: keep/add `aria-label`s, `aria-expanded` on the switcher popover, focus-visible rings consistent with existing components, full keyboard operability for the kebab menu and switcher.
- No new dependencies.
- Keep `localStorage` keys stable where behavior is preserved (`sema:questionSections` becomes unused — remove its code).
- Run `npm run lint` and `npm run build` in `frontend/` before finishing.

## Acceptance checklist

- [ ] Sidebar shows only: brand, New chat, search, Pinned/Today/Last 7 days/Older conversations, bottom workspace switcher.
- [ ] No pastel question cards anywhere in the sidebar; active conversation is the only accent-colored row.
- [ ] Header contains only the brand/title block (and the mobile drawer toggle) — no select, no status dot.
- [ ] Client switching works from the bottom switcher on desktop and in the mobile drawer, and shows connection status.
- [ ] Home screen shows suggested cards + trending chips with counts; both send the question on click.
- [ ] Answers show up to 3 "Others also asked" chips that continue the same conversation.
- [ ] Auto-scroll only follows when the user is at the bottom; "back to bottom" button works in both the main chat and the drill panel.
- [ ] `npm run lint` and `npm run build` pass; Hebrew (RTL) layout unaffected.
