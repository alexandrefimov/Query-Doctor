"""Raw-free unknown-primary closure taxonomy helpers."""

from __future__ import annotations

import re
from collections import Counter

from query_doctor.report.safety_validation import contains_raw_sql_like_text
from query_doctor.safety import redaction


URL_RE = re.compile(r"\bhttps?://", re.IGNORECASE)
LOCAL_PATH_RE = re.compile(r"(?<![\w/])(?:/private)?/tmp/|(?<![\w/])/Users/")

UNKNOWN_REASON_CATEGORY_BY_REASON = {
    "codegen_finding_not_primary_supported": "analyzer_primary_branch_gap",
    "data_movement_context_only": "data_movement_context_only_gap",
    "memory_estimate_context_only": "memory_context_only_gap",
    "missing_reason": "unknown_reason_missing",
    "no_primary_branch_supported": "analyzer_primary_branch_gap",
    "operator_time_not_dominant": "operator_timing_gap",
    "profile_dialect_not_supported_for_primary": "profile_dialect_gap",
    "scan_skew_medium_supporting_only": "scan_skew_supporting_only_gap",
    "storage_context_view_only": "storage_context_only_gap",
    "tail_candidates": "client_fetch_tail_followup",
    "unsafe_reason": "unsafe_unknown_primary_reason",
    "very_short_query_or_unknown_wall_clock": "short_or_missing_wall_clock_boundary",
    "wall_clock_not_explained_by_mapped_operators": "operator_timing_gap",
}
UNKNOWN_CATEGORY_CLOSURE_TRACK = {
    "analyzer_primary_branch_gap": "add_deterministic_primary_branch_evidence",
    "client_fetch_tail_followup": "calibrate_client_fetch_tail_evidence",
    "data_movement_context_only_gap": "add_selected_query_data_movement_evidence",
    "memory_context_only_gap": "add_selected_query_memory_pressure_evidence",
    "mixed_unknown_evidence_gap": "split_mixed_unknown_reasons",
    "operator_timing_gap": "map_operator_time_to_selected_query_wall_clock",
    "profile_dialect_gap": "add_profile_dialect_mapping_fixtures",
    "scan_skew_supporting_only_gap": "add_scan_skew_corroborating_evidence",
    "short_or_missing_wall_clock_boundary": "separate_short_or_missing_wall_clock_cases",
    "storage_context_only_gap": "add_bounded_storage_context_evidence",
    "unsafe_unknown_primary_reason": "remove_raw_like_unknown_primary_reason_text",
    "unknown_reason_missing": "preserve_unknown_until_reason_is_reported",
    "unknown_reason_not_reported": "preserve_unknown_until_reason_is_reported",
    "unknown_reason_unmapped": "map_unknown_reason_to_safe_category",
}


def unknown_category_counts(
    reason_counts: Counter[str],
    *,
    unknown_primary_cases: int,
) -> Counter[str]:
    categories: Counter[str] = Counter()
    for reason, count in reason_counts.items():
        category = unknown_reason_category(reason)
        if category:
            categories[category] += int_value(count)
    reported = sum(categories.values())
    missing = max(0, int_value(unknown_primary_cases) - int_value(reported))
    if missing:
        categories["unknown_reason_not_reported"] += missing
    return categories


def unknown_reason_category(reason: object) -> str:
    token = safe_summary_key(reason)
    if not token:
        return "unknown_reason_missing"
    if token in UNKNOWN_REASON_CATEGORY_BY_REASON:
        return UNKNOWN_REASON_CATEGORY_BY_REASON[token]
    matched = tuple(
        reason_token for reason_token in UNKNOWN_REASON_CATEGORY_BY_REASON if reason_token in token
    )
    if len(matched) == 1:
        return UNKNOWN_REASON_CATEGORY_BY_REASON[matched[0]]
    if len(matched) > 1:
        return "mixed_unknown_evidence_gap"
    return "unknown_reason_unmapped"


def top_unknown_category_payload(
    category_counts: Counter[str],
    *,
    unknown_primary_cases: int,
    limit: int = 5,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for category, count in sorted(
        category_counts.items(),
        key=lambda item: (-int_value(item[1]), safe_summary_key(item[0])),
    )[: max(1, limit)]:
        safe_category = safe_summary_key(category) or "unknown_reason_unmapped"
        rows.append(
            {
                "category": safe_category,
                "unknown_primary_cases": int_value(count),
                "unknown_share_percent": rate_value(int_value(count), unknown_primary_cases),
                "closure_track": UNKNOWN_CATEGORY_CLOSURE_TRACK.get(
                    safe_category,
                    "map_unknown_reason_to_safe_category",
                ),
            }
        )
    return rows


def rate_value(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((count / total) * 100.0, 4)


def int_value(value: object) -> int:
    try:
        return max(0, int(float(str(value).strip())))
    except (TypeError, ValueError):
        return 0


def safe_summary_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if raw_like_summary_text(text):
        return "unsafe_token"
    return normalized_token(text)


def raw_like_summary_text(text: str) -> bool:
    return (
        contains_raw_sql_like_text(text)
        or URL_RE.search(text) is not None
        or LOCAL_PATH_RE.search(text) is not None
        or redaction.EMAIL_RE.search(text) is not None
        or redaction.IPV4_RE.search(text) is not None
        or redaction.HOSTLIKE_FQDN_RE.search(text) is not None
        or redaction.SECRET_VALUE_RE.search(text) is not None
    )


def normalized_token(value: object) -> str:
    text = str(value or "unknown").strip().lower()
    text = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in text)
    text = "_".join(part for part in text.split("_") if part)
    return text[:60] if text else "unknown"
