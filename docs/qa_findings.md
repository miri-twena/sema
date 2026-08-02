# Backend QA sweep — findings

Produced by `backend_qa_prompt.md` (PROMPT_QUEUE.md item 18): a systematic
sweep across authorization, tenant isolation, failure resilience,
concurrency, and cost guardrails, ahead of the first real customer. Companion
to the new automated tests in `tests/test_authz_matrix.py`,
`tests/test_tenant_isolation.py`, `tests/test_failure_resilience.py`,
`tests/test_concurrency.py`, `tests/test_query_limit.py`, and
`tests/test_cache.py` — this document covers what those tests *found*, not
what they cover (read the tests' docstrings for that).

## Fixed during this sweep

| What | Where | Severity |
|---|---|---|
| `GET /api/admin/alerts/templates` and `GET /api/admin/alerts/metrics` had no `Depends(require_client_admin)` at all — reachable by anyone with just the API key (or no key at all in local dev), despite living under `/api/admin/` and being intended as admin-only per `alert_templates_prompt.md`'s own scope. Caught by the systematic authorization matrix (`tests/test_authz_matrix.py`), which is exactly the class of bug that test exists to catch — a route that silently drifted from its sibling routes' pattern. Low real-world impact (both routes only return static template/KPI-catalog metadata, no tenant data), but a real authorization gap. | `api/main.py` (`admin_alert_templates`, `admin_alert_metrics`) | Medium (authz gap, no data exposure) |
| Every one of the app's 12 SQLite-backed metadata stores (conversations, org users, audit log, org settings, home config, semantic drafts, alerts, feedback, retention runs, data-source connections/requests/uploads) opened connections with sqlite3's default rollback-journal mode — never WAL. In production ALL 12 share one file (`settings.conversation_db_path`); under concurrent writers, rollback-journal mode takes a database-wide lock for a write's duration, so a slow write in one store can make an unrelated store's write see "database is locked". Fixed with one shared `sema_core/sqlite_utils.connect()` helper (enables `PRAGMA journal_mode=WAL` on every connection) used by all 12 stores. | `sema_core/sqlite_utils.py` + all 12 store modules | Medium (latent, load-dependent) |
| **Postgres connection-pool exhaustion under concurrent load** (originally reported below as finding #1, now fixed as a follow-up in the same task — see "Finding #1, fixed" below for the full root-cause writeup). Two changes: `sema_core.cache.ttl_cache` is now single-flight (a cold cache key is computed by exactly one caller, every concurrent caller for that same key waits and reuses the result, instead of each independently repeating the — often DB-hitting — work), and `SEMA_DB_POOL_MAX`'s default rose from 5 to 20 as real headroom on top of that fix, not a band-aid over it. | `sema_core/cache.py`, `sema_core/settings.py`, `.env.example` | was High, now fixed |

## New feature: per-user daily LLM soft cap (item 5)

Implemented, not just found: `sema_core/query_limit_store.py` (SQLite,
one row per client/org_user/UTC-day), `SEMA_DAILY_QUERY_LIMIT` (default
200/user/day, 0 disables), wired into both `/api/chat` and
`/api/chat/stream` ahead of the real `get_response()` call. Over the cap
returns a `mode="access_denied"` response (same quiet, restrained rendering
as a data-access-scope refusal — no KPI cards/chart/actions), bilingual per
the *question's* language (matching `AGENTS.md`'s "agent answers follow the
question, never the org setting" rule), and logs `usage.limit_reached`
**once per user per day** (a store-level `notified` flag, not once per
over-the-cap request — a capped user asking 10 more questions that day
doesn't spam the audit log 10 times). The capped turn still gets persisted
like any other answer (no special-cased persistence path). See
`tests/test_query_limit.py` for under/at/over/reset/disabled coverage.

Known, deliberate simplification: the cap resets at **UTC midnight**
regardless of the org's own configured timezone (`org_settings.timezone`).
This is a cost guardrail against runaway usage, not a precise usage quota —
matching that to org-local midnight is a fine v2 refinement, not needed for
the pilot.

## Finding #1, fixed: Postgres connection-pool exhaustion was the REAL concurrency ceiling, not SQLite

**Severity: was High, now fixed** (this was the single most actionable
finding in this sweep — fixed as a same-task follow-up once identified).

Item 4 asked to "state the practical concurrency ceiling of the current
single-instance + SQLite design." Measured directly (`tests/test_concurrency.py`):
the SQLite/WAL layer was **not** the bottleneck — 60 parallel writes spread
across 3 stores sharing one file (audit + feedback + semantic drafts, the
production shape) completed in ~2.7s with zero "database is locked" errors,
and 20 parallel `/api/chat` requests (SQLite conversation-store path only,
Postgres mocked) completed with p50=594ms / p95=852ms, no contention.

The real ceiling showed up by accident while writing that same test with
Postgres left **live**: 20 concurrent `/api/chat` requests (a completely
ordinary burst — e.g. a small team opening the dashboard at once) drove
individual request latency to **10–45 seconds** and the server log filled
with `psycopg2.pool.PoolError: connection pool exhausted`. First-pass root
cause: every single `/api/chat`(`/stream`) call — not just ones that run
SQL — builds a `[SEMA-CONTEXT]` pulse block (`_pulse_context` →
`build_daily_brief` → `queries.get_data_bounds`) that checks out a
connection from a `ThreadedConnectionPool` sized `SEMA_DB_POOL_MAX=5` **per
(client, role)**. 5 concurrent in-flight requests is a very low bar for even
a handful of simultaneous users, let alone a burst.

This failure mode was *silent to the end user* — `_pulse_context` and
`daily_brief.py`'s `_max_date` are both deliberately fail-open (catch
`Exception`, degrade to no pulse block) — so nobody saw an error, the app
just got slow-to-unusable under load with no signal in the UI about why.
That combination (invisible + severe) is what made this high severity
rather than medium.

**Deeper root cause, found while fixing it:** the pool size alone wasn't the
real story. `queries.get_data_bounds` (and every other report function) is
already wrapped in `sema_core.cache.ttl_cache` — but the original
implementation only held its lock around the cache *check*, not the
*compute*. Under N concurrent callers racing a **cold** cache (every process
restart, or every TTL expiry under real traffic — `get_data_bounds`'s TTL is
5 minutes), all N would see "not cached" and each independently run the
underlying (DB-hitting) function — a classic thundering-herd / cache-
stampede bug. 20 concurrent chat requests didn't need 5 connections, or even
20 — in the worst case they could all pile onto Postgres at once for
*identical* data, because nothing serialized "the first caller computes,
the rest wait and reuse it."

**Fix (two parts, both landed):**
1. `sema_core/cache.py`'s `ttl_cache` is now single-flight: a per-key lock
   ensures a cold key is computed by exactly one caller, with every other
   concurrent caller for that SAME key blocking on the first one's result
   instead of repeating the work. Distinct keys (different clients,
   different report functions) never block each other. Verified directly:
   `tests/test_cache.py` (20 threads racing a cold key → exactly 1 real
   computation) and `tests/test_concurrency.py`'s
   `test_concurrent_requests_for_the_same_report_hit_postgres_once_not_n_times`
   (the same proof on the actual `queries.get_data_bounds` function
   implicated above).
2. `SEMA_DB_POOL_MAX`'s default raised from 5 to 20 — real headroom now that
   the thundering-herd bug that made 20 concurrent requests need up to 20
   simultaneous connections is fixed, not a band-aid papering over it.

## Not fixed — reported

### 2. Some existing `/api/chat`-path tests transitively depend on a live Postgres connection

**Severity: Low. Timing: during pilot** (test-hygiene, not correctness).

`api/main.py`'s `_internal_context` → `_pulse_context` → `build_daily_brief`
call happens on every `/api/chat` request, including ones in
`tests/test_api_chat.py` that only mock `get_response` itself (e.g.
`test_backend_exception_does_not_leak_internals`). This project's own stated
architecture (`AGENTS.md`, `tests/conftest.py`'s module docstring) is that
`tests/` never touch a live database — this is a pre-existing gap (confirmed
present before this sweep, not introduced by it), currently masked because
Postgres happens to be reachable in every developer's local Docker stack.
It would silently break (hang or error, depending on reachability) in a CI
environment with no Postgres running. `tests/test_authz_matrix.py`,
`tests/test_concurrency.py`, and `tests/test_failure_resilience.py`
(this sweep's own new tests) all explicitly mock `build_daily_brief` /
`build_overview` / `alerts_engine.evaluate_all_alerts` /
`org_alerts.readings_for_alerts_engine` for exactly this reason — the
pre-existing `/api/chat`-route tests were not touched, to keep this sweep's
diff scoped to what it was asked to add. **Recommendation:** either add the
same mock to `tests/conftest.py` as an autouse fixture (risk: could mask a
future *real* regression in pulse-context error handling if it's mocked too
broadly) or accept the live-DB dependency as a documented trade-off for this
one code path.

### 3. Tenant isolation guarantees rest on `client_id` plumbing, not real identity — by design, today

**Severity: Informational (documents an existing, known limitation).**

There is no real login yet (`sema_core/current_user.py`): every request's
identity resolves to one hard-coded mock user. Every cross-tenant isolation
guarantee this sweep verified (`tests/test_tenant_isolation.py`) — the
`WHERE client_id = ?` filtering in every store, the 404-not-403
indistinguishable-from-unknown convention — is enforced at the **store**
layer, keyed on whatever `client_id` reaches it. For `/api/admin/*` routes
that's `require_client_admin`'s resolved identity; for the non-admin
conversation routes (`/api/conversations*`, `/api/feedback`) `client_id` is
a **plain query parameter**, not derived from identity at all (see
`_resolve_client`) — a deliberate, documented choice ("no login yet"), not
an oversight. When real auth (`auth_login_prompt.md` Parts A+B) lands and
`current_identity()` starts reading a verified session, every guarantee
proven here keeps holding unchanged, because the enforcement point is the
store layer's `client_id` filtering, not the identity mechanism above it —
but until then, anyone who can construct a request can pick which tenant's
`client_id` to send on those non-admin routes (mitigated only by needing to
already know/guess a real `conversation_id`, which is an unguessable UUID).
This is the exact same limitation already documented in
`docs/deployment.md`'s "no real authentication yet" warning; recorded here
too because item 2 explicitly asked for it, not because it's new.

### 4. `TurnFeedbackStore` performs zero `client_id` filtering at the store layer

**Severity: Low (currently safe by construction, but a sharp edge for future code).**

`TurnFeedbackStore.get()` / `get_for_conversation()` take a `conversation_id`
only — no `client_id` parameter exists on either method, so the store itself
would happily return tenant B's feedback given tenant B's `conversation_id`.
This is safe **today** only because every current caller in `api/main.py`
(`GET /api/conversations/{id}`, `POST /api/feedback`) validates the
conversation's ownership via `conversation_store` *before* ever touching
`feedback_store` — confirmed by both a store-level test proving the gap
exists in isolation and a route-level regression test proving the guard
holds (`tests/test_tenant_isolation.py`). Every OTHER app-owned store
(`org_alerts`, `client_connections`, `uploads`, `source_requests`,
`semantic` versions) enforces `client_id` in its own SQL `WHERE` clause,
making this one store an inconsistent outlier. **Recommendation:** add a
`client_id` parameter to `TurnFeedbackStore`'s read methods (mirroring every
sibling store) the next time this file is touched for another reason — not
urgent enough to justify a standalone change today, since the route-layer
guard is real and tested, but worth closing so a *future* route can't
reintroduce the same class of bug by calling the store directly.

### 5. Explicit timeouts — verified present (not a gap, recorded per item 3's own ask)

- **LLM calls:** `Anthropic(timeout=settings.anthropic_timeout_s, max_retries=settings.anthropic_max_retries)` —
  defaults 60s / 2 retries (`sema_core/agent/agent.py`, both the main `run()`
  and `generate_title()` construct the client this way). Confirmed via a new
  structural test (`tests/test_failure_resilience.py`).
- **SQL execution:** the read-only Postgres role's session sets
  `statement_timeout` from `settings.statement_timeout_ms` (default 5000ms)
  via connection `options` at pool-creation time (`sema_core/db.py`'s
  `READONLY_TIMEOUT_MS`). Confirmed via a new structural test.
- Both were already correctly wired before this sweep — nothing to fix here,
  included for completeness against the prompt's explicit accept criterion.

### 6. A truncated model response degrades to an empty answer, not a message

**Severity: Low (UX polish, not a crash risk).**

If the model's response is truncated (`stop_reason="max_tokens"`) before it
emits any text block at all, `agent.run()`'s prose-answer fallback
(`agent.py` line ~403-409) joins zero text blocks and returns
`insight_text=""` — an empty answer, not a crash, but also not the
"graceful error answer" a user would expect (confirmed via
`tests/test_failure_resilience.py::test_truncated_response_with_no_text_never_crashes_the_loop`).
In practice this needs a response so severely truncated it cuts off before
any prose at all, which is rare (`MAX_TOKENS` is generous) — not urgent, but
a one-line fix (fall back to `unavailable_text`-style copy when
`final_text` is empty) would be trivial the next time this function is
touched.

### 7. `test_org_settings.py`'s conflict-detection test is a genuine Windows timestamp-resolution race

**Severity: Informational (test-infra, not product code).**

`test_update_flags_conflict_when_stale_but_still_applies` has been flagged
"pre-existing, flaky, unrelated" in nearly every `PROMPT_QUEUE.md` entry for
months without anyone confirming *why*. Root-caused during this sweep:
`datetime.now(timezone.utc).isoformat()` on this Windows dev machine has
coarse enough clock resolution that two `store.update()` calls executed
back-to-back in the same test can produce the **identical** timestamp string
(confirmed directly: two consecutive calls returned
`2026-08-02T11:40:22.003250+00:00` both times). The test's conflict check
compares timestamp strings for inequality, so on the (uncommon but real) tick
where both calls land in the same clock granule, it sees no change and
reports no conflict. Full suite run: 918 tests, this one failed once,
passed 5/5 on immediate retry — consistent with a low-probability race, not
a deterministic bug. Not fixed here (out of this sweep's scope — the fix is
either a monotonic counter alongside the timestamp or accepting sub-tick
imprecision), but recorded with an actual root cause instead of "known
flaky" for the next person who hits it.

## Explicitly out of scope for this sweep

- **`SEMA_ENV=production`-gated dev-only routes → 404**: audited (walked
  every registered route, see `tests/test_authz_matrix.py`) — no such route
  exists in the app today (confirmed independently during
  `deployment_prep_prompt.md` too). Nothing to test until one is added; the
  route-classification harness has room for a third `prod_gated` bucket
  whenever that happens.
- **API restart mid-conversation**: verified conversation state survives a
  simulated process restart (a fresh `SqliteConversationStore` instance
  against the same file sees everything the old one wrote) — there is no
  orphaned in-flight state to lose in the first place, because `/api/chat`
  and `/api/chat/stream` only ever persist a turn *after* `get_response`
  returns successfully (see the "conversation not corrupted" tests in
  `tests/test_failure_resilience.py`).
