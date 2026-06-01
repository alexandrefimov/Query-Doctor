# Synthetic Impala Profile Digest

## SQL

```sql
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
```

## ExecSummary

```text
04:HASH JOIN                        1  1s000ms  1s000ms    100.00K      90.00K   64.00 MiB   64.00 MiB  INNER JOIN, BROADCAST
05:EXCHANGE                         1  500ms    500ms      100.00K      90.00K    4.00 MiB    4.00 MiB  UNPARTITIONED
```

## Metric lines

```text
- TotalBytesRead: 128.0 MiB
- TotalBytesSent: 32.0 MiB
- TotalTime: 2s
```
