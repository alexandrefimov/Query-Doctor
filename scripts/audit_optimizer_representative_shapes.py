#!/usr/bin/env python3
"""Print raw-free representative optimizer structural shapes."""

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
from query_doctor.optimizer.sql_shape import (  # noqa: E402
    analyze_cte_shape,
    analyze_derived_table_shape,
    top_level_join_signature,
    top_level_keyword_count,
)
from query_doctor.recent.query_optimization_score import optimizer_rewriteability_rank  # noqa: E402
from scripts.audit_optimizer_funnel import (  # noqa: E402
    AuditInputError,
    SupportView,
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
    blocker_key,
    is_structural_review_case,
    shape_descriptor,
    support_actionability,
)


@dataclass(frozen=True)
class SourceShapeSummary:
    source_status: str = "unavailable"
    sql_length_bucket: str = "unknown"
    top_level_join_count: int = 0
    top_level_set_op_count: int = 0
    top_level_where_count: int = 0
    top_level_group_count: int = 0
    top_level_having_count: int = 0
    top_level_order_count: int = 0
    top_level_limit_count: int = 0
    cte_count: int = 0
    cte_graph_shape: str = "no_cte"
    cte_dependency_edge_count: int = 0
    cte_final_ref_count: int = 0
    cte_max_consumer_count: int = 0
    cte_single_use_count: int = 0
    cte_pass_through_count: int = 0
    cte_predicate_pushdown_status: str = "no_cte"
    cte_simplification_status: str = "no_cte"
    cte_predicate_origin_status: str = "no_cte"
    cte_predicate_path_status: str = "no_cte"
    cte_projection_preservation_status: str = "no_cte"
    cte_union_branch_count: int = 0
    cte_union_branch_filter_status: str = "no_union_all"
    cte_boundary_reasons: tuple[str, ...] = ()
    derived_table_count: int = 0
    derived_predicate_pushdown_status: str = "no_derived_table"
    derived_projection_preservation_status: str = "no_derived_table"
    derived_boundary_reasons: tuple[str, ...] = ()
    plain_feature_cluster: str = "unknown"


@dataclass(frozen=True)
class RepresentativeCase:
    workload: str
    primary: str
    candidate_reason: str
    support_source: str
    status: str
    bucket: str
    rank: int
    actionability: str
    blocker: str
    family: str
    decision_shape: str
    source_shape: SourceShapeSummary


@dataclass
class RepresentativeGroup:
    key: str
    count: int = 0
    workloads: Counter[str] = field(default_factory=Counter)
    primary_labels: Counter[str] = field(default_factory=Counter)
    candidate_reasons: Counter[str] = field(default_factory=Counter)
    risk_modes: Counter[str] = field(default_factory=Counter)
    cases: list[RepresentativeCase] = field(default_factory=list)


@dataclass
class RepresentativeShapesResult:
    summary_name: str
    total_cases: int = 0
    audited_cases: int = 0
    structural_cases: int = 0
    group_count: int = 0
    groups: list[RepresentativeGroup] = field(default_factory=list)


def audit_representative_shapes(
    summary_path: Path,
    *,
    recompute_support: bool = True,
    group_limit: int = 8,
    cases_per_group: int = 2,
) -> RepresentativeShapesResult:
    summary_path = summary_path.resolve(strict=True)
    cases = summary_cases(load_summary(summary_path))
    grouped: dict[str, RepresentativeGroup] = {}
    result = RepresentativeShapesResult(summary_name=summary_path.name, total_cases=len(cases))

    for case in cases:
        result.audited_cases += 1
        support, support_source = support_for_case(
            case,
            summary_path=summary_path,
            recompute_support=recompute_support,
        )
        payload = support_actionability_payload(support)
        rank = optimizer_rewriteability_rank(payload)
        actionability = support_actionability(support, payload)
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
        decision_shape = shape_descriptor(
            support,
            case=case,
            summary_path=summary_path,
            source_sql=plain_source_sql,
        )
        group_key = (
            f"rank={rank}; actionability={actionability}; "
            f"bucket={support.rewriteability_bucket}; family={family}; "
            f"blocker={blocker}; shape={decision_shape}"
        )
        group = grouped.setdefault(group_key, RepresentativeGroup(key=group_key))
        result.structural_cases += 1
        group.count += 1
        workload = workload_key(case)
        primary = primary_label(case)
        reason = first_candidate_reason(case)
        group.workloads[workload] += 1
        group.primary_labels[primary] += 1
        group.candidate_reasons[reason] += 1
        group.risk_modes[support.risk_mode or "unknown"] += 1
        group.cases.append(
            RepresentativeCase(
                workload=workload,
                primary=primary,
                candidate_reason=reason,
                support_source=support_source,
                status=support.status,
                bucket=support.rewriteability_bucket,
                rank=rank,
                actionability=actionability,
                blocker=blocker,
                family=family,
                decision_shape=decision_shape,
                source_shape=source_shape_summary(case, support, summary_path=summary_path),
            )
        )

    sorted_groups = sorted(grouped.values(), key=lambda item: (-item.count, item.key))
    result.group_count = len(sorted_groups)
    result.groups = [
        limit_representatives(group, limit=max(1, cases_per_group))
        for group in sorted_groups[: max(1, group_limit)]
    ]
    return result


