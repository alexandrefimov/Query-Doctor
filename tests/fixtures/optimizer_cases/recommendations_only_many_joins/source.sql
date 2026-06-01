SELECT f.order_id
FROM example_analytics.fact_orders f
JOIN example_analytics.dim_1 d1 ON f.key_1 = d1.key_1
JOIN example_analytics.dim_2 d2 ON f.key_2 = d2.key_2
JOIN example_analytics.dim_3 d3 ON f.key_3 = d3.key_3
JOIN example_analytics.dim_4 d4 ON f.key_4 = d4.key_4
JOIN example_analytics.dim_5 d5 ON f.key_5 = d5.key_5
JOIN example_analytics.dim_6 d6 ON f.key_6 = d6.key_6
JOIN example_analytics.dim_7 d7 ON f.key_7 = d7.key_7
JOIN example_analytics.dim_8 d8 ON f.key_8 = d8.key_8
JOIN example_analytics.dim_9 d9 ON f.key_9 = d9.key_9
JOIN example_analytics.dim_10 d10 ON f.key_10 = d10.key_10
JOIN example_analytics.dim_11 d11 ON f.key_11 = d11.key_11
WHERE f.ds = 20260507;
