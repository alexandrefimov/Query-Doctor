# Synthetic Impala Profile Digest

## ExecSummary

```text
01:HDFS SCAN                        1  5s000ms  5s000ms    6.00M      6.00M   512.00 MiB   512.00 MiB
02:AGGREGATE                        1  8s000ms  8s000ms    6.00M     10.00K   256.00 MiB    64.00 MiB
```

## Backend counters

```text
Averaged Fragment F02
  Instance inst-a (host=synth-runtime-a)
    - RowsProduced: 1,100,000
    - BytesRead: 1.0 GiB
    - ExecutionTime: 20s
  Instance inst-b (host=synth-runtime-b)
    - RowsProduced: 1,050,000
    - BytesRead: 1.0 GiB
    - ExecutionTime: 21s
  Instance inst-c (host=synth-runtime-c)
    - RowsProduced: 6,300,000
    - BytesRead: 1.1 GiB
    - ExecutionTime: 22s
```

## Metric lines

```text
- TotalTime: 1m30s
- TotalBytesRead: 1.5 GiB
- TotalBytesSent: 512.0 MiB
```
