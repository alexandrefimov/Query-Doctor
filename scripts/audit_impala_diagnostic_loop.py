#!/usr/bin/env python3
"""Run strict raw-free Impala diagnostic-loop audits for one Recent summary."""

from __future__ import annotations

import argparse
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
