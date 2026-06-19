"""Trino Beta retained-list Recent scan for the local web UI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Iterable

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.trino.coordinator_query_list_target import (
    TrinoCoordinatorQueryListRecord,
    load_trino_coordinator_query_list,
)
from query_doctor.web.display_safety import sanitize_browser_error_text
from query_doctor.web.models import (
    BatchRunConfig,
    WebError,
    WebSettings,
    WebTrinoRecentScanResult,
    WebTrinoRecentScanRow,
)
from query_doctor.web.trino_beta_query import (
    trino_auth_headers,
    trino_beta_query_configured,
    trino_engine_contract_web_error,
    trino_local_reference_error,
    trino_not_configured_error,
    trino_query_list_fetcher,
    run_trino_query_id_analysis,
)
from query_doctor.web.error_contract import web_error_info_from_error


TRINO_RECENT_UNSUPPORTED_FILTER_MESSAGE = (
    "Trino Beta Recent does not support User, Pool, or query-type filters. "
    "Use a bounded source-side list or One Query ID for a specific query."
)
TRINO_RECENT_WORKFLOW = "Trino Beta Recent"
CancelCheck = Callable[[], bool]
ProgressFunc = Callable[[int], None]


def trino_beta_recent_configured(settings: WebSettings) -> bool:
    return bool(trino_beta_query_configured(settings) and settings.trino_query_list_source_contract)


def validate_trino_recent_config_for_settings(
    config: BatchRunConfig,
    settings: WebSettings,
) -> None:
    if config.only_running or config.include_running:
        raise WebError(
            "Trino Beta Running scans are not supported. Use Trino Beta Finished queries "
            "or One Query ID.",
            title="Trino Beta Running is unavailable",
            reason_code="trino_beta.running_unsupported",
            stage="Checking Trino Recent request",
            next_step="Switch to Trino Beta Finished queries or One Query ID.",
        )
    if not trino_beta_recent_configured(settings):
        raise trino_not_configured_error(TRINO_RECENT_WORKFLOW)
    if config.metadata_top_limit > 0:
        raise WebError(
            "Trino Beta Recent does not support metadata collection. Disable metadata for "
            "this scan.",
            title="Trino Beta metadata is unavailable",
            reason_code="trino_beta.metadata_unsupported",
            stage="Checking Trino Recent request",
            next_step="Disable metadata collection for Trino Beta Recent and retry.",
        )
    if config.user or config.pool or config.query_type:
        raise WebError(
            TRINO_RECENT_UNSUPPORTED_FILTER_MESSAGE,
            title="Trino Beta Recent filters rejected",
            reason_code="trino_beta.recent_filter_unsupported",
            stage="Checking Trino Recent request",
            next_step="Remove User, Pool, and query-type filters, then retry.",
        )


def run_trino_recent_scan(
    config: BatchRunConfig,
    settings: WebSettings,
    *,
    progress: ProgressFunc | None = None,
    cancel_check: CancelCheck | None = None,
) -> WebTrinoRecentScanResult:
    validate_trino_recent_config_for_settings(config, settings)
    source_contract = settings.trino_query_list_source_contract
    coordinator_url = settings.trino_coordinator_url
    if source_contract is None or coordinator_url is None:
        raise trino_not_configured_error(TRINO_RECENT_WORKFLOW)
    update_progress(progress, 1)
    stop_if_cancelled(cancel_check)
    try:
        auth_headers = trino_auth_headers(settings)
        result = load_trino_coordinator_query_list(
            source_contract,
            coordinator_url=coordinator_url,
            auth_headers=auth_headers,
            fetcher=trino_query_list_fetcher(settings),
        )
    except OSError as exc:
        raise trino_local_reference_error(TRINO_RECENT_WORKFLOW) from exc
    except EngineFactContractError as exc:
        raise trino_engine_contract_web_error(
            exc,
            workflow=TRINO_RECENT_WORKFLOW,
            stage="Reading bounded query list",
        ) from exc

    update_progress(progress, 2)
    stop_if_cancelled(cancel_check)
    selected, warnings = select_trino_recent_records(
        result.records,
        config=config,
        query_bound=result.source_contract.max_query_ids,
    )
    update_progress(progress, 3)
    rows: list[WebTrinoRecentScanRow] = []
    diagnosed = 0
    query_settings = replace(settings, selected_engine="trino")
    for record in selected:
        stop_if_cancelled(cancel_check)
        try:
            analysis = run_trino_query_id_analysis(
                record.query_id,
                query_settings,
                progress=None,
                cancel_check=cancel_check,
            )
            rows.append(row_from_diagnosis(record.query_id, analysis.diagnosis))
            diagnosed += 1
        except WebError as exc:
            error_info = web_error_info_from_error(
                exc,
                default_reason_code="trino_beta.query_diagnosis_failed",
                stage="Diagnosing selected QueryInfo",
                default_next_step="Retry the row as One Query ID after checking local Trino Beta access.",
            )
            rows.append(
                WebTrinoRecentScanRow(
                    query_id=record.query_id,
                    status="failed",
                    error=sanitize_browser_error_text(error_info.message),
                    error_reason_code=error_info.reason_code,
                    error_next_step=error_info.next_step,
                )
            )
    update_progress(progress, 4)
    stop_if_cancelled(cancel_check)
    return WebTrinoRecentScanResult(
        rows=tuple(rows),
        records_seen=result.records_seen,
        records_selected=len(selected),
        records_diagnosed=diagnosed,
        query_bound=result.source_contract.max_query_ids,
        cluster_key=config.cluster_key,
        warnings=tuple(warnings),
    )


def select_trino_recent_records(
    records: Iterable[TrinoCoordinatorQueryListRecord],
    *,
    config: BatchRunConfig,
    query_bound: int,
    now: datetime | None = None,
) -> tuple[tuple[TrinoCoordinatorQueryListRecord, ...], list[str]]:
    current = now or datetime.now(timezone.utc)
    window_start = current - timedelta(minutes=config.recent_window_minutes)
    warnings: list[str] = []
    candidates: list[TrinoCoordinatorQueryListRecord] = []
    timestamp_missing = False
    duration_missing_for_filter = False
    for record in records:
        record_time = record.update_time or record.end_time or record.create_time
        if record_time is None:
            timestamp_missing = True
            continue
        elif record_time < window_start:
            continue
        if config.min_duration_sec is not None or config.max_duration_sec is not None:
            if record.elapsed_ms is None:
                duration_missing_for_filter = True
                continue
            duration_sec = float(record.elapsed_ms) / 1000.0
            if config.min_duration_sec is not None and duration_sec < config.min_duration_sec:
                continue
            if config.max_duration_sec is not None and duration_sec > config.max_duration_sec:
                continue
        candidates.append(record)
    if timestamp_missing:
        warnings.append(
            "Some Trino query-list records lacked timestamps and were excluded because the "
            "Recent window could not be verified."
        )
    if duration_missing_for_filter:
        warnings.append(
            "Some Trino query-list records lacked elapsed time and were excluded by duration filters."
        )
    ordered = order_trino_recent_records(candidates, config.order)
    limit = max(0, min(config.triage_profile_limit, query_bound))
    return tuple(ordered[:limit]), warnings


def order_trino_recent_records(
    records: list[TrinoCoordinatorQueryListRecord],
    order: str,
) -> list[TrinoCoordinatorQueryListRecord]:
    indexed = list(enumerate(records))

    def timestamp(record: TrinoCoordinatorQueryListRecord) -> datetime:
        return (
            record.update_time
            or record.end_time
            or record.create_time
            or datetime.min.replace(tzinfo=timezone.utc)
        )

    def duration(record: TrinoCoordinatorQueryListRecord) -> float:
        return float(record.elapsed_ms) if record.elapsed_ms is not None else -1.0

    if order == "duration-asc":
        indexed.sort(key=lambda item: (duration(item[1]) < 0, duration(item[1]), item[0]))
    elif order == "recent":
        indexed.sort(key=lambda item: (timestamp(item[1]), -item[0]), reverse=True)
    elif order == "recent-duration-desc":
        indexed.sort(
            key=lambda item: (timestamp(item[1]), duration(item[1]), -item[0]),
            reverse=True,
        )
    elif order == "status-priority":
        indexed.sort(
            key=lambda item: (
                0 if item[1].state == "FAILED" else 1,
                -duration(item[1]),
                item[0],
            )
        )
    else:
        indexed.sort(key=lambda item: (-duration(item[1]), item[0]))
    return [record for _index, record in indexed]


def row_from_diagnosis(query_id: str, diagnosis: dict[str, object]) -> WebTrinoRecentScanRow:
    diagnostic_lane = diagnosis.get("diagnostic_lane")
    supported_count = 0
    if isinstance(diagnostic_lane, dict):
        value = diagnostic_lane.get("supported_attention_area_count")
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            supported_count = value
    attention_areas: list[str] = []
    raw_areas = diagnosis.get("attention_areas")
    if isinstance(raw_areas, list):
        for item in raw_areas:
            if not isinstance(item, dict) or item.get("state") != "supported":
                continue
            area_id = item.get("id")
            if isinstance(area_id, str) and area_id:
                attention_areas.append(area_id)
    return WebTrinoRecentScanRow(
        query_id=query_id,
        status="ok",
        lifecycle=str(diagnosis.get("lifecycle") or "unknown"),
        parser_coverage=str(diagnosis.get("parser_coverage") or "unknown"),
        supported_attention_area_count=supported_count,
        attention_areas=tuple(attention_areas[:3]),
    )


def update_progress(progress: ProgressFunc | None, stage_index: int) -> None:
    if progress is not None:
        progress(stage_index)


def stop_if_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise WebError(
            "Analysis was stopped by the user.",
            title="Job stopped",
            reason_code="job.cancelled",
            stage="Cancelled",
            next_step="Start a new job when you are ready to retry.",
        )
