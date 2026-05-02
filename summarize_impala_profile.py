#!/usr/bin/env python3
"""
Legacy/development profile summarizer.

This script is not the current supported production path. Prefer
query_doctor_collect_cm_profiles.py for profile collection and
analyze_profile_digest.py for deterministic analyzer facts. This helper can
still be useful for local debugging of old raw profile.txt cases, but do not
treat it as the trusted analyzer/report contract.
"""

import argparse
import re
from pathlib import Path


IMPORTANT_PATTERNS = [
    r"Query \(id=.*?\)",
    r"Query Timeline",
    r"Query Compilation",
    r"Query Options",
    r"Admission",
    r"Planner Timeline",
    r"ExecSummary",
    r"Operator.*#Hosts.*Avg Time.*Max Time",
    r"HDFS_SCAN_NODE",
    r"SCAN HDFS",
    r"HASH_JOIN_NODE",
    r"JOIN",
    r"AGGREGATION_NODE",
    r"AGGREGATE",
    r"SORT_NODE",
    r"SORT",
    r"EXCHANGE_NODE",
    r"EXCHANGE",
    r"KrpcDataStreamSender",
    r"DataStreamSender",
    r"Averaged Fragment",
    r"Errors:",
    r"Warnings:",
    r"Memory",
    r"PeakMemoryUsage",
    r"RowsRead",
    r"RowsReturned",
    r"RowsProduced",
    r"BytesRead",
    r"TotalBytesRead",
    r"TotalBytesSent",
    r"TotalTime",
    r"TotalRawHdfsReadTime",
    r"ScannerThreadsTotalWallClockTime",
    r"TotalStorageWaitTime",
    r"SpilledPartitions",
    r"BytesWritten",
    r"WriteIoBytes",
    r"ReadIoBytes",
    r"NumScannerThreads",
    r"PeakScannerThreadConcurrency",
    r"Per Read Thread Raw HDFS Throughput",
    r"split sizes:",
    r"completion times:",
    r"execution rates:",
]


def find_query_text(text: str) -> str:
    candidates = [
        r"(?is)Query:\s*(.*?)(?:\n\s*(?:Query Timeline|Query Options|Plan|Planner Timeline|ExecSummary|Coordinator|Fragment))",
        r"(?is)Sql Statement:\s*(.*?)(?:\n\s*(?:Query Timeline|Query Options|Plan|Planner Timeline|ExecSummary|Coordinator|Fragment))",
        r"(?is)Statement:\s*(.*?)(?:\n\s*(?:Query Timeline|Query Options|Plan|Planner Timeline|ExecSummary|Coordinator|Fragment))",
    ]

    for pat in candidates:
        m = re.search(pat, text)
        if m:
            q = m.group(1).strip()
            if len(q) > 20:
                return q[:20000]

    return ""


def extract_exec_summary(text: str) -> str:
    # Обычно ExecSummary — самый ценный кусок профиля.
    patterns = [
        r"(?is)(ExecSummary:.*?)(?:\n\s*Errors:|\n\s*Query Compilation|\n\s*Coordinator Fragment|\n\s*Fragment \d+:|\Z)",
        r"(?is)(ExecSummary.*?)(?:\n\s*Errors:|\n\s*Query Compilation|\n\s*Coordinator Fragment|\n\s*Fragment \d+:|\Z)",
    ]

    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()[:120000]

    return ""


def extract_blocks_by_keywords(text: str, context_before: int = 2, context_after: int = 45) -> str:
    lines = text.splitlines()
    regex = re.compile("|".join(IMPORTANT_PATTERNS), re.IGNORECASE)

    selected = set()

    for i, line in enumerate(lines):
        if regex.search(line):
            start = max(0, i - context_before)
            end = min(len(lines), i + context_after)
            for j in range(start, end):
                selected.add(j)

    if not selected:
        return ""

    chunks = []
    prev = None

    for idx in sorted(selected):
        if prev is None or idx > prev + 1:
            chunks.append("\n--- snip ---\n")
        chunks.append(lines[idx])
        prev = idx

    return "\n".join(chunks)


def extract_top_metric_lines(text: str, limit: int = 300) -> str:
    metric_re = re.compile(
        r"(RowsRead|RowsReturned|RowsProduced|BytesRead|TotalBytesRead|TotalBytesSent|"
        r"PeakMemoryUsage|TotalTime|TotalRawHdfsReadTime|ScannerThreadsTotalWallClockTime|"
        r"TotalStorageWaitTime|SerializeBatchTime|SpilledPartitions|ReadIoBytes|WriteIoBytes|"
        r"PeakReservation|CumulativeAllocationBytes|LargestPartitionPercent|NumRepartitions)",
        re.IGNORECASE,
    )

    lines = []
    for line in text.splitlines():
        if metric_re.search(line):
            lines.append(line)

    return "\n".join(lines[:limit])


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Legacy/development profile summarizer. Prefer "
            "analyze_profile_digest.py for supported analyzer facts."
        )
    )
    parser.add_argument("case_dir")
    parser.add_argument("--max-output-chars", type=int, default=180000)
    args = parser.parse_args()

    case_dir = Path(args.case_dir)
    profile_path = case_dir / "profile.txt"
    out_path = case_dir / "profile_summary.txt"
    sql_path = case_dir / "sql.sql"

    if not profile_path.exists():
        raise SystemExit(f"profile.txt not found: {profile_path}")

    text = profile_path.read_text(encoding="utf-8", errors="replace")

    parts = []

    query_text = find_query_text(text)
    if query_text:
        parts.append("# SQL / Query text extracted from profile\n\n" + query_text)

        # Если sql.sql пустой — заполним.
        existing_sql = ""
        if sql_path.exists():
            existing_sql = sql_path.read_text(encoding="utf-8", errors="replace").strip()

        if not existing_sql or existing_sql.startswith("-- SQL statement was not found"):
            sql_path.write_text(query_text.strip() + "\n", encoding="utf-8")

    exec_summary = extract_exec_summary(text)
    if exec_summary:
        parts.append("# ExecSummary\n\n" + exec_summary)

    metric_lines = extract_top_metric_lines(text)
    if metric_lines:
        parts.append("# Important metric lines\n\n" + metric_lines)

    keyword_blocks = extract_blocks_by_keywords(text)
    if keyword_blocks:
        parts.append("# Important profile blocks\n\n" + keyword_blocks)

    summary = "\n\n\n".join(parts)

    if len(summary) > args.max_output_chars:
        head = summary[: args.max_output_chars // 2]
        tail = summary[-args.max_output_chars // 2 :]
        summary = (
            head
            + f"\n\n[... SUMMARY TRUNCATED: {len(summary) - args.max_output_chars} chars omitted ...]\n\n"
            + tail
        )

    out_path.write_text(summary, encoding="utf-8")

    print(f"[summarize_impala_profile] input chars: {len(text)}")
    print(f"[summarize_impala_profile] output chars: {len(summary)}")
    print(f"[summarize_impala_profile] written: {out_path}")

    if query_text:
        print(f"[summarize_impala_profile] sql extracted: {len(query_text)} chars")
    else:
        print("[summarize_impala_profile] sql extracted: 0 chars")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
