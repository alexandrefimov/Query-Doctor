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
    NO_RECIPE_REVIEW_TRACKS,
    OptimizerRewriteSupport,
    classify_optimizer_rewrite_support,
)
from query_doctor.recent.query_optimization_score import (  # noqa: E402
    QueryOptimizationCandidateScore,
    optimizer_adjacent_actionability,
    optimizer_no_draft_actionability,
    optimizer_rewriteability_rank,
)
from query_doctor.report.safety_validation import contains_raw_sql_like_text  # noqa: E402
from query_doctor.safety import redaction  # noqa: E402
from query_doctor.web.presenters.optimizer_facts import (  # noqa: E402
    optimizer_no_recipe_change_direction,
    optimizer_no_recipe_review_area,
    optimizer_no_recipe_review_track_label,
    optimizer_no_recipe_verification,
    optimizer_no_recipe_workload_metric,
)
from query_doctor.web.presenters.recent_scan_action_candidates import (  # noqa: E402
    optimizer_rewrite_support_text,
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
REPEATED_NO_RECIPE_READINESS_GAPS = {
    "missing_track",
    "mixed_tracks",
    "source_unavailable",
    "unknown_track",
}
REPEATED_NO_RECIPE_GUIDANCE_GAPS = {
    "missing_change_direction",
    "missing_review_area",
    "missing_verification",
    "missing_workload_metric",
    "raw_like_candidate_reason",
    "weak_workload_metric",
    "weak_verification",
    "weak_no_draft_contract",
}
MIXED_NO_RECIPE_REVIEW_TRACK = "mixed_query_shape_review"
NO_RECIPE_REVIEW_TRACK_UNREADY = {"not_applicable", "source_unavailable", "unknown"}
SUMMARY_SCHEMA_VERSION = "optimizer_funnel_audit_v1"
URL_RE = re.compile(r"\bhttps?://", re.IGNORECASE)
LOCAL_PATH_RE = re.compile(r"(?<![\w/])(?:/private)?/tmp/|(?<![\w/])/Users/")


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
    recipe_id: str = ""
    draft_unavailable_class: str = "not_applicable"
    draft_unavailable_reasons: tuple[str, ...] = ()
    no_recipe_review_track: str = "not_applicable"
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
    review_tracks: Counter[str] = field(default_factory=Counter)
    cte_graph_shapes: Counter[str] = field(default_factory=Counter)
    cte_predicate_pushdown_statuses: Counter[str] = field(default_factory=Counter)
    cte_simplification_statuses: Counter[str] = field(default_factory=Counter)
    derived_predicate_pushdown_statuses: Counter[str] = field(default_factory=Counter)
    risk_modes: Counter[str] = field(default_factory=Counter)


@dataclass(frozen=True)
class OptimizerFunnelIssue:
    category: str
    message: str


@dataclass
class OptimizerFunnelAuditResult:
    summary_name: str
    total_cases: int = 0
    audited_cases: int = 0
    support_source_counts: Counter[str] = field(default_factory=Counter)
    severity_counts: Counter[str] = field(default_factory=Counter)
    candidate_tier_counts: Counter[str] = field(default_factory=Counter)
    candidate_confidence_counts: Counter[str] = field(default_factory=Counter)
    candidate_score_band_counts: Counter[str] = field(default_factory=Counter)
    medium_high_candidate_primary_counts: Counter[str] = field(default_factory=Counter)
    medium_high_candidate_reason_counts: Counter[str] = field(default_factory=Counter)
    medium_high_candidate_counter_signal_counts: Counter[str] = field(default_factory=Counter)
    medium_high_candidate_status_bucket_counts: Counter[str] = field(default_factory=Counter)
    status_counts: Counter[str] = field(default_factory=Counter)
    bucket_counts: Counter[str] = field(default_factory=Counter)
    effective_rewriteability_rank_counts: Counter[str] = field(default_factory=Counter)
    status_bucket_counts: Counter[str] = field(default_factory=Counter)
    severity_status_bucket_counts: Counter[str] = field(default_factory=Counter)
    adjacent_actionability_counts: Counter[str] = field(default_factory=Counter)
    no_draft_actionability_counts: Counter[str] = field(default_factory=Counter)
    review_reason_counts: Counter[str] = field(default_factory=Counter)
    review_primary_counts: Counter[str] = field(default_factory=Counter)
    review_risk_mode_counts: Counter[str] = field(default_factory=Counter)
    review_risk_reason_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_family_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_hint_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_review_track_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_family_reason_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_cte_graph_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_cte_predicate_pushdown_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_cte_simplification_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_cte_boundary_reason_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_derived_predicate_pushdown_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_derived_boundary_reason_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_risk_mode_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_risk_reason_counts: Counter[str] = field(default_factory=Counter)
    repeated_no_recipe_review_track_counts: Counter[str] = field(default_factory=Counter)
    repeated_no_recipe_review_readiness_counts: Counter[str] = field(default_factory=Counter)
    repeated_no_recipe_guidance_readiness_counts: Counter[str] = field(default_factory=Counter)
    repeated_no_recipe_family_counts: Counter[str] = field(default_factory=Counter)
    plain_feature_cluster_counts: Counter[str] = field(default_factory=Counter)
    no_recipe_workloads: dict[str, WorkloadRollup] = field(default_factory=dict)
    issues: list[OptimizerFunnelIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


class AuditInputError(RuntimeError):
    """Raised when the summary file is not usable for optimizer funnel audit."""


class AuditOutputError(RuntimeError):
    """Raised when the summary output cannot be written safely."""


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
    fail_on_repeated_no_recipe_readiness_gaps: bool = False,
) -> OptimizerFunnelAuditResult:
    summary_path = summary_path.resolve(strict=True)
    cases = summary_cases(load_summary(summary_path))
    result = OptimizerFunnelAuditResult(summary_name=summary_path.name, total_cases=len(cases))

    for case in cases:
        result.audited_cases += 1
        severity = safe_token(case.get("score_severity"), default="unknown")
        primary = primary_label(case)
        collect_candidate_distribution(result, case, primary)
        support, support_source = support_for_case(
            case,
            summary_path=summary_path,
            recompute_support=recompute_support,
        )
        result.support_source_counts[support_source] += 1
        result.severity_counts[severity] += 1
        result.status_counts[support.status] += 1
        result.bucket_counts[support.rewriteability_bucket] += 1
        support_payload = support_actionability_payload(support)
        result.effective_rewriteability_rank_counts[
            str(optimizer_rewriteability_rank(support_payload))
        ] += 1
        if support.rewriteability_bucket == "recipe_adjacent_shape":
            result.adjacent_actionability_counts[
                optimizer_adjacent_actionability(support_payload)
            ] += 1
        elif support.rewriteability_bucket == "recipe_detected_no_draft":
            result.no_draft_actionability_counts[
                optimizer_no_draft_actionability(support_payload)
            ] += 1
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
        if candidate_is_medium_or_high(case):
            result.medium_high_candidate_status_bucket_counts[
                f"{support.status}:{support.rewriteability_bucket}"
            ] += 1

    populate_repeated_no_recipe_rollups(result)
    if fail_on_repeated_no_recipe_readiness_gaps:
        add_repeated_no_recipe_readiness_issues(result)
    return result


def collect_candidate_distribution(
    result: OptimizerFunnelAuditResult,
    case: dict[str, Any],
    primary: str,
) -> None:
    candidate = case.get("query_optimization_candidate")
    if not isinstance(candidate, dict):
        result.candidate_tier_counts["missing"] += 1
        result.candidate_confidence_counts["missing"] += 1
        result.candidate_score_band_counts["missing"] += 1
        return
    tier = safe_token(candidate.get("tier"), default="not_likely")
    confidence = safe_token(candidate.get("confidence"), default="unknown")
    score = int_value(candidate.get("score"))
    result.candidate_tier_counts[tier] += 1
    result.candidate_confidence_counts[confidence] += 1
    result.candidate_score_band_counts[score_band(score)] += 1
    if tier not in {"medium", "high"}:
        return
    result.medium_high_candidate_primary_counts[primary] += 1
    reasons = safe_reason_list(candidate.get("reasons"))
    counter_signals = safe_reason_list(candidate.get("counter_signals"))
    result.medium_high_candidate_reason_counts.update(reasons or ["<none>"])
    result.medium_high_candidate_counter_signal_counts.update(counter_signals or ["<none>"])


def candidate_is_medium_or_high(case: dict[str, Any]) -> bool:
    candidate = case.get("query_optimization_candidate")
    if not isinstance(candidate, dict):
        return False
    return safe_token(candidate.get("tier"), default="not_likely") in {"medium", "high"}


def score_band(score: int) -> str:
    if score <= 0:
        return "0"
    if score <= 20:
        return "1-20"
    if score < 40:
        return "21-39"
    if score < 70:
        return "40-69"
    return "70-100"


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
        recipe_id=safe_token(support.recipe_id, default=""),
        draft_unavailable_class=safe_token(
            support.draft_unavailable_class, default="not_applicable"
        ),
        draft_unavailable_reasons=tuple(safe_reason_list(support.draft_unavailable_reasons)),
        no_recipe_review_track=safe_no_recipe_review_track(support.no_recipe_review_track),
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
        recipe_id=safe_token(support.get("recipe_id"), default=""),
        draft_unavailable_class=safe_token(
            support.get("draft_unavailable_class"), default="not_applicable"
        ),
        draft_unavailable_reasons=tuple(safe_reason_list(support.get("draft_unavailable_reasons"))),
        no_recipe_review_track=safe_no_recipe_review_track(support.get("no_recipe_review_track")),
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


def support_actionability_payload(support: SupportView) -> dict[str, object]:
    return {
        "status": support.status,
        "rewriteability_bucket": support.rewriteability_bucket,
        "draft_eligibility": support.draft_eligibility,
        "recipe_id": support.recipe_id,
        "draft_unavailable_class": support.draft_unavailable_class,
        "draft_unavailable_reasons": support.draft_unavailable_reasons,
        "cte_predicate_pushdown_status": support.cte_predicate_pushdown_status,
        "cte_simplification_status": support.cte_simplification_status,
        "cte_boundary_reasons": support.cte_boundary_reasons,
        "derived_predicate_pushdown_status": support.derived_predicate_pushdown_status,
        "derived_boundary_reasons": support.derived_boundary_reasons,
    }


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
    result.no_recipe_review_track_counts[support.no_recipe_review_track or "not_applicable"] += 1
    result.no_recipe_family_reason_counts[f"{family}:{support.reason or '<missing>'}"] += 1
    result.no_recipe_risk_mode_counts[support.risk_mode or "unknown"] += 1
    result.no_recipe_risk_reason_counts.update(support.risk_reasons)
    if support.cte_count:
        result.no_recipe_cte_graph_counts[support.cte_graph_shape] += 1
        result.no_recipe_cte_predicate_pushdown_counts[support.cte_predicate_pushdown_status] += 1
        result.no_recipe_cte_simplification_counts[support.cte_simplification_status] += 1
        result.no_recipe_cte_boundary_reason_counts.update(support.cte_boundary_reasons)
    if support.derived_table_count:
        result.no_recipe_derived_predicate_pushdown_counts[
            support.derived_predicate_pushdown_status
        ] += 1
        result.no_recipe_derived_boundary_reason_counts.update(support.derived_boundary_reasons)
    workload = workload_key(case)
    rollup = result.no_recipe_workloads.setdefault(workload, WorkloadRollup(key=workload))
    rollup.count += 1
    rollup.shape_families[family] += 1
    rollup.primary_labels[primary] += 1
    rollup.candidate_reasons[candidate_reason] += 1
    rollup.risk_modes[support.risk_mode or "unknown"] += 1
    rollup.review_tracks[support.no_recipe_review_track or "not_applicable"] += 1
    if support.cte_count:
        rollup.cte_graph_shapes[support.cte_graph_shape] += 1
        rollup.cte_predicate_pushdown_statuses[support.cte_predicate_pushdown_status] += 1
        rollup.cte_simplification_statuses[support.cte_simplification_status] += 1
    if support.derived_table_count:
        rollup.derived_predicate_pushdown_statuses[support.derived_predicate_pushdown_status] += 1
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


def safe_no_recipe_review_track(value: Any) -> str:
    track = safe_token(value, default="not_applicable")
    return track if track in NO_RECIPE_REVIEW_TRACKS else "unknown"


def safe_reason(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if raw_like_summary_text(text):
        return "unsafe_reason"
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


def summary_json_payload(
    result: OptimizerFunnelAuditResult,
    *,
    workload_limit: int = 12,
) -> dict[str, object]:
    concentration = no_recipe_workload_concentration(result)
    medium = result.candidate_tier_counts.get("medium", 0)
    high = result.candidate_tier_counts.get("high", 0)
    metrics = safe_count_dict(
        {
            "total_cases": result.total_cases,
            "audited_cases": result.audited_cases,
            "medium_high_candidates": medium + high,
            "high_candidates": high,
            "medium_candidates": medium,
            "draft_supported_medium_high": draft_supported_count(
                result.medium_high_candidate_status_bucket_counts
            ),
            "issues": len(result.issues),
            **{f"no_recipe_{key}": value for key, value in concentration.items()},
        }.items(),
        include_zero=True,
    )
    payload: dict[str, object] = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": "ok" if result.ok else "issues",
        "metrics": metrics,
        "issue_counts": safe_count_dict(Counter(issue.category for issue in result.issues).items()),
        "counters": summary_counter_payload(result),
        "top_no_recipe_workloads": [
            workload_rollup_summary_json(rollup)
            for rollup in sorted(
                result.no_recipe_workloads.values(),
                key=lambda item: item.count,
                reverse=True,
            )[: max(1, workload_limit)]
        ],
    }
    return payload


def summary_counter_payload(result: OptimizerFunnelAuditResult) -> dict[str, object]:
    counters = {
        "support_source_counts": result.support_source_counts,
        "severity_counts": result.severity_counts,
        "candidate_tier_counts": result.candidate_tier_counts,
        "candidate_confidence_counts": result.candidate_confidence_counts,
        "candidate_score_band_counts": result.candidate_score_band_counts,
        "medium_high_candidate_primary_counts": result.medium_high_candidate_primary_counts,
        "medium_high_candidate_reason_counts": result.medium_high_candidate_reason_counts,
        "medium_high_candidate_counter_signal_counts": (
            result.medium_high_candidate_counter_signal_counts
        ),
        "medium_high_candidate_status_bucket_counts": (
            result.medium_high_candidate_status_bucket_counts
        ),
        "status_counts": result.status_counts,
        "rewriteability_bucket_counts": result.bucket_counts,
        "effective_rewriteability_rank_counts": result.effective_rewriteability_rank_counts,
        "status_bucket_counts": result.status_bucket_counts,
        "severity_status_bucket_counts": result.severity_status_bucket_counts,
        "recipe_adjacent_actionability_counts": result.adjacent_actionability_counts,
        "recipe_detected_no_draft_actionability_counts": result.no_draft_actionability_counts,
        "review_primary_counts": result.review_primary_counts,
        "review_reason_counts": result.review_reason_counts,
        "review_risk_mode_counts": result.review_risk_mode_counts,
        "review_risk_reason_counts": result.review_risk_reason_counts,
        "no_recipe_family_counts": result.no_recipe_family_counts,
        "no_recipe_hint_counts": result.no_recipe_hint_counts,
        "no_recipe_review_track_counts": result.no_recipe_review_track_counts,
        "no_recipe_family_reason_counts": result.no_recipe_family_reason_counts,
        "no_recipe_risk_mode_counts": result.no_recipe_risk_mode_counts,
        "no_recipe_risk_reason_counts": result.no_recipe_risk_reason_counts,
        "repeated_no_recipe_review_track_counts": (result.repeated_no_recipe_review_track_counts),
        "repeated_no_recipe_review_readiness_counts": (
            result.repeated_no_recipe_review_readiness_counts
        ),
        "repeated_no_recipe_guidance_readiness_counts": (
            result.repeated_no_recipe_guidance_readiness_counts
        ),
        "repeated_no_recipe_family_counts": result.repeated_no_recipe_family_counts,
        "no_recipe_cte_graph_counts": result.no_recipe_cte_graph_counts,
        "no_recipe_cte_predicate_pushdown_counts": result.no_recipe_cte_predicate_pushdown_counts,
        "no_recipe_cte_simplification_counts": result.no_recipe_cte_simplification_counts,
        "no_recipe_cte_boundary_reason_counts": result.no_recipe_cte_boundary_reason_counts,
        "no_recipe_derived_predicate_pushdown_counts": (
            result.no_recipe_derived_predicate_pushdown_counts
        ),
        "no_recipe_derived_boundary_reason_counts": (
            result.no_recipe_derived_boundary_reason_counts
        ),
        "plain_feature_cluster_counts": result.plain_feature_cluster_counts,
    }
    payload: dict[str, object] = {}
    for name, counter in counters.items():
        safe_name = safe_summary_key(name)
        values = safe_count_dict(counter.items())
        if safe_name and values:
            payload[safe_name] = values
    return payload


def workload_rollup_summary_json(rollup: WorkloadRollup) -> dict[str, object]:
    return {
        "workload": safe_workload_label(rollup.key),
        "cases": int_value(rollup.count),
        "shape_families": safe_count_dict(rollup.shape_families.items()),
        "primary_labels": safe_count_dict(rollup.primary_labels.items()),
        "candidate_reasons": safe_count_dict(rollup.candidate_reasons.items()),
        "feature_clusters": safe_count_dict(rollup.feature_clusters.items()),
        "review_tracks": safe_count_dict(rollup.review_tracks.items()),
        "cte_graph_shapes": safe_count_dict(rollup.cte_graph_shapes.items()),
        "cte_predicate_pushdown": safe_count_dict(rollup.cte_predicate_pushdown_statuses.items()),
        "cte_simplification": safe_count_dict(rollup.cte_simplification_statuses.items()),
        "derived_predicate_pushdown": safe_count_dict(
            rollup.derived_predicate_pushdown_statuses.items()
        ),
        "risk_modes": safe_count_dict(rollup.risk_modes.items()),
    }


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
        counts[safe_key] += max(0, int_value(value))
    return {key: value for key, value in sorted(counts.items()) if include_zero or value > 0}


def safe_summary_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if raw_like_summary_text(text):
        return "unsafe_token"
    return safe_token(text, default="")


def safe_workload_label(value: object) -> str:
    text = str(value or "").strip()
    if text == "<none>":
        return "none"
    if re.fullmatch(r"wf_\.\.\.[0-9a-f]{8}", text):
        return text
    return safe_summary_key(text) or "unknown"


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
    result: OptimizerFunnelAuditResult,
    path: Path,
    *,
    input_summary: Path,
    workload_limit: int,
) -> None:
    if same_path(path, input_summary):
        raise AuditOutputError("summary JSON output must not overwrite input summary")
    try:
        path.write_text(
            json.dumps(
                summary_json_payload(result, workload_limit=workload_limit),
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise AuditOutputError("cannot write summary JSON") from exc


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=False) == right.resolve(strict=False)
    except OSError:
        return left.absolute() == right.absolute()


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
        track = ", ".join(f"{key}={count}" for key, count in rollup.review_tracks.most_common(3))
        reason = ", ".join(
            f"{key}={count}" for key, count in rollup.candidate_reasons.most_common(2)
        )
        features = ", ".join(
            f"{key}={count}" for key, count in rollup.feature_clusters.most_common(1)
        )
        cte_graph = ", ".join(
            f"{key}={count}" for key, count in rollup.cte_graph_shapes.most_common(1)
        )
        cte_pushdown = ", ".join(
            f"{key}={count}" for key, count in rollup.cte_predicate_pushdown_statuses.most_common(1)
        )
        cte_simplification = ", ".join(
            f"{key}={count}" for key, count in rollup.cte_simplification_statuses.most_common(1)
        )
        derived_pushdown = ", ".join(
            f"{key}={count}"
            for key, count in rollup.derived_predicate_pushdown_statuses.most_common(1)
        )
        risk = ", ".join(f"{key}={count}" for key, count in rollup.risk_modes.most_common(1))
        print(
            f"  {rollup.key}: cases={rollup.count}; family={family}; "
            f"track={track}; primary={primary}; reason={reason}; risk={risk or '<none>'}; "
            f"cte_graph={cte_graph or '<none>'}; cte_pushdown={cte_pushdown or '<none>'}; "
            f"cte_simplification={cte_simplification or '<none>'}; "
            f"derived_pushdown={derived_pushdown or '<none>'}; "
            f"features={features or '<none>'}",
            file=out,
        )


def no_recipe_workload_concentration(result: OptimizerFunnelAuditResult) -> dict[str, object]:
    known_rollups = [
        rollup for rollup in result.no_recipe_workloads.values() if rollup.key != "<none>"
    ]
    unknown_cases = sum(
        rollup.count for rollup in result.no_recipe_workloads.values() if rollup.key == "<none>"
    )
    repeated_rollups = [rollup for rollup in known_rollups if rollup.count >= 2]
    repeated_cases = sum(rollup.count for rollup in repeated_rollups)
    known_cases = sum(rollup.count for rollup in known_rollups)
    total_cases = known_cases + unknown_cases
    top_count = max((rollup.count for rollup in known_rollups), default=0)
    return {
        "total_cases": total_cases,
        "known_cases": known_cases,
        "unknown_cases": unknown_cases,
        "known_groups": len(known_rollups),
        "repeated_groups": len(repeated_rollups),
        "repeated_cases": repeated_cases,
        "singleton_groups": len([rollup for rollup in known_rollups if rollup.count == 1]),
        "top_group_cases": top_count,
    }


def populate_repeated_no_recipe_rollups(result: OptimizerFunnelAuditResult) -> None:
    track_counts: Counter[str] = Counter()
    readiness_counts: Counter[str] = Counter()
    guidance_readiness_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    for rollup in result.no_recipe_workloads.values():
        if rollup.key == "<none>" or rollup.count < 2:
            continue
        track_counts.update(rollup.review_tracks)
        readiness_counts[repeated_no_recipe_review_readiness(rollup)] += 1
        guidance_readiness_counts[repeated_no_recipe_guidance_readiness(rollup)] += 1
        family_counts.update(rollup.shape_families)
    result.repeated_no_recipe_review_track_counts = track_counts
    result.repeated_no_recipe_review_readiness_counts = readiness_counts
    result.repeated_no_recipe_guidance_readiness_counts = guidance_readiness_counts
    result.repeated_no_recipe_family_counts = family_counts


def add_repeated_no_recipe_readiness_issues(result: OptimizerFunnelAuditResult) -> None:
    for readiness in sorted(REPEATED_NO_RECIPE_READINESS_GAPS):
        count = result.repeated_no_recipe_review_readiness_counts.get(readiness, 0)
        if not count:
            continue
        result.issues.append(
            OptimizerFunnelIssue(
                readiness,
                f"repeated no-recipe workloads have {readiness} ({count} groups)",
            )
        )
    for readiness in sorted(REPEATED_NO_RECIPE_GUIDANCE_GAPS):
        count = result.repeated_no_recipe_guidance_readiness_counts.get(readiness, 0)
        if not count:
            continue
        result.issues.append(
            OptimizerFunnelIssue(
                readiness,
                f"repeated no-recipe workloads have {readiness} ({count} groups)",
            )
        )


def repeated_no_recipe_review_readiness(rollup: WorkloadRollup) -> str:
    tracks = set(rollup.review_tracks)
    if not tracks:
        return "missing_track"
    if "unknown" in tracks:
        return "unknown_track"
    if "not_applicable" in tracks:
        return "missing_track"
    if tracks == {"source_unavailable"}:
        return "source_unavailable"
    if len(tracks) > 1:
        if all(
            track in NO_RECIPE_REVIEW_TRACKS and track not in NO_RECIPE_REVIEW_TRACK_UNREADY
            for track in tracks
        ):
            return "mixed_specific_tracks"
        return "mixed_tracks"
    return "specific_track"


def repeated_no_recipe_guidance_readiness(rollup: WorkloadRollup) -> str:
    track_readiness = repeated_no_recipe_review_readiness(rollup)
    if track_readiness == "mixed_specific_tracks":
        track = MIXED_NO_RECIPE_REVIEW_TRACK
    elif track_readiness == "specific_track":
        track = sorted(rollup.review_tracks)[0]
    else:
        return track_readiness
    if not optimizer_no_recipe_review_area(track):
        return "missing_review_area"
    if not optimizer_no_recipe_change_direction(track):
        return "missing_change_direction"
    workload_metric = optimizer_no_recipe_workload_metric(track)
    if not workload_metric:
        return "missing_workload_metric"
    if not optimizer_workload_metric_has_comparable_group_signal(workload_metric):
        return "weak_workload_metric"
    verification = optimizer_no_recipe_verification(track)
    if not verification:
        return "missing_verification"
    if not optimizer_verification_has_comparison_and_rerun(verification):
        return "weak_verification"
    if not optimizer_review_only_text_has_no_draft_manual_contract(
        optimizer_no_recipe_review_only_contract(track)
    ):
        return "weak_no_draft_contract"
    if rollup.candidate_reasons.get("unsafe_reason", 0) > 0:
        return "raw_like_candidate_reason"
    return "guidance_ready"


def optimizer_no_recipe_review_only_contract(track: str) -> str:
    return optimizer_rewrite_support_text(
        {
            "rewrite_support_label": "Guidance only",
            "rewrite_support_reason": "No Python-owned SQL rewrite recipe is available for this shape",
            "rewriteability_bucket": "not_rewriteable",
            "rewriteability_label": "Not rewriteable",
            "rewrite_support_facts": optimizer_no_recipe_review_track_label(track),
        }
    )


def optimizer_review_only_text_has_no_draft_manual_contract(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    has_no_draft_boundary = "trusted sql draft" in text and any(
        term in text
        for term in (
            "no trusted sql draft",
            "will not be generated",
            "not generated",
            "not shown",
            "not produce",
            "not produced",
            "disabled",
        )
    )
    has_manual_review = "manual" in text and any(
        term in text for term in ("review", "analysis", "guidance")
    )
    return has_no_draft_boundary and has_manual_review


def optimizer_verification_has_comparison_and_rerun(value: str) -> bool:
    text = str(value or "").strip().lower()
    if "compare" not in text:
        return False
    return any(
        term in text
        for term in (
            "rerun",
            "re-run",
            "next scan",
            "repeated workload",
            "repeated group",
            "repeated-group",
        )
    )


def optimizer_workload_metric_has_comparable_group_signal(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    return any(
        term in text
        for term in (
            "repeated-group",
            "repeated workload",
            "repeated group",
            "workload p95",
            "group p95",
            "comparable rerun",
            "comparable re-run",
            "next scan",
        )
    )


def no_recipe_workload_concentration_headline(result: OptimizerFunnelAuditResult) -> str:
    concentration = no_recipe_workload_concentration(result)
    total_cases = int(concentration["total_cases"])
    known_cases = int(concentration["known_cases"])
    repeated_cases = int(concentration["repeated_cases"])
    top_group_cases = int(concentration["top_group_cases"])
    return (
        "No-recipe workload concentration: "
        f"cases={total_cases}; known_workload_cases={known_cases}; "
        f"unknown_workload_cases={concentration['unknown_cases']}; "
        f"known_groups={concentration['known_groups']}; "
        f"repeated_groups={concentration['repeated_groups']}; "
        f"repeated_cases={repeated_cases} ({percentage(repeated_cases, known_cases)} of known); "
        f"singleton_groups={concentration['singleton_groups']}; "
        f"top_group_cases={top_group_cases} ({percentage(top_group_cases, known_cases)} of known)"
    )


def candidate_calibration_headline(result: OptimizerFunnelAuditResult) -> str:
    medium = result.candidate_tier_counts.get("medium", 0)
    high = result.candidate_tier_counts.get("high", 0)
    medium_high = medium + high
    total = result.audited_cases
    status_counts = medium_high_status_counts(result.medium_high_candidate_status_bucket_counts)
    return (
        f"Candidate calibration: medium/high={medium_high}/{total} "
        f"({percentage(medium_high, total)}); high={high}; medium={medium}; "
        f"draft-supported={draft_supported_count(result.medium_high_candidate_status_bucket_counts)}; "
        f"guidance-only={status_counts.get('guidance_only', 0)}; "
        f"source-unavailable={status_counts.get('source_unavailable', 0)}"
    )


def medium_high_status_counts(counter: Counter[str]) -> Counter[str]:
    statuses: Counter[str] = Counter()
    for key, count in counter.items():
        status, _, _bucket = key.partition(":")
        statuses[status or "unknown"] += count
    return statuses


def draft_supported_count(counter: Counter[str]) -> int:
    total = 0
    for key, count in counter.items():
        status, _separator, bucket = key.partition(":")
        if bucket == "safe_material_draft" or status in {
            "sql_draft_supported",
            "sql_draft_attemptable",
        }:
            total += count
    return total


def percentage(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def print_result(
    result: OptimizerFunnelAuditResult,
    *,
    limit: int = 12,
    out: TextIO | None = None,
) -> None:
    out = out or sys.stdout
    print(f"Summary: {result.summary_name}", file=out)
    print(f"Cases: total={result.total_cases}, audited={result.audited_cases}", file=out)
    print(candidate_calibration_headline(result), file=out)
    print(no_recipe_workload_concentration_headline(result), file=out)
    print_counter("Support source", result.support_source_counts, limit=limit, out=out)
    print_counter("Severity", result.severity_counts, limit=limit, out=out)
    print_counter("Candidate tiers", result.candidate_tier_counts, limit=limit, out=out)
    print_counter("Candidate confidence", result.candidate_confidence_counts, limit=limit, out=out)
    print_counter("Candidate score bands", result.candidate_score_band_counts, limit=limit, out=out)
    print_counter(
        "Medium/high candidate primary labels",
        result.medium_high_candidate_primary_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "Medium/high candidate reasons",
        result.medium_high_candidate_reason_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "Medium/high candidate counter-signals",
        result.medium_high_candidate_counter_signal_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "Medium/high candidate status / bucket",
        result.medium_high_candidate_status_bucket_counts,
        limit=limit,
        out=out,
    )
    print_counter("Optimizer status", result.status_counts, limit=limit, out=out)
    print_counter("Rewriteability buckets", result.bucket_counts, limit=limit, out=out)
    print_counter(
        "Effective rewriteability ranks",
        result.effective_rewriteability_rank_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "Recipe-adjacent actionability",
        result.adjacent_actionability_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "Recipe-detected no-draft actionability",
        result.no_draft_actionability_counts,
        limit=limit,
        out=out,
    )
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
        "No-recipe review tracks",
        result.no_recipe_review_track_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "No-recipe family / reason",
        result.no_recipe_family_reason_counts,
        limit=limit,
        out=out,
    )
    print_counter("No-recipe risk modes", result.no_recipe_risk_mode_counts, limit=limit, out=out)
    print_counter(
        "No-recipe risk reasons",
        result.no_recipe_risk_reason_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "Repeated no-recipe review tracks",
        result.repeated_no_recipe_review_track_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "Repeated no-recipe review readiness",
        result.repeated_no_recipe_review_readiness_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "Repeated no-recipe guidance readiness",
        result.repeated_no_recipe_guidance_readiness_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "Repeated no-recipe shape families",
        result.repeated_no_recipe_family_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "No-recipe CTE graph shapes",
        result.no_recipe_cte_graph_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "No-recipe CTE predicate pushdown",
        result.no_recipe_cte_predicate_pushdown_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "No-recipe CTE simplification",
        result.no_recipe_cte_simplification_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "No-recipe CTE boundary reasons",
        result.no_recipe_cte_boundary_reason_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "No-recipe derived predicate pushdown",
        result.no_recipe_derived_predicate_pushdown_counts,
        limit=limit,
        out=out,
    )
    print_counter(
        "No-recipe derived boundary reasons",
        result.no_recipe_derived_boundary_reason_counts,
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
    if result.issues:
        print("Issues:", file=out)
        for issue in result.issues:
            print(f"  {issue.category}: {issue.message}", file=out)
    else:
        print("Issues: none", file=out)


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
        "--use-stored-optimizer-support",
        dest="use_stored_support",
        action="store_true",
        help="Use optimizer_rewrite_support already present in the summary instead of recomputing.",
    )
    parser.add_argument(
        "--fail-on-repeated-no-recipe-readiness-gaps",
        action="store_true",
        help=(
            "Fail when repeated no-recipe workload groups lack one specific safe review "
            "track, mapped review guidance, workload metric, or compare/rerun verification."
        ),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Write a raw-free machine-readable optimizer funnel summary JSON.",
    )
    parser.add_argument("--limit", type=int, default=12, help="Rows to print per counter.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        result = audit_summary(
            args.summary,
            recompute_support=not args.use_stored_support,
            fail_on_repeated_no_recipe_readiness_gaps=(
                args.fail_on_repeated_no_recipe_readiness_gaps
            ),
        )
    except AuditInputError as exc:
        print(f"optimizer funnel audit failed: {exc}", file=sys.stderr)
        return 2
    print_result(result, limit=max(1, args.limit))
    if args.summary_json is not None:
        try:
            write_summary_json(
                result,
                args.summary_json,
                input_summary=args.summary,
                workload_limit=max(1, args.limit),
            )
        except AuditOutputError as exc:
            print(f"optimizer funnel audit failed: {exc}", file=sys.stderr)
            return 2
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
