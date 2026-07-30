# Task: Semantic model screen in the client admin panel

Implement the "Semantic model" tab (nav id `semantic-model` in `frontend/src/components/admin/AdminPanel.tsx`) per the approved mockups. Follow `AGENTS.md`; reuse the admin shell patterns from the Users slice (`UsersScreen.tsx`, `Toast.tsx`, admin middleware, `/api/admin/*` conventions).

## Concept

The semantic layer (`sql/semantic/*.yaml`, loaded by `sema_core/agent/semantic.py`) becomes editable from the panel and grows beyond metrics. Editing flow everywhere: **Draft → Validate → Publish**. Drafts live in the DB; YAML on disk stays the published source of truth — ONLY the server writes it, on Publish. Every publish snapshots a version with author + timestamp, restorable.

## Data model (extend the YAML schema, keep loader backward-compatible)

Five sections; new files alongside existing metric YAMLs:

- **Metrics** (existing files): add optional `status: certified|draft|deprecated`, `synonyms: []`.
- **Entities** (`entities.yaml`): entity name, table, grain, allowed joins (read-only in UI this slice — auto-derived where possible from schema; editing = V2).
- **Business rules** (`rules.yaml`): `name`, `definition` (plain language), `logic` (SQL fragment, optional), `applies_to: [metric names]`, `status`.
- **Calendar & knowledge** (`knowledge.yaml`): items with `type: recurring_event|incident|note`, `name`, `date_range` (or `recurrence`), `description`, `affects: [metrics/tables]`.
- **Glossary** (`glossary.yaml`): term → canonical metric/entity mapping, Hebrew + English terms supported.

## Backend

1. `GET /api/admin/semantic` — full model (published + the caller's drafts merged, draft-flagged). `PUT /api/admin/semantic/{section}/{name}` — save draft. `DELETE` — discard draft or archive published item (archive = `deprecated`, never hard-delete).
2. `POST /api/admin/semantic/validate` — dry-run: for metrics/rules with SQL, execute against the DB via the existing read-only role + safety guards (`sema_core/agent/safety.py`), scoped to the last complete month, LIMIT-protected; return computed value, row count, duration, or a specific error. For non-SQL items: schema validation only.
3. `POST /api/admin/semantic/publish` — re-validate server-side, write the YAML files atomically, snapshot previous state into `semantic_versions` table (full YAML blob, author, timestamp, changed items), bump version, hot-reload the agent's semantic loader (add a reload hook to `semantic.py` if loading is cached), audit-log the change. `POST .../restore/{version_id}` reverses to a snapshot (itself creating a new version).
4. Agent integration (minimal, this slice): loader exposes the new sections; `get_semantic_layer` tool output includes business rules, knowledge items overlapping the queried date range, and glossary synonyms. Prompt additions (`prompts.py`): cite applicable rules as assumptions; add caveat when an incident overlaps the answer's date range; treat glossary terms as synonyms. Keep additions compact — the full "relaxed anomaly detection" behavior is out of scope.
5. Client-admin permission via existing middleware; all writes audit-logged.

## Frontend — per the approved mockups

Screen header: "Semantic model", publish status chip ("Published v12 · N drafts"). Tab bar with counts: Metrics · Entities · Business rules · Calendar & knowledge · Glossary.

- **Metrics tab:** two-pane — searchable metric list (draft dot indicator) + editor: business definition input, SQL expression (mono, LTR-isolated — reuse `.sema-code` conventions), format select, synonyms input, status badge, version line ("v4 · edited by {name} · History"). Buttons: Discard / Run validation / Publish (Publish enabled only after passing validation of THIS draft). Validation result banner: green with computed value ("Read-only dry run on Jun 2026: $661.46 across 1,951 orders · 0.4s") or red with the error.
- **Business rules tab:** card list per mockup — name, status badge, plain-language definition, mono logic line, "Applies to: …" footer + "cited in answers as an assumption". Add/edit in an inline expanding card (no separate page).
- **Calendar & knowledge tab:** card list with type icon (calendar-event / alert-circle / bulb), name + date range, description, one-line agent-effect note. "Add event or note" opens an inline form (type, name, dates/recurrence, description, affects).
- **Entities tab:** read-only cards (entity, table, grain, joins) with an info note that editing arrives later.
- **Glossary tab:** simple two-column editable list (term → maps to), add row inline, RTL-safe for Hebrew terms (`dir="auto"`).
- History: a slide-over listing versions (author, date, changed items) with Restore (confirm popover via `useDismiss`).

## Constraints

- YAML writes: atomic (temp file + rename), preserve key order where feasible; server-side only.
- Validation SQL runs ONLY under the read-only role and existing safety checks; never trust client SQL text beyond that.
- RTL-safe UI; SQL/logic always LTR-isolated. No new frontend deps (a YAML lib in Python is fine if one's already in `requirements-api.txt` — check; PyYAML is standard).
- Tests: validate endpoint (good SQL, bad SQL, injection attempt rejected by safety layer), publish snapshot + restore round-trip, loader backward-compat with pre-existing YAMLs lacking new fields. Run `pytest`, `npm run lint`, `npm run build`.

## Accept

- [ ] Edit AOV's definition → validate shows a real computed value → publish updates `sql/semantic/*.yaml`, bumps version, and the agent's next answer uses the new definition.
- [ ] Business rule and knowledge item can be created, published, and appear in `get_semantic_layer` output; incident overlap adds a caveat to answers.
- [ ] Draft state survives navigation; Publish disabled until validation passes; restore returns the previous YAML exactly.
- [ ] Pre-existing YAML files load unchanged; `pytest`, lint, build pass.
