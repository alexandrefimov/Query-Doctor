#!/usr/bin/env python3
"""Build a wheel, install it in a clean venv, and run the README Quickstart smoke."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README_QUICKSTART_SMOKE_SCRIPT = "scripts/installed_readme_quickstart_smoke.py"
README_QUICKSTART_SMOKE = ROOT / README_QUICKSTART_SMOKE_SCRIPT


class CleanWheelSmokeFailure(RuntimeError):
    """Safe clean-wheel rehearsal failure."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-dir",
        type=Path,
        default=ROOT,
        help="Repository checkout to build. Default: %(default)s",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python interpreter used to build the wheel and create the venv.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Optional rehearsal workspace. A fresh temporary directory is used by default.",
    )
    parser.add_argument(
        "--keep-work-dir",
        action="store_true",
        help="Keep the rehearsal workspace for debugging.",
    )
    parser.add_argument(
        "--no-build-isolation",
        action="store_true",
        help=(
            "Pass --no-isolation to python -m build for offline local rehearsals. "
            "By default the script uses build isolation to match release builds."
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Local bind host for the README Quickstart web server.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Local bind port for the README Quickstart web server.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=240.0,
        help="Per-step timeout in seconds. Default: %(default)s",
    )
    return parser.parse_args(argv)


def safe_output_snippet(text: str, *, max_chars: int = 800) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3] + "..."


def run_command(
    cmd: list[str],
    *,
    cwd: Path,
    timeout_sec: float,
    label: str,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout_sec,
        check=False,
    )
    if result.returncode != 0:
        detail = safe_output_snippet(result.stderr) or safe_output_snippet(result.stdout)
        raise CleanWheelSmokeFailure(f"{label} failed: {detail or result.returncode}")
    return result


def build_wheel(
    *,
    python: Path,
    repo_dir: Path,
    dist_dir: Path,
    timeout_sec: float,
    no_build_isolation: bool,
) -> Path:
    cmd = [
        str(python),
        "-m",
        "build",
        "--wheel",
        "--outdir",
        str(dist_dir),
    ]
    if no_build_isolation:
        cmd.append("--no-isolation")
    cmd.append(str(repo_dir))
    run_command(
        cmd,
        cwd=repo_dir,
        timeout_sec=timeout_sec,
        label="wheel build",
    )
    wheels = sorted(dist_dir.glob("query_doctor-*.whl"))
    if len(wheels) != 1:
        raise CleanWheelSmokeFailure("wheel build did not produce exactly one query_doctor wheel")
    return wheels[0]


def create_venv(*, python: Path, venv_dir: Path, timeout_sec: float) -> Path:
    run_command(
        [str(python), "-m", "venv", str(venv_dir)],
        cwd=venv_dir.parent,
        timeout_sec=timeout_sec,
        label="clean venv creation",
    )
    candidate = venv_dir / "bin" / "python"
    if not candidate.is_file():
        candidate = venv_dir / "Scripts" / "python.exe"
    if not candidate.is_file():
        raise CleanWheelSmokeFailure("clean venv Python executable was not created")
    return candidate


def install_wheel(
    *,
    venv_python: Path,
    wheel: Path,
    timeout_sec: float,
) -> None:
    run_command(
        [str(venv_python), "-m", "pip", "install", str(wheel)],
        cwd=wheel.parent,
        timeout_sec=timeout_sec,
        label="wheel install in clean venv",
    )


def assert_installed_package_not_from_repo(
    *,
    venv_python: Path,
    repo_dir: Path,
    timeout_sec: float,
) -> Path:
    result = run_command(
        [
            str(venv_python),
            "-c",
            (
                "import json, pathlib, query_doctor; "
                "print(json.dumps({'package_file': str(pathlib.Path(query_doctor.__file__).resolve())}))"
            ),
        ],
        cwd=repo_dir.parent,
        timeout_sec=timeout_sec,
        label="installed package import boundary",
    )
    try:
        payload = json.loads(result.stdout)
        package_file = Path(str(payload["package_file"]))
    except (KeyError, json.JSONDecodeError, TypeError) as exc:
        raise CleanWheelSmokeFailure("could not inspect installed package import path") from exc
    try:
        package_file.resolve().relative_to(repo_dir.resolve())
    except ValueError:
        return package_file
    raise CleanWheelSmokeFailure("clean venv imported query_doctor from the repository checkout")


