# SEMA — Architecture

This doc explains **how** SEMA is built: the database schema, the semantic
layer, the agent/tool design, the chat UI, and the file structure. It's
written so each piece can be understood on its own, with analogies to SQL/BI
concepts where useful.

---

## 1. Component Map

```
┌─────────────────────────────────────────────────────────────┐
│  Streamlit Chat UI                                            │
│  - Sidebar: KPIs, suggested questions, data sources, recent   │
│    chats                                                      │
│  - Main: chat history + input box                            │
└───────────────────────┬────────────────────────────────────-┘
                         │ user question
                         v
┌─────────────────────────────────────────────────────────────┐
│  Orchestrator (Claude, agent loop)                            │
│  Reasons step-by-step, calling tools as needed:               │
│    get_schema | get_semantic_layer | run_sql | format_response│
└───────────────────────┬────────────────────────────────────-┘
                         │ structured JSON result
                         v
┌─────────────────────────────────────────────────────────────┐
│  Response Renderer (Streamlit)                                │
│  Renders: text insight, KPI cards, table, chart, recommended  │
│  actions — based on the JSON shape returned by the agent      │
└─────────────────────────────────────────────────────────────┘

                         ┌─────────────────────────────┐
                         │  PostgreSQL (read-only role)  │
                         │  customers, products, orders, │
                         │  order_items, campaigns,       │
                         │  website_sessions              │
                         └─────────────────────────────┘
```

**Analogy:** think of the Orchestrator like a junior analyst sitting at a
terminal. You (the user) ask a question in Slack. The analyst doesn't have
your dashboard memorized — they open the data dictionary (`get_schema` +
`get_semantic_layer`), figure out which tables/columns map to "revenue" or
"churn", write a query (`run_sql`), look at the result, and then write you a
short Slack reply with a chart attached and a couple of suggestions. The
"tools" are just the things the analyst is allowed to do.

---

## 2. Agent Design: Tools

Claude operates in a **reasoning loop**: it gets the user's question + a
system prompt describing its role and tools, then repeatedly decides
"what do I need next?" until it has enough to answer. This is sometimes
called **tool use** or **function calling** — like giving the AI access to a
small set of stored procedures it can call, and it decides which ones to
call and in what order, based on the conversation.

### Tools (Phase 1)

| Tool | Purpose | Analogy |
|---|---|---|
| `get_schema()` | Returns table/column definitions + sample rows | Like opening the data dictionary / ERD before writing a query |
| `get_semantic_layer(concepts?)` | Returns business-term definitions and their SQL logic (all, or filtered to relevant concepts) | Like a metrics catalog (e.g. a Power BI "measures" list with DAX definitions, but for SQL) |
| `run_sql(query)` | Executes a validated, read-only `SELECT` against Postgres, with row limit + timeout | Running a query through a read-only reporting login |
| `format_response(...)` | Not a DB call — Claude's own structured output describing how to render the answer (text/KPI/table/chart + chart spec + recommendations) | The "presentation layer" decision — same data, but "should this be a card or a chart?" |

**Why a semantic layer tool instead of just dumping the schema?**
A schema tells Claude *what columns exist*; it doesn't tell Claude *what
"churn" means for this business* (e.g., "no order in 60+ days"). Without
that definition, two different questions about "churn" could get
inconsistent SQL. The semantic layer is the **single source of truth** for
business-concept → SQL logic, so answers stay consistent. This is the same
problem a "metrics layer" or "semantic model" solves in tools like Looker or
Power BI datasets — one definition, reused everywhere.

### Agent Loop (Phase 1, simplified)

```
1. User asks a question
2. Claude calls get_semantic_layer() to check which business concepts apply
3. Claude calls get_schema() if it needs column-level detail
4. Claude writes a SQL query (using semantic layer definitions as building
   blocks) and calls run_sql(query)
   - If the query errors, Claude revises it and retries (max N retries)
5. Claude analyzes the result rows
6. Claude produces a structured response: insight text, output format
   choice, chart spec (if any), and recommended actions
7. Streamlit renders the structured response
```

### Structured Output Shape

```json
{
  "insight_text": "Revenue dropped 18% in May vs April, driven mainly by the Accessories category and a decline in Meta-attributed orders.",
  "kpis": [
    {"label": "Revenue (May)", "value": 142000, "delta_pct": -18.0, "vs": "April"}
  ],
  "table": null,
  "chart": {
    "type": "bar",
    "x": "category",
    "y": "revenue_change_pct",
    "title": "Revenue Change by Category (Apr -> May)"
  },
  "recommended_actions": [
    "Review Meta campaign performance for May",
    "Investigate the Accessories category decline",
    "Compare customer acquisition trends month over month"
  ]
}
```

