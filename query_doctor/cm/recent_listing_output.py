"""Sanitized Recent query listing output helpers."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from query_doctor.cm.models import (
    CMQuerySummary,
    CollectorConfig,
    RecentQueryCandidate,
    sanitize_cm_url_for_display,
)
from query_doctor.safety.redaction import sanitize_text_for_log


def sanitize_query_summary_for_log(summary: CMQuerySummary) -> dict[str, object]:
    return {
        "query_id": summary.query_id,
        "start_time": summary.start_time,
        "end_time": summary.end_time,
        "duration_ms": summary.duration_ms,
        "status": summary.status,
        "user": summary.user,
        "pool": summary.pool,
        "query_type": summary.query_type,
    }


def sanitized_recent_candidate(candidate: RecentQueryCandidate) -> dict[str, object]:
    summary = candidate.summary
    return {
        "query_id": summary.query_id,
        "selected": candidate.selected,
        "reason": candidate.reason,
        "sql_verb": candidate.sql_verb,
        "query_type": summary.query_type,
        "status": summary.status,
        "start_time": summary.start_time,
        "end_time": summary.end_time,
        "duration_ms": summary.duration_ms,
        "duration_sec": summary.duration_sec,
        "user": "<user>" if summary.user else None,
        "pool": sanitize_text_for_log(summary.pool) if summary.pool else None,
    }


def write_recent_candidates_json(
    path: Path,
    *,
    config: CollectorConfig,
    candidates: list[RecentQueryCandidate],
    warnings: Iterable[str] = (),
) -> None:
    payload = {
        "mode": "recent-query-listing",
        "cm_url": sanitize_cm_url_for_display(config.cm_url),
        "cluster": config.cluster,
        "service": config.service,
        "recent_limit": config.recent_limit,
        "recent_select": config.recent_select,
        "recent_window_minutes": config.recent_window_minutes,
        "recent_min_duration_sec": config.recent_min_duration_sec,
        "recent_max_duration_sec": config.recent_max_duration_sec,
        "recent_order": config.recent_order,
        "inspected_count": len(candidates),
        "selected_count": sum(1 for candidate in candidates if candidate.selected),
        "warnings": [sanitize_text_for_log(warning) for warning in warnings],
        "candidates": [sanitized_recent_candidate(candidate) for candidate in candidates],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
