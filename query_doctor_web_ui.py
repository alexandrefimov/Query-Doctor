"""Pure HTML rendering helpers for the local Query Doctor UI."""

from __future__ import annotations

import html
import json
import re
from typing import Any

from query_doctor_web_ui_recent_scan import (
    SafeHtml,
    batch_case_details_link,
    batch_case_display_report_status,
    batch_case_id,
    batch_report_status,
    badge_html,
    case_detail,
    case_has_failure,
    compact_cell,
    discovery_detail,
    display_score,
    escape_value,
    explain_score_reason,
    form_or_config_bool,
    form_or_config_value,
    has_metadata_aggregate_facts,
    metadata_detail,
    metadata_fact_limitations,
    metadata_rows,
    metadata_score_reasons,
    metadata_statement_counts_summary,
    numeric_count,
    numeric_value,
    progress_step,
    read_batch_progress_events,
    read_local_config_values,
    reason_cell,
    batch_progress_percent,
    render_batch_card,
    render_batch_case_detail,
    render_batch_case_report_action,
    render_batch_case_row,
    render_batch_empty_note,
    render_batch_number_field,
    render_batch_progress_panel,
    render_batch_run_panel,
    render_batch_scope_note,
    render_batch_summary,
    render_batch_text_field,
    render_case_status_summary,
    render_metadata_fact_table_row,
    render_metadata_facts_body,
    render_metadata_facts_section,
    render_runtime_signals,
    render_score_reason_card,
    render_score_reason_explanations,
    render_technical_details,
    report_badge,
    score_badge,
    status_badge,
    summarize_batch_progress,
)


WEB_STAGES = (
    (0, "Checking Query ID", 4),
    (1, "Collecting or reusing profile", 24),
    (2, "Analyzing profile", 62),
    (3, "Preparing deterministic result", 86),
    (4, "Done", 100),
)


def render_page(
    settings: Any,
    *,
    query_id: str = "",
    report_mode: str = "user",
    result: Any | None = None,
    job: Any | None = None,
    error: object | None = None,
    active_nav: str = "query",
    extra_sections: list[str] | None = None,
    show_run_panel: bool = True,
) -> str:
    body = [
        "<!doctype html>",
        "<html lang=\"en\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>impala-query-doctor</title>",
        "<style>",
        render_shared_styles(),
        "</style>",
        render_client_script(),
        "</head>",
        "<body>",
        "<main class=\"page\" id=\"top\">",
        render_app_header(active_nav),
    ]
    if show_run_panel:
        body.append(render_run_panel(query_id=query_id, report_mode=report_mode))
    if error is not None:
        body.append(render_error_panel(error))
    if job is not None:
        body.append(render_job_panel(job))
    if result is not None:
        body.extend(render_query_output(result))
    if extra_sections:
        body.extend(extra_sections)
    body.extend(["</main>", "</body>", "</html>"])
    return "\n".join(body)


