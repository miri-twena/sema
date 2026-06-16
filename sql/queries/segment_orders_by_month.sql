-- Orders and revenue per customer segment, per month, completed orders only.
-- Used for: drilling into the March 2026 revenue dip (returning-customer
-- order volume slowdown).
SELECT
    DATE_TRUNC('month', o.order_date)::date AS month,
    c.segment,
    COUNT(*) AS order_count,
    ROUND(SUM(o.total_amount), 2) AS revenue
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.status = 'completed'
GROUP BY 1, 2
ORDER BY 1, 2;
