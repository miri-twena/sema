-- ============================================================================
-- SEMA client schema: AUTO INSURANCE company
-- ============================================================================
-- A parallel dataset to the ecommerce demo (sql/schema.sql), modelling a
-- motor (auto) insurance carrier. It is NOT loaded by the current app, which
-- is wired to the ecommerce DB -- it's the data model for a second client.
--
-- Shape: a small star schema.
--   Dimensions : policyholders, agents, products, vehicles, drivers
--   Facts      : policies (the contract + written premium),
--                premium_payments (billing / cash collected),
--                claims (the cost side / incurred losses)
--
-- The whole profitability story in insurance is the tension between PREMIUM
-- (what the customer pays -> policies/premium_payments) and CLAIMS (what the
-- carrier pays out -> claims). The semantic layer in sql/insurance/semantic/
-- defines the KPIs (Loss Ratio, Claims Frequency/Severity, Retention, ...)
-- on top of these tables.
--
-- Re-runnable: drops and recreates every table.
-- ============================================================================

DROP TABLE IF EXISTS claims CASCADE;
DROP TABLE IF EXISTS premium_payments CASCADE;
DROP TABLE IF EXISTS policies CASCADE;
DROP TABLE IF EXISTS drivers CASCADE;
DROP TABLE IF EXISTS vehicles CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS agents CASCADE;
DROP TABLE IF EXISTS policyholders CASCADE;

-- ---------------------------------------------------------------------------
-- DIMENSION: policyholders -- the customer / account that owns the policy
-- ---------------------------------------------------------------------------
CREATE TABLE policyholders (
    policyholder_id     SERIAL PRIMARY KEY,
    first_name          TEXT        NOT NULL,
    last_name           TEXT        NOT NULL,
    date_of_birth       DATE        NOT NULL,        -- drives age-band analysis
    gender              TEXT,                        -- 'M' / 'F' / 'Other'
    email               TEXT,
    phone               TEXT,
    city                TEXT,
    region              TEXT,                        -- district / state
    postal_code         TEXT,
    marital_status      TEXT,                        -- Single / Married / ...
    customer_since      DATE        NOT NULL,        -- first-ever policy date
    acquisition_channel TEXT,                        -- Agent / Online / Aggregator / Broker / Referral
    credit_band         TEXT                         -- A / B / C / D (risk proxy)
);

-- ---------------------------------------------------------------------------
-- DIMENSION: agents -- who sold / services the policy
-- ---------------------------------------------------------------------------
CREATE TABLE agents (
    agent_id    SERIAL PRIMARY KEY,
    agent_name  TEXT NOT NULL,
    agency_name TEXT,
    region      TEXT,
    channel     TEXT,                                -- Tied Agent / Broker / Direct-Online
    hire_date   DATE
);

-- ---------------------------------------------------------------------------
-- DIMENSION: products -- the coverage tier offered (auto only)
-- ---------------------------------------------------------------------------
CREATE TABLE products (
    product_id          SERIAL PRIMARY KEY,
    product_name        TEXT NOT NULL,
    coverage_type       TEXT NOT NULL,               -- Liability / TPFT / Comprehensive
    base_annual_premium NUMERIC(10, 2),              -- reference price before risk loading
    description         TEXT
);

-- ---------------------------------------------------------------------------
-- DIMENSION: vehicles -- the insured car (the risk object)
-- ---------------------------------------------------------------------------
CREATE TABLE vehicles (
    vehicle_id          SERIAL PRIMARY KEY,
    policyholder_id     INT  NOT NULL REFERENCES policyholders(policyholder_id),
    make                TEXT,
    model               TEXT,
    model_year          INT,
    vehicle_category    TEXT,                        -- Sedan / SUV / Hatchback / Truck / Sports / EV
    vehicle_value       NUMERIC(12, 2),              -- market value / sum insured basis
    usage_type          TEXT,                        -- Private / Commute / Commercial / Rideshare
    annual_mileage_band TEXT,                        -- <10k / 10-20k / 20k+
    registration_region TEXT
);

-- ---------------------------------------------------------------------------
-- DIMENSION: drivers -- people covered to drive (risk is driver-driven)
-- ---------------------------------------------------------------------------
CREATE TABLE drivers (
    driver_id                SERIAL PRIMARY KEY,
    policyholder_id          INT NOT NULL REFERENCES policyholders(policyholder_id),
    first_name               TEXT,
    last_name                TEXT,
    date_of_birth            DATE,                   -- young drivers = higher risk
    gender                   TEXT,
    license_issue_date       DATE,                   -- years_licensed = experience
    is_primary               BOOLEAN DEFAULT TRUE,
    prior_at_fault_accidents INT DEFAULT 0           -- claims history at underwriting
);

