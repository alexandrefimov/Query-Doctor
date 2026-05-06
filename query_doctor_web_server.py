#!/usr/bin/env python3
"""Local-only Query Doctor web server for explicit CM query ids."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, quote, unquote, urlparse
from zoneinfo import ZoneInfo

import query_doctor_collect_cm_profiles as cm_collector
import query_doctor_collect_impala_context as impala_context_collector
import query_doctor_impala_metadata_workflow as metadata_workflow
import table_metadata_facts
import query_doctor_batch_recent as batch_recent
from query_doctor_optimize_query import (
    QueryOptimizationError,
    decide_optimizer_risk_mode,
    dedupe_preserve_order,
    detect_optimizer_rewrite_recipe,
    draft_has_material_change,
    extract_optimizable_source_sql,
    optimizer_specific_recommendation_bullets,
    read_source_sql,
    sql_completeness_errors,
    validate_draft_sql,
    validate_optimizer_recommendations_text,
)
from query_doctor_config_contract import load_and_validate_config, merge_kerberos_cache_env
from query_doctor_web_display_safety import redact_browser_display_text
from query_doctor_optimizer_sql import ExtractedTable, OptimizerSqlError, extract_referenced_tables
from query_doctor_query_optimizer import OptimizerAnalysis, analyze_query_optimizer
from query_doctor_web_ui import (
    WEB_STAGES,
    batch_progress_percent,
    render_batch_card,
    render_batch_case_detail_page,
    render_batch_case_not_found_page,
    render_batch_case_report_page,
    render_batch_page,
    render_batch_progress_panel,
    render_details_inline_report_html,
    render_page,
    render_query_page,
    render_readme_page,
    render_report_markdown_html,
    render_result,
    render_specific_query_detail,
    render_specific_query_result,
    render_specific_query_results,
)
from query_doctor_web_ui_help import render_demo_guide_page, render_help_page
from query_doctor_web_ui_optimizer import render_optimizer_page
from query_doctor_web_ui_running import render_running_queries_page
from query_doctor_web_ui_recent_scan_presenter import case_score_severity, present_recent_scan_summary
from query_doctor_web_ui_recent_scan_results import (
    filter_rows_by_query_group,
    sort_rows_for_query_group,
)
from query_doctor_web_optimizer_artifacts import decorate_cases_with_optimizer_artifact_status


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_TIMEOUT_SEC = 1800
DEFAULT_MODEL = "qwen3-coder:30b-a3b-q8_0"
DEFAULT_OPTIMIZER_MODEL = os.getenv("QD_OPTIMIZER_MODEL")
DEFAULT_CORPUS_DIR = Path("cases/cm-corpus")
REPORT_VALIDATION_EXIT_CODE = 4
LOCAL_BIND_HOSTS = {"127.0.0.1", "localhost"}
OUTPUT_CASE_RE = re.compile(r"^Output case directory:\s*(?P<path>.+)$", re.MULTILINE)
COLLECTED_CASE_FILES = ("profile_digest.md", "cm_metadata.json", "collection_warnings.txt")
PROFILE_SUMMARY_READ_CHARS = 65536
REPORT_VALIDATION_FAILURE_MESSAGE = (
    "Report generation finished, but the deterministic validator rejected the "
    "report because it contradicted extracted facts. The unsafe report is not "
    "shown. Try generating the report again."
)
MISSING_CM_CREDENTIALS_MESSAGE = (
    "CM credentials were not found in the web server environment. Start the "
    "server from a terminal where CM_USERNAME/CM_PASSWORD or CM_TOKEN is set."
)
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
BATCH_ORDER_VALUES = {"recent", "duration-desc", "duration-asc", "recent-duration-desc", "status-priority"}
BATCH_CM_INSPECT_LIMIT_MAX = 5000
BATCH_METADATA_TOP_LIMIT_MAX = 200
WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT = 70
BATCH_JOBS_MAX = 100
BATCH_FULL_JOBS_MAX = 4
BATCH_CM_JOBS_MAX = 100
BATCH_METADATA_JOBS_MAX = 5
WEB_RUNNING_SCAN_WINDOW_MINUTES = 120
WEB_RUNNING_CM_INSPECT_LIMIT_DEFAULT = 500
RECENT_SCAN_TIMEZONE = ZoneInfo("Europe/Moscow")
RECENT_SCAN_LOOKBACK_DAYS = 2
RECENT_SCAN_BUCKET_HOURS = 1
DEFAULT_METADATA_AUTH = "kerberos"
DEFAULT_METADATA_PROTOCOL = "beeswax"
DEFAULT_METADATA_TIMEOUT_SEC = 30
MAX_METADATA_FACTS_BYTES = 512 * 1024
BATCH_REPORT_NAME = "diagnosis.md"
BATCH_REPORT_PARTIAL_NAME = "diagnosis.partial.md"
BATCH_REPORT_VALIDATION_MARKER = "diagnosis.validated.json"
OPTIMIZED_QUERY_NAME = "optimized_query.sql"
OPTIMIZED_QUERY_RECOMMENDATIONS_NAME = "optimized_query_recommendations.md"
OPTIMIZED_QUERY_PARTIAL_NAME = "optimized_query.partial.txt"
OPTIMIZED_QUERY_VALIDATION_MARKER = "optimized_query.validated.json"
EXTERNAL_REWRITE_SQL_FIELD = "rewritten_sql"
MAX_EXTERNAL_REWRITE_SQL_BYTES = 256 * 1024
MAX_WEB_POST_BODY_BYTES = 320 * 1024
WEB_REPORT_VALIDATION_MODE = "strict"
OPTIMIZED_QUERY_MARKER_SCHEMA_VERSION = 2
OPTIMIZED_QUERY_VALIDATION_MODE = "strict_v2"
TABLE_METADATA_SUMMARY_KEYS = {
    "context file": "context file",
    "context path": "context path",
    "table metadata facts": "table metadata facts",
    "tables requested": "tables requested",
    "read-only statements only": "read-only statements only",
    "error": "error",
}
TABLE_METADATA_TABLE_KEYS = {
    "object type": "object type",
    "table stats rows": "table stats rows",
    "table stats row-count completeness": "table stats row-count completeness",
    "table stats size": "table stats size",
    "column stats columns observed": "column stats columns observed",
    "column stats missing/unknown markers": "column stats missing/unknown markers",
    "column stats completeness": "column stats completeness",
    "column stats columns": "column stats columns",
    "file format": "file format",
    "partition columns": "partition columns",
}
TABLE_METADATA_TABLE_KEYS_START = {"table", "table name", "referenced table"}


def batch_output_dir(job_id: str) -> Path:
    return Path("/tmp") / f"query-doctor-web-batch-{job_id}"


def batch_progress_path(job_id: str) -> Path:
    return batch_output_dir(job_id) / "progress.jsonl"


class WebError(RuntimeError):
    """User-facing web error that must not contain secrets or raw profiles."""


@dataclass(frozen=True)
class WebSettings:
    config: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    allow_nonlocal_web_bind: bool = False
    max_profile_bytes: int | None = None
    model: str = DEFAULT_MODEL
    optimizer_model: str | None = None
    timeout_sec: int = DEFAULT_TIMEOUT_SEC
    repo_dir: Path = Path(__file__).resolve().parent
    corpus_dir: Path = DEFAULT_CORPUS_DIR
    batch_summary: Path | None = None
    metadata_coordinator: str | None = None
    metadata_impala_shell: str | None = None
    metadata_auth: str = DEFAULT_METADATA_AUTH
    metadata_protocol: str = DEFAULT_METADATA_PROTOCOL
    metadata_ssl: bool = False
    metadata_ca_cert: str | None = None
    metadata_timeout_sec: int = DEFAULT_METADATA_TIMEOUT_SEC
    metadata_max_tables: int | None = None
    metadata_max_output_bytes: int | None = None
    metadata_redact: bool = False
    krb5ccname: str | None = None


@dataclass(frozen=True)
class WebResult:
    query_id: str
    case_dir: Path
    case_source: str
    report_mode: str
    parsed_operators: str
    cardinality_anomalies: str
    memory_anomalies: str
    report_text: str
    report_retry: bool = False


@dataclass(frozen=True)
class WebQueryAnalysisResult:
    query_id: str
    case: dict[str, object]


@dataclass(frozen=True)
class BatchRunConfig:
    recent_window_minutes: int = 30
    scan_date: str = ""
    scan_hour: int = 0
    from_time: str | None = None
    to_time: str | None = None
    cm_inspect_limit: int = BATCH_CM_INSPECT_LIMIT_MAX
    triage_profile_limit: int = BATCH_CM_INSPECT_LIMIT_MAX
    metadata_top_limit: int = WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT
    min_duration_sec: float | None = None
    max_duration_sec: float | None = None
    order: str = "duration-desc"
    parallelism: int = 50
    cm_jobs: int = 50
    jobs: int = 50
    metadata_jobs: int = 5
    user: str = ""
    pool: str = ""
    query_type: str = ""
    include_failed: bool = True
    include_running: bool = False
    only_running: bool = False
    collect_cm_timeseries: bool = False


@dataclass(frozen=True)
class WebJobSnapshot:
    job_id: str
    query_id: str
    report_mode: str
    status: str
    stage_label: str
    progress: int
    kind: str = "query"
    result_html: str = ""
    error: str = ""
    batch_form_values: dict[str, object] | None = None
    batch_progress_path: Path | None = None
    batch_case_id: str | None = None
    batch_source: str = "batch"


@dataclass
class WebJob:
    job_id: str
    query_id: str
    report_mode: str
    status: str
    stage_label: str
    progress: int
    kind: str = "query"
    result_html: str = ""
    error: str = ""
    batch_form_values: dict[str, object] | None = None
    batch_progress_path: Path | None = None
    batch_case_id: str | None = None
    batch_source: str = "batch"

    def snapshot(self) -> WebJobSnapshot:
        return WebJobSnapshot(
            job_id=self.job_id,
            query_id=self.query_id,
            report_mode=self.report_mode,
            status=self.status,
            stage_label=self.stage_label,
            progress=self.progress,
            kind=self.kind,
            result_html=self.result_html,
            error=self.error,
            batch_form_values=dict(self.batch_form_values) if self.batch_form_values is not None else None,
            batch_progress_path=self.batch_progress_path,
            batch_case_id=self.batch_case_id,
            batch_source=self.batch_source,
        )


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
            job.error = sanitize_for_display(error)


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


AnalysisFunc = Callable[[str, str, bool, WebSettings], object]
Runner = Callable[..., subprocess.CompletedProcess[str]]
ProgressFunc = Callable[[int], None]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the localhost-only Query Doctor web UI for recent scans, explicit CM query ids, and pasted SQL."
    )
    parser.add_argument(
        "--config",
        help=(
            "Local ignored Query Doctor JSON config. If omitted, "
            f"{cm_collector.DEFAULT_LOCAL_CONFIG_NAME} is loaded when present, falling back to "
            f"legacy {cm_collector.LEGACY_LOCAL_CONFIG_NAME}. Credentials still come from environment."
        ),
    )
    parser.add_argument("--host", help=f"Bind host. Default comes from config or {DEFAULT_HOST}.")
    parser.add_argument("--port", type=positive_int, help=f"Bind port. Default comes from config or {DEFAULT_PORT}.")
    parser.add_argument(
        "--allow-nonlocal-web-bind",
        "--allow-nonlocal-demo-bind",
        dest="allow_nonlocal_web_bind",
        action="store_true",
        help=(
            "Allow binding outside localhost. Unsafe for this local web UI; prints a warning. "
            "--allow-nonlocal-demo-bind is accepted as a legacy alias."
        ),
    )
    parser.add_argument(
        "--max-profile-bytes",
        type=positive_int,
        help=f"Override collector max profile bytes. Default comes from config or {cm_collector.DEFAULT_MAX_PROFILE_BYTES}.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model for reports. Default: {DEFAULT_MODEL}.")
    parser.add_argument(
        "--optimizer-model",
        help="Ollama model for Query LLM optimizer. Defaults to config/env value, otherwise --model.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=positive_int,
        default=DEFAULT_TIMEOUT_SEC,
        help=f"Per-step subprocess timeout. Default: {DEFAULT_TIMEOUT_SEC}.",
    )
    parser.add_argument(
        "--batch-summary",
        help=(
            "Optional local batch_summary.json to render read-only at / and /batch. "
            "The web UI never chooses this path from request parameters."
        ),
    )
    parser.add_argument("--metadata-coordinator", help="Impala coordinator HOST:PORT for web metadata collection.")
    parser.add_argument("--metadata-impala-shell", help="impala-shell executable for web metadata collection.")
    parser.add_argument(
        "--metadata-auth",
        help="Metadata auth mode. Default comes from config or kerberos.",
    )
    parser.add_argument(
        "--metadata-protocol",
        choices=("beeswax", "hs2", "hs2-http"),
        help="impala-shell protocol for web metadata collection. Default comes from config or beeswax.",
    )
    parser.add_argument("--metadata-ssl", action="store_true", help="Pass --ssl to impala-shell metadata collection.")
    parser.add_argument("--metadata-ca-cert", help="CA certificate path for --metadata-ssl metadata connections.")
    parser.add_argument(
        "--metadata-timeout-sec",
        type=positive_int,
        help=f"Timeout per metadata statement. Default comes from config or {DEFAULT_METADATA_TIMEOUT_SEC}.",
    )
    parser.add_argument("--metadata-max-tables", type=positive_int, help="Maximum referenced tables to collect.")
    parser.add_argument("--metadata-max-output-bytes", type=positive_int, help="Maximum metadata output bytes.")
    parser.add_argument("--metadata-redact", action="store_true", help="Pass --metadata-redact to web metadata collection.")
    return parser.parse_args(argv)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def validate_bind_host(host: str, *, allow_nonlocal_web_bind: bool) -> None:
    if host in LOCAL_BIND_HOSTS:
        return
    if allow_nonlocal_web_bind:
        return
    raise WebError(
        "Refusing non-local bind. Use --host 127.0.0.1 or pass "
        "--allow-nonlocal-web-bind explicitly for a local web risk review."
    )


def validate_query_id(query_id: str) -> str:
    try:
        return cm_collector.validate_cm_query_id_path_segment(query_id)
    except cm_collector.CMAdapterError as exc:
        raise WebError(str(exc)) from exc


def sanitize_for_display(value: object) -> str:
    return redact_browser_display_text(value, redact_artifact_markers=True, max_chars=1200)


def run_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    timeout_sec: int,
    runner: Runner,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return runner(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )


def effective_subprocess_env(
    settings: WebSettings,
    base_env: dict[str, str] | os._Environ[str] | None = None,
) -> dict[str, str]:
    return merge_kerberos_cache_env(
        os.environ if base_env is None else base_env,
        {"krb5ccname": settings.krb5ccname},
    )


def resolve_metadata_impala_shell(settings: WebSettings, env: dict[str, str]) -> str | None:
    executable = settings.metadata_impala_shell or "impala-shell"
    if "/" in executable:
        path = Path(executable)
        if not path.is_absolute():
            path = settings.repo_dir / path
        return str(path) if path.is_file() else None
    return shutil.which(executable, path=env.get("PATH"))


def preflight_web_metadata_batch(
    settings: WebSettings,
    *,
    runner: Runner = subprocess.run,
    base_env: dict[str, str] | os._Environ[str] | None = None,
) -> None:
    env = effective_subprocess_env(settings, base_env=base_env)
    if not metadata_configured(settings):
        raise WebError("Metadata collection is not configured for this web session. Restart with metadata options or disable metadata in config.")
    if not resolve_metadata_impala_shell(settings, env):
        raise WebError("Metadata preflight failed: impala-shell executable is not available. Fix server metadata settings or disable metadata in config.")
    krb5ccname = env.get("KRB5CCNAME", "")
    if krb5ccname and any(ord(ch) < 32 or ord(ch) == 127 for ch in krb5ccname):
        raise WebError("Metadata preflight failed: Kerberos cache setting is invalid. Fix server environment or disable metadata in config.")
    try:
        completed = run_subprocess(
            ["klist"],
            cwd=settings.repo_dir,
            timeout_sec=min(settings.timeout_sec, 30),
            runner=runner,
            env=env,
        )
    except OSError as exc:
        raise WebError("Metadata preflight failed: klist is not available. Fix server Kerberos setup or disable metadata in config.") from exc
    if completed.returncode != 0:
        raise WebError(
            "Metadata preflight failed: Kerberos cache is not available or expired. "
            "Renew the Kerberos ticket or disable metadata in config."
        )


def subprocess_failure_message(stage: str, completed: subprocess.CompletedProcess[str]) -> str:
    return (
        f"{stage} failed with exit code {completed.returncode}. "
        "Captured subprocess output is not shown because it may contain raw "
        "profile text, SQL, JSON, or credentials."
    )


def has_cm_credentials(
    env: dict[str, str] | os._Environ[str] | None = None,
    *,
    username: str | None = None,
) -> bool:
    env = os.environ if env is None else env
    token = (env.get("CM_TOKEN") or "").strip()
    effective_username = (username or env.get("CM_USERNAME") or "").strip()
    password = (env.get("CM_PASSWORD") or "").strip()
    return bool(token) or (bool(effective_username) and bool(password))


def run_web_analysis(
    query_id: str,
    report_mode: str,
    redact_identifiers: bool,
    settings: WebSettings,
    *,
    runner: Runner = subprocess.run,
    progress: ProgressFunc | None = None,
) -> WebResult:
    update_progress(progress, 0)
    validated_query_id = validate_query_id(query_id)
    if report_mode not in {"admin", "user"}:
        raise WebError("Report mode must be admin or user.")
    subprocess_env = effective_subprocess_env(settings)

    update_progress(progress, 1)
    expected_case_dir = expected_case_dir_for_query(validated_query_id, settings)
    if expected_case_dir.exists():
        ensure_complete_existing_case(expected_case_dir)
        case_dir = expected_case_dir
        case_source = "reused existing local case"
    else:
        case_dir = collect_case(
            validated_query_id,
            expected_case_dir,
            redact_identifiers,
            settings,
            runner,
            env=subprocess_env,
        )
        case_source = "collected now"

    report_name = f"report_{report_mode}.md"
    update_progress(progress, 2)
    analyzed = run_subprocess(
        build_analyzer_command(case_dir, settings),
        cwd=settings.repo_dir,
        timeout_sec=settings.timeout_sec,
        runner=runner,
        env=subprocess_env,
    )
    if analyzed.returncode != 0:
        raise WebError(subprocess_failure_message("Query Doctor analyzer", analyzed))

    update_progress(progress, 3)
    reported = run_subprocess(
        build_report_command(case_dir, report_mode, report_name, settings),
        cwd=settings.repo_dir,
        timeout_sec=settings.timeout_sec,
        runner=runner,
        env=subprocess_env,
    )
    update_progress(progress, 4)
    report_retry = False
    if reported.returncode == REPORT_VALIDATION_EXIT_CODE:
        retried = run_subprocess(
            build_report_command(case_dir, report_mode, report_name, settings),
            cwd=settings.repo_dir,
            timeout_sec=settings.timeout_sec,
            runner=runner,
            env=subprocess_env,
        )
        if retried.returncode == REPORT_VALIDATION_EXIT_CODE:
            raise WebError(REPORT_VALIDATION_FAILURE_MESSAGE)
        if retried.returncode != 0:
            raise WebError(subprocess_failure_message("Query Doctor report retry", retried))
        report_retry = True
    elif reported.returncode != 0:
        raise WebError(subprocess_failure_message("Query Doctor report generation", reported))

    facts_path = case_dir / "analysis_facts.md"
    report_path = case_dir / report_name
    if not facts_path.exists() or not report_path.exists():
        raise WebError("Analyzer/report output was not created.")

    facts_text = facts_path.read_text(encoding="utf-8", errors="replace")
    report_text = report_path.read_text(encoding="utf-8", errors="replace")
    facts = parse_facts_summary(facts_text)
    update_progress(progress, 5)
    return WebResult(
        query_id=validated_query_id,
        case_dir=case_dir,
        case_source=case_source,
        report_mode=report_mode,
        parsed_operators=facts.get("Parsed operators", "unknown"),
        cardinality_anomalies=facts.get("Cardinality anomalies", "unknown"),
        memory_anomalies=facts.get("Memory anomalies", "unknown"),
        report_text=report_text,
        report_retry=report_retry,
    )


def run_query_id_analysis(
    query_id: str,
    report_mode: str,
    redact_identifiers: bool,
    settings: WebSettings,
    *,
    runner: Runner = subprocess.run,
    progress: ProgressFunc | None = None,
) -> WebQueryAnalysisResult:
    del report_mode
    update_progress(progress, 0)
    validated_query_id = validate_query_id(query_id)
    subprocess_env = effective_subprocess_env(settings)

    update_progress(progress, 1)
    expected_case_dir = expected_case_dir_for_query(validated_query_id, settings)
    case_dir = collect_analyze_and_replace_query_case(
        validated_query_id,
        expected_case_dir,
        redact_identifiers,
        settings,
        runner,
        subprocess_env,
        progress=progress,
    )
    collection_status = "ok"
    analysis_status = "ok"

    update_progress(progress, 3)
    summary_case = build_query_id_summary_case(
        validated_query_id,
        case_dir,
        collection_status=collection_status,
        analysis_status=analysis_status,
    )
    update_progress(progress, 4)
    return WebQueryAnalysisResult(query_id=validated_query_id, case=summary_case)


def build_query_id_summary_case(
    query_id: str,
    case_dir: Path,
    *,
    collection_status: str = "ok",
    analysis_status: str = "ok",
) -> dict[str, object]:
    metadata = read_case_metadata(case_dir)
    profile_summary = read_profile_summary_fields(case_dir)
    case = batch_recent.CaseResult(
        index=1,
        query_id=query_id,
        duration_sec=case_duration_sec(metadata),
        user=profile_summary.get("user") or case_metadata_string(metadata, "user"),
        pool=profile_summary.get("pool") or case_metadata_string(metadata, "pool"),
        query_type=case_metadata_string(metadata, "query_type"),
        sql_verb=None,
        wrapper_dir=case_dir,
        actual_case_dir=case_dir,
        collection_status=collection_status,
        analysis_status=analysis_status,
        report_generated=False,
        report_validation_status="not_run",
    )
    batch_recent.inspect_case_outputs(case)
    batch_recent.score_case(case)
    summary_case = batch_recent.case_to_summary(case)
    summary_case.pop("case_index", None)
    summary_case.pop("case_dir", None)
    return summary_case


def read_case_metadata(case_dir: Path) -> dict[str, object]:
    metadata_path = case_dir / "cm_metadata.json"
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def case_metadata_string(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def read_profile_summary_fields(case_dir: Path) -> dict[str, str]:
    profile_path = case_dir / "profile_digest.md"
    try:
        with profile_path.open(encoding="utf-8", errors="replace") as handle:
            text = handle.read(PROFILE_SUMMARY_READ_CHARS)
    except OSError:
        return {}
    fields: dict[str, str] = {}
    for match in re.finditer(
        r"(?:^|\\n|\n)\s*(User|Pool|Request Pool|Resource Pool|Admission Pool)\s*:\s*([^\\\n\r\"]+)",
        text,
        flags=re.IGNORECASE,
    ):
        name = match.group(1).strip().lower()
        value = match.group(2).strip()
        if not value:
            continue
        if name == "user":
            fields["user"] = value
        elif "pool" in name:
            fields["pool"] = value
    return fields


def read_case_duration_sec(case_dir: Path) -> float | None:
    return case_duration_sec(read_case_metadata(case_dir))


def case_duration_sec(payload: dict[str, object]) -> float | None:
    if not payload:
        return None
    value = payload.get("duration_sec")
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    duration_ms = payload.get("duration_ms")
    if isinstance(duration_ms, (int, float)) and math.isfinite(float(duration_ms)):
        return float(duration_ms) / 1000
    return None


def render_query_analysis_output(result: object) -> list[str]:
    if isinstance(result, WebQueryAnalysisResult):
        return render_specific_query_result(result)
    return render_result(result)


def update_progress(progress: ProgressFunc | None, stage_index: int) -> None:
    if progress is not None:
        progress(stage_index)


def build_analyzer_command(case_dir: Path, settings: WebSettings) -> list[str]:
    return [
        sys.executable,
        str(settings.repo_dir / "query_doctor_pipeline.py"),
        str(case_dir),
        "--skip-report",
    ]


def build_query_id_analyzer_command(case_dir: Path, settings: WebSettings) -> list[str]:
    metadata_enabled = metadata_configured(settings)
    cmd = [
        sys.executable,
        str(settings.repo_dir / "query_doctor_pipeline.py"),
        str(case_dir),
        "--stop-after-analysis",
        "--metadata-failure-policy",
        "continue",
        "--metadata-mode",
        "on" if metadata_enabled else "off",
    ]
    if metadata_enabled:
        append_web_metadata_args(cmd, settings)
    return cmd


def build_report_command(case_dir: Path, report_mode: str, report_name: str, settings: WebSettings) -> list[str]:
    return [
        sys.executable,
        str(settings.repo_dir / "query_doctor_report.py"),
        str(case_dir),
        "--model",
        settings.model,
        "--mode",
        report_mode,
        "--out",
        report_name,
        "--keep-alive",
        "0",
        "--validation-mode",
        WEB_REPORT_VALIDATION_MODE,
    ]


def build_batch_case_report_command(case_dir: Path, settings: WebSettings) -> list[str]:
    return [
        sys.executable,
        str(settings.repo_dir / "query_doctor_pipeline.py"),
        str(case_dir),
        "--mode",
        "admin",
        "--model",
        settings.model,
        "--out",
        BATCH_REPORT_NAME,
        "--metadata-mode",
        "off",
        "--keep-alive",
        "0",
        "--report-validation-mode",
        WEB_REPORT_VALIDATION_MODE,
    ]


def build_optimized_query_command(case_dir: Path, settings: WebSettings) -> list[str]:
    return [
        sys.executable,
        str(settings.repo_dir / "query_doctor_optimize_query.py"),
        str(case_dir),
        "--model",
        optimizer_model_for_settings(settings),
        "--out",
        OPTIMIZED_QUERY_NAME,
        "--keep-alive",
        "0",
    ]


def optimizer_model_for_settings(settings: WebSettings) -> str:
    return settings.optimizer_model or settings.model


def collect_case(
    validated_query_id: str,
    expected_case_dir: Path,
    redact_identifiers: bool,
    settings: WebSettings,
    runner: Runner,
    env: dict[str, str] | None = None,
    out_dir: Path | None = None,
) -> Path:
    config_username = None
    try:
        config_username = optional_config_string(
            load_web_local_config(settings.config, cwd=Path.cwd()),
            "username",
        )
    except cm_collector.ConfigError:
        config_username = None
    if not has_cm_credentials(username=config_username):
        raise WebError(MISSING_CM_CREDENTIALS_MESSAGE)

    collection_out_dir = out_dir if out_dir is not None else settings.corpus_dir
    collector_cmd = [
        sys.executable,
        str(settings.repo_dir / "query_doctor_collect_cm_profiles.py"),
        "--config",
        str(settings.config),
        "--query-id",
        validated_query_id,
        "--limit",
        "1",
        "--redact",
        "--out",
        str(collection_out_dir),
    ]
    if redact_identifiers:
        collector_cmd.append("--redact-identifiers")
    if settings.max_profile_bytes is not None:
        collector_cmd.extend(["--max-profile-bytes", str(settings.max_profile_bytes)])

    collected = run_subprocess(
        collector_cmd,
        cwd=settings.repo_dir,
        timeout_sec=settings.timeout_sec,
        runner=runner,
        env=effective_subprocess_env(settings) if env is None else env,
    )
    if collected.returncode != 0:
        raise WebError(subprocess_failure_message("CM single-query collection", collected))

    case_dir = parse_output_case_dir(collected.stdout)
    if not case_dir.is_absolute():
        case_dir = (settings.repo_dir / case_dir).resolve()
    expected_corpus_dir = resolve_under_repo(settings.repo_dir, collection_out_dir)
    try:
        case_dir.relative_to(expected_corpus_dir)
    except ValueError as exc:
        raise WebError("Collector returned a case directory outside the web corpus directory.") from exc
    if case_dir != expected_case_dir:
        raise WebError("Collector returned a case directory that does not match the requested query id.")
    if not case_dir.exists():
        raise WebError("Collector did not create the expected case directory.")
    return case_dir


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def replace_case_dir_after_success(staged_case_dir: Path, expected_case_dir: Path) -> Path:
    ensure_complete_existing_case(staged_case_dir)
    if not (staged_case_dir / "analysis_facts.md").is_file():
        raise WebError("Analyzer output was not created.")

    expected_case_dir.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if expected_case_dir.exists() or expected_case_dir.is_symlink():
        backup_path = expected_case_dir.with_name(
            f".replace-{expected_case_dir.name}-{uuid.uuid4().hex}"
        )
        expected_case_dir.rename(backup_path)
    try:
        staged_case_dir.rename(expected_case_dir)
    except Exception:
        if backup_path is not None and backup_path.exists() and not expected_case_dir.exists():
            backup_path.rename(expected_case_dir)
        raise
    if backup_path is not None:
        remove_path(backup_path)
    return expected_case_dir


def collect_analyze_and_replace_query_case(
    validated_query_id: str,
    expected_case_dir: Path,
    redact_identifiers: bool,
    settings: WebSettings,
    runner: Runner,
    subprocess_env: dict[str, str],
    progress: ProgressFunc | None = None,
) -> Path:
    corpus_dir = resolve_under_repo(settings.repo_dir, settings.corpus_dir)
    staging_root = corpus_dir / f".query-refresh-{uuid.uuid4().hex}"
    staging_case_dir = staging_root / expected_case_dir.name
    try:
        case_dir = collect_case(
            validated_query_id,
            staging_case_dir,
            redact_identifiers,
            settings,
            runner,
            env=subprocess_env,
            out_dir=staging_root,
        )
        update_progress(progress, 2)
        analyzed = run_subprocess(
            build_query_id_analyzer_command(case_dir, settings),
            cwd=settings.repo_dir,
            timeout_sec=settings.timeout_sec,
            runner=runner,
            env=subprocess_env,
        )
        if analyzed.returncode != 0:
            raise WebError(subprocess_failure_message("Query Doctor analyzer", analyzed))
        return replace_case_dir_after_success(case_dir, expected_case_dir)
    finally:
        if staging_root.exists():
            remove_path(staging_root)


def expected_case_dir_for_query(validated_query_id: str, settings: WebSettings) -> Path:
    try:
        slug = cm_collector.safe_case_slug(validated_query_id)
    except cm_collector.OutputError as exc:
        raise WebError(str(exc)) from exc
    corpus_dir = resolve_under_repo(settings.repo_dir, settings.corpus_dir)
    case_dir = (corpus_dir / slug).resolve(strict=False)
    try:
        case_dir.relative_to(corpus_dir)
    except ValueError as exc:
        raise WebError("Computed web case directory is outside the web corpus directory.") from exc
    return case_dir


def ensure_complete_existing_case(case_dir: Path) -> None:
    if not case_dir.is_dir():
        raise WebError(
            "Existing Query ID case is incomplete. "
            "Re-run analysis to regenerate required artifacts."
        )
    missing = [name for name in COLLECTED_CASE_FILES if not (case_dir / name).is_file()]
    if missing:
        raise WebError(
            "Existing Query ID case is incomplete. "
            "Re-run analysis to regenerate required artifacts."
        )


def parse_output_case_dir(stdout: str) -> Path:
    match = OUTPUT_CASE_RE.search(stdout)
    if not match:
        raise WebError("Collector output did not include a case directory.")
    return Path(match.group("path").strip())


def resolve_under_repo(repo_dir: Path, path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (repo_dir / path).resolve()


def parse_facts_summary(facts_text: str) -> dict[str, str]:
    summary: dict[str, str] = {}
    for key in ("Parsed operators", "Cardinality anomalies", "Memory anomalies"):
        match = re.search(rf"^\s*[-*]?\s*{re.escape(key)}\s*:\s*(?P<value>\d+)\s*$", facts_text, re.MULTILINE)
        if match:
            summary[key] = match.group("value")
    return summary


def default_recent_scan_bucket(now: datetime | None = None) -> tuple[str, int]:
    current = now.astimezone(RECENT_SCAN_TIMEZONE) if now else datetime.now(RECENT_SCAN_TIMEZONE)
    bucket = current.replace(minute=0, second=0, microsecond=0)
    return bucket.date().isoformat(), bucket.hour


def allowed_recent_scan_dates(now: datetime | None = None) -> set[str]:
    current = now.astimezone(RECENT_SCAN_TIMEZONE).date() if now else datetime.now(RECENT_SCAN_TIMEZONE).date()
    return {(current - timedelta(days=days)).isoformat() for days in range(RECENT_SCAN_LOOKBACK_DAYS + 1)}


def parse_recent_scan_window(form: dict[str, list[str]]) -> tuple[str, int, str, str]:
    default_date, default_hour = default_recent_scan_bucket()
    scan_date = first_form_value(form, "scan_date") or default_date
    scan_hour_text = first_form_value(form, "scan_hour") or str(default_hour)
    if scan_date not in allowed_recent_scan_dates():
        raise WebError("Scan date must be today or one of the previous two days.")
    try:
        parsed_date = date.fromisoformat(scan_date)
    except ValueError as exc:
        raise WebError("Scan date must be formatted as YYYY-MM-DD.") from exc
    try:
        scan_hour = int(scan_hour_text)
    except ValueError as exc:
        raise WebError("Scan hour must be an integer from 0 to 23.") from exc
    if scan_hour < 0 or scan_hour > 23:
        raise WebError("Scan hour must be an integer from 0 to 23.")
    latest_date, latest_hour = default_recent_scan_bucket()
    if scan_date > latest_date or (scan_date == latest_date and scan_hour > latest_hour):
        raise WebError("Scan hour must not be in the future.")
    start_local = datetime.combine(parsed_date, datetime_time(scan_hour), tzinfo=RECENT_SCAN_TIMEZONE)
    end_local = start_local + timedelta(hours=RECENT_SCAN_BUCKET_HOURS)
    from_time = start_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_time = end_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return scan_date, scan_hour, from_time, to_time


def parse_batch_run_config(
    form: dict[str, list[str]],
    *,
    default_metadata_top_limit: int = WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT,
    default_parallelism: int = 50,
) -> BatchRunConfig:
    scan_date, scan_hour, from_time, to_time = parse_recent_scan_window(form)
    recent_window_minutes = RECENT_SCAN_BUCKET_HOURS * 60
    cm_inspect_limit = BATCH_CM_INSPECT_LIMIT_MAX
    triage_profile_limit = cm_inspect_limit
    metadata_top_limit = parse_non_negative_form_int(
        form, "metadata_top_limit", default=default_metadata_top_limit, maximum=BATCH_METADATA_TOP_LIMIT_MAX
    )
    min_duration_sec = parse_optional_non_negative_form_float(form, "min_duration_sec")
    max_duration_text = first_form_value(form, "max_duration_sec")
    max_duration_sec = None
    if max_duration_text:
        max_duration_sec = parse_non_negative_form_float(form, "max_duration_sec", default=0.0)
        if min_duration_sec is not None and max_duration_sec < min_duration_sec:
            raise WebError("max_duration_sec must be greater than or equal to min_duration_sec.")
    order = first_form_value(form, "order") or "duration-desc"
    if order not in BATCH_ORDER_VALUES:
        raise WebError("Order must be one of: recent, duration-desc, duration-asc, recent-duration-desc, status-priority.")
    parallelism_text = first_form_value(form, "parallelism")
    if not parallelism_text and first_form_value(form, "jobs"):
        parallelism_text = first_form_value(form, "jobs")
    if not parallelism_text and first_form_value(form, "cm_jobs"):
        parallelism_text = first_form_value(form, "cm_jobs")
    parallelism_form = {"parallelism": [parallelism_text]} if parallelism_text else {}
    parallelism = parse_positive_form_int(
        parallelism_form,
        "parallelism",
        default=default_parallelism,
        maximum=min(BATCH_CM_JOBS_MAX, BATCH_JOBS_MAX),
    )
    metadata_jobs = parse_positive_form_int(form, "metadata_jobs", default=5, maximum=BATCH_METADATA_JOBS_MAX)
    user = first_form_value(form, "user")
    pool = first_form_value(form, "pool")
    collect_cm_timeseries = bool(first_form_value(form, "collect_cm_timeseries"))
    return BatchRunConfig(
        recent_window_minutes=recent_window_minutes,
        scan_date=scan_date,
        scan_hour=scan_hour,
        from_time=from_time,
        to_time=to_time,
        cm_inspect_limit=cm_inspect_limit,
        triage_profile_limit=triage_profile_limit,
        metadata_top_limit=metadata_top_limit,
        min_duration_sec=min_duration_sec,
        max_duration_sec=max_duration_sec,
        order=order,
        parallelism=parallelism,
        cm_jobs=parallelism,
        jobs=parallelism,
        metadata_jobs=metadata_jobs,
        user=user,
        pool=pool,
        query_type="",
        include_failed=True,
        include_running=False,
        collect_cm_timeseries=collect_cm_timeseries,
    )


def parse_running_run_config(
    form: dict[str, list[str]],
    *,
    default_metadata_top_limit: int = WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT,
    default_parallelism: int = 50,
) -> BatchRunConfig:
    cm_inspect_limit = WEB_RUNNING_CM_INSPECT_LIMIT_DEFAULT
    metadata_top_limit = parse_non_negative_form_int(
        form, "metadata_top_limit", default=default_metadata_top_limit, maximum=BATCH_METADATA_TOP_LIMIT_MAX
    )
    min_duration_sec = parse_optional_non_negative_form_float(form, "min_duration_sec")
    parallelism_text = first_form_value(form, "parallelism")
    parallelism_form = {"parallelism": [parallelism_text]} if parallelism_text else {}
    parallelism = parse_positive_form_int(
        parallelism_form,
        "parallelism",
        default=default_parallelism,
        maximum=min(BATCH_CM_JOBS_MAX, BATCH_JOBS_MAX),
    )
    metadata_jobs = parse_positive_form_int(form, "metadata_jobs", default=5, maximum=BATCH_METADATA_JOBS_MAX)
    return BatchRunConfig(
        recent_window_minutes=WEB_RUNNING_SCAN_WINDOW_MINUTES,
        from_time=None,
        to_time=None,
        cm_inspect_limit=cm_inspect_limit,
        triage_profile_limit=cm_inspect_limit,
        metadata_top_limit=metadata_top_limit,
        min_duration_sec=min_duration_sec,
        max_duration_sec=None,
        order="status-priority",
        parallelism=parallelism,
        cm_jobs=parallelism,
        jobs=parallelism,
        metadata_jobs=metadata_jobs,
        user=first_form_value(form, "user"),
        pool=first_form_value(form, "pool"),
        query_type="",
        include_failed=False,
        include_running=True,
        only_running=True,
        collect_cm_timeseries=True,
    )


def validate_batch_config_for_settings(config: BatchRunConfig, settings: WebSettings) -> None:
    if config.metadata_top_limit > 0:
        if not metadata_configured(settings):
            raise WebError("Metadata collection is not configured for this web session. Restart with metadata options or disable metadata in config.")
        if settings.metadata_ca_cert and not settings.metadata_ssl:
            raise WebError("--metadata-ca-cert requires --metadata-ssl for web batch metadata.")


def metadata_configured(settings: WebSettings) -> bool:
    return bool(settings.metadata_coordinator)


def resolve_web_config_path(config_path: str | Path | None, *, cwd: Path) -> Path:
    if config_path:
        return Path(config_path).expanduser()
    default_path = cm_collector.discover_default_local_config(
        cwd=cwd,
        repo_root=Path(__file__).resolve().parent,
    )
    return default_path or (cwd / cm_collector.DEFAULT_LOCAL_CONFIG_NAME)


def load_web_local_config(config_path: str | Path | None, *, cwd: Path) -> dict[str, object]:
    if config_path:
        path = Path(config_path).expanduser()
        if not path.is_absolute():
            path = cwd / path
        if not path.is_file():
            return {}
        return cm_collector.load_local_config(str(path), cwd=cwd)
    else:
        result = load_and_validate_config(
            None,
            cwd=cwd,
            repo_root=Path(__file__).resolve().parent,
        )
        return result.values


def load_krb5ccname_from_local_config(config_path: Path, *, cwd: Path) -> str | None:
    values = load_web_local_config(config_path, cwd=cwd)
    value = values.get("krb5ccname")
    return value if isinstance(value, str) else None


def validate_web_startup_config(
    config_path: Path,
    *,
    cwd: Path,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> list[str]:
    env = os.environ if env is None else env
    config_values = load_web_local_config(config_path, cwd=cwd)
    missing: list[str] = []
    if not first_string_value(optional_config_string(config_values, "cm_url"), env.get("CM_URL")):
        missing.append("cm_url")
    if not first_string_value(optional_config_string(config_values, "username"), env.get("CM_USERNAME")):
        missing.append("username/cm_user")
    if not optional_config_string(config_values, "cluster"):
        missing.append("cluster")
    if not optional_config_string(config_values, "service"):
        missing.append("service")
    if not ((env.get("CM_PASSWORD") or "").strip() or (env.get("CM_TOKEN") or "").strip()):
        missing.append("CM_PASSWORD/CM_TOKEN environment variable")
    if missing:
        raise WebError(
            "Missing required CM startup setting(s): "
            + ", ".join(missing)
            + ". Provide non-secret CM settings in local config and CM_PASSWORD or CM_TOKEN via environment variables."
        )

    warnings: list[str] = []
    ca_bundle = optional_config_string(config_values, "ca_bundle")
    insecure_skip_verify = optional_config_bool(config_values, "insecure_skip_verify") is True
    if ca_bundle:
        ca_path = Path(ca_bundle).expanduser()
        if not ca_path.is_absolute():
            ca_path = cwd / ca_path
        if not ca_path.is_file() or not os.access(ca_path, os.R_OK):
            raise WebError(f"Configured ca_bundle is not readable: {ca_bundle}")
        if insecure_skip_verify:
            warnings.append(
                "insecure_skip_verify=true is set; CM TLS verification will be disabled even though ca_bundle is configured."
            )
    elif insecure_skip_verify:
        warnings.append("insecure_skip_verify=true is set; CM TLS verification will be disabled.")
    return warnings


def optional_config_string(config_values: dict[str, object], key: str) -> str | None:
    value = config_values.get(key)
    return value if isinstance(value, str) and value else None


def optional_config_int(config_values: dict[str, object], key: str) -> int | None:
    value = config_values.get(key)
    return value if isinstance(value, int) else None


def optional_config_bool(config_values: dict[str, object], key: str) -> bool | None:
    value = config_values.get(key)
    return value if isinstance(value, bool) else None


def first_string_value(*values: str | None) -> str | None:
    for value in values:
        if value:
            return value
    return None


def first_int_value(*values: int | None, default: int | None) -> int | None:
    for value in values:
        if value is not None:
            return value
    return default


def merged_bool_setting(cli_value: bool, config_value: bool | None, *, default: bool = False) -> bool:
    return bool(cli_value) or (config_value if config_value is not None else default)


def build_web_settings(args: argparse.Namespace, *, cwd: Path) -> WebSettings:
    config_path = resolve_web_config_path(args.config, cwd=cwd)
    config_values = load_web_local_config(args.config, cwd=cwd)
    return WebSettings(
        config=config_path,
        host=first_string_value(
            args.host,
            optional_config_string(config_values, "host"),
            DEFAULT_HOST,
        )
        or DEFAULT_HOST,
        port=first_int_value(
            args.port,
            optional_config_int(config_values, "port"),
            default=DEFAULT_PORT,
        ),
        allow_nonlocal_web_bind=args.allow_nonlocal_web_bind,
        max_profile_bytes=first_int_value(
            args.max_profile_bytes,
            optional_config_int(config_values, "max_profile_bytes"),
            default=None,
        ),
        model=args.model,
        optimizer_model=first_string_value(
            args.optimizer_model,
            optional_config_string(config_values, "optimizer_model"),
            DEFAULT_OPTIMIZER_MODEL,
            args.model,
        ),
        timeout_sec=args.timeout_sec,
        batch_summary=Path(args.batch_summary).expanduser() if args.batch_summary else None,
        metadata_coordinator=first_string_value(
            args.metadata_coordinator,
            optional_config_string(config_values, "metadata_coordinator"),
        ),
        metadata_impala_shell=first_string_value(
            args.metadata_impala_shell,
            optional_config_string(config_values, "metadata_impala_shell"),
        ),
        metadata_auth=first_string_value(
            args.metadata_auth,
            optional_config_string(config_values, "metadata_auth"),
            DEFAULT_METADATA_AUTH,
        )
        or DEFAULT_METADATA_AUTH,
        metadata_protocol=first_string_value(
            args.metadata_protocol,
            optional_config_string(config_values, "metadata_protocol"),
            DEFAULT_METADATA_PROTOCOL,
        )
        or DEFAULT_METADATA_PROTOCOL,
        metadata_ssl=merged_bool_setting(
            args.metadata_ssl,
            optional_config_bool(config_values, "metadata_ssl"),
        ),
        metadata_ca_cert=first_string_value(
            args.metadata_ca_cert,
            optional_config_string(config_values, "metadata_ca_cert"),
        ),
        metadata_timeout_sec=first_int_value(
            args.metadata_timeout_sec,
            optional_config_int(config_values, "metadata_timeout_sec"),
            default=DEFAULT_METADATA_TIMEOUT_SEC,
        ),
        metadata_max_tables=first_int_value(
            args.metadata_max_tables,
            optional_config_int(config_values, "metadata_max_tables"),
            default=None,
        ),
        metadata_max_output_bytes=first_int_value(
            args.metadata_max_output_bytes,
            optional_config_int(config_values, "metadata_max_output_bytes"),
            default=None,
        ),
        metadata_redact=merged_bool_setting(
            args.metadata_redact,
            optional_config_bool(config_values, "metadata_redact"),
        ),
        krb5ccname=optional_config_string(config_values, "krb5ccname"),
    )


def display_float(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value)


def parse_positive_form_int(
    form: dict[str, list[str]],
    name: str,
    *,
    default: int,
    maximum: int | None = None,
) -> int:
    text = first_form_value(form, name)
    if not text:
        value = default
    else:
        try:
            value = int(text)
        except ValueError as exc:
            raise WebError(f"{name} must be a positive integer.") from exc
    if value <= 0:
        raise WebError(f"{name} must be a positive integer.")
    if maximum is not None and value > maximum:
        raise WebError(f"{name} must be <= {maximum}.")
    return value


def parse_non_negative_form_int(
    form: dict[str, list[str]],
    name: str,
    *,
    default: int,
    maximum: int | None = None,
) -> int:
    text = first_form_value(form, name)
    if not text:
        value = default
    else:
        try:
            value = int(text)
        except ValueError as exc:
            raise WebError(f"{name} must be a non-negative integer.") from exc
    if value < 0:
        raise WebError(f"{name} must be a non-negative integer.")
    if maximum is not None and value > maximum:
        raise WebError(f"{name} must be <= {maximum}.")
    return value


def parse_non_negative_form_float(form: dict[str, list[str]], name: str, *, default: float) -> float:
    text = first_form_value(form, name)
    if not text:
        value = default
    else:
        try:
            value = float(text)
        except ValueError as exc:
            raise WebError(f"{name} must be a non-negative number.") from exc
    if value < 0:
        raise WebError(f"{name} must be a non-negative number.")
    if not math.isfinite(value):
        raise WebError(f"{name} must be a finite non-negative number.")
    return value


def parse_optional_non_negative_form_float(form: dict[str, list[str]], name: str) -> float | None:
    text = first_form_value(form, name)
    if not text:
        return None
    try:
        value = float(text)
    except ValueError as exc:
        raise WebError(f"{name} must be a non-negative number.") from exc
    if value < 0:
        raise WebError(f"{name} must be a non-negative number.")
    if not math.isfinite(value):
        raise WebError(f"{name} must be a finite non-negative number.")
    return value


def build_batch_command(job_id: str, config: BatchRunConfig, settings: WebSettings) -> tuple[list[str], Path]:
    validate_batch_config_for_settings(config, settings)
    out_dir = batch_output_dir(job_id)
    progress_path = batch_progress_path(job_id)
    metadata_enabled = config.metadata_top_limit > 0
    metadata_mode = "on" if metadata_enabled else "off"
    if config.only_running:
        from_time = to_time = None
    elif config.from_time and config.to_time:
        from_time, to_time = config.from_time, config.to_time
    else:
        _, _, from_time, to_time = parse_recent_scan_window({})
    cmd = [
        sys.executable,
        str(settings.repo_dir / "query_doctor_batch_recent.py"),
        "--config",
        str(settings.config),
        "--out",
        str(out_dir),
        "--cm-inspect-limit",
        str(config.cm_inspect_limit),
        "--triage-profile-limit",
        str(config.triage_profile_limit),
        "--metadata-top-limit",
        str(config.metadata_top_limit if metadata_enabled else 0),
        "--order",
        config.order,
        "--metadata-mode",
        metadata_mode,
        "--top-reports",
        "0",
        "--cm-jobs",
        str(config.cm_jobs),
        "--jobs",
        str(config.jobs),
        "--metadata-jobs",
        str(config.metadata_jobs if metadata_enabled else 1),
        "--overwrite",
        "--progress-jsonl",
        str(progress_path),
    ]
    if config.only_running:
        cmd.extend(["--recent-window-minutes", str(config.recent_window_minutes)])
    else:
        cmd.extend(["--from-time", str(from_time), "--to-time", str(to_time)])
    if config.min_duration_sec is None:
        cmd.append("--no-min-duration-filter")
    else:
        cmd.extend(["--min-duration-sec", display_float(config.min_duration_sec)])
    if config.max_duration_sec is not None:
        cmd.extend(["--max-duration-sec", display_float(config.max_duration_sec)])
    if config.user:
        cmd.extend(["--user", config.user])
    if config.pool:
        cmd.extend(["--pool", config.pool])
    if config.query_type:
        cmd.extend(["--query-type", config.query_type])
    if config.include_failed:
        cmd.append("--include-failed")
    if config.include_running:
        cmd.append("--include-running")
    if config.only_running:
        cmd.append("--only-running")
    if config.collect_cm_timeseries:
        cmd.append("--collect-cm-timeseries")
    if metadata_enabled:
        append_web_metadata_args(cmd, settings)
    if config.jobs > BATCH_FULL_JOBS_MAX:
        cmd.append("--allow-high-jobs")
    return cmd, out_dir


def append_web_metadata_args(cmd: list[str], settings: WebSettings) -> None:
    if settings.metadata_coordinator:
        cmd.extend(["--metadata-coordinator", settings.metadata_coordinator])
    if settings.metadata_impala_shell:
        cmd.extend(["--metadata-impala-shell", settings.metadata_impala_shell])
    cmd.extend(["--metadata-auth", settings.metadata_auth])
    cmd.extend(["--metadata-protocol", settings.metadata_protocol])
    cmd.extend(["--metadata-timeout-sec", str(settings.metadata_timeout_sec)])
    if settings.metadata_ssl:
        cmd.append("--metadata-ssl")
    if settings.metadata_ca_cert:
        cmd.extend(["--metadata-ca-cert", settings.metadata_ca_cert])
    if settings.metadata_max_tables is not None:
        cmd.extend(["--metadata-max-tables", str(settings.metadata_max_tables)])
    if settings.metadata_max_output_bytes is not None:
        cmd.extend(["--metadata-max-output-bytes", str(settings.metadata_max_output_bytes)])
    if settings.metadata_redact:
        cmd.append("--metadata-redact")


def handle_analyze_request(
    form: dict[str, list[str]],
    settings: WebSettings,
    *,
    analysis_func: AnalysisFunc = run_query_id_analysis,
) -> tuple[int, str]:
    query_id = first_form_value(form, "query_id")
    report_mode = "analysis"
    redact_identifiers = False
    if not query_id:
        return 400, render_query_page(settings, error="Query ID is required.")
    try:
        result = analysis_func(query_id, report_mode, redact_identifiers, settings)
    except WebError as exc:
        return 400, render_query_page(
            settings,
            query_id=query_id,
            report_mode=report_mode,
            error=sanitize_for_display(exc),
        )
    return 200, render_query_page(settings, report_mode=report_mode, result=result)


def handle_optimizer_request(
    form: dict[str, list[str]],
    settings: WebSettings,
    *,
    runner: Runner = subprocess.run,
) -> tuple[int, str]:
    sql = first_form_value(form, "sql")
    if not sql:
        return 400, render_optimizer_page(settings, error="SQL query text is required.")
    try:
        result = run_optimizer_analysis(sql, settings, runner=runner)
    except WebError as exc:
        return 400, render_optimizer_page(settings, error=sanitize_for_display(exc))
    return 200, render_optimizer_page(settings, result=result)


def run_optimizer_analysis(
    sql: str,
    settings: WebSettings,
    *,
    runner: Runner = subprocess.run,
) -> OptimizerAnalysis:
    try:
        tables = extract_referenced_tables(sql)
    except OptimizerSqlError as exc:
        raise WebError(str(exc)) from exc
    metadata_context, metadata_status, metadata_message = collect_optimizer_metadata(tables, settings, runner=runner)
    return analyze_query_optimizer(
        sql,
        tables=tables,
        metadata_context=metadata_context,
        metadata_status=metadata_status,
        metadata_message=metadata_message,
    )


def collect_optimizer_metadata(
    tables: list[ExtractedTable],
    settings: WebSettings,
    *,
    runner: Runner = subprocess.run,
) -> tuple[dict[str, Any] | None, str, str]:
    if not tables:
        return None, "unavailable", "Metadata collection was not attempted because no physical tables were detected."
    if not metadata_configured(settings):
        return None, "unavailable", "Metadata is unavailable. Configure local metadata settings to enable table facts."

    max_tables = settings.metadata_max_tables or metadata_workflow.DEFAULT_METADATA_MAX_TABLES
    plan = metadata_workflow.build_metadata_plan([table.name for table in tables], max_tables)
    if not plan.selected_tables:
        return None, "unavailable", "No fully qualified db.table identifiers were available for metadata collection."

    env = effective_subprocess_env(settings)
    impala_shell = resolve_metadata_impala_shell(settings, env)
    if not impala_shell:
        return None, "unavailable", "Metadata is unavailable because the local impala-shell executable is not available."

    with tempfile.TemporaryDirectory(prefix="query-doctor-optimizer-") as tmp:
        args = argparse.Namespace(
            table=plan.selected_tables,
            out=tmp,
            impala_shell=impala_shell,
            coordinator=settings.metadata_coordinator,
            auth=settings.metadata_auth,
            protocol=settings.metadata_protocol,
            ssl=settings.metadata_ssl,
            ca_cert=settings.metadata_ca_cert,
            timeout_sec=settings.metadata_timeout_sec,
            max_output_bytes=settings.metadata_max_output_bytes
            or impala_context_collector.DEFAULT_MAX_OUTPUT_BYTES,
            redact=True,
            dry_run=False,
            config=None,
            krb5ccname=settings.krb5ccname,
        )
        try:
            exit_code = impala_context_collector.collect_impala_context(args, runner=runner)
        except Exception:
            return None, "failed", "Metadata collection failed. Extracted tables are still shown with safe limitations."
        context = read_optimizer_metadata_context(Path(tmp))
    if context is None:
        return None, "failed", "Metadata collection did not produce safe metadata facts."
    if exit_code != 0:
        return context, "failed", "Metadata collection was incomplete. Only available safe facts are used."
    skipped = f" Skipped {len(plan.skipped_tables)} table(s) due to the configured metadata table limit." if plan.skipped_tables else ""
    return context, "collected", f"Safe metadata facts were collected for {len(plan.selected_tables)} table(s).{skipped}"


def read_optimizer_metadata_context(out_dir: Path) -> dict[str, Any] | None:
    context_path = out_dir / "impala_context.json"
    try:
        payload = json.loads(context_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return table_metadata_facts.context_from_payload(payload, context_path, out_dir)


def start_analyze_job(
    form: dict[str, list[str]],
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    analysis_func: AnalysisFunc = run_query_id_analysis,
) -> tuple[int, str]:
    query_id = first_form_value(form, "query_id")
    report_mode = "analysis"
    redact_identifiers = False
    if not query_id:
        return 400, render_query_page(settings, error="Query ID is required.")

    job = job_store.create(query_id, report_mode)
    thread = threading.Thread(
        target=run_analysis_job,
        args=(job.job_id, query_id, report_mode, redact_identifiers, settings, job_store, analysis_func),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


def start_batch_job(
    form: dict[str, list[str]],
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
) -> tuple[int, str]:
    try:
        config = parse_batch_run_config(
            form,
            default_metadata_top_limit=WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT if metadata_configured(settings) else 0,
            default_parallelism=50,
        )
        validate_batch_config_for_settings(config, settings)
        if config.metadata_top_limit > 0:
            preflight_web_metadata_batch(settings, runner=runner)
    except WebError as exc:
        return 400, render_batch_page(settings, error=sanitize_for_display(exc), form_values=form_values_from_form(form))

    job = job_store.create_batch(form_values_from_config(config))
    thread = threading.Thread(
        target=run_batch_job,
        args=(job.job_id, config, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


def start_running_job(
    form: dict[str, list[str]],
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
) -> tuple[int, str]:
    try:
        config = parse_running_run_config(
            form,
            default_metadata_top_limit=WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT if metadata_configured(settings) else 0,
            default_parallelism=50,
        )
        validate_batch_config_for_settings(config, settings)
        if config.metadata_top_limit > 0:
            preflight_web_metadata_batch(settings, runner=runner)
    except WebError as exc:
        return 400, render_running_queries_page(
            settings,
            error=sanitize_for_display(exc),
            form_values=form_values_from_form(form),
        )

    job = job_store.create_running_batch(form_values_from_config(config))
    thread = threading.Thread(
        target=run_batch_job,
        args=(job.job_id, config, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


def start_batch_case_report_job(
    case_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
    source: str = "auto",
) -> tuple[int, str]:
    if source == "running":
        effective_settings, case = resolve_running_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = running_detail_kwargs()
    else:
        effective_settings, case = resolve_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = {}
    if case is None:
        return 404, render_batch_case_not_found_page(effective_settings, case_id)
    if not case_allows_llm_report(case):
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store, **detail_kwargs)
    if job_store.running_batch_report(case_id) is not None:
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store, **detail_kwargs)
    case_dir = resolve_batch_case_report_dir(effective_settings, case)
    if case_dir is None:
        metadata_facts = load_batch_case_metadata_facts(effective_settings, case)
        report_state = {
            "status": "failed",
            "running": False,
            "trusted": False,
            "partial": False,
            "error": "Report generation requires a complete server-owned case. Re-run analysis first.",
        }
        return 400, render_batch_case_detail_page(effective_settings, case_id, case, metadata_facts, report_state=report_state, **detail_kwargs)

    job = job_store.create_batch_report(case_id, source="running" if source == "running" else "batch")
    thread = threading.Thread(
        target=run_batch_case_report_job,
        args=(job.job_id, case_id, case_dir, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


def start_specific_query_report_job(
    query_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
) -> tuple[int, str]:
    try:
        validated_query_id = validate_query_id(query_id)
    except WebError as exc:
        return 400, render_query_page(settings, query_id=query_id, error=exc)
    case_dir = expected_case_dir_for_query(validated_query_id, settings)
    try:
        ensure_complete_existing_case(case_dir)
    except WebError:
        message = WebError("Specific Query details are available after analysis completes.")
        return 404, render_query_page(settings, query_id=validated_query_id, error=message)
    if not (case_dir / "analysis_facts.md").is_file():
        message = WebError("Specific Query details are available after analysis completes.")
        return 404, render_query_page(settings, query_id=validated_query_id, error=message)
    case = build_query_id_summary_case(validated_query_id, case_dir)
    if not case_allows_llm_report(case):
        metadata_facts = load_specific_query_metadata_facts(case_dir)
        cm_metrics_facts = load_specific_query_cm_metrics_facts(case_dir)
        runtime_diagnosis_facts = load_specific_query_runtime_diagnosis_facts(case_dir)
        report_state = load_specific_query_report_state(settings, validated_query_id, case_dir, job_store)
        return 400, render_page(
            settings,
            active_nav="query",
            show_run_panel=False,
            extra_sections=[
                render_specific_query_detail(
                    validated_query_id,
                    case,
                    metadata_facts,
                    cm_metrics_facts,
                    runtime_diagnosis_facts,
                    report_state=report_state,
                )
            ],
        )
    if job_store.running_query_report(validated_query_id) is not None:
        metadata_facts = load_specific_query_metadata_facts(case_dir)
        cm_metrics_facts = load_specific_query_cm_metrics_facts(case_dir)
        runtime_diagnosis_facts = load_specific_query_runtime_diagnosis_facts(case_dir)
        report_state = load_specific_query_report_state(settings, validated_query_id, case_dir, job_store)
        return 400, render_page(
            settings,
            active_nav="query",
            show_run_panel=False,
            extra_sections=[
                render_specific_query_detail(
                    validated_query_id,
                    case,
                    metadata_facts,
                    cm_metrics_facts,
                    runtime_diagnosis_facts,
                    report_state=report_state,
                )
            ],
        )

    job = job_store.create_query_report(validated_query_id)
    thread = threading.Thread(
        target=run_specific_query_report_job,
        args=(job.job_id, validated_query_id, case_dir, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


def start_batch_case_optimized_query_job(
    case_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
    source: str = "auto",
) -> tuple[int, str]:
    if source == "running":
        effective_settings, case = resolve_running_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = running_detail_kwargs()
    else:
        effective_settings, case = resolve_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = {}
    if case is None:
        return 404, render_batch_case_not_found_page(effective_settings, case_id)
    case_dir = resolve_batch_case_report_dir(effective_settings, case)
    if case_dir is None:
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store, **detail_kwargs)
    if not case_has_safe_source_sql(case_dir):
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store, **detail_kwargs)
    if job_store.running_batch_optimized_query(case_id) is not None:
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store, **detail_kwargs)
    job = job_store.create_batch_optimized_query(case_id, source="running" if source == "running" else "batch")
    thread = threading.Thread(
        target=run_optimized_query_job,
        args=(job.job_id, case_id, case_dir, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


def start_specific_query_optimized_query_job(
    query_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
) -> tuple[int, str]:
    try:
        validated_query_id = validate_query_id(query_id)
    except WebError as exc:
        return 400, render_query_page(settings, query_id=query_id, error=exc)
    case_dir = expected_case_dir_for_query(validated_query_id, settings)
    try:
        ensure_complete_existing_case(case_dir)
    except WebError:
        message = WebError("Specific Query details are available after analysis completes.")
        return 404, render_query_page(settings, query_id=validated_query_id, error=message)
    if not case_has_safe_source_sql(case_dir):
        case = build_query_id_summary_case(validated_query_id, case_dir)
        metadata_facts = load_specific_query_metadata_facts(case_dir)
        cm_metrics_facts = load_specific_query_cm_metrics_facts(case_dir)
        runtime_diagnosis_facts = load_specific_query_runtime_diagnosis_facts(case_dir)
        optimized_query_state = load_optimized_query_state(case_dir, job_store, query_id=validated_query_id)
        return 400, render_page(
            settings,
            active_nav="query",
            show_run_panel=False,
            extra_sections=[
                render_specific_query_detail(
                    validated_query_id,
                    case,
                    metadata_facts,
                    cm_metrics_facts,
                    runtime_diagnosis_facts,
                    optimized_query_state=optimized_query_state,
                )
            ],
        )
    if job_store.running_query_optimized_query(validated_query_id) is not None:
        return render_specific_query_detail_for_request(settings, validated_query_id, job_store)
    job = job_store.create_query_optimized_query(validated_query_id)
    thread = threading.Thread(
        target=run_optimized_query_job,
        args=(job.job_id, validated_query_id, case_dir, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


def handle_batch_case_external_rewrite_validation(
    case_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    form: dict[str, list[str]],
    *,
    source: str = "auto",
) -> tuple[int, str]:
    if source == "running":
        effective_settings, case = resolve_running_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = running_detail_kwargs()
    else:
        effective_settings, case = resolve_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = {}
    if case is None:
        return 404, render_batch_case_not_found_page(effective_settings, case_id)
    case_dir = resolve_batch_case_report_dir(effective_settings, case)
    result = validate_external_optimizer_rewrite(case_dir, form)
    return 200, render_batch_case_detail_for_request(
        effective_settings,
        case_id,
        case,
        job_store,
        optimizer_validation_result=result,
        **detail_kwargs,
    )


def handle_specific_query_external_rewrite_validation(
    query_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    form: dict[str, list[str]],
) -> tuple[int, str]:
    try:
        validated_query_id = validate_query_id(query_id)
    except WebError as exc:
        return 400, render_query_page(settings, query_id=query_id, error=exc)
    case_dir = expected_case_dir_for_query(validated_query_id, settings)
    result = validate_external_optimizer_rewrite(case_dir, form)
    return render_specific_query_detail_for_request(
        settings,
        validated_query_id,
        job_store,
        optimizer_validation_result=result,
    )


def start_batch_case_llm_actions_job(
    case_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
    source: str = "auto",
) -> tuple[int, str]:
    if source == "running":
        effective_settings, case = resolve_running_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = running_detail_kwargs()
    else:
        effective_settings, case = resolve_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = {}
    if case is None:
        return 404, render_batch_case_not_found_page(effective_settings, case_id)
    if not case_allows_llm_report(case):
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store, **detail_kwargs)
    case_dir = resolve_batch_case_report_dir(effective_settings, case)
    if case_dir is None or not case_has_safe_source_sql(case_dir):
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store, **detail_kwargs)
    if job_store.running_batch_report(case_id) is not None or job_store.running_batch_optimized_query(case_id) is not None:
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store, **detail_kwargs)
    job = job_store.create_batch_llm_actions(case_id, source="running" if source == "running" else "batch")
    thread = threading.Thread(
        target=run_llm_actions_job,
        args=(job.job_id, case_id, case_dir, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


def start_specific_query_llm_actions_job(
    query_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
) -> tuple[int, str]:
    try:
        validated_query_id = validate_query_id(query_id)
    except WebError as exc:
        return 400, render_query_page(settings, query_id=query_id, error=exc)
    case_dir = expected_case_dir_for_query(validated_query_id, settings)
    try:
        ensure_complete_existing_case(case_dir)
    except WebError:
        message = WebError("Specific Query details are available after analysis completes.")
        return 404, render_query_page(settings, query_id=validated_query_id, error=message)
    case = build_query_id_summary_case(validated_query_id, case_dir)
    if not case_allows_llm_report(case) or not case_has_safe_source_sql(case_dir):
        return render_specific_query_detail_for_request(settings, validated_query_id, job_store)
    if job_store.running_query_report(validated_query_id) is not None or job_store.running_query_optimized_query(validated_query_id) is not None:
        return render_specific_query_detail_for_request(settings, validated_query_id, job_store)
    job = job_store.create_query_llm_actions(validated_query_id)
    thread = threading.Thread(
        target=run_llm_actions_job,
        args=(job.job_id, validated_query_id, case_dir, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


def form_values_from_form(form: dict[str, list[str]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for name in (
        "scan_date",
        "scan_hour",
        "metadata_top_limit",
        "min_duration_sec",
        "max_duration_sec",
        "order",
        "parallelism",
        "metadata_jobs",
        "user",
        "pool",
    ):
        values[name] = first_form_value(form, name)
    if not values.get("parallelism"):
        values["parallelism"] = first_form_value(form, "jobs") or first_form_value(form, "cm_jobs")
    return values


def form_values_from_config(config: BatchRunConfig) -> dict[str, object]:
    return {
        "scan_date": config.scan_date,
        "scan_hour": str(config.scan_hour),
        "metadata_top_limit": str(config.metadata_top_limit),
        "min_duration_sec": "" if config.min_duration_sec is None else display_float(config.min_duration_sec),
        "max_duration_sec": "" if config.max_duration_sec is None else display_float(config.max_duration_sec),
        "order": config.order,
        "parallelism": str(config.parallelism),
        "metadata_jobs": str(config.metadata_jobs),
        "user": config.user,
        "pool": config.pool,
    }


def run_analysis_job(
    job_id: str,
    query_id: str,
    report_mode: str,
    redact_identifiers: bool,
    settings: WebSettings,
    job_store: WebJobStore,
    analysis_func: AnalysisFunc,
) -> None:
    def progress(stage_index: int) -> None:
        job_store.update_stage(job_id, stage_index)

    try:
        if analysis_func is run_query_id_analysis:
            result = run_query_id_analysis(
                query_id,
                report_mode,
                redact_identifiers,
                settings,
                progress=progress,
            )
        elif analysis_func is run_web_analysis:
            result = run_web_analysis(
                query_id,
                report_mode,
                redact_identifiers,
                settings,
                progress=progress,
            )
        else:
            result = analysis_func(query_id, report_mode, redact_identifiers, settings)
        job_store.complete(job_id, result)
    except WebError as exc:
        job_store.fail(job_id, exc)
    except Exception:  # pragma: no cover - defensive UI sanitization.
        job_store.fail(job_id, "Unexpected web failure. Details are hidden because they may contain sensitive data.")


def run_batch_job(
    job_id: str,
    config: BatchRunConfig,
    settings: WebSettings,
    job_store: WebJobStore,
    runner: Runner,
) -> None:
    try:
        job_store.update_stage(job_id, 1)
        cmd, out_dir = build_batch_command(job_id, config, settings)
        completed = run_subprocess(
            cmd,
            cwd=settings.repo_dir,
            timeout_sec=settings.timeout_sec,
            runner=runner,
            env=effective_subprocess_env(settings),
        )
        if completed.returncode != 0:
            raise WebError(subprocess_failure_message("Query Doctor recent scan", completed))
        job_store.update_stage(job_id, 2)
        summary_path = out_dir / "batch_summary.json"
        if not summary_path.is_file():
            raise WebError("Batch run completed but batch_summary.json was not created.")
        job = job_store.get(job_id)
        if job is not None and job.kind == "running":
            job_store.set_latest_running_summary(summary_path)
            running_settings = replace(settings, batch_summary=summary_path)
            job_store.complete_html(
                job_id,
                render_batch_card(running_settings, title="Running Queries", details_base_path="/running/case"),
            )
        else:
            job_store.set_latest_batch_summary(summary_path)
            batch_settings = replace(settings, batch_summary=summary_path)
            job_store.complete_html(job_id, render_batch_card(batch_settings))
    except WebError as exc:
        job_store.fail(job_id, exc)
    except Exception:  # pragma: no cover - defensive UI sanitization.
        job_store.fail(job_id, "Unexpected recent scan failure. Details are hidden because they may contain sensitive data.")


def run_batch_case_report_job(
    job_id: str,
    case_id: str,
    case_dir: Path,
    settings: WebSettings,
    job_store: WebJobStore,
    runner: Runner,
) -> None:
    try:
        job_store.update_stage(job_id, 1)
        completed = run_subprocess(
            build_batch_case_report_command(case_dir, settings),
            cwd=settings.repo_dir,
            timeout_sec=settings.timeout_sec,
            runner=runner,
            env=effective_subprocess_env(settings),
        )
        job_store.update_stage(job_id, 2)
        if completed.returncode == REPORT_VALIDATION_EXIT_CODE:
            raise WebError(
                "Report generation completed but validation rejected the output. "
                "The partial report is untrusted and hidden."
            )
        if completed.returncode != 0:
            raise WebError(subprocess_failure_message("Query Doctor batch case report generation", completed))
        report_path = case_dir / BATCH_REPORT_NAME
        if not report_path.is_file():
            raise WebError("Report generation completed but the validated report was not created.")
        write_batch_case_report_validation_marker(case_dir)
        job_store.complete_html(job_id, f"Validated report generated for {case_id}.")
    except WebError as exc:
        job_store.fail(job_id, exc)


def run_specific_query_report_job(
    job_id: str,
    query_id: str,
    case_dir: Path,
    settings: WebSettings,
    job_store: WebJobStore,
    runner: Runner,
) -> None:
    try:
        job_store.update_stage(job_id, 1)
        completed = run_subprocess(
            build_batch_case_report_command(case_dir, settings),
            cwd=settings.repo_dir,
            timeout_sec=settings.timeout_sec,
            runner=runner,
            env=effective_subprocess_env(settings),
        )
        job_store.update_stage(job_id, 2)
        if completed.returncode == REPORT_VALIDATION_EXIT_CODE:
            raise WebError(
                "Report generation completed but validation rejected the output. "
                "The partial report is untrusted and hidden."
            )
        if completed.returncode != 0:
            raise WebError(subprocess_failure_message("Query Doctor specific query report generation", completed))
        report_path = case_dir / BATCH_REPORT_NAME
        if not report_path.is_file():
            raise WebError("Report generation completed but the validated report was not created.")
        write_batch_case_report_validation_marker(case_dir)
        job_store.complete_html(job_id, f"Validated report generated for {redact_browser_display_text(query_id)}.")
    except WebError as exc:
        job_store.fail(job_id, exc)
    except Exception:  # pragma: no cover - defensive UI sanitization.
        job_store.fail(job_id, "Unexpected report generation failure. Details are hidden because they may contain sensitive data.")


def generate_validated_report_artifact(case_dir: Path, settings: WebSettings, runner: Runner, *, label: str) -> None:
    completed = run_subprocess(
        build_batch_case_report_command(case_dir, settings),
        cwd=settings.repo_dir,
        timeout_sec=settings.timeout_sec,
        runner=runner,
        env=effective_subprocess_env(settings),
    )
    if completed.returncode == REPORT_VALIDATION_EXIT_CODE:
        raise WebError(
            "Report generation completed but validation rejected the output. "
            "The partial report is untrusted and hidden."
        )
    if completed.returncode != 0:
        raise WebError(subprocess_failure_message(label, completed))
    report_path = case_dir / BATCH_REPORT_NAME
    if not report_path.is_file():
        raise WebError("Report generation completed but the validated report was not created.")
    write_batch_case_report_validation_marker(case_dir)


def generate_validated_optimizer_artifact(case_dir: Path, settings: WebSettings, runner: Runner) -> None:
    completed = run_subprocess(
        build_optimized_query_command(case_dir, settings),
        cwd=settings.repo_dir,
        timeout_sec=settings.timeout_sec,
        runner=runner,
        env=effective_subprocess_env(settings),
    )
    if completed.returncode == REPORT_VALIDATION_EXIT_CODE:
        raise WebError(
            "Optimized query draft was generated but failed deterministic validation. "
            "The partial draft is untrusted and hidden."
        )
    if completed.returncode != 0:
        raise WebError(subprocess_failure_message("Query Doctor optimized query generation", completed))
    if not optimized_query_validated_exists(case_dir):
        raise WebError("Optimized query generation completed but the validated draft was not created.")


def run_llm_actions_job(
    job_id: str,
    label: str,
    case_dir: Path,
    settings: WebSettings,
    job_store: WebJobStore,
    runner: Runner,
) -> None:
    try:
        job_store.update_stage(job_id, 1)
        generate_validated_report_artifact(
            case_dir,
            settings,
            runner,
            label="Query Doctor selected case report generation",
        )
        job_store.update_stage(job_id, 2)
        generate_validated_optimizer_artifact(case_dir, settings, runner)
        job_store.complete_html(job_id, f"LLM report and optimizer generated for {redact_browser_display_text(label)}.")
    except WebError as exc:
        job_store.fail(job_id, exc)
    except Exception:  # pragma: no cover - defensive UI sanitization.
        job_store.fail(job_id, "Unexpected LLM action failure. Details are hidden because they may contain sensitive data.")


def run_optimized_query_job(
    job_id: str,
    label: str,
    case_dir: Path,
    settings: WebSettings,
    job_store: WebJobStore,
    runner: Runner,
) -> None:
    try:
        job_store.update_stage(job_id, 1)
        completed = run_subprocess(
            build_optimized_query_command(case_dir, settings),
            cwd=settings.repo_dir,
            timeout_sec=settings.timeout_sec,
            runner=runner,
            env=effective_subprocess_env(settings),
        )
        job_store.update_stage(job_id, 2)
        if completed.returncode == REPORT_VALIDATION_EXIT_CODE:
            raise WebError(
                "Optimized query draft was generated but failed deterministic validation. "
                "The partial draft is untrusted and hidden."
            )
        if completed.returncode != 0:
            raise WebError(subprocess_failure_message("Query Doctor optimized query generation", completed))
        if not optimized_query_validated_exists(case_dir):
            raise WebError("Optimized query generation completed but the validated draft was not created.")
        job_store.complete_html(job_id, f"Optimized query draft generated for {redact_browser_display_text(label)}.")
    except WebError as exc:
        job_store.fail(job_id, exc)
    except Exception:  # pragma: no cover - defensive UI sanitization.
        job_store.fail(job_id, "Unexpected optimized query generation failure. Details are hidden because they may contain sensitive data.")


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


def first_form_value(form: dict[str, list[str]], name: str) -> str:
    values = form.get(name, [])
    if not values:
        return ""
    return values[0].strip()


def form_flag_enabled(form: dict[str, list[str]], name: str) -> bool:
    return first_form_value(form, name).lower() in {"1", "true", "yes", "on"}


def read_analysis_facts_text(case_dir: Path) -> str:
    return (case_dir / "analysis_facts.md").read_text(encoding="utf-8", errors="replace")


def optimizer_manual_guidance(case_dir: Path | None, *, reason: str = "no_trusted_draft") -> str | None:
    if case_dir is None:
        return None
    try:
        facts_text = read_analysis_facts_text(case_dir)
        source = extract_optimizable_source_sql(read_source_sql(case_dir))
        risk_decision = decide_optimizer_risk_mode(source.sql)
        rewrite_recipe = detect_optimizer_rewrite_recipe(source.sql, facts_text)
    except (OSError, OptimizerSqlError, QueryOptimizationError):
        return None
    reason_bullets = {
        "failed": "- No trusted SQL rewrite is shown because optimizer generation did not complete with a validated outcome.",
        "partial_untrusted": "- No trusted SQL rewrite is shown because the generated draft remained untrusted.",
        "not_run": "- No trusted SQL rewrite is shown yet. Use the bullets below as manual rewrite guidance.",
    }
    bullets = [reason_bullets.get(reason, "- No trusted SQL rewrite is shown for this case.")]
    bullets.append("- The bullets below are deterministic manual rewrite guidance from Python-owned analysis facts.")
    bullets.extend(optimizer_specific_recommendation_bullets(facts_text, risk_decision, rewrite_recipe))
    text = "\n".join(bullets)
    return text if not validate_optimizer_recommendations_text(text) else None


def optimizer_manual_rewrite_allowed(state: dict[str, object]) -> bool:
    status = str(state.get("status") or "")
    if status == "partial_untrusted":
        return True
    if status == "generated" and str(state.get("fallback_reason") or "") == "validation_failed":
        return True
    if status == "failed" and "failed deterministic validation" in str(state.get("error") or "").lower():
        return True
    return False


def validate_external_optimizer_rewrite(case_dir: Path | None, form: dict[str, list[str]]) -> dict[str, object]:
    draft_sql = first_form_value(form, EXTERNAL_REWRITE_SQL_FIELD)
    if not draft_sql:
        return {
            "status": "not_ok",
            "title": "External rewrite validation failed",
            "items": ["Pasted rewrite is empty."],
        }
    if len(draft_sql.encode("utf-8")) > MAX_EXTERNAL_REWRITE_SQL_BYTES:
        return {
            "status": "not_ok",
            "title": "External rewrite validation failed",
            "items": ["Pasted rewrite exceeds the bounded validation limit."],
        }
    if case_dir is None:
        return {
            "status": "unavailable",
            "title": "External rewrite validation unavailable",
            "items": ["Source case is unavailable."],
        }
    try:
        facts_text = read_analysis_facts_text(case_dir)
        source = extract_optimizable_source_sql(read_source_sql(case_dir))
        rewrite_recipe = detect_optimizer_rewrite_recipe(source.sql, facts_text)
        errors = validate_draft_sql(source.sql, draft_sql, rewrite_recipe)
        if not errors and not draft_has_material_change(source.sql, draft_sql):
            errors = ["optimized draft does not materially change source SQL"]
    except (OSError, OptimizerSqlError, QueryOptimizationError):
        return {
            "status": "unavailable",
            "title": "External rewrite validation unavailable",
            "items": ["Source SQL is unavailable or outside optimizer validation scope."],
        }
    if errors:
        return {
            "status": "not_ok",
            "title": "External rewrite validation failed",
            "items": safe_optimizer_validation_categories(errors),
        }
    return {
        "status": "ok",
        "title": "External rewrite validation passed",
        "items": [
            "Read-only SQL scope passed.",
            "Physical table set was preserved.",
            "Filter, join, projection and result-shape checks passed.",
            "Run EXPLAIN comparison and rerun under comparable load before using it.",
        ],
    }


def safe_optimizer_validation_categories(errors: list[str]) -> list[str]:
    categories: list[str] = []
    for error in errors:
        lowered = error.lower()
        if "empty" in lowered:
            categories.append("Pasted rewrite is empty.")
        elif "incomplete" in lowered or "missing its final" in lowered:
            categories.append("Pasted rewrite appears incomplete.")
        elif "outside optimizer scope" in lowered or "final sql safety validation" in lowered:
            categories.append("Pasted rewrite is outside read-only optimizer scope.")
        elif "adds physical tables" in lowered or "physical table set changed" in lowered:
            categories.append("Physical table set changed.")
        elif "removes source where" in lowered or "where predicates changed" in lowered:
            categories.append("Source filter scope changed.")
        elif "removes source having" in lowered:
            categories.append("Source HAVING scope changed.")
        elif "removes source limit" in lowered:
            categories.append("Source LIMIT scope changed.")
        elif "distinct" in lowered:
            categories.append("DISTINCT output shape changed.")
        elif "join on" in lowered or "join predicates changed" in lowered:
            categories.append("JOIN conditions changed.")
        elif "join shape" in lowered:
            categories.append("JOIN shape changed.")
        elif "cte" in lowered:
            categories.append("CTE shape or body changed outside a supported recipe.")
        elif "top-level where expression" in lowered:
            categories.append("Top-level WHERE expression changed.")
        elif "top-level having expression" in lowered:
            categories.append("Top-level HAVING expression changed.")
        elif "top-level group" in lowered:
            categories.append("Top-level GROUP BY shape changed.")
        elif "top-level order" in lowered:
            categories.append("Top-level ORDER BY shape changed.")
        elif "projection" in lowered:
            categories.append("Output projection changed.")
        elif "materially change" in lowered:
            categories.append("Rewrite does not materially change the source query.")
        else:
            categories.append("Deterministic validator rejected the rewrite.")
    return dedupe_preserve_order(categories)[:8]


def batch_page_settings(settings: WebSettings, job_store: WebJobStore) -> WebSettings:
    if settings.batch_summary is not None:
        return settings
    latest = job_store.latest_batch_summary()
    if latest is None:
        return settings
    return replace(settings, batch_summary=latest)


def running_page_settings(settings: WebSettings, job_store: WebJobStore) -> WebSettings:
    latest = job_store.latest_running_summary()
    if latest is None:
        return replace(settings, batch_summary=None)
    return replace(settings, batch_summary=latest)


def running_detail_kwargs() -> dict[str, str]:
    return {
        "workflow_title": "Running Queries",
        "list_href": "/running#recent-results",
        "detail_base_path": "/running/case",
        "active_nav": "running",
    }


def resolve_running_case_detail_settings(
    settings: WebSettings,
    job_store: WebJobStore,
    case_id: str,
) -> tuple[WebSettings, dict[str, object] | None]:
    running_settings = running_page_settings(settings, job_store)
    running_summary = load_batch_summary(running_settings)
    running_case = find_batch_case(running_summary, case_id) if running_summary is not None else None
    if running_case is not None:
        running_case = case_with_detail_ranks(running_summary, case_id, running_case)
    return running_settings, running_case


def resolve_case_detail_settings(
    settings: WebSettings,
    job_store: WebJobStore,
    case_id: str,
) -> tuple[WebSettings, dict[str, object] | None]:
    batch_settings = batch_page_settings(settings, job_store)
    summary = load_batch_summary(batch_settings)
    case = find_batch_case(summary, case_id) if summary is not None else None
    if case is not None:
        return batch_settings, case_with_detail_ranks(summary, case_id, case)
    running_settings = running_page_settings(settings, job_store)
    if running_settings.batch_summary != batch_settings.batch_summary:
        running_summary = load_batch_summary(running_settings)
        running_case = find_batch_case(running_summary, case_id) if running_summary is not None else None
        if running_case is not None:
            return running_settings, case_with_detail_ranks(running_summary, case_id, running_case)
    return batch_settings, None


def load_batch_summary(settings: WebSettings) -> dict[str, object] | None:
    summary_path = settings.batch_summary
    if summary_path is None:
        return None
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return decorate_cases_with_optimizer_artifact_status(payload) if isinstance(payload, dict) else None


def case_with_detail_ranks(
    summary: dict[str, object] | None,
    case_id: str,
    case: dict[str, object],
) -> dict[str, object]:
    rank_fields = batch_case_detail_rank_fields(summary, case_id)
    if not rank_fields:
        return case
    decorated = dict(case)
    decorated.update(rank_fields)
    return decorated


def batch_case_detail_rank_fields(summary: dict[str, object] | None, case_id: str) -> dict[str, int]:
    if not isinstance(summary, dict):
        return {}
    view = present_recent_scan_summary(summary)
    result: dict[str, int] = {}
    for row in view.rows:
        if row.case_id == case_id:
            result["_detail_overall_rank"] = row.rank
            break
    for group, key in (
        ("optimization", "_detail_optimization_rank"),
        ("stats", "_detail_stats_rank"),
    ):
        rows = sort_rows_for_query_group(filter_rows_by_query_group(view.rows, group), group)
        for display_rank, row in enumerate(rows, start=1):
            if row.case_id == case_id:
                result[key] = display_rank
                break
    return result


def render_batch_case_detail_for_request(
    settings: WebSettings,
    case_id: str,
    case: dict[str, object],
    job_store: WebJobStore,
    *,
    job: WebJobSnapshot | None = None,
    workflow_title: str = "Finished Queries",
    list_href: str = "/#recent-results",
    detail_base_path: str = "/batch/case",
    active_nav: str = "batch",
    optimizer_validation_result: dict[str, object] | None = None,
) -> str:
    metadata_facts = load_batch_case_metadata_facts(settings, case)
    cm_metrics_facts = load_batch_case_cm_metrics_facts(settings, case)
    runtime_diagnosis_facts = load_batch_case_runtime_diagnosis_facts(settings, case)
    report_state = load_batch_case_report_state(settings, case_id, case, job_store, job=job)
    artifact_dir = resolve_batch_case_report_dir(settings, case)
    optimized_query_state = load_optimized_query_state(artifact_dir, job_store, batch_case_id=case_id, job=job)
    trusted_report_text = load_validated_batch_case_report(settings, case) if report_state.get("trusted") else None
    trusted_optimized_query = load_validated_optimized_query(artifact_dir) if artifact_dir is not None and optimized_query_state.get("trusted") else None
    trusted_optimizer_recommendations = (
        load_validated_optimizer_recommendations(artifact_dir)
        if artifact_dir is not None and optimized_query_state.get("trusted")
        else None
    )
    manual_guidance_reason = str(optimized_query_state.get("status") or "not_run")
    optimizer_guidance = (
        None
        if trusted_optimized_query
        or trusted_optimizer_recommendations
        or not optimizer_manual_rewrite_allowed(optimized_query_state)
        else optimizer_manual_guidance(artifact_dir, reason=manual_guidance_reason)
    )
    return render_batch_case_detail_page(
        settings,
        case_id,
        case,
        metadata_facts,
        cm_metrics_facts,
        runtime_diagnosis_facts,
        report_state=report_state,
        optimized_query_state=optimized_query_state,
        trusted_report_text=trusted_report_text,
        trusted_optimized_query=trusted_optimized_query,
        trusted_optimizer_recommendations=trusted_optimizer_recommendations,
        optimizer_manual_guidance=optimizer_guidance,
        optimizer_validation_result=optimizer_validation_result,
        workflow_title=workflow_title,
        list_href=list_href,
        detail_base_path=detail_base_path,
        active_nav=active_nav,
    )


def render_specific_query_detail_for_request(
    settings: WebSettings,
    query_id: str,
    job_store: WebJobStore,
    *,
    job: WebJobSnapshot | None = None,
    optimizer_validation_result: dict[str, object] | None = None,
) -> tuple[int, str]:
    try:
        validated_query_id = validate_query_id(query_id)
    except WebError as exc:
        return 400, render_query_page(settings, query_id=query_id, error=exc)
    case_dir = expected_case_dir_for_query(validated_query_id, settings)
    try:
        ensure_complete_existing_case(case_dir)
    except WebError:
        message = WebError("Specific Query details are available after analysis completes.")
        return 404, render_query_page(settings, query_id=validated_query_id, error=message)
    if not (case_dir / "analysis_facts.md").is_file():
        message = WebError("Specific Query details are available after analysis completes.")
        return 404, render_query_page(settings, query_id=validated_query_id, error=message)
    case = build_query_id_summary_case(validated_query_id, case_dir)
    metadata_facts = load_specific_query_metadata_facts(case_dir)
    cm_metrics_facts = load_specific_query_cm_metrics_facts(case_dir)
    runtime_diagnosis_facts = load_specific_query_runtime_diagnosis_facts(case_dir)
    report_state = load_specific_query_report_state(settings, validated_query_id, case_dir, job_store, job=job)
    optimized_query_state = load_optimized_query_state(case_dir, job_store, query_id=validated_query_id, job=job)
    trusted_report_text = load_validated_specific_query_report(case_dir) if report_state.get("trusted") else None
    trusted_optimized_query = load_validated_optimized_query(case_dir) if optimized_query_state.get("trusted") else None
    trusted_optimizer_recommendations = (
        load_validated_optimizer_recommendations(case_dir) if optimized_query_state.get("trusted") else None
    )
    manual_guidance_reason = str(optimized_query_state.get("status") or "not_run")
    optimizer_guidance = (
        None
        if trusted_optimized_query
        or trusted_optimizer_recommendations
        or not optimizer_manual_rewrite_allowed(optimized_query_state)
        else optimizer_manual_guidance(case_dir, reason=manual_guidance_reason)
    )
    return 200, render_page(
        settings,
        active_nav="query",
        show_run_panel=False,
        extra_sections=[
            render_specific_query_detail(
                validated_query_id,
                case,
                metadata_facts,
                cm_metrics_facts,
                runtime_diagnosis_facts,
                report_state=report_state,
                optimized_query_state=optimized_query_state,
                trusted_report_text=trusted_report_text,
                trusted_optimized_query=trusted_optimized_query,
                trusted_optimizer_recommendations=trusted_optimizer_recommendations,
                optimizer_manual_guidance=optimizer_guidance,
                optimizer_validation_result=optimizer_validation_result,
            )
        ],
    )


def render_specific_query_report_for_request(settings: WebSettings, query_id: str) -> tuple[int, str]:
    try:
        validated_query_id = validate_query_id(query_id)
    except WebError as exc:
        return 400, render_query_page(settings, query_id=query_id, error=exc)
    case_dir = expected_case_dir_for_query(validated_query_id, settings)
    try:
        ensure_complete_existing_case(case_dir)
    except WebError:
        message = WebError("Specific Query details are available after analysis completes.")
        return 404, render_query_page(settings, query_id=validated_query_id, error=message)
    case = build_query_id_summary_case(validated_query_id, case_dir)
    report_text = load_validated_specific_query_report(case_dir)
    if report_text is None:
        metadata_facts = load_specific_query_metadata_facts(case_dir)
        cm_metrics_facts = load_specific_query_cm_metrics_facts(case_dir)
        runtime_diagnosis_facts = load_specific_query_runtime_diagnosis_facts(case_dir)
        return 404, render_page(
            settings,
            active_nav="query",
            show_run_panel=False,
            extra_sections=[
                render_specific_query_detail(
                    validated_query_id,
                    case,
                    metadata_facts,
                    cm_metrics_facts,
                    runtime_diagnosis_facts,
                )
            ],
        )
    return 200, render_specific_query_report_page(settings, validated_query_id, case, report_text)


def render_specific_query_report_page(
    settings: WebSettings,
    query_id: str,
    case: dict[str, object],
    report_text: str,
) -> str:
    section = (
        "<section class=\"panel report-header\" aria-label=\"Specific Query report header\">"
        "<div class=\"breadcrumb\"><a href=\"/query\">Specific Query</a><span>/</span>"
        f"<a href=\"/query/details/{quote(query_id, safe='')}\">{html.escape(query_id)}</a>"
        "<span>/</span><span>validated report</span></div>"
        "<div class=\"report-title-row\"><div>"
        "<h1>Validated Specific Query report</h1>"
        "<div class=\"report-subtitle\">Rendered only after the report action completed validation.</div>"
        "<div class=\"query-line\">"
        f"<span>Query:</span><code>{html.escape(query_id)}</code>"
        "</div></div></div>"
        "<div class=\"status-strip\" aria-label=\"Report status\">"
        "<span class=\"status-item\"><span class=\"dot\"></span>Validation: <span class=\"badge green\">PASS</span></span>"
        "<span class=\"status-item\"><span class=\"dot gray\"></span>Mode: <span class=\"badge gray\">admin</span></span>"
        "</div></section>"
        "<details class=\"panel report-card\" open aria-label=\"Validated report body\">"
        "<summary>Validated diagnosis markdown</summary>"
        f"<div class=\"report-body\">{render_report_markdown_html(report_text, with_heading_ids=True)}</div>"
        "</details>"
    )
    return render_page(settings, active_nav="query", show_run_panel=False, extra_sections=[section])


def load_specific_query_metadata_facts(case_dir: Path) -> dict[str, Any] | None:
    fallback_facts: dict[str, Any] | None = None
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        facts = load_batch_case_analysis_metadata_facts(artifact_dir)
        if facts and facts.get("tables"):
            return facts
        if facts and fallback_facts is None:
            fallback_facts = facts
        context_facts = load_batch_case_impala_context_facts(artifact_dir)
        if context_facts:
            return context_facts
    return fallback_facts


def load_specific_query_cm_metrics_facts(case_dir: Path) -> dict[str, Any] | None:
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        facts = load_case_analysis_cm_metrics_facts(artifact_dir)
        if facts:
            return facts
    return None


def load_specific_query_runtime_diagnosis_facts(case_dir: Path) -> dict[str, Any] | None:
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        facts = load_case_analysis_runtime_diagnosis_facts(artifact_dir)
        if facts:
            return facts
    return None


def load_validated_batch_case_report(settings: WebSettings, case: dict[str, object]) -> str | None:
    case_dir = resolve_batch_case_report_dir(settings, case)
    if case_dir is None or not batch_case_validated_report_exists(case_dir, case):
        return None
    try:
        report_text = (case_dir / BATCH_REPORT_NAME).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    hidden_paths = {str(case_dir)}
    wrapper_dir = resolve_batch_case_dir(settings, case)
    if wrapper_dir is not None:
        hidden_paths.add(str(wrapper_dir))
    for path in hidden_paths:
        if path:
            report_text = report_text.replace(path, "[local case path hidden]")
    return report_text


def load_validated_specific_query_report(case_dir: Path) -> str | None:
    if not batch_case_validated_report_exists(case_dir):
        return None
    try:
        report_text = (case_dir / BATCH_REPORT_NAME).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    case_path = str(case_dir)
    return report_text.replace(case_path, "[local case path hidden]") if case_path else report_text


def load_validated_optimized_query(case_dir: Path) -> str | None:
    if not optimized_query_validated_exists(case_dir):
        return None
    marker = read_optimized_query_marker(case_dir)
    if marker.get("output_kind") in {"recommendations_only", "no_rewrite"}:
        return None
    try:
        return (case_dir / OPTIMIZED_QUERY_NAME).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def load_validated_optimizer_recommendations(case_dir: Path) -> str | None:
    if not optimized_query_validated_exists(case_dir):
        return None
    marker = read_optimized_query_marker(case_dir)
    if marker.get("output_kind") not in {"recommendations_only", "no_rewrite"}:
        return None
    try:
        recommendations = (case_dir / OPTIMIZED_QUERY_RECOMMENDATIONS_NAME).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if validate_optimizer_recommendations_text(recommendations):
        return None
    return recommendations


def find_batch_case(summary: dict[str, object], case_id: str) -> dict[str, object] | None:
    if not re.fullmatch(r"case-[0-9]{3}", case_id):
        return None
    cases = summary.get("cases")
    if not isinstance(cases, list):
        return None
    for case in cases:
        if not isinstance(case, dict):
            continue
        try:
            index = int(case.get("case_index"))
        except (TypeError, ValueError):
            continue
        if f"case-{index:03d}" == case_id:
            return case
    return None


def load_batch_case_metadata_facts(settings: WebSettings, case: dict[str, object]) -> dict[str, Any] | None:
    case_dir = resolve_batch_case_dir(settings, case)
    if case_dir is None:
        return None
    fallback_facts: dict[str, Any] | None = None
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        facts = load_batch_case_analysis_metadata_facts(artifact_dir)
        if facts and facts.get("tables"):
            return facts
        if facts and fallback_facts is None:
            fallback_facts = facts
        context_facts = load_batch_case_impala_context_facts(artifact_dir)
        if context_facts:
            return context_facts
    return fallback_facts


def load_batch_case_cm_metrics_facts(settings: WebSettings, case: dict[str, object]) -> dict[str, Any] | None:
    case_dir = resolve_batch_case_dir(settings, case)
    if case_dir is None:
        return None
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        facts = load_case_analysis_cm_metrics_facts(artifact_dir)
        if facts:
            return facts
    return None


def load_batch_case_runtime_diagnosis_facts(settings: WebSettings, case: dict[str, object]) -> dict[str, Any] | None:
    case_dir = resolve_batch_case_dir(settings, case)
    if case_dir is None:
        return None
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        facts = load_case_analysis_runtime_diagnosis_facts(artifact_dir)
        if facts:
            return facts
    return None


def load_batch_case_report_state(
    settings: WebSettings,
    case_id: str,
    case: dict[str, object],
    job_store: WebJobStore,
    *,
    job: WebJobSnapshot | None = None,
) -> dict[str, object]:
    if job is not None and job.status == "running" and job.kind in {"batch_report", "batch_llm_actions"}:
        running_job = job
    else:
        running_job = job_store.running_batch_report(case_id)
    artifact_dir = resolve_batch_case_report_dir(settings, case)
    trusted = False
    partial = False
    if artifact_dir is not None:
        trusted = batch_case_validated_report_exists(artifact_dir, case)
        partial = (artifact_dir / BATCH_REPORT_PARTIAL_NAME).is_file()
    status = "generated" if trusted else "not_run"
    if partial and not trusted:
        status = "partial_untrusted"
    if running_job is not None:
        status = "running"
    elif job is not None and job.status == "failed" and job.kind == "batch_report":
        status = "failed"
    elif job is not None and job.status == "failed" and job.kind == "batch_llm_actions" and not trusted:
        status = "failed"
    report_job = running_job if running_job is not None else job
    return {
        "status": status,
        "running": running_job is not None,
        "trusted": trusted,
        "partial": partial,
        "error": job.error if job is not None and job.status == "failed" else "",
        "job_id": report_job.job_id if report_job is not None else "",
        "stage_label": report_job.stage_label if report_job is not None else "",
        "progress": report_job.progress if report_job is not None else 0,
    }


def load_specific_query_report_state(
    settings: WebSettings,
    query_id: str,
    case_dir: Path,
    job_store: WebJobStore,
    *,
    job: WebJobSnapshot | None = None,
) -> dict[str, object]:
    if job is not None and job.status == "running" and job.kind in {"query_report", "query_llm_actions"}:
        running_job = job
    else:
        running_job = job_store.running_query_report(query_id)
    trusted = batch_case_validated_report_exists(case_dir)
    partial = (case_dir / BATCH_REPORT_PARTIAL_NAME).is_file()
    status = "generated" if trusted else "not_run"
    if partial and not trusted:
        status = "partial_untrusted"
    if running_job is not None:
        status = "running"
    elif job is not None and job.status == "failed" and job.kind == "query_report":
        status = "failed"
    elif job is not None and job.status == "failed" and job.kind == "query_llm_actions" and not trusted:
        status = "failed"
    report_job = running_job if running_job is not None else job
    return {
        "status": status,
        "running": running_job is not None,
        "trusted": trusted,
        "partial": partial,
        "error": job.error if job is not None and job.status == "failed" else "",
        "job_id": report_job.job_id if report_job is not None else "",
        "stage_label": report_job.stage_label if report_job is not None else "",
        "progress": report_job.progress if report_job is not None else 0,
    }


def case_has_safe_source_sql(case_dir: Path) -> bool:
    for name in ("original_query.sql", "query.sql", "sql.sql"):
        path = case_dir / name
        if path.is_file():
            try:
                source = extract_optimizable_source_sql(
                    path.read_text(encoding="utf-8", errors="replace")
                )
                extract_referenced_tables(source.sql)
                return True
            except (OSError, OptimizerSqlError, QueryOptimizationError):
                return False
    metadata_path = case_dir / "cm_metadata.json"
    if not metadata_path.is_file():
        return False
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    for key in ("statement", "statementText", "statement_text", "query", "queryText", "query_text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            try:
                source = extract_optimizable_source_sql(value)
                extract_referenced_tables(source.sql)
                return True
            except (OptimizerSqlError, QueryOptimizationError):
                return False
    return False


def load_optimized_query_state(
    case_dir: Path | None,
    job_store: WebJobStore,
    *,
    batch_case_id: str | None = None,
    query_id: str | None = None,
    job: WebJobSnapshot | None = None,
) -> dict[str, object]:
    running_job: WebJobSnapshot | None = None
    if job is not None and job.status == "running" and job.kind in {"batch_optimized_query", "query_optimized_query", "batch_llm_actions", "query_llm_actions"}:
        running_job = job
    elif batch_case_id is not None:
        running_job = job_store.running_batch_optimized_query(batch_case_id)
    elif query_id is not None:
        running_job = job_store.running_query_optimized_query(query_id)

    trusted = case_dir is not None and optimized_query_validated_exists(case_dir)
    marker = read_optimized_query_marker(case_dir) if case_dir is not None and trusted else {}
    partial = case_dir is not None and (
        (case_dir / OPTIMIZED_QUERY_PARTIAL_NAME).is_file()
        or ((case_dir / OPTIMIZED_QUERY_NAME).is_file() and not trusted)
    )
    source_available = case_dir is not None and case_has_safe_source_sql(case_dir)
    status = "generated" if trusted else "not_run"
    if not source_available and not trusted:
        status = "unavailable"
    if partial and not trusted:
        status = "partial_untrusted"
    if running_job is not None:
        status = "running"
    elif job is not None and job.status == "failed" and job.kind in {"batch_optimized_query", "query_optimized_query"}:
        status = "failed"
    elif (
        job is not None
        and job.status == "failed"
        and job.kind in {"batch_llm_actions", "query_llm_actions"}
        and not trusted
        and case_dir is not None
        and batch_case_validated_report_exists(case_dir)
    ):
        status = "failed"
    state_job = running_job if running_job is not None else job
    return {
        "status": status,
        "running": running_job is not None,
        "trusted": trusted,
        "partial": partial,
        "source_available": source_available,
        "output_kind": marker.get("output_kind") or "sql_draft",
        "fallback_reason": marker.get("fallback_reason") or "",
        "risk_mode": marker.get("risk_mode") or "",
        "source_scope": marker.get("source_scope") or "",
        "error": job.error if job is not None and job.status == "failed" else "",
        "job_id": state_job.job_id if state_job is not None else "",
        "stage_label": state_job.stage_label if state_job is not None else "",
        "progress": state_job.progress if state_job is not None else 0,
    }


def case_allows_llm_report(case: dict[str, object]) -> bool:
    return case_score_severity(case) != "clean"


def resolve_batch_case_report_dir(settings: WebSettings, case: dict[str, object]) -> Path | None:
    case_dir = resolve_batch_case_dir(settings, case)
    if case_dir is None:
        return None
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        if (artifact_dir / "profile_digest.md").is_file():
            return artifact_dir
    return None


def file_sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_optimized_query_marker(case_dir: Path) -> dict[str, object]:
    try:
        marker = json.loads((case_dir / OPTIMIZED_QUERY_VALIDATION_MARKER).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return marker if isinstance(marker, dict) else {}


def batch_case_validated_report_exists(case_dir: Path, case: dict[str, object] | None = None) -> bool:
    report_path = case_dir / BATCH_REPORT_NAME
    facts_path = case_dir / "analysis_facts.md"
    marker_path = case_dir / BATCH_REPORT_VALIDATION_MARKER
    if not report_path.is_file() or not facts_path.is_file():
        return False
    if not marker_path.is_file():
        return False
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if marker.get("validated") is not True:
        return False
    if marker.get("validation_mode") != WEB_REPORT_VALIDATION_MODE:
        return False
    if marker.get("report") != BATCH_REPORT_NAME:
        return False
    if marker.get("report_sha256") != file_sha256(report_path):
        return False
    if marker.get("facts_sha256") != file_sha256(facts_path):
        return False
    return True


def optimized_query_validated_exists(case_dir: Path) -> bool:
    draft_path = case_dir / OPTIMIZED_QUERY_NAME
    recommendations_path = case_dir / OPTIMIZED_QUERY_RECOMMENDATIONS_NAME
    facts_path = case_dir / "analysis_facts.md"
    marker_path = case_dir / OPTIMIZED_QUERY_VALIDATION_MARKER
    if not facts_path.is_file() or not marker_path.is_file():
        return False
    marker = read_optimized_query_marker(case_dir)
    if not marker:
        return False
    if marker.get("validated") is not True:
        return False
    if marker.get("schema_version") != OPTIMIZED_QUERY_MARKER_SCHEMA_VERSION:
        return False
    if marker.get("validation_mode") != OPTIMIZED_QUERY_VALIDATION_MODE:
        return False
    output_kind = marker.get("output_kind") or "sql_draft"
    if output_kind in {"recommendations_only", "no_rewrite"}:
        if marker.get("recommendations") != OPTIMIZED_QUERY_RECOMMENDATIONS_NAME:
            return False
        if not recommendations_path.is_file():
            return False
        if marker.get("recommendations_sha256") != file_sha256(recommendations_path):
            return False
    else:
        if marker.get("draft") != OPTIMIZED_QUERY_NAME:
            return False
        if not draft_path.is_file():
            return False
        if marker.get("draft_sha256") != file_sha256(draft_path):
            return False
    if marker.get("facts_sha256") != file_sha256(facts_path):
        return False
    try:
        source_sql = extract_optimizable_source_sql(read_source_sql(case_dir))
        if marker.get("source_scope") != source_sql.scope:
            return False
        if marker.get("source_sql_sha256") != text_sha256(source_sql.sql):
            return False
        if output_kind not in {"recommendations_only", "no_rewrite"}:
            draft_text = draft_path.read_text(encoding="utf-8", errors="replace")
            if sql_completeness_errors(draft_text):
                return False
            extract_referenced_tables(draft_text)
    except (OSError, OptimizerSqlError, QueryOptimizationError):
        return False
    return True


def write_batch_case_report_validation_marker(case_dir: Path) -> None:
    marker = {
        "report": BATCH_REPORT_NAME,
        "validated": True,
        "validation_mode": WEB_REPORT_VALIDATION_MODE,
        "report_sha256": file_sha256(case_dir / BATCH_REPORT_NAME),
        "facts_sha256": file_sha256(case_dir / "analysis_facts.md"),
        "source": "query_doctor_web_server batch case report action",
    }
    (case_dir / BATCH_REPORT_VALIDATION_MARKER).write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")


def batch_case_artifact_dirs(case_dir: Path) -> list[Path]:
    try:
        resolved_case_dir = case_dir.resolve(strict=True)
    except OSError:
        return []
    if not resolved_case_dir.is_dir():
        return []

    dirs = [resolved_case_dir]
    try:
        children = sorted(resolved_case_dir.iterdir(), key=lambda path: path.name)
    except OSError:
        return dirs
    for child in children:
        try:
            resolved_child = child.resolve(strict=True)
            resolved_child.relative_to(resolved_case_dir)
        except (OSError, ValueError):
            continue
        if resolved_child.is_dir() and batch_case_artifact_dir_has_safe_facts(resolved_child):
            dirs.append(resolved_child)
    return dirs


def batch_case_artifact_dir_has_safe_facts(case_dir: Path) -> bool:
    return any(
        (case_dir / name).is_file()
        for name in ("analysis_facts.md", "impala_context.json")
    ) or (case_dir / "impala_context" / "impala_context.json").is_file()


def load_batch_case_analysis_metadata_facts(case_dir: Path) -> dict[str, Any] | None:
    try:
        facts_path = (case_dir / "analysis_facts.md").resolve(strict=True)
        facts_path.relative_to(case_dir)
        if facts_path.stat().st_size > MAX_METADATA_FACTS_BYTES:
            return None
        text = facts_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None
    return parse_table_metadata_context_facts(text)


def load_case_analysis_cm_metrics_facts(case_dir: Path) -> dict[str, Any] | None:
    try:
        facts_path = (case_dir / "analysis_facts.md").resolve(strict=True)
        facts_path.relative_to(case_dir)
        if facts_path.stat().st_size > MAX_METADATA_FACTS_BYTES:
            return None
        text = facts_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None
    return parse_cm_metrics_facts(text)


def load_case_analysis_runtime_diagnosis_facts(case_dir: Path) -> dict[str, Any] | None:
    try:
        facts_path = (case_dir / "analysis_facts.md").resolve(strict=True)
        facts_path.relative_to(case_dir)
        if facts_path.stat().st_size > MAX_METADATA_FACTS_BYTES:
            return None
        text = facts_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None
    return parse_runtime_diagnosis_facts(text)


def load_batch_case_impala_context_facts(case_dir: Path) -> dict[str, Any] | None:
    for candidate in (
        case_dir / "impala_context.json",
        case_dir / "impala_context" / "impala_context.json",
    ):
        try:
            context_path = candidate.resolve(strict=True)
            context_path.relative_to(case_dir)
            if context_path.stat().st_size > MAX_METADATA_FACTS_BYTES:
                return None
            payload = json.loads(context_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        context = table_metadata_facts.context_from_payload(payload, context_path, case_dir)
        return convert_table_metadata_context_for_web(context)
    return None


def resolve_batch_case_dir(settings: WebSettings, case: dict[str, object]) -> Path | None:
    if settings.batch_summary is None:
        return None
    raw_case_dir = case.get("case_dir")
    if not isinstance(raw_case_dir, str) or not raw_case_dir:
        return None
    try:
        summary_root = settings.batch_summary.resolve(strict=True).parent
    except OSError:
        return None
    case_dir = Path(raw_case_dir)
    if not case_dir.is_absolute():
        case_dir = summary_root / case_dir
    try:
        resolved_case_dir = case_dir.resolve(strict=False)
        resolved_case_dir.relative_to(summary_root)
    except (OSError, ValueError):
        return None
    return resolved_case_dir


def convert_table_metadata_context_for_web(context: dict[str, Any]) -> dict[str, Any] | None:
    tables = context.get("tables")
    if not isinstance(tables, list):
        return None
    converted = [convert_table_metadata_table_for_web(table) for table in tables if isinstance(table, dict)]
    if not converted and not context:
        return None
    return {
        "summary": {
            "context file": context.get("context_file", "unknown"),
            "table metadata facts": context.get("table_metadata_facts", "unknown"),
            "tables requested": str(context.get("tables_requested", "unknown")),
            "read-only statements only": context.get("read_only_statements_only", "unknown"),
        },
        "tables": converted,
        "statement_counts": metadata_statement_counts(converted),
    }


def convert_table_metadata_table_for_web(table: dict[str, Any]) -> dict[str, Any]:
    return {
        "table": table.get("table", "unknown"),
        "object type": table.get("object_type", "unknown"),
        "statements": table.get("statements") if isinstance(table.get("statements"), dict) else {},
        "table stats row-count completeness": table.get("table_stats_row_count_completeness", "unknown"),
        "column stats columns observed": table.get("column_stats_columns_observed", "unknown"),
        "column stats missing/unknown markers": table.get("column_stats_missing_markers", "unknown"),
        "column stats completeness": table.get("column_stats_completeness", "unknown"),
        "file format": table.get("file_format", "unknown"),
        "partition columns": ", ".join(str(item) for item in table.get("partition_columns") or []) or "unknown",
    }


def parse_table_metadata_context_facts(text: str) -> dict[str, Any] | None:
    in_section = False
    summary: dict[str, str] = {}
    tables: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            in_section = line == "## Table Metadata Context"
            current = None
            continue
        if not in_section:
            continue
        if line.startswith("### "):
            table_name = parse_table_metadata_heading(line)
            if table_name:
                current = {"table": table_name, "statements": {}}
                tables.append(current)
            else:
                current = None
            continue
        if not line.startswith("- ") or ": " not in line:
            continue
        key, value = line[2:].split(": ", 1)
        key = key.strip()
        value = clean_metadata_fact_value(value)
        key_lower = key.lower()
        if key_lower in TABLE_METADATA_TABLE_KEYS_START:
            if value:
                current = {"table": value, "statements": {}}
                tables.append(current)
            continue
        if current is None:
            if key_lower in TABLE_METADATA_SUMMARY_KEYS:
                summary[TABLE_METADATA_SUMMARY_KEYS[key_lower]] = value
            continue
        statement = parse_table_metadata_statement_status_key(key)
        if statement:
            current.setdefault("statements", {})[statement] = value
        elif key_lower in TABLE_METADATA_TABLE_KEYS:
            current[TABLE_METADATA_TABLE_KEYS[key_lower]] = value
    if not summary and not tables:
        return None
    return {
        "summary": summary,
        "tables": tables,
        "statement_counts": metadata_statement_counts(tables),
    }


CM_METRIC_SIGNAL_LABELS = {
    "host_cpu_pressure": "Host CPU pressure",
    "daemon_memory_growth": "Daemon memory growth",
    "daemon_memory_pressure": "Daemon memory pressure",
    "network_io_spike": "Network I/O spike",
}


def parse_cm_metrics_facts(text: str) -> dict[str, Any] | None:
    section = ""
    in_limitations = False
    summary: dict[str, str] = {}
    correlation_summary: dict[str, str] = {}
    signal_values: dict[str, dict[str, str]] = {
        key: {"label": label}
        for key, label in CM_METRIC_SIGNAL_LABELS.items()
    }
    correlation_values: dict[str, dict[str, str]] = {
        key: {"label": label}
        for key, label in CM_METRIC_SIGNAL_LABELS.items()
    }
    current_correlation_key = ""
    limitations: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            if line == "## CM Metrics Facts":
                section = "facts"
            elif line == "## CM Metrics Correlation":
                section = "correlation"
            else:
                section = ""
            in_limitations = False
            current_correlation_key = ""
            continue
        if not section:
            continue
        if line.startswith("### "):
            in_limitations = section == "facts" and line == "### CM metrics limitations"
            continue
        if not line.startswith("- "):
            continue
        bullet = line[2:].strip()
        if section == "facts" and in_limitations:
            if bullet:
                limitations.append(clean_metadata_fact_value(bullet))
            continue
        if ": " not in bullet:
            continue
        key, value = bullet.split(": ", 1)
        key = key.strip()
        value = clean_metadata_fact_value(value)
        if section == "facts" and key in {"status", "coverage"}:
            summary[key] = value
            continue
        if section == "facts" and key.endswith("_basis"):
            signal_key = key.removesuffix("_basis")
            if signal_key in signal_values:
                signal_values[signal_key]["basis"] = value
            continue
        if section == "facts" and key in signal_values:
            signal_values[key]["status"] = value
            continue
        if section == "correlation" and key in {"status", "coverage", "correlated_signals", "context_only_signals", "guardrail"}:
            correlation_summary[key] = value
            current_correlation_key = ""
            continue
        if section == "correlation" and key in correlation_values:
            status, _, rest = value.partition(" ")
            correlation_values[key]["status"] = clean_metadata_fact_value(status)
            match = re.search(r"metric=([^,\s)]+)", rest)
            if match:
                correlation_values[key]["metric_status"] = clean_metadata_fact_value(match.group(1))
            match = re.search(r"strength=([^,\s)]+)", rest)
            if match:
                correlation_values[key]["strength"] = clean_metadata_fact_value(match.group(1))
            current_correlation_key = key
            continue
        if section == "correlation" and current_correlation_key and key in {"basis", "interpretation"}:
            correlation_values[current_correlation_key][key] = value
    signals = [
        signal
        for signal in signal_values.values()
        if signal.get("status") or signal.get("basis")
    ]
    correlations = [
        correlation
        for correlation in correlation_values.values()
        if correlation.get("status") or correlation.get("interpretation")
    ]
    if not summary and not signals and not limitations and not correlation_summary and not correlations:
        return None
    return {
        "summary": summary,
        "signals": signals,
        "correlation_summary": correlation_summary,
        "correlations": correlations,
        "limitations": limitations[:5],
    }


def parse_runtime_diagnosis_facts(text: str) -> dict[str, Any] | None:
    section = ""
    summary: dict[str, str] = {}
    signals: list[dict[str, Any]] = []
    current_signal: dict[str, Any] | None = None
    in_evidence = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            section = "runtime_diagnosis" if line == "## Runtime Diagnosis" else ""
            current_signal = None
            in_evidence = False
            continue
        if not section:
            continue
        if line.startswith("### "):
            title = clean_metadata_fact_value(line.removeprefix("###").strip())
            current_signal = {"title": title, "evidence": []}
            signals.append(current_signal)
            in_evidence = False
            continue
        if not line.startswith("- "):
            continue
        bullet = line[2:].strip()
        if current_signal is not None and in_evidence and bullet:
            current_signal.setdefault("evidence", []).append(clean_metadata_fact_value(bullet))
            continue
        if ": " not in bullet:
            continue
        key, value = bullet.split(": ", 1)
        key = key.strip()
        value = clean_metadata_fact_value(value)
        if current_signal is None:
            if key in {"status", "summary", "guardrail"}:
                summary[key] = value
            continue
        if key == "evidence":
            in_evidence = True
            if value and value != "none":
                current_signal.setdefault("evidence", []).append(value)
            continue
        if key in {"status", "interpretation"}:
            current_signal[key] = value
            in_evidence = False
    if not summary and not signals:
        return None
    return {
        "status": summary.get("status", "unknown"),
        "summary": summary.get("summary", "unknown"),
        "guardrail": summary.get("guardrail", ""),
        "signals": signals,
    }


def parse_table_metadata_heading(line: str) -> str:
    heading = line.removeprefix("###").strip()
    if heading.lower().startswith("table:"):
        return heading.split(":", 1)[1].strip()
    return ""


def parse_table_metadata_statement_status_key(key: str) -> str:
    key_upper = key.upper()
    if not key_upper.endswith(" STATUS"):
        return ""
    statement = key_upper.removesuffix(" STATUS").strip()
    return statement if statement in table_metadata_facts.STATEMENTS else ""


def clean_metadata_fact_value(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text.startswith("`") and text.endswith("`"):
        return text[1:-1]
    return text


def metadata_statement_counts(tables: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in tables:
        statements = table.get("statements")
        if not isinstance(statements, dict):
            continue
        for status in statements.values():
            key = str(status or "unknown")
            counts[key] = counts.get(key, 0) + 1
    return counts


def make_handler(
    settings: WebSettings,
    analysis_func: AnalysisFunc = run_query_id_analysis,
    job_store: WebJobStore | None = None,
    runner: Runner = subprocess.run,
) -> type[BaseHTTPRequestHandler]:
    store = job_store or WebJobStore()

    class QueryDoctorWebHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html", "/batch"}:
                query = parse_qs(parsed.query, keep_blank_values=True)
                self.write_html(
                    200,
                    render_batch_page(
                        batch_page_settings(settings, store),
                        query_group=first_form_value(query, "query_group"),
                        only_with_spills=form_flag_enabled(query, "only_with_spills"),
                    ),
                )
                return
            match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)/report", parsed.path)
            if match:
                case_id = match.group("case_id")
                effective_settings, case = resolve_case_detail_settings(settings, store, case_id)
                if case is None:
                    self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                    return
                report_text = load_validated_batch_case_report(effective_settings, case)
                if report_text is None:
                    self.write_html(404, render_batch_case_detail_for_request(effective_settings, case_id, case, store))
                    return
                self.write_html(200, render_batch_case_report_page(effective_settings, case_id, case, report_text))
                return
            match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)/optimized-query", parsed.path)
            if match:
                case_id = match.group("case_id")
                effective_settings, case = resolve_case_detail_settings(settings, store, case_id)
                if case is None:
                    self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                    return
                self.write_html(200, render_batch_case_detail_for_request(effective_settings, case_id, case, store))
                return
            match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)", parsed.path)
            if match:
                case_id = match.group("case_id")
                effective_settings, case = resolve_case_detail_settings(settings, store, case_id)
                if case is None:
                    self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                    return
                self.write_html(200, render_batch_case_detail_for_request(effective_settings, case_id, case, store))
                return
            match = re.fullmatch(r"/running/case/(?P<case_id>[^/]+)/report", parsed.path)
            if match:
                case_id = match.group("case_id")
                effective_settings, case = resolve_running_case_detail_settings(settings, store, case_id)
                if case is None:
                    self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                    return
                report_text = load_validated_batch_case_report(effective_settings, case)
                if report_text is None:
                    self.write_html(404, render_batch_case_detail_for_request(effective_settings, case_id, case, store, **running_detail_kwargs()))
                    return
                self.write_html(200, render_batch_case_report_page(effective_settings, case_id, case, report_text))
                return
            match = re.fullmatch(r"/running/case/(?P<case_id>[^/]+)/optimized-query", parsed.path)
            if match:
                case_id = match.group("case_id")
                effective_settings, case = resolve_running_case_detail_settings(settings, store, case_id)
                if case is None:
                    self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                    return
                self.write_html(200, render_batch_case_detail_for_request(effective_settings, case_id, case, store, **running_detail_kwargs()))
                return
            match = re.fullmatch(r"/running/case/(?P<case_id>[^/]+)", parsed.path)
            if match:
                case_id = match.group("case_id")
                effective_settings, case = resolve_running_case_detail_settings(settings, store, case_id)
                if case is None:
                    self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                    return
                self.write_html(200, render_batch_case_detail_for_request(effective_settings, case_id, case, store, **running_detail_kwargs()))
                return
            match = re.fullmatch(r"/query/details/(?P<query_id>[^/]+)/report", parsed.path)
            if match:
                status, body = render_specific_query_report_for_request(settings, unquote(match.group("query_id")))
                self.write_html(status, body)
                return
            match = re.fullmatch(r"/query/details/(?P<query_id>[^/]+)/optimized-query", parsed.path)
            if match:
                status, body = render_specific_query_detail_for_request(settings, unquote(match.group("query_id")), store)
                self.write_html(status, body)
                return
            match = re.fullmatch(r"/query/details/(?P<query_id>[^/]+)", parsed.path)
            if match:
                status, body = render_specific_query_detail_for_request(settings, unquote(match.group("query_id")), store)
                self.write_html(status, body)
                return
            if parsed.path in {"/query", "/run"}:
                self.write_html(200, render_query_page(settings))
                return
            if parsed.path in {"/optimizer", "/query-optimizer"}:
                self.write_html(200, render_optimizer_page(settings))
                return
            if parsed.path in {"/running", "/running-queries"}:
                query = parse_qs(parsed.query, keep_blank_values=True)
                self.write_html(
                    200,
                    render_running_queries_page(
                        running_page_settings(settings, store),
                        query_group=first_form_value(query, "query_group"),
                        only_with_spills=form_flag_enabled(query, "only_with_spills"),
                    ),
                )
                return
            if parsed.path == "/help":
                self.write_html(200, render_help_page(settings))
                return
            if parsed.path in {"/demo", "/demo-guide"}:
                self.write_html(200, render_demo_guide_page(settings))
                return
            if parsed.path == "/readme":
                self.write_html(200, render_readme_page(settings))
                return
            match = re.fullmatch(r"/jobs/(?P<job_id>[0-9a-f]{32})", parsed.path)
            if match:
                job = store.get(match.group("job_id"))
                if job is None:
                    self.write_html(
                        404,
                        render_batch_page(
                            batch_page_settings(settings, store),
                            error="Analysis job was not found.",
                        ),
                    )
                    return
                if job.kind == "batch":
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    self.write_html(
                        200,
                        render_batch_page(
                            batch_page_settings(settings, store),
                            job=job,
                            query_group=first_form_value(query, "query_group"),
                            only_with_spills=form_flag_enabled(query, "only_with_spills"),
                        ),
                    )
                elif job.kind == "running":
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    self.write_html(
                        200,
                        render_running_queries_page(
                            running_page_settings(settings, store),
                            job=job,
                            query_group=first_form_value(query, "query_group"),
                            only_with_spills=form_flag_enabled(query, "only_with_spills"),
                        ),
                    )
                elif job.kind in {"batch_report", "batch_llm_actions"}:
                    case_id = job.batch_case_id or job.query_id
                    if job.batch_source == "running":
                        effective_settings, case = resolve_running_case_detail_settings(settings, store, case_id)
                        detail_kwargs = running_detail_kwargs()
                    else:
                        effective_settings, case = resolve_case_detail_settings(settings, store, case_id)
                        detail_kwargs = {}
                    if case is None:
                        self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                        return
                    self.write_html(200, render_batch_case_detail_for_request(effective_settings, case_id, case, store, job=job, **detail_kwargs))
                elif job.kind in {"query_report", "query_llm_actions"}:
                    status, body = render_specific_query_detail_for_request(settings, job.query_id, store, job=job)
                    self.write_html(status, body)
                elif job.kind == "batch_optimized_query":
                    case_id = job.batch_case_id or job.query_id
                    if job.batch_source == "running":
                        effective_settings, case = resolve_running_case_detail_settings(settings, store, case_id)
                        detail_kwargs = running_detail_kwargs()
                    else:
                        effective_settings, case = resolve_case_detail_settings(settings, store, case_id)
                        detail_kwargs = {}
                    if case is None:
                        self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                        return
                    self.write_html(200, render_batch_case_detail_for_request(effective_settings, case_id, case, store, job=job, **detail_kwargs))
                elif job.kind == "query_optimized_query":
                    status, body = render_specific_query_detail_for_request(settings, job.query_id, store, job=job)
                    self.write_html(status, body)
                else:
                    self.write_html(200, render_query_page(settings, report_mode=job.report_mode, job=job))
                return
            match = re.fullmatch(r"/jobs/(?P<job_id>[0-9a-f]{32})/status", parsed.path)
            if match:
                job = store.get(match.group("job_id"))
                if job is None:
                    self.write_json(404, render_job_status_json(None))
                    return
                self.write_json(200, render_job_status_json(job))
                return
            self.send_error(404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            report_match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)/report", parsed.path)
            optimized_query_match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)/optimized-query", parsed.path)
            validate_rewrite_match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)/validate-rewrite", parsed.path)
            llm_actions_match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)/llm-actions", parsed.path)
            running_report_match = re.fullmatch(r"/running/case/(?P<case_id>[^/]+)/report", parsed.path)
            running_optimized_query_match = re.fullmatch(r"/running/case/(?P<case_id>[^/]+)/optimized-query", parsed.path)
            running_validate_rewrite_match = re.fullmatch(r"/running/case/(?P<case_id>[^/]+)/validate-rewrite", parsed.path)
            running_llm_actions_match = re.fullmatch(r"/running/case/(?P<case_id>[^/]+)/llm-actions", parsed.path)
            query_report_match = re.fullmatch(r"/query/details/(?P<query_id>[^/]+)/report", parsed.path)
            query_optimized_query_match = re.fullmatch(r"/query/details/(?P<query_id>[^/]+)/optimized-query", parsed.path)
            query_validate_rewrite_match = re.fullmatch(r"/query/details/(?P<query_id>[^/]+)/validate-rewrite", parsed.path)
            query_llm_actions_match = re.fullmatch(r"/query/details/(?P<query_id>[^/]+)/llm-actions", parsed.path)
            if (
                parsed.path not in {"/analyze", "/batch/run", "/running/run", "/optimizer", "/query-optimizer"}
                and report_match is None
                and optimized_query_match is None
                and validate_rewrite_match is None
                and llm_actions_match is None
                and running_report_match is None
                and running_optimized_query_match is None
                and running_validate_rewrite_match is None
                and running_llm_actions_match is None
                and query_report_match is None
                and query_optimized_query_match is None
                and query_validate_rewrite_match is None
                and query_llm_actions_match is None
            ):
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(min(length, MAX_WEB_POST_BODY_BYTES + 1)).decode("utf-8", errors="replace")
            if length > MAX_WEB_POST_BODY_BYTES:
                self.write_html(413, render_page(settings, active_nav="batch", error=WebError("Submitted form exceeds the bounded web input limit.")))
                return
            form = parse_qs(raw_body, keep_blank_values=True)
            if report_match is not None:
                status, body = start_batch_case_report_job(report_match.group("case_id"), settings, store, runner=runner)
            elif optimized_query_match is not None:
                status, body = start_batch_case_optimized_query_job(optimized_query_match.group("case_id"), settings, store, runner=runner)
            elif validate_rewrite_match is not None:
                status, body = handle_batch_case_external_rewrite_validation(
                    validate_rewrite_match.group("case_id"),
                    settings,
                    store,
                    form,
                )
            elif llm_actions_match is not None:
                status, body = start_batch_case_llm_actions_job(llm_actions_match.group("case_id"), settings, store, runner=runner)
            elif running_report_match is not None:
                status, body = start_batch_case_report_job(
                    running_report_match.group("case_id"),
                    settings,
                    store,
                    runner=runner,
                    source="running",
                )
            elif running_optimized_query_match is not None:
                status, body = start_batch_case_optimized_query_job(
                    running_optimized_query_match.group("case_id"),
                    settings,
                    store,
                    runner=runner,
                    source="running",
                )
            elif running_validate_rewrite_match is not None:
                status, body = handle_batch_case_external_rewrite_validation(
                    running_validate_rewrite_match.group("case_id"),
                    settings,
                    store,
                    form,
                    source="running",
                )
            elif running_llm_actions_match is not None:
                status, body = start_batch_case_llm_actions_job(
                    running_llm_actions_match.group("case_id"),
                    settings,
                    store,
                    runner=runner,
                    source="running",
                )
            elif query_report_match is not None:
                status, body = start_specific_query_report_job(
                    unquote(query_report_match.group("query_id")),
                    settings,
                    store,
                    runner=runner,
                )
            elif query_optimized_query_match is not None:
                status, body = start_specific_query_optimized_query_job(
                    unquote(query_optimized_query_match.group("query_id")),
                    settings,
                    store,
                    runner=runner,
                )
            elif query_validate_rewrite_match is not None:
                status, body = handle_specific_query_external_rewrite_validation(
                    unquote(query_validate_rewrite_match.group("query_id")),
                    settings,
                    store,
                    form,
                )
            elif query_llm_actions_match is not None:
                status, body = start_specific_query_llm_actions_job(
                    unquote(query_llm_actions_match.group("query_id")),
                    settings,
                    store,
                    runner=runner,
                )
            elif parsed.path == "/batch/run":
                status, body = start_batch_job(form, settings, store, runner=runner)
            elif parsed.path == "/running/run":
                status, body = start_running_job(form, settings, store, runner=runner)
            elif parsed.path in {"/optimizer", "/query-optimizer"}:
                status, body = handle_optimizer_request(form, settings, runner=runner)
            else:
                status, body = start_analyze_job(form, settings, store, analysis_func=analysis_func)
            if status == 303:
                self.send_response(303)
                self.send_header("Location", body)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self.write_html(status, body)

        def write_html(self, status: int, body: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def write_json(self, status: int, body: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"[Query Doctor web] {self.address_string()} {fmt % args}", file=sys.stderr)

    return QueryDoctorWebHandler


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = build_web_settings(args, cwd=Path.cwd())
        validate_bind_host(settings.host, allow_nonlocal_web_bind=settings.allow_nonlocal_web_bind)
        startup_warnings = validate_web_startup_config(settings.config, cwd=Path.cwd())
    except WebError as exc:
        print(f"[Query Doctor web] ERROR: {exc}", file=sys.stderr)
        return 2
    except cm_collector.ConfigError as exc:
        print(f"[Query Doctor web] ERROR: {exc}", file=sys.stderr)
        return 2
    if settings.host not in LOCAL_BIND_HOSTS:
        print(
            "[Query Doctor web] WARNING: non-local bind requested for a local web server.",
            file=sys.stderr,
        )
    for warning in startup_warnings:
        print(f"[Query Doctor web] WARNING: {warning}", file=sys.stderr)

    handler = make_handler(settings)
    server = ThreadingHTTPServer((settings.host, settings.port), handler)
    print(f"[Query Doctor web] listening on http://{settings.host}:{settings.port}")
    print("[Query Doctor web] credentials and CM config are read only by local subprocesses; they are not shown in the UI.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Query Doctor web] stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