def limit_representatives(group: RepresentativeGroup, *, limit: int) -> RepresentativeGroup:
    selected: list[RepresentativeCase] = []
    seen_workloads: set[str] = set()
    for case in group.cases:
        if len(selected) >= limit:
            break
        if case.workload != "<none>" and case.workload in seen_workloads:
            continue
        selected.append(case)
        seen_workloads.add(case.workload)
    if len(selected) < limit:
        for case in group.cases:
            if len(selected) >= limit:
                break
            if case in selected:
                continue
            selected.append(case)
    return RepresentativeGroup(
        key=group.key,
        count=group.count,
        workloads=group.workloads,
        primary_labels=group.primary_labels,
        candidate_reasons=group.candidate_reasons,
        risk_modes=group.risk_modes,
        cases=selected,
    )


def source_shape_summary(
    case: dict[str, object],
    support: SupportView,
    *,
    summary_path: Path,
) -> SourceShapeSummary:
    source_sql = source_sql_for_case(case, summary_path=summary_path)
    if not source_sql:
        return SourceShapeSummary()
    try:
        cte = analyze_cte_shape(source_sql)
        derived = analyze_derived_table_shape(source_sql)
        return SourceShapeSummary(
            source_status="available",
            sql_length_bucket=length_bucket(source_sql),
            top_level_join_count=len(top_level_join_signature(source_sql)),
            top_level_set_op_count=sum(
                top_level_keyword_count(source_sql, keyword)
                for keyword in ("UNION", "EXCEPT", "INTERSECT")
            ),
            top_level_where_count=top_level_keyword_count(source_sql, "WHERE"),
            top_level_group_count=top_level_keyword_count(source_sql, "GROUP"),
            top_level_having_count=top_level_keyword_count(source_sql, "HAVING"),
            top_level_order_count=top_level_keyword_count(source_sql, "ORDER"),
            top_level_limit_count=top_level_keyword_count(source_sql, "LIMIT"),
            cte_count=cte.cte_count,
            cte_graph_shape=cte.graph_shape,
            cte_dependency_edge_count=cte.dependency_edge_count,
            cte_final_ref_count=cte.final_ref_count,
            cte_max_consumer_count=cte.max_consumer_count,
            cte_single_use_count=cte.single_use_cte_count,
            cte_pass_through_count=cte.pass_through_cte_count,
            cte_predicate_pushdown_status=cte.predicate_pushdown_status,
            cte_simplification_status=cte.simplification_status,
            cte_predicate_origin_status=cte.predicate_origin_status,
            cte_predicate_path_status=cte.predicate_path_status,
            cte_projection_preservation_status=cte.projection_preservation_status,
            cte_union_branch_count=cte.union_branch_count,
            cte_union_branch_filter_status=cte.union_branch_filter_status,
            cte_boundary_reasons=cte.boundary_reasons,
            derived_table_count=derived.derived_table_count,
            derived_predicate_pushdown_status=derived.predicate_pushdown_status,
            derived_projection_preservation_status=derived.projection_preservation_status,
            derived_boundary_reasons=derived.boundary_reasons,
            plain_feature_cluster=plain_feature_cluster(source_sql, support),
        )
    except (OptimizerSqlError, ValueError):
        return SourceShapeSummary(source_status="parse_limited")


def plain_feature_cluster(source_sql: str, support: SupportView) -> str:
    if shape_family(support) != "plain":
        return "not_plain"
    return sql_feature_cluster(source_sql)


