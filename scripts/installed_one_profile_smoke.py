#!/usr/bin/env python3
"""Smoke-check one-profile intake from an installed Query Doctor wheel."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from smoke_workdir import SmokeWorkDirError, prepare_smoke_work_dir


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUERY_ID = "1111111111111111:2222222222222222"
DEFAULT_PROFILE_TEXT = (
    ROOT / "tests" / "fixtures" / "mixed_stats_runtime_case" / "profile_digest.md"
)
INSTALLED_BIN_ENV = "QUERY_DOCTOR_INSTALLED_CLI_BIN"

INSTALLED_WEB_SMOKE = r"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from urllib.parse import quote

import query_doctor
from query_doctor.cli import web as web_cli
from query_doctor.web.config import build_web_settings, validate_web_startup_config
from query_doctor.web.command_builders import REPORT_VARIANT_PYTHON
from query_doctor.web.job_workers import generate_validated_report_artifact
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.query_analysis import expected_case_dir_for_query, run_query_id_analysis
from query_doctor.web.routes import route_get_request
from query_doctor.web.server_args import parse_args


def path_contains(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


work_dir = Path(os.environ["QD_INSTALLED_SMOKE_WORK"]).resolve()
profile_text = Path(os.environ["QD_INSTALLED_SMOKE_PROFILE"]).resolve()
quickstart_corpus = Path(os.environ["QD_INSTALLED_SMOKE_QUICKSTART_CORPUS"]).resolve()
query_id = os.environ["QD_INSTALLED_SMOKE_QUERY_ID"]
slug = query_id.replace(":", "_")

bad_default_config = work_dir / web_cli.cm_collector.DEFAULT_LOCAL_CONFIG_NAME
bad_default_config.write_text(json.dumps({"future_config_field": True}), encoding="utf-8")

seen_server = {}

class FakeServer:
    def __init__(self, address, handler):
        seen_server["address"] = address
        seen_server["handler"] = handler

    def serve_forever(self):
        raise KeyboardInterrupt

    def server_close(self):
        seen_server["closed"] = True

original_server = web_cli.ThreadingHTTPServer
web_cli.ThreadingHTTPServer = FakeServer
try:
    quickstart_main_result = web_cli.main(["--corpus-dir", str(quickstart_corpus)])
finally:
    web_cli.ThreadingHTTPServer = original_server
if quickstart_main_result != 0 or seen_server.get("closed") is not True:
    raise SystemExit("Quickstart corpus web main did not ignore invalid unused default config")

quickstart_args = parse_args(["--corpus-dir", str(quickstart_corpus)])
quickstart_settings = web_cli.quickstart_corpus_settings_without_default_config(
    quickstart_args,
    work_dir,
)
if quickstart_settings is None:
    raise SystemExit("Quickstart corpus did not produce a web summary")
quickstart_startup_errors = validate_web_startup_config(
    quickstart_settings.config,
    cwd=work_dir,
    env={},
    require_cm=quickstart_settings.batch_summary is None
    and quickstart_settings.corpus_summary is None,
)
if quickstart_startup_errors:
    raise SystemExit(f"Quickstart corpus web startup validation failed: {quickstart_startup_errors}")
store = WebJobStore()
home = route_get_request("/", quickstart_settings, store)
if home is None or home.status != 200:
    status = None if home is None else home.status
    raise SystemExit(f"Quickstart corpus home did not render successfully: {status}")
for expected_text in ("Exported Profiles", "All analyzed", query_id):
    if expected_text not in home.body:
        raise SystemExit(f"Quickstart corpus home is missing expected text: {expected_text!r}")
quickstart_detail = route_get_request("/batch/case/case-001", quickstart_settings, store)
if quickstart_detail is None or quickstart_detail.status != 200:
    status = None if quickstart_detail is None else quickstart_detail.status
    raise SystemExit(f"Quickstart corpus Details did not render successfully: {status}")
for expected_text in ('<section id="case-overview" class="case-verdict"', query_id):
    if expected_text not in quickstart_detail.body:
        raise SystemExit(f"Quickstart corpus Details is missing expected text: {expected_text!r}")
for forbidden_text in ("Query Runtime Profile", str(work_dir), str(quickstart_corpus)):
    if forbidden_text in home.body or forbidden_text in quickstart_detail.body:
        raise SystemExit(f"Quickstart corpus web leaked forbidden text: {forbidden_text!r}")

inbox_dir = work_dir / "profile-inbox"
inbox_dir.mkdir(parents=True, exist_ok=True)
inbox_profile = inbox_dir / f"{slug}.txt"
inbox_profile.write_text(profile_text.read_text(encoding="utf-8"), encoding="utf-8")

config_path = work_dir / "manual-web-config.json"
config_path.write_text(json.dumps({"manual_profile_dir": str(inbox_dir)}), encoding="utf-8")
startup_errors = validate_web_startup_config(config_path, cwd=work_dir, env={})
if startup_errors:
    raise SystemExit(f"manual-only web startup validation failed: {startup_errors}")

settings = build_web_settings(parse_args(["--config", str(config_path), "--no-llm"]), cwd=work_dir)
expected_corpus = work_dir / "cases" / "cm-corpus"
if settings.corpus_dir != expected_corpus:
    raise SystemExit(f"unexpected default corpus_dir: {settings.corpus_dir}")

result = run_query_id_analysis(query_id, "analysis", True, settings)
case_dir = expected_case_dir_for_query(query_id, settings)
if result.query_id != query_id:
    raise SystemExit(f"unexpected query id in web result: {result.query_id}")
if not case_dir.is_dir():
    raise SystemExit("manual inbox analysis did not create the expected case directory")

required_case_files = (
    "analysis.json",
    "analysis_facts.md",
    "cm_metadata.json",
    "profile_digest.md",
)
missing = [name for name in required_case_files if not (case_dir / name).is_file()]
if missing:
    raise SystemExit(f"manual inbox case is missing expected files: {missing}")

store = WebJobStore()
details = route_get_request(f"/query/details/{quote(query_id, safe='')}", settings, store)
if details is None or details.status != 200:
    status = None if details is None else details.status
    raise SystemExit(f"Known Query ID Details did not render successfully: {status}")
for expected_text in ("Known Query ID details", query_id):
    if expected_text not in details.body:
        raise SystemExit(f"Details page is missing expected text: {expected_text!r}")
for forbidden_text in ("Query Runtime Profile", str(work_dir), str(inbox_profile)):
    if forbidden_text in details.body:
        raise SystemExit(f"Details page leaked forbidden text: {forbidden_text!r}")

generate_validated_report_artifact(
    case_dir,
    settings,
    subprocess.run,
    label="installed one-profile smoke",
    report_variant=REPORT_VARIANT_PYTHON,
)
report_path = case_dir / "diagnosis_python.md"
marker_path = case_dir / "diagnosis_python.validated.json"
if not report_path.is_file() or not marker_path.is_file():
    raise SystemExit("Python report smoke did not create a validated report artifact")

report = route_get_request(
    f"/query/details/{quote(query_id, safe='')}/python-report",
    settings,
    store,
)
if report is None or report.status != 200:
    status = None if report is None else report.status
    raise SystemExit(f"Known Query ID Python report did not render successfully: {status}")
if "Query Doctor Report" not in report.body:
    raise SystemExit("Python report page is missing the report title")

package_dir = Path(query_doctor.__file__).resolve().parent
if path_contains(package_dir, case_dir):
    raise SystemExit("manual inbox case was written under the installed package directory")

print(
    json.dumps(
        {
            "case_under_package_dir": False,
            "corpus_default": "launch_dir",
            "quickstart_corpus_home_rendered": True,
            "quickstart_corpus_details_rendered": True,
            "quickstart_corpus_invalid_default_config_ignored": True,
            "details_rendered": True,
            "python_report_validated": True,
            "score": result.case.get("score"),
        },
        sort_keys=True,
    )
)
"""


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
        "--replace-work-dir",
        action="store_true",
        help=(
            "Remove an existing non-empty --work-dir before running. Requires a "
            "query-doctor-* work directory."
        ),
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=120.0,
        help="Per-command timeout in seconds. Default: %(default)s",
    )
    return parser.parse_args(argv)


