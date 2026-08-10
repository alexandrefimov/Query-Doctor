"""Web job state and progress helpers."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from query_doctor.safety.browser_display import redact_browser_display_text
from query_doctor.web.display_safety import sanitize_browser_error_text
from query_doctor.web.error_contract import (
    web_error_info_from_error,
    web_error_info_payload,
)
from query_doctor.web.job_progress import (
    BATCH_REPORT_STAGES,
    BATCH_STAGES,
    LLM_ACTIONS_STAGES,
    OPTIMIZED_QUERY_STAGES,
    TRINO_RECENT_STAGES,
    TRINO_QUERY_STAGES,
    WEB_STAGES,
    progress_view_from_snapshot,
    progress_view_payload as job_progress_view_payload,
)
from query_doctor.web.models import (
    WebJob,
    WebJobSnapshot,
    WebQueryAnalysisResult,
    WebResult,
    WebTrinoQueryAnalysisResult,
    batch_progress_path,
)
from query_doctor.web.ui.recent_scan_progress import (
    batch_progress_percent,
    batch_progress_view_payload,
    render_batch_progress_panel,
)
from query_doctor.web.ui.report import render_result
from query_doctor.web.ui.specific_query import (
    render_specific_query_result,
    render_specific_query_results,
)
from query_doctor.web.ui.errors import render_error_info_body
from query_doctor.web.ui.trino import render_trino_query_analysis_result


TERMINAL_JOB_STATUSES = {"ok", "failed", "cancelled"}
DEFAULT_TERMINAL_JOB_TTL_SEC = 6 * 60 * 60
DEFAULT_MAX_TERMINAL_JOBS = 100


def sanitize_job_error(value: object) -> str:
    return sanitize_browser_error_text(value)


def render_query_analysis_output(result: object) -> list[str]:
    if isinstance(result, WebQueryAnalysisResult):
        return render_specific_query_result(result)
    if isinstance(result, WebTrinoQueryAnalysisResult):
        return [render_trino_query_analysis_result(result)]
    return render_result(result)


def stages_for_job_kind(kind: str) -> tuple[tuple[int, str, int], ...]:
    if kind == "trino_query":
        return TRINO_QUERY_STAGES
    if kind == "trino_recent":
        return TRINO_RECENT_STAGES
    if kind in {"batch", "running"}:
        return BATCH_STAGES
    if kind in {"batch_report", "query_report", "batch_llm_report", "query_llm_report"}:
        return BATCH_REPORT_STAGES
    if kind in {"batch_optimized_query", "query_optimized_query"}:
        return OPTIMIZED_QUERY_STAGES
    if kind in {
        "batch_case_actions",
        "query_case_actions",
        "batch_llm_actions",
        "query_llm_actions",
    }:
        return LLM_ACTIONS_STAGES
    return WEB_STAGES


def render_job_status_json(job: WebJobSnapshot | None) -> str:
    if job is None:
        info = web_error_info_from_error(
            "Analysis job was not found.",
            default_title="Job was not found",
            default_reason_code="job.not_found",
            default_next_step="Start a new analysis job from the Query Inbox page.",
        )
        error_info = web_error_info_payload(info)
        payload = {
            "status": "failed",
            "stage": "Not found",
            "progress": 100,
            "progress_view": None,
            "error": "Analysis job was not found.",
            "error_info": error_info,
            "error_html": render_error_info_body(error_info),
            "result_html": "",
        }
    else:
        if job.kind in {"batch", "running"}:
            progress_view = batch_progress_view_payload(job.batch_progress_path, job.status)
            progress = progress_view["percent"]
        else:
            progress = job.progress
            progress_view = job_progress_view_payload(progress_view_from_snapshot(job))
        error_html = (
            render_error_info_body(job.error_info or job.error)
            if job.status in {"failed", "cancelled"}
            else ""
        )
        payload = {
            "status": job.status,
            "stage": job.stage_label,
            "progress": progress,
            "progress_view": progress_view,
            "kind": job.kind,
            "error": job.error,
            "error_info": job.error_info,
            "error_html": error_html,
            "result_html": job.result_html,
            "cancel_requested": job.cancel_requested,
            "progress_html": render_batch_progress_panel(job.batch_progress_path, job.status)
            if job.kind in {"batch", "running"}
            else "",
        }
    return json.dumps(payload, ensure_ascii=False)


class WebJobStore:
    def __init__(
        self,
        *,
        terminal_job_ttl_sec: float = DEFAULT_TERMINAL_JOB_TTL_SEC,
        max_terminal_jobs: int = DEFAULT_MAX_TERMINAL_JOBS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._jobs: dict[str, WebJob] = {}
        self._query_results: list[dict[str, object]] = []
        self._latest_batch_summary: Path | None = None
        self._latest_running_summary: Path | None = None
        self._terminal_job_ttl_sec = max(0.0, float(terminal_job_ttl_sec))
        self._max_terminal_jobs = max(0, int(max_terminal_jobs))
        self._clock = clock
        self._lock = threading.Lock()

    def create(
        self,
        query_id: str,
        report_mode: str,
        form_values: dict[str, object] | None = None,
        *,
        kind: str = "query",
    ) -> WebJobSnapshot:
        stages = stages_for_job_kind(kind)
        stage = stages[0]
        with self._lock:
            prior_result_html = (
                "\n".join(render_specific_query_results(tuple(self._query_results)))
                if kind == "query" and self._query_results
                else ""
            )
            job = WebJob(
                job_id=uuid.uuid4().hex,
                query_id=query_id,
                report_mode=report_mode,
                status="running",
                stage_label=stage[1],
                progress=stage[2],
                kind=kind,
                result_html=prior_result_html,
                batch_form_values=dict(form_values) if form_values is not None else None,
            )
            self._store_job_locked(job)
            return job.snapshot()

    def create_batch(
        self,
        form_values: dict[str, object] | None = None,
        *,
        batch_root: Path | None = None,
    ) -> WebJobSnapshot:
        stage = BATCH_STAGES[0]
        job_id = uuid.uuid4().hex
        job = WebJob(
            job_id=job_id,
            query_id="recent scan",
            report_mode="batch",
            status="running",
            stage_label=stage[1],
            progress=stage[2],
            kind="batch",
            batch_form_values=dict(form_values) if form_values is not None else None,
            batch_progress_path=batch_progress_path(job_id, root=batch_root),
        )
        with self._lock:
            self._store_job_locked(job)
            return job.snapshot()

    def running_batch_with_form_values(
        self,
        form_values: dict[str, object] | None = None,
        *,
        kind: str = "batch",
    ) -> WebJobSnapshot | None:
        with self._lock:
            self._prune_locked()
            job = self._running_job_with_form_values_locked(kind, form_values)
            return job.snapshot() if job is not None else None

    def create_or_reuse_batch(
        self,
        form_values: dict[str, object] | None = None,
        *,
        batch_root: Path | None = None,
    ) -> tuple[WebJobSnapshot, bool]:
        with self._lock:
            self._prune_locked()
            existing = self._running_job_with_form_values_locked("batch", form_values)
            if existing is not None:
                return existing.snapshot(), True
            stage = BATCH_STAGES[0]
            job_id = uuid.uuid4().hex
            job = WebJob(
                job_id=job_id,
                query_id="recent scan",
                report_mode="batch",
                status="running",
                stage_label=stage[1],
                progress=stage[2],
                kind="batch",
                batch_form_values=dict(form_values) if form_values is not None else None,
                batch_progress_path=batch_progress_path(job_id, root=batch_root),
            )
            self._store_job_locked(job)
            return job.snapshot(), False

    def create_running_batch(
        self,
        form_values: dict[str, object] | None = None,
        *,
        batch_root: Path | None = None,
    ) -> WebJobSnapshot:
        stage = BATCH_STAGES[0]
        job_id = uuid.uuid4().hex
        job = WebJob(
            job_id=job_id,
            query_id="running queries",
            report_mode="running",
            status="running",
            stage_label=stage[1],
            progress=stage[2],
            kind="running",
            batch_form_values=dict(form_values) if form_values is not None else None,
            batch_progress_path=batch_progress_path(job_id, root=batch_root),
        )
        with self._lock:
            self._store_job_locked(job)
            return job.snapshot()

    def create_trino_recent(self, form_values: dict[str, object] | None = None) -> WebJobSnapshot:
        stage = TRINO_RECENT_STAGES[0]
        job = WebJob(
            job_id=uuid.uuid4().hex,
            query_id="trino recent scan",
            report_mode="trino_recent",
            status="running",
            stage_label=stage[1],
            progress=stage[2],
            kind="trino_recent",
            batch_form_values=dict(form_values) if form_values is not None else None,
        )
        with self._lock:
            self._store_job_locked(job)
            return job.snapshot()

    def create_or_reuse_trino_recent(
        self, form_values: dict[str, object] | None = None
    ) -> tuple[WebJobSnapshot, bool]:
        with self._lock:
            self._prune_locked()
            existing = self._running_job_with_form_values_locked("trino_recent", form_values)
            if existing is not None:
                return existing.snapshot(), True
            stage = TRINO_RECENT_STAGES[0]
            job = WebJob(
                job_id=uuid.uuid4().hex,
                query_id="trino recent scan",
                report_mode="trino_recent",
                status="running",
                stage_label=stage[1],
                progress=stage[2],
                kind="trino_recent",
                batch_form_values=dict(form_values) if form_values is not None else None,
            )
            self._store_job_locked(job)
            return job.snapshot(), False

    def create_batch_report(
        self, case_id: str, *, source: str = "batch", report_variant: str = "python"
    ) -> WebJobSnapshot:
        stage = BATCH_REPORT_STAGES[0]
        kind = "batch_llm_report" if report_variant == "llm" else "batch_report"
        report_mode = "llm_report" if report_variant == "llm" else "python_report"
        job = WebJob(
            job_id=uuid.uuid4().hex,
            query_id=case_id,
            report_mode=report_mode,
            status="running",
            stage_label=stage[1],
            progress=stage[2],
            kind=kind,
            batch_case_id=case_id,
            batch_source=source,
        )
        with self._lock:
            self._store_job_locked(job)
            return job.snapshot()

    def create_query_report(
        self, query_id: str, *, report_variant: str = "python"
    ) -> WebJobSnapshot:
        stage = BATCH_REPORT_STAGES[0]
        kind = "query_llm_report" if report_variant == "llm" else "query_report"
        report_mode = "llm_report" if report_variant == "llm" else "python_report"
        job = WebJob(
            job_id=uuid.uuid4().hex,
            query_id=query_id,
            report_mode=report_mode,
            status="running",
            stage_label=stage[1],
            progress=stage[2],
            kind=kind,
        )
        with self._lock:
            self._store_job_locked(job)
            return job.snapshot()

    def create_batch_optimized_query(
        self, case_id: str, *, source: str = "batch"
    ) -> WebJobSnapshot:
        stage = OPTIMIZED_QUERY_STAGES[0]
        job = WebJob(
            job_id=uuid.uuid4().hex,
            query_id=case_id,
            report_mode="optimized_query",
            status="running",
            stage_label=stage[1],
            progress=stage[2],
            kind="batch_optimized_query",
            batch_case_id=case_id,
            batch_source=source,
        )
        with self._lock:
            self._store_job_locked(job)
            return job.snapshot()

    def create_query_optimized_query(self, query_id: str) -> WebJobSnapshot:
        stage = OPTIMIZED_QUERY_STAGES[0]
        job = WebJob(
            job_id=uuid.uuid4().hex,
            query_id=query_id,
            report_mode="optimized_query",
            status="running",
            stage_label=stage[1],
            progress=stage[2],
            kind="query_optimized_query",
        )
        with self._lock:
            self._store_job_locked(job)
            return job.snapshot()

    def create_batch_llm_actions(self, case_id: str, *, source: str = "batch") -> WebJobSnapshot:
        return self.create_batch_case_actions(case_id, source=source)

    def create_batch_case_actions(self, case_id: str, *, source: str = "batch") -> WebJobSnapshot:
        stage = LLM_ACTIONS_STAGES[0]
        job = WebJob(
            job_id=uuid.uuid4().hex,
            query_id=case_id,
            report_mode="case_actions",
            status="running",
            stage_label=stage[1],
            progress=stage[2],
            kind="batch_case_actions",
            batch_case_id=case_id,
            batch_source=source,
        )
        with self._lock:
            self._store_job_locked(job)
            return job.snapshot()

    def create_query_llm_actions(self, query_id: str) -> WebJobSnapshot:
        return self.create_query_case_actions(query_id)

    def create_query_case_actions(self, query_id: str) -> WebJobSnapshot:
        stage = LLM_ACTIONS_STAGES[0]
        job = WebJob(
            job_id=uuid.uuid4().hex,
            query_id=query_id,
            report_mode="case_actions",
            status="running",
            stage_label=stage[1],
            progress=stage[2],
            kind="query_case_actions",
        )
        with self._lock:
            self._store_job_locked(job)
            return job.snapshot()

    def running_batch_report(
        self, case_id: str, *, report_variant: str | None = None
    ) -> WebJobSnapshot | None:
        if report_variant == "python":
            kinds = {"batch_report", "batch_case_actions", "batch_llm_actions"}
        elif report_variant == "llm":
            kinds = {"batch_llm_report"}
        else:
            kinds = {
                "batch_report",
                "batch_llm_report",
                "batch_case_actions",
                "batch_llm_actions",
            }
        with self._lock:
            self._prune_locked()
            for job in self._jobs.values():
                if job.kind in kinds and job.batch_case_id == case_id and job.status == "running":
                    return job.snapshot()
        return None

    def running_query_report(
        self, query_id: str, *, report_variant: str | None = None
    ) -> WebJobSnapshot | None:
        if report_variant == "python":
            kinds = {"query_report", "query_case_actions", "query_llm_actions"}
        elif report_variant == "llm":
            kinds = {"query_llm_report"}
        else:
            kinds = {
                "query_report",
                "query_llm_report",
                "query_case_actions",
                "query_llm_actions",
            }
        with self._lock:
            self._prune_locked()
            for job in self._jobs.values():
                if job.kind in kinds and job.query_id == query_id and job.status == "running":
                    return job.snapshot()
        return None

    def running_batch_optimized_query(self, case_id: str) -> WebJobSnapshot | None:
        with self._lock:
            self._prune_locked()
            for job in self._jobs.values():
                if (
                    job.kind
                    in {
                        "batch_optimized_query",
                        "batch_case_actions",
                        "batch_llm_actions",
                    }
                    and job.batch_case_id == case_id
                    and job.status == "running"
                ):
                    return job.snapshot()
        return None

    def running_query_optimized_query(self, query_id: str) -> WebJobSnapshot | None:
        with self._lock:
            self._prune_locked()
            for job in self._jobs.values():
                if (
                    job.kind
                    in {
                        "query_optimized_query",
                        "query_case_actions",
                        "query_llm_actions",
                    }
                    and job.query_id == query_id
                    and job.status == "running"
                ):
                    return job.snapshot()
        return None

    def get(self, job_id: str) -> WebJobSnapshot | None:
        with self._lock:
            self._prune_locked()
            job = self._jobs.get(job_id)
            return job.snapshot() if job is not None else None

    def request_cancel(self, job_id: str) -> WebJobSnapshot | None:
        with self._lock:
            self._prune_locked()
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.cancel_requested = True
            if job.status == "running":
                job.status = "cancelled"
                job.stage_label = "Cancelled"
                job.progress = 100
                info = web_error_info_from_error(
                    "Job stopped by user.",
                    default_title="Job stopped",
                    default_reason_code="job.cancelled",
                    stage="Cancelled",
                    default_next_step="Start a new job when you are ready to retry.",
                )
                job.error = info.message
                job.error_info = web_error_info_payload(info)
                job.result_html = ""
            job.updated_at = self._now()
            return job.snapshot()

    def cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            self._prune_locked()
            job = self._jobs.get(job_id)
            return bool(job is not None and job.cancel_requested)

    def latest_batch_summary(self) -> Path | None:
        with self._lock:
            return self._latest_batch_summary

    def set_latest_batch_summary(self, path: Path) -> None:
        with self._lock:
            self._latest_batch_summary = path

    def latest_running_summary(self) -> Path | None:
        with self._lock:
            return self._latest_running_summary

    def set_latest_running_summary(self, path: Path) -> None:
        with self._lock:
            self._latest_running_summary = path

    def update_stage(self, job_id: str, stage_index: int) -> None:
        with self._lock:
            self._prune_locked()
            job = self._jobs.get(job_id)
            if job is None or job.status != "running":
                return
            stages = stages_for_job_kind(job.kind)
            stage = stages[stage_index]
            job.stage_label = stage[1]
            job.progress = stage[2]
            job.updated_at = self._now()

    def complete(
        self,
        job_id: str,
        result: WebResult | WebQueryAnalysisResult | WebTrinoQueryAnalysisResult,
    ) -> None:
        with self._lock:
            self._prune_locked()
            job = self._jobs.get(job_id)
            if job is None or job.status != "running":
                return
            stages = stages_for_job_kind(job.kind)
            job.status = "ok"
            job.stage_label = stages[-1][1]
            job.progress = stages[-1][2]
            if isinstance(result, WebQueryAnalysisResult):
                safe_case = dict(result.case)
                safe_case.pop("case_index", None)
                safe_case.pop("case_dir", None)
                self._query_results.append(safe_case)
                job.result_html = "\n".join(
                    render_specific_query_results(tuple(self._query_results))
                )
            else:
                job.result_html = "\n".join(render_query_analysis_output(result))
            job.error = ""
            job.error_info = None
            job.updated_at = self._now()
            self._prune_locked()

    def complete_html(self, job_id: str, result_html: str) -> None:
        with self._lock:
            self._prune_locked()
            job = self._jobs.get(job_id)
            if job is None or job.status != "running":
                return
            stages = stages_for_job_kind(job.kind)
            job.status = "ok"
            job.stage_label = stages[-1][1]
            job.progress = stages[-1][2]
            job.result_html = result_html
            job.error = ""
            job.error_info = None
            job.updated_at = self._now()
            self._prune_locked()

    def fail(self, job_id: str, error: object) -> None:
        with self._lock:
            self._prune_locked()
            job = self._jobs.get(job_id)
            if job is None or job.status != "running":
                return
            info = web_error_info_from_error(
                error,
                default_reason_code=default_job_error_reason_code(job.kind),
                stage=job.stage_label,
                default_next_step=default_job_error_next_step(job.kind),
            )
            job.status = "failed"
            job.stage_label = "Failed"
            job.progress = 100
            job.error = sanitize_job_error(info.message)
            job.error_info = web_error_info_payload(info)
            job.updated_at = self._now()
            self._prune_locked()

    def _store_job_locked(self, job: WebJob) -> None:
        now = self._now()
        self._prune_locked(now)
        job.created_at = now
        job.updated_at = now
        self._jobs[job.job_id] = job

    def _running_job_with_form_values_locked(
        self,
        kind: str,
        form_values: dict[str, object] | None,
    ) -> WebJob | None:
        normalized = dict(form_values) if form_values is not None else None
        for job in self._jobs.values():
            if job.kind != kind or job.status != "running":
                continue
            if job.batch_form_values == normalized:
                return job
        return None

    def _prune_locked(self, now: float | None = None) -> None:
        current = self._now() if now is None else now
        if self._terminal_job_ttl_sec >= 0:
            expired = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in TERMINAL_JOB_STATUSES
                and current - job.updated_at > self._terminal_job_ttl_sec
            ]
            for job_id in expired:
                self._jobs.pop(job_id, None)
        if self._max_terminal_jobs <= 0:
            return
        terminal_jobs = [
            (job.updated_at, job_id)
            for job_id, job in self._jobs.items()
            if job.status in TERMINAL_JOB_STATUSES
        ]
        excess_count = len(terminal_jobs) - self._max_terminal_jobs
        if excess_count <= 0:
            return
        for _updated_at, job_id in sorted(terminal_jobs)[:excess_count]:
            self._jobs.pop(job_id, None)

    def _now(self) -> float:
        return float(self._clock())


def default_job_error_reason_code(kind: str) -> str:
    safe_kind = "".join(
        char for char in str(kind or "job").lower() if char.isalnum() or char == "_"
    )
    return f"{safe_kind or 'job'}.failed"


def default_job_error_next_step(kind: str) -> str:
    if kind in {"trino_query", "trino_recent"}:
        return (
            "Check the selected Trino local source, source contracts, auth reference, "
            "and coordinator reachability, then retry."
        )
    if kind in {"batch", "running"}:
        return "Review the selected source, local config, credentials, and scan bounds, then retry."
    return "Review the selected inputs and local configuration, then retry."
