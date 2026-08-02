# Task: Backend QA sweep — systematic tests + findings report before the first real customer

Goal: close the backend QA gaps that per-feature tests don't cover. Two outputs: (a) new automated tests that PASS and stay in the suite, (b) `docs/qa_findings.md` — an honest findings report for anything discovered that can't/shouldn't be fixed inside this task (with severity + recommendation). Do NOT silently expand scope fixing everything found — fix trivial things, report the rest. Follow `AGENTS.md`.

## 1. Authorization matrix (systematic, not sampled)

Auto-discover every registered route (walk the FastAPI app's routes at test time) and assert the expected access class for EACH: `/api/admin/*` → 403/401 for analyst and viewer identities, 200-class for client_admin; chat/product endpoints → accessible to all three roles; gated dev endpoints (`SEMA_ENV=production`) → 404. The test must FAIL if a new route appears without a classification entry — that's the point: future endpoints can't skip the matrix. Include `POST /api/feedback`, exports, logo upload/download.

## 2. Tenant isolation (multi-tenant correctness)

Systematic tests that NOTHING leaks across `ecommerce` ↔ `insurance`: conversations/threads listing, audit events, org settings/logo, home config, alerts, semantic drafts + versions, data-source cards/requests, feedback rows, retention runs. Pattern: create artifact as tenant A, assert invisible via tenant B's identity on every read path (list + direct-ID fetch → 404, not 403 — no existence leak). Document in the findings report the known mocked-identity/workspace limitation and exactly which of these guarantees currently rest on `client_id` plumbing vs. real identity (prep for auth Part A).

## 3. Failure resilience

- LLM API failure modes (mock the provider client): timeout, 429, 500, malformed/truncated response mid-stream → user gets a graceful error answer (existing error shape), no stack trace in the response, conversation not corrupted (next question works), progress panel reaches a terminal state.
- Postgres unavailable: chat query → clean `cannot_answer`-style error; `/healthz` reflects it; recovery works without restart once DB returns.
- API restart mid-conversation: conversation restores from store; no orphaned in-flight state.
- Set/verify explicit timeouts exist for LLM calls and SQL execution (report current values in findings; flag if any path has none).

## 4. Concurrency + SQLite contention

- Async test firing 15-20 parallel chat requests (mocked LLM, real stores): all complete, no "database is locked" errors, no cross-request data bleed (each answer bound to its own conversation).
- Parallel writes to the SQLite state stores (feedback + audit + drafts simultaneously): verify WAL mode is enabled (enable it if not — trivial fix, in scope) and writes serialize without errors.
- Findings report: measure and record simple numbers (p50/p95 latency of the store layer under this load) and state the practical concurrency ceiling of the current single-instance + SQLite design for the pilot.

## 5. LLM cost guardrails (soft limit, in scope)

Per-user daily soft cap: env-configured `SEMA_DAILY_QUERY_LIMIT` (default generous, e.g. 200/user/day; 0 = off). Over the cap → the same quiet policy-style response pattern as access_denied ("הגעת למכסה היומית — פנה לאדמין" / bilingual), audit event `usage.limit_reached` (once per user per day, not per request). Count server-side per org_user per day. UI: no new components — the standard answer card renders the message. Tests: under/at/over the cap, reset next day, limit=0 disables.

## Constraints

- No new deps (use FastAPI TestClient/pytest-asyncio already present; if pytest-asyncio absent, thread-based concurrency is fine).
- Every finding that isn't fixed lands in `docs/qa_findings.md` with: what, where, severity (blocker/high/medium/low), recommended fix, suggested timing (pre-pilot / during pilot / V2).
- `pytest` (full suite + new tests), `npm run lint`, `npm run build` green.

## Accept

- [ ] Route matrix covers 100% of registered routes and fails on unclassified additions.
- [ ] Tenant isolation suite green across all listed surfaces; known limitations documented, not papered over.
- [ ] All failure-mode tests green; timeouts verified/documented.
- [ ] Concurrency tests green with WAL; ceiling documented with numbers.
- [ ] Soft query cap works end-to-end and is audit-logged.
- [ ] `docs/qa_findings.md` exists with an honest, prioritized findings list.
