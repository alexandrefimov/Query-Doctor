"""Finished/Running case detail resolution helpers for the web server."""

from __future__ import annotations

import json
import re
from dataclasses import replace

from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebSettings
from query_doctor.web.presenters.recent_scan import case_score_severity, present_recent_scan_summary
from query_doctor.web.trusted_artifacts import decorate_cases_with_optimizer_artifact_status
from query_doctor.web.ui.recent_scan_results import filter_rows_by_query_group, sort_rows_for_query_group


def batch_page_settings(settings: WebSettings, job_store: WebJobStore) -> WebSettings:
    if settings.batch_summary is not None:
        return settings
    latest = job_store.latest_batch_summary()
    if latest is None:
        return settings
    return replace(settings, batch_summary=latest)


def running_page_settings(settings: WebSettings, job_store: WebJobStore) -> WebSettings:
    latest = job_store.latest_running_summary()
    if latest is None:
        return replace(settings, batch_summary=None)
    return replace(settings, batch_summary=latest)


def running_detail_kwargs() -> dict[str, str]:
    return {
        "workflow_title": "Running Queries",
        "list_href": "/running#recent-results",
        "detail_base_path": "/running/case",
        "active_nav": "running",
    }


def resolve_running_case_detail_settings(
    settings: WebSettings,
    job_store: WebJobStore,
    case_id: str,
) -> tuple[WebSettings, dict[str, object] | None]:
    running_settings = running_page_settings(settings, job_store)
    running_summary = load_batch_summary(running_settings)
    running_case = find_batch_case(running_summary, case_id) if running_summary is not None else None
    if running_case is not None:
        running_case = case_with_detail_ranks(running_summary, case_id, running_case)
    return running_settings, running_case


def resolve_case_detail_settings(
    settings: WebSettings,
    job_store: WebJobStore,
    case_id: str,
) -> tuple[WebSettings, dict[str, object] | None]:
    batch_settings = batch_page_settings(settings, job_store)
    summary = load_batch_summary(batch_settings)
    case = find_batch_case(summary, case_id) if summary is not None else None
    if case is not None:
        return batch_settings, case_with_detail_ranks(summary, case_id, case)
    running_settings = running_page_settings(settings, job_store)
    if running_settings.batch_summary != batch_settings.batch_summary:
        running_summary = load_batch_summary(running_settings)
        running_case = find_batch_case(running_summary, case_id) if running_summary is not None else None
        if running_case is not None:
            return running_settings, case_with_detail_ranks(running_summary, case_id, running_case)
    return batch_settings, None


def load_batch_summary(settings: WebSettings) -> dict[str, object] | None:
    summary_path = settings.batch_summary
    if summary_path is None:
        return None
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return decorate_cases_with_optimizer_artifact_status(payload) if isinstance(payload, dict) else None


def case_with_detail_ranks(
    summary: dict[str, object] | None,
    case_id: str,
    case: dict[str, object],
) -> dict[str, object]:
    rank_fields = batch_case_detail_rank_fields(summary, case_id)
    if not rank_fields:
        return case
    decorated = dict(case)
    decorated.update(rank_fields)
    return decorated


def batch_case_detail_rank_fields(summary: dict[str, object] | None, case_id: str) -> dict[str, int]:
    if not isinstance(summary, dict):
        return {}
    view = present_recent_scan_summary(summary)
    result: dict[str, int] = {}
    for row in view.rows:
        if row.case_id == case_id:
            result["_detail_overall_rank"] = row.rank
            break
    for group, key in (
        ("optimization", "_detail_optimization_rank"),
        ("stats", "_detail_stats_rank"),
    ):
        rows = sort_rows_for_query_group(filter_rows_by_query_group(view.rows, group), group)
        for display_rank, row in enumerate(rows, start=1):
            if row.case_id == case_id:
                result[key] = display_rank
                break
    return result


def find_batch_case(summary: dict[str, object], case_id: str) -> dict[str, object] | None:
    if not re.fullmatch(r"case-[0-9]{3}", case_id):
        return None
    cases = summary.get("cases")
    if not isinstance(cases, list):
        return None
    for case in cases:
        if not isinstance(case, dict):
            continue
        try:
            index = int(case.get("case_index"))
        except (TypeError, ValueError):
            continue
        if f"case-{index:03d}" == case_id:
            return case
    return None


def case_allows_llm_report(case: dict[str, object]) -> bool:
    return case_score_severity(case) != "clean"
