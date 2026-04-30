#!/usr/bin/env python3
"""Local-only Query Doctor demo server for explicit CM query ids."""

from __future__ import annotations

import argparse
import html
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


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_TIMEOUT_SEC = 1800
DEFAULT_MODEL = "qwen3-coder:30b"
DEFAULT_CORPUS_DIR = Path("cases/cm-corpus")
REPORT_VALIDATION_EXIT_CODE = 4
LOCAL_BIND_HOSTS = {"127.0.0.1", "localhost"}
OUTPUT_CASE_RE = re.compile(r"^Output case directory:\s*(?P<path>.+)$", re.MULTILINE)
COLLECTED_CASE_FILES = ("profile_digest.md", "cm_metadata.json", "collection_warnings.txt")
DEMO_STAGES = (
    (0, "Проверяем Query ID", 4),
    (1, "Собираем или переиспользуем профиль", 24),
    (2, "Анализируем профиль", 50),
    (3, "Генерируем отчёт", 74),
    (4, "Проверяем отчёт", 90),
    (5, "Готово", 100),
)
REPORT_VALIDATION_FAILURE_MESSAGE = (
    "Генерация отчёта завершилась, но детерминированный валидатор отклонил "
    "текст отчёта: он противоречил извлечённым фактам. Небезопасный отчёт "
    "не показан. Попробуйте повторить генерацию."
)
MISSING_CM_CREDENTIALS_MESSAGE = (
    "Не найдены учётные данные CM в окружении demo server. Запустите сервер из "
    "терминала, где заданы CM_USERNAME/CM_PASSWORD или CM_TOKEN."
)


class DemoError(RuntimeError):
    """User-facing demo error that must not contain secrets or raw profiles."""


@dataclass(frozen=True)
class DemoSettings:
    config: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    allow_nonlocal_demo_bind: bool = False
    max_profile_bytes: int | None = None
    model: str = DEFAULT_MODEL
    timeout_sec: int = DEFAULT_TIMEOUT_SEC
    repo_dir: Path = Path(__file__).resolve().parent
    corpus_dir: Path = DEFAULT_CORPUS_DIR


@dataclass(frozen=True)
class DemoResult:
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
class DemoJobSnapshot:
    job_id: str
    query_id: str
    report_mode: str
    status: str
    stage_label: str
    progress: int
    result_html: str = ""
    error: str = ""


@dataclass
class DemoJob:
    job_id: str
    query_id: str
    report_mode: str
    status: str
    stage_label: str
    progress: int
    result_html: str = ""
    error: str = ""

    def snapshot(self) -> DemoJobSnapshot:
        return DemoJobSnapshot(
            job_id=self.job_id,
            query_id=self.query_id,
            report_mode=self.report_mode,
            status=self.status,
            stage_label=self.stage_label,
            progress=self.progress,
            result_html=self.result_html,
            error=self.error,
        )


class DemoJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, DemoJob] = {}
        self._lock = threading.Lock()

    def create(self, query_id: str, report_mode: str) -> DemoJobSnapshot:
        stage = DEMO_STAGES[0]
        job = DemoJob(
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

    def get(self, job_id: str) -> DemoJobSnapshot | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.snapshot() if job is not None else None

    def update_stage(self, job_id: str, stage_index: int) -> None:
        stage = DEMO_STAGES[stage_index]
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "running":
                return
            job.stage_label = stage[1]
            job.progress = stage[2]

    def complete(self, job_id: str, result: DemoResult) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "ok"
            job.stage_label = DEMO_STAGES[-1][1]
            job.progress = DEMO_STAGES[-1][2]
            job.result_html = "\n".join(render_result(result))
            job.error = ""

    def fail(self, job_id: str, error: object) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.error = sanitize_for_display(error)


AnalysisFunc = Callable[[str, str, bool, DemoSettings], DemoResult]
Runner = Callable[..., subprocess.CompletedProcess[str]]
ProgressFunc = Callable[[int], None]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a localhost-only Query Doctor demo for one explicit CM query id."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Local ignored CM collector JSON config. Credentials still come from environment.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Bind host. Default: {DEFAULT_HOST}.")
    parser.add_argument("--port", type=positive_int, default=DEFAULT_PORT)
    parser.add_argument(
        "--allow-nonlocal-demo-bind",
        action="store_true",
        help="Allow binding outside localhost. Unsafe for this demo; prints a warning.",
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


def validate_bind_host(host: str, *, allow_nonlocal_demo_bind: bool) -> None:
    if host in LOCAL_BIND_HOSTS:
        return
    if allow_nonlocal_demo_bind:
        return
    raise DemoError(
        "Refusing non-local bind. Use --host 127.0.0.1 or pass "
        "--allow-nonlocal-demo-bind explicitly for a local demo risk review."
    )


def validate_query_id(query_id: str) -> str:
    try:
        return cm_collector.validate_cm_query_id_path_segment(query_id)
    except cm_collector.CMAdapterError as exc:
        raise DemoError(str(exc)) from exc


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


def run_demo_analysis(
    query_id: str,
    report_mode: str,
    redact_identifiers: bool,
    settings: DemoSettings,
    *,
    runner: Runner = subprocess.run,
    progress: ProgressFunc | None = None,
) -> DemoResult:
    update_progress(progress, 0)
    validated_query_id = validate_query_id(query_id)
    if report_mode not in {"admin", "user"}:
        raise DemoError("Report mode must be admin or user.")

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
        raise DemoError(subprocess_failure_message("Query Doctor analyzer", analyzed))

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
            raise DemoError(REPORT_VALIDATION_FAILURE_MESSAGE)
        if retried.returncode != 0:
            raise DemoError(subprocess_failure_message("Query Doctor report retry", retried))
        report_retry = True
    elif reported.returncode != 0:
        raise DemoError(subprocess_failure_message("Query Doctor report generation", reported))

    facts_path = case_dir / "analysis_facts.md"
    report_path = case_dir / report_name
    if not facts_path.exists() or not report_path.exists():
        raise DemoError("Analyzer/report output was not created.")

    facts_text = facts_path.read_text(encoding="utf-8", errors="replace")
    report_text = report_path.read_text(encoding="utf-8", errors="replace")
    facts = parse_facts_summary(facts_text)
    update_progress(progress, 5)
    return DemoResult(
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


def build_analyzer_command(case_dir: Path, settings: DemoSettings) -> list[str]:
    return [
        sys.executable,
        str(settings.repo_dir / "query_doctor_pipeline.py"),
        str(case_dir),
        "--skip-report",
    ]


def build_report_command(case_dir: Path, report_mode: str, report_name: str, settings: DemoSettings) -> list[str]:
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
    settings: DemoSettings,
    runner: Runner,
) -> Path:
    if not has_cm_credentials():
        raise DemoError(MISSING_CM_CREDENTIALS_MESSAGE)

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
        raise DemoError(subprocess_failure_message("CM single-query collection", collected))

    case_dir = parse_output_case_dir(collected.stdout)
    if not case_dir.is_absolute():
        case_dir = (settings.repo_dir / case_dir).resolve()
    expected_corpus_dir = resolve_under_repo(settings.repo_dir, settings.corpus_dir)
    try:
        case_dir.relative_to(expected_corpus_dir)
    except ValueError as exc:
        raise DemoError("Collector returned a case directory outside the demo corpus directory.") from exc
    if case_dir != expected_case_dir:
        raise DemoError("Collector returned a case directory that does not match the requested query id.")
    if not case_dir.exists():
        raise DemoError("Collector did not create the expected case directory.")
    return case_dir


def expected_case_dir_for_query(validated_query_id: str, settings: DemoSettings) -> Path:
    try:
        slug = cm_collector.safe_case_slug(validated_query_id)
    except cm_collector.OutputError as exc:
        raise DemoError(str(exc)) from exc
    corpus_dir = resolve_under_repo(settings.repo_dir, settings.corpus_dir)
    case_dir = (corpus_dir / slug).resolve(strict=False)
    try:
        case_dir.relative_to(corpus_dir)
    except ValueError as exc:
        raise DemoError("Computed demo case directory is outside the demo corpus directory.") from exc
    return case_dir


def ensure_complete_existing_case(case_dir: Path) -> None:
    if not case_dir.is_dir():
        raise DemoError(
            f"Existing demo case path is not a directory: {case_dir}. "
            "Remove that specific path manually if you want to recollect."
        )
    missing = [name for name in COLLECTED_CASE_FILES if not (case_dir / name).is_file()]
    if missing:
        missing_list = ", ".join(missing)
        raise DemoError(
            f"Local demo case is incomplete or broken: {case_dir}. "
            f"Missing required file(s): {missing_list}. Remove or rebuild that specific case directory "
            "manually before trying to recollect."
        )


def parse_output_case_dir(stdout: str) -> Path:
    match = OUTPUT_CASE_RE.search(stdout)
    if not match:
        raise DemoError("Collector output did not include a case directory.")
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
    settings: DemoSettings,
    *,
    analysis_func: AnalysisFunc = run_demo_analysis,
) -> tuple[int, str]:
    query_id = first_form_value(form, "query_id")
    report_mode = first_form_value(form, "mode") or "admin"
    redact_identifiers = first_form_value(form, "redact_identifiers") == "on"
    if not query_id:
        return 400, render_page(settings, error="Query ID is required.")
    try:
        result = analysis_func(query_id, report_mode, redact_identifiers, settings)
    except DemoError as exc:
        return 400, render_page(settings, query_id=query_id, report_mode=report_mode, error=sanitize_for_display(exc))
    return 200, render_page(settings, query_id=query_id, report_mode=report_mode, result=result)


