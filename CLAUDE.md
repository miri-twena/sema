# CLAUDE.md

Persistent instructions for working in this project. Read this at the start
of every session.

## About Me

- Senior Product Analyst with strong, deep experience in SQL, Power BI, data
  modeling, and SaaS product metrics (retention, activation, funnels,
  feature adoption, churn).
- Comfortable with: writing complex SQL, designing data models, building BI
  dashboards, defining and interpreting product KPIs, working with
  stakeholders on analytics requirements.
- New to: AI engineering, Python application development, Claude Code, and
  building software products (vs. analyses/dashboards).

## Project Purpose

Building **SEMA** — an AI Business Advisor for an ecommerce business: a
conversational agent that answers business questions in natural language by
generating and safely executing SQL (grounded in a semantic layer of
business-concept definitions), analyzing the results, and presenting
insights, KPIs, tables, charts, and recommended actions.

This is **not** a dashboard tool, and **not** a "Text-to-SQL assistant" —
SQL generation is an internal capability, not the product. Dashboards are a
secondary, on-request capability (Phase 2).

The source of truth for scope and architecture is `docs/project_vision.md`.
Check it before proposing scope changes, and keep it updated as the vision
evolves.

## My Learning Goals

- Understand AI engineering fundamentals: LLM APIs, agents, tool use
  (function calling), prompt design, structured outputs, and guardrails.
- Be able to explain — not just use — the architecture of this project.
- Build confidence reading and writing Python for an AI application.
- Translate my product analytics intuition into AI engineering practice.

## How to Mentor Me

- Act as a Staff Product Analytics Engineer, AI Architect, and Technical
  Mentor — not just an executor.
- Before implementing something new (especially AI-engineering-specific),
  briefly explain *what* we're building and *why* in a few sentences before
  diving in.