Returning structured JSON (instead of free-form text the app has to parse)
means the UI code is simple: each field maps to one Streamlit component.
This is a deliberate trade-off — slightly more constrained prompting, in
exchange for much more reliable rendering.

---

## 3. Database Schema (PostgreSQL)

Six tables, designed to support the KPIs in `mvp_scope.md` §4 (revenue, AOV,
conversion rate, retention/churn, campaign ROI, category performance,
traffic source performance).

```sql
-- Customers
CREATE TABLE customers (
    customer_id     SERIAL PRIMARY KEY,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    signup_date     DATE NOT NULL,
    country         TEXT NOT NULL,
    acquisition_channel TEXT NOT NULL,   -- e.g. 'Organic', 'Meta', 'Google', 'Email', 'Referral'
    segment         TEXT NOT NULL        -- e.g. 'New', 'Returning', 'VIP' (can also be derived, see note)
);

-- Products
CREATE TABLE products (
    product_id      SERIAL PRIMARY KEY,
    product_name    TEXT NOT NULL,
    category        TEXT NOT NULL,       -- e.g. 'Accessories', 'Apparel', 'Electronics'
    unit_price      NUMERIC(10,2) NOT NULL,
    unit_cost       NUMERIC(10,2) NOT NULL,
    launch_date     DATE NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

-- Marketing campaigns
CREATE TABLE marketing_campaigns (
    campaign_id     SERIAL PRIMARY KEY,
    campaign_name   TEXT NOT NULL,
    channel         TEXT NOT NULL,       -- e.g. 'Meta', 'Google', 'Email', 'Organic'
    start_date      DATE NOT NULL,
    end_date        DATE,
    budget          NUMERIC(12,2),
    spend           NUMERIC(12,2)
);

-- Website sessions (for traffic/conversion analysis)
CREATE TABLE website_sessions (
    session_id      SERIAL PRIMARY KEY,
    customer_id     INTEGER REFERENCES customers(customer_id),  -- NULL if anonymous
    session_start   TIMESTAMP NOT NULL,
    traffic_source  TEXT NOT NULL,       -- e.g. 'Organic', 'Meta', 'Google', 'Email', 'Direct'
    campaign_id     INTEGER REFERENCES marketing_campaigns(campaign_id),  -- NULL if not campaign-attributed
    device_type     TEXT NOT NULL,       -- 'desktop', 'mobile', 'tablet'
    converted       BOOLEAN NOT NULL DEFAULT FALSE,
    order_id        INTEGER  -- NULL until order placed; FK added after orders table
);

-- Orders
CREATE TABLE orders (
    order_id        SERIAL PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date      TIMESTAMP NOT NULL,
    status          TEXT NOT NULL,       -- 'completed', 'refunded', 'cancelled'
    traffic_source  TEXT,                -- denormalized for convenience, matches website_sessions.traffic_source
    campaign_id     INTEGER REFERENCES marketing_campaigns(campaign_id),
    discount_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
    shipping_cost   NUMERIC(10,2) NOT NULL DEFAULT 0,
    total_amount    NUMERIC(12,2) NOT NULL  -- sum of order_items net of discount, + shipping
);

ALTER TABLE website_sessions
    ADD CONSTRAINT fk_sessions_order FOREIGN KEY (order_id) REFERENCES orders(order_id);

-- Order line items
CREATE TABLE order_items (
    order_item_id   SERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders(order_id),
    product_id      INTEGER NOT NULL REFERENCES products(product_id),
    quantity        INTEGER NOT NULL,
    unit_price      NUMERIC(10,2) NOT NULL  -- price at time of sale (may differ from products.unit_price)
);
```

### Design notes

- **`customers.segment`**: simplest to generate as a stored attribute for
  MVP (e.g. assigned at signup based on intended behavior), rather than
  computed on the fly. We can *also* define a "segment" concept in the
  semantic layer that recomputes it from order history (e.g. VIP = lifetime
  spend > X) — useful to show both a stored label and a computed one as a
  teaching example of "two ways to define the same business concept."
- **`orders.total_amount`**: stored (denormalized) rather than always
  computed from `order_items`, so simple "total revenue" queries don't
  require a join — but `order_items` remains the source of truth for
  product/category-level analysis. Data generation must keep these
  consistent.
