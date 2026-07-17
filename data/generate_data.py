"""
SEMA synthetic ecommerce data generator.

This script creates a realistic-looking 13-month ecommerce dataset
(2025-06-01 .. 2026-06-30) and writes it to CSV files in data/output/. The
CSVs are then loaded into PostgreSQL by data/load_data.py.

Why generate data instead of using a real dataset?
- No real customer data is needed or used (privacy, simplicity).
- We can bake in *known* business patterns (seasonality, a revenue dip,
  category/campaign/traffic-source differences) so we can later check
  whether SEMA's answers match the "ground truth" we built in here.

How to run:
    python data/generate_data.py

Output:
    data/output/customers.csv
    data/output/products.csv
    data/output/marketing_campaigns.csv
    data/output/orders.csv
    data/output/order_items.csv
    data/output/website_sessions.csv
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

# Windows consoles often default to a non-UTF-8 codepage (e.g. cp1252),
# which can't encode the "✓" characters in the final summary below.
# Reconfigure stdout to UTF-8 so the script runs the same on every platform.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
from faker import Faker

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEED = 42  # fixed seed -> running this script always produces the same data

N_CUSTOMERS = 5_000
N_PRODUCTS = 100
# Orders are split across months proportional to MONTH_SEASONALITY, so this
# total is a *density* knob, not just a size knob: N_ORDERS / sum(weights) is
# the orders-per-average-month. When the window grew from 12 to 13 months
# (2026-06 added), keeping 20,000 here would have silently shrunk every
# existing month by ~7.7% -- a contraction with no business story behind it.
# 21,633 = 20,000 * 13.25/12.25 (the ratio of summed seasonality weights),
# which holds the per-month volume of the original 12 months constant.
# This is the SEASONALITY BASELINE, not the final row count: the June 2026
# Summer Sale adds ~490 incremental orders on top (see SUMMER_SALE_*).
N_ORDERS = 21_633

# 13 months of history, ending the last COMPLETE month before "today" in this
# project (today = 2026-07-16). Deliberately not date.today()-derived: the
# documented ground truth below (and evals/golden/) is verified against this
# exact window, so reproducibility beats auto-freshness. A partial month is
# never generated -- it would poison every month-over-month comparison.
START_DATE = date(2025, 6, 1)
END_DATE = date(2026, 6, 30)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# Product categories, with a realistic price range and how many of the
# 100 products fall into each category. Counts sum to N_PRODUCTS.
CATEGORIES: dict[str, dict] = {
    "Electronics":       {"price_range": (80, 600), "n_products": 15},
    "Apparel":           {"price_range": (15, 120), "n_products": 25},
    "Accessories":       {"price_range": (8, 60),   "n_products": 25},
    "Home & Kitchen":    {"price_range": (20, 200), "n_products": 15},
    "Beauty":            {"price_range": (10, 80),  "n_products": 12},
    "Sports & Outdoors": {"price_range": (15, 250), "n_products": 8},
}

# Traffic sources used for both customer acquisition and order/session
# attribution, with their overall popularity weights.
TRAFFIC_SOURCES = ["Organic", "Direct", "Google", "Meta", "Email", "Referral"]
TRAFFIC_SOURCE_WEIGHTS = [0.35, 0.20, 0.15, 0.15, 0.10, 0.05]

# Channels that can have a marketing campaign attached (Direct/Organic/
# Referral are never campaign-attributed).
CAMPAIGN_CHANNELS = ["Meta", "Google", "Email"]

# Target conversion rate (sessions -> orders) per traffic source. Organic
# and Direct visitors convert better than paid/cold channels -- a realistic
# pattern that SEMA should be able to surface.
CONVERSION_RATES = {
    "Organic": 0.15,
    "Direct": 0.20,
    "Email": 0.18,
    "Google": 0.08,
    "Meta": 0.06,
    "Referral": 0.10,
}

DEVICE_TYPES = ["mobile", "desktop", "tablet"]
DEVICE_WEIGHTS = [0.55, 0.35, 0.10]

COUNTRIES = [
    "United States", "Canada", "United Kingdom", "Germany",
    "Australia", "France", "Netherlands", "Ireland",
]

# --- Business story: seasonality ---
# Per-month seasonality multiplier (relative demand), applied to order
# volume via orders_per_month in generate_orders_and_items(). November and
# December get a strong holiday boost; January and February are a
# post-holiday slowdown; March carries an *additional* intentional dip on
# top of its multiplier (see MARCH_DIP_* below).
MONTH_SEASONALITY = {
    1: 0.80,   # Jan - post-holiday slowdown (-20%)
    2: 0.90,   # Feb - continued seasonal softness (-10%)
    3: 0.80,   # Mar - intentional revenue dip (~-20%), see MARCH_DIP_* below
    4: 1.00,
    5: 1.00,
    6: 1.00,
    7: 0.95,
    8: 0.95,
    9: 1.00,
    10: 1.05,
    11: 1.35,  # Nov - early holiday shopping (+35%)
    12: 1.45,  # Dec - peak holiday shopping (+45%)
}

# --- Business story: March 2026 revenue dip ---
# March 2026 is a deliberately "bad month" (~-20% revenue overall, via
# MONTH_SEASONALITY above). On top of that overall dip, three specific
# drivers are exaggerated so the drop has a discoverable "story" when
# sliced by category, channel, or customer segment:
#   - Electronics' share of March orders is cut further (-25% relative
#     weight) -> Electronics revenue falls more than the category average.
#   - Meta's share of March traffic is cut further (-30% relative weight)
#     -> Meta-attributed orders/revenue underperform in March.
#   - "Returning"-like customers (medium/high/VIP purchase propensity) are
#     less likely to be selected for a March order -> repeat-customer order
#     volume dips in March specifically.
# A "Meta Retarget - Electronics" campaign runs in March with normal spend
# but (because of the two effects above) few attributed orders -- a
# "campaign ROI tanked" story SEMA can find via campaign performance.
MARCH_DIP_MONTH = date(2026, 3, 1)
MARCH_DIP_CATEGORY = "Electronics"
MARCH_DIP_CATEGORY_FACTOR = 0.75   # relative category weight in March (-25%)
MARCH_DIP_CHANNEL = "Meta"
MARCH_DIP_CHANNEL_FACTOR = 0.70    # relative traffic-source weight in March (-30%)
MARCH_RETURNING_FACTOR = 0.70      # relative selection weight for repeat-buyer customers in March

# --- Business story: VIP customers (Pareto effect) ---
# ~5% of customers are flagged as "VIP seeds" at creation time (see
# generate_customers). They get the highest purchase-propensity tier (so
# they're picked far more often as the buyer on an order), are biased toward
# Organic/Referral acquisition, and -- in generate_orders_and_items -- build
# bigger baskets with a preference for premium-priced products. Together
# this concentrates roughly 40% of total revenue in this 5% of customers,
# the classic "Pareto" pattern.
VIP_SEED_FRACTION = 0.05
VIP_CHANNELS = ["Organic", "Referral"]
VIP_CHANNEL_WEIGHT = 0.70  # probability a VIP seed's acquisition_channel is Organic/Referral
PREMIUM_PRICE_QUANTILE = 0.60  # within a category, products at/above this price quantile are "premium"

# --- Business story: churn-risk customers ---
# ~10% of customers are flagged as "churn risk" at creation time. They have
# normal order/session history earlier in the dataset, but:
#   - place no orders at all in the last 90 days (relative to END_DATE)
#   - in the ~60 days before that cutoff, their basket size/AOV declines
#   - their website session frequency declines over that same window, then
#     drops to zero after the cutoff
CHURN_RISK_FRACTION = 0.10
CHURN_CUTOFF_DATE = END_DATE - timedelta(days=90)            # last 90 days = "inactive"
CHURN_DECLINE_START = CHURN_CUTOFF_DATE - timedelta(days=60)  # gradual decline window

# --- Business story: June 2026 "Summer Sale" -- bought growth ---
# June 2026 revenue recovers from the spring level, but NOT healthily: the
# lift is bought with a heavily discounted, heavily promoted sale.
#   - order volume is boosted (+30%) for this month only
#   - far more orders carry a discount (45% vs the 15% baseline) and the
#     discounts are deeper (15-35% vs 5-20%) -> AOV falls ~9%
#   - a "Summer Sale 2026" campaign carries a large spend for a mediocre
#     ROAS -> "we grew, but we paid for it"
# Deliberately NOT the worst campaign in the dataset (that stays Email
# Campaign 2): the story here is "mediocre return on a big bet", not "this
# campaign is a disaster".
# Note this is a DATE-specific multiplier, not a MONTH_SEASONALITY change:
# that dict is keyed by month NUMBER, so raising month 6 would also alter
# June 2025 and break the existing documented ground truth.
SUMMER_SALE_MONTH = date(2026, 6, 1)
SUMMER_SALE_VOLUME_FACTOR = 1.30       # +30% orders vs a normal June
SUMMER_SALE_DISCOUNT_PROB = 0.45       # vs 0.15 baseline
SUMMER_SALE_DISCOUNT_RANGE = (0.15, 0.35)  # vs (0.05, 0.20) baseline
SUMMER_SALE_CHANNEL = "Meta"
# Spend is sized so the campaign lands MEDIOCRE (ROAS ~10-13: well under the
# ~20-30 median, comfortably above the worst) rather than becoming the
# worst campaign in the set -- "Email Campaign 2" keeps that title, and the
# golden eval for "which campaign performed worst" depends on it.
SUMMER_SALE_BUDGET = 10_000.00
SUMMER_SALE_SPEND = 9_000.00

# --- Business story: Electronics price increase (June 2026) ---
# Electronics list prices rise 7% on June 1 2026, and demand responds: the
# category's share of orders falls ~10%. Net effect is revenue roughly flat
# (1.07 * 0.90 = 0.96) with AOV up and units down -- the classic "was the
# price increase worth it?" question.
# NOTE on measurement: there is no per-CATEGORY conversion rate in this
# schema -- website_sessions has no category dimension, so conversion rate
# only exists per traffic_source. The demand response is therefore modelled
# as fewer Electronics orders/units (which the schema CAN express) rather
# than as a category conversion rate.
# Historical order_items keep the price they were sold at; products.unit_price
# is bumped to the new list price at the end of the run (unit_cost is left
# alone, so the margin widens -- part of the same story).
PRICE_INCREASE_MONTH = date(2026, 6, 1)
PRICE_INCREASE_CATEGORY = "Electronics"
PRICE_INCREASE_FACTOR = 1.07        # +7% list price from June 1 2026
# Relative category weight (elasticity). This has to be strong enough to
# swim UPSTREAM against the Summer Sale: June carries +30% order volume, so
# a mild factor would still leave Electronics units RISING and hide the whole
# story. At 0.65 the category's units fall ~7% against May even with the sale
# on, which -- with prices +7% -- lands revenue roughly flat while every other
# category grows. That contrast ("everything else was discounted and grew;
# Electronics got dearer and flatlined") is the story.
# Like MARCH_DIP_CATEGORY_FACTOR, this only steers the order's FOCUS category
# (70% of line items); the other 30% still draw from the base weights, so the
# realised swing is milder than the constant looks.
PRICE_INCREASE_DEMAND_FACTOR = 0.65

# --- Business story: Email conversion lift (June 2026) ---
# A new email flow goes live in June 2026: the same Email traffic converts
# far better, making Email the best-converting channel that month (it is
# normally third, behind Direct and Organic). Modelled by placing fewer
# NON-converting Email sessions in June -- converting sessions follow orders,
# so cutting the denominator is what raises the rate.
EMAIL_LIFT_MONTH = date(2026, 6, 1)
EMAIL_LIFT_SOURCE = "Email"
EMAIL_LIFT_SESSION_FACTOR = 0.60  # relative weight of June for non-converting Email sessions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def month_range(start: date, end: date) -> list[date]:
    """Return the first day of each month from start to end, inclusive."""
    months = []
    current = date(start.year, start.month, 1)
    while current <= end:
        months.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return months


def random_datetime_in_month(rng: np.random.Generator, month_start: date) -> datetime:
    """Pick a random timestamp within the given calendar month."""
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)
    days_in_month = (next_month - month_start).days
    day_offset = int(rng.integers(0, days_in_month))
    seconds_offset = int(rng.integers(0, 24 * 60 * 60))
    return datetime(month_start.year, month_start.month, 1) + timedelta(
        days=day_offset, seconds=seconds_offset
    )


# ---------------------------------------------------------------------------
# Step 1: Products
# ---------------------------------------------------------------------------

def generate_products(rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    """Create N_PRODUCTS products spread across the defined categories."""
    rows = []
    product_id = 1
    for category, cfg in CATEGORIES.items():
        low, high = cfg["price_range"]
        for _ in range(cfg["n_products"]):
            unit_price = round(float(rng.uniform(low, high)), 2)
            # Margin: cost is 40-70% of price (so 30-60% gross margin).
            unit_cost = round(unit_price * float(rng.uniform(0.40, 0.70)), 2)
            launch_date = date(2024, 1, 1) + timedelta(
                days=int(rng.integers(0, (END_DATE - date(2024, 1, 1)).days))
            )
            rows.append(
                {
                    "product_id": product_id,
                    "product_name": f"{category} {fake.word().capitalize()} {product_id}",
                    "category": category,
                    "unit_price": unit_price,
                    "unit_cost": unit_cost,
                    "launch_date": launch_date.isoformat(),
                    "is_active": True,
                }
            )
            product_id += 1
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 2: Marketing campaigns
# ---------------------------------------------------------------------------

def generate_campaigns(rng: np.random.Generator) -> pd.DataFrame:
    """
    Create marketing campaigns across Meta/Google/Email, each active for a
    1-3 month window. Includes one special campaign tied to the
    intentional March revenue dip (see MARCH_DIP_MONTH / MARCH_DIP_CATEGORY
    above).
    """
    rows = []
    campaign_id = 1
    months = month_range(START_DATE, END_DATE)

    # 1-2 campaigns per channel per quarter-ish -> roughly 12-15 total.
    for channel in CAMPAIGN_CHANNELS:
        for i in range(5):
            start_month = months[int(rng.integers(0, len(months)))]
            duration_months = int(rng.integers(1, 4))  # 1-3 months
            end_month_idx = min(
                months.index(start_month) + duration_months - 1, len(months) - 1
            )
            end_month = months[end_month_idx]
            if end_month.month == 12:
                end_date_val = date(end_month.year, 12, 31)
            else:
                end_date_val = date(end_month.year, end_month.month + 1, 1) - timedelta(days=1)

            budget = round(float(rng.uniform(3_000, 20_000)), 2)
            spend = round(budget * float(rng.uniform(0.80, 1.05)), 2)

            rows.append(
                {
                    "campaign_id": campaign_id,
                    "campaign_name": f"{channel} Campaign {i + 1}",
                    "channel": channel,
                    "start_date": start_month.isoformat(),
                    "end_date": end_date_val.isoformat(),
                    "budget": budget,
                    "spend": spend,
                }
            )
            campaign_id += 1

    # The dip campaign: runs only during MARCH_DIP_MONTH, on the
    # MARCH_DIP_CHANNEL channel, with a normal-sized spend -- but (by
    # construction, see generate_orders_and_items) it drives very few
    # orders. This is the "campaign ROI tanked" story for the March dip.
    if MARCH_DIP_MONTH.month == 12:
        dip_end = date(MARCH_DIP_MONTH.year, 12, 31)
    else:
        dip_end = date(MARCH_DIP_MONTH.year, MARCH_DIP_MONTH.month + 1, 1) - timedelta(days=1)

    rows.append(
        {
            "campaign_id": campaign_id,
            "campaign_name": f"{MARCH_DIP_CHANNEL} Retarget - {MARCH_DIP_CATEGORY}",
            "channel": MARCH_DIP_CHANNEL,
            "start_date": MARCH_DIP_MONTH.isoformat(),
            "end_date": dip_end.isoformat(),
            "budget": 12_000.00,
            "spend": 11_500.00,
        }
    )
    campaign_id += 1

    # The Summer Sale campaign: runs only during SUMMER_SALE_MONTH with a
    # large spend. It DOES drive extra orders (see the volume factor in
    # generate_orders_and_items) -- but they're deeply discounted, so the
    # revenue it buys per dollar spent is unremarkable. This is the
    # "we grew, but we bought the growth" story.
    sale_end = date(
        SUMMER_SALE_MONTH.year, SUMMER_SALE_MONTH.month + 1, 1
    ) - timedelta(days=1)
    rows.append(
        {
            "campaign_id": campaign_id,
            "campaign_name": "Summer Sale 2026",
            "channel": SUMMER_SALE_CHANNEL,
            "start_date": SUMMER_SALE_MONTH.isoformat(),
            "end_date": sale_end.isoformat(),
            "budget": SUMMER_SALE_BUDGET,
            "spend": SUMMER_SALE_SPEND,
        }
    )

    return pd.DataFrame(rows)


def build_campaign_lookup(campaigns: pd.DataFrame) -> dict:
    """
    Pre-parse campaign channel/start/end dates into plain numpy arrays once,
    so active_campaign_for() (called tens of thousands of times) doesn't
    re-parse dates from strings on every call.
    """
    return {
        "campaign_id": campaigns["campaign_id"].to_numpy(),
        "channel": campaigns["channel"].to_numpy(),
        "start_date": pd.to_datetime(campaigns["start_date"]).dt.date.to_numpy(),
        "end_date": pd.to_datetime(campaigns["end_date"]).dt.date.to_numpy(),
    }


def active_campaign_for(
    lookup: dict, channel: str, on_date: date, rng: np.random.Generator
) -> int | None:
    """Pick a random campaign on the given channel that is active on_date, if any."""
    mask = (
        (lookup["channel"] == channel)
        & (lookup["start_date"] <= on_date)
        & (lookup["end_date"] >= on_date)
    )
    candidates = lookup["campaign_id"][mask]
    if len(candidates) == 0:
        return None
    return int(rng.choice(candidates))


# ---------------------------------------------------------------------------
# Step 3: Customers
# ---------------------------------------------------------------------------

def generate_customers(rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    """
    Create N_CUSTOMERS customers. Each gets a "propensity" tier (vip / high
    / medium / low) which influences how often they show up as the buyer on
    an order later -- this is what creates a realistic spread from
    one-time buyers to frequent VIPs. The actual "segment" label
    (New/Returning/VIP) is derived afterwards from real order history, in
    assign_customer_segments().

    Two extra flags are assigned here, on disjoint subsets of customers, and
    used later (in generate_orders_and_items / generate_website_sessions) to
    inject the VIP-Pareto and churn-risk business stories:
      - "_vip_seed": ~VIP_SEED_FRACTION of customers, given the "vip"
        propensity tier (ordered most often) and biased toward
        Organic/Referral acquisition.
      - "_churn_risk": ~CHURN_RISK_FRACTION of customers, given a
        non-"low" propensity (so they have real history) but excluded from
        orders/sessions after CHURN_CUTOFF_DATE.
    Both columns are temporary helper columns, dropped before saving to CSV.
    """
    rows = []
    signup_window_days = (END_DATE - (START_DATE - timedelta(days=365))).days

    # Pick disjoint sets of customer_ids for the VIP-seed and churn-risk
    # groups via a single shuffled permutation of 1..N_CUSTOMERS.
    n_vip = int(round(N_CUSTOMERS * VIP_SEED_FRACTION))
    n_churn = int(round(N_CUSTOMERS * CHURN_RISK_FRACTION))
    shuffled_ids = rng.permutation(np.arange(1, N_CUSTOMERS + 1))
    vip_seed_ids = set(shuffled_ids[:n_vip].tolist())
    churn_risk_ids = set(shuffled_ids[n_vip:n_vip + n_churn].tolist())

    for customer_id in range(1, N_CUSTOMERS + 1):
        signup_date = (START_DATE - timedelta(days=365)) + timedelta(
            days=int(rng.integers(0, signup_window_days))
        )

        is_vip_seed = customer_id in vip_seed_ids
        is_churn_risk = customer_id in churn_risk_ids

        if is_vip_seed:
            propensity = "vip"
            # VIP customers mostly came in via Organic or Referral.
            if rng.random() < VIP_CHANNEL_WEIGHT:
                acquisition_channel = rng.choice(VIP_CHANNELS)
            else:
                acquisition_channel = rng.choice(TRAFFIC_SOURCES, p=TRAFFIC_SOURCE_WEIGHTS)
        elif is_churn_risk:
            # Keep churn-risk customers out of the "low"/near-one-time-buyer
            # tier so they have a real order history before going quiet.
            propensity = rng.choice(["high", "medium"], p=[0.30, 0.70])
            acquisition_channel = rng.choice(TRAFFIC_SOURCES, p=TRAFFIC_SOURCE_WEIGHTS)
        else:
            propensity = rng.choice(["high", "medium", "low"], p=[0.10, 0.30, 0.60])
            acquisition_channel = rng.choice(TRAFFIC_SOURCES, p=TRAFFIC_SOURCE_WEIGHTS)

        rows.append(
            {
                "customer_id": customer_id,
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "email": fake.unique.email(),
                "signup_date": signup_date.isoformat(),
                "country": rng.choice(COUNTRIES),
                "acquisition_channel": acquisition_channel,
                # temporary helper columns, dropped before saving to CSV
                "_propensity": propensity,
                "_vip_seed": is_vip_seed,
                "_churn_risk": is_churn_risk,
            }
        )
    return pd.DataFrame(rows)


def build_premium_product_ids(products: pd.DataFrame) -> set:
    """
    Return the set of product_ids that count as "premium" -- the top
    (1 - PREMIUM_PRICE_QUANTILE) of products by price *within each
    category*. Used to give VIP customers a higher average order value by
    biasing their basket toward these products.
    """
    premium_ids: set = set()
    for _category, group in products.groupby("category"):
        threshold = group["unit_price"].quantile(PREMIUM_PRICE_QUANTILE)
        premium_ids.update(group.loc[group["unit_price"] >= threshold, "product_id"].tolist())
    return premium_ids


# ---------------------------------------------------------------------------
# Step 4: Orders and order_items
# ---------------------------------------------------------------------------

def generate_orders_and_items(
    rng: np.random.Generator,
    customers: pd.DataFrame,
    products: pd.DataFrame,
    campaigns: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generate N_ORDERS orders (with order_date driven by seasonality) plus
    their order_items. This is where the March 2026 revenue dip, the VIP
    Pareto effect, and the churn-risk customers' order behavior are injected
    -- see the MARCH_DIP_*, VIP_*, and CHURN_* constants near the top of this
    file.
    """
    campaign_lookup = build_campaign_lookup(campaigns)
    months = month_range(START_DATE, END_DATE)

    # Distribute N_ORDERS across months proportional to seasonality.
    weights = np.array([MONTH_SEASONALITY[m.month] for m in months], dtype=float)
    weights = weights / weights.sum()
    orders_per_month = (weights * N_ORDERS).round().astype(int)
    # Adjust rounding so the seasonality baseline totals exactly N_ORDERS.
    # NOTE: this must happen BEFORE the Summer Sale boost below -- months[-1]
    # IS the sale month, so applying it afterwards would subtract the boost
    # straight back out.
    orders_per_month[-1] += N_ORDERS - orders_per_month.sum()
    # Summer Sale: the promo drives INCREMENTAL order volume in June 2026 only
    # -- extra demand, not demand borrowed from other months -- so the run
    # writes slightly more than N_ORDERS rows. Applied here rather than via
    # MONTH_SEASONALITY (keyed by month number, so it would also hit June 2025).
    if SUMMER_SALE_MONTH in months:
        sale_idx = months.index(SUMMER_SALE_MONTH)
        orders_per_month[sale_idx] = int(
            round(orders_per_month[sale_idx] * SUMMER_SALE_VOLUME_FACTOR)
        )

    # Propensity -> sampling weight ("vip" customers get picked far more
    # often than even "high"-propensity customers -- this is the main lever
    # for the VIP/Pareto effect).
    propensity_weight = {"vip": 15.0, "high": 5.0, "medium": 2.0, "low": 1.0}
    customer_signup = pd.to_datetime(customers["signup_date"]).dt.date.values
    customer_ids = customers["customer_id"].values
    customer_weights = customers["_propensity"].map(propensity_weight).values

    # March revenue dip: precompute a second weight array where
    # "returning"-like customers (medium/high/vip propensity) are down-
    # weighted, so they're selected less often for March orders.
    returning_like_mask = customers["_propensity"].isin(["medium", "high", "vip"]).values
    march_customer_weights = customer_weights.copy()
    march_customer_weights[returning_like_mask] *= MARCH_RETURNING_FACTOR

    # Churn-risk customers stop placing orders after CHURN_CUTOFF_DATE.
    churn_risk_mask = customers["_churn_risk"].values
    vip_seed_set = set(customers.loc[customers["_vip_seed"], "customer_id"].tolist())
    churn_risk_set = set(customers.loc[customers["_churn_risk"], "customer_id"].tolist())

    # Premium products, used to give VIP customers a higher AOV.
    premium_product_ids = build_premium_product_ids(products)

    category_names = list(CATEGORIES.keys())
    # Baseline popularity: bigger categories (more SKUs) get picked more often.
    category_weights = np.array([CATEGORIES[c]["n_products"] for c in category_names], dtype=float)
    category_weights = category_weights / category_weights.sum()

    order_rows = []
    item_rows = []
    order_id = 1
    item_id = 1

    for month_start, n_orders_this_month in zip(months, orders_per_month):
        for _ in range(int(n_orders_this_month)):
            order_dt = random_datetime_in_month(rng, month_start)
            order_date_only = order_dt.date()

            is_march_dip = month_start == MARCH_DIP_MONTH
            is_summer_sale = month_start == SUMMER_SALE_MONTH
            # Electronics list prices rise on PRICE_INCREASE_MONTH and stay
            # up, so this is a ">=" test, not a single-month test.
            price_increase_active = order_date_only >= PRICE_INCREASE_MONTH

            # --- pick a "focus category" for this order ---
            cat_weights = category_weights.copy()
            if is_march_dip:
                # March dip: Electronics gets an extra reduction in its
                # share of orders (-25% relative weight).
                idx = category_names.index(MARCH_DIP_CATEGORY)
                cat_weights[idx] *= MARCH_DIP_CATEGORY_FACTOR
                cat_weights = cat_weights / cat_weights.sum()
            if price_increase_active:
                # Price increase: demand responds, so Electronics' share of
                # orders falls (the schema has no per-category conversion
                # rate -- see PRICE_INCREASE_* -- so elasticity shows up as
                # fewer Electronics orders/units).
                idx = category_names.index(PRICE_INCREASE_CATEGORY)
                cat_weights[idx] *= PRICE_INCREASE_DEMAND_FACTOR
                cat_weights = cat_weights / cat_weights.sum()
            focus_category = rng.choice(category_names, p=cat_weights)

            # --- pick a traffic source for this order ---
            src_weights = np.array(TRAFFIC_SOURCE_WEIGHTS, dtype=float)
            if is_march_dip:
                # March dip: Meta gets an extra reduction in its share of
                # traffic (-30% relative weight) -> fewer Meta-attributed
                # orders/revenue in March.
                idx = TRAFFIC_SOURCES.index(MARCH_DIP_CHANNEL)
                src_weights = src_weights.copy()
                src_weights[idx] *= MARCH_DIP_CHANNEL_FACTOR
                src_weights = src_weights / src_weights.sum()
            traffic_source = rng.choice(TRAFFIC_SOURCES, p=src_weights)

            # --- pick the customer (must have signed up by order_date) ---
            eligible = customer_signup <= order_date_only
            if order_date_only > CHURN_CUTOFF_DATE:
                # Churn-risk customers place no orders in the last 90 days.
                eligible = eligible & ~churn_risk_mask
            elig_ids = customer_ids[eligible]
            # March dip: use the weight array where repeat-buyer customers
            # are down-weighted, so they order less often in March.
            weights_to_use = march_customer_weights if is_march_dip else customer_weights
            elig_weights = weights_to_use[eligible].astype(float)
            elig_weights = elig_weights / elig_weights.sum()
            customer_id = int(rng.choice(elig_ids, p=elig_weights))

            is_vip_customer = customer_id in vip_seed_set
            is_churn_customer = customer_id in churn_risk_set
            # AOV declines in the ~60 days before a churn-risk customer goes
            # quiet for good.
            in_churn_decline_window = (
                is_churn_customer
                and CHURN_DECLINE_START <= order_date_only <= CHURN_CUTOFF_DATE
            )

            # --- campaign attribution ---
            campaign_id = None
            if traffic_source in CAMPAIGN_CHANNELS:
                campaign_id = active_campaign_for(campaign_lookup, traffic_source, order_date_only, rng)

            # --- order items: mostly from the focus category ---
            if in_churn_decline_window:
                # Smaller baskets as a churn-risk customer winds down.
                n_items = int(rng.integers(1, 3))
            elif is_vip_customer:
                # VIP customers build bigger baskets -> higher AOV.
                n_items = int(rng.integers(2, 6))
            else:
                n_items = int(rng.integers(1, 5))

            subtotal = 0.0
            for _ in range(n_items):
                if rng.random() < 0.7:
                    cat_for_item = focus_category
                else:
                    cat_for_item = rng.choice(category_names, p=category_weights)
                cat_products = products[products["category"] == cat_for_item]
                if is_vip_customer and rng.random() < 0.6:
                    # VIP customers skew toward premium-priced products.
                    premium_in_cat = cat_products[cat_products["product_id"].isin(premium_product_ids)]
                    if len(premium_in_cat) > 0:
                        cat_products = premium_in_cat
                product = cat_products.sample(1, random_state=int(rng.integers(0, 1_000_000))).iloc[0]
                if in_churn_decline_window:
                    quantity = 1
                elif is_vip_customer:
                    quantity = int(rng.integers(2, 4))
                else:
                    quantity = int(rng.integers(1, 4))
                unit_price = float(product["unit_price"])
                if price_increase_active and cat_for_item == PRICE_INCREASE_CATEGORY:
                    # Sold at the new list price. Line items keep the price
                    # they were actually sold at, so pre-June history stays
                    # at the old price (products.unit_price is bumped to the
                    # new list price at the end of the run).
                    unit_price = round(unit_price * PRICE_INCREASE_FACTOR, 2)
                subtotal += quantity * unit_price
                item_rows.append(
                    {
                        "order_item_id": item_id,
                        "order_id": order_id,
                        "product_id": int(product["product_id"]),
                        "quantity": quantity,
                        "unit_price": unit_price,
                    }
                )
                item_id += 1

            # --- discount: ~15% of orders get a 5-20% discount ---
            # During the Summer Sale, far more orders are discounted and the
            # discounts are deeper -> AOV falls even as order count rises.
            if is_summer_sale:
                discount_prob = SUMMER_SALE_DISCOUNT_PROB
                discount_low, discount_high = SUMMER_SALE_DISCOUNT_RANGE
            else:
                discount_prob = 0.15
                discount_low, discount_high = 0.05, 0.20

            discount_amount = 0.0
            if rng.random() < discount_prob:
                discount_amount = round(subtotal * float(rng.uniform(discount_low, discount_high)), 2)

            # --- shipping: free over $50 net of discount, else $5.99 ---
            net_subtotal = subtotal - discount_amount
            shipping_cost = 0.0 if net_subtotal >= 50 else 5.99

            total_amount = round(net_subtotal + shipping_cost, 2)

            # --- status: mostly completed, some refunded/cancelled ---
            status = rng.choice(["completed", "refunded", "cancelled"], p=[0.92, 0.05, 0.03])

            order_rows.append(
                {
                    "order_id": order_id,
                    "customer_id": customer_id,
                    "order_date": order_dt.isoformat(sep=" "),
                    "status": status,
                    "traffic_source": traffic_source,
                    "campaign_id": campaign_id,
                    "discount_amount": discount_amount,
                    "shipping_cost": shipping_cost,
                    "total_amount": total_amount,
                }
            )
            order_id += 1

    return pd.DataFrame(order_rows), pd.DataFrame(item_rows)


