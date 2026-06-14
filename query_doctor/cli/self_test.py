"""Installed-package self-test for local Query Doctor user paths."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.parse import quote


DEFAULT_QUERY_ID = "1111111111111111:2222222222222222"
FILENAME_FALLBACK_QUERY_ID = "3333333333333333:4444444444444444"
SELF_TEST_PROFILE_NAME = "exported-impala-profile.txt"
SELF_TEST_FILENAME_FALLBACK_PROFILE_NAME = "profile_3333333333333333_4444444444444444"
SELF_TEST_CORPUS_NAME = "query-doctor-self-test-corpus"
SELF_TEST_DEMO_NAME = "query-doctor-self-test-demo"
SELF_TEST_REPORT_NAME = "diagnosis_self_test.md"
SELF_TEST_CORPUS_SMOKE_NAME = "corpus_self_test.json"
SELF_TEST_EXPECTED_CASE_COUNT = 2
INSTALLED_CORE_COMMANDS = (
    "query-doctor-self-test",
    "query-doctor-analyze",
    "query-doctor-web",
    "query-doctor-demo",
    "query-doctor-report",
    "query-doctor-corpus-smoke",
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


@dataclass(frozen=True)
class SelfTestCheck:
    id: str
    label: str
    status: str
    detail: str = ""

    def to_json(self) -> dict[str, str]:
        payload = {"id": self.id, "label": self.label, "status": self.status}
        if self.detail:
            payload["detail"] = self.detail
        return payload


class SelfTestFailure(RuntimeError):
    """Safe user-facing self-test failure."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a local installed-package self-test. The test uses synthetic data only "
            "and does not contact Cloudera Manager, impalad, Spark, Trino, Prometheus, "
            "Ollama, or external LLM services."
        )
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
        help="Keep the temporary workspace and print its path for inspection.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=120.0,
        help="Per-command timeout in seconds. Default: %(default)s",
    )
    parser.add_argument(
        "--bin-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing installed query-doctor-* console scripts. "
            "Usually not needed; defaults to the current Python environment's script directory."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable summary JSON instead of progress lines.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def installed_bin_dir(args: argparse.Namespace) -> Path:
    if args.bin_dir is not None:
        return args.bin_dir.expanduser().resolve()
    argv0 = Path(sys.argv[0])
    script_names = set(INSTALLED_CORE_COMMANDS)
    script_names.update(f"{name}.exe" for name in INSTALLED_CORE_COMMANDS)
    if argv0.name in script_names:
        if argv0.is_file():
            return argv0.expanduser().resolve().parent
    scripts_path = sysconfig.get_path("scripts")
    if scripts_path:
        return Path(scripts_path).expanduser().resolve()
    return Path(sys.executable).parent.expanduser().resolve()


def installed_executable(bin_dir: Path, name: str) -> Path:
    candidates = (bin_dir / name, bin_dir / f"{name}.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SelfTestFailure(f"installed console script is missing: {name}")


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
    cmd: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_sec: float,
    label: str,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(cmd),
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SelfTestFailure(f"{label} timed out after {timeout_sec:.0f}s") from exc
    if result.returncode != 0:
        stderr = safe_output_snippet(result.stderr)
        stdout = safe_output_snippet(result.stdout)
        detail = stderr or stdout or f"exit {result.returncode}"
        raise SelfTestFailure(f"{label} failed: {detail}")
    return result


def safe_output_snippet(text: str, *, max_chars: int = 500) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3] + "..."


def synthetic_profile_text(
    query_id: str = DEFAULT_QUERY_ID, *, include_query_id_header: bool = True
) -> str:
    header = "Query Runtime Profile\n"
    if include_query_id_header:
        header += f"Query ID: {query_id}\n"
    return (
        header
        + """User: query_doctor_self_test_user
Request Pool: query_doctor_self_test_pool
Start Time: 2026-06-14 10:00:00.000000000
End Time: 2026-06-14 10:05:00.000000000
Coordinator: self-test-impalad.example.invalid:22000

Sql Statement:
SELECT 1

ExecSummary:
Operator              #Hosts   Avg Time   Max Time    #Rows  Est. #Rows  Peak Mem  Est. Peak Mem  Detail
01:SCAN HDFS               1       1s000ms  2s000ms   1.00M      10.00K  128.00 MB      64.00 MB  table=self_test.synthetic_table
02:HASH JOIN               1       2s000ms  4s000ms   1.00M      10.00K  256.00 MB      64.00 MB  INNER JOIN, PARTITIONED

Query Timeline:
   Query submitted: 0ns
   Query finished: 5m

TotalTime: 5m
TotalBytesRead: 12.00 GiB
TotalBytesSent: 2.00 GiB
"""
    )


def write_profile(work_dir: Path) -> Path:
    profile_path = work_dir / SELF_TEST_PROFILE_NAME
    profile_path.write_text(synthetic_profile_text(), encoding="utf-8")
    return profile_path


def write_filename_fallback_profile(work_dir: Path) -> Path:
    profile_path = work_dir / SELF_TEST_FILENAME_FALLBACK_PROFILE_NAME
    profile_path.write_text(
        synthetic_profile_text(
            FILENAME_FALLBACK_QUERY_ID,
            include_query_id_header=False,
        ),
        encoding="utf-8",
    )
    return profile_path


def output_check(check: SelfTestCheck, *, json_mode: bool) -> None:
    if not json_mode:
        print(f"[Query Doctor self-test] {check.label}: {check.status}")


def check_console_scripts(
    *,
    bin_dir: Path,
    work_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
) -> SelfTestCheck:
    for name in INSTALLED_CORE_COMMANDS:
        executable = installed_executable(bin_dir, name)
        run_command(
            [str(executable), "--help"],
            cwd=work_dir,
            env=env,
            timeout_sec=timeout_sec,
            label=f"{name} --help",
        )
    return SelfTestCheck("console_scripts", "Installed console scripts", "OK")


def check_demo_generation(
    *,
    bin_dir: Path,
    work_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
) -> SelfTestCheck:
    demo_dir = work_dir / SELF_TEST_DEMO_NAME
    demo = installed_executable(bin_dir, "query-doctor-demo")
    run_command(
        [str(demo), "--out", str(demo_dir), "--overwrite"],
        cwd=work_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="query-doctor-demo",
    )
    summary_path = demo_dir / "batch_summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SelfTestFailure("synthetic demo summary was not written") from exc
    if summary.get("demo_mode") is not True:
        raise SelfTestFailure("synthetic demo summary did not declare demo mode")
    return SelfTestCheck("demo", "Synthetic demo generation", "OK")


def check_profile_analysis(
    *,
    bin_dir: Path,
    work_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
) -> tuple[SelfTestCheck, Path, Path]:
    profile_path = write_profile(work_dir)
    corpus_dir = work_dir / SELF_TEST_CORPUS_NAME
    analyze = installed_executable(bin_dir, "query-doctor-analyze")
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
        label="query-doctor-analyze --profile-text",
    )
    case_dir = corpus_dir / DEFAULT_QUERY_ID.replace(":", "_")
    for name in ("analysis_facts.md", "analysis.json", "query_metadata.json", "profile_digest.md"):
        if not (case_dir / name).is_file():
            raise SelfTestFailure(f"profile analysis did not write {name}")
    return SelfTestCheck("profile_analysis", "One-profile analysis", "OK"), corpus_dir, case_dir


