"""Connection option safety policy for read-only Impala metadata collection."""

from __future__ import annotations

import re


ALLOWED_AUTH_MODES = ("kerberos",)
# impyla speaks HiveServer2 only. Beeswax was reachable through impala-shell and
# is not reachable any more, so it is rejected here rather than failing later at
# connect time with a confusing transport error.
ALLOWED_PROTOCOLS = ("hs2", "hs2-http")
RETIRED_PROTOCOLS = ("beeswax",)
COORDINATOR_HOSTPORT_RE = re.compile(r"([A-Za-z0-9_.-]+):([0-9]{1,5})\Z")
COORDINATOR_IPV6_RE = re.compile(r"\[([0-9A-Fa-f:.]+)\]:([0-9]{1,5})\Z")
KERBEROS_SERVICE_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
HOST_LABEL_RE = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
KERBEROS_HOST_FQDN_RE = re.compile(rf"(?=^.{{1,253}}\Z){HOST_LABEL_RE}(?:\.{HOST_LABEL_RE})*\Z")


class ImpalaConnectionConfigError(ValueError):
    """Raised when Impala connection options are unsafe or unsupported."""


def _validate_port(raw_port: str) -> int:
    port = int(raw_port)
    if port <= 0 or port > 65535:
        raise ImpalaConnectionConfigError("Coordinator port must be between 1 and 65535.")
    return port


def validate_coordinator(coordinator: str) -> str:
    value = coordinator.strip()
    if not value:
        raise ImpalaConnectionConfigError("--coordinator must not be empty.")
    if value != coordinator or re.search(r"\s", value):
        raise ImpalaConnectionConfigError("--coordinator must not contain whitespace.")
    if "://" in value or "@" in value:
        raise ImpalaConnectionConfigError(
            "--coordinator must be HOST:PORT, not a URL or credential string."
        )
    if re.search(r"[;&|`$<>'\"(){}\\]", value):
        raise ImpalaConnectionConfigError("--coordinator contains characters a host cannot have.")

    match = COORDINATOR_HOSTPORT_RE.fullmatch(value) or COORDINATOR_IPV6_RE.fullmatch(value)
    if not match:
        raise ImpalaConnectionConfigError("--coordinator must be HOST:PORT or [IPv6]:PORT.")
    _validate_port(match.group(2))
    return value


def split_coordinator(coordinator: str) -> tuple[str, int]:
    """Return the validated coordinator as a (host, port) pair."""
    value = validate_coordinator(coordinator)
    match = COORDINATOR_HOSTPORT_RE.fullmatch(value) or COORDINATOR_IPV6_RE.fullmatch(value)
    assert match is not None  # validate_coordinator already rejected everything else
    return match.group(1), _validate_port(match.group(2))


def validate_auth(auth: str) -> str:
    if auth not in ALLOWED_AUTH_MODES:
        allowed = ", ".join(ALLOWED_AUTH_MODES)
        raise ImpalaConnectionConfigError(f"Unsupported --auth value {auth!r}; allowed: {allowed}.")
    return auth


def validate_protocol(protocol: str | None) -> str | None:
    if protocol is None:
        return None
    if protocol in RETIRED_PROTOCOLS:
        allowed = ", ".join(ALLOWED_PROTOCOLS)
        raise ImpalaConnectionConfigError(
            f"Protocol {protocol!r} is no longer reachable: metadata collection speaks "
            f"HiveServer2. Use one of: {allowed}, and point the coordinator at its HS2 port."
        )
    if protocol not in ALLOWED_PROTOCOLS:
        allowed = ", ".join(ALLOWED_PROTOCOLS)
        raise ImpalaConnectionConfigError(
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
        raise ImpalaConnectionConfigError(
            "Kerberos service name must be a short token such as hive or impala."
        )
    return normalized


def validate_kerberos_host_fqdn(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if value != normalized or "://" in normalized or "@" in normalized or ":" in normalized:
        raise ImpalaConnectionConfigError(
            "Kerberos host FQDN must be a hostname without scheme, port, or credentials."
        )
    if not KERBEROS_HOST_FQDN_RE.fullmatch(normalized):
        raise ImpalaConnectionConfigError(
            "Kerberos host FQDN must be a hostname such as impala-coordinator.example.com."
        )
    return normalized
