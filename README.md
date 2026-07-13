# SEMA — AI Business Advisor

## Vision

SEMA is a **conversational AI Business Advisor** for ecommerce businesses.
It is **not** a dashboard tool and **not** a "Text-to-SQL" assistant —
those are internal implementation details, not the product.

Users ask business questions in plain English — for example:

- "Why did revenue drop last month?"
- "Which products perform best?"
- "Which marketing campaign performs best?"
- "Which customers are at risk of churning?"

SEMA understands the business intent, generates SQL grounded in a semantic
layer of business definitions, executes it safely against PostgreSQL,
analyzes the results, and responds with whatever combination of text
insight, KPI cards, table, and chart best fits the question — plus a few
recommended next actions.

## How It Works (high level)

```
You ask a question (chat)
        |
        v
AI understands intent + relevant business concepts (semantic layer)
        |
        v
AI generates SQL  -->  SQL runs safely (read-only)  -->  results returned
        |
        v
AI analyzes the results
        |
        v
AI responds: text insight + KPI cards + table + chart (auto-selected)
        |
        v
AI suggests recommended actions
```

## Project Structure

### `data/`
Synthetic ecommerce data: customers, products, orders, order items,
marketing campaigns, and website sessions — 12 months of history with
intentional, explainable patterns. Generated locally for development — no
real customer data.

### `sql/`
Database schema (`schema.sql`) and the **semantic layer**
(`semantic/*.yaml`) — business-concept definitions (Revenue, AOV, VIP
Customers, Active Customers, Conversion Rate, Churn Risk, Campaign ROI,
Returning Customers, Revenue by Category) with their SQL logic. The agent
uses these as grounding so it generates accurate, consistent SQL instead of
writing every query from scratch. Also includes `create_readonly_role.sql`
(the read-only role the agent's queries run under) and `queries/` (the
predefined queries powering the rule-based fallback).

### `notebooks/`
Data generation scripts, semantic-layer prototyping, and prompt experiments
— the scratchpad for building and testing pieces before they become part of
the app.

### `dashboard/`
Output of the Phase 2 dashboard-generation capability — used only when a
user explicitly asks for a dashboard. Secondary to the chat experience.

### `sema_core/`
The framework-free backend — installed as an editable package
(`pip install -e .`) so Streamlit, FastAPI, pytest, and scripts all import it
the same way, with no `PYTHONPATH` or `sys.path` hacks:
- `wiring.py` — routes each question to the agent, with the rule-based router
  as fallback.
- `agent/` — the LLM agent: `agent.py` (reasoning loop, optional
  `on_progress` callback for streaming), `tools.py` (`get_schema` /
  `get_semantic_layer` / `run_sql`), `prompts.py`, `semantic.py`
  (semantic-layer loader), `safety.py` (SQL guardrails), and `response.py`
  (`present_answer` → structured response).
- `db.py` — PostgreSQL access via `psycopg2` connection pools, one pool per
  `(client_id, role)` — full role for app introspection, read-only role for
  agent queries.
- `client_registry.py` — multi-client config; unknown `client_id` raises
  rather than silently falling back to another tenant.
- `settings.py` — env-driven config (model, timeouts, row limits, DB
  credentials, CORS, API key). `obs.py` — structured JSON logging
  (request/token/cost tracking). `cache.py` — framework-neutral TTL cache.
- `conversation_store.py` — server-side chat history (SQLite metadata store,
  separate from the tenant analytics databases), with token-budget
  truncation.
- `queries.py`, `query_router.py`, `insight_builder.py`,
  `alerts_engine.py` — the rule-based fallback and semantic-layer alerts.

### `api/`
FastAPI REST layer over `sema_core` (a React frontend consumes this):
- `main.py` — routes, incl. `/api/chat` (blocking) and `/api/chat/stream`
  (SSE progress + answer), tenant validation (404 on unknown `client_id`),
  an `X-API-Key` auth scaffold, and no-leak error handling (a `request_id`
  is returned; details go to the server log only).
- `models.py` — the stable Pydantic request/response contract.
- `serialize.py` — converts backend DataFrames to the contract's
  `{columns, rows}` shape.

### `app/`
The Streamlit UI only (imports `sema_core` for everything else):
`main.py` (entry point and chat loop) and `components/` (theme, styles,
sidebar, chat, KPI cards, charts, tables, actions).

### `frontend/`
A React (Vite + TypeScript + Tailwind) client consuming the FastAPI REST
layer in `api/`.

### `tests/`
`pytest` suite for `sema_core`/`api` — no live database, API key, or
Streamlit required. Run with `.venv\Scripts\python.exe -m pytest`.

### `evals/`
Golden-question regression suite that runs real questions through the live
agent and scores the answers (content, direction, numeric tolerance, SQL
usage) — catches prompt/model regressions `pytest`'s fakes can't. Needs a
live database and API key; see [`evals/README.md`](evals/README.md).

### `docs/`
Project vision, MVP scope, and architecture docs.

## Project Phases

- **Phase 1 (MVP):** Chat interface, semantic layer, text-to-SQL, safe SQL
  execution, result interpretation, automatic format/chart selection, basic
  recommended actions. See [`docs/mvp_scope.md`](docs/mvp_scope.md).
- **Phase 2:** Dashboard generation on request, customer health
  score/churn-risk detection, automatic alerts, proactive opportunity
  detection, weekly automated summaries, evaluation framework.

## Status

