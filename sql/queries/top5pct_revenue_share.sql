-- Pareto check: what share of total revenue comes from the top 5% of
-- customers by lifetime completed revenue?
-- Used for: "Who are our most valuable customers?" and "What percentage of
-- revenue comes from the top 5% of customers?".
WITH customer_revenue AS (
    SELECT
        customer_id,
        SUM(total_amount) AS revenue
    FROM orders
    WHERE status = 'completed'
    GROUP BY customer_id
),
ranked AS (
    SELECT
        customer_id,
        revenue,
        PERCENT_RANK() OVER (ORDER BY revenue DESC) AS pct_rank
    FROM customer_revenue
)
SELECT
    (SELECT COUNT(*) FROM ranked WHERE pct_rank <= 0.05) AS top5pct_customers,
    (SELECT COUNT(*) FROM ranked) AS total_customers,
    ROUND((SELECT SUM(revenue) FROM ranked WHERE pct_rank <= 0.05), 2) AS top5pct_revenue,
    ROUND((SELECT SUM(revenue) FROM ranked), 2) AS total_revenue,
    ROUND(
        100.0 * (SELECT SUM(revenue) FROM ranked WHERE pct_rank <= 0.05)
              / (SELECT SUM(revenue) FROM ranked),
        1
    ) AS top5pct_share_pct;
