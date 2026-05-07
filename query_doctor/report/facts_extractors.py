"""Pure helpers for extracting report contracts from analysis facts."""

from __future__ import annotations

import re

from query_doctor.report.contract import (
    CLUSTER_RUNTIME_CONTEXT_HEADING,
    CM_METRICS_CORRELATION_HEADING,
    CM_METRICS_FACTS_HEADING,
    CM_TIMESERIES_CONTEXT_HEADING,
    TABLE_METADATA_CONTEXT_HEADING,
)
from query_doctor.report.markdown import extract_markdown_section, strip_markdown_section


FACT_APPENDIX_MAX_ITEMS = 8
FACTS_TABLE_OPERATOR_RE = re.compile(r"^\s*\|\s*(?P<operator>\d{2,}:[^|]+?)\s*\|")
BACKEND_SUMMARY_RE = re.compile(r"^\s*[-*]\s*(?P<key>[^:]+):\s*(?P<value>.+?)\s*$")


def facts_text_for_model_prompt(facts_text: str) -> str:
    """Return deterministic facts that are enabled for LLM-written narrative."""
    safe_lines = [
        line
        for line in facts_text.splitlines()
        if not line.strip().lower().startswith("source digest:")
    ]
    prompt_facts = "\n".join(safe_lines)
    prompt_facts = strip_markdown_section(prompt_facts, TABLE_METADATA_CONTEXT_HEADING)
    return strip_markdown_section(prompt_facts, CM_TIMESERIES_CONTEXT_HEADING)


def facts_cardinality_anomaly_count(facts_text: str) -> int | None:
    return facts_summary_count(facts_text, "Cardinality anomalies")


def facts_memory_anomaly_count(facts_text: str) -> int | None:
    return facts_summary_count(facts_text, "Memory anomalies")


def facts_summary_count(facts_text: str, label: str) -> int | None:
    match = re.search(
        rf"^\s*(?:[-*]\s*)?{re.escape(label)}\s*:\s*(?P<count>\d+)\s*$",
        facts_text,
        re.MULTILINE,
    )
    if not match:
        return None
    return int(match.group("count"))


def parse_ratio_value(value: str) -> float | None:
    cleaned = value.strip().lower().replace(",", "")
    if cleaned in {"", "n/a", "na", "nan"}:
        return None
    if cleaned.endswith("x"):
        cleaned = cleaned[:-1].strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_operator_key(operator: str) -> str:
    return re.sub(r"\s+", " ", operator.strip()).upper()


def operator_id_prefix(operator: str) -> str:
    return operator.split(":", 1)[0]


def operator_type_name(operator: str) -> str:
    _, _, rest = operator.partition(":")
    return re.sub(r"\s*\(.*?\)", "", rest).strip()


def parse_row_estimate_directions(facts_text: str) -> dict[str, str]:
    directions: dict[str, str] = {}
    for line in facts_text.splitlines():
        match = FACTS_TABLE_OPERATOR_RE.match(line)
        if not match:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        operator = cells[0]
        ratio = parse_ratio_value(cells[4])
        if ratio is None:
            continue
        key = normalize_operator_key(operator)
        if ratio > 1.0:
            directions[key] = "underestimated"
        elif ratio < 1.0:
            directions[key] = "overestimated"
        else:
            directions[key] = "matched"
    return directions


def parse_memory_estimate_directions(facts_text: str) -> dict[str, str]:
    directions: dict[str, str] = {}
    for line in facts_text.splitlines():
        match = FACTS_TABLE_OPERATOR_RE.match(line)
        if not match:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 8:
            continue
        operator = cells[0]
        ratio = parse_ratio_value(cells[7])
        if ratio is None:
            continue
        key = normalize_operator_key(operator)
        if ratio > 1.0:
            directions[key] = "underestimated"
        elif ratio < 1.0:
            directions[key] = "overestimated"
        else:
            directions[key] = "matched"
    return directions


