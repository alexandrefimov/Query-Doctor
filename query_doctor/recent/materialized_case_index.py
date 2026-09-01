"""Raw-free Recent materialized case index projection."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from query_doctor.safety.browser_display import redact_browser_display_text


SCHEMA_VERSION = 1
MAX_TEXT_CHARS = 512
MAX_LIST_ITEMS = 20

SUMMARY_SOURCE_FIELDS = (
    "mode",
    "query_profile_source",
    "runtime_metrics_provider",
    "source_visibility",
)
SUMMARY_SCOPE_FIELDS = (
    "recent_window_minutes",
    "from_time",
    "to_time",
    "duration_filter",
    "duration_filter_mode",
    "query_type_filter",
    "include_failed",
    "include_running",
    "only_running",
    "user_filter_present",
    "pool_filter_present",
    "order",
)
SUMMARY_COVERAGE_FIELDS = (
    "selected_count",
    "summaries_inspected",
    "candidate_exclusion_count",
    "discovery_failed",
    "scan_too_broad",
    "cm_summary_safety_cap_hit",
    "cm_summary_raw_scan_cap_hit",
    "time_sharded",
    "time_shard_count",
    "metadata_top_limit",
    "collect_cm_timeseries",
    "collect_prometheus_timeseries",
)

CASE_FIELDS = (
    "case_index",
    "candidate_rank",
    "triage_rank",
    "query_id",
    "duration_sec",
    "start_time",
    "end_time",
    "user",
    "pool",
    "query_type",
    "sql_verb",
    "collection_status",
    "analysis_status",
    "metadata_status",
    "table_stats_status",
    "referenced_table_count",
    "collectable_metadata_table_count",
    "collected_metadata_table_count",
    "skipped_due_to_max_table_limit",
    "too_large_count",
    "score",
    "score_severity",
    "score_reasons",
    "scoring_evidence_source",
    "scoring_fallback_reason",
    "query_optimization_rank",
    "stats_optimization_rank",
    "case_primary_bottleneck",
    "source_locators",
    "cardinality_anomaly_count",
    "memory_anomaly_count",
    "zero_row_estimate_gap_count",
    "zero_memory_estimate_gap_count",
    "backend_data_skew",
    "host_tail_candidate_count",
    "execution_tail_candidate_count",
    "report_generated",
    "report_validation_status",
    "_optimizer_artifact_status",
    "metadata_refreshed",
    "failure_category",
    "failure_reason",
    "profile_status",
    "cm_collect_seconds",
    "analysis_seconds",
    "report_seconds",
    "total_seconds",
    "group_fingerprint",
    "workload_fingerprint",
    "workload_fingerprint_incomplete",
    "workload_fingerprint_incomplete_fields",
    "workload_group_member_count",
    "workload_group_duration_sec_p95",
    "workload_baseline_duration_sec_p95",
    "workload_baseline_sample_count",
    "workload_regression",
    "workload_shape",
)

QUERY_OPTIMIZATION_FIELDS = (
    "score",
    "tier",
    "confidence",
    "impact",
    "reasons",
    "counter_signals",
    "suggested_review_areas",
    "evidence_source",
    "evidence_fallback_reason",
)
STATS_OPTIMIZATION_FIELDS = (
    "score",
    "tier",
    "confidence",
    "impact",
    "need_type",
    "table_stats_need",
    "column_stats_need",
    "speed_benefit",
    "reasons",
    "counter_signals",
    "suggested_review_areas",
    "required_confirmation",
    "evidence_detail",
    "evidence_source",
    "evidence_fallback_reason",
)
OPTIMIZER_REWRITE_SUPPORT_FIELDS = (
    "status",
    "label",
    "reason",
    "risk_mode",
    "risk_reasons",
    "recipe_id",
    "recipe_detected",
    "draft_eligibility",
    "draft_eligibility_label",
    "rewriteability_bucket",
    "rewriteability_label",
    "draft_unavailable_reasons",
    "draft_unavailable_class",
    "draft_unavailable_class_label",
    "no_recipe_review_track",
    "cte_count",
    "cte_graph_shape",
    "cte_predicate_origin_status",
    "cte_predicate_path_status",
    "cte_projection_preservation_status",
    "cte_simplification_status",
    "cte_simple_projection_count",
    "cte_expression_projection_count",
    "cte_union_branch_count",
    "cte_union_branch_filter_status",
    "cte_boundary_reasons",
    "derived_table_count",
    "derived_predicate_origin_status",
    "derived_projection_preservation_status",
    "derived_boundary_reasons",
)
PRIMARY_BOTTLENECK_FIELDS = ("label", "confidence", "reasons")
WORKLOAD_SHAPE_FIELDS = (
    "sql_verb",
    "query_type",
    "join_count",
    "cte_count",
    "set_operation_count",
    "scan_count",
    "exchange_count",
    "aggregate_present",
    "window_present",
    "referenced_tables",
)


def build_materialized_case_index(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Build the path-free Recent inbox index projection from a batch summary."""

    cases = tuple(_case_dicts(summary.get("cases")))
    return {
        "schema_version": SCHEMA_VERSION,
        "source": _project_fields(summary, SUMMARY_SOURCE_FIELDS),
        "scope": _project_fields(summary, SUMMARY_SCOPE_FIELDS),
        "coverage": {
            **_project_fields(summary, SUMMARY_COVERAGE_FIELDS),
            "case_count": len(cases),
            "warning_count": len(summary.get("warnings") or ())
            if isinstance(summary.get("warnings"), list)
            else 0,
        },
        "freshness": {
            "state": "materialized_snapshot",
            "from_time": _project_value(summary.get("from_time")),
            "to_time": _project_value(summary.get("to_time")),
            "recent_window_minutes": _project_value(summary.get("recent_window_minutes")),
        },
        "cases": [_project_case(case) for case in cases],
    }


