"""Recent batch metadata refresh selection policy."""

from __future__ import annotations

from query_doctor.recent.batch_config import (
    BAD_METADATA_REFRESH_LIMIT,
    SUSPICIOUS_METADATA_PROMOTION_SCORE_FLOOR,
    SUSPICIOUS_METADATA_REFRESH_LIMIT,
)
from query_doctor.recent.batch_models import BatchConfig, CaseResult
from query_doctor.recent.batch_summary import batch_ranking_key, case_score_severity


def rank_cases_for_metadata(cases: list[CaseResult]) -> list[CaseResult]:
    ranked = sorted(
        [case for case in cases if case.analysis_status == "ok"],
        key=batch_ranking_key,
    )
    for rank, case in enumerate(ranked, start=1):
        case.triage_rank = rank
    return ranked


def metadata_refresh_candidates(config: BatchConfig, cases: list[CaseResult]) -> list[CaseResult]:
    ranked = rank_cases_for_metadata(cases)
    if metadata_refresh_skip_reason(config, ranked) is not None:
        mark_metadata_not_requested(ranked)
        return []
    candidates = select_metadata_refresh_candidates(ranked, config.metadata_top_limit)
    refreshed_ids = {id(case) for case in candidates}
    mark_metadata_not_requested([case for case in ranked if id(case) not in refreshed_ids])
    return candidates


def metadata_refresh_skip_reason(config: BatchConfig, ranked_cases: list[CaseResult]) -> str | None:
    if config.metadata_mode == "off":
        return "metadata disabled"
    if not config.metadata_coordinator:
        return "metadata not configured"
    if config.metadata_top_limit <= 0:
        return "metadata_top_limit=0"
    if not ranked_cases:
        return "no eligible cases"
    return None


def mark_metadata_not_requested(cases: list[CaseResult]) -> None:
    for case in cases:
        if case.metadata_status in {"skipped", "not_observed"}:
            case.metadata_status = "not_requested"


def select_metadata_refresh_candidates(ranked_cases: list[CaseResult], limit: int) -> list[CaseResult]:
    if limit <= 0:
        return []
    remaining = limit
    bad_limit = min(BAD_METADATA_REFRESH_LIMIT, remaining)
    bad = [case for case in ranked_cases if case_score_severity(case) == "high"][:bad_limit]
    remaining -= len(bad)
    suspicious_limit = min(SUSPICIOUS_METADATA_REFRESH_LIMIT, remaining)
    suspicious = [
        case
        for case in ranked_cases
        if case_score_severity(case) == "suspicious" and suspicious_can_be_promoted_by_metadata(case)
    ][:suspicious_limit]
    return bad + suspicious


def suspicious_can_be_promoted_by_metadata(case: CaseResult) -> bool:
    return case.score >= SUSPICIOUS_METADATA_PROMOTION_SCORE_FLOOR