def installed_executable(bin_dir: Path, name: str) -> Path:
    candidates = (bin_dir / name, bin_dir / f"{name}.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(f"installed executable not found in {bin_dir}: {name}")


def clean_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return env


def run_command(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_sec: float,
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
        print(f"[installed-one-profile-smoke] command failed: {cmd}", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    return result


def prepare_smoke_profile(source: Path, destination: Path, *, query_id: str) -> None:
    if not source.is_file():
        raise SystemExit(f"profile text fixture not found: {source}")
    profile_text = source.read_text(encoding="utf-8")
    destination.write_text(
        f"Query Runtime Profile\nQuery ID: {query_id}\n\n{profile_text}",
        encoding="utf-8",
    )


def run_smoke(args: argparse.Namespace, work_dir: Path) -> None:
    if not args.bin_dir:
        raise SystemExit(f"--bin-dir or ${INSTALLED_BIN_ENV} is required")
    bin_dir = Path(args.bin_dir).expanduser().resolve()
    python = installed_executable(bin_dir, "python")
    analyze = installed_executable(bin_dir, "query-doctor-analyze")
    web = installed_executable(bin_dir, "query-doctor-web")
    report = installed_executable(bin_dir, "query-doctor-report")
    env = clean_env()

    profile_text = work_dir / "exported-profile.txt"
    prepare_smoke_profile(
        args.profile_text.expanduser().resolve(), profile_text, query_id=args.query_id
    )

    for command in (
        [str(analyze), "--help"],
        [str(web), "--help"],
        [str(report), "--help"],
    ):
        run_command(command, cwd=work_dir, env=env, timeout_sec=args.timeout_sec)

    cli_out = work_dir / "cli-corpus"
    run_command(
        [
            str(analyze),
            "--profile-text",
            str(profile_text),
            "--out",
            str(cli_out),
            "--redact-identifiers",
        ],
        cwd=work_dir,
        env=env,
        timeout_sec=args.timeout_sec,
    )
    cli_case_dir = cli_out / args.query_id.replace(":", "_")
    for name in ("analysis_facts.md", "analysis.json", "cm_metadata.json"):
        if not (cli_case_dir / name).is_file():
            raise SystemExit(f"CLI profile-text smoke did not write {name}")

    env.update(
        {
            "QD_INSTALLED_SMOKE_WORK": str(work_dir / "web-workspace"),
            "QD_INSTALLED_SMOKE_PROFILE": str(profile_text),
            "QD_INSTALLED_SMOKE_QUICKSTART_CORPUS": str(cli_out),
            "QD_INSTALLED_SMOKE_QUERY_ID": args.query_id,
        }
    )
    (work_dir / "web-workspace").mkdir(parents=True, exist_ok=True)
    inner_script = work_dir / "installed_web_smoke.py"
    inner_script.write_text(INSTALLED_WEB_SMOKE, encoding="utf-8")
    result = run_command(
        [str(python), str(inner_script)],
        cwd=work_dir / "web-workspace",
        env=env,
        timeout_sec=args.timeout_sec,
    )
    print(result.stdout.strip())


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    requested_work_dir = args.work_dir.expanduser().resolve() if args.work_dir else None
    try:
        prepared = prepare_smoke_work_dir(
            args.work_dir,
            keep_work_dir=args.keep_work_dir,
            replace_work_dir=args.replace_work_dir,
            temp_prefix="query-doctor-installed-one-profile-",
            protected_roots=(ROOT,),
        )
        work_dir = prepared.path
        run_smoke(args, work_dir)
    except SmokeWorkDirError as exc:
        print(f"[installed-one-profile-smoke] FAILED: {exc}", file=sys.stderr)
        if requested_work_dir is not None:
            print(f"[installed-one-profile-smoke] work dir: {requested_work_dir}", file=sys.stderr)
        return 1
    finally:
        if "prepared" in locals() and prepared.cleanup:
            shutil.rmtree(prepared.path, ignore_errors=True)
        elif "prepared" in locals() and (args.keep_work_dir or args.work_dir is not None):
            print(f"[installed-one-profile-smoke] work dir: {prepared.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
