"""HTML rendering for the safe Trino compact diagnosis page."""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from typing import Any

from query_doctor.web.display_safety import sanitize_browser_error_text
from query_doctor.web.ui.pages import render_page


def render_trino_compact_page(
    settings: Any,
    *,
    result: Mapping[str, Any] | None = None,
    error: object | None = None,
) -> str:
    sections = [render_trino_compact_panel()]
    if error is not None:
        sections.append(render_trino_compact_error_panel(error))
    if result is not None:
        sections.append(render_trino_compact_result(result))
    return render_page(
        settings,
        active_nav="batch",
        show_run_panel=False,
        extra_sections=sections,
    )


def render_trino_compact_panel() -> str:
    return (
        '<section class="panel optimizer-panel trino-compact-panel" '
        'aria-label="Paste Trino boundary JSON">'
        '<div class="section-heading"><div>'
        '<h1 class="section-title">Trino compact diagnosis</h1>'
        '<div class="section-kicker">Bounded local diagnosis for one already raw-free Trino engine fact boundary.</div>'
        "</div></div>"
        '<form class="optimizer-form trino-compact-form" method="post" '
        'action="/trino/compact-diagnosis">'
        '<div class="field">'
        '<label for="trino_boundary_json">Raw-free Trino boundary JSON</label>'
        '<textarea class="input optimizer-sql trino-boundary-json" id="trino_boundary_json" '
        'name="boundary_json" aria-describedby="trino_boundary_json_help" required></textarea>'
        '<p class="helper optimizer-field-help" id="trino_boundary_json_help">'
        "Paste one accepted normalized boundary payload, or a package boundary export "
        "from query-doctor-trino-import --format boundary-json. Query Doctor validates it "
        "locally, does not contact Trino, does not submit SQL, and clears the input after submit."
        "</p>"
        "</div>"
        '<div class="field">'
        '<label for="trino_sample_index">Package sample index</label>'
        '<input class="input" id="trino_sample_index" name="sample_index" '
        'type="number" min="0" step="1" inputmode="numeric" '
        'aria-describedby="trino_sample_index_help">'
        '<p class="helper optimizer-field-help" id="trino_sample_index_help">'
        "Required only when a pasted package boundary export contains multiple sample boundaries."
        "</p>"
        "</div>"
        '<div class="optimizer-actions-row">'
        '<button class="run-button" type="submit">Diagnose boundary</button>'
        "</div>"
        f"{render_trino_compact_scope_details()}"
        "</form></section>"
    )


def render_trino_compact_scope_details() -> str:
    return (
        '<details class="compact-details optimizer-scope-details trino-compact-scope">'
        "<summary>Scope and safety</summary>"
        '<div class="compact-details-body">'
        '<ul class="optimizer-scope-list">'
        "<li><strong>Input:</strong> one raw-free Trino engine fact boundary, or one selected sample boundary from an approved package export.</li>"
        "<li><strong>Collection:</strong> no Trino coordinator calls, query-history crawl, metadata collection, or SQL execution.</li>"
        "<li><strong>Output:</strong> attention areas, limitations, and verification direction without raw input echo.</li>"
        "<li><strong>Status:</strong> compact browser intake only; this is not Recent, Details, trusted report, or optimizer support.</li>"
        "</ul>"
        "</div>"
        "</details>"
    )


def render_trino_compact_error_panel(error: object) -> str:
    safe_error = sanitize_browser_error_text(error, max_chars=None)
    return (
        '<section class="error-card" role="alert">'
        "<strong>Safe Trino compact state</strong>"
        f"{html.escape(safe_error)}<br>"
        "Submitted boundary JSON is not displayed back, and rejected input is hidden."
        "</section>"
    )


def render_trino_compact_result(result: Mapping[str, Any]) -> str:
    return (
        '<section class="panel optimizer-result trino-compact-result" '
        'aria-label="Trino compact diagnosis result">'
        '<div class="section-heading"><div>'
        '<h2 class="section-title">Diagnosis result</h2>'
        '<div class="section-kicker">Deterministic compact-fact checks only. Root cause is not claimed.</div>'
        "</div></div>"
        f"{render_trino_compact_status(result)}"
        f"{render_trino_diagnostic_lane(result.get('diagnostic_lane'))}"
        f"{render_trino_attention_areas(result.get('attention_areas'))}"
        f"{render_trino_limitations(result.get('limitations'))}"
        f"{render_trino_boundary(result.get('diagnosis_boundary'))}"
        "</section>"
    )


def render_trino_compact_status(result: Mapping[str, Any]) -> str:
    support_status = safe_status_label(result.get("support_status"))
    parser_coverage = safe_status_label(result.get("parser_coverage"))
    lifecycle = safe_status_label(result.get("lifecycle"))
    return (
        '<div class="optimizer-block">'
        "<h3>Accepted boundary status</h3>"
        '<ul class="optimizer-table-list trino-compact-status-list">'
        '<li><strong>Engine</strong> <span class="badge blue">Trino</span></li>'
        f'<li><strong>Mode</strong> <span class="badge amber">{html.escape(support_status)}</span></li>'
        f'<li><strong>Coverage</strong> <span class="badge {badge_for_state(parser_coverage)}">{html.escape(parser_coverage)}</span></li>'
        f'<li><strong>Lifecycle</strong> <span class="badge gray">{html.escape(lifecycle)}</span></li>'
        "</ul>"
        "</div>"
    )


