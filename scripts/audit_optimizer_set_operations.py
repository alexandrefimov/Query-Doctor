#!/usr/bin/env python3
"""Build a raw-free optimizer set-operation shape matrix."""

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

from query_doctor.optimizer.sql import OptimizerSqlError  # noqa: E402
from query_doctor.optimizer.shape_guidance import SET_OPERATION_REVIEW_TRACKS  # noqa: E402
from query_doctor.optimizer.sql_shape import (  # noqa: E402
    cte_projection_preservation_status,
    nested_query_signatures,
    projection_item_fragments,
    split_top_level_union_all_fragments,
    top_level_join_signature,
    top_level_keyword_count,
)
from query_doctor.recent.query_optimization_score import optimizer_rewriteability_rank  # noqa: E402
from scripts.audit_optimizer_funnel import (  # noqa: E402
    AuditInputError,
    first_candidate_reason,
    load_summary,
    primary_label,
    shape_family,
    source_sql_for_case,
    sql_feature_cluster,
    summary_cases,
    support_actionability_payload,
    support_for_case,
    workload_key,
)
from scripts.audit_optimizer_plain_shapes import (  # noqa: E402
    aggregate_function_count,
    count_bucket,
    count_shape,
    plain_aggregate_shape,
    plain_relation_shape,
    plain_set_shape,
    plain_shape_facts,
)
from scripts.audit_optimizer_structural_backlog import (  # noqa: E402
    is_structural_review_case,
    support_actionability,
)


@dataclass(frozen=True)
class SetOperationShapeFacts:
    source_status: str
    set_shape: str
    branch_count_shape: str
    branch_relation_shape: str
    branch_filter_shape: str
    branch_aggregate_shape: str
    branch_nested_shape: str
    branch_projection_count_shape: str
    branch_projection_preservation_shape: str
    review_track: str
    feature_cluster: str


@dataclass
class SetOperationGroup:
    key: str
    count: int = 0
    workloads: Counter[str] = field(default_factory=Counter)
    primary_labels: Counter[str] = field(default_factory=Counter)
    candidate_reasons: Counter[str] = field(default_factory=Counter)
    risk_modes: Counter[str] = field(default_factory=Counter)
    feature_clusters: Counter[str] = field(default_factory=Counter)


@dataclass
class SetOperationAuditResult:
    summary_name: str
    total_cases: int = 0
    audited_cases: int = 0
    structural_cases: int = 0
    plain_cases: int = 0
    set_operation_cases: int = 0
    source_status_counts: Counter[str] = field(default_factory=Counter)
    review_track_counts: Counter[str] = field(default_factory=Counter)
    set_shape_counts: Counter[str] = field(default_factory=Counter)
    branch_count_shape_counts: Counter[str] = field(default_factory=Counter)
    branch_relation_shape_counts: Counter[str] = field(default_factory=Counter)
    branch_filter_shape_counts: Counter[str] = field(default_factory=Counter)
    branch_aggregate_shape_counts: Counter[str] = field(default_factory=Counter)
    branch_nested_shape_counts: Counter[str] = field(default_factory=Counter)
    branch_projection_count_shape_counts: Counter[str] = field(default_factory=Counter)
    branch_projection_preservation_shape_counts: Counter[str] = field(default_factory=Counter)
    groups: dict[str, SetOperationGroup] = field(default_factory=dict)


