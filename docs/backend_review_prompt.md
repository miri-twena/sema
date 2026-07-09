# SEMA Backend — Code Review Fixes & Hardening

You are a senior backend engineer in a modern SaaS company. Apply the following
improvements to the SEMA backend (api/, app/agent/, app/db.py,
app/client_registry.py, app/wiring.py, app/components/alerts_engine.py).
Work in priority order. Keep the existing API contract (api/models.py) stable.
Explain each change briefly before implementing (per CLAUDE.md mentoring style).

## P0 — Correctness & tenant-safety bugs

1. **Per-client schema cache bug** (`app/agent/tools.py`):
   `_introspect_schema()` uses `@lru_cache(maxsize=1)` but resolves the active
   client inside — after switching clients the agent gets the PREVIOUS
   client's schema. Fix: make it `_introspect_schema(client_id: str)` cached
   per client, and pass `active_client_id()` explicitly from `get_schema()`.

2. **Silent tenant fallback** (`app/client_registry.py`):
   `get_client_by_id()` silently returns the FIRST client for an unknown id.
   An API call with an invalid `client_id` silently queries the wrong
   tenant's database. Fix: raise `ClientConfigError` for unknown ids; in
   `api/main.py` validate `client_id` at the top of every endpoint and return
   HTTP 404 for unknown clients. Never fall back across tenants.

3. **Error handling & leakage** (`api/main.py`, `app/wiring.py`):
   - `/api/chat` returns `error=str(exc)` to the client — internal details
     (paths, SQL, driver errors) leak out. Log the full traceback server-side
     with a generated request_id; return a generic message + request_id in
     `ChatResponse.error`.
   - `wiring.get_response` swallows agent exceptions with bare `pass`. Log
     them (logger.exception) before falling back to the rule-based router.

## P1 — Architecture: decouple core from frameworks

4. **Framework-free core**: `app/db.py` uses `@st.cache_resource` and
   `alerts_engine` uses `@st.cache_data`, yet both are imported by FastAPI.
   Refactor:
   - Replace Streamlit caching in db.py with a framework-neutral mechanism:
     a module-level dict of connections keyed by client_id (or SQLAlchemy
     engines, see #5). Streamlit and FastAPI both consume the same core.
   - In alerts_engine, replace `st.cache_data(ttl=120)` with a small TTL
     cache (e.g. cachetools.TTLCache or hand-rolled timestamp check).
   - Move shared backend modules toward a proper package (e.g. `sema_core/`)
     with a pyproject.toml, eliminating the sys.path hack in api/main.py.
     Do this incrementally; keep Streamlit working at every step.

5. **Connection pooling**: a single cached psycopg2 connection per client is
   shared across concurrent FastAPI requests (threadpool) — unsafe under
   load. Replace with SQLAlchemy engines (one per client_id per role:
   full + readonly) with pool_pre_ping=True. This also removes the pandas
   "only supports SQLAlchemy" warning suppression and the manual
   stale-connection retry in run_query/run_sql_readonly.

6. **Centralized settings**: create a `settings.py` (pydantic-settings)
   for: ANTHROPIC model name (currently hard-coded "claude-sonnet-4-6" in
   agent.py), MAX_ITERATIONS, MAX_TOKENS, statement timeout, CORS origins,
   DB credentials, row limits. All read from env with sane defaults.

7. **Observability**: add structured logging (std logging, JSON-ish) across
   the agent loop and API:
   - per /api/chat request: request_id, client_id, question length, duration,
     number of tool calls, SQL statements run, model token usage
     (response.usage input/output tokens) and stop_reason.
   - This is the foundation for per-tenant cost tracking — log it now even
     if it's only read from log files.

## P2 — Hardening & product readiness

8. **Anthropic client robustness** (agent.py): pass an explicit timeout and
   max_retries to `Anthropic(...)`; catch `anthropic.APIError` distinctly and
   surface a friendly "the AI service is temporarily unavailable" response
   instead of falling into the generic exception path.

9. **Input validation on the contract** (api/models.py): use
   `Literal["user","assistant"]` for Message.role, Literal enums for
   status/severity/chart kind; add max lengths (question, history size).
   Reject histories over N items with 422 instead of silently truncating.

10. **Tests** (pytest, no live DB / no API key needed):
    - safety.py: table-driven tests — allowed (SELECT, WITH, UNION,
      auto-LIMIT added/preserved) and rejected (INSERT/UPDATE/DELETE/DROP,
      multi-statement, empty, unparsable).
    - response.build_response: chart/table binding by result_index,
      out-of-range indices, missing optional fields.
    - agent.run with a fake client object (scripted tool_use responses):
      happy path, max-iterations path, prose-answer fallback.
    - client_registry: unknown id now raises; override ContextVar behavior.
    - serialize.to_chat_response: DataFrame -> columns/rows, dates/Decimals.

11. **SQL safety polish** (safety.py): also reject queries touching
    pg_catalog/information_schema when called via the agent tool (schema
    should come from get_schema), and cap LIMIT even when the model supplies
    one larger than DEFAULT_ROW_LIMIT.

12. **API auth scaffold**: add a simple API-key dependency (X-API-Key header
    checked against env) applied to all routes — a placeholder for real
    auth, but it closes the "anyone on the network can query any tenant"
    hole today. Structure it as a FastAPI dependency so swapping in JWT
    later is trivial.

## Product-architect notes (design for these, don't build yet)

- **Streaming**: /api/chat is a single blocking call that can take 20-30s
  (multiple LLM rounds + SQL). Plan an SSE endpoint streaming agent progress
  ("running query 2...") and the final structured answer. Keep the current
  endpoint; add streaming alongside.
- **Server-side conversations**: history currently ships from the client on
  every request (payload grows unboundedly, cap is turns not tokens). Plan a
  conversation_id + server-side store (start with SQLite/Postgres table).
- **Agent evals**: create a golden-question set per client (question ->
  expected metric/direction) and a script that runs them and scores answers.
  This is the regression suite for prompt/model changes.
- **Feedback loop**: add thumbs up/down on answers to the contract
  (ChatResponse already stable) — the data feeds the eval set.
- **Semantic-layer versioning**: metric YAMLs are the product's source of
  truth; plan git-tagged versions + a changelog so answer changes are
  attributable to definition changes.

## Definition of done
- All P0 items fixed with tests proving the bug is gone.
- Streamlit app AND FastAPI both work after each refactor step.
- `pytest` green; no Streamlit import required to run api/ or the test suite.
