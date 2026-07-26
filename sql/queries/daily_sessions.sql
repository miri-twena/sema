-- Website sessions and conversions per calendar day, for the trailing 70 days
-- relative to the newest COMPLETED order date (the same "now" convention
-- daily_orders.sql / data_bounds.sql use) -- not session_start's own max,
-- so the pulse's conversion metric lines up with the same day boundaries as
-- revenue/orders.
-- Used for: the home dashboard's Daily Brief (conversion rate pulse tile).
SELECT
    session_start::date AS day,
    COUNT(*) AS session_count,
    SUM(CASE WHEN converted THEN 1 ELSE 0 END) AS converted_count
FROM website_sessions
WHERE session_start::date >= (
      SELECT MAX(order_date) FROM orders WHERE status = 'completed'
  )::date - INTERVAL '70 days'
GROUP BY 1
ORDER BY 1;
