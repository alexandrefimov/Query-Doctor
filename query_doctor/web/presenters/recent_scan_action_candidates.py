"""Action-candidate view models for Recent scan Details pages."""

from __future__ import annotations

from typing import Any

from query_doctor.web.presenters.recent_scan_models import (
    RecentScanActionCandidateCardView,
    RecentScanActionCandidatesView,
    RecentScanCaseDetailView,
    RecentScanDiagnosticFactView,
    RecentScanSourceLocatorView,
)


def present_recent_scan_action_candidates(
    view: RecentScanCaseDetailView,
) -> RecentScanActionCandidatesView:
    cards: list[RecentScanActionCandidateCardView] = []
    optimization = view.optimization_candidate
    if candidate_is_visible(optimization):
        rank_text = candidate_rank_text(view.optimization_rank)
        rewrite_support_text = optimizer_rewrite_support_text(optimization)
        summary = str(optimization.get("summary") or "query-shape evidence").strip()
        review_areas = str(optimization.get("review_areas") or "query shape").strip()
        counter_text = candidate_counter_signal_note(optimization)
        source_locators = view.source_locators.get("query_optimization", ())
        cards.append(
            RecentScanActionCandidateCardView(
                "Query-shape recommendation",
                (
                    f"Candidate strength: {candidate_title(optimization.get('tier'))}. "
                    f"Score: {optimization.get('score')}/100. "
                    f"{rank_text}"
                    f"Impact: {candidate_title(optimization.get('impact'))}. "
                    f"Confidence: {candidate_title(optimization.get('confidence'))}."
                ),
                recommendation_id="query_optimization_review.v1",
                source_locators=source_locators,
                supporting_facts=supporting_facts_for_action(
                    view,
                    (
                        "resource_footprint",
                        "signals",
                        "workload_baseline",
                        "cluster_context",
                        "table_stats",
                        "spill",
                    ),
                ),
                why=query_optimization_why(summary, counter_text, source_locators),
                guardrails=rewrite_support_text,
                change_direction=query_optimization_change_direction(
                    review_areas,
                    source_locators,
                ),
                verification=(
                    "Compare EXPLAIN before and after the change, then rerun under comparable load "
                    "and confirm estimates, exchange, memory, spill, or runtime behavior improved."
                ),
            )
        )
    stats = view.stats_candidate
    if candidate_is_visible(stats):
        rank_text = candidate_rank_text(view.stats_rank)
        summary = str(stats.get("summary") or "stats-planning evidence").strip()
        review_areas = str(stats.get("review_areas") or "stats evidence").strip()
        confirmation = str(
            stats.get("required_confirmation") or "compare EXPLAIN and rerun under comparable load"
        ).strip()
        counter_sentence = candidate_counter_signal_note(stats)
        source_locators = view.source_locators.get("stats_refresh", ())
        cards.append(
            RecentScanActionCandidateCardView(
                "Stats maintenance recommendation",
                (
                    f"Candidate strength: {candidate_title(stats.get('tier'))}. "
                    f"Score: {stats.get('score')}/100. "
                    f"{rank_text}"
                    f"Need: {detail_stats_need_label(stats.get('need_type'))}. "
                    f"Speed benefit: {candidate_title(stats.get('speed_benefit'))}. "
                    f"Confidence: {candidate_title(stats.get('confidence'))}."
                ),
                recommendation_id="stats_refresh_review.v1",
                source_locators=source_locators,
                supporting_facts=supporting_facts_for_action(
                    view,
                    (
                        "table_stats",
                        "signals",
                        "resource_footprint",
                        "workload_baseline",
                        "cluster_context",
                    ),
                ),
                why=stats_why(stats.get("need_type"), summary, counter_sentence, source_locators),
                change_direction=stats_change_direction(
                    stats.get("need_type"),
                    review_areas,
                    source_locators,
                ),
                verification=confirmation,
            )
        )
    if view.primary_bottleneck.label == "Admission/runtime":
        reason = (
            f" Evidence: {view.primary_bottleneck.reason_summary}."
            if view.primary_bottleneck.reason_summary
            else ""
        )
        cards.append(
            RecentScanActionCandidateCardView(
                "Admission/runtime follow-up",
                (
                    "Runtime admission is the primary follow-up. "
                    f"Confidence: {view.primary_bottleneck.confidence}."
                ),
                recommendation_id="runtime_admission_check.v1",
                source_locators=view.source_locators.get("runtime_admission", ()),
                supporting_facts=supporting_facts_for_action(
                    view,
                    (
                        "admission_wait",
                        "pool",
                        "cluster_context",
                        "query_window",
                    ),
                ),
                why=(
                    "Explicit query-specific admission evidence made runtime admission "
                    f"the primary bottleneck.{reason}"
                ),
                change_direction=(
                    "Check pool saturation and admission wait around the case window before changing SQL."
                ),
                verification="Rerun under comparable load and confirm admission wait no longer dominates.",
            )
        )
    return RecentScanActionCandidatesView(cards=tuple(cards))


