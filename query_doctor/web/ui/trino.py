"""HTML rendering for the safe Trino compact diagnosis page."""

from __future__ import annotations

import html
import re
from collections.abc import Mapping, Sequence
from typing import Any

from query_doctor.safety.browser_display import redact_browser_display_text
from query_doctor.trino.support_mode import trino_support_mode_is_production
from query_doctor.web.trino_case_artifacts import (
    TRINO_WEB_OPTIMIZER_GUIDANCE_STATUS,
    TRINO_WEB_PYTHON_REPORT_STATUS,
    safe_trino_case_details_href,
)
from query_doctor.web.ui.errors import render_error_panel
from query_doctor.web.ui.pages import render_page


TRINO_DYNAMIC_ARTIFACT_NAME_RE = re.compile(r"\b[A-Za-z0-9_.-]+\.(?:json|ndjson|txt|log)\b")


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


def render_trino_query_analysis_result(result: Any) -> str:
    query_id = html.escape(str(getattr(result, "query_id", "")))
    diagnosis = getattr(result, "diagnosis", {}) or {}
    mode_label = trino_result_mode_label(result)
    beta_boundary = mode_label == "Trino Beta"
    case_artifacts = getattr(result, "case_artifacts", None)
    details_available = bool(safe_trino_case_details_href(case_artifacts))
    return (
        '<section class="panel batch-panel trino-beta-query-result" '
        f'aria-label="{html.escape(mode_label)} Query ID diagnosis">'
        f'<div class="batch-head"><div><h1>{html.escape(mode_label)} Query ID diagnosis</h1>'
        "<p>One bounded pruned coordinator QueryInfo read, deterministic compact diagnosis, "
        "raw-free materialized case facts, and no Running scans, query-history crawling, "
        "metadata collection, LLM reports, Query Optimizer jobs, generated SQL, or "
        "SQL execution. Python Report and optimizer guidance are available only from "
        "materialized Details.</p></div></div>"
        f'<div class="status-strip" aria-label="{html.escape(mode_label)} status">'
        '<span class="status-item"><span class="dot"></span>Engine: '
        f'<span class="badge gray">{html.escape(mode_label)}</span></span>'
        '<span class="status-item"><span class="dot gray"></span>Scope: '
        '<span class="badge gray">one Query ID</span></span>'
        "</div>"
        f"{render_trino_beta_blocked_surfaces(mode_label=mode_label, details_available=details_available)}"
        f'<div class="query-line"><span>Query:</span><code>{query_id}</code></div>'
        f"{render_trino_case_details_action(case_artifacts, mode_label=mode_label)}"
        f"{render_trino_query_boundary_note(beta_boundary=beta_boundary)}"
        "</section>"
        f"{render_trino_compact_result(diagnosis)}"
    )


def trino_result_mode_label(result: Any) -> str:
    support_mode = getattr(result, "support_mode", "beta")
    return "Trino" if trino_support_mode_is_production(support_mode) else "Trino Beta"


def render_trino_beta_blocked_surfaces(
    *, mode_label: str = "Trino Beta", details_available: bool = False
) -> str:
    details_html = (
        '<span class="status-item"><span class="dot"></span>Details: '
        '<span class="badge blue">raw-free case view</span></span>'
        if details_available
        else '<span class="status-item"><span class="dot gray"></span>Details: '
        '<span class="badge gray">not available</span></span>'
    )
    return (
        '<div class="status-strip trino-beta-blocked-surfaces" '
        f'aria-label="{html.escape(mode_label, quote=True)} blocked surfaces">'
        f"{details_html}"
        '<span class="status-item"><span class="dot gray"></span>Running: '
        '<span class="badge gray">not available</span></span>'
        '<span class="status-item"><span class="dot gray"></span>Query-history crawl: '
        '<span class="badge gray">not performed</span></span>'
        '<span class="status-item"><span class="dot gray"></span>Metadata: '
        '<span class="badge gray">not collected</span></span>'
        '<span class="status-item"><span class="dot"></span>Python Report: '
        + (
            '<span class="badge blue">via Details</span></span>'
            if details_available
            else '<span class="badge gray">not available</span></span>'
        )
        + '<span class="status-item"><span class="dot gray"></span>LLM reports: '
        '<span class="badge gray">not available</span></span>'
        '<span class="status-item"><span class="dot"></span>Optimizer: '
        + (
            '<span class="badge blue">guidance via Details</span></span>'
            if details_available
            else '<span class="badge gray">guidance not available</span></span>'
        )
        + '<span class="status-item"><span class="dot gray"></span>Optimizer job: '
        '<span class="badge gray">not available</span></span>'
        '<span class="status-item"><span class="dot gray"></span>Generated SQL: '
        '<span class="badge gray">not generated</span></span>'
        '<span class="status-item"><span class="dot gray"></span>SQL execution: '
        '<span class="badge gray">not performed</span></span>'
        "</div>"
    )


