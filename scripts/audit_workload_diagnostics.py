#!/usr/bin/env python3
"""Audit raw-free workload diagnostics across a Recent batch summary."""

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

from query_doctor.web.action_outcomes import (  # noqa: E402
    DEFAULT_METRIC_MIN_APPLIED,
    RECOMMENDATION_LABELS,
    SCHEMA_VERSION as ACTION_OUTCOME_SCHEMA_VERSION,
    WorkloadOutcomeMetric,
    load_action_outcomes,
    recommendation_id_allowed,
    safe_recommendation_label,
    summarize_workload_action_outcomes,
    workload_outcome_signal_for_recommendation,
)
from query_doctor.recent.workload_fingerprint import compute_workload_fingerprint  # noqa: E402
from query_doctor.report.safety_validation import contains_raw_sql_like_text  # noqa: E402
from query_doctor.safety import redaction  # noqa: E402
from query_doctor.web.presenters.recent_scan import present_recent_scan_summary  # noqa: E402
from query_doctor.web.presenters.workload_detail import present_workload_detail  # noqa: E402


COMPARABLE_COMPARISON_TERMS = (
    "compare",
    "comparable",
)
COMPARABLE_RERUN_TERMS = (
    "next scan",
    "next run",
    "rerun",
    "re-run",
    "comparable load",
    "comparable scan",
    "under comparable",
)
REGRESSION_LABELS = {"strong", "mild", "none", "unknown"}
URL_RE = re.compile(r"\bhttps?://", re.IGNORECASE)
LOCAL_PATH_RE = re.compile(r"(?<![\w/])(?:/private)?/tmp/|(?<![\w/])/Users/")
MEASURED_OUTCOME_SUMMARY_RE = re.compile(
    r"\b(?:improved|no change|worsened)\s+[1-9][0-9]*\b",
    re.IGNORECASE,
)
SUMMARY_SCHEMA_VERSION = "workload_diagnostics_audit_v1"
ACTION_OUTCOME_FEEDBACK_ISSUE_CATEGORIES = (
    "workload_action_outcome_feedback_missing",
    "workload_action_outcome_sample_below_threshold",
    "workload_action_outcome_result_unmeasured",
    "workload_action_outcome_no_apply_decision",
    "workload_action_outcome_family_feedback_missing",
    "workload_action_outcome_family_sample_below_threshold",
    "workload_action_outcome_family_result_unmeasured",
)
MEASURED_ACTION_OUTCOMES = ("improved", "no_change", "worsened")
TRACKED_ACTION_OUTCOMES = (*MEASURED_ACTION_OUTCOMES, "unsure")


@dataclass(frozen=True)
class WorkloadAuditIssue:
    category: str
    message: str