def supporting_facts_for_action(
    view: RecentScanCaseDetailView,
    fact_ids: tuple[str, ...],
    *,
    limit: int = 4,
) -> tuple[RecentScanDiagnosticFactView, ...]:
    by_id = {fact.fact_id: fact for fact in view.diagnostic_facts}
    facts: list[RecentScanDiagnosticFactView] = []
    for fact_id in fact_ids:
        fact = by_id.get(fact_id)
        if fact is None or fact in facts:
            continue
        facts.append(fact)
        if len(facts) >= limit:
            break
    return tuple(facts)


def candidate_is_visible(candidate: dict[str, Any]) -> bool:
    return str(candidate.get("tier") or "").lower() in {"high", "medium"}


def candidate_rank_text(rank: Any) -> str:
    if not is_meaningful_detail_value(rank):
        return ""
    return f"Rank: #{rank}. "


def candidate_counter_signal_note(candidate: dict[str, Any]) -> str:
    counter_signals = candidate.get("counter_signals")
    if not counter_signals:
        return ""
    return f"Keep in mind: {counter_signals}."


def join_action_text(*parts: str) -> str:
    sentences: list[str] = []
    for part in parts:
        text = str(part or "").strip()
        if not text:
            continue
        if text[-1] not in ".!?":
            text += "."
        sentences.append(text)
    return " ".join(sentences)


def query_optimization_why(
    summary: str,
    counter_text: str,
    locators: tuple[RecentScanSourceLocatorView, ...],
) -> str:
    evidence = meaningful_text(summary, "query-shape evidence")
    explanation = (
        f"Deterministic analysis found {evidence}. "
        "That makes this query worth a focused rewrite review, not a proven root-cause claim."
    )
    location_hint = query_optimization_location_hint(locators)
    return join_action_text(explanation, location_hint, counter_text)


def query_optimization_location_hint(locators: tuple[RecentScanSourceLocatorView, ...]) -> str:
    labels = source_locator_labels(locators)
    if "SQL: final SELECT filter" in labels and "Plan: estimate-mismatch operator" in labels:
        return (
            "Start where the late SQL filter meets the flagged plan operator; that is the "
            "supported place to check whether fewer rows can reach expensive join or exchange work."
        )
    if "SQL: final SELECT filter" in labels:
        return (
            "Start with the late SQL filter; the safest review is whether the same condition can "
            "filter rows earlier without changing the result."
        )
    if "SQL: downstream CTE filter" in labels or "SQL: mixed downstream filters" in labels:
        return (
            "Start with the downstream CTE filters; the review is whether rows can be reduced "
            "closer to the CTE producer."
        )
    if "SQL: derived table" in labels:
        return (
            "Start with the derived table boundary; the review is whether an outer filter can move "
            "inside without crossing unsafe projection, aggregate, or join boundaries."
        )
    if "SQL: UNION branch" in labels:
        return (
            "Start with the UNION branches; the review is whether each branch can reduce rows "
            "before the final rollup or exchange."
        )
    if "Plan: memory-pressure operator" in labels:
        return (
            "Start with the memory-pressure plan operator and look for a query-shape change that "
            "reduces rows before it."
        )
    if "Plan: data movement operator" in labels:
        return (
            "Start with the data-movement plan operator and look for a query-shape change that "
            "reduces rows before exchange."
        )
    return "Use the listed review location as the safe anchor for the first manual check."


