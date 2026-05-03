"""Recent query scan form rendering helpers."""

from __future__ import annotations

import html
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


WEB_RECENT_SCAN_DEFAULTS = {
    "metadata_top_limit": "8",
    "cm_jobs": "20",
    "jobs": "4",
    "metadata_jobs": "1",
}
RECENT_SCAN_TIMEZONE = ZoneInfo("Europe/Moscow")
RECENT_SCAN_LOOKBACK_DAYS = 2


def render_batch_run_panel(settings: Any, form_values: dict[str, Any] | None = None, *, run_disabled: bool = False) -> str:
    metadata_configured = bool(getattr(settings, "metadata_coordinator", None))
    local_config = read_local_config_values(settings)
    default_scan_date, default_scan_hour = default_recent_scan_bucket()
    values = {
        "analysis_depth": "full" if metadata_configured else "fast",
        "scan_date": form_or_config_value(
            form_values,
            "scan_date",
            config_values=local_config,
            fallback=default_scan_date,
        ),
        "scan_hour": form_or_config_value(
            form_values,
            "scan_hour",
            config_values=local_config,
            fallback=str(default_scan_hour),
        ),
        "metadata_top_limit": form_or_config_value(
            form_values,
            "metadata_top_limit",
            config_values=local_config,
            config_key="recent_metadata_top_limit",
            fallback=WEB_RECENT_SCAN_DEFAULTS["metadata_top_limit"],
        ),
        "min_duration_sec": form_or_config_value(
            form_values,
            "min_duration_sec",
            config_values=local_config,
            config_key="recent_min_duration_sec",
        ),
        "max_duration_sec": "",
        "jobs": form_or_config_value(
            form_values,
            "jobs",
            config_values=local_config,
            fallback=WEB_RECENT_SCAN_DEFAULTS["jobs"],
        ),
        "cm_jobs": form_or_config_value(
            form_values,
            "cm_jobs",
            config_values=local_config,
            config_key="recent_cm_jobs",
            fallback=WEB_RECENT_SCAN_DEFAULTS["cm_jobs"],
        ),
        "metadata_jobs": form_or_config_value(
            form_values,
            "metadata_jobs",
            config_values=local_config,
            config_key="recent_metadata_jobs",
            fallback=WEB_RECENT_SCAN_DEFAULTS["metadata_jobs"],
        ),
        "user": form_or_config_value(form_values, "user", config_values=local_config, config_key="recent_user"),
        "pool": form_or_config_value(form_values, "pool", config_values=local_config, config_key="recent_pool"),
        "query_type": "QUERY",
        "include_failed": form_or_config_bool(
            form_values,
            "include_failed",
            config_values=local_config,
            config_key="recent_include_failed",
        ),
        "include_running": form_or_config_bool(
            form_values,
            "include_running",
            config_values=local_config,
            config_key="recent_include_running",
        ),
    }
    if form_values:
        values.update(form_values)

    def value(name: str) -> str:
        return html.escape(str(values.get(name, "")), quote=True)

    def checked(name: str) -> str:
        return " checked" if values.get(name) else ""

    analysis_depth = str(values.get("analysis_depth") or "full")
    if not metadata_configured and analysis_depth == "full":
        analysis_depth = "fast"
        values["analysis_depth"] = "fast"
    full_checked = " checked" if analysis_depth == "full" else ""
    fast_checked = " checked" if analysis_depth == "fast" else ""
    full_disabled = "" if metadata_configured else " disabled"
    full_label = "Full scan" if metadata_configured else "Full scan (metadata unavailable)"
    scan_mode_help = render_scan_mode_help(analysis_depth, metadata_configured=metadata_configured)
    metadata_note = "" if metadata_configured else "Metadata collection is not configured for this web session. Fast scan still works."
    metadata_note_html = f"<div class=\"batch-note\">{html.escape(metadata_note)}</div>" if metadata_note else ""
    button_disabled = " disabled" if run_disabled else ""
    button_label = "Running" if run_disabled else "Run scan"
    return (
        "<section class=\"panel batch-run-panel\" aria-label=\"Run recent query scan\">"
        "<div class=\"section-heading\"><div>"
        "<h1 class=\"section-title\">Recent query scan</h1>"
        "<div class=\"section-kicker\">Scan recent Impala queries from Cloudera Manager summaries.</div>"
        "</div></div>"
        "<form id=\"batch-form\" class=\"batch-form\" method=\"post\" action=\"/batch/run\">"
        "<div class=\"batch-checkbox-row\" role=\"group\" aria-label=\"Analysis depth\">"
        f"<label><input type=\"radio\" name=\"analysis_depth\" value=\"full\"{full_checked}{full_disabled}> "
        f"{html.escape(full_label)}</label>"
        f"<label><input type=\"radio\" name=\"analysis_depth\" value=\"fast\"{fast_checked}> "
        "Fast scan</label>"
        "<details class=\"info-popover info-popover--inline\"><summary aria-label=\"Scan mode help\">i</summary>"
        f"{scan_mode_help}</details>"
        "</div>"
        f"{metadata_note_html}"
        "<div class=\"batch-primary-row\">"
        f"{render_scan_date_select(value('scan_date'))}"
        f"{render_scan_hour_select(value('scan_hour'))}"
        f"<button class=\"run-button\" type=\"submit\"{button_disabled}>{button_label}</button>"
        "</div>"
        "<div class=\"scope-line\" aria-label=\"Recent scan collection scope\">"
        "<strong>Scope:</strong> one selected CM hour → matching summaries → analyzable profiles → ranked cases → top-case metadata · no auto LLM"
        "</div>"
        "<div class=\"batch-advanced-body\">"
        "<div class=\"batch-form-grid\">"
        f"{render_batch_number_field('metadata_top_limit', 'Cases with metadata', value('metadata_top_limit'), required=False, help_text='Maximum top-ranked analyzed cases enriched with read-only table metadata in Full scan. Fast scan skips metadata.')}"
        f"{render_batch_number_field('min_duration_sec', 'Minimum duration (sec)', value('min_duration_sec'), step='0.001', required=False, help_text='Only include queries at least this long. Empty means no duration filter.')}"
        f"{render_batch_number_field('cm_jobs', 'CM profile jobs', value('cm_jobs'), help_text='Parallel workers for CM profile downloads. Use higher values to speed the CM collection phase. Hard cap: 100.')}"
        f"{render_batch_number_field('jobs', 'Analyzer jobs', value('jobs'), help_text='Parallel local analyzer workers after profiles are collected. Full scan keeps this capped at 4.')}"
        f"{render_batch_number_field('metadata_jobs', 'Metadata refresh jobs', value('metadata_jobs'), help_text='Parallel read-only metadata refresh workers for top cases. Keep this low to protect Impala and the metastore. Hard cap: 4.')}"
        f"{render_batch_text_field('user', 'CM user', value('user'), help_text='Optional exact Cloudera Manager query user filter. Empty means all users.')}"
        f"{render_batch_text_field('pool', 'Resource pool', value('pool'), help_text='Optional Cloudera Manager pool filter. Empty means all pools.')}"
        "</div>"
        "<div class=\"batch-checkbox-row\">"
        f"<label><input type=\"checkbox\" name=\"include_failed\" value=\"on\"{checked('include_failed')}> Include failed</label>"
        f"<label><input type=\"checkbox\" name=\"include_running\" value=\"on\"{checked('include_running')}> Include running</label>"
        "<details class=\"info-popover info-popover--inline\"><summary aria-label=\"Status filter help\">i</summary>"
        "<div class=\"info-body\">Include failed or still-running CM query summaries in the candidate set.</div></details>"
        "</div>"
        "</div>"
        "</form></section>"
    )


