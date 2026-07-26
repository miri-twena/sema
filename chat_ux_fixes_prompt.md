# Task: Chat scroll behavior, drill-panel persistence, drill-panel RTL

Three focused fixes in `frontend/` (React 19 + Tailwind + TS). Read `AGENTS.md` first. Note: this REPLACES "Part 5" of `sidebar_redesign_prompt.md` if that part hasn't been implemented yet — the scroll spec here is the newer one.

## Part 1 — Scroll: follow progress, then show the answer from its top

Current behavior: `App.tsx` (~line 86) and `DrillChat.tsx` (~line 89) force-scroll to the bottom on every `chat.turns`/`chat.loading` change — it yanks users who scrolled up, and a long answer lands with the user staring at its END, having to scroll up to start reading.

Desired behavior, in one shared hook `frontend/src/hooks/useChatScroll.ts` used by both views:

1. **While waiting/streaming progress** (turn sent, `response` not yet set): follow the bottom — but ONLY if the user is "attached" (within 80px of the bottom; an `onScroll` handler updates this). Scrolling up detaches; scrolling back down re-attaches. Sending a question (or retry) always re-attaches.
2. **When a turn's answer arrives** (`turn.response` transitions from undefined to set on the LAST turn): scroll so the TOP of that answer card is at the top of the viewport (small offset, ~8px), so the user reads the answer from its beginning. Implement with a ref on the last turn's answer element + `scrollIntoView({ block: "start", behavior: "smooth" })`. This scroll happens even if the user was attached-to-bottom; skip it only if the user manually detached while waiting AND is scrolled away reading something else.
3. **"Back to latest" floating button**: shown when detached and content changed below. Circular, `bg-surface border border-line shadow-pop`, lucide `ArrowDown`, positioned near the bottom-center of the scroll area with logical properties. Click → scroll to bottom + re-attach. `aria-label="Scroll to latest"`.
4. Remove both old `scrollTo` effects. No timers; state-driven only.

## Part 2 — Drill-down panel: don't silently lose the conversation

Context: `DrillChat.tsx` runs its own `useChat` with `persistKey: null` — closing the panel discards the whole drill conversation with zero warning (close button, backdrop click, and Escape all call `requestClose`).

1. **Baseline (required): gentle discard confirmation.** If the drill chat has at least one turn, `requestClose` first shows a small inline confirm bar at the top of the panel (not `window.confirm`): text like "This drill-down conversation will be discarded." with buttons "Keep exploring" / "Discard". Style consistent with the app (rounded-xl, border-line, bg-surfaceAlt, text-sm). Escape/backdrop trigger the same bar; a second Escape confirms discard. No turns → close immediately as today.
2. **If cheaply possible: "Save to main chat".** Check `frontend/src/lib/api.ts` + `useChat.ts`/`useConversations.ts` for an existing way to append turns to a stored conversation or create a conversation from turns. If one exists, add a "Save to chat" action next to Discard (and as a small header button): it persists the drill transcript as a conversation (title = the widget title) so it appears in the sidebar, then closes without warning. **If this requires backend changes, skip it** and leave a `TODO` comment noting the endpoint that would be needed — do not modify the backend in this task.

## Part 3 — Drill-down panel: logical (RTL-safe) layout

`DrillChat.tsx` uses physical CSS while the rest of the app uses logical properties:

1. `right-0` → `end-0`; `border-l` → `border-s`.
2. The slide keyframes (`sema-slide-in-right` / `sema-slide-out-right` in `index.css`) translate from `+100%` — correct only in LTR. Make them direction-aware: add logical variants (e.g. `[dir="rtl"]` overrides that flip the sign, or new `sema-slide-in-end`/`sema-slide-out-end` keyframe pairs selected via `dir`) so the panel slides in from the inline-end side in both directions. Keep the "keyframes, not toggled transitions" approach documented in `index.css`.
3. The expand/collapse icons (`ChevronsLeft`/`ChevronsRight`) point the wrong way in RTL — flip them based on document direction (e.g. `rtl:rotate-180` or choosing the icon by `dir`).
4. Audit the rest of `DrillChat.tsx` for any other physical properties and convert them.

## Part 4 — "In short" summary at the top of analytical answers

Goal: every full analytical answer (`mode === "answer"`) opens with a concise headline takeaway inside a visually distinct tinted block, ABOVE the prose/KPIs/chart/table/actions, titled:

- Hebrew (`dir === "rtl"`): `סיכום בקצרה`
- English: `In short`

**Mandatory architectural principle — the summary is a structured field produced by the agent, end to end.** It must NOT be derived in the frontend by any of: slicing the first sentence of `answer`, character truncation, Markdown parsing, regex over the answer, or an extra LLM call. If `summary` is absent in a response, render nothing — no fallback extraction.

Backend (this part is EXEMPT from the "no backend changes" constraint below):

1. Add an optional `summary` field to the agent's structured answer. Chain to touch: `sema_core/agent/response.py` (`present_answer` schema), `sema_core/agent/prompts.py` (instruct the model to produce it), `api/models.py` + `api/serialize.py` (expose it), and any place `agent.py` assembles the final payload. Example value: `"Revenue increased by 4.4%, driven by a 30.2% rise in orders, which more than offset the 19.8% decline in AOV."`
2. Prompt requirements: 1–2 sentences, the central conclusion with its key numbers, same language as the user's question, no Markdown. Only for full answers — clarification / cannot_answer / off_topic modes must not carry a summary (strip it server-side like the other analytical fields, following the existing belt-and-braces pattern).
3. Update the rule-based fallback path (`sema_core/wiring.py`) consistently: give its predefined answers a real summary where natural, else omit.

Frontend:

4. Add `summary?: string | null` to `ChatResponse` in `frontend/src/lib/api.ts` (~line 99).
5. In `AssistantResponseCard.tsx`, render the summary block above the prose (after the badges/PeriodBanner): rounded-xl tinted container (e.g. `bg-primary/[0.06] border border-lineSoft`), a small uppercase label row with a lucide icon (e.g. `Sparkles`) reading `In short` / `סיכום בקצרה` per `dir`, then the summary text at `text-[0.95rem]` medium weight. Plain text rendering — no Markdown. Respect `dir` and `unicodeBidi: "plaintext"` like the alert messages do.
6. Include the summary in the existing copy action (prepended to the copied answer) and make sure tests in `tests/`/`evals/` that assert the response schema are updated.

## Constraints

- No new dependencies; no backend changes (EXCEPT Part 4's `summary` field chain).
- Accessibility: confirm bar buttons keyboard-reachable, `aria-live="polite"` on the bar; the floating scroll button needs `aria-label`; keep existing focus-visible ring styles.
- Logical properties only in anything you touch.
- Run `npm run lint` and `npm run build` in `frontend/` before finishing.

## Acceptance checklist

- [ ] Scrolling up during a long generation is never interrupted; new-answer arrival aligns the viewport to the answer's top; "back to latest" works in main chat AND drill panel.
- [ ] Closing a drill panel with turns asks before discarding (close button, backdrop, Escape); empty panel closes instantly.
- [ ] "Save to chat" exists only if it was implementable client-side; otherwise a TODO documents the missing endpoint.
- [ ] Drill panel renders and animates correctly with `dir="rtl"` on the document root.
- [ ] Analytical answers open with the tinted "In short" / "סיכום בקצרה" block sourced ONLY from the structured `summary` field; non-answer modes never show it; missing summary renders nothing.
- [ ] `npm run lint` and `npm run build` pass, and backend tests (`pytest`) pass with the new field.