def render_shared_styles() -> str:
    return """
:root{color-scheme:light;--bg:#f7f8fa;--panel:#fff;--panel-muted:#f8fafc;--border:#dce3eb;--border-strong:#c8d2df;--text:#17202a;--muted:#627184;--muted-2:#7b8794;--accent:#176b87;--accent-strong:#0f5268;--accent-soft:#e7f4f7;--green:#166534;--green-bg:#eaf7ef;--amber:#92400e;--amber-bg:#fff3d8;--red:#991b1b;--red-bg:#fdecec;--gray:#4b5563;--gray-bg:#eef1f5;--shadow:0 1px 2px rgba(15,23,42,.04),0 3px 8px rgba(15,23,42,.03);--radius:7px;--mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace;--sans:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);font-family:var(--sans);line-height:1.45}a{color:inherit;text-decoration:none}fieldset{border:0;margin:0;padding:0}.page{max-width:1180px;margin:0 auto;padding:22px 28px 48px}.app-header{display:flex;align-items:center;justify-content:space-between;gap:22px;margin-bottom:22px}.brand{display:inline-flex;align-items:center;gap:10px;min-width:0}.brand:focus{outline:2px solid rgba(23,107,135,.28);outline-offset:4px;border-radius:8px}.brand-mark{width:36px;height:36px;display:grid;place-items:center;border:1px solid var(--border-strong);border-radius:6px;background:#fff;box-shadow:0 1px 1px rgba(15,23,42,.035);color:var(--accent-strong);flex:0 0 auto}.brand-mark svg{width:23px;height:23px}.brand-title{display:block;font-weight:720;letter-spacing:-.03em;font-size:17px;line-height:1.1}.brand-subtitle{display:block;margin-top:3px;color:var(--muted);font-size:13px}.top-nav{display:flex;align-items:center;gap:5px;padding:4px;border:1px solid var(--border);border-radius:7px;background:#fff}.nav-link{padding:7px 12px;border-radius:6px;color:var(--muted);font-size:13px;font-weight:600}.nav-link:hover,.nav-link:focus{color:var(--accent-strong);outline:none}.nav-link--active{color:var(--text);background:var(--panel-muted);box-shadow:inset 0 0 0 1px rgba(200,210,223,.7)}
.panel{border:1px solid var(--border);border-radius:var(--radius);background:var(--panel);box-shadow:var(--shadow)}.badge{display:inline-flex;align-items:center;justify-content:center;min-height:22px;padding:2px 7px;border-radius:5px;border:1px solid transparent;font-family:var(--mono);font-size:10.5px;font-weight:750;line-height:1;white-space:nowrap}.badge.green{color:var(--green);background:var(--green-bg);border-color:rgba(22,101,52,.16)}.badge.amber{color:var(--amber);background:var(--amber-bg);border-color:rgba(146,64,14,.16)}.badge.red{color:var(--red);background:var(--red-bg);border-color:rgba(153,27,27,.14)}.badge.gray{color:var(--gray);background:var(--gray-bg);border-color:rgba(75,85,99,.14)}.badge.blue{color:var(--accent-strong);background:var(--accent-soft);border-color:rgba(23,107,135,.16)}code,.technical,.mono{font-family:var(--mono);color:var(--text)}
.button,.run-button{display:inline-flex;align-items:center;justify-content:center;height:32px;padding:0 11px;border:1px solid var(--border-strong);border-radius:6px;background:#fff;color:var(--muted);font-size:12px;font-weight:700;cursor:pointer}.button.primary,.run-button{border-color:var(--accent-strong);background:var(--accent);color:#fff;box-shadow:0 4px 10px rgba(23,107,135,.14)}.run-button{height:40px;min-width:88px;margin-top:26px;padding:0 17px;font-size:13px}.button[disabled],.run-button[disabled]{opacity:.62;cursor:wait}
.run-panel{padding:18px 20px 20px;margin-bottom:14px}.section-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:14px}.section-title{margin:0;font-size:16px;font-weight:720;letter-spacing:-.01em}.section-kicker{margin-top:4px;color:var(--muted);font-size:13px}.readiness-line,.pipeline-line,.scope-line{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);color:var(--muted);font-size:12px}.readiness-line{margin-bottom:13px}.readiness-label,.pipeline-line strong,.scope-line strong{color:#303a46;font-weight:700}.status-token{display:inline-flex;align-items:center;gap:5px;padding:3px 7px;border:1px solid var(--border);border-radius:5px;background:#fff;font-family:var(--mono);color:var(--muted)}
.optimizer-panel,.optimizer-result{padding:18px 20px 20px;margin-bottom:14px}.optimizer-form{display:grid;gap:13px}.optimizer-sql{min-height:220px;height:auto;resize:vertical;padding:12px;line-height:1.45}.optimizer-result h3{margin:0 0 8px;font-size:13px;color:#303a46}.optimizer-block{display:grid;gap:8px;margin-top:14px}.optimizer-block:first-of-type{margin-top:0}.optimizer-table-list{display:flex;flex-wrap:wrap;gap:7px;margin:0;padding:0;list-style:none}.optimizer-table-list li{display:inline-flex;align-items:center;gap:7px;padding:7px 8px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);font-size:12px}.optimizer-empty{color:var(--muted)}.optimizer-findings{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.optimizer-finding{display:grid;gap:5px}.optimizer-finding .badge{justify-self:start}
.run-form{display:grid;gap:13px}.run-main-row{display:grid;grid-template-columns:minmax(280px,1fr) auto;gap:12px;align-items:start}.field{display:grid;gap:7px;min-width:0}.field label,.mode-control>span{color:#303a46;font-size:13px;font-weight:650}.label-row{display:flex;align-items:center;gap:6px;min-width:0}.label-row label{margin:0}.info-popover{position:relative;display:inline-block;vertical-align:middle;line-height:1}.info-popover>summary{display:inline-grid;place-items:center;width:17px;height:17px;padding:0;border:1px solid var(--border);border-radius:999px;background:#fff;color:var(--muted);font-family:var(--mono);font-size:10.5px;font-weight:800;line-height:1;cursor:pointer;list-style:none}.info-popover>summary::-webkit-details-marker{display:none}.info-popover[open]>summary{background:var(--accent-soft);border-color:rgba(23,107,135,.24);color:var(--accent-strong)}.info-popover .info-body{position:absolute;z-index:20;left:0;top:23px;width:max-content;min-width:220px;max-width:min(460px,80vw);padding:8px 9px;border:1px solid var(--border-strong);border-radius:7px;background:#fff;box-shadow:0 8px 22px rgba(15,23,42,.12);color:var(--muted);font-size:11.5px;font-weight:500;line-height:1.35}.info-popover--inline .info-body{left:0;top:23px}.batch-form-grid .field:nth-child(3n) .info-popover .info-body{left:auto;right:0}.compact-details{border:1px solid var(--border);border-radius:7px;background:#fff;overflow:hidden}.compact-details summary{cursor:pointer;padding:9px 11px;background:var(--panel-muted);color:#303a46;font-size:13px;font-weight:720}.compact-details-body{padding:10px 12px;color:var(--muted);font-size:12px}.input{width:100%;height:40px;border:1px solid var(--border-strong);border-radius:6px;background:#fff;color:var(--text);font-family:var(--mono);font-size:13px;padding:0 12px;outline:none}.input:focus{border-color:rgba(23,107,135,.65);box-shadow:0 0 0 3px rgba(23,107,135,.1)}.helper{color:var(--muted);font-size:12px}.run-secondary-row{display:block}.mode-control{display:inline-grid;gap:6px}.segmented{display:inline-grid;grid-template-columns:repeat(2,1fr);gap:2px;height:34px;padding:2px;border:1px solid var(--border-strong);border-radius:6px;background:var(--panel-muted)}.segmented input{position:absolute;opacity:0;pointer-events:none}.segmented label{min-width:58px;display:grid;place-items:center;border-radius:4px;color:var(--muted);cursor:pointer;font-family:var(--mono);font-size:11.5px;font-weight:700}.segmented input:checked+span,.segmented input:checked+label{color:var(--accent-strong);background:#fff;box-shadow:0 1px 2px rgba(15,23,42,.06)}.segmented span{display:grid;place-items:center;min-width:58px;border-radius:4px;padding:0 10px}.mode-help{display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin-top:7px;color:var(--muted);font-size:12px}.mode-help span{display:inline-flex;align-items:center;gap:6px;padding:5px 8px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted)}.manual-inputs-hidden{display:none}.batch-run-panel{padding:18px 20px 20px;margin-bottom:14px}.batch-form{display:grid;gap:13px}.batch-form .input{height:34px;padding:0 10px}.batch-form .run-button{height:34px;width:160px;max-width:100%;justify-self:start;margin-top:0;padding:0 14px;font-size:12.5px}.batch-form-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.batch-form-sections{display:grid;gap:12px}.batch-form-section{display:grid;gap:12px;margin:0;padding:12px;border:1px solid var(--border);border-radius:7px;background:#fff}.batch-form-section legend{padding:0 4px;color:#303a46;font-size:12px;font-weight:760}.batch-actions{display:flex;justify-content:flex-end;padding-top:2px}.batch-primary-row{display:grid;grid-template-columns:minmax(180px,260px) auto;gap:12px;align-items:end}.batch-advanced{border:1px solid var(--border);border-radius:7px;background:#fff;overflow:hidden}.batch-advanced>summary{cursor:pointer;padding:10px 12px;background:var(--panel-muted);color:#303a46;font-size:13px;font-weight:720}.batch-advanced-body{display:grid;gap:12px;padding:12px}.batch-checkbox-row{display:flex;flex-wrap:wrap;align-items:center;gap:10px 16px;color:#303a46;font-size:13px;font-weight:650}.batch-checkbox-row input{margin-right:6px}.trust-strip{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;margin:14px 0;padding:9px 12px;border:1px solid var(--border);border-radius:7px;background:#fff;color:var(--muted);font-size:12px;font-weight:650;box-shadow:0 1px 2px rgba(15,23,42,.035)}.trust-item{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}.trust-icon{width:14px;height:14px;display:inline-grid;place-items:center;border-radius:999px;background:var(--accent-soft);color:var(--accent-strong);font-family:var(--mono);font-size:9px;line-height:1;flex:0 0 auto}.no-reports-note{padding:10px 12px;margin-bottom:14px;color:var(--muted);font-size:12px}.no-reports-note strong{display:block;margin-bottom:2px;color:var(--text);font-size:13px}
.error-card{border:1px solid rgba(153,27,27,.18);background:var(--red-bg);padding:12px 14px;color:var(--red);border-radius:7px;margin-bottom:14px}.error-card strong{display:block;margin-bottom:4px;color:var(--red)}.progress-card{padding:13px 14px;margin-bottom:14px}#job-result-slot:not(:empty){margin-top:16px}.progress-card--hidden{display:none}.progress-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}.progress-title{font-weight:650}.progress-stage{color:var(--muted);font-size:.84rem}.progress-bar{height:6px;border-radius:999px;background:var(--gray-bg);border:1px solid var(--border);overflow:hidden}.progress-fill{display:block;height:100%;width:4%;background:var(--accent);transition:width .2s ease}.progress-note{margin:8px 0 0;color:var(--muted);font-size:.77rem}.batch-progress{margin-top:12px;display:grid;gap:10px}.batch-progress-steps{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:6px}.batch-progress-step{border:1px solid var(--border);border-radius:7px;background:var(--panel-muted);padding:8px;min-width:0}.batch-progress-step strong{display:block;font-size:11px;color:var(--text);overflow-wrap:anywhere;line-height:1.2}.batch-progress-step span{display:block;margin-top:3px;font-size:10.5px;color:var(--muted);overflow-wrap:anywhere;line-height:1.25}.batch-progress-step--done{border-color:rgba(22,101,52,.2);background:var(--green-bg)}.batch-progress-step--running{border-color:rgba(23,107,135,.22);background:var(--accent-soft)}.batch-progress-step--failed{border-color:rgba(153,27,27,.18);background:var(--red-bg)}.batch-progress-metrics{display:flex;flex-wrap:wrap;gap:7px;color:var(--muted);font-size:12px}.batch-progress-metrics span{border:1px solid var(--border);border-radius:999px;background:#fff;padding:4px 8px}.report-progress{display:grid;gap:10px;margin-bottom:12px}.report-progress .batch-progress{margin-top:0}.report-progress .batch-progress-steps{grid-template-columns:repeat(4,minmax(0,1fr))}
.batch-panel{padding:18px 20px;overflow:hidden}.batch-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:14px}.batch-head h1{margin:0 0 4px;font-size:20px;line-height:1.2;letter-spacing:-.02em}.batch-head p{margin:0;color:var(--muted);font-size:13px}.batch-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(108px,1fr));gap:8px;margin-bottom:12px}.batch-metric{display:grid;gap:4px;padding:9px 10px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);min-width:0}.batch-metric span{color:var(--muted);font-size:11px;font-weight:650;text-transform:uppercase}.batch-metric strong{font-family:var(--mono);font-size:13px;overflow-wrap:anywhere}.batch-note{margin-bottom:12px;padding:9px 10px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);color:var(--muted);font-size:12px}.batch-detail-grid{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}.batch-detail-grid span{display:inline-flex;align-items:center;min-height:26px;padding:4px 8px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);color:var(--muted);font-size:11.5px}.batch-result-filters{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:8px;margin:0 0 12px}.batch-filter-tabs{display:flex;flex-wrap:wrap;gap:6px;margin:0}.batch-filter-link,.batch-spill-toggle{display:inline-flex;align-items:center;gap:7px;min-height:32px;padding:0 10px;border:1px solid var(--border-strong);border-radius:6px;background:#fff;color:var(--muted);font-size:12px;font-weight:720}.batch-filter-link span{display:inline-grid;place-items:center;min-width:20px;height:20px;padding:0 6px;border-radius:999px;background:var(--panel-muted);font-family:var(--mono);font-size:10.5px;color:var(--text)}.batch-filter-link--active,.batch-spill-toggle--active{background:var(--accent-soft);border-color:rgba(23,107,135,.32);color:var(--accent-strong)}.batch-spill-check{display:inline-grid;place-items:center;width:14px;height:14px;border:1px solid var(--border-strong);border-radius:3px;background:#fff;color:var(--accent-strong);font-size:11px;line-height:1}.case-overview{display:grid;gap:10px;margin-bottom:14px}.case-query-line{display:grid;gap:4px;padding:10px 11px;border:1px solid var(--border);border-radius:6px;background:#fff;min-width:0}.case-query-line span,.case-overview-card span{color:var(--muted);font-size:11px;font-weight:650;text-transform:uppercase}.case-query-line strong{font-family:var(--mono);font-size:12px;white-space:nowrap;overflow-x:auto;overflow-y:hidden}.case-overview-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.case-overview-card{display:grid;gap:4px;padding:9px 10px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);min-width:0}.case-overview-card strong{font-family:var(--mono);font-size:12px;overflow-wrap:anywhere}.case-summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:14px}.case-summary-card{display:grid;gap:4px;padding:9px 10px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);min-width:0}.case-summary-card span{color:var(--muted);font-size:11px;font-weight:650;text-transform:uppercase}.case-summary-card strong{font-family:var(--mono);font-size:12px;overflow-wrap:anywhere}.reason-list{display:grid;gap:10px;margin:0;padding:0;list-style:none}.reason-card{border:1px solid var(--border);border-radius:7px;background:#fff;padding:10px 11px}.reason-card strong{display:block;margin-bottom:3px;font-size:13px}.reason-card p{margin:0;color:var(--muted);font-size:12px}.technical-details{overflow:hidden}.metadata-statement-line{display:inline-flex;gap:8px;flex-wrap:wrap;font-family:var(--mono);font-size:12px}.batch-table-wrap{margin-top:14px;max-width:100%;overflow-x:auto;overflow-y:visible;border:1px solid var(--border);border-radius:7px}.batch-table{min-width:0;width:100%;table-layout:auto;border-collapse:collapse;font-size:12px;background:#fff}.batch-table th,.batch-table td{border-bottom:1px solid var(--border);padding:8px 9px;text-align:left;vertical-align:top}.batch-table th{position:sticky;top:0;background:var(--panel-muted);color:#303a46;font-size:11px;text-transform:uppercase;letter-spacing:0;font-weight:720}.batch-row{cursor:pointer}.batch-row:hover,.batch-row:focus{background:var(--panel-muted);outline:none}.batch-row--failed{background:rgba(253,236,236,.55)}.batch-row--failed:hover,.batch-row--failed:focus{background:var(--red-bg)}.batch-cell--compact{width:1%;font-family:var(--mono);white-space:nowrap;overflow-wrap:normal}.batch-cell--query-id{width:1%;min-width:250px;font-family:var(--mono);font-size:11px;line-height:1.3;white-space:nowrap;overflow-wrap:normal}.batch-cell--summary{width:100%;min-width:320px;white-space:normal}.batch-cell--summary strong{display:block;margin-bottom:3px;color:var(--text);font-size:12px;overflow-wrap:anywhere}.batch-cell--summary span{display:block;color:var(--muted);font-size:11px;overflow-wrap:anywhere}.batch-cell--reason{min-width:260px;white-space:normal;overflow-wrap:anywhere}.batch-mini-badge{display:inline-flex;align-items:center;min-height:20px;padding:2px 7px;border-radius:5px;border:1px solid transparent;font-family:var(--mono);font-size:10.5px;font-weight:750;line-height:1;white-space:nowrap}.batch-severity--high,.batch-severity--failed,.batch-status--failed,.batch-report--untrusted{color:var(--red);background:var(--red-bg);border-color:rgba(153,27,27,.14)}.batch-severity--suspicious,.batch-status--warning,.batch-report--generated{color:var(--amber);background:var(--amber-bg);border-color:rgba(146,64,14,.16)}.batch-severity--clean,.batch-status--ok,.batch-report--passed{color:var(--green);background:var(--green-bg);border-color:rgba(22,101,52,.16)}.batch-status--neutral,.batch-report--neutral{color:var(--gray);background:var(--gray-bg);border-color:rgba(75,85,99,.14)}.empty-cell{color:var(--muted);text-align:center}
.report-header{margin-bottom:14px;padding:18px 20px}.breadcrumb{display:flex;align-items:center;gap:8px;margin-bottom:12px;color:var(--muted);font-size:12px;font-weight:650}.report-title-row{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.report-title-row h1{margin:0 0 8px;font-size:20px;line-height:1.2;letter-spacing:-.03em}.report-subtitle{color:var(--muted);font-size:13px}.query-line{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px 10px;color:var(--muted);font-size:12px}.status-strip{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;padding:9px 10px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);color:var(--muted);font-size:12px;font-weight:650}.status-item{display:inline-flex;align-items:center;gap:6px}.dot{width:7px;height:7px;border-radius:999px;background:var(--green)}.dot.amber{background:#d97706}.dot.gray{background:#6b7280}.report-shell{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:14px;align-items:start}.content-main{display:grid;gap:14px}.report-card,.docs-panel{padding:0;overflow:hidden}.batch-panel>.docs-panel{margin-top:14px}.analysis-details-body{padding:0}.analysis-subdetails{background:#fff;border-top:1px solid var(--border);overflow:hidden}.analysis-subdetails:first-child{border-top:0}.report-card summary,.docs-panel h1,.docs-panel>summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 18px;margin:0;border-bottom:1px solid var(--border);background:var(--panel-muted);font-size:15px;font-weight:720}.docs-panel>summary,.analysis-subdetails>summary{cursor:pointer;list-style:none}.docs-panel>summary::-webkit-details-marker,.analysis-subdetails>summary::-webkit-details-marker{display:none}.docs-panel>summary::after,.analysis-subdetails>summary::after,.report-card>summary::after,.report-body>details>summary::after{content:"";width:7px;height:7px;border:solid currentColor;border-width:0 2px 2px 0;transform:rotate(45deg);transition:transform .15s ease;flex:0 0 auto}.docs-panel[open]>summary::after,.analysis-subdetails[open]>summary::after,.report-card[open]>summary::after,.report-body>details[open]>summary::after{transform:rotate(225deg)}.analysis-subdetails>summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 18px;background:#fff;font-size:13px;font-weight:720}.analysis-subdetails[open]>summary{border-bottom:1px solid var(--border);background:var(--panel-muted)}.analysis-subdetails>.report-body{padding:14px 18px}.report-body{padding:16px 18px;color:var(--text);font-size:13px}.report-body>details{margin:10px 0;border:1px solid var(--border);border-radius:7px;background:#fff;overflow:hidden}.report-body>details>summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 13px;background:var(--panel-muted);color:#303a46;font-size:13px;font-weight:780;cursor:pointer;list-style:none}.report-body>details>summary::-webkit-details-marker{display:none}.report-body>details[open]>summary{border-bottom:1px solid var(--border)}.report-body>details>*:not(summary){margin-left:13px;margin-right:13px}.inline-report{margin-top:14px;padding-top:14px;border-top:1px solid var(--border)}.report-body h1,.report-body h2,.report-body h3,.report-body h4{margin:1.15em 0 .5em;line-height:1.2}.report-body h1:first-child,.report-body h2:first-child,.report-body h3:first-child{margin-top:0}.report-body h1{font-size:20px}.report-body h2{font-size:17px}.report-body h3{font-size:15px}.report-body p{margin:.7em 0}.report-body ul,.report-body ol{margin:.55em 0 .8em;padding-left:1.35rem}.report-body li{margin:.32em 0;overflow-wrap:anywhere}.report-body code{background:var(--panel-muted);border:1px solid var(--border);border-radius:5px;padding:.08rem .28rem;font-family:var(--mono);font-size:.88em;overflow-wrap:anywhere}.report-body pre{margin:.75em 0;padding:12px;background:#0f1720;color:#e5edf5;border:1px solid var(--border);border-radius:6px;white-space:pre-wrap;overflow-wrap:anywhere}.report-body pre code{border:0;background:transparent;padding:0;color:inherit}.report-body blockquote{margin:.75em 0;padding:.35em .8em;border-left:3px solid var(--accent);background:var(--accent-soft);color:#36505c}.report-body table{width:100%;border-collapse:collapse;margin:.8em 0;font-size:.86rem}.report-body th,.report-body td{border:1px solid var(--border);padding:6px 8px;text-align:left;vertical-align:top}.report-body th{background:var(--panel-muted);color:#303a46}.appendix-notice{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 12px;padding:10px 12px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);color:var(--muted);font-size:12px}.side-panel{position:sticky;top:18px;display:grid;gap:14px}.side-card{padding:14px}.side-card h2{margin:0 0 10px;font-size:14px}.meta-list{display:grid;gap:8px}.meta-row{display:flex;justify-content:space-between;gap:12px;padding-bottom:8px;border-bottom:1px solid var(--border);color:var(--muted);font-size:12px}.meta-row:last-child{padding-bottom:0;border-bottom:0}.meta-row strong{color:var(--text);font-family:var(--mono);font-size:11px;text-align:right}.artifact-list,.toc-list,.timeline{display:grid;gap:7px}.artifact-item,.toc-list a{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px 10px;padding:8px 9px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);color:var(--muted);font-size:12px;font-weight:650}.artifact-item code{display:block;margin-top:2px;font-family:var(--mono);color:var(--text);font-size:11px}.toc-list a{display:block}.timeline-item{display:grid;grid-template-columns:16px 1fr;gap:8px;color:var(--muted);font-size:12px}.timeline-dot{width:8px;height:8px;margin-top:5px;border-radius:999px;background:var(--green)}.timeline-item strong{display:block;color:var(--text);font-size:12px}
@media(max-width:980px){.report-shell{grid-template-columns:1fr}.side-panel{position:static}.batch-metrics,.case-summary-grid,.case-overview-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.batch-form-grid{grid-template-columns:repeat(2,minmax(120px,1fr))}.batch-progress-steps{grid-template-columns:repeat(3,minmax(0,1fr))}.optimizer-findings{grid-template-columns:1fr}}@media(max-width:760px){.page{padding:18px 16px 40px}.app-header{align-items:stretch;flex-direction:column}.top-nav{width:fit-content}.run-main-row,.batch-primary-row{grid-template-columns:1fr}.batch-form .run-button{width:100%}.run-secondary-row{align-items:stretch;flex-direction:column}.mode-control,.run-button{width:100%}.segmented{width:100%}.report-title-row{align-items:stretch;flex-direction:column}.batch-metrics,.batch-form-grid,.case-summary-grid,.case-overview-grid{grid-template-columns:1fr}.batch-progress-steps{grid-template-columns:1fr}}
""".strip()


