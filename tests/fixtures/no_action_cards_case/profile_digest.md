# Synthetic Impala Profile Digest

## SQL

```sql
SELECT id, amount
FROM example_sales.orders
WHERE dt = '2026-01-01'
```

## ExecSummary

```text
01:HDFS SCAN                        1  500ms  500ms    100.00K     100.00K   16.00 MiB   16.00 MiB  example_sales.orders
02:EXCHANGE                         1  250ms  250ms    100.00K      90.00K    8.00 MiB    8.00 MiB  UNPARTITIONED
```

## Metric lines

```text
- TotalBytesRead: 256.0 MiB
- TotalBytesSent: 64.0 MiB
- TotalTime: 1s
```
