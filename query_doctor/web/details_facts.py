"""Safe facts loaders and parsers for web details pages."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from query_doctor.impala import table_metadata_facts

from query_doctor.web.models import WebSettings
from query_doctor.web.trusted_artifacts import batch_case_artifact_dirs, resolve_batch_case_dir


MAX_METADATA_FACTS_BYTES = 512 * 1024
TABLE_METADATA_SUMMARY_KEYS = {
    "context file": "context file",
    "context path": "context path",
    "table metadata facts": "table metadata facts",
    "tables requested": "tables requested",
    "read-only statements only": "read-only statements only",
    "error": "error",
}
TABLE_METADATA_TABLE_KEYS = {
    "object type": "object type",
    "table stats rows": "table stats rows",
    "table stats row-count completeness": "table stats row-count completeness",
    "table stats size": "table stats size",
    "column stats columns observed": "column stats columns observed",
    "column stats missing/unknown markers": "column stats missing/unknown markers",
    "column stats completeness": "column stats completeness",
    "column stats columns": "column stats columns",
    "file format": "file format",
    "partition columns": "partition columns",
}
TABLE_METADATA_TABLE_KEYS_START = {"table", "table name", "referenced table"}
CM_METRIC_SIGNAL_LABELS = {
    "admission_pool_pressure": "Admission/pool pressure",
    "host_cpu_pressure": "Host CPU pressure",
    "daemon_memory_growth": "Daemon memory growth",
    "daemon_memory_pressure": "Daemon memory pressure",
    "host_disk_io_pressure": "Host disk I/O pressure",
    "hdfs_datanode_io_pressure": "HDFS DataNode I/O pressure",
    "network_io_spike": "Network I/O spike",
}


def load_specific_query_metadata_facts(case_dir: Path) -> dict[str, Any] | None:
    fallback_facts: dict[str, Any] | None = None
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        facts = load_batch_case_analysis_metadata_facts(artifact_dir)
        if facts and facts.get("tables"):
            return facts
        if facts and fallback_facts is None:
            fallback_facts = facts
        context_facts = load_batch_case_impala_context_facts(artifact_dir)
        if context_facts:
            return context_facts
    return fallback_facts


def load_specific_query_cm_metrics_facts(case_dir: Path) -> dict[str, Any] | None:
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        facts = load_case_analysis_cm_metrics_facts(artifact_dir)
        if facts:
            return facts
    return None


def load_specific_query_runtime_diagnosis_facts(case_dir: Path) -> dict[str, Any] | None:
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        facts = load_case_analysis_runtime_diagnosis_facts(artifact_dir)
        if facts:
            return facts
    return None


def load_specific_query_cluster_runtime_context_facts(case_dir: Path) -> dict[str, Any] | None:
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        facts = load_case_analysis_cluster_runtime_context_facts(artifact_dir)
        if facts:
            return facts
    return None


def load_batch_case_metadata_facts(settings: WebSettings, case: dict[str, object]) -> dict[str, Any] | None:
    case_dir = resolve_batch_case_dir(settings, case)
    if case_dir is None:
        return None
    fallback_facts: dict[str, Any] | None = None
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        facts = load_batch_case_analysis_metadata_facts(artifact_dir)
        if facts and facts.get("tables"):
            return facts
        if facts and fallback_facts is None:
            fallback_facts = facts
        context_facts = load_batch_case_impala_context_facts(artifact_dir)
        if context_facts:
            return context_facts
    return fallback_facts


def load_batch_case_cm_metrics_facts(settings: WebSettings, case: dict[str, object]) -> dict[str, Any] | None:
    case_dir = resolve_batch_case_dir(settings, case)
    if case_dir is None:
        return None
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        facts = load_case_analysis_cm_metrics_facts(artifact_dir)
        if facts:
            return facts
    return None


def load_batch_case_runtime_diagnosis_facts(settings: WebSettings, case: dict[str, object]) -> dict[str, Any] | None:
    case_dir = resolve_batch_case_dir(settings, case)
    if case_dir is None:
        return None
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        facts = load_case_analysis_runtime_diagnosis_facts(artifact_dir)
        if facts:
            return facts
    return None


def load_batch_case_cluster_runtime_context_facts(settings: WebSettings, case: dict[str, object]) -> dict[str, Any] | None:
    case_dir = resolve_batch_case_dir(settings, case)
    if case_dir is None:
        return None
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        facts = load_case_analysis_cluster_runtime_context_facts(artifact_dir)
        if facts:
            return facts
    return None


def load_batch_case_analysis_metadata_facts(case_dir: Path) -> dict[str, Any] | None:
    try:
        facts_path = (case_dir / "analysis_facts.md").resolve(strict=True)
        facts_path.relative_to(case_dir)
        if facts_path.stat().st_size > MAX_METADATA_FACTS_BYTES:
            return None
        text = facts_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None
    return parse_table_metadata_context_facts(text)


def load_case_analysis_cm_metrics_facts(case_dir: Path) -> dict[str, Any] | None:
    try:
        facts_path = (case_dir / "analysis_facts.md").resolve(strict=True)
        facts_path.relative_to(case_dir)
        if facts_path.stat().st_size > MAX_METADATA_FACTS_BYTES:
            return None
        text = facts_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None
    return parse_cm_metrics_facts(text)


def load_case_analysis_runtime_diagnosis_facts(case_dir: Path) -> dict[str, Any] | None:
    try:
        facts_path = (case_dir / "analysis_facts.md").resolve(strict=True)
        facts_path.relative_to(case_dir)
        if facts_path.stat().st_size > MAX_METADATA_FACTS_BYTES:
            return None
        text = facts_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None
    return parse_runtime_diagnosis_facts(text)


def load_case_analysis_cluster_runtime_context_facts(case_dir: Path) -> dict[str, Any] | None:
    try:
        facts_path = (case_dir / "analysis_facts.md").resolve(strict=True)
        facts_path.relative_to(case_dir)
        if facts_path.stat().st_size > MAX_METADATA_FACTS_BYTES:
            return None
        text = facts_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None
    return parse_cluster_runtime_context_facts(text)


def load_batch_case_impala_context_facts(case_dir: Path) -> dict[str, Any] | None:
    for candidate in (
        case_dir / "impala_context.json",
        case_dir / "impala_context" / "impala_context.json",
    ):
        try:
            context_path = candidate.resolve(strict=True)
            context_path.relative_to(case_dir)
            if context_path.stat().st_size > MAX_METADATA_FACTS_BYTES:
                return None
            payload = json.loads(context_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        context = table_metadata_facts.context_from_payload(payload, context_path, case_dir)
        return convert_table_metadata_context_for_web(context)
    return None


def convert_table_metadata_context_for_web(context: dict[str, Any]) -> dict[str, Any] | None:
    tables = context.get("tables")
    if not isinstance(tables, list):
        return None
    converted = [convert_table_metadata_table_for_web(table) for table in tables if isinstance(table, dict)]
    if not converted and not context:
        return None
    return {
        "summary": {
            "context file": context.get("context_file", "unknown"),
            "table metadata facts": context.get("table_metadata_facts", "unknown"),
            "tables requested": str(context.get("tables_requested", "unknown")),
            "read-only statements only": context.get("read_only_statements_only", "unknown"),
        },
        "tables": converted,
        "statement_counts": metadata_statement_counts(converted),
    }


def convert_table_metadata_table_for_web(table: dict[str, Any]) -> dict[str, Any]:
    return {
        "table": table.get("table", "unknown"),
        "object type": table.get("object_type", "unknown"),
        "statements": table.get("statements") if isinstance(table.get("statements"), dict) else {},
        "table stats row-count completeness": table.get("table_stats_row_count_completeness", "unknown"),
        "column stats columns observed": table.get("column_stats_columns_observed", "unknown"),
        "column stats missing/unknown markers": table.get("column_stats_missing_markers", "unknown"),
        "column stats completeness": table.get("column_stats_completeness", "unknown"),
        "file format": table.get("file_format", "unknown"),
        "partition columns": ", ".join(str(item) for item in table.get("partition_columns") or []) or "unknown",
    }


def parse_table_metadata_context_facts(text: str) -> dict[str, Any] | None:
    in_section = False
    summary: dict[str, str] = {}
    tables: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            in_section = line == "## Table Metadata Context"
            current = None
            continue
        if not in_section:
            continue
        if line.startswith("### "):
            table_name = parse_table_metadata_heading(line)
            if table_name:
                current = {"table": table_name, "statements": {}}
                tables.append(current)
            else:
                current = None
            continue
        if not line.startswith("- ") or ": " not in line:
            continue
        key, value = line[2:].split(": ", 1)
        key = key.strip()
        value = clean_metadata_fact_value(value)
        key_lower = key.lower()
        if key_lower in TABLE_METADATA_TABLE_KEYS_START:
            if value:
                current = {"table": value, "statements": {}}
                tables.append(current)
            continue
        if current is None:
            if key_lower in TABLE_METADATA_SUMMARY_KEYS:
                summary[TABLE_METADATA_SUMMARY_KEYS[key_lower]] = value
            continue
        statement = parse_table_metadata_statement_status_key(key)
        if statement:
            current.setdefault("statements", {})[statement] = value
        elif key_lower in TABLE_METADATA_TABLE_KEYS:
            current[TABLE_METADATA_TABLE_KEYS[key_lower]] = value
    if not summary and not tables:
        return None
    return {
        "summary": summary,
        "tables": tables,
        "statement_counts": metadata_statement_counts(tables),
    }


def parse_cm_metrics_facts(text: str) -> dict[str, Any] | None:
    section = ""
    in_limitations = False
    summary: dict[str, str] = {}
    correlation_summary: dict[str, str] = {}
    signal_values: dict[str, dict[str, str]] = {
        key: {"label": label}
        for key, label in CM_METRIC_SIGNAL_LABELS.items()
    }
    correlation_values: dict[str, dict[str, str]] = {
        key: {"label": label}
        for key, label in CM_METRIC_SIGNAL_LABELS.items()
    }
    current_correlation_key = ""
    limitations: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            if line == "## CM Metrics Facts":
                section = "facts"
            elif line == "## CM Metrics Correlation":
                section = "correlation"
            else:
                section = ""
            in_limitations = False
            current_correlation_key = ""
            continue
        if not section:
            continue
        if line.startswith("### "):
            in_limitations = section == "facts" and line == "### CM metrics limitations"
            continue
        if not line.startswith("- "):
            continue
        bullet = line[2:].strip()
        if section == "facts" and in_limitations:
            if bullet:
                limitations.append(clean_metadata_fact_value(bullet))
            continue
        if ": " not in bullet:
            continue
        key, value = bullet.split(": ", 1)
        key = key.strip()
        value = clean_metadata_fact_value(value)
        if section == "facts" and key in {
            "status",
            "metrics_profile",
            "coverage",
            "availability",
            "unavailable_metrics",
            "no_data_metrics",
        }:
            summary[key] = value
            continue
        if section == "facts" and key.endswith("_basis"):
            signal_key = key.removesuffix("_basis")
            if signal_key in signal_values:
                signal_values[signal_key]["basis"] = value
            continue
        if section == "facts" and key in signal_values:
            signal_values[key]["status"] = value
            continue
        if section == "correlation" and key in {"status", "coverage", "correlated_signals", "context_only_signals", "guardrail"}:
            correlation_summary[key] = value
            current_correlation_key = ""
            continue
        if section == "correlation" and key in correlation_values:
            status, _, rest = value.partition(" ")
            correlation_values[key]["status"] = clean_metadata_fact_value(status)
            match = re.search(r"metric=([^,\s)]+)", rest)
            if match:
                correlation_values[key]["metric_status"] = clean_metadata_fact_value(match.group(1))
            match = re.search(r"strength=([^,\s)]+)", rest)
            if match:
                correlation_values[key]["strength"] = clean_metadata_fact_value(match.group(1))
            current_correlation_key = key
            continue
        if section == "correlation" and current_correlation_key and key in {"basis", "interpretation"}:
            correlation_values[current_correlation_key][key] = value
    signals = [
        signal
        for signal in signal_values.values()
        if signal.get("status") or signal.get("basis")
    ]
    correlations = [
        correlation
        for correlation in correlation_values.values()
        if correlation.get("status") or correlation.get("interpretation")
    ]
    if not summary and not signals and not limitations and not correlation_summary and not correlations:
        return None
    return {
        "summary": summary,
        "signals": signals,
        "correlation_summary": correlation_summary,
        "correlations": correlations,
        "limitations": limitations[:5],
    }


def parse_runtime_diagnosis_facts(text: str) -> dict[str, Any] | None:
    section = ""
    summary: dict[str, str] = {}
    signals: list[dict[str, Any]] = []
    current_signal: dict[str, Any] | None = None
    in_evidence = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            section = "runtime_diagnosis" if line == "## Runtime Diagnosis" else ""
            current_signal = None
            in_evidence = False
            continue
        if not section:
            continue
        if line.startswith("### "):
            title = clean_metadata_fact_value(line.removeprefix("###").strip())
            current_signal = {"title": title, "evidence": []}
            signals.append(current_signal)
            in_evidence = False
            continue
        if not line.startswith("- "):
            continue
        bullet = line[2:].strip()
        if current_signal is not None and in_evidence and bullet:
            current_signal.setdefault("evidence", []).append(clean_metadata_fact_value(bullet))
            continue
        if ": " not in bullet:
            continue
        key, value = bullet.split(": ", 1)
        key = key.strip()
        value = clean_metadata_fact_value(value)
        if current_signal is None:
            if key in {"status", "summary", "guardrail"}:
                summary[key] = value
            continue
        if key == "evidence":
            in_evidence = True
            if value and value != "none":
                current_signal.setdefault("evidence", []).append(value)
            continue
        if key in {"status", "interpretation"}:
            current_signal[key] = value
            in_evidence = False
    if not summary and not signals:
        return None
    return {
        "status": summary.get("status", "unknown"),
        "summary": summary.get("summary", "unknown"),
        "guardrail": summary.get("guardrail", ""),
        "signals": signals,
    }


def parse_cluster_runtime_context_facts(text: str) -> dict[str, Any] | None:
    section = ""
    summary: dict[str, str] = {}
    signal_rollup: dict[str, str] = {}
    limitations: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            section = "cluster_runtime_context" if line == "## Cluster Runtime Context" else ""
            continue
        if not section:
            continue
        if line.startswith("### "):
            heading = line.removeprefix("###").strip()
            if heading == "Signal rollup":
                section = "cluster_runtime_rollup"
            elif heading == "Cluster runtime limitations":
                section = "cluster_runtime_limitations"
            else:
                section = "cluster_runtime_context"
            continue
        if not line.startswith("- "):
            continue
        bullet = line[2:].strip()
        if section == "cluster_runtime_limitations":
            if bullet:
                limitations.append(clean_metadata_fact_value(bullet))
            continue
        if ": " not in bullet:
            continue
        key, value = bullet.split(": ", 1)
        key = key.strip()
        value = clean_metadata_fact_value(value)
        if section == "cluster_runtime_rollup":
            if key in {
                "observed_signals",
                "correlated_signals",
                "context_only_signals",
                "unknown_signals",
                "not_observed_signals",
            }:
                signal_rollup[key] = value
            continue
        if key in {
            "status",
            "collection_status",
            "coverage",
            "metrics_profile",
            "window_scope",
            "limit_summary",
            "scoring_contribution",
            "guardrail",
        }:
            summary[key] = value
    if not summary and not signal_rollup and not limitations:
        return None
    return {
        "summary": summary,
        "signal_rollup": signal_rollup,
        "limitations": limitations[:8],
    }


def parse_table_metadata_heading(line: str) -> str:
    heading = line.removeprefix("###").strip()
    if heading.lower().startswith("table:"):
        return heading.split(":", 1)[1].strip()
    return ""


def parse_table_metadata_statement_status_key(key: str) -> str:
    key_upper = key.upper()
    if not key_upper.endswith(" STATUS"):
        return ""
    statement = key_upper.removesuffix(" STATUS").strip()
    return statement if statement in table_metadata_facts.STATEMENTS else ""


def clean_metadata_fact_value(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text.startswith("`") and text.endswith("`"):
        return text[1:-1]
    return text


def metadata_statement_counts(tables: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in tables:
        statements = table.get("statements")
        if not isinstance(statements, dict):
            continue
        for status in statements.values():
            key = str(status or "unknown")
            counts[key] = counts.get(key, 0) + 1
    return counts
