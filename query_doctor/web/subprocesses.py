"""Subprocess helpers for the local web UI."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import BinaryIO, Callable

from query_doctor.config.contract import merge_kerberos_cache_env

from query_doctor.web.config import metadata_configured
from query_doctor.web.models import WebError, WebSettings


Runner = Callable[..., subprocess.CompletedProcess[str]]
CancelCheck = Callable[[], bool]
WEB_CANCELLED_RETURN_CODE = -15
WEB_SUBPROCESS_CAPTURE_LIMIT_BYTES = 1_048_576
WEB_SUBPROCESS_READ_CHUNK_BYTES = 8192
WEB_SUBPROCESS_STOP_GRACE_SEC = 2.0


def run_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    timeout_sec: int,
    runner: Runner,
    env: dict[str, str] | None = None,
    cancel_check: CancelCheck | None = None,
) -> subprocess.CompletedProcess[str]:
    if runner is subprocess.run:
        return run_bounded_subprocess(
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
    return bound_completed_process_output(completed)


def run_bounded_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    timeout_sec: int,
    env: dict[str, str] | None,
    cancel_check: CancelCheck | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        start_new_session=os.name == "posix",
    )
    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    output_threads = start_bounded_output_readers(process, stdout_buffer, stderr_buffer)
    deadline = time.monotonic() + timeout_sec
    cancelled = False
    while True:
        if cancel_check is not None and cancel_check():
            cancelled = True
            terminate_process_tree(process)
            break
        if process.poll() is not None:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            terminate_process_tree(process, force=True)
            wait_after_stop(process)
            join_output_threads(output_threads)
            raise subprocess.TimeoutExpired(cmd, timeout_sec)
        time.sleep(min(0.05, remaining))

    if cancelled:
        wait_after_stop(process)
    else:
        process.wait()
    join_output_threads(output_threads)
    return subprocess.CompletedProcess(
        cmd,
        WEB_CANCELLED_RETURN_CODE if cancelled else process.returncode,
        stdout=decode_bounded_output(stdout_buffer),
        stderr=decode_bounded_output(stderr_buffer),
    )


def run_cancellable_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    timeout_sec: int,
    env: dict[str, str] | None,
    cancel_check: CancelCheck,
) -> subprocess.CompletedProcess[str]:
    return run_bounded_subprocess(
        cmd,
        cwd=cwd,
        timeout_sec=timeout_sec,
        env=env,
        cancel_check=cancel_check,
    )


def start_bounded_output_readers(
    process: subprocess.Popen[bytes],
    stdout_buffer: bytearray,
    stderr_buffer: bytearray,
) -> tuple[threading.Thread, threading.Thread]:
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("subprocess output pipes were not configured")
    stdout_thread = threading.Thread(
        target=read_stream_bounded,
        args=(process.stdout, stdout_buffer),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=read_stream_bounded,
        args=(process.stderr, stderr_buffer),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    return stdout_thread, stderr_thread


def read_stream_bounded(stream: BinaryIO, buffer: bytearray) -> None:
    try:
        while True:
            chunk = stream.read(WEB_SUBPROCESS_READ_CHUNK_BYTES)
            if not chunk:
                return
            remaining = WEB_SUBPROCESS_CAPTURE_LIMIT_BYTES - len(buffer)
            if remaining > 0:
                buffer.extend(chunk[:remaining])
    finally:
        stream.close()


def join_output_threads(threads: tuple[threading.Thread, threading.Thread]) -> None:
    for thread in threads:
        thread.join(timeout=WEB_SUBPROCESS_STOP_GRACE_SEC)


def decode_bounded_output(buffer: bytearray) -> str:
    return bytes(buffer).decode("utf-8", errors="replace")


def bound_completed_process_output(
    completed: subprocess.CompletedProcess[str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        completed.args,
        completed.returncode,
        stdout=bound_output_value(completed.stdout),
        stderr=bound_output_value(completed.stderr),
    )


def bound_output_value(value: object) -> str:
    if isinstance(value, bytes):
        return value[:WEB_SUBPROCESS_CAPTURE_LIMIT_BYTES].decode("utf-8", errors="replace")
    if isinstance(value, str):
        encoded = value.encode("utf-8", errors="replace")
        if len(encoded) <= WEB_SUBPROCESS_CAPTURE_LIMIT_BYTES:
            return value
        return encoded[:WEB_SUBPROCESS_CAPTURE_LIMIT_BYTES].decode("utf-8", errors="replace")
    if value is None:
        return ""
    return str(value)


def terminate_process_tree(process: subprocess.Popen[object], *, force: bool = False) -> None:
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


def wait_after_stop(process: subprocess.Popen[object]) -> None:
    try:
        process.wait(timeout=WEB_SUBPROCESS_STOP_GRACE_SEC)
    except subprocess.TimeoutExpired:
        terminate_process_tree(process, force=True)
        process.wait()


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
    effective = merge_kerberos_cache_env(
        os.environ if base_env is None else base_env,
        {"krb5ccname": settings.krb5ccname},
    )
    if settings.cm_username and not effective.get("CM_USERNAME"):
        effective["CM_USERNAME"] = settings.cm_username
    return effective


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
        raise WebError(
            "Metadata collection is not configured for this web session. Restart with metadata options or disable metadata in config."
        )
    if not resolve_metadata_impala_shell(settings, env):
        raise WebError(
            "Metadata preflight failed: impala-shell executable is not available. Fix server metadata settings or disable metadata in config."
        )
    krb5ccname = env.get("KRB5CCNAME", "")
    if krb5ccname and any(ord(ch) < 32 or ord(ch) == 127 for ch in krb5ccname):
        raise WebError(
            "Metadata preflight failed: Kerberos cache setting is invalid. Fix server environment or disable metadata in config."
        )
    try:
        completed = run_subprocess(
            ["klist"],
            cwd=settings.repo_dir,
            timeout_sec=min(settings.timeout_sec, 30),
            runner=runner,
            env=env,
        )
    except OSError as exc:
        raise WebError(
            "Metadata preflight failed: klist is not available. Fix server Kerberos setup or disable metadata in config."
        ) from exc
    if completed.returncode != 0:
        raise WebError(
            "Metadata preflight failed: Kerberos cache is not available or expired. "
            "Renew the Kerberos ticket or disable metadata in config."
        )


def subprocess_failure_message(stage: str, completed: subprocess.CompletedProcess[str]) -> str:
    message = (
        f"{stage} failed with exit code {completed.returncode}. "
        "Captured subprocess output is not shown because it may contain raw "
        "profile text, SQL, JSON, or credentials."
    )
    if completed.returncode == 2:
        message += (
            " Exit code 2 usually indicates command-line argument validation or "
            "local configuration validation failed."
        )
    return message


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
