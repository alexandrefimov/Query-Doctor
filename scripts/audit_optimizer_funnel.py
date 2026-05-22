#!/usr/bin/env python3
"""Audit optimizer rewrite-support funnel for an existing batch summary."""

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

from query_doctor.cli.optimize_query import (  # noqa: E402
    extract_optimizable_source_sql,
    read_source_sql,
)
from query_doctor.optimizer.source_sql import QueryOptimizationError  # noqa: E402
from query_doctor.optimizer.sql import OptimizerSqlError  # noqa: E402
from query_doctor.recent.optimizer_rewrite_support import (  # noqa: E402
    OptimizerRewriteSupport,
    classify_optimizer_rewrite_support,
)
from query_doctor.recent.query_optimization_score import (  # noqa: E402
    QueryOptimizationCandidateScore,
)


REVIEW_STATUSES = {"guidance_only", "draft_disabled", "source_unavailable"}
SAFE_PRIMARY_LABELS = {
    "mixed",
    "runtime_admission",
    "runtime_data_movement",
    "runtime_skew",
    "runtime_storage",
    "sql_shape",
    "stats",
    "unknown",
}
WORKLOAD_FINGERPRINT_RE = re.compile(r"^wf_[0-9a-f]{24}$")


@dataclass(frozen=True)
class StoredStatsCandidate:
    tier: str


@dataclass(frozen=True)
class SupportView:
    status: str
    reason: str
    rewriteability_bucket: str
    draft_eligibility: str
    risk_mode: str
    risk_reasons: tuple[str, ...]
    cte_count: int = 0
    cte_graph_shape: str = "no_cte"
    cte_predicate_pushdown_status: str = "no_cte"
    cte_simplification_status: str = "no_cte"
    cte_predicate_origin_status: str = "no_cte"
    cte_predicate_path_status: str = "no_cte"
    cte_projection_preservation_status: str = "no_cte"
    cte_boundary_reasons: tuple[str, ...] = ()
    derived_table_count: int = 0
    derived_predicate_pushdown_status: str = "no_derived_table"
    derived_predicate_origin_status: str = "no_derived_table"
    derived_projection_preservation_status: str = "no_derived_table"
    derived_boundary_reasons: tuple[str, ...] = ()


@dataclass
class WorkloadRollup:
    key: str
    count: int = 0
    shape_families: Counter[str] = field(default_factory=Counter)
    primary_labels: Counter[str] = field(default_factory=Counter)
    candidate_reasons: Counter[str] = field(default_factory=Counter)
    feature_clusters: Counter[str] = field(default_factory=Counter)


@dataclass
class OptimizerFunnelAuditResult:
    summary_name: str
    total_cases: int = 0
    audited_cases: int = 0
    support_source_counts: Counter[str] = field(default_factory=Counter)
    severity_counts: Counter[str] = field(default_factory=Counter)
    status_counts: Counter[str] = field(default_factory=Counter)
    bucket_counts: Counter[str] = field(default_factory=Counter)
    status_bucket_counts: Counter[str] = field(default_factory=Counter)
    severity_status_bucket_counts: Counter[str] = field(default_factory=Counter)
    review_reason_counts: Counter[str] = field(default_factory=Counter)
    review_primary_counts: Counter[str] = field(default_factory=Counter)
    review_risk_mode_counts: Counter[str] = field(default_factory=Counter)
    review_risk_reason_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_family_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_hint_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_family_reason_counts: Counter[str] = field(default_factory=Counter)
    plain_feature_cluster_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_workloads: dict[str, WorkloadRollup] = field(default_factory=dict)


class AuditInputError(RuntimeError):
    """Raised when the summary file is not usable for optimizer funnel audit."""


