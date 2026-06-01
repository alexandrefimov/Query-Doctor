# Synthetic Impala Profile Digest

## SQL

```sql
SELECT *
FROM example_fact.events
```

## ExecSummary

```text
12:HASH JOIN                        1  2s000ms  2s000ms    2.00M          0   256.00 MiB  0 B  INNER JOIN, PARTITIONED
13:EXCHANGE                         1  1s000ms  1s000ms    2.00M        n/a    32.00 MiB  n/a  UNPARTITIONED
```

## Metric lines

```text
- TotalBytesRead: 1.0 GiB
- TotalBytesSent: 1.0 GiB
- TotalTime: 4s
```
