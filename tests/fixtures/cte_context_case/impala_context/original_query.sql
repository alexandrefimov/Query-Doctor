WITH recent_orders AS (
  SELECT customer_id, order_id
  FROM example_warehouse.orders
),
ranked_customers AS (
  SELECT customer_id
  FROM recent_orders
)
SELECT rc.customer_id, c.segment
FROM ranked_customers rc
JOIN example_warehouse.customers c
  ON rc.customer_id = c.customer_id