def render_trino_beta_query_boundary_note() -> str:
    return render_trino_query_boundary_note(beta_boundary=True)


def render_trino_query_boundary_note(*, beta_boundary: bool) -> str:
    heading = "Beta boundary" if beta_boundary else "Local boundary"
    first_sentence = (
        "This result is the complete Trino Beta product output for the selected Query ID."
        if beta_boundary
        else "This result is the complete local Trino output for the selected Query ID."
    )
    return (
        '<div class="source-locator-block trino-beta-boundary-note">'
        f'<span class="source-locator-heading">{html.escape(heading)}</span>'
        "<p>"
        f"{html.escape(first_sentence)} "
        "It does not create Running scans, a query-history crawl, metadata collection, "
        "LLM reports, Query Optimizer jobs, generated SQL drafts, or SQL execution. "
        "The deterministic Python Report and optimizer guidance are available only after "
        "the raw-free Details case has been materialized."
        "</p>"
        "</div>"
    )


def render_trino_recent_scan_result(result: Any) -> str:
    rows = tuple(getattr(result, "rows", ()) or ())
    warnings = tuple(getattr(result, "warnings", ()) or ())
    cluster_key = text_value(getattr(result, "cluster_key", ""))
    mode_label = trino_result_mode_label(result)
    beta_boundary = mode_label == "Trino Beta"
    details_available = any(
        bool(safe_trino_case_details_href(getattr(row, "case_artifacts", None))) for row in rows
    )
    limitations_summary = "Beta limitations" if beta_boundary else "Limitations"
    warning_html = "".join(
        f"<li>{html.escape(text_value(warning))}</li>"
        for warning in warnings
        if text_value(warning)
    )
    if warning_html:
        warning_html = (
            '<details class="compact-details optimizer-reading-guide trino-limitations" open>'
            f"<summary>{html.escape(limitations_summary)}</summary>"
            '<div class="compact-details-body">'
            f'<ul class="optimizer-scope-list">{warning_html}</ul>'
            "</div></details>"
        )
    row_html = "".join(
        render_trino_recent_scan_row(row, cluster_key=cluster_key, mode_label=mode_label)
        for row in rows
    )
    if not row_html:
        row_html = (
            '<tr><td colspan="6">'
            "No retained Trino Query IDs matched the selected bounded window and filters."
            "</td></tr>"
        )
    records_seen = safe_int(getattr(result, "records_seen", 0))
    records_selected = safe_int(getattr(result, "records_selected", 0))
    records_diagnosed = safe_int(getattr(result, "records_diagnosed", 0))
    query_bound = safe_int(getattr(result, "query_bound", 0))
    return (
        '<section class="panel batch-panel trino-beta-recent-result" '
        f'aria-label="{html.escape(mode_label)} Recent diagnosis">'
        f'<div class="batch-head"><div><h1>{html.escape(mode_label)} Recent diagnosis</h1>'
        "<p>Bounded retained coordinator query list, selected Query IDs, and one pruned "
        "QueryInfo compact diagnosis per selected query. Running scans, query-history crawling, "
        "metadata collection, LLM reports, Query Optimizer jobs, generated SQL, and "
        "SQL execution remain unavailable. Python Report and optimizer guidance are available "
        "only from materialized Details rows.</p></div></div>"
        f'<div class="status-strip" aria-label="{html.escape(mode_label)} Recent status">'
        '<span class="status-item"><span class="dot"></span>Engine: '
        f'<span class="badge gray">{html.escape(mode_label)}</span></span>'
        '<span class="status-item"><span class="dot gray"></span>Retained records: '
        f"<strong>{records_seen}</strong></span>"
        '<span class="status-item"><span class="dot gray"></span>Selected: '
        f"<strong>{records_selected}</strong></span>"
        '<span class="status-item"><span class="dot gray"></span>Diagnosed: '
        f"<strong>{records_diagnosed}</strong></span>"
        '<span class="status-item"><span class="dot gray"></span>Contract bound: '
        f"<strong>{query_bound}</strong></span>"
        "</div>"
        f"{render_trino_beta_blocked_surfaces(mode_label=mode_label, details_available=details_available)}"
        f"{warning_html}"
        '<div class="batch-table-wrap">'
        '<table class="batch-table trino-recent-table">'
        "<thead><tr>"
        "<th>Query ID</th><th>Status</th><th>Lifecycle</th><th>Coverage</th>"
        "<th>Attention</th><th>Safe note</th>"
        "</tr></thead>"
        f"<tbody>{row_html}</tbody>"
        "</table>"
        "</div>"
        f"{render_trino_recent_boundary_note(beta_boundary=beta_boundary)}"
        "</section>"
    )


