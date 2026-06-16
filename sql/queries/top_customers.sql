-- Top 10 customers by lifetime completed revenue, with segment, channel,
-- and order behavior. Used for: "Who are our most valuable customers?".
SELECT
    c.customer_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    c.segment,
    c.acquisition_channel,
    c.country,
    COUNT(o.order_id) AS order_count,
    ROUND(SUM(o.total_amount), 2) AS lifetime_revenue,
    ROUND(AVG(o.total_amount), 2) AS avg_order_value
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id AND o.status = 'completed'
GROUP BY c.customer_id, c.first_name, c.last_name, c.segment, c.acquisition_channel, c.country
ORDER BY lifetime_revenue DESC
LIMIT 10;
