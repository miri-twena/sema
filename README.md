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

### `app/`
SEMA itself:
- `main.py` — Streamlit entry point and chat loop.
- `wiring.py` — routes each question to the agent, with the rule-based router
  as fallback.
- `agent/` — the LLM agent: `agent.py` (reasoning loop), `tools.py`
  (`get_schema` / `get_semantic_layer` / `run_sql`), `prompts.py`,
  `semantic.py` (semantic-layer loader), `safety.py` (SQL guardrails), and
  `response.py` (`present_answer` → structured response).
- `components/` — UI rendering (theme, styles, sidebar, chat, KPI cards,
  charts, tables, actions).
- `db.py` — PostgreSQL access (full role for app introspection, read-only
  role for agent queries). `queries.py`, `query_router.py`, and
  `insight_builder.py` power the rule-based fallback.

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

**Phase 1 is built.** SEMA runs as a Streamlit app over a live PostgreSQL
database (synthetic ecommerce data), with:

- A premium chat UI (light pastel theme, KPI cards, charts, tables,
  recommended actions).
- An **LLM agent** (Claude, `claude-sonnet-4-6`) that answers questions using
  three tools (`get_schema`, `get_semantic_layer`, `run_sql`) plus a
  `present_answer` step, grounded in the semantic layer (`sql/semantic/`).
- **SQL safety**: a read-only Postgres role, `sqlglot` SELECT-only
  validation, automatic `LIMIT`, and a statement timeout.
- A **graceful fallback**: when `ANTHROPIC_API_KEY` is not set, the original
  rule-based router answers the known questions and the app clearly notes the
  agent is offline.
- **RTL support**: a question asked in Hebrew renders the entire answer
  right-to-left (text, lists, and KPI-card order); English stays
  left-to-right. Direction is decided per turn from the question's language.

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
4. **Run the app**:
   ```powershell
   $env:PYTHONPATH = "$PWD\app"
   .venv\Scripts\python.exe -m streamlit run app\main.py
   ```
   Then open http://localhost:8501. `PYTHONPATH=app` is required because the
   app modules import as top-level packages.

Environment variables are read at startup, so **restart Streamlit after
editing `.env`**. See [`docs/project_vision.md`](docs/project_vision.md) and
[`docs/architecture.md`](docs/architecture.md) for the full design.