def render_trino_recent_scan_row(
    row: Any, *, cluster_key: str = "", mode_label: str = "Trino Beta"
) -> str:
    query_id_value = str(getattr(row, "query_id", ""))
    status = safe_status_label(getattr(row, "status", "unknown"))
    lifecycle = safe_status_label(getattr(row, "lifecycle", "unknown"))
    coverage = safe_status_label(getattr(row, "parser_coverage", "unknown"))
    attention_count = safe_int(getattr(row, "supported_attention_area_count", 0))
    raw_areas = getattr(row, "attention_areas", ()) or ()
    areas = [
        label_from_id(area, fallback="Attention")
        for area in raw_areas
        if isinstance(area, str) and area
    ][:3]
    attention = ", ".join(areas) if areas else "No supported attention areas"
    error = text_value(getattr(row, "error", ""))
    note_html = (
        render_trino_recent_row_error(row, error)
        if error
        else html.escape(f"{attention_count} supported area(s)")
        + render_trino_case_details_action(
            getattr(row, "case_artifacts", None), mode_label=mode_label
        )
    )
    return (
        "<tr>"
        f"<td>{render_trino_recent_query_id_action(query_id_value, cluster_key, mode_label)}</td>"
        f'<td><span class="badge {badge_for_state(status)}">{html.escape(status)}</span></td>'
        f'<td><span class="badge gray">{html.escape(lifecycle)}</span></td>'
        f'<td><span class="badge {badge_for_state(coverage)}">{html.escape(coverage)}</span></td>'
        f"<td>{html.escape(attention)}</td>"
        f"<td>{note_html}</td>"
        "</tr>"
    )


def render_trino_case_details_action(
    case_artifacts: object,
    *,
    mode_label: str = "Trino Beta",
) -> str:
    href = safe_trino_case_details_href(case_artifacts)
    if not href:
        return ""
    label = html.escape(f"Open {mode_label} Details", quote=True)
    return (
        '<div class="trino-details-action">'
        f'<a class="secondary-action trino-details-link" href="{html.escape(href, quote=True)}" '
        f'aria-label="{label}">Open Details</a>'
        "</div>"
    )


def render_trino_recent_row_error(row: Any, error: str) -> str:
    reason = text_value(getattr(row, "error_reason_code", ""))
    next_step = text_value(getattr(row, "error_next_step", ""))
    reason_html = f'<span class="badge amber">{html.escape(reason)}</span>' if reason else ""
    next_step_html = f"<small>{html.escape(next_step)}</small>" if next_step else ""
    return (
        '<div class="trino-row-error">'
        f"<strong>{html.escape(error)}</strong>"
        f"{reason_html}"
        f"{next_step_html}"
        "</div>"
    )


def render_trino_recent_query_id_action(
    query_id: str, cluster_key: str, mode_label: str = "Trino Beta"
) -> str:
    escaped_query_id = html.escape(query_id, quote=True)
    escaped_cluster_key = html.escape(cluster_key, quote=True)
    visible_query_id = html.escape(query_id)
    action_label = html.escape(f"Open {mode_label} Query ID diagnosis", quote=True)
    return (
        '<form class="trino-recent-query-action" method="post" action="/analyze">'
        '<input type="hidden" name="engine" value="trino">'
        '<input type="hidden" name="diagnosis_target" value="query">'
        f'<input type="hidden" name="cluster_key" value="{escaped_cluster_key}">'
        f'<input type="hidden" name="query_id" value="{escaped_query_id}">'
        '<button class="trino-recent-query-button" type="submit" '
        f'aria-label="{action_label}">'
        f"<code>{visible_query_id}</code>"
        "</button>"
        "</form>"
    )