def start_analyze_job(
    form: dict[str, list[str]],
    settings: DemoSettings,
    job_store: DemoJobStore,
    *,
    analysis_func: AnalysisFunc = run_demo_analysis,
) -> tuple[int, str]:
    query_id = first_form_value(form, "query_id")
    report_mode = first_form_value(form, "mode") or "admin"
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
    settings: DemoSettings,
    job_store: DemoJobStore,
    analysis_func: AnalysisFunc,
) -> None:
    def progress(stage_index: int) -> None:
        job_store.update_stage(job_id, stage_index)

    try:
        if analysis_func is run_demo_analysis:
            result = run_demo_analysis(
                query_id,
                report_mode,
                redact_identifiers,
                settings,
                progress=progress,
            )
        else:
            result = analysis_func(query_id, report_mode, redact_identifiers, settings)
        job_store.complete(job_id, result)
    except DemoError as exc:
        job_store.fail(job_id, exc)
    except Exception:  # pragma: no cover - defensive UI sanitization.
        job_store.fail(job_id, "Unexpected demo failure. Details are hidden because they may contain sensitive data.")


def render_job_status_json(job: DemoJobSnapshot | None) -> str:
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


def render_page(
    settings: DemoSettings,
    *,
    query_id: str = "",
    report_mode: str = "admin",
    result: DemoResult | None = None,
    job: DemoJobSnapshot | None = None,
    error: object | None = None,
) -> str:
    query_value = html.escape(query_id, quote=True)
    admin_checked = "checked" if report_mode == "admin" else ""
    user_checked = "checked" if report_mode == "user" else ""
    has_output = result is not None or error is not None or job is not None
    shell_class = "page-shell page-shell--with-result" if has_output else "page-shell"
    body = [
        "<!doctype html>",
        "<html lang=\"ru\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>Query Doctor Demo</title>",
        "<style>",
        ":root{color-scheme:dark;--bg:#111318;--panel:#171a20;--tile:#101318;--line:#2a3038;--line-soft:#222830;--text:#eef2f7;--muted:#9aa3ad;--accent:#7aa2f7;--accent-soft:#22304a;--danger:#ef8585;--ok:#8dd8a2;--shadow:0 14px 42px rgba(0,0,0,.28)}",
        "*{box-sizing:border-box}html{min-height:100%}body{min-height:100vh;margin:0;font-family:'Segoe UI',system-ui,-apple-system,BlinkMacSystemFont,sans-serif;background:radial-gradient(circle at 74% 38%,rgba(122,162,247,.09),transparent 30%),#101216;color:var(--text);line-height:1.4;overflow-x:hidden}fieldset{border:0;margin:0;padding:0}",
        ".demo-watermark{position:fixed;right:calc(50% - 500px);top:50%;width:min(24vw,230px);height:auto;opacity:.34;pointer-events:none;z-index:0;transform:translateY(-48%);filter:drop-shadow(0 14px 28px rgba(0,0,0,.28))}",
        ".page-shell{position:relative;z-index:1;min-height:100vh;width:min(100% - 32px,700px);margin:0 auto;display:flex;flex-direction:column;justify-content:center;gap:10px;padding:22px 0}.page-shell--with-result{justify-content:flex-start;padding-top:22px;padding-bottom:34px}",
        ".hero-card,.summary-card,.report-card,.progress-card{border:1px solid var(--line);background:rgba(23,26,32,.96);box-shadow:var(--shadow);border-radius:12px}",
        ".hero-card{padding:17px 18px 16px}.brand{text-align:center;margin-bottom:14px}.brand-mark-wrap{display:inline-grid;place-items:center;width:46px;height:46px;margin-bottom:7px;border:1px solid var(--line);border-radius:12px;background:#11151b}.brand-mark{width:36px;height:36px;display:block}.brand h1{margin:0;font-size:clamp(1.48rem,3vw,2rem);line-height:1.06;font-weight:650;letter-spacing:0}.brand p{margin:6px auto 0;max-width:500px;color:var(--muted);font-size:.86rem}",
        ".form-grid{display:grid;grid-template-columns:1fr 176px;gap:9px;align-items:end}.field label,.fieldset-title{display:block;margin:0 0 5px;color:#d7dde5;font-weight:600;font-size:.78rem}.field input[type=text]{width:100%;height:36px;border-radius:8px;border:1px solid var(--line);background:#101318;color:var(--text);font:inherit;padding:0 10px;outline:none}.field input[type=text]:focus{border-color:var(--accent);box-shadow:0 0 0 2px rgba(122,162,247,.18)}",
        ".mode-card{min-width:0}.segmented{display:grid;grid-template-columns:1fr 1fr;gap:0;background:#101318;border:1px solid var(--line);border-radius:8px;overflow:hidden}.segmented input{position:absolute;opacity:0;pointer-events:none}.segmented span{display:block;text-align:center;padding:7px 10px;color:var(--muted);font-weight:600;border-right:1px solid var(--line)}.segmented label:last-child span{border-right:0}.segmented input:checked+span{background:var(--accent-soft);color:#eaf1ff}.segmented label:focus-within span{outline:2px solid var(--accent);outline-offset:-2px}",
        ".controls{display:grid;grid-template-columns:1fr 176px;align-items:center;gap:9px;margin-top:10px}.check{display:flex;align-items:center;gap:7px;color:#d7dde5;font-weight:500;font-size:.84rem}.check input{width:14px;height:14px;accent-color:var(--accent)}.primary{border:1px solid rgba(122,162,247,.52);border-radius:8px;background:#345da8;color:white;font:inherit;font-weight:650;padding:8px 14px;min-width:0;cursor:pointer;box-shadow:none}.primary:hover{background:#3d68b5}.primary:focus{outline:2px solid #9bb8f7;outline-offset:2px}.primary[disabled]{opacity:.62;cursor:wait}",
        ".error-card{border:1px solid rgba(239,133,133,.5);background:rgba(56,26,31,.92);padding:12px 14px;color:#fee2e2;border-radius:10px}.error-card strong{color:#fecaca}",
        ".progress-card{padding:13px 14px}.progress-card--hidden{display:none}.progress-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}.progress-title{font-weight:650}.progress-stage{color:var(--muted);font-size:.84rem}.progress-bar{height:6px;border-radius:999px;background:#101318;border:1px solid var(--line-soft);overflow:hidden}.progress-fill{display:block;height:100%;width:4%;background:#7aa2f7;transition:width .2s ease}.progress-note{margin:8px 0 0;color:var(--muted);font-size:.77rem}",
        ".summary-card{padding:13px 14px;border-color:#2c4434}.summary-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}.status-pill{display:inline-flex;align-items:center;gap:8px;border-radius:8px;padding:4px 8px;background:rgba(141,216,162,.1);border:1px solid rgba(141,216,162,.3);color:#c9f7d3;font-weight:700}.summary-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.metric{border:1px solid var(--line-soft);background:rgba(16,19,24,.88);border-radius:8px;padding:8px}.metric span{display:block;color:var(--muted);font-size:.68rem;text-transform:uppercase;letter-spacing:.04em}.metric strong,.metric code{display:block;margin-top:4px;color:var(--text);font-size:.88rem;overflow-wrap:anywhere}.metric--wide{grid-column:span 3}",
        ".report-card{padding:0;overflow:hidden}.report-card summary{cursor:pointer;padding:11px 14px;font-size:.94rem;font-weight:700;border-bottom:1px solid var(--line);background:#151920}.report-body{padding:15px;color:#e8edf5;font-size:.9rem}.report-body h1,.report-body h2,.report-body h3,.report-body h4{margin:1.1em 0 .45em;line-height:1.18}.report-body h1:first-child,.report-body h2:first-child,.report-body h3:first-child{margin-top:0}.report-body h1{font-size:1.35rem}.report-body h2{font-size:1.18rem}.report-body h3{font-size:1.04rem}.report-body p{margin:.7em 0}.report-body ul,.report-body ol{margin:.55em 0 .8em;padding-left:1.35rem}.report-body li{margin:.28em 0}.report-body code{background:#0d1117;border:1px solid var(--line-soft);border-radius:5px;padding:.08rem .28rem;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.88em}.report-body pre{margin:.75em 0;padding:12px;background:#0d1117;border:1px solid var(--line-soft);border-radius:8px;white-space:pre-wrap;overflow-wrap:anywhere}.report-body pre code{border:0;background:transparent;padding:0}.report-body blockquote{margin:.75em 0;padding:.35em .8em;border-left:3px solid var(--accent);background:rgba(122,162,247,.07);color:#d9e2ee}.report-body table{width:100%;border-collapse:collapse;margin:.8em 0;font-size:.86rem}.report-body th,.report-body td{border:1px solid var(--line-soft);padding:6px 8px;text-align:left;vertical-align:top}.report-body th{background:#151920;color:#f2f6fb}",
        "@media (max-width:720px){.page-shell{width:min(100% - 20px,700px);padding:18px 0}.hero-card{padding:16px}.form-grid,.controls{grid-template-columns:1fr}.summary-grid{grid-template-columns:1fr}.metric--wide{grid-column:span 1}.demo-watermark{right:-58px;top:auto;bottom:22px;width:170px;opacity:.16;transform:none}}",
        "</style>",
        render_client_script(),
        "</head>",
        "<body>",
        render_watermark_svg(),
        f"<main class=\"{shell_class}\">",
        "<section class=\"hero-card\" aria-label=\"Query Doctor Demo form\">",
        "<header class=\"brand\">",
        "<div class=\"brand-mark-wrap\">",
        render_brand_mark_svg(),
        "</div>",
        "<h1>Query Doctor Demo</h1>",
        "<p>Интеллектуальный анализ Impala-запросов по Query ID</p>",
        "</header>",
        "<form id=\"analyze-form\" method=\"post\" action=\"/analyze\">",
        "<div class=\"form-grid\">",
        "<div class=\"field\">",
        "<label for=\"query_id\">Query ID</label>",
        f"<input id=\"query_id\" name=\"query_id\" type=\"text\" value=\"{query_value}\" autocomplete=\"off\" required placeholder=\"fa469f95f6fb7286:ea9f070d00000000\">",
        "</div>",
        "<fieldset class=\"mode-card\" aria-labelledby=\"mode_title\">",
        "<legend id=\"mode_title\" class=\"fieldset-title\">Режим отчёта</legend>",
        "<div class=\"segmented\">",
        f"<label><input type=\"radio\" name=\"mode\" value=\"user\" {user_checked}><span>user</span></label>",
        f"<label><input type=\"radio\" name=\"mode\" value=\"admin\" {admin_checked}><span>admin</span></label>",
        "</div>",
        "</fieldset>",
        "</div>",
        "<div class=\"controls\">",
        "<label class=\"check\"><input type=\"checkbox\" name=\"redact_identifiers\"> <span>Редактировать идентификаторы</span></label>",
        "<button class=\"primary\" type=\"submit\">Анализировать</button>",
        "</div>",
        "</form>",
        "</section>",
        render_pending_progress_panel(),
    ]
    if error is not None:
        body.append(f"<section class=\"error-card\" role=\"alert\"><strong>FAILED</strong><br>{html.escape(str(error))}</section>")
    if job is not None:
        body.append(render_job_panel(job))
    if result is not None:
        body.extend(render_result(result))
    body.extend(["</main>", "</body>", "</html>"])
    return "\n".join(body)


