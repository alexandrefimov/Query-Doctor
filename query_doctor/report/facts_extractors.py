"""Pure helpers for extracting report contracts from analysis facts."""

from __future__ import annotations

import re

from query_doctor.report.contract import (
    CLUSTER_EVENT_CONTEXT_HEADING,
    CLUSTER_RUNTIME_CONTEXT_HEADING,
    CM_METRICS_CORRELATION_HEADING,
    CM_METRICS_FACTS_HEADING,
    CM_TIMESERIES_CONTEXT_HEADING,
    RUNTIME_METRICS_CORRELATION_HEADING,
    RUNTIME_METRICS_FACTS_HEADING,
    TABLE_METADATA_CONTEXT_HEADING,
)
from query_doctor.report.markdown import (
    extract_markdown_section,
    extract_markdown_subsection,
    strip_markdown_section,
)
from query_doctor.safety.browser_display import redact_browser_display_text


FACT_APPENDIX_MAX_ITEMS = 8
FACTS_TABLE_OPERATOR_RE = re.compile(r"^\s*\|\s*(?P<operator>\d{2,}:[^|]+?)\s*\|")
BACKEND_SUMMARY_RE = re.compile(r"^\s*[-*]\s*(?P<key>[^:]+):\s*(?P<value>.+?)\s*$")
SOURCE_PROVENANCE_KINDS = {"engine", "profile", "metrics", "events", "metadata"}
SOURCE_PROVENANCE_STATUSES = {"available", "partial", "unavailable", "none", "unknown"}
STATS_GAP_STATUSES = {"missing", "unknown", "missing/unknown", "incomplete", "incomplete/unknown"}
STATS_DETAIL_GAP_STATUSES = {"missing", "partial", "limited"}
STATS_NON_GAP_STATUSES = {
    "available",
    "complete",
    "not_applicable",
    "not_checked",
    "not_observed",
}


def extract_first_markdown_section(facts_text: str, *headings: str) -> list[str]:
    for heading in headings:
        lines = extract_markdown_section(facts_text, heading)
        if lines:
            return lines
    return []


def facts_text_for_model_prompt(facts_text: str) -> str:
    """Return deterministic facts that are enabled for LLM-written narrative."""
    safe_lines = [
        line
        for line in facts_text.splitlines()
        if not line.strip().lower().startswith("source digest:")
    ]
    prompt_facts = "\n".join(safe_lines)
    prompt_facts = strip_markdown_section(prompt_facts, TABLE_METADATA_CONTEXT_HEADING)
    prompt_facts = strip_markdown_section(prompt_facts, CM_TIMESERIES_CONTEXT_HEADING)
    return redact_browser_display_text(
        prompt_facts,
        redact_artifact_markers=True,
        redact_field_names=True,
        redact_model_names=True,
        redact_infrastructure=True,
    )


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


def markdown_bullet_values(
    lines: list[str],
    *,
    limit: int = FACT_APPENDIX_MAX_ITEMS,
) -> list[str]:
    values: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        values.append(stripped[2:].strip())
        if len(values) >= limit:
            break
    return values


def evidence_quality_summary(facts_text: str) -> dict[str, str | list[str]]:
    lines = extract_markdown_section(facts_text, "## Evidence Quality")
    if not lines:
        return {}

    summary: dict[str, str | list[str]] = {}
    for label in ("score", "level"):
        value = first_bullet_value(lines, label)
        if value is not None:
            summary[label] = value

    strengths = markdown_bullet_values(extract_markdown_subsection(lines, "### Strengths"))
    limitations = markdown_bullet_values(extract_markdown_subsection(lines, "### Limitations"))
    if strengths:
        summary["strengths"] = strengths
    if limitations:
        summary["limitations"] = limitations
    return summary


def evidence_quality_points(facts_text: str) -> list[str]:
    summary = evidence_quality_summary(facts_text)
    if not summary:
        return []

    points: list[str] = []
    score = summary.get("score")
    level = summary.get("level")
    parts = []
    if isinstance(score, str):
        parts.append(f"score={score}")
    if isinstance(level, str):
        parts.append(f"level={level}")
    points.append("Evidence Quality" + (f": {', '.join(parts)}" if parts else " facts present"))

    limitations = summary.get("limitations")
    if isinstance(limitations, list):
        points.extend(f"limitation: {item}" for item in limitations[:2])
    strengths = summary.get("strengths")
    if isinstance(strengths, list):
        points.extend(f"strength: {item}" for item in strengths[:2])
    return points[:FACT_APPENDIX_MAX_ITEMS]


