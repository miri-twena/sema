# Task: Data access scopes (metric/domain-level permissions) — "what each user may ask about"

Adds a second permission axis alongside role: **data scope** — which semantic domains and metrics a user's questions may touch. Role = what you can *do* in the product; data scope = what you can *ask about*. OLS-style (metric/object-level), not RLS — row-level filtering stays out of scope (V2). Follow `AGENTS.md`; backend `sema_core/` + `api/`, frontend `frontend/`. Builds on the Users and permissions screen (`admin_users_screen_prompt.md`) and the mock-identity middleware — still no real auth.

## Semantic layer

1. Add a `domain` field to every metric/entity in the semantic YAML (`sql/semantic/`): one of `sales`, `customers`, `marketing`, `finance`. Additionally tag profitability-sensitive metrics (gross margin, profit, costs, COGS, LLM-cost style metrics) with `sensitive: financials`. YAML stays the single source of truth; validate on load (unknown domain = startup error).
2. Scope presets defined server-side in one place (config/constant, not per-user rows):
   - `full` — all domains, all metrics.
   - `no_financials` — all domains except `finance`, plus any metric tagged `sensitive: financials` is blocked even inside allowed domains.
   - `sales_only` — `sales` domain only (and finance/sensitive blocked by implication).
   - `custom` — reserved for V2: schema allows it, UI disables it, server rejects PATCH to it.

## Backend

3. `org_users.data_scope ENUM('full','no_financials','sales_only','custom') NOT NULL DEFAULT 'full'`. Rule: `client_admin` is always `full` (enforced server-side — PATCHing an admin's scope or promoting a scoped user to admin resets/requires `full`).
4. Seed (matches existing seed users): Dan Avrahami (CEO, viewer) → `full`; Avi Peretz (CFO, viewer) → `full`; Miri (admin) → `full`; Noa Berman + Demo User + Tamar Golan → `no_financials`; Yossi Cohen (retitle to Sales Analyst) → `sales_only`; Lior Katz → `no_financials`; pending invite dana → `no_financials`.
5. API:
   - `GET /api/admin/data-scopes` — catalog for the UI: id, display name, one-line description, included/excluded domains, whether selectable (custom = false). Single source of truth for legend + editor copy.
   - Extend `/api/admin/users` list/detail payload with `data_scope`; `PATCH` accepts `data_scope`; invite accepts optional `data_scope` (default `no_financials`).
   - Guards: only client_admin may change scopes; cannot change own scope; cannot set `custom`.
6. **Enforcement in the agent pipeline (the core of this task).** After the agent resolves which metrics/entities a planned query touches and BEFORE SQL execution, check them against the requester's scope (requester = mock identity for now — same middleware seam):
   - All touched items allowed → proceed unchanged.
   - Any blocked → do NOT execute. Return a structured `access_denied` answer: which topic is blocked (human phrasing, not metric ids), what the user CAN ask about (from their scope), and "contact your admin". Never silently drop blocked metrics from a multi-metric question — if any part is blocked, say so explicitly (partial answers allowed only when the user's question decomposes cleanly and the answer states what was omitted and why).
   - Enforcement lives server-side in `sema_core` (not the frontend, not the prompt): treat the LLM as untrusted — even if the model plans a blocked query, execution is refused. Add the user's scope summary to the agent's context so it can also decline early and phrase alternatives well.
7. Scope applies everywhere answers are produced: chat, drill-down threads, daily brief, home-screen KPIs, suggested/trending questions (filter out suggestions touching blocked domains). Brief generators that need blocked metrics simply skip those cards for that user.

## Frontend

8. **Users table:** new "Data access" column between Role and Last active — pill badge per scope (Full access / No financials / Sales only), distinct muted tints, ⓘ affordance on the column header opening a legend built from `GET /api/admin/data-scopes`. Admin rows show "Full access" with no edit affordance.
9. **Scope editor:** clicking the badge (or from the user detail drawer) opens a panel/popover — radio list of presets, each with name + one-line description; `sales_only` shows domain chips (included highlighted, excluded muted); `custom` rendered disabled with a "V2" tag. Optimistic PATCH, toast on failure. Own row and admin rows: read-only.
10. **Chat blocked state:** render `access_denied` answers as a distinct quiet variant — lock icon, one-line "not included in your access" + the can-ask summary. No red/error styling (it's policy, not failure). RTL-safe; copy in Hebrew/English per app language.
11. Invite modal: add scope select (default No financials) under the role select.

## Constraints

- No new deps; RTL-safe logical properties; keyboard accessible (editor is a focus-trapped popover, `useDismiss`).
- Copy tone: matter-of-fact, no apology spiral. Hebrew: "נתוני רווחיות אינם כלולים בהרשאות שלך."
- Tests (`pytest`): enforcement matrix (each preset × allowed/blocked metric), admin-always-full rule, own-scope guard, brief/suggestions filtering. Run `npm run lint`, `npm run build`.

## Accept

- [ ] Semantic YAML items carry `domain` (+ `sensitive: financials` where relevant); loader validates.
- [ ] Yossi (sales_only) asking about gross margin gets a structured refusal naming the block + what he can ask; same question from Avi (full) answers normally.
- [ ] Multi-metric question with one blocked metric is refused/flagged — never silently trimmed.
- [ ] Brief, home KPIs, and suggested questions respect scope per user.
- [ ] Admin UI: Data access column + legend + editor work end-to-end with guards (admin locked to full, no self-change, custom disabled).
- [ ] `pytest`, lint, build pass.
