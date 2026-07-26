-- Revenue and order count per calendar day, completed orders only, for the
-- trailing 70 days relative to the newest order date in the data (not the
-- wall clock -- the same convention data_bounds.sql / at_risk_customers.sql
-- use for "now"). 70 days covers the Daily Brief's two lookbacks cheaply:
--   - month-to-date pace needs up to ~31 days of the current month plus up
--     to ~31 days of the previous month (worst case: day 31 of a 31-day month);
--   - the yesterday-vs-typical-weekday check needs the trailing 28 days.
-- Used for: the home dashboard's Daily Brief (MTD pace, yesterday anomaly).
SELECT
    order_date::date AS day,
    COUNT(*) AS order_count,
    ROUND(SUM(total_amount), 2) AS revenue
FROM orders
WHERE status = 'completed'
  AND order_date >= (
      SELECT MAX(order_date) FROM orders WHERE status = 'completed'
  ) - INTERVAL '70 days'
GROUP BY 1
ORDER BY 1;
