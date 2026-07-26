-- VIP customers (customers.segment = 'VIP' -- the semantic layer's primary
-- VIP definition, see sql/semantic/vip_customers.yaml) with no completed
-- order in 60+ days, plus their TRAILING-12-MONTH revenue (not lifetime), so
-- the Daily Brief can size how much recent value is going quiet. "60+ days"
-- and "12 months" are both anchored to the dataset's newest completed order
-- date, the same convention churn_risk.yaml's 90-day window uses.
-- Used for: the home dashboard's Daily Brief (vip_inactive insight).
WITH bounds AS (
    SELECT MAX(order_date) AS max_order_date FROM orders WHERE status = 'completed'
),
vip_last_order AS (
    SELECT o.customer_id, MAX(o.order_date) AS last_order_date
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.status = 'completed' AND c.segment = 'VIP'
    GROUP BY o.customer_id
),
trailing_12mo AS (
    SELECT o.customer_id, SUM(o.total_amount) AS revenue_12mo
    FROM orders o, bounds
    WHERE o.status = 'completed' AND o.order_date >= bounds.max_order_date - INTERVAL '365 days'
    GROUP BY o.customer_id
)
SELECT
    vlo.customer_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    vlo.last_order_date::date AS last_order_date,
    (bounds.max_order_date::date - vlo.last_order_date::date) AS days_inactive,
    ROUND(COALESCE(t.revenue_12mo, 0), 2) AS revenue_12mo
FROM vip_last_order vlo
JOIN customers c ON c.customer_id = vlo.customer_id
CROSS JOIN bounds
LEFT JOIN trailing_12mo t ON t.customer_id = vlo.customer_id
WHERE vlo.last_order_date <= bounds.max_order_date - INTERVAL '60 days'
ORDER BY days_inactive DESC;
