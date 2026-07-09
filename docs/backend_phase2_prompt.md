# SEMA Backend — Phase 2: finish deferred work & build the product layer

**Token efficiency — strict:** read only the files you actually need; show
diffs, not full file rewrites; no re-reading files you already have in
context; keep explanations to 1-2 sentences per change; don't re-run the full
test suite after every micro-edit — run it once per step. Skip pleasantries
and long summaries.

**Product hat:** alongside the engineering work, act as a product architect —
at the END of the session, give me a short prioritized list (max 5) of product
improvement suggestions for SEMA based on what you saw in the code: features,
UX of the answers, trust/explainability, or monetization-relevant capabilities.
One sentence each + why it matters. Suggestions only — do not build them.

Continue from the previous session. All 12 review items (P0/P1/P2) are done and
verified (48 tests passing). This phase: close the two deferred items, then
build the highest-value product-architect items. Work in order, verify each
step (pytest green + Streamlit and FastAPI both still run), commit nothing.
Explain each step briefly before implementing (per CLAUDE.md mentoring style).

## Step 1 — Commit checkpoint (do this first)
Show me `git status` + a grouped `git diff --stat`, and propose the two-commit
split you suggested: (1) P0 tenant-safety fixes + tests, (2) framework
decoupling + hardening. Show the proposed commit messages and WAIT for my
approval before committing anything.

## Step 2 — Finish the sema_core/ physical move (deferred mechanical step)
Move the framework-free core modules (db.py, client_registry.py, settings.py,
obs.py, cache.py, wiring.py, agent/ package, queries.py, query_router.py,
insight_builder.py) into a proper `sema_core/` package; `app/` keeps only
Streamlit UI (main.py, pages/, components/ UI modules). Rules:
- alerts_engine.py is product logic, not UI — decide and justify where it
  lands (likely sema_core, with the panel rendering staying in app/).
- Update pyproject.toml, all imports, api/main.py, and the CLAUDE.md
  "Running SEMA Locally" section (PYTHONPATH note) to match.
- This is a pure mechanical refactor: no behavior change, pytest must stay
  green, and both entry points must run. Show the plan (max 5 bullets) and
  wait for approval before moving files — this touches 3+ files.

## Step 3 — SSE streaming endpoint (product priority #1)
/api/chat blocks for 20-30s. Add `POST /api/chat/stream` (SSE) alongside the
existing endpoint (which stays unchanged):
- Refactor agent.run() minimally to accept an optional progress callback
  (or become a generator) emitting events: `status` ("consulting semantic
  layer", "running query 2..."), then a final `answer` event carrying the
  full ChatResponse JSON, or an `error` event.
- Use FastAPI StreamingResponse with media_type "text/event-stream"; no new
  dependencies (hand-roll the SSE frames: `event:`/`data:` lines).
- The existing non-streaming endpoint must share the same code path (callback
  simply unused), not a fork.
- Tests: fake client drives the loop; assert the event sequence and that the
  final event parses into ChatResponse.

## Step 4 — Server-side conversations (product priority #2)
Replace client-shipped history with a conversation_id:
- New table (in the app's OWN metadata store, NOT the client analytics DBs —
  create a small SQLite file store first, interface-driven so Postgres can
  replace it later): conversations(id, client_id, created_at) and
  messages(conversation_id, role, content, created_at).
- Contract: ChatRequest gains optional `conversation_id`; response returns it
  (new on first message). If both history and conversation_id are sent,
  conversation_id wins. Keep `history` working for backward compatibility
  (the React app migrates later).
- Cap context sent to the model by TOKEN budget, not turn count: estimate
  ~4 chars/token, budget from settings (default ~8000 tokens), truncate whole
  turns from the oldest, always starting on a user message.
- Tests: store CRUD, follow-up question pulls prior context, token-budget
  truncation, tenant isolation (conversation from client A not readable via
  client B's requests).

## Step 5 — Golden-question eval harness (product priority #3)
Create `evals/` with:
- `evals/golden/ecommerce.yaml`: 8-10 questions with expected assertions
  (e.g. metric mentioned, direction of change, a number within tolerance,
  which tool calls are expected). Derive expected values from
  data/README.md's documented patterns (March-2026 dip, VIP ~60% share, Q4
  seasonality) — verify each against the live DB before writing it down.
- `evals/run_evals.py`: runs each question through wiring.get_response,
  scores assertions, prints a pass/fail table + total cost (from obs token
  logging). Needs a live DB + API key; NOT part of pytest.
- Document in evals/README.md how to run and how to add a question.

## Definition of done
- Steps show plan → approval → implementation for anything touching 3+ files.
- pytest green after every step; Streamlit + FastAPI both boot.
- New endpoints visible in /docs (Swagger) with correct models.
- Nothing committed without my explicit approval (Step 1 gate).
- Session ends with the max-5 product improvement suggestions list.
