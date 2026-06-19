"""Shared safe error rendering for browser-visible web failures."""

from __future__ import annotations

import html
from typing import Any, Mapping

from query_doctor.web.error_contract import (
    WebErrorInfo,
    web_error_info_from_error,
    web_error_info_from_payload,
)


DEFAULT_ERROR_FOOTER = "Unsafe details remain hidden."


def render_error_panel(
    error: object,
    *,
    default_title: str = "Safe inspection state",
    footer: str = "Unvalidated or partial report output is hidden.",
) -> str:
    info = web_error_info_from_error(error, default_title=default_title)
    return (
        '<section class="error-card" role="alert">'
        f"{render_error_info_body(info, footer=footer)}"
        "</section>"
    )


def render_error_info_body(
    error_info: WebErrorInfo | Mapping[str, Any] | object,
    *,
    footer: str = DEFAULT_ERROR_FOOTER,
) -> str:
    info = _normalize_error_info(error_info)
    details_html = ""
    if info.details:
        details_html = (
            '<ul class="error-detail-list">'
            + "".join(f"<li>{html.escape(detail)}</li>" for detail in info.details)
            + "</ul>"
        )
    meta_rows = [
        ("Reason", info.reason_code),
        ("Stage", info.stage),
    ]
    meta_html = "".join(
        "<div>"
        f"<span>{html.escape(label)}</span>"
        f"<strong>{html.escape(value or 'unknown')}</strong>"
        "</div>"
        for label, value in meta_rows
        if value
    )
    if meta_html:
        meta_html = f'<div class="error-meta">{meta_html}</div>'
    next_step_html = (
        f'<p class="error-next-step"><strong>Next step:</strong> {html.escape(info.next_step)}</p>'
        if info.next_step
        else ""
    )
    footer_html = f'<p class="error-boundary-note">{html.escape(footer)}</p>' if footer else ""
    return (
        f"<strong>{html.escape(info.title)}</strong>"
        f'<p class="error-summary">{html.escape(info.message)}</p>'
        f"{meta_html}"
        f"{details_html}"
        f"{next_step_html}"
        f"{footer_html}"
    )


def _normalize_error_info(error_info: WebErrorInfo | Mapping[str, Any] | object) -> WebErrorInfo:
    if isinstance(error_info, WebErrorInfo):
        return error_info
    payload_info = web_error_info_from_payload(error_info)
    if payload_info is not None:
        return payload_info
    return web_error_info_from_error(error_info)
