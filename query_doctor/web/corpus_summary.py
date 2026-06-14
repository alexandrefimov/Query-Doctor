"""In-memory summaries for already staged local profile cases."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from query_doctor.analyzer.context_collection import MANUAL_PROFILE_TEXT_SOURCE
from query_doctor.cm.client import validate_cm_query_id_path_segment
from query_doctor.cm.models import CMAdapterError
from query_doctor.web.case_files import (
    build_query_id_summary_case,
    case_relative_file_path,
    read_case_metadata,
    resolve_under_repo,
)
from query_doctor.web.models import WebSettings


@dataclass(frozen=True)
class CorpusSummaryRuntime:
    settings: WebSettings
    case_count: int


def prepare_corpus_summary_runtime(settings: WebSettings) -> CorpusSummaryRuntime | None:
    if settings.batch_summary is not None or settings.public_demo:
        return None
    summary_root = resolve_under_repo(settings.repo_dir, settings.corpus_dir)
    summary = build_manual_profile_corpus_summary(summary_root)
    if summary is None:
        return None
    cases = summary.get("cases")
    case_count = len(cases) if isinstance(cases, list) else 0
    return CorpusSummaryRuntime(
        settings=replace(
            settings,
            corpus_summary=summary,
            corpus_summary_root=summary_root,
        ),
        case_count=case_count,
    )


def build_manual_profile_corpus_summary(corpus_dir: Path) -> dict[str, object] | None:
    root = corpus_dir.expanduser().resolve(strict=False)
    if not root.is_dir():
        return None
    cases: list[dict[str, object]] = []
    for case_index, (query_id, case_dir) in enumerate(iter_manual_profile_cases(root), start=1):
        cases.append(
            build_query_id_summary_case(
                query_id,
                case_dir,
                case_index=case_index,
                include_batch_fields=True,
                case_dir_reference=case_dir.name,
            )
        )
    if not cases:
        return None
    return {
        "mode": "manual-profile-corpus",
        "query_profile_source": "manual_profile_text",
        "source_visibility": "safe",
        "runtime_metrics_provider": "none",
        "summaries_inspected": len(cases),
        "selected_count": len(cases),
        "candidate_exclusion_count": 0,
        "duration_filter": "none",
        "duration_filter_mode": "none",
        "triage_profile_limit": len(cases),
        "metadata_top_limit": 0,
        "collect_cm_timeseries": False,
        "collect_prometheus_timeseries": False,
        "collect_cm_events": False,
        "top_reports": 0,
        "cm_jobs": 0,
        "jobs": 0,
        "metadata_jobs": 0,
        "recent_window_minutes": None,
        "query_type_filter": "all",
        "include_failed": True,
        "include_running": False,
        "only_running": False,
        "user_filter_present": False,
        "pool_filter_present": False,
        "order": "local-profile-corpus",
        "warnings": [
            "Local exported Impala text profile cases loaded from the configured corpus directory",
            "No live Cloudera Manager, direct Impala, metadata, events, or runtime metrics collection was run by the web server",
        ],
        "cases": cases,
    }


def iter_manual_profile_cases(corpus_dir: Path) -> list[tuple[str, Path]]:
    cases: list[tuple[str, Path]] = []
    for child in sorted(corpus_dir.iterdir(), key=lambda path: path.name):
        if child.name.startswith(".") or not child.is_dir():
            continue
        try:
            case_dir = child.resolve(strict=True)
            case_dir.relative_to(corpus_dir)
        except (OSError, ValueError):
            continue
        metadata = read_case_metadata(case_dir)
        if metadata.get("profile_source") != MANUAL_PROFILE_TEXT_SOURCE:
            continue
        query_id = metadata.get("query_id")
        if not isinstance(query_id, str):
            continue
        try:
            validated_query_id = validate_cm_query_id_path_segment(query_id)
        except CMAdapterError:
            continue
        if not manual_profile_case_is_renderable(case_dir):
            continue
        cases.append((validated_query_id, case_dir))
    return cases


def manual_profile_case_is_renderable(case_dir: Path) -> bool:
    return all(
        case_relative_file_path(case_dir, name) is not None
        for name in (
            "profile_digest.md",
            "analysis_facts.md",
            "query_metadata.json",
            "collection_warnings.txt",
        )
    )
