"""Focused impala-shell argv construction for read-only metadata collection."""

from __future__ import annotations

import re
import subprocess
from typing import Callable


ALLOWED_AUTH_MODES = ("kerberos",)
ALLOWED_PROTOCOLS = ("beeswax", "hs2", "hs2-http")
COORDINATOR_HOSTPORT_RE = re.compile(r"([A-Za-z0-9_.-]+):([0-9]{1,5})\Z")
COORDINATOR_IPV6_RE = re.compile(r"\[([0-9A-Fa-f:.]+)\]:([0-9]{1,5})\Z")
KERBEROS_SERVICE_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")

Runner = Callable[..., subprocess.CompletedProcess[bytes]]


class ImpalaShellConfigError(ValueError):
    """Raised when impala-shell connection options are unsafe or unsupported."""


def _validate_port(raw_port: str) -> None:
    port = int(raw_port)
    if port <= 0 or port > 65535:
        raise ImpalaShellConfigError("Coordinator port must be between 1 and 65535.")


def validate_coordinator(coordinator: str) -> str:
    value = coordinator.strip()
    if not value:
        raise ImpalaShellConfigError("--coordinator must not be empty.")
    if value != coordinator or re.search(r"\s", value):
        raise ImpalaShellConfigError("--coordinator must not contain whitespace.")
    if "://" in value or "@" in value:
        raise ImpalaShellConfigError(
            "--coordinator must be HOST:PORT, not a URL or credential string."
        )
    if re.search(r"[;&|`$<>'\"(){}\\]", value):
        raise ImpalaShellConfigError("--coordinator contains unsupported shell metacharacters.")

    match = COORDINATOR_HOSTPORT_RE.fullmatch(value) or COORDINATOR_IPV6_RE.fullmatch(value)
    if not match:
        raise ImpalaShellConfigError("--coordinator must be HOST:PORT or [IPv6]:PORT.")
    _validate_port(match.group(2))
    return value


def validate_auth(auth: str) -> str:
    if auth not in ALLOWED_AUTH_MODES:
        allowed = ", ".join(ALLOWED_AUTH_MODES)
        raise ImpalaShellConfigError(f"Unsupported --auth value {auth!r}; allowed: {allowed}.")
    return auth


def validate_protocol(protocol: str | None) -> str | None:
    if protocol is None:
        return None
    if protocol not in ALLOWED_PROTOCOLS:
        allowed = ", ".join(ALLOWED_PROTOCOLS)
        raise ImpalaShellConfigError(
            f"Unsupported --protocol value {protocol!r}; allowed: {allowed}."
        )
    return protocol


def validate_kerberos_service_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if not KERBEROS_SERVICE_NAME_RE.fullmatch(normalized):
        raise ImpalaShellConfigError(
            "Kerberos service name must be a short token such as hive or impala."
        )
    return normalized


def build_impala_shell_argv(
    *,
    impala_shell: str,
    coordinator: str,
    auth: str,
    sql: str,
    protocol: str | None = None,
    ssl: bool = False,
    ca_cert: str | None = None,
    kerberos_service_name: str | None = None,
) -> list[str]:
    validate_coordinator(coordinator)
    validate_auth(auth)
    validate_protocol(protocol)
    kerberos_service_name = validate_kerberos_service_name(kerberos_service_name)
    if not impala_shell.strip():
        raise ImpalaShellConfigError("--impala-shell must not be empty.")
    if ca_cert and not ssl:
        raise ImpalaShellConfigError("--ca-cert requires --ssl.")

    argv = [
        impala_shell,
        "-i",
        coordinator,
        "-k",
        "-q",
        sql,
        "--output_delimiter=\t",
        "--print_header",
    ]
    if ssl:
        argv.append("--ssl")
    if ca_cert:
        argv.extend(["--ca_cert", ca_cert])
    if protocol:
        argv.extend(["--protocol", protocol])
    if kerberos_service_name:
        argv.append(f"--kerberos_service_name={kerberos_service_name}")
    return argv


def run_impala_shell(
    argv: list[str],
    *,
    timeout_sec: int,
    runner: Runner = subprocess.run,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "timeout": timeout_sec,
        "shell": False,
    }
    if env is not None:
        kwargs["env"] = env
    return runner(argv, **kwargs)
