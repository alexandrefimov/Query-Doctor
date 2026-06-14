#!/usr/bin/env python3
"""Smoke-check sanitized Impala Web UI exports through an installed wheel."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from installed_web_e2e_smoke import (
    WebE2EFailure,
    clean_env,
    fetch,
    installed_executable,
    require_page,
    run_command,
    safe_output_snippet,
    stop_process,
    wait_for_ready,
)

ROOT = Path(__file__).resolve().parents[1]
INSTALLED_BIN_ENV = "QUERY_DOCTOR_INSTALLED_CLI_BIN"
DEFAULT_FIXTURE_DIR = ROOT / "tests" / "fixtures" / "impala_web_ui_exports"
MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class ProfileFixture:
    filename: str
    query_id: str
    query_id_source: str
    expected_operator_count: int
    description: str

    @property
    def slug(self) -> str:
        return self.query_id.replace(":", "_")


class InstalledExportsSmokeFailure(RuntimeError):
    """Safe installed-smoke failure."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bin-dir",
        default=os.environ.get(INSTALLED_BIN_ENV),
        help=f"Directory containing installed Query Doctor console scripts. Defaults to ${INSTALLED_BIN_ENV}.",
    )
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=DEFAULT_FIXTURE_DIR,
        help="Sanitized Impala Web UI export fixture directory. Default: %(default)s",
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


def load_manifest(fixture_dir: Path) -> list[ProfileFixture]:
    manifest_path = fixture_dir / MANIFEST_NAME
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstalledExportsSmokeFailure("fixture manifest is missing or invalid") from exc
    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    if not isinstance(profiles, list) or not profiles:
        raise InstalledExportsSmokeFailure("fixture manifest does not list profiles")

    parsed: list[ProfileFixture] = []
    for item in profiles:
        if not isinstance(item, dict):
            raise InstalledExportsSmokeFailure("fixture manifest profile is not an object")
        try:
            fixture = ProfileFixture(
                filename=str(item["filename"]),
                query_id=str(item["query_id"]),
                query_id_source=str(item["query_id_source"]),
                expected_operator_count=int(item["expected_operator_count"]),
                description=str(item.get("description") or ""),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InstalledExportsSmokeFailure("fixture manifest profile is incomplete") from exc
        if not (fixture_dir / fixture.filename).is_file():
            raise InstalledExportsSmokeFailure(f"fixture profile is missing: {fixture.filename}")
        parsed.append(fixture)
    return parsed


def analyze_profile_exports(
    *,
    analyze: Path,
    fixtures: list[ProfileFixture],
    fixture_dir: Path,
    corpus_dir: Path,
    work_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for fixture in fixtures:
        profile_path = fixture_dir / fixture.filename
        run_command(
            [
                str(analyze),
                "--profile-text",
                str(profile_path),
                "--out",
                str(corpus_dir),
                "--redact-identifiers",
            ],
            cwd=work_dir,
            env=env,
            timeout_sec=timeout_sec,
            label=f"query-doctor-analyze {fixture.filename}",
        )
        case_dir = corpus_dir / fixture.slug
        for filename in (
            "analysis_facts.md",
            "analysis.json",
            "query_metadata.json",
            "cm_metadata.json",
            "profile_digest.md",
            "collection_warnings.txt",
        ):
            if not (case_dir / filename).is_file():
                raise InstalledExportsSmokeFailure(f"{fixture.filename} did not write {filename}")
        analysis = json.loads((case_dir / "analysis.json").read_text(encoding="utf-8"))
        metadata = json.loads((case_dir / "query_metadata.json").read_text(encoding="utf-8"))
        operators = analysis.get("operators")
        operator_count = len(operators) if isinstance(operators, list) else -1
        if operator_count != fixture.expected_operator_count:
            raise InstalledExportsSmokeFailure(
                f"{fixture.filename} parsed {operator_count} operators; "
                f"expected {fixture.expected_operator_count}"
            )
        if metadata.get("query_id") != fixture.query_id:
            raise InstalledExportsSmokeFailure(f"{fixture.filename} query ID mismatch")
        if metadata.get("profile_query_id_source") != fixture.query_id_source:
            raise InstalledExportsSmokeFailure(f"{fixture.filename} Query ID source mismatch")
        results.append(
            {
                "filename": fixture.filename,
                "query_id": fixture.query_id,
                "operator_count": operator_count,
                "query_id_source": fixture.query_id_source,
            }
        )
    return results


def smoke_corpus_cli(
    *,
    corpus_smoke: Path,
    corpus_dir: Path,
    work_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
    expected_case_count: int,
) -> None:
    summary_path = work_dir / "impala-web-ui-exports-corpus-smoke.json"
    run_command(
        [
            str(corpus_smoke),
            str(corpus_dir),
            "--keep-generated",
            "--json-out",
            str(summary_path),
            "--fail-on-analyzer-error",
            "--fail-on-banned-phrases",
        ],
        cwd=work_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="query-doctor-corpus-smoke",
    )
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstalledExportsSmokeFailure("corpus smoke summary was not written") from exc
    totals = payload.get("totals") if isinstance(payload, dict) else None
    if not isinstance(totals, dict):
        raise InstalledExportsSmokeFailure("corpus smoke summary is missing totals")
    if totals.get("cases_scanned") != expected_case_count:
        raise InstalledExportsSmokeFailure("corpus smoke scanned an unexpected case count")
    if totals.get("analyzer_failed") != 0:
        raise InstalledExportsSmokeFailure("corpus smoke reported analyzer failures")


def free_local_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, 0))
        except OSError as exc:
            raise InstalledExportsSmokeFailure("local web server port allocation failed") from exc
        return int(sock.getsockname()[1])


