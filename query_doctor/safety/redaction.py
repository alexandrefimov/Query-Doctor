"""Redaction helpers for safe logs, collected profiles, and metadata."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable
from typing import Protocol


class SupportsSecretValues(Protocol):
    def secret_values(self) -> tuple[str, ...]:
        """Return secret values that must be redacted from diagnostics."""


EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
BRACKETED_IPV6_RE = re.compile(r"\[(?P<ip>[0-9A-Fa-f:]+)\]")
IPV6_CANDIDATE_RE = re.compile(r"(?<![A-Za-z0-9_.-])(?P<ip>[0-9A-Fa-f:]*:[0-9A-Fa-f:.]+)(?![A-Za-z0-9_.-])")
URL_CREDENTIAL_RE = re.compile(r"\b(https?://)([^/\s:@]+):([^@\s/]+)@", re.IGNORECASE)
URL_HOST_RE = re.compile(
    r"\b(https?://)(<redacted>@)?([^/\s:?#\\[]+)(:\d+)?",
    re.IGNORECASE,
)
AUTH_HEADER_RE = re.compile(
    r"(?im)^([ \t]*(?:Authorization|Proxy-Authorization)[ \t]*:[ \t]*(?:Bearer|Basic)[ \t]+)\S+"
)
COOKIE_HEADER_RE = re.compile(r"(?im)^([ \t]*(?:Cookie|Set-Cookie)[ \t]*:[ \t]*).+$")
BEARER_BASIC_RE = re.compile(r"\b(Bearer|Basic)[ \t]+[A-Za-z0-9._~+/=-]{8,}\b")
SECRET_VALUE_RE = re.compile(
    r"\b(password|passwd|pwd|token|secret|cookie|api[_-]?key|access[_-]?token|refresh[_-]?token)\b"
    r"([ \t]*[:=][ \t]*)([\"']?)([^\"'\s,;]+)([\"']?)",
    re.IGNORECASE,
)
USER_FIELD_RE = re.compile(
    r"(?im)^([ \t]*(?:User|Username|Effective User|Connected User|Delegated User)"
    r"[ \t]*[:=][ \t]*)([^ \t\r\n]+)"
)
USER_KV_RE = re.compile(r"\b(user|username)([ \t]*=[ \t]*)([A-Za-z][A-Za-z0-9_.-]*)\b", re.IGNORECASE)
HOST_FIELD_RE = re.compile(
    r"(?im)^([ \t]*(?:Host|Hostname|Coordinator|Coordinator Host|Daemon|Impala Daemon|"
    r"Impalad|Server)[ \t]*[:=][ \t]*)([^ \t\r\n]+)"
)
HOSTLIKE_FQDN_RE = re.compile(
    r"\b(?=[A-Za-z0-9.-]*(?:host|node|worker|server|impala|coordinator|cm|db|dn|nn)"
    r"[A-Za-z0-9.-]*)(?:[A-Za-z0-9-]+\.){2,}[A-Za-z][A-Za-z0-9-]*\b",
    re.IGNORECASE,
)
HOST_ASSIGNMENT_RE = re.compile(
    r"\b(?P<key>host|hostname|executor|backend)(?P<sep>[ \t]*=[ \t]*)(?P<value>[^ \t\r\n,)]+)",
    re.IGNORECASE,
)
HOST_ALIAS_RE = re.compile(r"^host_\d{2,}$", re.IGNORECASE)
SQL_DB_TABLE_RE = re.compile(
    r"\b(FROM|JOIN|TABLE|DESCRIBE)\s+`?[A-Za-z_][A-Za-z0-9_$]*`?"
    r"\s*\.\s*`?[A-Za-z_][A-Za-z0-9_$]*`?",
    re.IGNORECASE,
)
SQL_TABLE_RE = re.compile(
    r"\b(FROM|JOIN)\s+`?[A-Za-z_][A-Za-z0-9_$]*`?",
    re.IGNORECASE,
)

PRESERVED_METADATA_KEYS = {
    "query_id",
    "start_time",
    "end_time",
    "duration_ms",
    "duration_sec",
    "status",
    "query_type",
}
USER_METADATA_KEYS = {"user", "username", "effective_user", "connected_user", "delegated_user"}
POOL_METADATA_KEYS = {"pool", "admission_pool", "queue"}
SECRET_METADATA_KEY_PARTS = (
    "password",
    "passwd",
    "pwd",
    "token",
    "secret",
    "auth",
    "api_key",
    "apikey",
    "authorization",
)
HOST_METADATA_KEY_PARTS = ("host", "hostname", "coordinator", "impalad", "daemon", "server")
URL_METADATA_KEY_PARTS = ("url", "uri", "endpoint", "link")


def sanitize_text_for_log(text: object, *, secrets: Iterable[str] = ()) -> str:
    safe = str(text)
    for secret in secrets:
        if secret:
            safe = safe.replace(secret, "<secret>")
    safe = AUTH_HEADER_RE.sub(r"\1<redacted>", safe)
    safe = COOKIE_HEADER_RE.sub(r"\1<redacted>", safe)
    safe = BEARER_BASIC_RE.sub(r"\1 <redacted>", safe)
    safe = URL_CREDENTIAL_RE.sub(r"\1<redacted>@", safe)
    safe = SECRET_VALUE_RE.sub(redact_secret_value_match_preserving_marker, safe)
    safe = redact_host_identifiers(safe)
    return safe


def redact_secret_value_match_preserving_marker(match: re.Match[str]) -> str:
    marker = "<secret>" if match.group(4) == "<secret>" else "<redacted>"
    return f"{match.group(1)}{match.group(2)}{match.group(3)}{marker}{match.group(5)}"


def sanitize_http_error_message(text: object, config: SupportsSecretValues) -> str:
    safe = str(text)
    safe = AUTH_HEADER_RE.sub(r"\1<redacted>", safe)
    safe = COOKIE_HEADER_RE.sub(r"\1<redacted>", safe)
    safe = BEARER_BASIC_RE.sub(r"\1 <redacted>", safe)
    safe = URL_CREDENTIAL_RE.sub(r"\1<redacted>@", safe)
    safe = SECRET_VALUE_RE.sub(r"\1\2\3<redacted>\5", safe)
    safe = sanitize_text_for_log(safe, secrets=config.secret_values())
    return safe


def sanitize_adapter_error_message(text: object, *, secrets: Iterable[str] = ()) -> str:
    safe = str(text)
    safe = AUTH_HEADER_RE.sub(r"\1<redacted>", safe)
    safe = COOKIE_HEADER_RE.sub(r"\1<redacted>", safe)
    safe = BEARER_BASIC_RE.sub(r"\1 <redacted>", safe)
    safe = URL_CREDENTIAL_RE.sub(r"\1<redacted>@", safe)
    safe = SECRET_VALUE_RE.sub(r"\1\2\3<redacted>\5", safe)
    return sanitize_text_for_log(safe, secrets=secrets)


class HostAliasRedactor:
    """Assign stable safe host aliases within one redaction operation."""

    def __init__(self) -> None:
        self._aliases: dict[str, str] = {}

    def alias_for(self, host: str) -> str:
        normalized = host.strip().strip("[]").rstrip(".").lower()
        if not normalized:
            return "host_00"
        if HOST_ALIAS_RE.fullmatch(normalized):
            return normalized
        alias = self._aliases.get(normalized)
        if alias is None:
            alias = f"host_{len(self._aliases) + 1:02d}"
            self._aliases[normalized] = alias
        return alias

    def redact_host_value(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            return stripped
        bracketed_ipv6 = re.match(r"^\[(?P<ip>[0-9A-Fa-f:]+)\](?P<port>:\d+)?$", stripped)
        if bracketed_ipv6:
            try:
                ipaddress.ip_address(bracketed_ipv6.group("ip"))
            except ValueError:
                pass
            else:
                return f"{self.alias_for(bracketed_ipv6.group('ip'))}{bracketed_ipv6.group('port') or ''}"
        try:
            ipaddress.ip_address(stripped)
        except ValueError:
            pass
        else:
            return self.alias_for(stripped)
        match = re.match(r"^(?P<host>.+?)(?P<port>:\d+)?$", stripped)
        if not match:
            return self.alias_for(stripped)
        return f"{self.alias_for(match.group('host'))}{match.group('port') or ''}"


def redact_host_identifiers(text: str, redactor: HostAliasRedactor | None = None) -> str:
    host_redactor = redactor or HostAliasRedactor()

    def replace_ipv6_candidate(match: re.Match[str]) -> str:
        value = match.group("ip")
        try:
            ipaddress.ip_address(value)
        except ValueError:
            return match.group(0)
        return host_redactor.alias_for(value)

    def replace_bracketed_ipv6(match: re.Match[str]) -> str:
        value = match.group("ip")
        try:
            ipaddress.ip_address(value)
        except ValueError:
            return match.group(0)
        return host_redactor.alias_for(value)

    def replace_host_field(match: re.Match[str]) -> str:
        return f"{match.group(1)}{host_redactor.redact_host_value(match.group(2))}"

    def replace_host_assignment(match: re.Match[str]) -> str:
        alias = host_redactor.redact_host_value(match.group("value"))
        return f"{match.group('key')}{match.group('sep')}{alias}"

    def replace_url_host(match: re.Match[str]) -> str:
        alias = host_redactor.alias_for(match.group(3))
        return f"{match.group(1)}{match.group(2) or ''}{alias}{match.group(4) or ''}"

    redacted = HOST_FIELD_RE.sub(replace_host_field, text)
    redacted = HOST_ASSIGNMENT_RE.sub(replace_host_assignment, redacted)
    redacted = URL_HOST_RE.sub(replace_url_host, redacted)
    redacted = HOSTLIKE_FQDN_RE.sub(lambda match: host_redactor.alias_for(match.group(0)), redacted)
    redacted = IPV4_RE.sub(lambda match: host_redactor.alias_for(match.group(0)), redacted)
    redacted = BRACKETED_IPV6_RE.sub(replace_bracketed_ipv6, redacted)
    redacted = IPV6_CANDIDATE_RE.sub(replace_ipv6_candidate, redacted)
    return redacted


def redact_profile_text(
    text: str,
    *,
    redact_identifiers: bool = False,
    redact_hosts: bool = True,
) -> str:
    host_redactor = HostAliasRedactor()
    redacted = text
    redacted = EMAIL_RE.sub("<email>", redacted)
    redacted = URL_CREDENTIAL_RE.sub(r"\1<redacted>@", redacted)
    redacted = AUTH_HEADER_RE.sub(r"\1<redacted>", redacted)
    redacted = COOKIE_HEADER_RE.sub(r"\1<redacted>", redacted)
    redacted = BEARER_BASIC_RE.sub(r"\1 <redacted>", redacted)
    redacted = SECRET_VALUE_RE.sub(r"\1\2\3<redacted>\5", redacted)
    redacted = USER_FIELD_RE.sub(r"\1<user>", redacted)
    redacted = USER_KV_RE.sub(r"\1\2<user>", redacted)
    if redact_hosts:
        redacted = redact_host_identifiers(redacted, host_redactor)

    if redact_identifiers:
        redacted = SQL_DB_TABLE_RE.sub(lambda match: f"{match.group(1)} <db>.<table>", redacted)
        redacted = SQL_TABLE_RE.sub(lambda match: f"{match.group(1)} <table>", redacted)

    return redacted


def redact_metadata(
    metadata: dict[str, object],
    *,
    redact_identifiers: bool = False,
    redact_hosts: bool = True,
) -> dict[str, object]:
    host_redactor = HostAliasRedactor()
    return {
        key: redact_metadata_value(
            key,
            value,
            redact_identifiers=redact_identifiers,
            redact_hosts=redact_hosts,
            host_redactor=host_redactor,
        )
        for key, value in metadata.items()
    }


def redact_metadata_value(
    key: str,
    value: object,
    *,
    redact_identifiers: bool,
    redact_hosts: bool,
    host_redactor: HostAliasRedactor,
) -> object:
    normalized_key = key.lower()

    if normalized_key in PRESERVED_METADATA_KEYS:
        return value
    if normalized_key in USER_METADATA_KEYS:
        return "<user>" if value is not None else None
    if normalized_key in POOL_METADATA_KEYS:
        return "<pool>" if value is not None else None
    if any(part in normalized_key for part in SECRET_METADATA_KEY_PARTS):
        return "<redacted>" if value is not None else None
    if redact_hosts and any(part in normalized_key for part in HOST_METADATA_KEY_PARTS):
        return host_redactor.redact_host_value(str(value)) if value is not None else None
    if any(part in normalized_key for part in URL_METADATA_KEY_PARTS):
        return "<url>" if value is not None else None
    if isinstance(value, str):
        redacted = redact_profile_text(
            value,
            redact_identifiers=redact_identifiers,
            redact_hosts=redact_hosts,
        )
        return redact_host_identifiers(redacted, host_redactor) if redact_hosts else redacted
    if isinstance(value, dict):
        return {
            child_key: redact_metadata_value(
                child_key,
                child_value,
                redact_identifiers=redact_identifiers,
                redact_hosts=redact_hosts,
                host_redactor=host_redactor,
            )
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [
            redact_metadata_value(
                key,
                item,
                redact_identifiers=redact_identifiers,
                redact_hosts=redact_hosts,
                host_redactor=host_redactor,
            )
            for item in value
        ]
    return value
