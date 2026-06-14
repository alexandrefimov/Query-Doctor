#!/usr/bin/env python3
"""E2E smoke-check one-profile Quickstart through an installed web server."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUERY_ID = "1111111111111111:2222222222222222"
DEFAULT_PROFILE_TEXT = (
    ROOT / "tests" / "fixtures" / "mixed_stats_runtime_case" / "profile_digest.md"
)
INSTALLED_BIN_ENV = "QUERY_DOCTOR_INSTALLED_CLI_BIN"
WEB_STATIC_SMOKE = ROOT / "scripts" / "web_static_smoke.py"
SECRET_ENV_PREFIXES = ("CM_",)
SECRET_ENV_NAMES = {
    "KRB5CCNAME",
    "QD_CM_ENV",
    "QD_CONFIG",
    "QD_LLM_API_KEY",
    "QD_OPTIMIZER_LLM_API_KEY",
    "QD_REPORT_LLM_API_KEY",
}


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: str


class WebE2EFailure(RuntimeError):
    """Safe user-facing installed web E2E failure."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bin-dir",
        default=os.environ.get(INSTALLED_BIN_ENV),
        help=f"Directory containing installed Query Doctor console scripts. Defaults to ${INSTALLED_BIN_ENV}.",
    )
    parser.add_argument(
        "--profile-text",
        type=Path,
        default=DEFAULT_PROFILE_TEXT,
        help="Synthetic exported Impala text profile fixture to smoke. Default: %(default)s",
    )
    parser.add_argument(
        "--query-id",
        default=DEFAULT_QUERY_ID,
        help="Query ID to inject into the smoke profile. Default: %(default)s",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Optional temporary workspace. A fresh temporary directory is used by default.",
    )
    parser.add_argument(
        "--keep-work-dir",
        action="store_true",
        help="Keep the temporary workspace for debugging.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Local bind host for the installed web server. Default: %(default)s",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Local bind port. Defaults to an available ephemeral port.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=120.0,
        help="Per-step timeout in seconds. Default: %(default)s",
    )
    return parser.parse_args(argv)


