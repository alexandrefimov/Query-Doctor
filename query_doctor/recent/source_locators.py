"""Raw-free source locators for Recent scan action candidates."""

from __future__ import annotations

import re
from typing import Any

from query_doctor.optimizer.source_sql import (
    QueryOptimizationError,
    extract_optimizable_source_sql,
    read_source_sql,
)
from query_doctor.optimizer.sql import OptimizerSqlError
from query_doctor.recent.batch_models import CaseResult
from query_doctor.recent.source_coordinates import sql_source_coordinates
from query_doctor.safety.browser_display import redact_browser_display_text

SOURCE_LOCATOR_GROUPS = {
    "query_optimization",
    "stats_refresh",
    "runtime_admission",
}

SOURCE_LOCATOR_IDS = {
    "metadata_referenced_stats",
    "metadata_table_stats",
    "plan_cardinality_anomaly",
    "plan_data_movement_operator",
    "plan_memory_anomaly",
    "plan_top_time_operator",
    "profile_resource_admission_evidence",
    "profile_timing_admission_evidence",
    "runtime_admission_window",
    "sql_cte_block",
    "sql_derived_table",
    "sql_downstream_cte_filter",
    "sql_final_select_filter",
    "sql_join_filter_review",
    "sql_mixed_downstream_filters",
    "sql_union_branch",
}

OPERATOR_CATEGORIES = {
    "AGGREGATE",
    "ANALYTIC",
    "EXCHANGE",
    "HASH JOIN",
    "HDFS SCAN",
    "NESTED LOOP JOIN",
    "SCAN",
    "SORT",
    "UNION",
}

SAFE_OPERATOR_ID_RE = re.compile(r"^[A-Za-z0-9_:-]{1,32}$")


def build_source_locators(
    case: CaseResult,
    analysis: dict[str, object] | None,
    *,
    include_source_coordinates: bool = False,
) -> dict[str, list[dict[str, str]]]:
    """Build browser-safe locator hints from already trusted structured facts."""

    support = case.optimizer_rewrite_support.to_dict() if case.optimizer_rewrite_support else {}
    coordinates = source_coordinates_for_case(case) if include_source_coordinates else {}
    locators = {
        "query_optimization": query_optimization_locators(
            case, analysis, support, coordinates=coordinates
        ),
        "stats_refresh": stats_refresh_locators(case, analysis),
        "runtime_admission": runtime_admission_locators(case),
    }
    return {key: value for key, value in locators.items() if value}


def query_optimization_locators(
    case: CaseResult,
    analysis: dict[str, object] | None,
    support: dict[str, object],
    *,
    coordinates: dict[str, str],
) -> list[dict[str, str]]:
    locators: list[dict[str, str]] = []
    candidate = case.query_optimization_candidate
    if candidate is None or candidate.tier not in {"high", "medium"}:
        return locators

    add_sql_shape_locators(locators, support, coordinates=coordinates)
    if analysis:
        add_operator_locator(
            locators,
            "plan_cardinality_anomaly",
            first_operator(analysis.get("cardinality_anomalies")),
        )
        add_operator_locator(
            locators,
            "plan_memory_anomaly",
            first_operator(analysis.get("memory_anomalies")),
        )
        add_operator_locator(
            locators,
            "plan_top_time_operator",
            first_operator(analysis.get("top_operators_by_time")),
        )
        if finding_present(analysis, "large_intermediate_or_exchange_traffic"):
            locators.append(locator("plan_data_movement_operator", "EXCHANGE/data movement"))

    reason_text = " ".join(candidate.reasons + candidate.suggested_review_areas).lower()
    if "join" in reason_text or "filter" in reason_text:
        locators.append(
            locator(
                "sql_join_filter_review",
                "join and filter placement",
                coordinate=coordinates.get("sql_join_filter_review", ""),
            )
        )
    return dedupe_locators(locators, limit=5)