def render_client_script() -> str:
    return """<script>
document.addEventListener('DOMContentLoaded', function () {
  var form = document.getElementById('analyze-form');
  var pending = document.getElementById('pending-panel');
  if (form && pending) {
    form.addEventListener('submit', function () {
      pending.classList.remove('progress-card--hidden');
      var button = form.querySelector('button[type="submit"]');
      if (button) {
        button.disabled = true;
        button.textContent = 'Запускаем...';
      }
    });
  }
  var jobPanel = document.querySelector('[data-job-status-url]');
  if (!jobPanel) {
    return;
  }
  var stage = document.getElementById('job-stage');
  var fill = document.getElementById('job-progress-fill');
  var resultSlot = document.getElementById('job-result-slot');
  var errorSlot = document.getElementById('job-error-slot');
  function poll() {
    fetch(jobPanel.getAttribute('data-job-status-url'), {cache: 'no-store'})
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (stage) { stage.textContent = data.stage || ''; }
        if (fill) { fill.style.width = String(data.progress || 0) + '%'; }
        if (data.status === 'ok') {
          if (resultSlot) { resultSlot.innerHTML = data.result_html || ''; }
          return;
        }
        if (data.status === 'failed') {
          if (errorSlot) {
            errorSlot.hidden = false;
            errorSlot.textContent = data.error || 'Analysis failed.';
          }
          return;
        }
        window.setTimeout(poll, 1200);
      })
      .catch(function () { window.setTimeout(poll, 1800); });
  }
  poll();
});
</script>"""


