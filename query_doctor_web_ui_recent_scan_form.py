"""Recent query scan form rendering helpers."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def render_batch_run_panel(settings: Any, form_values: dict[str, Any] | None = None, *, run_disabled: bool = False) -> str:
    metadata_configured = bool(getattr(settings, "metadata_coordinator", None))
    local_config = read_local_config_values(settings)
    values = {
        "analysis_depth": "full" if metadata_configured else "fast",
        "recent_window_minutes": form_or_config_value(
            form_values,
            "recent_window_minutes",
            config_values=local_config,
            config_key="recent_window_minutes",
            fallback="30",
        ),
        "cm_inspect_limit": form_or_config_value(
            form_values,
            "cm_inspect_limit",
            config_values=local_config,
            config_key="recent_cm_summary_limit",
        ),
        "triage_profile_limit": form_or_config_value(
            form_values,
            "triage_profile_limit",
            config_values=local_config,
            config_key="recent_profile_analysis_limit",
        ),
        "metadata_top_limit": form_or_config_value(
            form_values,
            "metadata_top_limit",
            config_values=local_config,
            config_key="recent_metadata_top_limit",
        ),
        "min_duration_sec": form_or_config_value(
            form_values,
            "min_duration_sec",
            config_values=local_config,
            config_key="recent_min_duration_sec",
        ),
        "max_duration_sec": "",
        "order": form_or_config_value(
            form_values,
            "order",
            config_values=local_config,
            config_key="recent_order",
            fallback="duration-desc",
        ),
        "jobs": "4",
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

    order = str(values.get("order") or "duration-desc")
    analysis_depth = str(values.get("analysis_depth") or "full")
    if not metadata_configured and analysis_depth == "full":
        analysis_depth = "fast"
        values["analysis_depth"] = "fast"
    full_checked = " checked" if analysis_depth == "full" else ""
    fast_checked = " checked" if analysis_depth == "fast" else ""
    full_disabled = "" if metadata_configured else " disabled"
    full_label = (
        "Full scan: include table metadata"
        if metadata_configured
        else "Full scan: include table metadata (unavailable: metadata not configured)"
    )
    metadata_note = "" if metadata_configured else "Metadata collection is not configured for this web session. Fast scan still works."
    metadata_note_html = f"<div class=\"batch-note\">{html.escape(metadata_note)}</div>" if metadata_note else ""
    order_options = "".join(
        f"<option value=\"{html.escape(option, quote=True)}\"{' selected' if option == order else ''}>{html.escape(option)}</option>"
        for option in ("duration-desc", "recent", "duration-asc")
    )
    button_disabled = " disabled" if run_disabled else ""
    button_label = "Running" if run_disabled else "Run scan"
    return (
        "<section class=\"panel batch-run-panel\" aria-label=\"Run recent query scan\">"
        "<div class=\"section-heading\"><div>"
        "<h1 class=\"section-title\">Recent query scan</h1>"
        "<div class=\"section-kicker\">Collect recent Impala query profiles, rank suspicious cases, "
        "and prepare the most relevant ones for deeper analysis.<br>"
        "LLM report generation stays disabled for web batch runs.</div>"
        "</div></div>"
        "<form id=\"batch-form\" class=\"batch-form\" method=\"post\" action=\"/batch/run\">"
        "<div class=\"batch-checkbox-row\" role=\"group\" aria-label=\"Analysis depth\">"
        f"<label><input type=\"radio\" name=\"analysis_depth\" value=\"full\"{full_checked}{full_disabled}> "
        f"{html.escape(full_label)}</label>"
        f"<label><input type=\"radio\" name=\"analysis_depth\" value=\"fast\"{fast_checked}> "
        "Fast scan: profiles only</label>"
        "</div>"
        f"{metadata_note_html}"
        "<div class=\"batch-primary-row\">"
        f"{render_recent_window_select(value('recent_window_minutes'))}"
        f"<button class=\"run-button\" type=\"submit\"{button_disabled}>{button_label}</button>"
        "</div>"
        "<details class=\"batch-advanced\">"
        "<summary>Advanced search parameters</summary>"
        "<div class=\"batch-advanced-body\">"
        "<div class=\"batch-form-grid\">"
        f"{render_batch_number_field('cm_inspect_limit', 'CM summary limit', value('cm_inspect_limit'), required=False)}"
        f"{render_batch_number_field('triage_profile_limit', 'Profile analysis limit', value('triage_profile_limit'), required=False)}"
        f"{render_batch_number_field('metadata_top_limit', 'Metadata top cases', value('metadata_top_limit'), required=False)}"
        f"{render_batch_number_field('min_duration_sec', 'Min duration sec', value('min_duration_sec'), step='0.001', required=False)}"
        "<div class=\"field\"><label for=\"order\">Order</label>"
        f"<select class=\"input\" id=\"order\" name=\"order\">{order_options}</select></div>"
        f"{render_batch_number_field('jobs', 'Jobs', value('jobs'))}"
        f"{render_batch_text_field('user', 'User filter', value('user'))}"
        f"{render_batch_text_field('pool', 'Pool filter', value('pool'))}"
        "</div>"
        "<div class=\"batch-checkbox-row\">"
        f"<label><input type=\"checkbox\" name=\"include_failed\" value=\"on\"{checked('include_failed')}> Include failed</label>"
        f"<label><input type=\"checkbox\" name=\"include_running\" value=\"on\"{checked('include_running')}> Include running</label>"
        "</div>"
        "</div>"
        "</details>"
        "</form></section>"
    )


def render_recent_window_select(selected_value: str) -> str:
    options = [
        ("10", "10 minutes"),
        ("30", "30 minutes"),
        ("60", "1 hour"),
        ("120", "2 hours"),
        ("360", "6 hours"),
        ("720", "12 hours"),
        ("1440", "24 hours"),
    ]
    selected_raw = html.unescape(str(selected_value))
    option_values = {value for value, _ in options}
    if selected_raw and selected_raw not in option_values:
        options.append((selected_raw, f"{format_recent_window_label(selected_raw)} (configured)"))
    rendered_options = "".join(
        f"<option value=\"{html.escape(value, quote=True)}\"{' selected' if value == selected_raw else ''}>"
        f"{html.escape(label)}</option>"
        for value, label in options
    )
    return (
        "<div class=\"field\"><label for=\"recent_window_minutes\">Search depth</label>"
        f"<select class=\"input\" id=\"recent_window_minutes\" name=\"recent_window_minutes\">{rendered_options}</select></div>"
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
) -> str:
    if form_values is not None and form_key in form_values:
        value = form_values.get(form_key)
        if value is not None:
            return str(value)
    value = config_values.get(config_key or form_key)
    if isinstance(value, bool) or value is None:
        return fallback
    if isinstance(value, (int, float, str)):
        return str(value)
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


def format_recent_window_label(value: str) -> str:
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return f"{value} minutes"
    if minutes < 60:
        return f"{minutes} minutes"
    if minutes == 60:
        return "1 hour"
    if minutes % 60 == 0:
        return f"{minutes // 60} hours"
    return f"{minutes} minutes"


def render_batch_number_field(name: str, label: str, value: str, *, step: str = "1", required: bool = True) -> str:
    required_attr = " required" if required else ""
    return (
        f"<div class=\"field\"><label for=\"{html.escape(name, quote=True)}\">{html.escape(label)}</label>"
        f"<input class=\"input\" id=\"{html.escape(name, quote=True)}\" name=\"{html.escape(name, quote=True)}\" "
        f"type=\"number\" min=\"0\" step=\"{html.escape(step, quote=True)}\" value=\"{value}\"{required_attr}></div>"
    )


def render_batch_text_field(name: str, label: str, value: str) -> str:
    return (
        f"<div class=\"field\"><label for=\"{html.escape(name, quote=True)}\">{html.escape(label)}</label>"
        f"<input class=\"input\" id=\"{html.escape(name, quote=True)}\" name=\"{html.escape(name, quote=True)}\" "
        f"type=\"text\" value=\"{value}\" autocomplete=\"off\"></div>"
    )
