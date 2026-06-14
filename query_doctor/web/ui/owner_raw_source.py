"""Render the isolated owner-raw SQL source surface."""

from __future__ import annotations

import html

from query_doctor.web.models import WebSettings
from query_doctor.web.owner_raw_source import (
    OwnerRawSourceDecision,
    OwnerRawSourceHighlight,
    OwnerRawSourceView,
)
from query_doctor.web.ui.html_helpers import escape_value
from query_doctor.web.ui.pages import render_page


def render_owner_raw_source_page(
    settings: WebSettings,
    view: OwnerRawSourceView,
    *,
    active_nav: str = "batch",
) -> str:
    section = (
        '<section class="panel owner-raw-source-panel" '
        'aria-label="Owner-only raw source">'
        f"{render_owner_raw_source_header(view)}"
        f"{render_owner_raw_source_highlight_summary(view.highlights)}"
        f"{render_owner_raw_source_code(view.source_sql, view.highlights)}"
        "</section>"
    )
    return render_page(
        settings,
        active_nav=active_nav,
        show_run_panel=False,
        extra_sections=[section],
    )


def render_owner_raw_source_unavailable_page(
    settings: WebSettings,
    *,
    case_id: str,
    back_href: str,
    decision: OwnerRawSourceDecision,
    active_nav: str = "batch",
) -> str:
    safe_case_id = html.escape(case_id)
    safe_back_href = html.escape(back_href, quote=True)
    safe_reason = html.escape(decision.reason_code)
    section = (
        '<section class="panel owner-raw-source-panel" '
        'aria-label="Owner-only raw source unavailable">'
        '<div class="breadcrumb">'
        f'<a href="{safe_back_href}">Case details</a><span>/</span>'
        "<span>owner-only raw source</span></div>"
        '<div class="owner-raw-source-head">'
        "<div>"
        '<span class="owner-raw-boundary">Owner-only raw source</span>'
        "<h1>Raw source unavailable</h1>"
        "<p>The selected-case raw source view failed closed before rendering source text.</p>"
        "</div>"
        f'<span class="badge gray">{safe_case_id}</span>'
        "</div>"
        '<div class="owner-raw-source-policy" data-reason-code="'
        f'{safe_reason}">Reason: <code>{safe_reason}</code></div>'
        "</section>"
    )
    return render_page(
        settings,
        active_nav=active_nav,
        show_run_panel=False,
        extra_sections=[section],
    )


def render_owner_raw_source_header(view: OwnerRawSourceView) -> str:
    safe_back_href = html.escape(view.back_href, quote=True)
    return (
        '<div class="breadcrumb">'
        f'<a href="{safe_back_href}">Case details</a><span>/</span>'
        "<span>owner-only raw source</span></div>"
        '<div class="owner-raw-source-head">'
        "<div>"
        '<span class="owner-raw-boundary">Owner-only raw source</span>'
        "<h1>Original SQL source</h1>"
        "<p>Selected-case source only; credentials and local paths remain masked.</p>"
        "</div>"
        f'<span class="badge blue">{escape_value(view.case_id)}</span>'
        "</div>"
        '<div class="owner-raw-source-policy" '
        f'data-reason-code="{html.escape(view.reason_code, quote=True)}">'
        f"Query: <code>{escape_value(view.query_id)}</code>"
        f"<span>Owner: <code>{escape_value(view.query_user)}</code></span>"
        f"<span>Scope: <code>{escape_value(view.source_scope)}</code></span>"
        "</div>"
    )


def render_owner_raw_source_highlight_summary(
    highlights: tuple[OwnerRawSourceHighlight, ...],
) -> str:
    if not highlights:
        return (
            '<div class="owner-raw-source-locations">'
            "<strong>Highlights</strong><span>No SQL line highlights are available for this case.</span>"
            "</div>"
        )
    items = "".join(
        "<li>"
        f"<span>{html.escape(highlight_coordinate(highlight))}</span>"
        f"<strong>{escape_value(highlight.label)}</strong>"
        f"{render_highlight_detail(highlight)}"
        "</li>"
        for highlight in highlights
    )
    return (
        f'<div class="owner-raw-source-locations"><strong>Highlights</strong><ul>{items}</ul></div>'
    )


def render_highlight_detail(highlight: OwnerRawSourceHighlight) -> str:
    if not highlight.detail:
        return ""
    return f"<em>{escape_value(highlight.detail)}</em>"


def render_owner_raw_source_code(
    source_sql: str,
    highlights: tuple[OwnerRawSourceHighlight, ...],
) -> str:
    lines = source_sql.splitlines() or [""]
    rows = "".join(
        render_owner_raw_source_line(line, line_number=index, highlights=highlights)
        for index, line in enumerate(lines, start=1)
    )
    return (
        '<div class="owner-raw-source-code" role="region" aria-label="Original SQL source">'
        f"{rows}</div>"
    )


def render_owner_raw_source_line(
    line: str,
    *,
    line_number: int,
    highlights: tuple[OwnerRawSourceHighlight, ...],
) -> str:
    matching = tuple(
        highlight for highlight in highlights if highlight_covers_line(highlight, line_number)
    )
    classes = ["owner-raw-source-line"]
    if matching:
        classes.append("owner-raw-source-line--highlight")
    highlight_label = " / ".join(highlight.label.removeprefix("SQL: ") for highlight in matching)
    title = f' title="{html.escape(highlight_label, quote=True)}"' if highlight_label else ""
    return (
        f'<div class="{" ".join(classes)}"{title}>'
        f'<span class="owner-raw-source-line__number">{line_number}</span>'
        f'<code class="owner-raw-source-line__text">{html.escape(line) or " "}</code>'
        f"{render_line_marker(matching)}"
        "</div>"
    )


def render_line_marker(highlights: tuple[OwnerRawSourceHighlight, ...]) -> str:
    if not highlights:
        return ""
    labels = " / ".join(highlight.label.removeprefix("SQL: ") for highlight in highlights)
    return f'<span class="owner-raw-source-line__marker">{escape_value(labels)}</span>'


def highlight_covers_line(highlight: OwnerRawSourceHighlight, line_number: int) -> bool:
    return highlight.start_line <= line_number <= highlight.end_line


def highlight_coordinate(highlight: OwnerRawSourceHighlight) -> str:
    if highlight.start_line == highlight.end_line:
        return f"line {highlight.start_line}"
    return f"lines {highlight.start_line}-{highlight.end_line}"
