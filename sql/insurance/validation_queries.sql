-- SEMA: validation queries -- INSURANCE client.
--
-- Run these after loading data (data/insurance/load_data.py) to sanity-check
-- the dataset, the same way sql/validation_queries.sql does for ecommerce.
-- Run them with psql, a DB GUI (DBeaver, pgAdmin, etc.), or VS Code's
-- PostgreSQL extension -- against the insurance_db database.
--
-- Expected values live in the module docstring of
-- data/insurance/generate_data.py, which is the answer key for this dataset.


-- 1. Range guard: losses must stop at the last COMPLETE month (2026-06-30).
-- The generator deliberately separates END_DATE (the loss ceiling) from TODAY
-- (the status reference, 2026-07-16). A claim dated into a half-finished July
-- would drag that month's loss ratio down and poison every MoM comparison.
-- Expect: max_claim = 2026-06-30, and zero July claims.
SELECT
    MIN(claim_date) AS first_claim,
    MAX(claim_date) AS last_claim,
    COUNT(*) FILTER (WHERE claim_date >= '2026-07-01') AS july_claims_must_be_zero
FROM claims;


-- 2. Loss ratio by month -- the two catastrophe events should stand out.
-- Expect: a large Jan-2026 spike (the North storm) and a smaller but clear
-- Jun-2026 bump (the South heatwave), against a quiet baseline.
SELECT
    DATE_TRUNC('month', claim_date)::date AS month,
    COUNT(*) AS claims,
    ROUND(SUM(paid_amount), 0) AS incurred
FROM claims
WHERE claim_date >= '2025-10-01'
GROUP BY 1
ORDER BY 1;


-- 3. The two events side by side -- "compare the two events" is a real
-- question, so they differ in region, size AND character.
-- Expect: Jan = ~440 high-frequency Weather claims (~$1.5M) in the North;
-- Jun = ~55 claims (~$0.5M, roughly a third of Jan) in the South, dominated
-- by a few high-severity Fire losses.
SELECT
    CASE WHEN claim_date < '2026-02-01' THEN 'Jan 2026 North storm'
         ELSE 'Jun 2026 South heatwave' END AS event,
    claim_type,
    COUNT(*) AS claims,
    ROUND(SUM(paid_amount), 0) AS incurred,
    ROUND(AVG(paid_amount), 0) AS avg_severity
FROM claims
WHERE (claim_date >= '2026-01-01' AND claim_date < '2026-02-01'
       AND incident_region = 'North' AND claim_type = 'Weather')
   OR (claim_date >= '2026-06-01' AND claim_date < '2026-07-01'
       AND incident_region = 'South' AND claim_type IN ('Weather', 'Fire'))
GROUP BY 1, 2
ORDER BY 1, 2;


-- 4. The heatwave against the South's own baseline -- the spike should be
-- unmistakable rather than a rounding artefact.
-- Expect: a handful of claims a month, then ~57 in June 2026.
SELECT
    DATE_TRUNC('month', claim_date)::date AS month,
    COUNT(*) AS claims,
    ROUND(SUM(paid_amount), 0) AS incurred
FROM claims
WHERE incident_region = 'South' AND claim_date >= '2026-01-01'
GROUP BY 1
ORDER BY 1;


-- 5. Rate action: renewals written from 2026-06-01 carry ~+5%.
-- Compare June against the Jan-May average (~$1,014) rather than against May
-- alone -- single months are noisy at these cohort sizes.
-- Expect: June ~$1,067, i.e. ~+5% on the Jan-May average.
SELECT
    DATE_TRUNC('month', start_date)::date AS inception_month,
    COUNT(*) AS renewals,
    ROUND(AVG(annual_premium), 2) AS avg_premium
FROM policies
WHERE business_type = 'Renewal' AND start_date >= '2026-01-01'
GROUP BY 1
ORDER BY 1;


-- 6. Rate action: what the increase COST in retention.
-- Expect: the cohort whose term expired on/after 2026-06-01 renews a few
-- points worse than the baseline cohort (~77.5% vs ~81.5%).
SELECT
    CASE WHEN end_date >= '2026-06-01' THEN 'expired on/after 2026-06-01 (rate action)'
         ELSE 'expired before 2026-06-01 (baseline)' END AS cohort,
    COUNT(*) AS terms,
    SUM(CASE WHEN status = 'Renewed' THEN 1 ELSE 0 END) AS renewed,
    ROUND(100.0 * SUM(CASE WHEN status = 'Renewed' THEN 1 ELSE 0 END) / COUNT(*), 1)
        AS renewal_rate_pct
FROM policies
WHERE status IN ('Renewed', 'Lapsed') AND end_date >= '2025-06-01'
GROUP BY 1
ORDER BY 1 DESC;


-- 7. Existing story: Comprehensive is the LEAST profitable tier.
-- This one is load-bearing and fragile: any catastrophe that lands
-- per-policy but coverage-blind compresses this ordering, because premium is
-- concentrated in Comprehensive (61% of premium on 45% of policies). The
-- June heatwave is therefore restricted to policies that actually cover
-- own-vehicle damage (see HEATWAVE_COVERED_TYPES).
-- Expect: Comprehensive (~89%) > TPFT (~84%) > Liability (~68%).
SELECT
    pr.coverage_type,
    ROUND(SUM(p.annual_premium), 0) AS written,
    ROUND(COALESCE(SUM(c.paid), 0), 0) AS incurred,
    ROUND(100.0 * COALESCE(SUM(c.paid), 0) / NULLIF(SUM(p.annual_premium), 0), 1)
        AS loss_ratio_pct
FROM policies p
JOIN products pr ON pr.product_id = p.product_id
LEFT JOIN (
    SELECT policy_id, SUM(paid_amount) AS paid FROM claims GROUP BY 1
) c ON c.policy_id = p.policy_id
GROUP BY 1
ORDER BY loss_ratio_pct DESC;


-- 8. Existing story: retention by channel.
-- Expect: Tied Agent (~88%) > Broker (~82%) > Direct-Online (~63%).
SELECT
    a.channel,
    COUNT(*) AS terms,
    ROUND(100.0 * SUM(CASE WHEN p.status = 'Renewed' THEN 1 ELSE 0 END) / COUNT(*), 1)
        AS renewal_rate_pct
FROM policies p
JOIN agents a ON a.agent_id = p.agent_id
WHERE p.status IN ('Renewed', 'Lapsed')
GROUP BY 1
ORDER BY renewal_rate_pct DESC;


-- 9. Existing story: young drivers (<25) claim far more often.
SELECT
    CASE WHEN EXTRACT(YEAR FROM AGE(DATE '2026-07-16', d.date_of_birth)) < 25
         THEN 'under 25' ELSE '25 and over' END AS age_band,
    COUNT(DISTINCT p.policy_id) AS policies,
    COUNT(c.claim_id) AS claims,
    ROUND(1.0 * COUNT(c.claim_id) / NULLIF(COUNT(DISTINCT p.policy_id), 0), 3)
        AS claims_per_policy
FROM policies p
JOIN drivers d ON d.driver_id = p.primary_driver_id
LEFT JOIN claims c ON c.policy_id = p.policy_id
GROUP BY 1
ORDER BY claims_per_policy DESC;
