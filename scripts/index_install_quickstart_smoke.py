#!/usr/bin/env python3
"""Install Query Doctor from a package index in a clean venv and smoke README Quickstart."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from smoke_workdir import SmokeWorkDirError, prepare_smoke_work_dir


ROOT = Path(__file__).resolve().parents[1]
README_QUICKSTART_SMOKE_SCRIPT = "scripts/installed_readme_quickstart_smoke.py"
README_QUICKSTART_SMOKE = ROOT / README_QUICKSTART_SMOKE_SCRIPT


class IndexInstallSmokeFailure(RuntimeError):
    """Safe package-index install smoke failure."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package",
        default="query-doctor",
        help="Package name to install from the configured index. Default: %(default)s",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Optional exact package version to install, for example 0.7.0.",
    )
    parser.add_argument(
        "--index-url",
        default=None,
        help="Optional pip --index-url, for example https://test.pypi.org/simple/.",
    )
    parser.add_argument(
        "--extra-index-url",
        action="append",
        default=[],
        help="Optional pip --extra-index-url. Can be repeated.",
    )
    parser.add_argument(
        "--pre",
        action="store_true",
        help="Allow pre-release package versions during pip install.",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python interpreter used to create the clean venv.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Optional install-smoke workspace. A fresh temporary directory is used by default.",
    )
    parser.add_argument(
        "--keep-work-dir",
        action="store_true",
        help="Keep the install-smoke workspace for debugging.",
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
        default=300.0,
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
        raise IndexInstallSmokeFailure(f"{label} failed: {detail or result.returncode}")
    return result


def requirement(package: str, version: str | None) -> str:
    normalized = package.strip()
    if not normalized:
        raise IndexInstallSmokeFailure("package name is empty")
    if version:
        return f"{normalized}=={version.strip()}"
    return normalized


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
        raise IndexInstallSmokeFailure("clean venv Python executable was not created")
    return candidate


def install_from_index(
    *,
    venv_python: Path,
    requirement_text: str,
    index_url: str | None,
    extra_index_urls: list[str],
    pre: bool,
    timeout_sec: float,
) -> None:
    cmd = [str(venv_python), "-m", "pip", "install"]
    if index_url:
        cmd.extend(["--index-url", index_url])
    for extra_index_url in extra_index_urls:
        cmd.extend(["--extra-index-url", extra_index_url])
    if pre:
        cmd.append("--pre")
    cmd.append(requirement_text)
    run_command(
        cmd,
        cwd=venv_python.parent,
        timeout_sec=timeout_sec,
        label="package index install",
    )


def installed_package_summary(
    *, venv_python: Path, package: str, repo_dir: Path, timeout_sec: float
) -> dict[str, str]:
    result = run_command(
        [
            str(venv_python),
            "-c",
            (
                "import importlib.metadata as md, json, pathlib, query_doctor; "
                f"print(json.dumps({{'version': md.version({package!r}), "
                "'package_file': str(pathlib.Path(query_doctor.__file__).resolve())}))"
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
        raise IndexInstallSmokeFailure("could not inspect installed package import path") from exc
    try:
        package_file.resolve().relative_to(repo_dir.resolve())
    except ValueError:
        return {"version": str(payload["version"]), "package_file": str(package_file)}
    raise IndexInstallSmokeFailure("clean venv imported query_doctor from the repository checkout")


def run_readme_smoke(
    *,
    venv_python: Path,
    work_dir: Path,
    host: str,
    port: int | None,
    timeout_sec: float,
) -> dict[str, object]:
    cmd = [
        str(venv_python),
        str(README_QUICKSTART_SMOKE),
        "--bin-dir",
        str(venv_python.parent),
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
        label="README Quickstart smoke against package-index install",
    )
    try:
        payload = json.loads(result.stdout.splitlines()[0])
    except (IndexError, json.JSONDecodeError) as exc:
        raise IndexInstallSmokeFailure("README Quickstart smoke did not emit JSON") from exc
    if payload.get("status") != "OK" or payload.get("real_web_server") is not True:
        raise IndexInstallSmokeFailure("README Quickstart smoke did not pass")
    return payload


def run_smoke(args: argparse.Namespace, work_dir: Path) -> None:
    python = args.python.expanduser().resolve()
    if not python.is_file():
        raise IndexInstallSmokeFailure("Python interpreter does not exist")
    requirement_text = requirement(args.package, args.version)
    venv_python = create_venv(
        python=python,
        venv_dir=work_dir / "venv",
        timeout_sec=args.timeout_sec,
    )
    install_from_index(
        venv_python=venv_python,
        requirement_text=requirement_text,
        index_url=args.index_url,
        extra_index_urls=args.extra_index_url,
        pre=args.pre,
        timeout_sec=args.timeout_sec,
    )
    package_summary = installed_package_summary(
        venv_python=venv_python,
        package=args.package,
        repo_dir=ROOT,
        timeout_sec=args.timeout_sec,
    )
    readme_summary = run_readme_smoke(
        venv_python=venv_python,
        work_dir=work_dir / "readme-quickstart-smoke",
        host=args.host,
        port=args.port,
        timeout_sec=args.timeout_sec,
    )
    print(
        json.dumps(
            {
                "schema_version": "query_doctor_index_install_quickstart_smoke_v1",
                "status": "OK",
                "requirement": requirement_text,
                "installed_version": package_summary["version"],
                "package_imported_from_repo": False,
                "package_import_parent": Path(package_summary["package_file"]).parent.name,
                "index_url_configured": bool(args.index_url),
                "extra_index_url_count": len(args.extra_index_url),
                "readme_quickstart_smoke": True,
                "readme_quickstart_schema_version": readme_summary.get("schema_version"),
                "real_web_server": readme_summary.get("real_web_server") is True,
                "package_index_used": True,
                "quickstart_external_services_used": False,
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
            temp_prefix="query-doctor-index-install-quickstart-",
            protected_roots=(ROOT,),
        )
        run_smoke(args, prepared.path)
    except (IndexInstallSmokeFailure, SmokeWorkDirError) as exc:
        print(f"[index-install-quickstart-smoke] FAILED: {exc}", file=sys.stderr)
        if requested_work_dir is not None:
            print(
                f"[index-install-quickstart-smoke] work dir: {requested_work_dir}", file=sys.stderr
            )
        return 1
    finally:
        if "prepared" in locals() and prepared.cleanup:
            shutil.rmtree(prepared.path, ignore_errors=True)
        elif "prepared" in locals() and (args.keep_work_dir or args.work_dir is not None):
            print(f"[index-install-quickstart-smoke] work dir: {prepared.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
