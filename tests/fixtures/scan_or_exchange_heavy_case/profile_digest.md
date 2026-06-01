# Synthetic Impala Profile Digest

## SQL

```sql
SELECT event_id, payload
FROM example_logs.raw_events
```

## ExecSummary

```text
01:HDFS SCAN                        1  1s000ms  1s000ms    900.00K     900.00K   128.00 MiB  128.00 MiB  example_logs.raw_events
02:EXCHANGE                         1  2s000ms  2s000ms    900.00K     900.00K    16.00 MiB   16.00 MiB  UNPARTITIONED
```

## Metric lines

```text
- TotalBytesRead: 25.0 GiB
- TotalBytesSent: 15.0 GiB
- TotalTime: 12s
```
