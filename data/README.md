# SEMA Synthetic Ecommerce Dataset

This dataset is generated locally — no real customer data is used. It's
designed to look like a real 13-month ecommerce business, **with a few
patterns deliberately built in** so we can later check whether SEMA finds
the right story when asked questions like "why did revenue drop?".

The range always ends on a **complete month** — the last full month before
today. A partial month would drag its own totals down and poison every
month-over-month comparison the agent makes. Unlike earlier versions of this
file, `END_DATE` is now `date.today()`-derived by default (see
`_configure()` in `data/generate_data.py`), so the demo never looks stale —
regenerate it periodically and the window slides forward automatically.
Pass `--end-date YYYY-MM-DD` (must be a month-end) to pin a reproducible
window instead, e.g. for a test fixture.

**As of this file's last regeneration, the window is 2025-07-01 →
2026-07-31.** Every number below is verified against that exact run — if you
regenerate, the window (and every verified number in this file) will have
moved on, and this file needs re-verifying against the new live database.
That's an accepted trade-off, not a bug: see `demo_freshness_prompt.md` /
`PROMPT_QUEUE.md` item 22 for why complete-months-only was chosen over
literally "yesterday".

## How to (re)generate

```
python data/generate_data.py                          # ends on the last complete month before today
python data/generate_data.py --end-date 2026-06-30     # pinned, reproducible (e.g. for a test fixture)
```

This writes six CSV files to `data/output/` (gitignored — regenerate any
time; the script uses a fixed random seed, so a given `--end-date` always
produces the same output unless you change the config at the top of the
script).

## Tables

Row counts below are **verified against the live database** after
`data/load_data.py`, not estimated.

| Table | Rows | Notes |
|---|---|---|
| `customers` | 5,000 | segment (`New`/`Returning`/`VIP`) derived from real order history |
| `products` | 100 | across 6 categories |
| `marketing_campaigns` | 17 | Meta/Google/Email, 1-3 month windows (incl. the March dip + Summer Sale campaigns) |
| `orders` | 22,100 | 13 months: 2025-07-01 to 2026-07-31 |
| `order_items` | 61,255 | 1-4 items per order |
| `website_sessions` | 144,215 | converting + non-converting visits |

`N_ORDERS` in the generator is **21,633**, not 22,100: it's the *seasonality
baseline*, and the Summer Sale month (§5) adds a few hundred incremental
orders on top (~467 this run). That baseline is itself `20,000 × 13.25/12.25`
— the ratio of summed
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
after this file's most recent regeneration (window 2025-07-01 → 2026-07-31,
today = 2026-08-01). This file is the answer key for `evals/`, so treat a
mismatch here as a bug in the docs, not in the data — and remember that the
*correct* numbers change every time the window slides forward, so "mismatch"
only means something right after a fresh regeneration + re-verification.

Revenue by month, for reference (completed orders):

| Month | Orders | Revenue | AOV |
|---|---|---|---|
| 2025-07 | 1,445 | $1,023,707 | $708 |
| 2025-08 | 1,444 | $1,092,577 | $757 |
| 2025-09 | 1,516 | $1,099,529 | $725 |
| 2025-10 | 1,570 | $1,202,679 | $766 |
| 2025-11 | 2,038 | $1,584,978 | $778 |
| **2025-12** | **2,195** | **$1,639,978** | $747 | ← Q4 peak |
| 2026-01 | 1,207 | $915,615 | $759 |
| 2026-02 | 1,359 | $988,171 | $727 |
| **2026-03** | **1,208** | **$794,007** | $657 | ← the dip (lowest month) |
| 2026-04 | 1,506 | $1,035,826 | $688 |
| 2026-05 | 1,512 | $1,176,403 | $778 |
| 2026-06 | 1,501 | $1,166,394 | $777 |
| **2026-07** | **1,861** | **$1,189,852** | **$639** | ← Summer Sale |

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

- **Overall**: $988,171 → $794,007 (**-19.6%**) — March is the lowest month
  of all 13.
- **Electronics**: $455,782 → $342,542 (-24.8%), an absolute drop of
  **$113,240 — the largest of any category**, so it is the biggest single
  contributor to the decline. (By *percentage* the sharpest faller is
  Sports & Outdoors at -28.7%; "contributed most" means the absolute drop.)
- **Meta orders**: 230 → 126 (**-45.2%**, the steepest of any channel).

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
top 5% of customers?" is computed from real spend — the top 5% of the 4,030
*paying* customers (202 of them) earn **47.9% of total revenue** (verified
against the live DB; it was 48.2% before the freshness fix). That 47.9% is
what `evals/golden/ecommerce.yaml` asserts.

Expected questions: "Who are our most valuable customers?", "Which
acquisition channels bring high-value customers?", "What % of revenue comes
from the top 5%?".

### 4. Churn-risk customers

~10% of customers are flagged as **churn risk** at creation time
(`CHURN_RISK_FRACTION`). Relative to the end of the dataset
(`END_DATE` = 2026-07-31, this run), these customers:

