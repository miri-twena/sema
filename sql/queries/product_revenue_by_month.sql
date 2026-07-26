-- Revenue per product per month, completed orders only, for the trailing 70
-- days (covers "this month" and "last month" for the top-seller ranking).
-- Used for: the home dashboard's Daily Brief (product_rank_shift insight --
-- a product entering the top 3 sellers this month that wasn't there last month).
SELECT
    DATE_TRUNC('month', o.order_date)::date AS month,
    p.product_id,
    p.product_name,
    ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
JOIN products p ON p.product_id = oi.product_id
WHERE o.order_date >= (
      SELECT MAX(order_date) FROM orders WHERE status = 'completed'
  ) - INTERVAL '70 days'
GROUP BY 1, 2, 3
ORDER BY 1, 4 DESC;
