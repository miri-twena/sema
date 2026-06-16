# SEMA — MVP Scope (Phase 1)

This document defines exactly what's **in** and **out** for the MVP, and
what "done" looks like. Detailed component design lives in
[`architecture.md`](architecture.md).

---

## 1. In Scope

| # | Feature | Notes |
|---|---|---|
| 1 | Chat interface | Streamlit, single conversation, message history kept in session |
| 2 | Natural language understanding | Claude interprets business intent from the question |
| 3 | Semantic layer | Maps business terms (Revenue, Churn, AOV, Conversion Rate, ROI, Retention, Active Customer...) to schema + SQL logic |
| 4 | Text-to-SQL generation | Claude generates SQL grounded in schema + semantic layer |
| 5 | Safe SQL execution | Read-only Postgres role, `SELECT`-only validation, row limits, query timeout, self-correction on error |
| 6 | Result interpretation | Claude analyzes the returned rows for trends, comparisons, drivers |
| 7 | Automatic output format selection | Text / KPI card(s) / table / chart — chosen by the agent, not the user |
| 8 | Automatic chart type selection | Line, bar, funnel, table, or KPI cards |
| 9 | Basic recommended actions | 2-4 short, concrete next-step suggestions after each analytical answer |
| 10 | Sidebar: Business KPIs | A small set of headline KPIs computed on load (e.g. Revenue, Orders, AOV, Active Customers) |
| 11 | Sidebar: Suggested questions | Static curated list to help users get started |
| 12 | Sidebar: Connected data sources | Static display — shows "Synthetic Ecommerce DB (PostgreSQL)" |
| 13 | Sidebar: Recent chats | Session-only list of past questions (no persistence across app restarts in MVP) |

## 2. Explicitly Out of Scope (Phase 2+)

- Dashboard generation on request
- Customer health scores / churn-risk modeling
- Automatic alerts, scheduled/weekly summaries
- Proactive opportunity detection
- Multi-user auth, persisted chat history across sessions
- Real (non-synthetic) data sources
- Evaluation framework / automated regression testing of AI answers

These are listed so we don't accidentally scope-creep into them, and so we
have a ready-made backlog once Phase 1 is solid.

---

## 3. Database & Synthetic Dataset

**Database:** PostgreSQL (local, via Docker or local install — TBD when we
get to setup).

**Domain:** Synthetic ecommerce business, generated locally. No real data.

| Table | Purpose | Approx. size (MVP target) |
|---|---|---|
| `customers` | Who buys | 5,000+ |
| `products` | What's sold | 100+ |
| `orders` | Purchase transactions | 20,000+ |
| `order_items` | Line items per order | ~order count × 1.5-3 |
| `marketing_campaigns` | Paid/organic acquisition campaigns | ~10-20 |
| `website_sessions` | Site visits (incl. non-converting) | enough to support funnel/conversion analysis |

**Time range:** 12 months of history.

**Design requirement:** Like the original SaaS dataset design, this data
needs **intentional, explainable patterns** baked in — e.g. a real revenue
dip in a specific month driven by a specific campaign/category, a segment
with notably different behavior — so we can verify SEMA's answers against
known ground truth. Full column-level schema is in
[`architecture.md`](architecture.md#3-database-schema-postgresql).

---

## 4. KPIs / Business Concepts Covered (Semantic Layer v1)

These are the business concepts SEMA must understand and be able to compute
for the ecommerce domain:

- **Revenue** (total, by period, by category, by segment, by channel)
- **Orders** (count, by period)
- **AOV** (Average Order Value)
- **Conversion Rate** (sessions → orders)
- **Repeat Purchase Rate** / **Retention** (customers ordering again within
  a window)
- **Churn** (customers who stopped ordering — defined by recency threshold)
- **Customer Segments** (e.g. New / Returning / VIP, by spend or order count)
- **Campaign Performance / ROI / ROAS** (revenue & orders attributed to a
  campaign vs. its spend)
- **Category / Product Performance** (revenue, units sold, growth)
- **Traffic Source Performance** (sessions, conversion rate, revenue by
  source)

Each of these gets a definition entry in the semantic layer (see
architecture doc) — a plain-language description + the SQL logic to compute
it.

---

## 5. Example MVP Interaction (Acceptance Bar)

Question:

> "Why did revenue drop last month?"

SEMA should be able to:

1. Identify the relevant time comparison (last month vs. prior month / vs.
   trend)
2. Compute total revenue for both periods and the % change
3. Break the drop down by at least one dimension (category, channel, or
   campaign) to identify where the decline is concentrated
4. Present: a text insight, a KPI card (revenue + % change), and a bar/line
   chart showing the breakdown
5. Offer 2-4 recommended actions referencing the specific drivers found
   (e.g. "Review Meta campaign performance", "Investigate Accessories
   category decline")

This is the scenario from the PRD and is our **end-to-end smoke test** for
the MVP — if SEMA can do this well, the core loop works.

---

## 6. "Done" Criteria for MVP

- [ ] PostgreSQL database created and seeded with the synthetic dataset
      (with intentional patterns documented in `data/`)
- [ ] Semantic layer definitions written for all concepts in Section 4
- [ ] Agent can answer the example interaction in Section 5 correctly
- [ ] Agent correctly chooses output format (text/KPI/table/chart) across a
      range of question types (a "why" question, a "compare X vs Y"
      question, a "trend over time" question, a "which is best/worst"
      question)
- [ ] SQL guardrails verified: non-`SELECT` queries are rejected, runaway
      queries are capped, malformed SQL triggers a self-correction retry
- [ ] Chat UI matches the layout in `architecture.md` (sidebar + main chat,
      with KPI cards/tables/charts rendered inline)
- [ ] You (the user) can explain, in your own words, how each component
      works
