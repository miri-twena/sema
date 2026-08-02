# Task: "New conversation" opens a clean ask canvas (approved mode A)

New feature (August 2026): clicking "New conversation" opens a SEPARATE, much cleaner chat state — a focused ask canvas, per the approved mode-A mockup. No dashboard elements at all: no brief, no KPIs, no attention line — the user's intent here is "I want to ask", the screen answers only that. NOTE: this supersedes item §5 of `home_hebrew_polish_prompt.md` (which merely moved the old intro block to the top) — replace that arrangement with this canvas.

## Layout (centered, calm)

1. **Headline:** "What would you like to know?" + one muted subtitle line "Ask anything about your business — in plain language." (bilingual via locale files; Hebrew neutral phrasing, right-aligned per the Hebrew-headings rule, punctuation direction correct).
2. **Hero input:** large, centered (~max-w-xl), visually primary (accent border + soft ring per the mockup), with the SAME behaviors already built for the home top bar (`home_ask_bar_top_prompt.md`): cycling live placeholder from real suggested questions (org language aware), autofocus on desktop, `/` shortcut, submit → standard conversation layout takes over (input drops to bottom).
3. **Recommended questions:** 4 cards in a 2×2 grid under the input (stack on narrow) — from the org's suggested-questions config, each with a domain icon (existing icon set), whole card clickable → submits that question. `dir="auto"` per card.
4. **Trending in your company:** a labeled chip row under the cards — the existing company-popular questions source, click submits. Respects the org's home-config "Trending" toggle (off → row hidden) and data scopes (a user never sees a suggestion their scope blocks — verify the existing filter applies here).
5. Nothing else on the canvas. Generous whitespace; the sidebar stays as-is.

## Behavior

6. Entry points: the "New conversation" button (sidebar) and any other new-chat affordance all land on this canvas. The canvas is a STATE of the chat pane, not a modal/new browser window.
7. First submitted question (typed, card, or chip) transitions to the normal conversation UI — streaming/progress exactly as today. Leaving the canvas without asking (clicking an old conversation / home) creates NOTHING (no empty conversation in the sidebar).
8. Home screen keeps its own top ask bar (unchanged) — two entry surfaces, one ask flow.

## Constraints

- Reuse: input component + placeholder cycling from the home top bar; locale files for all new strings (parity test); RTL rules per AGENTS.md (anchored layout, per-text direction).
- Tests: canvas renders all sections per config (trending off → hidden; scope-blocked suggestion absent), card/chip click submits that exact question, no empty conversation persisted on abandon. `npm run lint`, `npm run build`, vitest, `pytest` green.

Accept: [ ] "New conversation" → clean centered canvas (headline, hero input, 4 recommended cards, trending chips) in both languages; asking from any element starts a normal conversation; abandoning leaves no trace; home screen unaffected.
