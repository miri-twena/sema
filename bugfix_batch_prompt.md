# Task: Bug batch — wide-screen admin layout, drill summary language, chart label spacing

Three user-reported bugs (July 2026, with screenshots). Fix all three; each has its own accept line. Follow `AGENTS.md`.

## Bug 1 — Admin panel doesn't use wide screens

On a wide viewport the admin screens (e.g. Users and permissions) stay narrow with a large dead zone on the right — the staged wide-screen container work (`max-w-3xl xl:max-w-5xl 2xl:max-w-6xl` in `App.tsx`) was applied to the chat app but not to the admin panel.

- Apply a staged responsive container to ALL admin screens (Users, Home screen config, Data sources, Semantic model, Organization settings, Audit log). Tables/screens with many columns are exactly where width helps — Users and Audit log should breathe at 2xl.
- Keep readable line lengths for prose-heavy areas (don't stretch form labels to 2000px); tables and two-pane layouts get the width, text blocks keep a sane max.
- Verify at 1280 / 1680 / 2560 widths; no horizontal scrollbars introduced at narrow sizes.

Accept: [ ] Users screen and Audit log visibly use the extra width at 2xl; no regression at laptop width.

## Bug 2 — Drill-down summary ("סיכום בקצרה") comes out in English for a Hebrew question

Screenshot evidence: drill answer whose question was Hebrew shows the summary block labeled "סיכום בקצרה" with English content. This violates the absolute rule: the agent answers in the language of the QUESTION — summary included.

- Reproduce first: Hebrew question in a DrillChat thread → inspect the `summary` field language. Likely cause: the drill [SEMA-CONTEXT] block and parent-answer context are English-heavy and pull the model to English; the system prompt's "same language as the question" instruction may need to be restated/anchored for the summary field specifically in drill turns.
- Fix at the agent layer (`prompts.py` — strengthen the summary-language instruction to reference THE CURRENT question's language explicitly, not the conversation's dominant language), NOT by post-hoc translation in the frontend.
- Add an eval case: Hebrew drill question over an English parent answer → summary must be Hebrew; and the mirror case (English drill over Hebrew parent) → English.

Accept: [ ] Hebrew drill question yields a fully Hebrew summary (and answer); eval case added and passing.

## Bug 3 — Chart value labels sit too close to the bars

The numbers rendered above bar columns are nearly touching the bar tops, in all charts.

- In the shared chart rendering (wherever bar value labels are drawn — main answers, drill answers, brief sparkline labels if applicable): add consistent vertical offset between the label baseline and the bar top (visually ~4-8px equivalent in the charting lib's units). One shared constant, not per-chart tweaks.
- Check the label doesn't clip at the chart's top edge for the tallest bar (increase top margin/domain padding if needed).
- Verify with Hebrew (RTL) labels and with currency-formatted values (₪/$ prefixes) — no overlap, no clipping, LTR digits intact.

Accept: [ ] Clear gap between value labels and bar tops in main chat + drill charts; tallest-bar label never clips; both languages verified.

## Constraints

`npm run lint`, `npm run build`, `pytest` (for the eval/prompt change) all green. No new deps. Before/after screenshots of each fix in the final report.
