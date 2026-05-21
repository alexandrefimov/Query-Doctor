"""Shared HTML layout assets for the local Query Doctor web UI."""

from __future__ import annotations

import html
from importlib.resources import files
from typing import Any
from urllib.parse import quote

from query_doctor.web.ui.i18n import language_label, normalize_ui_language, text


BRAND_MARK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="#0f5268" stroke-width="1.8" stroke-linecap="round" '
    'stroke-linejoin="round"><path d="M5 12h3l2-5 4 10 2-5h3"/>'
    '<path d="M12 3v3M12 18v3M3 12h2M19 12h2"/></svg>'
)


def read_static_asset_text(filename: str) -> str:
    return files("query_doctor.web.static").joinpath(filename).read_text(encoding="utf-8")


def render_favicon_link() -> str:
    return (
        '<link rel="icon" type="image/svg+xml" '
        f'href="data:image/svg+xml,{quote(BRAND_MARK_SVG, safe="")}">'
    )


def render_shared_styles() -> str:
    return read_static_asset_text("app.css").strip()


def render_static_stylesheet_link() -> str:
    return '<link rel="stylesheet" href="/static/app.css">'


def render_app_header(active: str, settings: Any | None = None) -> str:
    return (
        '<header class="app-header" aria-label="Application header">'
        '<a class="brand" href="/" aria-label="Query Doctor home">'
        '<span class="brand-mark" aria-hidden="true">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M5 12h3l2-5 4 10 2-5h3"/>'
        '<path d="M12 3v3M12 18v3M3 12h2M19 12h2"/>'
        "</svg></span>"
        '<span><span class="brand-title">impala-query-doctor</span>'
        '<span class="brand-subtitle">Impala query performance diagnostics</span></span>'
        "</a>"
        '<div class="header-actions">'
        f"{render_top_nav(active)}"
        f"{render_language_indicator(settings)}"
        f"{render_theme_toggle()}"
        "</div>"
        "</header>"
    )


def render_top_nav(active: str) -> str:
    batch_class = (
        "nav-link nav-link--active" if active in {"batch", "running", "query"} else "nav-link"
    )
    help_class = "nav-link nav-link--active" if active == "help" else "nav-link"
    return (
        '<nav class="top-nav" aria-label="Main navigation">'
        f'<a class="{batch_class}" href="/">Diagnose</a>'
        f'<a class="{help_class}" href="/help">Help</a>'
        "</nav>"
    )


def render_language_indicator(settings: Any | None = None) -> str:
    language = normalize_ui_language(getattr(settings, "language", "en"))
    label = language_label(language)
    code = language.upper()
    tooltip = text(
        language,
        f"Global language setting: {label}. It controls Help, Details, and newly generated reports. Change config field language in local config.",
        f"Глобальная настройка языка: {label}. Она управляет Help, Details и новыми отчетами. Измените поле language в локальном конфиге.",
    )
    aria_label = text(
        language,
        f"Global language setting: {label}. Change config field language in local config.",
        f"Глобальная настройка языка: {label}. Измените поле language в локальном конфиге.",
    )
    return (
        '<span class="language-indicator" role="status" '
        f'aria-label="{html.escape(aria_label, quote=True)}" '
        f'title="{html.escape(tooltip, quote=True)}">'
        f"{html.escape(code)}</span>"
    )


def render_theme_toggle() -> str:
    return (
        '<button class="theme-toggle" type="button" id="theme-toggle" aria-label="Switch to dark theme" '
        'aria-pressed="false" title="Toggle theme">'
        '<svg class="theme-icon-light" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>'
        "</svg>"
        '<svg class="theme-icon-dark" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>'
        "</svg>"
        "</button>"
    )


def render_theme_bootstrap_script() -> str:
    return '<script src="/static/theme-bootstrap.js"></script>'


def render_client_script() -> str:
    return read_static_asset_text("app.js").strip()


def render_script_link() -> str:
    return '<script src="/static/app.js"></script>'