def render_app_header(active: str) -> str:
    return (
        "<header class=\"app-header\" aria-label=\"Application header\">"
        "<a class=\"brand\" href=\"/\" aria-label=\"Query Doctor home\">"
        "<span class=\"brand-mark\" aria-hidden=\"true\">"
        "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" "
        "stroke-linecap=\"round\" stroke-linejoin=\"round\">"
        "<path d=\"M5 12h3l2-5 4 10 2-5h3\"/>"
        "<path d=\"M12 3v3M12 18v3M3 12h2M19 12h2\"/>"
        "</svg></span>"
        "<span><span class=\"brand-title\">impala-query-doctor</span>"
        "<span class=\"brand-subtitle\">Impala query performance diagnostics</span></span>"
        "</a>"
        f"{render_top_nav(active)}"
        "</header>"
    )


def render_top_nav(active: str) -> str:
    batch_class = "nav-link nav-link--active" if active == "batch" else "nav-link"
    query_class = "nav-link nav-link--active" if active == "query" else "nav-link"
    running_class = "nav-link nav-link--active" if active == "running" else "nav-link"
    help_class = "nav-link nav-link--active" if active == "help" else "nav-link"
    return (
        "<nav class=\"top-nav\" aria-label=\"Main navigation\">"
        f"<a class=\"{batch_class}\" href=\"/\">Finished Queries</a>"
        f"<a class=\"{running_class}\" href=\"/running\">Running Queries</a>"
        f"<a class=\"{query_class}\" href=\"/query\">Specific Query</a>"
        f"<a class=\"{help_class}\" href=\"/help\">Help</a>"
        "</nav>"
    )


