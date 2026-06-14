"""Safe web audit event rendering."""

from __future__ import annotations

import re
from dataclasses import dataclass


AUDIT_TOKEN_RE = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")


@dataclass(frozen=True)
class WebAuditEvent:
    name: str
    fields: tuple[tuple[str, str], ...] = ()


def safe_audit_token(value: object) -> str:
    text = str(value or "").strip()
    if AUDIT_TOKEN_RE.fullmatch(text):
        return text
    return "redacted"


def render_web_audit_log_line(event: WebAuditEvent, *, request_id: str) -> str:
    fields = [
        ("event", event.name),
        ("request_id", request_id),
        *event.fields,
    ]
    suffix = " ".join(f"{safe_audit_token(key)}={safe_audit_token(value)}" for key, value in fields)
    return f"[Query Doctor audit] {suffix}"