@dataclass
class WorkloadDiagnosticsAuditResult:
    summary_name: str
    total_cases: int
    row_count: int = 0
    workload_group_count: int = 0
    workload_detail_count: int = 0
    row_workload_fingerprint_count: int = 0
    row_incomplete_workload_fingerprint_count: int = 0
    row_repeated_workload_group_count: int = 0
    row_repeated_workload_case_count: int = 0
    repeated_case_count: int = 0
    action_queue_count: int = 0
    workload_history_counts: Counter[str] = field(default_factory=Counter)
    group_regression_counts: Counter[str] = field(default_factory=Counter)
    group_baseline_counts: Counter[str] = field(default_factory=Counter)
    group_member_count_buckets: Counter[str] = field(default_factory=Counter)
    detail_representative_counts: Counter[str] = field(default_factory=Counter)
    detail_action_hint_counts: Counter[str] = field(default_factory=Counter)
    detail_limitation_counts: Counter[str] = field(default_factory=Counter)
    action_queue_signal_counts: Counter[str] = field(default_factory=Counter)
    action_queue_verification_counts: Counter[str] = field(default_factory=Counter)
    action_outcome_source_counts: Counter[str] = field(default_factory=Counter)
    action_outcome_min_applied: int = DEFAULT_METRIC_MIN_APPLIED
    action_outcome_group_coverage_counts: Counter[str] = field(default_factory=Counter)
    action_outcome_family_counts: Counter[str] = field(default_factory=Counter)
    action_outcome_family_requirement_counts: Counter[str] = field(default_factory=Counter)
    action_outcome_gate_counts: Counter[str] = field(default_factory=Counter)
    action_outcome_verification_counts: Counter[str] = field(default_factory=Counter)
    action_outcome_result_counts: Counter[str] = field(default_factory=Counter)
    action_queue_outcome_counts: Counter[str] = field(default_factory=Counter)
    detail_action_hint_outcome_counts: Counter[str] = field(default_factory=Counter)
    row_incomplete_workload_field_counts: Counter[str] = field(default_factory=Counter)
    row_incomplete_workload_field_source_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[WorkloadAuditIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


class WorkloadAuditInputError(RuntimeError):
    """Raised when a batch summary cannot be audited."""


class WorkloadAuditOutputError(RuntimeError):
    """Raised when a raw-free summary cannot be written."""


def load_summary(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorkloadAuditInputError(f"cannot read summary: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkloadAuditInputError(f"summary is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise WorkloadAuditInputError(f"summary root is not an object: {path}")
    if not isinstance(payload.get("cases"), list):
        raise WorkloadAuditInputError(f"summary does not contain a cases list: {path}")
    return payload


def audit_summary(
    summary_path: Path,
    *,
    fail_on_workload_readiness_gaps: bool = False,
    require_workload_groups: bool = False,
    action_outcomes_path: Path | None = None,
    fail_on_action_outcome_readiness_gaps: bool = False,
    action_outcome_min_applied: int = DEFAULT_METRIC_MIN_APPLIED,
) -> WorkloadDiagnosticsAuditResult:
    summary_path = summary_path.resolve(strict=True)
    summary = load_summary(summary_path)
    action_outcome_min_applied = max(1, int_value(action_outcome_min_applied))
    action_outcome_metrics = load_workload_outcome_metrics(
        result_path=action_outcomes_path,
        min_applied=action_outcome_min_applied,
    )
    audit_action_outcome_feedback = (
        action_outcomes_path is not None or fail_on_action_outcome_readiness_gaps
    )
    scan = present_recent_scan_summary(summary, workload_outcome_metrics=action_outcome_metrics)
    result = WorkloadDiagnosticsAuditResult(
        summary_name=summary_path.name,
        total_cases=len(summary.get("cases") or ()),
        row_count=len(scan.rows),
        workload_group_count=len(scan.workload_groups.groups),
        action_queue_count=len(scan.workload_digest.action_queue),
        action_outcome_min_applied=action_outcome_min_applied,
    )
    raw_cases = tuple(case for case in summary.get("cases") or () if isinstance(case, dict))
    audit_row_workload_fingerprints(result, scan.rows, raw_cases=raw_cases)

    if audit_action_outcome_feedback:
        audit_action_outcome_source(result, action_outcomes_path, action_outcome_metrics)
    audit_workload_history(result, scan.workload_history)
    grouped_rows = {
        group.fingerprint: tuple(
            row for row in scan.rows if row.workload_fingerprint == group.fingerprint
        )
        for group in scan.workload_groups.groups
    }
    for group in scan.workload_groups.groups:
        rows = grouped_rows.get(group.fingerprint, ())
        audit_workload_group(
            result,
            summary,
            group,
            rows,
            action_outcome_metrics=action_outcome_metrics,
            audit_action_outcome_feedback=audit_action_outcome_feedback,
        )
    for entry in scan.workload_digest.action_queue:
        audit_action_queue_entry(
            result,
            entry,
            action_outcome_metrics=action_outcome_metrics,
            audit_action_outcome_feedback=audit_action_outcome_feedback,
        )
    update_action_outcome_gate_counts(result, audit_action_outcome_feedback)

    if fail_on_workload_readiness_gaps:
        add_readiness_issues(result)
    if require_workload_groups:
        add_workload_group_requirement_issue(result)
    if fail_on_action_outcome_readiness_gaps:
        add_action_outcome_readiness_issues(result)
    return result


def load_workload_outcome_metrics(
    *,
    result_path: Path | None,
    min_applied: int,
) -> dict[str, WorkloadOutcomeMetric]:
    if result_path is None:
        return {}
    records = load_action_outcomes(path=result_path, limit=1_000_000)
    return summarize_workload_action_outcomes(records, min_applied=max(1, min_applied))


def audit_action_outcome_source(
    result: WorkloadDiagnosticsAuditResult,
    action_outcomes_path: Path | None,
    metrics: dict[str, WorkloadOutcomeMetric],
) -> None:
    if action_outcomes_path is None:
        result.action_outcome_source_counts["not_supplied"] += 1
        return
    result.action_outcome_source_counts["supplied"] += 1
    result.action_outcome_source_counts[f"workloads_{count_bucket(len(metrics))}"] += 1
    if not metrics:
        result.issue_counts["action_outcomes_empty"] += 1
    if action_outcomes_raw_free_violations(action_outcomes_path):
        result.issue_counts["action_outcomes_raw_like"] += 1


def action_outcomes_raw_free_violations(path: Path) -> tuple[str, ...]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ()
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


def audit_row_workload_fingerprints(
    result: WorkloadDiagnosticsAuditResult,
    rows: Iterable[Any],
    *,
    raw_cases: Iterable[dict[str, Any]] = (),
) -> None:
    counts: Counter[str] = Counter()
    incomplete_count = 0
    raw_case_by_index = tuple(raw_cases)
    for index, row in enumerate(rows):
        fingerprint = str(getattr(row, "workload_fingerprint", "") or "").strip()
        if not fingerprint:
            continue
        if str(getattr(row, "workload_fingerprint_short", "") or "").strip():
            counts[fingerprint] += 1
        else:
            incomplete_count += 1
            raw_case = raw_case_by_index[index] if index < len(raw_case_by_index) else {}
            audit_incomplete_workload_fields(result, raw_case)
    result.row_workload_fingerprint_count = sum(counts.values())
    result.row_incomplete_workload_fingerprint_count = incomplete_count
    result.row_repeated_workload_group_count = sum(1 for count in counts.values() if count >= 2)
    result.row_repeated_workload_case_count = sum(count for count in counts.values() if count >= 2)


def audit_incomplete_workload_fields(
    result: WorkloadDiagnosticsAuditResult,
    raw_case: dict[str, Any],
) -> None:
    raw_fields = raw_case.get("workload_fingerprint_incomplete_fields")
    if isinstance(raw_fields, list) and raw_fields:
        result.row_incomplete_workload_field_source_counts["stored"] += 1
        audit_incomplete_workload_field_items(result, raw_fields)
        return

    recomputed_fields = summary_only_incomplete_workload_fields(raw_case)
    if recomputed_fields:
        result.row_incomplete_workload_field_source_counts["summary_recomputed"] += 1
        audit_incomplete_workload_field_items(result, recomputed_fields)
        return

    result.row_incomplete_workload_field_source_counts["unspecified"] += 1
    result.row_incomplete_workload_field_counts["unspecified"] += 1


def audit_incomplete_workload_field_items(
    result: WorkloadDiagnosticsAuditResult,
    raw_fields: Iterable[object],
) -> None:
    for item in raw_fields:
        result.row_incomplete_workload_field_counts[safe_workload_shape_field(item)] += 1


def summary_only_incomplete_workload_fields(raw_case: dict[str, Any]) -> tuple[str, ...]:
    if not raw_case:
        return ()
    fields = compute_workload_fingerprint(raw_case, None).shape.get("incomplete_fields")
    if not isinstance(fields, list):
        return ()
    safe_fields = tuple(
        field for item in fields if (field := safe_workload_shape_field(item)) != "unspecified"
    )
    return tuple(sorted(set(safe_fields)))


def safe_workload_shape_field(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "unspecified"
    return (
        text
        if all(character.isalnum() or character == "_" for character in text)
        else "unspecified"
    )


def audit_workload_history(result: WorkloadDiagnosticsAuditResult, history: object) -> None:
    if history is None:
        result.workload_history_counts["missing"] += 1
        return
    enabled = "enabled" if getattr(history, "enabled", False) else "disabled"
    append_status = safe_token(getattr(history, "append_status", "unknown"))
    result.workload_history_counts[enabled] += 1
    result.workload_history_counts[f"append_{append_status}"] += 1
    loaded = int_value(getattr(history, "loaded_record_count", 0))
    result.workload_history_counts[f"loaded_{count_bucket(loaded)}"] += 1


def audit_workload_group(
    result: WorkloadDiagnosticsAuditResult,
    summary: dict[str, Any],
    group: Any,
    rows: tuple[Any, ...],
    *,
    action_outcome_metrics: dict[str, WorkloadOutcomeMetric],
    audit_action_outcome_feedback: bool,
) -> None:
    result.repeated_case_count += int_value(getattr(group, "member_count", 0))
    regression = safe_regression(getattr(group, "regression", "unknown"))
    baseline_count = int_value(getattr(group, "baseline_sample_count", 0))
    result.group_regression_counts[regression] += 1
    result.group_baseline_counts["available" if baseline_count > 0 else "missing"] += 1
    result.group_member_count_buckets[
        count_bucket(int_value(getattr(group, "member_count", 0)))
    ] += 1

    if len(rows) < int_value(getattr(group, "member_count", 0)):
        result.issue_counts["workload_group_row_gap"] += 1
    if regression in {"strong", "mild"} and baseline_count <= 0:
        result.issue_counts["regression_without_baseline"] += 1
    detail = present_workload_detail(
        summary,
        getattr(group, "fingerprint", ""),
        workload_outcome_metrics=action_outcome_metrics,
    )
    if detail is None:
        result.issue_counts["workload_detail_missing"] += 1
        return
    result.workload_detail_count += 1
    representative_count = len(detail.representatives)
    result.detail_representative_counts[count_bucket(representative_count)] += 1
    if representative_count <= 0:
        result.issue_counts["workload_representatives_missing"] += 1
    action_hint_count = len(detail.action_hints)
    result.detail_action_hint_counts[count_bucket(action_hint_count)] += 1
    required_recommendation_ids = workload_detail_required_recommendation_ids(detail)
    if audit_action_outcome_feedback:
        if required_recommendation_ids:
            metric = action_outcome_metrics.get(str(getattr(group, "fingerprint", "")))
            audit_workload_outcome_metric(
                result,
                metric,
            )
            audit_action_outcome_required_families(
                result,
                metric,
                required_recommendation_ids,
            )
            result.action_outcome_group_coverage_counts[
                required_family_outcome_bucket(metric, required_recommendation_ids)
            ] += 1
    for limitation in detail.limitations:
        result.detail_limitation_counts[classify_limitation(limitation)] += 1
    for hint in detail.action_hints:
        audit_action_hint(
            result,
            hint,
            metric=action_outcome_metrics.get(str(getattr(group, "fingerprint", ""))),
            audit_action_outcome_feedback=audit_action_outcome_feedback,
        )


def workload_detail_required_recommendation_ids(detail: Any) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                recommendation_id
                for hint in getattr(detail, "action_hints", ()) or ()
                if recommendation_id_allowed(
                    recommendation_id := str(getattr(hint, "recommendation_id", "") or "")
                )
            }
        )
    )


def audit_action_outcome_required_families(
    result: WorkloadDiagnosticsAuditResult,
    metric: WorkloadOutcomeMetric | None,
    recommendation_ids: Iterable[str],
) -> None:
    unmeasured_required_family = False
    for recommendation_id in recommendation_ids:
        family = safe_signal(recommendation_id)
        result.action_outcome_family_requirement_counts[f"{family}_required"] += 1
        if metric is None or metric.total_records <= 0:
            result.action_outcome_family_requirement_counts[f"{family}_missing"] += 1
            continue
        signal = workload_outcome_signal_for_recommendation(metric, recommendation_id)
        if signal.total_records <= 0:
            result.action_outcome_family_requirement_counts[f"{family}_missing"] += 1
            continue
        record_action_outcome_result_counts(result, signal)
        if not signal.min_sample_met:
            result.action_outcome_family_requirement_counts[f"{family}_sample_below_threshold"] += 1
            continue
        result.action_outcome_family_requirement_counts[f"{family}_sample_met"] += 1
        if measured_outcome_count(signal) > 0:
            result.action_outcome_family_requirement_counts[f"{family}_result_measured"] += 1
        else:
            result.action_outcome_family_requirement_counts[f"{family}_result_unmeasured"] += 1
            unmeasured_required_family = True
    if unmeasured_required_family:
        result.issue_counts["workload_action_outcome_result_unmeasured"] += 1


def record_action_outcome_result_counts(
    result: WorkloadDiagnosticsAuditResult,
    signal: Any,
) -> None:
    comparable_bucket = count_bucket(int_value(getattr(signal, "comparable_rerun_count", 0)))
    result.action_outcome_result_counts[
        f"required_family_comparable_reruns_{comparable_bucket}"
    ] += 1
    for outcome in TRACKED_ACTION_OUTCOMES:
        count = int_value(getattr(signal, f"{outcome}_count", 0))
        if count > 0:
            result.action_outcome_result_counts[f"required_family_{outcome}"] += count
    measured = measured_outcome_count(signal)
    if measured > 0:
        result.action_outcome_result_counts["required_family_measured_results"] += measured
    if signal.min_sample_met:
        result.action_outcome_result_counts[
            "required_family_sample_measured"
            if measured > 0
            else "required_family_sample_unmeasured"
        ] += 1


def measured_outcome_count(signal: Any) -> int:
    return sum(
        int_value(getattr(signal, f"{outcome}_count", 0)) for outcome in MEASURED_ACTION_OUTCOMES
    )


def audit_workload_outcome_metric(
    result: WorkloadDiagnosticsAuditResult,
    metric: WorkloadOutcomeMetric | None,
) -> None:
    if metric is None or metric.total_records <= 0:
        result.issue_counts["workload_action_outcome_feedback_missing"] += 1
        return
    result.action_outcome_family_counts[safe_signal(metric.family_signal.recommendation_id)] += 1
    result.action_outcome_family_counts[
        "family_sample_met"
        if metric.family_signal.min_sample_met
        else "family_sample_below_threshold"
    ] += 1
    result.action_outcome_verification_counts[
        f"workload_comparable_reruns_{count_bucket(metric.comparable_rerun_count)}"
    ] += 1
    result.action_outcome_verification_counts[
        f"family_comparable_reruns_{count_bucket(metric.family_signal.comparable_rerun_count)}"
    ] += 1
    if metric.unverified_applied_count > 0:
        result.action_outcome_verification_counts[
            f"workload_unverified_applied_{count_bucket(metric.unverified_applied_count)}"
        ] += 1
    if metric.family_signal.unverified_applied_count > 0:
        result.action_outcome_verification_counts[
            "family_unverified_applied_"
            f"{count_bucket(metric.family_signal.unverified_applied_count)}"
        ] += 1
    if not metric.family_signal.min_sample_met:
        result.issue_counts["workload_action_outcome_sample_below_threshold"] += 1
    if metric.applied_count + metric.not_applied_count <= 0:
        result.issue_counts["workload_action_outcome_no_apply_decision"] += 1


def update_action_outcome_gate_counts(
    result: WorkloadDiagnosticsAuditResult,
    audit_action_outcome_feedback: bool,
) -> None:
    result.action_outcome_gate_counts.clear()
    payload = action_outcome_gate_payload(
        result,
        audit_action_outcome_feedback=audit_action_outcome_feedback,
    )
    source = payload["source"]
    requirements = payload["requirements"]
    result.action_outcome_gate_counts[
        "action_outcomes_supplied"
        if source["action_outcomes_supplied"]
        else "action_outcomes_not_supplied"
    ] += 1
    result.action_outcome_gate_counts[
        "raw_free_passed" if source["raw_free_passed"] else "raw_free_failed"
    ] += 1
    result.action_outcome_gate_counts[
        "gate_evaluable" if payload["gate_evaluable"] else "gate_not_evaluable"
    ] += 1
    result.action_outcome_gate_counts[
        "gate_passed" if payload["gate_passed"] else "gate_failed"
    ] += 1
    for name in (
        "required_family_groups",
        "sample_met_family_groups",
        "missing_family_groups",
        "sample_below_threshold_family_groups",
        "measured_result_family_groups",
        "unmeasured_result_family_groups",
        "open_family_groups",
    ):
        value = int_value(requirements[name])
        if value > 0:
            result.action_outcome_gate_counts[name] += value


def audit_action_hint(
    result: WorkloadDiagnosticsAuditResult,
    hint: Any,
    *,
    metric: WorkloadOutcomeMetric | None,
    audit_action_outcome_feedback: bool,
) -> None:
    missing_fields = [
        field
        for field in (
            "where_to_look",
            "change_direction",
            "verification_metric",
            "verification",
        )
        if not str(getattr(hint, field, "") or "").strip()
    ]
    if missing_fields:
        result.issue_counts["workload_action_hint_incomplete"] += 1
    combined = " ".join(
        str(getattr(hint, field, "") or "")
        for field in ("change_direction", "verification_metric", "verification")
    )
    if not has_comparable_verification(combined):
        result.issue_counts["workload_action_hint_without_comparable_verification"] += 1
    if audit_action_outcome_feedback:
        result.detail_action_hint_outcome_counts[
            action_surface_outcome_bucket(
                result,
                metric,
                getattr(hint, "recommendation_id", ""),
                getattr(hint, "outcome_summary", ""),
            )
        ] += 1


def audit_action_queue_entry(
    result: WorkloadDiagnosticsAuditResult,
    entry: Any,
    *,
    action_outcome_metrics: dict[str, WorkloadOutcomeMetric],
    audit_action_outcome_feedback: bool,
) -> None:
    result.action_queue_signal_counts[safe_signal(getattr(entry, "signal", ""))] += 1
    combined = " ".join(
        str(getattr(entry, field, "") or "")
        for field in ("next_step", "review_anchor", "verification_metric", "verification")
    )
    has_verification = has_comparable_verification(combined)
    result.action_queue_verification_counts[
        "comparable_or_rerun" if has_verification else "missing_comparable"
    ] += 1
    if not has_verification:
        result.issue_counts["workload_action_queue_without_comparable_verification"] += 1
    if audit_action_outcome_feedback:
        metric = action_outcome_metrics.get(str(getattr(entry, "fingerprint", "")))
        result.action_queue_outcome_counts[
            action_surface_outcome_bucket(
                result,
                metric,
                getattr(entry, "recommendation_id", ""),
                getattr(entry, "outcome_summary", ""),
            )
        ] += 1


def action_surface_outcome_bucket(
    result: WorkloadDiagnosticsAuditResult,
    metric: WorkloadOutcomeMetric | None,
    recommendation_id: object,
    outcome_summary: object,
) -> str:
    recommendation_id_text = str(recommendation_id or "").strip()
    if not recommendation_id_allowed(recommendation_id_text):
        return outcome_summary_bucket(outcome_summary)
    if metric is None or metric.total_records <= 0:
        return "missing"
    signal = workload_outcome_signal_for_recommendation(metric, recommendation_id_text)
    if signal.total_records <= 0:
        result.issue_counts["workload_action_outcome_family_feedback_missing"] += 1
        return "missing"
    if signal.min_sample_met:
        if measured_outcome_count(signal) <= 0:
            result.issue_counts["workload_action_outcome_family_result_unmeasured"] += 1
            return "sample_unmeasured"
        return "sample_met"
    if signal.recommendation_id != metric.family_signal.recommendation_id:
        result.issue_counts["workload_action_outcome_family_sample_below_threshold"] += 1
    return "sample_below_threshold"


def required_family_outcome_bucket(
    metric: WorkloadOutcomeMetric | None,
    recommendation_ids: Iterable[str],
) -> str:
    if metric is None or metric.total_records <= 0:
        return "missing"
    saw_below_threshold = False
    saw_unmeasured = False
    for recommendation_id in recommendation_ids:
        signal = workload_outcome_signal_for_recommendation(metric, recommendation_id)
        if signal.total_records <= 0:
            return "missing"
        if not signal.min_sample_met:
            saw_below_threshold = True
            continue
        if measured_outcome_count(signal) <= 0:
            saw_unmeasured = True
    if saw_below_threshold:
        return "sample_below_threshold"
    if saw_unmeasured:
        return "sample_unmeasured"
    return "sample_met"


def add_readiness_issues(result: WorkloadDiagnosticsAuditResult) -> None:
    if (
        result.row_incomplete_workload_fingerprint_count > 0
        and result.row_repeated_workload_group_count <= 0
        and result.workload_group_count <= 0
    ):
        add_issue(
            result,
            "workload_fingerprints_incomplete",
            "strict workload calibration observed incomplete row fingerprints but no derived or materialized workload groups",
        )
    if result.row_repeated_workload_group_count > 0 and result.workload_group_count <= 0:
        add_issue(
            result,
            "workload_groups_missing_for_repeated_rows",
            "strict workload calibration observed repeated row fingerprints but no workload groups",
        )
    if result.workload_group_count <= 0:
        return
    if result.workload_history_counts.get("missing", 0) and workload_history_required(result):
        add_issue(
            result,
            "workload_history_missing",
            "strict workload calibration requires workload history status when baseline or regression claims are present",
        )
    for category in (
        "workload_group_row_gap",
        "regression_without_baseline",
        "workload_detail_missing",
        "workload_representatives_missing",
        "workload_action_hint_incomplete",
        "workload_action_hint_without_comparable_verification",
        "workload_action_queue_without_comparable_verification",
    ):
        count = result.issue_counts.get(category, 0)
        if count:
            add_issue(result, category, f"{category} observed in {count} workload group(s)")


def workload_history_required(result: WorkloadDiagnosticsAuditResult) -> bool:
    if result.group_baseline_counts.get("available", 0) > 0:
        return True
    return any(
        count > 0 for label, count in result.group_regression_counts.items() if label != "unknown"
    )


def add_workload_group_requirement_issue(result: WorkloadDiagnosticsAuditResult) -> None:
    if result.workload_group_count > 0:
        return
    add_issue(
        result,
        "workload_groups_missing",
        "representative workload calibration requires at least one repeated workload group",
    )


def add_action_outcome_readiness_issues(result: WorkloadDiagnosticsAuditResult) -> None:
    if result.workload_group_count <= 0:
        add_issue(
            result,
            "workload_groups_missing_for_action_outcomes",
            "strict action outcome calibration requires at least one repeated workload group",
        )
        return
    if result.action_outcome_source_counts.get("not_supplied", 0) and action_outcomes_required(
        result
    ):
        add_issue(
            result,
            "action_outcomes_not_supplied",
            "strict action outcome calibration requires an explicit local action-outcomes JSONL input",
        )
    for category in (
        "action_outcomes_empty",
        "action_outcomes_raw_like",
        *ACTION_OUTCOME_FEEDBACK_ISSUE_CATEGORIES,
    ):
        count = result.issue_counts.get(category, 0)
        if count:
            scope = "workload action surface(s)" if "_family_" in category else "workload group(s)"
            add_issue(result, category, f"{category} observed in {count} {scope}")


def action_outcomes_required(result: WorkloadDiagnosticsAuditResult) -> bool:
    return any(
        result.issue_counts.get(category, 0) > 0
        for category in ACTION_OUTCOME_FEEDBACK_ISSUE_CATEGORIES
    )


def add_issue(result: WorkloadDiagnosticsAuditResult, category: str, message: str) -> None:
    result.issues.append(WorkloadAuditIssue(category, message))


def has_comparable_verification(value: str) -> bool:
    text = value.strip().lower()
    has_comparison = any(term in text for term in COMPARABLE_COMPARISON_TERMS)
    has_rerun_context = any(term in text for term in COMPARABLE_RERUN_TERMS)
    return has_comparison and has_rerun_context


def outcome_summary_bucket(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text or text == "none":
        return "missing"
    if "feedback sample threshold met" in text:
        if not MEASURED_OUTCOME_SUMMARY_RE.search(text):
            return "sample_unmeasured"
        return "sample_met"
    if "feedback sample below threshold" in text:
        return "sample_below_threshold"
    return "recorded"


def classify_limitation(value: object) -> str:
    text = str(value or "").strip().lower()
    if "baseline" in text:
        return "baseline_missing"
    if "failed" in text or "collection" in text or "analysis" in text:
        return "status_incomplete"
    if "dominant primary" in text:
        return "primary_unknown"
    if "selected analyzed cases" in text:
        return "selected_cases_only"
    if "members are not available" in text:
        return "member_rows_missing"
    return "other"


def safe_signal(value: object) -> str:
    return safe_token(value, default="unknown_signal")


def safe_regression(value: object) -> str:
    token = safe_token(value)
    return token if token in REGRESSION_LABELS else "unknown"


def safe_token(value: object, *, default: str = "unknown") -> str:
    text = str(value or "").strip().lower()
    text = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in text)
    text = "_".join(part for part in text.split("_") if part)
    return text[:60] if text else default


def int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(float(str(value).strip())))
    except (TypeError, ValueError):
        return 0


