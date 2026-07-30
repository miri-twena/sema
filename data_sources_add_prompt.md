# Task: Add data source — connector gallery, SQL DB wizard with credentials, Sheets/CSV, request flow

Implements spec §4.4 (`SEMA-Client-Screens-Spec.pdf` v1.6). Builds ON TOP of the completed Phase 4 slice (`sema_core/data_sources.py`, `GET /api/admin/data-sources`, status cards, report-problem). Three add paths by connector kind. Follow `AGENTS.md`.

## Connector catalog (config-driven)

1. Server-side catalog (extend the `data_sources` config pattern): each connector = id, kind (`sql_db` / `saas_request` / `light`), label, one-line "what it unlocks" (bilingual), availability (`available` / `coming_soon` / `driver_pending`). Initial catalog:
   - `sql_db`: PostgreSQL (available — driver exists), MySQL (available IF `pymysql` can be added cleanly — pure-Python, pre-approved dep; otherwise `driver_pending`), MS SQL Server (attempt `pymssql`/`pyodbc` ONLY if it installs without system-level packages in the container; otherwise show the card as `driver_pending` — visible, explains "בקרוב", records interest. Do NOT fight ODBC for hours).
   - `saas_request`: Priority ERP, Salesforce.
   - `light`: Google Sheets, Excel/CSV upload.
   - `coming_soon`: Shopify/WooCommerce, Google Analytics, Meta Ads — click records interest (audit + platform log).

## Path A — SQL DB self-service wizard (the credentials panel)

2. **4-step wizard** (modal/stepper in the Data sources screen): (1) connection details — host, port (default per engine), database, user, password, SSL toggle; (2) test connection; (3) schema review — tables found + detected date fields, semantic-layer association (default template or empty); (4) done — card appears active with first health check.
3. **Credentials handling — production bar:**
   - Write-only: sent once over the API, NEVER returned in any response, never logged, never in audit payloads, never in error messages (scrub connection errors of passwords).
   - Encrypted at rest: `cryptography` Fernet with key from `SEMA_SECRETS_KEY` env (add `cryptography` to requirements if absent — pre-approved; document key generation in `.env.example`). Stored in a new `client_connections` table, not in YAML/config.
   - After save: UI shows host/database + a fingerprint (e.g. last 4 of a hash), edit requires re-entering credentials.
4. **Test connection** (`POST /api/admin/data-sources/test`): connectivity → read probe → **write-permission probe** (engine-specific check whether the user has INSERT/UPDATE/DDL rights). If write perms detected: prominent warning + ready-to-copy read-only-user SQL snippet per engine (all three), continue only via explicit acknowledgment checkbox. Never store the credentials before a passed test.
5. Created source plugs into the EXISTING health/status machinery (`source_health`, cards, stale caveat) — one source model, no parallel path.

## Path B — SaaS request flow (Priority, Salesforce)

6. Non-secret form (display name, environment, technical contact, notes — server-side validation that no credential-like fields are accepted), creates `source_requests(id, client_id, connector_type, details JSON, status ENUM('requested','configuring','testing','active','rejected'), created_by, created_at)` + audit + platform log. Card renders immediately in "בהקמה" with a 4-step progress rail (בקשה נשלחה ← בהגדרה ← בבדיקה ← פעיל); status transitions are platform-side only (internal/dev endpoint).

## Path C — Light sources (mid-market reality)

7. **Google Sheets:** paste sheet URL → instructions screen "share with {service-account email} (read-only)" (email from env `SEMA_GSHEETS_SA_EMAIL`; if unset, flow still works and the source lands in "בהקמה" awaiting platform setup) → validate button checks access when the service account is configured → preview of columns → synced as a table into the analytics DB on a schedule (reuse the retention-job scheduling pattern). No client credentials at any point.
8. **Excel/CSV upload:** file upload (10MB cap, .csv/.xlsx — parse with the existing Python stack) → column preview + type inference → lands as a table in a dedicated `uploads` schema in the client's analytics DB → source card with "replace file" action. Table becomes available to the semantic model like any other (mapping done in the Semantic model screen).

## Constraints

- RTL-safe, bilingual, keyboard-accessible wizard; `useDismiss` for modals.
- Audit every action (create/test-fail/test-pass/request/interest/upload/replace) — never with credentials or file contents.
- Tests (`pytest`): encryption round-trip; credentials absent from every GET/list/audit/log output (assert by grepping responses); write-permission probe warning path; test-before-store enforced; request flow rejects credential-like fields; CSV upload type inference + replace; catalog gating (driver_pending never opens the wizard). Run `npm run lint`, `npm run build`.
- Note in the final report which of MySQL/MSSQL ended up available vs driver_pending and why.

## Accept

- [ ] Admin connects a real PostgreSQL DB end-to-end from the client panel: details → test (with write-perm warning if applicable) → schema review → active card with health.
- [ ] Credentials are nowhere retrievable after save (API, logs, audit, errors); edit requires re-entry; fingerprint shown.
- [ ] Priority/Salesforce request creates a tracked "בהקמה" card; coming-soon clicks record interest.
- [ ] Google Sheets flow reaches "בהקמה" (or fully syncs when SA configured); CSV upload produces a queryable table and its card.
- [ ] `pytest`, lint, build pass.