def stats_why(
    need_type: Any,
    summary: str,
    counter_text: str,
    locators: tuple[RecentScanSourceLocatorView, ...],
) -> str:
    evidence = meaningful_text(summary, "stats and estimate-mismatch evidence")
    need = detail_stats_need_label(need_type)
    explanation = (
        f"Deterministic analysis found {evidence}. "
        f"That makes {need} worth checking before deeper SQL rewrites, because missing or "
        "incomplete stats can leave the planner choosing from weak row estimates."
    )
    location_hint = stats_location_hint(locators)
    return join_action_text(explanation, location_hint, counter_text)


def stats_location_hint(locators: tuple[RecentScanSourceLocatorView, ...]) -> str:
    labels = source_locator_labels(locators)
    if (
        "Metadata: referenced table stats" in labels
        and "Plan: estimate-mismatch operator" in labels
    ):
        return (
            "Start with the referenced table stats and use the flagged estimate-mismatch plan "
            "operator as the before/after comparison point."
        )
    if "Metadata: referenced table stats" in labels:
        return "Start with the referenced table stats; they are the supported metadata gap."
    if "Plan: estimate-mismatch operator" in labels:
        return (
            "Use the flagged estimate-mismatch plan operator as the before/after comparison point."
        )
    return "Use the listed metadata or plan location as the safe anchor for the stats check."


def query_optimization_change_direction(
    review_areas: str,
    locators: tuple[RecentScanSourceLocatorView, ...],
) -> str:
    labels = source_locator_labels(locators)
    directions: list[str] = []
    if "SQL: final SELECT filter" in labels:
        directions.append(
            "Try to reduce rows earlier: move the final SELECT filter closer to the data-producing "
            "CTE or subquery only when the result columns, join semantics, and filters stay the same."
        )
    elif "SQL: downstream CTE filter" in labels or "SQL: mixed downstream filters" in labels:
        directions.append(
            "Try to reduce rows inside the relevant CTE path: move only the downstream filters that "
            "belong to the CTE output, and keep projection plus dependency shape intact."
        )
    elif "SQL: derived table" in labels:
        directions.append(
            "Try to reduce rows inside the derived table: move the outer filter inward only if it "
            "does not cross projection, aggregate, set-operation, or join boundaries."
        )
    elif "SQL: UNION branch" in labels:
        directions.append(
            "Try to reduce rows per UNION branch: apply equivalent branch-local filters or "
            "pre-aggregation while preserving every branch output column."
        )
    elif "SQL: CTE block" in labels:
        directions.append(
            "Try to simplify the CTE path only where facts support it: review filter placement and "
            "pass-through layers, but avoid CTE inlining or reordering without trusted validation."
        )

    if "Plan: estimate-mismatch operator" in labels:
        directions.append(
            "Use the flagged estimate-mismatch operator as the plan comparison anchor; after the "
            "change, check whether fewer rows or better estimates feed that operator."
        )
    elif "Plan: memory-pressure operator" in labels:
        directions.append(
            "Use the marked memory-pressure operator as the plan comparison anchor; prefer reducing "
            "rows before it over runtime tuning."
        )
    elif "Plan: data movement operator" in labels:
        directions.append(
            "Use the marked data-movement operator as the plan comparison anchor; prefer reducing "
            "unnecessary rows before exchange or large intermediate movement."
        )

    if directions:
        return " ".join(directions[:2])
    return (
        f"Review {review_areas}; make only row-reduction or shape changes that can be explained by "
        "the listed deterministic facts or by a trusted optimizer outcome."
    )


