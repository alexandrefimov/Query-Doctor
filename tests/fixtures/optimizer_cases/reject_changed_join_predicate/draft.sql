SELECT f.order_id, d.user_segment, f.amount
FROM example_analytics.fact_orders f
JOIN example_analytics.dim_users d ON f.account_id = d.user_id
WHERE f.ds BETWEEN 20260501 AND 20260507;