def load_summary(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AuditInputError(f"cannot read summary: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AuditInputError(f"summary is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise AuditInputError(f"summary root is not an object: {path}")
    if not isinstance(payload.get("cases"), list):
        raise AuditInputError(f"summary does not contain a cases list: {path}")
    return payload


def summary_cases(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [case for case in summary.get("cases") or [] if isinstance(case, dict)]


def audit_summary(
    summary_path: Path,
    *,
    recompute_support: bool = True,
) -> OptimizerFunnelAuditResult:
    summary_path = summary_path.resolve(strict=True)
    cases = summary_cases(load_summary(summary_path))
    result = OptimizerFunnelAuditResult(summary_name=summary_path.name, total_cases=len(cases))

    for case in cases:
        result.audited_cases += 1
        severity = safe_token(case.get("score_severity"), default="unknown")
        primary = primary_label(case)
        support, support_source = support_for_case(
            case,
            summary_path=summary_path,
            recompute_support=recompute_support,
        )
        result.support_source_counts[support_source] += 1
        result.severity_counts[severity] += 1
        result.status_counts[support.status] += 1
        result.bucket_counts[support.rewriteability_bucket] += 1
        result.status_bucket_counts[f"{support.status}:{support.rewriteability_bucket}"] += 1
        result.severity_status_bucket_counts[
            f"{severity}:{support.status}:{support.rewriteability_bucket}"
        ] += 1

        if support.status in REVIEW_STATUSES:
            result.review_reason_counts[support.reason or "<missing>"] += 1
            result.review_primary_counts[primary] += 1
            result.review_risk_mode_counts[support.risk_mode or "unknown"] += 1
            result.review_risk_reason_counts.update(support.risk_reasons)

        if support.status == "guidance_only" and support.draft_eligibility == "no_recipe":
            collect_no_recipe_case(result, case, support, primary, summary_path=summary_path)

    return result


def support_for_case(
    case: dict[str, Any],
    *,
    summary_path: Path,
    recompute_support: bool,
) -> tuple[SupportView, str]:
    if not recompute_support:
        return support_view_from_dict(case.get("optimizer_rewrite_support")), "stored"
    candidate = candidate_from_dict(case.get("query_optimization_candidate"))
    case_dir = actual_case_dir(case, summary_path=summary_path)
    facts_text = read_analysis_facts(case_dir)
    support = classify_optimizer_rewrite_support(
        case_dir,
        candidate,
        facts_text,
        primary_bottleneck=case.get("case_primary_bottleneck"),
        stats_candidate=stats_candidate_from_dict(case.get("stats_optimization_candidate")),
    )
    return support_view_from_support(support), "recomputed"


def actual_case_dir(case: dict[str, Any], *, summary_path: Path) -> Path | None:
    raw = case.get("case_dir")
    if not raw:
        return None
    path = Path(str(raw))
    if not path.is_absolute():
        path = summary_path.parent / path
    if (path / "analysis_facts.md").exists():
        return path
    if path.exists():
        for child in path.iterdir():
            if child.is_dir() and (child / "analysis_facts.md").exists():
                return child
    return path


def read_analysis_facts(case_dir: Path | None) -> str:
    if case_dir is None:
        return ""
    facts_path = case_dir / "analysis_facts.md"
    try:
        return facts_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def candidate_from_dict(value: Any) -> QueryOptimizationCandidateScore | None:
    if not isinstance(value, dict):
        return None
    return QueryOptimizationCandidateScore(
        score=int_value(value.get("score")),
        tier=safe_token(value.get("tier"), default="not_likely"),
        confidence=safe_token(value.get("confidence"), default="low"),
        impact=safe_token(value.get("impact"), default="low"),
        reasons=tuple(safe_reason_list(value.get("reasons"))),
        counter_signals=tuple(safe_reason_list(value.get("counter_signals"))),
        suggested_review_areas=tuple(safe_reason_list(value.get("suggested_review_areas"))),
    )


def stats_candidate_from_dict(value: Any) -> StoredStatsCandidate | None:
    if not isinstance(value, dict):
        return None
    return StoredStatsCandidate(tier=safe_token(value.get("tier"), default="not_likely"))


def support_view_from_support(support: OptimizerRewriteSupport) -> SupportView:
    return SupportView(
        status=safe_token(support.status, default="unknown"),
        reason=safe_reason(support.reason),
        rewriteability_bucket=safe_token(support.rewriteability_bucket, default="unknown"),
        draft_eligibility=safe_token(support.draft_eligibility, default="unknown"),
        risk_mode=safe_token(support.risk_mode, default="unknown"),
        risk_reasons=tuple(safe_reason_list(support.risk_reasons)),
        cte_count=int_value(support.cte_count),
        cte_graph_shape=safe_token(support.cte_graph_shape, default="no_cte"),
        cte_predicate_pushdown_status=safe_token(
            support.cte_predicate_pushdown_status, default="no_cte"
        ),
        cte_simplification_status=safe_token(support.cte_simplification_status, default="no_cte"),
        cte_predicate_origin_status=safe_token(
            support.cte_predicate_origin_status, default="no_cte"
        ),
        cte_predicate_path_status=safe_token(support.cte_predicate_path_status, default="no_cte"),
        cte_projection_preservation_status=safe_token(
            support.cte_projection_preservation_status, default="no_cte"
        ),
        cte_boundary_reasons=tuple(safe_reason_list(support.cte_boundary_reasons)),
        derived_table_count=int_value(support.derived_table_count),
        derived_predicate_pushdown_status=safe_token(
            support.derived_predicate_pushdown_status, default="no_derived_table"
        ),
        derived_predicate_origin_status=safe_token(
            support.derived_predicate_origin_status, default="no_derived_table"
        ),
        derived_projection_preservation_status=safe_token(
            support.derived_projection_preservation_status, default="no_derived_table"
        ),
        derived_boundary_reasons=tuple(safe_reason_list(support.derived_boundary_reasons)),
    )


def support_view_from_dict(value: Any) -> SupportView:
    support = value if isinstance(value, dict) else {}
    return SupportView(
        status=safe_token(support.get("status"), default="unknown"),
        reason=safe_reason(support.get("reason")),
        rewriteability_bucket=safe_token(support.get("rewriteability_bucket"), default="unknown"),
        draft_eligibility=safe_token(support.get("draft_eligibility"), default="unknown"),
        risk_mode=safe_token(support.get("risk_mode"), default="unknown"),
        risk_reasons=tuple(safe_reason_list(support.get("risk_reasons"))),
        cte_count=int_value(support.get("cte_count")),
        cte_graph_shape=safe_token(support.get("cte_graph_shape"), default="no_cte"),
        cte_predicate_pushdown_status=safe_token(
            support.get("cte_predicate_pushdown_status"), default="no_cte"
        ),
        cte_simplification_status=safe_token(
            support.get("cte_simplification_status"), default="no_cte"
        ),
        cte_predicate_origin_status=safe_token(
            support.get("cte_predicate_origin_status"), default="no_cte"
        ),
        cte_predicate_path_status=safe_token(
            support.get("cte_predicate_path_status"), default="no_cte"
        ),
        cte_projection_preservation_status=safe_token(
            support.get("cte_projection_preservation_status"), default="no_cte"
        ),
        cte_boundary_reasons=tuple(safe_reason_list(support.get("cte_boundary_reasons"))),
        derived_table_count=int_value(support.get("derived_table_count")),
        derived_predicate_pushdown_status=safe_token(
            support.get("derived_predicate_pushdown_status"), default="no_derived_table"
        ),
        derived_predicate_origin_status=safe_token(
            support.get("derived_predicate_origin_status"), default="no_derived_table"
        ),
        derived_projection_preservation_status=safe_token(
            support.get("derived_projection_preservation_status"), default="no_derived_table"
        ),
        derived_boundary_reasons=tuple(safe_reason_list(support.get("derived_boundary_reasons"))),
    )


def collect_no_recipe_case(
    result: OptimizerFunnelAuditResult,
    case: dict[str, Any],
    support: SupportView,
    primary: str,
    *,
    summary_path: Path,
) -> None:
    family = shape_family(support)
    hint = recipe_hint(support)
    candidate_reason = first_candidate_reason(case)
    result.no_recipe_family_counts[family] += 1
    result.no_recipe_hint_counts[hint] += 1
    result.no_recipe_family_reason_counts[f"{family}:{support.reason or '<missing>'}"] += 1
    workload = workload_key(case)
    rollup = result.no_recipe_workloads.setdefault(workload, WorkloadRollup(key=workload))
    rollup.count += 1
    rollup.shape_families[family] += 1
    rollup.primary_labels[primary] += 1
    rollup.candidate_reasons[candidate_reason] += 1
    if family == "plain":
        cluster = sql_feature_cluster(source_sql_for_case(case, summary_path=summary_path))
        result.plain_feature_cluster_counts[cluster] += 1
        rollup.feature_clusters[cluster] += 1


def source_sql_for_case(case: dict[str, Any], *, summary_path: Path) -> str:
    case_dir = actual_case_dir(case, summary_path=summary_path)
    if case_dir is None:
        return ""
    try:
        source_sql = extract_optimizable_source_sql(read_source_sql(case_dir))
    except (OSError, OptimizerSqlError, QueryOptimizationError, ValueError):
        return ""
    return source_sql.sql


def shape_family(support: SupportView) -> str:
    if support.cte_count == 0 and support.derived_table_count == 0:
        return "plain"
    if support.cte_count and support.derived_table_count:
        return "cte_and_derived"
    if support.cte_count:
        return "cte"
    return "derived"


def recipe_hint(support: SupportView) -> str:
    if support.cte_simplification_status in {"single_use_candidate", "pass_through_candidate"}:
        return f"cte_simplification:{support.cte_simplification_status}"
    if support.cte_predicate_pushdown_status == "candidate":
        return "cte_predicate_pushdown:candidate"
    if support.derived_predicate_pushdown_status == "candidate":
        return "derived_predicate_pushdown:candidate"
    if support.cte_predicate_pushdown_status == "blocked_no_downstream_filter":
        return "cte_no_downstream_filter"
    if support.derived_predicate_pushdown_status == "blocked_no_downstream_filter":
        return "derived_no_downstream_filter"
    if support.cte_predicate_pushdown_status == "blocked_unsupported_graph":
        return "cte_unsupported_graph"
    if support.derived_predicate_pushdown_status == "blocked_unsupported_shape":
        return "derived_unsupported_shape"
    return "no_specific_recipe_hint"


def sql_feature_cluster(sql: str) -> str:
    lower = strip_string_literals(sql).lower()
    features = {
        "joins": count_pattern(lower, r"\bjoin\b", cap=5),
        "left": count_pattern(lower, r"\bleft\s+(?:outer\s+)?join\b", cap=3),
        "where": count_pattern(lower, r"\bwhere\b", cap=3),
        "group": count_pattern(lower, r"\bgroup\s+by\b", cap=3),
        "having": count_pattern(lower, r"\bhaving\b", cap=2),
        "window": count_pattern(lower, r"\bover\s*\(", cap=3),
        "distinct": count_pattern(lower, r"\bdistinct\b", cap=2),
        "union": count_pattern(lower, r"\bunion\b", cap=2),
        "aggs": count_pattern(lower, r"\b(?:sum|count|avg|min|max)\s*\(", cap=5),
        "case": count_pattern(lower, r"\bcase\b", cap=3),
        "len": length_bucket(sql),
    }
    return "; ".join(f"{key}={value}" for key, value in features.items())


def strip_string_literals(sql: str) -> str:
    return re.sub(r"'(?:''|[^'])*'", "''", sql or "")


def count_pattern(text: str, pattern: str, *, cap: int) -> int:
    return min(len(re.findall(pattern, text)), cap)


def length_bucket(sql: str) -> str:
    size = len(sql or "")
    if size < 2_000:
        return "short"
    if size < 10_000:
        return "medium"
    return "long"


def workload_key(case: dict[str, Any]) -> str:
    raw = str(case.get("group_fingerprint") or case.get("workload_fingerprint") or "").strip()
    if not WORKLOAD_FINGERPRINT_RE.fullmatch(raw):
        return "<none>"
    return f"wf_...{raw[-8:]}"


def primary_label(case: dict[str, Any]) -> str:
    primary = case.get("case_primary_bottleneck")
    primary = primary if isinstance(primary, dict) else {}
    label = safe_token(primary.get("label"), default="unknown")
    return label if label in SAFE_PRIMARY_LABELS else "unknown"


def first_candidate_reason(case: dict[str, Any]) -> str:
    candidate = case.get("query_optimization_candidate")
    candidate = candidate if isinstance(candidate, dict) else {}
    reasons = safe_reason_list(candidate.get("reasons"))
    return reasons[0] if reasons else "<none>"


def safe_token(value: Any, *, default: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return default
    return re.sub(r"[^a-z0-9_+.-]+", "_", text)[:80] or default


def safe_reason(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"(?<![A-Za-z0-9_])(?:/Users/|/private/tmp/|/tmp/)[^\s,;)]*", "<path>", text)
    text = re.sub(r"\b(?:SELECT|WITH|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)\b.*", "<sql>", text)
    return text[:240]


def safe_reason_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [safe_reason(item) for item in value if safe_reason(item)]


def int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


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


def print_workload_rollups(
    rollups: Iterable[WorkloadRollup],
    *,
    limit: int,
    out: TextIO,
) -> None:
    print("Top no-recipe workload groups:", file=out)
    sorted_rollups = sorted(rollups, key=lambda item: item.count, reverse=True)
    if not sorted_rollups:
        print("  <none>", file=out)
        return
    for rollup in sorted_rollups[:limit]:
        primary = ", ".join(f"{key}={count}" for key, count in rollup.primary_labels.most_common(3))
        family = ", ".join(f"{key}={count}" for key, count in rollup.shape_families.most_common(3))
        reason = ", ".join(
            f"{key}={count}" for key, count in rollup.candidate_reasons.most_common(2)
        )
        features = ", ".join(
            f"{key}={count}" for key, count in rollup.feature_clusters.most_common(1)
        )
        print(
            f"  {rollup.key}: cases={rollup.count}; family={family}; "
            f"primary={primary}; reason={reason}; features={features or '<none>'}",
            file=out,
        )


def print_result(
    result: OptimizerFunnelAuditResult,
    *,
    limit: int = 12,
    out: TextIO | None = None,
) -> None:
    out = out or sys.stdout
    print(f"Summary: {result.summary_name}", file=out)
    print(f"Cases: total={result.total_cases}, audited={result.audited_cases}", file=out)
    print_counter("Support source", result.support_source_counts, limit=limit, out=out)
    print_counter("Severity", result.severity_counts, limit=limit, out=out)
    print_counter("Optimizer status", result.status_counts, limit=limit, out=out)
    print_counter("Rewriteability buckets", result.bucket_counts, limit=limit, out=out)
    print_counter("Status / bucket", result.status_bucket_counts, limit=limit, out=out)
    print_counter(
        "Severity / status / bucket",
        result.severity_status_bucket_counts,
        limit=limit,
        out=out,
    )
    print_counter("Review primary labels", result.review_primary_counts, limit=limit, out=out)
    print_counter("Review reasons", result.review_reason_counts, limit=limit, out=out)
    print_counter("Review risk modes", result.review_risk_mode_counts, limit=limit, out=out)
    print_counter("Review risk reasons", result.review_risk_reason_counts, limit=limit, out=out)
    print_counter("No-recipe shape families", result.no_recipe_family_counts, limit=limit, out=out)
    print_counter("No-recipe hints", result.no_recipe_hint_counts, limit=limit, out=out)
    print_counter(
        "No-recipe family / reason",
        result.no_recipe_family_reason_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "Plain no-recipe feature clusters",
        result.plain_feature_cluster_counts,
        limit=limit,
        out=out,
    )
    print_workload_rollups(result.no_recipe_workloads.values(), limit=limit, out=out)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit optimizer rewrite-support funnel for an existing batch_summary.json. "
            "The audit prints aggregate shape/status data only and never prints source SQL."
        )
    )
    parser.add_argument("summary", type=Path, help="Path to batch_summary.json")
    parser.add_argument(
        "--use-stored-support",
        action="store_true",
        help="Use optimizer_rewrite_support already present in the summary instead of recomputing.",
    )
    parser.add_argument("--limit", type=int, default=12, help="Rows to print per counter.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        result = audit_summary(args.summary, recompute_support=not args.use_stored_support)
    except AuditInputError as exc:
        print(f"optimizer funnel audit failed: {exc}", file=sys.stderr)
        return 2
    print_result(result, limit=max(1, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
