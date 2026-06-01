# Synthetic Impala Profile Digest

## ExecSummary

```text
01:HDFS SCAN                        3  30s000ms 30s000ms   300.00M     300.00M   256.00 MiB  256.00 MiB  example_warehouse.events
```

## Backend counters

```text
Backend 1 host=worker-a.example.net fragment=F00:000
  - ScanBytesAssigned: 10.0 GiB
  - BytesRead: 10.0 GiB
  - HDFSBytesWritten: 9.8 GiB
  - RowsProduced: 100,000,000
  - ReadRate: 320.0 MiB/s
  - WriteRate: 300.0 MiB/s
  - HdfsWriteTime: 32s
  - ExecutionTime: 40s
Backend 2 host=worker-b.example.net fragment=F00:001
  - ScanBytesAssigned: 10.5 GiB
  - BytesRead: 10.2 GiB
  - HDFSBytesWritten: 10.0 GiB
  - RowsProduced: 101,000,000
  - ReadRate: 315.0 MiB/s
  - WriteRate: 295.0 MiB/s
  - HdfsWriteTime: 34s
  - ExecutionTime: 42s
Backend 3 host=worker-c.example.net fragment=F00:002
  - ScanBytesAssigned: 10.1 GiB
  - BytesRead: 10.0 GiB
  - HDFSBytesWritten: 9.9 GiB
  - RowsProduced: 99,000,000
  - ReadRate: 82.0 MiB/s
  - WriteRate: 41.0 MiB/s
  - HdfsWriteTime: 240s
  - ExecutionTime: 260s
```