def render_pending_progress_panel() -> str:
    stage = DEMO_STAGES[0]
    return (
        "<section id=\"pending-panel\" class=\"progress-card progress-card--hidden\" aria-live=\"polite\">"
        "<div class=\"progress-head\"><span class=\"progress-title\">Анализ запущен</span>"
        f"<span class=\"progress-stage\">{html.escape(stage[1])}</span></div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\"><span class=\"progress-fill\"></span></div>"
        "<p class=\"progress-note\">Обычно это занимает от нескольких секунд до пары минут.</p>"
        "</section>"
    )


def render_job_panel(job: DemoJobSnapshot) -> str:
    result_html = job.result_html if job.status == "ok" else ""
    error_html = html.escape(job.error) if job.status == "failed" else ""
    error_hidden = "" if job.status == "failed" else " hidden"
    return (
        f"<section class=\"progress-card\" data-job-status-url=\"/jobs/{html.escape(job.job_id)}/status\" aria-live=\"polite\">"
        "<div class=\"progress-head\"><span class=\"progress-title\">Анализ выполняется</span>"
        f"<span id=\"job-stage\" class=\"progress-stage\">{html.escape(job.stage_label)}</span></div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\">"
        f"<span id=\"job-progress-fill\" class=\"progress-fill\" style=\"width:{job.progress}%\"></span>"
        "</div>"
        "<p class=\"progress-note\">Обычно это занимает от нескольких секунд до пары минут.</p>"
        f"<div id=\"job-error-slot\" class=\"error-card\" role=\"alert\"{error_hidden}>{error_html}</div>"
        f"<div id=\"job-result-slot\">{result_html}</div>"
        "</section>"
    )


