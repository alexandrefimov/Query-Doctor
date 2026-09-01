"""Small in-process cache for safe Recent scan presenter views."""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from query_doctor.case_metadata import QUERY_METADATA_FILENAMES
from query_doctor.web.action_outcomes import (
    WorkloadOutcomeMetric,
    action_outcomes_path,
    workload_outcome_metrics_by_fingerprint,
)
from query_doctor.web.command_builders import (
    OPTIMIZED_QUERY_NAME,
    OPTIMIZED_QUERY_PARTIAL_NAME,
    OPTIMIZED_QUERY_RECOMMENDATIONS_NAME,
    OPTIMIZED_QUERY_VALIDATION_MARKER,
)
from query_doctor.web.presenters.recent_scan import present_recent_scan_summary
from query_doctor.web.presenters.recent_scan_models import RecentScanSummaryView
from query_doctor.web.trusted_artifacts import (
    decorate_cases_with_optimizer_artifact_status,
    optimizer_artifact_dirs,
)


MAX_RECENT_SCAN_SUMMARY_VIEW_CACHE_ENTRIES = 8
SOURCE_SQL_STATE_FILES = (
    "original_query.sql",
    "query.sql",
    "sql.sql",
    "impala_context/original_query.sql",
)
OPTIMIZER_ARTIFACT_STATE_FILES = (
    "analysis_facts.md",
    OPTIMIZED_QUERY_PARTIAL_NAME,
    OPTIMIZED_QUERY_NAME,
    OPTIMIZED_QUERY_RECOMMENDATIONS_NAME,
    OPTIMIZED_QUERY_VALIDATION_MARKER,
    *SOURCE_SQL_STATE_FILES,
    *QUERY_METADATA_FILENAMES,
)


@dataclass(frozen=True)
class FileState:
    path: str
    mtime_ns: int
    size: int


@dataclass(frozen=True)
class RecentScanSummaryViewCacheKey:
    summary: FileState
    language: str
    action_outcomes: FileState
    optimizer_artifacts_digest: str


_CACHE_LOCK = threading.Lock()
_SUMMARY_VIEW_CACHE: OrderedDict[RecentScanSummaryViewCacheKey, RecentScanSummaryView] = (
    OrderedDict()
)


@dataclass(frozen=True)
class _SharedRecentScanSummaryView:
    source: object
    workload_outcome_metrics: object | None
    view: RecentScanSummaryView


_SHARED_SUMMARY_VIEWS: ContextVar[dict[tuple[int, int], _SharedRecentScanSummaryView] | None] = (
    ContextVar(
        "recent_scan_shared_summary_views",
        default=None,
    )
)


@contextmanager
def shared_recent_scan_summary_views():
    """Reuse presenter work only within one page render."""

    token = _SHARED_SUMMARY_VIEWS.set({})
    try:
        yield
    finally:
        _SHARED_SUMMARY_VIEWS.reset(token)


def recent_scan_summary_view_for_render(
    summary: dict[str, Any],
    *,
    cache_source: object | None = None,
    workload_outcome_metrics: dict[str, WorkloadOutcomeMetric] | None = None,
    reuse_existing_for_source: bool = False,
) -> RecentScanSummaryView:
    """Present a summary once per render without retaining it across requests."""

    memo = _SHARED_SUMMARY_VIEWS.get()
    if memo is None:
        return present_recent_scan_summary(
            summary,
            workload_outcome_metrics=workload_outcome_metrics,
        )

    source = summary if cache_source is None else cache_source
    if reuse_existing_for_source:
        for cached in memo.values():
            if cached.source is source:
                return cached.view
    normalized_metrics = workload_outcome_metrics or None
    key = (
        id(source),
        0 if normalized_metrics is None else id(normalized_metrics),
    )
    cached = memo.get(key)
    if cached is not None and cached.source is source:
        if (
            normalized_metrics is None and cached.workload_outcome_metrics is None
        ) or cached.workload_outcome_metrics is normalized_metrics:
            return cached.view

    view = present_recent_scan_summary(
        summary,
        workload_outcome_metrics=workload_outcome_metrics,
    )
    memo[key] = _SharedRecentScanSummaryView(
        source=source,
        workload_outcome_metrics=normalized_metrics,
        view=view,
    )
    return view