def render_trino_recent_boundary_note(*, beta_boundary: bool = True) -> str:
    heading = "Beta boundary" if beta_boundary else "Local boundary"
    first_sentence = (
        "Trino Recent Beta uses only the bounded retained coordinator list to choose Query IDs,"
        if beta_boundary
        else "Trino Recent uses only the bounded retained coordinator list to choose Query IDs,"
    )
    return (
        '<div class="source-locator-block trino-beta-boundary-note">'
        f'<span class="source-locator-heading">{html.escape(heading)}</span>'
        "<p>"
        f"{html.escape(first_sentence)} "
        "then renders compact raw-free diagnosis for each selected Query ID. It does not create "
        "LLM reports, Query Optimizer jobs, generated SQL drafts, metadata collection, "
        "query-history crawling, Running scans, or SQL execution. Deterministic Python Report "
        "and optimizer guidance require a materialized Details case."
        "</p>"
        "</div>"
    )


def render_trino_details_page(settings: Any, view: Any) -> str:
    return render_page(
        settings,
        active_nav="batch",
        show_run_panel=False,
        extra_sections=[
            render_trino_details_overview(view),
            render_trino_compact_result(getattr(view, "diagnosis", {}) or {}),
        ],
    )


def render_trino_details_error_page(settings: Any, error: object) -> str:
    return render_page(
        settings,
        active_nav="batch",
        show_run_panel=False,
        extra_sections=[
            render_error_panel(
                error,
                default_title="Trino Details unavailable",
                footer="Raw Trino payloads, local paths, and artifact names remain hidden.",
            )
        ],
    )


def render_trino_details_overview(view: Any) -> str:
    analysis = getattr(view, "analysis", {}) or {}
    metadata_summary = getattr(view, "metadata_summary", {}) or {}
    status = analysis.get("status") if isinstance(analysis, Mapping) else {}
    boundary = analysis.get("diagnosis_boundary") if isinstance(analysis, Mapping) else {}
    status = status if isinstance(status, Mapping) else {}
    boundary = boundary if isinstance(boundary, Mapping) else {}
    workflow = safe_status_label(analysis.get("workflow") if isinstance(analysis, Mapping) else "")
    lifecycle = safe_status_label(status.get("lifecycle"))
    coverage = safe_status_label(status.get("parser_coverage"))
    readiness = safe_status_label(status.get("evidence_readiness"))
    verification = safe_status_label(status.get("verification_scope"))
    attention_count = safe_int(status.get("supported_attention_area_count"))
    metadata_collection = safe_status_label(
        metadata_summary.get("collection") if isinstance(metadata_summary, Mapping) else ""
    )
    raw_policy = analysis.get("raw_source_policy") if isinstance(analysis, Mapping) else {}
    raw_policy = raw_policy if isinstance(raw_policy, Mapping) else {}
    python_report = safe_status_label(raw_policy.get("python_report"))
    optimizer_guidance = safe_status_label(raw_policy.get("optimizer_guidance"))
    optimizer_behavior = safe_status_label(
        raw_policy.get("optimizer_behavior") or boundary.get("optimizer_behavior")
    )
    llm_reports = safe_status_label(raw_policy.get("llm_reports"))
    return (
        '<section class="panel batch-panel trino-details-result" '
        'aria-label="Trino Details">'
        '<div class="batch-head"><div><h1>Trino Details</h1>'
        "<p>Raw-free local case view built from materialized Trino facts. Deterministic "
        "Python Report and optimizer guidance are available for this case; LLM reports, "
        "Query Optimizer jobs, metadata collection, generated SQL, and SQL execution remain "
        "unavailable.</p></div></div>"
        '<div class="status-strip trino-details-status" aria-label="Trino Details status">'
        '<span class="status-item"><span class="dot"></span>Engine: '
        '<span class="badge blue">Trino</span></span>'
        '<span class="status-item"><span class="dot gray"></span>Workflow: '
        f'<span class="badge gray">{html.escape(label_from_id(workflow, fallback="Unknown"))}</span></span>'
        '<span class="status-item"><span class="dot gray"></span>Lifecycle: '
        f'<span class="badge {badge_for_state(lifecycle)}">{html.escape(lifecycle)}</span></span>'
        '<span class="status-item"><span class="dot gray"></span>Coverage: '
        f'<span class="badge {badge_for_state(coverage)}">{html.escape(coverage)}</span></span>'
        "</div>"
        '<div class="optimizer-block trino-details-summary">'
        "<h2>Decision facts</h2>"
        '<ul class="optimizer-table-list trino-compact-status-list">'
        f'<li><strong>Evidence readiness</strong> <span class="badge {badge_for_lane_readiness(readiness)}">{html.escape(readiness)}</span></li>'
        f'<li><strong>Verification scope</strong> <span class="badge blue">{html.escape(label_from_id(verification, fallback="Unknown"))}</span></li>'
        f"<li><strong>Supported attention areas</strong> {attention_count}</li>"
        f'<li><strong>Metadata collection</strong> <span class="badge gray">{html.escape(metadata_collection)}</span></li>'
        f'<li><strong>Root cause</strong> <span class="badge gray">{html.escape(safe_status_label(boundary.get("root_cause")))}</span></li>'
        f'<li><strong>Python Report</strong> <span class="badge {badge_for_state(python_report)}">{html.escape(python_report)}</span></li>'
        f'<li><strong>Optimizer guidance</strong> <span class="badge {badge_for_state(optimizer_guidance)}">{html.escape(optimizer_guidance)}</span></li>'
        f'<li><strong>LLM reports</strong> <span class="badge gray">{html.escape(llm_reports)}</span></li>'
        f'<li><strong>Optimizer behavior</strong> <span class="badge blue">{html.escape(optimizer_behavior)}</span></li>'
        f'<li><strong>SQL execution</strong> <span class="badge gray">{html.escape(safe_status_label(boundary.get("trino_sql_execution")))}</span></li>'
        "</ul>"
        "</div>"
        f"{render_trino_python_report_action(raw_policy)}"
        f"{render_trino_optimizer_guidance_action(raw_policy)}"
        f"{render_trino_attention_areas(analysis.get('attention_areas') if isinstance(analysis, Mapping) else None)}"
        f"{render_trino_limitations(analysis.get('limitations') if isinstance(analysis, Mapping) else None)}"
        "</section>"
    )