def render_run_panel(*, query_id: str, report_mode: str) -> str:
    from query_doctor_web_ui_home import render_run_panel as _render_run_panel

    return _render_run_panel(query_id=query_id, report_mode=report_mode)


def render_trust_strip() -> str:
    from query_doctor_web_ui_home import render_trust_strip as _render_trust_strip

    return _render_trust_strip()


def render_no_reports_note() -> str:
    from query_doctor_web_ui_home import render_no_reports_note as _render_no_reports_note

    return _render_no_reports_note()


def render_error_panel(error: object) -> str:
    return (
        "<section class=\"error-card\" role=\"alert\">"
        "<strong>Safe inspection state</strong>"
        f"{html.escape(str(error))}<br>"
        "Unvalidated or partial report output is hidden."
        "</section>"
    )


def render_readme_page(settings: Any) -> str:
    from query_doctor_web_ui_help import render_help_page

    return render_help_page(settings)


def render_query_page(
    settings: Any,
    *,
    query_id: str = "",
    report_mode: str = "user",
    result: Any | None = None,
    job: Any | None = None,
    error: object | None = None,
) -> str:
    return render_page(
        settings,
        query_id=query_id,
        report_mode=report_mode,
        result=result,
        job=job,
        error=error,
        active_nav="query",
        show_run_panel=True,
    )