**Phase 1 is built**, with a hardened backend and a REST API alongside the
original Streamlit app. SEMA runs over a live PostgreSQL database (synthetic
ecommerce data), with:

- A premium chat UI (light pastel theme, KPI cards, charts, tables,
  recommended actions) — in Streamlit (`app/`) and in a React frontend
  (`frontend/`) talking to the FastAPI layer (`api/`).
- An **LLM agent** (Claude, model configurable via `SEMA_MODEL`) that answers
  questions using three tools (`get_schema`, `get_semantic_layer`, `run_sql`)
  plus a `present_answer` step, grounded in the semantic layer
  (`sql/semantic/`). `POST /api/chat/stream` streams progress ("running
  query 2...") over SSE instead of blocking for the full 20-30s run.
- **Server-side conversations**: the API resolves prior turns from its own
  metadata store via `conversation_id` (token-budget-truncated), rather than
  trusting an ever-growing history payload from the client.
- **SQL safety**: a read-only Postgres role, `sqlglot` SELECT-only
  validation (also blocking `pg_catalog`/`information_schema` access),
  automatic and capped `LIMIT`, and a statement timeout.
- **Multi-tenant safety**: an unknown `client_id` 404s rather than silently
  falling back to another tenant's database; per-client schema/report
  caching is correctly isolated per tenant.
- A **graceful fallback**: when `ANTHROPIC_API_KEY` is not set, the original
  rule-based router answers the known questions and the app clearly notes the
  agent is offline.
- **RTL support**: a question asked in Hebrew renders the entire answer
  right-to-left (text, lists, and KPI-card order); English stays
  left-to-right. Direction is decided per turn from the question's language.
- **Tests & evals**: a `pytest` suite (`tests/`, no live DB/API key needed)
  and a golden-question eval harness (`evals/`) that scores real agent
  answers against the live dataset.

## Quickstart

Prerequisites: Docker Desktop, Python 3.12, and a virtualenv at `.venv` with
`requirements.txt` installed (`pip install -r requirements.txt`). Commands
below are PowerShell (Windows).

1. **Start the database** (PostgreSQL via Docker):
   ```powershell
   docker compose up -d
   ```
2. **Load the synthetic data** (drops/recreates tables and bulk-loads the
   deterministic dataset — 5,000 customers, 20,000 orders, with the
   intentional patterns in [`data/README.md`](data/README.md)):
   ```powershell
   .venv\Scripts\python.exe data\load_data.py
   ```
3. **Add your Claude API key** — put `ANTHROPIC_API_KEY=...` on its own line
   in `.env` (gitignored). Optional: without it the app runs in rule-based
   fallback mode.
4. **Install the backend package** (once per venv — makes `sema_core`/`api`
   importable everywhere, no `PYTHONPATH` needed):
   ```powershell
   .venv\Scripts\python.exe -m pip install -e .
   ```
5. **Run the Streamlit app**:
   ```powershell
   .venv\Scripts\python.exe -m streamlit run app\main.py
   ```
   Then open http://localhost:8501.

   **Or run the FastAPI + React stack** instead:
   ```powershell
   .venv\Scripts\python.exe -m uvicorn api.main:app --reload --port 8000
   ```
   Swagger docs at http://localhost:8000/docs; see
   [`frontend/README.md`](frontend/README.md) for the React dev server.

2b. **Load the insurance client data** (optional; second client, same
   container, the `insurance_db` database):
   ```powershell
   .venv\Scripts\python.exe data\insurance\load_data.py
   ```

Environment variables are read at startup, so **restart Streamlit after
editing `.env`**. See [`docs/project_vision.md`](docs/project_vision.md) and
[`docs/architecture.md`](docs/architecture.md) for the full design.

## Multi-client

SEMA serves multiple business clients, each with its own database and its own
semantic layer — same agent, safety, and UI, different governed dataset behind
it. Clients are declared in [`config/clients.yaml`](config/clients.yaml):

```yaml
clients:
  - id: ecommerce
    label: "🛍️ E-Commerce"
    db_env: POSTGRES_DB              # env var holding the DB name
    semantic_dir: sql/semantic
    suggested_questions: [ ... ]
  - id: insurance
    label: "🚗 Auto Insurance"
    db_env: POSTGRES_DB_INSURANCE
    semantic_dir: sql/insurance/semantic
    suggested_questions: [ ... ]
```

**Adding a client is a YAML change, not a code change**: add an entry, point
`db_env` at its database, drop its metric `.yaml` files in `semantic_dir`.

How it works:
- `sema_core/client_registry.py` reads the YAML and resolves the active
  client from Streamlit session state, or from a per-request override the
  API sets (a `ContextVar`, so concurrent FastAPI requests never cross
  tenants). An unknown `client_id` raises rather than silently falling back
  to another tenant.
- `sema_core/db.py` pools connections **per `(client_id, role)`**
  (`psycopg2.pool.ThreadedConnectionPool`), so switching clients — or
  concurrent requests for different clients — never reuses the wrong
  database or connection.
- `sema_core/agent/semantic.py` resolves the metric folder at call time from
  the active client; schema introspection and report caching are likewise
  cached per client, not globally.
- **Switch clients at runtime** from the ⚙ admin page (sidebar → “Switch
  client”) — no restart. `SEMA_CLIENT` in `.env` only sets the startup client.

Both databases live in one local Postgres container; `sql/init/` bootstraps
`insurance_db` and the read-only role on a fresh volume.
