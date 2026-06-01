# Synthetic Impala Profile Digest

## SQL

```sql
SELECT account_id
FROM example_mart.daily_accounts
ORDER BY last_seen_at
```

## ExecSummary

```text
07:SORT                             1  4s000ms  4s000ms    500.00K     500.00K   20.00 GiB  512.00 MiB
```

## Metric lines

```text
- TotalBytesRead: 2.0 GiB
- TotalBytesSent: 512.0 MiB
- TotalTime: 6s
```