def check_profile_filename_fallback(
    *,
    bin_dir: Path,
    work_dir: Path,
    corpus_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
) -> SelfTestCheck:
    profile_path = write_filename_fallback_profile(work_dir)
    analyze = installed_executable(bin_dir, "query-doctor-analyze")
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
        label="query-doctor-analyze filename fallback profile",
    )
    case_dir = corpus_dir / FILENAME_FALLBACK_QUERY_ID.replace(":", "_")
    for name in ("analysis_facts.md", "analysis.json", "query_metadata.json", "profile_digest.md"):
        if not (case_dir / name).is_file():
            raise SelfTestFailure(f"filename fallback analysis did not write {name}")
    try:
        metadata = json.loads((case_dir / "query_metadata.json").read_text(encoding="utf-8"))
        analysis = json.loads((case_dir / "analysis.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SelfTestFailure("filename fallback analysis output was not readable") from exc
    if metadata.get("query_id") != FILENAME_FALLBACK_QUERY_ID:
        raise SelfTestFailure("filename fallback profile used an unexpected Query ID")
    if metadata.get("profile_query_id_source") != "impala_web_profile_filename":
        raise SelfTestFailure("filename fallback profile did not use the Web UI filename Query ID")
    if metadata.get("profile_filename_query_id_verified") is not True:
        raise SelfTestFailure("filename fallback profile filename was not verified")
    operators = analysis.get("operators")
    if not isinstance(operators, list) or len(operators) != 2:
        raise SelfTestFailure("filename fallback profile did not parse expected operators")
    return SelfTestCheck(
        "filename_fallback_profile",
        "Impala Web UI filename fallback",
        "OK",
    )


def check_web_rendering(*, work_dir: Path, corpus_dir: Path) -> SelfTestCheck:
    from query_doctor.cli import web as web_cli
    from query_doctor.web.config import validate_web_startup_config
    from query_doctor.web.jobs import WebJobStore
    from query_doctor.web.routes import route_get_request
    from query_doctor.web.server_args import parse_args as parse_web_args

    web_args = parse_web_args(["--corpus-dir", str(corpus_dir), "--no-llm"])
    settings = web_cli.quickstart_corpus_settings_without_default_config(web_args, work_dir)
    if settings is None:
        raise SelfTestFailure("web settings did not load the analyzed profile corpus")
    startup_errors = validate_web_startup_config(
        settings.config,
        cwd=work_dir,
        env={},
        require_cm=settings.batch_summary is None and settings.corpus_summary is None,
    )
    if startup_errors:
        raise SelfTestFailure("web startup validation failed for local corpus mode")
    store = WebJobStore()
    home = route_get_request("/", settings, store)
    details = route_get_request("/batch/case/case-001", settings, store)
    if home is None or home.status != 200:
        raise SelfTestFailure("web home route did not render")
    if details is None or details.status != 200:
        raise SelfTestFailure("web Details route did not render")
    for expected in ("Exported Profiles", "All analyzed", DEFAULT_QUERY_ID):
        if expected not in home.body:
            raise SelfTestFailure("web home route did not include analyzed profile summary")
    if FILENAME_FALLBACK_QUERY_ID not in home.body:
        raise SelfTestFailure("web home route did not include the filename fallback profile")
    if DEFAULT_QUERY_ID not in details.body:
        raise SelfTestFailure("web Details route did not include the self-test query")
    for forbidden in ("Query Runtime Profile", str(work_dir), str(corpus_dir)):
        if forbidden in home.body or forbidden in details.body:
            raise SelfTestFailure("web rendering leaked raw profile text or local paths")
    quoted_query_id = quote(DEFAULT_QUERY_ID, safe="")
    query_details = route_get_request(f"/query/details/{quoted_query_id}", settings, store)
    if query_details is None or query_details.status != 200:
        raise SelfTestFailure("Known Query ID Details route did not render")
    fallback_query_id = quote(FILENAME_FALLBACK_QUERY_ID, safe="")
    fallback_details = route_get_request(f"/query/details/{fallback_query_id}", settings, store)
    if fallback_details is None or fallback_details.status != 200:
        raise SelfTestFailure("filename fallback Known Query ID Details route did not render")
    return SelfTestCheck("web_rendering", "Local web rendering", "OK")


def check_report_generation(
    *,
    bin_dir: Path,
    work_dir: Path,
    case_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
) -> SelfTestCheck:
    report = installed_executable(bin_dir, "query-doctor-report")
    run_command(
        [
            str(report),
            str(case_dir),
            "--no-llm",
            "--out",
            SELF_TEST_REPORT_NAME,
            "--validation-mode",
            "strict",
        ],
        cwd=work_dir,
        env=env,
        timeout_sec=timeout_sec,
        label="query-doctor-report --no-llm",
    )
    if not (case_dir / SELF_TEST_REPORT_NAME).is_file():
        raise SelfTestFailure("deterministic report output was not written")
    return SelfTestCheck("report", "Deterministic report generation", "OK")


def check_corpus_smoke(
    *,
    bin_dir: Path,
    work_dir: Path,
    corpus_dir: Path,
    env: dict[str, str],
    timeout_sec: float,
) -> SelfTestCheck:
    corpus_smoke = installed_executable(bin_dir, "query-doctor-corpus-smoke")
    summary_path = work_dir / SELF_TEST_CORPUS_SMOKE_NAME
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
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SelfTestFailure("corpus smoke summary was not written") from exc
    totals = summary.get("totals")
    cases_scanned = totals.get("cases_scanned") if isinstance(totals, dict) else None
    if cases_scanned != SELF_TEST_EXPECTED_CASE_COUNT:
        raise SelfTestFailure("corpus smoke did not inspect all self-test cases")
    return SelfTestCheck("corpus_smoke", "Corpus smoke", "OK")


def run_self_test(args: argparse.Namespace, work_dir: Path) -> list[SelfTestCheck]:
    bin_dir = installed_bin_dir(args)
    env = clean_env(bin_dir, work_dir / "home")
    (work_dir / "home").mkdir(parents=True, exist_ok=True)
    checks: list[SelfTestCheck] = []

    check = check_console_scripts(
        bin_dir=bin_dir,
        work_dir=work_dir,
        env=env,
        timeout_sec=args.timeout_sec,
    )
    checks.append(check)
    output_check(check, json_mode=args.json)

    check = check_demo_generation(
        bin_dir=bin_dir,
        work_dir=work_dir,
        env=env,
        timeout_sec=args.timeout_sec,
    )
    checks.append(check)
    output_check(check, json_mode=args.json)

    check, corpus_dir, case_dir = check_profile_analysis(
        bin_dir=bin_dir,
        work_dir=work_dir,
        env=env,
        timeout_sec=args.timeout_sec,
    )
    checks.append(check)
    output_check(check, json_mode=args.json)

    check = check_profile_filename_fallback(
        bin_dir=bin_dir,
        work_dir=work_dir,
        corpus_dir=corpus_dir,
        env=env,
        timeout_sec=args.timeout_sec,
    )
    checks.append(check)
    output_check(check, json_mode=args.json)

    check = check_web_rendering(work_dir=work_dir, corpus_dir=corpus_dir)
    checks.append(check)
    output_check(check, json_mode=args.json)

    check = check_report_generation(
        bin_dir=bin_dir,
        work_dir=work_dir,
        case_dir=case_dir,
        env=env,
        timeout_sec=args.timeout_sec,
    )
    checks.append(check)
    output_check(check, json_mode=args.json)

    check = check_corpus_smoke(
        bin_dir=bin_dir,
        work_dir=work_dir,
        corpus_dir=corpus_dir,
        env=env,
        timeout_sec=args.timeout_sec,
    )
    checks.append(check)
    output_check(check, json_mode=args.json)
    return checks


def summary_payload(
    *,
    status: str,
    checks: Sequence[SelfTestCheck],
    work_dir: Path,
    kept_work_dir: bool,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "query_doctor_self_test_v1",
        "status": status,
        "checks": [check.to_json() for check in checks],
        "external_services_used": False,
        "llm_used": False,
    }
    if kept_work_dir:
        payload["work_dir"] = str(work_dir)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="query-doctor-self-test-"))
        cleanup = not args.keep_work_dir
    else:
        work_dir = args.work_dir.expanduser().resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        cleanup = False
    checks: list[SelfTestCheck] = []
    try:
        checks = run_self_test(args, work_dir)
    except SelfTestFailure as exc:
        failure = SelfTestCheck("self_test", "Self-test", "FAILED", str(exc))
        checks.append(failure)
        if args.json:
            print(
                json.dumps(
                    summary_payload(
                        status="FAILED",
                        checks=checks,
                        work_dir=work_dir,
                        kept_work_dir=not cleanup,
                    ),
                    sort_keys=True,
                )
            )
        else:
            print(f"[Query Doctor self-test] Self-test: FAILED ({exc})", file=sys.stderr)
            if not cleanup:
                print(f"[Query Doctor self-test] work dir: {work_dir}", file=sys.stderr)
        return 1
    finally:
        if cleanup:
            shutil.rmtree(work_dir, ignore_errors=True)

    if args.json:
        print(
            json.dumps(
                summary_payload(
                    status="OK",
                    checks=checks,
                    work_dir=work_dir,
                    kept_work_dir=not cleanup,
                ),
                sort_keys=True,
            )
        )
    else:
        if not cleanup:
            print(f"[Query Doctor self-test] work dir: {work_dir}")
        print("[Query Doctor self-test] Self-test: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
