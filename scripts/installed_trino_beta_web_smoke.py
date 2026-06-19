#!/usr/bin/env python3
"""E2E smoke-check Trino Beta web lanes through an installed web server."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from smoke_workdir import SmokeWorkDirError, prepare_smoke_work_dir


ROOT = Path(__file__).resolve().parents[1]
INSTALLED_BIN_ENV = "QUERY_DOCTOR_INSTALLED_CLI_BIN"
WEB_TRINO_BETA_SMOKE = ROOT / "scripts" / "query-doctor-web-trino-beta-smoke"
QUERY_ID = "20260603_120102_00001_abcde"
SECRET_ENV_PREFIXES = ("CM_",)
SECRET_ENV_NAMES = {
    "KRB5CCNAME",
    "QD_CM_ENV",
    "QD_CONFIG",
    "QD_LLM_API_KEY",
    "QD_OPTIMIZER_LLM_API_KEY",
    "QD_REPORT_LLM_API_KEY",
}


class InstalledTrinoBetaWebFailure(RuntimeError):
    """Safe installed Trino Beta web smoke failure."""


class FakeTrinoCoordinator:
    def __init__(self, *, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.query_list_reads = 0
        self.query_info_reads = 0

    def start(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                parsed = urlsplit(self.path)
                query = parse_qs(parsed.query)
                if parsed.path == "/v1/query" and query.get("pruned") == ["true"]:
                    outer.query_list_reads += 1
                    self._send_json(fake_query_list_payload())
                    return
                if parsed.path == f"/v1/query/{QUERY_ID}" and query.get("pruned") == ["true"]:
                    outer.query_info_reads += 1
                    self._send_json(fake_query_info_payload())
                    return
                self.send_response(404)
                self.end_headers()

            def log_message(self, _format: str, *_args: object) -> None:
                return

            def _send_json(self, payload: object) -> None:
                body = json.dumps(payload, sort_keys=True).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=5)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bin-dir",
        default=os.environ.get(INSTALLED_BIN_ENV),
        help=f"Directory containing installed Query Doctor console scripts. Defaults to ${INSTALLED_BIN_ENV}.",
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
        "--replace-work-dir",
        action="store_true",
        help=(
            "Remove an existing non-empty --work-dir before running. Requires a "
            "query-doctor-* work directory."
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Local bind host for the installed web server and fake coordinator.",
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=None,
        help="Local installed web bind port. Defaults to an available ephemeral port.",
    )
    parser.add_argument(
        "--coordinator-port",
        type=int,
        default=None,
        help="Local fake Trino coordinator bind port. Defaults to an available ephemeral port.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=180.0,
        help="Overall smoke timeout in seconds. Default: %(default)s",
    )
    return parser.parse_args(argv)


def installed_executable(bin_dir: Path, name: str) -> Path:
    candidates = (bin_dir / name, bin_dir / f"{name}.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise InstalledTrinoBetaWebFailure(f"installed executable not found: {name}")


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


def free_local_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def write_config(work_dir: Path, *, coordinator_url: str) -> Path:
    info_contract = work_dir / "trino-query-info-contract.json"
    info_contract.write_text(json.dumps(query_info_contract_payload()), encoding="utf-8")
    list_contract = work_dir / "trino-query-list-contract.json"
    list_contract.write_text(json.dumps(query_list_contract_payload()), encoding="utf-8")
    config = work_dir / "query-doctor-config.json"
    config.write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "id": "trino-beta-fixture",
                        "label": "Trino Beta fixture",
                        "trino_beta_enabled": True,
                        "trino_coordinator_url": coordinator_url,
                        "trino_query_info_source_contract": info_contract.name,
                        "trino_query_list_source_contract": list_contract.name,
                    }
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return config


def write_installed_web_wrapper(work_dir: Path, web: Path) -> Path:
    wrapper = work_dir / "query-doctor-web-installed-wrapper.py"
    wrapper.write_text(
        "\n".join(
            (
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "import os",
                "import sys",
                "",
                "web = os.environ['QD_INSTALLED_QUERY_DOCTOR_WEB']",
                "config = os.environ['QD_CONFIG']",
                "os.execv(web, [web, '--config', config, *sys.argv[1:]])",
                "",
            )
        ),
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return wrapper


def query_info_contract_payload() -> dict[str, object]:
    return {
        "source_contract_version": "trino_coordinator_query_info_source_contract_v1",
        "source_type": "coordinator_query_info",
        "query_info_contract_version": "trino_coordinator_query_info_target_v1",
        "trino_version_family": "477",
        "auth_reference": {
            "kind": "operator_managed_reference",
            "label": "external_ref_01",
        },
        "query_bound": {
            "kind": "explicit_query_id",
            "max_query_ids": 1,
        },
        "bounds": {
            "max_bytes": 65536,
            "max_query_info_depth": 16,
            "timeout_seconds": 30,
        },
        "redaction": {
            "redaction_review_required": True,
            "raw_payload_storage": "forbidden",
            "normalized_fact_storage": "allowed",
            "browser_report_output": "blocked",
        },
    }


def query_list_contract_payload() -> dict[str, object]:
    return {
        "source_contract_version": "trino_coordinator_query_list_source_contract_v1",
        "source_type": "trino_coordinator_query_list",
        "query_list_contract_version": "trino_coordinator_query_list_v1",
        "trino_version_family": "477",
        "auth_reference": {
            "kind": "operator_managed_reference",
            "label": "external_ref_01",
        },
        "query_bound": {
            "kind": "bounded_retained_query_list",
            "max_query_ids": 50,
        },
        "bounds": {
            "max_bytes": 65536,
            "max_query_list_depth": 12,
            "timeout_seconds": 30,
        },
        "redaction": {
            "redaction_review_required": True,
            "raw_payload_storage": "forbidden",
            "normalized_fact_storage": "allowed",
            "browser_report_output": "blocked",
        },
    }


def fake_query_list_payload() -> list[dict[str, object]]:
    return [
        {
            "queryId": QUERY_ID,
            "state": "FINISHED",
            "createTime": "2026-06-17T08:00:00Z",
            "endTime": "2026-06-17T08:00:02Z",
            "query": "SELECT secret_col FROM sensitive_table",
            "self": "https://coordinator.example.test/ui/query.html",
            "session": {"user": "raw_session_user"},
            "queryStats": {
                "elapsedTime": "2s",
                "queuedTime": "100ms",
                "planningTime": "200ms",
                "executionTime": "1s",
            },
        }
    ]


def fake_query_info_payload() -> dict[str, object]:
    return {
        "queryId": QUERY_ID,
        "state": "FINISHED",
        "query": "SELECT secret_col FROM sensitive_table",
        "self": "https://coordinator.example.test/ui/query.html",
        "session": {"user": "raw_session_user"},
        "outputStage": {
            "stageId": "stage-raw-id",
            "tasks": [
                {
                    "taskId": "task-raw-id",
                    "worker": "worker-a.example.net",
                    "path": "synthetic_local_path_marker",
                }
            ],
        },
        "queryStats": {
            "elapsedTime": "2.50s",
            "queuedTime": "100ms",
            "planningTime": "200ms",
            "executionTime": "2.00s",
            "totalCpuTime": "1.25s",
            "processedInputPositions": 123,
            "processedInputDataSize": "1MB",
            "outputPositions": 7,
            "outputDataSize": "2kB",
            "peakTotalMemoryReservation": "3MB",
            "spilledDataSize": "0B",
            "fullyBlocked": False,
            "totalTasks": 4,
            "failedTasks": 0,
        },
    }


def run_smoke(args: argparse.Namespace, work_dir: Path) -> None:
    if not args.bin_dir:
        raise InstalledTrinoBetaWebFailure(f"--bin-dir or ${INSTALLED_BIN_ENV} is required")
    bin_dir = Path(args.bin_dir).expanduser().resolve()
    python = installed_executable(bin_dir, "python")
    web = installed_executable(bin_dir, "query-doctor-web")
    env = clean_env(bin_dir, work_dir / "home")
    (work_dir / "home").mkdir(parents=True, exist_ok=True)

    coordinator_port = args.coordinator_port or free_local_port(args.host)
    web_port = args.web_port or free_local_port(args.host)
    coordinator = FakeTrinoCoordinator(host=args.host, port=coordinator_port)
    config = write_config(
        work_dir,
        coordinator_url=f"http://{args.host}:{coordinator_port}",
    )
    web_wrapper = write_installed_web_wrapper(work_dir, web)
    env["QD_CONFIG"] = str(config)
    env["QD_INSTALLED_QUERY_DOCTOR_WEB"] = str(web)
    coordinator.start()
    try:
        command = [
            str(python),
            str(WEB_TRINO_BETA_SMOKE),
            "--config",
            str(config),
            "--web-wrapper",
            str(web_wrapper),
            "--host",
            args.host,
            "--port",
            str(web_port),
            "--timeout-sec",
            str(args.timeout_sec),
            "--poll-interval-sec",
            "0.1",
        ]
        result = subprocess.run(
            command,
            cwd=work_dir,
            env=env,
            text=True,
            capture_output=True,
            timeout=args.timeout_sec + 10,
            check=False,
        )
    finally:
        coordinator.stop()

    if result.returncode != 0:
        detail = safe_output_snippet(result.stderr) or safe_output_snippet(result.stdout)
        raise InstalledTrinoBetaWebFailure(
            f"installed Trino Beta web smoke failed: {detail or result.returncode}"
        )
    if coordinator.query_list_reads != 1:
        raise InstalledTrinoBetaWebFailure("Trino Beta Recent did not read the fake query list")
    if coordinator.query_info_reads != 2:
        raise InstalledTrinoBetaWebFailure(
            "Trino Beta Recent plus One Query ID did not perform the expected QueryInfo reads"
        )
    combined = result.stdout + result.stderr
    for marker in (
        QUERY_ID,
        "secret_col",
        "sensitive_table",
        "coordinator.example.test",
        "raw_session_user",
    ):
        if marker in combined:
            raise InstalledTrinoBetaWebFailure("installed Trino Beta web smoke leaked raw output")

    print(
        json.dumps(
            {
                "schema_version": "query_doctor_installed_trino_beta_web_smoke_v1",
                "status": "OK",
                "real_web_server": True,
                "fake_trino_coordinator": True,
                "recent_form_checked": True,
                "one_query_id_form_checked": True,
                "query_list_reads": coordinator.query_list_reads,
                "query_info_reads": coordinator.query_info_reads,
                "external_services_used": False,
                "llm_used": False,
                "sql_execution_performed": False,
            },
            sort_keys=True,
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    requested_work_dir = args.work_dir.expanduser().resolve() if args.work_dir else None
    try:
        prepared = prepare_smoke_work_dir(
            args.work_dir,
            keep_work_dir=args.keep_work_dir,
            replace_work_dir=args.replace_work_dir,
            temp_prefix="query-doctor-installed-trino-beta-web-",
            protected_roots=(ROOT,),
        )
        work_dir = prepared.path
        run_smoke(args, work_dir)
    except SmokeWorkDirError as exc:
        print(f"[installed-trino-beta-web-smoke] FAILED: {exc}", file=sys.stderr)
        if requested_work_dir is not None:
            print(
                f"[installed-trino-beta-web-smoke] work dir: {requested_work_dir}",
                file=sys.stderr,
            )
        return 1
    except (InstalledTrinoBetaWebFailure, subprocess.TimeoutExpired, OSError) as exc:
        print(f"[installed-trino-beta-web-smoke] FAILED: {exc}", file=sys.stderr)
        return 1
    else:
        print(f"[installed-trino-beta-web-smoke] work dir: {work_dir}")
        return 0
    finally:
        if "prepared" in locals() and prepared.cleanup:
            prepared.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