def stats_refresh_locators(
    case: CaseResult,
    analysis: dict[str, object] | None,
) -> list[dict[str, str]]:
    locators: list[dict[str, str]] = []
    candidate = case.stats_optimization_candidate
    if candidate is None or candidate.tier not in {"high", "medium"}:
        return locators

    if case.referenced_table_count or case.metadata_status in {"collected", "partial"}:
        locators.append(
            locator(
                "metadata_referenced_stats",
                referenced_stats_detail(case.referenced_table_count),
            )
        )
    if case.table_stats_status and case.table_stats_status != "unknown":
        locators.append(locator("metadata_table_stats", safe_stats_status(case.table_stats_status)))
    if analysis:
        add_operator_locator(
            locators,
            "plan_cardinality_anomaly",
            first_operator(analysis.get("cardinality_anomalies")),
        )
        add_operator_locator(
            locators,
            "plan_memory_anomaly",
            first_operator(analysis.get("memory_anomalies")),
        )
    if case.zero_row_estimate_gap_count:
        locators.append(locator("plan_cardinality_anomaly", "zero or unknown row estimate gap"))
    return dedupe_locators(locators, limit=5)


def runtime_admission_locators(case: CaseResult) -> list[dict[str, str]]:
    bottleneck = (
        case.case_primary_bottleneck if isinstance(case.case_primary_bottleneck, dict) else {}
    )
    if str(bottleneck.get("label") or "").strip().lower() != "runtime_admission":
        return []
    locators = [locator("runtime_admission_window", "case runtime window")]
    reasons = normalized_bottleneck_reasons(bottleneck)
    if "admission_wait_source_profile_resource_facts" in reasons:
        locators.append(
            locator(
                "profile_resource_admission_evidence",
                "query-specific admission result or resource wait",
            )
        )
    if "admission_wait_source_profile_timing_facts" in reasons:
        locators.append(
            locator(
                "profile_timing_admission_evidence",
                "query timeline admission phase",
            )
        )
    return dedupe_locators(locators, limit=5)


def normalized_bottleneck_reasons(bottleneck: dict[str, object]) -> set[str]:
    reasons = bottleneck.get("reasons")
    if not isinstance(reasons, (list, tuple)):
        return set()
    return {str(reason or "").strip().lower() for reason in reasons if reason is not None}


def add_sql_shape_locators(
    locators: list[dict[str, str]],
    support: dict[str, object],
    *,
    coordinates: dict[str, str],
) -> None:
    cte_count = positive_int(support.get("cte_count"))
    if cte_count:
        locators.append(
            locator(
                "sql_cte_block",
                f"{cte_count} CTEs",
                coordinate=coordinates.get("sql_cte_block", ""),
            )
        )
    predicate_origin = str(support.get("cte_predicate_origin_status") or "").strip().lower()
    if predicate_origin == "final_select_filter":
        locators.append(
            locator(
                "sql_final_select_filter",
                "predicate near final SELECT",
                coordinate=coordinates.get("sql_final_select_filter", ""),
            )
        )
    elif predicate_origin == "downstream_cte_filter":
        locators.append(
            locator(
                "sql_downstream_cte_filter",
                "predicate in downstream CTE",
                coordinate=coordinates.get("sql_downstream_cte_filter", ""),
            )
        )
    elif predicate_origin in {"mixed_downstream_filters", "mixed"}:
        locators.append(
            locator(
                "sql_mixed_downstream_filters",
                "mixed downstream filters",
                coordinate=coordinates.get("sql_mixed_downstream_filters", ""),
            )
        )
    union_branches = positive_int(support.get("cte_union_branch_count"))
    if union_branches:
        locators.append(
            locator(
                "sql_union_branch",
                f"{union_branches} UNION branches",
                coordinate=coordinates.get("sql_union_branch", ""),
            )
        )
    derived_count = positive_int(support.get("derived_table_count"))
    if derived_count:
        locators.append(
            locator(
                "sql_derived_table",
                f"{derived_count} derived tables",
                coordinate=coordinates.get("sql_derived_table", ""),
            )
        )
    derived_origin = str(support.get("derived_predicate_origin_status") or "").strip().lower()
    if derived_origin == "outer_filter":
        locators.append(
            locator(
                "sql_derived_table",
                "outer filter on derived table",
                coordinate=coordinates.get("sql_derived_table", ""),
            )
        )


def add_operator_locator(
    locators: list[dict[str, str]],
    locator_id: str,
    operator: dict[str, object] | None,
) -> None:
    detail = operator_detail(operator)
    if detail:
        locators.append(locator(locator_id, detail))


