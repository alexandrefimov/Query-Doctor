"""Raw-free configured Recent summary collector projection for Online History."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from query_doctor.recent.batch_config import expand_optional_path
from query_doctor.recent.collector_summary import (
    COLLECTOR_STATUSES,
    SUMMARY_KIND as COLLECTOR_SUMMARY_KIND,
)
from query_doctor.recent.operator_readiness import unsafe_summary_payload
from query_doctor.web.config import optional_config_string


COLLECTOR_SUMMARY_CONFIG_KEY = "recent_history_collector_summary_json"
MAX_COLLECTOR_ISSUE_CODES = 3
COLLECTOR_ISSUE_CODES = frozenset(
    {
        "discovery_failed",
        "recent_history_disabled",
        "recent_history_warning",
        "summary_kind_drift",
        "summary_raw_free_flags_failed",
        "summary_unavailable",
        "summary_unsafe",
        "unknown_issue",
    }
)


def collector_summary_from_config(
    config_values: dict[str, object],
    *,
    cwd: Path,
) -> dict[str, object] | None:
    configured_path = expand_optional_path(
        optional_config_string(config_values, COLLECTOR_SUMMARY_CONFIG_KEY),
        cwd=cwd,
    )
    if configured_path is None:
        return None
    try:
        payload = json.loads(configured_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _collector_summary_unavailable("summary_unavailable")
    if not isinstance(payload, Mapping):
        return _collector_summary_unavailable("summary_unavailable")
    return project_collector_summary(payload)


def project_collector_summary(payload: Mapping[str, object]) -> dict[str, object]:
    if unsafe_summary_payload(payload):
        return _collector_summary_unavailable("summary_unsafe", status="blocked")
    if payload.get("summary_kind") != COLLECTOR_SUMMARY_KIND:
        return _collector_summary_unavailable("summary_kind_drift", status="blocked")
    if payload.get("raw_output") is True or payload.get("sensitive_value_echo") is True:
        return _collector_summary_unavailable(
            "summary_raw_free_flags_failed",
            status="blocked",
        )
    return {
        "status": _collector_status(payload.get("status")),
        "observed_at_iso": _safe_observed_at(payload.get("observed_at_iso")),
        "discover_only": payload.get("discover_only") is True,
        "history_backend": _history_backend(payload.get("history_backend")),
        "summaries_inspected": _safe_nonnegative_int(payload.get("summaries_inspected")),
        "candidates_discovered": _safe_nonnegative_int(payload.get("candidates_discovered")),
        "selected_count": _safe_nonnegative_int(payload.get("selected_count")),
        "summaries_recorded": _safe_nonnegative_int(payload.get("summaries_recorded")),
        "profile_jobs_planned": _safe_nonnegative_int(payload.get("profile_jobs_planned")),
        "issue_count": _safe_list_count(payload.get("issue_codes")),
        "issue_codes": _safe_collector_issue_codes(payload.get("issue_codes")),
    }


def _collector_summary_unavailable(
    issue_code: str,
    *,
    status: str = "unavailable",
) -> dict[str, object]:
    return {
        "status": status,
        "observed_at_iso": "",
        "discover_only": False,
        "history_backend": "unknown",
        "summaries_inspected": 0,
        "candidates_discovered": 0,
        "selected_count": 0,
        "summaries_recorded": 0,
        "profile_jobs_planned": 0,
        "issue_count": 1,
        "issue_codes": _safe_collector_issue_codes([issue_code]),
    }


def _collector_status(value: object) -> str:
    status = _safe_label(value)
    if status in COLLECTOR_STATUSES:
        return status
    if status in {"blocked", "unavailable"}:
        return status
    return "unknown"


def _history_backend(value: object) -> str:
    backend = _safe_label(value)
    return backend if backend in {"disabled", "sqlite", "postgres"} else "unknown"


def _safe_collector_issue_codes(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    issue_codes: list[str] = []
    for item in value:
        code = _safe_label(item)
        if code not in COLLECTOR_ISSUE_CODES:
            code = "unknown_issue"
        if code not in issue_codes:
            issue_codes.append(code)
        if len(issue_codes) >= MAX_COLLECTOR_ISSUE_CODES:
            break
    return issue_codes


def _safe_observed_at(value: object) -> str:
    text = str(value or "").strip()[:64]
    if not text or text.lower() in {"none", "null", "unknown"}:
        return ""
    return text


def _safe_label(value: object) -> str:
    text = str(value or "").strip().lower()[:64]
    if not text:
        return "unknown"
    return "".join(
        char if ("a" <= char <= "z" or "0" <= char <= "9" or char in {"_", "-"}) else "_"
        for char in text
    )


def _safe_nonnegative_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _safe_list_count(value: object) -> int:
    return len(value) if isinstance(value, list) else 0