- **Intentional patterns** (per `mvp_scope.md` §3) get baked in during data
  generation — e.g., a campaign with a spend spike and a revenue dip the
  following month, or a category with declining unit sales in a specific
  month. These patterns will be documented in `data/README.md` (or
  generation script comments) once we build the generator, so we have
  ground truth to check the agent's answers against.

---

## 4. Semantic Layer Design

The semantic layer is a small set of **structured definitions** — one per
business concept — that the agent can retrieve via `get_semantic_layer()`.
Each definition includes a plain-language description and the SQL pattern
to compute it.

**Format:** YAML files under `sql/semantic/`, one file per concept (mirrors
the existing project convention of "one KPI/concept per file" in `sql/`).

Example — `sql/semantic/revenue.yaml`:

```yaml
name: Revenue
description: >
  Total money received from completed orders, after discounts, excluding
  refunded or cancelled orders.
grain: order  # the level at which this concept is naturally measured
sql_template: |
  SELECT
    DATE_TRUNC('month', order_date) AS period,
    SUM(total_amount) AS revenue
  FROM orders
  WHERE status = 'completed'
  GROUP BY 1
  ORDER BY 1
related_dimensions:
  - category  # via order_items -> products
  - traffic_source
  - campaign_id
notes: >
  Refunded/cancelled orders are excluded by default. If a question asks
  about refunds specifically, use status = 'refunded'.
```

Example — `sql/semantic/churn.yaml`:

```yaml
name: Churn
description: >
  A customer is considered "churned" if their most recent completed order
  was more than 60 days before the analysis date (i.e., no repeat purchase
  in the last 60 days).
grain: customer
sql_template: |
  SELECT
    customer_id,
    MAX(order_date) AS last_order_date,
    (CURRENT_DATE - MAX(order_date)::date) > 60 AS is_churned
  FROM orders
  WHERE status = 'completed'
  GROUP BY customer_id
notes: >
  The 60-day threshold is a starting assumption for this dataset and should
  be revisited once order frequency patterns are known from the generated
  data.
```

### Concepts to define for MVP (from `mvp_scope.md` §4)

`revenue`, `orders`, `aov`, `conversion_rate`, `repeat_purchase_rate`,
`churn`, `customer_segment`, `campaign_roi`, `category_performance`,
`traffic_source_performance`.

### How the agent uses it

1. `get_semantic_layer()` (no args) returns a **summary list**: concept
   name + one-line description for all concepts — small enough to always
   include as grounding context.
2. If Claude needs the full SQL template for one or more concepts, it calls
   `get_semantic_layer(["revenue", "category_performance"])` to get the
   detailed YAML for just those.
3. Claude **adapts** the template (e.g., changes date range, adds a
   `GROUP BY category`) rather than writing the aggregation logic from
   scratch — this is the main lever for SQL accuracy and consistency,
   exactly like reusing a tested view/CTE instead of re-deriving a metric
   each time.

**Why two tiers (summary vs. full)?** Keeps the prompt small for simple
questions, but lets Claude "drill in" for the 1-3 concepts actually relevant
— similar to showing a list of available stored procedures vs. their full
definitions.

---

## 5. SQL Safety / Guardrails

Non-negotiable, same principles as the original project:

- **Read-only DB role** — the connection used by `run_sql` has only
  `SELECT` privileges at the Postgres level (defense in depth, not just
  app-level checks)
- **Single-statement `SELECT` validation** — reject anything containing
  `INSERT`/`UPDATE`/`DELETE`/`DROP`/`ALTER`/`;`-separated multi-statements,
  before execution
- **Row limit** — automatically append/enforce a `LIMIT` (e.g. 1,000) on
  result sets
- **Query timeout** — Postgres `statement_timeout` set on the connection
- **Self-correction loop** — if `run_sql` returns an error (syntax error,
  unknown column), the error message is fed back to Claude to revise the
  query, capped at a small number of retries (e.g. 2)

---

## 6. Chat UI Design (Streamlit)

### Layout

```
┌──────────────┬──────────────────────────────────────────────┐
│ SIDEBAR       │ MAIN AREA                                     │
│               │                                               │
│ Business KPIs │  [Chat message history]                       │
│  - Revenue    │   User: Why did revenue drop last month?      │
│  - Orders     │   SEMA: <insight text>                         │
│  - AOV        │         [KPI card row]                         │
│  - Active     │         [Chart]                                │
│    Customers  │         Recommended actions:                   │
│               │          - ...                                 │
│ Suggested     │          - ...                                 │
│ Questions     │                                               │
│  - ...        │                                               │
│  - ...        │                                               │
│               │                                               │
│ Data Sources  │  [Chat input box: "Ask a question..."]        │
│  - Synthetic  │                                               │
│    Ecommerce  │                                               │
│    DB (PG)    │                                               │
│               │                                               │
│ Recent Chats  │                                               │
│  - ...        │                                               │
└──────────────┴──────────────────────────────────────────────┘
```

