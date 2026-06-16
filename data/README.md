# SEMA Synthetic Ecommerce Dataset

This dataset is generated locally — no real customer data is used. It's
designed to look like a real 12-month ecommerce business, **with a few
patterns deliberately built in** so we can later check whether SEMA finds
the right story when asked questions like "why did revenue drop?".

## How to (re)generate

```
python data/generate_data.py
```

This writes six CSV files to `data/output/` (gitignored — regenerate any
time; the script uses a fixed random seed, so the output is the same every
run unless you change the config at the top of the script).

## Tables

| Table | Rows (approx.) | Notes |
|---|---|---|
| `customers` | 5,000 | segment (`New`/`Returning`/`VIP`) derived from real order history |
| `products` | 100 | across 6 categories |
| `marketing_campaigns` | ~16 | Meta/Google/Email, 1-3 month windows |
| `orders` | 20,000 | 12 months: 2025-06-01 to 2026-05-31 |
| `order_items` | ~50,000 | 1-4 items per order |
| `website_sessions` | ~100,000+ | converting + non-converting visits |

## Categories

Electronics, Apparel, Accessories, Home & Kitchen, Beauty, Sports &
Outdoors — each with its own realistic price range, so AOV and category
mix differ meaningfully.

## Traffic sources & customer segments

- **Traffic sources**: Organic, Direct, Google, Meta, Email, Referral —
  each with a different overall popularity and a different
  sessions-to-orders conversion rate (Organic/Direct convert best; Meta
  converts worst).
- **Customer segments**: `New` (0-1 completed orders), `Returning` (2+
  completed orders), `VIP` (top 10% by total completed spend). These are
  computed once from the generated order history and stored on the
  `customers` table — the semantic layer can later define a second, "live"
  version of segment as a teaching example of two ways to express the same
  business concept.

## Intentional patterns (ground truth)

These are built into `data/generate_data.py` on purpose, so we have a known
answer to check SEMA's reasoning against. At the end of generation, the
script prints a checklist confirming all four stories below were injected.

### 1. Seasonality

Monthly order volume is scaled by `MONTH_SEASONALITY` in the generator:

| Month | Multiplier | Effect |
|---|---|---|
| November | 1.35 | +35% (early holiday shopping) |
| December | 1.45 | +45% (peak holiday shopping) |
| January | 0.80 | -20% (post-holiday slowdown) |
| February | 0.90 | -10% (continued seasonal softness) |
| March | 0.80 | -20% (see revenue dip below) |
| All other months | 1.00 / 1.05 | roughly flat |

This should show up directly as a revenue-by-month trend with a strong Q4
peak and a Jan-Mar trough — good for "show revenue trend over time" and
"compare Q4 to Q1" questions.

### 2. Revenue dip — March 2026

On top of the -20% seasonality multiplier above, March 2026 has three
additional, *targeted* reductions (`MARCH_DIP_*` constants in the
generator) so the dip has a discoverable "story" rather than just being a
uniform drop:

- **Electronics category** — its share of March orders is cut by an extra
  -25% (`MARCH_DIP_CATEGORY_FACTOR`), so Electronics revenue falls more than
  the category average in March.
- **Meta traffic source** — its share of March traffic is cut by an extra
  -30% (`MARCH_DIP_CHANNEL_FACTOR`), so Meta-attributed orders/revenue
  underperform in March specifically.
- **Returning customers** — customers with medium/high/VIP purchase
  propensity (i.e., repeat buyers) are down-weighted by 30%
  (`MARCH_RETURNING_FACTOR`) when picking the buyer for a March order, so
  repeat-customer order volume dips in March.

A **"Meta Retarget - Electronics"** campaign runs only in March 2026 with
normal spend but — because of the Electronics and Meta effects above — few
attributed orders, i.e. poor ROI.

Expected questions this supports: "Why did revenue drop in March 2026?",
"Which category contributed most?", "Which marketing channel
underperformed?".

### 3. VIP customers (Pareto effect)

~5% of customers are flagged as **VIP seeds** at creation time
(`VIP_SEED_FRACTION`). These customers:

- get the highest purchase-propensity tier (`"vip"`, sampling weight 15 vs.
  5/2/1 for high/medium/low), so they're picked far more often as the buyer
  on an order
- are biased toward **Organic or Referral** acquisition channels
  (`VIP_CHANNELS`, ~70% of the time)
- build bigger baskets (2-5 items, quantity 2-3 per item) and skew toward
  **premium-priced products** — the top 40% by price within each category
  (`PREMIUM_PRICE_QUANTILE`)

Together, this concentrates roughly **40% of total revenue in this top 5%
of customers** — a classic Pareto pattern. Note this 5% "VIP seed" group is
a generation-time construct distinct from (though largely overlapping with)
the `customers.segment = 'VIP'` label, which is derived separately from
actual spend (top 10%) in `assign_customer_segments`.

Expected questions: "Who are our most valuable customers?", "Which
acquisition channels bring high-value customers?", "What % of revenue comes
from the top 5%?".

### 4. Churn-risk customers

~10% of customers are flagged as **churn risk** at creation time
(`CHURN_RISK_FRACTION`). Relative to the end of the dataset
(`END_DATE` = 2026-05-31), these customers:

- have normal order/session history earlier on (their propensity is
  medium/high, so they're not just one-time buyers)
- place **no orders in the last 90 days** (`CHURN_CUTOFF_DATE` =
  `END_DATE` - 90 days, ~2026-03-02) — they're excluded from order
  generation entirely after that date
- in the ~60 days *before* that cutoff (`CHURN_DECLINE_START` ->
  `CHURN_CUTOFF_DATE`), their **basket size/AOV declines** — orders in this
  window are capped at 1-2 items, quantity 1
- their **website session frequency declines** in that same window
  (down-weighted to 30% of normal) and **drops to zero** after the cutoff

Expected questions: "Which customers are at risk?", "Show inactive
customers", "Who hasn't purchased in the last 90 days?".

### 5. Other baseline patterns

- **Category-level differences** — Electronics has the highest unit prices
  but fewest SKUs; Accessories has the most SKUs at the lowest price point.
  This creates different revenue-vs-units-sold profiles per category.
- **Traffic-source differences** — conversion rates differ by design
  (`CONVERSION_RATES` in the generator): Direct (~20%) and Organic (~15%)
  convert best; Meta (~6%) converts worst.
- **Customer segments** — `customers.segment` (`New`/`Returning`/`VIP`) is
  derived from actual completed-order history in
  `assign_customer_segments`, independent of (but correlated with) the VIP
  seed and churn-risk flags above.

## Loading into PostgreSQL

See the main repo README / architecture doc, or just:

```
python data/load_data.py
```

This applies `sql/schema.sql` (drops and recreates all tables) and bulk-
loads the CSVs from `data/output/`. Then run the checks in
`sql/validation_queries.sql` to confirm everything looks right.