- have normal order/session history earlier on (their propensity is
  medium/high, so they're not just one-time buyers)
- place **no orders in the last 90 days** (`CHURN_CUTOFF_DATE` =
  `END_DATE` - 90 days, **2026-05-02** this run) — they're excluded from
  order generation entirely after that date
- in the ~60 days *before* that cutoff (`CHURN_DECLINE_START` ->
  `CHURN_CUTOFF_DATE`), their **basket size/AOV declines** — orders in this
  window are capped at 1-2 items, quantity 1
- their **website session frequency declines** in that same window
  (down-weighted to 30% of normal) and **drops to zero** after the cutoff

The cutoff is **relative to `END_DATE`, by design**, and now `END_DATE`
itself is relative to today — so this date moves every regeneration.
Keeping it relative is what makes the constant honest: the cohort really is
"no order in the last 90 days" as measured against the data's own end,
which is exactly what the semantic layer computes from `MAX(order_date)`
(see `sql/semantic/churn_risk.yaml`). Pinning it to an absolute date would
have quietly turned it into a cohort inactive for however many extra days
have passed since that date was written.

Verified: **1,791 customers** have no completed order in the 90 days before
the dataset's max order date (2026-07-31, cutoff 2026-05-02). This was 1,795
before the freshness fix — essentially unchanged, because the definition is
relative on both sides (data and query).

Expected questions: "Which customers are at risk?", "Show inactive
customers", "Who hasn't purchased in the last 90 days?".

### 5. Summer Sale — always the window's LAST month ("bought growth")

The window's last calendar month recovers from the prior month, but not
healthily: the lift is **bought** with a heavily discounted, heavily
promoted sale (`SUMMER_SALE_*`). `SUMMER_SALE_MONTH` (like
`PRICE_INCREASE_MONTH` and `EMAIL_LIFT_MONTH` below) is always
`months[-1]` — it slides forward every regeneration, so **"June 2026" in
older docs/evals means "July 2026" as of this run**, and will mean whatever
month comes next after the next regeneration.

- order volume for the month only is boosted **+30%** relative to what that
  month's baseline seasonality would otherwise be (`SUMMER_SALE_VOLUME_FACTOR`)
- **45%** of sale-month orders carry a discount vs the 15% baseline, and the
  discounts are deeper (15-35% vs 5-20%)
- a **"Summer Sale `<year>`"** campaign (Meta, $9,000 spend) runs only in
  that month — the year in the name is derived from `SUMMER_SALE_MONTH`,
  not hardcoded

Verified this run (June 2026 → July 2026, the current sale month):

| | June 2026 | July 2026 | Change |
|---|---|---|---|
| Orders | 1,501 | 1,861 | **+24.0%** |
| Revenue | $1,166,394 | $1,189,852 | **+2.0%** |
| AOV | $777.08 | $639.36 | **-17.7%** |
| Orders discounted | 13.5% | 44.7% | +31pp |

**This is the story**: orders up 24%, revenue up only 2.0% — the discounting
ate almost the entire volume gain. The "Summer Sale 2026" campaign returns a
**ROAS of ~11.7** (~$104,901 attributed revenue on $9,000 spend) — mediocre
against a portfolio median around 20-30, though deliberately *not* the worst
campaign in the set (see §"Other baseline patterns" note on campaign ROI).

> **Note on the AOV figure.** The AOV drop is larger than a discount-only
> model predicts, because the Electronics price increase (§6) lands in the
> same month and drags the mix. This is arithmetically unavoidable: Electronics
> is a large share of revenue, so holding it down (§6) while total orders
> rise *forces* AOV down hard. The two same-month stories share one AOV.

### 6. Electronics price increase — always the window's LAST month

Electronics list prices rise **+7%** on the 1st of the window's last month
and demand responds (`PRICE_INCREASE_*`). Historical `order_items` keep the
price they were sold at; `products.unit_price` reflects the new list price,
and `unit_cost` is unchanged, so the margin widens.

Verified this run (June 2026 → July 2026):

| | June 2026 | July 2026 | Change |
|---|---|---|---|
| Avg unit price | $409.60 | $428.31 | **+4.6%** |
| Units sold | 1,404 | 1,270 | **-9.5%** |
| Revenue | $576,541 | $548,612 | **-4.8%** |

The realised avg unit price moves +4.6% rather than the full +7% because
product mix within the category shifts too — the +7% is applied to every
Electronics line item, so a per-product comparison shows the full increase.
This run's revenue move (-4.8%) is a real decline rather than "flat" — the
exact split between price/units/revenue effects varies run to run since the
underlying random draws shift with the window, but the qualitative story
(Electronics underperforms while the sale lifts every other category) holds.

**This is the story**: in a month when a discount sale pushed *every other*
category up, Electronics got more expensive, sold fewer units, and its
revenue fell. That contrast is the answer to "was the price increase worth it?".

> **Schema note.** There is no per-**category** conversion rate in this schema
> — `website_sessions` has no category dimension, so conversion rate exists
> only per traffic source. The demand response is therefore modelled as fewer
> Electronics orders/units, which is what the schema can actually express.
> `PRICE_INCREASE_DEMAND_FACTOR` is 0.65 (a strong-looking number) because it
> has to swim upstream against the sale's +30% volume *and* because — like
> `MARCH_DIP_CATEGORY_FACTOR` — it only steers the order's focus category
> (70% of line items).

### 7. Email conversion lift — always the window's LAST month

A new email flow goes live in the window's last month (`EMAIL_LIFT_*`): the
same Email traffic converts far better, making Email the **best-converting
channel that month**.

Verified this run, conversion rate (sessions → orders) by source:

| Source | June 2026 | July 2026 |
|---|---|---|
| **Email** | 15.63% (2nd) | **32.06% (1st)** |
| Direct | 18.84% (1st) | 22.81% |
| Organic | 15.06% (3rd) | 17.26% |
| Referral | 9.38% | 10.59% |
| Google | 7.18% | 8.73% |
| Meta | 6.06% | 7.87% |

Every channel's rate rises in the sale month (more orders against a flat
non-converting session base), but only Email **changes rank**, overtaking
Direct. Expected question: "which channel should I invest in?" — with a
time-sensitive answer.

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