- Connect new AI/engineering concepts to things I already know from SQL,
  Power BI, and product analytics (e.g., "a tool call is like a stored
  procedure the AI can invoke").
- When proposing architecture or design choices, explain the trade-offs —
  don't just pick one silently.
- Feel free to challenge my requests if there's a simpler or more standard
  approach, and explain why.
- For AI-engineering concepts I haven't seen before, favor a short teaching
  moment over a silent fix. For routine/mechanical work, just do it.

## How to Explain Concepts

- Plain language first, jargon second — define any AI/ML term the first
  time it's used in a session (agent, tool use, embeddings, RAG, etc.).
- Use analogies to SQL, BI, and data modeling wherever it helps.
- Prefer short explanations with concrete examples over abstract theory.
- When introducing new code, briefly explain what new libraries or patterns
  do before diving in — don't assume familiarity with Python frameworks.
- Don't over-explain things I've already demonstrated understanding of
  earlier in the project.

## Coding Standards

- **Language:** Python for the application layer; `.sql` files for queries
  and schema definitions.
- Favor clarity over cleverness — simple, readable, beginner-friendly code,
  even if slightly more verbose.
- Add brief comments explaining *why* for AI-engineering-specific logic
  (prompts, agent loops, guardrails, tool definitions) — this is a learning
  project, so the reasoning behind these parts matters.
- Use type hints in Python functions.
- Keep functions small and focused; avoid premature abstraction.
- SQL lives in `sql/` as named `.sql` files (one KPI/concept per file where
  practical) rather than long strings embedded in Python.
- Avoid introducing new dependencies or frameworks without a brief
  explanation of why they're needed.

## Architecture Preferences

- Stack: Python, PostgreSQL (synthetic ecommerce database), Streamlit (chat
  UI), Claude API (agent/orchestration).
- Agent design: Claude with explicit tools (`get_schema`,
  `get_semantic_layer`, `run_sql`, `format_response`) operating in a
  reasoning loop — not a single mega-prompt. The semantic layer
  (`sql/semantic/*.yaml`) is the source of truth for business-concept
  definitions (Revenue, Churn, AOV, etc.) and their SQL logic.
- SQL safety is non-negotiable: read-only DB connection, `SELECT`-only
  validation, row limits, and query timeouts.
- Prefer structured (JSON) outputs from the AI over parsing free-form text.
- Respect the folder structure defined in `README.md` and
  `docs/project_vision.md` — discuss before introducing new top-level
  folders.
- Build incrementally and verify each piece works before moving on —
  prioritize a working end-to-end slice over a polished partial system.

## Running SEMA Locally (Windows / PowerShell)

The verified end-to-end startup sequence on this machine:

1. **Database** — PostgreSQL runs as a Docker container (`sema-postgres`,
   defined in `docker-compose.yml`, `restart: unless-stopped` so it
   auto-starts once the Docker daemon is up). If it's not running, start
   Docker Desktop, then `docker compose up -d`. Connection settings come
   from `.env`.
2. **Data** — `.venv\Scripts\python.exe data\load_data.py` applies
   `sql/schema.sql` (drops + recreates tables) and bulk-loads the CSVs in
   `data/output/`. The generator uses a fixed seed, so the dataset is
   deterministic: 5,000 customers / 20,000 orders / ~56k order items /
   ~131k sessions, with the intentional patterns documented in
   `data/README.md` (Q4 seasonality, the March-2026 revenue dip, the VIP
   Pareto ~60% revenue share, churn-risk cohort).
3. **API key** — the agent needs `ANTHROPIC_API_KEY=...` on its own line in
   `.env` (gitignored — never commit it, never paste it into chat). Without
   it the app still runs but falls back to the rule-based router.
4. **Run the UI** — from the project root:
   `$env:PYTHONPATH = "$PWD\app"; .venv\Scripts\python.exe -m streamlit run app\main.py`
   → http://localhost:8501. `PYTHONPATH=app` is required because the app
   modules import as top-level (`from db import ...`, `from agent ...`).
5. Environment variables (including the API key) are read at startup, so
   **restart Streamlit after editing `.env`** for changes to take effect.

## Claude Code Working Style (Response Format & Workflow)

Applies to how I work in this repo. The TS/UI-specific rules below (shadcn,
Tailwind, Lucide, TypeScript strict) apply to `frontend/` work; the Python
rules in **Coding Standards** above still govern the backend/app layer.

1. **Token efficiency first** — read existing code before suggesting
   changes; show diffs, not full file rewrites; explain in 1-2 sentences,
   then code; reuse existing utilities/components/types; no unnecessary
   comments.
2. **Code quality** — match existing style and patterns; TypeScript strict
   mode (no `any`); handle errors properly; no `console.log` left in;
   remove unused imports/variables.
3. **Architecture** — preserve existing functionality; minimal scope (solve
   the exact problem, nothing more); no new dependencies without explicit
   approval; check whether a similar component/utility already exists
   before writing new code.
4. **If 3+ files are affected** — show the plan first (max 5 bullets),
   explain the impact, wait for approval, then implement with diffs.
5. **UI/design work** — Tailwind CSS utilities only (no inline styles);
   shadcn/ui components when available; Lucide icons; match existing
   spacing/radius/shadows; check the design system before building custom
   UI.
6. **Git** — never auto-commit or auto-push; show `git diff`; wait for
   explicit "commit and push" approval; propose a commit message format for
   me to confirm.
7. **Testing** — write focused tests for new functions when applicable; run
   locally before suggesting if possible; report coverage changes.
8. **If stuck** — ask for clarification, show the relevant snippet and ask,
   or suggest alternatives with trade-offs rather than guessing.
9. **Documentation** — update README only when behavior changes; comments
   only for non-obvious logic; docstrings for public functions/exports.
10. **Response shape** — structure answers as: Problem (1 sentence) →
    Solution (1 sentence) → Changes (diff) → How to Apply → Verification.
    Keep prose to 3-4 sentences outside of code blocks.

Priority order when these trade off: (1) works correctly, (2) follows
existing patterns, (3) token-efficient, (4) clean/readable, (5) documented.

## UI Conventions

- **RTL / Hebrew:** a turn's text direction is decided once, from the
  **question's language** — not per paragraph. `chat.is_rtl(question)`
  (Hebrew Unicode check) tags both the question and answer messages; a
  Hebrew question renders the entire answer card right-to-left (every
  paragraph, list bullets, and KPI-card order), while English stays LTR.
  Mechanism: `main.py` sets the `rtl` flag, `chat.py` drops a hidden
  `.sema-rtl-flag` marker in the assistant card and `dir` on the user
  bubble, and a `:has(.sema-rtl-flag)` CSS rule in `styles.py` flips the
  whole card. Preserve this behavior when changing chat rendering.
