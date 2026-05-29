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
    if processing_failure_is_visible(view):
        return RecentScanActionCandidatesView(cards=(processing_failure_follow_up_card(view),))
    cards: list[RecentScanActionCandidateCardView] = []
    optimization = view.optimization_candidate
    if candidate_is_visible(optimization):
        rank_text = candidate_rank_text(view.optimization_rank)
        rewrite_support_text = optimizer_rewrite_support_text(optimization)
        summary = str(optimization.get("summary") or "query-shape evidence").strip()
        review_areas = str(optimization.get("review_areas") or "query shape").strip()
        rewrite_review_direction = str(optimization.get("rewrite_review_direction") or "").strip()
        counter_text = candidate_counter_signal_note(optimization)
        source_locators = view.source_locators.get(
            "query_optimization",
            (),
        ) or generic_source_locator("query", "Query-shape evidence")
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
                    rewrite_review_direction,
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
        source_locators = view.source_locators.get(
            "stats_refresh",
            (),
        ) or generic_source_locator("metadata", "Stats or estimate evidence")
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
                source_locators=view.source_locators.get("runtime_admission", ())
                or generic_source_locator("runtime", "Runtime/admission evidence"),
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
    if not cards and processing_failure_is_visible(view):
        cards.append(processing_failure_follow_up_card(view))
    if not cards and diagnostic_follow_up_is_visible(view):
        cards.append(diagnostic_follow_up_card(view))
    return RecentScanActionCandidatesView(cards=tuple(cards))


def processing_failure_is_visible(view: RecentScanCaseDetailView) -> bool:
    severity = str(view.score_severity or "").strip().lower()
    return severity == "failed"


def processing_failure_follow_up_card(
    view: RecentScanCaseDetailView,
) -> RecentScanActionCandidateCardView:
    statuses = "; ".join(processing_failure_statuses(view)) or "processing failure recorded"
    reason = processing_failure_reason_text(view)
    reason_sentence = f" Reason: {reason}" if reason else ""
    return RecentScanActionCandidateCardView(
        "Processing failure follow-up",
        (
            "Collection, deterministic analysis, metadata, or report processing did not "
            "complete cleanly, so this case "
            "needs attention before diagnostic conclusions are trusted. "
            f"Status: {statuses}.{reason_sentence}"
        ),
        recommendation_id="processing_failure_follow_up.v1",
        supporting_facts=supporting_facts_for_action(
            view,
            (
                "priority",
                "main_signal",
                "confidence",
            ),
        ),
        why=(
            "The row is marked failed by selected-case status, not by a root-cause diagnosis. "
            "Regenerate deterministic facts before relying on report or optimizer actions."
        ),
        guardrails=(
            "Do not treat this as a SQL rewrite, stats, or admission recommendation until "
            "the failed processing step completes successfully."
        ),
        change_direction=(
            "Fix the failed processing step for this case, then rerun or regenerate the "
            "selected action before changing SQL, stats, or runtime settings."
        ),
        verification=(
            "Confirm the failed processing step completes successfully; Details should "
            "then show typed score evidence or a specific supported action candidate."
        ),
    )


def processing_failure_statuses(view: RecentScanCaseDetailView) -> tuple[str, ...]:
    failures: list[str] = []
    for label, value in view.status_fields:
        normalized_label = str(label or "").strip().lower()
        normalized_value = str(value or "").strip().lower()
        if normalized_label in {"collection", "analysis", "metadata", "report"} and (
            normalized_value == "failed"
        ):
            failures.append(f"{normalized_label} failed")
    if not failures and processing_failure_category_recorded(view):
        failures.append("processing failure category recorded")
    return tuple(failures)


def processing_failure_category_recorded(view: RecentScanCaseDetailView) -> bool:
    for label, value in view.technical_fields:
        normalized_label = str(label or "").strip().lower()
        normalized_value = str(value or "").strip().lower()
        if normalized_label == "failure category" and normalized_value not in {
            "",
            "none",
            "unknown",
        }:
            return True
    return False


def processing_failure_reason_text(view: RecentScanCaseDetailView) -> str:
    for label, value in view.technical_fields:
        normalized_label = str(label or "").strip().lower()
        normalized_value = str(value or "").strip()
        if normalized_label == "failure reason" and normalized_value.lower() not in {
            "",
            "none",
            "unknown",
        }:
            return normalized_value
    return ""


def diagnostic_follow_up_is_visible(view: RecentScanCaseDetailView) -> bool:
    severity = str(view.score_severity or "").strip().lower()
    if severity not in {"high", "suspicious", "failed"}:
        return False
    if view.signal_summary != "no positive analyzer signals":
        return True
    primary = str(view.primary_bottleneck.label or "").strip()
    return bool(primary and primary not in {"Unknown", "Not classified"})


