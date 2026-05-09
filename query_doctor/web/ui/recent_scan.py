"""Recent query scan rendering helpers for the local Query Doctor UI."""

from __future__ import annotations

from query_doctor.web.presenters.recent_scan import (
    batch_case_display_report_status,
    batch_report_status,
    case_has_failure,
    numeric_count,
    numeric_value,
)
from query_doctor.web.ui.action_candidates import render_action_candidate_findings_view
from query_doctor.web.ui.html_helpers import (
    SafeHtml,
    badge_html,
    compact_cell,
    display_score,
    escape_value,
    metadata_rows,
    reason_cell,
    report_badge,
    score_badge,
    status_badge,
)
from query_doctor.web.ui.metadata_details import (
    has_metadata_aggregate_facts,
    metadata_fact_limitations,
    metadata_score_reasons,
    metadata_statement_counts_summary,
    render_metadata_fact_table_row,
    render_metadata_fact_table_row_view,
    render_metadata_facts_body,
    render_metadata_facts_section,
    render_metadata_facts_view,
)
from query_doctor.web.ui.recent_scan_details import (
    explain_score_reason,
    render_batch_case_detail,
    render_case_detail_overview_view,
    render_case_status_summary,
    render_case_status_summary_view,
    render_evidence_action_guide_view,
    render_recent_scan_case_detail_view,
    render_score_reason_card,
    render_score_reason_card_view,
    render_score_reason_explanations,
    render_score_reason_explanations_view,
    render_technical_details,
    render_technical_details_view,
)
from query_doctor.web.ui.recent_scan_form import (
    form_or_config_bool,
    form_or_config_value,
    read_local_config_values,
    render_batch_number_field,
    render_batch_run_panel,
    render_batch_text_field,
)
from query_doctor.web.ui.recent_scan_results import (
    batch_progress_percent,
    batch_case_details_link,
    batch_case_id,
    case_detail,
    discovery_detail,
    metadata_detail,
    progress_step,
    read_batch_progress_events,
    render_batch_card,
    render_batch_case_row,
    render_batch_empty_note,
    render_batch_progress_panel,
    render_batch_scope_note,
    render_batch_summary,
    summarize_batch_progress,
)
from query_doctor.web.ui.report_actions import render_batch_case_report_action
from query_doctor.web.ui.runtime_metrics import render_runtime_signals
