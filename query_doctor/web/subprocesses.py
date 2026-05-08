"""Subprocess helpers for the local web UI."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable

from query_doctor.config.contract import merge_kerberos_cache_env

from query_doctor.web.config import metadata_configured
from query_doctor.web.models import WebError, WebSettings


Runner = Callable[..., subprocess.CompletedProcess[str]]
CancelCheck = Callable[[], bool]
WEB_CANCELLED_RETURN_CODE = -15


def run_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    timeout_sec: int,
    runner: Runner,
    env: dict[str, str] | None = None,
    cancel_check: CancelCheck | None = None,
) -> subprocess.CompletedProcess[str]:
    if cancel_check is not None and runner is subprocess.run:
        return run_cancellable_subprocess(
            cmd,
            cwd=cwd,
            timeout_sec=timeout_sec,
            env=env,
            cancel_check=cancel_check,
        )
    completed = runner(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )
    if cancel_check is not None and cancel_check():
        return subprocess.CompletedProcess(cmd, WEB_CANCELLED_RETURN_CODE, stdout="", stderr="")
    return completed


def run_cancellable_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    timeout_sec: int,
    env: dict[str, str] | None,
    cancel_check: CancelCheck,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=os.name == "posix",
    )
    deadline = time.monotonic() + timeout_sec
    while True:
        if cancel_check():
            terminate_process_tree(process)
            stdout, stderr = communicate_after_stop(process)
            return subprocess.CompletedProcess(cmd, WEB_CANCELLED_RETURN_CODE, stdout=stdout, stderr=stderr)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            terminate_process_tree(process, force=True)
            raise subprocess.TimeoutExpired(cmd, timeout_sec)
        try:
            stdout, stderr = process.communicate(timeout=min(0.2, remaining))
            return subprocess.CompletedProcess(cmd, process.returncode, stdout=stdout, stderr=stderr)
        except subprocess.TimeoutExpired:
            continue


def terminate_process_tree(process: subprocess.Popen[str], *, force: bool = False) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
        elif force:
            process.kill()
        else:
            process.terminate()
    except ProcessLookupError:
        return


def communicate_after_stop(process: subprocess.Popen[str]) -> tuple[str, str]:
    try:
        return process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        terminate_process_tree(process, force=True)
        return process.communicate()


def effective_subprocess_env(
    settings: WebSettings,
    base_env: dict[str, str] | os._Environ[str] | None = None,
) -> dict[str, str]:
    return merge_kerberos_cache_env(
        os.environ if base_env is None else base_env,
        {"krb5ccname": settings.krb5ccname},
    )


def resolve_metadata_impala_shell(settings: WebSettings, env: dict[str, str]) -> str | None:
    executable = settings.metadata_impala_shell or "impala-shell"
    if "/" in executable:
        path = Path(executable)
        if not path.is_absolute():
            path = settings.repo_dir / path
        return str(path) if path.is_file() else None
    return shutil.which(executable, path=env.get("PATH"))


def preflight_web_metadata_batch(
    settings: WebSettings,
    *,
    runner: Runner = subprocess.run,
    base_env: dict[str, str] | os._Environ[str] | None = None,
) -> None:
    env = effective_subprocess_env(settings, base_env=base_env)
    if not metadata_configured(settings):
        raise WebError("Metadata collection is not configured for this web session. Restart with metadata options or disable metadata in config.")
    if not resolve_metadata_impala_shell(settings, env):
        raise WebError("Metadata preflight failed: impala-shell executable is not available. Fix server metadata settings or disable metadata in config.")
    krb5ccname = env.get("KRB5CCNAME", "")
    if krb5ccname and any(ord(ch) < 32 or ord(ch) == 127 for ch in krb5ccname):
        raise WebError("Metadata preflight failed: Kerberos cache setting is invalid. Fix server environment or disable metadata in config.")
    try:
        completed = run_subprocess(
            ["klist"],
            cwd=settings.repo_dir,
            timeout_sec=min(settings.timeout_sec, 30),
            runner=runner,
            env=env,
        )
    except OSError as exc:
        raise WebError("Metadata preflight failed: klist is not available. Fix server Kerberos setup or disable metadata in config.") from exc
    if completed.returncode != 0:
        raise WebError(
            "Metadata preflight failed: Kerberos cache is not available or expired. "
            "Renew the Kerberos ticket or disable metadata in config."
        )


def subprocess_failure_message(stage: str, completed: subprocess.CompletedProcess[str]) -> str:
    return (
        f"{stage} failed with exit code {completed.returncode}. "
        "Captured subprocess output is not shown because it may contain raw "
        "profile text, SQL, JSON, or credentials."
    )


def has_cm_credentials(
    env: dict[str, str] | os._Environ[str] | None = None,
    *,
    username: str | None = None,
) -> bool:
    env = os.environ if env is None else env
    token = (env.get("CM_TOKEN") or "").strip()
    effective_username = (username or env.get("CM_USERNAME") or "").strip()
    password = (env.get("CM_PASSWORD") or "").strip()
    return bool(token) or (bool(effective_username) and bool(password))
