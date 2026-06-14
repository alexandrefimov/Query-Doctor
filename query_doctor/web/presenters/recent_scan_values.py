"""Safe value normalization helpers for Recent scan presenters."""

from __future__ import annotations

import re
from typing import Any

from query_doctor.safety.browser_display import redact_browser_display_text


STATEMENT_LABELS = {
    "SHOW CREATE TABLE": "create metadata",
    "SHOW TABLE STATS": "table stats",
    "SHOW COLUMN STATS": "column stats",
}
METADATA_UNKNOWN_MARKERS = {"", "-1", "null", "none", "unknown", "n/a", "nan"}


def safe_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y"}


def safe_statement_statuses(statements: dict[Any, Any]) -> dict[str, Any]:
    return {
        statement_display_label(key): safe_display_value(value) for key, value in statements.items()
    }


def metadata_fact_limitations(table: dict[str, Any], statements: dict[str, Any]) -> str:
    limitations: list[str] = []
    object_type = str(table.get("object type") or "unknown")
    table_stats = metadata_stat_text(table.get("table stats row-count completeness"))
    column_stats = metadata_stat_text(table.get("column stats completeness"))
    partition_count = numeric_count(table.get("partition count"))
    known_partitions = numeric_count(table.get("partitions with known row count"))
    unknown_partitions = numeric_count(table.get("partitions with unknown row count"))
    zero_partitions = numeric_count(table.get("partitions with zero row count"))
    ndv_missing_columns = numeric_count(table.get("column stats NDV-missing columns"))
    size_missing_columns = numeric_count(table.get("column stats size-missing columns"))
    all_missing_columns = numeric_count(table.get("column stats all-missing columns"))
    if object_type == "view":
        limitations.append("view metadata stats not applicable")
    for statement, status in statements.items():
        status_text = str(status or "unknown")
        if status_text in {"error", "too_large", "timeout", "not_applicable"}:
            limitations.append(f"{statement}: {status_text}")
    if table_stats not in {"available", "unknown"}:
        limitations.append(f"row-count stats: {safe_display_text(table_stats)}")
    if partition_count > 0:
        limitations.append(
            "partition row counts: "
            f"{known_partitions}/{partition_count} known, "
            f"{unknown_partitions} unknown, {zero_partitions} zero"
        )
    if column_stats not in {"available", "complete", "unknown"}:
        limitations.append(f"column stats: {safe_display_text(column_stats)}")
    column_status_parts = []
    if ndv_missing_columns:
        column_status_parts.append(f"{ndv_missing_columns} NDV missing")
    if size_missing_columns:
        column_status_parts.append(f"{size_missing_columns} size missing")
    if all_missing_columns:
        column_status_parts.append(f"{all_missing_columns} all missing")
    if column_status_parts:
        limitations.append("column stats detail: " + ", ".join(column_status_parts))
    return "; ".join(limitations) if limitations else "none observed"


def statement_display_label(statement: Any) -> str:
    return STATEMENT_LABELS.get(str(statement), safe_display_text(statement))


def metadata_statement_counts_summary(statement_counts: dict[Any, Any]) -> str:
    parts = [
        ("ok", statement_counts.get("ok", 0)),
        ("error", statement_counts.get("error", 0)),
        ("not_applicable", statement_counts.get("not_applicable", 0)),
        ("too_large", statement_counts.get("too_large", 0)),
    ]
    return " / ".join(f"{int(numeric_value(value))} {label}" for label, value in parts)


def metadata_score_reasons(case: dict[str, Any]) -> list[str]:
    reasons = case.get("score_reasons")
    if not isinstance(reasons, list):
        return []
    result: list[str] = []
    for reason in reasons:
        text = safe_display_text(reason)
        lower = text.lower()
        if any(marker in lower for marker in ("metadata", "stats", "statistic")):
            result.append(text)
    return result


def has_metadata_aggregate_facts(case: dict[str, Any]) -> bool:
    metadata_status = str(case.get("metadata_status") or "").lower()
    if metadata_status in {"collected", "failed", "partial"}:
        return True
    for key in (
        "referenced_table_count",
        "collectable_metadata_table_count",
        "collected_metadata_table_count",
        "too_large_count",
    ):
        if numeric_value(case.get(key)) > 0:
            return True
    return bool(metadata_score_reasons(case))


def batch_report_status(case: dict[str, Any]) -> str:
    validation = str(case.get("report_validation_status") or "not_run")
    generated = case.get("report_generated") is True
    if validation == "failed_partial_untrusted":
        return "partial untrusted"
    if generated and validation == "passed":
        return "validated report"
    if generated:
        return f"generated/{safe_display_text(validation)}"
    return safe_display_text(validation)


def batch_case_display_report_status(
    case: dict[str, Any], report_state: dict[str, Any] | None = None
) -> str:
    if isinstance(report_state, dict):
        status = str(report_state.get("status") or "")
        if status == "generated" or report_state.get("trusted"):
            return "validated report"
        if status == "running":
            return "running"
        if status == "failed":
            return "failed"
        if status == "partial_untrusted":
            return "partial untrusted"
    return batch_report_status(case)


def case_has_failure(case: dict[str, Any]) -> bool:
    if case.get("failure_category"):
        return True
    return any(
        case.get(name) == "failed"
        for name in (
            "collection_status",
            "analysis_status",
            "metadata_status",
            "report_validation_status",
        )
    )


def batch_case_id(case: dict[str, Any]) -> str | None:
    value = case.get("case_index")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return f"case-{parsed:03d}"


def numeric_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def numeric_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_display_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    return safe_display_text(value)


def safe_metadata_stat_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return "unknown" if value is None else value
    if isinstance(value, (int, float)):
        return "unknown" if value < 0 else value
    text = str(value).strip()
    if is_metadata_unknown_marker(text):
        return "unknown"
    return safe_display_text(text)


def metadata_stat_text(value: Any) -> str:
    return str(safe_metadata_stat_value(value) or "unknown")


def is_metadata_unknown_marker(value: str) -> bool:
    text = str(value).strip().lower()
    if text in METADATA_UNKNOWN_MARKERS:
        return True
    try:
        return float(text.replace(",", "")) < 0
    except ValueError:
        return False


def safe_display_text(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "unknown"
    return redact_browser_display_text(
        value,
        redact_field_names=True,
        redact_artifact_markers=True,
        redact_model_names=True,
        redact_infrastructure=True,
    )


def safe_optimization_display_text(value: Any) -> str:
    text = str(value if value is not None else "unknown")
    text = re.sub(r"\b(statistics|stats)\s+refresh\b", r"\1 update", text, flags=re.IGNORECASE)
    return redact_browser_display_text(
        text,
        redact_field_names=True,
        redact_artifact_markers=True,
        redact_model_names=True,
        redact_sql_snippets=True,
        redact_infrastructure=True,
    )
