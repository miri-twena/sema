# SEMA — Project Vision

**Status:** Source of truth for project scope and direction. Update this file
whenever the vision, scope, or architecture changes — other docs and code
should align to this, not the other way around.

> **2026-06-14 — Pivot note:** This project was originally scoped as a
> "Product Analytics AI Copilot" (DuckDB, synthetic SaaS product-usage data).
> It has been **re-scoped to SEMA**: an AI Business Advisor over a synthetic
> **ecommerce** business (PostgreSQL). The core architecture pattern — chat
> UI, agent with tools, text-to-SQL grounded by a semantic layer, safe SQL
> execution, automatic output formatting, recommendations — carries over
> largely unchanged. What changes is the **domain** (ecommerce business
> metrics instead of SaaS product-usage metrics), the **database**
> (PostgreSQL instead of DuckDB), and the **dataset**.

> **2026-06-15 — Implementation note:** Phase 1 is now built. The Intent
> Router was migrated from rule-based keyword matching to a **Claude agent**
> (`claude-sonnet-4-6`) with tools (`get_schema`, `get_semantic_layer`,
> `run_sql`) and a `present_answer` step, grounded in `sql/semantic/`. SQL
> safety uses a dedicated read-only Postgres role + `sqlglot` SELECT-only
> validation + auto-LIMIT + statement timeout. The rule-based router is
> **retained as a fallback** and is used when `ANTHROPIC_API_KEY` is not
> configured (the UI then notes the agent is offline). PostgreSQL, the insight
> rendering, and the UI were left unchanged by the migration.

> **2026-07-16 — Freeze decision:** Streamlit (`app/`) is **frozen as an internal
> dev tool**. The **product UI is React + FastAPI** (`frontend/` + `api/`).
> Rationale: maintaining two frontends is a double maintenance tax, and a
> single design system (React) is cleaner for users and the team. RTL/Hebrew
> support will be handled once in React (`frontend/src/lib/rtl.ts`), not
> duplicated across Streamlit. Streamlit will not be deleted — it remains
> useful for local sanity-checks and as a fallback — but it receives no new
> features, no design changes, and no investment. This is enforced by a
> guardrail test (`tests/test_streamlit_freeze.py`) that fails if product code
> (`sema_core/`, `api/`) ever imports from `app/`.

---

## 1. Product Vision

SEMA is a **conversational AI Business Advisor**. Users — business owners,
analysts, managers, executives, CS/sales teams — ask business questions in
plain language and get back insights, visualizations, KPIs, and recommended
actions.

SEMA is explicitly **not**:

- A BI dashboard tool (dashboards are a secondary, on-request capability)
- A "Text-to-SQL" assistant (SQL generation is an internal implementation
  detail, not the product)
- A static reporting tool

### Target Experience

Every interaction follows this flow:

```
Business question (chat)
  -> AI understands business intent + semantics
  -> AI generates SQL (grounded by the semantic layer)
  -> SQL executes safely (read-only, validated)
  -> AI analyzes the results
  -> AI presents: text insight + KPI cards + table + chart (auto-selected)
  -> AI suggests recommended actions
```

### Target Users / Personas

| Persona | Who they are | Typical questions |
|---|---|---|
| **SMB owner** (ecommerce store, agency, consultant) | Non-technical, runs the business | "Why are sales down?" "Which products perform best?" |
| **Product/Marketing Manager** | Owns a function, semi-technical | "Which campaign performs best?" "What changed this quarter?" |
| **Director / Executive** | Cares about overall trajectory | "What changed this quarter?" "Which business units underperform?" |
| **Customer Success / Sales** | Manages accounts | "Which customers are at risk?" "Which accounts should we upsell?" |
| **Analyst** *(you, as a secondary user)* | Strong SQL/BI skills | Validates the AI's SQL and reasoning, asks complex comparisons |

### Core Principle

SEMA should behave like a **junior business analyst**, not a query tool: it
investigates, explains *why* something happened, and suggests *what to do
next*. Users should never need to know table names, columns, or SQL — SEMA
translates business concepts (Revenue, Churn, Retention, ROI, Conversion
Rate, Active Customer, etc.) into the correct queries automatically.

---

## 2. MVP Scope (Phase 1)

See [`mvp_scope.md`](mvp_scope.md) for the detailed breakdown. In summary:

- Streamlit chat interface
- Natural language understanding + semantic layer grounding
- Text-to-SQL generation against a synthetic PostgreSQL ecommerce database
- Safe, read-only SQL execution with guardrails
- Automatic output format selection (text / KPI / table / chart)
- Automatic chart type selection (line / bar / funnel / table / KPI cards)
- Basic recommended actions after each answer

---

## 3. Architecture

See [`architecture.md`](architecture.md) for the full design: database
schema, semantic layer, agent/tool design, chat UI, and file structure.

### High-Level Component Map

```
Chat UI (Streamlit)
   -> Router (wiring.py): the LLM agent if ANTHROPIC_API_KEY is set,
      otherwise the rule-based fallback (keyword router + insight builder)
   -> Agent (Claude claude-sonnet-4-6, reasoning loop with tools)
        -> get_schema / get_semantic_layer / run_sql   (read-only, validated)
        -> present_answer                              (structured final answer)
   -> Response Renderer (text / KPI cards / table / chart)
   -> Recommended actions (part of every answer)
```

### Note: Claude Code vs. Claude API

*Claude Code* (used to build this project) is a development assistant.
The *product* itself calls the *Claude API* at runtime — that's the
"Orchestrator" above. These are two separate uses of Claude: one builds the
system, the other **is** the system.

---

## 4. Phase 2 (Future Roadmap)

- Dashboard generation on request
- Customer health score / churn risk detection
- Automatic alerts ("tell me if churn risk increases")
- Proactive opportunity detection
- Weekly automated business summaries
- Evaluation framework (test set of question/answer pairs)
- Real data warehouse connections (replacing synthetic data)
