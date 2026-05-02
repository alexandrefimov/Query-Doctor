#!/usr/bin/env python3
"""
make_profile_digest.py

Legacy/development digest helper.

This script is not the current supported production path. Prefer
analyze_profile_digest.py for deterministic analyzer facts and
query_doctor_pipeline.py for the supported validated report flow. This helper
can still be useful for local debugging of old profile_summary.txt/profile.txt
cases, but do not treat it as the trusted analyzer contract.

Builds a compact, LLM-friendly digest from an Impala query profile.

Expected input in case directory:
  - profile_summary.txt  preferred
  - profile.txt          fallback

Output:
  - profile_digest.md

Usage:
  ./make_profile_digest.py /path/to/case-dir

Example:
  cd ~/query-doctor
  ./make_profile_digest.py cases/<case_dir>
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


# ExecSummary operator rows in Impala often look like:
#   F27:ROOT ...
#   66:EXCHANGE ...
#   33:SORT ...
#   18:HASH JOIN ...
#   03:SCAN HDFS ...
#
# The previous version matched Fxx rows, but missed numeric operator ids like 33:SORT.
OPERATOR_RE = re.compile(
    r"^\s*(?:F\d+:|\d+:)?\s*"
    r"(ROOT|EXCHANGE|EXCHANGE SENDER|SELECT|ANALYTIC|SORT|HASH JOIN|"
    r"NESTED LOOP JOIN|AGGREGATE|AGGREGATION|SCAN HDFS|HDFS_SCAN_NODE|"
    r"UNION|TOP-N|KUDU_SCAN_NODE|DATASTREAM SINK)",
    re.IGNORECASE,
)

IMPORTANT_OPERATOR_WORDS = (
    "SORT",
    "ANALYTIC",
    "JOIN",
    "AGGREG",
    "SCAN",
    "EXCHANGE",
    "TOP-N",
)

METRIC_RE = re.compile(
    r"(RowsRead|RowsReturned|RowsProduced|BytesRead|TotalBytesRead|TotalBytesSent|"
    r"PeakMemoryUsage|Peak Mem|Est\. Peak Mem|TotalTime|ExecTime|"
    r"ScannerThreadsTotalWallClockTime|TotalRawHdfsReadTime|TotalStorageWaitTime|"
    r"SerializeBatchTime|SpilledPartitions|ScratchBytesRead|ScratchBytesWritten|"
    r"WriteIoBytes|ReadIoBytes|ReductionFactor|HTResizeTime|StreamingTime|"
    r"PartitionsCreated|NumRepartitions|LargestPartitionPercent|Estimated|"
    r"Est\. #Rows|CodegenTotalWallClockTime|CodegenTime|Codegen)",
    re.IGNORECASE,
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_section(
    text: str,
    start_pat: str,
    end_pats: list[str],
    max_chars: int = 80_000,
) -> str:
    start_match = re.search(start_pat, text, flags=re.IGNORECASE)
    if not start_match:
        return ""

    start = start_match.start()
    end = len(text)

    tail = text[start + 1 :]
    for end_pat in end_pats:
        end_match = re.search(end_pat, tail, flags=re.IGNORECASE)
        if end_match:
            end = min(end, start + 1 + end_match.start())

    return text[start:end][:max_chars].strip()


def extract_sql(text: str, max_chars: int = 12_000) -> str:
    patterns = [
        r"(?is)# SQL / Query text extracted from profile\s*(.*?)(?:\n\s*# ExecSummary|\n\s*F\d+:PLAN FRAGMENT|\Z)",
        r"(?is)\b(WITH\s+.*?\)\s*SELECT\s+.*?)(?:\n\s*# ExecSummary|\n\s*F\d+:PLAN FRAGMENT|\Z)",
        r"(?is)\b(SELECT\s+.*?)(?:\n\s*# ExecSummary|\n\s*F\d+:PLAN FRAGMENT|\Z)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            sql = match.group(1).strip()
            if len(sql) > 20:
                return sql[:max_chars]

    return ""


def parse_exec_summary_rows(exec_summary: str) -> list[str]:
    rows: list[str] = []

    for line in exec_summary.splitlines():
        line = line.rstrip()
        if not line:
            continue

        if OPERATOR_RE.match(line):
            rows.append(line)

    return rows


def extract_important_exec_rows(exec_rows: list[str]) -> list[str]:
    important: list[str] = []

    for line in exec_rows:
        upper = line.upper()
        if any(word in upper for word in IMPORTANT_OPERATOR_WORDS):
            important.append(line)

    return important


def extract_metric_lines(text: str, max_lines: int = 250) -> str:
    lines: list[str] = []

    for line in text.splitlines():
        if METRIC_RE.search(line):
            stripped = line.rstrip()

            # Drop the most useless repeated zeros, otherwise they dominate the digest.
            if re.search(r"(InactiveTotalTime|TotalTime): 0ns \(0\)", stripped):
                continue
            if "ScratchBytesRead: 0 B (0)" in stripped:
                continue
            if "ScratchBytesWritten: 0 B (0)" in stripped:
                continue

            lines.append(stripped)

    return "\n".join(lines[:max_lines])


def compact_blank_lines(text: str) -> str:
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip() + "\n"


def build_digest(case_dir: Path, max_digest_chars: int) -> tuple[str, dict[str, int]]:
    summary_path = case_dir / "profile_summary.txt"
    raw_path = case_dir / "profile.txt"

    if summary_path.exists():
        text = read_text(summary_path)
        source = "profile_summary.txt"
    elif raw_path.exists():
        text = read_text(raw_path)
        source = "profile.txt"
    else:
        raise FileNotFoundError(
            f"Neither profile_summary.txt nor profile.txt found in {case_dir}"
        )

    sql = extract_sql(text)

    exec_summary = extract_section(
        text=text,
        start_pat=r"ExecSummary:",
        end_pats=[
            r"\n# Important metric lines",
            r"\n# Important profile blocks",
            r"\nErrors:",
            r"\nWarnings:",
            r"\nQuery Compilation",
        ],
        max_chars=80_000,
    )

    exec_rows = parse_exec_summary_rows(exec_summary)
    important_rows = extract_important_exec_rows(exec_rows)
    metric_lines = extract_metric_lines(text)

    # Keep full operator signal, not just "suspicious" rows, because some apparently boring
    # EXCHANGE / SELECT rows help reconstruct the shape of the plan.
    if important_rows:
        important_exec = "\n".join(important_rows[:160])
    elif exec_rows:
        important_exec = "\n".join(exec_rows[:160])
    elif exec_summary:
        important_exec = exec_summary[:25_000]
    else:
        important_exec = "ExecSummary was not found."

    digest = f"""# Impala Query Profile Digest