def diagnostic_follow_up_card(
    view: RecentScanCaseDetailView,
) -> RecentScanActionCandidateCardView:
    primary = str(view.primary_bottleneck.label or "Diagnostic evidence").strip()
    confidence = str(view.primary_bottleneck.confidence or "unknown").strip()
    signal = meaningful_text(view.signal_summary, "supported analyzer signals")
    reason = (
        f" Primary signal: {view.primary_bottleneck.reason_summary}."
        if view.primary_bottleneck.reason_summary
        else ""
    )
    return RecentScanActionCandidateCardView(
        diagnostic_follow_up_title(primary),
        (
            "No Medium/High rewrite or stats candidate was selected, but deterministic "
            f"scoring still marked this case as {candidate_title(view.score_severity)}. "
            f"Score: {view.score}. Confidence: {candidate_title(confidence)}.{reason}"
        ),
        recommendation_id="diagnostic_follow_up.v1",
        source_locators=diagnostic_follow_up_locators(view),
        supporting_facts=supporting_facts_for_action(
            view,
            (
                "main_signal",
                "signals",
                "resource_footprint",
                "cluster_context",
                "table_stats",
            ),
        ),
        why=(
            f"Deterministic analysis found {signal}. "
            "This is a review direction, not a root-cause claim."
        ),
        guardrails=(
            "No trusted SQL draft is implied by this recommendation. Keep changes limited to "
            "directions supported by analyzer facts or by a later trusted optimizer outcome."
        ),
        change_direction=diagnostic_follow_up_change_direction(primary),
        verification=diagnostic_follow_up_verification(primary),
    )


def diagnostic_follow_up_locators(
    view: RecentScanCaseDetailView,
) -> tuple[RecentScanSourceLocatorView, ...]:
    for group in ("query_optimization", "stats_refresh", "runtime_admission"):
        locators = view.source_locators.get(group, ())
        if locators:
            return locators
    return diagnostic_generic_source_locator(view)


def diagnostic_generic_source_locator(
    view: RecentScanCaseDetailView,
) -> tuple[RecentScanSourceLocatorView, ...]:
    primary = str(view.primary_bottleneck.label or "").strip()
    if primary == "SQL shape":
        return generic_source_locator("query", "SQL-shape diagnostic evidence")
    if primary == "Runtime skew":
        return generic_source_locator("runtime", "Runtime skew evidence")
    if primary == "Data movement":
        return generic_source_locator("plan", "Data-movement evidence")
    if primary == "Storage/HDFS":
        return generic_source_locator("runtime", "Storage or HDFS evidence")
    if primary == "Stats":
        return generic_source_locator("metadata", "Stats or estimate evidence")
    if primary == "Client fetch tail":
        return generic_source_locator("runtime", "Client fetch wait evidence")
    if primary == "Competing signals":
        return generic_source_locator("diagnostics", "Mixed diagnostic evidence")
    if view.signal_summary != "no positive analyzer signals":
        return generic_source_locator("diagnostics", "Deterministic score evidence")
    return ()


def generic_source_locator(kind: str, label: str) -> tuple[RecentScanSourceLocatorView, ...]:
    return (RecentScanSourceLocatorView(kind=kind, label=label, coordinate="", detail=""),)


def diagnostic_follow_up_title(primary: str) -> str:
    if primary == "SQL shape":
        return "SQL shape follow-up"
    if primary == "Runtime skew":
        return "Runtime skew follow-up"
    if primary == "Data movement":
        return "Data movement follow-up"
    if primary == "Storage/HDFS":
        return "Storage/HDFS follow-up"
    if primary == "Stats":
        return "Stats evidence follow-up"
    if primary == "Competing signals":
        return "Mixed-signal follow-up"
    return "Diagnostic follow-up"


def diagnostic_follow_up_change_direction(primary: str) -> str:
    if primary == "SQL shape":
        return (
            "Inspect the join, aggregation, filter, and exchange shape behind the score signals. "
            "Prefer reducing rows before joins, exchanges, or memory-heavy operators; keep result "
            "columns and join semantics unchanged."
        )
    if primary == "Runtime skew":
        return (
            "Inspect data distribution and hot-key behavior before changing SQL. If a query-shape "
            "change is attempted, it should reduce skewed rows or improve join distribution."
        )
    if primary == "Data movement":
        return (
            "Inspect exchange and intermediate-volume evidence. Prefer pre-filtering or "
            "pre-aggregation that reduces rows before data movement while preserving output shape."
        )
    if primary == "Storage/HDFS":
        return (
            "Inspect storage and scan-footprint evidence first. Separate HDFS or storage pressure "
            "from SQL-shape changes before tuning joins or admission settings."
        )
    if primary == "Stats":
        return (
            "Confirm table and column statistics around the estimate-mismatch evidence before "
            "trying a rewrite. Treat stats maintenance as a hypothesis to verify, not proof."
        )
    if primary == "Competing signals":
        return (
            "Split the review into small checks: estimates and query shape first, then runtime "
            "skew or data movement if the plan remains suspicious."
        )
    return (
        "Use the diagnostics evidence as the review anchor and make only changes that can be "
        "confirmed by EXPLAIN and a comparable rerun."
    )


def diagnostic_follow_up_verification(primary: str) -> str:
    if primary == "Runtime skew":
        return (
            "Rerun under comparable load and confirm backend row/time spread, runtime metrics, "
            "and elapsed time improve without new spill or admission pressure."
        )
    if primary == "Storage/HDFS":
        return (
            "Rerun under comparable load and confirm scan, storage, or HDFS signals improve "
            "before attributing the case to SQL shape."
        )
    return (
        "Compare EXPLAIN before and after the change, then rerun under comparable load and confirm "
        "the flagged score signals, exchange volume, memory pressure, skew, or runtime metrics improve."
    )


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
    rewrite_review_direction: str = "",
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

    if rewrite_review_direction:
        directions.append(rewrite_review_direction)

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
