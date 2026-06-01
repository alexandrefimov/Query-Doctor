SELECT nested_orders.order_id
FROM (
  SELECT order_id, key_1, key_2, key_3, key_4, key_5, key_6, key_7, key_8, key_9, key_10, key_11, ds
  FROM example_analytics.fact_orders
  WHERE ds = 20260507
) nested_orders
JOIN example_analytics.dim_1 d1 ON nested_orders.key_1 = d1.key_1
JOIN example_analytics.dim_2 d2 ON nested_orders.key_2 = d2.key_2
JOIN example_analytics.dim_3 d3 ON nested_orders.key_3 = d3.key_3
JOIN example_analytics.dim_4 d4 ON nested_orders.key_4 = d4.key_4
JOIN example_analytics.dim_5 d5 ON nested_orders.key_5 = d5.key_5
JOIN example_analytics.dim_6 d6 ON nested_orders.key_6 = d6.key_6
JOIN example_analytics.dim_7 d7 ON nested_orders.key_7 = d7.key_7
JOIN example_analytics.dim_8 d8 ON nested_orders.key_8 = d8.key_8
JOIN example_analytics.dim_9 d9 ON nested_orders.key_9 = d9.key_9
JOIN example_analytics.dim_10 d10 ON nested_orders.key_10 = d10.key_10
JOIN example_analytics.dim_11 d11 ON nested_orders.key_11 = d11.key_11
WHERE nested_orders.ds = 20260507
