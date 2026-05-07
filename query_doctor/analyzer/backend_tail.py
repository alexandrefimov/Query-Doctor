"""Backend host parsing and tail-skew analysis for Impala profiles."""

from __future__ import annotations

import re

from query_doctor.analyzer.context_files import compact_line
from query_doctor.analyzer.models import BackendHostFact
from query_doctor.analyzer.operators import parse_raw_counter_number
from query_doctor.analyzer.runtime_counters import line_indent, normalize_metric_key
from query_doctor.analyzer.scalars import (
    extract_first_duration_ms,
    parse_rate_bytes_per_sec,
    parse_seconds_per_gib,
    parse_size_bytes,
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


def append_backend_evidence(fact: BackendHostFact, line: str) -> None:
    evidence = compact_line(line)
    if evidence not in fact.evidence_lines:
        fact.evidence_lines.append(evidence)


def first_number(value: str) -> float | None:
    m = re.search(r"\d[\d,]*(?:\.\d+)?", value)
    if not m:
        return None
    return float(m.group(0).replace(",", ""))


def set_backend_metric(
    fact: BackendHostFact,
    key: str,
    value: str,
    line: str,
    *,
    direct_execution_metric: bool = True,
) -> None:
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
    elif normalized_key in BACKEND_EXECUTION_TIME_KEYS and direct_execution_metric:
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
    current_header_indent: int | None = None
    current_child_indent: int | None = None

    def finish_current() -> None:
        nonlocal current, current_header_indent, current_child_indent
        if current is not None and current.host and current.has_metric():
            if current.hdfs_write_sec_per_gib is None and current.hdfs_write_time_ms and current.bytes_written:
                gib = current.bytes_written / (1024**3)
                if gib > 0:
                    current.hdfs_write_sec_per_gib = (current.hdfs_write_time_ms / 1000) / gib
            facts.append(current)
        current = None
        current_header_indent = None
        current_child_indent = None

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
                current_header_indent = line_indent(line)
                current_child_indent = None
            else:
                current = None
                current_header_indent = None
                current_child_indent = None
            continue

        if current is None:
            continue

        stripped = line.strip()
        if not stripped:
            current_child_indent = None
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
            indent = line_indent(line)
            nested_metric = False
            if current_child_indent is not None:
                if indent > current_child_indent:
                    nested_metric = True
                else:
                    current_child_indent = None
            direct_execution_metric = (
                not nested_metric
                and current_header_indent is not None
                and indent > current_header_indent
            )
            set_backend_metric(
                current,
                metric_match.group("key"),
                metric_match.group("value"),
                line,
                direct_execution_metric=direct_execution_metric,
            )
            continue

        if current_header_indent is not None:
            indent = line_indent(line)
            if indent <= current_header_indent:
                current_child_indent = None
            elif not stripped.startswith("-"):
                current_child_indent = indent

    finish_current()
    return facts


from query_doctor.analyzer.backend_tail_analysis import (  # noqa: E402
    BACKEND_DATA_SKEW_RATIO,
    BACKEND_EXECUTION_TAIL_HIGH_GAP_MS,
    BACKEND_EXECUTION_TAIL_HIGH_MS,
    BACKEND_EXECUTION_TAIL_MIN_GAP_MS,
    BACKEND_EXECUTION_TAIL_MIN_MS,
    BACKEND_EXECUTION_TAIL_RATIO,
    BACKEND_MIN_HOSTS_FOR_SKEW,
    BACKEND_TAIL_RATIO,
    BACKEND_WORK_COMPARABLE_RATIO,
    backend_data_skew_status,
    backend_tail_finding_severity,
    build_backend_tail_analysis,
    host_to_json,
    metric_values,
    ratio_for_values,
    tail_candidate_from_metric,
    tail_value_human,
)