def render_trino_diagnostic_lane(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    readiness = safe_status_label(value.get("evidence_readiness"))
    granularity = safe_status_label(value.get("source_granularity"))
    verification_scope = safe_status_label(value.get("verification_scope"))
    supported_count = value.get("supported_attention_area_count")
    if isinstance(supported_count, bool) or not isinstance(supported_count, int):
        supported_count = 0
    return (
        '<div class="optimizer-block trino-diagnostic-lane">'
        "<h3>Diagnostic lane</h3>"
        '<ul class="optimizer-table-list trino-compact-status-list">'
        f'<li><strong>Readiness</strong> <span class="badge {badge_for_lane_readiness(readiness)}">{html.escape(readiness)}</span></li>'
        f'<li><strong>Granularity</strong> <span class="badge gray">{html.escape(granularity)}</span></li>'
        f'<li><strong>Verification scope</strong> <span class="badge blue">{html.escape(verification_scope)}</span></li>'
        f"<li><strong>Supported attention areas</strong> {supported_count}</li>"
        "</ul>"
        "</div>"
    )


def render_trino_attention_areas(value: object) -> str:
    areas = tuple(mapping_items(value))
    cards = "".join(render_trino_attention_card(area) for area in areas)
    if not cards:
        cards = (
            '<article class="reason-card optimizer-finding">'
            "<strong>No attention areas</strong>"
            "<p>The accepted boundary did not produce supported attention signals.</p>"
            '<span class="badge gray">not_observed</span>'
            "</article>"
        )
    return (
        '<div class="optimizer-block">'
        "<h3>Attention areas</h3>"
        f'<div class="optimizer-findings trino-attention-areas">{cards}</div>'
        "</div>"
    )


def render_trino_attention_card(area: Mapping[str, Any]) -> str:
    state = safe_status_label(area.get("state"))
    observed = render_observed_value(area.get("observed_value"))
    observed_values = render_observed_values(area.get("observed_values"))
    return (
        '<article class="reason-card optimizer-finding trino-attention-card">'
        f"<strong>{html.escape(label_from_id(area.get('id'), fallback='Trino attention area'))}</strong>"
        f"<p>{html.escape(text_value(area.get('summary')))}</p>"
        f"{observed}{observed_values}"
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
    label = metric_value_label(value)
    if not label:
        return ""
    return f"<p><strong>Observed:</strong> {html.escape(label)}</p>"


def render_observed_values(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    rows = []
    for raw_id, metric in value.items():
        label = metric_value_label(metric)
        if not label:
            continue
        rows.append(
            "<li>"
            f"<strong>{html.escape(label_from_id(raw_id, fallback='Observed'))}</strong> "
            f"{html.escape(label)}"
            "</li>"
        )
    if not rows:
        return ""
    return '<ul class="optimizer-scope-list trino-observed-values">' + "".join(rows) + "</ul>"


def metric_value_label(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    raw_number = value.get("value")
    if isinstance(raw_number, bool):
        label = "true" if raw_number else "false"
    elif isinstance(raw_number, float):
        label = f"{raw_number:g}"
    elif isinstance(raw_number, int):
        label = str(raw_number)
    else:
        return ""
    unit = text_value(value.get("unit"))
    if unit:
        label = f"{label} {unit}"
    return label


def render_trino_limitations(value: object) -> str:
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
        '<details class="compact-details optimizer-reading-guide trino-limitations" open>'
        "<summary>Limitations</summary>"
        '<div class="compact-details-body">'
        f'<ul class="optimizer-scope-list">{rows}</ul>'
        "</div>"
        "</details>"
    )


def render_trino_boundary(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    root_cause = safe_status_label(value.get("root_cause"))
    report_surface = safe_status_label(value.get("details_trusted_report_surface"))
    optimizer_behavior = safe_status_label(value.get("optimizer_behavior"))
    trino_execution = safe_status_label(value.get("trino_sql_execution"))
    live_recent = safe_status_label(value.get("live_recent_scan"))
    return (
        '<details class="compact-details optimizer-reading-guide trino-boundary">'
        "<summary>Diagnosis boundary</summary>"
        '<div class="compact-details-body">'
        "<p>"
        f'Root cause: <span class="badge gray">{html.escape(root_cause)}</span> '
        f'Details/trusted report wiring: <span class="badge gray">{html.escape(report_surface)}</span> '
        f'Optimizer behavior: <span class="badge gray">{html.escape(optimizer_behavior)}</span> '
        f'Trino SQL execution: <span class="badge gray">{html.escape(trino_execution)}</span> '
        f'Live Recent scan: <span class="badge gray">{html.escape(live_recent)}</span>'
        "</p>"
        "</div>"
        "</details>"
    )


def mapping_items(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def text_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def safe_status_label(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    safe = "".join(char for char in value.lower().strip() if char.isalnum() or char in "_-")
    return safe or "unknown"


def badge_for_state(value: str) -> str:
    if value == "supported":
        return "green"
    if value == "not_observed":
        return "gray"
    if value in {"unknown", "not_wired", "not_performed"}:
        return "amber"
    return "blue"


def badge_for_lane_readiness(value: str) -> str:
    if value == "one_query_attention_ready":
        return "green"
    if value in {"aggregate_selection_only", "source_coverage_unknown"}:
        return "amber"
    if value == "one_query_limited_no_supported_attention":
        return "gray"
    return "blue"


def label_from_id(value: object, *, fallback: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return fallback
    words = [word for word in value.replace("-", "_").split("_") if word]
    if not words:
        return fallback
    return " ".join(words).capitalize()