def render_batch_page(
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
        render_batch_run_panel(settings, effective_form_values, run_disabled=job is not None and job.status == "running")
    ]
    if job is not None:
        result_html = None
        if job.status == "ok" and getattr(job, "kind", "") == "batch":
            result_html = render_batch_card(settings, query_group=query_group, only_with_spills=only_with_spills)
        sections.append(render_job_panel(job, result_html_override=result_html))
    if job is None or job.status != "ok":
        batch_card = render_batch_card(settings, query_group=query_group, only_with_spills=only_with_spills)
        if batch_card:
            sections.append(batch_card)
    return render_page(
        settings,
        active_nav="batch",
        show_run_panel=False,
        error=error,
        extra_sections=sections,
    )


def render_batch_case_detail_page(
    settings: Any,
    case_id: str,
    case: dict[str, Any],
    metadata_facts: dict[str, Any] | None = None,
    cm_metrics_facts: dict[str, Any] | None = None,
    report_state: dict[str, Any] | None = None,
    optimized_query_state: dict[str, Any] | None = None,
    trusted_report_text: str | None = None,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
    workflow_title: str = "Finished Queries",
    list_href: str = "/#recent-results",
    detail_base_path: str = "/batch/case",
    active_nav: str = "batch",
) -> str:
    trusted_report_html = (
        SafeHtml(render_report_markdown_html(trusted_report_text, with_heading_ids=True))
        if trusted_report_text
        else None
    )
    sections = [
        render_batch_case_detail(
            case_id,
            case,
            metadata_facts,
            cm_metrics_facts,
            report_state=report_state,
            optimized_query_state=optimized_query_state,
            trusted_report_html=trusted_report_html,
            trusted_optimized_query=trusted_optimized_query,
            trusted_optimizer_recommendations=trusted_optimizer_recommendations,
            workflow_title=workflow_title,
            list_href=list_href,
            detail_base_path=detail_base_path,
        )
    ]
    return render_page(settings, active_nav=active_nav, show_run_panel=False, extra_sections=sections)


