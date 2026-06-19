"""HTML rendering for the safe Spark compact diagnosis page."""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from typing import Any

from query_doctor.web.display_safety import sanitize_browser_error_text
from query_doctor.web.ui.errors import render_error_panel
from query_doctor.web.ui.pages import render_page


def render_spark_compact_page(
    settings: Any,
    *,
    result: Mapping[str, Any] | None = None,
    error: object | None = None,
    collection_status: Mapping[str, Any] | None = None,
) -> str:
    sections = [render_spark_history_panel(), render_spark_compact_panel()]
    if error is not None:
        sections.append(render_spark_compact_error_panel(error))
    if result is not None:
        sections.append(render_spark_compact_result(result, collection_status=collection_status))
    return render_page(
        settings,
        active_nav="batch",
        show_run_panel=False,
        extra_sections=sections,
    )


def render_spark_history_panel() -> str:
    return (
        '<section class="panel optimizer-panel spark-history-panel" '
        'aria-label="Spark History Server compact collection">'
        '<div class="section-heading"><div>'
        '<h1 class="section-title">Spark compact diagnosis</h1>'
        '<div class="section-kicker">Experimental local intake for one explicit Spark application through summary-only History Server JSON.</div>'
        "</div></div>"
        '<form class="optimizer-form spark-history-form" method="post" '
        'action="/spark/compact-diagnosis">'
        '<input type="hidden" name="spark_compact_action" value="history_server">'
        f"{render_text_input('history_server_url', 'History Server base URL', required=True)}"
        f"{render_text_input('application_id', 'Application id', required=True)}"
        f"{render_text_input('application_attempt_id', 'Application attempt id', required=False)}"
        f"{render_text_input('sql_execution_id', 'SQL execution id', required=False)}"
        f"{render_spark_history_bounds()}"
        '<div class="optimizer-actions-row">'
        '<button class="run-button" type="submit">Collect and diagnose</button>'
        "</div>"
        f"{render_spark_history_scope_details()}"
        "</form></section>"
    )


def render_spark_compact_panel() -> str:
    return (
        '<section class="panel optimizer-panel spark-compact-panel" '
        'aria-label="Paste Spark compact JSON">'
        '<div class="section-heading"><div>'
        '<h2 class="section-title">Paste compact JSON</h2>'
        '<div class="section-kicker">Use an already accepted raw-free Spark compact summary without calling Spark services.</div>'
        "</div></div>"
        '<form class="optimizer-form spark-compact-form" method="post" '
        'action="/spark/compact-diagnosis">'
        '<input type="hidden" name="spark_compact_action" value="compact_json">'
        '<div class="field">'
        '<label for="spark_compact_json">Compact Spark JSON</label>'
        '<textarea class="input optimizer-sql spark-compact-json" id="spark_compact_json" '
        'name="compact_json" aria-describedby="spark_compact_json_help" required></textarea>'
        '<p class="helper optimizer-field-help" id="spark_compact_json_help">'
        "Paste one accepted compact Spark JSON summary. Query Doctor validates it locally, "
        "does not execute Spark jobs, does not ingest event logs, and clears the input after submit."
        "</p>"
        "</div>"
        '<div class="optimizer-actions-row">'
        '<button class="run-button" type="submit">Diagnose compact summary</button>'
        "</div>"
        f"{render_spark_compact_scope_details()}"
        "</form></section>"
    )


def render_text_input(name: str, label: str, *, required: bool) -> str:
    safe_name = html.escape(name, quote=True)
    required_attr = " required" if required else ""
    return (
        '<div class="field">'
        f'<label for="{safe_name}">{html.escape(label)}</label>'
        f'<input class="input" id="{safe_name}" name="{safe_name}" '
        f'type="text" autocomplete="off"{required_attr}>'
        "</div>"
    )


