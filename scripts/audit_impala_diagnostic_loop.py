#!/usr/bin/env python3
"""Run strict raw-free Impala diagnostic-loop audits for one Recent summary."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, TextIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_optimizer_funnel import audit_summary as audit_optimizer_summary  # noqa: E402
from scripts.audit_profile_evidence_gates import audit_summary as audit_profile_summary  # noqa: E402
from scripts.audit_recent_details import audit_summary as audit_details_summary  # noqa: E402
from scripts.audit_stats_diagnostics import audit_summary as audit_stats_summary  # noqa: E402
from scripts.audit_workload_diagnostics import audit_summary as audit_workload_summary  # noqa: E402
from scripts.audit_impala_coverage_gaps import (  # noqa: E402
    audit_summaries as audit_coverage_summaries,
    safe_unknown_reason_count_dict,
    safe_unknown_resolution_count_dict,
)
from query_doctor.analyzer.unknown_primary_taxonomy import unknown_category_counts  # noqa: E402
from query_doctor.report.safety_validation import contains_raw_sql_like_text  # noqa: E402
from query_doctor.report.language_contract import SUPPORTED_REPORT_LANGUAGES  # noqa: E402
from query_doctor.report.trusted_text import validate_report_for_mode  # noqa: E402
from query_doctor.safety import redaction  # noqa: E402
from query_doctor.web.case_files import read_case_relative_text  # noqa: E402
from query_doctor.web.command_builders import (  # noqa: E402
    REPORT_VARIANT_LLM,
    REPORT_VARIANT_PYTHON,
    report_artifacts_for_variant,
)
from query_doctor.web.jobs import WebJobStore  # noqa: E402
from query_doctor.web.models import WebSettings  # noqa: E402
from query_doctor.web.trusted_artifacts import (  # noqa: E402
    load_case_analyzer_facts_text,
    load_batch_case_report_state,
    load_batch_case_trusted_report_artifact,
    load_optimized_query_state,
    load_validated_optimized_query,
    load_validated_optimizer_recommendations,
    resolve_batch_case_report_dir,
)


DETAIL_ISSUE_CATEGORIES = (
    ("forbidden browser text leaked", "forbidden_browser_text"),
    ("details rendering failed", "details_render_failed"),
    ("case_index is missing", "case_index_missing"),
    ("problem case has no action card", "problem_without_action_card"),
    ("problem case has no score reasons", "problem_without_score_reasons"),
    ("has no why text", "action_without_why"),
    ("has no change direction", "action_without_change_direction"),
    ("has no verification", "action_without_verification"),
    ("verification lacks comparable rerun guidance", "action_without_comparable_rerun"),
    ("stats action lacks structured metadata detail", "stats_action_missing_detail"),
)
REPORT_VARIANTS = (REPORT_VARIANT_PYTHON, REPORT_VARIANT_LLM)
TRUSTED_REPORT_FORBIDDEN_DISPLAY_FRAGMENTS = (
    "analysis_facts.md",
    "case_dir",
    "profile_digest.md",
    "query_metadata.json",
)
URL_RE = re.compile(r"\bhttps?://", re.IGNORECASE)
LOCAL_PATH_RE = re.compile(r"(?i)(?:^|[\s:(])(?:/users/|/private/|/tmp/|[a-z]:\\)")
SUMMARY_KEY_LOCAL_PATH_RE = re.compile(r"(?i)(?:/users/|/private/|/tmp/|[a-z]:\\)")


@dataclass(frozen=True)
class ComponentAudit:
    name: str
    ok: bool
    metrics: tuple[tuple[str, str], ...]
    issue_counts: Counter[str] = field(default_factory=Counter)
    breakdowns: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = field(default_factory=tuple)


@dataclass
class DiagnosticLoopAuditResult:
    summary_name: str
    components: tuple[ComponentAudit, ...]

    @property
    def ok(self) -> bool:
        return all(component.ok for component in self.components)


class LoopAuditInputError(RuntimeError):
    """Raised when the aggregate loop audit cannot load its primary input."""


class LoopAuditOutputError(RuntimeError):
    """Raised when the aggregate loop audit cannot write a safe output."""


@dataclass(frozen=True)
class TrustedReportIssue:
    category: str
    message: str


@dataclass
class TrustedReportAuditResult:
    summary_name: str
    total_cases: int
    audited_cases: int = 0
    trusted_report_count: int = 0
    revalidated_report_count: int = 0
    revalidation_failure_count: int = 0
    partial_untrusted_count: int = 0
    state_status_counts: Counter[str] = field(default_factory=Counter)
    trusted_variant_counts: Counter[str] = field(default_factory=Counter)
    revalidation_status_counts: Counter[str] = field(default_factory=Counter)
    issues: list[TrustedReportIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class OptimizerArtifactIssue:
    category: str
    message: str


@dataclass
class OptimizerArtifactAuditResult:
    summary_name: str
    total_cases: int
    audited_cases: int = 0
    trusted_artifact_count: int = 0
    trusted_draft_count: int = 0
    trusted_recommendation_count: int = 0
    trusted_no_rewrite_count: int = 0
    partial_untrusted_count: int = 0
    state_status_counts: Counter[str] = field(default_factory=Counter)
    output_kind_counts: Counter[str] = field(default_factory=Counter)
    artifact_readability_counts: Counter[str] = field(default_factory=Counter)
    issues: list[OptimizerArtifactIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def audit_summary(
    summary_path: Path,
    *,
    action_outcomes_path: Path | None = None,
    require_action_outcomes: bool = False,
    require_workload_groups: bool = False,
    require_direct_source_readiness: bool = False,
    recompute_optimizer_support: bool = True,
    use_current_classifier_primary: bool = False,
    max_unknown_primary_rate: float = 30.0,
    min_medium_primary_rate: float = 70.0,
) -> DiagnosticLoopAuditResult:
    try:
        resolved_summary = summary_path.resolve(strict=True)
    except OSError as exc:
        raise LoopAuditInputError("batch summary is not readable") from exc

    components = (
        run_component(
            "details",
            lambda: audit_details_summary(
                resolved_summary,
                fail_on_stats_detail_gaps=True,
                fail_on_comparable_rerun_gaps=True,
            ),
            metrics=details_metrics,
            breakdowns=details_breakdowns,
        ),
        run_component(
            "trusted_reports",
            lambda: audit_trusted_report_summary(resolved_summary),
            metrics=trusted_report_metrics,
            breakdowns=trusted_report_breakdowns,
        ),
        run_component(
            "optimizer_artifacts",
            lambda: audit_optimizer_artifact_summary(resolved_summary),
            metrics=optimizer_artifact_metrics,
            breakdowns=optimizer_artifact_breakdowns,
        ),
        run_component(
            "profile_evidence",
            lambda: audit_profile_summary(resolved_summary),
            metrics=profile_metrics,
            breakdowns=profile_breakdowns,
        ),
        run_component(
            "diagnostic_coverage",
            lambda: audit_coverage_summaries(
                (resolved_summary,),
                fail_on_diagnostic_coverage_gaps=True,
                fail_on_direct_source_readiness_gaps=require_direct_source_readiness,
                use_current_classifier_primary=use_current_classifier_primary,
                max_unknown_primary_rate=max_unknown_primary_rate,
                min_medium_primary_rate=min_medium_primary_rate,
            ),
            metrics=coverage_metrics,
            breakdowns=coverage_breakdowns,
        ),
        run_component(
            "workload",
            lambda: audit_workload_summary(
                resolved_summary,
                fail_on_workload_readiness_gaps=True,
                require_workload_groups=require_workload_groups,
                action_outcomes_path=action_outcomes_path,
                fail_on_action_outcome_readiness_gaps=require_action_outcomes,
            ),
            metrics=workload_metrics,
            breakdowns=workload_breakdowns,
        ),
        run_component(
            "stats",
            lambda: audit_stats_summary(
                resolved_summary,
                fail_on_stats_readiness_gaps=True,
            ),
            metrics=stats_metrics,
            breakdowns=stats_breakdowns,
        ),
        run_component(
            "optimizer",
            lambda: audit_optimizer_summary(
                resolved_summary,
                recompute_support=recompute_optimizer_support,
                fail_on_repeated_no_recipe_readiness_gaps=True,
            ),
            metrics=optimizer_metrics,
            breakdowns=optimizer_breakdowns,
        ),
    )
    return DiagnosticLoopAuditResult(
        summary_name=resolved_summary.name,
        components=components,
    )


def audit_trusted_report_summary(summary_path: Path) -> TrustedReportAuditResult:
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LoopAuditInputError("batch summary is not readable") from exc
    cases = payload.get("cases")
    if not isinstance(cases, list):
        cases = []
    result = TrustedReportAuditResult(summary_name=summary_path.name, total_cases=len(cases))
    settings = WebSettings(config=Path("query_doctor_audit_config"), batch_summary=summary_path)
    job_store = WebJobStore()

    for case in cases:
        if not isinstance(case, dict):
            continue
        result.audited_cases += 1
        case_id = safe_case_id(case)
        for variant in REPORT_VARIANTS:
            state = load_batch_case_report_state(
                settings,
                case_id,
                case,
                job_store,
                report_variant=variant,
            )
            status = safe_token(state.get("status"))
            result.state_status_counts[counter_key(variant, status or "missing")] += 1
            if status == "partial_untrusted":
                result.partial_untrusted_count += 1
                result.issues.append(
                    TrustedReportIssue(
                        category="partial_untrusted_report",
                        message="case has partial or untrusted report output",
                    )
                )
            if state.get("trusted"):
                artifact = load_batch_case_trusted_report_artifact(
                    settings,
                    case_id,
                    case,
                    report_variant=variant,
                )
                if artifact is None:
                    result.issues.append(
                        TrustedReportIssue(
                            category="trusted_report_unreadable",
                            message="trusted report marker exists but report artifact is unreadable",
                        )
                    )
                    continue
                result.trusted_report_count += 1
                result.trusted_variant_counts[safe_token(variant)] += 1
                result.revalidated_report_count += 1
                if not trusted_report_passes_current_validation(settings, case, variant):
                    result.revalidation_failure_count += 1
                    result.revalidation_status_counts[counter_key(variant, "failed")] += 1
                    result.issues.append(
                        TrustedReportIssue(
                            category="trusted_report_revalidation_failed",
                            message="trusted report no longer passes current strict validation",
                        )
                    )
                else:
                    result.revalidation_status_counts[counter_key(variant, "passed")] += 1
                if trusted_report_has_display_leak(artifact.text):
                    result.issues.append(
                        TrustedReportIssue(
                            category="trusted_report_display_leak",
                            message="trusted report display text contains forbidden browser-visible data",
                        )
                    )
    return result


def audit_optimizer_artifact_summary(summary_path: Path) -> OptimizerArtifactAuditResult:
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LoopAuditInputError("batch summary is not readable") from exc
    cases = payload.get("cases")
    if not isinstance(cases, list):
        cases = []
    result = OptimizerArtifactAuditResult(summary_name=summary_path.name, total_cases=len(cases))
    settings = WebSettings(config=Path("query_doctor_audit_config"), batch_summary=summary_path)
    job_store = WebJobStore()

    for case in cases:
        if not isinstance(case, dict):
            continue
        result.audited_cases += 1
        case_id = safe_case_id(case)
        artifact_dir = resolve_batch_case_report_dir(settings, case)
        state = load_optimized_query_state(artifact_dir, job_store, batch_case_id=case_id)
        status = safe_token(state.get("status"))
        result.state_status_counts[status or "missing"] += 1
        if status == "partial_untrusted":
            result.partial_untrusted_count += 1
            result.issues.append(
                OptimizerArtifactIssue(
                    category="partial_untrusted_optimizer_artifact",
                    message="case has partial or untrusted optimizer output",
                )
            )
        if state.get("trusted"):
            result.trusted_artifact_count += 1
            output_kind = safe_token(state.get("output_kind")) or "sql_draft"
            result.output_kind_counts[output_kind] += 1
            if output_kind == "no_rewrite":
                result.trusted_no_rewrite_count += 1
            elif output_kind == "recommendations_only":
                result.trusted_recommendation_count += 1
            else:
                result.trusted_draft_count += 1
            readable = trusted_optimizer_artifact_is_readable(artifact_dir, state)
            result.artifact_readability_counts["readable" if readable else "unreadable"] += 1
            if not readable:
                result.issues.append(
                    OptimizerArtifactIssue(
                        category="trusted_optimizer_artifact_unreadable",
                        message="trusted optimizer marker exists but output is unreadable",
                    )
                )
    return result


def trusted_optimizer_artifact_is_readable(
    artifact_dir: Path | None,
    state: dict[str, object],
) -> bool:
    if artifact_dir is None:
        return False
    output_kind = safe_token(state.get("output_kind")) or "sql_draft"
    if output_kind == "no_rewrite":
        return load_validated_optimizer_recommendations(artifact_dir) is not None
    if output_kind == "recommendations_only":
        return load_validated_optimizer_recommendations(artifact_dir) is not None
    return load_validated_optimized_query(artifact_dir) is not None


def trusted_report_passes_current_validation(
    settings: WebSettings,
    case: dict[str, object],
    report_variant: str,
) -> bool:
    artifact_dir = resolve_batch_case_report_dir(settings, case)
    if artifact_dir is None:
        return False
    report_name, _partial_name, _marker_name = report_artifacts_for_variant(report_variant)
    report_text = read_case_relative_text(artifact_dir, report_name)
    facts_text = load_case_analyzer_facts_text(artifact_dir)
    if report_text is None or facts_text is None:
        return False
    return trusted_report_errors_for_supported_languages(report_text, facts_text) == []


def trusted_report_errors_for_supported_languages(report_text: str, facts_text: str) -> list[str]:
    all_errors: list[str] = []
    for language in SUPPORTED_REPORT_LANGUAGES:
        errors = validate_report_for_mode(
            report_text,
            facts_text=facts_text,
            validation_mode="strict",
            language=language,
        )
        if not errors:
            return []
        all_errors.extend(errors)
    return all_errors


def safe_case_id(case: dict[str, object]) -> str:
    for key in ("case_id", "case_index", "query_id"):
        token = safe_token(case.get(key))
        if token:
            return token
    return "case"


def trusted_report_has_display_leak(text: str) -> bool:
    normalized = text.lower()
    if LOCAL_PATH_RE.search(text):
        return True
    return any(fragment in normalized for fragment in TRUSTED_REPORT_FORBIDDEN_DISPLAY_FRAGMENTS)


def run_component(
    name: str,
    audit: Callable[[], Any],
    *,
    metrics: Callable[[Any], tuple[tuple[str, str], ...]],
    breakdowns: Callable[[Any], tuple[tuple[str, tuple[tuple[str, str], ...]], ...]] | None = None,
) -> ComponentAudit:
    try:
        result = audit()
    except Exception:
        return ComponentAudit(
            name=name,
            ok=False,
            metrics=(("status", "component_error"),),
            issue_counts=Counter({"component_error": 1}),
        )
    issue_counts = component_issue_counts(result)
    return ComponentAudit(
        name=name,
        ok=bool(getattr(result, "ok", False)),
        metrics=metrics(result),
        issue_counts=issue_counts,
        breakdowns=breakdowns(result) if breakdowns is not None else (),
    )


def component_issue_counts(result: Any) -> Counter[str]:
    issues = getattr(result, "issues", ())
    counter: Counter[str] = Counter()
    for issue in issues or ():
        counter[issue_category(issue)] += 1
    if not counter and int_value(getattr(result, "analysis_error_count", 0)) > 0:
        counter["analysis_error"] += int_value(getattr(result, "analysis_error_count", 0))
    return counter


def issue_category(issue: Any) -> str:
    category = safe_token(getattr(issue, "category", ""))
    if category:
        return category
    message = str(getattr(issue, "message", "") or "").strip().lower()
    for fragment, detail_category in DETAIL_ISSUE_CATEGORIES:
        if fragment in message:
            return detail_category
    return "component_issue"


def details_metrics(result: Any) -> tuple[tuple[str, str], ...]:
    return metric_pairs(
        total_cases=getattr(result, "total_cases", 0),
        audited_cases=getattr(result, "audited_cases", 0),
        issues=len(getattr(result, "issues", ()) or ()),
    )


def details_breakdowns(result: Any) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    return breakdown_pairs(
        severity_counts=getattr(result, "severity_counts", {}),
        metadata_counts=getattr(result, "metadata_counts", {}),
        title_counts=getattr(result, "title_counts", {}),
        action_counts=getattr(result, "action_counts", {}),
        stats_detail_counts=getattr(result, "stats_detail_counts", {}),
        verification_counts=getattr(result, "verification_counts", {}),
        optimizer_counts=getattr(result, "optimizer_counts", {}),
        report_counts=getattr(result, "report_counts", {}),
    )


def trusted_report_metrics(result: Any) -> tuple[tuple[str, str], ...]:
    return metric_pairs(
        total_cases=getattr(result, "total_cases", 0),
        audited_cases=getattr(result, "audited_cases", 0),
        trusted_reports=getattr(result, "trusted_report_count", 0),
        revalidated_reports=getattr(result, "revalidated_report_count", 0),
        revalidation_failures=getattr(result, "revalidation_failure_count", 0),
        partial_untrusted=getattr(result, "partial_untrusted_count", 0),
        issues=len(getattr(result, "issues", ()) or ()),
    )


def trusted_report_breakdowns(result: Any) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    return breakdown_pairs(
        state_status_counts=getattr(result, "state_status_counts", {}),
        trusted_variant_counts=getattr(result, "trusted_variant_counts", {}),
        revalidation_status_counts=getattr(result, "revalidation_status_counts", {}),
    )


def optimizer_artifact_metrics(result: Any) -> tuple[tuple[str, str], ...]:
    return metric_pairs(
        total_cases=getattr(result, "total_cases", 0),
        audited_cases=getattr(result, "audited_cases", 0),
        trusted_artifacts=getattr(result, "trusted_artifact_count", 0),
        trusted_drafts=getattr(result, "trusted_draft_count", 0),
        trusted_recommendations=getattr(result, "trusted_recommendation_count", 0),
        trusted_no_rewrite=getattr(result, "trusted_no_rewrite_count", 0),
        partial_untrusted=getattr(result, "partial_untrusted_count", 0),
        issues=len(getattr(result, "issues", ()) or ()),
    )


def optimizer_artifact_breakdowns(
    result: Any,
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    return breakdown_pairs(
        state_status_counts=getattr(result, "state_status_counts", {}),
        output_kind_counts=getattr(result, "output_kind_counts", {}),
        artifact_readability_counts=getattr(result, "artifact_readability_counts", {}),
    )


def profile_metrics(result: Any) -> tuple[tuple[str, str], ...]:
    return metric_pairs(
        total_cases=getattr(result, "total_cases", 0),
        analyzed_cases=getattr(result, "analyzed_cases", 0),
        missing_analysis=getattr(result, "missing_analysis_count", 0),
        analysis_errors=getattr(result, "analysis_error_count", 0),
        issues=len(getattr(result, "issues", ()) or ()),
    )


def profile_breakdowns(result: Any) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    return breakdown_pairs(
        severity_counts=getattr(result, "severity_counts", {}),
        primary_counts=getattr(result, "primary_counts", {}),
        primary_confidence_counts=getattr(result, "primary_confidence_counts", {}),
        profile_dialect_counts=getattr(result, "profile_dialect_counts", {}),
        profile_policy_counts=getattr(result, "profile_policy_counts", {}),
        profile_counter_registry_counts=getattr(
            result,
            "profile_counter_registry_counts",
            {},
        ),
        evidence_quality_counts=getattr(result, "evidence_quality_counts", {}),
        client_fetch_counts=getattr(result, "client_fetch_counts", {}),
        admission_counts=getattr(result, "admission_counts", {}),
        memory_pressure_counts=getattr(result, "memory_pressure_counts", {}),
        backend_tail_counts=getattr(result, "backend_tail_counts", {}),
        scan_skew_counts=getattr(result, "scan_skew_counts", {}),
        data_movement_counts=getattr(result, "data_movement_counts", {}),
        runtime_filter_counts=getattr(result, "runtime_filter_counts", {}),
        storage_context_counts=getattr(result, "storage_context_counts", {}),
        resource_trace_counts=getattr(result, "resource_trace_counts", {}),
        primary_classifier_drift_counts=getattr(
            result,
            "primary_classifier_drift_counts",
            {},
        ),
    )


def coverage_metrics(result: Any) -> tuple[tuple[str, str], ...]:
    return metric_pairs(
        total_cases=getattr(result, "total_cases", 0),
        analyzed_cases=getattr(result, "analyzed_cases", 0),
        missing_analysis=getattr(result, "missing_analysis_count", 0),
        direct_impala_cases=getattr(result, "direct_impala_case_count", 0),
        issues=len(getattr(result, "issues", ()) or ()),
    )


def coverage_breakdowns(result: Any) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    primary_counts = getattr(result, "primary_counts", {})
    unknown_primary_cases = 0
    if hasattr(primary_counts, "get"):
        unknown_primary_cases = int_value(primary_counts.get("unknown", 0))
    unknown_primary_reason_counts = Counter(
        safe_unknown_reason_count_dict(getattr(result, "unknown_primary_reason_counts", {}))
    )
    strict_unknown_primary_reason_counts = Counter(
        safe_unknown_reason_count_dict(
            getattr(
                result,
                "strict_unknown_primary_reason_counts",
                {},
            )
        )
    )
    unknown_primary_category_counts = unknown_category_counts(
        unknown_primary_reason_counts,
        unknown_primary_cases=unknown_primary_cases,
    )
    strict_unknown_primary_category_counts = unknown_category_counts(
        strict_unknown_primary_reason_counts,
        unknown_primary_cases=int_value(getattr(result, "strict_unknown_primary_count", 0)),
    )
    return breakdown_pairs(
        primary_counts=primary_counts,
        primary_confidence_counts=getattr(result, "primary_confidence_counts", {}),
        primary_classifier_drift_counts=getattr(result, "primary_classifier_drift_counts", {}),
        strict_primary_out_of_scope_counts=getattr(
            result,
            "strict_primary_out_of_scope_counts",
            {},
        ),
        strict_unknown_primary_reason_counts=strict_unknown_primary_reason_counts,
        source_compatibility_counts=getattr(result, "source_compatibility_counts", {}),
        optional_source_counts=getattr(result, "optional_source_counts", {}),
        source_status_counts=getattr(result, "source_status_counts", {}),
        direct_discovery_counts=getattr(result, "direct_discovery_counts", {}),
        direct_source_readiness_counts=getattr(result, "direct_source_readiness_counts", {}),
        direct_source_readiness_gap_counts=getattr(
            result,
            "direct_source_readiness_gap_counts",
            {},
        ),
        evidence_quality_counts=getattr(result, "evidence_quality_counts", {}),
        unknown_primary_reason_counts=unknown_primary_reason_counts,
        unknown_primary_category_counts=unknown_primary_category_counts,
        strict_unknown_primary_category_counts=strict_unknown_primary_category_counts,
        unknown_primary_resolution_counts=safe_unknown_resolution_count_dict(
            getattr(result, "unknown_primary_resolution_counts", {})
        ),
        storage_unknown_reason_counts=getattr(result, "storage_unknown_reason_counts", {}),
        scan_skew_supporting_reason_counts=getattr(
            result,
            "scan_skew_supporting_reason_counts",
            {},
        ),
        data_movement_supporting_reason_counts=getattr(
            result,
            "data_movement_supporting_reason_counts",
            {},
        ),
        data_movement_calibration_signal_counts=getattr(
            result,
            "data_movement_calibration_signal_counts",
            {},
        ),
        runtime_filter_calibration_signal_counts=getattr(
            result,
            "runtime_filter_calibration_signal_counts",
            {},
        ),
        gap_counts=getattr(result, "gap_counts", {}),
        opportunity_counts=getattr(result, "opportunity_counts", {}),
    )


def workload_metrics(result: Any) -> tuple[tuple[str, str], ...]:
    return metric_pairs(
        total_cases=getattr(result, "total_cases", 0),
        workload_groups=getattr(result, "workload_group_count", 0),
        row_incomplete_workload_fingerprints=getattr(
            result, "row_incomplete_workload_fingerprint_count", 0
        ),
        row_repeated_workload_groups=getattr(result, "row_repeated_workload_group_count", 0),
        row_repeated_workload_cases=getattr(result, "row_repeated_workload_case_count", 0),
        action_queue=getattr(result, "action_queue_count", 0),
        issues=len(getattr(result, "issues", ()) or ()),
    )


def workload_breakdowns(result: Any) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    return breakdown_pairs(
        workload_history_counts=getattr(result, "workload_history_counts", {}),
        group_regression_counts=getattr(result, "group_regression_counts", {}),
        group_baseline_counts=getattr(result, "group_baseline_counts", {}),
        group_member_count_buckets=getattr(result, "group_member_count_buckets", {}),
        detail_representative_counts=getattr(result, "detail_representative_counts", {}),
        detail_action_hint_counts=getattr(result, "detail_action_hint_counts", {}),
        detail_limitation_counts=getattr(result, "detail_limitation_counts", {}),
        action_queue_signal_counts=getattr(result, "action_queue_signal_counts", {}),
        action_queue_verification_counts=getattr(result, "action_queue_verification_counts", {}),
        action_outcome_source_counts=getattr(result, "action_outcome_source_counts", {}),
        action_outcome_group_coverage_counts=getattr(
            result,
            "action_outcome_group_coverage_counts",
            {},
        ),
        action_outcome_family_counts=getattr(result, "action_outcome_family_counts", {}),
        action_outcome_family_requirement_counts=getattr(
            result,
            "action_outcome_family_requirement_counts",
            {},
        ),
        action_outcome_gate_counts=getattr(result, "action_outcome_gate_counts", {}),
        action_outcome_verification_counts=getattr(
            result,
            "action_outcome_verification_counts",
            {},
        ),
        action_outcome_result_counts=getattr(result, "action_outcome_result_counts", {}),
        action_queue_outcome_counts=getattr(result, "action_queue_outcome_counts", {}),
        detail_action_hint_outcome_counts=getattr(
            result,
            "detail_action_hint_outcome_counts",
            {},
        ),
        row_incomplete_workload_field_counts=getattr(
            result,
            "row_incomplete_workload_field_counts",
            {},
        ),
        row_incomplete_workload_field_source_counts=getattr(
            result,
            "row_incomplete_workload_field_source_counts",
            {},
        ),
    )


def stats_metrics(result: Any) -> tuple[tuple[str, str], ...]:
    return metric_pairs(
        total_cases=getattr(result, "total_cases", 0),
        actionable_candidates=getattr(result, "actionable_candidate_count", 0),
        issues=len(getattr(result, "issues", ()) or ()),
    )


def stats_breakdowns(result: Any) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    return breakdown_pairs(
        tier_counts=getattr(result, "tier_counts", {}),
        need_type_counts=getattr(result, "need_type_counts", {}),
        metadata_status_counts=getattr(result, "metadata_status_counts", {}),
        evidence_detail_counts=getattr(result, "evidence_detail_counts", {}),
        confirmation_counts=getattr(result, "confirmation_counts", {}),
        review_area_counts=getattr(result, "review_area_counts", {}),
    )


def optimizer_metrics(result: Any) -> tuple[tuple[str, str], ...]:
    return metric_pairs(
        total_cases=getattr(result, "total_cases", 0),
        audited_cases=getattr(result, "audited_cases", 0),
        issues=len(getattr(result, "issues", ()) or ()),
    )


def optimizer_breakdowns(result: Any) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    return breakdown_pairs(
        support_source_counts=getattr(result, "support_source_counts", {}),
        status_counts=getattr(result, "status_counts", {}),
        bucket_counts=getattr(result, "bucket_counts", {}),
        no_draft_actionability_counts=getattr(result, "no_draft_actionability_counts", {}),
        review_reason_counts=getattr(result, "review_reason_counts", {}),
        review_primary_counts=getattr(result, "review_primary_counts", {}),
        no_recipe_family_counts=getattr(result, "no_recipe_family_counts", {}),
        no_recipe_hint_counts=getattr(result, "no_recipe_hint_counts", {}),
        no_recipe_review_track_counts=getattr(result, "no_recipe_review_track_counts", {}),
        no_recipe_risk_mode_counts=getattr(result, "no_recipe_risk_mode_counts", {}),
        repeated_no_recipe_review_track_counts=getattr(
            result,
            "repeated_no_recipe_review_track_counts",
            {},
        ),
        repeated_no_recipe_review_readiness_counts=getattr(
            result,
            "repeated_no_recipe_review_readiness_counts",
            {},
        ),
        repeated_no_recipe_guidance_readiness_counts=getattr(
            result,
            "repeated_no_recipe_guidance_readiness_counts",
            {},
        ),
        repeated_no_recipe_family_counts=getattr(
            result,
            "repeated_no_recipe_family_counts",
            {},
        ),
    )


def metric_pairs(**values: object) -> tuple[tuple[str, str], ...]:
    return tuple((safe_token(key), str(int_value(value))) for key, value in values.items())


def counter_key(*parts: object) -> str:
    return "/".join(safe_token(part) or "unknown" for part in parts)


def breakdown_pairs(
    **counters: object,
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    pairs: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for name, counter in counters.items():
        values = safe_counter_pairs(counter)
        if values:
            pairs.append((safe_summary_key(name), values))
    return tuple(pairs)


def safe_counter_pairs(counter: object) -> tuple[tuple[str, str], ...]:
    if not hasattr(counter, "items"):
        return ()
    safe_counts = safe_count_dict(counter.items())
    return tuple((key, str(value)) for key, value in sorted(safe_counts.items()) if value > 0)


def safe_count_dict(
    items: Iterable[tuple[object, object]],
    *,
    include_zero: bool = False,
) -> dict[str, int]:
    safe_counts: Counter[str] = Counter()
    for key, value in items:
        safe_key = safe_summary_key(key)
        if safe_key:
            safe_counts[safe_key] += int_value(value)
    return {key: value for key, value in sorted(safe_counts.items()) if include_zero or value > 0}


def safe_summary_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if raw_like_summary_key(text):
        return "unsafe_token"
    return safe_token(text)


def raw_like_summary_key(text: str) -> bool:
    return (
        contains_raw_sql_like_text(text)
        or URL_RE.search(text) is not None
        or SUMMARY_KEY_LOCAL_PATH_RE.search(text) is not None
        or redaction.EMAIL_RE.search(text) is not None
        or redaction.IPV4_RE.search(text) is not None
        or redaction.HOSTLIKE_FQDN_RE.search(text) is not None
        or redaction.SECRET_VALUE_RE.search(text) is not None
    )


def safe_token(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    token = re.sub(r"[^a-z0-9_+.-]+", "_", text)
    token = "_".join(part for part in token.split("_") if part)
    return token[:120]


def int_value(value: object) -> int:
    try:
        return max(0, int(float(str(value).strip())))
    except (TypeError, ValueError):
        return 0


def print_result(
    result: DiagnosticLoopAuditResult,
    *,
    out: TextIO = sys.stdout,
    limit: int = 12,
) -> None:
    print(f"Summary: {result.summary_name}", file=out)
    print(f"Status: {'ok' if result.ok else 'issues'}", file=out)
    print("Components:", file=out)
    for component in result.components:
        metric_text = "; ".join(f"{key}={value}" for key, value in component.metrics)
        print(
            f"  {component.name}: {'ok' if component.ok else 'issues'}; {metric_text}",
            file=out,
        )
    print("Issue categories:", file=out)
    for component in result.components:
        print(f"  {component.name}:", file=out)
        if not component.issue_counts:
            print("    none", file=out)
            continue
        for category, count in component.issue_counts.most_common(limit):
            print(f"    {category}: {count}", file=out)


def summary_json_payload(result: DiagnosticLoopAuditResult) -> dict[str, object]:
    return {
        "schema_version": "impala_diagnostic_loop_audit_v1",
        "status": "ok" if result.ok else "issues",
        "components": [component_summary_json(component) for component in result.components],
    }


def component_summary_json(component: ComponentAudit) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": safe_summary_key(component.name),
        "status": "ok" if component.ok else "issues",
        "metrics": safe_count_dict(component.metrics, include_zero=True),
        "issue_counts": safe_count_dict(sorted(component.issue_counts.items())),
    }
    if component.breakdowns:
        payload["breakdowns"] = {
            safe_summary_key(name): safe_count_dict(values)
            for name, values in component.breakdowns
            if safe_summary_key(name)
        }
    return payload


def write_summary_json(result: DiagnosticLoopAuditResult, path: Path) -> None:
    payload = summary_json_payload(result)
    try:
        path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise LoopAuditOutputError("cannot write summary JSON") from exc


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path, help="Path to batch_summary.json")
    parser.add_argument(
        "--action-outcomes",
        type=Path,
        help="Optional local action_outcomes.jsonl for strict workload outcome calibration.",
    )
    parser.add_argument(
        "--require-action-outcomes",
        action="store_true",
        help="Fail workload calibration when repeated groups lack local action-outcome feedback.",
    )
    parser.add_argument(
        "--require-workload-groups",
        action="store_true",
        help="Fail representative workload calibration when repeated workload groups are absent.",
    )
    parser.add_argument(
        "--require-direct-source-readiness",
        action="store_true",
        help="Fail coverage calibration when direct Impala source states are not readiness-safe.",
    )
    parser.add_argument(
        "--use-stored-optimizer-support",
        action="store_true",
        help="Use stored optimizer_rewrite_support instead of recomputing source-based support.",
    )
    parser.add_argument(
        "--use-current-classifier-primary",
        action="store_true",
        help=(
            "Calculate diagnostic coverage from current deterministic analysis.json "
            "primary classification instead of persisted summary labels."
        ),
    )
    parser.add_argument(
        "--max-unknown-primary-rate",
        type=float,
        default=30.0,
        help="Maximum allowed unknown primary-bottleneck percentage for coverage readiness.",
    )
    parser.add_argument(
        "--min-medium-primary-rate",
        type=float,
        default=70.0,
        help="Minimum medium-or-better primary-bottleneck percentage for coverage readiness.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Write a raw-free machine-readable audit summary JSON.",
    )
    parser.add_argument("--limit", type=int, default=12, help="Rows to print per issue section.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = audit_summary(
            args.summary,
            action_outcomes_path=args.action_outcomes,
            require_action_outcomes=args.require_action_outcomes,
            require_workload_groups=args.require_workload_groups,
            require_direct_source_readiness=args.require_direct_source_readiness,
            recompute_optimizer_support=not args.use_stored_optimizer_support,
            use_current_classifier_primary=args.use_current_classifier_primary,
            max_unknown_primary_rate=args.max_unknown_primary_rate,
            min_medium_primary_rate=args.min_medium_primary_rate,
        )
    except LoopAuditInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_result(result, limit=max(1, args.limit))
    if args.summary_json is not None:
        try:
            write_summary_json(result, args.summary_json)
        except LoopAuditOutputError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