def render_batch_case_not_found_page(settings: Any, case_id: str) -> str:
    safe_case_id = html.escape(case_id)
    section = (
        "<section class=\"panel batch-panel\" aria-label=\"Finished Queries case not found\">"
        "<div class=\"batch-head\"><div><h1>Finished Queries case not found</h1>"
        f"<p>No batch case summary was found for <code>{safe_case_id}</code>.</p></div>"
        "<span class=\"badge gray\">not found</span></div>"
        "<div class=\"batch-note\">Case details are resolved only from the server-owned "
        "<code>batch_summary.json</code>; request paths cannot choose local files.</div>"
        "</section>"
    )
    return render_page(settings, active_nav="batch", show_run_panel=False, extra_sections=[section])


def render_batch_case_report_page(settings: Any, case_id: str, case: dict[str, Any], report_text: str) -> str:
    query_id = case.get("query_id")
    section = (
        "<section class=\"panel report-header\" aria-label=\"Finished Queries case report header\">"
        "<div class=\"breadcrumb\"><a href=\"/\">Finished Queries</a><span>/</span>"
        f"<a href=\"/batch/case/{html.escape(case_id, quote=True)}\">{html.escape(case_id)}</a>"
        "<span>/</span><span>validated report</span></div>"
        "<div class=\"report-title-row\"><div>"
        "<h1>Validated Finished Queries case report</h1>"
        "<div class=\"report-subtitle\">Rendered only after the report action completed validation.</div>"
        "<div class=\"query-line\">"
        f"<span>Case:</span><code>{html.escape(case_id)}</code>"
        f"<span>Query:</span><code>{escape_value(query_id)}</code>"
        "</div></div></div>"
        "<div class=\"status-strip\" aria-label=\"Report status\">"
        "<span class=\"status-item\"><span class=\"dot\"></span>Validation: <span class=\"badge green\">PASS</span></span>"
        "<span class=\"status-item\"><span class=\"dot gray\"></span>Mode: <span class=\"badge gray\">admin</span></span>"
        "<span class=\"status-item\"><span class=\"dot\"></span>Partial reports remain untrusted and hidden</span>"
        "</div></section>"
        "<details class=\"panel report-card\" open aria-label=\"Validated report body\">"
        "<summary>Validated diagnosis markdown</summary>"
        f"<div class=\"report-body\">{render_report_markdown_html(report_text, with_heading_ids=True)}</div>"
        "</details>"
    )
    return render_page(settings, active_nav="batch", show_run_panel=False, extra_sections=[section])


