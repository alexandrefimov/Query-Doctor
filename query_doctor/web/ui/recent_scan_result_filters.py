"""Safe view-only Recent scan result filters."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from typing import Mapping

from query_doctor.web.presenters.workload_action_contract import row_has_status_issue
from query_doctor.web.presenters.recent_scan_models import RecentScanCaseRowView


REPORT_FILTER_PARAM = "report_filter"
OPTIMIZER_FILTER_PARAM = "optimizer_filter"
OUTCOME_FILTER_PARAM = "outcome_filter"
LIFECYCLE_FILTER_PARAM = "lifecycle_filter"
OWNER_FILTER_PARAM = "owner_filter"
POOL_FILTER_PARAM = "pool_filter"
REPORT_FILTER_VALIDATED = "validated"
OPTIMIZER_FILTER_READY = "ready"
OUTCOME_FILTER_RECORDED = "recorded"
LIFECYCLE_FILTER_CLEAN = "clean"
LIFECYCLE_FILTER_STATUS_FOLLOWUP = "status_followup"
LIFECYCLE_FILTER_METADATA_AVAILABLE = "metadata_available"
OWNER_FILTER_TAGGED = "tagged"
POOL_FILTER_TAGGED = "tagged"
_OWNER_FILTER_TOKEN_PREFIX = "ot_"
_POOL_FILTER_TOKEN_PREFIX = "pt_"
_FILTER_TOKEN_HEX_LENGTH = 16
_OWNER_FILTER_TOKEN_RE = re.compile(r"^ot_[0-9a-f]{16}$")
_POOL_FILTER_TOKEN_RE = re.compile(r"^pt_[0-9a-f]{16}$")

REPORT_FILTER_LABEL = "Validated reports"
OPTIMIZER_FILTER_LABEL = "Optimizer guidance"
OUTCOME_FILTER_LABEL = "Outcomes recorded"
OWNER_FILTER_LABEL = "Owner tagged"
POOL_FILTER_LABEL = "Pool tagged"
LIFECYCLE_FILTER_LABELS = {
    LIFECYCLE_FILTER_CLEAN: "Clean analysis",
    LIFECYCLE_FILTER_STATUS_FOLLOWUP: "Status follow-up",
    LIFECYCLE_FILTER_METADATA_AVAILABLE: "Metadata available",
}

RESULT_FILTER_PARAMS = (
    REPORT_FILTER_PARAM,
    OPTIMIZER_FILTER_PARAM,
    OUTCOME_FILTER_PARAM,
    LIFECYCLE_FILTER_PARAM,
    OWNER_FILTER_PARAM,
    POOL_FILTER_PARAM,
)


@dataclass(frozen=True)
class ResultFilterToggle:
    param: str
    value: str
    label: str
    aria_label: str
    count: int | None = None


RESULT_FILTER_TOGGLES = (
    ResultFilterToggle(
        param=OWNER_FILTER_PARAM,
        value=OWNER_FILTER_TAGGED,
        label=OWNER_FILTER_LABEL,
        aria_label="Only rows with a safe owner tag",
    ),
    ResultFilterToggle(
        param=POOL_FILTER_PARAM,
        value=POOL_FILTER_TAGGED,
        label=POOL_FILTER_LABEL,
        aria_label="Only rows with a safe pool tag",
    ),
    ResultFilterToggle(
        param=LIFECYCLE_FILTER_PARAM,
        value=LIFECYCLE_FILTER_CLEAN,
        label=LIFECYCLE_FILTER_LABELS[LIFECYCLE_FILTER_CLEAN],
        aria_label="Only rows with clean collection and analysis status",
    ),
    ResultFilterToggle(
        param=LIFECYCLE_FILTER_PARAM,
        value=LIFECYCLE_FILTER_STATUS_FOLLOWUP,
        label=LIFECYCLE_FILTER_LABELS[LIFECYCLE_FILTER_STATUS_FOLLOWUP],
        aria_label="Only rows needing status follow-up",
    ),
    ResultFilterToggle(
        param=LIFECYCLE_FILTER_PARAM,
        value=LIFECYCLE_FILTER_METADATA_AVAILABLE,
        label=LIFECYCLE_FILTER_LABELS[LIFECYCLE_FILTER_METADATA_AVAILABLE],
        aria_label="Only rows with metadata facts available",
    ),
    ResultFilterToggle(
        param=REPORT_FILTER_PARAM,
        value=REPORT_FILTER_VALIDATED,
        label=REPORT_FILTER_LABEL,
        aria_label="Only rows with validated reports",
    ),
    ResultFilterToggle(
        param=OPTIMIZER_FILTER_PARAM,
        value=OPTIMIZER_FILTER_READY,
        label=OPTIMIZER_FILTER_LABEL,
        aria_label="Only rows with optimizer guidance",
    ),
    ResultFilterToggle(
        param=OUTCOME_FILTER_PARAM,
        value=OUTCOME_FILTER_RECORDED,
        label=OUTCOME_FILTER_LABEL,
        aria_label="Only rows with recorded action outcomes",
    ),
)

_OPTIMIZER_READY_ARTIFACT_STATUSES = {
    "trusted_draft",
    "trusted_recommendations",
    "trusted_no_rewrite",
}
_OPTIMIZER_READY_SUPPORT_STATUSES = {
    "sql_draft_supported",
    "sql_draft_attemptable",
    "recipe_detected",
    "guidance_only",
}
_OPTIMIZER_READY_REWRITEABILITY_BUCKETS = {
    "safe_material_draft",
    "recipe_detected_no_draft",
    "recipe_adjacent_shape",
    "human_review_only",
}
_METADATA_AVAILABLE_STATUSES = {"available", "collected", "done", "ok", "partial"}
_TAG_UNKNOWN_VALUES = {
    "",
    "-",
    "all pools",
    "all users",
    "all users/pools",
    "n/a",
    "none",
    "null",
    "unknown",
}
_VALUE_FILTER_LIMIT_PER_KIND = 6


@dataclass(frozen=True)
class RecentScanResultFilters:
    report: str = ""
    optimizer: str = ""
    outcome: str = ""
    lifecycle: str = ""
    owner: str = ""
    pool: str = ""


def recent_scan_result_filters_from_mapping(
    values: Mapping[str, object] | None,
) -> RecentScanResultFilters:
    return normalize_recent_scan_result_filters(
        RecentScanResultFilters(
            report=_normalize_report_filter(_mapping_first_value(values, REPORT_FILTER_PARAM)),
            optimizer=_normalize_optimizer_filter(
                _mapping_first_value(values, OPTIMIZER_FILTER_PARAM)
            ),
            outcome=_normalize_outcome_filter(_mapping_first_value(values, OUTCOME_FILTER_PARAM)),
            lifecycle=_normalize_lifecycle_filter(
                _mapping_first_value(values, LIFECYCLE_FILTER_PARAM)
            ),
            owner=_normalize_owner_filter(_mapping_first_value(values, OWNER_FILTER_PARAM)),
            pool=_normalize_pool_filter(_mapping_first_value(values, POOL_FILTER_PARAM)),
        )
    )


def normalize_recent_scan_result_filters(
    filters: RecentScanResultFilters | None,
) -> RecentScanResultFilters:
    normalized = filters or RecentScanResultFilters()
    return RecentScanResultFilters(
        report=_normalize_report_filter(normalized.report),
        optimizer=_normalize_optimizer_filter(normalized.optimizer),
        outcome=_normalize_outcome_filter(normalized.outcome),
        lifecycle=_normalize_lifecycle_filter(normalized.lifecycle),
        owner=_normalize_owner_filter(normalized.owner),
        pool=_normalize_pool_filter(normalized.pool),
    )


def recent_scan_result_filter_query(filters: RecentScanResultFilters | None) -> dict[str, str]:
    normalized = normalize_recent_scan_result_filters(filters)
    query: dict[str, str] = {}
    if normalized.report:
        query[REPORT_FILTER_PARAM] = normalized.report
    if normalized.optimizer:
        query[OPTIMIZER_FILTER_PARAM] = normalized.optimizer
    if normalized.outcome:
        query[OUTCOME_FILTER_PARAM] = normalized.outcome
    if normalized.lifecycle:
        query[LIFECYCLE_FILTER_PARAM] = normalized.lifecycle
    if normalized.owner:
        query[OWNER_FILTER_PARAM] = normalized.owner
    if normalized.pool:
        query[POOL_FILTER_PARAM] = normalized.pool
    return query


def recent_scan_result_filter_toggles(
    rows: tuple[RecentScanCaseRowView, ...] = (),
) -> tuple[ResultFilterToggle, ...]:
    value_toggles = owner_pool_value_filter_toggles(rows)
    if not value_toggles:
        return RESULT_FILTER_TOGGLES
    return (*RESULT_FILTER_TOGGLES[:2], *value_toggles, *RESULT_FILTER_TOGGLES[2:])


def owner_pool_value_filter_toggles(
    rows: tuple[RecentScanCaseRowView, ...],
    *,
    limit_per_kind: int = _VALUE_FILTER_LIMIT_PER_KIND,
) -> tuple[ResultFilterToggle, ...]:
    return (
        *_value_filter_toggles(
            rows,
            attr="user",
            param=OWNER_FILTER_PARAM,
            kind="owner",
            label_prefix="Owner",
            aria_prefix="Only rows for owner",
            limit=limit_per_kind,
        ),
        *_value_filter_toggles(
            rows,
            attr="pool",
            param=POOL_FILTER_PARAM,
            kind="pool",
            label_prefix="Pool",
            aria_prefix="Only rows for pool",
            limit=limit_per_kind,
        ),
    )


def result_filters_with_toggle(
    filters: RecentScanResultFilters | None,
    param: str,
    value: str,
) -> RecentScanResultFilters:
    normalized = normalize_recent_scan_result_filters(filters)
    report = normalized.report
    optimizer = normalized.optimizer
    outcome = normalized.outcome
    lifecycle = normalized.lifecycle
    owner = normalized.owner
    pool = normalized.pool
    active = _filter_value_for_param(normalized, param) == value
    next_value = "" if active else value
    if param == REPORT_FILTER_PARAM:
        report = _normalize_report_filter(next_value)
    elif param == OPTIMIZER_FILTER_PARAM:
        optimizer = _normalize_optimizer_filter(next_value)
    elif param == OUTCOME_FILTER_PARAM:
        outcome = _normalize_outcome_filter(next_value)
    elif param == LIFECYCLE_FILTER_PARAM:
        lifecycle = _normalize_lifecycle_filter(next_value)
    elif param == OWNER_FILTER_PARAM:
        owner = _normalize_owner_filter(next_value)
    elif param == POOL_FILTER_PARAM:
        pool = _normalize_pool_filter(next_value)
    return RecentScanResultFilters(
        report=report,
        optimizer=optimizer,
        outcome=outcome,
        lifecycle=lifecycle,
        owner=owner,
        pool=pool,
    )


def result_filter_is_active(
    filters: RecentScanResultFilters | None,
    param: str,
    value: str,
) -> bool:
    return _filter_value_for_param(normalize_recent_scan_result_filters(filters), param) == value


def active_recent_scan_result_filter_count(filters: RecentScanResultFilters | None) -> int:
    normalized = normalize_recent_scan_result_filters(filters)
    return sum(
        1
        for value in (
            normalized.report,
            normalized.optimizer,
            normalized.outcome,
            normalized.lifecycle,
            normalized.owner,
            normalized.pool,
        )
        if value
    )


def active_recent_scan_result_filter_labels(
    filters: RecentScanResultFilters | None,
    *,
    toggles: tuple[ResultFilterToggle, ...] = (),
) -> tuple[str, ...]:
    normalized = normalize_recent_scan_result_filters(filters)
    labels: list[str] = []
    if normalized.report == REPORT_FILTER_VALIDATED:
        labels.append(REPORT_FILTER_LABEL)
    if normalized.optimizer == OPTIMIZER_FILTER_READY:
        labels.append(OPTIMIZER_FILTER_LABEL)
    if normalized.outcome == OUTCOME_FILTER_RECORDED:
        labels.append(OUTCOME_FILTER_LABEL)
    lifecycle_label = LIFECYCLE_FILTER_LABELS.get(normalized.lifecycle)
    if lifecycle_label:
        labels.append(lifecycle_label)
    if normalized.owner == OWNER_FILTER_TAGGED:
        labels.append(OWNER_FILTER_LABEL)
    elif _normalize_owner_filter(normalized.owner):
        labels.append(_active_value_filter_label(toggles, OWNER_FILTER_PARAM, normalized.owner))
    if normalized.pool == POOL_FILTER_TAGGED:
        labels.append(POOL_FILTER_LABEL)
    elif _normalize_pool_filter(normalized.pool):
        labels.append(_active_value_filter_label(toggles, POOL_FILTER_PARAM, normalized.pool))
    return tuple(labels)


def filter_rows_by_result_filters(
    rows: tuple[RecentScanCaseRowView, ...],
    filters: RecentScanResultFilters | None,
) -> tuple[RecentScanCaseRowView, ...]:
    normalized = normalize_recent_scan_result_filters(filters)
    if not active_recent_scan_result_filter_count(normalized):
        return rows
    return tuple(row for row in rows if row_matches_result_filters(row, normalized))


def row_matches_result_filters(
    row: RecentScanCaseRowView,
    filters: RecentScanResultFilters | None,
) -> bool:
    normalized = normalize_recent_scan_result_filters(filters)
    if normalized.report == REPORT_FILTER_VALIDATED and not row_has_validated_report(row):
        return False
    if normalized.optimizer == OPTIMIZER_FILTER_READY and not row_has_optimizer_guidance(row):
        return False
    if normalized.outcome == OUTCOME_FILTER_RECORDED and not row_has_recorded_outcome(row):
        return False
    if normalized.lifecycle and not row_matches_lifecycle_filter(row, normalized.lifecycle):
        return False
    if normalized.owner == OWNER_FILTER_TAGGED and not row_has_owner_tag(row):
        return False
    if _is_owner_filter_token(normalized.owner) and not row_matches_owner_filter(
        row, normalized.owner
    ):
        return False
    if normalized.pool == POOL_FILTER_TAGGED and not row_has_pool_tag(row):
        return False
    if _is_pool_filter_token(normalized.pool) and not row_matches_pool_filter(row, normalized.pool):
        return False
    return True


def row_matches_lifecycle_filter(row: RecentScanCaseRowView, lifecycle_filter: str) -> bool:
    normalized = _normalize_lifecycle_filter(lifecycle_filter)
    if normalized == LIFECYCLE_FILTER_CLEAN:
        return row_has_clean_analysis(row)
    if normalized == LIFECYCLE_FILTER_STATUS_FOLLOWUP:
        return row_has_status_issue(row)
    if normalized == LIFECYCLE_FILTER_METADATA_AVAILABLE:
        return row_has_metadata_available(row)
    return True


def row_has_clean_analysis(row: RecentScanCaseRowView) -> bool:
    return (
        _normalized_status(row.collection_status) == "ok"
        and _normalized_status(row.analysis_status) == "ok"
        and not row_has_status_issue(row)
    )


def row_has_validated_report(row: RecentScanCaseRowView) -> bool:
    return str(row.report_status or "").strip().lower() in {"validated", "validated report"}


def row_has_optimizer_guidance(row: RecentScanCaseRowView) -> bool:
    artifact_status = str(row.optimization_artifact_status or "").strip().lower()
    rewrite_support = str(row.optimizer_rewrite_support or "").strip().lower()
    rewriteability = str(row.optimizer_rewriteability_bucket or "").strip().lower()
    return (
        artifact_status in _OPTIMIZER_READY_ARTIFACT_STATUSES
        or rewrite_support in _OPTIMIZER_READY_SUPPORT_STATUSES
        or rewriteability in _OPTIMIZER_READY_REWRITEABILITY_BUCKETS
    )


def row_has_recorded_outcome(row: RecentScanCaseRowView) -> bool:
    summary = str(row.action_outcome_summary or "").strip().lower()
    return bool(summary and summary != "none")


def row_has_metadata_available(row: RecentScanCaseRowView) -> bool:
    return _normalized_status(row.metadata_status) in _METADATA_AVAILABLE_STATUSES


def row_has_owner_tag(row: RecentScanCaseRowView) -> bool:
    return _has_safe_tag_value(row.user)


def row_has_pool_tag(row: RecentScanCaseRowView) -> bool:
    return _has_safe_tag_value(row.pool)


def row_matches_owner_filter(row: RecentScanCaseRowView, owner_filter: str) -> bool:
    return owner_filter_value_token(row.user) == owner_filter


def row_matches_pool_filter(row: RecentScanCaseRowView, pool_filter: str) -> bool:
    return pool_filter_value_token(row.pool) == pool_filter


def owner_filter_value_token(value: object) -> str:
    return _value_filter_token("owner", value)


def pool_filter_value_token(value: object) -> str:
    return _value_filter_token("pool", value)


def _filter_value_for_param(filters: RecentScanResultFilters, param: str) -> str:
    if param == REPORT_FILTER_PARAM:
        return filters.report
    if param == OPTIMIZER_FILTER_PARAM:
        return filters.optimizer
    if param == OUTCOME_FILTER_PARAM:
        return filters.outcome
    if param == LIFECYCLE_FILTER_PARAM:
        return filters.lifecycle
    if param == OWNER_FILTER_PARAM:
        return filters.owner
    if param == POOL_FILTER_PARAM:
        return filters.pool
    return ""


def _mapping_first_value(values: Mapping[str, object] | None, key: str) -> object:
    if values is None:
        return ""
    value = values.get(key, "")
    if isinstance(value, (list, tuple)):
        return value[0] if value else ""
    return value


def _normalize_report_filter(value: object) -> str:
    text = str(value or "").strip().lower()
    return REPORT_FILTER_VALIDATED if text == REPORT_FILTER_VALIDATED else ""


def _normalize_optimizer_filter(value: object) -> str:
    text = str(value or "").strip().lower()
    return OPTIMIZER_FILTER_READY if text == OPTIMIZER_FILTER_READY else ""


def _normalize_outcome_filter(value: object) -> str:
    text = str(value or "").strip().lower()
    return OUTCOME_FILTER_RECORDED if text == OUTCOME_FILTER_RECORDED else ""


def _normalize_lifecycle_filter(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in LIFECYCLE_FILTER_LABELS else ""


def _normalize_owner_filter(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == OWNER_FILTER_TAGGED:
        return OWNER_FILTER_TAGGED
    return text if _is_owner_filter_token(text) else ""


def _normalize_pool_filter(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == POOL_FILTER_TAGGED:
        return POOL_FILTER_TAGGED
    return text if _is_pool_filter_token(text) else ""


def _has_safe_tag_value(value: object) -> bool:
    text = _canonical_tag_value(value)
    return text not in _TAG_UNKNOWN_VALUES


def _value_filter_toggles(
    rows: tuple[RecentScanCaseRowView, ...],
    *,
    attr: str,
    param: str,
    kind: str,
    label_prefix: str,
    aria_prefix: str,
    limit: int,
) -> tuple[ResultFilterToggle, ...]:
    counter: Counter[str] = Counter()
    labels: dict[str, str] = {}
    for row in rows:
        value = getattr(row, attr, "")
        if not _has_safe_tag_value(value):
            continue
        canonical = _canonical_tag_value(value)
        counter[canonical] += 1
        labels.setdefault(canonical, str(value or "").strip())
    selected = sorted(counter, key=lambda item: (-counter[item], labels.get(item, item).lower()))
    selected = selected[: max(0, limit)]
    toggles: list[ResultFilterToggle] = []
    for canonical in selected:
        label = labels.get(canonical, canonical)
        token = _value_filter_token(kind, label)
        if not token:
            continue
        toggles.append(
            ResultFilterToggle(
                param=param,
                value=token,
                label=f"{label_prefix}: {label}",
                aria_label=f"{aria_prefix} {label}; {counter[canonical]} matching rows",
                count=counter[canonical],
            )
        )
    return tuple(toggles)


def _active_value_filter_label(
    toggles: tuple[ResultFilterToggle, ...],
    param: str,
    value: str,
) -> str:
    for toggle in toggles:
        if toggle.param == param and toggle.value == value:
            return toggle.label
    return "Owner value" if param == OWNER_FILTER_PARAM else "Pool value"


def _value_filter_token(kind: str, value: object) -> str:
    canonical = _canonical_tag_value(value)
    if not _has_safe_tag_value(canonical):
        return ""
    if kind == "owner":
        prefix = _OWNER_FILTER_TOKEN_PREFIX
    elif kind == "pool":
        prefix = _POOL_FILTER_TOKEN_PREFIX
    else:
        return ""
    digest = hashlib.sha256(
        f"query-doctor-result-filter-v1:{kind}:{canonical}".encode()
    ).hexdigest()
    return f"{prefix}{digest[:_FILTER_TOKEN_HEX_LENGTH]}"


def _canonical_tag_value(value: object) -> str:
    return str(value or "").strip().lower()


def _is_owner_filter_token(value: str) -> bool:
    return bool(_OWNER_FILTER_TOKEN_RE.fullmatch(value))


def _is_pool_filter_token(value: str) -> bool:
    return bool(_POOL_FILTER_TOKEN_RE.fullmatch(value))


def _normalized_status(value: object) -> str:
    return str(value or "").strip().lower()
