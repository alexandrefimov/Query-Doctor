"""Web job state and progress helpers."""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from query_doctor.safety.browser_display import redact_browser_display_text
from query_doctor.web.display_safety import sanitize_browser_error_text
from query_doctor.web.models import (
    WebJob,
    WebJobSnapshot,
    WebQueryAnalysisResult,
    WebResult,
    batch_progress_path,
)
from query_doctor.web.ui.progress import WEB_STAGES
from query_doctor.web.ui.recent_scan import batch_progress_percent, render_batch_progress_panel
from query_doctor.web.ui.report import render_result
from query_doctor.web.ui.specific_query import render_specific_query_result, render_specific_query_results


BATCH_STAGES = (
    (0, "Checking recent scan parameters", 4),
    (1, "Running recent scan", 24),
    (2, "Reading batch_summary.json", 86),
    (3, "Done", 100),
)
BATCH_REPORT_STAGES = (
    (0, "Checking selected batch case", 8),
    (1, "Generating validated report", 62),
    (2, "Validating result", 88),
    (3, "Done", 100),
)
OPTIMIZED_QUERY_STAGES = (
    (0, "Checking source SQL", 8),
    (1, "Generating optimizer draft", 45),
    (2, "Validating optimizer draft", 88),
    (3, "Done", 100),
)
LLM_ACTIONS_STAGES = (
    (0, "Checking selected case", 6),
    (1, "Generating validated report", 38),
    (2, "Generating optimizer draft", 72),
    (3, "Done", 100),
)


def sanitize_job_error(value: object) -> str:
    return sanitize_browser_error_text(value)


def render_query_analysis_output(result: object) -> list[str]:
    if isinstance(result, WebQueryAnalysisResult):
        return render_specific_query_result(result)
    return render_result(result)


def stages_for_job_kind(kind: str) -> tuple[tuple[int, str, int], ...]:
    if kind in {"batch", "running"}:
        return BATCH_STAGES
    if kind in {"batch_report", "query_report"}:
        return BATCH_REPORT_STAGES
    if kind in {"batch_optimized_query", "query_optimized_query"}:
        return OPTIMIZED_QUERY_STAGES
    if kind in {"batch_llm_actions", "query_llm_actions"}:
        return LLM_ACTIONS_STAGES
    return WEB_STAGES


def render_job_status_json(job: WebJobSnapshot | None) -> str:
    if job is None:
        payload = {
            "status": "failed",
            "stage": "Not found",
            "progress": 100,
            "error": "Analysis job was not found.",
            "result_html": "",
        }
    else:
        payload = {
            "status": job.status,
            "stage": job.stage_label,
            "progress": batch_progress_percent(job.batch_progress_path, job.status)
            if job.kind in {"batch", "running"}
            else job.progress,
            "kind": job.kind,
            "error": job.error,
            "result_html": job.result_html,
            "progress_html": render_batch_progress_panel(job.batch_progress_path, job.status)
            if job.kind in {"batch", "running"}
            else "",
        }
    return json.dumps(payload, ensure_ascii=False)


class WebJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, WebJob] = {}
        self._query_results: list[dict[str, object]] = []
        self._latest_batch_summary: Path | None = None
        self._latest_running_summary: Path | None = None
        self._lock = threading.Lock()

    def create(self, query_id: str, report_mode: str) -> WebJobSnapshot:
        stage = WEB_STAGES[0]
        with self._lock:
            prior_result_html = "\n".join(render_specific_query_results(tuple(self._query_results))) if self._query_results else ""
            job = WebJob(
                job_id=uuid.uuid4().hex,
                query_id=query_id,
                report_mode=report_mode,
                status="running",
                stage_label=stage[1],
                progress=stage[2],
                result_html=prior_result_html,
            )
            self._jobs[job.job_id] = job
            return job.snapshot()

    def create_batch(self, form_values: dict[str, object] | None = None) -> WebJobSnapshot:
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
            batch_progress_path=batch_progress_path(job_id),
        )
        with self._lock:
            self._jobs[job.job_id] = job
            return job.snapshot()

    def create_running_batch(self, form_values: dict[str, object] | None = None) -> WebJobSnapshot:
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
            batch_progress_path=batch_progress_path(job_id),
        )
        with self._lock:
            self._jobs[job.job_id] = job
            return job.snapshot()

    def create_batch_report(self, case_id: str, *, source: str = "batch") -> WebJobSnapshot:
        stage = BATCH_REPORT_STAGES[0]
        job = WebJob(
            job_id=uuid.uuid4().hex,
            query_id=case_id,
            report_mode="admin",
            status="running",
            stage_label=stage[1],
            progress=stage[2],
            kind="batch_report",
            batch_case_id=case_id,
            batch_source=source,
        )
        with self._lock:
            self._jobs[job.job_id] = job
            return job.snapshot()

    def create_query_report(self, query_id: str) -> WebJobSnapshot:
        stage = BATCH_REPORT_STAGES[0]
        job = WebJob(
            job_id=uuid.uuid4().hex,
            query_id=query_id,
            report_mode="admin",
            status="running",
            stage_label=stage[1],
            progress=stage[2],
            kind="query_report",
        )
        with self._lock:
            self._jobs[job.job_id] = job
            return job.snapshot()

    def create_batch_optimized_query(self, case_id: str, *, source: str = "batch") -> WebJobSnapshot:
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
            self._jobs[job.job_id] = job
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
            self._jobs[job.job_id] = job
            return job.snapshot()

    def create_batch_llm_actions(self, case_id: str, *, source: str = "batch") -> WebJobSnapshot:
        stage = LLM_ACTIONS_STAGES[0]
        job = WebJob(
            job_id=uuid.uuid4().hex,
            query_id=case_id,
            report_mode="llm_actions",
            status="running",
            stage_label=stage[1],
            progress=stage[2],
            kind="batch_llm_actions",
            batch_case_id=case_id,
            batch_source=source,
        )
        with self._lock:
            self._jobs[job.job_id] = job
            return job.snapshot()

    def create_query_llm_actions(self, query_id: str) -> WebJobSnapshot:
        stage = LLM_ACTIONS_STAGES[0]
        job = WebJob(
            job_id=uuid.uuid4().hex,
            query_id=query_id,
            report_mode="llm_actions",
            status="running",
            stage_label=stage[1],
            progress=stage[2],
            kind="query_llm_actions",
        )
        with self._lock:
            self._jobs[job.job_id] = job
            return job.snapshot()

    def running_batch_report(self, case_id: str) -> WebJobSnapshot | None:
        with self._lock:
            for job in self._jobs.values():
                if job.kind in {"batch_report", "batch_llm_actions"} and job.batch_case_id == case_id and job.status == "running":
                    return job.snapshot()
        return None

    def running_query_report(self, query_id: str) -> WebJobSnapshot | None:
        with self._lock:
            for job in self._jobs.values():
                if job.kind in {"query_report", "query_llm_actions"} and job.query_id == query_id and job.status == "running":
                    return job.snapshot()
        return None

    def running_batch_optimized_query(self, case_id: str) -> WebJobSnapshot | None:
        with self._lock:
            for job in self._jobs.values():
                if job.kind in {"batch_optimized_query", "batch_llm_actions"} and job.batch_case_id == case_id and job.status == "running":
                    return job.snapshot()
        return None

    def running_query_optimized_query(self, query_id: str) -> WebJobSnapshot | None:
        with self._lock:
            for job in self._jobs.values():
                if job.kind in {"query_optimized_query", "query_llm_actions"} and job.query_id == query_id and job.status == "running":
                    return job.snapshot()
        return None

    def get(self, job_id: str) -> WebJobSnapshot | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.snapshot() if job is not None else None

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
            job = self._jobs.get(job_id)
            if job is None or job.status != "running":
                return
            stages = stages_for_job_kind(job.kind)
            stage = stages[stage_index]
            job.stage_label = stage[1]
            job.progress = stage[2]

    def complete(self, job_id: str, result: WebResult | WebQueryAnalysisResult) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "ok"
            job.stage_label = WEB_STAGES[-1][1]
            job.progress = WEB_STAGES[-1][2]
            if isinstance(result, WebQueryAnalysisResult):
                safe_case = dict(result.case)
                safe_case.pop("case_index", None)
                safe_case.pop("case_dir", None)
                self._query_results.append(safe_case)
                job.result_html = "\n".join(render_specific_query_results(tuple(self._query_results)))
            else:
                job.result_html = "\n".join(render_query_analysis_output(result))
            job.error = ""

    def complete_html(self, job_id: str, result_html: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            stages = stages_for_job_kind(job.kind)
            job.status = "ok"
            job.stage_label = stages[-1][1]
            job.progress = stages[-1][2]
            job.result_html = result_html
            job.error = ""

    def fail(self, job_id: str, error: object) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.stage_label = "Failed"
            job.progress = 100
            job.error = sanitize_job_error(error)
