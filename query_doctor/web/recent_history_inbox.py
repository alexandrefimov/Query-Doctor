"""Read-only raw-free Recent history projection for Query Inbox."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from query_doctor.recent.batch_config import (
    DEFAULT_RECENT_HISTORY_POSTGRES_DSN_ENV,
    expand_optional_path,
    normalize_recent_history_backend,
    validate_env_var_name,
)
from query_doctor.recent.history_store import RecentHistoryStoreError
from query_doctor.recent.postgres_history_store import PostgresRecentHistoryStore
from query_doctor.recent.profile_budget import (
    ANALYSIS_CACHE_SUMMARY_FIELDS,
    PROFILE_STATUS_ANALYZED,
    PROFILE_STATUS_FAILED,
    PROFILE_STATUS_NOT_COLLECTED,
    PROFILE_STATUS_PENDING,
    PROFILE_STATUS_PROCESSING,
    PROFILE_STATUS_RETRY_PENDING,
    safe_optional_profile_error_code,
)
from query_doctor.recent.sqlite_history_store import SqliteRecentHistoryStore
from query_doctor.safety.browser_display import redact_browser_display_text
from query_doctor.web.config import (
    load_web_local_config,
    optional_config_string,
)
from query_doctor.web.models import WebSettings
from query_doctor.web.recent_history_collector_status import collector_summary_from_config
from query_doctor.web.operator_readiness_status import operator_readiness_summary_from_config


MAX_HISTORY_INBOX_ROWS = 500
MATERIALIZED_ANALYSIS_FIELDS = ANALYSIS_CACHE_SUMMARY_FIELDS
COLLECTOR_FRESHNESS_STALE_AFTER_MINUTES = 120


def recent_history_inbox_summary_from_settings(settings: WebSettings) -> dict[str, object] | None:
    if settings.public_demo:
        return None
    try:
        config_values = load_web_local_config(settings.config, cwd=Path.cwd())
        store, backend = _history_store_from_config(config_values)
        if store is None:
            return None
        payloads = store.load_materialized_payloads()
        retained_count = store.count_summaries()
        operator_readiness = operator_readiness_summary_from_config(
            config_values,
            cwd=Path.cwd(),
        )
        collector_run = collector_summary_from_config(
            config_values,
            cwd=Path.cwd(),
        )
        profile_backlog_health: Mapping[str, object] | None = None
        try:
            profile_backlog_health = store.summarize_profile_backlog_health(
                now_iso=datetime.now(timezone.utc).isoformat()
            ).safe_payload()
        except (OSError, RecentHistoryStoreError):
            profile_backlog_health = None
    except (OSError, ValueError, RecentHistoryStoreError):
        return recent_history_unavailable_summary()
    return recent_history_summary_from_payloads(
        payloads,
        backend=backend,
        retained_count=retained_count,
        operator_readiness=operator_readiness,
        collector_run=collector_run,
        profile_backlog_health=profile_backlog_health,
    )


def recent_history_summary_from_payloads(
    payloads: list[dict[str, object]],
    *,
    backend: str,
    retained_count: int | None = None,
    operator_readiness: Mapping[str, object] | None = None,
    collector_run: Mapping[str, object] | None = None,
    profile_backlog_health: Mapping[str, object] | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    cases = [
        _history_case(index, payload)
        for index, payload in enumerate(payloads[:MAX_HISTORY_INBOX_ROWS], start=1)
        if isinstance(payload, Mapping)
    ]
    from_time = _min_nonempty(_safe_string(case.get("start_time")) for case in cases)
    to_time = _max_nonempty(_safe_string(case.get("end_time")) for case in cases)
    retained = retained_count if retained_count is not None else len(payloads)
    running_seen = any(_case_is_running(case) for case in cases)
    profile_status_counts = _profile_status_counts_from_payloads(payloads)
    details_ready_count = _details_ready_count_from_payloads(payloads)
    collector_freshness = _history_collector_freshness(
        payloads,
        retained_count=retained,
        displayed_count=len(cases),
        now=now,
    )
    warnings: list[str] = []
    if retained > len(cases):
        warnings.append(
            f"Online history retained {retained} summary rows; showing the newest {len(cases)} rows."
        )
    summary: dict[str, object] = {
        "mode": "recent-history-online",
        "query_profile_source": "history",
        "source_visibility": "safe",
        "selected_count": len(cases),
        "summaries_inspected": retained,
        "triage_profile_limit": len(cases),
        "from_time": from_time,
        "to_time": to_time,
        "include_failed": True,
        "include_running": running_seen,
        "include_history": True,
        "history_profile_status_counts": profile_status_counts,
        "history_details_ready_count": details_ready_count,
        "history_collector_freshness": collector_freshness,
        "warnings": warnings,
        "cases": cases,
        "materialized_case_index": {
            "schema_version": 1,
            "source": {
                "mode": "recent-history-online",
                "query_profile_source": "history",
                "source_visibility": "safe",
            },
            "scope": {
                "from_time": from_time,
                "to_time": to_time,
                "include_failed": True,
                "include_running": running_seen,
                "only_running": False,
                "order": "recent",
            },
            "coverage": {
                "case_count": len(cases),
                "retained_summary_count": retained,
                "displayed_summary_count": len(cases),
                "history_backend": backend,
                "warning_count": len(warnings),
                "profile_status_counts": profile_status_counts,
                "details_ready_count": details_ready_count,
            },
            "freshness": {
                "state": "online_history",
                "from_time": from_time,
                "to_time": to_time,
            },
            "cases": cases,
        },
    }
    if operator_readiness is not None:
        summary["operator_readiness"] = dict(operator_readiness)
    if collector_run is not None:
        summary["history_collector_run"] = dict(collector_run)
    if profile_backlog_health is not None:
        summary["history_profile_backlog_health"] = dict(profile_backlog_health)
    return summary


def recent_history_unavailable_summary() -> dict[str, object]:
    return {
        "mode": "recent-history-online",
        "query_profile_source": "history",
        "source_visibility": "safe",
        "selected_count": 0,
        "summaries_inspected": 0,
        "warnings": [
            "Online history is configured, but the Recent history store could not be read."
        ],
        "cases": [],
    }


def _history_store_from_config(
    config_values: dict[str, object],
) -> tuple[object | None, str]:
    db = expand_optional_path(
        optional_config_string(config_values, "recent_history_db"), cwd=Path.cwd()
    )
    backend = normalize_recent_history_backend(
        optional_config_string(config_values, "recent_history_backend"),
        recent_history_db=db,
    )
    if backend == "disabled":
        return None, backend
    if backend == "sqlite":
        if db is None:
            raise RecentHistoryStoreError("recent_history_sqlite_db_missing")
        return SqliteRecentHistoryStore(db), backend
    dsn_env = validate_env_var_name(
        optional_config_string(config_values, "recent_history_postgres_dsn_env")
        or DEFAULT_RECENT_HISTORY_POSTGRES_DSN_ENV,
        name="recent_history_postgres_dsn_env",
    )
    return PostgresRecentHistoryStore.from_env(dsn_env, env=dict(os.environ)), backend


def _history_case(index: int, payload: Mapping[str, object]) -> dict[str, object]:
    duration_ms = _nonnegative_int(payload.get("duration_ms"))
    duration_sec = round(duration_ms / 1000, 3) if duration_ms is not None else None
    suspicion_level = _safe_string(payload.get("suspicion_level"))
    profile_status = _normalized_profile_status(payload.get("profile_status"))
    profile_last_error_code = safe_optional_profile_error_code(
        payload.get("profile_last_error_code")
    )
    collection_status, analysis_status, failure_category = _profile_status_case_fields(
        profile_status,
        profile_last_error_code=profile_last_error_code,
    )
    analysis_payload = _analysis_cache_payload(payload.get("analysis_cache_payload"))
    materialized = profile_status == PROFILE_STATUS_ANALYZED and bool(analysis_payload)
    case = {
        "candidate_rank": index,
        "triage_rank": index,
        "query_id": _safe_string(payload.get("query_id")),
        "duration_sec": duration_sec,
        "start_time": _safe_string(payload.get("start_time")),
        "end_time": _safe_string(payload.get("end_time")),
        "status": _safe_string(payload.get("status")),
        "query_state": _safe_string(payload.get("query_state")),
        "user": _safe_string(payload.get("user")),
        "pool": _safe_string(payload.get("pool")),
        "query_type": _safe_string(payload.get("query_type")),
        "sql_verb": _safe_string(payload.get("sql_verb")),
        "profile_status": profile_status,
        "collection_status": collection_status,
        "analysis_status": analysis_status,
        "metadata_status": "not_materialized",
        "score": _nonnegative_int(payload.get("suspicion_score")) or 0,
        "score_severity": "failed"
        if profile_status == PROFILE_STATUS_FAILED
        else _score_severity(suspicion_level),
        "score_reasons": _safe_reason_list(payload.get("suspicion_reasons")),
        "report_generated": False,
        "report_validation_status": "not_materialized",
    }
    if materialized:
        case["case_index"] = index
        case.update(_project_analysis_cache_payload(analysis_payload))
    if failure_category:
        case["failure_category"] = failure_category
    return case


def _normalized_profile_status(value: object) -> str:
    status = _safe_string(value).lower() or PROFILE_STATUS_NOT_COLLECTED
    if status in {
        PROFILE_STATUS_NOT_COLLECTED,
        PROFILE_STATUS_PENDING,
        PROFILE_STATUS_PROCESSING,
        PROFILE_STATUS_RETRY_PENDING,
        PROFILE_STATUS_ANALYZED,
        PROFILE_STATUS_FAILED,
    }:
        return status
    return PROFILE_STATUS_NOT_COLLECTED


def _profile_status_case_fields(
    status: str,
    *,
    profile_last_error_code: str | None = None,
) -> tuple[str, str, str | None]:
    if status == PROFILE_STATUS_ANALYZED:
        return "profile_collected", "profile_analyzed", None
    if status == PROFILE_STATUS_FAILED:
        return (
            "summary_history",
            "failed",
            profile_last_error_code or "recent_profile_worker_failed",
        )
    if status == PROFILE_STATUS_PROCESSING:
        return "summary_history", "profile_processing", None
    if status == PROFILE_STATUS_RETRY_PENDING:
        return "summary_history", "profile_retry_pending", profile_last_error_code
    if status == PROFILE_STATUS_PENDING:
        return "summary_history", "profile_pending", None
    return "summary_history", "profile_not_collected", None


def _profile_status_counts(cases: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        status = _normalized_profile_status(case.get("profile_status"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _profile_status_counts_from_payloads(
    payloads: Iterable[Mapping[str, object]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        status = _normalized_profile_status(payload.get("profile_status"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _details_ready_count_from_payloads(payloads: Iterable[Mapping[str, object]]) -> int:
    ready = 0
    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        if _normalized_profile_status(payload.get("profile_status")) != PROFILE_STATUS_ANALYZED:
            continue
        if _analysis_cache_payload(payload.get("analysis_cache_payload")):
            ready += 1
    return ready


def _history_collector_freshness(
    payloads: Iterable[Mapping[str, object]],
    *,
    retained_count: int,
    displayed_count: int,
    now: datetime | None = None,
) -> dict[str, object]:
    retained = max(0, retained_count)
    displayed = max(0, displayed_count)
    latest = max(
        (
            parsed
            for payload in payloads
            if isinstance(payload, Mapping)
            for parsed in (_parse_history_timestamp(payload.get("recorded_at_iso")),)
            if parsed is not None
        ),
        default=None,
    )
    freshness: dict[str, object] = {
        "schema_version": 1,
        "status": "empty" if retained == 0 else "unknown",
        "retained_summary_count": retained,
        "displayed_summary_count": displayed,
        "stale_after_minutes": COLLECTOR_FRESHNESS_STALE_AFTER_MINUTES,
    }
    if latest is None:
        return freshness
    effective_now = _effective_utc_now(now)
    age_minutes = max(0, int((effective_now - latest).total_seconds() // 60))
    freshness.update(
        {
            "status": "stale" if age_minutes > COLLECTOR_FRESHNESS_STALE_AFTER_MINUTES else "fresh",
            "latest_recorded_at_iso": latest.isoformat(),
            "age_minutes": age_minutes,
        }
    )
    return freshness


def _parse_history_timestamp(value: object) -> datetime | None:
    text = _safe_string(value)
    if not text or text.lower() in {"synthetic", "unknown", "none", "null"}:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _effective_utc_now(now: datetime | None) -> datetime:
    effective_now = now or datetime.now(timezone.utc)
    if effective_now.tzinfo is None:
        return effective_now.replace(tzinfo=timezone.utc)
    return effective_now.astimezone(timezone.utc)


def _analysis_cache_payload(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _project_analysis_cache_payload(payload: Mapping[str, object]) -> dict[str, object]:
    projected: dict[str, object] = {}
    for field in MATERIALIZED_ANALYSIS_FIELDS:
        if field in payload:
            projected[field] = _safe_analysis_value(payload.get(field))
    return projected


def _safe_analysis_value(value: Any) -> object:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_browser_display_text(
            value,
            redact_field_names=True,
            redact_artifact_markers=True,
            redact_model_names=True,
            redact_sql_snippets=True,
            redact_infrastructure=True,
            max_chars=512,
        )
    if isinstance(value, list):
        return [_safe_analysis_value(item) for item in value[:20]]
    if isinstance(value, Mapping):
        return {
            str(key): _safe_analysis_value(item)
            for key, item in list(value.items())[:20]
            if isinstance(key, str)
        }
    return _safe_string(value)


def _score_severity(suspicion_level: str) -> str:
    if suspicion_level in {"critical", "high"}:
        return "high"
    if suspicion_level in {"medium", "low"}:
        return "suspicious"
    return "clean"


def _safe_reason_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [_safe_string(item) for item in value[:20] if _safe_string(item)]


def _safe_string(value: object) -> str:
    return str(value or "").strip()[:256]


def _safe_bool(value: object) -> bool:
    return bool(value) if isinstance(value, bool) else False


def _case_is_running(case: Mapping[str, object]) -> bool:
    status = _safe_string(case.get("status")).lower()
    query_state = _safe_string(case.get("query_state")).lower()
    return (
        _safe_bool(case.get("include_running")) or status == "running" or query_state == "running"
    )


def _min_nonempty(values: Iterable[object]) -> str:
    nonempty = [value for value in values if isinstance(value, str) and value]
    return min(nonempty, default="")


def _max_nonempty(values: Iterable[object]) -> str:
    nonempty = [value for value in values if isinstance(value, str) and value]
    return max(nonempty, default="")


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
