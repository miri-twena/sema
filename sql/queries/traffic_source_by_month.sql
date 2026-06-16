-- Orders and revenue per traffic source, per month, completed orders only.
-- Used for: drilling into the March 2026 revenue dip (Meta underperformance).
SELECT
    DATE_TRUNC('month', order_date)::date AS month,
    traffic_source,
    COUNT(*) AS order_count,
    ROUND(SUM(total_amount), 2) AS revenue
FROM orders
WHERE status = 'completed'
GROUP BY 1, 2
ORDER BY 1, 2;
