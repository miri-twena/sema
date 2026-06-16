-- Monthly website-session counts for customers identified as "at risk"
-- (no completed order in the last 90 days, see at_risk_customers.sql).
-- Used to show that this group's site activity has been declining --
-- supports "Which customers are at risk?".
WITH bounds AS (
    SELECT MAX(order_date) AS max_order_date
    FROM orders
    WHERE status = 'completed'
),
at_risk AS (
    SELECT customer_id
    FROM orders
    WHERE status = 'completed'
    GROUP BY customer_id
    HAVING MAX(order_date) <= (SELECT max_order_date - INTERVAL '90 days' FROM bounds)
)
SELECT
    DATE_TRUNC('month', ws.session_start)::date AS month,
    COUNT(*) AS session_count
FROM website_sessions ws
JOIN at_risk ar ON ar.customer_id = ws.customer_id
GROUP BY 1
ORDER BY 1;
