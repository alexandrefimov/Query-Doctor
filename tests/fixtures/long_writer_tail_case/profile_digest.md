# Synthetic Impala Profile Digest

## ExecSummary

```text
01:HDFS SCAN                        1  2s000ms  2s000ms  120.00M  120.00M   512.00 MiB  512.00 MiB
02:AGGREGATE                        1  3s000ms  3s000ms  120.00M  120.00M   256.00 MiB  256.00 MiB
```

## Backend counters

```text
Averaged Fragment F07
  Instance writer-a (host=synth-long-writer-a)
    - ScanBytesAssigned: 12.0 GiB
    - BytesRead: 12.0 GiB
    - HDFSBytesWritten: 40.0 GiB
    - RowsProduced: 120,000,000
    - WriteRate: 400.0 MiB/s
    - HdfsWriteTime: 7m
    - ExecutionTime: 4m
  Instance writer-b (host=synth-long-writer-b)
    - ScanBytesAssigned: 12.1 GiB
    - BytesRead: 12.0 GiB
    - HDFSBytesWritten: 40.0 GiB
    - RowsProduced: 119,500,000
    - WriteRate: 390.0 MiB/s
    - HdfsWriteTime: 6m30s
    - ExecutionTime: 4m10s
  Instance writer-c (host=synth-long-writer-c)
    - ScanBytesAssigned: 12.0 GiB
    - BytesRead: 12.2 GiB
    - HDFSBytesWritten: 40.0 GiB
    - RowsProduced: 120,500,000
    - WriteRate: 42.0 MiB/s
    - HdfsWriteTime: 52m
    - ExecutionTime: 4m05s
```

## Metric lines

```text
- TotalTime: 55m
- TotalBytesRead: 36.0 GiB
- TotalBytesSent: 512.0 MiB
```
