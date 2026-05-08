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
    render_cm_metrics_profile_select,
    render_running_scan_framing_note,
)
from query_doctor.cm.metrics_catalog import DEFAULT_CM_METRICS_PROFILE
from query_doctor.web.models import WEB_CM_EVENTS_MAX_EVENTS_DEFAULT, WEB_CM_TIMESERIES_TOP_LIMIT_DEFAULT
from query_doctor.web.ui.pages import render_page
from query_doctor.web.ui.progress import render_job_panel
from query_doctor.web.ui.recent_scan import render_batch_card


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
    metadata_configured = bool(getattr(settings, "metadata_coordinator", None))
    local_config = read_local_config_values(settings)
    if "recent_parallelism" not in local_config and "recent_cm_jobs" in local_config:
        local_config["recent_parallelism"] = local_config["recent_cm_jobs"]
    values = {
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
        "cm_events_max_events": form_or_config_value(
            form_values,
            "cm_events_max_events",
            config_values=local_config,
            config_key="recent_cm_events_max_events",
            fallback=str(WEB_CM_EVENTS_MAX_EVENTS_DEFAULT),
        ),
        "cm_metrics_profile": form_or_config_value(
            form_values,
            "cm_metrics_profile",
            config_values=local_config,
            fallback=DEFAULT_CM_METRICS_PROFILE,
        ),
        "cm_timeseries_top_limit": form_or_config_value(
            form_values,
            "cm_timeseries_top_limit",
            config_values=local_config,
            config_key="recent_cm_timeseries_top_limit",
            fallback=str(WEB_CM_TIMESERIES_TOP_LIMIT_DEFAULT),
        ),
        "user": form_or_config_value(form_values, "user", config_values=local_config, config_key="recent_user"),
        "pool": form_or_config_value(form_values, "pool", config_values=local_config, config_key="recent_pool"),
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
        "<section class=\"panel batch-run-panel\" aria-label=\"Run running query scan\">"
        "<div class=\"section-heading\"><div>"
        "<h1 class=\"section-title\">Running Queries</h1>"
        "<div class=\"section-kicker\">Scan currently running Impala queries from Cloudera Manager summaries.</div>"
        "</div></div>"
        "<form id=\"running-form\" class=\"batch-form\" method=\"post\" action=\"/running/run\">"
        f"{metadata_note_html}"
        "<div class=\"scope-line\" aria-label=\"Running query collection scope\">"
        "<strong>Scope:</strong> current running CM summaries → analyzable profiles → ranked cases → automatic metadata for top bad/suspicious cases · no auto LLM. "
        "CM events and CM metrics are collected by default as bounded runtime context."
        "</div>"
        f"{render_running_scan_framing_note()}"
        "<div class=\"batch-form-sections\">"
        "<fieldset class=\"batch-form-section\"><legend>Query filters</legend>"
        "<div class=\"batch-form-grid\">"
        f"{render_batch_number_field('min_duration_sec', 'Minimum duration (sec)', value('min_duration_sec'), step='0.001', required=False, help_text='Only include running queries at least this long. Empty means no duration filter.')}"
        f"{render_batch_text_field('user', 'Username', value('user'), help_text='Optional exact Cloudera Manager query user filter. Empty means all users.')}"
        f"{render_batch_text_field('pool', 'Resource pool', value('pool'), help_text='Optional Cloudera Manager pool filter. Empty means all pools.')}"
        "</div>"
        "</fieldset>"
        "<fieldset class=\"batch-form-section\"><legend>Analysis settings</legend>"
        "<div class=\"batch-form-grid\">"
        f"{render_batch_number_field('parallelism', 'Parallelism', value('parallelism'), help_text='Parallel workers for CM profile downloads and local analysis. Hard cap: 100.')}"
        f"{render_batch_number_field('metadata_jobs', 'Metadata parallelism', value('metadata_jobs'), help_text='Parallel read-only metadata refresh workers for top queries. Keep this bounded to protect Impala and the metastore. Hard cap: 5.')}"
        f"{render_batch_number_field('cm_events_max_events', 'CM events max events', value('cm_events_max_events'), help_text='Maximum Cloudera Manager Events records to summarize once for the running scan window. Hard cap: 200.')}"
        f"{render_cm_metrics_profile_select(value('cm_metrics_profile'))}"
        f"{render_batch_number_field('cm_timeseries_top_limit', 'CM metrics top cases', value('cm_timeseries_top_limit'), required=False, help_text='Maximum top ranked analyzed running cases that receive bounded Cloudera Manager time-series summaries. Default: 10. Use 0 to skip metrics refresh.')}"
        "</div>"
        "</fieldset>"
        "</div>"
        "<div class=\"batch-actions\">"
        f"<button class=\"run-button\" type=\"submit\"{button_disabled}>{button_label}</button>"
        "</div>"
        "</form></section>"
    )