def evidence_quality_report_evidence_bullet(
    facts_text: str,
    *,
    language: str = "ru",
) -> str | None:
    summary = evidence_quality_summary(facts_text)
    if not summary:
        return None

    score = summary.get("score")
    level = summary.get("level")
    header_parts = []
    if isinstance(score, str):
        header_parts.append(f"score={score}")
    if isinstance(level, str):
        header_parts.append(f"level={level}")
    header = "Evidence Quality" + (f": {', '.join(header_parts)}" if header_parts else "")

    detail_parts: list[str] = []
    strengths = summary.get("strengths")
    if isinstance(strengths, list) and strengths:
        detail_parts.append("strengths: " + "; ".join(strengths[:2]))
    limitations = summary.get("limitations")
    if isinstance(limitations, list) and limitations:
        detail_parts.append("limitations: " + "; ".join(limitations[:2]))

    guardrail = (
        "Используйте это как рамку уверенности и покрытия, не как самостоятельное доказательство root cause."
        if language == "ru"
        else "Use this as confidence and coverage framing, not standalone root-cause proof."
    )
    suffix = f"; {'; '.join(detail_parts)}" if detail_parts else ""
    return f"- {header}{suffix}. {guardrail}"


def source_provenance_summary(facts_text: str) -> dict[str, str]:
    lines = extract_markdown_section(facts_text, "## Source Provenance")
    summary: dict[str, str] = {}
    for line in lines:
        match = re.match(
            r"^\s*-\s*(?P<kind>[a-z_]+)\s*:\s*(?P<status>[a-z_]+)\b",
            line,
            re.IGNORECASE,
        )
        if not match:
            continue
        kind = match.group("kind").lower()
        status = match.group("status").lower()
        if kind in SOURCE_PROVENANCE_KINDS and status in SOURCE_PROVENANCE_STATUSES:
            summary[kind] = status
    return summary


def source_provenance_report_evidence_bullet(
    facts_text: str,
    *,
    language: str = "ru",
) -> str | None:
    summary = source_provenance_summary(facts_text)
    if not summary:
        return None

    ordered_kinds = ("engine", "profile", "metrics", "events", "metadata")
    coverage = ", ".join(f"{kind}={summary[kind]}" for kind in ordered_kinds if kind in summary)
    if language == "en":
        details = source_provenance_limitation_details_en(summary)
        suffix = f" Coverage limitations: {'; '.join(details)}." if details else ""
        return (
            f"- Source Provenance: {coverage}."
            f"{suffix} Use source coverage as a limitation frame, not root-cause proof."
        )

    details = source_provenance_limitation_details_ru(summary)
    suffix = f" Ограничения покрытия: {'; '.join(details)}." if details else ""
    return (
        f"- Source Provenance: {coverage}."
        f"{suffix} Используйте покрытие источников как рамку ограничений, "
        "не как доказательство причины."
    )


def source_provenance_limitation_details_en(summary: dict[str, str]) -> list[str]:
    details: list[str] = []
    if summary.get("engine") == "unknown":
        details.append("engine identity is unavailable from deterministic profile facts")
    if summary.get("profile") in {"unknown", "unavailable"}:
        details.append("profile coverage is unknown or unavailable")
    elif summary.get("profile") == "partial":
        details.append("profile coverage is partial")
    if summary.get("metrics") in {"partial", "unavailable"}:
        details.append("runtime metrics are incomplete or unavailable")
    elif summary.get("metrics") in {"none", "unknown"}:
        details.append("runtime metrics were not collected or coverage is unknown")
    if summary.get("events") in {"none", "unavailable", "partial", "unknown"}:
        details.append("event context is absent or incomplete")
    if summary.get("metadata") == "partial":
        details.append("bounded metadata is partial")
    elif summary.get("metadata") in {"none", "unavailable", "unknown"}:
        details.append("bounded metadata is unavailable or unknown")
    return details