def browser_forbidden_text(
    *,
    work_dir: Path,
    fixture_dir: Path,
    corpus_dir: Path,
    fixtures: list[ProfileFixture],
) -> tuple[str, ...]:
    return (
        "Query Runtime Profile",
        "Sql Statement:",
        "ExecSummary:",
        str(work_dir),
        str(fixture_dir),
        str(corpus_dir),
        "analysis.json",
        "profile_digest.md",
        "query_metadata.json",
        "cm_metadata.json",
        "collection_warnings.txt",
        *(fixture.filename for fixture in fixtures),
    )


def smoke_web_render(
    *,
    web: Path,
    fixtures: list[ProfileFixture],
    fixture_dir: Path,
    corpus_dir: Path,
    work_dir: Path,
    env: dict[str, str],
    host: str,
    port_arg: int | None,
    timeout_sec: float,
) -> None:
    launch_dir = work_dir / "web-launch"
    launch_dir.mkdir(parents=True, exist_ok=True)
    port = port_arg or free_local_port(host)
    try:
        process = subprocess.Popen(
            [
                str(web),
                "--host",
                host,
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
    except OSError as exc:
        raise InstalledExportsSmokeFailure("installed web server could not start") from exc
    stdout = ""
    stderr = ""
    try:
        wait_for_ready(process, host=host, port=port, timeout_sec=timeout_sec)
        forbidden = browser_forbidden_text(
            work_dir=work_dir,
            fixture_dir=fixture_dir,
            corpus_dir=corpus_dir,
            fixtures=fixtures,
        )
        expected_query_ids = tuple(fixture.query_id for fixture in fixtures)
        require_page(
            fetch(host, port, "/"),
            label="GET /",
            expected=("Exported Profiles", "All analyzed", *expected_query_ids),
            forbidden=forbidden,
        )
        for index, fixture in enumerate(sorted(fixtures, key=lambda item: item.slug), start=1):
            require_page(
                fetch(host, port, f"/batch/case/case-{index:03d}"),
                label=f"GET /batch/case/case-{index:03d}",
                expected=('id="case-overview"', fixture.query_id),
                forbidden=forbidden,
            )
            require_page(
                fetch(host, port, f"/query/details/{quote(fixture.query_id, safe='')}"),
                label=f"GET /query/details/{fixture.slug}",
                expected=("Known Query ID details", fixture.query_id),
                forbidden=forbidden,
            )
    finally:
        stdout, stderr = stop_process(process)

    if process.returncode not in {0, -15, -9, 143}:
        detail = safe_output_snippet(stderr) or safe_output_snippet(stdout)
        raise InstalledExportsSmokeFailure(f"installed web server exited unexpectedly: {detail}")


def run_smoke(args: argparse.Namespace, work_dir: Path) -> None:
    if not args.bin_dir:
        raise InstalledExportsSmokeFailure(f"--bin-dir or ${INSTALLED_BIN_ENV} is required")
    if args.port is not None and not (0 < args.port <= 65535):
        raise InstalledExportsSmokeFailure("--port must be between 1 and 65535")

    bin_dir = Path(args.bin_dir).expanduser().resolve()
    fixture_dir = args.fixture_dir.expanduser().resolve()
    fixtures = load_manifest(fixture_dir)
    analyze = installed_executable(bin_dir, "query-doctor-analyze")
    corpus_smoke = installed_executable(bin_dir, "query-doctor-corpus-smoke")
    web = installed_executable(bin_dir, "query-doctor-web")
    env = clean_env(bin_dir, work_dir / "home")
    (work_dir / "home").mkdir(parents=True, exist_ok=True)

    corpus_dir = work_dir / "cases" / "cm-corpus"
    profile_results = analyze_profile_exports(
        analyze=analyze,
        fixtures=fixtures,
        fixture_dir=fixture_dir,
        corpus_dir=corpus_dir,
        work_dir=work_dir,
        env=env,
        timeout_sec=args.timeout_sec,
    )
    smoke_corpus_cli(
        corpus_smoke=corpus_smoke,
        corpus_dir=corpus_dir,
        work_dir=work_dir,
        env=env,
        timeout_sec=args.timeout_sec,
        expected_case_count=len(fixtures),
    )
    smoke_web_render(
        web=web,
        fixtures=fixtures,
        fixture_dir=fixture_dir,
        corpus_dir=corpus_dir,
        work_dir=work_dir,
        env=env,
        host=args.host,
        port_arg=args.port,
        timeout_sec=args.timeout_sec,
    )

    print(
        json.dumps(
            {
                "schema_version": "query_doctor_installed_impala_web_ui_exports_smoke_v1",
                "status": "OK",
                "case_count": len(fixtures),
                "profiles": profile_results,
                "filename_fallback_checked": any(
                    fixture.query_id_source == "impala_web_profile_filename"
                    and fixture.expected_operator_count > 0
                    for fixture in fixtures
                ),
                "zero_operator_profile_checked": any(
                    fixture.expected_operator_count == 0 for fixture in fixtures
                ),
                "corpus_smoke_checked": True,
                "real_web_server": True,
                "external_services_used": False,
                "llm_used": False,
            },
            sort_keys=True,
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="query-doctor-installed-impala-web-ui-"))
        cleanup = not args.keep_work_dir
    else:
        work_dir = args.work_dir.expanduser().resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        cleanup = False
    try:
        run_smoke(args, work_dir)
    except (InstalledExportsSmokeFailure, WebE2EFailure) as exc:
        print(f"[installed-impala-web-ui-exports-smoke] FAILED: {exc}", file=sys.stderr)
        if not cleanup:
            print(f"[installed-impala-web-ui-exports-smoke] work dir: {work_dir}", file=sys.stderr)
        return 1
    finally:
        if cleanup:
            shutil.rmtree(work_dir, ignore_errors=True)
        elif args.keep_work_dir or args.work_dir is not None:
            print(f"[installed-impala-web-ui-exports-smoke] work dir: {work_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
