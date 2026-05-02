#!/usr/bin/env python3
"""Local-only Query Doctor web server for explicit CM query ids."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

import query_doctor_collect_cm_profiles as cm_collector
from query_doctor_web_ui import (
    WEB_STAGES,
    render_batch_card,
    render_batch_case_detail_page,
    render_batch_case_not_found_page,
    render_batch_page,
    render_batch_progress_panel,
    render_page,
    render_query_page,
    render_readme_page,
    render_report_markdown_html,
    render_result,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_TIMEOUT_SEC = 1800
DEFAULT_MODEL = "qwen3-coder:30b"
DEFAULT_CORPUS_DIR = Path("cases/cm-corpus")
REPORT_VALIDATION_EXIT_CODE = 4
LOCAL_BIND_HOSTS = {"127.0.0.1", "localhost"}
OUTPUT_CASE_RE = re.compile(r"^Output case directory:\s*(?P<path>.+)$", re.MULTILINE)
COLLECTED_CASE_FILES = ("profile_digest.md", "cm_metadata.json", "collection_warnings.txt")
REPORT_VALIDATION_FAILURE_MESSAGE = (
    "Генерация отчёта завершилась, но детерминированный валидатор отклонил "
    "текст отчёта: он противоречил извлечённым фактам. Небезопасный отчёт "
    "не показан. Попробуйте повторить генерацию."
)
MISSING_CM_CREDENTIALS_MESSAGE = (
    "Не найдены учётные данные CM в окружении web server. Запустите сервер из "
    "терминала, где заданы CM_USERNAME/CM_PASSWORD или CM_TOKEN."
)
BATCH_STAGES = (
    (0, "Проверяем параметры batch triage", 4),
    (1, "Запускаем batch triage", 24),
    (2, "Читаем batch_summary.json", 86),
    (3, "Готово", 100),
)
BATCH_ORDER_VALUES = {"recent", "duration-desc", "duration-asc"}
BATCH_CM_INSPECT_LIMIT_MAX = 1000
BATCH_SELECT_LIMIT_MAX = 200
BATCH_JOBS_MAX = 100
BATCH_FULL_JOBS_MAX = 4
BATCH_ANALYSIS_DEPTH_VALUES = {"full", "fast"}
DEFAULT_METADATA_AUTH = "kerberos"
DEFAULT_METADATA_PROTOCOL = "beeswax"
DEFAULT_METADATA_TIMEOUT_SEC = 30


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
class BatchRunConfig:
    analysis_depth: str = "full"
    recent_window_minutes: int = 1440
    cm_inspect_limit: int = 1000
    select_limit: int = 200
    min_duration_sec: float = 10.0
    max_duration_sec: float | None = None
    order: str = "duration-desc"
    jobs: int = 4
    user: str = ""
    pool: str = ""
    query_type: str = "QUERY"
    include_failed: bool = False
    include_running: bool = False


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
        )


class WebJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, WebJob] = {}
        self._latest_batch_summary: Path | None = None
        self._lock = threading.Lock()

    def create(self, query_id: str, report_mode: str) -> WebJobSnapshot:
        stage = WEB_STAGES[0]
        job = WebJob(
            job_id=uuid.uuid4().hex,
            query_id=query_id,
            report_mode=report_mode,
            status="running",
            stage_label=stage[1],
            progress=stage[2],
        )
        with self._lock:
            self._jobs[job.job_id] = job
            return job.snapshot()

    def create_batch(self, form_values: dict[str, object] | None = None) -> WebJobSnapshot:
        stage = BATCH_STAGES[0]
        job_id = uuid.uuid4().hex
        job = WebJob(
            job_id=job_id,
            query_id="batch triage",
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

    def update_stage(self, job_id: str, stage_index: int) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "running":
                return
            stages = BATCH_STAGES if job.kind == "batch" else WEB_STAGES
            stage = stages[stage_index]
            job.stage_label = stage[1]
            job.progress = stage[2]

    def complete(self, job_id: str, result: WebResult) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "ok"
            job.stage_label = WEB_STAGES[-1][1]
            job.progress = WEB_STAGES[-1][2]
            job.result_html = "\n".join(render_result(result))
            job.error = ""

    def complete_html(self, job_id: str, result_html: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            stages = BATCH_STAGES if job.kind == "batch" else WEB_STAGES
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
            job.stage_label = "Ошибка"
            job.progress = 100
            job.error = sanitize_for_display(error)


AnalysisFunc = Callable[[str, str, bool, WebSettings], WebResult]
Runner = Callable[..., subprocess.CompletedProcess[str]]
ProgressFunc = Callable[[int], None]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the localhost-only Query Doctor web UI for batch triage and explicit CM query ids."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Local ignored CM collector JSON config. Credentials still come from environment.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Bind host. Default: {DEFAULT_HOST}.")
    parser.add_argument("--port", type=positive_int, default=DEFAULT_PORT)
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
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model. Default: {DEFAULT_MODEL}.")
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
    parser.add_argument("--metadata-coordinator", help="Impala coordinator HOST:PORT for web batch metadata.")
    parser.add_argument("--metadata-impala-shell", help="impala-shell executable for web batch metadata.")
    parser.add_argument("--metadata-auth", default=DEFAULT_METADATA_AUTH, help="Metadata auth mode. Default: kerberos.")
    parser.add_argument(
        "--metadata-protocol",
        choices=("beeswax", "hs2", "hs2-http"),
        default=DEFAULT_METADATA_PROTOCOL,
        help="impala-shell protocol for web batch metadata. Default: beeswax.",
    )
    parser.add_argument("--metadata-ssl", action="store_true", help="Pass --ssl to impala-shell metadata collection.")
    parser.add_argument("--metadata-ca-cert", help="CA certificate path for --metadata-ssl metadata connections.")
    parser.add_argument(
        "--metadata-timeout-sec",
        type=positive_int,
        default=DEFAULT_METADATA_TIMEOUT_SEC,
        help=f"Timeout per metadata statement. Default: {DEFAULT_METADATA_TIMEOUT_SEC}.",
    )
    parser.add_argument("--metadata-max-tables", type=positive_int, help="Maximum referenced tables to collect.")
    parser.add_argument("--metadata-max-output-bytes", type=positive_int, help="Maximum metadata output bytes.")
    parser.add_argument("--metadata-redact", action="store_true", help="Pass --metadata-redact to web batch runs.")
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
    text = str(value)
    for secret in (os.environ.get("CM_PASSWORD"), os.environ.get("CM_TOKEN")):
        if secret:
            text = text.replace(secret, "<secret>")
    text = cm_collector.AUTH_HEADER_RE.sub(r"\1<redacted>", text)
    text = cm_collector.BEARER_BASIC_RE.sub(r"\1 <redacted>", text)
    text = cm_collector.URL_CREDENTIAL_RE.sub(r"\1<redacted>@", text)
    text = cm_collector.SECRET_VALUE_RE.sub(r"\1\2\3<redacted>\4", text)
    return text[:1200]


def run_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    timeout_sec: int,
    runner: Runner,
) -> subprocess.CompletedProcess[str]:
    return runner(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )


def subprocess_failure_message(stage: str, completed: subprocess.CompletedProcess[str]) -> str:
    return (
        f"{stage} failed with exit code {completed.returncode}. "
        "Captured subprocess output is not shown because it may contain raw "
        "profile text, SQL, JSON, or credentials."
    )


def has_cm_credentials(env: dict[str, str] | os._Environ[str] | None = None) -> bool:
    env = os.environ if env is None else env
    token = (env.get("CM_TOKEN") or "").strip()
    username = (env.get("CM_USERNAME") or "").strip()
    password = (env.get("CM_PASSWORD") or "").strip()
    return bool(token) or (bool(username) and bool(password))


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

    update_progress(progress, 1)
    expected_case_dir = expected_case_dir_for_query(validated_query_id, settings)
    if expected_case_dir.exists():
        ensure_complete_existing_case(expected_case_dir)
        case_dir = expected_case_dir
        case_source = "reused existing local case"
    else:
        case_dir = collect_case(validated_query_id, expected_case_dir, redact_identifiers, settings, runner)
        case_source = "collected now"

    report_name = f"report_{report_mode}.md"
    update_progress(progress, 2)
    analyzed = run_subprocess(
        build_analyzer_command(case_dir, settings),
        cwd=settings.repo_dir,
        timeout_sec=settings.timeout_sec,
        runner=runner,
    )
    if analyzed.returncode != 0:
        raise WebError(subprocess_failure_message("Query Doctor analyzer", analyzed))

    update_progress(progress, 3)
    reported = run_subprocess(
        build_report_command(case_dir, report_mode, report_name, settings),
        cwd=settings.repo_dir,
        timeout_sec=settings.timeout_sec,
        runner=runner,
    )
    update_progress(progress, 4)
    report_retry = False
    if reported.returncode == REPORT_VALIDATION_EXIT_CODE:
        retried = run_subprocess(
            build_report_command(case_dir, report_mode, report_name, settings),
            cwd=settings.repo_dir,
            timeout_sec=settings.timeout_sec,
            runner=runner,
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
    ]


def collect_case(
    validated_query_id: str,
    expected_case_dir: Path,
    redact_identifiers: bool,
    settings: WebSettings,
    runner: Runner,
) -> Path:
    if not has_cm_credentials():
        raise WebError(MISSING_CM_CREDENTIALS_MESSAGE)

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
        str(settings.corpus_dir),
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
    )
    if collected.returncode != 0:
        raise WebError(subprocess_failure_message("CM single-query collection", collected))

    case_dir = parse_output_case_dir(collected.stdout)
    if not case_dir.is_absolute():
        case_dir = (settings.repo_dir / case_dir).resolve()
    expected_corpus_dir = resolve_under_repo(settings.repo_dir, settings.corpus_dir)
    try:
        case_dir.relative_to(expected_corpus_dir)
    except ValueError as exc:
        raise WebError("Collector returned a case directory outside the web corpus directory.") from exc
    if case_dir != expected_case_dir:
        raise WebError("Collector returned a case directory that does not match the requested query id.")
    if not case_dir.exists():
        raise WebError("Collector did not create the expected case directory.")
    return case_dir


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
            f"Existing web case path is not a directory: {case_dir}. "
            "Remove that specific path manually if you want to recollect."
        )
    missing = [name for name in COLLECTED_CASE_FILES if not (case_dir / name).is_file()]
    if missing:
        missing_list = ", ".join(missing)
        raise WebError(
            f"Local web case is incomplete or broken: {case_dir}. "
            f"Missing required file(s): {missing_list}. Remove or rebuild that specific case directory "
            "manually before trying to recollect."
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


def parse_batch_run_config(form: dict[str, list[str]]) -> BatchRunConfig:
    analysis_depth = first_form_value(form, "analysis_depth") or "full"
    if analysis_depth not in BATCH_ANALYSIS_DEPTH_VALUES:
        raise WebError("Analysis depth must be full or fast.")
    recent_window_minutes = parse_positive_form_int(form, "recent_window_minutes", default=1440)
    cm_inspect_limit = parse_positive_form_int(
        form, "cm_inspect_limit", default=1000, maximum=BATCH_CM_INSPECT_LIMIT_MAX
    )
    select_limit = parse_positive_form_int(form, "select_limit", default=200, maximum=BATCH_SELECT_LIMIT_MAX)
    min_duration_sec = parse_non_negative_form_float(form, "min_duration_sec", default=10.0)
    max_duration_text = first_form_value(form, "max_duration_sec")
    max_duration_sec = None
    if max_duration_text:
        max_duration_sec = parse_non_negative_form_float(form, "max_duration_sec", default=0.0)
        if max_duration_sec < min_duration_sec:
            raise WebError("max_duration_sec must be greater than or equal to min_duration_sec.")
    order = first_form_value(form, "order") or "duration-desc"
    if order not in BATCH_ORDER_VALUES:
        raise WebError("Order must be one of: recent, duration-desc, duration-asc.")
    jobs = parse_positive_form_int(form, "jobs", default=BATCH_FULL_JOBS_MAX, maximum=BATCH_JOBS_MAX)
    user = first_form_value(form, "user")
    pool = first_form_value(form, "pool")
    query_type = first_form_value(form, "query_type") or "QUERY"
    return BatchRunConfig(
        analysis_depth=analysis_depth,
        recent_window_minutes=recent_window_minutes,
        cm_inspect_limit=cm_inspect_limit,
        select_limit=select_limit,
        min_duration_sec=min_duration_sec,
        max_duration_sec=max_duration_sec,
        order=order,
        jobs=jobs,
        user=user,
        pool=pool,
        query_type=query_type,
        include_failed=first_form_value(form, "include_failed") == "on",
        include_running=first_form_value(form, "include_running") == "on",
    )


def validate_batch_config_for_settings(config: BatchRunConfig, settings: WebSettings) -> None:
    if config.analysis_depth == "full":
        if config.jobs > BATCH_FULL_JOBS_MAX:
            raise WebError("Full analysis collects Impala metadata and requires jobs <= 4. Use Fast triage for higher jobs.")
        if not metadata_configured(settings):
            raise WebError("Metadata collection is not configured for this web session. Use Fast triage or restart with metadata options.")
        if settings.metadata_ca_cert and not settings.metadata_ssl:
            raise WebError("--metadata-ca-cert requires --metadata-ssl for web batch metadata.")


def metadata_configured(settings: WebSettings) -> bool:
    return bool(settings.metadata_coordinator)


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


def build_batch_command(job_id: str, config: BatchRunConfig, settings: WebSettings) -> tuple[list[str], Path]:
    validate_batch_config_for_settings(config, settings)
    out_dir = batch_output_dir(job_id)
    progress_path = batch_progress_path(job_id)
    metadata_mode = "on" if config.analysis_depth == "full" else "off"
    cmd = [
        sys.executable,
        str(settings.repo_dir / "query_doctor_batch_recent.py"),
        "--config",
        str(settings.config),
        "--out",
        str(out_dir),
        "--recent-window-minutes",
        str(config.recent_window_minutes),
        "--cm-inspect-limit",
        str(config.cm_inspect_limit),
        "--select-limit",
        str(config.select_limit),
        "--min-duration-sec",
        display_float(config.min_duration_sec),
        "--order",
        config.order,
        "--metadata-mode",
        metadata_mode,
        "--top-reports",
        "0",
        "--jobs",
        str(config.jobs),
        "--overwrite",
        "--progress-jsonl",
        str(progress_path),
    ]
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
    if config.analysis_depth == "full":
        append_web_metadata_args(cmd, settings)
    elif config.jobs > BATCH_FULL_JOBS_MAX:
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
    analysis_func: AnalysisFunc = run_web_analysis,
) -> tuple[int, str]:
    query_id = first_form_value(form, "query_id")
    report_mode = first_form_value(form, "mode") or "user"
    redact_identifiers = first_form_value(form, "redact_identifiers") == "on"
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
    return 200, render_query_page(settings, query_id=query_id, report_mode=report_mode, result=result)


def start_analyze_job(
    form: dict[str, list[str]],
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    analysis_func: AnalysisFunc = run_web_analysis,
) -> tuple[int, str]:
    query_id = first_form_value(form, "query_id")
    report_mode = first_form_value(form, "mode") or "user"
    redact_identifiers = first_form_value(form, "redact_identifiers") == "on"
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
        config = parse_batch_run_config(form)
        validate_batch_config_for_settings(config, settings)
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


def form_values_from_form(form: dict[str, list[str]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for name in (
        "analysis_depth",
        "recent_window_minutes",
        "cm_inspect_limit",
        "select_limit",
        "min_duration_sec",
        "max_duration_sec",
        "order",
        "jobs",
        "user",
        "pool",
        "query_type",
    ):
        values[name] = first_form_value(form, name)
    values["include_failed"] = first_form_value(form, "include_failed") == "on"
    values["include_running"] = first_form_value(form, "include_running") == "on"
    return values


def form_values_from_config(config: BatchRunConfig) -> dict[str, object]:
    return {
        "analysis_depth": config.analysis_depth,
        "recent_window_minutes": str(config.recent_window_minutes),
        "cm_inspect_limit": str(config.cm_inspect_limit),
        "select_limit": str(config.select_limit),
        "min_duration_sec": display_float(config.min_duration_sec),
        "max_duration_sec": "" if config.max_duration_sec is None else display_float(config.max_duration_sec),
        "order": config.order,
        "jobs": str(config.jobs),
        "user": config.user,
        "pool": config.pool,
        "query_type": config.query_type,
        "include_failed": config.include_failed,
        "include_running": config.include_running,
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
        if analysis_func is run_web_analysis:
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
        )
        if completed.returncode != 0:
            raise WebError(subprocess_failure_message("Query Doctor batch triage", completed))
        job_store.update_stage(job_id, 2)
        summary_path = out_dir / "batch_summary.json"
        if not summary_path.is_file():
            raise WebError("Batch run completed but batch_summary.json was not created.")
        job_store.set_latest_batch_summary(summary_path)
        batch_settings = replace(settings, batch_summary=summary_path)
        job_store.complete_html(job_id, render_batch_card(batch_settings))
    except WebError as exc:
        job_store.fail(job_id, exc)
    except Exception:  # pragma: no cover - defensive UI sanitization.
        job_store.fail(job_id, "Unexpected batch triage failure. Details are hidden because they may contain sensitive data.")


def render_job_status_json(job: WebJobSnapshot | None) -> str:
    if job is None:
        payload = {
            "status": "failed",
            "stage": "Не найдено",
            "progress": 100,
            "error": "Analysis job was not found.",
            "result_html": "",
        }
    else:
        payload = {
            "status": job.status,
            "stage": job.stage_label,
            "progress": job.progress,
            "kind": job.kind,
            "error": job.error,
            "result_html": job.result_html,
            "progress_html": render_batch_progress_panel(job.batch_progress_path, job.status)
            if job.kind == "batch"
            else "",
        }
    return json.dumps(payload, ensure_ascii=False)


def first_form_value(form: dict[str, list[str]], name: str) -> str:
    values = form.get(name, [])
    if not values:
        return ""
    return values[0].strip()


def batch_page_settings(settings: WebSettings, job_store: WebJobStore) -> WebSettings:
    if settings.batch_summary is not None:
        return settings
    latest = job_store.latest_batch_summary()
    if latest is None:
        return settings
    return replace(settings, batch_summary=latest)


def load_batch_summary(settings: WebSettings) -> dict[str, object] | None:
    summary_path = settings.batch_summary
    if summary_path is None:
        return None
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


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


def make_handler(
    settings: WebSettings,
    analysis_func: AnalysisFunc = run_web_analysis,
    job_store: WebJobStore | None = None,
    runner: Runner = subprocess.run,
) -> type[BaseHTTPRequestHandler]:
    store = job_store or WebJobStore()

    class QueryDoctorWebHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html", "/batch"}:
                self.write_html(200, render_batch_page(batch_page_settings(settings, store)))
                return
            match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)", parsed.path)
            if match:
                case_id = match.group("case_id")
                effective_settings = batch_page_settings(settings, store)
                summary = load_batch_summary(effective_settings)
                case = find_batch_case(summary, case_id) if summary is not None else None
                if case is None:
                    self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                    return
                self.write_html(200, render_batch_case_detail_page(effective_settings, case_id, case))
                return
            if parsed.path in {"/query", "/run"}:
                self.write_html(200, render_query_page(settings))
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
                    self.write_html(200, render_batch_page(batch_page_settings(settings, store), job=job))
                else:
                    self.write_html(200, render_query_page(settings, query_id=job.query_id, report_mode=job.report_mode, job=job))
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
            if self.path not in {"/analyze", "/batch/run"}:
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(min(length, 65536)).decode("utf-8", errors="replace")
            form = parse_qs(raw_body, keep_blank_values=True)
            if self.path == "/batch/run":
                status, body = start_batch_job(form, settings, store, runner=runner)
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
        validate_bind_host(args.host, allow_nonlocal_web_bind=args.allow_nonlocal_web_bind)
    except WebError as exc:
        print(f"[Query Doctor web] ERROR: {exc}", file=sys.stderr)
        return 2
    if args.host not in LOCAL_BIND_HOSTS:
        print(
            "[Query Doctor web] WARNING: non-local bind requested for a local web server.",
            file=sys.stderr,
        )

    settings = WebSettings(
        config=Path(args.config).expanduser(),
        host=args.host,
        port=args.port,
        allow_nonlocal_web_bind=args.allow_nonlocal_web_bind,
        max_profile_bytes=args.max_profile_bytes,
        model=args.model,
        timeout_sec=args.timeout_sec,
        batch_summary=Path(args.batch_summary).expanduser() if args.batch_summary else None,
        metadata_coordinator=args.metadata_coordinator,
        metadata_impala_shell=args.metadata_impala_shell,
        metadata_auth=args.metadata_auth,
        metadata_protocol=args.metadata_protocol,
        metadata_ssl=args.metadata_ssl,
        metadata_ca_cert=args.metadata_ca_cert,
        metadata_timeout_sec=args.metadata_timeout_sec,
        metadata_max_tables=args.metadata_max_tables,
        metadata_max_output_bytes=args.metadata_max_output_bytes,
        metadata_redact=args.metadata_redact,
    )
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