def materialized_case_entries(summary: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Return sanitized case entries from an existing or computed materialized index."""

    existing = summary.get("materialized_case_index")
    if isinstance(existing, Mapping) and existing.get("schema_version") == SCHEMA_VERSION:
        cases = existing.get("cases")
        if isinstance(cases, list):
            return tuple(_project_case(case) for case in _case_dicts(cases))
    index = build_materialized_case_index(summary)
    return tuple(case for case in index["cases"] if isinstance(case, dict))


def _project_case(case: Mapping[str, Any]) -> dict[str, Any]:
    projected = _project_fields(case, CASE_FIELDS)
    case_ref = _case_ref(case.get("case_ref") or case.get("case_index"))
    if case_ref:
        projected["case_ref"] = case_ref

    candidate = case.get("query_optimization_candidate")
    if isinstance(candidate, Mapping):
        projected["query_optimization_candidate"] = _project_fields(
            candidate,
            QUERY_OPTIMIZATION_FIELDS,
        )

    stats_candidate = case.get("stats_optimization_candidate")
    if isinstance(stats_candidate, Mapping):
        projected["stats_optimization_candidate"] = _project_fields(
            stats_candidate,
            STATS_OPTIMIZATION_FIELDS,
        )

    rewrite_support = case.get("optimizer_rewrite_support")
    if isinstance(rewrite_support, Mapping):
        projected["optimizer_rewrite_support"] = _project_fields(
            rewrite_support,
            OPTIMIZER_REWRITE_SUPPORT_FIELDS,
        )

    primary = case.get("case_primary_bottleneck")
    if isinstance(primary, Mapping):
        projected["case_primary_bottleneck"] = _project_fields(
            primary,
            PRIMARY_BOTTLENECK_FIELDS,
        )

    workload_shape = case.get("workload_shape")
    if isinstance(workload_shape, Mapping):
        projected["workload_shape"] = _project_fields(workload_shape, WORKLOAD_SHAPE_FIELDS)

    return projected


def _project_fields(source: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in fields:
        if field in source:
            result[field] = _project_value(source.get(field))
    return result


def _project_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, (list, tuple)):
        return [_project_value(item) for item in value[:MAX_LIST_ITEMS]]
    if isinstance(value, Mapping):
        return {
            _safe_text(key): _project_value(item)
            for key, item in list(value.items())[:MAX_LIST_ITEMS]
            if isinstance(key, str)
        }
    return _safe_text(value)


def _safe_text(value: Any) -> str:
    return redact_browser_display_text(
        value,
        redact_field_names=True,
        redact_artifact_markers=True,
        redact_model_names=True,
        redact_sql_snippets=True,
        redact_infrastructure=True,
        max_chars=MAX_TEXT_CHARS,
    )


def _case_dicts(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _case_ref(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("recent-case-"):
        suffix = text.removeprefix("recent-case-")
        if suffix.isdigit() and int(suffix) > 0:
            return f"recent-case-{int(suffix):03d}"
        return ""
    if text.startswith("case-"):
        suffix = text.removeprefix("case-")
        if suffix.isdigit() and int(suffix) > 0:
            return f"case-{int(suffix):03d}"
        return ""
    try:
        index = int(text)
    except ValueError:
        return ""
    if index <= 0:
        return ""
    return f"case-{index:03d}"