def render_client_script() -> str:
    return """<script>
document.addEventListener('DOMContentLoaded', function () {
  var form = document.getElementById('analyze-form');
  var pending = document.getElementById('pending-panel');
  if (form) {
    form.addEventListener('submit', function () {
      if (pending) {
        pending.classList.remove('progress-card--hidden');
      }
      var button = form.querySelector('button[type="submit"]');
      if (button) {
        button.disabled = true;
        button.textContent = 'Run';
      }
      var queryInput = form.querySelector('input[name="query_id"]');
      if (queryInput) {
        window.setTimeout(function () { queryInput.value = ''; }, 0);
      }
    });
  }
  var infoPopovers = Array.prototype.slice.call(document.querySelectorAll('.info-popover'));
  function closeInfoPopovers(exceptPopover) {
    infoPopovers.forEach(function (popover) {
      if (popover !== exceptPopover) {
        popover.removeAttribute('open');
      }
    });
  }
  infoPopovers.forEach(function (popover) {
    popover.addEventListener('toggle', function () {
      if (popover.open) {
        closeInfoPopovers(popover);
      }
    });
  });
  document.addEventListener('click', function (event) {
    if (!event.target.closest || !event.target.closest('.info-popover')) {
      closeInfoPopovers(null);
    }
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      closeInfoPopovers(null);
    }
  });
  function detailJobProgressElements() {
    return Array.prototype.slice.call(document.querySelectorAll('[data-report-job-status-url], [data-optimizer-job-status-url]'));
  }
  function detailJobStatusUrl(progressElement) {
    return progressElement.getAttribute('data-report-job-status-url') || progressElement.getAttribute('data-optimizer-job-status-url');
  }
  function detailJobRedirectUrl(progressElement) {
    return progressElement.getAttribute('data-report-job-url') || progressElement.getAttribute('data-optimizer-job-url');
  }
  function pollDetailJobProgress(progressElement) {
    var statusUrl = detailJobStatusUrl(progressElement);
    if (!statusUrl) {
      return;
    }
    fetch(statusUrl, {cache: 'no-store'})
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (data.status === 'ok' || data.status === 'failed') {
          window.location.href = detailJobRedirectUrl(progressElement) || window.location.href;
          return;
        }
        window.setTimeout(function () { pollDetailJobProgress(progressElement); }, 1200);
      })
      .catch(function () { window.setTimeout(function () { pollDetailJobProgress(progressElement); }, 1800); });
  }
  function pollDetailJobProgressElements() {
    detailJobProgressElements().forEach(pollDetailJobProgress);
  }
  var jobPanel = document.querySelector('[data-job-status-url]');
  if (!jobPanel) {
    pollDetailJobProgressElements();
    return;
  }
  var stage = document.getElementById('job-stage');
  var fill = document.getElementById('job-progress-fill');
  var resultSlot = document.getElementById('job-result-slot');
  var errorSlot = document.getElementById('job-error-slot');
  var title = jobPanel.querySelector('.progress-title');
  var batchRunButton = document.querySelector('#batch-form button[type="submit"], #running-form button[type="submit"]');
  function poll() {
    fetch(jobPanel.getAttribute('data-job-status-url'), {cache: 'no-store'})
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (stage) { stage.textContent = data.stage || ''; }
        if (fill) { fill.style.width = String(data.progress || 0) + '%'; }
        var runningProgressSlot = document.getElementById('batch-progress-slot');
        if (runningProgressSlot) { runningProgressSlot.innerHTML = data.progress_html || ''; }
        if (data.status === 'ok') {
          if (title) { title.textContent = 'Analysis complete'; }
          if ((data.kind === 'batch' || data.kind === 'running') && batchRunButton) {
            batchRunButton.disabled = false;
            batchRunButton.textContent = 'Run scan';
          }
          if (resultSlot && !resultSlot.querySelector('#recent-results')) {
            resultSlot.innerHTML = data.result_html || '';
          }
          return;
        }
        if (data.status === 'failed') {
          if (title) { title.textContent = 'Analysis failed'; }
          if ((data.kind === 'batch' || data.kind === 'running') && batchRunButton) {
            batchRunButton.disabled = false;
            batchRunButton.textContent = 'Run scan';
          }
          if (errorSlot) {
            errorSlot.hidden = false;
            errorSlot.textContent = data.error || 'Analysis failed.';
          }
          return;
        }
        window.setTimeout(poll, 1200);
      })
      .catch(function () { window.setTimeout(poll, 1800); });
  }
  poll();
});
</script>"""


def render_pending_progress_panel() -> str:
    stage = WEB_STAGES[0]
    return (
        "<section id=\"pending-panel\" class=\"panel progress-card progress-card--hidden\" aria-live=\"polite\">"
        "<div class=\"progress-head\"><span class=\"progress-title\">Analysis started</span>"
        f"<span class=\"progress-stage\">{html.escape(stage[1])}</span></div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\"><span class=\"progress-fill\"></span></div>"
        "</section>"
    )


def render_job_panel(job: Any, *, result_html_override: str | None = None) -> str:
    result_html = (
        result_html_override
        if result_html_override is not None
        else job.result_html
        if job.status == "ok" or getattr(job, "kind", "") == "query"
        else ""
    )
    error_html = html.escape(job.error) if job.status == "failed" else ""
    error_hidden = "" if job.status == "failed" else " hidden"
    batch_progress_html = ""
    progress = job.progress
    if getattr(job, "kind", "") in {"batch", "running"}:
        progress = batch_progress_percent(getattr(job, "batch_progress_path", None), job.status)
        batch_progress_html = (
            "<div id=\"batch-progress-slot\">"
            f"{render_batch_progress_panel(getattr(job, 'batch_progress_path', None), job.status)}"
            "</div>"
        )
    if job.status == "ok":
        title = "Analysis complete"
    elif job.status == "failed":
        title = "Analysis failed"
    else:
        title = "Analysis running"
    return (
        f"<section class=\"panel progress-card\" data-job-status-url=\"/jobs/{html.escape(job.job_id)}"
        "/status\" aria-live=\"polite\">"
        f"<div class=\"progress-head\"><span class=\"progress-title\">{title}</span>"
        f"<span id=\"job-stage\" class=\"progress-stage\">{html.escape(job.stage_label)}</span></div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\">"
        f"<span id=\"job-progress-fill\" class=\"progress-fill\" style=\"width:{progress}%\"></span>"
        "</div>"
        f"{batch_progress_html}"
        f"<div id=\"job-error-slot\" class=\"error-card\" role=\"alert\"{error_hidden}>{error_html}</div>"
        f"<div id=\"job-result-slot\">{result_html}</div>"
        "</section>"
    )


