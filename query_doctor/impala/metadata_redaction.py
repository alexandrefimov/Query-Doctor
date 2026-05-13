"""Redaction helpers for Impala metadata collection output."""

from __future__ import annotations

import re

from query_doctor.safety.redaction import HostAliasRedactor, redact_profile_text


SQL_SECRET_VALUE_RE = re.compile(
    r"((?:'|\")?(?:password|passwd|pwd|token|secret|cookie|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token)(?:'|\")?[ \t]*[=:][ \t]*(?:'|\")?)([^'\"\s,;)]+)((?:'|\")?)",
    re.IGNORECASE,
)
GENERIC_URL_CREDENTIAL_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9+.-]*://)([^/\s:@]+):([^@\s/]+)@",
    re.IGNORECASE,
)
URI_HOST_RE = re.compile(
    r"\b(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)"
    r"(?P<credential><redacted>@)?"
    r"(?P<host>\[[^\]\s]+\]|[^/\s:?#'\"`]+)"
    r"(?P<port>:\d+)?"
)
USER_PATH_RE = re.compile(r"(?i)(/user/)[^/\s'\"`]+")
BARE_TABLE_IDENTIFIER_RE = re.compile(
    r"(?<![A-Za-z0-9_$./-])`?[A-Za-z_][A-Za-z0-9_$]*`?"
    r"\s*\.\s*`?[A-Za-z_][A-Za-z0-9_$]*`?(?![A-Za-z0-9_$])"
)


def redact_impala_context_text(
    text: object,
    *,
    redact_identifiers: bool = True,
    redact_hosts: bool = True,
) -> str:
    redacted = redact_profile_text(
        str(text),
        redact_identifiers=redact_identifiers,
        redact_hosts=redact_hosts,
    )
    redacted = GENERIC_URL_CREDENTIAL_RE.sub(r"\1<redacted>@", redacted)
    if redact_hosts:
        redacted = redact_uri_hosts(redacted)
    redacted = SQL_SECRET_VALUE_RE.sub(r"\1<redacted>\3", redacted)
    redacted = USER_PATH_RE.sub(r"\1<user>", redacted)
    if redact_identifiers:
        redacted = BARE_TABLE_IDENTIFIER_RE.sub("<db>.<table>", redacted)
    return redacted


def redact_uri_hosts(text: str) -> str:
    host_redactor = HostAliasRedactor()

    def replace_host(match: re.Match[str]) -> str:
        host = match.group("host")
        if host.startswith("host_"):
            alias = host
        else:
            alias = host_redactor.alias_for(host.strip("[]"))
        return (
            f"{match.group('scheme')}{match.group('credential') or ''}"
            f"{alias}{match.group('port') or ''}"
        )

    return URI_HOST_RE.sub(replace_host, text)
