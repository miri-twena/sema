# Task: Witty off-topic replies + senior-advisor recommendation engine

Two upgrades to the agent core, both centered on `sema_core/agent/prompts.py` (+ `response.py` schema and frontend rendering where noted). Follow `AGENTS.md`. When done, record the new behavioral conventions in `AGENTS.md` (agent persona + off-topic policy) so future sessions inherit them.

## Part 1 — Off-topic mode: playful deflection + useful redirect

Today mode='off_topic' returns "one or two light, friendly sentences". Replace that policy with:

1. **Tone: witty / lightly sarcastic, never mean.** One short joke or dry quip in the USER'S language that plays off what they asked (recipe question → "אני מומחה לתמהיל מוצרים, פחות לתמהיל תבלינים"). Rules: never mock the user personally, never punch down, no sensitive topics (politics, religion, health, tragedy — for those stay warm and neutral, no humor), no emojis, max 2 sentences of humor. Humor must land in both Hebrew and English — instruct the model to write it natively in the user's language, not translate a canned joke.
2. **Then pivot to value.** After the quip, one bridging sentence ("אבל בזמן שאתה כאן — ") plus concrete suggestions for improving the business:
   - `follow_up_questions` (2-3): real data questions worth asking THIS business right now. Prefer grounding: if [SEMA-CONTEXT] carries daily-brief signals or trending topics, derive suggestions from them (e.g. "AOV ירד השבוע — שווה לבדוק למה"); otherwise fall back to high-leverage evergreen questions (dormant VIP customers, negative-ROI campaigns, slow-moving inventory).
   - `recommended_actions` (1-2, now allowed in off_topic mode): short, generic-but-useful efficiency actions phrased as an experienced advisor's nudge, clearly marked as not data-derived.
3. Off-topic still runs NO data tools (unchanged) — grounding comes only from context already in the prompt. The prompt-injection guard paragraph stays as is.
4. **Schema/UI:** allow `recommended_actions` and `follow_up_questions` in off_topic responses end-to-end (`response.py` validation, API, frontend — the off-topic bubble renders follow-up chips like a normal answer). Keep the existing muted/light styling.

## Part 2 — Recommendation engine: 15+ years senior advisor

Upgrade `recommended_actions` from "2-3 concrete next steps" to advisor-grade recommendations:

5. **Persona (system prompt, applies to the whole agent voice):** SEMA is a senior business advisor with 15+ years of hands-on ecommerce experience — pattern-matching across hundreds of similar situations, direct, opinionated, allergic to fluff. It says what it would do, not "you could consider". Add this as a compact persona block near the top of the system prompt; do NOT let it inflate answer length — confidence shows in specificity, not verbosity.
6. **Structured actions.** Extend the `present_answer` schema: each action becomes `{action, why, expected_impact, effort}`:
   - `action` — imperative, specific, parameterized from the actual data ("צור קמפיין win-back ל-142 לקוחות ה-VIP שלא קנו 60+ יום", not "שפר שימור לקוחות").
   - `why` — one sentence tying it to evidence from THIS answer (numbers, segment names).
   - `expected_impact` — order-of-magnitude estimate when derivable from the data ("שווי שנתי משוער ₪180K"), phrased as an estimate; omit rather than invent.
   - `effort` — `low`/`medium`/`high` (proxy for "מה לעשות קודם").
7. **Quality bar (prompt rules):** actions sorted by impact-to-effort; no truisms ("עקוב אחרי המדדים"), no action the data doesn't support; when the data reveals a root cause, the action targets the cause not the symptom; at most one action requiring budget spend unless the question is about spend; reuse the exact segment/metric names from evidence so actions are auditable.
8. **Frontend:** render structured actions — action as the row title, `why` muted below, impact + effort as small badges (effort: teal/amber/coral). Backward-compatible: plain-string actions (old conversations) still render.
8a. **Copy action text:** every recommended-action card gets a copy control — EVERYWHERE actions render, including DrillChat (drill-down), not just the main answer. Icon button revealed on hover/focus (always visible on touch), copies the full plain text of that action (action + why + impact when present; strip markdown), `navigator.clipboard.writeText` with a brief inline check-icon confirmation (no toast). RTL-safe placement (logical inline-end), `aria-label` "העתק המלצה"/"Copy recommendation" per app language.
9. **Evals:** the project has `evals/` — add/extend cases: (a) off-topic question returns humor + grounded follow-ups and no tool calls; (b) sensitive off-topic gets no humor; (c) answer-mode actions are structured, reference evidence values, and contain no generic filler (assert against a blocklist of truism phrases).

## Constraints

- Hebrew/English parity for all new copy; RTL-safe rendering of badges.
- No new deps. `pytest` for schema changes, `npm run lint`, `npm run build`.
- Persona and off-topic policy documented in `AGENTS.md` under a "Agent voice" section.

## Accept

- [ ] Off-topic ("מה מזג האוויר?") → witty 1-2 sentence reply in the question's language + 2-3 grounded follow-up chips + 0 tool calls.
- [ ] Sensitive off-topic → neutral warm redirect, no humor.
- [ ] Answer-mode recommendations are structured (action/why/impact/effort), data-specific, sorted, and render with badges; old plain-string actions still display.
- [ ] Copy control works on every action card in both the main answer and DrillChat — copies clean plain text, shows confirmation, accessible and RTL-correct.
- [ ] Persona block present; median answer length does NOT grow (spot-check 5 eval questions before/after).
- [ ] Evals + `pytest` + lint + build pass; `AGENTS.md` updated.
