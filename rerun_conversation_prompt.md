# Task: "Rerun" option in the conversation kebab menu — fresh run in a NEW conversation

Add "Rerun" to the sidebar conversation ⋯ menu (alongside Rename / Pin chat / Archive / Delete). Semantics — explicitly NOT retry: retry re-executes inside the same conversation; **Rerun opens a NEW conversation and asks the source conversation's original question there, fresh** (new SQL, current data, current semantic model). Use case: data or metric definitions changed since the original run — compare then vs. now without touching the original.

1. **Behavior:** Rerun takes the FIRST user message of the source conversation and submits it as a brand-new conversation through the normal ask flow (same as if the user typed it). The new conversation opens in the main pane immediately (standard streaming/progress UX), gets its own title the normal way, and appears in the sidebar as a regular new conversation. The source conversation is untouched.
2. **Multi-turn sources:** MVP scope = first question only (it defines the chat). Do NOT replay the whole turn sequence — follow-ups often depend on earlier answers and drift. (If trivial to add later: a submenu "Rerun first question / Rerun all" is V2 — note it in code comments, don't build.)
3. **Menu placement:** after "Rename", icon: a refresh/redo glyph from the existing icon set. Locale files get the label in both languages (`menus.conversation.rerun`: "Rerun" / "הרצה מחדש") — per the i18n rules in AGENTS.md.
4. **Edge cases:** archived conversations — Rerun allowed (creates a fresh active conversation); empty/broken source (no user message) — option hidden; drill threads are NOT rerun (they belong to the source's widgets).
5. **No backend changes expected** (reuses the existing create-conversation + ask flow); if the first-user-message lookup needs a store helper, add it minimally.
6. Tests: menu renders the option, rerun creates a NEW conversation id with the same first question text, source unchanged; hidden for empty conversations. `npm run lint`, `npm run build`, `pytest`/vitest green.

Accept: [ ] Rerun on a Hebrew and an English conversation each opens a new conversation asking the same original question fresh; the old conversation and its drill threads are untouched; label localized.