def render_number_input(name: str, label: str, value: int, maximum: int) -> str:
    safe_name = html.escape(name, quote=True)
    return (
        '<div class="field">'
        f'<label for="{safe_name}">{html.escape(label)}</label>'
        f'<input class="input" id="{safe_name}" name="{safe_name}" '
        f'type="number" min="1" max="{maximum}" step="1" value="{value}" required>'
        "</div>"
    )


def render_checkbox_input(name: str, label: str) -> str:
    safe_name = html.escape(name, quote=True)
    return (
        '<div class="field checkbox-field">'
        f'<label for="{safe_name}">'
        f'<input id="{safe_name}" name="{safe_name}" type="checkbox" value="on"> '
        f"{html.escape(label)}"
        "</label>"
        '<p class="helper optimizer-field-help">'
        "Required for explicit loopback, private-network, carrier-grade NAT, or unique-local targets. "
        "Metadata, link-local, reserved, documentation, multicast, and unspecified targets stay blocked."
        "</p>"
        "</div>"
    )


def render_spark_history_bounds() -> str:
    return (
        '<details class="compact-details optimizer-scope-details spark-history-bounds">'
        "<summary>Collection bounds</summary>"
        '<div class="compact-details-body">'
        '<div class="optimizer-form">'
        f"{render_checkbox_input('allow_local_history_server_target', 'Allow local/private History Server target')}"
        f"{render_number_input('timeout_sec', 'Endpoint timeout seconds', 15, 60)}"
        f"{render_number_input('max_response_bytes', 'Response bytes per endpoint', 2097152, 16777216)}"
        f"{render_number_input('max_application_attempts', 'Application attempts to compact', 16, 50)}"
        f"{render_number_input('max_sql_executions', 'SQL executions to inspect', 10, 50)}"
        f"{render_number_input('max_jobs', 'Linked jobs to compact', 200, 500)}"
        f"{render_number_input('max_stages', 'Linked stages to compact', 500, 1000)}"
        f"{render_number_input('max_task_summaries', 'Stage task summaries to inspect', 32, 100)}"
        f"{render_number_input('max_tasks_sampled', 'Task sample cap', 256, 1000)}"
        "</div>"
        "</div>"
        "</details>"
    )


def render_spark_history_scope_details() -> str:
    return (
        '<details class="compact-details optimizer-scope-details spark-history-scope">'
        "<summary>History Server safety</summary>"
        '<div class="compact-details-body">'
        '<ul class="optimizer-scope-list">'
        "<li><strong>Input:</strong> one explicit application selector; request selectors are not displayed back.</li>"
        "<li><strong>Requests:</strong> summary-only REST JSON with SQL details and plan descriptions disabled.</li>"
        "<li><strong>Skipped:</strong> no event logs, environment dumps, driver logs, executor logs, raw SQL, or plans.</li>"
        "<li><strong>Status:</strong> experimental compact intake only; this is not full Spark product support.</li>"
        "</ul>"
        "</div>"
        "</details>"
    )


def render_spark_compact_error_panel(error: object) -> str:
    return render_error_panel(
        error,
        default_title="Safe Spark compact state",
        footer="Submitted compact JSON is not displayed back, and rejected input is hidden.",
    )


def render_spark_compact_scope_details() -> str:
    return (
        '<details class="compact-details optimizer-scope-details spark-compact-scope">'
        "<summary>Scope and safety</summary>"
        '<div class="compact-details-body">'
        '<ul class="optimizer-scope-list">'
        "<li><strong>Input:</strong> one raw-free compact Spark summary that already follows the local contract.</li>"
        "<li><strong>Collection:</strong> no Spark job execution - no event log ingestion - no raw plans or SQL.</li>"
        "<li><strong>Output:</strong> attention areas - limitations - verification direction, without raw input echo.</li>"
        "<li><strong>Status:</strong> experimental compact intake only; this is not full Spark product support.</li>"
        "</ul>"
        "</div>"
        "</details>"
    )


