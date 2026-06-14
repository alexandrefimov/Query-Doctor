"""Raw-free source location chip rendering."""

from __future__ import annotations

import html

from query_doctor.web.presenters.recent_scan_models import RecentScanSourceLocatorView
from query_doctor.web.ui.html_helpers import escape_value


def render_source_location_chips(
    locators: tuple[RecentScanSourceLocatorView, ...],
    *,
    limit: int = 3,
) -> str:
    chips: list[str] = []
    seen: set[tuple[str, str]] = set()
    for locator in locators:
        if locator.kind != "sql" or not locator.coordinate:
            continue
        key = (locator.label, locator.coordinate)
        if key in seen:
            continue
        seen.add(key)
        chips.append(render_source_location_chip(locator))
        if len(chips) >= limit:
            break
    if not chips:
        return ""
    return (
        '<span class="source-location-chips" aria-label="Raw-free source locations">'
        + "".join(chips)
        + "</span>"
    )


def render_source_location_chip(locator: RecentScanSourceLocatorView) -> str:
    title_parts = [locator.label, locator.coordinate]
    if locator.detail:
        title_parts.append(locator.detail)
    title = " - ".join(title_parts)
    return (
        '<span class="source-location-chip source-location-chip--sql" '
        f'title="{html.escape(title, quote=True)}">'
        f"{escape_value(locator.coordinate)}</span>"
    )


def render_redacted_sql_source_map(
    locators: tuple[RecentScanSourceLocatorView, ...],
    *,
    limit: int = 3,
) -> str:
    rows: list[str] = []
    seen: set[tuple[str, str]] = set()
    for locator in locators:
        if locator.kind != "sql" or not locator.coordinate:
            continue
        key = (locator.label, locator.coordinate)
        if key in seen:
            continue
        seen.add(key)
        rows.append(render_redacted_sql_source_map_row(locator))
        if len(rows) >= limit:
            break
    if not rows:
        return ""
    return (
        '<div class="redacted-source-map" aria-label="Redacted SQL source map">'
        '<div class="redacted-source-map__title">Redacted source map</div>'
        + "".join(rows)
        + "</div>"
    )


def render_redacted_sql_source_map_row(locator: RecentScanSourceLocatorView) -> str:
    label = locator.label.removeprefix("SQL: ").strip() or locator.label
    detail = f" - {locator.detail}" if locator.detail else ""
    return (
        '<div class="redacted-source-map__row">'
        f'<span class="redacted-source-map__line">{escape_value(locator.coordinate)}</span>'
        '<span class="redacted-source-map__mask">source text hidden</span>'
        f'<span class="redacted-source-map__label">{escape_value(label)}{escape_value(detail)}</span>'
        "</div>"
    )