def render_watermark_svg() -> str:
    return """<svg class="demo-watermark doctor-impala-mascot" viewBox="0 0 220 220" aria-hidden="true" focusable="false">
<path d="M73 97 C48 70 37 42 44 22 C62 41 80 66 91 94" fill="none" stroke="#7aa2f7" stroke-width="10" stroke-linecap="round"/>
<path d="M147 97 C172 70 183 42 176 22 C158 41 140 66 129 94" fill="none" stroke="#7aa2f7" stroke-width="10" stroke-linecap="round"/>
<path d="M72 88 C88 64 132 64 148 88 C166 116 157 158 110 184 C63 158 54 116 72 88 Z" fill="rgba(122,162,247,.12)" stroke="#8fb0f7" stroke-width="8" stroke-linejoin="round"/>
<path d="M88 78 H132 L125 58 H95 Z" fill="rgba(238,242,247,.08)" stroke="#dbe6f7" stroke-width="5" stroke-linejoin="round"/>
<path d="M110 64 v22 M99 75 h22" stroke="#7aa2f7" stroke-width="6" stroke-linecap="round"/>
<path d="M87 122 C98 133 122 133 133 122" fill="none" stroke="#e8eef7" stroke-width="7" stroke-linecap="round"/>
<path d="M74 151 C48 159 44 183 62 197 C80 211 104 200 104 177" fill="none" stroke="#7aa2f7" stroke-width="6" stroke-linecap="round"/>
<circle cx="104" cy="177" r="9" fill="rgba(122,162,247,.12)" stroke="#e8eef7" stroke-width="5"/>
</svg>"""


