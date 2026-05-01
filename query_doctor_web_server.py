#!/usr/bin/env python3
"""Local-only Query Doctor web server for explicit CM query ids."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

import query_doctor_collect_cm_profiles as cm_collector
from query_doctor_web_ui import (
    WEB_STAGES,
    render_page,
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
class WebJobSnapshot:
    job_id: str
    query_id: str
    report_mode: str
    status: str
    stage_label: str
    progress: int
    result_html: str = ""
    error: str = ""


@dataclass
class WebJob:
    job_id: str
    query_id: str
    report_mode: str
    status: str
    stage_label: str
    progress: int
    result_html: str = ""
    error: str = ""

    def snapshot(self) -> WebJobSnapshot:
        return WebJobSnapshot(
            job_id=self.job_id,
            query_id=self.query_id,
            report_mode=self.report_mode,
            status=self.status,
            stage_label=self.stage_label,
            progress=self.progress,
            result_html=self.result_html,
            error=self.error,
        )


class WebJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, WebJob] = {}
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

    def get(self, job_id: str) -> WebJobSnapshot | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.snapshot() if job is not None else None

    def update_stage(self, job_id: str, stage_index: int) -> None:
        stage = WEB_STAGES[stage_index]
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "running":
                return
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

    def fail(self, job_id: str, error: object) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.error = sanitize_for_display(error)


AnalysisFunc = Callable[[str, str, bool, WebSettings], WebResult]
Runner = Callable[..., subprocess.CompletedProcess[str]]
ProgressFunc = Callable[[int], None]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a localhost-only Query Doctor local web UI for one explicit CM query id."
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
        return 400, render_page(settings, error="Query ID is required.")
    try:
        result = analysis_func(query_id, report_mode, redact_identifiers, settings)
    except WebError as exc:
        return 400, render_page(settings, query_id=query_id, report_mode=report_mode, error=sanitize_for_display(exc))
    return 200, render_page(settings, query_id=query_id, report_mode=report_mode, result=result)


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
        return 400, render_page(settings, error="Query ID is required.")

    job = job_store.create(query_id, report_mode)
    thread = threading.Thread(
        target=run_analysis_job,
        args=(job.job_id, query_id, report_mode, redact_identifiers, settings, job_store, analysis_func),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


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
            "error": job.error,
            "result_html": job.result_html,
        }
    return json.dumps(payload, ensure_ascii=False)


def first_form_value(form: dict[str, list[str]], name: str) -> str:
    values = form.get(name, [])
    if not values:
        return ""
    return values[0].strip()


def make_handler(
    settings: WebSettings,
    analysis_func: AnalysisFunc = run_web_analysis,
    job_store: WebJobStore | None = None,
) -> type[BaseHTTPRequestHandler]:
    store = job_store or WebJobStore()

    class QueryDoctorWebHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self.write_html(200, render_page(settings))
                return
            if parsed.path == "/readme":
                self.write_html(200, render_readme_page(settings))
                return
            match = re.fullmatch(r"/jobs/(?P<job_id>[0-9a-f]{32})", parsed.path)
            if match:
                job = store.get(match.group("job_id"))
                if job is None:
                    self.write_html(404, render_page(settings, error="Analysis job was not found."))
                    return
                self.write_html(200, render_page(settings, query_id=job.query_id, report_mode=job.report_mode, job=job))
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
            if self.path != "/analyze":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(min(length, 65536)).decode("utf-8", errors="replace")
            form = parse_qs(raw_body, keep_blank_values=True)
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