-- ---------------------------------------------------------------------------
-- FACT: policies -- the contract. One row per policy term (usually 12 months).
--        annual_premium here is the WRITTEN premium (bookings).
-- ---------------------------------------------------------------------------
CREATE TABLE policies (
    policy_id           SERIAL PRIMARY KEY,
    policy_number       TEXT UNIQUE NOT NULL,
    policyholder_id     INT  NOT NULL REFERENCES policyholders(policyholder_id),
    vehicle_id          INT  NOT NULL REFERENCES vehicles(vehicle_id),
    product_id          INT  NOT NULL REFERENCES products(product_id),
    agent_id            INT  REFERENCES agents(agent_id),
    primary_driver_id   INT  REFERENCES drivers(driver_id),
    start_date          DATE NOT NULL,               -- inception / effective date
    end_date            DATE NOT NULL,               -- expiry date
    term_months         INT  NOT NULL DEFAULT 12,
    business_type       TEXT NOT NULL,               -- New Business / Renewal
    previous_policy_id  INT  REFERENCES policies(policy_id),  -- renewal chain (NULL for new)
    status              TEXT NOT NULL,               -- Active / Expired / Cancelled / Lapsed / Renewed
    annual_premium      NUMERIC(10, 2) NOT NULL,     -- WRITTEN premium for the term
    deductible          NUMERIC(10, 2),              -- policyholder's own contribution per claim
    sum_insured         NUMERIC(12, 2),              -- max coverage limit
    payment_frequency   TEXT,                        -- Annual / Monthly
    cancellation_date   DATE,                         -- NULL unless cancelled mid-term
    cancellation_reason TEXT
);

-- ---------------------------------------------------------------------------
-- FACT: premium_payments -- billing schedule & cash actually collected
-- ---------------------------------------------------------------------------
CREATE TABLE premium_payments (
    payment_id     SERIAL PRIMARY KEY,
    policy_id      INT  NOT NULL REFERENCES policies(policy_id),
    due_date       DATE NOT NULL,
    paid_date      DATE,                              -- NULL if not yet paid
    amount         NUMERIC(10, 2) NOT NULL,
    payment_method TEXT,                              -- Credit Card / Bank Transfer / Direct Debit
    status         TEXT NOT NULL                      -- Paid / Pending / Failed / Refunded
);

-- ---------------------------------------------------------------------------
-- FACT: claims -- the cost side. paid_amount is the incurred loss.
-- ---------------------------------------------------------------------------
CREATE TABLE claims (
    claim_id        SERIAL PRIMARY KEY,
    claim_number    TEXT UNIQUE NOT NULL,
    policy_id       INT  NOT NULL REFERENCES policies(policy_id),
    vehicle_id      INT  REFERENCES vehicles(vehicle_id),
    claim_date      DATE NOT NULL,                    -- date of loss / incident
    report_date     DATE,                             -- when reported (report lag)
    claim_type      TEXT,                             -- Collision / Third-Party Liability / Theft / Fire / Weather / Glass / Vandalism
    status          TEXT NOT NULL,                    -- Open / In Review / Approved / Paid / Rejected / Closed
    claim_amount    NUMERIC(12, 2),                   -- amount claimed / reserved
    paid_amount     NUMERIC(12, 2) DEFAULT 0,         -- amount actually paid (incurred loss)
    settlement_date DATE,                             -- NULL while open
    at_fault        BOOLEAN,                          -- was the insured at fault?
    fraud_flag      BOOLEAN DEFAULT FALSE,
    incident_region TEXT
);

-- ---------------------------------------------------------------------------
-- Helpful indexes for the period/dimension slicing the semantic layer does.
-- ---------------------------------------------------------------------------
CREATE INDEX idx_policies_start_date   ON policies (start_date);
CREATE INDEX idx_policies_status       ON policies (status);
CREATE INDEX idx_policies_prev         ON policies (previous_policy_id);
CREATE INDEX idx_claims_claim_date     ON claims (claim_date);
CREATE INDEX idx_claims_policy         ON claims (policy_id);
CREATE INDEX idx_payments_policy       ON premium_payments (policy_id);