def render_brand_mark_svg() -> str:
    return """<svg class="brand-mark doctor-impala-mark" viewBox="0 0 64 64" aria-hidden="true" focusable="false">
<path d="M21 29 C13 20 10 11 13 5 C19 12 25 21 29 30" fill="none" stroke="#7aa2f7" stroke-width="3.5" stroke-linecap="round"/>
<path d="M43 29 C51 20 54 11 51 5 C45 12 39 21 35 30" fill="none" stroke="#7aa2f7" stroke-width="3.5" stroke-linecap="round"/>
<path d="M20 25 C25 16 39 16 44 25 C50 36 43 51 32 58 C21 51 14 36 20 25 Z" fill="rgba(122,162,247,.13)" stroke="#9bb8f7" stroke-width="2.6" stroke-linejoin="round"/>
<path d="M24 23 H40 L37 16 H27 Z" fill="rgba(238,242,247,.10)" stroke="#dbe6f7" stroke-width="2.2" stroke-linejoin="round"/>
<path d="M32 18 v11 M26.5 23.5 h11" stroke="#7aa2f7" stroke-width="3" stroke-linecap="round"/>
<path d="M25 40 C29 44 35 44 39 40" fill="none" stroke="#e8eef7" stroke-width="2.8" stroke-linecap="round"/>
<path d="M12 45 C7 48 7 55 12 58 C18 61 24 56 23 51" fill="none" stroke="#7aa2f7" stroke-width="2.2" stroke-linecap="round"/>
<circle cx="23" cy="51" r="2.8" fill="rgba(122,162,247,.15)" stroke="#e8eef7" stroke-width="1.8"/>
</svg>"""


def render_result(result: DemoResult) -> list[str]:
    return [
        "<section class=\"summary-card\" aria-label=\"Analysis summary\">",
        "<div class=\"summary-head\"><span class=\"status-pill\">Status: OK</span><strong>Краткая сводка</strong></div>",
        "<div class=\"summary-grid\">",
        f"<div class=\"metric\"><span>Case source</span><strong>{html.escape(result.case_source)}</strong></div>",
        f"<div class=\"metric\"><span>Parsed operators</span><strong>{html.escape(result.parsed_operators)}</strong></div>",
        f"<div class=\"metric\"><span>Report mode</span><strong>{html.escape(result.report_mode)}</strong></div>",
        f"<div class=\"metric\"><span>Cardinality anomalies</span><strong>{html.escape(result.cardinality_anomalies)}</strong></div>",
        f"<div class=\"metric\"><span>Memory anomalies</span><strong>{html.escape(result.memory_anomalies)}</strong></div>",
        f"<div class=\"metric\"><span>Query ID</span><code>{html.escape(result.query_id)}</code></div>",
        f"<div class=\"metric metric--wide\"><span>Collected case directory</span><code>{html.escape(str(result.case_dir))}</code></div>",
        render_retry_metric(result),
        "</div>",
        "</section>",
        "<details class=\"report-card\" open>",
        "<summary>Полный отчёт</summary>",
        f"<div class=\"report-body\">{render_report_markdown_html(result.report_text)}</div>",
        "</details>",
    ]