def render_scan_mode_help(analysis_depth: str, *, metadata_configured: bool) -> str:
    full_text = (
        "Full scan collects bounded read-only metadata only for top-ranked cases after profile analysis."
        if metadata_configured
        else "Full scan requires metadata settings for this web session and is disabled right now."
    )
    fast_text = "Fast scan collects and analyzes profiles only; metadata collection is skipped."
    selected_text = full_text if analysis_depth == "full" else fast_text
    return (
        "<div class=\"info-body\" id=\"scan-mode-help\" data-full-help=\"{full}\" data-fast-help=\"{fast}\">{selected}</div>"
    ).format(
        full=html.escape(full_text, quote=True),
        fast=html.escape(fast_text, quote=True),
        selected=html.escape(selected_text),
    )


def default_recent_scan_bucket(now: datetime | None = None) -> tuple[str, int]:
    current = now.astimezone(RECENT_SCAN_TIMEZONE) if now else datetime.now(RECENT_SCAN_TIMEZONE)
    bucket = current.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    return bucket.date().isoformat(), bucket.hour


def recent_scan_date_options(now: datetime | None = None) -> list[tuple[str, str]]:
    current = now.astimezone(RECENT_SCAN_TIMEZONE).date() if now else datetime.now(RECENT_SCAN_TIMEZONE).date()
    return [
        ((current - timedelta(days=days)).isoformat(), (current - timedelta(days=days)).strftime("%d.%m"))
        for days in range(RECENT_SCAN_LOOKBACK_DAYS + 1)
    ]