def stats_change_direction(
    need_type: Any,
    review_areas: str,
    locators: tuple[RecentScanSourceLocatorView, ...],
) -> str:
    need = str(need_type or "").strip().lower()
    if need == "table_and_column_stats":
        primary = (
            "Refresh table/partition row-count stats for the referenced physical tables first; add "
            "column stats only if the plan still shows weak estimates after that."
        )
    elif need == "table_stats":
        primary = (
            "Refresh table/partition row-count stats for the referenced physical tables, then "
            "recheck the plan before collecting broader column stats."
        )
    elif need == "column_stats":
        primary = (
            "Collect column stats for join and filter columns only after table/partition row-count "
            "stats are available."
        )
    else:
        primary = (
            f"Update {detail_stats_need_label(need_type)}, then inspect {review_areas} for "
            "estimate-driven planning changes."
        )

    labels = source_locator_labels(locators)
    if "Plan: estimate-mismatch operator" in labels:
        return (
            f"{primary} Use the flagged estimate-mismatch operator as the before/after plan anchor."
        )
    if "Plan: memory-pressure operator" in labels:
        return (
            f"{primary} Use the marked memory-pressure operator as a secondary before/after anchor."
        )
    return primary


def meaningful_text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if text.lower() in {"", "unknown", "none"}:
        return fallback
    return text


def source_locator_labels(locators: tuple[RecentScanSourceLocatorView, ...]) -> set[str]:
    return {locator.label for locator in locators}


def optimizer_rewrite_support_text(candidate: dict[str, Any]) -> str:
    label = str(candidate.get("rewrite_support_label") or "").strip()
    reason = str(candidate.get("rewrite_support_reason") or "").strip()
    rewriteability = str(candidate.get("rewriteability_label") or "").strip()
    rewriteability_bucket = str(candidate.get("rewriteability_bucket") or "").strip().lower()
    facts = str(candidate.get("rewrite_support_facts") or "").strip()
    guardrails = str(candidate.get("rewrite_support_guardrails") or "").strip()
    context = ""
    if rewriteability and rewriteability.lower() != "unknown":
        context += f" Rewriteability: {rewriteability}."
    if facts:
        context += f" Facts: {facts}."
    if guardrails:
        context += f" Guardrails: {guardrails}."
    if rewriteability_bucket == "not_rewriteable":
        reason_text = f" Reason: {reason}." if reason else ""
        return (
            "No trusted SQL draft will be generated for this case by the current deterministic optimizer; "
            f"use the Review first areas for manual query-shape analysis.{reason_text}{context} "
        )
    if rewriteability_bucket == "human_review_only":
        reason_text = f" Reason: {reason}." if reason else ""
        return f"SQL draft is disabled by guardrails; use manual optimizer guidance.{reason_text}{context} "
    if not label:
        return context.strip() + (" " if context else "")
    if reason:
        return f"Rewrite support: {label} ({reason}).{context} "
    return f"Rewrite support: {label}.{context} "


def candidate_title(value: Any) -> str:
    text = str(value or "unknown").replace("_", " ").strip()
    return text.title() if text else "Unknown"


def detail_stats_need_label(value: Any) -> str:
    labels = {
        "table_stats": "table/partition stats",
        "column_stats": "column stats",
        "table_and_column_stats": "table/partition stats first, then column stats",
        "stats_possibly_stale": "stats freshness unknown",
        "insufficient_metadata": "insufficient metadata",
        "not_likely_stats_issue": "not likely a stats issue",
    }
    return labels.get(str(value), str(value or "unknown"))


def is_meaningful_detail_value(value: Any) -> bool:
    if value is None:
        return False
    if value is False:
        return False
    text = str(value).strip().lower()
    return text not in {"", "unknown", "none", "not_run", "false"}