def print_result(
    result: RepresentativeShapesResult,
    *,
    out: TextIO | None = None,
) -> None:
    out = out or sys.stdout
    print(f"Summary: {result.summary_name}", file=out)
    print(
        f"Cases: total={result.total_cases}, audited={result.audited_cases}, "
        f"structural_review={result.structural_cases}, groups={result.group_count}",
        file=out,
    )
    print("Representative structural groups:", file=out)
    if not result.groups:
        print("  <none>", file=out)
        return
    for index, group in enumerate(result.groups, start=1):
        print(f"  {index}. cases={group.count}; {group.key}", file=out)
        print(f"     common={common_group_summary(group)}", file=out)
        for case_index, case in enumerate(group.cases, start=1):
            print(
                f"     representative {case_index}: {representative_case_summary(case)}", file=out
            )
            print(f"       parsed_shape={source_shape_text(case.source_shape)}", file=out)


def common_group_summary(group: RepresentativeGroup) -> str:
    return "; ".join(
        [
            f"workloads={counter_text(group.workloads, limit=3)}",
            f"primary={counter_text(group.primary_labels, limit=3)}",
            f"reason={counter_text(group.candidate_reasons, limit=2)}",
            f"risk={counter_text(group.risk_modes, limit=2)}",
        ]
    )


def representative_case_summary(case: RepresentativeCase) -> str:
    return "; ".join(
        [
            f"workload={case.workload}",
            f"primary={case.primary}",
            f"reason={case.candidate_reason}",
            f"support={case.support_source}",
            f"status={case.status}",
            f"bucket={case.bucket}",
            f"rank={case.rank}",
            f"actionability={case.actionability}",
            f"blocker={case.blocker}",
            f"family={case.family}",
            f"decision_shape={case.decision_shape}",
        ]
    )


def source_shape_text(shape: SourceShapeSummary) -> str:
    if shape.source_status != "available":
        return f"source={shape.source_status}"
    parts = [
        "source=available",
        f"len={shape.sql_length_bucket}",
        f"joins={shape.top_level_join_count}",
        f"set_ops={shape.top_level_set_op_count}",
        f"where={shape.top_level_where_count}",
        f"group={shape.top_level_group_count}",
        f"having={shape.top_level_having_count}",
        f"order={shape.top_level_order_count}",
        f"limit={shape.top_level_limit_count}",
        f"cte_count={shape.cte_count}",
        f"cte_graph={shape.cte_graph_shape}",
        f"cte_edges={shape.cte_dependency_edge_count}",
        f"cte_final_refs={shape.cte_final_ref_count}",
        f"cte_max_consumers={shape.cte_max_consumer_count}",
        f"cte_single_use={shape.cte_single_use_count}",
        f"cte_pass_through={shape.cte_pass_through_count}",
        f"cte_pushdown={shape.cte_predicate_pushdown_status}",
        f"cte_simplification={shape.cte_simplification_status}",
        f"cte_predicate_origin={shape.cte_predicate_origin_status}",
        f"cte_predicate_path={shape.cte_predicate_path_status}",
        f"cte_projection={shape.cte_projection_preservation_status}",
        f"cte_union_branches={shape.cte_union_branch_count}",
        f"cte_union_filter={shape.cte_union_branch_filter_status}",
        f"cte_boundary={tuple_text(shape.cte_boundary_reasons)}",
        f"derived_count={shape.derived_table_count}",
        f"derived_pushdown={shape.derived_predicate_pushdown_status}",
        f"derived_projection={shape.derived_projection_preservation_status}",
        f"derived_boundary={tuple_text(shape.derived_boundary_reasons)}",
    ]
    if shape.plain_feature_cluster != "not_plain":
        parts.append(f"plain_features={shape.plain_feature_cluster}")
    return "; ".join(parts)


def counter_text(counter: Counter[str], *, limit: int) -> str:
    if not counter:
        return "<none>"
    return ", ".join(f"{key}={count}" for key, count in counter.most_common(limit))


def tuple_text(values: tuple[str, ...]) -> str:
    return "+".join(values) if values else "<none>"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print raw-free representative structural optimizer shapes from an existing "
            "batch_summary.json. The output contains only aggregate categories and "
            "shape counts, never source SQL or case paths."
        )
    )
    parser.add_argument("summary", type=Path, help="Path to batch_summary.json")
    parser.add_argument(
        "--use-stored-support",
        action="store_true",
        help="Use optimizer_rewrite_support already present in the summary instead of recomputing.",
    )
    parser.add_argument("--groups", type=int, default=8, help="Structural groups to print.")
    parser.add_argument(
        "--cases-per-group",
        type=int,
        default=2,
        help="Representative cases to print per structural group.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        result = audit_representative_shapes(
            args.summary,
            recompute_support=not args.use_stored_support,
            group_limit=args.groups,
            cases_per_group=args.cases_per_group,
        )
    except AuditInputError as exc:
        print(f"optimizer representative-shape audit failed: {exc}", file=sys.stderr)
        return 2
    print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