def audit_set_operations(
    summary_path: Path,
    *,
    recompute_support: bool = True,
) -> SetOperationAuditResult:
    summary_path = summary_path.resolve(strict=True)
    cases = summary_cases(load_summary(summary_path))
    result = SetOperationAuditResult(summary_name=summary_path.name, total_cases=len(cases))

    for case in cases:
        result.audited_cases += 1
        support, _support_source = support_for_case(
            case,
            summary_path=summary_path,
            recompute_support=recompute_support,
        )
        payload = support_actionability_payload(support)
        rank = optimizer_rewriteability_rank(payload)
        actionability = support_actionability(support, payload)
        if not is_structural_review_case(support, rank=rank, actionability=actionability):
            continue
        result.structural_cases += 1
        if shape_family(support) != "plain":
            continue
        result.plain_cases += 1

        source_sql = source_sql_for_case(case, summary_path=summary_path)
        plain_facts = plain_shape_facts(source_sql)
        if plain_facts.review_track not in SET_OPERATION_REVIEW_TRACKS | {"set_operation_research"}:
            continue

        result.set_operation_cases += 1
        facts = set_operation_shape_facts(source_sql)
        result.source_status_counts[facts.source_status] += 1
        result.review_track_counts[facts.review_track] += 1
        result.set_shape_counts[facts.set_shape] += 1
        result.branch_count_shape_counts[facts.branch_count_shape] += 1
        result.branch_relation_shape_counts[facts.branch_relation_shape] += 1
        result.branch_filter_shape_counts[facts.branch_filter_shape] += 1
        result.branch_aggregate_shape_counts[facts.branch_aggregate_shape] += 1
        result.branch_nested_shape_counts[facts.branch_nested_shape] += 1
        result.branch_projection_count_shape_counts[facts.branch_projection_count_shape] += 1
        result.branch_projection_preservation_shape_counts[
            facts.branch_projection_preservation_shape
        ] += 1

        key = set_operation_group_key(facts)
        group = result.groups.setdefault(key, SetOperationGroup(key=key))
        group.count += 1
        group.workloads[workload_key(case)] += 1
        group.primary_labels[primary_label(case)] += 1
        group.candidate_reasons[first_candidate_reason(case)] += 1
        group.risk_modes[support.risk_mode or "unknown"] += 1
        group.feature_clusters[facts.feature_cluster] += 1

    return result


def set_operation_shape_facts(source_sql: str) -> SetOperationShapeFacts:
    if not source_sql:
        return SetOperationShapeFacts(
            source_status="unavailable",
            set_shape="unknown",
            branch_count_shape="unknown",
            branch_relation_shape="unknown",
            branch_filter_shape="unknown",
            branch_aggregate_shape="unknown",
            branch_nested_shape="unknown",
            branch_projection_count_shape="unknown",
            branch_projection_preservation_shape="unknown",
            review_track="source_unavailable",
            feature_cluster="unknown",
        )
    feature_cluster = sql_feature_cluster(source_sql)
    set_shape = plain_set_shape(source_sql)
    if not set_shape.startswith("union_all_"):
        return SetOperationShapeFacts(
            source_status="available",
            set_shape=set_shape,
            branch_count_shape="not_union_all",
            branch_relation_shape="not_union_all",
            branch_filter_shape="not_union_all",
            branch_aggregate_shape="not_union_all",
            branch_nested_shape="not_union_all",
            branch_projection_count_shape="not_union_all",
            branch_projection_preservation_shape="not_union_all",
            review_track="mixed_or_distinct_set_boundary",
            feature_cluster=feature_cluster,
        )
    branches = split_top_level_union_all_fragments(source_sql)
    if len(branches) <= 1:
        return SetOperationShapeFacts(
            source_status="parse_limited",
            set_shape=set_shape,
            branch_count_shape="unknown",
            branch_relation_shape="unknown",
            branch_filter_shape="unknown",
            branch_aggregate_shape="unknown",
            branch_nested_shape="unknown",
            branch_projection_count_shape="unknown",
            branch_projection_preservation_shape="unknown",
            review_track="parse_limited",
            feature_cluster=feature_cluster,
        )
    try:
        branch_relation_values = tuple(branch_relation_shape(branch) for branch in branches)
        branch_filter_values = tuple(branch_filter_shape(branch) for branch in branches)
        branch_aggregate_values = tuple(branch_aggregate_shape(branch) for branch in branches)
        branch_nested_values = tuple(branch_nested_shape(branch) for branch in branches)
        projection_counts = tuple(len(projection_item_fragments(branch)) for branch in branches)
        projection_preservation_values = tuple(
            cte_projection_preservation_status(branch) for branch in branches
        )
    except (OptimizerSqlError, ValueError):
        return SetOperationShapeFacts(
            source_status="parse_limited",
            set_shape=set_shape,
            branch_count_shape=f"branches_{count_bucket(len(branches))}",
            branch_relation_shape="unknown",
            branch_filter_shape="unknown",
            branch_aggregate_shape="unknown",
            branch_nested_shape="unknown",
            branch_projection_count_shape="unknown",
            branch_projection_preservation_shape="unknown",
            review_track="parse_limited",
            feature_cluster=feature_cluster,
        )

    projection_count_shape = projection_count_alignment(projection_counts)
    projection_preservation_shape = uniform_or_mixed(
        projection_preservation_values,
        prefix="projection",
    )
    relation_shape = uniform_or_mixed(branch_relation_values, prefix="relation")
    filter_shape = uniform_or_mixed(branch_filter_values, prefix="filter")
    aggregate_shape = uniform_or_mixed(branch_aggregate_values, prefix="aggregate")
    nested_shape = uniform_or_mixed(branch_nested_values, prefix="nested")
    return SetOperationShapeFacts(
        source_status="available",
        set_shape=set_shape,
        branch_count_shape=f"branches_{count_bucket(len(branches))}",
        branch_relation_shape=relation_shape,
        branch_filter_shape=filter_shape,
        branch_aggregate_shape=aggregate_shape,
        branch_nested_shape=nested_shape,
        branch_projection_count_shape=projection_count_shape,
        branch_projection_preservation_shape=projection_preservation_shape,
        review_track=set_operation_review_track(
            branch_filter_shape=filter_shape,
            branch_aggregate_shape=aggregate_shape,
            branch_nested_shape=nested_shape,
            branch_projection_count_shape=projection_count_shape,
            branch_projection_preservation_shape=projection_preservation_shape,
            branch_relation_shape=relation_shape,
        ),
        feature_cluster=feature_cluster,
    )


