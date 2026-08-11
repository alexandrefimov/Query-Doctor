"""Generate synthetic Impala-shaped text profiles of a target size for timing tests.

Synthetic only. No real cluster data, hostnames, users, tables, or SQL.
"""
from __future__ import annotations

import sys

HEADER = """Query Runtime Profile
Query (id=aa4d4a4a4a4a4a4a:bb5b5b5b5b5b5b5b)
User: synthetic_user
Request Pool: synthetic_pool
Start Time: 2026-06-14 11:00:00.000000000
End Time: 2026-06-14 11:07:00.000000000
Coordinator: synthetic-impalad.example.invalid:22000
Query Type: QUERY
Query State: FINISHED
Impala Version: impalad version 4.4.0-SYNTHETIC

Sql Statement:
SELECT /* synthetic */ a, b, count(*) FROM synthetic_db.synthetic_fact GROUP BY a, b

Query Timeline:
   Query submitted: 0ns
   Planning finished: 1s200ms
   Ready to start on 20 backends: 1s400ms
   All 20 execution backends (40 fragment instances) started: 2s100ms
   Rows available: 6m30s
   First row fetched: 6m40s
   Last row fetched: 6m55s
   Query finished: 7m

TotalTime: 7m
TotalBytesRead: 6.00 GiB
TotalBytesSent: 256.00 MiB
"""


def exec_summary(n_ops: int) -> str:
    lines = [
        "ExecSummary:",
        "Operator              #Hosts   Avg Time   Max Time    #Rows  Est. #Rows  "
        "Peak Mem  Est. Peak Mem  Detail",
    ]
    for i in range(n_ops):
        kind = ("SCAN HDFS", "AGGREGATE", "HASH JOIN", "EXCHANGE")[i % 4]
        avg = 500 + (i * 37) % 4000
        mx = avg + 900
        rows = 100_000 * (i + 1)
        est = 20_000 * (i + 1)
        lines.append(
            f"{i:02d}:{kind:<18} 20  {avg // 1000}s{avg % 1000:03d}ms  "
            f"{mx // 1000}s{mx % 1000:03d}ms  {rows / 1e6:.2f}M  {est / 1e3:.2f}K  "
            f"{128 + i}.00 MB  {64 + i}.00 MB  table=synthetic_db.synthetic_t{i % 7}"
        )
    return "\n".join(lines) + "\n"


COUNTERS = [
    "BytesRead: {b}.00 GB",
    "BytesReadLocal: {b}.00 GB",
    "DecompressionTime: {t}ms",
    "RowsRead: {r}",
    "RowsReturned: {r}",
    "ScannerThreadsTotalWallClockTime: {t}ms",
    "ScannerThreadsSysTime: {t}ms",
    "ScannerThreadsUserTime: {t}ms",
    "PeakMemoryUsage: {m}.00 MB",
    "TotalStorageWaitTime: {t}ms",
    "TotalNetworkSendTime: {t}ms",
    "TotalNetworkReceiveTime: {t}ms",
    "InactiveTotalTime: {t}ms",
    "TotalTime: {t}ms",
    "BuildRows: {r}",
    "BuildTime: {t}ms",
    "ProbeRows: {r}",
    "ProbeTime: {t}ms",
    "SpilledPartitions: 0",
    "NumHashTableBuildsSkipped: 0",
    "RowsReturnedRate: {r}/sec",
    "OpenTime: {t}ms",
    "PrepareTime: {t}ms",
    "ExecTreeExecTime: {t}ms",
    "CodegenTime: {t}ms",
]


def execution_profile(n_frag: int, n_inst: int) -> str:
    out = ["Execution Profile aa4d4a4a4a4a4a4a:bb5b5b5b5b5b5b5b:"]
    for f in range(n_frag):
        out.append(f"  Fragment F{f:02d}:")
        out.append(f"    Instance aa4d4a4a4a4a4a4a:bb5b5b5b5b5b{f:04x} "
                   f"(host=synthetic-impalad-{f % 20}.example.invalid:22000):")
        for inst in range(n_inst):
            out.append(f"      HDFS_SCAN_NODE (id={f * 10 + inst % 10}):")
            for k, tmpl in enumerate(COUNTERS):
                val = tmpl.format(
                    b=(f + inst + k) % 9 + 1,
                    t=(f * 131 + inst * 17 + k * 7) % 90000,
                    r=(f * 100003 + inst * 977 + k) % 5_000_000,
                    m=(f + inst * 3 + k) % 512 + 32,
                )
                out.append(f"        - {val}")
    return "\n".join(out) + "\n"


def build(target_bytes: int) -> str:
    n_ops = 40
    n_inst = 8
    n_frag = 1
    base = HEADER + exec_summary(n_ops)
    while True:
        text = base + execution_profile(n_frag, n_inst)
        if len(text.encode()) >= target_bytes or n_frag > 4000:
            return text
        n_frag = max(n_frag + 1, int(n_frag * 1.6))


if __name__ == "__main__":
    target = int(sys.argv[1])
    out = sys.argv[2]
    text = build(target)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"{out}: {len(text.encode()) / 1024:.0f} KiB, {text.count(chr(10))} lines")