def summary_json_payload(result: WorkloadDiagnosticsAuditResult) -> dict[str, object]:
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": "ok" if result.ok else "issues",
        "metrics": safe_count_dict(
            {
                "total_cases": result.total_cases,
                "rows": result.row_count,
                "workload_groups": result.workload_group_count,
                "details": result.workload_detail_count,
                "action_queue": result.action_queue_count,
                "row_workload_fingerprints": result.row_workload_fingerprint_count,
                "row_incomplete_workload_fingerprints": (
                    result.row_incomplete_workload_fingerprint_count
                ),
                "row_repeated_workload_groups": result.row_repeated_workload_group_count,
                "row_repeated_workload_cases": result.row_repeated_workload_case_count,
                "repeated_cases": result.repeated_case_count,
                "issues": len(result.issues),
            }.items(),
            include_zero=True,
        ),
        "issue_counts": safe_count_dict(Counter(issue.category for issue in result.issues).items()),
        "counters": summary_counter_payload(result),
        "action_outcome_gate": action_outcome_gate_payload(result),
        "action_outcome_requirements": action_outcome_requirement_payload(result),
    }


def action_outcome_gate_payload(
    result: WorkloadDiagnosticsAuditResult,
    *,
    audit_action_outcome_feedback: bool | None = None,
) -> dict[str, object]:
    counts = result.action_outcome_family_requirement_counts
    required = int_value(
        sum(count for key, count in counts.items() if str(key).endswith("_required"))
    )
    missing = int_value(
        sum(count for key, count in counts.items() if str(key).endswith("_missing"))
    )
    below_threshold = int_value(
        sum(count for key, count in counts.items() if str(key).endswith("_sample_below_threshold"))
    )
    sample_met = int_value(
        sum(count for key, count in counts.items() if str(key).endswith("_sample_met"))
    )
    measured_result = int_value(
        sum(count for key, count in counts.items() if str(key).endswith("_result_measured"))
    )
    unmeasured_result = int_value(
        sum(count for key, count in counts.items() if str(key).endswith("_result_unmeasured"))
    )
    open_groups = missing + below_threshold + unmeasured_result
    families_required = sum(
        1
        for recommendation_id in RECOMMENDATION_LABELS
        if int_value(counts.get(f"{safe_signal(recommendation_id)}_required", 0)) > 0
    )
    raw_free_passed = result.issue_counts.get("action_outcomes_raw_like", 0) <= 0
    action_outcomes_supplied = result.action_outcome_source_counts.get("supplied", 0) > 0
    gate_evaluable = required > 0
    if audit_action_outcome_feedback is None:
        audit_action_outcome_feedback = bool(result.action_outcome_source_counts) or gate_evaluable
    gate_passed = (
        gate_evaluable
        and audit_action_outcome_feedback
        and action_outcomes_supplied
        and raw_free_passed
        and open_groups == 0
        and sample_met >= required
        and measured_result >= required
    )
    return {
        "thresholds": {
            "min_comparable_reruns_per_group": result.action_outcome_min_applied,
            "accepted_verification_status": "comparable_rerun",
            "measured_result_outcomes": list(MEASURED_ACTION_OUTCOMES),
            "record_schema_version": ACTION_OUTCOME_SCHEMA_VERSION,
        },
        "source": {
            "action_outcomes_supplied": action_outcomes_supplied,
            "raw_free_passed": raw_free_passed,
        },
        "requirements": {
            "families_required": families_required,
            "required_family_groups": required,
            "sample_met_family_groups": sample_met,
            "missing_family_groups": missing,
            "sample_below_threshold_family_groups": below_threshold,
            "measured_result_family_groups": measured_result,
            "unmeasured_result_family_groups": unmeasured_result,
            "open_family_groups": open_groups,
        },
        "gate_evaluable": gate_evaluable,
        "gate_passed": gate_passed,
    }