def render_trino_python_report_action(raw_policy: Mapping[str, Any]) -> str:
    if safe_status_label(raw_policy.get("python_report")) != TRINO_WEB_PYTHON_REPORT_STATUS:
        return ""
    return (
        '<div class="case-actions trino-python-report-actions">'
        '<a class="secondary-action trino-python-report-link" href="?report=python">'
        "Open Python Report</a>"
        '<a class="secondary-action trino-python-report-download" '
        'href="?report=python&amp;download=1" download="query-doctor-trino-python-report.md">'
        "Download Markdown</a>"
        "</div>"
    )


def render_trino_optimizer_guidance_action(raw_policy: Mapping[str, Any]) -> str:
    if (
        safe_status_label(raw_policy.get("optimizer_guidance"))
        != TRINO_WEB_OPTIMIZER_GUIDANCE_STATUS
    ):
        return ""
    return (
        '<div class="case-actions trino-optimizer-guidance-actions">'
        '<a class="secondary-action trino-optimizer-guidance-link" href="?guidance=optimizer">'
        "Open optimizer guidance</a>"
        '<a class="secondary-action trino-optimizer-guidance-download" '
        'href="?guidance=optimizer&amp;download=1" '
        'download="query-doctor-trino-optimizer-guidance.md">'
        "Download guidance</a>"
        "</div>"
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
        "<li><strong>Status:</strong> compact browser intake only; this is not Recent, materialized Details, Python Report, or optimizer support.</li>"
        "</ul>"
        "</div>"
        "</details>"
    )


def render_trino_compact_error_panel(error: object) -> str:
    return render_error_panel(
        error,
        default_title="Safe Trino compact state",
        footer="Submitted boundary JSON is not displayed back, and rejected input is hidden.",
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
        f'Details/report wiring: <span class="badge gray">{html.escape(report_surface)}</span> '
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
    if not isinstance(value, str):
        return ""
    redacted = redact_browser_display_text(
        value,
        redact_artifact_markers=True,
        redact_infrastructure=True,
        redact_sql_snippets=True,
    )
    return TRINO_DYNAMIC_ARTIFACT_NAME_RE.sub("[artifact name hidden]", redacted)


def safe_status_label(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    safe = "".join(char for char in value.lower().strip() if char.isalnum() or char in "_-")
    return safe or "unknown"


def safe_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value if value >= 0 else 0


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
