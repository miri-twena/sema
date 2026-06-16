-- Customers who placed at least one completed order in the past, but none
-- in the last 90 days relative to the most recent order date in the
-- dataset (2026-05-31 -- the synthetic "today"). Includes lifetime revenue
-- and AOV so we can prioritize win-back outreach.
-- Used for: "Which customers are at risk?" / "Show inactive customers".
WITH bounds AS (
    SELECT MAX(order_date) AS max_order_date
    FROM orders
    WHERE status = 'completed'
),
customer_orders AS (
    SELECT
        customer_id,
        MAX(order_date) AS last_order_date,
        COUNT(*) AS order_count,
        ROUND(SUM(total_amount), 2) AS lifetime_revenue,
        ROUND(AVG(total_amount), 2) AS avg_order_value
    FROM orders
    WHERE status = 'completed'
    GROUP BY customer_id
)
SELECT
    co.customer_id,
    cu.first_name || ' ' || cu.last_name AS customer_name,
    cu.segment,
    cu.acquisition_channel,
    co.last_order_date::date AS last_order_date,
    (bounds.max_order_date::date - co.last_order_date::date) AS days_inactive,
    co.order_count,
    co.lifetime_revenue,
    co.avg_order_value
FROM customer_orders co
JOIN customers cu ON cu.customer_id = co.customer_id
CROSS JOIN bounds
WHERE co.last_order_date <= (bounds.max_order_date - INTERVAL '90 days')
ORDER BY co.lifetime_revenue DESC;
