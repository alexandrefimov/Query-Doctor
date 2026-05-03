"""Recent query scan form rendering helpers."""

from __future__ import annotations

import html
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


WEB_RECENT_SCAN_DEFAULTS = {
    "parallelism": "50",
    "metadata_jobs": "5",
}
RECENT_SCAN_TIMEZONE = ZoneInfo("Europe/Moscow")
RECENT_SCAN_LOOKBACK_DAYS = 2


def render_batch_run_panel(settings: Any, form_values: dict[str, Any] | None = None, *, run_disabled: bool = False) -> str:
    metadata_configured = bool(getattr(settings, "metadata_coordinator", None))
    local_config = read_local_config_values(settings)
    if "recent_parallelism" not in local_config and "recent_cm_jobs" in local_config:
        local_config["recent_parallelism"] = local_config["recent_cm_jobs"]
    default_scan_date, default_scan_hour = default_recent_scan_bucket()
    default_parallelism = WEB_RECENT_SCAN_DEFAULTS["parallelism"]
    values = {
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
        "min_duration_sec": form_or_config_value(
            form_values,
            "min_duration_sec",
            config_values=local_config,
            config_key="recent_min_duration_sec",
        ),
        "max_duration_sec": "",
        "parallelism": form_or_config_value(
            form_values,
            "parallelism",
            config_values=local_config,
            config_key="recent_parallelism",
            fallback=default_parallelism,
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
    }
    if form_values:
        values.update(form_values)

    def value(name: str) -> str:
        return html.escape(str(values.get(name, "")), quote=True)

    metadata_note = "" if metadata_configured else "Metadata collection is not configured for this web session."
    metadata_note_html = f"<div class=\"batch-note\">{html.escape(metadata_note)}</div>" if metadata_note else ""
    button_disabled = " disabled" if run_disabled else ""
    button_label = "Running" if run_disabled else "Run scan"
    return (
        "<section class=\"panel batch-run-panel\" aria-label=\"Run recent query scan\">"
        "<div class=\"section-heading\"><div>"
        "<h1 class=\"section-title\">Finished Queries</h1>"
        "<div class=\"section-kicker\">Scan recent Impala queries from Cloudera Manager summaries.</div>"
        "</div></div>"
        "<form id=\"batch-form\" class=\"batch-form\" method=\"post\" action=\"/batch/run\">"
        f"{metadata_note_html}"
        "<div class=\"scope-line\" aria-label=\"Recent scan collection scope\">"
        "<strong>Scope:</strong> one selected CM hour → matching summaries → analyzable profiles → ranked cases → automatic metadata for top bad/suspicious cases · no auto LLM"
        "</div>"
        "<div class=\"batch-form-sections\">"
        "<fieldset class=\"batch-form-section\"><legend>Query filters</legend>"
        "<div class=\"batch-form-grid\">"
        f"{render_scan_date_select(value('scan_date'))}"
        f"{render_scan_hour_select(value('scan_hour'), scan_date=value('scan_date'))}"
        f"{render_batch_number_field('min_duration_sec', 'Minimum duration (sec)', value('min_duration_sec'), step='0.001', required=False, help_text='Only include queries at least this long. Empty means no duration filter.')}"
        f"{render_batch_text_field('user', 'Username', value('user'), help_text='Optional exact Cloudera Manager query user filter. Empty means all users.')}"
        f"{render_batch_text_field('pool', 'Resource pool', value('pool'), help_text='Optional Cloudera Manager pool filter. Empty means all pools.')}"
        "</div>"
        "</fieldset>"
        "<fieldset class=\"batch-form-section\"><legend>Analysis settings</legend>"
        "<div class=\"batch-form-grid\">"
        f"{render_batch_number_field('parallelism', 'Parallelism', value('parallelism'), help_text='Parallel workers for CM profile downloads and local analysis. Hard cap: 100.')}"
        f"{render_batch_number_field('metadata_jobs', 'Metadata parallelism', value('metadata_jobs'), help_text='Parallel read-only metadata refresh workers for top queries. Keep this bounded to protect Impala and the metastore. Hard cap: 5.')}"
        "</div>"
        "</fieldset>"
        "</div>"
        "<div class=\"batch-actions\">"
        f"<button class=\"run-button\" type=\"submit\"{button_disabled}>{button_label}</button>"
        "</div>"
        "</form></section>"
    )


def default_recent_scan_bucket(now: datetime | None = None) -> tuple[str, int]:
    current = now.astimezone(RECENT_SCAN_TIMEZONE) if now else datetime.now(RECENT_SCAN_TIMEZONE)
    bucket = current.replace(minute=0, second=0, microsecond=0)
    return bucket.date().isoformat(), bucket.hour


def recent_scan_date_options(now: datetime | None = None) -> list[tuple[str, str]]:
    current = now.astimezone(RECENT_SCAN_TIMEZONE).date() if now else datetime.now(RECENT_SCAN_TIMEZONE).date()
    return [
        ((current - timedelta(days=days)).isoformat(), (current - timedelta(days=days)).strftime("%d.%m.%Y"))
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


def latest_selectable_scan_bucket(now: datetime | None = None) -> tuple[str, int]:
    return default_recent_scan_bucket(now)


def scan_hour_options(scan_date: str, now: datetime | None = None) -> list[tuple[str, str]]:
    latest_date, latest_hour = latest_selectable_scan_bucket(now)
    max_hour = latest_hour if scan_date == latest_date else 23
    if scan_date > latest_date:
        max_hour = -1
    return [
        (str(hour), f"{hour:02d}:00 - {(hour + 1) % 24:02d}:00")
        for hour in range(max_hour + 1)
    ]


def render_scan_hour_select(selected_value: str, *, scan_date: str = "") -> str:
    selected_raw = html.unescape(str(selected_value))
    selected_date = html.unescape(str(scan_date))
    options = scan_hour_options(selected_date or default_recent_scan_bucket()[0])
    option_values = {value for value, _label in options}
    if selected_raw and selected_raw not in option_values:
        try:
            selected_hour = int(selected_raw)
        except ValueError:
            selected_hour = -1
        if 0 <= selected_hour <= 23:
            options.append((selected_raw, f"{selected_hour:02d}:00 - {(selected_hour + 1) % 24:02d}:00 (selected)"))
    rendered_options = ""
    for value, label in options:
        rendered_options += (
            f"<option value=\"{value}\"{' selected' if value == selected_raw else ''}>"
            f"{html.escape(label)}</option>"
        )
    return (
        "<div class=\"field\">"
        f"{render_label_with_info('scan_hour', 'Scan Hour', 'One local-hour CM window to inspect. Times are shown in Europe/Moscow time and sent to CM as UTC bounds.')}"
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
