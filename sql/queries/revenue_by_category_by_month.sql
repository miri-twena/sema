-- Revenue per product category, per month, completed orders only.
-- Used for: drilling into the March 2026 revenue dip (Electronics decline).
SELECT
    DATE_TRUNC('month', o.order_date)::date AS month,
    p.category,
    ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
WHERE o.status = 'completed'
GROUP BY 1, 2
ORDER BY 1, 2;