def render_spark_compact_result(
    result: Mapping[str, Any],
    *,
    collection_status: Mapping[str, Any] | None = None,
) -> str:
    return (
        '<section class="panel optimizer-result spark-compact-result" '
        'aria-label="Spark compact diagnosis result">'
        '<div class="section-heading"><div>'
        '<h2 class="section-title">Diagnosis result</h2>'
        '<div class="section-kicker">Deterministic compact-fact checks only. Root cause is not claimed.</div>'
        "</div></div>"
        f"{render_spark_collection_status(collection_status)}"
        f"{render_spark_compact_status(result)}"
        f"{render_spark_diagnostic_lane(result.get('diagnostic_lane'))}"
        f"{render_spark_runtime_context(result.get('runtime_context'))}"
        f"{render_spark_attention_areas(result.get('attention_areas'))}"
        f"{render_spark_limitations(result.get('limitations'))}"
        f"{render_spark_boundary(result.get('diagnosis_boundary'))}"
        "</section>"
    )


def render_spark_collection_status(value: Mapping[str, Any] | None) -> str:
    if not value:
        return ""
    attempted = int_value(value.get("attempted_endpoints"))
    successful = int_value(value.get("successful_endpoints"))
    warnings = tuple(text_value(item) for item in sequence_value(value.get("warnings")))
    warning_rows = "".join(f"<li>{html.escape(warning)}</li>" for warning in warnings if warning)
    warning_block = f'<ul class="optimizer-scope-list">{warning_rows}</ul>' if warning_rows else ""
    return (
        '<div class="optimizer-block">'
        "<h3>Collection result</h3>"
        '<p class="helper">'
        f"Summary endpoints accepted: {successful}/{attempted}. "
        "Request selectors and compact JSON are not displayed."
        "</p>"
        f"{warning_block}"
        "</div>"
    )


def render_spark_compact_status(result: Mapping[str, Any]) -> str:
    support_status = safe_status_label(result.get("support_status"))
    parser_coverage = safe_status_label(result.get("parser_coverage"))
    lifecycle = safe_status_label(result.get("lifecycle"))
    return (
        '<div class="optimizer-block">'
        "<h3>Accepted summary status</h3>"
        '<ul class="optimizer-table-list spark-compact-status-list">'
        f'<li><strong>Engine</strong> <span class="badge blue">Spark</span></li>'
        f'<li><strong>Mode</strong> <span class="badge amber">{html.escape(support_status)}</span></li>'
        f'<li><strong>Coverage</strong> <span class="badge {badge_for_state(parser_coverage)}">{html.escape(parser_coverage)}</span></li>'
        f'<li><strong>Lifecycle</strong> <span class="badge gray">{html.escape(lifecycle)}</span></li>'
        "</ul>"
        "</div>"
    )