def run_readme_smoke(
    *,
    venv_python: Path,
    bin_dir: Path,
    work_dir: Path,
    host: str,
    port: int | None,
    timeout_sec: float,
) -> dict[str, object]:
    cmd = [
        str(venv_python),
        str(README_QUICKSTART_SMOKE),
        "--bin-dir",
        str(bin_dir),
        "--work-dir",
        str(work_dir),
        "--host",
        host,
        "--timeout-sec",
        str(timeout_sec),
    ]
    if port is not None:
        cmd.extend(["--port", str(port)])
    result = run_command(
        cmd,
        cwd=ROOT,
        timeout_sec=timeout_sec,
        label="README Quickstart smoke against clean wheel venv",
    )
    try:
        payload = json.loads(result.stdout.splitlines()[0])
    except (IndexError, json.JSONDecodeError) as exc:
        raise CleanWheelSmokeFailure("README Quickstart smoke did not emit JSON") from exc
    if payload.get("status") != "OK" or payload.get("real_web_server") is not True:
        raise CleanWheelSmokeFailure("README Quickstart smoke did not pass")
    return payload


def run_smoke(args: argparse.Namespace, work_dir: Path) -> None:
    repo_dir = args.repo_dir.expanduser().resolve()
    python = args.python.expanduser().resolve()
    if not (repo_dir / "pyproject.toml").is_file():
        raise CleanWheelSmokeFailure("repo-dir does not contain pyproject.toml")
    if not python.is_file():
        raise CleanWheelSmokeFailure("Python interpreter does not exist")

    dist_dir = work_dir / "dist"
    venv_dir = work_dir / "venv"
    readme_work_dir = work_dir / "readme-quickstart-smoke"
    dist_dir.mkdir(parents=True, exist_ok=True)
    wheel = build_wheel(
        python=python,
        repo_dir=repo_dir,
        dist_dir=dist_dir,
        timeout_sec=args.timeout_sec,
        no_build_isolation=args.no_build_isolation,
    )
    venv_python = create_venv(python=python, venv_dir=venv_dir, timeout_sec=args.timeout_sec)
    install_wheel(
        venv_python=venv_python,
        wheel=wheel,
        timeout_sec=args.timeout_sec,
    )
    package_file = assert_installed_package_not_from_repo(
        venv_python=venv_python,
        repo_dir=repo_dir,
        timeout_sec=args.timeout_sec,
    )
    readme_summary = run_readme_smoke(
        venv_python=venv_python,
        bin_dir=venv_python.parent,
        work_dir=readme_work_dir,
        host=args.host,
        port=args.port,
        timeout_sec=args.timeout_sec,
    )

    print(
        json.dumps(
            {
                "schema_version": "query_doctor_clean_wheel_quickstart_smoke_v1",
                "status": "OK",
                "wheel_filename": wheel.name,
                "build_isolation": not args.no_build_isolation,
                "package_imported_from_repo": False,
                "package_import_parent": package_file.parent.name,
                "readme_quickstart_smoke": True,
                "readme_quickstart_schema_version": readme_summary.get("schema_version"),
                "real_web_server": readme_summary.get("real_web_server") is True,
                "external_services_used": False,
                "llm_used": False,
            },
            sort_keys=True,
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="query-doctor-clean-wheel-quickstart-"))
        cleanup = not args.keep_work_dir
    else:
        work_dir = args.work_dir.expanduser().resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        cleanup = False
    try:
        run_smoke(args, work_dir)
    except CleanWheelSmokeFailure as exc:
        print(f"[clean-wheel-quickstart-smoke] FAILED: {exc}", file=sys.stderr)
        if not cleanup:
            print(f"[clean-wheel-quickstart-smoke] work dir: {work_dir}", file=sys.stderr)
        return 1
    finally:
        if cleanup:
            shutil.rmtree(work_dir, ignore_errors=True)
        elif args.keep_work_dir or args.work_dir is not None:
            print(f"[clean-wheel-quickstart-smoke] work dir: {work_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
