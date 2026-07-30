# Task: Close the org-settings gaps — retention job, org language enforcement, semantic draft audit

Three gaps found auditing Phase 1 (`SEMA-Client-Screens-Spec.pdf` v1.2 §2) against the code. All three are "half-built promises": the setting is stored and shown in the UI, but nothing consumes it. Follow `AGENTS.md`. Small task — no new screens.

## Part 1 — Retention actually runs (the important one)

Today `sema_core/retention.py` works but is only reachable via `python -m sema_core.retention`. A client can select "30 days", the UI implies the policy is active, and nothing is ever deleted. Silent broken promise.

1. **Daily background task in the API.** On FastAPI startup (lifespan), start an asyncio task that runs the retention sweep for every client once every 24h, plus once shortly after boot (~60s delay, so startup isn't blocked). Guard it: wrap each run in try/except so a failure never kills the loop or the API; log start/finish/error via the existing `obs` logging. Make it disableable with an env var (`SEMA_RETENTION_ENABLED`, default on) so tests and local runs can opt out.
2. **Idempotency + last-run tracking.** New table (or a row in an existing settings/meta table) `retention_runs(client_id, last_run_at, deleted_count, status, error)`. On each run, record it. Skip a client whose `last_run_at` is under 20h old (so a restart loop can't hammer deletions). Reuse the existing soft-delete logic — do NOT reimplement it.
3. **Auditability.** Each sweep that deletes anything writes an audit event (`org.retention_swept`, actor = system/service actor — extend `log_admin_event` with a system-actor path rather than faking a user). Zero-deletion runs are logged to the app log only, not the audit table.
4. **Visible in the UI.** Under the retention selector in `OrgSettingsScreen.tsx`, show a muted status line built from `retention_runs`: "ניקוי אחרון: לפני 6 שעות · 12 שיחות נמחקו" / "Last cleanup: 6 hours ago · 12 conversations deleted". If retention is set to "forever": "ניקוי אוטומטי כבוי". If a run errored, show it in warning tone with the error summary. Expose via the existing org-settings GET payload (no new endpoint needed) or a tiny `GET /api/admin/org-settings/retention-status` — pick whichever fits the existing shape.

## Part 2 — Organization language is actually applied (MINIMAL scope; answers always follow the question)

Per spec v1.8 §2.1 (product decision, July 2026), the org language's effect on the UI is DELIBERATELY MINIMAL:

**What changes when org language = Hebrew — exactly two things:**
   - The chat input ghost placeholder ("...Ask about revenue, customers, campaigns" → "...שאלי על הכנסות, לקוחות, קמפיינים" — feminine per AGENTS.md? No: address the USER neutrally — use "אפשר לשאול על הכנסות, לקוחות, קמפיינים").
   - The "New conversation" label → "שיחה חדשה".

**What NEVER changes:** everything else. The sidebar (all other strings), navigation, admin panel, buttons, labels, empty states — remain in English regardless of org language. The layout is anchored — sidebar always LEFT, no `dir="rtl"` on the app shell, no mirroring. Full UI translation is a future i18n pass, out of scope.

5. `default_language` is currently excluded from `PublicOrgSettings` (`api/models.py`). Include it (rename to `language` in the public payload if clearer) so the app can read it. **MVP default = English, always: seed/reset the stored value to English for ALL clients (including both demo tenants), and the setting's default for new orgs is English.** Hebrew is opt-in per org via the admin screen.
6. Frontend consumes it at app init alongside the existing `configureFormatting()` call: applies ONLY the two strings above, and only when the org explicitly set Hebrew. Precedence: org setting → English. No user-level override, no localStorage override, no browser-language detection in the app.
7. Answer-language behavior stays exactly as it is today (the agent always answers in the language of the QUESTION — absolute rule, do not add any org-language instruction to the agent prompts). Update the `AGENTS.md` Agent Voice note to state the final split: org language = the two UI strings above; answer language = always the question's language.
8. Mixed-language reality is expected: English chrome with Hebrew answers is correct behavior. Answer containers keep per-message `dir="auto"` so Hebrew answers render RTL inside the English chrome — verify both directions.
9. Changing the language in the admin screen takes effect for other users on next load; the editing admin's own UI updates immediately.

## Part 3 — Audit semantic draft saves

9. Spec §3.1 lists semantic "draft, publish, restore"; only publish/restore are wired. Add `semantic.draft_saved` (and draft discard/archive) to `log_admin_event` at the existing PUT/DELETE draft routes, with target = section + item name, before/after limited to the changed fields. Add the sentence templates to `auditSentences.ts` in both languages.

## Constraints

- No new deps. RTL-safe copy in both languages. All new server behavior behind the existing middleware/patterns.
- Tests (`pytest`): retention loop unit-tested via direct call (not by sleeping) — assert the 20h skip guard, the run record, the audit event on non-zero deletions, and that an exception in one client's sweep doesn't abort the others; language present in the public settings payload; semantic draft save produces exactly one audit event.
- Run `pytest`, `npm run lint`, `npm run build`.

## Accept

- [ ] With a 30-day policy and seeded old conversations, starting the API results in a sweep within a minute; conversations are soft-deleted; a second immediate restart does NOT re-sweep (20h guard).
- [ ] Org settings screen shows an accurate "last cleanup" line, including the "off" and "error" states.
- [ ] Retention deletions appear in the Audit log with a system actor.
- [ ] Switching org language changes the UI chrome for all users on next load, with no per-user setting anywhere.
- [ ] Answer language still mirrors the question in every case: Hebrew question in an English-configured org returns a Hebrew answer rendered RTL, and the reverse also renders correctly.
- [ ] Saving a semantic draft appears in the Audit log with a readable bilingual sentence.
- [ ] `pytest`, lint, build pass.
