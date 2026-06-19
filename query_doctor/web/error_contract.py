"""Structured, browser-safe web error helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from query_doctor.web.display_safety import sanitize_browser_error_text


SAFE_REASON_CODE_RE = re.compile(r"[a-z0-9_.-]{1,96}\Z")
DEFAULT_ERROR_TITLE = "Safe failure details"
DEFAULT_ERROR_REASON_CODE = "web.error"
DEFAULT_ERROR_NEXT_STEP = "Review the selected inputs and local configuration, then retry."


@dataclass(frozen=True)
class WebErrorInfo:
    title: str
    message: str
    reason_code: str
    stage: str
    next_step: str
    details: tuple[str, ...] = ()


def web_error_info_from_error(
    error: object,
    *,
    default_title: str = DEFAULT_ERROR_TITLE,
    default_reason_code: str = DEFAULT_ERROR_REASON_CODE,
    stage: object | None = None,
    default_next_step: str = DEFAULT_ERROR_NEXT_STEP,
) -> WebErrorInfo:
    """Build a raw-free error envelope from a user-facing error object."""

    message = sanitize_error_text(str(error) if error is not None else "")
    title = sanitize_error_text(
        _optional_error_attr(error, "title") or default_title, max_chars=120
    )
    reason_code = safe_reason_code(_optional_error_attr(error, "reason_code"), default_reason_code)
    error_stage = sanitize_error_text(
        _optional_error_attr(error, "stage") or stage or "",
        max_chars=160,
    )
    next_step = sanitize_error_text(
        _optional_error_attr(error, "next_step") or default_next_step,
        max_chars=360,
    )
    details = tuple(
        detail
        for detail in (
            sanitize_error_text(item, max_chars=360)
            for item in _iter_details(_optional_error_attr(error, "details"))
        )
        if detail
    )[:5]
    if not message:
        message = "The request failed before Query Doctor could render a trusted result."
    return WebErrorInfo(
        title=title or default_title,
        message=message,
        reason_code=reason_code,
        stage=error_stage,
        next_step=next_step,
        details=details,
    )


def web_error_info_from_payload(payload: object) -> WebErrorInfo | None:
    if not isinstance(payload, Mapping):
        return None
    message = sanitize_error_text(payload.get("message") or "")
    if not message:
        return None
    return WebErrorInfo(
        title=sanitize_error_text(payload.get("title") or DEFAULT_ERROR_TITLE, max_chars=120),
        message=message,
        reason_code=safe_reason_code(payload.get("reason_code"), DEFAULT_ERROR_REASON_CODE),
        stage=sanitize_error_text(payload.get("stage") or "", max_chars=160),
        next_step=sanitize_error_text(
            payload.get("next_step") or DEFAULT_ERROR_NEXT_STEP,
            max_chars=360,
        ),
        details=tuple(
            detail
            for detail in (
                sanitize_error_text(item, max_chars=360)
                for item in _iter_details(payload.get("details"))
            )
            if detail
        )[:5],
    )


def web_error_info_payload(info: WebErrorInfo) -> dict[str, object]:
    return {
        "title": info.title,
        "message": info.message,
        "reason_code": info.reason_code,
        "stage": info.stage,
        "next_step": info.next_step,
        "details": list(info.details),
    }


def safe_web_error_info_payload(payload: object) -> dict[str, object] | None:
    info = web_error_info_from_payload(payload)
    return web_error_info_payload(info) if info is not None else None


def safe_reason_code(value: object, fallback: str = DEFAULT_ERROR_REASON_CODE) -> str:
    text = str(value or "").strip().lower()
    if SAFE_REASON_CODE_RE.fullmatch(text):
        return text
    return fallback if SAFE_REASON_CODE_RE.fullmatch(fallback) else DEFAULT_ERROR_REASON_CODE


def sanitize_error_text(value: object, *, max_chars: int | None = 1200) -> str:
    return sanitize_browser_error_text(value, max_chars=max_chars).strip()


def _iter_details(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)):
        return (value,)
    if isinstance(value, (tuple, list)):
        return tuple(value)
    return (value,)


def _optional_error_attr(error: object, name: str) -> object | None:
    value = getattr(error, name, None)
    if callable(value):
        return None
    return value