def cached_recent_scan_summary_view(
    summary: dict[str, Any],
    *,
    summary_path: Path,
    language: str = "en",
) -> RecentScanSummaryView:
    """Return a raw-free presenter view keyed by source and dynamic status state."""

    key = recent_scan_summary_view_cache_key(
        summary,
        summary_path=summary_path,
        language=language,
    )
    with _CACHE_LOCK:
        cached = _SUMMARY_VIEW_CACHE.get(key)
        if cached is not None:
            _SUMMARY_VIEW_CACHE.move_to_end(key)
            return cached

    view = present_recent_scan_summary(
        decorate_cases_with_optimizer_artifact_status(summary),
        workload_outcome_metrics=workload_outcome_metrics_by_fingerprint(),
    )
    with _CACHE_LOCK:
        existing = _SUMMARY_VIEW_CACHE.get(key)
        if existing is not None:
            _SUMMARY_VIEW_CACHE.move_to_end(key)
            return existing
        _SUMMARY_VIEW_CACHE[key] = view
        while len(_SUMMARY_VIEW_CACHE) > MAX_RECENT_SCAN_SUMMARY_VIEW_CACHE_ENTRIES:
            _SUMMARY_VIEW_CACHE.popitem(last=False)
    return view


def recent_scan_summary_view_cache_key(
    summary: dict[str, Any],
    *,
    summary_path: Path,
    language: str = "en",
) -> RecentScanSummaryViewCacheKey:
    return RecentScanSummaryViewCacheKey(
        summary=file_state(summary_path),
        language=str(language or "en"),
        action_outcomes=file_state(action_outcomes_path()),
        optimizer_artifacts_digest=optimizer_artifacts_digest(summary),
    )


def file_state(path: Path) -> FileState:
    expanded = path.expanduser()
    try:
        stat = expanded.stat()
    except OSError:
        return FileState(path=str(expanded), mtime_ns=-1, size=-1)
    return FileState(path=str(expanded), mtime_ns=stat.st_mtime_ns, size=stat.st_size)


def optimizer_artifacts_digest(summary: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    cases = summary.get("cases")
    if not isinstance(cases, list):
        digest.update(b"cases:not-list")
        return digest.hexdigest()
    for index, case in enumerate(cases):
        digest.update(f"case:{index}:".encode("utf-8"))
        if not isinstance(case, dict):
            digest.update(b"non-dict;")
            continue
        case_dir_value = case.get("case_dir")
        if not isinstance(case_dir_value, str) or not case_dir_value.strip():
            digest.update(b"case-dir:missing;")
            continue
        case_dir = Path(case_dir_value)
        update_path_state_digest(digest, "case-dir", case_dir)
        for artifact_dir in optimizer_artifact_dirs(case_dir):
            update_path_state_digest(digest, "artifact-dir", artifact_dir)
            for name in OPTIMIZER_ARTIFACT_STATE_FILES:
                update_path_state_digest(digest, name, artifact_dir / name)
    return digest.hexdigest()


def update_path_state_digest(digest: Any, label: str, path: Path) -> None:
    digest.update(label.encode("utf-8", errors="replace"))
    digest.update(b":")
    digest.update(hashlib.sha256(str(path).encode("utf-8", errors="replace")).digest())
    digest.update(b":")
    try:
        stat = path.stat()
    except OSError:
        digest.update(b"missing;")
        return
    digest.update(b"dir:" if path.is_dir() else b"file:" if path.is_file() else b"other:")
    digest.update(str(stat.st_mtime_ns).encode("ascii"))
    digest.update(b":")
    digest.update(str(stat.st_size).encode("ascii"))
    digest.update(b";")


def clear_recent_scan_summary_view_cache() -> None:
    with _CACHE_LOCK:
        _SUMMARY_VIEW_CACHE.clear()
