-- Campaign spend vs. attributed revenue (same ROAS math as
-- campaign_performance.sql), plus each campaign's date range and days-active
-- so the Daily Brief can flag a campaign that has been running at a loss for
-- a while. Note: spend is a single lump sum for the campaign's whole run --
-- there is no daily spend column -- so "days active" describes the
-- campaign's own duration, not a literal derivative of a daily spend curve.
-- Used for: the home dashboard's Daily Brief (campaign_negative_roi insight).
SELECT
    c.campaign_id,
    c.campaign_name,
    c.channel,
    c.start_date::date AS start_date,
    c.end_date::date AS end_date,
    c.spend,
    ROUND(COALESCE(SUM(o.total_amount), 0), 2) AS attributed_revenue,
    ROUND(COALESCE(SUM(o.total_amount), 0) / NULLIF(c.spend, 0), 2) AS roas,
    (
        (SELECT MAX(order_date) FROM orders WHERE status = 'completed')::date
        - c.start_date::date
    ) AS days_active,
    (
        c.end_date IS NULL
        OR c.end_date >= (SELECT MAX(order_date) FROM orders WHERE status = 'completed')
    ) AS is_active
FROM marketing_campaigns c
LEFT JOIN orders o
    ON o.campaign_id = c.campaign_id AND o.status = 'completed'
GROUP BY c.campaign_id, c.campaign_name, c.channel, c.start_date, c.end_date, c.spend
ORDER BY roas ASC NULLS LAST;
