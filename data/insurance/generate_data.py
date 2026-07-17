"""
SEMA synthetic AUTO INSURANCE data generator.

Creates a realistic ~2.5-year motor-insurance dataset (2024-01-01 .. losses
through 2026-06-30) and writes it to CSV files in data/insurance/output/,
matching sql/insurance/schema.sql. It is the insurance equivalent of
data/generate_data.py (ecommerce).

Why generate data: no real policyholder data is used, and we can bake in
*known* business patterns so we can later check whether SEMA's answers match
the ground truth we built in here.

Ground-truth stories injected (see constants + the summary printed at the end):
  - Claims seasonality: winter (Dec-Feb) has higher claim frequency.
  - Loss-ratio SPIKE in Jan 2026, driven by a weather event in the North
    region (the insurance analogue of the ecommerce "March revenue dip").
  - A SECOND, smaller event: a June 2026 heatwave in the South region
    (Weather + Fire claims, and only on policies that cover own-vehicle
    damage) -- deliberately a different region and a smaller magnitude than
    January, so the two events are worth comparing.
  - A June 2026 RATE ACTION: renewals from 2026-06-01 are written at +5%,
    and the renewing cohort retains noticeably worse -- the price/retention
    trade-off.
  - Young drivers (<25) have much higher claim frequency.
  - Comprehensive coverage is the least profitable (highest loss ratio);
    Liability-only is the most profitable.
  - Retention differs by channel: Tied Agent renews best, Direct-Online worst.
  - A severity tail: a few Theft / total-loss claims carry a big share of cost.

How to run:
    python data/insurance/generate_data.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

# Windows consoles often default to cp1252, which can't encode the summary's
# check marks. Reconfigure stdout to UTF-8 so it runs the same everywhere.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
from faker import Faker

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEED = 42  # fixed seed -> deterministic output

N_POLICYHOLDERS = 5_000
N_AGENTS = 40

# ~2.5 years of history so annual policies have time to renew (retention),
# ending the last COMPLETE month before "today" in this project.
#
# END_DATE and TODAY do DIFFERENT jobs, and the difference matters:
#   - END_DATE is the LOSS ceiling: no claim occurs after it, and exposure
#     (earned time on risk) stops there. It is a full month-end on purpose --
#     claims dated into a half-finished July would drag that month's loss
#     ratio down and poison every month-over-month comparison the agent makes.
#   - TODAY is the STATUS reference: which term is currently in force, which
#     premium instalments have been billed, and which claims have had time to
#     settle. Those are genuinely "as of now" facts, so they run to the real
#     current date.
# Both are explicit constants rather than date.today(): the ground truth in
# the docstring above is verified against this exact window, so reproducibility
# beats auto-freshness.
START_DATE = date(2024, 1, 1)
END_DATE = date(2026, 6, 30)
TODAY = date(2026, 7, 16)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# --- Coverage tiers (the products) ---
# base_annual_premium is the reference price before per-policy risk loading.
PRODUCTS = [
    {"product_name": "Auto Liability",      "coverage_type": "Liability",     "base_annual_premium": 450},
    {"product_name": "Auto TPFT",           "coverage_type": "TPFT",          "base_annual_premium": 750},
    {"product_name": "Auto Comprehensive",  "coverage_type": "Comprehensive", "base_annual_premium": 1150},
]
# How policyholders choose a tier.
COVERAGE_CHOICE = ["Comprehensive", "TPFT", "Liability"]
COVERAGE_WEIGHTS = [0.45, 0.30, 0.25]

# --- Distribution / regions ---
REGIONS = ["North", "Central", "South", "East", "West"]
REGION_WEIGHTS = [0.22, 0.26, 0.20, 0.16, 0.16]

# Sales / servicing channels (on the agent). Drives the RETENTION story.
AGENT_CHANNELS = ["Tied Agent", "Broker", "Direct-Online"]
AGENT_CHANNEL_WEIGHTS = [0.45, 0.30, 0.25]
# Probability a policy renews at expiry, by the selling agent's channel.
RENEWAL_PROB_BY_CHANNEL = {
    "Tied Agent": 0.88,     # best retention
    "Broker": 0.82,
    "Direct-Online": 0.62,  # price-shoppers churn most
}

VEHICLE_CATEGORIES = ["Sedan", "SUV", "Hatchback", "Truck", "Sports", "EV"]
VEHICLE_CATEGORY_WEIGHTS = [0.34, 0.26, 0.18, 0.08, 0.06, 0.08]
USAGE_TYPES = ["Private", "Commute", "Commercial", "Rideshare"]
USAGE_WEIGHTS = [0.45, 0.40, 0.08, 0.07]
MILEAGE_BANDS = ["<10k", "10-20k", "20k+"]

PAYMENT_METHODS = ["Credit Card", "Bank Transfer", "Direct Debit"]
CREDIT_BANDS = ["A", "B", "C", "D"]

# --- Claims model -----------------------------------------------------------
# Base expected claims per policy per year, scaled by the multipliers below.
BASE_CLAIM_FREQUENCY = 0.08

# Frequency multipliers for the injected stories. Comprehensive's multiplier
# is set high enough to overcome its larger premium base, so it lands as the
# LEAST profitable tier (highest loss ratio) -- Liability stays the best.
COVERAGE_FREQ_MULT = {"Comprehensive": 1.9, "TPFT": 0.95, "Liability": 0.40}
REGION_FREQ_MULT = {"North": 1.6, "Central": 1.2, "South": 1.0, "East": 1.0, "West": 1.0}
REGION_SEVERITY_MULT = {"North": 1.2, "Central": 1.3, "South": 1.0, "East": 1.0, "West": 1.0}

# Winter months get more claims (collisions / weather).
WINTER_MONTHS = {12, 1, 2}
WINTER_FREQ_MULT = 1.6

# The Jan-2026 weather event: extra Weather claims for North-region policies
# active that month -> a discoverable loss-ratio spike.
EVENT_MONTH = date(2026, 1, 1)
EVENT_REGION = "North"
EVENT_EXTRA_WEATHER_LAMBDA = 0.45  # extra Weather claims (Poisson) per active North policy

# --- Business story: June 2026 heatwave (the SECOND, smaller catastrophe) ---
# A heatwave hits the South region in June 2026: extra Weather and Fire
# claims for policies in force that month. Deliberately a different region
# and a materially smaller event than the Jan-2026 storm, so "compare the
# two events" is a real question with a real answer rather than a repeat.
# Sizing: lambda 0.10 vs Jan's 0.45, and South carries no severity loading
# (REGION_SEVERITY_MULT South 1.0 vs North 1.2) -- the Fire share raises the
# per-claim cost, but total incurred still lands well under the Jan event.
# The event only touches policies that actually COVER own-vehicle damage --
# which is both physically correct and load-bearing for an existing story:
#   - Liability covers damage you do to OTHERS, so a heatwave wrecking your
#     own car produces no claim at all -> excluded.
#   - TPFT is Third Party, FIRE & Theft: fire is covered, general weather is
#     not -> Fire claims only.
#   - Comprehensive covers both -> Weather or Fire.
# Without this, the event lands per-POLICY and is coverage-blind, while
# premium is concentrated in Comprehensive (61% of premium on 45% of
# policies). TPFT would then absorb 30% of the event's claims on 26% of the
# premium, its loss ratio would climb faster than Comprehensive's, and the
# documented "Comprehensive is the least profitable tier" story would invert.
# Verified: coverage-blind gave TPFT 84.6% vs Comprehensive 84.5% (inverted);
# coverage-aware restores Comprehensive to the top of the table.
HEATWAVE_MONTH = date(2026, 6, 1)
HEATWAVE_REGION = "South"
HEATWAVE_EXTRA_LAMBDA = 0.10  # extra claims (Poisson) per active, covered South policy
HEATWAVE_COVERED_TYPES = {"Comprehensive", "TPFT"}
HEATWAVE_CLAIM_TYPES = ["Weather", "Fire"]
HEATWAVE_TYPE_WEIGHTS = [0.75, 0.25]  # Comprehensive only; TPFT gets Fire by definition

# --- Business story: June 2026 rate action ---
# A ~5% rate increase applies to renewals incepting from June 2026, and it
# costs some retention: the renewing cohort whose term expires on/after that
# date renews less often. Sets up the trade-off question -- "did the rate
# increase help the loss ratio, and what did it cost us in retention?"
RATE_ACTION_DATE = date(2026, 6, 1)
RATE_ACTION_PREMIUM_FACTOR = 1.05    # +5% on renewal premiums from that date
RATE_ACTION_RETENTION_DROP = 0.08    # renewal probability -8pp for terms expiring on/after it

# Claim types and their baseline mix; severity is a lognormal around the mean.
CLAIM_TYPES = ["Collision", "Third-Party Liability", "Glass", "Weather", "Theft", "Vandalism", "Fire"]
CLAIM_TYPE_WEIGHTS = [0.35, 0.20, 0.15, 0.10, 0.07, 0.08, 0.05]
CLAIM_SEVERITY_MEAN = {
    "Collision": 4_500,
    "Third-Party Liability": 6_000,
    "Glass": 500,
    "Weather": 2_500,
    "Theft": 16_000,      # the heavy tail
    "Vandalism": 1_200,
    "Fire": 12_000,
}
AT_FAULT_PROB = {
    "Collision": 0.55, "Third-Party Liability": 0.80, "Glass": 0.10,
    "Weather": 0.05, "Theft": 0.0, "Vandalism": 0.0, "Fire": 0.10,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def add_year(d: date) -> date:
    """Return the date one year later (handles Feb 29 by falling back a day)."""
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=d.day - 1)


def random_date_between(rng: np.random.Generator, start: date, end: date) -> date:
    """Uniform random date in [start, end]."""
    span = (end - start).days
    if span <= 0:
        return start
    return start + timedelta(days=int(rng.integers(0, span + 1)))


def lognormal_amount(rng: np.random.Generator, mean: float) -> float:
    """A positive amount whose median is roughly `mean`, with a right tail."""
    # sigma controls spread; mu set so exp(mu) = mean (median).
    value = float(rng.lognormal(mean=np.log(mean), sigma=0.6))
    return round(value, 2)


# ---------------------------------------------------------------------------
# Step 1: Products (coverage tiers)
# ---------------------------------------------------------------------------

def generate_products() -> pd.DataFrame:
    rows = []
    for i, p in enumerate(PRODUCTS, start=1):
        rows.append(
            {
                "product_id": i,
                "product_name": p["product_name"],
                "coverage_type": p["coverage_type"],
                "base_annual_premium": p["base_annual_premium"],
                "description": f"{p['coverage_type']} motor cover",
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 2: Agents
# ---------------------------------------------------------------------------

def generate_agents(rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    rows = []
    for agent_id in range(1, N_AGENTS + 1):
        channel = rng.choice(AGENT_CHANNELS, p=AGENT_CHANNEL_WEIGHTS)
        rows.append(
            {
                "agent_id": agent_id,
                "agent_name": fake.name(),
                "agency_name": f"{fake.last_name()} Insurance Services",
                "region": rng.choice(REGIONS, p=REGION_WEIGHTS),
                "channel": channel,
                "hire_date": random_date_between(rng, date(2018, 1, 1), date(2023, 12, 31)).isoformat(),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 3: Policyholders, vehicles, drivers
# ---------------------------------------------------------------------------

def generate_policyholders_vehicles_drivers(
    rng: np.random.Generator, fake: Faker, agents: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """One vehicle and one primary driver per policyholder; ~15% also get an
    additional driver. Returns (policyholders, vehicles, drivers)."""
    ph_rows, veh_rows, drv_rows = [], [], []
    agent_ids = agents["agent_id"].to_numpy()
    agent_channel = dict(zip(agents["agent_id"], agents["channel"]))

    driver_id = 1
    for pid in range(1, N_POLICYHOLDERS + 1):
        region = rng.choice(REGIONS, p=REGION_WEIGHTS)
        agent_id = int(rng.choice(agent_ids))
        # Age skews adult; a meaningful minority are young (<25) -> risk story.
        age = int(rng.choice(
            [22, 30, 40, 50, 60, 72],
            p=[0.14, 0.24, 0.24, 0.18, 0.13, 0.07],
        ) + rng.integers(0, 6))
        dob = date(TODAY.year - age, int(rng.integers(1, 13)), int(rng.integers(1, 28)))

        ph_rows.append(
            {
                "policyholder_id": pid,
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "date_of_birth": dob.isoformat(),
                "gender": rng.choice(["M", "F"]),
                "email": fake.unique.email(),
                "phone": fake.numerify("05#-###-####"),
                "city": fake.city(),
                "region": region,
                "postal_code": fake.numerify("#####"),
                "marital_status": rng.choice(["Single", "Married", "Divorced"], p=[0.4, 0.5, 0.1]),
                "customer_since": "",  # filled after we know first policy date
                "acquisition_channel": agent_channel[agent_id],
                "credit_band": rng.choice(CREDIT_BANDS, p=[0.30, 0.35, 0.25, 0.10]),
                # helper columns, dropped before save (no leading "_": pandas
                # itertuples renames underscore-prefixed columns to positional)
                "hlp_agent_id": agent_id,
                "hlp_region": region,
            }
        )

        # Vehicle
        veh_value = round(float(rng.uniform(8_000, 60_000)), 2)
        veh_rows.append(
            {
                "vehicle_id": pid,  # 1:1 with policyholder
                "policyholder_id": pid,
                "make": fake.company().split()[0],
                "model": fake.word().capitalize(),
                "model_year": int(rng.integers(2012, 2026)),
                "vehicle_category": rng.choice(VEHICLE_CATEGORIES, p=VEHICLE_CATEGORY_WEIGHTS),
                "vehicle_value": veh_value,
                "usage_type": rng.choice(USAGE_TYPES, p=USAGE_WEIGHTS),
                "annual_mileage_band": rng.choice(MILEAGE_BANDS, p=[0.35, 0.45, 0.20]),
                "registration_region": region,
            }
        )

        # Primary driver (the policyholder)
        license_age = max(age - 18, 1)
        primary_driver_id = driver_id
        drv_rows.append(
            {
                "driver_id": driver_id,
                "policyholder_id": pid,
                "first_name": ph_rows[-1]["first_name"],
                "last_name": ph_rows[-1]["last_name"],
                "date_of_birth": dob.isoformat(),
                "gender": ph_rows[-1]["gender"],
                "license_issue_date": date(dob.year + 18, dob.month, dob.day).isoformat(),
                "is_primary": True,
                "prior_at_fault_accidents": int(rng.choice([0, 1, 2, 3], p=[0.70, 0.20, 0.07, 0.03])),
            }
        )
        driver_id += 1

        # ~15% have an additional driver (not the primary)
        if rng.random() < 0.15:
            add_age = int(rng.integers(20, 65))
            add_dob = date(TODAY.year - add_age, int(rng.integers(1, 13)), int(rng.integers(1, 28)))
            drv_rows.append(
                {
                    "driver_id": driver_id,
                    "policyholder_id": pid,
                    "first_name": fake.first_name(),
                    "last_name": ph_rows[-1]["last_name"],
                    "date_of_birth": add_dob.isoformat(),
                    "gender": rng.choice(["M", "F"]),
                    "license_issue_date": date(add_dob.year + 18, add_dob.month, add_dob.day).isoformat(),
                    "is_primary": False,
                    "prior_at_fault_accidents": int(rng.choice([0, 1, 2], p=[0.8, 0.15, 0.05])),
                }
            )
            driver_id += 1

        # stash the primary driver age + id for premium/claim calc later
        ph_rows[-1]["hlp_primary_driver_id"] = primary_driver_id
        ph_rows[-1]["hlp_primary_age"] = age

    return pd.DataFrame(ph_rows), pd.DataFrame(veh_rows), pd.DataFrame(drv_rows)


# ---------------------------------------------------------------------------
# Step 4: Policies (renewal chains) -> written premium + retention
# ---------------------------------------------------------------------------

def _age_freq_mult(age: int) -> float:
    if age < 25:
        return 2.2          # young-driver story
    if age > 70:
        return 1.3
    return 1.0


def _premium_for(rng, base, age, veh_value, region, prior_accidents) -> float:
    mult = 1.0
    mult *= 1.6 if age < 25 else (1.2 if age > 70 else 1.0)
    mult *= 1.0 + min(veh_value, 60_000) / 200_000.0   # +0..0.3 for value
    mult *= {"North": 1.15, "Central": 1.10}.get(region, 1.0)
    mult *= 1.0 + 0.15 * prior_accidents
    mult *= float(rng.uniform(0.95, 1.08))             # idiosyncratic noise
    return round(base * mult, 2)


def generate_policies(
    rng: np.random.Generator,
    policyholders: pd.DataFrame,
    products: pd.DataFrame,
) -> pd.DataFrame:
    base_by_coverage = dict(zip(products["coverage_type"], products["base_annual_premium"]))
    pid_to_product = dict(zip(products["coverage_type"], products["product_id"]))

    rows = []
    policy_id = 1
    for ph in policyholders.itertuples():
        coverage = rng.choice(COVERAGE_CHOICE, p=COVERAGE_WEIGHTS)
        product_id = int(pid_to_product[coverage])
        base = base_by_coverage[coverage]
        channel = ph.acquisition_channel
        renewal_prob = RENEWAL_PROB_BY_CHANNEL[channel]
        prior_accidents = 0  # reflected via premium noise; kept simple here

        # First inception: anywhere in the first ~18 months of history.
        current_start = random_date_between(rng, START_DATE, date(2025, 6, 1))
        business_type = "New Business"
        previous_policy_id = None
        first_policy_date = current_start

        while True:
            end = add_year(current_start)
            premium = _premium_for(
                rng, base, ph.hlp_primary_age, 0, ph.hlp_region, prior_accidents
            )
            # Renewals drift the rate a little.
            if business_type == "Renewal":
                premium = round(premium * float(rng.uniform(0.98, 1.10)), 2)
                # Rate action: renewals incepting from RATE_ACTION_DATE are
                # written at +5% on top of the usual drift.
                if current_start >= RATE_ACTION_DATE:
                    premium = round(premium * RATE_ACTION_PREMIUM_FACTOR, 2)

            cancelled = False
            cancellation_date = None
            cancellation_reason = None
            successor_coming = False

            if current_start <= TODAY < end:
                # The term that covers "today" -> currently in force.
                status = "Active"
                # small chance of a mid-term cancellation even while active
                if rng.random() < 0.03:
                    status = "Cancelled"
                    cancelled = True
                    cancellation_date = random_date_between(rng, current_start, TODAY)
                    cancellation_reason = rng.choice(["Non-payment", "Customer request", "Sold vehicle"])
            else:
                # A term that has already fully ended: renew or lapse.
                # Rate action: a term expiring on/after RATE_ACTION_DATE is
                # quoted the higher renewal price, and some of those customers
                # walk -- the retention cost of the increase.
                effective_renewal_prob = renewal_prob
                if end >= RATE_ACTION_DATE:
                    effective_renewal_prob = max(renewal_prob - RATE_ACTION_RETENTION_DROP, 0.0)

                if rng.random() < 0.04:
                    status = "Cancelled"
                    cancelled = True
                    cancellation_date = random_date_between(rng, current_start, end)
                    cancellation_reason = rng.choice(["Non-payment", "Customer request", "Sold vehicle"])
                elif rng.random() < effective_renewal_prob:
                    status = "Renewed"
                    successor_coming = True
                else:
                    status = "Lapsed"

            rows.append(
                {
                    "policy_id": policy_id,
                    "policy_number": f"POL-{policy_id:06d}",
                    "policyholder_id": ph.policyholder_id,
                    "vehicle_id": ph.policyholder_id,  # 1:1
                    "product_id": product_id,
                    "agent_id": ph.hlp_agent_id,
                    "primary_driver_id": ph.hlp_primary_driver_id,
                    "start_date": current_start.isoformat(),
                    "end_date": end.isoformat(),
                    "term_months": 12,
                    "business_type": business_type,
                    "previous_policy_id": previous_policy_id,
                    "status": status,
                    "annual_premium": premium,
                    "deductible": float(rng.choice([0, 250, 500, 1000], p=[0.1, 0.35, 0.4, 0.15])),
                    "sum_insured": round(float(rng.uniform(15_000, 70_000)), 2),
                    "payment_frequency": "Monthly" if rng.random() < 0.30 else "Annual",
                    "cancellation_date": cancellation_date.isoformat() if cancellation_date else None,
                    "cancellation_reason": cancellation_reason,
                    # helper columns for claims/payments, dropped before save
                    "hlp_coverage": coverage,
                    "hlp_region": ph.hlp_region,
                    "hlp_age": ph.hlp_primary_age,
                    "hlp_cancelled": cancelled,
                }
            )

            this_id = policy_id
            policy_id += 1

            if successor_coming:
                previous_policy_id = this_id
                business_type = "Renewal"
                current_start = end
                continue
            break

        # record the policyholder's first-ever policy date as customer_since
        # (done back on the policyholders frame after generation)
        policyholders.loc[policyholders["policyholder_id"] == ph.policyholder_id, "customer_since"] = \
            first_policy_date.isoformat()

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 5: Premium payments (billing schedule + cash collected)
# ---------------------------------------------------------------------------

def generate_premium_payments(rng: np.random.Generator, policies: pd.DataFrame) -> pd.DataFrame:
    rows = []
    payment_id = 1
    for p in policies.itertuples():
        start = date.fromisoformat(p.start_date)
        cancel = date.fromisoformat(p.cancellation_date) if p.cancellation_date else None

        if p.payment_frequency == "Monthly":
            n, amount = 12, round(p.annual_premium / 12.0, 2)
            due_dates = [start.replace(day=1) + timedelta(days=0) for _ in range(0)]  # placeholder
            due_dates = []
            d = start
            for k in range(n):
                # advance ~1 month at a time
                month = (d.month % 12) + 1 if k > 0 else d.month
                year = d.year + (1 if (k > 0 and d.month == 12) else 0)
                d = date(year, month, min(start.day, 28)) if k > 0 else start
                due_dates.append(d)
        else:
            amount = p.annual_premium
            due_dates = [start]

        for due in due_dates:
            if cancel and due > cancel:
                break  # no further billing after cancellation
            if due <= TODAY:
                status = rng.choice(["Paid", "Failed", "Pending"], p=[0.95, 0.03, 0.02])
                paid = (due + timedelta(days=int(rng.integers(0, 6)))).isoformat() if status == "Paid" else None
            else:
                status, paid = "Pending", None
            rows.append(
                {
                    "payment_id": payment_id,
                    "policy_id": p.policy_id,
                    "due_date": due.isoformat(),
                    "paid_date": paid,
                    "amount": amount,
                    "payment_method": rng.choice(PAYMENT_METHODS),
                    "status": status,
                }
            )
            payment_id += 1
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 6: Claims (the cost side + the loss-ratio stories)
# ---------------------------------------------------------------------------

def _claim_date_in_term(rng, start: date, end: date) -> date:
    """Pick a loss date in the term, weighted toward winter months.

    Bounded by END_DATE (not TODAY): losses stop at the last complete month,
    so no claim lands in a partial month.
    """
    span = (min(end, END_DATE) - start).days
    if span <= 0:
        return start
    # sample a handful of candidate dates and prefer winter ones
    best = start + timedelta(days=int(rng.integers(0, span + 1)))
    for _ in range(2):
        cand = start + timedelta(days=int(rng.integers(0, span + 1)))
        if cand.month in WINTER_MONTHS and best.month not in WINTER_MONTHS:
            best = cand
    return best


def generate_claims(rng: np.random.Generator, policies: pd.DataFrame) -> pd.DataFrame:
    rows = []
    claim_id = 1
    type_weights = np.array(CLAIM_TYPE_WEIGHTS, dtype=float)

    for p in policies.itertuples():
        start = date.fromisoformat(p.start_date)
        end = date.fromisoformat(p.end_date)
        # Exposure stops at END_DATE, not TODAY: time on risk in a partial
        # month would earn claims into a month the dataset doesn't cover.
        active_end = min(end, END_DATE)
        if active_end <= start:
            continue
        term_years = (active_end - start).days / 365.0

        # Expected claim count for this term from the multipliers.
        lam = (
            BASE_CLAIM_FREQUENCY
            * COVERAGE_FREQ_MULT[p.hlp_coverage]
            * REGION_FREQ_MULT[p.hlp_region]
            * _age_freq_mult(p.hlp_age)
            * term_years
        )
        n_claims = int(rng.poisson(lam))

        # Jan-2026 weather event: extra Weather claims for North policies that
        # were in force that month.
        event_claims = 0
        if (
            p.hlp_region == EVENT_REGION
            and start <= EVENT_MONTH
            and end > EVENT_MONTH
            and EVENT_MONTH <= END_DATE
        ):
            event_claims = int(rng.poisson(EVENT_EXTRA_WEATHER_LAMBDA))

        # June-2026 heatwave: the second, smaller event -- extra Weather/Fire
        # claims for South policies in force that month.
        heatwave_claims = 0
        if (
            p.hlp_region == HEATWAVE_REGION
            and start <= HEATWAVE_MONTH
            and end > HEATWAVE_MONTH
            and HEATWAVE_MONTH <= END_DATE
            and p.hlp_coverage in HEATWAVE_COVERED_TYPES
        ):
            heatwave_claims = int(rng.poisson(HEATWAVE_EXTRA_LAMBDA))

        for k in range(n_claims + event_claims + heatwave_claims):
            is_event = n_claims <= k < n_claims + event_claims
            is_heatwave = k >= n_claims + event_claims
            if is_heatwave:
                # TPFT covers fire but not own-vehicle weather damage.
                if p.hlp_coverage == "TPFT":
                    claim_type = "Fire"
                else:
                    claim_type = rng.choice(HEATWAVE_CLAIM_TYPES, p=HEATWAVE_TYPE_WEIGHTS)
                claim_date = date(2026, 6, int(rng.integers(1, 31)))  # June has 30 days
            elif is_event:
                claim_type = "Weather"
                claim_date = date(2026, 1, int(rng.integers(1, 29)))
            else:
                # Winter tilts the mix toward Collision/Weather; North toward Theft.
                w = type_weights.copy()
                claim_date = _claim_date_in_term(rng, start, end)
                if claim_date.month in WINTER_MONTHS:
                    w[CLAIM_TYPES.index("Collision")] *= 1.4
                    w[CLAIM_TYPES.index("Weather")] *= 1.8
                if p.hlp_region == "North":
                    w[CLAIM_TYPES.index("Theft")] *= 1.5
                    w[CLAIM_TYPES.index("Weather")] *= 1.3
                w = w / w.sum()
                claim_type = rng.choice(CLAIM_TYPES, p=w)

            severity = lognormal_amount(rng, CLAIM_SEVERITY_MEAN[claim_type])
            severity = round(severity * REGION_SEVERITY_MULT[p.hlp_region], 2)

            # status: most settled; some recent ones open; a few rejected.
            report = claim_date + timedelta(days=int(rng.integers(0, 14)))
            roll = rng.random()
            if roll < 0.08:
                status, paid, settle = "Rejected", 0.0, None
            elif roll < 0.20 and claim_date > TODAY - timedelta(days=45):
                status, paid, settle = rng.choice(["Open", "In Review"]), 0.0, None
            else:
                status = "Paid"
                paid = severity
                settle = (report + timedelta(days=int(rng.integers(5, 60)))).isoformat()

            rows.append(
                {
                    "claim_id": claim_id,
                    "claim_number": f"CLM-{claim_id:06d}",
                    "policy_id": p.policy_id,
                    "vehicle_id": p.vehicle_id,
                    "claim_date": claim_date.isoformat(),
                    "report_date": report.isoformat(),
                    "claim_type": claim_type,
                    "status": status,
                    "claim_amount": severity,
                    "paid_amount": paid,
                    "settlement_date": settle,
                    "at_fault": bool(rng.random() < AT_FAULT_PROB[claim_type]),
                    "fraud_flag": bool(rng.random() < (0.04 if claim_type == "Theft" else 0.01)),
                    "incident_region": p.hlp_region,
                }
            )
            claim_id += 1
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    rng = np.random.default_rng(SEED)
    fake = Faker()
    Faker.seed(SEED)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Generating products (coverage tiers)...")
    products = generate_products()

    print("Generating agents...")
    agents = generate_agents(rng, fake)

    print(f"Generating {N_POLICYHOLDERS:,} policyholders, vehicles, drivers...")
    policyholders, vehicles, drivers = generate_policyholders_vehicles_drivers(rng, fake, agents)

    print("Generating policies (renewal chains)...")
    policies = generate_policies(rng, policyholders, products)

    print("Generating premium payments...")
    payments = generate_premium_payments(rng, policies)

    print("Generating claims...")
    claims = generate_claims(rng, policies)

    # Drop helper columns before saving.
    policyholders = policyholders.drop(
        columns=["hlp_agent_id", "hlp_region", "hlp_primary_driver_id", "hlp_primary_age"]
    )
    policies_save = policies.drop(columns=["hlp_coverage", "hlp_region", "hlp_age", "hlp_cancelled"])

    # Nullable integer columns -> Int64 so CSV writes "1" not "1.0".
    policies_save["previous_policy_id"] = policies_save["previous_policy_id"].astype("Int64")

    print("Writing CSV files to", OUTPUT_DIR)
    products.to_csv(os.path.join(OUTPUT_DIR, "products.csv"), index=False)
    agents.to_csv(os.path.join(OUTPUT_DIR, "agents.csv"), index=False)
    policyholders.to_csv(os.path.join(OUTPUT_DIR, "policyholders.csv"), index=False)
    vehicles.to_csv(os.path.join(OUTPUT_DIR, "vehicles.csv"), index=False)
    drivers.to_csv(os.path.join(OUTPUT_DIR, "drivers.csv"), index=False)
    policies_save.to_csv(os.path.join(OUTPUT_DIR, "policies.csv"), index=False)
    payments.to_csv(os.path.join(OUTPUT_DIR, "premium_payments.csv"), index=False)
    claims.to_csv(os.path.join(OUTPUT_DIR, "claims.csv"), index=False)

    # --- ground-truth summary ---
    settled = claims[claims["status"].isin(["Paid", "Approved", "Closed"])]
    written = policies_save["annual_premium"].sum()
    incurred = settled["paid_amount"].sum()
    overall_lr = 100.0 * incurred / written if written else 0.0

    print("\nDone.")
    print(f"  products:          {len(products):,}")
    print(f"  agents:            {len(agents):,}")
    print(f"  policyholders:     {len(policyholders):,}")
    print(f"  vehicles:          {len(vehicles):,}")
    print(f"  drivers:           {len(drivers):,}")
    print(f"  policies:          {len(policies_save):,}")
    print(f"  premium_payments:  {len(payments):,}")
    print(f"  claims:            {len(claims):,}")
    print(f"\n  written premium:   {written:,.0f}")
    print(f"  incurred claims:   {incurred:,.0f}")
    print(f"  overall loss ratio (vs written): {overall_lr:.1f}%")

    print("\nBusiness stories injected:")
    print("  ✓ Claims seasonality (winter Dec-Feb higher frequency)")
    print("  ✓ Loss-ratio spike Jan 2026 (North region weather event)")
    print("  ✓ Heatwave Jun 2026 (South region, Weather/Fire -- smaller than Jan)")
    print("  ✓ Rate action Jun 2026 (+5% on renewals, retention dip in that cohort)")
    print("  ✓ Young drivers (<25) higher claim frequency")
    print("  ✓ Comprehensive least profitable; Liability most profitable")
    print("  ✓ Retention by channel (Tied Agent best, Direct-Online worst)")
    print("  ✓ Severity tail (Theft / total-loss claims dominate cost)")


if __name__ == "__main__":
    main()
