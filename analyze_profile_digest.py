#!/usr/bin/env python3
"""
Deterministic analyzer for Query Doctor Impala profile_digest.md files.

Purpose:
- Extract facts from profile_digest.md with regex/rules.
- Write analysis_facts.md for an LLM report writer.
- Avoid asking the LLM to parse profile text or infer unsupported facts.

No external dependencies.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


KNOWN_OPERATOR_NAMES = [
    "NESTED LOOP JOIN",
    "STREAMING AGGREGATE",
    "HASH AGGREGATE",
    "MERGING EXCHANGE",
    "DATASTREAM SINK",
    "PLAN ROOT SINK",
    "HDFS SCAN",
    "HBASE SCAN",
    "KUDU SCAN",
    "HASH JOIN",
    "CROSS JOIN",
    "AGGREGATE",
    "ANALYTIC",
    "EXCHANGE",
    "SORT",
    "TOP-N",
    "UNION",
    "SELECT",
    "SCAN",
]

OP_RE = re.compile(
    r"\b(?P<id>\d{1,3})\s*:\s*(?P<name>"
    + "|".join(re.escape(x) for x in KNOWN_OPERATOR_NAMES)
    + r")\b",
    flags=re.IGNORECASE,
)

SIZE_RE = re.compile(
    r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>KiB|MiB|GiB|TiB|KB|MB|GB|TB|B)\b",
    flags=re.IGNORECASE,
)

# Deliberately case-sensitive for single-letter units.
# This avoids treating row suffix "6.37M actual rows" as "6.37 minutes".
DURATION_TOKEN_RE = re.compile(
    r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>ms|msec|milliseconds?|s|sec|seconds?|m|min|minutes?|h|hr|hours?)(?![A-Za-z])"
)

TABLE_DURATION_TOKEN_RE = re.compile(
    r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>ns|us|µs|ms|msec|milliseconds?|s|sec|seconds?|m|min|minutes?|h|hr|hours?)(?![A-Za-z])"
)

ROW_NUMBER = r"\d[\d,]*(?:\.\d+)?\s*[KMBT]?"
SIZE_PATTERN = r"\d[\d,]*(?:\.\d+)?\s*(?:KiB|MiB|GiB|TiB|KB|MB|GB|TB|B)"

TABLE_SEPARATOR_RE = re.compile(r"\s{2,}")

ROWS_PATTERNS = [
    re.compile(
        rf"(?P<actual>{ROW_NUMBER})\s+actual\s+rows?\s+(?:vs|/)\s+"
        rf"(?P<estimated>{ROW_NUMBER})\s+estimated\s+rows?",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"actual\s+rows?\s*[:=]\s*(?P<actual>{ROW_NUMBER}).{{0,100}}?"
        rf"estimated\s+rows?\s*[:=]\s*(?P<estimated>{ROW_NUMBER})",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"estimated\s+rows?\s*[:=]\s*(?P<estimated>{ROW_NUMBER}).{{0,100}}?"
        rf"actual\s+rows?\s*[:=]\s*(?P<actual>{ROW_NUMBER})",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"rows\s*[:=]\s*(?P<actual>{ROW_NUMBER}).{{0,100}}?"
        rf"est(?:imated)?\.?\s+rows\s*[:=]\s*(?P<estimated>{ROW_NUMBER})",
        flags=re.IGNORECASE,
    ),
]

MEM_PATTERNS = [
    re.compile(
        rf"(?:Peak\s+Mem(?:ory)?|PeakMem)\s*[:=]?\s*(?P<actual>{SIZE_PATTERN}).{{0,80}}?"
        rf"(?:Est\.?\s*Peak\s+Mem(?:ory)?|Estimated\s+Peak\s+Mem(?:ory)?|EstPeakMem)\s*[:=]?\s*(?P<estimated>{SIZE_PATTERN})",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"(?:Est\.?\s*Peak\s+Mem(?:ory)?|Estimated\s+Peak\s+Mem(?:ory)?|EstPeakMem)\s*[:=]?\s*(?P<estimated>{SIZE_PATTERN}).{{0,80}}?"
        rf"(?:Peak\s+Mem(?:ory)?|PeakMem)\s*[:=]?\s*(?P<actual>{SIZE_PATTERN})",
        flags=re.IGNORECASE,
    ),
]

SINGLE_PEAK_MEM_RE = re.compile(
    rf"(?:Peak\s+Mem(?:ory)?|PeakMem)\s*[:=]?\s*(?P<actual>{SIZE_PATTERN})",
    flags=re.IGNORECASE,
)

JOIN_KIND_RE = re.compile(
    r"\b(?P<kind>LEFT\s+ANTI|LEFT\s+SEMI|RIGHT\s+ANTI|RIGHT\s+SEMI|LEFT\s+OUTER|RIGHT\s+OUTER|FULL\s+OUTER|INNER|LEFT|RIGHT|FULL|CROSS)\s+JOIN\b",
    flags=re.IGNORECASE,
)

TOTAL_COUNTER_ALIASES = {
    "TotalBytesRead": ["TotalBytesRead", "Total Bytes Read"],
    "TotalBytesSent": ["TotalBytesSent", "Total Bytes Sent", "Bytes Sent"],
    "TotalTime": ["TotalTime", "Total Time"],
}

CM_PROFILE_TEXT_FIELDS = ("details", "profile", "profileText", "text")
CM_RUNTIME_PROFILE_MARKERS = (
    "Runtime Profile",
    "ExecSummary",
    "Averaged Fragment",
    "PLAN",
    "HDFS_SCAN_NODE",
    "HASH_JOIN_NODE",
    "RowsProduced",
)

ESTIMATED_ROWS_ONLY_RE = re.compile(
    rf"\bcardinality\s*[:=]\s*(?P<estimated>{ROW_NUMBER})\b",
    flags=re.IGNORECASE,
)

RAW_NODE_HEADER_RE = re.compile(
    r"^\s*(?P<node>[A-Z][A-Z0-9_]+_NODE)\s+\(id=(?P<id>\d{1,3})\)",
)

RAW_NODE_NAME_MAP = {
    "ANALYTIC_EVAL_NODE": "ANALYTIC",
    "AGGREGATE_NODE": "AGGREGATE",
    "AGGREGATION_NODE": "AGGREGATE",
    "EXCHANGE_NODE": "EXCHANGE",
    "HASH_JOIN_NODE": "HASH JOIN",
    "HBASE_SCAN_NODE": "HBASE SCAN",
    "HDFS_SCAN_NODE": "HDFS SCAN",
    "KUDU_SCAN_NODE": "KUDU SCAN",
    "NESTED_LOOP_JOIN_NODE": "NESTED LOOP JOIN",
    "SCAN_NODE": "SCAN",
    "SELECT_NODE": "SELECT",
    "SORT_NODE": "SORT",
    "TOPN_NODE": "TOP-N",
    "UNION_NODE": "UNION",
}

RAW_ROW_COUNTER_RE = re.compile(
    r"-\s*(?:RowsProduced|RowsReturned|RowsRead|RowsSent)\s*:\s*(?P<value>[^\n\r]+)",
    flags=re.IGNORECASE,
)
RAW_PEAK_MEMORY_RE = re.compile(
    rf"-\s*(?:PeakMemoryUsage|PerHostPeakMemUsage|PeakMemUsage)\s*:\s*(?P<value>{SIZE_PATTERN})",
    flags=re.IGNORECASE,
)
RAW_TIME_COUNTER_RE = re.compile(
    r"-\s*(?:TotalTime|ExecTime|ScannerThreadsTotalWallClockTime)\s*:\s*(?P<value>[^\n\r]+)",
    flags=re.IGNORECASE,
)
RAW_COUNTER_NUMBER_RE = re.compile(
    r"(?P<display>\d[\d,]*(?:\.\d+)?\s*[KMBT]?)(?:\s*\((?P<exact>\d[\d,]*(?:\.\d+)?)\))?",
    flags=re.IGNORECASE,
)

STATS_PATTERNS = [
    re.compile(r"\bmissing\s+(?:table\s+|column\s+)?stats\b", re.IGNORECASE),
    re.compile(r"\bno\s+(?:table\s+|column\s+)?stats\b", re.IGNORECASE),
    re.compile(r"\bcompute\s+stats\b", re.IGNORECASE),
    re.compile(r"\bcardinality\b", re.IGNORECASE),
]

SPILL_RE = re.compile(r"\b(spill|spilled|scratch)\b", re.IGNORECASE)
SPILL_METRIC_RE = re.compile(
    rf"\b(?P<name>SpilledBytes|ScratchBytesWritten|PeakScratch|ScratchBytesRead|WriteIoBytes|BytesWritten|SpilledPartitions)\b"
    rf"\s*[:=]\s*(?P<value>{SIZE_PATTERN}|\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)
SCAN_STORAGE_RE = re.compile(
    r"\b(HDFS|SCAN|SCANNER|DISK|IO\s+WAIT|REMOTE\s+READ|SHORT-CIRCUIT|CACHE)\b",
    re.IGNORECASE,
)
CODEGEN_RE = re.compile(r"\b(codegen|llvm)\b", re.IGNORECASE)
CODEGEN_TIMING_RE = re.compile(
    r"\b(?:Codegen|CodeGen|LLVM)[A-Za-z]*(?:Time|WallClockTime)\b\s*[:=]\s*(?P<value>[^\n\r]+)",
    re.IGNORECASE,
)


@dataclass
class OperatorFact:
    operator_id: str
    operator_name: str
    time_ms: float | None = None
    actual_rows: float | None = None
    estimated_rows: float | None = None
    peak_mem_bytes: float | None = None
    estimated_peak_mem_bytes: float | None = None
    join_kind: str | None = None
    is_partitioned: bool = False
    evidence_lines: list[str] = field(default_factory=list)

    @property
    def rows_ratio(self) -> float | None:
        if self.actual_rows is None or self.estimated_rows is None or self.estimated_rows <= 0:
            return None
        return self.actual_rows / self.estimated_rows

    @property
    def mem_ratio(self) -> float | None:
        if (
            self.peak_mem_bytes is None
            or self.estimated_peak_mem_bytes is None
            or self.estimated_peak_mem_bytes <= 0
        ):
            return None
        return self.peak_mem_bytes / self.estimated_peak_mem_bytes

    @property
    def is_join(self) -> bool:
        return "JOIN" in self.operator_name.upper()

    @property
    def is_sort(self) -> bool:
        return self.operator_name.upper() in {"SORT", "TOP-N"}

    @property
    def is_analytic(self) -> bool:
        return "ANALYTIC" in self.operator_name.upper()

    @property
    def is_scan(self) -> bool:
        return "SCAN" in self.operator_name.upper()


def parse_scaled_number(value: str) -> float | None:
    s = value.strip().replace(" ", "")
    m = re.fullmatch(r"(?P<num>\d[\d,]*(?:\.\d+)?)(?P<suffix>[KMBT])?", s, flags=re.IGNORECASE)
    if not m:
        return None
    num = float(m.group("num").replace(",", ""))
    suffix = (m.group("suffix") or "").upper()
    scale = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[suffix]
    return num * scale


def parse_size_bytes(value: str) -> float | None:
    m = SIZE_RE.search(value.strip())
    if not m:
        return None
    num = float(m.group("value").replace(",", ""))
    unit = m.group("unit").lower()
    scale = {
        "b": 1,
        "kb": 1000,
        "mb": 1000**2,
        "gb": 1000**3,
        "tb": 1000**4,
        "kib": 1024,
        "mib": 1024**2,
        "gib": 1024**3,
        "tib": 1024**4,
    }[unit]
    return num * scale


def duration_group_to_ms(matches: list[re.Match[str]]) -> float:
    total = 0.0
    for m in matches:
        value = float(m.group("value").replace(",", ""))
        unit = m.group("unit")
        if unit in {"ms", "msec", "millisecond", "milliseconds"}:
            total += value
        elif unit in {"s", "sec", "second", "seconds"}:
            total += value * 1000
        elif unit in {"m", "min", "minute", "minutes"}:
            total += value * 60 * 1000
        elif unit in {"h", "hr", "hour", "hours"}:
            total += value * 60 * 60 * 1000
    return total


def table_duration_to_ms(value: str) -> float | None:
    matches = list(TABLE_DURATION_TOKEN_RE.finditer(value.strip()))
    if not matches:
        return None

    total = 0.0
    for m in matches:
        num = float(m.group("value").replace(",", ""))
        unit = m.group("unit")
        if unit == "ns":
            total += num / 1_000_000
        elif unit in {"us", "µs"}:
            total += num / 1000
        elif unit in {"ms", "msec", "millisecond", "milliseconds"}:
            total += num
        elif unit in {"s", "sec", "second", "seconds"}:
            total += num * 1000
        elif unit in {"m", "min", "minute", "minutes"}:
            total += num * 60 * 1000
        elif unit in {"h", "hr", "hour", "hours"}:
            total += num * 60 * 60 * 1000
    return total


def extract_first_duration_ms(text: str) -> float | None:
    matches = list(DURATION_TOKEN_RE.finditer(text))
    if not matches:
        return None

    # Build the first contiguous duration group: "1m2s", "1m 2s", "52s385ms".
    group = [matches[0]]
    prev = matches[0]
    for m in matches[1:]:
        gap = text[prev.end() : m.start()]
        if gap.strip() == "":
            group.append(m)
            prev = m
            continue
        break
    return duration_group_to_ms(group)


def extract_total_counter(text: str, canonical_name: str) -> dict[str, Any] | None:
    aliases = TOTAL_COUNTER_ALIASES[canonical_name]
    alias_re = "|".join(re.escape(x) for x in aliases)
    rx = re.compile(rf"(?:{alias_re})\s*[:=]\s*(?P<value>[^\n\r,;|]+)", re.IGNORECASE)
    m = rx.search(text)
    if not m:
        return None
    raw = m.group("value").strip().rstrip(".")
    if "Bytes" in canonical_name:
        b = parse_size_bytes(raw)
        return {"raw": raw, "bytes": b}
    ms = extract_first_duration_ms(raw)
    return {"raw": raw, "ms": ms}


def compact_line(line: str, max_len: int = 320) -> str:
    line = re.sub(r"\s+", " ", line.strip())
    if len(line) > max_len:
        return line[: max_len - 1] + "…"
    return line


def looks_like_cm_runtime_profile(value: str) -> bool:
    lower = value.lower()
    return any(marker.lower() in lower for marker in CM_RUNTIME_PROFILE_MARKERS)


def normalize_profile_text(text: str) -> str:
    """Unwrap CM API JSON responses that store runtime profile text in one field."""
    stripped = text.lstrip()
    if not stripped.startswith("{"):
        return text

    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return text

    if not isinstance(raw, dict):
        return text

    for field in CM_PROFILE_TEXT_FIELDS:
        value = raw.get(field)
        if isinstance(value, str) and looks_like_cm_runtime_profile(value):
            return value
    return text


def parse_estimated_rows_only(window: str) -> float | None:
    m = ESTIMATED_ROWS_ONLY_RE.search(window)
    if not m:
        return None
    return parse_scaled_number(m.group("estimated"))


def parse_rows(window: str) -> tuple[float | None, float | None]:
    for rx in ROWS_PATTERNS:
        m = rx.search(window)
        if m:
            return parse_scaled_number(m.group("actual")), parse_scaled_number(m.group("estimated"))
    return None, None


def parse_memory(window: str) -> tuple[float | None, float | None]:
    for rx in MEM_PATTERNS:
        m = rx.search(window)
        if m:
            return parse_size_bytes(m.group("actual")), parse_size_bytes(m.group("estimated"))
    m = SINGLE_PEAK_MEM_RE.search(window)
    if m:
        return parse_size_bytes(m.group("actual")), None
    return None, None


def parse_operator_table_line(line: str) -> OperatorFact | None:
    """Parse fixed-width Impala operator summary rows.

    Expected columns:
    operator, #Hosts, Avg Time, Max Time, #Rows, Est. #Rows, Peak Mem,
    Est. Peak Mem, Detail.
    """
    stripped = line.strip()
    if not re.match(r"^\d{1,3}\s*:", stripped):
        return None

    parts = TABLE_SEPARATOR_RE.split(stripped, maxsplit=8)
    if len(parts) < 8:
        return None

    op_match = OP_RE.search(parts[0])
    if not op_match:
        return None

    try:
        int(parts[1])
    except ValueError:
        return None

    actual_rows = parse_scaled_number(parts[4])
    estimated_rows = parse_scaled_number(parts[5])
    peak_mem = parse_size_bytes(parts[6])
    estimated_peak_mem = parse_size_bytes(parts[7])
    detail = parts[8] if len(parts) > 8 else ""
    evidence = compact_line(line)
    join_match = JOIN_KIND_RE.search(detail)

    return OperatorFact(
        operator_id=op_match.group("id").zfill(2),
        operator_name=op_match.group("name").upper(),
        time_ms=table_duration_to_ms(parts[3]),
        actual_rows=actual_rows,
        estimated_rows=estimated_rows,
        peak_mem_bytes=peak_mem,
        estimated_peak_mem_bytes=estimated_peak_mem,
        join_kind=(join_match.group("kind").upper() + " JOIN") if join_match else None,
        is_partitioned=bool(re.search(r"\bPARTITIONED\b", detail, re.IGNORECASE)),
        evidence_lines=[evidence],
    )


def update_operator(existing: OperatorFact, new: OperatorFact) -> None:
    def prefer_max(attr: str) -> None:
        old = getattr(existing, attr)
        val = getattr(new, attr)
        if val is None:
            return
        if old is None or val > old:
            setattr(existing, attr, val)

    for attr in ["time_ms", "actual_rows", "estimated_rows", "peak_mem_bytes", "estimated_peak_mem_bytes"]:
        prefer_max(attr)
    if not existing.join_kind and new.join_kind:
        existing.join_kind = new.join_kind
    existing.is_partitioned = existing.is_partitioned or new.is_partitioned
    for line in new.evidence_lines:
        if line not in existing.evidence_lines:
            existing.evidence_lines.append(line)


def line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def parse_raw_counter_number(value: str) -> float | None:
    m = RAW_COUNTER_NUMBER_RE.search(value.strip())
    if not m:
        return None
    raw = m.group("exact") or m.group("display")
    return parse_scaled_number(raw)


def raw_node_section(lines: list[str], start: int) -> str:
    header_indent = line_indent(lines[start])
    section = [lines[start]]
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if not stripped:
            section.append(line)
            continue
        if line_indent(line) <= header_indent and not stripped.startswith("-"):
            break
        section.append(line)
    return "\n".join(section)


def parse_raw_node_section(lines: list[str], start: int) -> OperatorFact | None:
    header = lines[start]
    m = RAW_NODE_HEADER_RE.match(header)
    if not m:
        return None

    op_name = RAW_NODE_NAME_MAP.get(m.group("node"))
    if not op_name:
        return None

    section = raw_node_section(lines, start)
    evidence = [compact_line(header)]

    actual_rows: float | None = None
    for row_match in RAW_ROW_COUNTER_RE.finditer(section):
        value = parse_raw_counter_number(row_match.group("value"))
        if value is not None and (actual_rows is None or value > actual_rows):
            actual_rows = value
            evidence_line = compact_line(row_match.group(0))
            if evidence_line not in evidence:
                evidence.append(evidence_line)

    peak_mem: float | None = None
    for mem_match in RAW_PEAK_MEMORY_RE.finditer(section):
        value = parse_size_bytes(mem_match.group("value"))
        if value is not None and (peak_mem is None or value > peak_mem):
            peak_mem = value
            evidence_line = compact_line(mem_match.group(0))
            if evidence_line not in evidence:
                evidence.append(evidence_line)

    time_ms: float | None = None
    for time_match in RAW_TIME_COUNTER_RE.finditer(section):
        value = extract_first_duration_ms(time_match.group("value"))
        if value is not None and (time_ms is None or value > time_ms):
            time_ms = value
            evidence_line = compact_line(time_match.group(0))
            if evidence_line not in evidence:
                evidence.append(evidence_line)

    return OperatorFact(
        operator_id=m.group("id").zfill(2),
        operator_name=op_name,
        time_ms=time_ms,
        actual_rows=actual_rows,
        peak_mem_bytes=peak_mem,
        evidence_lines=evidence,
    )


def parse_raw_runtime_nodes(lines: list[str]) -> list[OperatorFact]:
    facts: list[OperatorFact] = []
    for i, line in enumerate(lines):
        fact = parse_raw_node_section(lines, i)
        if fact:
            facts.append(fact)
    return facts


def build_operator_windows(lines: list[str], lookahead: int = 3) -> Iterable[tuple[str, str, str]]:
    """Yield (operator_id, operator_name, window_text)."""
    for i, line in enumerate(lines):
        m = OP_RE.search(line)
        if not m:
            continue

        window_parts = [line.strip()]
        for j in range(i + 1, min(len(lines), i + 1 + lookahead)):
            nxt = lines[j]
            if OP_RE.search(nxt):
                break
            stripped = nxt.strip()
            if not stripped:
                break
            if stripped.startswith(("-", "*", "|")) or re.match(
                r"^(Actual|Estimated|Rows|Peak|Exec|Time|Memory|Join|Type|Cardinality)\b",
                stripped,
                flags=re.IGNORECASE,
            ):
                window_parts.append(stripped)
            else:
                break

        yield m.group("id"), m.group("name").upper(), " ".join(window_parts)


def parse_operators(text: str) -> list[OperatorFact]:
    lines = text.splitlines()
    by_key: dict[tuple[str, str], OperatorFact] = {}

    table_line_numbers: set[int] = set()
    for i, line in enumerate(lines):
        fact = parse_operator_table_line(line)
        if not fact:
            continue
        table_line_numbers.add(i)
        key = (fact.operator_id, fact.operator_name)
        if key in by_key:
            update_operator(by_key[key], fact)
        else:
            by_key[key] = fact

    for op_id, op_name, window in build_operator_windows(lines):
        first_line = window.split(" ", 1)[0]
        if any(lines[i].strip().startswith(first_line) for i in table_line_numbers):
            continue

        # Parse duration only from the substring after the operator token.
        op_match = OP_RE.search(window)
        after_op = window[op_match.end() :] if op_match else window

        actual_rows, estimated_rows = parse_rows(window)
        if estimated_rows is None:
            estimated_rows = parse_estimated_rows_only(window)
        peak_mem, est_peak_mem = parse_memory(window)
        join_match = JOIN_KIND_RE.search(window)

        fact = OperatorFact(
            operator_id=op_id.zfill(2),
            operator_name=op_name,
            time_ms=extract_first_duration_ms(after_op),
            actual_rows=actual_rows,
            estimated_rows=estimated_rows,
            peak_mem_bytes=peak_mem,
            estimated_peak_mem_bytes=est_peak_mem,
            join_kind=(join_match.group("kind").upper() + " JOIN") if join_match else None,
            is_partitioned=bool(re.search(r"\bPARTITIONED\b", window, re.IGNORECASE)),
            evidence_lines=[compact_line(window)],
        )

        key = (fact.operator_id, fact.operator_name)
        if key in by_key:
            update_operator(by_key[key], fact)
        else:
            by_key[key] = fact

    for fact in parse_raw_runtime_nodes(lines):
        key = (fact.operator_id, fact.operator_name)
        if key in by_key:
            update_operator(by_key[key], fact)
        else:
            by_key[key] = fact

    return sorted(by_key.values(), key=lambda x: (int(x.operator_id), x.operator_name))


def find_matching_lines(text: str, rx: re.Pattern[str]) -> list[str]:
    return [compact_line(line) for line in text.splitlines() if rx.search(line)]


def line_has_nonzero_metric(line: str) -> bool:
    for m in SIZE_RE.finditer(line):
        val = parse_size_bytes(m.group(0))
        if val and val > 0:
            return True

    # For spill/scratch lines only. Avoid taking operator IDs from all lines.
    number_matches = re.findall(r"(?<![A-Za-z])(?:[:=]\s*)?(\d+(?:\.\d+)?)\b", line)
    for raw in number_matches:
        try:
            if float(raw) > 0:
                return True
        except ValueError:
            pass
    return False


def spill_metric_value(line: str) -> float | None:
    m = SPILL_METRIC_RE.search(line)
    if not m:
        return None
    raw = m.group("value")
    if SIZE_RE.fullmatch(raw.strip()):
        return parse_size_bytes(raw)
    return parse_scaled_number(raw)


def find_nonzero_spill_metric_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        value = spill_metric_value(line)
        if value is not None and value > 0:
            lines.append(compact_line(line))
    return lines


def find_codegen_bottleneck_lines(text: str, total_time_ms: float | None, min_share: float = 0.10) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        m = CODEGEN_TIMING_RE.search(line)
        if not m:
            continue
        codegen_ms = extract_first_duration_ms(m.group("value"))
        if codegen_ms is None or codegen_ms <= 0:
            continue
        if total_time_ms and total_time_ms > 0 and codegen_ms / total_time_ms < min_share:
            continue
        lines.append(compact_line(line))
    return lines


def fmt_duration(ms: float | None) -> str:
    if ms is None:
        return "n/a"
    if ms < 1000:
        return f"{ms:.0f}ms"
    seconds = ms / 1000
    if seconds < 60:
        s = f"{seconds:.3f}".rstrip("0").rstrip(".")
        return f"{s}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.2f}m"
    hours = minutes / 60
    return f"{hours:.2f}h"


def fmt_bytes(value: float | None) -> str:
    if value is None:
        return "n/a"
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    val = float(value)
    for unit in units:
        if abs(val) < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{val:.0f} {unit}"
            return f"{val:.2f} {unit}"
        val /= 1024
    return f"{value:.0f} B"


def fmt_rows(value: float | None) -> str:
    if value is None:
        return "n/a"
    abs_v = abs(value)
    if abs_v >= 1e12:
        return f"{value / 1e12:.2f}T"
    if abs_v >= 1e9:
        return f"{value / 1e9:.2f}B"
    if abs_v >= 1e6:
        return f"{value / 1e6:.2f}M"
    if abs_v >= 1e3:
        return f"{value / 1e3:.2f}K"
    return f"{value:.0f}"


def fmt_ratio(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "n/a"
    if value >= 100:
        return f"{value:.0f}x"
    if value >= 10:
        return f"{value:.1f}x"
    return f"{value:.2f}x"


def md_escape(value: str) -> str:
    return value.replace("|", "\\|")


def rel_path(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def context_file_status(path: Path, case_dir: Path) -> dict[str, Any]:
    return {
        "available": path.exists(),
        "path": rel_path(path, case_dir),
    }


def context_table_file_status(context_dir: Path, case_dir: Path, table: str) -> dict[str, dict[str, Any]]:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", table).strip("._") or "table"
    tables_dir = context_dir / "tables"
    return {
        "SHOW CREATE TABLE": context_file_status(tables_dir / f"{safe_name}.show_create.sql", case_dir),
        "SHOW TABLE STATS": context_file_status(tables_dir / f"{safe_name}.table_stats.txt", case_dir),
        "SHOW COLUMN STATS": context_file_status(tables_dir / f"{safe_name}.column_stats.txt", case_dir),
        "DESCRIBE FORMATTED": context_file_status(tables_dir / f"{safe_name}.describe_formatted.txt", case_dir),
    }


def read_referenced_context_tables(path: Path) -> list[str]:
    if not path.exists():
        return []
    tables: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped not in tables:
            tables.append(stripped)
    return tables


def extract_context_warnings(summary_path: Path) -> list[str]:
    if not summary_path.exists():
        return []
    lines: list[str] = []
    in_warnings = False
    for line in summary_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            in_warnings = "warning" in stripped.lower() or "failure" in stripped.lower()
            continue
        lower = stripped.lower()
        if in_warnings or "warning" in lower or "failed" in lower or "failure" in lower:
            lines.append(compact_line(stripped.lstrip("- ")))
    return dedupe_lines(lines)


def dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out


def collect_impala_context(case_dir: Path) -> dict[str, Any] | None:
    context_dir = case_dir / "impala_context"
    summary_path = context_dir / "impala_context.md"
    if not summary_path.exists():
        return None

    original_query_path = context_dir / "original_query.sql"
    referenced_tables_path = context_dir / "referenced_tables.txt"
    explain_path = context_dir / "explain.txt"
    tables = read_referenced_context_tables(referenced_tables_path)

    return {
        "context_dir": rel_path(context_dir, case_dir),
        "summary": context_file_status(summary_path, case_dir),
        "original_sql": context_file_status(original_query_path, case_dir),
        "referenced_tables_file": context_file_status(referenced_tables_path, case_dir),
        "referenced_tables": tables,
        "explain": context_file_status(explain_path, case_dir),
        "table_metadata": {
            table: context_table_file_status(context_dir, case_dir, table)
            for table in tables
        },
        "warnings": extract_context_warnings(summary_path),
    }


def op_label(op: OperatorFact) -> str:
    flags: list[str] = []
    if op.join_kind:
        flags.append(op.join_kind)
    if op.is_partitioned:
        flags.append("PARTITIONED")
    suffix = f" ({', '.join(flags)})" if flags else ""
    return f"{op.operator_id}:{op.operator_name}{suffix}"


def op_to_json(op: OperatorFact) -> dict[str, Any]:
    return {
        "operator_id": op.operator_id,
        "operator_name": op.operator_name,
        "label": op_label(op),
        "time_ms": op.time_ms,
        "time": fmt_duration(op.time_ms),
        "actual_rows": op.actual_rows,
        "actual_rows_human": fmt_rows(op.actual_rows),
        "estimated_rows": op.estimated_rows,
        "estimated_rows_human": fmt_rows(op.estimated_rows),
        "rows_actual_to_estimated_ratio": op.rows_ratio,
        "rows_ratio_human": fmt_ratio(op.rows_ratio),
        "peak_mem_bytes": op.peak_mem_bytes,
        "peak_mem_human": fmt_bytes(op.peak_mem_bytes),
        "estimated_peak_mem_bytes": op.estimated_peak_mem_bytes,
        "estimated_peak_mem_human": fmt_bytes(op.estimated_peak_mem_bytes),
        "mem_actual_to_estimated_ratio": op.mem_ratio,
        "mem_ratio_human": fmt_ratio(op.mem_ratio),
        "join_kind": op.join_kind,
        "is_partitioned": op.is_partitioned,
        "evidence_lines": op.evidence_lines,
    }


def operator_key(op: dict[str, Any]) -> tuple[str, str]:
    return str(op.get("operator_id", "")), str(op.get("operator_name", ""))


def context_referenced_tables(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("impala_context") or {}
    return list(context.get("referenced_tables") or [])


def context_missing_metadata(analysis: dict[str, Any], command_names: set[str]) -> list[str]:
    context = analysis.get("impala_context") or {}
    missing: list[str] = []
    for table, metadata in (context.get("table_metadata") or {}).items():
        for command_name in command_names:
            status = metadata.get(command_name)
            if status and not status.get("available"):
                missing.append(f"{command_name} for `{table}`")
    return missing


def action_card_score(card: dict[str, Any]) -> float:
    op = card["operator"]
    rows_ratio = op.get("rows_actual_to_estimated_ratio") or 0
    mem_ratio = op.get("mem_actual_to_estimated_ratio") or 0
    actual_rows = op.get("actual_rows") or 0
    peak_mem = op.get("peak_mem_bytes") or 0
    return rows_ratio * 1_000_000_000 + mem_ratio * 1_000_000 + actual_rows + peak_mem / 1024


def build_action_cards(analysis: dict[str, Any], max_cards: int = 5) -> list[dict[str, Any]]:
    thresholds = analysis.get("thresholds", {})
    large_rows_threshold = float(thresholds.get("large_rows_threshold") or 1_000_000)
    large_bytes_threshold = float(thresholds.get("large_bytes_threshold") or 10 * 1024**3)
    total_read = analysis.get("totals", {}).get("TotalBytesRead") or {}
    total_sent = analysis.get("totals", {}).get("TotalBytesSent") or {}
    memory_by_key = {
        operator_key(op): op
        for op in analysis.get("memory_anomalies", [])
    }

    cards: list[dict[str, Any]] = []
    used_keys: set[tuple[str, str]] = set()

    for op in analysis.get("cardinality_anomalies", []):
        if (op.get("rows_actual_to_estimated_ratio") or 0) < 100:
            continue
        if (op.get("actual_rows") or 0) < large_rows_threshold:
            continue
        key = operator_key(op)
        used_keys.add(key)
        related_memory = memory_by_key.get(key)
        cards.append(
            make_action_card(
                "Severe cardinality underestimation before high-cost operator",
                op,
                related_memory=related_memory,
                total_read=total_read,
                total_sent=total_sent,
                large_bytes_threshold=large_bytes_threshold,
                analysis=analysis,
            )
        )

    for op in analysis.get("memory_anomalies", []):
        key = operator_key(op)
        if key in used_keys:
            continue
        mem_ratio = op.get("mem_actual_to_estimated_ratio") or 0
        peak_mem = op.get("peak_mem_bytes") or 0
        if mem_ratio < 10 and peak_mem < large_bytes_threshold:
            continue
        cards.append(
            make_action_card(
                "Severe memory underestimation at high-memory operator",
                op,
                related_memory=op,
                total_read=total_read,
                total_sent=total_sent,
                large_bytes_threshold=large_bytes_threshold,
                analysis=analysis,
            )
        )

    return sorted(cards, key=action_card_score, reverse=True)[:max_cards]


def make_action_card(
    title: str,
    op: dict[str, Any],
    *,
    related_memory: dict[str, Any] | None,
    total_read: dict[str, Any],
    total_sent: dict[str, Any],
    large_bytes_threshold: float,
    analysis: dict[str, Any],
) -> dict[str, Any]:
    evidence = [
        f"operator: {op['label']}",
        f"actual rows: {op['actual_rows_human']}",
        f"estimated rows: {op['estimated_rows_human']}",
        f"actual/estimated ratio: {op['rows_ratio_human']}",
    ]
    if related_memory:
        evidence.extend(
            [
                f"peak memory: {related_memory['peak_mem_human']}",
                f"estimated peak memory: {related_memory['estimated_peak_mem_human']}",
                f"peak/estimated memory ratio: {related_memory['mem_ratio_human']}",
            ]
        )
    if total_read.get("raw"):
        evidence.append(f"TotalBytesRead: {total_read['raw']} ({fmt_bytes(total_read.get('bytes'))})")
    if total_sent.get("raw"):
        evidence.append(f"TotalBytesSent: {total_sent['raw']} ({fmt_bytes(total_sent.get('bytes'))})")

    admin_actions = [
        "Check per-host RowsProduced for this operator.",
        "Check spill/scratch counters for this operator if available in profile.",
    ]
    if related_memory:
        admin_actions.append("Check per-host PeakMemUsage for this operator.")
        admin_actions.append("Check whether admission pool memory limits were hit.")
    if total_sent.get("bytes") and total_sent["bytes"] >= large_bytes_threshold:
        admin_actions.append("Check whether exchange volume matches TotalBytesSent.")

    tables = context_referenced_tables(analysis)
    user_actions: list[str] = []
    if tables:
        user_actions.append(
            "Run SHOW TABLE STATS for referenced tables involved in this query: "
            + ", ".join(f"`{table}`" for table in tables)
            + "."
        )
    else:
        user_actions.append("Run SHOW TABLE STATS for referenced tables involved in this query.")
    user_actions.extend(
        [
            "Run SHOW COLUMN STATS for join/filter columns once join/filter columns are identified.",
            "Check whether the query creates many-to-many JOIN amplification before SORT/ANALYTIC/AGGREGATE.",
            "If stats are missing or stale, refresh stats through the approved operational process, then re-run the query.",
        ]
    )

    missing_evidence = [
        "Exact join/filter keys unless parsed deterministically.",
        "Per-host operator distribution.",
        "Table/column stats freshness unless parsed from context.",
        "Hot key distribution.",
        "Skew is suspected but not proven.",
    ]
    for missing in context_missing_metadata(analysis, {"SHOW TABLE STATS", "SHOW COLUMN STATS"}):
        missing_evidence.append(f"Collector metadata missing: {missing}.")

    return {
        "title": title,
        "operator": op,
        "finding": f"Severe deterministic evidence was detected for {op['label']}.",
        "evidence": evidence,
        "admin_actions": admin_actions,
        "user_actions": user_actions,
        "how_to_verify": [
            "Re-run the query and compare actual vs estimated rows for the same operator.",
            "Compare PeakMemUsage and spill counters before/after.",
            "Compare runtime and bytes sent/read before/after.",
        ],
        "missing_evidence": missing_evidence,
    }


def make_finding(
    finding_id: str,
    severity: str,
    title: str,
    summary: str,
    operators: list[dict[str, Any]] | None = None,
    evidence_lines: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "severity": severity,
        "title": title,
        "summary": summary,
        "operators": operators or [],
        "evidence_lines": evidence_lines or [],
    }


def analyze(text: str, args: argparse.Namespace) -> dict[str, Any]:
    text = normalize_profile_text(text)
    operators = parse_operators(text)
    totals = {
        name: extract_total_counter(text, name)
        for name in ["TotalBytesRead", "TotalBytesSent", "TotalTime"]
    }

    top_by_time = sorted(
        [op for op in operators if op.time_ms is not None],
        key=lambda x: x.time_ms or 0,
        reverse=True,
    )[: args.top_n]
    top_by_memory = sorted(
        [op for op in operators if op.peak_mem_bytes is not None],
        key=lambda x: x.peak_mem_bytes or 0,
        reverse=True,
    )[: args.top_n]

    cardinality_anomalies = sorted(
        [op for op in operators if op.rows_ratio is not None and op.rows_ratio >= args.rows_ratio_threshold],
        key=lambda x: x.rows_ratio or 0,
        reverse=True,
    )
    memory_anomalies = sorted(
        [op for op in operators if op.mem_ratio is not None and op.mem_ratio >= args.mem_ratio_threshold],
        key=lambda x: x.mem_ratio or 0,
        reverse=True,
    )

    join_bottlenecks = [
        op
        for op in operators
        if op.is_join
        and (
            (op.time_ms is not None and op.time_ms >= args.slow_operator_ms)
            or (op.actual_rows is not None and op.actual_rows >= args.large_rows_threshold)
            or op.is_partitioned
            or (op.rows_ratio is not None and op.rows_ratio >= args.rows_ratio_threshold)
        )
    ]
    sort_bottlenecks = [
        op
        for op in operators
        if op.is_sort
        and (
            (op.time_ms is not None and op.time_ms >= args.slow_operator_ms)
            or (op.actual_rows is not None and op.actual_rows >= args.large_rows_threshold)
            or (op.mem_ratio is not None and op.mem_ratio >= args.mem_ratio_threshold)
        )
    ]
    analytic_bottlenecks = [
        op
        for op in operators
        if op.is_analytic
        and (
            (op.time_ms is not None and op.time_ms >= args.slow_operator_ms)
            or (op.actual_rows is not None and op.actual_rows >= args.large_rows_threshold)
        )
    ]

    spill_lines = find_matching_lines(text, SPILL_RE)
    spill_nonzero_lines = find_nonzero_spill_metric_lines(text)
    stats_lines = find_matching_lines(text, re.compile("|".join(p.pattern for p in STATS_PATTERNS), re.IGNORECASE))
    storage_lines = find_matching_lines(text, SCAN_STORAGE_RE)
    codegen_lines = find_matching_lines(text, CODEGEN_RE)

    scan_top_ops = [op for op in top_by_time[:3] if op.is_scan]
    total_time_ms = totals.get("TotalTime", {}).get("ms") if totals.get("TotalTime") else None
    codegen_bottleneck_lines = find_codegen_bottleneck_lines(text, total_time_ms)
    storage_bottleneck_evidence: list[str] = []
    for op in scan_top_ops:
        if op.time_ms is not None and op.time_ms >= args.slow_operator_ms:
            share = None
            if total_time_ms and total_time_ms > 0:
                share = op.time_ms / total_time_ms
            if share is None or share >= 0.10:
                storage_bottleneck_evidence.append(
                    f"{op_label(op)} is among top time operators: {fmt_duration(op.time_ms)}"
                )

    network_exchange_evidence: list[str] = []
    total_sent = totals.get("TotalBytesSent")
    if total_sent and total_sent.get("bytes") and total_sent["bytes"] >= args.large_bytes_threshold:
        network_exchange_evidence.append(
            f"TotalBytesSent is large: {total_sent['raw']} ({fmt_bytes(total_sent['bytes'])})"
        )
    for op in top_by_time[: args.top_n]:
        if "EXCHANGE" in op.operator_name.upper() and op.time_ms is not None:
            network_exchange_evidence.append(
                f"{op_label(op)} has notable time: {fmt_duration(op.time_ms)}"
            )

    findings: list[dict[str, Any]] = []
    not_supported_causes: list[str] = []

    if cardinality_anomalies:
        worst = cardinality_anomalies[0]
        findings.append(
            make_finding(
                "cardinality_estimate_errors",
                "high" if (worst.rows_ratio or 0) >= 100 else "medium",
                "Cardinality estimate errors",
                (
                    f"Detected actual-vs-estimated row count mismatches. Worst parsed ratio: "
                    f"{op_label(worst)} = {fmt_ratio(worst.rows_ratio)} "
                    f"({fmt_rows(worst.actual_rows)} actual vs {fmt_rows(worst.estimated_rows)} estimated)."
                ),
                operators=[op_to_json(op) for op in cardinality_anomalies],
            )
        )
    else:
        not_supported_causes.append(
            "No parsed actual-vs-estimated row count anomaly above threshold; do not claim cardinality estimate errors unless another evidence line supports it."
        )

    if memory_anomalies:
        worst = memory_anomalies[0]
        findings.append(
            make_finding(
                "memory_estimate_errors",
                "high" if (worst.mem_ratio or 0) >= 10 else "medium",
                "Memory estimate errors",
                (
                    f"Detected peak memory above estimated peak memory. Worst parsed ratio: "
                    f"{op_label(worst)} = {fmt_ratio(worst.mem_ratio)} "
                    f"({fmt_bytes(worst.peak_mem_bytes)} peak vs {fmt_bytes(worst.estimated_peak_mem_bytes)} estimated)."
                ),
                operators=[op_to_json(op) for op in memory_anomalies],
            )
        )

    if join_bottlenecks:
        findings.append(
            make_finding(
                "join_bottleneck",
                "high",
                "Join bottleneck",
                "Detected heavy join operators by time, row volume, partitioned join mode, or bad estimates.",
                operators=[op_to_json(op) for op in sorted(join_bottlenecks, key=lambda x: x.time_ms or 0, reverse=True)],
            )
        )

    if sort_bottlenecks:
        findings.append(
            make_finding(
                "sort_bottleneck",
                "medium",
                "Sort bottleneck",
                "Detected expensive SORT/TOP-N operators by time, row volume, or memory estimate mismatch.",
                operators=[op_to_json(op) for op in sorted(sort_bottlenecks, key=lambda x: x.time_ms or 0, reverse=True)],
            )
        )

    if analytic_bottlenecks:
        findings.append(
            make_finding(
                "analytic_bottleneck",
                "medium",
                "Analytic bottleneck",
                "Detected ANALYTIC operators with notable time or row volume.",
                operators=[op_to_json(op) for op in sorted(analytic_bottlenecks, key=lambda x: x.time_ms or 0, reverse=True)],
            )
        )
    elif re.search(r"\bANALYTIC\b", text, re.IGNORECASE):
        findings.append(
            make_finding(
                "analytic_present",
                "info",
                "Analytic present",
                "ANALYTIC operators are mentioned in the digest, but this parser did not extract enough per-operator metrics to rank them.",
            )
        )

    if spill_nonzero_lines:
        findings.append(
            make_finding(
                "spill_or_scratch_io",
                "medium",
                "Spill or scratch I/O",
                "Detected non-zero spill/scratch metric evidence in digest lines.",
                evidence_lines=spill_nonzero_lines,
            )
        )
    else:
        not_supported_causes.append(
            "No non-zero spill/scratch I/O evidence was parsed."
        )

    if storage_bottleneck_evidence:
        findings.append(
            make_finding(
                "hdfs_or_storage_bottleneck",
                "medium",
                "HDFS or storage bottleneck",
                "Detected scan/storage operator evidence among top time operators.",
                evidence_lines=storage_bottleneck_evidence,
            )
        )
    else:
        not_supported_causes.append(
            "No direct HDFS/storage bottleneck evidence was parsed. Large TotalBytesRead is an I/O footprint, not proof that HDFS/block size/replication is the root cause."
        )

    if network_exchange_evidence:
        findings.append(
            make_finding(
                "large_intermediate_or_exchange_traffic",
                "medium",
                "Large intermediate or exchange traffic",
                "Detected large bytes sent / exchange footprint. Treat as intermediate data movement evidence, not automatically as a network fault.",
                evidence_lines=network_exchange_evidence,
            )
        )
    else:
        not_supported_causes.append(
            "No large exchange/network traffic evidence was parsed from TotalBytesSent or EXCHANGE operators."
        )

    if codegen_bottleneck_lines:
        findings.append(
            make_finding(
                "codegen_bottleneck",
                "medium",
                "Codegen bottleneck",
                "Detected codegen/LLVM timing evidence large enough to be treated as a bottleneck.",
                evidence_lines=codegen_bottleneck_lines[: args.max_evidence_lines],
            )
        )
    else:
        not_supported_causes.append(
            "No codegen/LLVM bottleneck evidence was parsed."
        )

    not_supported_causes.append(
        "No evidence in profile_digest.md supports HDFS block-size or replication-factor changes as a query-level fix unless scan/storage counters from the raw profile prove it."
    )
    not_supported_causes.append(
        "No evidence in profile_digest.md supports blaming external network instability; large TotalBytesSent only shows data movement volume."
    )

    return {
        "thresholds": {
            "rows_ratio_threshold": args.rows_ratio_threshold,
            "mem_ratio_threshold": args.mem_ratio_threshold,
            "slow_operator_ms": args.slow_operator_ms,
            "large_rows_threshold": args.large_rows_threshold,
            "large_bytes_threshold": args.large_bytes_threshold,
            "report_top_n": args.top_n,
        },
        "totals": totals,
        "operators": [op_to_json(op) for op in operators],
        "top_operators_by_time": [op_to_json(op) for op in top_by_time],
        "top_operators_by_peak_memory": [op_to_json(op) for op in top_by_memory],
        "cardinality_anomalies": [op_to_json(op) for op in cardinality_anomalies],
        "memory_anomalies": [op_to_json(op) for op in memory_anomalies],
        "stats_evidence_lines": stats_lines[: args.max_evidence_lines],
        "spill_evidence_lines": spill_lines[: args.max_evidence_lines],
        "spill_nonzero_evidence_lines": spill_nonzero_lines[: args.max_evidence_lines],
        "storage_evidence_lines": storage_lines[: args.max_evidence_lines],
        "codegen_evidence_lines": codegen_lines[: args.max_evidence_lines],
        "findings": findings,
        "not_supported_causes": not_supported_causes,
    }


def render_operator_table(title: str, rows: list[dict[str, Any]], max_rows: int | None = None) -> list[str]:
    out = [f"## {title}", ""]
    if not rows:
        out += ["No parsed operators in this category.", ""]
        return out
    visible_rows = rows[:max_rows] if max_rows is not None else rows
    out.append(
        "| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |"
    )
    out.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for op in visible_rows:
        out.append(
            "| "
            + " | ".join(
                [
                    md_escape(op["label"]),
                    op["time"],
                    op["actual_rows_human"],
                    op["estimated_rows_human"],
                    op["rows_ratio_human"],
                    op["peak_mem_human"],
                    op["estimated_peak_mem_human"],
                    op["mem_ratio_human"],
                ]
            )
            + " |"
        )
    if len(visible_rows) < len(rows):
        out.append(f"| ... {len(rows) - len(visible_rows)} more in verbose output |  |  |  |  |  |  |  |")
    out.append("")
    return out


def render_summary(analysis: dict[str, Any]) -> list[str]:
    return [
        "## Summary",
        "",
        f"- Parsed operators: {len(analysis['operators'])}",
        f"- Cardinality anomalies: {len(analysis['cardinality_anomalies'])}",
        f"- Memory anomalies: {len(analysis['memory_anomalies'])}",
        "",
    ]


def render_action_cards(analysis: dict[str, Any]) -> list[str]:
    lines = ["## Action Cards", ""]
    cards = analysis.get("action_cards") or []
    if not cards:
        lines.append("No deterministic action cards were triggered from the parsed evidence.")
        lines.append("")
        return lines

    for i, card in enumerate(cards, start=1):
        lines.append(f"### Card {i}: {card['title']}")
        lines.append("")
        lines.append("Finding:")
        lines.append(f"- {card['finding']}")
        lines.append("")
        lines.append("Evidence:")
        for item in card["evidence"]:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("Admin actions:")
        for item in card["admin_actions"]:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("User actions:")
        for item in card["user_actions"]:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("How to verify:")
        for item in card["how_to_verify"]:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("Missing evidence:")
        for item in card["missing_evidence"]:
            lines.append(f"- {item}")
        lines.append("")
    return lines


def render_findings(analysis: dict[str, Any], verbose: bool) -> list[str]:
    lines = ["## Findings", ""]
    if not analysis["findings"]:
        lines.append("No deterministic findings were produced from the digest.")
        lines.append("")
        return lines

    for finding in analysis["findings"]:
        heading = finding.get("title") or finding["id"]
        lines.append(f"### {heading} [{finding['severity']}]")
        lines.append("")
        lines.append(f"- {finding['summary']}")
        if finding.get("operators"):
            operators = finding["operators"] if verbose else finding["operators"][:5]
            lines.append("- Operators:")
            for op in operators:
                lines.append(
                    f"  - {op['label']}: time={op['time']}, "
                    f"rows={op['actual_rows_human']} vs est {op['estimated_rows_human']} "
                    f"({op['rows_ratio_human']}), mem={op['peak_mem_human']} vs est "
                    f"{op['estimated_peak_mem_human']} ({op['mem_ratio_human']})"
                )
            if not verbose and len(finding["operators"]) > len(operators):
                lines.append(f"  - ... {len(finding['operators']) - len(operators)} more in verbose output")
        if verbose and finding.get("evidence_lines"):
            lines.append("- Evidence lines:")
            for ev in finding["evidence_lines"]:
                lines.append(f"  - `{ev}`")
        lines.append("")
    return lines


def render_verbose_evidence(analysis: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if analysis.get("stats_evidence_lines"):
        lines.append("## Stats/cardinality-related lines from digest")
        lines.append("")
        for line in analysis["stats_evidence_lines"]:
            lines.append(f"- `{line}`")
        lines.append("")

    if analysis.get("spill_evidence_lines"):
        lines.append("## Spill/scratch-related lines from digest")
        lines.append("")
        for line in analysis["spill_evidence_lines"]:
            lines.append(f"- `{line}`")
        lines.append("")

    if analysis.get("codegen_evidence_lines"):
        lines.append("## Codegen/LLVM mention lines from digest")
        lines.append("")
        for line in analysis["codegen_evidence_lines"]:
            lines.append(f"- `{line}`")
        lines.append("")

    lines.append("## Parsed operator evidence")
    lines.append("")
    for op in analysis["operators"]:
        lines.append(
            f"- {op['label']}: rows={op['actual_rows_human']} vs est {op['estimated_rows_human']} "
            f"({op['rows_ratio_human']}), mem={op['peak_mem_human']} vs est "
            f"{op['estimated_peak_mem_human']} ({op['mem_ratio_human']})"
        )
        for ev in op.get("evidence_lines", []):
            lines.append(f"  - `{ev}`")
    lines.append("")
    return lines


def availability_label(item: dict[str, Any]) -> str:
    return "available" if item.get("available") else "missing"


def render_impala_context(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("impala_context")
    if not context:
        return []

    lines = ["## Impala Context", ""]
    original_sql = context["original_sql"]
    lines.extend(
        [
            "### Original SQL",
            "",
            f"- present: {'yes' if original_sql['available'] else 'no'}",
            f"- path: `{original_sql['path']}`",
            "",
            "### Referenced Tables",
            "",
        ]
    )

    tables = context.get("referenced_tables") or []
    if tables:
        lines.extend(f"- `{table}`" for table in tables)
    else:
        lines.append("- none parsed")
    lines.append("")

    lines.extend(["### Collected Metadata", ""])
    explain = context["explain"]
    lines.append(f"- EXPLAIN: {availability_label(explain)} (`{explain['path']}`)")
    for table in tables:
        lines.append(f"- `{table}`:")
        for command, status in context["table_metadata"].get(table, {}).items():
            lines.append(f"  - {command}: {availability_label(status)} (`{status['path']}`)")
    lines.append("")

    lines.extend(["### Collector Warnings / Failures", ""])
    warnings = context.get("warnings") or []
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none found in collector summary")
    lines.append("")
    return lines


def render_md(analysis: dict[str, Any], source_path: Path, verbose: bool = False) -> str:
    totals = analysis["totals"]
    lines: list[str] = []
    lines.append("# Query Doctor deterministic analysis facts")
    lines.append("")
    lines.append(f"Source digest: `{source_path}`")
    lines.append("")
    lines.append("> This file is generated by deterministic parsing/rules. The LLM report writer must not add facts that are absent here.")
    lines.append("")

    lines.append("## Totals")
    lines.append("")
    for key in ["TotalTime", "TotalBytesRead", "TotalBytesSent"]:
        item = totals.get(key)
        if not item:
            lines.append(f"- {key}: not parsed")
            continue
        if key == "TotalTime":
            lines.append(f"- {key}: {item.get('raw')} ({fmt_duration(item.get('ms'))})")
        else:
            lines.append(f"- {key}: {item.get('raw')} ({fmt_bytes(item.get('bytes'))})")
    lines.append("")

    lines += render_summary(analysis)
    report_top_n = int(analysis.get("thresholds", {}).get("report_top_n", 10))
    max_table_rows = None if verbose else report_top_n
    lines += render_operator_table("Top operators by time", analysis["top_operators_by_time"])
    lines += render_operator_table("Actual rows vs estimated rows anomalies", analysis["cardinality_anomalies"], max_table_rows)
    lines += render_operator_table("Peak memory vs estimated memory anomalies", analysis["memory_anomalies"], max_table_rows)

    lines += render_impala_context(analysis)
    lines += render_action_cards(analysis)

    lines += render_findings(analysis, verbose)

    lines.append("## What is NOT supported by the parsed evidence")
    lines.append("")
    for cause in analysis["not_supported_causes"]:
        lines.append(f"- {cause}")
    lines.append("")

    if verbose:
        lines += render_operator_table("Top operators by peak memory", analysis["top_operators_by_peak_memory"])
        lines += render_verbose_evidence(analysis)
    return "\n".join(lines)


def resolve_paths(input_path: Path, output_arg: str | None) -> tuple[Path, Path]:
    if input_path.is_dir():
        digest_path = input_path / "profile_digest.md"
        default_output = input_path / "analysis_facts.md"
    else:
        digest_path = input_path
        default_output = input_path.with_name("analysis_facts.md")
    output_path = Path(output_arg).expanduser() if output_arg else default_output
    return digest_path, output_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministically analyze an Impala profile_digest.md and write analysis_facts.md."
    )
    parser.add_argument(
        "input",
        help="Case directory containing profile_digest.md, or path to profile_digest.md",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output markdown file. Default: <case-dir>/analysis_facts.md",
    )
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--rows-ratio-threshold", type=float, default=10.0)
    parser.add_argument("--mem-ratio-threshold", type=float, default=4.0)
    parser.add_argument("--slow-operator-ms", type=float, default=10_000.0)
    parser.add_argument("--large-rows-threshold", type=float, default=1_000_000.0)
    parser.add_argument("--large-bytes-threshold", type=float, default=10 * 1024**3)
    parser.add_argument("--max-evidence-lines", type=int, default=30)
    parser.add_argument("--verbose", action="store_true", help="Include raw evidence lines and parsing details in markdown")
    parser.add_argument("--stdout", action="store_true", help="Also print markdown to stdout")
    parser.add_argument(
        "--json",
        nargs="?",
        const="-",
        metavar="PATH",
        help="Write machine-readable JSON to stdout, or to PATH if provided",
    )
    parser.add_argument(
        "--fail-on-empty",
        action="store_true",
        help="Exit with non-zero status if no operators were parsed",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    input_path = Path(args.input).expanduser()
    digest_path, output_path = resolve_paths(input_path, args.output)

    if not digest_path.exists():
        print(f"ERROR: digest not found: {digest_path}", file=sys.stderr)
        return 2

    text = digest_path.read_text(encoding="utf-8", errors="replace")
    analysis = analyze(text, args)
    analysis["impala_context"] = collect_impala_context(digest_path.parent)
    analysis["action_cards"] = build_action_cards(analysis)

    if args.fail_on_empty and not analysis["operators"]:
        print("ERROR: no operators parsed from digest", file=sys.stderr)
        return 3

    markdown = render_md(analysis, digest_path, verbose=args.verbose)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    json_text = json.dumps(analysis, ensure_ascii=False, indent=2)
    if args.json and args.json != "-":
        json_path = Path(args.json).expanduser()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json_text + "\n", encoding="utf-8")
    else:
        json_path = None

    status_stream = sys.stderr if args.json == "-" else sys.stdout
    print(f"Wrote: {output_path}", file=status_stream)
    if json_path:
        print(f"Wrote JSON: {json_path}", file=status_stream)
    print(f"Parsed operators: {len(analysis['operators'])}", file=status_stream)
    print(f"Cardinality anomalies: {len(analysis['cardinality_anomalies'])}", file=status_stream)
    print(f"Memory anomalies: {len(analysis['memory_anomalies'])}", file=status_stream)

    if args.stdout:
        print()
        print(markdown)
    if args.json == "-":
        try:
            print(json_text)
        except BrokenPipeError:
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
