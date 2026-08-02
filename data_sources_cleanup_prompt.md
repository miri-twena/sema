# Task: Data sources screen — show ONLY real connections

User decision (July 2026): the Data sources screen must show only connections that actually exist and serve data. Today that is exactly ONE card per tenant — the live PostgreSQL source (Healthy / entities mapped / last checked / data age / report a problem), as in the approved screenshot. Everything else currently rendering as a connection is leftover demo/test data and must go.

1. **Purge ALL non-real sources from the live dev DB, both tenants.** Confirmed leftovers visible right now (screenshots from the user): a wizard-created test connection "Warehouse Postgres" (fingerprint ••••3718 — a `client_connections` row), an uploaded test file "orders_sample.csv" (uploads-schema table + its card), and a "Main Priority instance" request card stuck on Requested/Syncing. Delete every test artifact of all three kinds: `client_connections` rows created during development, `source_requests` rows (requests AND interest records), uploaded files/tables in the uploads schema. Make sure the seed/reset path doesn't recreate any of them. The screen then renders only: sources from `config/clients.yaml` `data_sources` whose connector actually runs (today: `type: postgres` — exactly one card per tenant).
2. **Catalog stays, cards don't:** `priority`/`salesforce` remain in the config schema and the connector catalog (for the Add gallery) — they just must never render as connection CARDS unless a real, active connection exists.
3. **Add flow kept, verify the boundary:** the "Add data source" button + gallery stay (they're an add flow, not a fake connection). BUT a submitted request may create an "בהקמה" card again — that's correct behavior going forward (a real pending request from a real admin), only the test leftovers are wrong. Verify a fresh DB/seed shows exactly one card per tenant.
4. If any test in the suite depends on seeded demo requests, fix the test to create its own fixture data instead.

## Gallery updates (user decisions, July 2026)

5. **The "Add data source" button STAYS** — confirmed by the user; real connectors are planned. Do not hide it.
6. **Add to the files group:** "Google Drive" — "Pull spreadsheets and CSV files from a shared Drive folder"; "SharePoint" — "Pull files and lists from SharePoint sites". Behavior like Google Sheets (share/OAuth flow when implemented; placeholder toast for now, consistent with the other cards).
6a. **Add to Business systems:** "SAP Business One" — "Orders, invoices, inventory and financials from SAP B1". Same request-flow path as Priority (SaaS/ERP request, platform-side ETL later). Explicitly B1 — do NOT add a generic "SAP" card (S/4HANA enterprise integration is out of scope and a different market).
7. **Rename the group "מקורות קלים"** → "Files and sheets" (covers Sheets, Drive, SharePoint, Excel/CSV).
8. **Remove the "בקרוב" (Coming soon) group ENTIRELY** — delete the Shopify, Google Analytics, and Meta Ads cards and the group header (drop the interest-recording affordance with them; the catalog entries may stay server-side as inactive, just never rendered).
9. **Language:** per the product-wide "UI is English, always" decision, this modal renders in ENGLISH only (title "Add data source", group headers, card descriptions) — the screenshot shows it in Hebrew, which predates that decision. Align it.
10. **No email/calendar connectors** (decision reversed July 2026): Gmail / Outlook Email / Google Calendar / Outlook Calendar were briefly considered and dropped — privacy scope (personal correspondence, per-mailbox permissions, org consent) is too large for now. Do not add them anywhere.

11. `pytest`, `npm run lint`, `npm run build` green; verify live: both tenants show exactly one PostgreSQL card; the gallery opens in English with 3 groups (SQL databases / Business systems / Files and sheets) and 10 cards total (3 + 3 + 4), no coming-soon group.