def first_bullet_value(lines: list[str], label: str) -> str | None:
    pattern = re.compile(rf"^\s*[-*]\s+{re.escape(label)}\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE)
    for line in lines:
        match = pattern.match(line)
        if match:
            return match.group("value").strip()
    return None


def facts_has_backend_tail_evidence(facts_text: str) -> bool:
    lower = facts_text.lower()
    return (
        "backend / host tail evidence" in lower
        or "host-specific execution tail suspected" in lower
        or "execution skew is suspected from parsed backend counters" in lower
        or "execution skew is suspected from parsed backend execution-time counters" in lower
    )


def parse_backend_tail_summary(facts_text: str) -> dict[str, str | int]:
    summary: dict[str, str | int] = {}
    in_backend_section = False
    for line in facts_text.splitlines():
        stripped = line.strip()
        if stripped == "## Backend / Host Tail Evidence":
            in_backend_section = True
            continue
        if in_backend_section and stripped.startswith("## "):
            break
        if not in_backend_section:
            continue
        match = BACKEND_SUMMARY_RE.match(line)
        if not match:
            continue
        key = match.group("key").strip().lower()
        value = match.group("value").strip()
        if key in {
            "host tail candidates",
            "execution tail candidates",
            "read-rate tail candidates",
            "write-path tail candidates",
        }:
            number_match = re.match(r"\d+", value)
            if number_match:
                summary[key] = int(number_match.group(0))
            continue
        if key in {"data skew", "execution skew", "write-path anomaly"}:
            summary[key] = value.split()[0].lower()
    return summary


def backend_summary_value(summary: dict[str, str | int], key: str) -> str:
    value = summary.get(key, "unknown")
    return str(value)


def backend_has_proven_tail(summary: dict[str, str | int]) -> bool:
    candidates = summary.get("execution tail candidates")
    if not isinstance(candidates, int):
        candidates = summary.get("host tail candidates")
    execution_skew = str(summary.get("execution skew", "unknown")).lower()
    return isinstance(candidates, int) and candidates > 0 and execution_skew == "yes"


def backend_write_path_is_supported(summary: dict[str, str | int]) -> bool:
    return str(summary.get("write-path anomaly", "unknown")).lower() == "yes"


def backend_data_skew_is_supported(summary: dict[str, str | int]) -> bool:
    return str(summary.get("data skew", "unknown")).lower() == "yes"


def facts_have_spill_scratch_evidence(facts_text: str) -> bool:
    return bool(
        re.search(
            r"Spill or scratch I/O|non-zero spill/scratch metric evidence",
            facts_text,
            re.IGNORECASE,
        )
    )


def facts_have_action_cards(facts_text: str) -> bool:
    return bool("\n".join(extract_markdown_section(facts_text, "## Action Cards")).strip())


def facts_have_metadata_stats_gap(facts_text: str) -> bool:
    metadata_lines = "\n".join(extract_markdown_section(facts_text, TABLE_METADATA_CONTEXT_HEADING))
    if not metadata_lines:
        return False
    return bool(
        re.search(
            r"(?:table stats row-count completeness|column stats completeness)\s*:\s*"
            r"(?:missing/unknown|incomplete/unknown)",
            metadata_lines,
            re.IGNORECASE,
        )
    )


def facts_have_large_intermediate_or_exchange(facts_text: str) -> bool:
    findings_lines = extract_markdown_section(facts_text, "## Findings")
    if not findings_lines:
        return False
    findings_text = "\n".join(findings_lines)
    return bool(
        re.search(
            r"^###\s+Large intermediate or exchange traffic\b|"
            r"^-\s+TotalBytesSent is large\b|"
            r"^-\s+TotalBytesSent meets the high data-movement threshold\b",
            findings_text,
            re.IGNORECASE | re.MULTILINE,
        )
    )


def cm_metrics_facts_summary(facts_text: str) -> dict[str, str]:
    lines = extract_markdown_section(facts_text, CM_METRICS_FACTS_HEADING)
    if not lines:
        return {}

    summary: dict[str, str] = {}
    for label in (
        "status",
        "coverage",
        "host_cpu_pressure",
        "host_cpu_pressure_basis",
        "daemon_memory_growth",
        "daemon_memory_growth_basis",
        "daemon_memory_pressure",
        "daemon_memory_pressure_basis",
        "network_io_spike",
        "network_io_spike_basis",
    ):
        value = first_bullet_value(lines, label)
        if value is not None:
            summary[label] = value
    return summary


def cm_metrics_observed_points(facts_text: str) -> list[str]:
    summary = cm_metrics_facts_summary(facts_text)
    points: list[str] = []
    labels = (
        ("host_cpu_pressure", "Host CPU pressure"),
        ("daemon_memory_growth", "Daemon memory growth"),
        ("daemon_memory_pressure", "Daemon memory pressure"),
        ("network_io_spike", "Network I/O spike"),
    )
    for key, title in labels:
        if summary.get(key) != "observed":
            continue
        basis = summary.get(f"{key}_basis")
        points.append(f"{title}: observed" + (f"; {basis}" if basis else ""))
    return points[:FACT_APPENDIX_MAX_ITEMS]


def cm_metrics_correlation_summary(facts_text: str) -> dict[str, str]:
    lines = extract_markdown_section(facts_text, CM_METRICS_CORRELATION_HEADING)
    if not lines:
        return {}

    summary: dict[str, str] = {}
    for label in (
        "status",
        "coverage",
        "correlated_signals",
        "context_only_signals",
        "guardrail",
        "host_cpu_pressure",
        "daemon_memory_growth",
        "daemon_memory_pressure",
        "network_io_spike",
    ):
        value = first_bullet_value(lines, label)
        if value is not None:
            summary[label] = value
    return summary


def cm_metrics_correlation_points(facts_text: str) -> list[str]:
    summary = cm_metrics_correlation_summary(facts_text)
    points: list[str] = []
    labels = (
        ("host_cpu_pressure", "Host CPU pressure"),
        ("daemon_memory_growth", "Daemon memory growth"),
        ("daemon_memory_pressure", "Daemon memory pressure"),
        ("network_io_spike", "Network I/O spike"),
    )
    for key, title in labels:
        value = summary.get(key)
        if not value:
            continue
        if value.startswith("correlated"):
            points.append(f"{title}: {value}")
    return points[:FACT_APPENDIX_MAX_ITEMS]


def cluster_runtime_context_summary(facts_text: str) -> dict[str, str]:
    lines = extract_markdown_section(facts_text, CLUSTER_RUNTIME_CONTEXT_HEADING)
    if not lines:
        return {}

    summary: dict[str, str] = {}
    for label in (
        "status",
        "collection_status",
        "coverage",
        "metrics_profile",
        "window_scope",
        "limit_summary",
        "scoring_contribution",
        "observed_signals",
        "correlated_signals",
        "context_only_signals",
        "unknown_signals",
        "not_observed_signals",
        "guardrail",
    ):
        value = first_bullet_value(lines, label)
        if value is not None:
            summary[label] = value
    return summary


def cluster_runtime_context_points(facts_text: str) -> list[str]:
    summary = cluster_runtime_context_summary(facts_text)
    points: list[str] = []
    for label in (
        "coverage",
        "correlated_signals",
        "context_only_signals",
        "scoring_contribution",
    ):
        value = summary.get(label)
        if value and value != "none":
            points.append(f"{label}: {value}")
    return points[:FACT_APPENDIX_MAX_ITEMS]


def cm_metrics_report_evidence_bullet(facts_text: str) -> str | None:
    facts_summary = cm_metrics_facts_summary(facts_text)
    correlation_summary = cm_metrics_correlation_summary(facts_text)
    if facts_summary.get("status") not in {"available", "partial"}:
        return None
    parts = ["CM metrics collected"]
    coverage = facts_summary.get("coverage")
    if coverage:
        parts.append(coverage)
    correlated = correlation_summary.get("correlated_signals")
    context_only = correlation_summary.get("context_only_signals")
    if correlated is not None or context_only is not None:
        parts.append(f"correlated={correlated or '0'}, context-only={context_only or '0'}")
    observed = [
        label
        for key, label in (
            ("host_cpu_pressure", "host CPU pressure"),
            ("daemon_memory_growth", "daemon memory growth"),
            ("daemon_memory_pressure", "daemon memory pressure"),
            ("network_io_spike", "network I/O spike"),
        )
        if facts_summary.get(key) == "observed"
    ]
    if observed:
        parts.append("observed context signals: " + ", ".join(observed))
    spread_points: list[str] = []
    for key, label in (
        ("daemon_memory_growth", "daemon memory"),
        ("network_io_spike", "network I/O"),
        ("host_cpu_pressure", "host CPU"),
    ):
        basis = facts_summary.get(f"{key}_basis") or ""
        match = re.search(r"top series max/peer max=(?P<ratio>\d+(?:\.\d+)?)x", basis)
        if match:
            spread_points.append(f"{label} top/peer={match.group('ratio')}x")
    if spread_points:
        parts.append("series spread: " + ", ".join(spread_points[:3]))
    facts_lines = "\n".join(extract_markdown_section(facts_text, CM_METRICS_FACTS_HEADING))
    limit_points: list[str] = []
    if "CM metrics were truncated for:" in facts_lines:
        limit_points.append("some metric summaries were truncated by collection limits")
    if "CM metrics unavailable for:" in facts_lines:
        limit_points.append("some allowlisted metrics were unavailable")
    if limit_points:
        parts.append("limitations: " + "; ".join(limit_points))
    return "- " + "; ".join(parts) + ". Metrics are runtime context unless CM Metrics Correlation marks them as correlated."


def cm_metrics_signal_observed(facts_text: str, key: str) -> bool:
    summary = cm_metrics_facts_summary(facts_text)
    return summary.get("status") == "available" and summary.get(key) == "observed"


def cm_metrics_correlation_status(facts_text: str, key: str) -> str | None:
    lines = extract_markdown_section(facts_text, CM_METRICS_CORRELATION_HEADING)
    if not lines:
        return None
    pattern = re.compile(rf"^\s*-\s*{re.escape(key)}\s*:\s*(?P<status>[a-z_]+)\b", re.IGNORECASE)
    for line in lines:
        match = pattern.match(line)
        if match:
            return match.group("status").lower()
    return None


def cm_metric_context_only(facts_text: str, key: str) -> bool:
    return cm_metrics_correlation_status(facts_text, key) == "context_only"


def cm_metrics_profile_supported(facts_text: str, key: str) -> bool:
    status = cm_metrics_correlation_status(facts_text, key)
    if status is not None:
        return status == "correlated"
    return cm_metrics_signal_observed(facts_text, key)
