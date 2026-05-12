"""Running query analysis page for the local Query Doctor web UI."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.ui.recent_scan_form import (
    WEB_RECENT_SCAN_DEFAULTS,
    form_or_config_value,
    read_local_config_values,
    render_batch_number_field,
    render_batch_text_field,
    render_cluster_select,
    render_running_scan_framing_note,
)
from query_doctor.web.cluster_selection import default_cluster_key, settings_for_cluster_key
from query_doctor.web.models import WebError
from query_doctor.web.ui.pages import render_page
from query_doctor.web.ui.progress import render_job_panel
from query_doctor.web.ui.recent_scan_results import render_batch_card


def render_running_queries_page(
    settings: Any,
    *,
    job: Any | None = None,
    error: object | None = None,
    form_values: dict[str, Any] | None = None,
    query_group: str = "bad",
    only_with_spills: bool = False,
) -> str:
    effective_form_values = form_values
    if effective_form_values is None and job is not None:
        effective_form_values = getattr(job, "batch_form_values", None)
    sections = [
        render_running_queries_run_panel(
            settings,
            effective_form_values,
            run_disabled=job is not None and job.status == "running",
        )
    ]
    if job is not None:
        result_html = None
        if job.status == "ok" and getattr(job, "kind", "") == "running":
            result_html = render_batch_card(
                settings,
                query_group=query_group,
                only_with_spills=only_with_spills,
                title="Running Queries",
                details_base_path="/running/case",
            )
        sections.append(render_job_panel(job, result_html_override=result_html))
    if job is None or job.status != "ok":
        batch_card = render_batch_card(
            settings,
            query_group=query_group,
            only_with_spills=only_with_spills,
            title="Running Queries",
            details_base_path="/running/case",
        )
        if batch_card:
            sections.append(batch_card)
    return render_page(
        settings,
        active_nav="running",
        show_run_panel=False,
        error=error,
        extra_sections=sections,
    )


def render_running_queries_run_panel(
    settings: Any,
    form_values: dict[str, Any] | None = None,
    *,
    run_disabled: bool = False,
) -> str:
    local_config = read_local_config_values(settings)
    if "recent_parallelism" not in local_config and "recent_cm_jobs" in local_config:
        local_config["recent_parallelism"] = local_config["recent_cm_jobs"]
    values = {
        "cluster_key": form_or_config_value(
            form_values,
            "cluster_key",
            config_values=local_config,
            fallback=default_cluster_key(settings),
        ),
        "min_duration_sec": form_or_config_value(
            form_values,
            "min_duration_sec",
            config_values=local_config,
            config_key="recent_min_duration_sec",
        ),
        "parallelism": form_or_config_value(
            form_values,
            "parallelism",
            config_values=local_config,
            config_key="recent_parallelism",
            fallback=WEB_RECENT_SCAN_DEFAULTS["parallelism"],
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
    }
    if form_values:
        values.update(form_values)
    try:
        selected_settings = settings_for_cluster_key(settings, str(values.get("cluster_key") or ""))
    except WebError:
        selected_settings = settings
    metadata_configured = bool(getattr(selected_settings, "metadata_coordinator", None))

    def value(name: str) -> str:
        return html.escape(str(values.get(name, "")), quote=True)

    metadata_note = "" if metadata_configured else "Metadata collection is not configured for this web session."
    metadata_note_html = f"<div class=\"batch-note\">{html.escape(metadata_note)}</div>" if metadata_note else ""
    button_disabled = " disabled" if run_disabled else ""
    button_label = "Running" if run_disabled else "Run scan"
    return (
        "<section class=\"panel batch-run-panel\" aria-label=\"Run running query scan\">"
        "<div class=\"section-heading\"><div>"
        "<h1 class=\"section-title\">Running Queries</h1>"
        "<div class=\"section-kicker\">Scan currently running Impala queries from the selected source.</div>"
        "</div></div>"
        "<form id=\"running-form\" class=\"batch-form\" method=\"post\" action=\"/running/run\">"
        f"{metadata_note_html}"
        "<div class=\"scope-line\" aria-label=\"Running query collection scope\">"
        "<strong>Scope:</strong> current running query summaries → analyzable profiles → ranked cases → bounded automatic metadata · no auto LLM. "
        "Runtime context is collected automatically when the selected source supports it."
        "</div>"
        f"{render_running_scan_framing_note()}"
        "<div class=\"batch-form-sections\">"
        "<fieldset class=\"batch-form-section\"><legend>Query filters</legend>"
        "<div class=\"batch-form-grid\">"
        f"{render_cluster_select(settings, value('cluster_key'), field_id='running_cluster_key')}"
        f"{render_batch_number_field('min_duration_sec', 'Minimum duration (sec)', value('min_duration_sec'), step='0.001', required=False, help_text='Only include running queries at least this long. Empty means no duration filter.')}"
        f"{render_batch_text_field('user', 'Username', value('user'), help_text='Optional exact query user filter. Empty means all users.')}"
        f"{render_batch_text_field('pool', 'Resource pool', value('pool'), help_text='Optional resource pool filter. Empty means all pools.')}"
        "</div>"
        "</fieldset>"
        "<fieldset class=\"batch-form-section\"><legend>Analysis settings</legend>"
        "<div class=\"batch-form-grid\">"
        f"{render_batch_number_field('parallelism', 'Parallelism', value('parallelism'), help_text='Parallel workers for profile downloads and local analysis. Hard cap: 100.')}"
        f"{render_batch_number_field('metadata_jobs', 'Metadata parallelism', value('metadata_jobs'), help_text='Parallel read-only metadata refresh workers for top queries. Keep this bounded to protect Impala and the metastore. Hard cap: 5.')}"
        "</div>"
        "</fieldset>"
        "</div>"
        "<div class=\"batch-actions\">"
        f"<button class=\"run-button\" type=\"submit\"{button_disabled}>{button_label}</button>"
        "</div>"
        "</form></section>"
    )
