#!/usr/bin/env python3
"""Audit raw-free Impala diagnostic coverage gaps across batch summaries."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, TextIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.analyzer.data_movement import data_movement_facts_from_analysis  # noqa: E402
from query_doctor.analyzer.case_bottleneck import (  # noqa: E402
    CasePrimaryBottleneck,
    classify_case_primary_bottleneck,
    primary_bottleneck_profile_policy,
)
from query_doctor.analyzer.profile_evidence import (  # noqa: E402
    DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_MS,
    DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_SHARE,
    medium_data_movement_threshold,
)
from query_doctor.analyzer.profile_counter_registry import (  # noqa: E402
    BUNDLED_PROFILE_COUNTER_DEFINITIONS,
)
from query_doctor.analyzer.runtime_metrics import runtime_metrics_context  # noqa: E402
from query_doctor.analyzer.runtime_admission import (  # noqa: E402
    runtime_admission_facts_from_analysis,
)
from query_doctor.analyzer.scan_skew import scan_skew_facts_from_analysis  # noqa: E402
from query_doctor.report.safety_validation import contains_raw_sql_like_text  # noqa: E402
from query_doctor.safety import redaction  # noqa: E402
from scripts.audit_profile_evidence_gates import (  # noqa: E402
    EvidenceGateAuditInputError,
    analysis_path_for,
    bool_value,
    int_value,
    load_json_object,
    resolve_case_dir,
    summary_cases,
    text_value,
)


PRIMARY_BOTTLENECK_LABELS = {
    "stats",
    "sql_shape",
    "runtime_admission",
    "runtime_skew",
    "runtime_data_movement",
    "runtime_memory",
    "runtime_storage",
    "client_fetch_tail",
    "mixed",
    "unknown",
}
PRIMARY_BOTTLENECK_CONFIDENCES = {"high", "medium", "low"}
MEDIUM_OR_BETTER_PRIMARY_CONFIDENCES = {"high", "medium"}
NO_ACTIONABLE_PRIMARY_LABELS = {"missing", "none", "unknown"}
STRICT_PRIMARY_OUT_OF_SCOPE_REASONS = {
    "profile_dialect_not_supported_for_primary",
    "very_short_query_or_unknown_wall_clock",
}
SAFE_UNKNOWN_PRIMARY_REASONS = {
    "codegen_finding_not_primary_supported",
    "data_movement_context_only",
    "memory_estimate_context_only",
    "no_primary_branch_supported",
    "operator_time_not_dominant",
    "profile_dialect_not_supported_for_primary",
    "scan_skew_medium_supporting_only",
    "storage_context_view_only",
    "very_short_query_or_unknown_wall_clock",
    "wall_clock_not_explained_by_mapped_operators",
}
SAFE_UNKNOWN_REASON_SUMMARY_TOKENS = SAFE_UNKNOWN_PRIMARY_REASONS | {
    "missing_reason",
    "tail_candidates",
    "unsafe_reason",
}
UNKNOWN_PRIMARY_REASON_COUNTER_NAMES = {
    "strict_unknown_primary_reason_counts",
    "unknown_primary_reason_counts",
}
SAFE_UNKNOWN_PRIMARY_RESOLUTIONS = {
    "clean_case_no_action_boundary",
    "clean_short_no_action_boundary",
    "diagnostic_evidence_gap",
    "missing_wall_clock_collector_gap",
    "short_query_primary_out_of_scope",
}
UNKNOWN_PRIMARY_RESOLUTION_COUNTER_NAMES = {
    "unknown_primary_resolution_counts",
}
DIRECT_REQUIRED_PROVENANCE_KINDS = ("engine", "profile", "metrics", "events", "metadata")
DIRECT_REQUIRED_OPTIONAL_SOURCES = (
    "json_profile",
    "profile_docs",
    "admission_context",
    "metadata",
    "runtime_metrics",
    "cluster_events",
)
DIRECT_READY_OPTIONAL_STATES = {
    "available",
    "partial",
    "unavailable",
    "not_configured",
    "not_collected",
    "not_applicable",
}
DIRECT_READY_PROVENANCE_STATUSES = {"available", "partial", "unavailable", "none"}
SOURCE_PROVENANCE_KINDS = set(DIRECT_REQUIRED_PROVENANCE_KINDS)
SOURCE_PROVENANCE_STATUSES = DIRECT_READY_PROVENANCE_STATUSES | {
    "failed",
    "not_collected",
    "not_requested",
    "ok",
    "unknown",
}
URL_RE = re.compile(r"\bhttps?://", re.IGNORECASE)
LOCAL_PATH_RE = re.compile(r"(?<![\w/])(?:/private)?/tmp/|(?<![\w/])/Users/")
SUMMARY_SCHEMA_VERSION = "impala_coverage_audit_v1"


@dataclass(frozen=True)
class FollowUpDefinition:
    priority: str
    why: str
    next_step: str


FOLLOW_UPS: dict[str, FollowUpDefinition] = {
    "missing_analysis": FollowUpDefinition(
        "P0",
        "Some selected cases did not reach deterministic analyzer output.",
        "Retry collection or inspect bounded safe failure categories before using the batch for calibration.",
    ),
    "profile_policy_not_supported": FollowUpDefinition(
        "P0",
        "Profile-derived findings must fail closed when the profile policy is unsupported.",
        "Add dialect/source fixtures before widening profile-derived primary routing.",
    ),
    "unknown_primary_bottleneck": FollowUpDefinition(
        "P1",
        "Unknown primary labels show where deterministic evidence is still insufficient.",
        "Sample safe analyzer facts for these cases and add the narrowest missing evidence parser or limitation.",
    ),
    "missing_primary_bottleneck_label": FollowUpDefinition(
        "P1",
        "Analyzed cases should carry an explicit primary-bottleneck label, even when the label is unknown.",
        "Inspect analyzer summary assembly before treating these cases as diagnostic gaps.",
    ),
    "profile_docs_registry_not_available": FollowUpDefinition(
        "P1",
        "The bundled registry is safe, but live profile counter labels would improve version calibration.",
        "Run or improve optional `/profile_docs` collection where the source supports it; otherwise extend bundled aliases.",
    ),
    "profile_docs_missing_allowlisted_labels": FollowUpDefinition(
        "P1",
        "Missing allowlisted labels keep interpreted counters at UNKNOWN stability.",
        "Refresh the versioned registry only for counter families already interpreted by the analyzer.",
    ),
    "metadata_context_not_collected": FollowUpDefinition(
        "P1",
        "Without bounded metadata, storage family and stats context often remain unknown.",
        "Run a metadata-enabled Recent smoke for top cases or improve safe metadata collection coverage.",
    ),
    "storage_context_unknown": FollowUpDefinition(
        "P1",
        "Storage semantics affect HDFS locality, object-store, and cache diagnostics.",
        "Use safe metadata location summaries where available; keep raw paths and URIs out of facts.",
    ),
    "resource_trace_absent": FollowUpDefinition(
        "P1",
        "Resource trace can add CPU/I/O/network context when the profile source contains it.",
        "Keep absence as unknown; add selected-query isolation before allowing stronger CPU/I/O diagnosis.",
    ),
    "runtime_metrics_not_available": FollowUpDefinition(
        "P1",
        "Runtime metrics can corroborate selected-query facts but should not create causes alone.",
        "Improve configured CM or Prometheus metric availability only as supporting context.",
    ),
    "cluster_events_not_available": FollowUpDefinition(
        "P2",
        "Cluster events can explain external service pressure around selected queries.",
        "Keep events bounded and context-only until a selected-query fact supports promotion.",
    ),
    "runtime_filter_context_observed": FollowUpDefinition(
        "P1",
        "Observed runtime-filter context is useful only after producer, consumer, timing, and target scans are mapped.",
        "Add fixtures for safe producer/consumer mapping before claiming missing or late filters.",
    ),
    "runtime_filter_arrival_gap_observed": FollowUpDefinition(
        "P1",
        "Arrival gaps are a strong research signal but not enough for root-cause wording.",
        "Corroborate with target scan, producer timing, spill context, and completed-node evidence.",
    ),
    "runtime_filter_producer_consumer_mapped": FollowUpDefinition(
        "P1",
        "Producer/consumer pairing is now available as safe aggregate context for future target-scan mapping.",
        "Keep it context-only until target scans, timing, spill context, and node completion are mapped.",
    ),
    "runtime_filter_unpaired_plan_context": FollowUpDefinition(
        "P1",
        "Unpaired producer or consumer context can indicate parser coverage gaps or real plan-side asymmetry.",
        "Add fixtures for the repeated shape before turning this into diagnostic wording.",
    ),
    "runtime_filter_target_scan_mapped": FollowUpDefinition(
        "P1",
        "Runtime-filter consumers are mapped to safe aggregate scan targets for future target-scan evidence.",
        "Keep target-scan context below finding status until timing, spill context, and node completion corroborate it.",
    ),
    "runtime_filter_target_scan_incomplete": FollowUpDefinition(
        "P1",
        "Some runtime-filter consumers could not be mapped to paired scan targets.",
        "Inspect repeated safe shapes and add parser fixtures before changing diagnostic wording.",
    ),
    "runtime_filter_routing_table_observed": FollowUpDefinition(
        "P1",
        "Runtime-filter routing/final tables add bounded aggregate routing, pending, and completion context.",
        "Keep routing-table context below finding status until target scans, timing, spill context, and node completion corroborate it.",
    ),
    "scan_skew_medium_supporting": FollowUpDefinition(
        "P1",
        "Medium scan-spread signals are useful, but not enough for primary runtime-skew routing.",
        "Look for stable bytes, memory, or network corroboration before strengthening the finding.",
    ),
    "data_movement_supporting_not_primary": FollowUpDefinition(
        "P1",
        "Data movement can be a supported follow-up without enough mapped exchange time for primary routing.",
        "Calibrate exchange elapsed-time/share thresholds on comparable reruns.",
    ),
    "data_movement_exchange_context_only": FollowUpDefinition(
        "P1",
        "Mapped exchange operators without enough byte/time support identify parser or threshold gaps.",
        "Inspect safe exchange evidence tiers before adding aliases or changing thresholds.",
    ),
    "memory_estimate_context_only": FollowUpDefinition(
        "P1",
        "Memory estimate gaps are present, but no selected-query spill/scratch evidence supports memory pressure.",
        "Collect bounded metadata/cardinality context or add parser fixtures for stable spill/scratch evidence before routing memory as primary.",
    ),
    "memory_pressure_supported": FollowUpDefinition(
        "P1",
        "Spill/scratch-backed memory facts are deterministic selected-query evidence.",
        "Use them to calibrate memory-pressure wording and metadata/query-shape follow-ups.",
    ),
}


@dataclass(frozen=True)
class CoverageAuditIssue:
    category: str
    message: str


@dataclass
class CoverageAuditResult:
    summary_paths: list[Path]
    total_cases: int = 0
    analyzed_cases: int = 0
    missing_analysis_count: int = 0
    analysis_error_count: int = 0
    primary_counts: Counter[str] = field(default_factory=Counter)
    primary_confidence_counts: Counter[str] = field(default_factory=Counter)
    primary_classification_source_counts: Counter[str] = field(default_factory=Counter)
    primary_classifier_drift_counts: Counter[str] = field(default_factory=Counter)
    medium_or_better_primary_count: int = 0
    strict_primary_coverage_case_count: int = 0
    strict_unknown_primary_count: int = 0
    strict_medium_or_better_primary_count: int = 0
    strict_primary_out_of_scope_counts: Counter[str] = field(default_factory=Counter)
    strict_unknown_primary_reason_counts: Counter[str] = field(default_factory=Counter)
    profile_dialect_counts: Counter[str] = field(default_factory=Counter)
    profile_policy_counts: Counter[str] = field(default_factory=Counter)
    profile_counter_registry_counts: Counter[str] = field(default_factory=Counter)
    profile_counter_missing_name_counts: Counter[str] = field(default_factory=Counter)
    profile_counter_observed_missing_name_counts: Counter[str] = field(default_factory=Counter)
    optional_source_counts: Counter[str] = field(default_factory=Counter)
    source_compatibility_counts: Counter[str] = field(default_factory=Counter)
    source_status_counts: Counter[str] = field(default_factory=Counter)
    direct_impala_case_count: int = 0
    direct_discovery_counts: Counter[str] = field(default_factory=Counter)
    direct_source_readiness_counts: Counter[str] = field(default_factory=Counter)
    direct_source_readiness_gap_counts: Counter[str] = field(default_factory=Counter)
    evidence_quality_counts: Counter[str] = field(default_factory=Counter)
    unknown_primary_reason_counts: Counter[str] = field(default_factory=Counter)
    unknown_primary_resolution_counts: Counter[str] = field(default_factory=Counter)
    storage_unknown_reason_counts: Counter[str] = field(default_factory=Counter)
    scan_skew_supporting_reason_counts: Counter[str] = field(default_factory=Counter)
    data_movement_supporting_reason_counts: Counter[str] = field(default_factory=Counter)
    data_movement_calibration_signal_counts: Counter[str] = field(default_factory=Counter)
    runtime_filter_calibration_signal_counts: Counter[str] = field(default_factory=Counter)
    gap_counts: Counter[str] = field(default_factory=Counter)
    opportunity_counts: Counter[str] = field(default_factory=Counter)
    issues: list[CoverageAuditIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues and not self.analysis_error_count


class CoverageAuditOutputError(RuntimeError):
    """Raised when a raw-free summary cannot be written."""


def counter_key(*parts: object) -> str:
    return "/".join(text_value(part) for part in parts)


def primary_label_value(value: object) -> str:
    if value is None or not str(value).strip():
        return "missing"
    token = normalized_token(value)
    return token if token in PRIMARY_BOTTLENECK_LABELS else "unknown"


def primary_confidence_value(value: object) -> str:
    return allowed_token(value, PRIMARY_BOTTLENECK_CONFIDENCES)


def primary_is_medium_or_better(label: str, confidence: str) -> bool:
    return (
        label not in NO_ACTIONABLE_PRIMARY_LABELS
        and confidence in MEDIUM_OR_BETTER_PRIMARY_CONFIDENCES
    )


def primary_out_of_scope_reason(
    case: dict[str, Any],
    primary: dict[str, Any],
    primary_label: str,
    analysis: dict[str, Any],
    *,
    prefer_primary_reasons: bool = False,
) -> str:
    if normalized_token(case.get("score_severity")) == "clean":
        return "clean_case"
    if primary_label != "unknown":
        return ""
    analysis_primary = analysis.get("case_primary_bottleneck")
    analysis_primary = analysis_primary if isinstance(analysis_primary, dict) else {}
    reason = reason_key(
        primary.get("reasons")
        if prefer_primary_reasons
        else analysis_primary.get("reasons") or primary.get("reasons")
    )
    parts = set(reason.split("+"))
    for safe_reason in STRICT_PRIMARY_OUT_OF_SCOPE_REASONS:
        if safe_reason in parts:
            return safe_reason
    return ""


def reason_key(value: object) -> str:
    if isinstance(value, str):
        return safe_reason_token(value)
    if isinstance(value, (list, tuple)):
        parts = [safe_reason_token(item) for item in value if str(item).strip()]
        safe_parts = [part for part in parts if part != "unsafe_reason"]
        if safe_parts:
            return "+".join(safe_parts)
        if "unsafe_reason" in parts:
            return "unsafe_reason"
        return "missing_reason"
    return "missing_reason"


def safe_reason_token(value: object) -> str:
    token = normalized_token(value)
    if token in SAFE_UNKNOWN_PRIMARY_REASONS:
        return token
    if token.startswith("tail_candidates_"):
        return "tail_candidates"
    return "unsafe_reason"


def unknown_primary_resolution_key(
    case: dict[str, Any],
    analysis: dict[str, Any],
    *,
    out_of_scope: str,
    reason_value: object,
) -> str:
    """Separate unknown primary cases into no-action boundaries or evidence gaps."""

    reason_parts = set(reason_key(reason_value).split("+"))
    if clean_short_no_action_case(case, analysis):
        return "clean_short_no_action_boundary"
    if "very_short_query_or_unknown_wall_clock" in reason_parts:
        if selected_query_duration_sec(case, analysis) is None:
            return "missing_wall_clock_collector_gap"
        return "short_query_primary_out_of_scope"
    if out_of_scope == "clean_case":
        return "clean_case_no_action_boundary"
    return "diagnostic_evidence_gap"


def clean_short_no_action_case(case: dict[str, Any], analysis: dict[str, Any]) -> bool:
    if normalized_token(case.get("score_severity")) != "clean":
        return False
    duration_sec = selected_query_duration_sec(case, analysis)
    if duration_sec is None or duration_sec >= 60:
        return False
    if case.get("query_optimization_candidate") or case.get("stats_optimization_candidate"):
        return False
    regression = normalized_token(case.get("workload_regression"))
    return regression in {"none", "unknown"}


def selected_query_duration_sec(case: dict[str, Any], analysis: dict[str, Any]) -> float | None:
    case_duration = numeric_counter_value(case.get("duration_sec"))
    if case_duration is not None:
        return case_duration
    query_wall_clock = analysis.get("query_wall_clock")
    query_wall_clock = query_wall_clock if isinstance(query_wall_clock, dict) else {}
    duration_ms = numeric_counter_value(query_wall_clock.get("duration_ms"))
    if duration_ms is None:
        return None
    return duration_ms / 1000.0


def percent(count: int, total: int) -> str:
    if total <= 0:
        return "0.0%"
    return f"{(count / total) * 100:.1f}%"


def percent_value(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return (count / total) * 100


def add_gap(result: CoverageAuditResult, key: str) -> None:
    result.gap_counts[key] += 1


def add_opportunity(result: CoverageAuditResult, key: str) -> None:
    result.opportunity_counts[key] += 1


def add_issue(result: CoverageAuditResult, category: str, message: str) -> None:
    result.issues.append(CoverageAuditIssue(category, message))


def audit_summaries(
    summary_paths: Iterable[Path],
    *,
    fail_on_diagnostic_coverage_gaps: bool = False,
    fail_on_direct_source_readiness_gaps: bool = False,
    use_current_classifier_primary: bool = False,
    max_unknown_primary_rate: float = 30.0,
    min_medium_primary_rate: float = 70.0,
) -> CoverageAuditResult:
    paths = [path.resolve(strict=True) for path in summary_paths]
    result = CoverageAuditResult(summary_paths=paths)
    for summary_path in paths:
        audit_summary_into(
            result,
            summary_path,
            use_current_classifier_primary=use_current_classifier_primary,
        )
    if fail_on_diagnostic_coverage_gaps:
        add_diagnostic_coverage_issues(
            result,
            max_unknown_primary_rate=max_unknown_primary_rate,
            min_medium_primary_rate=min_medium_primary_rate,
        )
    if fail_on_direct_source_readiness_gaps:
        add_direct_source_readiness_issues(result)
    return result


def audit_summary_into(
    result: CoverageAuditResult,
    summary_path: Path,
    *,
    use_current_classifier_primary: bool,
) -> None:
    summary = load_json_object(summary_path)
    cases = summary_cases(summary)
    summary_is_direct = normalized_token(summary.get("query_profile_source")) == "impala"
    summary_prometheus_requested = bool(summary.get("collect_prometheus_timeseries"))
    result.total_cases += len(cases)
    audit_direct_discovery_summary(result, summary, summary_is_direct=summary_is_direct)

    for case in cases:
        stored_primary = case.get("case_primary_bottleneck")
        stored_primary = stored_primary if isinstance(stored_primary, dict) else {}
        case_dir = resolve_case_dir(summary_path, case)
        analysis_path = analysis_path_for(case_dir) if case_dir is not None else None
        if analysis_path is None:
            primary, primary_source = selected_primary(
                stored_primary,
                None,
                use_current_classifier_primary=use_current_classifier_primary,
            )
            audit_primary_summary(
                result,
                case,
                primary,
                analysis={},
                primary_source=primary_source,
                out_of_scope="",
                include_strict=False,
            )
            result.missing_analysis_count += 1
            add_gap(result, "missing_analysis")
            continue
        try:
            analysis = load_json_object(analysis_path)
        except EvidenceGateAuditInputError:
            primary, primary_source = selected_primary(
                stored_primary,
                None,
                use_current_classifier_primary=use_current_classifier_primary,
            )
            audit_primary_summary(
                result,
                case,
                primary,
                analysis={},
                primary_source=primary_source,
                out_of_scope="",
                include_strict=False,
            )
            result.analysis_error_count += 1
            continue
        primary, primary_source = selected_primary(
            stored_primary,
            analysis,
            use_current_classifier_primary=use_current_classifier_primary,
        )
        audit_primary_classifier_drift(result, stored_primary, primary, primary_source)
        out_of_scope = primary_out_of_scope_reason(
            case,
            primary,
            primary_label_value(primary.get("label")),
            analysis,
            prefer_primary_reasons=primary_source == "current_classifier",
        )
        audit_primary_summary(
            result,
            case,
            primary,
            analysis=analysis,
            primary_source=primary_source,
            out_of_scope=out_of_scope,
        )
        audit_analysis(
            result,
            analysis,
            summary_is_direct=summary_is_direct,
            summary_prometheus_requested=summary_prometheus_requested,
        )


def selected_primary(
    stored_primary: dict[str, Any],
    analysis: dict[str, Any] | None,
    *,
    use_current_classifier_primary: bool,
) -> tuple[dict[str, Any], str]:
    if use_current_classifier_primary and analysis is not None:
        current_primary = classify_case_primary_bottleneck(analysis)
        return primary_dict_from_classifier(current_primary), "current_classifier"
    return stored_primary, "stored_summary"


def primary_dict_from_classifier(primary: CasePrimaryBottleneck) -> dict[str, Any]:
    return {
        "label": primary.label,
        "confidence": primary.confidence,
        "reasons": list(primary.reasons),
    }


def audit_primary_classifier_drift(
    result: CoverageAuditResult,
    stored_primary: dict[str, Any],
    selected: dict[str, Any],
    primary_source: str,
) -> None:
    if primary_source != "current_classifier":
        return
    stored_label = primary_label_value(stored_primary.get("label"))
    stored_confidence = primary_confidence_value(stored_primary.get("confidence"))
    selected_label = primary_label_value(selected.get("label"))
    selected_confidence = primary_confidence_value(selected.get("confidence"))
    if stored_label == selected_label and stored_confidence == selected_confidence:
        return
    result.primary_classifier_drift_counts[
        counter_key(stored_label, stored_confidence, selected_label, selected_confidence)
    ] += 1


def audit_primary_summary(
    result: CoverageAuditResult,
    case: dict[str, Any],
    primary: dict[str, Any],
    *,
    analysis: dict[str, Any],
    primary_source: str,
    out_of_scope: str,
    include_strict: bool = True,
) -> None:
    primary_label = primary_label_value(primary.get("label"))
    primary_confidence = primary_confidence_value(primary.get("confidence"))
    result.primary_counts[primary_label] += 1
    result.primary_confidence_counts[counter_key(primary_label, primary_confidence)] += 1
    result.primary_classification_source_counts[primary_source] += 1
    if primary_is_medium_or_better(primary_label, primary_confidence):
        result.medium_or_better_primary_count += 1
    if not include_strict:
        return
    analysis_primary = analysis.get("case_primary_bottleneck")
    analysis_primary = analysis_primary if isinstance(analysis_primary, dict) else {}
    reason_value = (
        primary.get("reasons")
        if primary_source == "current_classifier"
        else analysis_primary.get("reasons") or primary.get("reasons")
    )
    if primary_label == "unknown":
        if not out_of_scope:
            add_gap(result, "unknown_primary_bottleneck")
        result.unknown_primary_reason_counts[reason_key(reason_value)] += 1
        result.unknown_primary_resolution_counts[
            unknown_primary_resolution_key(
                case,
                analysis,
                out_of_scope=out_of_scope,
                reason_value=reason_value,
            )
        ] += 1
    elif primary_label == "missing":
        add_gap(result, "missing_primary_bottleneck_label")
    audit_strict_primary_coverage(
        result,
        case,
        primary,
        primary_label=primary_label,
        primary_confidence=primary_confidence,
        analysis=analysis,
        out_of_scope=out_of_scope,
        reason_value=reason_value,
    )


def audit_strict_primary_coverage(
    result: CoverageAuditResult,
    case: dict[str, Any],
    primary: dict[str, Any],
    *,
    primary_label: str,
    primary_confidence: str,
    analysis: dict[str, Any],
    out_of_scope: str,
    reason_value: object,
) -> None:
    del case, primary, analysis
    if out_of_scope:
        result.strict_primary_out_of_scope_counts[out_of_scope] += 1
        return
    result.strict_primary_coverage_case_count += 1
    if primary_label == "unknown":
        result.strict_unknown_primary_count += 1
        result.strict_unknown_primary_reason_counts[reason_key(reason_value)] += 1
    if primary_is_medium_or_better(primary_label, primary_confidence):
        result.strict_medium_or_better_primary_count += 1


def add_diagnostic_coverage_issues(
    result: CoverageAuditResult,
    *,
    max_unknown_primary_rate: float,
    min_medium_primary_rate: float,
) -> None:
    if result.total_cases <= 0:
        add_issue(
            result,
            "empty_batch",
            "strict diagnostic coverage requires at least one selected case",
        )
        return

    if result.missing_analysis_count:
        add_issue(
            result,
            "missing_analysis",
            f"strict diagnostic coverage requires analyzer output for all selected cases "
            f"({result.missing_analysis_count} missing)",
        )
    if result.analysis_error_count:
        add_issue(
            result,
            "analysis_unreadable",
            f"strict diagnostic coverage requires readable analyzer output "
            f"({result.analysis_error_count} unreadable)",
        )

    missing_label_count = result.primary_counts.get("missing", 0)
    if missing_label_count:
        add_issue(
            result,
            "missing_primary_bottleneck_label",
            f"strict diagnostic coverage requires explicit primary labels "
            f"({missing_label_count} missing)",
        )

    strict_count = result.strict_primary_coverage_case_count
    if strict_count <= 0:
        return

    unknown_count = result.strict_unknown_primary_count
    unknown_rate = percent_value(unknown_count, strict_count)
    if unknown_rate > max_unknown_primary_rate:
        add_issue(
            result,
            "unknown_primary_rate",
            f"primary bottleneck unknown rate {unknown_rate:.1f}% exceeds "
            f"{max_unknown_primary_rate:.1f}% ({unknown_count}/{strict_count} strict cases)",
        )

    medium_rate = percent_value(result.strict_medium_or_better_primary_count, strict_count)
    if medium_rate < min_medium_primary_rate:
        add_issue(
            result,
            "medium_primary_rate",
            f"medium-or-better deterministic primary coverage {medium_rate:.1f}% is below "
            f"{min_medium_primary_rate:.1f}% "
            f"({result.strict_medium_or_better_primary_count}/{strict_count} strict cases)",
        )


def add_direct_source_readiness_issues(result: CoverageAuditResult) -> None:
    if result.direct_impala_case_count <= 0:
        add_issue(
            result,
            "direct_source_no_cases",
            "strict direct source readiness requires at least one direct Impala analyzed case",
        )
        return

    for category, count in result.direct_source_readiness_gap_counts.most_common():
        add_issue(
            result,
            category,
            f"strict direct source readiness observed {category} in {count} direct case(s)",
        )


def audit_analysis(
    result: CoverageAuditResult,
    analysis: dict[str, Any],
    *,
    summary_is_direct: bool,
    summary_prometheus_requested: bool,
) -> None:
    result.analyzed_cases += 1

    profile = analysis.get("profile_format")
    profile = profile if isinstance(profile, dict) else {}
    profile_dialect = text_value(profile.get("profile_dialect"))
    profile_policy = primary_bottleneck_profile_policy(analysis)
    result.profile_dialect_counts[profile_dialect] += 1
    result.profile_policy_counts[profile_policy] += 1
    if profile_policy != "supported":
        add_gap(result, "profile_policy_not_supported")

    registry = analysis.get("profile_counter_registry")
    registry = registry if isinstance(registry, dict) else {}
    registry_status = allowed_token(registry.get("status"), {"available", "not_observed"})
    registry_source = allowed_token(registry.get("source"), {"bundled", "profile_docs"})
    result.profile_counter_registry_counts[counter_key(registry_status, registry_source)] += 1
    missing_counter_names = safe_profile_counter_names(registry.get("missing_counter_names"))
    result.profile_counter_missing_name_counts.update(missing_counter_names)
    observed_missing_counter_names = tuple(
        name for name in missing_counter_names if name in observed_profile_counter_names(analysis)
    )
    result.profile_counter_observed_missing_name_counts.update(observed_missing_counter_names)
    if not (registry_status == "available" and registry_source == "profile_docs"):
        add_gap(result, "profile_docs_registry_not_available")
    if (
        registry_status == "available"
        and registry_source == "profile_docs"
        and int_value(registry.get("missing_counter_count")) > 0
        and (observed_missing_counter_names or not missing_counter_names)
    ):
        add_gap(result, "profile_docs_missing_allowlisted_labels")

    audit_source_compatibility(result, analysis, profile=profile, registry=registry)
    audit_optional_source_availability(result, analysis, profile=profile, registry=registry)
    if summary_is_direct or profile_is_direct_impala(profile):
        audit_direct_source_readiness(
            result,
            analysis,
            profile=profile,
            registry=registry,
            prometheus_requested=summary_prometheus_requested
            or analysis_prometheus_requested(analysis),
        )

    evidence_quality = analysis.get("evidence_quality")
    evidence_quality = evidence_quality if isinstance(evidence_quality, dict) else {}
    result.evidence_quality_counts[text_value(evidence_quality.get("level"))] += 1

    audit_source_provenance(result, analysis)
    audit_storage_context(result, analysis)
    audit_resource_trace(result, analysis)
    audit_runtime_filter_opportunities(result, analysis)
    audit_scan_skew_opportunities(result, analysis)
    audit_data_movement_opportunities(result, analysis)
    audit_memory_pressure_opportunities(result, analysis)


def audit_direct_discovery_summary(
    result: CoverageAuditResult,
    summary: dict[str, Any],
    *,
    summary_is_direct: bool,
) -> None:
    if not summary_is_direct:
        return
    result.direct_discovery_counts["summary"] += 1
    result.direct_discovery_counts[
        "discovery_failed" if bool(summary.get("discovery_failed")) else "discovery_ok"
    ] += 1
    result.direct_discovery_counts[
        counter_key("summaries_inspected", safe_count_bucket(summary.get("summaries_inspected")))
    ] += 1
    result.direct_discovery_counts[
        counter_key("selected", safe_count_bucket(summary.get("selected_count")))
    ] += 1
    for category in direct_discovery_warning_categories(summary.get("warnings")):
        result.direct_discovery_counts[counter_key("warning", category)] += 1


def direct_discovery_warning_categories(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        return ("none",)
    categories: set[str] = set()
    for item in value:
        text = str(item or "").strip().lower()
        if not text:
            continue
        if "readable query list" in text:
            categories.add("query_list_unreadable")
        elif "timeout" in text or "timed out" in text:
            categories.add("timeout")
        elif "kerberos" in text or "auth" in text:
            categories.add("auth_failed")
        elif "connect" in text:
            categories.add("connection_failed")
        else:
            categories.add("other")
    return tuple(sorted(categories)) or ("none",)


def profile_is_direct_impala(profile: dict[str, Any]) -> bool:
    return (
        text_value(profile.get("profile_source")) == "impala_daemon"
        or text_value(profile.get("source_label")) == "Impala daemon profile endpoint"
    )


def audit_source_compatibility(
    result: CoverageAuditResult,
    analysis: dict[str, Any],
    *,
    profile: dict[str, Any],
    registry: dict[str, Any],
) -> None:
    capabilities = profile.get("source_capabilities")
    capabilities = capabilities if isinstance(capabilities, dict) else {}
    query_context = analysis.get("query_context")
    query_context = query_context if isinstance(query_context, dict) else {}
    admission_context = analysis.get("admission_context")
    admission_context = admission_context if isinstance(admission_context, dict) else {}
    resource_trace = analysis.get("resource_trace")
    resource_trace = resource_trace if isinstance(resource_trace, dict) else {}

    result.source_compatibility_counts[
        counter_key(
            "impala_distribution",
            allowed_token(
                profile.get("impala_distribution"),
                {"apache_impala", "cloudera_impala", "unknown"},
            ),
        )
    ] += 1
    result.source_compatibility_counts[
        counter_key("impala_major_version", safe_major_version(profile.get("impala_major_version")))
    ] += 1
    result.source_compatibility_counts[
        counter_key(
            "impala_build_type",
            allowed_token(profile.get("impala_build_type"), {"release", "snapshot", "debug"}),
        )
    ] += 1
    result.source_compatibility_counts[
        counter_key(
            "profile_response_format",
            allowed_token(profile.get("profile_response_format"), {"json", "text", "default"}),
        )
    ] += 1
    for key in ("json_profile_probe", "profile_docs_probe"):
        result.source_compatibility_counts[
            counter_key(key, allowed_token(capabilities.get(key), {"enabled", "not_configured"}))
        ] += 1
    for key in ("json_profile_payload", "text_profile_payload"):
        result.source_compatibility_counts[
            counter_key(
                key,
                allowed_token(
                    capabilities.get(key),
                    {
                        "observed",
                        "mapped_limited",
                        "wrapped_text_observed",
                        "not_selected",
                        "selected_but_unmapped",
                    },
                ),
            )
        ] += 1
    result.source_compatibility_counts[
        counter_key(
            "primary_profile_routing",
            allowed_token(
                capabilities.get("primary_profile_routing"),
                {"supported", "non_profile_only", "unsupported"},
            ),
        )
    ] += 1
    result.source_compatibility_counts[
        counter_key(
            "profile_fetch_attempts",
            safe_count_bucket(capabilities.get("profile_fetch_attempt_count")),
        )
    ] += 1
    result.source_compatibility_counts[
        counter_key(
            "profile_docs_fetch_attempts",
            safe_count_bucket(capabilities.get("profile_docs_fetch_attempt_count")),
        )
    ] += 1
    result.source_compatibility_counts[
        counter_key(
            "profile_counter_registry",
            allowed_token(registry.get("status"), {"available", "not_observed", "unknown"}),
            allowed_token(registry.get("source"), {"bundled", "profile_docs", "unknown"}),
        )
    ] += 1
    result.source_compatibility_counts[
        counter_key(
            "admission_context_probe",
            enabled_or_unknown(query_context.get("admission_context_probe_enabled")),
        )
    ] += 1
    result.source_compatibility_counts[
        counter_key(
            "admission_context_fetch_attempts",
            safe_count_bucket(query_context.get("admission_context_fetch_attempt_count")),
        )
    ] += 1
    result.source_compatibility_counts[
        counter_key("admission_context", admission_context_status(admission_context))
    ] += 1
    result.source_compatibility_counts[
        counter_key(
            "resource_trace",
            allowed_token(
                resource_trace.get("status"),
                {"available", "unknown", "not_observed", "unavailable"},
            ),
        )
    ] += 1


def normalized_token(value: object) -> str:
    text = str(value or "unknown").strip().lower()
    text = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in text)
    text = "_".join(part for part in text.split("_") if part)
    return text[:60] if text else "unknown"


def allowed_token(value: object, allowed: set[str]) -> str:
    text = normalized_token(value)
    return text if text in allowed else "unknown"


def safe_major_version(value: object) -> str:
    parsed = int_value(value)
    return f"major_{parsed}" if parsed > 0 else "unknown"


def safe_count_bucket(value: object) -> str:
    count = int_value(value)
    if count <= 0:
        return "none"
    if count == 1:
        return "1"
    if count <= 4:
        return "2_4"
    return "5_plus"


def enabled_or_unknown(value: object) -> str:
    if isinstance(value, bool):
        return "enabled" if value else "not_configured"
    return "unknown"


def admission_context_status(context: dict[str, Any]) -> str:
    if not context:
        return "not_collected"
    status = allowed_token(context.get("status"), {"available", "unavailable"})
    if status in {"available", "unavailable"}:
        return status
    return "unknown"


def audit_optional_source_availability(
    result: CoverageAuditResult,
    analysis: dict[str, Any],
    *,
    profile: dict[str, Any],
    registry: dict[str, Any],
) -> None:
    capabilities = profile.get("source_capabilities")
    capabilities = capabilities if isinstance(capabilities, dict) else {}
    query_context = analysis.get("query_context")
    query_context = query_context if isinstance(query_context, dict) else {}
    admission_context = analysis.get("admission_context")
    admission_context = admission_context if isinstance(admission_context, dict) else {}
    resource_trace = analysis.get("resource_trace")
    resource_trace = resource_trace if isinstance(resource_trace, dict) else {}

    result.optional_source_counts[
        counter_key("json_profile", optional_json_profile_state(capabilities))
    ] += 1
    result.optional_source_counts[
        counter_key("profile_docs", optional_profile_docs_state(capabilities, registry))
    ] += 1
    result.optional_source_counts[
        counter_key(
            "admission_context",
            optional_admission_context_state(query_context, admission_context),
        )
    ] += 1
    result.optional_source_counts[
        counter_key(
            "metadata",
            optional_metadata_source_state(
                source_provenance_status(analysis, "metadata"),
                analysis=analysis,
            ),
        )
    ] += 1
    result.optional_source_counts[
        counter_key(
            "runtime_metrics",
            optional_source_state_from_source_status(source_provenance_status(analysis, "metrics")),
        )
    ] += 1
    result.optional_source_counts[
        counter_key(
            "cluster_events",
            optional_source_state_from_source_status(source_provenance_status(analysis, "events")),
        )
    ] += 1
    result.optional_source_counts[
        counter_key("resource_trace", optional_resource_trace_state(resource_trace))
    ] += 1


def optional_json_profile_state(capabilities: dict[str, Any]) -> str:
    probe = allowed_token(capabilities.get("json_profile_probe"), {"enabled", "not_configured"})
    payload = allowed_token(
        capabilities.get("json_profile_payload"),
        {
            "observed",
            "mapped_limited",
            "wrapped_text_observed",
            "not_selected",
            "selected_but_unmapped",
        },
    )
    if probe == "not_configured":
        return "not_configured"
    if probe == "enabled" and payload in {"observed", "mapped_limited", "wrapped_text_observed"}:
        return "available"
    if probe == "enabled" and payload == "selected_but_unmapped":
        return "unavailable"
    return "unknown"


def optional_profile_docs_state(
    capabilities: dict[str, Any],
    registry: dict[str, Any],
) -> str:
    probe = allowed_token(capabilities.get("profile_docs_probe"), {"enabled", "not_configured"})
    registry_status = allowed_token(registry.get("status"), {"available", "not_observed"})
    registry_source = allowed_token(registry.get("source"), {"bundled", "profile_docs"})
    attempts = int_value(capabilities.get("profile_docs_fetch_attempt_count"))
    if registry_status == "available" and registry_source == "profile_docs":
        return "available"
    if probe == "not_configured":
        return "not_configured"
    if probe == "enabled" and attempts > 0:
        return "unavailable"
    return "unknown"


def optional_admission_context_state(
    query_context: dict[str, Any],
    admission_context: dict[str, Any],
) -> str:
    probe = enabled_or_unknown(query_context.get("admission_context_probe_enabled"))
    status = admission_context_status(admission_context)
    if status in {"available", "unavailable"}:
        return status
    if probe == "not_configured":
        return "not_configured"
    return "unknown"


def optional_resource_trace_state(resource_trace: dict[str, Any]) -> str:
    status = allowed_token(
        resource_trace.get("status"),
        {"available", "unknown", "not_observed", "unavailable"},
    )
    if status == "available":
        return "available"
    if status == "unavailable":
        return "unavailable"
    if status == "not_observed":
        return "not_collected"
    return "unknown"


def source_provenance_status(analysis: dict[str, Any], kind: str) -> str:
    provenance = analysis.get("source_provenance")
    items = provenance.get("items") if isinstance(provenance, dict) else None
    if not isinstance(items, list):
        return "unknown"
    for item in items:
        if not isinstance(item, dict):
            continue
        if safe_source_provenance_kind(item.get("kind")) == kind:
            return safe_source_provenance_status(item.get("status"))
    return "unknown"


def safe_source_provenance_kind(value: object) -> str:
    return allowed_token(value, SOURCE_PROVENANCE_KINDS)


def safe_source_provenance_status(value: object) -> str:
    return allowed_token(value, SOURCE_PROVENANCE_STATUSES)


def optional_source_state_from_source_status(status: str) -> str:
    normalized = allowed_token(
        status,
        {
            "available",
            "ok",
            "none",
            "not_collected",
            "not_requested",
            "unavailable",
            "failed",
            "unknown",
        },
    )
    if normalized in {"available", "ok"}:
        return "available"
    if normalized in {"none", "not_collected", "not_requested"}:
        return "not_collected"
    if normalized in {"unavailable", "failed"}:
        return "unavailable"
    return "unknown"


def optional_metadata_source_state(status: str, *, analysis: dict[str, Any]) -> str:
    if source_status_is_unavailable(status) and metadata_not_applicable(analysis):
        return "not_applicable"
    return optional_source_state_from_source_status(status)


def audit_direct_source_readiness(
    result: CoverageAuditResult,
    analysis: dict[str, Any],
    *,
    profile: dict[str, Any],
    registry: dict[str, Any],
    prometheus_requested: bool,
) -> None:
    result.direct_impala_case_count += 1
    capabilities = profile.get("source_capabilities")
    capabilities = capabilities if isinstance(capabilities, dict) else {}
    query_context = analysis.get("query_context")
    query_context = query_context if isinstance(query_context, dict) else {}
    admission_context = analysis.get("admission_context")
    admission_context = admission_context if isinstance(admission_context, dict) else {}
    audit_direct_source_provenance_raw_free(result, analysis)

    profile_source = "impala_daemon" if profile_is_direct_impala(profile) else "unknown"
    record_direct_readiness(
        result, "profile_source", profile_source, ready=profile_source != "unknown"
    )

    profile_format = allowed_token(
        profile.get("profile_response_format"), {"json", "text", "default"}
    )
    record_direct_readiness(
        result,
        "profile_response_format",
        profile_format,
        ready=profile_format != "unknown",
    )

    profile_attempts = safe_count_bucket(capabilities.get("profile_fetch_attempt_count"))
    record_direct_readiness(
        result,
        "profile_fetch_attempts",
        profile_attempts,
        ready=profile_attempts != "none",
    )

    for key in ("json_profile_probe", "profile_docs_probe"):
        probe_state = allowed_token(capabilities.get(key), {"enabled", "not_configured"})
        record_direct_readiness(result, key, probe_state, ready=probe_state != "unknown")

    admission_probe = enabled_or_unknown(query_context.get("admission_context_probe_enabled"))
    record_direct_readiness(
        result,
        "admission_context_probe",
        admission_probe,
        ready=admission_probe != "unknown",
    )

    optional_states = {
        "json_profile": optional_json_profile_state(capabilities),
        "profile_docs": optional_profile_docs_state(capabilities, registry),
        "admission_context": optional_admission_context_state(query_context, admission_context),
        "metadata": direct_optional_metadata_source_state(
            source_provenance_status(analysis, "metadata"),
            analysis=analysis,
        ),
        "runtime_metrics": direct_optional_source_state_from_source_status(
            source_provenance_status(analysis, "metrics")
        ),
        "cluster_events": direct_optional_source_state_from_source_status(
            source_provenance_status(analysis, "events")
        ),
    }
    for source in DIRECT_REQUIRED_OPTIONAL_SOURCES:
        state = optional_states[source]
        record_direct_readiness(
            result,
            source,
            state,
            ready=state in DIRECT_READY_OPTIONAL_STATES,
        )

    if prometheus_requested and optional_states["runtime_metrics"] == "not_collected":
        add_direct_readiness_gap(result, "direct_runtime_metrics_configured_but_not_collected")

    for kind in DIRECT_REQUIRED_PROVENANCE_KINDS:
        status = direct_provenance_status_state(source_provenance_status(analysis, kind))
        record_direct_readiness(
            result,
            f"provenance_{kind}",
            status,
            ready=status in DIRECT_READY_PROVENANCE_STATUSES,
        )


def audit_direct_source_provenance_raw_free(
    result: CoverageAuditResult,
    analysis: dict[str, Any],
) -> None:
    provenance = analysis.get("source_provenance")
    if not isinstance(provenance, dict):
        return
    text = json.dumps(provenance, ensure_ascii=True, sort_keys=True)
    if direct_source_provenance_raw_free_violations(text):
        add_direct_readiness_gap(result, "direct_source_provenance_raw_like")


def direct_source_provenance_raw_free_violations(text: str) -> tuple[str, ...]:
    violations: list[str] = []
    if contains_raw_sql_like_text(text):
        violations.append("sql")
    if URL_RE.search(text):
        violations.append("url")
    if LOCAL_PATH_RE.search(text):
        violations.append("local_path")
    if redaction.EMAIL_RE.search(text):
        violations.append("email")
    if redaction.IPV4_RE.search(text):
        violations.append("ipv4")
    if redaction.HOSTLIKE_FQDN_RE.search(text):
        violations.append("hostname")
    if redaction.SECRET_VALUE_RE.search(text):
        violations.append("secret")
    return tuple(sorted(set(violations)))


def direct_optional_source_state_from_source_status(status: str) -> str:
    normalized = allowed_token(
        status,
        {
            "available",
            "ok",
            "partial",
            "none",
            "not_collected",
            "not_requested",
            "unavailable",
            "failed",
            "unknown",
        },
    )
    if normalized in {"available", "ok"}:
        return "available"
    if normalized == "partial":
        return "partial"
    if normalized in {"none", "not_collected", "not_requested"}:
        return "not_collected"
    if normalized in {"unavailable", "failed"}:
        return "unavailable"
    return "unknown"


def direct_optional_metadata_source_state(status: str, *, analysis: dict[str, Any]) -> str:
    if source_status_is_unavailable(status) and metadata_not_applicable(analysis):
        return "not_applicable"
    return direct_optional_source_state_from_source_status(status)


def direct_provenance_status_state(status: str) -> str:
    normalized = allowed_token(status, SOURCE_PROVENANCE_STATUSES)
    if normalized == "ok":
        return "available"
    if normalized in {"failed"}:
        return "unavailable"
    if normalized in {"not_collected", "not_requested"}:
        return "none"
    return normalized


def analysis_prometheus_requested(analysis: dict[str, Any]) -> bool:
    context = runtime_metrics_context(analysis) or {}
    source = text_value(context.get("source"), "")
    source_label = text_value(context.get("source_label"), "")
    return source == "prometheus" or source_label == "Prometheus runtime metrics"


def record_direct_readiness(
    result: CoverageAuditResult,
    dimension: str,
    state: str,
    *,
    ready: bool,
) -> None:
    safe_state = normalized_token(state)
    result.direct_source_readiness_counts[counter_key(dimension, safe_state)] += 1
    if not ready:
        add_direct_readiness_gap(result, f"direct_{dimension}_unknown")


def add_direct_readiness_gap(result: CoverageAuditResult, category: str) -> None:
    result.direct_source_readiness_gap_counts[category] += 1


def audit_source_provenance(result: CoverageAuditResult, analysis: dict[str, Any]) -> None:
    provenance = analysis.get("source_provenance")
    items = provenance.get("items") if isinstance(provenance, dict) else None
    if not isinstance(items, list):
        result.source_status_counts["source_provenance/unknown"] += 1
        return

    for item in items:
        if not isinstance(item, dict):
            continue
        kind = safe_source_provenance_kind(item.get("kind"))
        status = safe_source_provenance_status(item.get("status"))
        result.source_status_counts[counter_key(kind, status)] += 1
        if (
            kind == "metadata"
            and source_status_is_unavailable(status)
            and not metadata_not_applicable(analysis)
        ):
            add_gap(result, "metadata_context_not_collected")
        elif kind == "metrics" and source_status_is_unavailable(status):
            add_gap(result, "runtime_metrics_not_available")
        elif kind == "events" and source_status_is_unavailable(status):
            add_gap(result, "cluster_events_not_available")


def source_status_is_unavailable(status: str) -> bool:
    return status in {"failed", "none", "not_collected", "not_requested", "unavailable", "unknown"}


def metadata_not_applicable(analysis: dict[str, Any]) -> bool:
    referenced_tables = analysis.get("referenced_tables")
    return isinstance(referenced_tables, list) and not referenced_tables


def audit_storage_context(result: CoverageAuditResult, analysis: dict[str, Any]) -> None:
    context = analysis.get("storage_context")
    context = context if isinstance(context, dict) else {}
    if text_value(context.get("storage_family")) == "unknown":
        add_gap(result, "storage_context_unknown")
        result.storage_unknown_reason_counts[storage_unknown_reason(context)] += 1


def storage_unknown_reason(context: dict[str, Any]) -> str:
    source = text_value(context.get("source"))
    if source in {
        "table_metadata_view_only",
        "table_metadata_no_location",
        "unknown",
    }:
        return source
    if int_value(context.get("metadata_table_count")) <= 0:
        return "metadata_not_available"
    if int_value(context.get("location_scheme_count")) <= 0:
        return "table_metadata_no_location"
    return source or "unknown"


def audit_resource_trace(result: CoverageAuditResult, analysis: dict[str, Any]) -> None:
    facts = analysis.get("resource_trace")
    facts = facts if isinstance(facts, dict) else {}
    if (
        text_value(facts.get("status")) != "available"
        or int_value(facts.get("observed_metric_count")) <= 0
    ):
        add_gap(result, "resource_trace_absent")


def audit_runtime_filter_opportunities(
    result: CoverageAuditResult, analysis: dict[str, Any]
) -> None:
    facts = analysis.get("runtime_filters")
    facts = facts if isinstance(facts, dict) else {}
    observed = any(
        int_value(facts.get(field)) > 0
        for field in (
            "runtime_filter_lines",
            "runtime_filter_id_count",
            "bloom_filter_counter_lines",
            "bloom_filter_counter_nonzero_lines",
        )
    )
    if observed:
        add_opportunity(result, "runtime_filter_context_observed")
    if int_value(facts.get("missing_arrival_lines")) > 0:
        add_opportunity(result, "runtime_filter_arrival_gap_observed")
    mapping_status = text_value(facts.get("producer_consumer_mapping_status"))
    if mapping_status in {"mapped", "partial"}:
        add_opportunity(result, "runtime_filter_producer_consumer_mapped")
    if mapping_status in {"partial", "unpaired"}:
        add_opportunity(result, "runtime_filter_unpaired_plan_context")
    target_scan_status = text_value(facts.get("target_scan_mapping_status"))
    if target_scan_status in {"mapped", "partial"}:
        add_opportunity(result, "runtime_filter_target_scan_mapped")
    if target_scan_status in {"partial", "unpaired", "missing_target_scan"}:
        add_opportunity(result, "runtime_filter_target_scan_incomplete")
    if text_value(facts.get("routing_table_status")) == "observed":
        add_opportunity(result, "runtime_filter_routing_table_observed")
    result.runtime_filter_calibration_signal_counts.update(
        runtime_filter_calibration_signals(facts, observed=observed)
    )


def runtime_filter_calibration_signals(facts: dict[str, Any], *, observed: bool) -> tuple[str, ...]:
    signals: list[str] = []
    if observed:
        signals.append("context_observed")
    else:
        signals.append("context_not_observed")

    evidence_tier = text_value(facts.get("evidence_tier"))
    if evidence_tier == "context_only":
        signals.append("evidence_context_only")
    elif evidence_tier == "unsupported":
        signals.append("evidence_unsupported")

    profile_dialect = text_value(facts.get("profile_dialect"))
    if profile_dialect == "classic_text_profile":
        signals.append("classic_text_profile")
    elif profile_dialect not in {"", "unknown"}:
        signals.append("unsupported_profile_dialect")

    mapping_status = text_value(facts.get("producer_consumer_mapping_status"))
    if mapping_status == "mapped":
        signals.append("producer_consumer_mapped")
    elif mapping_status == "partial":
        signals.append("producer_consumer_partial")
    elif mapping_status == "unpaired":
        signals.append("producer_consumer_unpaired")
    elif mapping_status == "not_observed" and observed:
        signals.append("producer_consumer_not_observed")

    target_scan_status = text_value(facts.get("target_scan_mapping_status"))
    if target_scan_status == "mapped":
        signals.append("target_scan_mapped")
    elif target_scan_status == "partial":
        signals.append("target_scan_partial")
    elif target_scan_status in {"unpaired", "missing_target_scan"}:
        signals.append("target_scan_incomplete")
    elif target_scan_status == "not_observed" and observed:
        signals.append("target_scan_not_observed")

    if int_value(facts.get("target_scan_consumer_lines")) > 0:
        signals.append("target_scan_consumer_observed")
    if int_value(facts.get("non_scan_consumer_lines")) > 0:
        signals.append("non_scan_consumer_observed")
    if int_value(facts.get("unknown_target_consumer_lines")) > 0:
        signals.append("unknown_target_consumer_observed")

    if text_value(facts.get("routing_table_status")) == "observed":
        signals.append("routing_table_observed")
    if int_value(facts.get("routing_filter_count")) > 0:
        signals.append("routing_rows_observed")
    if int_value(facts.get("final_filter_count")) > 0:
        signals.append("final_rows_observed")
    if int_value(facts.get("enabled_filter_count")) > 0:
        signals.append("enabled_filters_observed")
    if int_value(facts.get("partition_filter_count")) > 0:
        signals.append("partition_filters_observed")
    if int_value(facts.get("pending_nonzero_count")) > 0:
        signals.append("pending_filters_observed")
    if int_value(facts.get("arrival_observed_count")) > 0:
        signals.append("routing_arrival_observed")
    if int_value(facts.get("completed_observed_count")) > 0:
        signals.append("routing_completion_observed")

    arrival_status_value = text_value(facts.get("arrival_status"))
    if arrival_status_value == "missing_observed":
        signals.append("arrival_gap_observed")
    elif arrival_status_value == "all_arrived_observed":
        signals.append("all_arrived_observed")
    elif arrival_status_value == "mixed":
        signals.extend(("arrival_gap_observed", "all_arrived_observed", "arrival_mixed"))
    elif arrival_status_value == "not_reported" and observed:
        signals.append("arrival_status_not_reported")

    if int_value(facts.get("bloom_filter_counter_lines")) > 0:
        signals.append("bloom_counter_observed")
    if int_value(facts.get("bloom_filter_counter_nonzero_lines")) > 0:
        signals.append("bloom_counter_nonzero")

    runtime_filter_effectiveness = text_value(facts.get("exec_node_runtime_filter_effectiveness"))
    if runtime_filter_effectiveness == "supported":
        signals.append("exec_node_effectiveness_supported")
    elif runtime_filter_effectiveness == "limited":
        signals.append("exec_node_effectiveness_limited")
    elif runtime_filter_effectiveness == "unknown":
        signals.append("exec_node_effectiveness_unknown")

    return tuple(signals) or ("runtime_filter_calibration_unspecified",)


def audit_scan_skew_opportunities(result: CoverageAuditResult, analysis: dict[str, Any]) -> None:
    facts = scan_skew_facts_from_analysis(analysis)
    if facts.finding_supported and facts.evidence_tier == "medium" and not facts.primary_supported:
        add_opportunity(result, "scan_skew_medium_supporting")
        result.scan_skew_supporting_reason_counts.update(scan_skew_supporting_reasons(facts))


def scan_skew_supporting_reasons(facts: Any) -> tuple[str, ...]:
    reasons: list[str] = []
    runtime_status = text_value(getattr(facts, "runtime_status", ""))
    if runtime_status == "timing_unknown":
        reasons.append("timing_unknown")
    elif runtime_status == "short_running":
        reasons.append("phase_short_running")
    elif runtime_status == "long_running_balanced":
        reasons.append("phase_long_running_balanced")
    elif runtime_status == "long_running_imbalanced":
        if text_value(getattr(facts, "skew_metric", "")) == "rows_produced":
            reasons.append("row_spread_without_scan_bytes")
        if int_value(getattr(facts, "corroborating_metric_count", 0)) < 2:
            reasons.append("long_running_imbalanced_single_metric")
    else:
        reasons.append("runtime_status_unknown")

    if text_value(getattr(facts, "evidence_source", "")) == "mapped_backend_group_summary":
        reasons.append("mapped_group_summary")
    return tuple(reasons) or ("medium_supporting_unspecified",)


def audit_data_movement_opportunities(
    result: CoverageAuditResult, analysis: dict[str, Any]
) -> None:
    facts = data_movement_facts_from_analysis(analysis)
    result.data_movement_calibration_signal_counts.update(
        data_movement_calibration_signals(facts, analysis)
    )
    if facts.finding_supported and not facts.primary_supported:
        add_opportunity(result, "data_movement_supporting_not_primary")
        result.data_movement_supporting_reason_counts.update(
            data_movement_supporting_reasons(facts, analysis)
        )
    if (
        facts.status == "context_only"
        and facts.evidence_tier == "context_only"
        and facts.exchange_operator_count > 0
    ):
        add_opportunity(result, "data_movement_exchange_context_only")
        result.data_movement_supporting_reason_counts.update(
            data_movement_supporting_reasons(facts, analysis)
        )


def data_movement_supporting_reasons(facts: Any, analysis: dict[str, Any]) -> tuple[str, ...]:
    reasons: list[str] = []
    total_bytes = numeric_counter_value(getattr(facts, "total_bytes_sent", None))
    threshold = medium_data_movement_threshold(analysis)
    exchange_ms = numeric_counter_value(getattr(facts, "exchange_elapsed_ms", None))
    exchange_share = numeric_counter_value(getattr(facts, "exchange_elapsed_share", None))

    if bool_value(getattr(facts, "finding_supported", False)):
        reasons.append("finding_supported_not_primary")
    elif text_value(getattr(facts, "status", "")) == "context_only":
        reasons.append("exchange_context_without_supported_finding")

    if total_bytes is None:
        reasons.append("bytes_missing_or_zero")
    elif total_bytes < threshold:
        reasons.append("bytes_below_finding_threshold")
    elif not bool_value(getattr(facts, "finding_supported", False)):
        reasons.append("bytes_without_supported_finding")

    if exchange_ms is None:
        reasons.append("exchange_timing_unavailable")
    elif exchange_ms < DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_MS:
        reasons.append("exchange_elapsed_below_primary_threshold")

    if exchange_share is None:
        reasons.append("exchange_share_unknown")
    elif exchange_share < DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_SHARE:
        reasons.append("exchange_share_below_primary_threshold")

    return tuple(reasons) or ("data_movement_supporting_unspecified",)


def data_movement_calibration_signals(facts: Any, analysis: dict[str, Any]) -> tuple[str, ...]:
    signals: list[str] = []
    status = text_value(getattr(facts, "status", ""))
    evidence_tier = text_value(getattr(facts, "evidence_tier", ""))
    total_bytes = numeric_counter_value(getattr(facts, "total_bytes_sent", None))
    threshold = medium_data_movement_threshold(analysis)
    exchange_count = int_value(getattr(facts, "exchange_operator_count", 0))
    exchange_ms = numeric_counter_value(getattr(facts, "exchange_elapsed_ms", None))
    exchange_share = numeric_counter_value(getattr(facts, "exchange_elapsed_share", None))

    if status:
        signals.append(f"status_{status}")
    if evidence_tier:
        signals.append(f"evidence_{evidence_tier}")

    if bool_value(getattr(facts, "finding_supported", False)):
        signals.append("finding_supported")
    else:
        signals.append("finding_not_supported")

    if bool_value(getattr(facts, "primary_supported", False)):
        signals.append("primary_supported")
    else:
        signals.append("primary_not_supported")

    signals.append(exchange_operator_bucket(exchange_count))

    if total_bytes is None:
        signals.append("bytes_missing_or_zero")
    elif total_bytes >= threshold:
        signals.append("bytes_ge_finding_threshold")
    else:
        signals.append("bytes_below_finding_threshold")

    if exchange_ms is None:
        signals.append("exchange_timing_unavailable")
    elif exchange_ms >= DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_MS:
        signals.append("exchange_elapsed_ge_primary_threshold")
    else:
        signals.append("exchange_elapsed_below_primary_threshold")

    if exchange_share is None:
        signals.append("exchange_share_unknown")
    elif exchange_share >= DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_SHARE:
        signals.append("exchange_share_ge_primary_threshold")
    else:
        signals.append("exchange_share_below_primary_threshold")

    return tuple(signals) or ("data_movement_calibration_unspecified",)


def exchange_operator_bucket(count: int) -> str:
    if count <= 0:
        return "exchange_ops_0"
    if count >= 4:
        return "exchange_ops_4_plus"
    return f"exchange_ops_{count}"


def numeric_counter_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def safe_profile_counter_names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    allowed = {definition.canonical_name for definition in BUNDLED_PROFILE_COUNTER_DEFINITIONS}
    names = []
    for item in value:
        name = str(item or "").strip()
        if name in allowed and name not in names:
            names.append(name)
    return tuple(names)


def observed_profile_counter_names(analysis: dict[str, Any]) -> tuple[str, ...]:
    names: list[str] = []
    for section in ("client_fetch", "memory_pressure", "data_movement", "profile_resources"):
        collect_profile_counter_names(analysis.get(section), names)
    return tuple(names)


def collect_profile_counter_names(value: object, names: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "counter":
                name = canonical_allowlisted_counter_name(item)
                if name and name not in names:
                    names.append(name)
            collect_profile_counter_names(item, names)
    elif isinstance(value, list):
        for item in value:
            collect_profile_counter_names(item, names)


def canonical_allowlisted_counter_name(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = text.lower()
    for definition in BUNDLED_PROFILE_COUNTER_DEFINITIONS:
        for name in (definition.canonical_name, *definition.aliases):
            if normalized == name.lower():
                return definition.canonical_name
    return ""


def audit_memory_pressure_opportunities(
    result: CoverageAuditResult, analysis: dict[str, Any]
) -> None:
    facts = analysis.get("memory_pressure")
    facts = facts if isinstance(facts, dict) else {}
    if bool_value(facts.get("finding_supported")):
        add_opportunity(result, "memory_pressure_supported")
    elif text_value(facts.get("status")) == "context_only" and (
        int_value(facts.get("memory_estimate_anomaly_count")) > 0
        or int_value(facts.get("zero_memory_estimate_gap_count")) > 0
    ):
        add_opportunity(result, "memory_estimate_context_only")


def summary_json_payload(
    result: CoverageAuditResult,
    *,
    max_unknown_primary_rate: float = 30.0,
    min_medium_primary_rate: float = 70.0,
) -> dict[str, object]:
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": "ok" if result.ok else "issues",
        "metrics": safe_count_dict(
            {
                "summaries": len(result.summary_paths),
                "total_cases": result.total_cases,
                "analyzed_cases": result.analyzed_cases,
                "missing_analysis": result.missing_analysis_count,
                "analysis_errors": result.analysis_error_count,
                "medium_or_better_primary_cases": result.medium_or_better_primary_count,
                "strict_primary_coverage_cases": result.strict_primary_coverage_case_count,
                "strict_unknown_primary_cases": result.strict_unknown_primary_count,
                "strict_medium_or_better_primary_cases": (
                    result.strict_medium_or_better_primary_count
                ),
                "direct_impala_cases": result.direct_impala_case_count,
                "issues": len(result.issues) + result.analysis_error_count,
            }.items(),
            include_zero=True,
        ),
        "issue_counts": safe_count_dict(Counter(issue.category for issue in result.issues).items()),
        "primary_gate": primary_gate_payload(
            result,
            max_unknown_primary_rate=max_unknown_primary_rate,
            min_medium_primary_rate=min_medium_primary_rate,
        ),
        "counters": summary_counter_payload(result),
    }


def primary_gate_payload(
    result: CoverageAuditResult,
    *,
    max_unknown_primary_rate: float = 30.0,
    min_medium_primary_rate: float = 70.0,
) -> dict[str, object]:
    strict_cases = result.strict_primary_coverage_case_count
    full_unknown_count = result.primary_counts.get("unknown", 0)
    full_medium_rate = rate_value(result.medium_or_better_primary_count, result.total_cases)
    full_unknown_rate = rate_value(full_unknown_count, result.total_cases)
    strict_unknown_rate = rate_value(result.strict_unknown_primary_count, strict_cases)
    strict_medium_rate = rate_value(result.strict_medium_or_better_primary_count, strict_cases)
    strict_gate_evaluable = strict_cases > 0
    unknown_rate_passed = strict_gate_evaluable and strict_unknown_rate <= max_unknown_primary_rate
    medium_rate_passed = strict_gate_evaluable and strict_medium_rate >= min_medium_primary_rate
    return {
        "thresholds": {
            "max_unknown_primary_rate_percent": float(max_unknown_primary_rate),
            "min_medium_primary_rate_percent": float(min_medium_primary_rate),
        },
        "full_batch": {
            "total_cases": result.total_cases,
            "unknown_primary_cases": full_unknown_count,
            "unknown_primary_rate_percent": full_unknown_rate,
            "medium_or_better_primary_cases": result.medium_or_better_primary_count,
            "medium_or_better_primary_rate_percent": full_medium_rate,
        },
        "strict": {
            "eligible_cases": strict_cases,
            "out_of_scope_cases": sum(result.strict_primary_out_of_scope_counts.values()),
            "unknown_primary_cases": result.strict_unknown_primary_count,
            "unknown_primary_rate_percent": strict_unknown_rate,
            "medium_or_better_primary_cases": result.strict_medium_or_better_primary_count,
            "medium_or_better_primary_rate_percent": strict_medium_rate,
            "gate_evaluable": strict_gate_evaluable,
            "unknown_rate_passed": unknown_rate_passed,
            "medium_rate_passed": medium_rate_passed,
            "gate_passed": unknown_rate_passed and medium_rate_passed,
        },
    }


def rate_value(count: int, total: int) -> float:
    return round(percent_value(count, total), 4)


def summary_counter_payload(result: CoverageAuditResult) -> dict[str, object]:
    counters = {
        "primary_counts": result.primary_counts,
        "primary_confidence_counts": result.primary_confidence_counts,
        "primary_classification_source_counts": result.primary_classification_source_counts,
        "primary_classifier_drift_counts": result.primary_classifier_drift_counts,
        "strict_primary_out_of_scope_counts": result.strict_primary_out_of_scope_counts,
        "strict_unknown_primary_reason_counts": result.strict_unknown_primary_reason_counts,
        "profile_dialect_counts": result.profile_dialect_counts,
        "profile_policy_counts": result.profile_policy_counts,
        "profile_counter_registry_counts": result.profile_counter_registry_counts,
        "profile_counter_missing_name_counts": result.profile_counter_missing_name_counts,
        "profile_counter_observed_missing_name_counts": (
            result.profile_counter_observed_missing_name_counts
        ),
        "source_compatibility_counts": result.source_compatibility_counts,
        "optional_source_counts": result.optional_source_counts,
        "direct_discovery_counts": result.direct_discovery_counts,
        "direct_source_readiness_counts": result.direct_source_readiness_counts,
        "direct_source_readiness_gap_counts": result.direct_source_readiness_gap_counts,
        "source_status_counts": result.source_status_counts,
        "evidence_quality_counts": result.evidence_quality_counts,
        "unknown_primary_reason_counts": result.unknown_primary_reason_counts,
        "unknown_primary_resolution_counts": result.unknown_primary_resolution_counts,
        "storage_unknown_reason_counts": result.storage_unknown_reason_counts,
        "scan_skew_supporting_reason_counts": result.scan_skew_supporting_reason_counts,
        "data_movement_supporting_reason_counts": (result.data_movement_supporting_reason_counts),
        "data_movement_calibration_signal_counts": (result.data_movement_calibration_signal_counts),
        "runtime_filter_calibration_signal_counts": (
            result.runtime_filter_calibration_signal_counts
        ),
        "coverage_gap_counts": result.gap_counts,
        "follow_up_opportunity_counts": result.opportunity_counts,
    }
    payload: dict[str, object] = {}
    for name, counter in counters.items():
        safe_name = safe_summary_key(name)
        if name in UNKNOWN_PRIMARY_REASON_COUNTER_NAMES:
            values = safe_unknown_reason_count_dict(counter)
        elif name in UNKNOWN_PRIMARY_RESOLUTION_COUNTER_NAMES:
            values = safe_unknown_resolution_count_dict(counter)
        else:
            values = safe_count_dict(counter.items())
        if safe_name and values:
            payload[safe_name] = values
    return payload


def safe_unknown_reason_count_dict(counter: object) -> dict[str, int]:
    if not hasattr(counter, "items"):
        return {}
    counts: Counter[str] = Counter()
    for key, value in counter.items():
        safe_key = safe_unknown_reason_summary_key(key)
        if safe_key:
            counts[safe_key] += int_value(value)
    return {key: value for key, value in sorted(counts.items()) if value > 0}


def safe_unknown_resolution_count_dict(counter: object) -> dict[str, int]:
    if not hasattr(counter, "items"):
        return {}
    counts: Counter[str] = Counter()
    for key, value in counter.items():
        token = normalized_token(key)
        if token in SAFE_UNKNOWN_PRIMARY_RESOLUTIONS:
            counts[token] += int_value(value)
    return {key: value for key, value in sorted(counts.items()) if value > 0}


def safe_unknown_reason_summary_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    safe_parts: list[str] = []
    for part in text.split("+"):
        token = normalized_token(part)
        if token in SAFE_UNKNOWN_REASON_SUMMARY_TOKENS:
            safe_parts.append(token)
    if not safe_parts:
        return ""
    return "_".join(safe_parts)


def safe_count_dict(
    items: Iterable[tuple[object, object]],
    *,
    include_zero: bool = False,
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for key, value in items:
        safe_key = safe_summary_key(key)
        if not safe_key:
            continue
        counts[safe_key] += int_value(value)
    return {key: value for key, value in sorted(counts.items()) if include_zero or value > 0}


def safe_summary_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if raw_like_summary_text(text):
        return "unsafe_token"
    return normalized_token(text)


def raw_like_summary_text(text: str) -> bool:
    return (
        contains_raw_sql_like_text(text)
        or URL_RE.search(text) is not None
        or LOCAL_PATH_RE.search(text) is not None
        or redaction.EMAIL_RE.search(text) is not None
        or redaction.IPV4_RE.search(text) is not None
        or redaction.HOSTLIKE_FQDN_RE.search(text) is not None
        or redaction.SECRET_VALUE_RE.search(text) is not None
    )


def write_summary_json(
    result: CoverageAuditResult,
    path: Path,
    *,
    input_summaries: Iterable[Path],
    max_unknown_primary_rate: float = 30.0,
    min_medium_primary_rate: float = 70.0,
) -> None:
    if any(same_path(path, input_summary) for input_summary in input_summaries):
        raise CoverageAuditOutputError("summary JSON output must not overwrite input artifacts")
    try:
        path.write_text(
            json.dumps(
                summary_json_payload(
                    result,
                    max_unknown_primary_rate=max_unknown_primary_rate,
                    min_medium_primary_rate=min_medium_primary_rate,
                ),
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise CoverageAuditOutputError("cannot write summary JSON") from exc


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=False) == right.resolve(strict=False)
    except OSError:
        return left.absolute() == right.absolute()


def print_counter(title: str, counter: Counter[str], *, out: TextIO, limit: int) -> None:
    print(f"{title}:", file=out)
    if not counter:
        print("  <none>", file=out)
        return
    for key, count in counter.most_common(limit):
        print(f"  {key}: {count}", file=out)


def print_follow_ups(
    title: str,
    counter: Counter[str],
    *,
    out: TextIO,
    total: int,
    limit: int,
) -> None:
    print(f"{title}:", file=out)
    if not counter:
        print("  <none>", file=out)
        return
    for key, count in counter.most_common(limit):
        definition = FOLLOW_UPS.get(
            key,
            FollowUpDefinition(
                "P2", "Unclassified coverage signal.", "Inspect safe facts before acting."
            ),
        )
        print(
            f"  {definition.priority} {key}: {count} ({percent(count, total)})",
            file=out,
        )
        print(f"    why: {definition.why}", file=out)
        print(f"    next: {definition.next_step}", file=out)


def print_issues(result: CoverageAuditResult, *, out: TextIO, limit: int) -> None:
    print("Issues:", file=out)
    if not result.issues:
        print("  none", file=out)
        return
    for issue in result.issues[:limit]:
        print(f"  {issue.category}: {issue.message}", file=out)


def print_result(result: CoverageAuditResult, *, out: TextIO = sys.stdout, limit: int = 12) -> None:
    print(f"Summaries: {len(result.summary_paths)}", file=out)
    print(
        "Cases: "
        f"total={result.total_cases}, analyzed={result.analyzed_cases}, "
        f"missing_analysis={result.missing_analysis_count}, "
        f"analysis_errors={result.analysis_error_count}",
        file=out,
    )
    print_counter("Primary bottlenecks", result.primary_counts, out=out, limit=limit)
    print_counter("Primary confidence", result.primary_confidence_counts, out=out, limit=limit)
    print_counter(
        "Primary classification source",
        result.primary_classification_source_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Primary classifier drift",
        result.primary_classifier_drift_counts,
        out=out,
        limit=limit,
    )
    print(
        "Medium-or-better primary coverage: "
        f"{result.medium_or_better_primary_count}/{result.total_cases} "
        f"({percent(result.medium_or_better_primary_count, result.total_cases)})",
        file=out,
    )
    print(
        "Strict primary coverage: "
        f"{result.strict_medium_or_better_primary_count}/"
        f"{result.strict_primary_coverage_case_count} medium-or-better "
        f"({percent(result.strict_medium_or_better_primary_count, result.strict_primary_coverage_case_count)}); "
        f"unknown={result.strict_unknown_primary_count}/"
        f"{result.strict_primary_coverage_case_count} "
        f"({percent(result.strict_unknown_primary_count, result.strict_primary_coverage_case_count)})",
        file=out,
    )
    print_counter(
        "Strict primary coverage out of scope",
        result.strict_primary_out_of_scope_counts,
        out=out,
        limit=limit,
    )
    print_counter("Profile dialects", result.profile_dialect_counts, out=out, limit=limit)
    print_counter("Profile policies", result.profile_policy_counts, out=out, limit=limit)
    print_counter(
        "Profile counter registry",
        result.profile_counter_registry_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Profile counter missing allowlist labels",
        result.profile_counter_missing_name_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Profile counter observed missing allowlist labels",
        result.profile_counter_observed_missing_name_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Impala source compatibility",
        result.source_compatibility_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Optional source availability",
        result.optional_source_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Direct discovery",
        result.direct_discovery_counts,
        out=out,
        limit=limit,
    )
    print(f"Direct Impala analyzed cases: {result.direct_impala_case_count}", file=out)
    print_counter(
        "Direct source readiness",
        result.direct_source_readiness_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Direct source readiness gaps",
        result.direct_source_readiness_gap_counts,
        out=out,
        limit=limit,
    )
    print_counter("Source coverage", result.source_status_counts, out=out, limit=limit)
    print_counter("Evidence quality", result.evidence_quality_counts, out=out, limit=limit)
    print_counter(
        "Unknown primary reasons",
        result.unknown_primary_reason_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Unknown primary resolutions",
        result.unknown_primary_resolution_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Strict unknown primary reasons",
        result.strict_unknown_primary_reason_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Storage unknown reasons",
        result.storage_unknown_reason_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Scan skew supporting reasons",
        result.scan_skew_supporting_reason_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Data movement supporting reasons",
        result.data_movement_supporting_reason_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Data movement calibration signals",
        result.data_movement_calibration_signal_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Runtime filter calibration signals",
        result.runtime_filter_calibration_signal_counts,
        out=out,
        limit=limit,
    )
    print_follow_ups(
        "Coverage gaps",
        result.gap_counts,
        out=out,
        total=max(result.total_cases, 1),
        limit=limit,
    )
    print_follow_ups(
        "Observed follow-up opportunities",
        result.opportunity_counts,
        out=out,
        total=max(result.analyzed_cases, 1),
        limit=limit,
    )
    print_issues(result, out=out, limit=limit)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summaries", nargs="+", type=Path, help="Path(s) to batch_summary.json")
    parser.add_argument("--limit", type=int, default=12, help="Rows to print per section")
    parser.add_argument(
        "--fail-on-diagnostic-coverage-gaps",
        action="store_true",
        help=(
            "Return non-zero when aggregate representative diagnostic coverage misses "
            "strict analyzer-output, primary-label, unknown-rate, or confidence-rate gates."
        ),
    )
    parser.add_argument(
        "--fail-on-direct-source-readiness-gaps",
        action="store_true",
        help=(
            "Return non-zero when direct Impala summaries lack explicit raw-free source "
            "provenance, profile capability states, or optional-source limitation states."
        ),
    )
    parser.add_argument(
        "--use-current-classifier-primary",
        action="store_true",
        help=(
            "Calculate primary-bottleneck coverage from current deterministic "
            "analysis.json classifier output instead of persisted summary labels; "
            "drift from retained summary labels is still reported."
        ),
    )
    parser.add_argument(
        "--max-unknown-primary-rate",
        type=float,
        default=30.0,
        metavar="PERCENT",
        help=(
            "Maximum allowed case_primary_bottleneck=unknown rate for strict coverage "
            "mode. Default: 30.0."
        ),
    )
    parser.add_argument(
        "--min-medium-primary-rate",
        type=float,
        default=70.0,
        metavar="PERCENT",
        help=(
            "Minimum required non-unknown medium/high primary-bottleneck coverage "
            "for strict coverage mode. Default: 70.0."
        ),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Write a raw-free machine-readable Impala coverage audit summary JSON.",
    )
    return parser.parse_args(argv)


def valid_percent_threshold(value: float) -> bool:
    return 0.0 <= value <= 100.0


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if not valid_percent_threshold(args.max_unknown_primary_rate):
        print("ERROR: --max-unknown-primary-rate must be between 0 and 100", file=sys.stderr)
        return 2
    if not valid_percent_threshold(args.min_medium_primary_rate):
        print("ERROR: --min-medium-primary-rate must be between 0 and 100", file=sys.stderr)
        return 2
    try:
        result = audit_summaries(
            args.summaries,
            fail_on_diagnostic_coverage_gaps=args.fail_on_diagnostic_coverage_gaps,
            fail_on_direct_source_readiness_gaps=args.fail_on_direct_source_readiness_gaps,
            use_current_classifier_primary=args.use_current_classifier_primary,
            max_unknown_primary_rate=args.max_unknown_primary_rate,
            min_medium_primary_rate=args.min_medium_primary_rate,
        )
    except EvidenceGateAuditInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_result(result, limit=args.limit)
    if args.summary_json is not None:
        try:
            write_summary_json(
                result,
                args.summary_json,
                input_summaries=args.summaries,
                max_unknown_primary_rate=args.max_unknown_primary_rate,
                min_medium_primary_rate=args.min_medium_primary_rate,
            )
        except CoverageAuditOutputError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    return 1 if not result.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