def locator(locator_id: str, detail: str = "", *, coordinate: str = "") -> dict[str, str]:
    if locator_id not in SOURCE_LOCATOR_IDS:
        raise ValueError(f"unknown source locator id: {locator_id}")
    clean_detail = safe_detail(detail)
    clean_coordinate = safe_coordinate(coordinate)
    result = {"id": locator_id}
    if clean_coordinate:
        result["coordinate"] = clean_coordinate
    if clean_detail:
        result["detail"] = clean_detail
    return result


def dedupe_locators(
    locators: list[dict[str, str]],
    *,
    limit: int,
) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in locators:
        locator_id = item.get("id", "")
        coordinate = item.get("coordinate", "")
        detail = item.get("detail", "")
        if locator_id not in SOURCE_LOCATOR_IDS:
            continue
        key = (locator_id, coordinate, detail)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(
            {
                "id": locator_id,
                **({"coordinate": coordinate} if coordinate else {}),
                **({"detail": detail} if detail else {}),
            }
        )
        if len(deduped) >= limit:
            break
    return deduped


def source_coordinates_for_case(case: CaseResult) -> dict[str, str]:
    if case.actual_case_dir is None:
        return {}
    try:
        source = extract_optimizable_source_sql(read_source_sql(case.actual_case_dir))
    except (OSError, OptimizerSqlError, QueryOptimizationError, ValueError):
        return {}
    if source.scope != "read_only_statement":
        return {}
    return sql_source_coordinates(source.sql)


def first_operator(value: object) -> dict[str, object] | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, dict):
            return item
    return None


def operator_detail(operator: dict[str, object] | None) -> str:
    if not operator:
        return ""
    category = operator_category(operator.get("operator_name") or operator.get("label"))
    if category in {"UNKNOWN", "OTHER"}:
        return ""
    operator_id = safe_operator_id(operator.get("operator_id"))
    prefix = f"node {operator_id}" if operator_id else "operator"
    flags: list[str] = []
    join_kind = safe_join_kind(operator.get("join_kind"))
    if join_kind:
        flags.append(join_kind)
    if operator.get("is_partitioned") is True:
        flags.append("partitioned")
    suffix = f" ({', '.join(flags)})" if flags else ""
    return f"{prefix} {category}{suffix}"


def operator_category(value: object) -> str:
    name = str(value or "").upper()
    for category in sorted(OPERATOR_CATEGORIES, key=len, reverse=True):
        if category in name:
            return category
    return "OTHER" if name else "UNKNOWN"


def safe_operator_id(value: object) -> str:
    text = str(value or "").strip()
    return text if SAFE_OPERATOR_ID_RE.fullmatch(text) else ""


def safe_join_kind(value: object) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    words = [word for word in re.split(r"\s+", text) if word.isalpha()]
    if not words or len(words) > 3:
        return ""
    return " ".join(words).lower()


def finding_present(analysis: dict[str, object], finding_id: str) -> bool:
    for finding in analysis.get("findings") or []:
        if isinstance(finding, dict) and finding.get("id") == finding_id:
            return True
    return False


def referenced_stats_detail(count: object) -> str:
    parsed = positive_int(count)
    if parsed <= 0:
        return "referenced tables"
    if parsed == 1:
        return "1 referenced table"
    return f"{parsed} referenced tables"


def safe_stats_status(value: object) -> str:
    text = str(value or "").strip().lower()
    allowed = {
        "available",
        "collected",
        "failed",
        "missing",
        "missing_or_unknown",
        "not_checked",
        "not_applicable",
        "partial",
        "skipped",
        "unknown",
    }
    return text.replace("_", " ") if text in allowed else "status unknown"


def positive_int(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def safe_detail(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = redact_browser_display_text(
        text,
        redact_field_names=True,
        redact_artifact_markers=True,
        redact_model_names=True,
        redact_sql_snippets=True,
        redact_infrastructure=True,
        max_chars=120,
    )
    text = re.sub(r"[^A-Za-z0-9 /:().,_-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:120]


def safe_coordinate(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if re.fullmatch(r"line [1-9]\d{0,5}", text):
        return text
    if re.fullmatch(r"lines [1-9]\d{0,5}-[1-9]\d{0,5}", text):
        start, end = (int(part) for part in text.removeprefix("lines ").split("-", 1))
        return text if start <= end else ""
    return ""
