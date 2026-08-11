#!/usr/bin/env python3
"""Smoke-check the public README Quickstart through installed console scripts."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from installed_web_e2e_smoke import (
    WebE2EFailure,
    clean_env,
    fetch,
    free_local_port,
    installed_executable,
    require_page,
    run_command,
    safe_output_snippet,
    stop_process,
    wait_for_ready,
)
from smoke_workdir import SmokeWorkDirError, prepare_smoke_work_dir


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUERY_ID = "1111111111111111:2222222222222222"
DEFAULT_PROFILE_TEXT = (
    ROOT / "tests" / "fixtures" / "mixed_stats_runtime_case" / "profile_digest.md"
)
INSTALLED_BIN_ENV = "QUERY_DOCTOR_INSTALLED_CLI_BIN"
README_PROFILE_NAME = "your-profile.txt"
README_PROFILE_ARG = "./your-profile.txt"
README_CORPUS_ARG = "cases/cm-corpus"
README_CORPUS_DIR = Path(README_CORPUS_ARG)
REQUIRED_SELF_TEST_CHECKS = frozenset(
    {
        "console_scripts",
        "demo",
        "profile_analysis",
        "filename_fallback_profile",
        "web_rendering",
        "report",
        "corpus_smoke",
    }
)


class ReadmeQuickstartSmokeFailure(RuntimeError):
    """Safe README Quickstart smoke failure."""


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
        help="Synthetic exported Impala text profile body to use in the README workspace.",
    )
    parser.add_argument(
        "--query-id",
        default=DEFAULT_QUERY_ID,
        help="Query ID to inject into the README Quickstart profile. Default: %(default)s",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Optional temporary README workspace. A fresh temporary directory is used by default.",
    )
    parser.add_argument(
        "--keep-work-dir",
        action="store_true",
        help="Keep the temporary README workspace for debugging.",
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
        default=180.0,
        help="Per-step timeout in seconds. Default: %(default)s",
    )
    return parser.parse_args(argv)


def write_readme_profile(source: Path, destination: Path, *, query_id: str) -> None:
    if not source.is_file():
        raise ReadmeQuickstartSmokeFailure("synthetic profile fixture is missing")
    profile_text = source.read_text(encoding="utf-8")
    destination.write_text(
        f"Query Runtime Profile\nQuery ID: {query_id}\n\n{profile_text}",
        encoding="utf-8",
    )


def readme_clean_env(bin_dir: Path, home_dir: Path) -> dict[str, str]:
    env = clean_env(bin_dir, home_dir)
    env.pop("PYTHONPATH", None)
    for name in list(env):
        if name.startswith("CM_"):
            env.pop(name, None)
    return env


def run_self_test(
    *,
    self_test: Path,
    quickstart_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
) -> list[str]:
    result = run_command(
        [
            str(self_test),
            "--work-dir",
            "query-doctor-self-test-work",
            "--timeout-sec",
            str(timeout_sec),
            "--json",
        ],
        cwd=quickstart_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="README query-doctor-self-test",
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReadmeQuickstartSmokeFailure("self-test did not emit JSON") from exc
    if payload.get("status") != "OK":
        raise ReadmeQuickstartSmokeFailure("self-test did not pass")
    checks = payload.get("checks")
    if not isinstance(checks, list):
        raise ReadmeQuickstartSmokeFailure("self-test summary is missing checks")
    check_ids = [str(check.get("id")) for check in checks if isinstance(check, dict)]
    missing = sorted(REQUIRED_SELF_TEST_CHECKS - set(check_ids))
    if missing:
        raise ReadmeQuickstartSmokeFailure("self-test omitted required checks")
    return check_ids


def run_analyze_quickstart(
    *,
    analyze: Path,
    quickstart_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
    query_id: str,
) -> Path:
    run_command(
        [
            str(analyze),
            "--profile-text",
            README_PROFILE_ARG,
            "--out",
            README_CORPUS_ARG,
        ],
        cwd=quickstart_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="README query-doctor-analyze",
    )
    case_dir = quickstart_dir / README_CORPUS_DIR / query_id.replace(":", "_")
    for filename in (
        "analysis_facts.md",
        "analysis.json",
        "query_metadata.json",
        "profile_digest.md",
    ):
        if not (case_dir / filename).is_file():
            raise ReadmeQuickstartSmokeFailure(f"README analyzer did not write {filename}")
    try:
        analysis = json.loads((case_dir / "analysis.json").read_text(encoding="utf-8"))
        metadata = json.loads((case_dir / "query_metadata.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadmeQuickstartSmokeFailure("README analyzer output was not readable") from exc
    if metadata.get("query_id") != query_id:
        raise ReadmeQuickstartSmokeFailure("README analyzer wrote an unexpected Query ID")
    operators = analysis.get("operators")
    if not isinstance(operators, list) or not operators:
        raise ReadmeQuickstartSmokeFailure("README analyzer did not parse any operators")
    return case_dir


def browser_forbidden_text(
    *, quickstart_dir: Path, corpus_dir: Path, profile_path: Path
) -> tuple[str, ...]:
    return (
        "Query Runtime Profile",
        "Sql Statement:",
        "ExecSummary:",
        str(quickstart_dir),
        str(corpus_dir),
        str(profile_path),
        README_PROFILE_NAME,
        "analysis.json",
        "profile_digest.md",
        "query_metadata.json",
        "cm_metadata.json",
        "collection_warnings.txt",
        "stdout",
        "stderr",
    )


def run_web_quickstart(
    *,
    web: Path,
    quickstart_dir: Path,
    env: dict[str, str],
    host: str,
    port_arg: int | None,
    timeout_sec: float,
    query_id: str,
) -> int:
    bad_default_config = quickstart_dir / "query-doctor-config.json"
    bad_default_config.write_text(
        json.dumps({"future_config_field": True}, sort_keys=True),
        encoding="utf-8",
    )
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
                README_CORPUS_ARG,
            ],
            cwd=quickstart_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise ReadmeQuickstartSmokeFailure("README web server could not start") from exc

    stdout = ""
    stderr = ""
    try:
        wait_for_ready(process, host=host, port=port, timeout_sec=timeout_sec)
        forbidden = browser_forbidden_text(
            quickstart_dir=quickstart_dir,
            corpus_dir=quickstart_dir / README_CORPUS_DIR,
            profile_path=quickstart_dir / README_PROFILE_NAME,
        )
        require_page(
            fetch(host, port, "/"),
            label="README GET /",
            expected=("Exported Profiles", "All analyzed", query_id),
            forbidden=forbidden,
        )
        require_page(
            fetch(host, port, "/batch/case/case-001"),
            label="README GET /batch/case/case-001",
            expected=('id="case-overview"', query_id),
            forbidden=forbidden,
        )
        require_page(
            fetch(host, port, f"/query/details/{quote(query_id, safe='')}"),
            label="README GET /query/details/<query-id>",
            expected=("Known Query ID details", query_id),
            forbidden=forbidden,
        )
    finally:
        stdout, stderr = stop_process(process)

    if process.returncode not in {0, -15, -9, 143}:
        detail = safe_output_snippet(stderr) or safe_output_snippet(stdout)
        raise ReadmeQuickstartSmokeFailure(f"README web server exited unexpectedly: {detail}")
    return port


def run_smoke(args: argparse.Namespace, work_dir: Path) -> None:
    if not args.bin_dir:
        raise ReadmeQuickstartSmokeFailure(f"--bin-dir or ${INSTALLED_BIN_ENV} is required")
    if args.port is not None and not (0 < args.port <= 65535):
        raise ReadmeQuickstartSmokeFailure("--port must be between 1 and 65535")

    bin_dir = Path(args.bin_dir).expanduser().resolve()
    self_test = installed_executable(bin_dir, "query-doctor-self-test")
    analyze = installed_executable(bin_dir, "query-doctor-analyze")
    web = installed_executable(bin_dir, "query-doctor-web")
    env = readme_clean_env(bin_dir, work_dir / "home")
    (work_dir / "home").mkdir(parents=True, exist_ok=True)

    quickstart_dir = work_dir / "readme-quickstart"
    quickstart_dir.mkdir(parents=True, exist_ok=True)
    profile_path = quickstart_dir / README_PROFILE_NAME
    write_readme_profile(
        args.profile_text.expanduser().resolve(),
        profile_path,
        query_id=args.query_id,
    )

    self_test_check_ids = run_self_test(
        self_test=self_test,
        quickstart_dir=quickstart_dir,
        env=env,
        timeout_sec=args.timeout_sec,
    )
    case_dir = run_analyze_quickstart(
        analyze=analyze,
        quickstart_dir=quickstart_dir,
        env=env,
        timeout_sec=args.timeout_sec,
        query_id=args.query_id,
    )
    port = run_web_quickstart(
        web=web,
        quickstart_dir=quickstart_dir,
        env=env,
        host=args.host,
        port_arg=args.port,
        timeout_sec=args.timeout_sec,
        query_id=args.query_id,
    )

    print(
        json.dumps(
            {
                "schema_version": "query_doctor_installed_readme_quickstart_smoke_v1",
                "status": "OK",
                "query_id": args.query_id,
                "self_test_checked": True,
                "self_test_check_ids": self_test_check_ids,
                "analyze_checked": True,
                "case_slug": case_dir.name,
                "real_web_server": True,
                "web_port": port,
                "first_run_exported_profiles_visible": True,
                "search_required": False,
                "relative_profile_path_checked": f"./{README_PROFILE_NAME}",
                "relative_corpus_dir_checked": README_CORPUS_ARG,
                "invalid_default_config_ignored": True,
                "readme_commands_checked": [
                    "query-doctor-self-test",
                    (
                        "query-doctor-analyze --profile-text "
                        f"{README_PROFILE_ARG} --out {README_CORPUS_ARG}"
                    ),
                    f"query-doctor-web --corpus-dir {README_CORPUS_ARG}",
                ],
                "external_services_used": False,
                "llm_used": False,
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
            temp_prefix="query-doctor-installed-readme-",
            protected_roots=(ROOT,),
        )
        work_dir = prepared.path
        run_smoke(args, work_dir)
    except (ReadmeQuickstartSmokeFailure, WebE2EFailure, SmokeWorkDirError) as exc:
        print(f"[installed-readme-quickstart-smoke] FAILED: {exc}", file=sys.stderr)
        if requested_work_dir is not None:
            print(
                f"[installed-readme-quickstart-smoke] work dir: {requested_work_dir}",
                file=sys.stderr,
            )
        return 1
    finally:
        if "prepared" in locals() and prepared.cleanup:
            shutil.rmtree(prepared.path, ignore_errors=True)
        elif "prepared" in locals() and (args.keep_work_dir or args.work_dir is not None):
            print(f"[installed-readme-quickstart-smoke] work dir: {prepared.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
