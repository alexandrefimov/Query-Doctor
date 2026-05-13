# Synthetic Impala Profile Digest

## Backend counters

```text
Backend 1 host=synth-writer-a fragment=F00:000
  - ScanBytesAssigned: 10.0 GiB
  - BytesRead: 10.0 GiB
  - HDFSBytesWritten: 10.0 GiB
  - RowsProduced: 100,000,000
  - WriteRate: 300.0 MiB/s
  - HdfsWriteTime: 30s
  - ExecutionTime: 40s
Backend 2 host=synth-writer-b fragment=F00:001
  - ScanBytesAssigned: 10.1 GiB
  - BytesRead: 10.0 GiB
  - HDFSBytesWritten: 10.0 GiB
  - RowsProduced: 101,000,000
  - WriteRate: 290.0 MiB/s
  - HdfsWriteTime: 32s
  - ExecutionTime: 40s
Backend 3 host=synth-writer-c fragment=F00:002
  - ScanBytesAssigned: 10.0 GiB
  - BytesRead: 10.2 GiB
  - HDFSBytesWritten: 10.0 GiB
  - RowsProduced: 99,000,000
  - WriteRate: 40.0 MiB/s
  - HdfsWriteTime: 240s
  - ExecutionTime: 40s
```
