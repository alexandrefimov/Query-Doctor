#!/usr/bin/env python3
"""Local-only Query Doctor web server for explicit CM query ids."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

import query_doctor_collect_cm_profiles as cm_collector
import table_metadata_facts
from query_doctor_web_ui import (
    WEB_STAGES,
    render_batch_card,
    render_batch_case_detail_page,
    render_batch_case_not_found_page,
    render_batch_case_report_page,
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
BATCH_REPORT_STAGES = (
    (0, "Проверяем выбранный batch case", 8),
    (1, "Генерируем валидированный отчёт", 62),
    (2, "Проверяем результат", 88),
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
MAX_METADATA_FACTS_BYTES = 512 * 1024
BATCH_REPORT_NAME = "diagnosis.md"
BATCH_REPORT_PARTIAL_NAME = "diagnosis.partial.md"
BATCH_REPORT_VALIDATION_MARKER = "diagnosis.validated.json"
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
class BatchRunConfig:
    analysis_depth: str = "full"
    recent_window_minutes: int = 1440
    cm_inspect_limit: int = 1000
    triage_profile_limit: int = 200
    metadata_top_limit: int = 8
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
    batch_case_id: str | None = None


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

    def create_batch_report(self, case_id: str) -> WebJobSnapshot:
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
        )
        with self._lock:
            self._jobs[job.job_id] = job
            return job.snapshot()

    def running_batch_report(self, case_id: str) -> WebJobSnapshot | None:
        with self._lock:
            for job in self._jobs.values():
                if job.kind == "batch_report" and job.batch_case_id == case_id and job.status == "running":
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

    def update_stage(self, job_id: str, stage_index: int) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "running":
                return
            stages = stages_for_job_kind(job.kind)
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
            job.stage_label = "Ошибка"
            job.progress = 100
            job.error = sanitize_for_display(error)


def stages_for_job_kind(kind: str) -> tuple[tuple[int, str, int], ...]:
    if kind == "batch":
        return BATCH_STAGES
    if kind == "batch_report":
        return BATCH_REPORT_STAGES
    return WEB_STAGES


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
    parser.add_argument(
        "--metadata-auth",
        help="Metadata auth mode. Default comes from config or kerberos.",
    )
    parser.add_argument(
        "--metadata-protocol",
        choices=("beeswax", "hs2", "hs2-http"),
        help="impala-shell protocol for web batch metadata. Default comes from config or beeswax.",
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
    effective = dict(os.environ if base_env is None else base_env)
    if not effective.get("KRB5CCNAME") and settings.krb5ccname:
        effective["KRB5CCNAME"] = settings.krb5ccname
    return effective


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
        raise WebError("Metadata collection is not configured for this web session. Use Fast triage or restart with metadata options.")
    if not resolve_metadata_impala_shell(settings, env):
        raise WebError("Metadata preflight failed: impala-shell executable is not available. Use Fast triage or fix server metadata settings.")
    krb5ccname = env.get("KRB5CCNAME", "")
    if krb5ccname and any(ord(ch) < 32 or ord(ch) == 127 for ch in krb5ccname):
        raise WebError("Metadata preflight failed: Kerberos cache setting is invalid. Use Fast triage or fix server environment.")
    try:
        completed = run_subprocess(
            ["klist"],
            cwd=settings.repo_dir,
            timeout_sec=min(settings.timeout_sec, 30),
            runner=runner,
            env=env,
        )
    except OSError as exc:
        raise WebError("Metadata preflight failed: klist is not available. Use Fast triage or fix server Kerberos setup.") from exc
    if completed.returncode != 0:
        raise WebError(
            "Metadata preflight failed: Kerberos cache is not available or expired. "
            "Renew the Kerberos ticket or use Fast triage."
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
    ]


def collect_case(
    validated_query_id: str,
    expected_case_dir: Path,
    redact_identifiers: bool,
    settings: WebSettings,
    runner: Runner,
    env: dict[str, str] | None = None,
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
        env=effective_subprocess_env(settings) if env is None else env,
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


def parse_batch_run_config(form: dict[str, list[str]], *, default_analysis_depth: str = "full") -> BatchRunConfig:
    analysis_depth = first_form_value(form, "analysis_depth") or default_analysis_depth
    if analysis_depth not in BATCH_ANALYSIS_DEPTH_VALUES:
        raise WebError("Analysis depth must be full or fast.")
    recent_window_minutes = parse_positive_form_int(form, "recent_window_minutes", default=1440)
    cm_inspect_limit = parse_positive_form_int(
        form, "cm_inspect_limit", default=1000, maximum=BATCH_CM_INSPECT_LIMIT_MAX
    )
    triage_profile_limit = parse_positive_form_int(
        form, "triage_profile_limit", default=200, maximum=BATCH_SELECT_LIMIT_MAX
    )
    metadata_top_limit = parse_non_negative_form_int(
        form, "metadata_top_limit", default=8, maximum=BATCH_SELECT_LIMIT_MAX
    )
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
        triage_profile_limit=triage_profile_limit,
        metadata_top_limit=metadata_top_limit,
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


def load_web_local_config(config_path: Path, *, cwd: Path) -> dict[str, object]:
    path = config_path.expanduser()
    if not path.is_absolute():
        path = cwd / path
    if not path.is_file():
        return {}
    return cm_collector.load_local_config(str(path), cwd=cwd)


def load_krb5ccname_from_local_config(config_path: Path, *, cwd: Path) -> str | None:
    values = load_web_local_config(config_path, cwd=cwd)
    value = values.get("krb5ccname")
    return value if isinstance(value, str) else None


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
    config_path = Path(args.config).expanduser()
    config_values = load_web_local_config(config_path, cwd=cwd)
    return WebSettings(
        config=config_path,
        host=args.host,
        port=args.port,
        allow_nonlocal_web_bind=args.allow_nonlocal_web_bind,
        max_profile_bytes=args.max_profile_bytes,
        model=args.model,
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
        "--triage-profile-limit",
        str(config.triage_profile_limit),
        "--metadata-top-limit",
        str(config.metadata_top_limit if config.analysis_depth == "full" else 0),
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
        default_depth = "full" if metadata_configured(settings) else "fast"
        config = parse_batch_run_config(form, default_analysis_depth=default_depth)
        validate_batch_config_for_settings(config, settings)
        if config.analysis_depth == "full":
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


def start_batch_case_report_job(
    case_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
) -> tuple[int, str]:
    effective_settings = batch_page_settings(settings, job_store)
    summary = load_batch_summary(effective_settings)
    case = find_batch_case(summary, case_id) if summary is not None else None
    if case is None:
        return 404, render_batch_case_not_found_page(effective_settings, case_id)
    if job_store.running_batch_report(case_id) is not None:
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store)
    case_dir = resolve_batch_case_report_dir(effective_settings, case)
    if case_dir is None:
        metadata_facts = load_batch_case_metadata_facts(effective_settings, case)
        report_state = {
            "status": "failed",
            "running": False,
            "trusted": False,
            "partial": False,
            "error": "Report generation requires a resolved server-owned case directory with profile_digest.md.",
        }
        return 400, render_batch_case_detail_page(effective_settings, case_id, case, metadata_facts, report_state=report_state)

    job = job_store.create_batch_report(case_id)
    thread = threading.Thread(
        target=run_batch_case_report_job,
        args=(job.job_id, case_id, case_dir, settings, job_store, runner),
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
        "triage_profile_limit",
        "metadata_top_limit",
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
        "triage_profile_limit": str(config.triage_profile_limit),
        "metadata_top_limit": str(config.metadata_top_limit),
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
            env=effective_subprocess_env(settings),
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
                "diagnosis.partial.md is untrusted and hidden."
            )
        if completed.returncode != 0:
            raise WebError(subprocess_failure_message("Query Doctor batch case report generation", completed))
        report_path = case_dir / BATCH_REPORT_NAME
        if not report_path.is_file():
            raise WebError("Report generation completed but diagnosis.md was not created.")
        write_batch_case_report_validation_marker(case_dir)
        job_store.complete_html(job_id, f"Validated report generated for {case_id}.")
    except WebError as exc:
        job_store.fail(job_id, exc)
    except Exception:  # pragma: no cover - defensive UI sanitization.
        job_store.fail(job_id, "Unexpected report generation failure. Details are hidden because they may contain sensitive data.")


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


def render_batch_case_detail_for_request(
    settings: WebSettings,
    case_id: str,
    case: dict[str, object],
    job_store: WebJobStore,
    *,
    job: WebJobSnapshot | None = None,
) -> str:
    metadata_facts = load_batch_case_metadata_facts(settings, case)
    report_state = load_batch_case_report_state(settings, case_id, case, job_store, job=job)
    return render_batch_case_detail_page(settings, case_id, case, metadata_facts, report_state=report_state)


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


def load_batch_case_report_state(
    settings: WebSettings,
    case_id: str,
    case: dict[str, object],
    job_store: WebJobStore,
    *,
    job: WebJobSnapshot | None = None,
) -> dict[str, object]:
    running_job = job if job is not None and job.status == "running" else job_store.running_batch_report(case_id)
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
    elif job is not None and job.status == "failed":
        status = "failed"
    return {
        "status": status,
        "running": running_job is not None,
        "trusted": trusted,
        "partial": partial,
        "error": job.error if job is not None and job.status == "failed" else "",
    }


def resolve_batch_case_report_dir(settings: WebSettings, case: dict[str, object]) -> Path | None:
    case_dir = resolve_batch_case_dir(settings, case)
    if case_dir is None:
        return None
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        if (artifact_dir / "profile_digest.md").is_file():
            return artifact_dir
    return None


def batch_case_validated_report_exists(case_dir: Path, case: dict[str, object] | None = None) -> bool:
    if not (case_dir / BATCH_REPORT_NAME).is_file():
        return False
    if (case_dir / BATCH_REPORT_VALIDATION_MARKER).is_file():
        return True
    if case is None:
        return False
    return case.get("report_generated") is True and str(case.get("report_validation_status") or "") == "passed"


def write_batch_case_report_validation_marker(case_dir: Path) -> None:
    marker = {
        "report": BATCH_REPORT_NAME,
        "validated": True,
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
            match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)/report", parsed.path)
            if match:
                case_id = match.group("case_id")
                effective_settings = batch_page_settings(settings, store)
                summary = load_batch_summary(effective_settings)
                case = find_batch_case(summary, case_id) if summary is not None else None
                if case is None:
                    self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                    return
                report_text = load_validated_batch_case_report(effective_settings, case)
                if report_text is None:
                    self.write_html(404, render_batch_case_detail_for_request(effective_settings, case_id, case, store))
                    return
                self.write_html(200, render_batch_case_report_page(effective_settings, case_id, case, report_text))
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
                self.write_html(200, render_batch_case_detail_for_request(effective_settings, case_id, case, store))
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
                elif job.kind == "batch_report":
                    effective_settings = batch_page_settings(settings, store)
                    case_id = job.batch_case_id or job.query_id
                    summary = load_batch_summary(effective_settings)
                    case = find_batch_case(summary, case_id) if summary is not None else None
                    if case is None:
                        self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                        return
                    self.write_html(200, render_batch_case_detail_for_request(effective_settings, case_id, case, store, job=job))
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
            parsed = urlparse(self.path)
            report_match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)/report", parsed.path)
            if parsed.path not in {"/analyze", "/batch/run"} and report_match is None:
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(min(length, 65536)).decode("utf-8", errors="replace")
            form = parse_qs(raw_body, keep_blank_values=True)
            if report_match is not None:
                status, body = start_batch_case_report_job(report_match.group("case_id"), settings, store, runner=runner)
            elif parsed.path == "/batch/run":
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
        settings = build_web_settings(args, cwd=Path.cwd())
    except WebError as exc:
        print(f"[Query Doctor web] ERROR: {exc}", file=sys.stderr)
        return 2
    except cm_collector.ConfigError as exc:
        print(f"[Query Doctor web] ERROR: {exc}", file=sys.stderr)
        return 2
    if args.host not in LOCAL_BIND_HOSTS:
        print(
            "[Query Doctor web] WARNING: non-local bind requested for a local web server.",
            file=sys.stderr,
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
