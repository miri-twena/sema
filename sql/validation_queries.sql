-- SEMA: validation queries.
--
-- Run these after loading data (data/load_data.py) to sanity-check the
-- dataset -- the same way you'd spot-check numbers after a Power BI model
-- refresh. Run them with psql, a DB GUI (DBeaver, pgAdmin, etc.), or
-- VS Code's PostgreSQL extension.


-- 1. Total revenue (completed orders only)
-- Expect: a single number in the low millions, given 20,000 orders with
-- typical order values of tens to a few hundred dollars.
SELECT
    ROUND(SUM(total_amount), 2) AS total_revenue
FROM orders
WHERE status = 'completed';


-- 2. Orders by month
-- Expect: ~12 rows, one per month. Nov/Dec should be noticeably higher
-- (holiday seasonality), and February should be the lowest month -- the
-- intentional revenue dip baked in by data/generate_data.py.
SELECT
    DATE_TRUNC('month', order_date)::date AS month,
    COUNT(*) AS order_count,
    ROUND(SUM(total_amount), 2) AS revenue
FROM orders
WHERE status = 'completed'
GROUP BY 1
ORDER BY 1;


-- 3. Revenue by category
-- Expect: 6 rows (one per category). "Accessories" should show a visible
-- dip if you filter to February specifically (see query 3b).
SELECT
    p.category,
    ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue,
    SUM(oi.quantity) AS units_sold
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
WHERE o.status = 'completed'
GROUP BY p.category
ORDER BY revenue DESC;

-- 3b. Revenue by category, February only (to see the Accessories dip)
SELECT
    p.category,
    ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
WHERE o.status = 'completed'
  AND DATE_TRUNC('month', o.order_date) = '2026-02-01'
GROUP BY p.category
ORDER BY revenue DESC;


-- 4. Customers by segment
-- Expect: 3 rows (New, Returning, VIP). VIP should be roughly 10% of
-- customers (by construction -- see assign_customer_segments in
-- data/generate_data.py).
SELECT
    segment,
    COUNT(*) AS customer_count
FROM customers
GROUP BY segment
ORDER BY customer_count DESC;


-- 5. Sessions by traffic source
-- Expect: 6 rows. Each source's conversion rate (converted sessions /
-- total sessions) should roughly match the targets in
-- data/generate_data.py's CONVERSION_RATES (e.g. Organic ~15%, Meta ~6%).
SELECT
    traffic_source,
    COUNT(*) AS session_count,
    SUM(CASE WHEN converted THEN 1 ELSE 0 END) AS converted_sessions,
    ROUND(
        100.0 * SUM(CASE WHEN converted THEN 1 ELSE 0 END) / COUNT(*), 2
    ) AS conversion_rate_pct
FROM website_sessions
GROUP BY traffic_source
ORDER BY session_count DESC;


-- Bonus: campaign performance (revenue vs. spend), to spot-check the
-- "Meta Retarget - Accessories" dip campaign's poor ROI.
SELECT
    c.campaign_name,
    c.channel,
    c.spend,
    ROUND(COALESCE(SUM(o.total_amount), 0), 2) AS attributed_revenue,
    COUNT(o.order_id) AS attributed_orders
FROM marketing_campaigns c
LEFT JOIN orders o
    ON o.campaign_id = c.campaign_id AND o.status = 'completed'
GROUP BY c.campaign_id, c.campaign_name, c.channel, c.spend
ORDER BY c.spend DESC;


-- ===========================================================================
-- June 2026 scenarios (added with the 13-month extension)
-- Each query below prints the numbers that PROVE one injected story exists.
-- Expected values are in data/README.md sections 5-7 -- if these drift, the
-- docs are the answer key, so fix whichever is actually wrong.
-- ===========================================================================


-- 10. Summer Sale: orders up, revenue barely up, AOV down ("bought growth")
-- Expect: June orders ~+30% vs May, revenue only ~+4%, AOV ~-20%, and the
-- share of discounted orders jumping from ~14% to ~46%.
SELECT
    DATE_TRUNC('month', order_date)::date AS month,
    COUNT(*) AS orders,
    ROUND(SUM(total_amount), 2) AS revenue,
    ROUND(AVG(total_amount), 2) AS aov,
    ROUND(100.0 * AVG(CASE WHEN discount_amount > 0 THEN 1 ELSE 0 END), 1) AS pct_discounted
FROM orders
WHERE status = 'completed' AND order_date >= '2026-04-01'
GROUP BY 1
ORDER BY 1;


-- 11. Summer Sale campaign ROI: mediocre, NOT the worst.
-- Expect: "Summer Sale 2026" around ROAS ~11 -- below the ~20-30 median but
-- above the weakest campaigns. If it ever becomes the worst, the
-- worst_campaign golden eval is measuring the wrong thing.
SELECT
    c.campaign_name,
    c.channel,
    c.spend,
    ROUND(COALESCE(SUM(o.total_amount), 0), 2) AS attributed_revenue,
    ROUND(COALESCE(SUM(o.total_amount), 0) / NULLIF(c.spend, 0), 2) AS roas
FROM marketing_campaigns c
LEFT JOIN orders o
    ON o.campaign_id = c.campaign_id AND o.status = 'completed'
GROUP BY c.campaign_id, c.campaign_name, c.channel, c.spend
ORDER BY roas ASC;


-- 12. Electronics price increase: price up, units down, revenue flat.
-- Expect: avg unit price +4% (mix-diluted; the list price rose 7%), units
-- -6%, revenue ~-2% -- while every OTHER category grew on the sale.
SELECT
    DATE_TRUNC('month', o.order_date)::date AS month,
    ROUND(AVG(oi.unit_price), 2) AS avg_unit_price,
    SUM(oi.quantity) AS units,
    ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
WHERE o.status = 'completed'
  AND p.category = 'Electronics'
  AND o.order_date >= '2026-04-01'
GROUP BY 1
ORDER BY 1;


-- 12b. The contrast that makes 12 a story: Electronics flat while the rest
-- of the catalogue grew on the sale. Expect Electronics to be the only
-- negative row.
SELECT
    p.category,
    ROUND(SUM(CASE WHEN o.order_date >= '2026-05-01' AND o.order_date < '2026-06-01'
              THEN oi.quantity * oi.unit_price END), 2) AS may_revenue,
    ROUND(SUM(CASE WHEN o.order_date >= '2026-06-01' AND o.order_date < '2026-07-01'
              THEN oi.quantity * oi.unit_price END), 2) AS jun_revenue
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
WHERE o.status = 'completed'
GROUP BY 1
ORDER BY 1;


-- 13. Email conversion lift: Email becomes the best-converting channel in
-- June 2026 (it is normally 3rd, behind Direct and Organic).
-- Expect: Email ~29.7% in June vs ~14.8% in May; Direct 2nd in June.
SELECT
    DATE_TRUNC('month', session_start)::date AS month,
    traffic_source,
    COUNT(*) AS sessions,
    ROUND(100.0 * SUM(CASE WHEN converted THEN 1 ELSE 0 END) / COUNT(*), 2) AS cvr_pct
FROM website_sessions
WHERE session_start >= '2026-05-01'
GROUP BY 1, 2
ORDER BY 1, cvr_pct DESC;


-- 14. Range guard: the data must end on a COMPLETE month (2026-06-30) --
-- never a partial July, which would poison every MoM comparison.
SELECT
    MIN(order_date)::date AS first_order,
    MAX(order_date)::date AS last_order
FROM orders
WHERE status = 'completed';
