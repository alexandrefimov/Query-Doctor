"""Question-grouped diagnostics for Recent scan Details pages."""

from __future__ import annotations

from query_doctor.web.presenters.recent_scan_models import (
    RecentScanCaseDetailView,
    RecentScanDiagnosticFactView,
    RecentScanDiagnosticQuestionGroupView,
    RecentScanDiagnosticQuestionsView,
)

QUESTION_GROUPS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "time_and_work",
        "When and how much?",
        "Query window, runtime, and compact resource footprint.",
        ("query_window", "resource_footprint", "query_type"),
    ),
    (
        "normality",
        "Is this normal?",
        "Comparison against matching workload context when available.",
        ("workload_baseline", "workload_group"),
    ),
    (
        "queue_or_cluster",
        "Queue or cluster?",
        "Admission, pool, and cluster context that may explain runtime.",
        ("admission_wait", "pool", "cluster_context"),
    ),
)


def present_recent_scan_diagnostic_questions(
    view: RecentScanCaseDetailView,
) -> RecentScanDiagnosticQuestionsView:
    by_id = {fact.fact_id: fact for fact in view.diagnostic_facts}
    groups: list[RecentScanDiagnosticQuestionGroupView] = []
    for group_id, title, prompt, fact_ids in QUESTION_GROUPS:
        facts = selected_group_facts(by_id, fact_ids)
        if not facts:
            continue
        groups.append(
            RecentScanDiagnosticQuestionGroupView(
                group_id=group_id,
                title=title,
                prompt=prompt,
                facts=facts,
            )
        )
    return RecentScanDiagnosticQuestionsView(groups=tuple(groups))


def selected_group_facts(
    facts_by_id: dict[str, RecentScanDiagnosticFactView],
    fact_ids: tuple[str, ...],
    *,
    limit: int = 4,
) -> tuple[RecentScanDiagnosticFactView, ...]:
    facts: list[RecentScanDiagnosticFactView] = []
    for fact_id in fact_ids:
        fact = facts_by_id.get(fact_id)
        if fact is None or fact in facts:
            continue
        facts.append(fact)
        if len(facts) >= limit:
            break
    return tuple(facts)