def source_provenance_limitation_details_ru(summary: dict[str, str]) -> list[str]:
    details: list[str] = []
    if summary.get("engine") == "unknown":
        details.append("идентификация движка недоступна из deterministic profile facts")
    if summary.get("profile") in {"unknown", "unavailable"}:
        details.append("покрытие profile неизвестно или недоступно")
    elif summary.get("profile") == "partial":
        details.append("покрытие profile частичное")
    if summary.get("metrics") in {"partial", "unavailable"}:
        details.append("runtime metrics неполные или недоступны")
    elif summary.get("metrics") in {"none", "unknown"}:
        details.append("runtime metrics не собраны или покрытие неизвестно")
    if summary.get("events") in {"none", "unavailable", "partial", "unknown"}:
        details.append("event context отсутствует или неполный")
    if summary.get("metadata") == "partial":
        details.append("bounded metadata частичная")
    elif summary.get("metadata") in {"none", "unavailable", "unknown"}:
        details.append("bounded metadata недоступна или неизвестна")
    return details


def facts_has_backend_tail_evidence(facts_text: str) -> bool:
    lower = facts_text.lower()
    return (
        "backend / host tail evidence" in lower
        or "host-specific execution tail suspected" in lower
        or "execution skew is suspected from parsed backend counters" in lower
        or "execution skew is suspected from parsed backend execution-time counters" in lower
    )