### Rendering rules (per response)

- `insight_text` -> `st.markdown(...)`
- `kpis` (list) -> row of `st.metric()` cards (label, value, delta)
- `table` -> `st.dataframe(...)`
- `chart` -> Plotly figure via `st.plotly_chart(...)`, type selected from
  `chart.type` (`line`, `bar`, `funnel`)
- `recommended_actions` -> bulleted list under a "Recommended actions"
  subheader

### Sidebar content (MVP — mostly static)

- **Business KPIs**: computed once at app load via the `revenue`, `orders`,
  `aov`, and a simple "active customers" semantic-layer query — refreshed
  on demand (button), not real-time
- **Suggested questions**: hardcoded list of ~6-8 questions covering the
  question types in `mvp_scope.md` §5/§6 (why/compare/trend/best-worst)
- **Connected data sources**: static text, "Synthetic Ecommerce DB
  (PostgreSQL)"
- **Recent chats**: list of past user questions from `st.session_state`
  (this session only — no cross-session persistence in MVP)

---

## 7. Recommendations (MVP — Basic Version)

Phase 1 keeps this lightweight compared to the original "playbook +
prioritization engine" design: recommendations are generated **in the same
agent turn** as the analytical answer (not a separate pass), as part of the
structured output (`recommended_actions` field). Claude is prompted to base
them on the specific data just retrieved (e.g., name the actual
underperforming category/campaign, not a generic suggestion).

A dedicated **playbook** (curated pattern → recommendation mappings) and a
**separate recommendation pass** with impact-based prioritization remain a
**Phase 2** enhancement — see `project_vision.md` §4. This keeps MVP scope
tight while leaving an obvious, well-understood extension point.

---

## 8. File Structure (Proposed)

```
product-analytics-ai/
├── AGENTS.md
├── README.md
├── docs/
│   ├── project_vision.md
│   ├── mvp_scope.md
│   └── architecture.md
├── data/
│   ├── generate_data.py        # builds the synthetic ecommerce dataset
│   └── README.md                # documents the intentional patterns baked in
├── sql/
│   ├── schema.sql                # CREATE TABLE statements (Section 3 above)
│   └── semantic/                 # semantic layer, one YAML per concept
│       ├── revenue.yaml
│       ├── orders.yaml
│       ├── aov.yaml
│       ├── conversion_rate.yaml
│       ├── repeat_purchase_rate.yaml
│       ├── churn.yaml
│       ├── customer_segment.yaml
│       ├── campaign_roi.yaml
│       ├── category_performance.yaml
│       └── traffic_source_performance.yaml
├── app/
│   ├── main.py                   # Streamlit entrypoint
│   ├── ui/
│   │   ├── sidebar.py
│   │   ├── chat.py                # message rendering (text/kpi/table/chart)
│   │   └── components.py          # reusable KPI cards, chart builders
│   ├── agent/
│   │   ├── orchestrator.py        # the agent loop (Claude + tools)
│   │   ├── tools.py                # get_schema, get_semantic_layer, run_sql definitions
│   │   ├── semantic_layer.py       # loads/serves sql/semantic/*.yaml
│   │   └── prompts/
│   │       └── system_prompt.md
│   └── db/
│       ├── connection.py           # read-only Postgres connection
│       └── safety.py               # SQL validation, row limits, timeout
├── notebooks/                     # data generation drafts, prompt experiments
└── dashboard/                      # Phase 2 — dashboard generation output
```

### Mapping back to old structure

This keeps the same top-level folders (`data/`, `sql/`, `app/`, `docs/`,
`notebooks/`, `dashboard/`) from the original project — their *roles* are
the same, just pointed at the new domain/stack. Nothing here requires new
top-level folders.

---

## 9. Open Questions for Discussion (before implementation)

1. **Postgres hosting**: local install vs. Docker container vs. a hosted
   free-tier instance? (Docker is recommended — reproducible, easy to
   reset/reseed.)
2. **Customer segment**: stored attribute, computed concept, or both (as a
   teaching example)?
3. **Churn threshold (60 days)**: placeholder — confirm once we see typical
   order frequency in the generated data.
4. **Recent chats persistence**: confirm session-only is fine for MVP (no
   database table or file for chat history yet).