def render_scan_date_select(selected_value: str) -> str:
    selected_raw = html.unescape(str(selected_value))
    options = recent_scan_date_options()
    option_values = {value for value, _ in options}
    if selected_raw and selected_raw not in option_values:
        options.append((selected_raw, f"{selected_raw} (selected)"))
    rendered_options = "".join(
        f"<option value=\"{html.escape(value, quote=True)}\"{' selected' if value == selected_raw else ''}>"
        f"{html.escape(label)}</option>"
        for value, label in options
    )
    return (
        "<div class=\"field\">"
        f"{render_label_with_info('scan_date', 'Scan date', 'Calendar day to inspect. Query Doctor keeps this bounded to today and the previous two days.')}"
        f"<select class=\"input\" id=\"scan_date\" name=\"scan_date\">{rendered_options}</select>"
        "</div>"
    )


def render_scan_hour_select(selected_value: str) -> str:
    selected_raw = html.unescape(str(selected_value))
    rendered_options = ""
    for hour in range(24):
        value = str(hour)
        end_hour = (hour + 1) % 24
        label = f"{hour:02d}:00 - {end_hour:02d}:00"
        rendered_options += (
            f"<option value=\"{value}\"{' selected' if value == selected_raw else ''}>"
            f"{html.escape(label)}</option>"
        )
    return (
        "<div class=\"field\">"
        f"{render_label_with_info('scan_hour', 'Hour bucket', 'One local-hour CM window to inspect. Times are shown in Europe/Moscow time and sent to CM as UTC bounds.')}"
        f"<select class=\"input\" id=\"scan_hour\" name=\"scan_hour\">{rendered_options}</select>"
        "</div>"
    )


def read_local_config_values(settings: Any) -> dict[str, object]:
    config_path = getattr(settings, "config", None)
    if config_path is None:
        return {}
    try:
        path = Path(config_path).expanduser()
        if not path.is_file():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def form_or_config_value(
    form_values: dict[str, Any] | None,
    form_key: str,
    *,
    config_values: dict[str, object],
    config_key: str | None = None,
    fallback: str = "",
    maximum: int | None = None,
) -> str:
    if form_values is not None and form_key in form_values:
        value = form_values.get(form_key)
        if value is not None:
            return str(value)
    value = config_values.get(config_key or form_key)
    if isinstance(value, bool) or value is None:
        return fallback
    if isinstance(value, (int, float, str)):
        text = str(value)
        if maximum is not None:
            try:
                if int(float(text)) > maximum:
                    return str(maximum)
            except (TypeError, ValueError):
                pass
        return text
    return fallback


def form_or_config_bool(
    form_values: dict[str, Any] | None,
    form_key: str,
    *,
    config_values: dict[str, object],
    config_key: str | None = None,
    fallback: bool = False,
) -> bool:
    if form_values is not None and form_key in form_values:
        return bool(form_values.get(form_key))
    value = config_values.get(config_key or form_key)
    if isinstance(value, bool):
        return value
    return fallback


def render_batch_number_field(
    name: str,
    label: str,
    value: str,
    *,
    step: str = "1",
    required: bool = True,
    help_text: str = "",
) -> str:
    required_attr = " required" if required else ""
    return (
        f"<div class=\"field\">{render_label_with_info(name, label, help_text)}"
        f"<input class=\"input\" id=\"{html.escape(name, quote=True)}\" name=\"{html.escape(name, quote=True)}\" "
        f"type=\"number\" min=\"0\" step=\"{html.escape(step, quote=True)}\" value=\"{value}\"{required_attr}>"
        "</div>"
    )


def render_batch_text_field(name: str, label: str, value: str, *, help_text: str = "") -> str:
    return (
        f"<div class=\"field\">{render_label_with_info(name, label, help_text)}"
        f"<input class=\"input\" id=\"{html.escape(name, quote=True)}\" name=\"{html.escape(name, quote=True)}\" "
        f"type=\"text\" value=\"{value}\" autocomplete=\"off\"></div>"
    )


def render_label_with_info(field_id: str, label: str, help_text: str = "") -> str:
    safe_id = html.escape(field_id, quote=True)
    safe_label = html.escape(label)
    if not help_text:
        return f"<label for=\"{safe_id}\">{safe_label}</label>"
    return (
        "<div class=\"label-row\">"
        f"<label for=\"{safe_id}\">{safe_label}</label>"
        "<details class=\"info-popover\">"
        f"<summary aria-label=\"{safe_label} help\">i</summary>"
        f"<div class=\"info-body\">{html.escape(help_text)}</div>"
        "</details></div>"
    )
