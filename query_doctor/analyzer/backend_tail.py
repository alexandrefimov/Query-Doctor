"""Backend host parsing and tail-skew analysis for Impala profiles."""

from __future__ import annotations

import re
from typing import Any

from query_doctor.analyzer.context_files import compact_line
from query_doctor.analyzer.models import BackendHostFact
from query_doctor.analyzer.operators import parse_raw_counter_number
from query_doctor.analyzer.runtime_counters import line_indent, normalize_metric_key
from query_doctor.analyzer.scalars import (
    extract_first_duration_ms,
    fmt_bytes,
    fmt_duration,
    fmt_rate,
    fmt_ratio,
    fmt_rows,
    parse_rate_bytes_per_sec,
    parse_seconds_per_gib,
    parse_size_bytes,
)


BACKEND_MIN_HOSTS_FOR_SKEW = 3
BACKEND_DATA_SKEW_RATIO = 3.0
BACKEND_WORK_COMPARABLE_RATIO = 1.5
BACKEND_TAIL_RATIO = 3.0
BACKEND_EXECUTION_TAIL_RATIO = 1.6
BACKEND_EXECUTION_TAIL_MIN_MS = 10 * 60 * 1000
BACKEND_EXECUTION_TAIL_MIN_GAP_MS = 10 * 60 * 1000
BACKEND_EXECUTION_TAIL_HIGH_MS = 30 * 60 * 1000
BACKEND_EXECUTION_TAIL_HIGH_GAP_MS = 15 * 60 * 1000

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


def tail_value_human(metric_key: str, value: float | None) -> str:
    if value is None:
        return "n/a"
    if metric_key.endswith("_ms"):
        return fmt_duration(value)
    if metric_key.endswith("_bps"):
        return fmt_rate(value)
    if metric_key.endswith("_sec_per_gib"):
        return f"{value:.2f}s/GiB"
    return f"{value:.2f}"


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
    execution_tail_candidates: list[dict[str, Any]] = []
    read_rate_tail_candidates: list[dict[str, Any]] = []
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
                "execution",
                False,
                BACKEND_EXECUTION_TAIL_RATIO,
                BACKEND_EXECUTION_TAIL_MIN_MS,
                BACKEND_EXECUTION_TAIL_MIN_GAP_MS,
            ),
            ("read_rate_bps", "read rate", "read_rate_human", False, "read_rate", False, BACKEND_TAIL_RATIO, None, None),
            ("write_rate_bps", "write rate", "write_rate_human", False, "write_path", True, BACKEND_TAIL_RATIO, None, None),
            ("hdfs_write_time_ms", "HDFS write time", "hdfs_write_time_human", True, "write_path", True, BACKEND_TAIL_RATIO, None, None),
            (
                "hdfs_write_sec_per_gib",
                "HDFS write sec/GiB",
                "hdfs_write_sec_per_gib_human",
                True,
                "write_path",
                True,
                BACKEND_TAIL_RATIO,
                None,
                None,
            ),
        ]
        for key, label, human_key, higher_is_worse, family, is_write_path, min_ratio, min_worst_value, min_gap in metric_specs:
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
            candidate["metric_family"] = family
            candidate["fragment_group"] = group
            candidate["worst_human"] = tail_value_human(key, candidate.get("worst_value"))
            candidate["peer_human"] = tail_value_human(key, candidate.get("peer_value"))
            candidate["gap_human"] = tail_value_human(key, candidate.get("gap"))
            candidates.append(candidate)
            if family == "execution":
                execution_tail_candidates.append(candidate)
            elif family == "read_rate":
                read_rate_tail_candidates.append(candidate)
            if is_write_path:
                write_path_candidates.append(candidate)

    execution_skew = "yes" if execution_tail_candidates else ("unknown" if not comparable_statuses else "no")
    write_path_anomaly = "yes" if write_path_candidates else ("unknown" if not comparable_statuses else "no")
    tail_candidate_count = len({candidate["host"] for candidate in candidates})
    execution_tail_candidate_count = len({candidate["host"] for candidate in execution_tail_candidates})
    read_rate_tail_candidate_count = len({candidate["host"] for candidate in read_rate_tail_candidates})
    write_path_tail_candidate_count = len({candidate["host"] for candidate in write_path_candidates})
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
        "execution_tail_candidate_count": execution_tail_candidate_count,
        "read_rate_tail_candidate_count": read_rate_tail_candidate_count,
        "write_path_tail_candidate_count": write_path_tail_candidate_count,
        "data_skew": data_skew,
        "data_skew_reason": data_skew_reason,
        "execution_skew": execution_skew,
        "write_path_anomaly": write_path_anomaly,
        "candidates": candidates,
        "execution_tail_candidates": execution_tail_candidates,
        "read_rate_tail_candidates": read_rate_tail_candidates,
        "write_path_candidates": write_path_candidates,
    }
