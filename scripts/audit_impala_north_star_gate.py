#!/usr/bin/env python3
"""Gate retained raw-free Impala diagnostic-loop north-star summaries."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_impala_diagnostic_loop import safe_count_dict, safe_summary_key  # noqa: E402
from scripts.audit_impala_coverage_gaps import rate_value  # noqa: E402
from query_doctor.safety.manifest_references import (  # noqa: E402
    is_safe_relative_json_reference,
)


INPUT_SCHEMA_VERSION = "impala_diagnostic_loop_audit_v1"
SUMMARY_SCHEMA_VERSION = "impala_north_star_gate_v1"
SUITE_MANIFEST_KIND = "impala_north_star_suite_v1"
SUITE_MANIFEST_BUILDER_KIND = "impala_north_star_suite_manifest_builder_v1"
SOURCE_KIND = "retained_impala_diagnostic_loop_audit_summaries"
DEFAULT_MAX_UNKNOWN_PRIMARY_RATE = 30.0
DEFAULT_MIN_MEDIUM_PRIMARY_RATE = 70.0
DEFAULT_MIN_ANALYZED_CASES = 1
MEDIUM_OR_BETTER_PRIMARY_CONFIDENCES = {"high", "medium"}
NO_ACTIONABLE_PRIMARY_LABELS = {"missing", "none", "unknown"}
UNKNOWN_REASON_CATEGORY_BY_REASON = {
    "codegen_finding_not_primary_supported": "analyzer_primary_branch_gap",
    "data_movement_context_only": "data_movement_context_only_gap",
    "memory_estimate_context_only": "memory_context_only_gap",
    "missing_reason": "unknown_reason_missing",
    "no_primary_branch_supported": "analyzer_primary_branch_gap",
    "operator_time_not_dominant": "operator_timing_gap",
    "profile_dialect_not_supported_for_primary": "profile_dialect_gap",
    "scan_skew_medium_supporting_only": "scan_skew_supporting_only_gap",
    "storage_context_view_only": "storage_context_only_gap",
    "tail_candidates": "client_fetch_tail_followup",
    "unsafe_reason": "unknown_reason_unmapped",
    "very_short_query_or_unknown_wall_clock": "short_or_missing_wall_clock_boundary",
    "wall_clock_not_explained_by_mapped_operators": "operator_timing_gap",
}
UNKNOWN_CATEGORY_CLOSURE_TRACK = {
    "analyzer_primary_branch_gap": "add_deterministic_primary_branch_evidence",
    "client_fetch_tail_followup": "calibrate_client_fetch_tail_evidence",
    "data_movement_context_only_gap": "add_selected_query_data_movement_evidence",
    "memory_context_only_gap": "add_selected_query_memory_pressure_evidence",
    "mixed_unknown_evidence_gap": "split_mixed_unknown_reasons",
    "operator_timing_gap": "map_operator_time_to_selected_query_wall_clock",
    "profile_dialect_gap": "add_profile_dialect_mapping_fixtures",
    "scan_skew_supporting_only_gap": "add_scan_skew_corroborating_evidence",
    "short_or_missing_wall_clock_boundary": "separate_short_or_missing_wall_clock_cases",
    "storage_context_only_gap": "add_bounded_storage_context_evidence",
    "unknown_reason_missing": "preserve_unknown_until_reason_is_reported",
    "unknown_reason_not_reported": "preserve_unknown_until_reason_is_reported",
    "unknown_reason_unmapped": "map_unknown_reason_to_safe_category",
}
UNKNOWN_RESOLUTION_CLASS_BY_RESOLUTION = {
    "clean_case_no_action_boundary": "no_action_boundary",
    "clean_short_no_action_boundary": "no_action_boundary",
    "diagnostic_evidence_gap": "deterministic_evidence_gap",
    "missing_wall_clock_collector_gap": "collector_wall_clock_gap",
    "short_query_primary_out_of_scope": "out_of_scope_boundary",
}
UNKNOWN_RESOLUTION_CLASS_CLOSURE_TRACK = {
    "collector_wall_clock_gap": "fix_missing_wall_clock_collection",
    "deterministic_evidence_gap": "add_deterministic_evidence_for_unknown_primary",
    "no_action_boundary": "keep_boundary_out_of_evidence_backlog",
    "out_of_scope_boundary": "keep_boundary_out_of_evidence_backlog",
    "unknown_resolution_not_reported": "preserve_unknown_until_resolution_is_reported",
    "unknown_resolution_unmapped": "map_unknown_resolution_to_safe_class",
}


@dataclass(frozen=True)
class NorthStarGateResult:
    aggregate: dict[str, Any]
    issues: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


class NorthStarGateInputError(RuntimeError):
    """Raised when retained north-star inputs cannot be audited."""


class NorthStarGateOutputError(RuntimeError):
    """Raised when retained north-star output cannot be written."""


@dataclass(frozen=True)
class NorthStarInputSpec:
    path: Path
    label: str


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "summaries",
        nargs="*",
        type=Path,
        help="Retained raw-free impala_diagnostic_loop_audit_v1 summary JSON files.",
    )
    parser.add_argument(
        "--suite-manifest",
        type=Path,
        help=(
            "Optional local impala_north_star_suite_v1 manifest with safe relative "
            "raw-free loop-summary references."
        ),
    )
    parser.add_argument(
        "--require-min-inputs",
        type=int,
        default=1,
        help="Minimum retained loop summaries required for this gate. Default: 1.",
    )
    parser.add_argument(
        "--max-unknown-primary-rate",
        type=float,
        default=DEFAULT_MAX_UNKNOWN_PRIMARY_RATE,
        help="Maximum allowed case_primary_bottleneck=unknown percentage. Default: 30.0.",
    )
    parser.add_argument(
        "--min-medium-primary-rate",
        type=float,
        default=DEFAULT_MIN_MEDIUM_PRIMARY_RATE,
        help="Minimum required medium-or-better primary percentage. Default: 70.0.",
    )
    parser.add_argument(
        "--min-analyzed-cases",
        type=int,
        default=DEFAULT_MIN_ANALYZED_CASES,
        help="Minimum analyzed cases required across retained summaries. Default: 1.",
    )
    parser.add_argument(
        "--trend-label",
        default="retained_loop_north_star_gate",
        help="Sanitized label for the one-point trend entry.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Optional output path for the raw-free retained north-star aggregate.",
    )
    return parser.parse_args(argv)


def audit_retained_summaries(
    summary_paths: Iterable[Path],
    *,
    max_unknown_primary_rate: float = DEFAULT_MAX_UNKNOWN_PRIMARY_RATE,
    min_medium_primary_rate: float = DEFAULT_MIN_MEDIUM_PRIMARY_RATE,
    min_analyzed_cases: int = DEFAULT_MIN_ANALYZED_CASES,
    trend_label: str = "retained_loop_north_star_gate",
    require_min_inputs: int = 1,
    input_specs: Iterable[NorthStarInputSpec] | None = None,
    input_mode: str = "direct_summary_list",
) -> NorthStarGateResult:
    specs = tuple(input_specs or ())
    if specs:
        paths = tuple(spec.path for spec in specs)
        trend_labels = tuple(spec.label for spec in specs)
    else:
        paths = tuple(summary_paths)
        trend_labels = ()
    if not paths:
        raise NorthStarGateInputError("at least one retained loop summary is required")
    validate_percent_threshold(
        max_unknown_primary_rate,
        "max unknown primary rate",
        lower_exclusive=True,
    )
    validate_percent_threshold(min_medium_primary_rate, "minimum medium primary rate")
    min_analyzed_cases = max(1, int_value(min_analyzed_cases))
    require_min_inputs = max(1, int_value(require_min_inputs))

    loop_status_counts: Counter[str] = Counter()
    component_status_counts: Counter[str] = Counter()
    coverage_component_issue_counts: Counter[str] = Counter()
    workload_component_issue_counts: Counter[str] = Counter()
    primary_counts: Counter[str] = Counter()
    primary_confidence_counts: Counter[str] = Counter()
    unknown_primary_reason_counts: Counter[str] = Counter()
    unknown_primary_resolution_counts: Counter[str] = Counter()
    action_outcome_gate_counts: Counter[str] = Counter()
    action_outcome_result_counts: Counter[str] = Counter()
    analyzed_cases = 0
    total_cases = 0
    input_trend_points: list[dict[str, object]] = []

    for index, path in enumerate(paths):
        payload = load_loop_summary(path)
        loop_status_counts[safe_status(payload.get("status"))] += 1
        components = components_by_name(payload)

        input_loop_status_counts: Counter[str] = Counter()
        input_component_status_counts: Counter[str] = Counter()
        input_coverage_component_issue_counts: Counter[str] = Counter()
        input_workload_component_issue_counts: Counter[str] = Counter()
        input_primary_counts: Counter[str] = Counter()
        input_primary_confidence_counts: Counter[str] = Counter()
        input_unknown_primary_reason_counts: Counter[str] = Counter()
        input_unknown_primary_resolution_counts: Counter[str] = Counter()
        input_action_outcome_gate_counts: Counter[str] = Counter()
        input_action_outcome_result_counts: Counter[str] = Counter()
        input_analyzed_cases = 0
        input_total_cases = 0

        status = safe_status(payload.get("status"))
        input_loop_status_counts[status] += 1
        coverage = components.get("diagnostic_coverage")
        if coverage is None:
            component_status_counts["diagnostic_coverage_missing"] += 1
            input_component_status_counts["diagnostic_coverage_missing"] += 1
        else:
            component_status = safe_status(coverage.get("status"))
            component_status_counts[f"diagnostic_coverage_{component_status}"] += 1
            input_component_status_counts[f"diagnostic_coverage_{component_status}"] += 1
            coverage_metrics = sanitized_counter(coverage.get("metrics"), include_zero=True)
            input_total_cases = int_value(coverage_metrics.get("total_cases"))
            input_analyzed_cases = int_value(coverage_metrics.get("analyzed_cases"))
            total_cases += input_total_cases
            analyzed_cases += input_analyzed_cases
            coverage_breakdowns = safe_mapping(coverage.get("breakdowns"))
            input_primary_counts.update(
                sanitized_counter(coverage_breakdowns.get("primary_counts"))
            )
            input_primary_confidence_counts.update(
                sanitized_counter(coverage_breakdowns.get("primary_confidence_counts"))
            )
            input_unknown_primary_reason_counts.update(
                sanitized_counter(coverage_breakdowns.get("unknown_primary_reason_counts"))
            )
            input_unknown_primary_resolution_counts.update(
                sanitized_counter(coverage_breakdowns.get("unknown_primary_resolution_counts"))
            )
            input_coverage_component_issue_counts.update(
                sanitized_counter(coverage.get("issue_counts"))
            )
            primary_counts.update(input_primary_counts)
            primary_confidence_counts.update(input_primary_confidence_counts)
            unknown_primary_reason_counts.update(input_unknown_primary_reason_counts)
            unknown_primary_resolution_counts.update(input_unknown_primary_resolution_counts)
            coverage_component_issue_counts.update(input_coverage_component_issue_counts)

        workload = components.get("workload")
        if workload is None:
            component_status_counts["workload_missing"] += 1
            input_component_status_counts["workload_missing"] += 1
        else:
            component_status = safe_status(workload.get("status"))
            component_status_counts[f"workload_{component_status}"] += 1
            input_component_status_counts[f"workload_{component_status}"] += 1
            workload_breakdowns = safe_mapping(workload.get("breakdowns"))
            input_action_outcome_gate_counts.update(
                sanitized_counter(workload_breakdowns.get("action_outcome_gate_counts"))
            )
            input_action_outcome_result_counts.update(
                sanitized_counter(workload_breakdowns.get("action_outcome_result_counts"))
            )
            input_workload_component_issue_counts.update(
                sanitized_counter(workload.get("issue_counts"))
            )
            action_outcome_gate_counts.update(input_action_outcome_gate_counts)
            action_outcome_result_counts.update(input_action_outcome_result_counts)
            workload_component_issue_counts.update(input_workload_component_issue_counts)

        if trend_labels:
            label = trend_labels[index]
            input_aggregate = build_gate_aggregate(
                retained_summary_count=1,
                loop_status_counts=input_loop_status_counts,
                component_status_counts=input_component_status_counts,
                coverage_component_issue_counts=input_coverage_component_issue_counts,
                workload_component_issue_counts=input_workload_component_issue_counts,
                total_cases=input_total_cases,
                analyzed_cases=input_analyzed_cases,
                primary_counts=input_primary_counts,
                primary_confidence_counts=input_primary_confidence_counts,
                unknown_primary_reason_counts=input_unknown_primary_reason_counts,
                unknown_primary_resolution_counts=input_unknown_primary_resolution_counts,
                action_outcome_gate_counts=input_action_outcome_gate_counts,
                action_outcome_result_counts=input_action_outcome_result_counts,
                max_unknown_primary_rate=max_unknown_primary_rate,
                min_medium_primary_rate=min_medium_primary_rate,
                min_analyzed_cases=min_analyzed_cases,
                require_min_inputs=1,
                trend_label=label,
                input_mode=input_mode,
            )
            input_current = safe_mapping(input_aggregate.get("current"))
            input_trend_points.append(
                {
                    "label": safe_summary_key(label) or f"retained_batch_{index + 1}",
                    "unknown_primary_rate_percent": float_value(
                        input_current.get("unknown_primary_rate_percent")
                    ),
                    "medium_or_better_primary_rate_percent": float_value(
                        input_current.get("medium_or_better_primary_rate_percent")
                    ),
                    "measured_result_family_groups": int_value(
                        input_current.get("measured_result_family_groups")
                    ),
                    "open_outcome_family_groups": int_value(
                        input_current.get("open_outcome_family_groups")
                    ),
                    "gate_passed": bool(input_current.get("gate_passed")),
                }
            )

    aggregate = build_gate_aggregate(
        retained_summary_count=len(paths),
        loop_status_counts=loop_status_counts,
        component_status_counts=component_status_counts,
        coverage_component_issue_counts=coverage_component_issue_counts,
        workload_component_issue_counts=workload_component_issue_counts,
        total_cases=total_cases,
        analyzed_cases=analyzed_cases,
        primary_counts=primary_counts,
        primary_confidence_counts=primary_confidence_counts,
        unknown_primary_reason_counts=unknown_primary_reason_counts,
        unknown_primary_resolution_counts=unknown_primary_resolution_counts,
        action_outcome_gate_counts=action_outcome_gate_counts,
        action_outcome_result_counts=action_outcome_result_counts,
        max_unknown_primary_rate=max_unknown_primary_rate,
        min_medium_primary_rate=min_medium_primary_rate,
        min_analyzed_cases=min_analyzed_cases,
        require_min_inputs=require_min_inputs,
        trend_label=trend_label,
        input_mode=input_mode,
        trend_points=input_trend_points or None,
    )
    issues = gate_issues(aggregate)
    aggregate["issue_counts"] = safe_count_dict(Counter(issues).items())
    return NorthStarGateResult(aggregate=aggregate, issues=tuple(issues))


def audit_suite_manifest(
    manifest_path: Path,
    *,
    max_unknown_primary_rate: float = DEFAULT_MAX_UNKNOWN_PRIMARY_RATE,
    min_medium_primary_rate: float = DEFAULT_MIN_MEDIUM_PRIMARY_RATE,
    min_analyzed_cases: int = DEFAULT_MIN_ANALYZED_CASES,
    require_min_inputs: int = 1,
) -> NorthStarGateResult:
    specs = load_suite_manifest(manifest_path)
    return audit_retained_summaries(
        (),
        max_unknown_primary_rate=max_unknown_primary_rate,
        min_medium_primary_rate=min_medium_primary_rate,
        min_analyzed_cases=min_analyzed_cases,
        require_min_inputs=require_min_inputs,
        input_specs=specs,
        input_mode="suite_manifest",
    )


def load_suite_manifest(path: Path) -> tuple[NorthStarInputSpec, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise NorthStarGateInputError("north-star suite manifest is unreadable") from exc
    except json.JSONDecodeError as exc:
        raise NorthStarGateInputError("north-star suite manifest is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise NorthStarGateInputError("north-star suite manifest root is not an object")
    if payload.get("manifest_kind") != SUITE_MANIFEST_KIND:
        raise NorthStarGateInputError("north-star suite manifest kind is unsupported")
    metadata = safe_mapping(payload.get("metadata"))
    if metadata.get("path_reference") != "relative_to_manifest":
        raise NorthStarGateInputError("north-star suite manifest path reference is unsupported")
    if metadata.get("redaction_reviewed") is not True:
        raise NorthStarGateInputError("north-star suite manifest requires redaction review")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise NorthStarGateInputError("north-star suite manifest has no entries")
    if int_value(metadata.get("entry_count")) != len(entries):
        raise NorthStarGateInputError("north-star suite manifest entry count mismatch")

    base_dir = path.parent
    specs: list[NorthStarInputSpec] = []
    seen_refs: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise NorthStarGateInputError("north-star suite manifest entry is invalid")
        reference = entry.get("loop_summary_json")
        if not is_safe_relative_json_reference(reference):
            raise NorthStarGateInputError("north-star suite manifest reference is unsafe")
        reference_text = str(reference)
        if reference_text in seen_refs:
            raise NorthStarGateInputError("north-star suite manifest references must be unique")
        seen_refs.add(reference_text)
        label = safe_summary_key(entry.get("label")) or f"retained_batch_{index + 1}"
        specs.append(NorthStarInputSpec(path=base_dir / reference_text, label=label))
    return tuple(specs)


def load_loop_summary(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise NorthStarGateInputError("retained loop summary is unreadable") from exc
    except json.JSONDecodeError as exc:
        raise NorthStarGateInputError("retained loop summary is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise NorthStarGateInputError("retained loop summary root is not an object")
    schema = str(payload.get("schema_version") or "")
    if schema != INPUT_SCHEMA_VERSION:
        raise NorthStarGateInputError("retained loop summary schema is unsupported")
    return payload


def components_by_name(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    components = payload.get("components")
    if not isinstance(components, list):
        return {}
    by_name: dict[str, dict[str, Any]] = {}
    for component in components:
        if not isinstance(component, dict):
            continue
        name = safe_summary_key(component.get("name"))
        if name and name not in by_name:
            by_name[name] = component
    return by_name


def build_gate_aggregate(
    *,
    retained_summary_count: int,
    loop_status_counts: Counter[str],
    component_status_counts: Counter[str],
    coverage_component_issue_counts: Counter[str],
    workload_component_issue_counts: Counter[str],
    total_cases: int,
    analyzed_cases: int,
    primary_counts: Counter[str],
    primary_confidence_counts: Counter[str],
    unknown_primary_reason_counts: Counter[str],
    unknown_primary_resolution_counts: Counter[str],
    action_outcome_gate_counts: Counter[str],
    action_outcome_result_counts: Counter[str],
    max_unknown_primary_rate: float,
    min_medium_primary_rate: float,
    min_analyzed_cases: int,
    require_min_inputs: int,
    trend_label: str,
    input_mode: str,
    trend_points: list[dict[str, object]] | None = None,
) -> dict[str, Any]:
    primary_label_cases = int(sum(primary_counts.values()))
    primary_confidence_cases = int(sum(primary_confidence_counts.values()))
    unknown_primary_cases = int(primary_counts.get("unknown", 0))
    medium_or_better_primary_cases = medium_or_better_primary_count(primary_confidence_counts)
    unknown_primary_rate = rate_value(unknown_primary_cases, primary_label_cases)
    medium_or_better_primary_rate = rate_value(
        medium_or_better_primary_cases,
        primary_label_cases,
    )
    unknown_primary_category_counts = unknown_category_counts(
        unknown_primary_reason_counts,
        unknown_primary_cases=unknown_primary_cases,
    )
    unknown_primary_resolution_class_counts = unknown_resolution_class_counts(
        unknown_primary_resolution_counts,
        unknown_primary_cases=unknown_primary_cases,
    )
    required_family_groups = int(action_outcome_gate_counts.get("required_family_groups", 0))
    sample_met_family_groups = int(action_outcome_gate_counts.get("sample_met_family_groups", 0))
    measured_result_family_groups = int(
        action_outcome_gate_counts.get("measured_result_family_groups", 0)
    )
    open_outcome_family_groups = int(action_outcome_gate_counts.get("open_family_groups", 0))
    required_family_measured_results = int(
        action_outcome_result_counts.get("required_family_measured_results", 0)
    )
    coverage_gate_passed = (
        retained_summary_count >= require_min_inputs
        and analyzed_cases >= min_analyzed_cases
        and primary_label_cases > 0
        and primary_confidence_cases == primary_label_cases
        and unknown_primary_rate < max_unknown_primary_rate
        and medium_or_better_primary_rate >= min_medium_primary_rate
    )
    outcome_gate_passed = (
        retained_summary_count >= require_min_inputs
        and int(action_outcome_gate_counts.get("gate_passed", 0)) == retained_summary_count
        and int(action_outcome_gate_counts.get("action_outcomes_supplied", 0))
        == retained_summary_count
        and int(action_outcome_gate_counts.get("raw_free_failed", 0)) == 0
        and required_family_groups > 0
        and sample_met_family_groups >= required_family_groups
        and measured_result_family_groups >= required_family_groups
        and open_outcome_family_groups == 0
    )
    input_gate_passed = (
        retained_summary_count >= require_min_inputs
        and loop_status_counts.get("ok", 0) == retained_summary_count
        and component_status_counts.get("diagnostic_coverage_ok", 0) == retained_summary_count
        and component_status_counts.get("workload_ok", 0) == retained_summary_count
    )
    current = {
        "retained_loop_summaries": retained_summary_count,
        "total_cases": int(total_cases),
        "analyzed_cases": int(analyzed_cases),
        "primary_label_cases": primary_label_cases,
        "primary_confidence_cases": primary_confidence_cases,
        "unknown_primary_cases": unknown_primary_cases,
        "unknown_primary_rate_percent": unknown_primary_rate,
        "medium_or_better_primary_cases": medium_or_better_primary_cases,
        "medium_or_better_primary_rate_percent": medium_or_better_primary_rate,
        "required_action_outcome_family_groups": required_family_groups,
        "sample_met_action_outcome_family_groups": sample_met_family_groups,
        "measured_result_family_groups": measured_result_family_groups,
        "open_outcome_family_groups": open_outcome_family_groups,
        "required_family_measured_results": required_family_measured_results,
        "unknown_primary_evidence_gap_cases": int(
            unknown_primary_resolution_class_counts.get("deterministic_evidence_gap", 0)
        ),
        "unknown_primary_boundary_cases": int(
            unknown_primary_resolution_class_counts.get("no_action_boundary", 0)
            + unknown_primary_resolution_class_counts.get("out_of_scope_boundary", 0)
        ),
        "unknown_primary_collector_gap_cases": int(
            unknown_primary_resolution_class_counts.get("collector_wall_clock_gap", 0)
        ),
        "unknown_primary_unclassified_resolution_cases": int(
            unknown_primary_resolution_class_counts.get("unknown_resolution_not_reported", 0)
            + unknown_primary_resolution_class_counts.get("unknown_resolution_unmapped", 0)
        ),
        "input_gate_passed": input_gate_passed,
        "coverage_gate_passed": coverage_gate_passed,
        "outcome_gate_passed": outcome_gate_passed,
        "gate_passed": input_gate_passed and coverage_gate_passed and outcome_gate_passed,
    }
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "source": SOURCE_KIND,
        "input": {
            "schema_version": INPUT_SCHEMA_VERSION,
            "mode": safe_summary_key(input_mode) or "direct_summary_list",
            "retained_loop_summaries": retained_summary_count,
        },
        "thresholds": {
            "max_unknown_primary_rate_percent": float(max_unknown_primary_rate),
            "min_medium_or_better_primary_rate_percent": float(min_medium_primary_rate),
            "min_analyzed_cases": int(min_analyzed_cases),
            "require_min_inputs": int(require_min_inputs),
            "action_outcome_gate_required": True,
        },
        "current": current,
        "input_status_counts": safe_count_dict(loop_status_counts.items()),
        "component_status_counts": safe_count_dict(component_status_counts.items()),
        "coverage": {
            "component_issue_counts": safe_count_dict(coverage_component_issue_counts.items()),
            "primary_counts": safe_count_dict(primary_counts.items()),
            "primary_confidence_counts": safe_count_dict(primary_confidence_counts.items()),
            "unknown_primary_reason_counts": safe_count_dict(unknown_primary_reason_counts.items()),
            "unknown_primary_category_counts": safe_count_dict(
                unknown_primary_category_counts.items()
            ),
            "top_unknown_primary_categories": top_unknown_category_payload(
                unknown_primary_category_counts,
                unknown_primary_cases=unknown_primary_cases,
            ),
            "unknown_primary_resolution_counts": safe_count_dict(
                unknown_primary_resolution_counts.items()
            ),
            "unknown_primary_resolution_class_counts": safe_count_dict(
                unknown_primary_resolution_class_counts.items()
            ),
            "top_unknown_primary_resolution_classes": top_unknown_resolution_class_payload(
                unknown_primary_resolution_class_counts,
                unknown_primary_cases=unknown_primary_cases,
            ),
        },
        "outcome": {
            "component_issue_counts": safe_count_dict(workload_component_issue_counts.items()),
            "action_outcome_gate_counts": safe_count_dict(action_outcome_gate_counts.items()),
            "action_outcome_result_counts": safe_count_dict(action_outcome_result_counts.items()),
        },
        "trend": trend_points
        or [
            {
                "label": safe_summary_key(trend_label) or "retained_loop_north_star_gate",
                "unknown_primary_rate_percent": unknown_primary_rate,
                "medium_or_better_primary_rate_percent": medium_or_better_primary_rate,
                "measured_result_family_groups": measured_result_family_groups,
                "open_outcome_family_groups": open_outcome_family_groups,
                "gate_passed": current["gate_passed"],
            }
        ],
    }


def gate_issues(aggregate: dict[str, Any]) -> list[str]:
    current = safe_mapping(aggregate.get("current"))
    thresholds = safe_mapping(aggregate.get("thresholds"))
    input_status_counts = sanitized_counter(aggregate.get("input_status_counts"))
    component_status_counts = sanitized_counter(aggregate.get("component_status_counts"))
    outcome = safe_mapping(aggregate.get("outcome"))
    action_outcome_gate_counts = sanitized_counter(outcome.get("action_outcome_gate_counts"))
    issues: list[str] = []

    retained_summaries = int_value(current.get("retained_loop_summaries"))
    if retained_summaries <= 0:
        issues.append("retained_loop_summaries_missing")
    if retained_summaries < int_value(thresholds.get("require_min_inputs")):
        issues.append("retained_loop_summary_sample_below_threshold")
    if input_status_counts.get("ok", 0) < retained_summaries:
        issues.append("retained_loop_summary_status_issues")
    if component_status_counts.get("diagnostic_coverage_ok", 0) < retained_summaries:
        issues.append("diagnostic_coverage_component_not_ok")
    if component_status_counts.get("workload_ok", 0) < retained_summaries:
        issues.append("workload_component_not_ok")

    if int_value(current.get("analyzed_cases")) < int_value(thresholds.get("min_analyzed_cases")):
        issues.append("analyzed_case_sample_below_threshold")
    if int_value(current.get("primary_label_cases")) <= 0:
        issues.append("primary_label_counts_missing")
    if int_value(current.get("primary_confidence_cases")) != int_value(
        current.get("primary_label_cases")
    ):
        issues.append("primary_confidence_counts_mismatch")
    if float_value(current.get("unknown_primary_rate_percent")) >= float_value(
        thresholds.get("max_unknown_primary_rate_percent")
    ):
        issues.append("unknown_primary_rate_above_threshold")
    if float_value(current.get("medium_or_better_primary_rate_percent")) < float_value(
        thresholds.get("min_medium_or_better_primary_rate_percent")
    ):
        issues.append("medium_or_better_primary_rate_below_threshold")

    if action_outcome_gate_counts.get("action_outcomes_supplied", 0) < retained_summaries:
        issues.append("action_outcomes_not_supplied")
    if action_outcome_gate_counts.get("gate_evaluable", 0) < retained_summaries:
        issues.append("action_outcome_gate_not_evaluable")
    if action_outcome_gate_counts.get("raw_free_failed", 0) > 0:
        issues.append("action_outcomes_raw_free_failed")
    required = int_value(current.get("required_action_outcome_family_groups"))
    if required <= 0:
        issues.append("action_outcome_required_family_groups_missing")
    if int_value(current.get("sample_met_action_outcome_family_groups")) < required:
        issues.append("action_outcome_sample_below_threshold")
    if int_value(current.get("measured_result_family_groups")) < required:
        issues.append("action_outcome_measured_results_missing")
    if int_value(current.get("open_outcome_family_groups")) > 0:
        issues.append("action_outcome_open_family_groups")
    if action_outcome_gate_counts.get("gate_passed", 0) < retained_summaries:
        issues.append("action_outcome_gate_failed")

    if not current.get("coverage_gate_passed"):
        issues.append("north_star_coverage_gate_failed")
    if not current.get("outcome_gate_passed"):
        issues.append("north_star_outcome_gate_failed")
    if not current.get("input_gate_passed"):
        issues.append("north_star_input_gate_failed")
    if not current.get("gate_passed"):
        issues.append("impala_north_star_gate_failed")
    return issues


def medium_or_better_primary_count(counter: Counter[str]) -> int:
    total = 0
    for key, count in counter.items():
        label, confidence = primary_confidence_parts(key)
        if (
            label not in NO_ACTIONABLE_PRIMARY_LABELS
            and confidence in MEDIUM_OR_BETTER_PRIMARY_CONFIDENCES
        ):
            total += int_value(count)
    return total


def unknown_category_counts(
    reason_counts: Counter[str],
    *,
    unknown_primary_cases: int,
) -> Counter[str]:
    categories: Counter[str] = Counter()
    for reason, count in reason_counts.items():
        category = unknown_reason_category(reason)
        if category:
            categories[category] += int_value(count)
    reported = sum(categories.values())
    missing = max(0, int_value(unknown_primary_cases) - int_value(reported))
    if missing:
        categories["unknown_reason_not_reported"] += missing
    return categories


def unknown_reason_category(reason: object) -> str:
    token = safe_summary_key(reason)
    if not token:
        return "unknown_reason_missing"
    if token in UNKNOWN_REASON_CATEGORY_BY_REASON:
        return UNKNOWN_REASON_CATEGORY_BY_REASON[token]
    matched = tuple(
        reason_token for reason_token in UNKNOWN_REASON_CATEGORY_BY_REASON if reason_token in token
    )
    if len(matched) == 1:
        return UNKNOWN_REASON_CATEGORY_BY_REASON[matched[0]]
    if len(matched) > 1:
        return "mixed_unknown_evidence_gap"
    return "unknown_reason_unmapped"


def top_unknown_category_payload(
    category_counts: Counter[str],
    *,
    unknown_primary_cases: int,
    limit: int = 5,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for category, count in sorted(
        category_counts.items(),
        key=lambda item: (-int_value(item[1]), safe_summary_key(item[0])),
    )[: max(1, limit)]:
        safe_category = safe_summary_key(category) or "unknown_reason_unmapped"
        rows.append(
            {
                "category": safe_category,
                "unknown_primary_cases": int_value(count),
                "unknown_share_percent": rate_value(int_value(count), unknown_primary_cases),
                "closure_track": UNKNOWN_CATEGORY_CLOSURE_TRACK.get(
                    safe_category,
                    "map_unknown_reason_to_safe_category",
                ),
            }
        )
    return rows


def unknown_resolution_class_counts(
    resolution_counts: Counter[str],
    *,
    unknown_primary_cases: int,
) -> Counter[str]:
    classes: Counter[str] = Counter()
    for resolution, count in resolution_counts.items():
        resolution_class = unknown_resolution_class(resolution)
        classes[resolution_class] += int_value(count)
    reported = sum(classes.values())
    missing = max(0, int_value(unknown_primary_cases) - int_value(reported))
    if missing:
        classes["unknown_resolution_not_reported"] += missing
    return classes


def unknown_resolution_class(resolution: object) -> str:
    token = safe_summary_key(resolution)
    if not token:
        return "unknown_resolution_not_reported"
    return UNKNOWN_RESOLUTION_CLASS_BY_RESOLUTION.get(token, "unknown_resolution_unmapped")


def top_unknown_resolution_class_payload(
    class_counts: Counter[str],
    *,
    unknown_primary_cases: int,
    limit: int = 5,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for resolution_class, count in sorted(
        class_counts.items(),
        key=lambda item: (-int_value(item[1]), safe_summary_key(item[0])),
    )[: max(1, limit)]:
        safe_class = safe_summary_key(resolution_class) or "unknown_resolution_unmapped"
        rows.append(
            {
                "resolution_class": safe_class,
                "unknown_primary_cases": int_value(count),
                "unknown_share_percent": rate_value(int_value(count), unknown_primary_cases),
                "closure_track": UNKNOWN_RESOLUTION_CLASS_CLOSURE_TRACK.get(
                    safe_class,
                    "map_unknown_resolution_to_safe_class",
                ),
            }
        )
    return rows


def primary_confidence_parts(key: object) -> tuple[str, str]:
    token = safe_summary_key(key)
    if "_" not in token:
        return token, ""
    label, confidence = token.rsplit("_", 1)
    return label, confidence


def sanitized_counter(value: object, *, include_zero: bool = False) -> dict[str, int]:
    if not hasattr(value, "items"):
        return {}
    return safe_count_dict(value.items(), include_zero=include_zero)


def safe_mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_status(value: object) -> str:
    return safe_summary_key(value) or "unknown"


def int_value(value: object) -> int:
    try:
        return max(0, int(float(str(value).strip())))
    except (TypeError, ValueError):
        return 0


def float_value(value: object) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def validate_percent_threshold(
    value: object,
    label: str,
    *,
    lower_exclusive: bool = False,
) -> None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise NorthStarGateInputError(f"{label} must be a percentage") from exc
    if lower_exclusive:
        valid = 0.0 < number <= 100.0
    else:
        valid = 0.0 <= number <= 100.0
    if not valid:
        raise NorthStarGateInputError(f"{label} must be between 0 and 100")


def write_summary_json(result: NorthStarGateResult, path: Path) -> None:
    try:
        path.write_text(
            json.dumps(result.aggregate, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise NorthStarGateOutputError("cannot write retained north-star summary JSON") from exc


def print_result(result: NorthStarGateResult) -> None:
    current = result.aggregate["current"]
    print(
        "Impala retained north-star: "
        f"summaries={current['retained_loop_summaries']}; "
        f"unknown={current['unknown_primary_cases']}/{current['primary_label_cases']} "
        f"({current['unknown_primary_rate_percent']}%); "
        f"medium+={current['medium_or_better_primary_cases']}/"
        f"{current['primary_label_cases']} "
        f"({current['medium_or_better_primary_rate_percent']}%); "
        f"outcome_measured_groups={current['measured_result_family_groups']}; "
        f"outcome_open_groups={current['open_outcome_family_groups']}"
    )
    print(f"Gate: {'passed' if result.ok else 'failed'}")
    if result.issues:
        print("Issues:")
        for issue in result.issues:
            print(f"  {issue}")


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.suite_manifest is not None and args.summaries:
            raise NorthStarGateInputError(
                "pass either retained loop summaries or --suite-manifest, not both"
            )
        if args.suite_manifest is None and not args.summaries:
            raise NorthStarGateInputError("at least one retained loop summary is required")
        if args.suite_manifest is not None:
            result = audit_suite_manifest(
                args.suite_manifest,
                max_unknown_primary_rate=args.max_unknown_primary_rate,
                min_medium_primary_rate=args.min_medium_primary_rate,
                min_analyzed_cases=args.min_analyzed_cases,
                require_min_inputs=args.require_min_inputs,
            )
        else:
            result = audit_retained_summaries(
                args.summaries,
                max_unknown_primary_rate=args.max_unknown_primary_rate,
                min_medium_primary_rate=args.min_medium_primary_rate,
                min_analyzed_cases=args.min_analyzed_cases,
                trend_label=args.trend_label,
                require_min_inputs=args.require_min_inputs,
            )
        if args.summary_json is not None:
            write_summary_json(result, args.summary_json)
    except (NorthStarGateInputError, NorthStarGateOutputError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_result(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
