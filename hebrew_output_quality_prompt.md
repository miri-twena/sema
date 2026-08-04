# Task: Hebrew output quality guard — no script leakage, no garbled text

User reported (August 2026, screenshot): a Hebrew recommendation containing an Arabic word ("الأسعار") mid-sentence plus garbled Hebrew phrasing — likely produced by the FALLBACK model (Haiku), where cross-script leakage is more common. This destroys trust. Fix in two layers: instruction AND deterministic guard — never rely on model compliance alone.

## 1. Deterministic script guard (the real fix)

Server-side, post-generation, in `response.py`'s cleaning pipeline (alongside `_clean_*` siblings):
- Detect **script leakage**: Arabic-block characters (U+0600–U+06FF, U+0750–U+077F) — and any other unexpected script (Cyrillic, CJK) — appearing in an answer whose question language is Hebrew or English. Check ALL user-facing text fields: summary, insight_text, KPI labels, recommended_actions (action/why/impact), follow_up_questions, clarification options.
- On detection: **retry the generation ONCE** with a corrective system nudge ("your previous answer contained text in the wrong script — answer entirely in the question's language"). If the retry also fails the check: strip is NOT safe (changes meaning) — degrade honestly: keep the answer but append the existing low-confidence treatment (set `confidence: low` + a deterministic notice like the fallback badge: "ייתכנו שיבושי ניסוח בתשובה זו"), and log `answer.script_leak` with the offending snippet for later analysis.
- The guard is cheap (regex over a few KB) — run it on every answer, both models, chat + drill + brief insights.

## 2. Prompt hardening

- System prompt: an explicit language-integrity rule — the answer must be written entirely in the question's language; English technical/metric terms are allowed inline; NO other scripts ever. Place it near the answer-language rule.
- The fallback-model path uses the SAME system prompt — verify (don't assume) the fallback call carries all language rules.

## 3. Evals + tests

- Unit tests for the detector (Hebrew with Arabic word → caught; legit Hebrew+English mix → passes; Hebrew with English metric names + $ symbols → passes; edge: Arabic-script user QUESTION → answer in Arabic is then LEGITIMATE, guard keys on the question's language, not a hardcoded allowlist).
- Retry path test (first response leaks → retried once → clean response used; both leak → low-confidence notice attached).
- Eval case with a mocked leaky response asserting the final answer shown is clean or flagged.

`pytest`, lint, build green. Report how often the guard fires against the demo (should be ~never with the primary model).

Accept: [ ] Injected leaky response gets retried and replaced (or flagged low-confidence); detector covers all user-facing fields; fallback path carries full language rules; legit bilingual Hebrew-English answers unaffected.