Source file: `{source}`

## SQL

```sql
{sql if sql else "-- SQL was not extracted"}
```

## ExecSummary: important operator rows

```text
{important_exec}
```

## Metric lines

```text
{metric_lines if metric_lines else "No important metric lines found."}
```

## Query Doctor instructions

Use only evidence from this digest.

Do not recommend disabling codegen unless CodegenTotalWallClockTime / CodegenTime is explicitly one of the dominant timings.

Do not recommend HDFS block-size or replication changes unless the digest clearly shows small files / many scan ranges / storage wait as the dominant bottleneck.

Prioritize:
1. Cardinality estimate errors: actual rows vs estimated rows.
2. SORT / ANALYTIC / JOIN / AGGREGATION operators by time and memory.
3. Network exchange / bytes sent.
4. Scan volume and partition pruning.
5. Spill / memory pressure.
6. Admission / planning / metadata only if visible in the digest.
"""

    digest = compact_blank_lines(digest)

    if len(digest) > max_digest_chars:
        digest = digest[:max_digest_chars] + "\n\n[... digest truncated ...]\n"

    stats = {
        "source_chars": len(text),
        "digest_chars": len(digest),
        "sql_chars": len(sql),
        "exec_rows": len(exec_rows),
        "important_rows": len(important_rows),
        "metric_lines": len(metric_lines.splitlines()) if metric_lines else 0,
    }

    return digest, stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Legacy/development helper for compact profile digests. Prefer "
            "analyze_profile_digest.py for supported analyzer facts."
        )
    )
    parser.add_argument(
        "case_dir",
        help="Case directory containing profile_summary.txt or profile.txt",
    )
    parser.add_argument(
        "--max-digest-chars",
        type=int,
        default=45_000,
        help="Maximum output digest size in characters. Default: 45000",
    )
    parser.add_argument(
        "--output",
        default="profile_digest.md",
        help="Output filename inside case_dir. Default: profile_digest.md",
    )

    args = parser.parse_args()

    case_dir = Path(args.case_dir).expanduser().resolve()
    if not case_dir.exists():
        raise SystemExit(f"Case directory does not exist: {case_dir}")

    digest, stats = build_digest(
        case_dir=case_dir,
        max_digest_chars=args.max_digest_chars,
    )

    out_path = case_dir / args.output
    out_path.write_text(digest, encoding="utf-8")

    print(f"[make_profile_digest] written: {out_path}")
    print(f"[make_profile_digest] source chars: {stats['source_chars']}")
    print(f"[make_profile_digest] digest chars: {stats['digest_chars']}")
    print(f"[make_profile_digest] sql chars: {stats['sql_chars']}")
    print(f"[make_profile_digest] exec rows: {stats['exec_rows']}")
    print(f"[make_profile_digest] important rows: {stats['important_rows']}")
    print(f"[make_profile_digest] metric lines: {stats['metric_lines']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
