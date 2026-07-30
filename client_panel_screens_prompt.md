# Task: Client panel — Organization settings, Audit log, Home screen, Data sources

Implements `SEMA-Client-Screens-Spec.pdf` (v1.1) — the four remaining nav items in `frontend/src/components/admin/AdminPanel.tsx`. Follow `AGENTS.md`; reuse the admin shell patterns (UsersScreen/SemanticModelScreen, `require_client_admin` middleware, `/api/admin/*` conventions, Toast, `useDismiss`).

**Work in 4 phases, in this order. Each phase must end green (`pytest`, `npm run lint`, `npm run build`) and be a natural `/clear` point — do not start the next phase with failing tests.** Flip each nav item to `active: true` only when its phase is done.

## Phase 1 — Organization settings (spec §2)

1. Table `org_settings(client_id PK, name, logo_path, timezone, currency, number_format, default_language, retention_policy ENUM('forever','90d','30d'), updated_at)`; seed current demo values for both tenants. `GET/PATCH /api/admin/org-settings` — PATCH is per-field (partial), validates (timezone from pytz-style list, currency from a fixed list), audit-logs every change with before/after.
2. Logo upload: `POST /api/admin/org-settings/logo` — PNG/SVG ≤1MB, stored under a server `var/` path, served via API; reject others with a specific error. Sidebar renders logo when present, initials-avatar otherwise.
3. Effects wiring: timezone feeds the governed calendar config the agent already uses (day boundaries) — change applies forward only, show the warning from the spec before saving; currency/number_format drive a shared frontend formatting util (display only, no conversion) used by KPIs/tables/charts; default_language = default for new users, personal preference wins.
4. Retention: daily job (reuse the existing scheduling/seed mechanism style) soft-deletes conversations older than policy. Changing policy returns a preview count ("N conversations will be deleted on next run") and requires confirm.
5. UI: single form in 4 groups (Identity · Time and region · Display · Data), per-field silent save, errors inline. Concurrent edit: last-write-wins + toast to the loser (compare `updated_at`).

## Phase 2 — Audit log (spec §3)

6. Table `audit_events(id, client_id, actor_id, actor_name, actor_role, action, target_type, target_id, target_label, before JSON, after JSON, created_at)`, indexes `(client_id, created_at)` and `(client_id, actor_id)`. Append-only: no UPDATE/DELETE paths, period.
7. Single write point: extend the existing `log_event` mechanism (`sema_core/obs.py`) so admin-action events ALSO persist to the table — one call site per action, no double logging. Wire ALL existing admin actions: users (invite/role/data_scope/suspend/remove/resend), semantic (draft/publish/restore — already logged), org-settings changes, and the phase-3/4 actions when they land. Canonical action ids (`user.role_changed`, `semantic.published`, ...).
8. `GET /api/admin/audit` — filters: actor, category (prefix match on action), date range, free-text on target_label; server-side pagination 50/page. `GET /api/admin/audit/export` — CSV of the current filter, cap 10K rows.
9. UI per spec: chronological table (relative time, actor avatar, human-readable sentence built from action id + target in the app language, category tag), filters toolbar, row click → drawer with field-by-field before/after diff, CSV button. Impersonation events get an amber side bar (event type exists even if impersonation itself is platform-level and not yet built).

## Phase 3 — Home screen customization (spec §1)

10. Table `org_home_config(client_id, draft JSON, published JSON, version, published_by, published_at)`. `GET /api/admin/home-config`, `PUT` (draft autosave), `POST /publish` (server-side validation: metrics exist and are certified, ≤4 pulse metrics, 4-8 KPIs, thresholds in range; snapshot + audit), `POST /revert`. The app's home screen reads the published config through the existing home/overview endpoint.
11. Editor UI: settings column (~380px) + live preview. Preview = the REAL home screen components rendered read-only with the draft config and the admin's own data scope (note shown if scope hides parts). Four accordion areas: Daily brief (layer toggles, pulse metric picker ≤4 certified metrics with drag order, sensitivity conservative/balanced/sensitive), Business overview (KPI picker 4-8 with drag order + delta toggle, default period), Suggested questions (edit list, org questions with save-time agent-answerability warning, Trending toggle), Alerts (per-type toggle + threshold; email/Slack shown disabled "V2"). Opening an area scrolls/highlights the matching preview region.
12. Status chip ("טיוטה · לא פורסם" / "פורסם לפני שעה"), Publish + Revert buttons. Graceful degradation: if the two-layer brief (`daily_brief_prompt.md`) isn't implemented yet, hide the sensitivity control and keep layer toggles working against the current brief.
13. Per-user scope filtering at render time (server-side): a user whose data scope blocks finance never receives finance KPIs/cards regardless of config. Deprecated/deleted metric: auto-dropped from render, warning badge in the editor.

## Phase 4 — Data sources, view-only slice (spec §4)

14. Source registry: config-level list per client (`postgres` for both demo tenants; the schema supports `priority`/`salesforce` types for later). Table/config exposes: type, display name, status, last_sync_at, sync_duration, primary date field. For the live Postgres source, health = the existing daily check + data age (`MAX(order_date)` style query per tenant).
15. Add `source` to semantic entities (default `postgres`, loader backward-compatible); map source→entities→dependent metrics server-side.
16. `GET /api/admin/data-sources` — cards payload incl. mapped entities + dependent metrics. `POST /api/admin/data-sources/{id}/report-problem` — creates an audit event + logs a platform notification (no email).
17. UI: status cards per spec — type logo/icon, status pill, last sync, data age, mapped-entities expander showing "revenue, aov ← Postgres" chains; error state banner + "Report a problem" (confirm, includes source details automatically). Read-only: no credentials, no editing, fingerprint only if present. Explicitly OUT OF SCOPE: Priority/Salesforce ETL connectors — schema-ready only.
18. Evidence integration (small): agent evidence panel shows source + freshness for the queried entities; if the source's last sync failed/stale, append the caveat ("נתוני X עודכנו לאחרונה לפני N ימים") — computed server-side like the incident caveat.

## Constraints

- RTL-safe (logical properties), keyboard accessible, no new frontend deps; Hebrew/English copy parity everywhere.
- All writes behind `require_client_admin`; audit-log everything that mutates.
- Tests per phase: settings validation + retention preview; audit persistence/filters/append-only (attempt UPDATE → fails); home-config publish validation + scope filtering + deprecated-metric drop; data-sources payload + stale-source caveat.

## Accept

- [ ] Phase 1: all fields editable with effects live (timezone warning, currency formatting, retention preview+job); changes audited.
- [ ] Phase 2: every existing admin action appears in the log with correct before/after; filters, pagination, CSV, drawer diff work; table is append-only.
- [ ] Phase 3: edit → live preview updates → publish → real home screen changes for all users; scope filtering and deprecated-metric handling verified; revert restores previous published config.
- [ ] Phase 4: status cards live for the Postgres source on both tenants; trust chain visible; report-problem creates an audit event; stale-data caveat appears in answers.
- [ ] All four nav items active; `pytest`, lint, build green after every phase.