# ---------------------------------------------------------------------------
# Step 5: Derive customer segments from order history
# ---------------------------------------------------------------------------

def assign_customer_segments(customers: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    """
    Label each customer New / Returning / VIP based on their *completed*
    order history:
      - VIP: total completed spend in the top 10% of all spenders
      - Returning: 2+ completed orders (but not a VIP)
      - New: 0 or 1 completed orders
    """
    completed = orders[orders["status"] == "completed"]
    agg = completed.groupby("customer_id")["total_amount"].agg(["sum", "count"])
    agg.columns = ["total_spend", "order_count"]

    vip_threshold = agg["total_spend"].quantile(0.90)

    def label(row) -> str:
        if row["total_spend"] >= vip_threshold:
            return "VIP"
        if row["order_count"] >= 2:
            return "Returning"
        return "New"

    agg["segment"] = agg.apply(label, axis=1)

    customers = customers.merge(
        agg["segment"], how="left", left_on="customer_id", right_index=True
    )
    # Customers with zero orders at all (not in `agg`) are "New".
    customers["segment"] = customers["segment"].fillna("New")
    return customers


# ---------------------------------------------------------------------------
# Step 6: Website sessions
# ---------------------------------------------------------------------------

def generate_website_sessions(
    rng: np.random.Generator,
    customers: pd.DataFrame,
    campaigns: pd.DataFrame,
    orders: pd.DataFrame,
) -> pd.DataFrame:
    """
    Create website sessions: a "converting" session for ~75% of orders
    (linking session -> order), plus extra non-converting sessions so that
    each traffic source's overall conversion rate roughly matches
    CONVERSION_RATES.

    Churn-risk customers (see CHURN_* constants): converting sessions for
    these customers naturally stop after CHURN_CUTOFF_DATE because they have
    no orders to convert from (handled in generate_orders_and_items). For
    non-converting sessions, this function additionally:
      - excludes churn-risk customers entirely after CHURN_CUTOFF_DATE
      - down-weights them (so they appear less often) in the
        CHURN_DECLINE_START -> CHURN_CUTOFF_DATE window, simulating a
        gradual drop-off in site visits before they go inactive.
    """
    campaign_lookup = build_campaign_lookup(campaigns)
    session_rows = []
    session_id = 1
    customer_ids = customers["customer_id"].values
    customer_signup = pd.to_datetime(customers["signup_date"]).dt.date.values

    # Lookup array (index = customer_id) for fast churn-risk checks below.
    # customer_id values are 1..N_CUSTOMERS, so size N_CUSTOMERS + 1 covers
    # index 0 (unused) through N_CUSTOMERS.
    is_churn_risk_by_id = np.zeros(N_CUSTOMERS + 1, dtype=bool)
    is_churn_risk_by_id[customers.loc[customers["_churn_risk"], "customer_id"].values] = True

    # --- converting sessions, one per order (for ~75% of orders) ---
    converting_orders = orders.sample(frac=0.75, random_state=SEED)
    converting_counts_by_source: dict[str, int] = {src: 0 for src in TRAFFIC_SOURCES}

    for _, order in converting_orders.iterrows():
        order_dt = pd.to_datetime(order["order_date"])
        session_start = order_dt - timedelta(minutes=int(rng.integers(2, 240)))
        traffic_source = order["traffic_source"]
        converting_counts_by_source[traffic_source] += 1
        session_rows.append(
            {
                "session_id": session_id,
                "customer_id": int(order["customer_id"]),
                "session_start": session_start.isoformat(sep=" "),
                "traffic_source": traffic_source,
                "campaign_id": order["campaign_id"],
                "device_type": rng.choice(DEVICE_TYPES, p=DEVICE_WEIGHTS),
                "converted": True,
                "order_id": int(order["order_id"]),
            }
        )
        session_id += 1

    # --- non-converting sessions, sized so each source hits its target
    #     conversion rate (sessions = converting / rate) ---
    months = month_range(START_DATE, END_DATE)
    for traffic_source in TRAFFIC_SOURCES:
        converting_count = converting_counts_by_source[traffic_source]
        target_rate = CONVERSION_RATES[traffic_source]
        total_sessions_for_source = int(round(converting_count / target_rate))
        non_converting = max(total_sessions_for_source - converting_count, 0)

        # Which month each non-converting session lands in. Uniform by
        # default; for Email in June 2026 the weight is cut, so fewer
        # non-converting Email sessions land that month. Converting sessions
        # follow real orders, so shrinking the denominator is what lifts
        # June's Email conversion rate (see EMAIL_LIFT_*).
        month_weights = np.ones(len(months), dtype=float)
        if traffic_source == EMAIL_LIFT_SOURCE and EMAIL_LIFT_MONTH in months:
            month_weights[months.index(EMAIL_LIFT_MONTH)] *= EMAIL_LIFT_SESSION_FACTOR
        month_weights = month_weights / month_weights.sum()

        for _ in range(non_converting):
            month_start = months[int(rng.choice(len(months), p=month_weights))]
            session_dt = random_datetime_in_month(rng, month_start)
            session_date_only = session_dt.date()

            # ~60% of non-converting sessions are anonymous (no customer_id)
            if rng.random() < 0.60:
                customer_id = None
            else:
                eligible = customer_signup <= session_date_only
                if session_date_only > CHURN_CUTOFF_DATE:
                    # Churn-risk customers have stopped visiting entirely.
                    eligible = eligible & ~is_churn_risk_by_id[customer_ids]
                elig_ids = customer_ids[eligible]
                if len(elig_ids) == 0:
                    customer_id = None
                elif CHURN_DECLINE_START <= session_date_only <= CHURN_CUTOFF_DATE:
                    # Gradual decline: churn-risk customers show up less
                    # often as sessions approach the cutoff.
                    sample_weights = np.where(is_churn_risk_by_id[elig_ids], 0.3, 1.0)
                    sample_weights = sample_weights / sample_weights.sum()
                    customer_id = int(rng.choice(elig_ids, p=sample_weights))
                else:
                    customer_id = int(rng.choice(elig_ids))

            campaign_id = None
            if traffic_source in CAMPAIGN_CHANNELS:
                campaign_id = active_campaign_for(campaign_lookup, traffic_source, session_date_only, rng)

            session_rows.append(
                {
                    "session_id": session_id,
                    "customer_id": customer_id,
                    "session_start": session_dt.isoformat(sep=" "),
                    "traffic_source": traffic_source,
                    "campaign_id": campaign_id,
                    "device_type": rng.choice(DEVICE_TYPES, p=DEVICE_WEIGHTS),
                    "converted": False,
                    "order_id": None,
                }
            )
            session_id += 1

    return pd.DataFrame(session_rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    rng = np.random.default_rng(SEED)
    fake = Faker()
    Faker.seed(SEED)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Generating products...")
    products = generate_products(rng, fake)

    print("Generating marketing campaigns...")
    campaigns = generate_campaigns(rng)

    print("Generating customers...")
    customers = generate_customers(rng, fake)

    print(f"Generating {N_ORDERS:,} orders and their line items...")
    orders, order_items = generate_orders_and_items(rng, customers, products, campaigns)

    print("Deriving customer segments from order history...")
    customers = assign_customer_segments(customers, orders)
    customers = customers.drop(columns=["_propensity"])

    print("Generating website sessions...")
    sessions = generate_website_sessions(rng, customers, campaigns, orders)
    customers = customers.drop(columns=["_vip_seed", "_churn_risk"])

    # Electronics price increase: the CATALOG now shows the new list price.
    # Done after order generation on purpose -- order_items already captured
    # the price each line was actually sold at (old price before June 2026,
    # new price from June 2026 on), which is what a real order line stores.
    # unit_cost is intentionally left alone, so the margin widens.
    electronics = products["category"] == PRICE_INCREASE_CATEGORY
    products.loc[electronics, "unit_price"] = (
        products.loc[electronics, "unit_price"] * PRICE_INCREASE_FACTOR
    ).round(2)

    # Nullable integer columns: without this, pandas stores them as float64
    # (because of the NaN/None values) and writes "1.0" instead of "1" to
    # CSV, which PostgreSQL's COPY rejects for INTEGER columns.
    orders["campaign_id"] = orders["campaign_id"].astype("Int64")
    sessions["customer_id"] = sessions["customer_id"].astype("Int64")
    sessions["campaign_id"] = sessions["campaign_id"].astype("Int64")
    sessions["order_id"] = sessions["order_id"].astype("Int64")

    print("Writing CSV files to", OUTPUT_DIR)
    products.to_csv(os.path.join(OUTPUT_DIR, "products.csv"), index=False)
    campaigns.to_csv(os.path.join(OUTPUT_DIR, "marketing_campaigns.csv"), index=False)
    customers.to_csv(os.path.join(OUTPUT_DIR, "customers.csv"), index=False)
    orders.to_csv(os.path.join(OUTPUT_DIR, "orders.csv"), index=False)
    order_items.to_csv(os.path.join(OUTPUT_DIR, "order_items.csv"), index=False)
    sessions.to_csv(os.path.join(OUTPUT_DIR, "website_sessions.csv"), index=False)

    print("Done.")
    print(f"  products:           {len(products):,}")
    print(f"  marketing_campaigns:{len(campaigns):,}")
    print(f"  customers:          {len(customers):,}")
    print(f"  orders:             {len(orders):,}")
    print(f"  order_items:        {len(order_items):,}")
    print(f"  website_sessions:   {len(sessions):,}")

    print()
    print("Business stories injected:")
    print("  ✓ Revenue dip (March 2026: Electronics, Meta, returning customers)")
    print("  ✓ VIP customers (Pareto: top 5% ~ 40% of revenue)")
    print("  ✓ Seasonality (Nov/Dec up, Jan/Feb down, Mar dip)")
    print("  ✓ Churn risk (~10% of customers inactive in last 90 days)")
    print("  ✓ Summer Sale (June 2026: orders up, AOV down, mediocre campaign ROI)")
    print("  ✓ Electronics price increase (June 2026: +7% price, units down, revenue flat)")
    print("  ✓ Email conversion lift (June 2026: best-converting channel that month)")


if __name__ == "__main__":
    main()