def branch_relation_shape(branch_sql: str) -> str:
    join_signatures = top_level_join_signature(branch_sql)
    outer_join_count = sum(
        1
        for signature in join_signatures
        if any(modifier in {"LEFT", "RIGHT", "FULL"} for modifier in signature)
    )
    return plain_relation_shape(len(join_signatures), outer_join_count)


def branch_filter_shape(branch_sql: str) -> str:
    return count_shape(top_level_keyword_count(branch_sql, "WHERE"), "filter")


def branch_aggregate_shape(branch_sql: str) -> str:
    return plain_aggregate_shape(
        branch_sql,
        aggregate_function_count(branch_sql),
        top_level_keyword_count(branch_sql, "GROUP"),
    )


def branch_nested_shape(branch_sql: str) -> str:
    return count_shape(len(nested_query_signatures(branch_sql)), "nested_query")


def projection_count_alignment(counts: tuple[int, ...]) -> str:
    if not counts:
        return "unknown"
    unique = set(counts)
    if len(unique) != 1:
        buckets = sorted({count_bucket(count) for count in counts})
        return f"mixed_projection_count_{'_'.join(buckets)}"
    return f"aligned_projection_count_{count_bucket(counts[0])}"


def uniform_or_mixed(values: tuple[str, ...], *, prefix: str) -> str:
    if not values:
        return f"{prefix}_unknown"
    unique = sorted(set(values))
    if len(unique) == 1:
        return f"uniform_{unique[0]}"
    if len(unique) <= 3:
        return f"mixed_{prefix}_{'_and_'.join(unique)}"
    return f"mixed_{prefix}_many"


def set_operation_review_track(
    *,
    branch_filter_shape: str,
    branch_aggregate_shape: str,
    branch_nested_shape: str,
    branch_projection_count_shape: str,
    branch_projection_preservation_shape: str,
    branch_relation_shape: str,
) -> str:
    if not branch_projection_count_shape.startswith("aligned_projection_count_"):
        return "branch_projection_mismatch_boundary"
    if "unknown_projection_preservation" in branch_projection_preservation_shape:
        return "branch_projection_unknown_boundary"
    if branch_nested_shape != "uniform_no_nested_query":
        return "nested_branch_boundary"
    if branch_aggregate_shape != "uniform_no_aggregate":
        return "aggregate_branch_boundary"
    if "outer_join" in branch_relation_shape or "mixed_join" in branch_relation_shape:
        return "outer_or_mixed_join_branch_review"
    if branch_filter_shape == "uniform_no_filter":
        return "unfiltered_union_all_branch_review"
    if branch_filter_shape.startswith("uniform_"):
        return "filtered_union_all_branch_review"
    return "mixed_filter_union_all_branch_review"


