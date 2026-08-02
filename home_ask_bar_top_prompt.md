# Task: Home screen — ask input moves to the top, under the greeting (approved mockup, mode B)

Problem: on the home screen the chat input sits at the bottom, small and easy to miss — first-time users don't understand the product is "ask me things". Approved fix (mockup, August 2026): the ask input becomes the SECOND thing on the page, directly under "Good afternoon, {name}". This task changes the HOME state only — the in-conversation layout (input at bottom) stays exactly as it is.

1. **Placement + look:** prominent input directly under the greeting, full content width (within the staged container), slightly larger than the old bottom bar (~44-48px), leading sparkles icon, send button at the end. The old bottom bar is REMOVED from the home state (one ask entry, not two). Focus ring on hover/focus per existing tokens.
2. **Behavior:** identical to the existing ask flow — submitting starts the conversation, view transitions to the standard conversation layout (input at bottom from then on). Autofocus the input when the home screen mounts (desktop only — no autofocus on touch to avoid keyboard popup).
3. **Live placeholder:** the placeholder cycles every ~3s through 3-4 REAL example questions sourced from the existing suggested-questions config (org-customized ones included), with a gentle fade. Cycling pauses permanently once the user focuses/types. Language: follows the existing org-language placeholder rules (Hebrew set → Hebrew questions, `dir` per content); cycling respects `prefers-reduced-motion` (static fallback).
4. **Hierarchy below:** Daily brief and Business overview keep their current designs, just ordered after the input (greeting → ask → brief → overview → suggested questions/trending as today). No dimming/opacity tricks in the real product — position carries the hierarchy.
5. **Keyboard:** `/` focuses the ask input from anywhere on the home screen (ignore when a modal/drawer is open or focus is already in an input).
6. Locale files per AGENTS.md for any new string. RTL-safe.
7. Tests: home renders single ask entry at top, submit starts a conversation (existing flow test adjusted), placeholder cycles and stops on focus (logic unit test), `/` shortcut guard conditions. `npm run lint`, `npm run build`, vitest, `pytest` green.

Accept: [ ] Home = greeting → prominent ask input (cycling placeholder) → brief → overview; no bottom bar on home; conversation state unchanged; both languages verified.