def render_result(result: Any) -> list[str]:
    from query_doctor_web_ui_report import render_result as _render_result

    return _render_result(result)


def render_specific_query_result(result: Any) -> list[str]:
    from query_doctor_web_ui_specific_query import render_specific_query_result as _render_specific_query_result

    return _render_specific_query_result(result)


def render_specific_query_results(cases: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[str]:
    from query_doctor_web_ui_specific_query import render_specific_query_results as _render_specific_query_results

    return _render_specific_query_results(cases)


def render_specific_query_detail(
    query_id: str,
    case: dict[str, Any],
    metadata_facts: dict[str, Any] | None = None,
    cm_metrics_facts: dict[str, Any] | None = None,
    report_state: dict[str, Any] | None = None,
    optimized_query_state: dict[str, Any] | None = None,
    trusted_report_text: str | None = None,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
) -> str:
    from query_doctor_web_ui_specific_query import render_specific_query_detail as _render_specific_query_detail

    trusted_report_html = (
        SafeHtml(render_report_markdown_html(trusted_report_text, with_heading_ids=True))
        if trusted_report_text
        else None
    )
    return _render_specific_query_detail(
        query_id,
        case,
        metadata_facts,
        cm_metrics_facts,
        report_state=report_state,
        optimized_query_state=optimized_query_state,
        trusted_report_html=trusted_report_html,
        trusted_optimized_query=trusted_optimized_query,
        trusted_optimizer_recommendations=trusted_optimizer_recommendations,
    )


def render_query_output(result: Any) -> list[str]:
    if hasattr(result, "case"):
        return render_specific_query_result(result)
    return render_result(result)


def render_report_markdown_html(markdown_text: str, *, with_heading_ids: bool = False) -> str:
    lines = markdown_text.splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    list_items: list[str] = []
    index = 0
    heading_counter = 0

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{render_inline_markdown(' '.join(part.strip() for part in paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_type
        if list_type is not None:
            tag = "ol" if list_type == "ol" else "ul"
            blocks.append(f"<{tag}>" + "".join(f"<li>{item}</li>" for item in list_items) + f"</{tag}>")
            list_items.clear()
            list_type = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            index += 1
            continue

        if stripped in {"<details>", "</details>"}:
            flush_paragraph()
            flush_list()
            blocks.append(stripped)
            index += 1
            continue

        summary_match = re.fullmatch(r"<summary>(.*?)</summary>", stripped)
        if summary_match:
            flush_paragraph()
            flush_list()
            blocks.append(f"<summary>{html.escape(summary_match.group(1))}</summary>")
            index += 1
            continue

        fence_match = re.match(r"^\s*(```|~~~)", line)
        if fence_match:
            flush_paragraph()
            flush_list()
            fence = fence_match.group(1)
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith(fence):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            code_text = html.escape("\n".join(code_lines))
            blocks.append(f"<pre><code>{code_text}</code></pre>")
            continue

        if is_table_start(lines, index):
            flush_paragraph()
            flush_list()
            table_lines = [lines[index], lines[index + 1]]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                table_lines.append(lines[index])
                index += 1
            blocks.append(render_markdown_table(table_lines))
            continue

        heading_match = re.match(r"^(#{1,4})\s+(.+?)\s*$", line)
        if heading_match:
            flush_paragraph()
            flush_list()
            level = len(heading_match.group(1))
            heading_counter += 1
            heading_id = f" id=\"section-{heading_counter}\"" if with_heading_ids else ""
            blocks.append(f"<h{level}{heading_id}>{render_inline_markdown(heading_match.group(2))}</h{level}>")
            index += 1
            continue

        quote_match = re.match(r"^\s*>\s?(.*)$", line)
        if quote_match:
            flush_paragraph()
            flush_list()
            quote_lines = [quote_match.group(1)]
            index += 1
            while index < len(lines):
                next_quote = re.match(r"^\s*>\s?(.*)$", lines[index])
                if not next_quote:
                    break
                quote_lines.append(next_quote.group(1))
                index += 1
            quote_text = "<br>".join(render_inline_markdown(part) for part in quote_lines)
            blocks.append(f"<blockquote>{quote_text}</blockquote>")
            continue

        unordered = re.match(r"^\s*[-*+]\s+(.+)$", line)
        ordered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if unordered or ordered:
            flush_paragraph()
            current_type = "ol" if ordered else "ul"
            if list_type != current_type:
                flush_list()
                list_type = current_type
            item_text = ordered.group(1) if ordered else unordered.group(1)
            list_items.append(render_inline_markdown(item_text))
            index += 1
            continue

        flush_list()
        paragraph.append(line)
        index += 1

    flush_paragraph()
    flush_list()
    return "\n".join(blocks)


def render_inline_markdown(text: str) -> str:
    parts = re.split(r"(`[^`]+`)", text)
    rendered: list[str] = []
    for part in parts:
        if len(part) >= 2 and part.startswith("`") and part.endswith("`"):
            rendered.append(f"<code>{html.escape(part[1:-1])}</code>")
        else:
            rendered.append(html.escape(part))
    return "".join(rendered)


def is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    return "|" in lines[index] and is_table_separator(lines[index + 1])


def is_table_separator(line: str) -> bool:
    cells = split_table_row(line)
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|") if cell.strip()]


def render_markdown_table(table_lines: list[str]) -> str:
    header = split_table_row(table_lines[0])
    rows = [split_table_row(line) for line in table_lines[2:]]
    header_html = "".join(f"<th>{render_inline_markdown(cell)}</th>" for cell in header)
    body_rows: list[str] = []
    for row in rows:
        cells = row[: len(header)] + [""] * max(0, len(header) - len(row))
        body_rows.append("<tr>" + "".join(f"<td>{render_inline_markdown(cell)}</td>" for cell in cells) + "</tr>")
    return "<table><thead><tr>" + header_html + "</tr></thead><tbody>" + "".join(body_rows) + "</tbody></table>"
