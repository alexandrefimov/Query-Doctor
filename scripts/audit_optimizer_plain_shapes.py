#!/usr/bin/env python3
"""Build a raw-free plain-SQL optimizer shape matrix."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.optimizer.sql import OptimizerSqlError  # noqa: E402
from query_doctor.optimizer.shape_guidance import (  # noqa: E402
    plain_set_operation_review_track,
)
from query_doctor.optimizer.sql_shape import (  # noqa: E402
    count_distinct_key_names,
    lower_sql_outside_quoted_text,
    main_select_has_distinct,
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
    length_bucket,
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
from scripts.audit_optimizer_structural_backlog import (  # noqa: E402
    is_structural_review_case,
    support_actionability,
)


@dataclass(frozen=True)
class PlainShapeFacts:
    source_status: str
    length: str
    feature_cluster: str
    relation_shape: str
    predicate_shape: str
    aggregate_shape: str
    set_shape: str
    nested_query_shape: str
    projection_shape: str
    review_track: str


@dataclass
class PlainShapeGroup:
    key: str
    count: int = 0
    workloads: Counter[str] = field(default_factory=Counter)
    primary_labels: Counter[str] = field(default_factory=Counter)
    candidate_reasons: Counter[str] = field(default_factory=Counter)
    risk_modes: Counter[str] = field(default_factory=Counter)
    feature_clusters: Counter[str] = field(default_factory=Counter)


@dataclass
class PlainShapeAuditResult:
    summary_name: str
    total_cases: int = 0
    audited_cases: int = 0
    structural_cases: int = 0
    plain_cases: int = 0
    source_status_counts: Counter[str] = field(default_factory=Counter)
    review_track_counts: Counter[str] = field(default_factory=Counter)
    relation_shape_counts: Counter[str] = field(default_factory=Counter)
    predicate_shape_counts: Counter[str] = field(default_factory=Counter)
    aggregate_shape_counts: Counter[str] = field(default_factory=Counter)
    set_shape_counts: Counter[str] = field(default_factory=Counter)
    nested_query_shape_counts: Counter[str] = field(default_factory=Counter)
    groups: dict[str, PlainShapeGroup] = field(default_factory=dict)


def audit_plain_shapes(
    summary_path: Path,
    *,
    recompute_support: bool = True,
) -> PlainShapeAuditResult:
    summary_path = summary_path.resolve(strict=True)
    cases = summary_cases(load_summary(summary_path))
    result = PlainShapeAuditResult(summary_name=summary_path.name, total_cases=len(cases))

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
        facts = plain_shape_facts(source_sql_for_case(case, summary_path=summary_path))
        result.source_status_counts[facts.source_status] += 1
        result.review_track_counts[facts.review_track] += 1
        result.relation_shape_counts[facts.relation_shape] += 1
        result.predicate_shape_counts[facts.predicate_shape] += 1
        result.aggregate_shape_counts[facts.aggregate_shape] += 1
        result.set_shape_counts[facts.set_shape] += 1
        result.nested_query_shape_counts[facts.nested_query_shape] += 1

        key = plain_shape_group_key(facts)
        group = result.groups.setdefault(key, PlainShapeGroup(key=key))
        group.count += 1
        group.workloads[workload_key(case)] += 1
        group.primary_labels[primary_label(case)] += 1
        group.candidate_reasons[first_candidate_reason(case)] += 1
        group.risk_modes[support.risk_mode or "unknown"] += 1
        group.feature_clusters[facts.feature_cluster] += 1

    return result


def plain_shape_facts(source_sql: str) -> PlainShapeFacts:
    if not source_sql:
        return PlainShapeFacts(
            source_status="unavailable",
            length="unknown",
            feature_cluster="unknown",
            relation_shape="unknown",
            predicate_shape="unknown",
            aggregate_shape="unknown",
            set_shape="unknown",
            nested_query_shape="unknown",
            projection_shape="unknown",
            review_track="source_unavailable",
        )
    try:
        join_signatures = top_level_join_signature(source_sql)
        join_count = len(join_signatures)
        outer_join_count = sum(
            1
            for signature in join_signatures
            if any(modifier in {"LEFT", "RIGHT", "FULL"} for modifier in signature)
        )
        where_count = top_level_keyword_count(source_sql, "WHERE")
        group_count = top_level_keyword_count(source_sql, "GROUP")
        aggregate_count = aggregate_function_count(source_sql)
        set_shape = plain_set_shape(source_sql)
        nested_count = len(nested_query_signatures(source_sql))
        relation_shape = plain_relation_shape(join_count, outer_join_count)
        predicate_shape = count_shape(where_count, "filter")
        aggregate_shape = plain_aggregate_shape(source_sql, aggregate_count, group_count)
        nested_shape = count_shape(nested_count, "nested_query")
        projection_shape = projection_count_shape(source_sql)
        review_track = plain_review_track(
            source_sql=source_sql,
            relation_shape=relation_shape,
            predicate_shape=predicate_shape,
            aggregate_shape=aggregate_shape,
            set_shape=set_shape,
            nested_query_shape=nested_shape,
        )
        return PlainShapeFacts(
            source_status="available",
            length=length_bucket(source_sql),
            feature_cluster=sql_feature_cluster(source_sql),
            relation_shape=relation_shape,
            predicate_shape=predicate_shape,
            aggregate_shape=aggregate_shape,
            set_shape=set_shape,
            nested_query_shape=nested_shape,
            projection_shape=projection_shape,
            review_track=review_track,
        )
    except (OptimizerSqlError, ValueError):
        return PlainShapeFacts(
            source_status="parse_limited",
            length=length_bucket(source_sql),
            feature_cluster=sql_feature_cluster(source_sql),
            relation_shape="unknown",
            predicate_shape="unknown",
            aggregate_shape="unknown",
            set_shape="unknown",
            nested_query_shape="unknown",
            projection_shape="unknown",
            review_track="parse_limited",
        )


def aggregate_function_count(source_sql: str) -> int:
    return len(
        re.findall(
            r"\b(?:sum|count|min|max|avg)\s*\(",
            lower_sql_outside_quoted_text(source_sql),
            re.IGNORECASE,
        )
    )


def plain_set_shape(source_sql: str) -> str:
    union_count = top_level_keyword_count(source_sql, "UNION")
    except_count = top_level_keyword_count(source_sql, "EXCEPT")
    intersect_count = top_level_keyword_count(source_sql, "INTERSECT")
    if union_count == 0 and except_count == 0 and intersect_count == 0:
        return "no_set_operation"
    if except_count or intersect_count:
        return "except_or_intersect"
    union_all_branches = split_top_level_union_all_fragments(source_sql)
    if len(union_all_branches) > 1 and len(union_all_branches) == union_count + 1:
        return f"union_all_{count_bucket(len(union_all_branches))}_branches"
    return "union_distinct_or_mixed"


def plain_relation_shape(join_count: int, outer_join_count: int) -> str:
    if join_count <= 0:
        return "single_relation_or_projection"
    if join_count == 1 and outer_join_count == 0:
        return "single_inner_join"
    if join_count == 1:
        return "single_outer_join"
    if outer_join_count == 0:
        return f"multi_inner_join_{count_bucket(join_count)}"
    return f"multi_mixed_join_{count_bucket(join_count)}"


def plain_aggregate_shape(source_sql: str, aggregate_count: int, group_count: int) -> str:
    if aggregate_count <= 0 and group_count <= 0 and not main_select_has_distinct(source_sql):
        return "no_aggregate"
    if count_distinct_key_names(source_sql):
        return "distinct_aggregate"
    if main_select_has_distinct(source_sql):
        return "select_distinct"
    if group_count > 0:
        return f"grouped_aggregate_{count_bucket(aggregate_count)}_functions"
    return f"scalar_aggregate_{count_bucket(aggregate_count)}_functions"


def projection_count_shape(source_sql: str) -> str:
    return f"projection_{count_bucket(len(projection_item_fragments(source_sql)))}_items"


def count_shape(count: int, label: str) -> str:
    if count <= 0:
        return f"no_{label}"
    if count == 1:
        return f"single_{label}"
    return f"multi_{label}_{count_bucket(count)}"


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


def plain_review_track(
    *,
    source_sql: str = "",
    relation_shape: str,
    predicate_shape: str,
    aggregate_shape: str,
    set_shape: str,
    nested_query_shape: str,
) -> str:
    if set_shape != "no_set_operation":
        if source_sql:
            return plain_set_operation_review_track(source_sql)
        return "set_operation_research"
    if nested_query_shape != "no_nested_query":
        return "nested_query_boundary"
    if (
        relation_shape == "single_relation_or_projection"
        and predicate_shape == "single_filter"
        and aggregate_shape == "scalar_aggregate_1_functions"
    ):
        return "filtered_scalar_aggregate_review"
    if aggregate_shape != "no_aggregate":
        if aggregate_shape == "distinct_aggregate":
            return "distinct_aggregate_review"
        if aggregate_shape.startswith("grouped_aggregate"):
            return "grouped_aggregate_review"
        if aggregate_shape == "scalar_aggregate_1_functions":
            return "scalar_aggregate_review"
        if aggregate_shape.startswith("scalar_aggregate"):
            return "scalar_multi_aggregate_review"
        return "aggregate_or_distinct_review"
    if relation_shape in {"single_outer_join"} or relation_shape.startswith("multi_mixed_join"):
        return "outer_join_review"
    if relation_shape in {"single_inner_join"} or relation_shape.startswith("multi_inner_join"):
        if predicate_shape == "no_filter":
            return "unfiltered_join_review"
        return "filtered_join_review"
    if predicate_shape == "no_filter":
        return "simple_scan_or_projection_review"
    return "single_relation_filter_review"


def plain_shape_group_key(facts: PlainShapeFacts) -> str:
    return (
        f"track={facts.review_track}; relation={facts.relation_shape}; "
        f"filter={facts.predicate_shape}; aggregate={facts.aggregate_shape}; "
        f"set={facts.set_shape}; nested={facts.nested_query_shape}; "
        f"projection={facts.projection_shape}; len={facts.length}"
    )


def print_result(
    result: PlainShapeAuditResult,
    *,
    limit: int = 20,
    out: TextIO | None = None,
) -> None:
    out = out or sys.stdout
    print(f"Summary: {result.summary_name}", file=out)
    print(
        f"Cases: total={result.total_cases}, audited={result.audited_cases}, "
        f"structural_review={result.structural_cases}, plain={result.plain_cases}",
        file=out,
    )
    print_counter("Plain source status", result.source_status_counts, limit=limit, out=out)
    print_counter("Plain review tracks", result.review_track_counts, limit=limit, out=out)
    print_counter("Plain relation shapes", result.relation_shape_counts, limit=limit, out=out)
    print_counter("Plain filter shapes", result.predicate_shape_counts, limit=limit, out=out)
    print_counter("Plain aggregate shapes", result.aggregate_shape_counts, limit=limit, out=out)
    print_counter("Plain set-operation shapes", result.set_shape_counts, limit=limit, out=out)
    print_counter(
        "Plain nested-query shapes", result.nested_query_shape_counts, limit=limit, out=out
    )
    print("Top plain structural groups:", file=out)
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
            "Build a raw-free matrix for plain SQL optimizer structural-review cases. "
            "The output contains only safe shape categories and never source SQL."
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
        result = audit_plain_shapes(args.summary, recompute_support=not args.use_stored_support)
    except AuditInputError as exc:
        print(f"optimizer plain-shape audit failed: {exc}", file=sys.stderr)
        return 2
    print_result(result, limit=max(1, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
