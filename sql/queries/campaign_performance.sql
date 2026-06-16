-- Marketing campaign performance: spend vs. attributed revenue/orders, and
-- a simple ROAS (return on ad spend = attributed revenue / spend).
-- Used for: "Which campaign performs best?" and the March 2026 dip story
-- (the "Meta Retarget - Electronics" campaign should show poor ROAS).
SELECT
    c.campaign_name,
    c.channel,
    c.spend,
    ROUND(COALESCE(SUM(o.total_amount), 0), 2) AS attributed_revenue,
    COUNT(o.order_id) AS attributed_orders,
    ROUND(COALESCE(SUM(o.total_amount), 0) / NULLIF(c.spend, 0), 2) AS roas
FROM marketing_campaigns c
LEFT JOIN orders o
    ON o.campaign_id = c.campaign_id AND o.status = 'completed'
GROUP BY c.campaign_id, c.campaign_name, c.channel, c.spend
ORDER BY roas DESC NULLS LAST;
