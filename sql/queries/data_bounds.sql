-- The date range the completed-order data actually covers.
-- Used by the home dashboard to decide which months are COMPLETE: the default
-- period is the latest complete month, never one that is still in progress.
-- "Now" is the newest order date in the dataset (the same convention
-- at_risk_customers.sql and the churn_risk alerts already use), not the wall
-- clock -- so a data feed that lags never empties the dashboard.
SELECT
    MIN(order_date)::date AS min_order_date,
    MAX(order_date)::date AS max_order_date
FROM orders
WHERE status = 'completed';
