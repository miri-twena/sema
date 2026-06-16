-- Total revenue and order count per month, completed orders only.
-- Used for: "Show revenue trend by month" and as context for the
-- March 2026 revenue-dip story.
SELECT
    DATE_TRUNC('month', order_date)::date AS month,
    COUNT(*) AS order_count,
    ROUND(SUM(total_amount), 2) AS revenue
FROM orders
WHERE status = 'completed'
GROUP BY 1
ORDER BY 1;
