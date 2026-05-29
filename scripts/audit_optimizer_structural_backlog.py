#!/usr/bin/env python3
"""Build a raw-free structural optimizer backlog shortlist."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.recent.query_optimization_score import (  # noqa: E402
    optimizer_adjacent_actionability,
    optimizer_no_draft_actionability,
    optimizer_rewriteability_rank,
)
from query_doctor.optimizer.shape_guidance import PLAIN_REVIEW_TRACKS, plain_review_track  # noqa: E402
from scripts.audit_optimizer_funnel import (  # noqa: E402
    AuditInputError,
    SupportView,
    actual_case_dir,
    first_candidate_reason,
    load_summary,
    primary_label,
    recipe_hint,
    shape_family,
    source_sql_for_case,
    sql_feature_cluster,
    summary_cases,
    support_actionability_payload,
    support_for_case,
    workload_key,
)


REVIEW_STATUSES = {"guidance_only", "draft_disabled", "source_unavailable"}


@dataclass
class StructuralGroup:
    key: str
    count: int = 0
    workloads: Counter[str] = field(default_factory=Counter)
    primary_labels: Counter[str] = field(default_factory=Counter)
    candidate_reasons: Counter[str] = field(default_factory=Counter)
    risk_modes: Counter[str] = field(default_factory=Counter)
    risk_reasons: Counter[str] = field(default_factory=Counter)


@dataclass
class StructuralBacklogResult:
    summary_name: str
    total_cases: int = 0
    audited_cases: int = 0
    structural_cases: int = 0
    effective_rank_counts: Counter[str] = field(default_factory=Counter)
    actionability_counts: Counter[str] = field(default_factory=Counter)
    bucket_counts: Counter[str] = field(default_factory=Counter)
    blocker_counts: Counter[str] = field(default_factory=Counter)
    groups: dict[str, StructuralGroup] = field(default_factory=dict)


def audit_structural_backlog(
    summary_path: Path,
    *,
    recompute_support: bool = True,
) -> StructuralBacklogResult:
    summary_path = summary_path.resolve(strict=True)
    cases = summary_cases(load_summary(summary_path))
    result = StructuralBacklogResult(summary_name=summary_path.name, total_cases=len(cases))

    for case in cases:
        result.audited_cases += 1
        support, _support_source = support_for_case(
            case,
            summary_path=summary_path,
            recompute_support=recompute_support,
        )
        payload = support_actionability_payload(support)
        rank = optimizer_rewriteability_rank(payload)
        result.effective_rank_counts[str(rank)] += 1
        actionability = support_actionability(support, payload)
        if actionability != "not_applicable":
            result.actionability_counts[actionability] += 1

        if not is_structural_review_case(support, rank=rank, actionability=actionability):
            continue

        family = shape_family(support)
        plain_source_sql = (
            source_sql_for_case(case, summary_path=summary_path) if family == "plain" else ""
        )
        blocker = blocker_key(
            support,
            actionability=actionability,
            source_sql=plain_source_sql,
        )
        shape = shape_descriptor(
            support,
            case=case,
            summary_path=summary_path,
            source_sql=plain_source_sql,
        )
        key = (
            f"rank={rank}; actionability={actionability}; "
            f"bucket={support.rewriteability_bucket}; family={family}; "
            f"blocker={blocker}; shape={shape}"
        )
        group = result.groups.setdefault(key, StructuralGroup(key=key))
        result.structural_cases += 1
        group.count += 1
        group.workloads[workload_key(case)] += 1
        group.primary_labels[primary_label(case)] += 1
        group.candidate_reasons[first_candidate_reason(case)] += 1
        group.risk_modes[support.risk_mode or "unknown"] += 1
        group.risk_reasons.update(support.risk_reasons)
        result.bucket_counts[support.rewriteability_bucket] += 1
        result.blocker_counts[blocker] += 1

    return result


def is_structural_review_case(
    support: SupportView,
    *,
    rank: int,
    actionability: str,
) -> bool:
    if support.status not in REVIEW_STATUSES:
        return False
    if actionability == "structural_boundary":
        return True
    return rank <= 1


def support_actionability(support: SupportView, payload: dict[str, object]) -> str:
    if support.rewriteability_bucket == "recipe_adjacent_shape":
        return optimizer_adjacent_actionability(payload)
    if support.rewriteability_bucket == "recipe_detected_no_draft":
        return optimizer_no_draft_actionability(payload)
    if support.rewriteability_bucket == "human_review_only":
        return "human_review_only"
    if support.status == "source_unavailable":
        return "source_unavailable"
    if support.rewriteability_bucket == "not_rewriteable":
        return "not_rewriteable"
    return "not_applicable"


def blocker_key(
    support: SupportView,
    *,
    actionability: str,
    source_sql: str = "",
) -> str:
    if support.status == "source_unavailable":
        return "source_unavailable"
    if support.rewriteability_bucket == "recipe_detected_no_draft":
        return f"no_draft:{support.draft_unavailable_class or 'other'}"
    if support.rewriteability_bucket == "recipe_adjacent_shape":
        boundary = first_priority_boundary(
            (*support.cte_boundary_reasons, *support.derived_boundary_reasons)
        )
        if boundary:
            return f"adjacent:{boundary}"
        return f"adjacent:{actionability}"
    if support.draft_eligibility == "disabled_by_safety_thresholds":
        return "safety_threshold"
    hint = recipe_hint(support)
    if hint != "no_specific_recipe_hint":
        return hint
    family = shape_family(support)
    if family == "plain":
        plain_track = plain_no_recipe_track(support, source_sql=source_sql)
        if plain_track:
            return f"plain:{plain_track}"
    return f"{family}:no_specific_recipe"


def plain_no_recipe_track(support: SupportView, *, source_sql: str = "") -> str:
    if support.no_recipe_review_track in PLAIN_REVIEW_TRACKS:
        return support.no_recipe_review_track
    if source_sql.strip():
        return plain_review_track(source_sql)
    reason = support.reason.lower()
    reason_tracks = {
        "plain aggregate or distinct": "aggregate_or_distinct_review",
        "plain set-operation": "set_operation_research",
        "plain nested-query": "nested_query_boundary",
        "plain unfiltered join": "unfiltered_join_review",
        "plain filtered join": "filtered_join_review",
        "plain outer-join": "outer_join_review",
        "plain single-relation filter": "single_relation_filter_review",
        "plain scan/projection": "simple_scan_or_projection_review",
    }
    for needle, track in reason_tracks.items():
        if needle in reason:
            return track
    return ""


def first_priority_boundary(reasons: tuple[str, ...]) -> str:
    priority = (
        "cte_body_validation_not_proven",
        "nested_body_validation_required",
        "disconnected",
        "unsupported_reference_order",
        "unsupported_graph",
        "aggregate_boundary",
        "outer_join_boundary",
        "outer_join_or_multiple_relations",
        "set_operation_boundary",
        "window_boundary",
        "projection_not_simple",
        "no_downstream_filter_for_pushdown",
    )
    reason_set = {reason for reason in reasons if reason}
    for reason in priority:
        if reason in reason_set:
            return reason
    return next(iter(sorted(reason_set)), "")


def shape_descriptor(
    support: SupportView,
    *,
    case: dict[str, object],
    summary_path: Path,
    source_sql: str = "",
) -> str:
    family = shape_family(support)
    if family == "plain":
        return sql_feature_cluster(
            source_sql or source_sql_for_case(case, summary_path=summary_path)
        )
    parts: list[str] = []
    if support.cte_count:
        parts.extend(
            [
                f"cte_graph={support.cte_graph_shape}",
                f"cte_pushdown={support.cte_predicate_pushdown_status}",
                f"cte_simplification={support.cte_simplification_status}",
            ]
        )
    if support.derived_table_count:
        parts.append(f"derived_pushdown={support.derived_predicate_pushdown_status}")
    return "; ".join(parts) if parts else "unknown"


def print_result(
    result: StructuralBacklogResult,
    *,
    limit: int = 15,
    out: TextIO | None = None,
) -> None:
    out = out or sys.stdout
    print(f"Summary: {result.summary_name}", file=out)
    print(
        f"Cases: total={result.total_cases}, audited={result.audited_cases}, "
        f"structural_review={result.structural_cases}",
        file=out,
    )
    print_counter("Effective ranks", result.effective_rank_counts, limit=limit, out=out)
    print_counter("Actionability", result.actionability_counts, limit=limit, out=out)
    print_counter("Structural buckets", result.bucket_counts, limit=limit, out=out)
    print_counter("Structural blockers", result.blocker_counts, limit=limit, out=out)
    print("Top structural groups:", file=out)
    groups = sorted(result.groups.values(), key=lambda item: item.count, reverse=True)
    if not groups:
        print("  <none>", file=out)
        return
    for group in groups[:limit]:
        workloads = ", ".join(f"{key}={count}" for key, count in group.workloads.most_common(3))
        primary = ", ".join(f"{key}={count}" for key, count in group.primary_labels.most_common(3))
        reasons = ", ".join(
            f"{key}={count}" for key, count in group.candidate_reasons.most_common(2)
        )
        risk = ", ".join(f"{key}={count}" for key, count in group.risk_modes.most_common(2))
        risk_reasons = ", ".join(
            f"{key}={count}" for key, count in group.risk_reasons.most_common(3)
        )
        print(
            f"  cases={group.count}; {group.key}; workloads={workloads or '<none>'}; "
            f"primary={primary or '<none>'}; reason={reasons or '<none>'}; "
            f"risk={risk or '<none>'}; risk_reasons={risk_reasons or '<none>'}",
            file=out,
        )
    remaining = len(groups) - limit
    if remaining > 0:
        print(f"  ... {remaining} more", file=out)


def print_counter(
    title: str,
    counter: Counter[str],
    *,
    limit: int,
    out: TextIO,
) -> None:
    print(f"{title}:", file=out)
    if not counter:
        print("  <none>", file=out)
        return
    for key, count in counter.most_common(limit):
        print(f"  {key}: {count}", file=out)
    remaining = len(counter) - limit
    if remaining > 0:
        print(f"  ... {remaining} more", file=out)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a raw-free shortlist of structural optimizer review groups from an "
            "existing batch_summary.json. The output prints aggregate shape/status "
            "categories only and never prints source SQL."
        )
    )
    parser.add_argument("summary", type=Path, help="Path to batch_summary.json")
    parser.add_argument(
        "--use-stored-support",
        action="store_true",
        help="Use optimizer_rewrite_support already present in the summary instead of recomputing.",
    )
    parser.add_argument("--limit", type=int, default=15, help="Rows to print per section.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        result = audit_structural_backlog(
            args.summary, recompute_support=not args.use_stored_support
        )
    except AuditInputError as exc:
        print(f"optimizer structural backlog audit failed: {exc}", file=sys.stderr)
        return 2
    print_result(result, limit=max(1, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