def set_operation_group_key(facts: SetOperationShapeFacts) -> str:
    return (
        f"track={facts.review_track}; set={facts.set_shape}; "
        f"branches={facts.branch_count_shape}; relation={facts.branch_relation_shape}; "
        f"filter={facts.branch_filter_shape}; aggregate={facts.branch_aggregate_shape}; "
        f"nested={facts.branch_nested_shape}; "
        f"projection_count={facts.branch_projection_count_shape}; "
        f"projection={facts.branch_projection_preservation_shape}"
    )


def print_result(
    result: SetOperationAuditResult,
    *,
    limit: int = 20,
    out: TextIO | None = None,
) -> None:
    out = out or sys.stdout
    print(f"Summary: {result.summary_name}", file=out)
    print(
        f"Cases: total={result.total_cases}, audited={result.audited_cases}, "
        f"structural_review={result.structural_cases}, plain={result.plain_cases}, "
        f"set_operation={result.set_operation_cases}",
        file=out,
    )
    print_counter("Set-operation source status", result.source_status_counts, limit=limit, out=out)
    print_counter("Set-operation review tracks", result.review_track_counts, limit=limit, out=out)
    print_counter("Set-operation shapes", result.set_shape_counts, limit=limit, out=out)
    print_counter("Branch count shapes", result.branch_count_shape_counts, limit=limit, out=out)
    print_counter(
        "Branch relation shapes", result.branch_relation_shape_counts, limit=limit, out=out
    )
    print_counter("Branch filter shapes", result.branch_filter_shape_counts, limit=limit, out=out)
    print_counter(
        "Branch aggregate shapes", result.branch_aggregate_shape_counts, limit=limit, out=out
    )
    print_counter("Branch nested shapes", result.branch_nested_shape_counts, limit=limit, out=out)
    print_counter(
        "Branch projection count shapes",
        result.branch_projection_count_shape_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "Branch projection preservation shapes",
        result.branch_projection_preservation_shape_counts,
        limit=limit,
        out=out,
    )
    print("Top set-operation structural groups:", file=out)
    groups = sorted(result.groups.values(), key=lambda item: (-item.count, item.key))
    if not groups:
        print("  <none>", file=out)
        return
    for group in groups[:limit]:
        print(
            f"  cases={group.count}; {group.key}; "
            f"workloads={counter_text(group.workloads, limit=3)}; "
            f"primary={counter_text(group.primary_labels, limit=3)}; "
            f"reason={counter_text(group.candidate_reasons, limit=2)}; "
            f"risk={counter_text(group.risk_modes, limit=2)}; "
            f"features={counter_text(group.feature_clusters, limit=1)}",
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


def counter_text(counter: Counter[str], *, limit: int) -> str:
    if not counter:
        return "<none>"
    return ", ".join(f"{key}={count}" for key, count in counter.most_common(limit))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a raw-free branch-level matrix for plain SQL set-operation optimizer "
            "structural-review cases. The output contains only safe shape categories."
        )
    )
    parser.add_argument("summary", type=Path, help="Path to batch_summary.json")
    parser.add_argument(
        "--use-stored-support",
        action="store_true",
        help="Use optimizer_rewrite_support already present in the summary instead of recomputing.",
    )
    parser.add_argument("--limit", type=int, default=20, help="Rows to print per section.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        result = audit_set_operations(args.summary, recompute_support=not args.use_stored_support)
    except AuditInputError as exc:
        print(f"optimizer set-operation audit failed: {exc}", file=sys.stderr)
        return 2
    print_result(result, limit=max(1, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
