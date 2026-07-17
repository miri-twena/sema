# SEMA Synthetic Ecommerce Dataset

This dataset is generated locally — no real customer data is used. It's
designed to look like a real 13-month ecommerce business (**2025-06-01 →
2026-06-30**), **with a few patterns deliberately built in** so we can later
check whether SEMA finds the right story when asked questions like "why did
revenue drop?".

The range always ends on a **complete month** — the last full month before
"today" in this project. A partial month would drag its own totals down and
poison every month-over-month comparison the agent makes. `END_DATE` is an
explicit constant rather than derived from `date.today()`: every number below
is verified against this exact window, and reproducibility beats
auto-freshness.

## How to (re)generate

```
python data/generate_data.py
```

This writes six CSV files to `data/output/` (gitignored — regenerate any
time; the script uses a fixed random seed, so the output is the same every
run unless you change the config at the top of the script).

## Tables

Row counts below are **verified against the live database** after
`data/load_data.py`, not estimated.

| Table | Rows | Notes |
|---|---|---|
| `customers` | 5,000 | segment (`New`/`Returning`/`VIP`) derived from real order history |
| `products` | 100 | across 6 categories |
| `marketing_campaigns` | 17 | Meta/Google/Email, 1-3 month windows (incl. the March dip + Summer Sale campaigns) |
| `orders` | 22,123 | 13 months: 2025-06-01 to 2026-06-30 |
| `order_items` | 61,641 | 1-4 items per order |
| `website_sessions` | 144,510 | converting + non-converting visits |

`N_ORDERS` in the generator is **21,633**, not 22,123: it's the *seasonality
baseline*, and the June 2026 Summer Sale adds ~490 incremental orders on top.
That baseline is itself `20,000 × 13.25/12.25` — the ratio of summed
seasonality weights when the window grew from 12 to 13 months. Leaving it at
20,000 would have spread the same orders over an extra month and silently
shrunk every existing month by ~7.7%.

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
script prints a checklist confirming all seven stories below were injected.

**Every figure in this section was re-verified against the live database**
after the 13-month extension. This file is the answer key for `evals/`, so
treat a mismatch here as a bug in the docs, not in the data.

Revenue by month, for reference (completed orders):

| Month | Orders | Revenue | AOV |
|---|---|---|---|
| 2025-06 | 1,512 | $1,087,511 | $719 |
| 2025-07 | 1,432 | $1,119,279 | $782 |
| 2025-08 | 1,437 | $1,057,614 | $736 |
| 2025-09 | 1,489 | $1,110,818 | $746 |
| 2025-10 | 1,590 | $1,211,232 | $762 |
| 2025-11 | 2,041 | $1,597,997 | $783 |
| **2025-12** | **2,184** | **$1,698,041** | $777 | ← Q4 peak |
| 2026-01 | 1,203 | $877,573 | $729 |
| 2026-02 | 1,349 | $932,212 | $691 |
| **2026-03** | **1,199** | **$793,243** | $662 | ← the dip (lowest month) |
| 2026-04 | 1,495 | $1,215,635 | $813 |
| 2026-05 | 1,498 | $1,235,547 | $825 |
| **2026-06** | **1,951** | **$1,290,504** | **$661** | ← Summer Sale |

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

Verified (Feb → Mar):

- **Overall**: $932,212 → $793,243 (**-14.9%**) — March is the lowest month
  of all 13.
- **Electronics**: $427,689 → $369,183 (-13.7%), an absolute drop of
  **$58,506 — the largest of any category**, so it is the biggest single
  contributor to the decline. (By *percentage* the sharpest fallers are
  Sports & Outdoors -31% and Home & Kitchen -23.7%; "contributed most"
  means the absolute drop.)
- **Meta orders**: 200 → 132 (**-34%**, the steepest of any channel).

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

⚠️ **Two different "top 5%" numbers — don't confuse them.** The ~40% above
describes the *designed generator cohort* (the `_vip_seed` flag). The number
a **user** actually gets when they ask "what share of revenue comes from our
top 5% of customers?" is computed from real spend — the top 5% of the 4,054
*paying* customers (203 of them) earn **48.2% of total revenue** (verified
against the live DB; it was 48.5% before the 13-month extension). That 48.2%
is what `evals/golden/ecommerce.yaml` asserts.

Expected questions: "Who are our most valuable customers?", "Which
acquisition channels bring high-value customers?", "What % of revenue comes
from the top 5%?".

### 4. Churn-risk customers

~10% of customers are flagged as **churn risk** at creation time
(`CHURN_RISK_FRACTION`). Relative to the end of the dataset
(`END_DATE` = 2026-06-30), these customers:

