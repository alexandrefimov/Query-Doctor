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

from table_metadata_facts import collect_table_metadata_context


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

NUMBER_PATTERN = r"\d[\d,]*(?:\.\d+)?(?:[eE][+-]?\d+)?"

SIZE_RE = re.compile(
    rf"(?P<value>{NUMBER_PATTERN})\s*(?P<unit>KiB|MiB|GiB|TiB|KB|MB|GB|TB|B)\b",
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

ROW_NUMBER = rf"{NUMBER_PATTERN}\s*[KMBT]?"
SIZE_PATTERN = rf"{NUMBER_PATTERN}\s*(?:KiB|MiB|GiB|TiB|KB|MB|GB|TB|B)"

TABLE_SEPARATOR_RE = re.compile(r"\s{2,}")
SQL_IDENTIFIER_RE = re.compile(r"`[^`]+`|[A-Za-z_][A-Za-z0-9_$]*")
SQL_TOKEN_RE = re.compile(r"`[^`]+`|[A-Za-z_][A-Za-z0-9_$]*|[(),.;]")
SQL_FROM_STOP_WORDS = {
    "where",
    "group",
    "having",
    "order",
    "limit",
    "union",
    "except",
    "intersect",
    "on",
    "qualify",
    "window",
    "cluster",
    "distribute",
    "sort",
}

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
MEDIUM_DATA_MOVEMENT_BYTES = 1024**3
DEFAULT_LARGE_BYTES_THRESHOLD = 10 * 1024**3
BACKEND_MIN_HOSTS_FOR_SKEW = 3
BACKEND_DATA_SKEW_RATIO = 3.0
BACKEND_WORK_COMPARABLE_RATIO = 1.5
BACKEND_TAIL_RATIO = 3.0
BACKEND_EXECUTION_TAIL_RATIO = 1.8
BACKEND_EXECUTION_TAIL_MIN_MS = 10 * 60 * 1000
BACKEND_EXECUTION_TAIL_MIN_GAP_MS = 10 * 60 * 1000
BACKEND_EXECUTION_TAIL_HIGH_MS = 30 * 60 * 1000
BACKEND_EXECUTION_TAIL_HIGH_GAP_MS = 15 * 60 * 1000

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
    r"-\s*(?:TotalTime|ExecTime)\s*:\s*(?P<value>[^\n\r]+)",
    flags=re.IGNORECASE,
)
RAW_COUNTER_NUMBER_RE = re.compile(
    rf"(?P<display>{NUMBER_PATTERN}\s*[KMBT]?)(?:\s*\((?P<exact>{NUMBER_PATTERN})\))?",
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
    rf"\b(?P<name>SpilledBytes|BytesSpilled|MemorySpilled|MemorySpilledBytes|"
    rf"ScratchBytesWritten|ScratchBytesRead|PeakScratch|SpilledPartitions)\b"
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
BACKEND_HEADER_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:Backend|Executor|Fragment\s+Instance|Instance)\b(?P<header>.*)$",
    re.IGNORECASE,
)
HOST_VALUE_RE = re.compile(
    r"\b(?:host|hostname|executor|backend)\s*[=:]\s*(?P<host>[A-Za-z0-9_.:-]+)",
    re.IGNORECASE,
)
HOST_LINE_RE = re.compile(r"^\s*-?\s*(?:host|hostname)\s*[:=]\s*(?P<host>[A-Za-z0-9_.:-]+)", re.IGNORECASE)
FRAGMENT_VALUE_RE = re.compile(
    r"\b(?:fragment(?:\s+instance)?|instance|fragment_instance)\s*(?:id)?\s*[=:]\s*(?P<fragment>[A-Za-z0-9_.:-]+)",
    re.IGNORECASE,
)
INSTANCE_HEADER_ID_RE = re.compile(r"^\s*(?P<fragment>[A-Za-z0-9_.:-]+)")
AVERAGED_FRAGMENT_RE = re.compile(r"^\s*Averaged\s+Fragment\s+(?P<fragment>F\d+)\b", re.IGNORECASE)
FRAGMENT_HEADER_RE = re.compile(r"^\s*Fragment\s+(?P<fragment>F\d+)\b", re.IGNORECASE)
FRAGMENT_LINE_RE = re.compile(
    r"^\s*-?\s*(?:fragment(?:\s+instance)?|instance|fragment_instance)\s*(?:id)?\s*[:=]\s*(?P<fragment>[A-Za-z0-9_.:-]+)",
    re.IGNORECASE,
)
METRIC_LINE_RE = re.compile(r"^\s*-?\s*(?P<key>[A-Za-z][A-Za-z0-9 _./-]*?)\s*[:=]\s*(?P<value>.+?)\s*$")

BACKEND_ASSIGNED_KEYS = {"scanbytesassigned", "assignedscanbytes", "assignedbytes", "bytesassigned", "scanrangebytes"}
BACKEND_BYTES_READ_KEYS = {"bytesread", "totalbytesread", "hdfsbytesread"}
BACKEND_BYTES_WRITTEN_KEYS = {"byteswritten", "hdfsbyteswritten", "hdfswrittenbytes", "writeiobytes"}
BACKEND_ROWS_KEYS = {"rowsproduced", "rowsread", "rowsreturned"}
BACKEND_READ_RATE_KEYS = {"readrate", "bytesreadrate", "hdfsreadrate", "scanrate"}
BACKEND_WRITE_RATE_KEYS = {"writerate", "byteswrittenrate", "hdfswriterate"}
BACKEND_WRITE_TIME_KEYS = {"hdfswritetime", "hdfswritewallclocktime", "writetime", "writewallclocktime"}
BACKEND_WRITE_SEC_PER_GIB_KEYS = {
    "hdfswritesecpergb",
    "hdfswritesecpergib",
    "writesecpergb",
    "writesecpergib",
}
BACKEND_SCANNER_WAIT_KEYS = {"scannerwaittime", "scannerwaitwallclocktime", "scannerthreadswaittime"}
BACKEND_MATERIALIZE_KEYS = {"materializetime", "materializewallclocktime"}
BACKEND_PARSE_KEYS = {"parsetime", "parsewallclocktime"}
BACKEND_SCANNER_CONCURRENCY_KEYS = {"peakscannerconcurrency", "numscannerthreads", "scannerthreadspeak"}
BACKEND_EXECUTION_TIME_KEYS = {"executiontime", "exectime", "totaltime", "backendtime", "donetime", "runtime"}


@dataclass
class OperatorObservation:
    time_ms: float | None = None
    actual_rows: float | None = None
    estimated_rows: float | None = None
    peak_mem_bytes: float | None = None
    estimated_peak_mem_bytes: float | None = None
    evidence_lines: list[str] = field(default_factory=list)


def observation_rows_ratio(observation: OperatorObservation) -> float | None:
    if (
        observation.actual_rows is None
        or observation.estimated_rows is None
        or observation.estimated_rows <= 0
    ):
        return None
    return observation.actual_rows / observation.estimated_rows


def observation_mem_ratio(observation: OperatorObservation) -> float | None:
    if (
        observation.peak_mem_bytes is None
        or observation.estimated_peak_mem_bytes is None
        or observation.estimated_peak_mem_bytes <= 0
    ):
        return None
    return observation.peak_mem_bytes / observation.estimated_peak_mem_bytes


def observation_has_zero_row_estimate_gap(observation: OperatorObservation) -> bool:
    return (
        observation.actual_rows is not None
        and observation.actual_rows > 0
        and observation.estimated_rows is not None
        and observation.estimated_rows <= 0
    )


def observation_has_zero_memory_estimate_gap(observation: OperatorObservation) -> bool:
    return (
        observation.peak_mem_bytes is not None
        and observation.peak_mem_bytes > 0
        and observation.estimated_peak_mem_bytes is not None
        and observation.estimated_peak_mem_bytes <= 0
    )


def observation_has_row_pair(observation: OperatorObservation) -> bool:
    return observation.actual_rows is not None and observation.estimated_rows is not None