def installed_executable(bin_dir: Path, name: str) -> Path:
    candidates = (bin_dir / name, bin_dir / f"{name}.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise WebE2EFailure(f"installed executable not found in {bin_dir}: {name}")


def clean_env(bin_dir: Path, home_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    for name in list(env):
        if name in SECRET_ENV_NAMES or any(
            name.startswith(prefix) for prefix in SECRET_ENV_PREFIXES
        ):
            env.pop(name, None)
    env["HOME"] = str(home_dir)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["QD_COMMAND_BACKEND"] = "console"
    return env


def safe_output_snippet(text: str, *, max_chars: int = 800) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3] + "..."


def run_command(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_sec: float,
    label: str,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout_sec,
        check=False,
    )
    if result.returncode != 0:
        detail = safe_output_snippet(result.stderr) or safe_output_snippet(result.stdout)
        raise WebE2EFailure(f"{label} failed: {detail or result.returncode}")
    return result


def prepare_smoke_profile(source: Path, destination: Path, *, query_id: str) -> None:
    if not source.is_file():
        raise WebE2EFailure(f"profile text fixture not found: {source}")
    profile_text = source.read_text(encoding="utf-8")
    destination.write_text(
        f"Query Runtime Profile\nQuery ID: {query_id}\n\n{profile_text}",
        encoding="utf-8",
    )


def free_local_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def fetch(host: str, port: int, path: str, *, timeout_sec: float = 5.0) -> HttpResponse:
    connection = http.client.HTTPConnection(host, port, timeout=timeout_sec)
    try:
        connection.request("GET", path, headers={"Host": f"{host}:{port}"})
        response = connection.getresponse()
        body = response.read().decode("utf-8", errors="replace")
        headers = {name.lower(): value for name, value in response.getheaders()}
        return HttpResponse(status=response.status, headers=headers, body=body)
    finally:
        connection.close()


def wait_for_ready(
    process: subprocess.Popen[str],
    *,
    host: str,
    port: int,
    timeout_sec: float,
) -> None:
    deadline = time.monotonic() + timeout_sec
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            detail = safe_output_snippet(stderr) or safe_output_snippet(stdout)
            raise WebE2EFailure(f"installed web server exited before readiness: {detail}")
        try:
            response = fetch(host, port, "/", timeout_sec=1.0)
        except OSError as exc:
            last_error = str(exc)
            time.sleep(0.2)
            continue
        if response.status == 200:
            return
        last_error = f"GET / returned {response.status}"
        time.sleep(0.2)
    raise WebE2EFailure(f"installed web server did not become ready: {last_error}")


def stop_process(process: subprocess.Popen[str]) -> tuple[str, str]:
    if process.poll() is None:
        process.terminate()
        try:
            return process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.communicate(timeout=10)
    return process.communicate(timeout=10)


def require_page(
    response: HttpResponse,
    *,
    label: str,
    expected: tuple[str, ...],
    forbidden: tuple[str, ...],
) -> None:
    if response.status != 200:
        raise WebE2EFailure(f"{label} returned HTTP {response.status}")
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type:
        raise WebE2EFailure(f"{label} returned unexpected Content-Type {content_type!r}")
    for value in expected:
        if value not in response.body:
            raise WebE2EFailure(f"{label} is missing expected text: {value!r}")
    for value in forbidden:
        if value and value in response.body:
            raise WebE2EFailure(f"{label} leaked forbidden text: {value!r}")


def run_static_smoke(
    *,
    base_url: str,
    query_id: str,
    env: dict[str, str],
    timeout_sec: float,
) -> None:
    quoted_query_id = quote(query_id, safe="")
    run_command(
        [
            sys.executable,
            str(WEB_STATIC_SMOKE),
            "--url",
            base_url,
            "--expect-text",
            "Exported Profiles",
            "--expect-text",
            query_id,
            "--expect-path-text",
            f"/batch/case/case-001::{query_id}",
            "--expect-path-text",
            f"/query/details/{quoted_query_id}::{query_id}",
        ],
        cwd=ROOT,
        env=env,
        timeout_sec=timeout_sec,
        label="web static smoke against installed web server",
    )


def run_smoke(args: argparse.Namespace, work_dir: Path) -> None:
    if not args.bin_dir:
        raise WebE2EFailure(f"--bin-dir or ${INSTALLED_BIN_ENV} is required")
    if args.port is not None and not (0 < args.port <= 65535):
        raise WebE2EFailure("--port must be between 1 and 65535")

    bin_dir = Path(args.bin_dir).expanduser().resolve()
    analyze = installed_executable(bin_dir, "query-doctor-analyze")
    web = installed_executable(bin_dir, "query-doctor-web")
    env = clean_env(bin_dir, work_dir / "home")
    (work_dir / "home").mkdir(parents=True, exist_ok=True)

    profile_text = work_dir / "exported-profile.txt"
    prepare_smoke_profile(
        args.profile_text.expanduser().resolve(), profile_text, query_id=args.query_id
    )
    corpus_dir = work_dir / "cases" / "cm-corpus"
    run_command(
        [
            str(analyze),
            "--profile-text",
            str(profile_text),
            "--out",
            str(corpus_dir),
            "--redact-identifiers",
        ],
        cwd=work_dir,
        env=env,
        timeout_sec=args.timeout_sec,
        label="installed query-doctor-analyze",
    )
    case_dir = corpus_dir / args.query_id.replace(":", "_")
    for filename in ("analysis_facts.md", "analysis.json", "cm_metadata.json"):
        if not (case_dir / filename).is_file():
            raise WebE2EFailure(f"installed analyzer did not write {filename}")

    launch_dir = work_dir / "web-launch"
    launch_dir.mkdir(parents=True, exist_ok=True)
    bad_default_config = launch_dir / "query-doctor-config.json"
    bad_default_config.write_text(json.dumps({"future_config_field": True}), encoding="utf-8")

    port = args.port or free_local_port(args.host)
    process = subprocess.Popen(
        [
            str(web),
            "--host",
            args.host,
            "--port",
            str(port),
            "--corpus-dir",
            str(corpus_dir),
            "--no-llm",
        ],
        cwd=launch_dir,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout = ""
    stderr = ""
    try:
        wait_for_ready(process, host=args.host, port=port, timeout_sec=args.timeout_sec)
        base_url = f"http://{args.host}:{port}"
        run_static_smoke(
            base_url=base_url,
            query_id=args.query_id,
            env=env,
            timeout_sec=args.timeout_sec,
        )
        forbidden = (
            "Query Runtime Profile",
            str(work_dir),
            str(corpus_dir),
            str(profile_text),
            "exported-profile.txt",
            "analysis.json",
            "profile_digest.md",
            "cm_metadata.json",
        )
        require_page(
            fetch(args.host, port, "/"),
            label="GET /",
            expected=("Exported Profiles", "All analyzed", args.query_id),
            forbidden=forbidden,
        )
        require_page(
            fetch(args.host, port, "/batch/case/case-001"),
            label="GET /batch/case/case-001",
            expected=('id="case-overview"', args.query_id),
            forbidden=forbidden,
        )
        require_page(
            fetch(args.host, port, f"/query/details/{quote(args.query_id, safe='')}"),
            label="GET /query/details/<query-id>",
            expected=("Known Query ID details", args.query_id),
            forbidden=forbidden,
        )
    finally:
        stdout, stderr = stop_process(process)

    if process.returncode not in {0, -15, -9, 143}:
        detail = safe_output_snippet(stderr) or safe_output_snippet(stdout)
        raise WebE2EFailure(f"installed web server exited unexpectedly: {detail}")

    print(
        json.dumps(
            {
                "schema_version": "query_doctor_installed_web_e2e_smoke_v1",
                "status": "OK",
                "query_id": args.query_id,
                "real_web_server": True,
                "quickstart_corpus_rendered": True,
                "details_rendered": True,
                "static_smoke_passed": True,
                "invalid_default_config_ignored": True,
                "external_services_used": False,
                "llm_used": False,
            },
            sort_keys=True,
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="query-doctor-installed-web-e2e-"))
        cleanup = not args.keep_work_dir
    else:
        work_dir = args.work_dir.expanduser().resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        cleanup = False
    try:
        run_smoke(args, work_dir)
    except WebE2EFailure as exc:
        print(f"[installed-web-e2e-smoke] FAILED: {exc}", file=sys.stderr)
        if not cleanup:
            print(f"[installed-web-e2e-smoke] work dir: {work_dir}", file=sys.stderr)
        return 1
    finally:
        if cleanup:
            shutil.rmtree(work_dir, ignore_errors=True)
        elif args.keep_work_dir or args.work_dir is not None:
            print(f"[installed-web-e2e-smoke] work dir: {work_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