- have normal order/session history earlier on (their propensity is
  medium/high, so they're not just one-time buyers)
- place **no orders in the last 90 days** (`CHURN_CUTOFF_DATE` =
  `END_DATE` - 90 days, **2026-04-01**) — they're excluded from order
  generation entirely after that date
- in the ~60 days *before* that cutoff (`CHURN_DECLINE_START` ->
  `CHURN_CUTOFF_DATE`), their **basket size/AOV declines** — orders in this
  window are capped at 1-2 items, quantity 1
- their **website session frequency declines** in that same window
  (down-weighted to 30% of normal) and **drops to zero** after the cutoff

The cutoff is **relative to `END_DATE`, by design** — it moved from
2026-03-02 to 2026-04-01 when the window was extended. Keeping it relative is
what makes the constant honest: the cohort really is "no order in the last 90
days" as measured against the data's own end, which is exactly what the
semantic layer computes from `MAX(order_date)`. Pinning it to an absolute
date would have quietly turned it into a *120-day-inactive* cohort.

Verified: **1,795 customers** have no completed order in the 90 days before
the dataset's max order date (2026-06-30, cutoff 2026-04-01). This was 1,845
before the extension.

Expected questions: "Which customers are at risk?", "Show inactive
customers", "Who hasn't purchased in the last 90 days?".

### 5. Summer Sale — June 2026 ("bought growth")

June 2026 recovers from the spring, but not healthily: the lift is **bought**
with a heavily discounted, heavily promoted sale (`SUMMER_SALE_*`).

- order volume for the month only is boosted **+30%** (`SUMMER_SALE_VOLUME_FACTOR`)
- **45%** of June orders carry a discount vs the 15% baseline, and the
  discounts are deeper (15-35% vs 5-20%)
- a **"Summer Sale 2026"** campaign (Meta, $9,000 spend) runs only in June

Verified (May → June):

| | May 2026 | June 2026 | Change |
|---|---|---|---|
| Orders | 1,498 | 1,951 | **+30.2%** |
| Revenue | $1,235,547 | $1,290,504 | **+4.4%** |
| AOV | $824.80 | $661.46 | **-19.8%** |
| Orders discounted | 13.5% | 45.6% | +32pp |

**This is the story**: orders up 30%, revenue up only 4.4% — the discounting
ate almost the entire volume gain. The "Summer Sale 2026" campaign returns a
**ROAS of 11.07** ($99,593 attributed revenue on $9,000 spend) — mediocre
against a portfolio median around 20-30, though deliberately *not* the worst
campaign in the set.

> **Note on the AOV figure.** The -19.8% is larger than a discount-only model
> predicts (~-9%), because the Electronics price increase (§6) lands in the
> same month and drags the mix. This is arithmetically unavoidable: Electronics
> is ~50% of revenue, so holding it flat (§6) while total orders rise 30%
> *forces* AOV down hard. The two June stories share one AOV.

### 6. Electronics price increase — June 2026

Electronics list prices rise **+7%** on 2026-06-01 and demand responds
(`PRICE_INCREASE_*`). Historical `order_items` keep the price they were sold
at; `products.unit_price` reflects the new list price, and `unit_cost` is
unchanged, so the margin widens.

Verified (May → June):

| | May 2026 | June 2026 | Change |
|---|---|---|---|
| Avg unit price | $409.68 | $426.34 | **+4.1%** |
| Units sold | 1,521 | 1,425 | **-6.3%** |
| Revenue | $626,051 | $612,203 | **-2.2% (flat)** |

The realised avg unit price moves +4.1% rather than the full +7% because
product mix within the category shifts too — the +7% is applied to every
Electronics line item, so a per-product comparison shows the full increase.

**This is the story**: in a month when a discount sale pushed *every other*
category up, Electronics got more expensive, sold fewer units, and flatlined.
That contrast is the answer to "was the price increase worth it?".

> **Schema note.** There is no per-**category** conversion rate in this schema
> — `website_sessions` has no category dimension, so conversion rate exists
> only per traffic source. The demand response is therefore modelled as fewer
> Electronics orders/units, which is what the schema can actually express.
> `PRICE_INCREASE_DEMAND_FACTOR` is 0.65 (a strong-looking number) because it
> has to swim upstream against the sale's +30% volume *and* because — like
> `MARCH_DIP_CATEGORY_FACTOR` — it only steers the order's focus category
> (70% of line items). The realised swing is the -6.3% above.

### 7. Email conversion lift — June 2026

A new email flow goes live in June 2026 (`EMAIL_LIFT_*`): the same Email
traffic converts far better, making Email the **best-converting channel that
month** — it is normally third, behind Direct and Organic.

Verified, conversion rate (sessions → orders) by source:

| Source | May 2026 | June 2026 |
|---|---|---|
| **Email** | 14.76% (2nd) | **29.72% (1st)** |
| Direct | 20.04% (1st) | 24.96% |
| Organic | 14.63% | 18.75% |
| Referral | 9.10% | 11.11% |
| Google | 6.74% | 9.58% |
| Meta | 6.08% | 6.89% |

Every channel's rate rises in June (the sale means more orders against a flat
non-converting session base), but only Email **changes rank**. Expected
question: "which channel should I invest in?" — with a time-sensitive answer.

### 8. Other baseline patterns

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
