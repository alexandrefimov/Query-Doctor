WITH base AS (
  SELECT order_id, key_1, key_2, key_3, key_4, key_5, key_6, key_7, key_8, key_9, key_10, key_11, ds
  FROM example_analytics.fact_orders
  WHERE ds = 20260507
)
SELECT base.order_id
FROM base
JOIN example_analytics.dim_1 d1 ON base.key_1 = d1.key_1
JOIN example_analytics.dim_2 d2 ON base.key_2 = d2.key_2
JOIN example_analytics.dim_3 d3 ON base.key_3 = d3.key_3
JOIN example_analytics.dim_4 d4 ON base.key_4 = d4.key_4
JOIN example_analytics.dim_5 d5 ON base.key_5 = d5.key_5
JOIN example_analytics.dim_6 d6 ON base.key_6 = d6.key_6
JOIN example_analytics.dim_7 d7 ON base.key_7 = d7.key_7
JOIN example_analytics.dim_8 d8 ON base.key_8 = d8.key_8
JOIN example_analytics.dim_9 d9 ON base.key_9 = d9.key_9
JOIN example_analytics.dim_10 d10 ON base.key_10 = d10.key_10
JOIN example_analytics.dim_11 d11 ON base.key_11 = d11.key_11
WHERE base.ds = 20260507
