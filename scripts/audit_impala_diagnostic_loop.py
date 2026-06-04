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

from scripts.audit_impala_coverage_gaps import audit_summaries as audit_coverage_summaries  # noqa: E402
from scripts.audit_optimizer_funnel import audit_summary as audit_optimizer_summary  # noqa: E402
from scripts.audit_profile_evidence_gates import audit_summary as audit_profile_summary  # noqa: E402
from scripts.audit_recent_details import audit_summary as audit_details_summary  # noqa: E402
from scripts.audit_stats_diagnostics import audit_summary as audit_stats_summary  # noqa: E402
from scripts.audit_workload_diagnostics import audit_summary as audit_workload_summary  # noqa: E402
from query_doctor.report.language_contract import SUPPORTED_REPORT_LANGUAGES  # noqa: E402
from query_doctor.report.trusted_text import validate_report_for_mode  # noqa: E402
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
LOCAL_PATH_RE = re.compile(r"(?i)(?:^|[\s:(])(?:/users/|/private/|/tmp/|[a-z]:\\)")


@dataclass(frozen=True)
class ComponentAudit:
    name: str
    ok: bool
    metrics: tuple[tuple[str, str], ...]
    issue_counts: Counter[str] = field(default_factory=Counter)


@dataclass
class DiagnosticLoopAuditResult:
    summary_name: str
    components: tuple[ComponentAudit, ...]

    @property
    def ok(self) -> bool:
        return all(component.ok for component in self.components)


class LoopAuditInputError(RuntimeError):
    """Raised when the aggregate loop audit cannot load its primary input."""


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
    issues: list[OptimizerArtifactIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def audit_summary(
    summary_path: Path,
    *,
    action_outcomes_path: Path | None = None,
    require_action_outcomes: bool = False,
    require_direct_source_readiness: bool = False,
    recompute_optimizer_support: bool = True,
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
        ),
        run_component(
            "trusted_reports",
            lambda: audit_trusted_report_summary(resolved_summary),
            metrics=trusted_report_metrics,
        ),
        run_component(
            "optimizer_artifacts",
            lambda: audit_optimizer_artifact_summary(resolved_summary),
            metrics=optimizer_artifact_metrics,
        ),
        run_component(
            "profile_evidence",
            lambda: audit_profile_summary(resolved_summary),
            metrics=profile_metrics,
        ),
        run_component(
            "diagnostic_coverage",
            lambda: audit_coverage_summaries(
                (resolved_summary,),
                fail_on_diagnostic_coverage_gaps=True,
                fail_on_direct_source_readiness_gaps=require_direct_source_readiness,
                max_unknown_primary_rate=max_unknown_primary_rate,
                min_medium_primary_rate=min_medium_primary_rate,
            ),
            metrics=coverage_metrics,
        ),
        run_component(
            "workload",
            lambda: audit_workload_summary(
                resolved_summary,
                fail_on_workload_readiness_gaps=True,
                action_outcomes_path=action_outcomes_path,
                fail_on_action_outcome_readiness_gaps=require_action_outcomes,
            ),
            metrics=workload_metrics,
        ),
        run_component(
            "stats",
            lambda: audit_stats_summary(
                resolved_summary,
                fail_on_stats_readiness_gaps=True,
            ),
            metrics=stats_metrics,
        ),
        run_component(
            "optimizer",
            lambda: audit_optimizer_summary(
                resolved_summary,
                recompute_support=recompute_optimizer_support,
                fail_on_repeated_no_recipe_readiness_gaps=True,
            ),
            metrics=optimizer_metrics,
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
                result.revalidated_report_count += 1
                if not trusted_report_passes_current_validation(settings, case, variant):
                    result.revalidation_failure_count += 1
                    result.issues.append(
                        TrustedReportIssue(
                            category="trusted_report_revalidation_failed",
                            message="trusted report no longer passes current strict validation",
                        )
                    )
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
            if output_kind == "no_rewrite":
                result.trusted_no_rewrite_count += 1
            elif output_kind == "recommendations_only":
                result.trusted_recommendation_count += 1
            else:
                result.trusted_draft_count += 1
            if not trusted_optimizer_artifact_is_readable(artifact_dir, state):
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


def profile_metrics(result: Any) -> tuple[tuple[str, str], ...]:
    return metric_pairs(
        total_cases=getattr(result, "total_cases", 0),
        analyzed_cases=getattr(result, "analyzed_cases", 0),
        missing_analysis=getattr(result, "missing_analysis_count", 0),
        analysis_errors=getattr(result, "analysis_error_count", 0),
        issues=len(getattr(result, "issues", ()) or ()),
    )


def coverage_metrics(result: Any) -> tuple[tuple[str, str], ...]:
    return metric_pairs(
        total_cases=getattr(result, "total_cases", 0),
        analyzed_cases=getattr(result, "analyzed_cases", 0),
        missing_analysis=getattr(result, "missing_analysis_count", 0),
        direct_impala_cases=getattr(result, "direct_impala_case_count", 0),
        issues=len(getattr(result, "issues", ()) or ()),
    )


def workload_metrics(result: Any) -> tuple[tuple[str, str], ...]:
    return metric_pairs(
        total_cases=getattr(result, "total_cases", 0),
        workload_groups=getattr(result, "workload_group_count", 0),
        action_queue=getattr(result, "action_queue_count", 0),
        issues=len(getattr(result, "issues", ()) or ()),
    )


def stats_metrics(result: Any) -> tuple[tuple[str, str], ...]:
    return metric_pairs(
        total_cases=getattr(result, "total_cases", 0),
        actionable_candidates=getattr(result, "actionable_candidate_count", 0),
        issues=len(getattr(result, "issues", ()) or ()),
    )


def optimizer_metrics(result: Any) -> tuple[tuple[str, str], ...]:
    return metric_pairs(
        total_cases=getattr(result, "total_cases", 0),
        audited_cases=getattr(result, "audited_cases", 0),
        issues=len(getattr(result, "issues", ()) or ()),
    )


def metric_pairs(**values: object) -> tuple[tuple[str, str], ...]:
    return tuple((safe_token(key), str(int_value(value))) for key, value in values.items())


def safe_token(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    token = re.sub(r"[^a-z0-9_+.-]+", "_", text)
    token = "_".join(part for part in token.split("_") if part)
    return token[:80]


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
    parser.add_argument("--limit", type=int, default=12, help="Rows to print per issue section.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = audit_summary(
            args.summary,
            action_outcomes_path=args.action_outcomes,
            require_action_outcomes=args.require_action_outcomes,
            require_direct_source_readiness=args.require_direct_source_readiness,
            recompute_optimizer_support=not args.use_stored_optimizer_support,
            max_unknown_primary_rate=args.max_unknown_primary_rate,
            min_medium_primary_rate=args.min_medium_primary_rate,
        )
    except LoopAuditInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_result(result, limit=max(1, args.limit))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
