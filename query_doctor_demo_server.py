#!/usr/bin/env python3
"""Local-only Query Doctor demo server for explicit CM query ids."""

from __future__ import annotations

import argparse
import html
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs

import query_doctor_collect_cm_profiles as cm_collector


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_TIMEOUT_SEC = 1800
DEFAULT_MODEL = "qwen3-coder:30b"
LOCAL_BIND_HOSTS = {"127.0.0.1", "localhost"}
OUTPUT_CASE_RE = re.compile(r"^Output case directory:\s*(?P<path>.+)$", re.MULTILINE)


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


@dataclass(frozen=True)
class DemoResult:
    query_id: str
    case_dir: Path
    report_mode: str
    parsed_operators: str
    cardinality_anomalies: str
    memory_anomalies: str
    report_text: str


AnalysisFunc = Callable[[str, str, bool, DemoSettings], DemoResult]
Runner = Callable[..., subprocess.CompletedProcess[str]]


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


def run_demo_analysis(
    query_id: str,
    report_mode: str,
    redact_identifiers: bool,
    settings: DemoSettings,
    *,
    runner: Runner = subprocess.run,
) -> DemoResult:
    validated_query_id = validate_query_id(query_id)
    if report_mode not in {"admin", "user"}:
        raise DemoError("Report mode must be admin or user.")

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
    if not case_dir.exists():
        raise DemoError("Collector did not create the expected case directory.")

    report_name = f"report_{report_mode}.md"
    pipeline_cmd = [
        sys.executable,
        str(settings.repo_dir / "query_doctor_pipeline.py"),
        str(case_dir),
        "--model",
        settings.model,
        "--mode",
        report_mode,
        "--out",
        report_name,
    ]
    reported = run_subprocess(
        pipeline_cmd,
        cwd=settings.repo_dir,
        timeout_sec=settings.timeout_sec,
        runner=runner,
    )
    if reported.returncode != 0:
        raise DemoError(subprocess_failure_message("Query Doctor report generation", reported))

    facts_path = case_dir / "analysis_facts.md"
    report_path = case_dir / report_name
    if not facts_path.exists() or not report_path.exists():
        raise DemoError("Analyzer/report output was not created.")

    facts_text = facts_path.read_text(encoding="utf-8", errors="replace")
    report_text = report_path.read_text(encoding="utf-8", errors="replace")
    facts = parse_facts_summary(facts_text)
    return DemoResult(
        query_id=validated_query_id,
        case_dir=case_dir,
        report_mode=report_mode,
        parsed_operators=facts.get("Parsed operators", "unknown"),
        cardinality_anomalies=facts.get("Cardinality anomalies", "unknown"),
        memory_anomalies=facts.get("Memory anomalies", "unknown"),
        report_text=report_text,
    )


def parse_output_case_dir(stdout: str) -> Path:
    match = OUTPUT_CASE_RE.search(stdout)
    if not match:
        raise DemoError("Collector output did not include a case directory.")
    return Path(match.group("path").strip())


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
    error: object | None = None,
) -> str:
    query_value = html.escape(query_id, quote=True)
    admin_selected = "selected" if report_mode == "admin" else ""
    user_selected = "selected" if report_mode == "user" else ""
    body = [
        "<!doctype html>",
        "<html lang=\"en\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>Query Doctor Demo</title>",
        "<style>",
        "body{font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:2rem;max-width:960px;line-height:1.45}",
        "label{display:block;margin-top:1rem;font-weight:600}input,select,button{font:inherit;padding:.45rem;margin-top:.3rem}input[type=text]{width:min(100%,38rem)}",
        "button{cursor:pointer}.status{padding:.75rem;margin:1rem 0;border:1px solid #999;background:#f7f7f7}.error{border-color:#b00020;background:#fff1f1}",
        "pre{white-space:pre-wrap;border:1px solid #ccc;padding:1rem;overflow:auto;background:#fafafa}",
        "</style>",
        "</head>",
        "<body>",
        "<h1>Query Doctor Demo</h1>",
        "<p>Local-only demo. Enter one CM Impala query id; broad collection is not enabled.</p>",
        "<form method=\"post\" action=\"/analyze\">",
        "<label for=\"query_id\">Query ID</label>",
        f"<input id=\"query_id\" name=\"query_id\" type=\"text\" value=\"{query_value}\" autocomplete=\"off\" required>",
        "<label for=\"mode\">Report mode</label>",
        f"<select id=\"mode\" name=\"mode\"><option value=\"admin\" {admin_selected}>admin</option><option value=\"user\" {user_selected}>user</option></select>",
        "<label><input type=\"checkbox\" name=\"redact_identifiers\"> Redact identifiers</label>",
        "<p><button type=\"submit\">Analyze</button></p>",
        "</form>",
    ]
    if error is not None:
        body.append(f"<div class=\"status error\"><strong>FAILED</strong><br>{html.escape(str(error))}</div>")
    if result is not None:
        body.extend(render_result(result))
    body.extend(["</body>", "</html>"])
    return "\n".join(body)


def render_result(result: DemoResult) -> list[str]:
    return [
        "<div class=\"status\"><strong>OK</strong>",
        f"<p>Query ID: <code>{html.escape(result.query_id)}</code></p>",
        f"<p>Collected case directory: <code>{html.escape(str(result.case_dir))}</code></p>",
        f"<p>Parsed operators: {html.escape(result.parsed_operators)}</p>",
        f"<p>Cardinality anomalies: {html.escape(result.cardinality_anomalies)}</p>",
        f"<p>Memory anomalies: {html.escape(result.memory_anomalies)}</p>",
        f"<p>Report mode: {html.escape(result.report_mode)}</p>",
        "</div>",
        "<h2>Report</h2>",
        f"<pre>{html.escape(result.report_text)}</pre>",
    ]


def make_handler(settings: DemoSettings, analysis_func: AnalysisFunc = run_demo_analysis) -> type[BaseHTTPRequestHandler]:
    class QueryDoctorDemoHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in {"/", "/index.html"}:
                self.send_error(404)
                return
            self.write_html(200, render_page(settings))

        def do_POST(self) -> None:
            if self.path != "/analyze":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(min(length, 65536)).decode("utf-8", errors="replace")
            form = parse_qs(raw_body, keep_blank_values=True)
            status, body = handle_analyze_request(form, settings, analysis_func=analysis_func)
            self.write_html(status, body)

        def write_html(self, status: int, body: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
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