def action_outcome_requirement_payload(
    result: WorkloadDiagnosticsAuditResult,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    counts = result.action_outcome_family_requirement_counts
    for recommendation_id in sorted(RECOMMENDATION_LABELS):
        family = safe_signal(recommendation_id)
        required = int_value(counts.get(f"{family}_required", 0))
        if required <= 0:
            continue
        missing = int_value(counts.get(f"{family}_missing", 0))
        below_threshold = int_value(counts.get(f"{family}_sample_below_threshold", 0))
        sample_met = int_value(counts.get(f"{family}_sample_met", 0))
        measured_result = int_value(counts.get(f"{family}_result_measured", 0))
        unmeasured_result = int_value(counts.get(f"{family}_result_unmeasured", 0))
        rows.append(
            {
                "recommendation_id": recommendation_id,
                "recommendation_label": safe_recommendation_label(recommendation_id),
                "required_groups": required,
                "sample_met_groups": sample_met,
                "missing_groups": missing,
                "sample_below_threshold_groups": below_threshold,
                "measured_result_groups": measured_result,
                "unmeasured_result_groups": unmeasured_result,
                "open_groups": missing + below_threshold + unmeasured_result,
                "min_comparable_reruns_per_group": result.action_outcome_min_applied,
                "accepted_verification_status": "comparable_rerun",
                "measured_result_outcomes": list(MEASURED_ACTION_OUTCOMES),
                "record_schema_version": ACTION_OUTCOME_SCHEMA_VERSION,
            }
        )
    return rows


def summary_counter_payload(result: WorkloadDiagnosticsAuditResult) -> dict[str, object]:
    counters = {
        "row_incomplete_workload_field_counts": result.row_incomplete_workload_field_counts,
        "row_incomplete_workload_field_source_counts": (
            result.row_incomplete_workload_field_source_counts
        ),
        "workload_history_counts": result.workload_history_counts,
        "group_regression_counts": result.group_regression_counts,
        "group_baseline_counts": result.group_baseline_counts,
        "group_member_count_buckets": result.group_member_count_buckets,
        "detail_representative_counts": result.detail_representative_counts,
        "detail_action_hint_counts": result.detail_action_hint_counts,
        "detail_limitation_counts": result.detail_limitation_counts,
        "action_queue_signal_counts": result.action_queue_signal_counts,
        "action_queue_verification_counts": result.action_queue_verification_counts,
        "action_outcome_source_counts": result.action_outcome_source_counts,
        "action_outcome_group_coverage_counts": result.action_outcome_group_coverage_counts,
        "action_outcome_family_counts": result.action_outcome_family_counts,
        "action_outcome_family_requirement_counts": (
            result.action_outcome_family_requirement_counts
        ),
        "action_outcome_gate_counts": result.action_outcome_gate_counts,
        "action_outcome_verification_counts": result.action_outcome_verification_counts,
        "action_outcome_result_counts": result.action_outcome_result_counts,
        "action_queue_outcome_counts": result.action_queue_outcome_counts,
        "detail_action_hint_outcome_counts": result.detail_action_hint_outcome_counts,
        "readiness_gap_counts": result.issue_counts,
    }
    payload: dict[str, object] = {}
    for name, counter in counters.items():
        safe_name = safe_summary_key(name)
        values = safe_count_dict(counter.items())
        if safe_name and values:
            payload[safe_name] = values
    return payload


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
    return safe_token(text, default="")


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
    result: WorkloadDiagnosticsAuditResult,
    path: Path,
    *,
    input_paths: Iterable[Path | None],
) -> None:
    if any(input_path is not None and same_path(path, input_path) for input_path in input_paths):
        raise WorkloadAuditOutputError("summary JSON output must not overwrite input artifacts")
    try:
        path.write_text(
            json.dumps(summary_json_payload(result), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise WorkloadAuditOutputError("cannot write summary JSON") from exc


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=False) == right.resolve(strict=False)
    except OSError:
        return left.absolute() == right.absolute()


def count_bucket(count: int) -> str:
    if count <= 0:
        return "0"
    if count == 1:
        return "1"
    if count <= 3:
        return "2_3"
    if count <= 5:
        return "4_5"
    return "6_plus"


def print_counter(title: str, counter: Counter[str], *, out: TextIO, limit: int) -> None:
    print(f"{title}:", file=out)
    if not counter:
        print("  <none>", file=out)
        return
    for key, count in counter.most_common(limit):
        print(f"  {key}: {count}", file=out)


def print_result(
    result: WorkloadDiagnosticsAuditResult,
    *,
    out: TextIO = sys.stdout,
    limit: int = 12,
) -> None:
    print(f"Summary: {result.summary_name}", file=out)
    print(
        "Cases: "
        f"total={result.total_cases}, rows={result.row_count}, "
        f"workload_groups={result.workload_group_count}, "
        f"details={result.workload_detail_count}, "
        f"action_queue={result.action_queue_count}",
        file=out,
    )
    print(
        "Row workload fingerprints: "
        f"known_cases={result.row_workload_fingerprint_count}, "
        f"incomplete_cases={result.row_incomplete_workload_fingerprint_count}, "
        f"repeated_groups={result.row_repeated_workload_group_count}, "
        f"repeated_cases={result.row_repeated_workload_case_count}",
        file=out,
    )
    print_counter(
        "Incomplete workload fields",
        result.row_incomplete_workload_field_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Incomplete workload field sources",
        result.row_incomplete_workload_field_source_counts,
        out=out,
        limit=limit,
    )
    print_counter("Workload history", result.workload_history_counts, out=out, limit=limit)
    print_counter("Group regressions", result.group_regression_counts, out=out, limit=limit)
    print_counter("Group baselines", result.group_baseline_counts, out=out, limit=limit)
    print_counter("Group member counts", result.group_member_count_buckets, out=out, limit=limit)
    print_counter(
        "Detail representatives", result.detail_representative_counts, out=out, limit=limit
    )
    print_counter("Detail action hints", result.detail_action_hint_counts, out=out, limit=limit)
    print_counter("Detail limitations", result.detail_limitation_counts, out=out, limit=limit)
    print_counter("Action queue signals", result.action_queue_signal_counts, out=out, limit=limit)
    print_counter(
        "Action queue verification",
        result.action_queue_verification_counts,
        out=out,
        limit=limit,
    )
    if has_action_outcome_counters(result):
        print_counter(
            "Action outcome source",
            result.action_outcome_source_counts,
            out=out,
            limit=limit,
        )
        print_counter(
            "Action outcome group coverage",
            result.action_outcome_group_coverage_counts,
            out=out,
            limit=limit,
        )
        print_counter(
            "Action outcome family signals",
            result.action_outcome_family_counts,
            out=out,
            limit=limit,
        )
        print_counter(
            "Action outcome family requirements",
            result.action_outcome_family_requirement_counts,
            out=out,
            limit=limit,
        )
        print_action_outcome_requirements(result, out=out, limit=limit)
        print_counter(
            "Action outcome verification",
            result.action_outcome_verification_counts,
            out=out,
            limit=limit,
        )
        print_counter(
            "Action outcome results",
            result.action_outcome_result_counts,
            out=out,
            limit=limit,
        )
        print_counter(
            "Action queue outcomes",
            result.action_queue_outcome_counts,
            out=out,
            limit=limit,
        )
        print_counter(
            "Detail action hint outcomes",
            result.detail_action_hint_outcome_counts,
            out=out,
            limit=limit,
        )
    print_counter("Readiness gap counters", result.issue_counts, out=out, limit=limit)
    print("Issues:", file=out)
    if not result.issues:
        print("  none", file=out)
        return
    for issue in result.issues[:limit]:
        print(f"  {issue.category}: {issue.message}", file=out)


def print_action_outcome_requirements(
    result: WorkloadDiagnosticsAuditResult,
    *,
    out: TextIO,
    limit: int,
) -> None:
    rows = action_outcome_requirement_payload(result)
    if not rows:
        return
    print("Action outcome required feedback:", file=out)
    for row in rows[:limit]:
        print(
            "  "
            f"{row['recommendation_id']}: "
            f"required_groups={row['required_groups']}, "
            f"sample_met_groups={row['sample_met_groups']}, "
            f"missing_groups={row['missing_groups']}, "
            f"sample_below_threshold_groups={row['sample_below_threshold_groups']}, "
            f"measured_result_groups={row['measured_result_groups']}, "
            f"unmeasured_result_groups={row['unmeasured_result_groups']}, "
            f"open_groups={row['open_groups']}, "
            "verification_status=comparable_rerun, "
            f"min_comparable_reruns_per_group={row['min_comparable_reruns_per_group']}",
            file=out,
        )


def has_action_outcome_counters(result: WorkloadDiagnosticsAuditResult) -> bool:
    return any(
        (
            result.action_outcome_source_counts,
            result.action_outcome_group_coverage_counts,
            result.action_outcome_family_counts,
            result.action_outcome_family_requirement_counts,
            result.action_outcome_verification_counts,
            result.action_outcome_result_counts,
            result.action_queue_outcome_counts,
            result.detail_action_hint_outcome_counts,
        )
    )


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path, help="Path to batch_summary.json")
    parser.add_argument("--limit", type=int, default=12, help="Rows to print per section")
    parser.add_argument(
        "--fail-on-workload-readiness-gaps",
        action="store_true",
        help=(
            "Return non-zero when repeated workload diagnostics lack history, detail rows, "
            "representatives, baselines for regressions, or compare-plus-rerun/scan "
            "verification guidance."
        ),
    )
    parser.add_argument(
        "--require-workload-groups",
        action="store_true",
        help="Return non-zero when representative workload calibration has no repeated groups.",
    )
    parser.add_argument(
        "--action-outcomes",
        type=Path,
        help="Optional local action_outcomes.jsonl used only for aggregate workload outcome calibration.",
    )
    parser.add_argument(
        "--fail-on-action-outcome-readiness-gaps",
        action="store_true",
        help=(
            "Return non-zero when repeated workload action queues/details lack explicit "
            "local action-outcome feedback or enough measured comparable-rerun samples for "
            "outcome calibration."
        ),
    )
    parser.add_argument(
        "--action-outcome-min-applied",
        type=int,
        default=DEFAULT_METRIC_MIN_APPLIED,
        help="Applied-record sample threshold for action outcome summaries.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Write a raw-free machine-readable workload diagnostics audit summary JSON.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = audit_summary(
            args.summary,
            fail_on_workload_readiness_gaps=args.fail_on_workload_readiness_gaps,
            require_workload_groups=args.require_workload_groups,
            action_outcomes_path=args.action_outcomes,
            fail_on_action_outcome_readiness_gaps=args.fail_on_action_outcome_readiness_gaps,
            action_outcome_min_applied=args.action_outcome_min_applied,
        )
    except WorkloadAuditInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_result(result, limit=args.limit)
    if args.summary_json is not None:
        try:
            write_summary_json(
                result,
                args.summary_json,
                input_paths=(args.summary, args.action_outcomes),
            )
        except WorkloadAuditOutputError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    return 1 if not result.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
