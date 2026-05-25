"""Profile text evidence scanners for deterministic analyzer signals."""

from __future__ import annotations

import re

from query_doctor.analyzer.context_files import compact_line
from query_doctor.analyzer.profile_counter_registry import (
    DEFAULT_PROFILE_COUNTER_REGISTRY,
    ProfileCounterRegistry,
    profile_counter_definition,
    profile_counter_supports_strong_evidence,
)
from query_doctor.analyzer.scalars import (
    SIZE_PATTERN,
    SIZE_RE,
    extract_first_duration_ms,
    parse_scaled_number,
    parse_size_bytes,
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


def spill_metric_counter_name(line: str) -> str | None:
    match = SPILL_METRIC_RE.search(line)
    if not match:
        return None
    return match.group("name")


def find_nonzero_spill_metric_lines(
    text: str,
    counter_registry: ProfileCounterRegistry = DEFAULT_PROFILE_COUNTER_REGISTRY,
) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        value = spill_metric_value(line)
        counter_name = spill_metric_counter_name(line)
        if counter_name is None:
            continue
        definition = profile_counter_definition(counter_name, counter_registry)
        if value is not None and value > 0 and profile_counter_supports_strong_evidence(definition):
            lines.append(compact_line(line))
    return lines


def find_codegen_bottleneck_lines(
    text: str, total_time_ms: float | None, min_share: float = 0.10
) -> list[str]:
    if not isinstance(total_time_ms, (int, float)) or total_time_ms <= 0:
        return []
    lines: list[str] = []
    for line in text.splitlines():
        m = CODEGEN_TIMING_RE.search(line)
        if not m:
            continue
        codegen_ms = extract_first_duration_ms(m.group("value"))
        if codegen_ms is None or codegen_ms <= 0:
            continue
        if codegen_ms / total_time_ms < min_share:
            continue
        lines.append(compact_line(line))
    return lines