def render_report_markdown_html(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    list_items: list[str] = []
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{render_inline_markdown(' '.join(part.strip() for part in paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_type
        if list_type is not None:
            tag = "ol" if list_type == "ol" else "ul"
            blocks.append(f"<{tag}>" + "".join(f"<li>{item}</li>" for item in list_items) + f"</{tag}>")
            list_items.clear()
            list_type = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            index += 1
            continue

        fence_match = re.match(r"^\s*(```|~~~)", line)
        if fence_match:
            flush_paragraph()
            flush_list()
            fence = fence_match.group(1)
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith(fence):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            code_text = html.escape("\n".join(code_lines))
            blocks.append(f"<pre><code>{code_text}</code></pre>")
            continue

        if is_table_start(lines, index):
            flush_paragraph()
            flush_list()
            table_lines = [lines[index], lines[index + 1]]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                table_lines.append(lines[index])
                index += 1
            blocks.append(render_markdown_table(table_lines))
            continue

        heading_match = re.match(r"^(#{1,4})\s+(.+?)\s*$", line)
        if heading_match:
            flush_paragraph()
            flush_list()
            level = len(heading_match.group(1))
            blocks.append(f"<h{level}>{render_inline_markdown(heading_match.group(2))}</h{level}>")
            index += 1
            continue

        quote_match = re.match(r"^\s*>\s?(.*)$", line)
        if quote_match:
            flush_paragraph()
            flush_list()
            quote_lines = [quote_match.group(1)]
            index += 1
            while index < len(lines):
                next_quote = re.match(r"^\s*>\s?(.*)$", lines[index])
                if not next_quote:
                    break
                quote_lines.append(next_quote.group(1))
                index += 1
            quote_text = "<br>".join(render_inline_markdown(part) for part in quote_lines)
            blocks.append(f"<blockquote>{quote_text}</blockquote>")
            continue

        unordered = re.match(r"^\s*[-*+]\s+(.+)$", line)
        ordered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if unordered or ordered:
            flush_paragraph()
            current_type = "ol" if ordered else "ul"
            if list_type != current_type:
                flush_list()
                list_type = current_type
            item_text = ordered.group(1) if ordered else unordered.group(1)
            list_items.append(render_inline_markdown(item_text))
            index += 1
            continue

        flush_list()
        paragraph.append(line)
        index += 1

    flush_paragraph()
    flush_list()
    return "\n".join(blocks)


def render_inline_markdown(text: str) -> str:
    parts = re.split(r"(`[^`]+`)", text)
    rendered: list[str] = []
    for part in parts:
        if len(part) >= 2 and part.startswith("`") and part.endswith("`"):
            rendered.append(f"<code>{html.escape(part[1:-1])}</code>")
        else:
            rendered.append(html.escape(part))
    return "".join(rendered)


def is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    return "|" in lines[index] and is_table_separator(lines[index + 1])


def is_table_separator(line: str) -> bool:
    cells = split_table_row(line)
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|") if cell.strip()]


def render_markdown_table(table_lines: list[str]) -> str:
    header = split_table_row(table_lines[0])
    rows = [split_table_row(line) for line in table_lines[2:]]
    header_html = "".join(f"<th>{render_inline_markdown(cell)}</th>" for cell in header)
    body_rows: list[str] = []
    for row in rows:
        cells = row[: len(header)] + [""] * max(0, len(header) - len(row))
        body_rows.append("<tr>" + "".join(f"<td>{render_inline_markdown(cell)}</td>" for cell in cells) + "</tr>")
    return "<table><thead><tr>" + header_html + "</tr></thead><tbody>" + "".join(body_rows) + "</tbody></table>"


def render_retry_metric(result: DemoResult) -> str:
    if not result.report_retry:
        return ""
    return (
        "<div class=\"metric metric--wide\"><span>Report generation</span>"
        "<strong>regenerated after validator retry</strong></div>"
    )


def make_handler(
    settings: DemoSettings,
    analysis_func: AnalysisFunc = run_demo_analysis,
    job_store: DemoJobStore | None = None,
) -> type[BaseHTTPRequestHandler]:
    store = job_store or DemoJobStore()

    class QueryDoctorDemoHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self.write_html(200, render_page(settings))
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
            print(f"[Query Doctor demo] {self.address_string()} {fmt % args}", file=sys.stderr)

    return QueryDoctorDemoHandler


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        validate_bind_host(args.host, allow_nonlocal_demo_bind=args.allow_nonlocal_demo_bind)
    except DemoError as exc:
        print(f"[Query Doctor demo] ERROR: {exc}", file=sys.stderr)
        return 2
    if args.host not in LOCAL_BIND_HOSTS:
        print(
            "[Query Doctor demo] WARNING: non-local bind requested for a local demo server.",
            file=sys.stderr,
        )

    settings = DemoSettings(
        config=Path(args.config).expanduser(),
        host=args.host,
        port=args.port,
        allow_nonlocal_demo_bind=args.allow_nonlocal_demo_bind,
        max_profile_bytes=args.max_profile_bytes,
        model=args.model,
        timeout_sec=args.timeout_sec,
    )
    handler = make_handler(settings)
    server = ThreadingHTTPServer((settings.host, settings.port), handler)
    print(f"[Query Doctor demo] listening on http://{settings.host}:{settings.port}")
    print("[Query Doctor demo] credentials and CM config are read only by local subprocesses; they are not shown in the UI.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Query Doctor demo] stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
