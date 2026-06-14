#!/usr/bin/env python3
"""Smoke-check public user workflows from an installed Query Doctor wheel."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]
INSTALLED_BIN_ENV = "QUERY_DOCTOR_INSTALLED_CLI_BIN"
ONE_PROFILE_SMOKE_SCRIPT = "scripts/installed_one_profile_smoke.py"
DEFAULT_QUERY_ID = "1111111111111111:2222222222222222"
PROFILE_FIXTURE = ROOT / "tests" / "fixtures" / "mixed_stats_runtime_case" / "profile_digest.md"
OPTIMIZER_FIXTURE = (
    ROOT / "tests" / "fixtures" / "optimizer_cases" / "single_cte_predicate_pushdown"
)
ENGINE_FIXTURE_DIR = ROOT / "tests" / "fixtures" / "engine_facts"
SPARK_EVENTLOG_FIXTURE = ENGINE_FIXTURE_DIR / "spark_history_eventlog_compact.json"
SPARK_HISTORY_SERVER_FIXTURE = (
    ENGINE_FIXTURE_DIR / "spark_history_server_compact_source_warning.json"
)
TRINO_QUERY_DETAIL_FIXTURE = ENGINE_FIXTURE_DIR / "trino_query_detail_export.json"

FORBIDDEN_SQL_EXECUTION_FLAGS = (
    "--execute-sql",
    "--run-sql",
    "--apply-sql",
    "--execute-query",
    "--allow-sql-execution",
)
SPARK_EXPERIMENTAL_SCRIPTS = frozenset(
    {
        "query-doctor-build-spark-evidence-package",
        "query-doctor-collect-spark-history",
        "query-doctor-diagnose-spark-compact",
        "query-doctor-export-spark-evidence-fixtures",
        "query-doctor-validate-spark-evidence-package",
    }
)
WORKFLOW_COMMANDS = (
    "query-doctor-analyze",
    "query-doctor-web",
    "query-doctor-report",
    "query-doctor-pipeline",
    "query-doctor-optimize-query",
    "query-doctor-corpus-smoke",
    "query-doctor-demo",
    "query-doctor-demo-preflight",
    "query-doctor-batch-recent",
    "query-doctor-collect-cm-profiles",
    "query-doctor-collect-impala-context",
    "query-doctor-collect-impala-profile",
    "query-doctor-trino-query-detail-import",
    "query-doctor-diagnose-trino-compact",
    "query-doctor-diagnose-spark-compact",
    "query-doctor-build-spark-evidence-package",
    "query-doctor-validate-spark-evidence-package",
)
SECRET_ENV_PREFIXES = ("CM_",)
SECRET_ENV_NAMES = {
    "KRB5CCNAME",
    "QD_CM_ENV",
    "QD_CONFIG",
    "QD_LLM_API_KEY",
    "QD_OPTIMIZER_LLM_API_KEY",
    "QD_REPORT_LLM_API_KEY",
}


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
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
        "--timeout-sec",
        type=float,
        default=180.0,
        help="Per-command timeout in seconds. Default: %(default)s",
    )
    parser.add_argument(
        "--query-id",
        default=DEFAULT_QUERY_ID,
        help="Synthetic Impala query ID used by installed user-path smokes.",
    )
    return parser.parse_args(argv)


def project_scripts() -> tuple[str, ...]:
    scripts: list[str] = []
    in_scripts = False
    for line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "[project.scripts]":
            in_scripts = True
            continue
        if in_scripts and stripped.startswith("["):
            break
        if in_scripts and stripped and not stripped.startswith("#") and "=" in stripped:
            scripts.append(stripped.split("=", 1)[0].strip())
    return tuple(scripts)


def installed_executable(bin_dir: Path, name: str) -> Path:
    candidates = (bin_dir / name, bin_dir / f"{name}.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(f"installed executable not found in {bin_dir}: {name}")


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


def run_command(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_sec: float,
    label: str,
    expected_returncode: int = 0,
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
    if result.returncode != expected_returncode:
        print(
            f"[installed-user-paths-smoke] {label} failed with exit {result.returncode}: {cmd}",
            file=sys.stderr,
        )
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode or 1)
    return result


def assert_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise SystemExit(f"[installed-user-paths-smoke] missing {label}: {path}")


def assert_json_field(path: Path, key: str, expected: object, label: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    actual = payload.get(key) if isinstance(payload, dict) else None
    if actual != expected:
        raise SystemExit(f"[installed-user-paths-smoke] unexpected {label}: {key}={actual!r}")


def print_ok(label: str) -> None:
    print(f"[installed-user-paths-smoke] {label}: ok")


def prepare_profile(destination: Path, query_id: str) -> None:
    profile = PROFILE_FIXTURE.read_text(encoding="utf-8")
    destination.write_text(
        f"Query Runtime Profile\nQuery ID: {query_id}\n\n{profile}",
        encoding="utf-8",
    )


def smoke_help_contract(
    bin_dir: Path, work_dir: Path, env: dict[str, str], timeout_sec: float
) -> None:
    scripts = project_scripts()
    if not scripts:
        raise SystemExit("[installed-user-paths-smoke] no project scripts found")
    missing_workflow_commands = sorted(set(WORKFLOW_COMMANDS) - set(scripts))
    if missing_workflow_commands:
        raise SystemExit(
            "[installed-user-paths-smoke] workflow command missing from project scripts: "
            + ", ".join(missing_workflow_commands)
        )
    for name in scripts:
        script = installed_executable(bin_dir, name)
        result = run_command(
            [str(script), "--help"],
            cwd=work_dir,
            env=env,
            timeout_sec=timeout_sec,
            label=f"{name} --help",
        )
        output = result.stdout + result.stderr
        normalized_output = " ".join(output.split())
        if "Traceback" in output or "No module named" in output:
            raise SystemExit(f"[installed-user-paths-smoke] unsafe help output for {name}")
        if name in SPARK_EXPERIMENTAL_SCRIPTS and (
            "does not claim Spark product support" not in normalized_output
        ):
            raise SystemExit(
                f"[installed-user-paths-smoke] Spark help omits no-support wording: {name}"
            )
        for flag in FORBIDDEN_SQL_EXECUTION_FLAGS:
            if flag in output:
                raise SystemExit(
                    f"[installed-user-paths-smoke] help exposes forbidden SQL flag {flag}: {name}"
                )
    print_ok("installed console help contract")


def smoke_one_profile_quickstart(
    bin_dir: Path,
    work_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
    query_id: str,
) -> Path:
    one_profile_dir = work_dir / "one-profile"
    run_command(
        [
            sys.executable,
            str(ROOT / ONE_PROFILE_SMOKE_SCRIPT),
            "--bin-dir",
            str(bin_dir),
            "--work-dir",
            str(one_profile_dir),
            "--timeout-sec",
            str(timeout_sec),
            "--query-id",
            query_id,
        ],
        cwd=ROOT,
        env=env,
        timeout_sec=timeout_sec,
        label="installed one-profile quickstart",
    )
    case_dir = one_profile_dir / "cli-corpus" / query_id.replace(":", "_")
    for name in ("analysis_facts.md", "analysis.json", "cm_metadata.json", "profile_digest.md"):
        assert_file(case_dir / name, f"one-profile {name}")
    print_ok("one-profile Quickstart and web inbox path")
    return case_dir


def copy_case(source: Path, destination: Path) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return destination


def smoke_case_commands(
    bin_dir: Path,
    work_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
    source_case: Path,
) -> None:
    report_case = copy_case(source_case, work_dir / "report-case")
    report = installed_executable(bin_dir, "query-doctor-report")
    run_command(
        [
            str(report),
            str(report_case),
            "--no-llm",
            "--out",
            "diagnosis_cli.md",
            "--validation-mode",
            "strict",
        ],
        cwd=work_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="installed report no-llm",
    )
    assert_file(report_case / "diagnosis_cli.md", "installed report output")

    pipeline_case = copy_case(source_case, work_dir / "pipeline-case")
    pipeline = installed_executable(bin_dir, "query-doctor-pipeline")
    run_command(
        [str(pipeline), str(pipeline_case), "--no-llm", "--out", "diagnosis_pipeline.md"],
        cwd=work_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="installed pipeline no-llm",
    )
    assert_file(pipeline_case / "diagnosis_pipeline.md", "installed pipeline report output")

    corpus_smoke = installed_executable(bin_dir, "query-doctor-corpus-smoke")
    corpus_summary = work_dir / "corpus-smoke.json"
    run_command(
        [
            str(corpus_smoke),
            str(source_case.parent),
            "--json-out",
            str(corpus_summary),
            "--fail-on-analyzer-error",
            "--fail-on-banned-phrases",
        ],
        cwd=work_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="installed corpus smoke",
    )
    assert_file(corpus_summary, "installed corpus smoke summary")
    print_ok("report, pipeline, and corpus smoke CLI paths")


def smoke_optimizer(
    bin_dir: Path,
    work_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
) -> None:
    case_dir = work_dir / "optimizer-case"
    case_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OPTIMIZER_FIXTURE / "analysis_facts.md", case_dir / "analysis_facts.md")
    shutil.copyfile(OPTIMIZER_FIXTURE / "source.sql", case_dir / "original_query.sql")
    optimizer = installed_executable(bin_dir, "query-doctor-optimize-query")
    run_command(
        [
            str(optimizer),
            str(case_dir),
            "--no-llm",
            "--source-visibility",
            "safe",
        ],
        cwd=work_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="installed optimizer recommendations",
    )
    assert_file(case_dir / "optimized_query_recommendations.md", "optimizer recommendations")
    marker = case_dir / "optimized_query.validated.json"
    assert_file(marker, "optimizer validation marker")
    assert_json_field(marker, "validated", True, "optimizer marker")
    print_ok("optimizer deterministic safe recommendations path")


def smoke_demo(
    bin_dir: Path,
    work_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
) -> None:
    demo = installed_executable(bin_dir, "query-doctor-demo")
    preflight = installed_executable(bin_dir, "query-doctor-demo-preflight")
    demo_dir = work_dir / "query-doctor-demo-pack"
    run_command(
        [str(preflight), "--repo", str(ROOT)],
        cwd=work_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="installed demo preflight",
    )
    run_command(
        [str(demo), "--out", str(demo_dir), "--overwrite"],
        cwd=work_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="installed demo pack",
    )
    assert_file(demo_dir / "batch_summary.json", "installed demo batch summary")
    print_ok("public demo generation path")


class FakeImpalaHandler(BaseHTTPRequestHandler):
    query_id = DEFAULT_QUERY_ID
    profile_text = ""

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        parsed = urlsplit(self.path)
        if parsed.path == "/queries":
            self._send_json(self.query_list_payload())
            return
        if parsed.path == "/query_profile":
            query = parse_qs(parsed.query)
            requested = query.get("query_id", [""])[0]
            if requested != self.query_id:
                self._send_text("Could not find query", status=404)
                return
            self._send_text(self.profile_text)
            return
        if parsed.path == "/metrics":
            self._send_json(
                {
                    "metrics": [
                        {
                            "name": "impala-server.version",
                            "value": "impalad version 4.5.0 RELEASE",
                        }
                    ]
                }
            )
            return
        if parsed.path == "/":
            self._send_text(
                "<html><body>Apache Impala impalad version 4.5.0 RELEASE"
                "<br>Impala Server Mode: coordinator</body></html>"
            )
            return
        self._send_text("not found", status=404)

    @classmethod
    def query_list_payload(cls) -> dict[str, object]:
        end_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        return {
            "completed_queries": [
                {
                    "query_id": cls.query_id,
                    "stmt": "SELECT 1",
                    "user": "installed_smoke",
                    "pool": "root.default",
                    "duration_ms": 120000,
                    "end_time": end_time,
                    "query_type": "QUERY",
                }
            ]
        }

    def _send_json(self, payload: Any, *, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, text: str, *, status: int = 200) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class FakeImpalaServer:
    def __init__(self, profile_text: str, query_id: str) -> None:
        FakeImpalaHandler.profile_text = profile_text
        FakeImpalaHandler.query_id = query_id
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeImpalaHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def host_arg(self) -> str:
        host, port = self.server.server_address
        return f"{host}:{port}"

    def __enter__(self) -> "FakeImpalaServer":
        self.thread.start()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()


def smoke_direct_impala(
    bin_dir: Path,
    work_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
    query_id: str,
) -> None:
    profile_path = work_dir / "direct-impala-profile.txt"
    prepare_profile(profile_path, query_id)
    profile_text = profile_path.read_text(encoding="utf-8")
    with FakeImpalaServer(profile_text, query_id) as server:
        batch = installed_executable(bin_dir, "query-doctor-batch-recent")
        batch_out = work_dir / "query-doctor-direct-impala-batch"
        run_command(
            [
                str(batch),
                "--query-profile-source",
                "impala",
                "--impala-profile-host",
                server.host_arg,
                "--out",
                str(batch_out),
                "--cm-inspect-limit",
                "5",
                "--from-time",
                "2000-01-01T00:00:00Z",
                "--to-time",
                "2999-01-01T00:00:00Z",
                "--triage-profile-limit",
                "1",
                "--metadata-mode",
                "off",
                "--top-reports",
                "0",
                "--discover-only",
                "--overwrite",
                "--no-min-duration-filter",
            ],
            cwd=work_dir,
            env=env,
            timeout_sec=timeout_sec,
            label="installed direct Impala recent discover-only",
        )
        summary = batch_out / "batch_summary.json"
        assert_file(summary, "direct Impala batch summary")
        summary_payload = json.loads(summary.read_text(encoding="utf-8"))
        if summary_payload.get("discovery_failed") is not False:
            raise SystemExit("[installed-user-paths-smoke] direct Impala discovery failed")
        if summary_payload.get("summaries_inspected") != 1:
            raise SystemExit("[installed-user-paths-smoke] direct Impala discovery count mismatch")
        if summary_payload.get("selected_count") != 1:
            raise SystemExit("[installed-user-paths-smoke] direct Impala selection count mismatch")

        collector = installed_executable(bin_dir, "query-doctor-collect-impala-profile")
        profile_out = work_dir / "query-doctor-direct-impala-profile-corpus"
        run_command(
            [
                str(collector),
                "--query-id",
                query_id,
                "--host",
                server.host_arg,
                "--timeout-sec",
                "5",
                "--out",
                str(profile_out),
                "--redact",
                "--redact-identifiers",
                "--collect-profile-docs",
                "--collect-admission-context",
            ],
            cwd=work_dir,
            env=env,
            timeout_sec=timeout_sec,
            label="installed direct Impala profile collection",
        )
        case_dir = profile_out / query_id.replace(":", "_")
        for name in ("profile_digest.md", "query_metadata.json"):
            assert_file(case_dir / name, f"direct Impala {name}")
        metadata = json.loads((case_dir / "query_metadata.json").read_text(encoding="utf-8"))
        if metadata.get("profile_source") != "impala_daemon":
            raise SystemExit("[installed-user-paths-smoke] direct Impala profile source mismatch")
    print_ok("direct Impala discover-only and profile collection paths")


def smoke_cm_dry_run(
    bin_dir: Path,
    work_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
) -> None:
    collector = installed_executable(bin_dir, "query-doctor-collect-cm-profiles")
    output_dir = work_dir / "cm-dry-run-corpus"
    result = run_command(
        [
            str(collector),
            "--cm-url",
            "https://cm.example.invalid:7183",
            "--cluster",
            "CLUSTER_NAME",
            "--service",
            "IMPALA_SERVICE_NAME",
            "--out",
            str(output_dir),
            "--dry-run",
        ],
        cwd=work_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="installed CM collector dry-run",
    )
    if "No CM API calls are performed in dry-run mode." not in result.stdout:
        raise SystemExit("[installed-user-paths-smoke] CM dry-run did not confirm no API calls")
    if output_dir.exists():
        raise SystemExit("[installed-user-paths-smoke] CM dry-run wrote an output directory")
    print_ok("CM collector dry-run path")


def smoke_impala_metadata_dry_run(
    bin_dir: Path,
    work_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
) -> None:
    collector = installed_executable(bin_dir, "query-doctor-collect-impala-context")
    out_dir = work_dir / "metadata-dry-run"
    run_command(
        [
            str(collector),
            "--table",
            "default.sample_orders",
            "--out",
            str(out_dir),
            "--dry-run",
            "--redact",
            "--redact-identifiers",
        ],
        cwd=work_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="installed Impala metadata dry-run",
    )
    print_ok("Impala metadata dry-run path")


def smoke_trino_compact(
    bin_dir: Path,
    work_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
) -> None:
    importer = installed_executable(bin_dir, "query-doctor-trino-query-detail-import")
    boundary = work_dir / "trino-query-detail-boundary.json"
    result = run_command(
        [
            str(importer),
            "--redaction-reviewed",
            "--format",
            "boundary-json",
            str(TRINO_QUERY_DETAIL_FIXTURE),
        ],
        cwd=work_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="installed Trino query-detail import",
    )
    import_payload = json.loads(result.stdout)
    query_detail_boundary = import_payload.get("query_detail_boundary")
    if not isinstance(query_detail_boundary, dict):
        raise SystemExit("[installed-user-paths-smoke] Trino import did not emit a boundary")
    boundary.write_text(json.dumps(query_detail_boundary, sort_keys=True), encoding="utf-8")
    diagnose = installed_executable(bin_dir, "query-doctor-diagnose-trino-compact")
    diagnosis = work_dir / "trino-diagnosis.json"
    run_command(
        [str(diagnose), "--boundary-json", str(boundary), "--diagnosis-out", str(diagnosis)],
        cwd=work_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="installed Trino compact diagnosis",
    )
    assert_json_field(diagnosis, "schema_version", "trino_compact_diagnosis_v1", "Trino diagnosis")
    print_ok("Trino local compact import and diagnosis paths")


def smoke_spark_compact(
    bin_dir: Path,
    work_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
) -> None:
    diagnose = installed_executable(bin_dir, "query-doctor-diagnose-spark-compact")
    diagnosis = work_dir / "spark-diagnosis.json"
    boundary = work_dir / "spark-boundary.json"
    run_command(
        [
            str(diagnose),
            "--compact-json",
            str(SPARK_EVENTLOG_FIXTURE),
            "--diagnosis-out",
            str(diagnosis),
            "--boundary-facts-out",
            str(boundary),
        ],
        cwd=work_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="installed Spark compact diagnosis",
    )
    assert_json_field(diagnosis, "schema_version", "spark_compact_diagnosis_v1", "Spark diagnosis")
    assert_json_field(boundary, "schema_version", "engine_fact_boundary_v1", "Spark boundary")

    package = work_dir / "spark-compact-package.json"
    builder = installed_executable(bin_dir, "query-doctor-build-spark-evidence-package")
    run_command(
        [
            str(builder),
            "--out",
            str(package),
            "--package-id",
            "installed_smoke_spark_compact_pkg",
            "--prepared-date-utc",
            "2026-06-14",
            "--known-omission",
            "no_streaming_coverage",
            "--unsupported-source",
            "raw_event_logs",
            "--synthetic-rejection",
            "oversized_or_over_deep_rejection_synthetic:1",
            "--synthetic-rejection",
            "unsafe_raw_field_rejection_synthetic:1",
            "--redaction-reviewed",
            "--sentinel-tests-passed",
            "--partial-ok",
            "--sample",
            f"finished_sql_exact_linkage:spark_eventlog_compact:{SPARK_EVENTLOG_FIXTURE}",
            "--sample",
            (
                "missing_or_partial_history_server_endpoint:"
                f"spark_history_server_compact:{SPARK_HISTORY_SERVER_FIXTURE}"
            ),
        ],
        cwd=work_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="installed Spark evidence package build",
    )
    assert_file(package, "Spark evidence package")
    validator = installed_executable(bin_dir, "query-doctor-validate-spark-evidence-package")
    result = run_command(
        [str(validator), str(package), "--partial-ok", "--summary-json"],
        cwd=work_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="installed Spark evidence package validation",
    )
    summary = json.loads(result.stdout)
    if summary.get("package_id") != "installed_smoke_spark_compact_pkg":
        raise SystemExit("[installed-user-paths-smoke] Spark package summary mismatch")
    print_ok("Spark compact diagnosis and evidence-package build/validate paths")


def run_smoke(args: argparse.Namespace, work_dir: Path) -> None:
    if not args.bin_dir:
        raise SystemExit(f"--bin-dir or ${INSTALLED_BIN_ENV} is required")
    bin_dir = Path(args.bin_dir).expanduser().resolve()
    installed_executable(bin_dir, "python")
    env = clean_env(bin_dir, work_dir / "home")
    (work_dir / "home").mkdir(parents=True, exist_ok=True)

    smoke_help_contract(bin_dir, work_dir, env, args.timeout_sec)
    source_case = smoke_one_profile_quickstart(
        bin_dir, work_dir, env, args.timeout_sec, args.query_id
    )
    smoke_case_commands(bin_dir, work_dir, env, args.timeout_sec, source_case)
    smoke_optimizer(bin_dir, work_dir, env, args.timeout_sec)
    smoke_demo(bin_dir, work_dir, env, args.timeout_sec)
    smoke_cm_dry_run(bin_dir, work_dir, env, args.timeout_sec)
    smoke_impala_metadata_dry_run(bin_dir, work_dir, env, args.timeout_sec)
    smoke_direct_impala(bin_dir, work_dir, env, args.timeout_sec, args.query_id)
    smoke_trino_compact(bin_dir, work_dir, env, args.timeout_sec)
    smoke_spark_compact(bin_dir, work_dir, env, args.timeout_sec)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    if args.work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="query-doctor-installed-user-paths-"))
        cleanup = not args.keep_work_dir
    else:
        work_dir = args.work_dir.expanduser().resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        cleanup = False
    try:
        run_smoke(args, work_dir)
    finally:
        if cleanup:
            shutil.rmtree(work_dir, ignore_errors=True)
        elif args.keep_work_dir or args.work_dir is not None:
            print(f"[installed-user-paths-smoke] work dir: {work_dir}")
    print_ok("installed user paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
