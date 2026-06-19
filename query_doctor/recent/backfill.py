"""Backfill helpers for large Recent batch calibration runs."""

from __future__ import annotations

from query_doctor.recent.batch_models import BatchConfig, CaseResult

BACKFILL_MIN_TRIAGE_PROFILE_LIMIT = 100
BACKFILL_RESERVE_FRACTION = 0.10


def backfill_candidate_pool_enabled(config: BatchConfig) -> bool:
    return (
        not config.discover_only
        and config.top_reports == 0
        and config.triage_profile_limit >= BACKFILL_MIN_TRIAGE_PROFILE_LIMIT
        and config.cm_inspect_limit > config.triage_profile_limit
    )


def discovery_select_limit(config: BatchConfig) -> int:
    if not backfill_candidate_pool_enabled(config):
        return config.triage_profile_limit
    reserve = max(1, round(config.triage_profile_limit * BACKFILL_RESERVE_FRACTION))
    return min(config.cm_inspect_limit, config.triage_profile_limit + reserve)


def backfill_pool_warning(config: BatchConfig, *, select_limit: int) -> str | None:
    if select_limit <= config.triage_profile_limit:
        return None
    return (
        "Large analyzer-only batch backfill is enabled: selected "
        f"{select_limit} candidates so the final summary can retain up to "
        f"{config.triage_profile_limit} successfully analyzed cases."
    )


def retain_backfilled_case_results(
    config: BatchConfig, cases: list[CaseResult]
) -> tuple[list[CaseResult], str | None]:
    select_limit = discovery_select_limit(config)
    if select_limit <= config.triage_profile_limit or len(cases) <= config.triage_profile_limit:
        return cases, None

    successful_cases: list[CaseResult] = []
    for case in cases:
        if case.analysis_status == "ok":
            successful_cases.append(case)
        if len(successful_cases) >= config.triage_profile_limit:
            return (
                successful_cases,
                "Large analyzer-only batch backfill retained "
                f"{len(successful_cases)} successfully analyzed cases from {len(cases)} "
                f"processed candidates; {len(cases) - len(successful_cases)} candidates "
                "without retained successful analysis were omitted "
                "from the final summary.",
            )

    return (
        cases,
        "Large analyzer-only batch backfill could not reach "
        f"{config.triage_profile_limit} successfully analyzed cases; retained all "
        f"{len(cases)} processed candidates with {len(successful_cases)} successful analyses.",
    )