def render_spark_diagnostic_lane(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    readiness = safe_status_label(value.get("evidence_readiness"))
    granularity = safe_status_label(value.get("source_granularity"))
    verification_scope = safe_status_label(value.get("verification_scope"))
    supported_count = int_value(value.get("supported_attention_area_count"))
    source_warning_count = int_value(value.get("source_warning_count"))
    return (
        '<div class="optimizer-block spark-diagnostic-lane">'
        "<h3>Diagnostic lane</h3>"
        '<p class="helper">'
        "Preview lane contract for this compact evidence. It is not a Spark support claim."
        "</p>"
        '<ul class="optimizer-table-list spark-compact-status-list">'
        f'<li><strong>Readiness</strong> <span class="badge {badge_for_lane_readiness(readiness)}">{html.escape(readiness)}</span></li>'
        f'<li><strong>Granularity</strong> <span class="badge gray">{html.escape(granularity)}</span></li>'
        f'<li><strong>Verification scope</strong> <span class="badge blue">{html.escape(verification_scope)}</span></li>'
        f"<li><strong>Supported attention areas</strong> {supported_count}</li>"
        f"<li><strong>Source warnings</strong> {source_warning_count}</li>"
        "</ul>"
        "</div>"
    )


def render_spark_runtime_context(value: object) -> str:
    items = tuple(mapping_items(value))
    if not items:
        return ""
    rows = "".join(render_spark_runtime_context_row(item) for item in items)
    return (
        '<div class="optimizer-block spark-runtime-context">'
        "<h3>Runtime context</h3>"
        '<p class="helper">'
        "Aggregate Spark compact values only. They add context but do not claim a root cause."
        "</p>"
        '<ul class="optimizer-table-list spark-runtime-context-list">'
        f"{rows}"
        "</ul>"
        "</div>"
    )


def render_spark_runtime_context_row(item: Mapping[str, Any]) -> str:
    label = text_value(item.get("label")) or "Spark context"
    state = safe_status_label(item.get("state"))
    observed = format_context_observed_value(item.get("observed_value"))
    if not observed:
        return ""
    return (
        "<li>"
        f"<strong>{html.escape(label)}</strong> "
        f"<span>{html.escape(observed)}</span> "
        f'<span class="badge {badge_for_state(state)}">{html.escape(state)}</span>'
        "</li>"
    )


def render_spark_attention_areas(value: object) -> str:
    areas = tuple(mapping_items(value))
    cards = "".join(render_spark_attention_card(area) for area in areas)
    if not cards:
        cards = (
            '<article class="reason-card optimizer-finding">'
            "<strong>No attention areas</strong>"
            "<p>The accepted compact summary did not produce supported attention signals.</p>"
            '<span class="badge gray">not_observed</span>'
            "</article>"
        )
    return (
        '<div class="optimizer-block">'
        "<h3>Attention areas</h3>"
        f'<div class="optimizer-findings spark-attention-areas">{cards}</div>'
        "</div>"
    )


def render_spark_attention_card(area: Mapping[str, Any]) -> str:
    state = safe_status_label(area.get("state"))
    observed = render_observed_value(area.get("observed_value"))
    return (
        '<article class="reason-card optimizer-finding spark-attention-card">'
        f"<strong>{html.escape(label_from_id(area.get('id'), fallback='Spark attention area'))}</strong>"
        f"<p>{html.escape(text_value(area.get('summary')))}</p>"
        f"{observed}"
        '<div class="source-locator-block">'
        '<span class="source-locator-heading">Change direction</span>'
        f"<p>{html.escape(text_value(area.get('change_direction')))}</p>"
        "</div>"
        '<div class="source-locator-block">'
        '<span class="source-locator-heading">Verification</span>'
        f"<p>{html.escape(text_value(area.get('verification')))}</p>"
        "</div>"
        f'<span class="badge {badge_for_state(state)}">{html.escape(state)}</span>'
        "</article>"
    )


def render_observed_value(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    used_ratio = value.get("used_ratio")
    if isinstance(used_ratio, (int, float)) and not isinstance(used_ratio, bool):
        if 0 <= used_ratio <= 1:
            label = f"{used_ratio * 100:.1f}% executor memory used"
            return f"<p><strong>Observed:</strong> {html.escape(label)}</p>"
    raw_number = value.get("value")
    if isinstance(raw_number, str):
        label = text_value(raw_number).replace("_", " ")
        if label:
            return f"<p><strong>Observed:</strong> {html.escape(label)}</p>"
    if not isinstance(raw_number, (int, float)) or isinstance(raw_number, bool):
        return ""
    unit = text_value(value.get("unit"))
    label = f"{raw_number:g}" if isinstance(raw_number, float) else str(raw_number)
    if unit:
        label = f"{label} {unit}"
    return f"<p><strong>Observed:</strong> {html.escape(label)}</p>"


def format_context_observed_value(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    unit = text_value(value.get("unit"))
    raw_number = value.get("value")
    if isinstance(raw_number, bool):
        return "yes" if raw_number else "no"
    if not isinstance(raw_number, (int, float)):
        return text_value(raw_number)
    if unit == "bytes":
        return format_bytes(raw_number)
    if unit == "ms":
        return format_millis(raw_number)
    number = format_number(raw_number)
    return f"{number} {unit}" if unit else number


def format_bytes(value: int | float) -> str:
    if value < 0:
        return ""
    units = ("bytes", "KiB", "MiB", "GiB", "TiB")
    scaled = float(value)
    unit = units[0]
    for candidate in units[1:]:
        if scaled < 1024:
            break
        scaled /= 1024
        unit = candidate
    if unit == "bytes":
        return f"{format_number(value)} bytes"
    return f"{scaled:.1f} {unit}"


def format_millis(value: int | float) -> str:
    if value < 0:
        return ""
    if value >= 1000:
        return f"{float(value) / 1000:.1f} s"
    return f"{format_number(value)} ms"


def format_number(value: int | float) -> str:
    if isinstance(value, int) or float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def render_spark_limitations(value: object) -> str:
    limitations = tuple(mapping_items(value))
    if not limitations:
        return ""
    rows = "".join(
        "<li>"
        f"<strong>{html.escape(label_from_id(item.get('id'), fallback='Limitation'))}</strong> "
        f'<span class="badge {badge_for_state(safe_status_label(item.get("state")))}">'
        f"{html.escape(safe_status_label(item.get('state')))}</span>"
        f"<p>{html.escape(text_value(item.get('summary')))}</p>"
        "</li>"
        for item in limitations
    )
    return (
        '<details class="compact-details optimizer-reading-guide spark-limitations" open>'
        "<summary>Limitations</summary>"
        '<div class="compact-details-body">'
        f'<ul class="optimizer-scope-list">{rows}</ul>'
        "</div>"
        "</details>"
    )


def render_spark_boundary(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    root_cause = safe_status_label(value.get("root_cause"))
    report_surface = safe_status_label(
        value.get("details_trusted_report_surface") or value.get("browser_report_surface")
    )
    optimizer_behavior = safe_status_label(value.get("optimizer_behavior"))
    spark_execution = safe_status_label(value.get("spark_job_execution"))
    return (
        '<details class="compact-details optimizer-reading-guide spark-boundary">'
        "<summary>Diagnosis boundary</summary>"
        '<div class="compact-details-body">'
        "<p>"
        f'Root cause: <span class="badge gray">{html.escape(root_cause)}</span> '
        f'Details/trusted report wiring: <span class="badge gray">{html.escape(report_surface)}</span> '
        f'Optimizer behavior: <span class="badge gray">{html.escape(optimizer_behavior)}</span> '
        f'Spark execution: <span class="badge gray">{html.escape(spark_execution)}</span>'
        "</p>"
        "</div>"
        "</details>"
    )


def mapping_items(value: object) -> Sequence[Mapping[str, Any]]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def sequence_value(value: object) -> Sequence[object]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(value)


def int_value(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def label_from_id(value: object, *, fallback: str) -> str:
    text = text_value(value)
    if not text:
        return fallback
    labels = {
        "no_browser_report_surface": "No Details or trusted reports",
    }
    if text in labels:
        return labels[text]
    return text.replace("_", " ").capitalize()


def safe_status_label(value: object) -> str:
    text = text_value(value)
    if not text:
        return "unknown"
    return text


def text_value(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return sanitize_browser_error_text(value, max_chars=260)


def badge_for_state(state: str) -> str:
    return {
        "supported": "green",
        "not_observed": "gray",
        "unknown": "amber",
        "unsupported": "amber",
        "not_claimed": "gray",
        "not_wired": "gray",
        "not_performed": "gray",
        "experimental_compact_intake": "amber",
    }.get(state, "gray")


def badge_for_lane_readiness(value: str) -> str:
    return {
        "compact_attention_ready": "green",
        "compact_limited_no_supported_attention": "amber",
        "compact_source_warnings_present": "amber",
        "source_coverage_unknown": "amber",
    }.get(value, "gray")