def observation_has_memory_pair(observation: OperatorObservation) -> bool:
    return observation.peak_mem_bytes is not None and observation.estimated_peak_mem_bytes is not None


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
    observations: list[OperatorObservation] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.observations:
            self.observations.append(
                OperatorObservation(
                    time_ms=self.time_ms,
                    actual_rows=self.actual_rows,
                    estimated_rows=self.estimated_rows,
                    peak_mem_bytes=self.peak_mem_bytes,
                    estimated_peak_mem_bytes=self.estimated_peak_mem_bytes,
                    evidence_lines=list(self.evidence_lines),
                )
            )

    def best_rows_observation(self) -> OperatorObservation | None:
        candidates = [
            observation
            for observation in self.observations
            if observation_rows_ratio(observation) is not None
        ]
        if not candidates and not any(observation_has_row_pair(observation) for observation in self.observations):
            fallback = OperatorObservation(
                time_ms=self.time_ms,
                actual_rows=self.actual_rows,
                estimated_rows=self.estimated_rows,
                peak_mem_bytes=self.peak_mem_bytes,
                estimated_peak_mem_bytes=self.estimated_peak_mem_bytes,
                evidence_lines=list(self.evidence_lines),
            )
            if observation_rows_ratio(fallback) is not None:
                candidates.append(fallback)
        if not candidates:
            return None
        return max(candidates, key=lambda observation: observation_rows_ratio(observation) or 0)

    def best_memory_observation(self) -> OperatorObservation | None:
        candidates = [
            observation
            for observation in self.observations
            if observation_mem_ratio(observation) is not None
        ]
        if not candidates and not any(observation_has_memory_pair(observation) for observation in self.observations):
            fallback = OperatorObservation(
                time_ms=self.time_ms,
                actual_rows=self.actual_rows,
                estimated_rows=self.estimated_rows,
                peak_mem_bytes=self.peak_mem_bytes,
                estimated_peak_mem_bytes=self.estimated_peak_mem_bytes,
                evidence_lines=list(self.evidence_lines),
            )
            if observation_mem_ratio(fallback) is not None:
                candidates.append(fallback)
        if not candidates:
            return None
        return max(candidates, key=lambda observation: observation_mem_ratio(observation) or 0)

    def best_zero_row_estimate_gap_observation(self) -> OperatorObservation | None:
        candidates = [
            observation
            for observation in self.observations
            if observation_has_zero_row_estimate_gap(observation)
        ]
        if not candidates and not any(observation_has_row_pair(observation) for observation in self.observations):
            fallback = OperatorObservation(
                time_ms=self.time_ms,
                actual_rows=self.actual_rows,
                estimated_rows=self.estimated_rows,
                peak_mem_bytes=self.peak_mem_bytes,
                estimated_peak_mem_bytes=self.estimated_peak_mem_bytes,
                evidence_lines=list(self.evidence_lines),
            )
            if observation_has_zero_row_estimate_gap(fallback):
                candidates.append(fallback)
        if not candidates:
            return None
        return max(candidates, key=lambda observation: observation.actual_rows or 0)

    def best_zero_memory_estimate_gap_observation(self) -> OperatorObservation | None:
        candidates = [
            observation
            for observation in self.observations
            if observation_has_zero_memory_estimate_gap(observation)
        ]
        if not candidates and not any(observation_has_memory_pair(observation) for observation in self.observations):
            fallback = OperatorObservation(
                time_ms=self.time_ms,
                actual_rows=self.actual_rows,
                estimated_rows=self.estimated_rows,
                peak_mem_bytes=self.peak_mem_bytes,
                estimated_peak_mem_bytes=self.estimated_peak_mem_bytes,
                evidence_lines=list(self.evidence_lines),
            )
            if observation_has_zero_memory_estimate_gap(fallback):
                candidates.append(fallback)
        if not candidates:
            return None
        return max(candidates, key=lambda observation: observation.peak_mem_bytes or 0)

    @property
    def rows_ratio(self) -> float | None:
        observation = self.best_rows_observation()
        if observation is None:
            return None
        return observation_rows_ratio(observation)

    @property
    def mem_ratio(self) -> float | None:
        observation = self.best_memory_observation()
        if observation is None:
            return None
        return observation_mem_ratio(observation)

    @property
    def has_zero_row_estimate_gap(self) -> bool:
        return self.best_zero_row_estimate_gap_observation() is not None

    @property
    def has_zero_memory_estimate_gap(self) -> bool:
        return self.best_zero_memory_estimate_gap_observation() is not None

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


@dataclass
class BackendHostFact:
    host: str
    fragment_instance: str | None = None
    fragment_group: str | None = None
    scan_bytes_assigned: float | None = None
    bytes_read: float | None = None
    bytes_written: float | None = None
    rows_produced: float | None = None
    read_rate_bps: float | None = None
    write_rate_bps: float | None = None
    hdfs_write_time_ms: float | None = None
    hdfs_write_sec_per_gib: float | None = None
    scanner_wait_time_ms: float | None = None
    materialize_time_ms: float | None = None
    parse_time_ms: float | None = None
    peak_scanner_concurrency: float | None = None
    execution_time_ms: float | None = None
    evidence_lines: list[str] = field(default_factory=list)

    def has_metric(self) -> bool:
        return any(
            value is not None
            for value in (
                self.scan_bytes_assigned,
                self.bytes_read,
                self.bytes_written,
                self.rows_produced,
                self.read_rate_bps,
                self.write_rate_bps,
                self.hdfs_write_time_ms,
                self.hdfs_write_sec_per_gib,
                self.scanner_wait_time_ms,
                self.materialize_time_ms,
                self.parse_time_ms,
                self.peak_scanner_concurrency,
                self.execution_time_ms,
            )
        )


def parse_scaled_number(value: str) -> float | None:
    s = value.strip().replace(" ", "")
    m = re.fullmatch(rf"(?P<num>{NUMBER_PATTERN})(?P<suffix>[KMBT])?", s, flags=re.IGNORECASE)
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


def parse_rate_bytes_per_sec(value: str) -> float | None:
    size_match = SIZE_RE.search(value)
    if not size_match:
        return None
    bytes_value = parse_size_bytes(size_match.group(0))
    if bytes_value is None:
        return None
    tail = value[size_match.end() :]
    unit_match = re.search(r"/\s*(?P<unit>ms|msec|s|sec|second|seconds)\b", tail, re.IGNORECASE)
    if not unit_match:
        return None
    unit = unit_match.group("unit").lower()
    if unit in {"ms", "msec"}:
        return bytes_value * 1000
    return bytes_value


def parse_seconds_per_gib(value: str) -> float | None:
    duration_ms = extract_first_duration_ms(value)
    if duration_ms is not None:
        return duration_ms / 1000
    number = parse_scaled_number(value)
    return number


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
    existing.observations.extend(new.observations)
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
        if RAW_NODE_HEADER_RE.match(line):
            break
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


def normalize_metric_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", key.lower())


def append_backend_evidence(fact: BackendHostFact, line: str) -> None:
    evidence = compact_line(line)
    if evidence not in fact.evidence_lines:
        fact.evidence_lines.append(evidence)


def first_number(value: str) -> float | None:
    m = re.search(r"\d[\d,]*(?:\.\d+)?", value)
    if not m:
        return None
    return float(m.group(0).replace(",", ""))


def set_backend_metric(fact: BackendHostFact, key: str, value: str, line: str) -> None:
    normalized_key = normalize_metric_key(key)
    if normalized_key in BACKEND_ASSIGNED_KEYS:
        parsed = parse_size_bytes(value)
        if parsed is not None:
            fact.scan_bytes_assigned = parsed
            append_backend_evidence(fact, line)
    elif normalized_key in BACKEND_BYTES_READ_KEYS:
        parsed = parse_size_bytes(value)
        if parsed is not None:
            fact.bytes_read = parsed
            append_backend_evidence(fact, line)
    elif normalized_key in BACKEND_BYTES_WRITTEN_KEYS:
        parsed = parse_size_bytes(value)
        if parsed is not None:
            fact.bytes_written = parsed
            append_backend_evidence(fact, line)
    elif normalized_key in BACKEND_ROWS_KEYS:
        parsed = parse_raw_counter_number(value)
        if parsed is not None:
            fact.rows_produced = parsed
            append_backend_evidence(fact, line)
    elif normalized_key in BACKEND_READ_RATE_KEYS:
        parsed = parse_rate_bytes_per_sec(value)
        if parsed is not None:
            fact.read_rate_bps = parsed
            append_backend_evidence(fact, line)
    elif normalized_key in BACKEND_WRITE_RATE_KEYS:
        parsed = parse_rate_bytes_per_sec(value)
        if parsed is not None:
            fact.write_rate_bps = parsed
            append_backend_evidence(fact, line)
    elif normalized_key in BACKEND_WRITE_TIME_KEYS:
        parsed = extract_first_duration_ms(value)
        if parsed is not None:
            fact.hdfs_write_time_ms = parsed
            append_backend_evidence(fact, line)
    elif normalized_key in BACKEND_WRITE_SEC_PER_GIB_KEYS:
        parsed = parse_seconds_per_gib(value)
        if parsed is not None:
            fact.hdfs_write_sec_per_gib = parsed
            append_backend_evidence(fact, line)
    elif normalized_key in BACKEND_SCANNER_WAIT_KEYS:
        parsed = extract_first_duration_ms(value)
        if parsed is not None:
            fact.scanner_wait_time_ms = parsed
            append_backend_evidence(fact, line)
    elif normalized_key in BACKEND_MATERIALIZE_KEYS:
        parsed = extract_first_duration_ms(value)
        if parsed is not None:
            fact.materialize_time_ms = parsed
            append_backend_evidence(fact, line)
    elif normalized_key in BACKEND_PARSE_KEYS:
        parsed = extract_first_duration_ms(value)
        if parsed is not None:
            fact.parse_time_ms = parsed
            append_backend_evidence(fact, line)
    elif normalized_key in BACKEND_SCANNER_CONCURRENCY_KEYS:
        parsed = first_number(value)
        if parsed is not None:
            fact.peak_scanner_concurrency = parsed
            append_backend_evidence(fact, line)
    elif normalized_key in BACKEND_EXECUTION_TIME_KEYS:
        parsed = extract_first_duration_ms(value)
        if parsed is not None:
            fact.execution_time_ms = parsed
            append_backend_evidence(fact, line)


def extract_host_from_text(text: str) -> str | None:
    m = HOST_VALUE_RE.search(text)
    if not m:
        return None
    return m.group("host").strip(" ,;")


def extract_fragment_from_text(text: str) -> str | None:
    m = FRAGMENT_VALUE_RE.search(text)
    if m:
        return m.group("fragment").strip(" ,;")
    m = INSTANCE_HEADER_ID_RE.search(text)
    if not m:
        return None
    return m.group("fragment").strip(" ,;")


def parse_backend_host_facts(text: str) -> list[BackendHostFact]:
    facts: list[BackendHostFact] = []
    current: BackendHostFact | None = None
    current_fragment_group: str | None = None

    def finish_current() -> None:
        nonlocal current
        if current is not None and current.host and current.has_metric():
            if current.hdfs_write_sec_per_gib is None and current.hdfs_write_time_ms and current.bytes_written:
                gib = current.bytes_written / (1024**3)
                if gib > 0:
                    current.hdfs_write_sec_per_gib = (current.hdfs_write_time_ms / 1000) / gib
            facts.append(current)
        current = None

    for line in text.splitlines():
        fragment_match = AVERAGED_FRAGMENT_RE.match(line) or FRAGMENT_HEADER_RE.match(line)
        if fragment_match:
            current_fragment_group = fragment_match.group("fragment").upper()

        header_match = BACKEND_HEADER_RE.match(line)
        if header_match:
            finish_current()
            header = header_match.group("header") or ""
            host = extract_host_from_text(header)
            fragment = extract_fragment_from_text(header)
            if host:
                current = BackendHostFact(
                    host=host,
                    fragment_instance=fragment,
                    fragment_group=current_fragment_group,
                    evidence_lines=[compact_line(line)],
                )
            else:
                current = None
            continue

        if current is None:
            continue

        host_line = HOST_LINE_RE.match(line)
        if host_line:
            current.host = host_line.group("host").strip(" ,;")
            append_backend_evidence(current, line)
            continue

        fragment_line = FRAGMENT_LINE_RE.match(line)
        if fragment_line:
            current.fragment_instance = fragment_line.group("fragment").strip(" ,;")
            append_backend_evidence(current, line)
            continue

        metric_match = METRIC_LINE_RE.match(line)
        if metric_match:
            set_backend_metric(current, metric_match.group("key"), metric_match.group("value"), line)

    finish_current()
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