def facts_have_backend_followup_evidence(facts_text: str) -> bool:
    summary = parse_backend_tail_summary(facts_text)
    if backend_data_skew_is_supported(summary):
        return True
    if backend_has_proven_tail(summary):
        return True
    if backend_write_path_is_supported(summary):
        return True
    if str(summary.get("execution skew", "unknown")).lower() == "yes":
        return True

    findings_text = "\n".join(extract_markdown_section(facts_text, "## Findings"))
    return bool(
        re.search(
            r"^###\s+Host-specific execution tail suspected\b|"
            r"Execution skew is suspected from parsed backend(?: execution-time)? counters",
            findings_text,
            re.IGNORECASE | re.MULTILINE,
        )
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
    scan_skew = scan_skew_summary(facts_text)
    if scan_skew:
        supported = (
            str(scan_skew.get("evidence_tier") or "").lower() == "strong"
            and str(scan_skew.get("finding_supported") or "").lower() == "yes"
        )
        summary["data skew"] = "yes" if supported else "no"
    return summary


def scan_skew_summary(facts_text: str) -> dict[str, str]:
    lines = extract_markdown_section(facts_text, "## Scan Skew Evidence")
    summary: dict[str, str] = {}
    for label in (
        "status",
        "evidence_tier",
        "finding_supported",
        "primary_supported",
        "skew_metric",
        "skew_ratio",
    ):
        value = first_bullet_value(lines, label)
        if value is not None:
            summary[label] = value
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
    memory_supported = structured_memory_pressure_supported(facts_text)
    if memory_supported is not None:
        return memory_supported

    findings_text = "\n".join(extract_markdown_section(facts_text, "## Findings"))
    if not findings_text:
        findings_text = facts_text
    return bool(
        re.search(
            r"^###\s+Spill or scratch I/O\b|"
            r"Detected non-zero spill/scratch metric evidence",
            findings_text,
            re.IGNORECASE | re.MULTILINE,
        )
    )


def structured_memory_pressure_supported(facts_text: str) -> bool | None:
    lines = extract_markdown_section(facts_text, "## Memory Pressure Evidence")
    if not lines:
        return None

    status = normalized_fact_value(first_bullet_value(lines, "status"))
    evidence_tier = normalized_fact_value(first_bullet_value(lines, "evidence_tier"))
    finding_supported = normalized_fact_value(first_bullet_value(lines, "finding_supported"))
    spill_count = first_bullet_value(lines, "spill_or_scratch_evidence_count") or ""
    has_spill_count = bool(re.search(r"[1-9]", spill_count))
    if finding_supported == "yes":
        return status == "supported" and evidence_tier in {"strong", "medium"} and has_spill_count
    if finding_supported == "no":
        return False
    if status in {"context_only", "not_observed"} or evidence_tier in {
        "context_only",
        "unsupported",
    }:
        return False
    return None


def facts_have_action_cards(facts_text: str) -> bool:
    return bool("\n".join(extract_markdown_section(facts_text, "## Action Cards")).strip())


def facts_have_metadata_stats_gap(facts_text: str) -> bool:
    stats_quality = structured_stats_quality_gap(facts_text)
    if stats_quality is not None:
        return stats_quality
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


def structured_stats_quality_gap(facts_text: str) -> bool | None:
    lines = extract_markdown_section(facts_text, "## Stats Metadata Quality")
    if not lines:
        return None

    recognized = False
    table_stats = normalized_fact_value(first_bullet_value(lines, "table_stats"))
    column_stats = normalized_fact_value(first_bullet_value(lines, "column_stats"))
    partition_coverage = normalized_fact_value(first_bullet_value(lines, "partition_coverage"))
    join_filter_relevance = normalized_fact_value(
        first_bullet_value(lines, "join_filter_column_relevance")
    )
    stats_context = normalized_fact_value(first_bullet_value(lines, "stats_context"))

    for value in (table_stats, column_stats):
        if value in STATS_GAP_STATUSES:
            return True
        if value in STATS_NON_GAP_STATUSES:
            recognized = True
    if partition_coverage in STATS_DETAIL_GAP_STATUSES:
        return True
    if join_filter_relevance in STATS_DETAIL_GAP_STATUSES:
        return True
    if partition_coverage in STATS_NON_GAP_STATUSES | {"unknown"}:
        recognized = True
    if join_filter_relevance in STATS_NON_GAP_STATUSES | {"unknown", "covered"}:
        recognized = True

    for label in (
        "tables_with_missing_table_stats",
        "tables_with_incomplete_column_stats",
        "partitioned_tables_with_missing_table_stats",
        "partitions_with_unknown_row_count",
        "join_filter_columns_without_stats",
        "join_filter_columns_with_ndv_missing_stats",
        "join_filter_columns_with_size_missing_stats",
        "join_filter_columns_with_all_missing_stats",
        "join_filter_columns_with_unknown_stats",
    ):
        count = first_bullet_int(lines, label)
        if count is None:
            continue
        recognized = True
        if count > 0:
            return True

    if stats_context in {
        "not_physical_table_stats",
        "stats_available_no_row_estimate_evidence",
        "stats_present_with_row_estimate_evidence",
        "metadata_unavailable",
        "stats_quality_unknown",
    }:
        return False
    if stats_context in {
        "stats_gap_with_row_estimate_evidence",
        "stats_gap_without_row_estimate_evidence",
    }:
        return True

    return False if recognized else None


def normalized_fact_value(value: str | None) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def first_bullet_int(lines: list[str], label: str) -> int | None:
    value = first_bullet_value(lines, label)
    if value is None:
        return None
    match = re.match(r"\s*(?P<count>\d+)\b", value)
    return int(match.group("count")) if match else None


def facts_have_large_intermediate_or_exchange(facts_text: str) -> bool:
    data_movement_supported = structured_data_movement_supported(facts_text)
    if data_movement_supported is not None:
        return data_movement_supported
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


def structured_data_movement_supported(facts_text: str) -> bool | None:
    lines = extract_markdown_section(facts_text, "## Data Movement Evidence")
    if not lines:
        return None

    status = normalized_fact_value(first_bullet_value(lines, "status"))
    evidence_tier = normalized_fact_value(first_bullet_value(lines, "evidence_tier"))
    finding_supported = normalized_fact_value(first_bullet_value(lines, "finding_supported"))
    if finding_supported == "yes":
        return status == "supported" and evidence_tier in {"strong", "medium"}
    if finding_supported == "no":
        return False
    if status in {"context_only", "not_observed"} or evidence_tier in {
        "context_only",
        "unsupported",
    }:
        return False
    return None


def cm_metrics_facts_summary(facts_text: str) -> dict[str, str]:
    lines = extract_first_markdown_section(
        facts_text,
        RUNTIME_METRICS_FACTS_HEADING,
        CM_METRICS_FACTS_HEADING,
    )
    if not lines:
        return {}

    summary: dict[str, str] = {}
    for label in (
        "status",
        "coverage",
        "admission_pool_pressure",
        "admission_pool_pressure_basis",
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
    lines = extract_first_markdown_section(
        facts_text,
        RUNTIME_METRICS_CORRELATION_HEADING,
        CM_METRICS_CORRELATION_HEADING,
    )
    if not lines:
        return {}

    summary: dict[str, str] = {}
    for label in (
        "status",
        "coverage",
        "correlated_signals",
        "context_only_signals",
        "guardrail",
        "admission_pool_pressure",
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
        ("admission_pool_pressure", "Admission/pool pressure"),
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


def cluster_runtime_context_report_evidence_bullet(facts_text: str) -> str | None:
    summary = cluster_runtime_context_summary(facts_text)
    if summary.get("status") not in {"available", "partial"}:
        return None
    parts = ["Cluster runtime context collected"]
    coverage = summary.get("coverage")
    if coverage:
        parts.append(coverage)
    correlated = summary.get("correlated_signals")
    context_only = summary.get("context_only_signals")
    if correlated and correlated != "none":
        parts.append(f"correlated signals: {correlated}")
    if context_only and context_only != "none":
        parts.append(f"context-only signals: {context_only}")
    scoring = summary.get("scoring_contribution")
    if scoring:
        parts.append("scoring: " + runtime_metrics_display_text(scoring))
    return (
        "- "
        + "; ".join(parts)
        + ". Treat this as runtime follow-up context, not standalone root-cause proof."
    )


def cluster_event_context_summary(facts_text: str) -> dict[str, str]:
    lines = extract_markdown_section(facts_text, CLUSTER_EVENT_CONTEXT_HEADING)
    if not lines:
        return {}

    summary: dict[str, str] = {}
    for label in (
        "status",
        "available",
        "source_status",
        "window_scope",
        "signal_counts",
        "guardrail",
    ):
        value = first_bullet_value(lines, label)
        if value is not None:
            summary[label] = value
    return summary


def facts_have_cluster_event_context(facts_text: str) -> bool:
    summary = cluster_event_context_summary(facts_text)
    return bool(summary) and summary.get("available") == "yes"


def cluster_event_context_points(facts_text: str) -> list[str]:
    summary = cluster_event_context_summary(facts_text)
    points: list[str] = []
    for label in ("status", "source_status", "window_scope", "signal_counts"):
        value = summary.get(label)
        if value and value not in {"none", "unknown"}:
            points.append(f"{label}: {value}")
    return points[:FACT_APPENDIX_MAX_ITEMS]


def cluster_event_context_report_evidence_bullet(facts_text: str) -> str | None:
    summary = cluster_event_context_summary(facts_text)
    if summary.get("available") != "yes":
        return None
    parts = ["Cluster event context collected"]
    status = summary.get("status")
    if status:
        parts.append(f"status={status}")
    signal_counts = summary.get("signal_counts")
    if signal_counts and signal_counts != "none":
        parts.append(f"signals: {signal_counts}")
    source_status = summary.get("source_status")
    if source_status and source_status != "none":
        parts.append(f"sources: {source_status}")
    return (
        "- "
        + "; ".join(parts)
        + ". Treat Cluster Event Context as follow-up context, not standalone root-cause proof."
    )


def cm_metrics_report_evidence_bullet(facts_text: str) -> str | None:
    facts_summary = cm_metrics_facts_summary(facts_text)
    correlation_summary = cm_metrics_correlation_summary(facts_text)
    if facts_summary.get("status") not in {"available", "partial"}:
        return None
    parts = ["Runtime metrics collected"]
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
            ("admission_pool_pressure", "admission/pool pressure"),
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
    facts_lines = "\n".join(
        extract_first_markdown_section(
            facts_text,
            RUNTIME_METRICS_FACTS_HEADING,
            CM_METRICS_FACTS_HEADING,
        )
    )
    limit_points: list[str] = []
    if "CM metrics were truncated for:" in facts_lines:
        limit_points.append("some metric summaries were truncated by collection limits")
    if "CM metrics unavailable for:" in facts_lines:
        limit_points.append("some allowlisted metrics were unavailable")
    if limit_points:
        parts.append("limitations: " + "; ".join(limit_points))
    return (
        "- "
        + "; ".join(parts)
        + ". Metrics are runtime context unless Runtime Metrics Correlation marks them as correlated."
    )


def runtime_metrics_display_text(value: str) -> str:
    return (
        value.replace("CM metric signal(s)", "runtime metric signal(s)")
        .replace("CM metric signals", "runtime metric signals")
        .replace("CM metrics", "Runtime metrics")
        .replace("CM metric", "Runtime metric")
    )


def cm_metrics_signal_observed(facts_text: str, key: str) -> bool:
    summary = cm_metrics_facts_summary(facts_text)
    return summary.get("status") == "available" and summary.get(key) == "observed"


def cm_metrics_correlation_status(facts_text: str, key: str) -> str | None:
    lines = extract_first_markdown_section(
        facts_text,
        RUNTIME_METRICS_CORRELATION_HEADING,
        CM_METRICS_CORRELATION_HEADING,
    )
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