def fmt_rate(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{fmt_bytes(value)}/s"


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


def normalize_sql(sql: str) -> str:
    return sql.strip().rstrip(";") + "\n"


def profile_digest_text_candidates(profile_digest_text: str) -> list[str]:
    candidates = [profile_digest_text]
    try:
        payload = json.loads(profile_digest_text)
    except json.JSONDecodeError:
        return candidates
    if isinstance(payload, dict):
        details = payload.get("details")
        if isinstance(details, str) and details and details != profile_digest_text:
            candidates.append(details)
    return candidates


def extract_labeled_sql_statement(text: str) -> str | None:
    label_match = re.search(
        r"(?ims)^\s*(?:Sql|SQL)\s+Statement\s*:\s*"
        r"(?P<sql>(?:WITH|SELECT|INSERT)\b.*?)(?=\n\s{2,}[A-Z][A-Za-z0-9 /_-]{1,80}:\s|\n\s*$|\Z)",
        text,
    )
    if label_match:
        return normalize_sql(label_match.group("sql"))

    query_match = re.search(
        r"(?ims)\bquery\(\)\s*:\s*query\s*=\s*"
        r"(?P<sql>(?:WITH|SELECT|INSERT)\b.*?)(?=\n\s{2,}[A-Z][A-Za-z0-9 /_-]{1,80}:\s|\n\s*$|\Z)",
        text,
    )
    if query_match:
        return normalize_sql(query_match.group("sql"))

    return None


def extract_original_sql(profile_digest_text: str) -> str | None:
    for candidate_text in profile_digest_text_candidates(profile_digest_text):
        heading_match = re.search(
            r"(?ims)^##\s+SQL\s*$\s*```(?:sql)?\s*(?P<sql>.*?)\s*```",
            candidate_text,
        )
        if heading_match:
            return normalize_sql(heading_match.group("sql"))

        labeled_fence_match = re.search(
            r"(?ims)^\s*(?:#+\s*)?(?:Original\s+)?(?:SQL|Query)\s*:?\s*$"
            r"\s*```(?:sql)?\s*(?P<sql>.*?)\s*```",
            candidate_text,
        )
        if labeled_fence_match:
            return normalize_sql(labeled_fence_match.group("sql"))

        first_sql_fence_match = re.search(
            r"(?is)```sql\s*(?P<sql>.*?)\s*```",
            candidate_text,
        )
        if first_sql_fence_match:
            return normalize_sql(first_sql_fence_match.group("sql"))

        inline_match = re.search(
            r"(?ims)^\s*(?:Original\s+)?(?:SQL|Query)\s*:\s*"
            r"(?P<sql>(?:WITH|SELECT|INSERT)\b.*?)(?:\n\s*\n|$)",
            candidate_text,
        )
        if inline_match:
            return normalize_sql(inline_match.group("sql"))

        labeled_sql = extract_labeled_sql_statement(candidate_text)
        if labeled_sql:
            return labeled_sql

    return None


def strip_sql_comments_and_strings(sql: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    text = re.sub(r"--[^\n\r]*", " ", text)
    text = re.sub(r"'(?:''|[^'])*'", "''", text)
    text = re.sub(r'"(?:""|[^"])*"', '""', text)
    return text


def sql_tokens(sql: str) -> list[str]:
    return [match.group(0) for match in SQL_TOKEN_RE.finditer(sql)]


def is_sql_identifier(token: str) -> bool:
    return bool(SQL_IDENTIFIER_RE.fullmatch(token))


def normalize_sql_identifier_part(token: str) -> str | None:
    if token.startswith("`") and token.endswith("`"):
        inner = token[1:-1].strip()
        return inner if inner and "`" not in inner else None
    if SQL_IDENTIFIER_RE.fullmatch(token):
        return token
    return None


def parse_table_identifier(tokens: list[str], index: int) -> tuple[str | None, int]:
    if index >= len(tokens) or not is_sql_identifier(tokens[index]):
        return None, index

    parts: list[str] = []
    part = normalize_sql_identifier_part(tokens[index])
    if not part:
        return None, index + 1
    parts.append(part)
    index += 1

    if index < len(tokens) and tokens[index] == ".":
        index += 1
        if index >= len(tokens) or not is_sql_identifier(tokens[index]):
            return None, index
        part = normalize_sql_identifier_part(tokens[index])
        if not part:
            return None, index + 1
        parts.append(part)
        index += 1
        # Keep the extractor conservative: Impala table refs are expected as
        # table or db.table here. Skip catalog.db.table-like references.
        if index < len(tokens) and tokens[index] == ".":
            return None, index

    return ".".join(parts), index


def skip_balanced_parentheses(tokens: list[str], index: int) -> int:
    if index >= len(tokens) or tokens[index] != "(":
        return index
    depth = 0
    while index < len(tokens):
        if tokens[index] == "(":
            depth += 1
        elif tokens[index] == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return index


def extract_cte_names_from_tokens(tokens: list[str]) -> set[str]:
    names: set[str] = set()
    index = 0
    while index < len(tokens):
        if tokens[index].lower() != "with":
            index += 1
            continue
        index += 1
        while index < len(tokens):
            cte_name, next_index = parse_table_identifier(tokens, index)
            if not cte_name or "." in cte_name:
                break
            index = next_index
            if index < len(tokens) and tokens[index] == "(":
                index = skip_balanced_parentheses(tokens, index)
            if index >= len(tokens) or tokens[index].lower() != "as":
                break
            names.add(cte_name.lower())
            index += 1
            if index < len(tokens) and tokens[index] == "(":
                index = skip_balanced_parentheses(tokens, index)
            if index < len(tokens) and tokens[index] == ",":
                index += 1
                continue
            break
    return names


def next_significant_token(tokens: list[str], index: int) -> str | None:
    return tokens[index] if index < len(tokens) else None


def is_function_reference(tokens: list[str], start: int, end: int) -> bool:
    if "." in tokens[start:end]:
        return False
    return next_significant_token(tokens, end) == "("


def extract_referenced_tables_from_sql(sql: str) -> list[str]:
    tokens = sql_tokens(strip_sql_comments_and_strings(sql))
    cte_names = extract_cte_names_from_tokens(tokens)
    tables: set[str] = set()
    index = 0
    in_from_list = False
    expect_table = False

    while index < len(tokens):
        token = tokens[index]
        lower = token.lower()

        if token in (")", ";") or lower in SQL_FROM_STOP_WORDS:
            in_from_list = False
            expect_table = False
        elif lower == "from":
            in_from_list = True
            expect_table = True
            index += 1
            continue
        elif lower == "join":
            expect_table = True
            index += 1
            continue
        elif lower == "into":
            previous = tokens[index - 1].lower() if index > 0 else ""
            if previous == "insert":
                index += 1
                if index < len(tokens) and tokens[index].lower() == "table":
                    index += 1
                expect_table = True
                continue
        elif lower == "overwrite":
            previous = tokens[index - 1].lower() if index > 0 else ""
            if previous == "insert":
                index += 1
                if index < len(tokens) and tokens[index].lower() == "table":
                    index += 1
                expect_table = True
                continue
        elif in_from_list and token == ",":
            expect_table = True
            index += 1
            continue

        if expect_table:
            if token == "(":
                expect_table = False
                in_from_list = False
                index += 1
                continue
            table, next_index = parse_table_identifier(tokens, index)
            if table:
                if table.lower() not in cte_names and not is_function_reference(tokens, index, next_index):
                    tables.add(table)
                expect_table = False
                index = next_index
                continue
            expect_table = False

        index += 1

    return sorted(tables, key=lambda value: value.lower())


def sql_inputs_for_case(case_dir: Path, profile_text: str) -> list[str]:
    inputs: list[str] = []
    for relative in (
        "sql.sql",
        "query.sql",
        "original_query.sql",
        "impala_context/original_query.sql",
    ):
        path = case_dir / relative
        if path.exists() and path.is_file():
            sql = normalize_sql(path.read_text(encoding="utf-8", errors="replace"))
            if sql.strip():
                inputs.append(sql)

    if inputs:
        return inputs

    embedded_sql = extract_original_sql(profile_text)
    if embedded_sql:
        inputs.append(embedded_sql)

    return inputs


def collect_referenced_tables(case_dir: Path, profile_text: str) -> list[str]:
    tables: set[str] = set()
    tables.update(read_referenced_context_tables(case_dir / "impala_context" / "referenced_tables.txt"))
    for sql in sql_inputs_for_case(case_dir, profile_text):
        tables.update(extract_referenced_tables_from_sql(sql))
    return sorted(tables, key=lambda value: value.lower())


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


CM_QUERY_CONTEXT_FIELDS = (
    "query_id",
    "status",
    "query_state",
    "query_type",
    "pool",
    "start_time",
    "end_time",
    "duration_ms",
    "admission_result",
    "admission_wait_ms",
    "rows_produced",
    "bytes_read",
    "bytes_sent",
    "memory_aggregate_peak",
    "memory_per_node_peak",
)


def collect_cm_query_context(case_dir: Path) -> dict[str, Any] | None:
    metadata_path = case_dir / "cm_metadata.json"
    if not metadata_path.exists():
        return None
    try:
        raw = json.loads(metadata_path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return {"available": False, "error": "failed to parse CM metadata"}
    if not isinstance(raw, dict):
        return {"available": False, "error": "CM metadata is not an object"}

    context = {
        field: raw.get(field)
        for field in CM_QUERY_CONTEXT_FIELDS
        if raw.get(field) is not None
    }
    context["available"] = bool(context)
    return context


def collect_cm_timeseries_context(case_dir: Path) -> dict[str, Any] | None:
    context_path = case_dir / "cm_timeseries_context.json"
    if not context_path.exists():
        return None
    try:
        raw = json.loads(context_path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return {"available": False, "error": "failed to parse CM time-series context"}
    if not isinstance(raw, dict):
        return {"available": False, "error": "CM time-series context is not an object"}
    queries = raw.get("queries")
    if not isinstance(queries, list):
        return {"available": False, "error": "CM time-series context query list is missing"}
    return {
        "available": bool(raw.get("available")),
        "window": raw.get("window") if isinstance(raw.get("window"), dict) else {},
        "queries": [
            query
            for query in queries
            if isinstance(query, dict)
        ],
        "warnings": [
            warning
            for warning in raw.get("warnings", [])
            if isinstance(warning, str)
        ][:5],
    }


def numeric_context_value(context: dict[str, Any], field: str) -> float | None:
    value = context.get(field)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


CM_METRIC_MIN_POINTS_FOR_SIGNAL = 3
CM_HOST_CPU_USER_MAX_THRESHOLD = 85.0
CM_HOST_CPU_USER_AVG_THRESHOLD = 70.0
CM_HOST_CPU_SYSTEM_MAX_THRESHOLD = 40.0
CM_DAEMON_MEMORY_GROWTH_DELTA_BYTES = 8 * 1024 * 1024 * 1024
CM_DAEMON_MEMORY_GROWTH_RATIO_THRESHOLD = 1.25
CM_NETWORK_SPIKE_BYTES_PER_SEC = 100 * 1024 * 1024
CM_NETWORK_SPIKE_RATIO_THRESHOLD = 5.0


def cm_metric_by_id(context: dict[str, Any], metric_id: str) -> dict[str, Any] | None:
    for query in context.get("queries") or []:
        if isinstance(query, dict) and query.get("id") == metric_id:
            return query
    return None


def cm_metric_point_count(metric: dict[str, Any] | None) -> int:
    if not metric:
        return 0
    value = metric.get("point_count")
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    return 0


def cm_metric_ready(metric: dict[str, Any] | None) -> bool:
    if not metric:
        return False
    if metric.get("status") != "ok":
        return False
    if cm_metric_point_count(metric) < CM_METRIC_MIN_POINTS_FOR_SIGNAL:
        return False
    return any(numeric_context_value(metric, field) is not None for field in ("min", "max", "avg", "latest"))


def cm_signal(status: str, basis: str) -> dict[str, str]:
    return {"status": status, "basis": basis}


def build_cm_metrics_facts(context: dict[str, Any]) -> dict[str, Any]:
    queries = [query for query in context.get("queries") or [] if isinstance(query, dict)]
    total_metrics = len(queries)
    ok_metrics = sum(1 for query in queries if query.get("status") == "ok")
    total_points = sum(cm_metric_point_count(query) for query in queries)
    available = bool(context.get("available")) and total_metrics > 0
    status = "available" if available and ok_metrics == total_metrics else "partial" if ok_metrics else "unavailable"

    host_cpu_user = cm_metric_by_id(context, "host_cpu_user")
    host_cpu_system = cm_metric_by_id(context, "host_cpu_system")
    daemon_memory = cm_metric_by_id(context, "impala_daemon_memory")
    network_io = cm_metric_by_id(context, "host_network_io")

    cpu_user_max = numeric_context_value(host_cpu_user or {}, "max")
    cpu_user_avg = numeric_context_value(host_cpu_user or {}, "avg")
    cpu_system_max = numeric_context_value(host_cpu_system or {}, "max")
    if cm_metric_ready(host_cpu_user) or cm_metric_ready(host_cpu_system):
        cpu_observed = (
            (cpu_user_max is not None and cpu_user_max >= CM_HOST_CPU_USER_MAX_THRESHOLD)
            or (cpu_user_avg is not None and cpu_user_avg >= CM_HOST_CPU_USER_AVG_THRESHOLD)
            or (cpu_system_max is not None and cpu_system_max >= CM_HOST_CPU_SYSTEM_MAX_THRESHOLD)
        )
        host_cpu_pressure = cm_signal(
            "observed" if cpu_observed else "not_observed",
            (
                f"host_cpu_user max={cpu_user_max:.2f} avg={cpu_user_avg:.2f}; "
                f"host_cpu_system max={cpu_system_max:.2f}"
            )
            if cpu_user_max is not None and cpu_user_avg is not None and cpu_system_max is not None
            else "available CPU metrics did not cross pressure thresholds",
        )
    else:
        host_cpu_pressure = cm_signal("unknown", "host CPU metrics are missing or have insufficient points")

    daemon_mem_min = numeric_context_value(daemon_memory or {}, "min")
    daemon_mem_max = numeric_context_value(daemon_memory or {}, "max")
    if cm_metric_ready(daemon_memory) and daemon_mem_min is not None and daemon_mem_max is not None:
        delta = daemon_mem_max - daemon_mem_min
        ratio = daemon_mem_max / daemon_mem_min if daemon_mem_min > 0 else None
        growth_observed = delta >= CM_DAEMON_MEMORY_GROWTH_DELTA_BYTES and (
            ratio is not None and ratio >= CM_DAEMON_MEMORY_GROWTH_RATIO_THRESHOLD
        )
        daemon_memory_growth = cm_signal(
            "observed" if growth_observed else "not_observed",
            (
                f"daemon memory min={fmt_bytes(daemon_mem_min)} max={fmt_bytes(daemon_mem_max)} "
                f"delta={fmt_bytes(delta)} ratio={ratio:.2f}x"
            )
            if ratio is not None
            else f"daemon memory min={fmt_bytes(daemon_mem_min)} max={fmt_bytes(daemon_mem_max)}",
        )
    else:
        daemon_memory_growth = cm_signal("unknown", "daemon memory metric is missing or has insufficient points")

    daemon_memory_pressure = cm_signal(
        "unknown",
        "daemon memory capacity or limit is not part of the current safe CM metrics contract",
    )

    network_max = numeric_context_value(network_io or {}, "max")
    network_avg = numeric_context_value(network_io or {}, "avg")
    if cm_metric_ready(network_io) and network_max is not None and network_avg is not None:
        ratio = network_max / network_avg if network_avg > 0 else None
        spike_observed = network_max >= CM_NETWORK_SPIKE_BYTES_PER_SEC and (
            ratio is None or ratio >= CM_NETWORK_SPIKE_RATIO_THRESHOLD
        )
        network_io_spike = cm_signal(
            "observed" if spike_observed else "not_observed",
            (
                f"host network I/O max={fmt_bytes(network_max)}/s avg={fmt_bytes(network_avg)}/s "
                f"ratio={ratio:.2f}x"
            )
            if ratio is not None
            else f"host network I/O max={fmt_bytes(network_max)}/s avg={fmt_bytes(network_avg)}/s",
        )
    else:
        network_io_spike = cm_signal("unknown", "host network I/O metric is missing or has insufficient points")

    limitations = [
        "CM metrics are bounded query-window context signals, not standalone proof of cause.",
        "Raw metric points and per-point times are intentionally excluded from trusted analysis facts.",
        "Memory pressure remains unknown until a safe capacity or limit metric is available.",
    ]
    warnings = [warning for warning in context.get("warnings") or [] if isinstance(warning, str)]
    if warnings:
        limitations.append(f"Collection warnings present: {len(warnings)}.")

    return {
        "status": status,
        "total_metrics": total_metrics,
        "ok_metrics": ok_metrics,
        "total_points": total_points,
        "host_cpu_pressure": host_cpu_pressure,
        "daemon_memory_growth": daemon_memory_growth,
        "daemon_memory_pressure": daemon_memory_pressure,
        "network_io_spike": network_io_spike,
        "limitations": limitations,
    }


def finding_ids(analysis: dict[str, Any]) -> set[str]:
    return {str(finding.get("id")) for finding in analysis.get("findings") or [] if isinstance(finding, dict)}


def has_memory_profile_evidence(analysis: dict[str, Any]) -> bool:
    thresholds = analysis.get("thresholds", {})
    large_bytes_threshold = float(thresholds.get("large_bytes_threshold") or DEFAULT_LARGE_BYTES_THRESHOLD)
    if analysis.get("memory_anomalies") or analysis.get("zero_memory_estimate_gaps"):
        return True
    if analysis.get("spill_nonzero_evidence_lines"):
        return True
    for op in analysis.get("top_operators_by_peak_memory") or []:
        if (op.get("peak_mem_bytes") or 0) >= large_bytes_threshold:
            return True
    return False


def has_network_profile_evidence(analysis: dict[str, Any]) -> bool:
    return "large_intermediate_or_exchange_traffic" in finding_ids(analysis)


def has_cpu_profile_evidence(analysis: dict[str, Any]) -> bool:
    ids = finding_ids(analysis)
    if ids.intersection(
        {
            "cardinality_estimate_errors",
            "zero_row_estimate_gaps",
            "join_bottleneck",
            "sort_bottleneck",
            "analytic_bottleneck",
        }
    ):
        return True
    thresholds = analysis.get("thresholds", {})
    slow_operator_ms = float(thresholds.get("slow_operator_ms") or 0)
    return any((op.get("time_ms") or 0) >= slow_operator_ms for op in analysis.get("top_operators_by_time") or [])


def build_cm_metrics_correlation(analysis: dict[str, Any]) -> dict[str, Any]:
    context = analysis.get("cm_timeseries_context")
    if not context:
        return {
            "status": "unavailable",
            "signals": [],
            "guardrail": "CM metrics context was not collected for this case.",
        }

    facts = build_cm_metrics_facts(context)
    if facts["status"] not in {"available", "partial"}:
        return {
            "status": facts["status"],
            "signals": [],
            "guardrail": "CM metrics are unavailable and do not affect analysis scoring or actions.",
        }

    memory_support = has_memory_profile_evidence(analysis)
    network_support = has_network_profile_evidence(analysis)
    cpu_support = has_cpu_profile_evidence(analysis)

    def signal_row(
        key: str,
        *,
        title: str,
        profile_support: bool,
        correlated_reason: str,
        context_reason: str,
    ) -> dict[str, str]:
        signal = facts[key]
        metric_status = signal["status"]
        if metric_status == "observed" and profile_support:
            return {
                "key": key,
                "title": title,
                "metric_status": metric_status,
                "correlation_status": "correlated",
                "strength": "moderate",
                "basis": signal["basis"],
                "interpretation": correlated_reason,
            }
        if metric_status == "observed":
            return {
                "key": key,
                "title": title,
                "metric_status": metric_status,
                "correlation_status": "context_only",
                "strength": "weak",
                "basis": signal["basis"],
                "interpretation": context_reason,
            }
        return {
            "key": key,
            "title": title,
            "metric_status": metric_status,
            "correlation_status": metric_status,
            "strength": "none",
            "basis": signal["basis"],
            "interpretation": "No deterministic optimizer or report action is derived from this metric status.",
        }

    signals = [
        signal_row(
            "host_cpu_pressure",
            title="Host CPU pressure",
            profile_support=cpu_support,
            correlated_reason=(
                "CPU pressure is correlated with parsed profile work; use it only to prioritize reducing "
                "row growth, expensive operators, or intermediate payload already shown by profile facts."
            ),
            context_reason=(
                "CPU pressure was observed, but parsed profile facts did not identify a matching SQL/operator target."
            ),
        ),
        signal_row(
            "daemon_memory_growth",
            title="Daemon memory growth",
            profile_support=memory_support,
            correlated_reason=(
                "Daemon memory growth is correlated with parsed memory, spill, or high-memory operator evidence; "
                "prioritize reducing intermediate memory footprint."
            ),
            context_reason=(
                "Daemon memory growth was observed, but parsed profile facts did not identify memory-heavy SQL evidence."
            ),
        ),
        signal_row(
            "daemon_memory_pressure",
            title="Daemon memory pressure",
            profile_support=memory_support,
            correlated_reason=(
                "Daemon memory pressure is correlated with parsed memory evidence; treat it as runtime context, "
                "not standalone proof."
            ),
            context_reason="Daemon memory pressure is observed only as runtime context without matching profile evidence.",
        ),
        signal_row(
            "network_io_spike",
            title="Network I/O spike",
            profile_support=network_support,
            correlated_reason=(
                "Network I/O spike is correlated with parsed large exchange/data movement evidence; "
                "prioritize reducing exchange rows or payload."
            ),
            context_reason=(
                "Network I/O spike was observed, but parsed profile facts did not show large exchange/data movement."
            ),
        ),
    ]
    correlated = sum(1 for signal in signals if signal["correlation_status"] == "correlated")
    context_only = sum(1 for signal in signals if signal["correlation_status"] == "context_only")
    return {
        "status": facts["status"],
        "coverage": f"{facts['ok_metrics']}/{facts['total_metrics']} metrics ok, {facts['total_points']} points",
        "signals": signals,
        "correlated_signals": correlated,
        "context_only_signals": context_only,
        "guardrail": "CM metrics can strengthen profile-supported evidence, but they are not standalone root-cause proof.",
    }


def cm_metric_correlation_signal(analysis: dict[str, Any], key: str) -> dict[str, Any] | None:
    correlation = analysis.get("cm_metrics_correlation") or {}
    for signal in correlation.get("signals") or []:
        if isinstance(signal, dict) and signal.get("key") == key:
            return signal
    return None


def correlated_cm_metric_line(analysis: dict[str, Any], key: str) -> str | None:
    signal = cm_metric_correlation_signal(analysis, key)
    if not signal or signal.get("correlation_status") != "correlated":
        return None
    return (
        f"CM metrics correlation: {signal['title']} is correlated "
        f"({signal['strength']}); {signal['interpretation']}"
    )


def op_label(op: OperatorFact) -> str:
    flags: list[str] = []
    if op.join_kind:
        flags.append(op.join_kind)
    if op.is_partitioned:
        flags.append("PARTITIONED")
    suffix = f" ({', '.join(flags)})" if flags else ""
    return f"{op.operator_id}:{op.operator_name}{suffix}"


def operator_with_observation(op: OperatorFact, observation: OperatorObservation) -> OperatorFact:
    return OperatorFact(
        operator_id=op.operator_id,
        operator_name=op.operator_name,
        time_ms=observation.time_ms if observation.time_ms is not None else op.time_ms,
        actual_rows=observation.actual_rows,
        estimated_rows=observation.estimated_rows,
        peak_mem_bytes=observation.peak_mem_bytes,
        estimated_peak_mem_bytes=observation.estimated_peak_mem_bytes,
        join_kind=op.join_kind,
        is_partitioned=op.is_partitioned,
        evidence_lines=list(observation.evidence_lines or op.evidence_lines),
        observations=[observation],
    )


def operator_with_best_rows_ratio(op: OperatorFact, threshold: float) -> OperatorFact | None:
    observation = op.best_rows_observation()
    if observation is None:
        return None
    ratio = observation_rows_ratio(observation)
    if ratio is None or ratio < threshold:
        return None
    return operator_with_observation(op, observation)


def operator_with_best_memory_ratio(op: OperatorFact, threshold: float) -> OperatorFact | None:
    observation = op.best_memory_observation()
    if observation is None:
        return None
    ratio = observation_mem_ratio(observation)
    if ratio is None or ratio < threshold:
        return None
    return operator_with_observation(op, observation)


def operator_with_zero_row_estimate_gap(op: OperatorFact) -> OperatorFact | None:
    observation = op.best_zero_row_estimate_gap_observation()
    if observation is None:
        return None
    return operator_with_observation(op, observation)


def operator_with_zero_memory_estimate_gap(op: OperatorFact) -> OperatorFact | None:
    observation = op.best_zero_memory_estimate_gap_observation()
    if observation is None:
        return None
    return operator_with_observation(op, observation)


def op_to_json(op: OperatorFact) -> dict[str, Any]:
    row_observation = op.best_rows_observation() or op.best_zero_row_estimate_gap_observation()
    memory_observation = op.best_memory_observation() or op.best_zero_memory_estimate_gap_observation()
    actual_rows = row_observation.actual_rows if row_observation else op.actual_rows
    estimated_rows = row_observation.estimated_rows if row_observation else op.estimated_rows
    rows_ratio = observation_rows_ratio(row_observation) if row_observation else None
    peak_mem_bytes = memory_observation.peak_mem_bytes if memory_observation else op.peak_mem_bytes
    estimated_peak_mem_bytes = (
        memory_observation.estimated_peak_mem_bytes if memory_observation else op.estimated_peak_mem_bytes
    )
    mem_ratio = observation_mem_ratio(memory_observation) if memory_observation else None
    return {
        "operator_id": op.operator_id,
        "operator_name": op.operator_name,
        "label": op_label(op),
        "time_ms": op.time_ms,
        "time": fmt_duration(op.time_ms),
        "actual_rows": actual_rows,
        "actual_rows_human": fmt_rows(actual_rows),
        "estimated_rows": estimated_rows,
        "estimated_rows_human": fmt_rows(estimated_rows),
        "rows_actual_to_estimated_ratio": rows_ratio,
        "rows_ratio_human": fmt_ratio(rows_ratio),
        "peak_mem_bytes": peak_mem_bytes,
        "peak_mem_human": fmt_bytes(peak_mem_bytes),
        "estimated_peak_mem_bytes": estimated_peak_mem_bytes,
        "estimated_peak_mem_human": fmt_bytes(estimated_peak_mem_bytes),
        "mem_actual_to_estimated_ratio": mem_ratio,
        "mem_ratio_human": fmt_ratio(mem_ratio),
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


def host_to_json(fact: BackendHostFact) -> dict[str, Any]:
    return {
        "host": fact.host,
        "fragment_instance": fact.fragment_instance,
        "fragment_group": fact.fragment_group,
        "scan_bytes_assigned": fact.scan_bytes_assigned,
        "scan_bytes_assigned_human": fmt_bytes(fact.scan_bytes_assigned),
        "bytes_read": fact.bytes_read,
        "bytes_read_human": fmt_bytes(fact.bytes_read),
        "bytes_written": fact.bytes_written,
        "bytes_written_human": fmt_bytes(fact.bytes_written),
        "rows_produced": fact.rows_produced,
        "rows_produced_human": fmt_rows(fact.rows_produced),
        "read_rate_bps": fact.read_rate_bps,
        "read_rate_human": fmt_rate(fact.read_rate_bps),
        "write_rate_bps": fact.write_rate_bps,
        "write_rate_human": fmt_rate(fact.write_rate_bps),
        "hdfs_write_time_ms": fact.hdfs_write_time_ms,
        "hdfs_write_time_human": fmt_duration(fact.hdfs_write_time_ms),
        "hdfs_write_sec_per_gib": fact.hdfs_write_sec_per_gib,
        "hdfs_write_sec_per_gib_human": (
            f"{fact.hdfs_write_sec_per_gib:.2f}s/GiB" if fact.hdfs_write_sec_per_gib is not None else "n/a"
        ),
        "scanner_wait_time_ms": fact.scanner_wait_time_ms,
        "scanner_wait_time_human": fmt_duration(fact.scanner_wait_time_ms),
        "materialize_time_ms": fact.materialize_time_ms,
        "materialize_time_human": fmt_duration(fact.materialize_time_ms),
        "parse_time_ms": fact.parse_time_ms,
        "parse_time_human": fmt_duration(fact.parse_time_ms),
        "peak_scanner_concurrency": fact.peak_scanner_concurrency,
        "execution_time_ms": fact.execution_time_ms,
        "execution_time_human": fmt_duration(fact.execution_time_ms),
        "evidence_lines": fact.evidence_lines,
    }


def metric_values(hosts: list[dict[str, Any]], key: str) -> list[tuple[dict[str, Any], float]]:
    values: list[tuple[dict[str, Any], float]] = []
    for host in hosts:
        value = host.get(key)
        if isinstance(value, (int, float)) and value > 0:
            values.append((host, float(value)))
    return values


def ratio_for_values(values: list[tuple[dict[str, Any], float]]) -> float | None:
    if len(values) < BACKEND_MIN_HOSTS_FOR_SKEW:
        return None
    raw_values = [value for _host, value in values if value > 0]
    if len(raw_values) < BACKEND_MIN_HOSTS_FOR_SKEW:
        return None
    min_value = min(raw_values)
    if min_value <= 0:
        return None
    return max(raw_values) / min_value


def backend_data_skew_status(hosts: list[dict[str, Any]]) -> tuple[str, str, bool]:
    metric_labels = [
        ("scan_bytes_assigned", "assigned scan bytes"),
        ("bytes_read", "bytes read"),
        ("rows_produced", "rows produced"),
    ]
    comparable_seen = False
    best_comparable = ""
    for key, label in metric_labels:
        values = metric_values(hosts, key)
        ratio = ratio_for_values(values)
        if ratio is None:
            continue
        if ratio >= BACKEND_DATA_SKEW_RATIO:
            return "yes", f"{label} max/min ratio is {fmt_ratio(ratio)}", False
        if ratio <= BACKEND_WORK_COMPARABLE_RATIO:
            comparable_seen = True
            best_comparable = f"{label} max/min ratio is {fmt_ratio(ratio)}"
    if comparable_seen:
        return "no", f"assigned/read work appears comparable ({best_comparable})", True
    return "unknown", "insufficient comparable per-host assigned/read/row metrics", False


def tail_candidate_from_metric(
    hosts: list[dict[str, Any]],
    *,
    key: str,
    label: str,
    human_key: str,
    higher_is_worse: bool,
    min_ratio: float = BACKEND_TAIL_RATIO,
    min_worst_value: float | None = None,
    min_gap: float | None = None,
) -> dict[str, Any] | None:
    values = metric_values(hosts, key)
    ratio = ratio_for_values(values)
    if ratio is None or ratio < min_ratio:
        return None
    worst_host, worst_value = (max if higher_is_worse else min)(values, key=lambda item: item[1])
    peer_value = (min if higher_is_worse else max)(value for _host, value in values)
    if min_worst_value is not None and worst_value < min_worst_value:
        return None
    if min_gap is not None and abs(worst_value - peer_value) < min_gap:
        return None
    evidence = (
        f"{label}: {worst_host.get(human_key, 'n/a')} vs peer "
        f"{'min' if higher_is_worse else 'max'} "
        f"{fmt_duration(peer_value) if key.endswith('_ms') else fmt_rate(peer_value) if key.endswith('_bps') else f'{peer_value:.2f}s/GiB'}"
    )
    return {
        "host": worst_host["host"],
        "fragment_instance": worst_host.get("fragment_instance"),
        "evidence": evidence,
        "metric_key": key,
        "metric": label,
        "ratio": ratio,
        "ratio_human": fmt_ratio(ratio),
        "worst_value": worst_value,
        "peer_value": peer_value,
        "gap": abs(worst_value - peer_value),
    }


def backend_tail_finding_severity(candidates: list[dict[str, Any]]) -> str:
    for candidate in candidates:
        if (candidate.get("ratio") or 0) >= 5:
            return "high"
        if (
            candidate.get("metric_key") == "execution_time_ms"
            and (candidate.get("worst_value") or 0) >= BACKEND_EXECUTION_TAIL_HIGH_MS
            and (candidate.get("gap") or 0) >= BACKEND_EXECUTION_TAIL_HIGH_GAP_MS
        ):
            return "high"
    return "medium"


def build_backend_tail_analysis(host_facts: list[BackendHostFact]) -> dict[str, Any]:
    hosts = [host_to_json(fact) for fact in host_facts]
    grouped_hosts: dict[str, list[dict[str, Any]]] = {}
    for host in hosts:
        group = str(host.get("fragment_group") or "unknown")
        grouped_hosts.setdefault(group, []).append(host)

    group_statuses: list[tuple[str, str, str, bool, list[dict[str, Any]]]] = []
    for group, group_hosts in grouped_hosts.items():
        group_data_skew, group_reason, comparable_work = backend_data_skew_status(group_hosts)
        group_statuses.append((group, group_data_skew, group_reason, comparable_work, group_hosts))

    yes_statuses = [status for status in group_statuses if status[1] == "yes"]
    comparable_statuses = [status for status in group_statuses if status[3]]
    if yes_statuses:
        group, data_skew, reason, _comparable, _group_hosts = yes_statuses[0]
    elif comparable_statuses:
        group, data_skew, reason, _comparable, _group_hosts = comparable_statuses[0]
    elif group_statuses:
        group, data_skew, reason, _comparable, _group_hosts = group_statuses[0]
    else:
        group, data_skew, reason = "unknown", "unknown", "insufficient comparable per-host assigned/read/row metrics"
    data_skew_reason = f"{group}: {reason}" if group != "unknown" else reason

    candidates: list[dict[str, Any]] = []
    write_path_candidates: list[dict[str, Any]] = []

    for group, _group_data_skew, _group_reason, comparable_work, group_hosts in group_statuses:
        if not comparable_work:
            continue
        metric_specs = [
            (
                "execution_time_ms",
                "execution time",
                "execution_time_human",
                True,
                False,
                BACKEND_EXECUTION_TAIL_RATIO,
                BACKEND_EXECUTION_TAIL_MIN_MS,
                BACKEND_EXECUTION_TAIL_MIN_GAP_MS,
            ),
            ("read_rate_bps", "read rate", "read_rate_human", False, False, BACKEND_TAIL_RATIO, None, None),
            ("write_rate_bps", "write rate", "write_rate_human", False, True, BACKEND_TAIL_RATIO, None, None),
            ("hdfs_write_time_ms", "HDFS write time", "hdfs_write_time_human", True, True, BACKEND_TAIL_RATIO, None, None),
            (
                "hdfs_write_sec_per_gib",
                "HDFS write sec/GiB",
                "hdfs_write_sec_per_gib_human",
                True,
                True,
                BACKEND_TAIL_RATIO,
                None,
                None,
            ),
        ]
        for key, label, human_key, higher_is_worse, is_write_path, min_ratio, min_worst_value, min_gap in metric_specs:
            candidate = tail_candidate_from_metric(
                group_hosts,
                key=key,
                label=f"{group} {label}" if group != "unknown" else label,
                human_key=human_key,
                higher_is_worse=higher_is_worse,
                min_ratio=min_ratio,
                min_worst_value=min_worst_value,
                min_gap=min_gap,
            )
            if candidate is None:
                continue
            candidates.append(candidate)
            if is_write_path:
                write_path_candidates.append(candidate)

    execution_skew = "yes" if candidates else ("unknown" if data_skew == "unknown" else "no")
    write_path_anomaly = "yes" if write_path_candidates else ("unknown" if not comparable_statuses else "no")
    tail_candidate_count = len({candidate["host"] for candidate in candidates})
    return {
        "rows_parsed": len(hosts),
        "hosts": hosts,
        "groups": [
            {
                "fragment_group": group,
                "host_count": len(group_hosts),
                "data_skew": group_data_skew,
                "data_skew_reason": group_reason,
                "comparable_work": comparable_work,
            }
            for group, group_data_skew, group_reason, comparable_work, group_hosts in group_statuses
        ],
        "tail_candidate_count": tail_candidate_count,
        "data_skew": data_skew,
        "data_skew_reason": data_skew_reason,
        "execution_skew": execution_skew,
        "write_path_anomaly": write_path_anomaly,
        "candidates": candidates,
        "write_path_candidates": write_path_candidates,
    }


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
    large_bytes_threshold = float(thresholds.get("large_bytes_threshold") or DEFAULT_LARGE_BYTES_THRESHOLD)
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
    if total_read.get("raw") and (total_read.get("bytes") or 0) >= MEDIUM_DATA_MOVEMENT_BYTES:
        evidence.append(f"TotalBytesRead: {total_read['raw']} ({fmt_bytes(total_read.get('bytes'))})")
    if total_sent.get("raw") and (total_sent.get("bytes") or 0) >= MEDIUM_DATA_MOVEMENT_BYTES:
        evidence.append(f"TotalBytesSent: {total_sent['raw']} ({fmt_bytes(total_sent.get('bytes'))})")
    metric_evidence_keys: list[str] = []
    if related_memory:
        metric_evidence_keys.extend(["daemon_memory_growth", "daemon_memory_pressure"])
    if total_sent.get("bytes") and total_sent["bytes"] >= MEDIUM_DATA_MOVEMENT_BYTES:
        metric_evidence_keys.append("network_io_spike")
    if op.get("rows_actual_to_estimated_ratio") or op.get("time_ms"):
        metric_evidence_keys.append("host_cpu_pressure")
    for key in metric_evidence_keys:
        line = correlated_cm_metric_line(analysis, key)
        if line and line not in evidence:
            evidence.append(line)

    admin_actions = [
        "Check per-host RowsProduced for this operator.",
        "Check spill/scratch counters for this operator if available in profile.",
    ]
    if related_memory:
        admin_actions.append("Check per-host PeakMemUsage for this operator.")
        admin_actions.append("Check whether admission pool memory limits were hit.")
    if total_sent.get("bytes") and total_sent["bytes"] >= large_bytes_threshold:
        admin_actions.append("Check whether exchange volume matches TotalBytesSent.")
    if any(item.startswith("CM metrics correlation:") for item in evidence):
        admin_actions.append("Use CM metrics only as correlated runtime context, not as standalone root-cause proof.")

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
    admin_actions: list[str] | None = None,
    missing_evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "severity": severity,
        "title": title,
        "summary": summary,
        "operators": operators or [],
        "evidence_lines": evidence_lines or [],
        "admin_actions": admin_actions or [],
        "missing_evidence": missing_evidence or [],
    }


def analyze(text: str, args: argparse.Namespace) -> dict[str, Any]:
    text = normalize_profile_text(text)
    operators = parse_operators(text)
    backend_tail = build_backend_tail_analysis(parse_backend_host_facts(text))
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
        [
            anomaly
            for op in operators
            if (anomaly := operator_with_best_rows_ratio(op, args.rows_ratio_threshold)) is not None
        ],
        key=lambda x: x.rows_ratio or 0,
        reverse=True,
    )
    memory_anomalies = sorted(
        [
            anomaly
            for op in operators
            if (anomaly := operator_with_best_memory_ratio(op, args.mem_ratio_threshold)) is not None
        ],
        key=lambda x: x.mem_ratio or 0,
        reverse=True,
    )
    zero_row_estimate_gaps = sorted(
        [
            gap
            for op in operators
            if (gap := operator_with_zero_row_estimate_gap(op)) is not None
        ],
        key=lambda x: x.actual_rows or 0,
        reverse=True,
    )
    zero_memory_estimate_gaps = sorted(
        [
            gap
            for op in operators
            if (gap := operator_with_zero_memory_estimate_gap(op)) is not None
        ],
        key=lambda x: x.peak_mem_bytes or 0,
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

    findings: list[dict[str, Any]] = []
    not_supported_causes: list[str] = []

    network_exchange_evidence: list[str] = []
    total_sent = totals.get("TotalBytesSent")
    network_exchange_severity = "medium"
    if (
        total_sent
        and total_sent.get("bytes") is not None
        and total_sent["bytes"] >= MEDIUM_DATA_MOVEMENT_BYTES
    ):
        if total_sent["bytes"] >= args.large_bytes_threshold:
            network_exchange_severity = "high"
        network_exchange_evidence.append(
            f"TotalBytesSent is large: {total_sent['raw']} ({fmt_bytes(total_sent['bytes'])})"
        )
    elif total_sent and total_sent.get("bytes") is not None and total_sent["bytes"] < MEDIUM_DATA_MOVEMENT_BYTES:
        not_supported_causes.append(
            "TotalBytesSent was parsed below the large data-movement threshold: "
            f"{total_sent['raw']} ({fmt_bytes(total_sent['bytes'])}); do not treat it as large exchange traffic."
        )

    if network_exchange_evidence:
        for op in top_by_time[: args.top_n]:
            if "EXCHANGE" in op.operator_name.upper() and op.time_ms is not None:
                network_exchange_evidence.append(
                    f"{op_label(op)} has notable time: {fmt_duration(op.time_ms)}"
                )

    total_read = totals.get("TotalBytesRead")
    if total_read and total_read.get("bytes") is not None and total_read["bytes"] < MEDIUM_DATA_MOVEMENT_BYTES:
        not_supported_causes.append(
            "TotalBytesRead was parsed below the large I/O footprint threshold: "
            f"{total_read['raw']} ({fmt_bytes(total_read['bytes'])}); do not treat it as large scan I/O."
        )

    if total_sent and total_sent.get("bytes") is not None and total_sent["bytes"] >= args.large_bytes_threshold:
        network_exchange_evidence.append(
            "TotalBytesSent meets the high data-movement threshold "
            f"({fmt_bytes(args.large_bytes_threshold)})."
        )

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
    elif not zero_row_estimate_gaps:
        not_supported_causes.append(
            "No parsed actual-vs-estimated row count anomaly above threshold; do not claim cardinality estimate errors unless another evidence line supports it."
        )

    if zero_row_estimate_gaps:
        worst = zero_row_estimate_gaps[0]
        findings.append(
            make_finding(
                "zero_row_estimate_gaps",
                "medium",
                "Zero/unknown row estimate gaps",
                (
                    "Detected positive actual rows with an explicit zero/non-positive row estimate. "
                    f"Worst parsed gap: {op_label(worst)} = {fmt_rows(worst.actual_rows)} "
                    f"actual rows vs {fmt_rows(worst.estimated_rows)} estimated rows."
                ),
                operators=[op_to_json(op) for op in zero_row_estimate_gaps],
            )
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

    if zero_memory_estimate_gaps:
        worst = zero_memory_estimate_gaps[0]
        findings.append(
            make_finding(
                "zero_memory_estimate_gaps",
                "medium",
                "Zero/unknown memory estimate gaps",
                (
                    "Detected positive peak memory with an explicit zero/non-positive estimated peak memory. "
                    f"Worst parsed gap: {op_label(worst)} = {fmt_bytes(worst.peak_mem_bytes)} "
                    f"peak memory vs {fmt_bytes(worst.estimated_peak_mem_bytes)} estimated peak memory."
                ),
                operators=[op_to_json(op) for op in zero_memory_estimate_gaps],
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
                "Storage/HDFS candidate signal",
                "Detected scan/storage operator evidence among top time operators. Treat this as a candidate signal, not a root-cause claim.",
                evidence_lines=storage_bottleneck_evidence,
            )
        )
    else:
        not_supported_causes.append(
            "No direct HDFS/storage candidate signal was parsed. Large TotalBytesRead is an I/O footprint, not proof that HDFS/block size/replication is the root cause."
        )

    if network_exchange_evidence:
        findings.append(
            make_finding(
                "large_intermediate_or_exchange_traffic",
                network_exchange_severity,
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
                "Codegen candidate signal",
                "Detected notable codegen/LLVM timing evidence. Treat this as a candidate signal, not a root-cause claim.",
                evidence_lines=codegen_bottleneck_lines[: args.max_evidence_lines],
            )
        )
    else:
        not_supported_causes.append(
            "No codegen/LLVM candidate signal was parsed."
        )

    if backend_tail["candidates"]:
        findings.append(
            make_finding(
                "host_execution_tail_suspected",
                backend_tail_finding_severity(backend_tail["candidates"]),
                "Host-specific execution tail suspected",
                (
                    "Execution skew is suspected from parsed backend counters. "
                    "Host-specific HDFS/RPC/write path issue is suspected, not proven."
                ),
                evidence_lines=[
                    f"{candidate['host']}: {candidate['evidence']} ({candidate['ratio_human']})"
                    for candidate in backend_tail["candidates"][: args.max_evidence_lines]
                ],
                admin_actions=[
                    "Compare per-host RowsProduced / BytesRead / BytesWritten rates.",
                    "Check HDFS write latency and DataNode pipeline details for the tail host.",
                    "Check NIC errors, retransmits, drops, MTU, LACP/bond, and switch output discards.",
                    "Check whether the tail persists after scanner thread cap changes if that evidence is available.",
                ],
                missing_evidence=[
                    "NIC counters.",
                    "Switch drops.",
                    "DataNode pipeline details.",
                    "Per-host OS/network metrics.",
                ],
            )
        )

    not_supported_causes.append(
        "No evidence in the profile digest supports HDFS block-size or replication-factor changes as a query-level fix unless scan/storage counters prove it."
    )
    not_supported_causes.append(
        "No evidence in the profile digest supports blaming external network instability; large TotalBytesSent only shows data movement volume."
    )

    return {
        "thresholds": {
            "rows_ratio_threshold": args.rows_ratio_threshold,
            "mem_ratio_threshold": args.mem_ratio_threshold,
            "slow_operator_ms": args.slow_operator_ms,
            "large_rows_threshold": args.large_rows_threshold,
            "large_bytes_threshold": args.large_bytes_threshold,
            "medium_data_movement_bytes": MEDIUM_DATA_MOVEMENT_BYTES,
            "report_top_n": args.top_n,
        },
        "totals": totals,
        "backend_tail": backend_tail,
        "operators": [op_to_json(op) for op in operators],
        "top_operators_by_time": [op_to_json(op) for op in top_by_time],
        "top_operators_by_peak_memory": [op_to_json(op) for op in top_by_memory],
        "cardinality_anomalies": [op_to_json(op) for op in cardinality_anomalies],
        "memory_anomalies": [op_to_json(op) for op in memory_anomalies],
        "zero_row_estimate_gaps": [op_to_json(op) for op in zero_row_estimate_gaps],
        "zero_memory_estimate_gaps": [op_to_json(op) for op in zero_memory_estimate_gaps],
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
        f"- Zero/unknown row estimate gaps: {len(analysis['zero_row_estimate_gaps'])}",
        f"- Zero/unknown memory estimate gaps: {len(analysis['zero_memory_estimate_gaps'])}",
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
        if finding.get("evidence_lines") and (verbose or finding.get("id") == "host_execution_tail_suspected"):
            lines.append("- Evidence lines:")
            for ev in finding["evidence_lines"]:
                lines.append(f"  - `{ev}`")
        if finding.get("admin_actions"):
            lines.append("- Admin checks:")
            for action in finding["admin_actions"]:
                lines.append(f"  - {action}")
        if finding.get("missing_evidence"):
            lines.append("- Missing evidence:")
            for item in finding["missing_evidence"]:
                lines.append(f"  - {item}")
        lines.append("")
    return lines


def render_backend_tail_evidence(analysis: dict[str, Any]) -> list[str]:
    backend = analysis.get("backend_tail") or {}
    if not backend.get("rows_parsed"):
        return []

    lines = ["## Backend / Host Tail Evidence", "", "### Summary", ""]
    lines.extend(
        [
            f"- backend rows parsed: {backend['rows_parsed']}",
            f"- host tail candidates: {backend['tail_candidate_count']}",
            f"- data skew: {backend['data_skew']} ({backend['data_skew_reason']})",
            f"- execution skew: {backend['execution_skew']}",
            f"- write-path anomaly: {backend['write_path_anomaly']}",
            "",
            "### Host tail candidates",
            "",
        ]
    )
    candidates = backend.get("candidates") or []
    if not candidates:
        lines.append("- none")
        lines.append("")
        return lines

    lines.append("| host | evidence | ratio/metric |")
    lines.append("|---|---|---:|")
    for candidate in candidates:
        host = candidate.get("host") or "unknown"
        evidence = candidate.get("evidence") or "n/a"
        ratio = candidate.get("ratio_human") or "n/a"
        lines.append(f"| {md_escape(host)} | {md_escape(evidence)} | {ratio} |")
    lines.append("")
    lines.extend(
        [
            "### Interpretation guardrails",
            "",
            "- Execution skew is suspected from parsed backend counters.",
            "- Host-specific HDFS/RPC/write path issue is suspected, not proven.",
            "",
        ]
    )
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


def render_referenced_tables(analysis: dict[str, Any]) -> list[str]:
    lines = ["## Referenced Tables", ""]
    tables = analysis.get("referenced_tables") or []
    if tables:
        lines.extend(f"- `{table}`" for table in tables)
    else:
        lines.append(
            "- not_observed: no referenced table names were parsed from SQL inputs or profile digest."
        )
    lines.append("")
    return lines


def render_table_metadata_context(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("table_metadata_context") or {}
    lines = ["## Table Metadata Context", ""]
    context_file = context.get("context_file", "not_observed")
    lines.append(f"- context file: {context_file}")
    if context.get("context_path"):
        lines.append(f"- context path: `{context['context_path']}`")
    lines.append(f"- table metadata facts: {context.get('table_metadata_facts', 'unknown')}")
    lines.append(f"- tables requested: {context.get('tables_requested', 0)}")
    read_only = context.get("read_only_statements_only")
    if read_only is not None:
        lines.append(f"- read-only statements only: {'yes' if read_only else 'no'}")
    if context.get("error"):
        lines.append(f"- error: {context['error']}")
    lines.append("")

    for table in context.get("tables") or []:
        lines.extend([f"### Table: {table['table']}", ""])
        lines.append(f"- object type: {table.get('object_type', 'unknown')}")
        for statement in ("SHOW CREATE TABLE", "SHOW TABLE STATS", "SHOW COLUMN STATS"):
            lines.append(f"- {statement} status: {table.get('statements', {}).get(statement, 'unknown')}")
        lines.append(f"- table stats rows: {table.get('table_rows', 'unknown')}")
        lines.append(
            "- table stats row-count completeness: "
            f"{table.get('table_stats_row_count_completeness', 'unknown')}"
        )
        lines.append(f"- table stats size: {table.get('table_size', 'unknown')}")
        lines.append(
            f"- column stats columns observed: {table.get('column_stats_columns_observed', 'unknown')}"
        )
        lines.append(
            f"- column stats missing/unknown markers: {table.get('column_stats_missing_markers', 'unknown')}"
        )
        lines.append(
            f"- column stats completeness: {table.get('column_stats_completeness', 'unknown')}"
        )
        columns = table.get("column_stats_columns") or []
        if columns:
            lines.append("- column stats columns: " + ", ".join(f"`{column}`" for column in columns))
        lines.append(f"- file format: {table.get('file_format', 'unknown')}")
        partitions = table.get("partition_columns") or []
        if partitions:
            lines.append("- partition columns: " + ", ".join(f"`{column}`" for column in partitions))
        else:
            lines.append("- partition columns: unknown")
        lines.append("")
    return lines


def render_cm_query_context(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("cm_query_context")
    if not context:
        return []

    lines = ["## CM Query Context", ""]
    if not context.get("available"):
        lines.append(f"- available: no")
        if context.get("error"):
            lines.append(f"- error: {context['error']}")
        lines.append("")
        return lines

    lines.append("- available: yes")
    for field in ("query_id", "status", "query_state", "query_type", "pool", "start_time", "end_time"):
        value = context.get(field)
        if value is not None:
            lines.append(f"- {field}: {value}")
    duration_ms = numeric_context_value(context, "duration_ms")
    if duration_ms is not None:
        lines.append(f"- duration: {fmt_duration(duration_ms)}")
    if context.get("admission_result") is not None:
        lines.append(f"- admission_result: {context['admission_result']}")
    admission_wait_ms = numeric_context_value(context, "admission_wait_ms")
    if admission_wait_ms is not None:
        lines.append(f"- admission_wait: {fmt_duration(admission_wait_ms)}")
    rows_produced = numeric_context_value(context, "rows_produced")
    if rows_produced is not None:
        lines.append(f"- rows_produced: {fmt_rows(rows_produced)}")
    for field, label in (
        ("bytes_read", "bytes_read"),
        ("bytes_sent", "bytes_sent"),
        ("memory_aggregate_peak", "memory_aggregate_peak"),
        ("memory_per_node_peak", "memory_per_node_peak"),
    ):
        value = numeric_context_value(context, field)
        if value is not None:
            lines.append(f"- {label}: {fmt_bytes(value)}")
    lines.append("")
    return lines


def render_cm_timeseries_context(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("cm_timeseries_context")
    if not context:
        return []

    lines = ["## CM Time-Series Context", ""]
    lines.append(f"- available: {'yes' if context.get('available') else 'no'}")
    window = context.get("window") or {}
    if window.get("from") and window.get("to"):
        lines.append(f"- window: {window['from']} to {window['to']}")
    if window.get("padding_sec") is not None:
        lines.append(f"- window padding seconds: {window['padding_sec']}")
    lines.append("")

    for query in context.get("queries") or []:
        label = query.get("label") or query.get("id") or "unknown"
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"- status: {query.get('status', 'unknown')}")
        lines.append(f"- point_count: {query.get('point_count', 0)}")
        if query.get("truncated"):
            lines.append("- truncated: yes")
        for field in ("min", "max", "avg", "latest"):
            value = numeric_context_value(query, field)
            if value is not None:
                lines.append(f"- {field}: {value:.2f}")
        lines.append("")

    warnings = context.get("warnings") or []
    if warnings:
        lines.extend(["### Collection warnings", ""])
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")
    return lines


def render_cm_metrics_facts(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("cm_timeseries_context")
    if not context:
        return []

    facts = build_cm_metrics_facts(context)
    lines = ["## CM Metrics Facts", ""]
    lines.append(f"- status: {facts['status']}")
    lines.append(
        f"- coverage: {facts['ok_metrics']}/{facts['total_metrics']} metrics ok, "
        f"{facts['total_points']} points"
    )
    for key in (
        "host_cpu_pressure",
        "daemon_memory_growth",
        "daemon_memory_pressure",
        "network_io_spike",
    ):
        signal = facts[key]
        lines.append(f"- {key}: {signal['status']}")
        lines.append(f"- {key}_basis: {signal['basis']}")
    lines.append("")

    limitations = facts.get("limitations") or []
    if limitations:
        lines.extend(["### CM metrics limitations", ""])
        for limitation in limitations:
            lines.append(f"- {limitation}")
        lines.append("")
    return lines


def render_cm_metrics_correlation(analysis: dict[str, Any]) -> list[str]:
    correlation = analysis.get("cm_metrics_correlation")
    if not correlation:
        return []

    lines = ["## CM Metrics Correlation", ""]
    lines.append(f"- status: {correlation.get('status', 'unknown')}")
    if correlation.get("coverage"):
        lines.append(f"- coverage: {correlation['coverage']}")
    lines.append(f"- correlated_signals: {correlation.get('correlated_signals', 0)}")
    lines.append(f"- context_only_signals: {correlation.get('context_only_signals', 0)}")
    lines.append(f"- guardrail: {correlation.get('guardrail', 'CM metrics are context only.')}")
    lines.append("")

    signals = correlation.get("signals") or []
    if not signals:
        lines.append("- No CM metric signals were available for correlation.")
        lines.append("")
        return lines

    for signal in signals:
        lines.append(
            f"- {signal['key']}: {signal['correlation_status']} "
            f"(metric={signal['metric_status']}, strength={signal['strength']})"
        )
        lines.append(f"  - basis: {signal['basis']}")
        lines.append(f"  - interpretation: {signal['interpretation']}")
    lines.append("")
    return lines


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
    lines += render_operator_table("Zero/unknown row estimate gaps", analysis["zero_row_estimate_gaps"], max_table_rows)
    lines += render_operator_table("Zero/unknown memory estimate gaps", analysis["zero_memory_estimate_gaps"], max_table_rows)

    lines += render_referenced_tables(analysis)
    lines += render_cm_query_context(analysis)
    lines += render_cm_timeseries_context(analysis)
    lines += render_cm_metrics_facts(analysis)
    lines += render_cm_metrics_correlation(analysis)
    lines += render_table_metadata_context(analysis)
    lines += render_impala_context(analysis)
    lines += render_backend_tail_evidence(analysis)
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
    parser.add_argument("--large-bytes-threshold", type=float, default=DEFAULT_LARGE_BYTES_THRESHOLD)
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
    analysis["cm_query_context"] = collect_cm_query_context(digest_path.parent)
    analysis["cm_timeseries_context"] = collect_cm_timeseries_context(digest_path.parent)
    analysis["impala_context"] = collect_impala_context(digest_path.parent)
    analysis["table_metadata_context"] = collect_table_metadata_context(digest_path.parent)
    analysis["referenced_tables"] = collect_referenced_tables(digest_path.parent, text)
    analysis["cm_metrics_correlation"] = build_cm_metrics_correlation(analysis)
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
