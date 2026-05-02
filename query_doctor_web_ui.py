"""Pure HTML rendering helpers for the local Query Doctor UI."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any


WEB_STAGES = (
    (0, "Проверяем Query ID", 4),
    (1, "Собираем или переиспользуем профиль", 24),
    (2, "Анализируем профиль", 50),
    (3, "Генерируем отчёт", 74),
    (4, "Проверяем отчёт", 90),
    (5, "Готово", 100),
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
        "<html lang=\"ru\">",
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
        body.append(render_trust_strip())
        body.append(render_no_reports_note())
        body.append(render_pending_progress_panel())
    if error is not None:
        body.append(render_error_panel(error))
    if job is not None:
        body.append(render_job_panel(job))
    if result is not None:
        body.extend(render_result(result))
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
.run-form{display:grid;gap:13px}.run-main-row{display:grid;grid-template-columns:minmax(280px,1fr) auto;gap:12px;align-items:start}.field{display:grid;gap:7px;min-width:0}.field label,.mode-control>span{color:#303a46;font-size:13px;font-weight:650}.input{width:100%;height:40px;border:1px solid var(--border-strong);border-radius:6px;background:#fff;color:var(--text);font-family:var(--mono);font-size:13px;padding:0 12px;outline:none}.input:focus{border-color:rgba(23,107,135,.65);box-shadow:0 0 0 3px rgba(23,107,135,.1)}.helper{color:var(--muted);font-size:12px}.run-secondary-row{display:block}.mode-control{display:inline-grid;gap:6px}.segmented{display:inline-grid;grid-template-columns:repeat(2,1fr);gap:2px;height:34px;padding:2px;border:1px solid var(--border-strong);border-radius:6px;background:var(--panel-muted)}.segmented input{position:absolute;opacity:0;pointer-events:none}.segmented label{min-width:58px;display:grid;place-items:center;border-radius:4px;color:var(--muted);cursor:pointer;font-family:var(--mono);font-size:11.5px;font-weight:700}.segmented input:checked+span,.segmented input:checked+label{color:var(--accent-strong);background:#fff;box-shadow:0 1px 2px rgba(15,23,42,.06)}.segmented span{display:grid;place-items:center;min-width:58px;border-radius:4px;padding:0 10px}.mode-help{display:flex;flex-wrap:wrap;gap:7px;margin-top:7px;color:var(--muted);font-size:12px}.mode-help span{display:inline-flex;align-items:center;gap:6px;padding:5px 8px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted)}.manual-inputs-hidden{display:none}.batch-run-panel{padding:18px 20px 20px;margin-bottom:14px}.batch-form{display:grid;gap:13px}.batch-form-grid{display:grid;grid-template-columns:repeat(5,minmax(120px,1fr));gap:12px}.batch-checkbox-row{display:flex;flex-wrap:wrap;gap:10px 16px;color:#303a46;font-size:13px;font-weight:650}.batch-checkbox-row input{margin-right:6px}.trust-strip{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;margin:14px 0;padding:9px 12px;border:1px solid var(--border);border-radius:7px;background:#fff;color:var(--muted);font-size:12px;font-weight:650;box-shadow:0 1px 2px rgba(15,23,42,.035)}.trust-item{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}.trust-icon{width:14px;height:14px;display:inline-grid;place-items:center;border-radius:999px;background:var(--accent-soft);color:var(--accent-strong);font-family:var(--mono);font-size:9px;line-height:1;flex:0 0 auto}.no-reports-note{padding:13px 14px;margin-bottom:14px;color:var(--muted);font-size:12px}.no-reports-note strong{display:block;margin-bottom:3px;color:var(--text);font-size:13px}
.error-card{border:1px solid rgba(153,27,27,.18);background:var(--red-bg);padding:12px 14px;color:var(--red);border-radius:7px;margin-bottom:14px}.error-card strong{display:block;margin-bottom:4px;color:var(--red)}.progress-card{padding:13px 14px;margin-bottom:14px}.progress-card--hidden{display:none}.progress-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}.progress-title{font-weight:650}.progress-stage{color:var(--muted);font-size:.84rem}.progress-bar{height:6px;border-radius:999px;background:var(--gray-bg);border:1px solid var(--border);overflow:hidden}.progress-fill{display:block;height:100%;width:4%;background:var(--accent);transition:width .2s ease}.progress-note{margin:8px 0 0;color:var(--muted);font-size:.77rem}.batch-progress{margin-top:12px;display:grid;gap:10px}.batch-progress-steps{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}.batch-progress-step{border:1px solid var(--border);border-radius:7px;background:var(--panel-muted);padding:9px 10px;min-width:0}.batch-progress-step strong{display:block;font-size:12px;color:var(--text);overflow-wrap:anywhere}.batch-progress-step span{display:block;margin-top:3px;font-size:11px;color:var(--muted);overflow-wrap:anywhere}.batch-progress-step--done{border-color:rgba(22,101,52,.2);background:var(--green-bg)}.batch-progress-step--running{border-color:rgba(23,107,135,.22);background:var(--accent-soft)}.batch-progress-step--failed{border-color:rgba(153,27,27,.18);background:var(--red-bg)}.batch-progress-metrics{display:flex;flex-wrap:wrap;gap:7px;color:var(--muted);font-size:12px}.batch-progress-metrics span{border:1px solid var(--border);border-radius:999px;background:#fff;padding:4px 8px}
.batch-panel{padding:18px 20px;overflow:hidden}.batch-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:14px}.batch-head h1{margin:0 0 4px;font-size:20px;line-height:1.2;letter-spacing:-.02em}.batch-head p{margin:0;color:var(--muted);font-size:13px}.batch-metrics{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px;margin-bottom:12px}.batch-metric{display:grid;gap:4px;padding:9px 10px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);min-width:0}.batch-metric span{color:var(--muted);font-size:11px;font-weight:650;text-transform:uppercase}.batch-metric strong{font-family:var(--mono);font-size:13px;overflow-wrap:anywhere}.batch-note{margin-bottom:12px;padding:9px 10px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);color:var(--muted);font-size:12px}.batch-table-wrap{max-width:100%;overflow-x:auto;overflow-y:visible;border:1px solid var(--border);border-radius:7px}.batch-table{min-width:1120px;width:100%;border-collapse:collapse;font-size:12px;background:#fff}.batch-table th,.batch-table td{border-bottom:1px solid var(--border);padding:8px 9px;text-align:left;vertical-align:top}.batch-table th{position:sticky;top:0;background:var(--panel-muted);color:#303a46;font-size:11px;text-transform:uppercase;letter-spacing:0;font-weight:720}.batch-cell--compact{font-family:var(--mono);white-space:nowrap;overflow-wrap:normal}.batch-cell--reason{min-width:260px;white-space:normal;overflow-wrap:anywhere}.batch-mini-badge{display:inline-flex;align-items:center;min-height:20px;padding:2px 7px;border-radius:5px;border:1px solid transparent;font-family:var(--mono);font-size:10.5px;font-weight:750;line-height:1;white-space:nowrap}.batch-severity--high,.batch-severity--failed,.batch-status--failed,.batch-report--untrusted{color:var(--red);background:var(--red-bg);border-color:rgba(153,27,27,.14)}.batch-severity--suspicious,.batch-status--warning,.batch-report--generated{color:var(--amber);background:var(--amber-bg);border-color:rgba(146,64,14,.16)}.batch-severity--clean,.batch-status--ok,.batch-report--passed{color:var(--green);background:var(--green-bg);border-color:rgba(22,101,52,.16)}.batch-status--neutral,.batch-report--neutral{color:var(--gray);background:var(--gray-bg);border-color:rgba(75,85,99,.14)}.empty-cell{color:var(--muted);text-align:center}
.report-header{margin-bottom:14px;padding:18px 20px}.breadcrumb{display:flex;align-items:center;gap:8px;margin-bottom:12px;color:var(--muted);font-size:12px;font-weight:650}.report-title-row{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.report-title-row h1{margin:0 0 8px;font-size:20px;line-height:1.2;letter-spacing:-.03em}.report-subtitle{color:var(--muted);font-size:13px}.query-line{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px 10px;color:var(--muted);font-size:12px}.status-strip{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;padding:9px 10px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);color:var(--muted);font-size:12px;font-weight:650}.status-item{display:inline-flex;align-items:center;gap:6px}.dot{width:7px;height:7px;border-radius:999px;background:var(--green)}.dot.amber{background:#d97706}.dot.gray{background:#6b7280}.report-shell{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:14px;align-items:start}.content-main{display:grid;gap:14px}.report-card,.docs-panel{padding:0;overflow:hidden}.report-card summary,.docs-panel h1{padding:16px 18px;margin:0;border-bottom:1px solid var(--border);background:var(--panel-muted);font-size:15px;font-weight:720}.report-body{padding:16px 18px;color:var(--text);font-size:13px}.report-body h1,.report-body h2,.report-body h3,.report-body h4{margin:1.15em 0 .5em;line-height:1.2}.report-body h1:first-child,.report-body h2:first-child,.report-body h3:first-child{margin-top:0}.report-body h1{font-size:20px}.report-body h2{font-size:17px}.report-body h3{font-size:15px}.report-body p{margin:.7em 0}.report-body ul,.report-body ol{margin:.55em 0 .8em;padding-left:1.35rem}.report-body li{margin:.32em 0;overflow-wrap:anywhere}.report-body code{background:var(--panel-muted);border:1px solid var(--border);border-radius:5px;padding:.08rem .28rem;font-family:var(--mono);font-size:.88em;overflow-wrap:anywhere}.report-body pre{margin:.75em 0;padding:12px;background:#0f1720;color:#e5edf5;border:1px solid var(--border);border-radius:6px;white-space:pre-wrap;overflow-wrap:anywhere}.report-body pre code{border:0;background:transparent;padding:0;color:inherit}.report-body blockquote{margin:.75em 0;padding:.35em .8em;border-left:3px solid var(--accent);background:var(--accent-soft);color:#36505c}.report-body table{width:100%;border-collapse:collapse;margin:.8em 0;font-size:.86rem}.report-body th,.report-body td{border:1px solid var(--border);padding:6px 8px;text-align:left;vertical-align:top}.report-body th{background:var(--panel-muted);color:#303a46}.appendix-notice{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 12px;padding:10px 12px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);color:var(--muted);font-size:12px}.side-panel{position:sticky;top:18px;display:grid;gap:14px}.side-card{padding:14px}.side-card h2{margin:0 0 10px;font-size:14px}.meta-list{display:grid;gap:8px}.meta-row{display:flex;justify-content:space-between;gap:12px;padding-bottom:8px;border-bottom:1px solid var(--border);color:var(--muted);font-size:12px}.meta-row:last-child{padding-bottom:0;border-bottom:0}.meta-row strong{color:var(--text);font-family:var(--mono);font-size:11px;text-align:right}.artifact-list,.toc-list,.timeline{display:grid;gap:7px}.artifact-item,.toc-list a{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px 10px;padding:8px 9px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);color:var(--muted);font-size:12px;font-weight:650}.artifact-item code{display:block;margin-top:2px;font-family:var(--mono);color:var(--text);font-size:11px}.toc-list a{display:block}.timeline-item{display:grid;grid-template-columns:16px 1fr;gap:8px;color:var(--muted);font-size:12px}.timeline-dot{width:8px;height:8px;margin-top:5px;border-radius:999px;background:var(--green)}.timeline-item strong{display:block;color:var(--text);font-size:12px}
@media(max-width:980px){.report-shell{grid-template-columns:1fr}.side-panel{position:static}.batch-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.batch-form-grid{grid-template-columns:repeat(2,minmax(120px,1fr))}}@media(max-width:760px){.page{padding:18px 16px 40px}.app-header{align-items:stretch;flex-direction:column}.top-nav{width:fit-content}.run-main-row{grid-template-columns:1fr}.run-secondary-row{align-items:stretch;flex-direction:column}.mode-control,.run-button{width:100%}.segmented{width:100%}.report-title-row{align-items:stretch;flex-direction:column}.batch-metrics,.batch-form-grid{grid-template-columns:1fr}}
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
        "<span class=\"brand-subtitle\">Local-first Impala query diagnostics</span></span>"
        "</a>"
        f"{render_top_nav(active)}"
        "</header>"
    )


def render_top_nav(active: str) -> str:
    batch_class = "nav-link nav-link--active" if active == "batch" else "nav-link"
    query_class = "nav-link nav-link--active" if active == "query" else "nav-link"
    readme_class = "nav-link nav-link--active" if active == "readme" else "nav-link"
    return (
        "<nav class=\"top-nav\" aria-label=\"Main navigation\">"
        f"<a class=\"{batch_class}\" href=\"/\">Batch</a>"
        f"<a class=\"{query_class}\" href=\"/query\">Query ID</a>"
        f"<a class=\"{readme_class}\" href=\"/readme\">README</a>"
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
    return render_page(
        settings,
        active_nav="readme",
        show_run_panel=False,
        extra_sections=[render_readme_card(settings.repo_dir)],
    )


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
) -> str:
    effective_form_values = form_values
    if effective_form_values is None and job is not None:
        effective_form_values = getattr(job, "batch_form_values", None)
    sections = [
        render_batch_run_panel(settings, effective_form_values, run_disabled=job is not None and job.status == "running")
    ]
    if job is not None:
        sections.append(render_job_panel(job))
    if job is None or job.status != "ok":
        sections.append(render_batch_card(settings))
    return render_page(
        settings,
        active_nav="batch",
        show_run_panel=False,
        error=error,
        extra_sections=sections,
    )


def render_batch_run_panel(settings: Any, form_values: dict[str, Any] | None = None, *, run_disabled: bool = False) -> str:
    metadata_configured = bool(getattr(settings, "metadata_coordinator", None))
    values = {
        "analysis_depth": "full" if metadata_configured else "fast",
        "recent_window_minutes": "1440",
        "cm_inspect_limit": "1000",
        "select_limit": "200",
        "min_duration_sec": "10",
        "max_duration_sec": "",
        "order": "duration-desc",
        "jobs": "4",
        "user": "",
        "pool": "",
        "query_type": "QUERY",
        "include_failed": False,
        "include_running": False,
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
        "Full analysis: collect table metadata"
        if metadata_configured
        else "Full analysis: collect table metadata (unavailable: metadata not configured)"
    )
    metadata_note = (
        "Metadata collection is configured for this web session."
        if metadata_configured
        else "Metadata collection is not configured for this web session. Fast triage still works."
    )
    order_options = "".join(
        f"<option value=\"{html.escape(option, quote=True)}\"{' selected' if option == order else ''}>{html.escape(option)}</option>"
        for option in ("duration-desc", "recent", "duration-asc")
    )
    button_disabled = " disabled" if run_disabled else ""
    button_label = "Running" if run_disabled else "Run"
    return (
        "<section class=\"panel batch-run-panel\" aria-label=\"Run batch triage\">"
        "<div class=\"section-heading\"><div>"
        "<h1 class=\"section-title\">Batch query triage</h1>"
        "<div class=\"section-kicker\">Run a bounded batch with metadata by default, or choose fast analyzer-only triage. "
        "LLM report generation stays disabled from web batch runs.</div>"
        "</div><span class=\"badge blue\">batch triage</span></div>"
        "<form id=\"batch-form\" class=\"batch-form\" method=\"post\" action=\"/batch/run\">"
        "<div class=\"batch-checkbox-row\" role=\"group\" aria-label=\"Analysis depth\">"
        f"<label><input type=\"radio\" name=\"analysis_depth\" value=\"full\"{full_checked}{full_disabled}> "
        f"{html.escape(full_label)}</label>"
        f"<label><input type=\"radio\" name=\"analysis_depth\" value=\"fast\"{fast_checked}> "
        "Fast triage: analyzer only</label>"
        "</div>"
        f"<div class=\"batch-note\">{html.escape(metadata_note)}</div>"
        "<div class=\"batch-form-grid\">"
        f"{render_batch_number_field('recent_window_minutes', 'Recent window minutes', value('recent_window_minutes'))}"
        f"{render_batch_number_field('cm_inspect_limit', 'CM inspect limit', value('cm_inspect_limit'))}"
        f"{render_batch_number_field('select_limit', 'Select limit', value('select_limit'))}"
        f"{render_batch_number_field('min_duration_sec', 'Min duration sec', value('min_duration_sec'), step='0.001')}"
        f"{render_batch_number_field('max_duration_sec', 'Max duration sec', value('max_duration_sec'), step='0.001', required=False)}"
        "<div class=\"field\"><label for=\"order\">Order</label>"
        f"<select class=\"input\" id=\"order\" name=\"order\">{order_options}</select></div>"
        f"{render_batch_number_field('jobs', 'Jobs', value('jobs'))}"
        f"{render_batch_text_field('user', 'User filter', value('user'))}"
        f"{render_batch_text_field('pool', 'Pool filter', value('pool'))}"
        f"{render_batch_text_field('query_type', 'Query type', value('query_type'))}"
        "</div>"
        "<div class=\"batch-checkbox-row\">"
        f"<label><input type=\"checkbox\" name=\"include_failed\" value=\"on\"{checked('include_failed')}> Include failed</label>"
        f"<label><input type=\"checkbox\" name=\"include_running\" value=\"on\"{checked('include_running')}> Include running</label>"
        "</div>"
        "<div class=\"pipeline-line\" aria-label=\"Batch safety scope\">"
        "<span><strong>Full:</strong> <code>--metadata-mode on</code> with server-startup metadata settings</span>"
        "<span><strong>Fast:</strong> <code>--metadata-mode off</code></span>"
        "<span><strong>Always:</strong> <code>--top-reports 0</code>; no LLM report generation</span>"
        "<span><strong>Output:</strong> generated dedicated <code>/tmp/query-doctor-web-batch-*</code> directory</span>"
        "<span><strong>Summary:</strong> rendered summaries are read-only</span>"
        "<span><strong>Credentials:</strong> environment or local config only; never entered here</span>"
        "</div>"
        f"<button class=\"run-button\" type=\"submit\"{button_disabled}>{button_label}</button>"
        "</form></section>"
    )


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


def render_batch_card(settings: Any) -> str:
    summary_path = getattr(settings, "batch_summary", None)
    if summary_path is None:
        return (
            "<section class=\"panel batch-panel\" aria-label=\"Batch triage\">"
            "<div class=\"batch-head\">"
            "<div><h1>Batch query triage</h1>"
            "<p>Run a batch from this page, or start the web UI with "
            "<code>--batch-summary PATH</code> to inspect an existing summary.</p></div>"
            "</div>"
            "<div class=\"batch-note\">Web batch runs use <code>top-reports 0</code>: no LLM report generation. "
            "Full mode collects metadata only when configured at server startup; Fast mode keeps metadata off. "
            "Rendered summaries are read-only.</div>"
            "</section>"
        )
    try:
        payload = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (
            "<section class=\"panel batch-panel\" aria-label=\"Batch triage\">"
            "<div class=\"batch-head\"><div><h1>Batch query triage</h1>"
            "<p>Configured batch summary could not be read.</p></div></div>"
            f"<div class=\"batch-note\">{html.escape(type(exc).__name__)}</div>"
            "</section>"
        )
    if not isinstance(payload, dict):
        return (
            "<section class=\"panel batch-panel\" aria-label=\"Batch triage\">"
            "<div class=\"batch-head\"><div><h1>Batch query triage</h1>"
            "<p>Configured batch summary is not a JSON object.</p></div></div>"
            "</section>"
        )
    return render_batch_summary(payload)


def render_batch_summary(summary: dict[str, Any]) -> str:
    cases = summary.get("cases")
    if not isinstance(cases, list):
        cases = []
    score_positive = sum(1 for case in cases if isinstance(case, dict) and numeric_value(case.get("score")) > 0)
    failed_count = sum(1 for case in cases if isinstance(case, dict) and case_has_failure(case))
    header_items = [
        ("total cases", len(cases)),
        ("selected candidates", summary.get("selected_count")),
        ("score > 0", score_positive),
        ("failed cases", failed_count),
        ("duration filter", summary.get("duration_filter")),
        ("jobs", summary.get("jobs")),
        ("total seconds", summary.get("total_seconds")),
    ]
    header = "".join(
        "<div class=\"batch-metric\">"
        f"<span>{html.escape(label)}</span>"
        f"<strong>{escape_value(value)}</strong>"
        "</div>"
        for label, value in header_items
    )
    rows = "\n".join(
        render_batch_case_row(rank, case)
        for rank, case in enumerate(cases, start=1)
        if isinstance(case, dict)
    )
    if not rows:
        rows = (
            "<tr><td colspan=\"14\" class=\"empty-cell\">No case summaries were found in the configured batch summary.</td></tr>"
        )
    return (
        "<section class=\"panel batch-panel\" aria-label=\"Batch triage\">"
        "<div class=\"batch-head\">"
        "<div><h1>Batch query triage</h1>"
        "<p>Read-only deterministic analyzer ranking from <code>batch_summary.json</code>.</p></div>"
        "<span class=\"badge blue\">read-only</span>"
        "</div>"
        f"<div class=\"batch-metrics\">{header}</div>"
        "<div class=\"batch-note\">Score is deterministic analyzer output. LLM reports exist only where "
        "<code>report_generated</code> is true. Partial reports are untrusted and not rendered here.</div>"
        "<div class=\"batch-table-wrap\"><table class=\"batch-table\">"
        "<thead><tr>"
        "<th>Rank</th><th>Query ID</th><th>Score</th><th>Duration</th>"
        "<th>Card</th><th>Mem</th><th>Skew</th><th>Tail</th>"
        "<th>Collection</th><th>Analysis</th><th>Metadata</th><th>Report</th><th>Reasons</th><th>Details</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
        "</section>"
    )


def render_batch_case_row(rank: int, case: dict[str, Any]) -> str:
    report_status = batch_report_status(case)
    reasons = case.get("score_reasons")
    if isinstance(reasons, list):
        reason_text = "; ".join(str(item) for item in reasons)
    else:
        reason_text = ""
    cells = [
        compact_cell(rank),
        compact_cell(case.get("query_id")),
        compact_cell(score_badge(case)),
        compact_cell(case.get("duration_sec")),
        compact_cell(case.get("cardinality_anomaly_count")),
        compact_cell(case.get("memory_anomaly_count")),
        compact_cell(case.get("backend_data_skew")),
        compact_cell(case.get("host_tail_candidate_count")),
        compact_cell(status_badge(case.get("collection_status"))),
        compact_cell(status_badge(case.get("analysis_status"))),
        compact_cell(status_badge(case.get("metadata_status"))),
        compact_cell(report_badge(report_status)),
        reason_cell(reason_text),
        compact_cell(batch_case_details_link(case)),
    ]
    return f"<tr>{''.join(cells)}</tr>"


def batch_case_details_link(case: dict[str, Any]) -> SafeHtml:
    case_id = batch_case_id(case)
    if case_id is None:
        return SafeHtml("")
    escaped = html.escape(case_id, quote=True)
    return SafeHtml(f"<a class=\"button\" href=\"/batch/case/{escaped}\">Details</a>")


def batch_case_id(case: dict[str, Any]) -> str | None:
    value = case.get("case_index")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return f"case-{parsed:03d}"


def render_batch_case_detail_page(
    settings: Any,
    case_id: str,
    case: dict[str, Any],
    metadata_facts: dict[str, Any] | None = None,
) -> str:
    sections = [render_batch_case_detail(case_id, case, metadata_facts)]
    return render_page(settings, active_nav="batch", show_run_panel=False, extra_sections=sections)


def render_batch_case_not_found_page(settings: Any, case_id: str) -> str:
    safe_case_id = html.escape(case_id)
    section = (
        "<section class=\"panel batch-panel\" aria-label=\"Batch case not found\">"
        "<div class=\"batch-head\"><div><h1>Batch case not found</h1>"
        f"<p>No batch case summary was found for <code>{safe_case_id}</code>.</p></div>"
        "<span class=\"badge gray\">not found</span></div>"
        "<div class=\"batch-note\">Case details are resolved only from the server-owned "
        "<code>batch_summary.json</code>; request paths cannot choose local files.</div>"
        "</section>"
    )
    return render_page(settings, active_nav="batch", show_run_panel=False, extra_sections=[section])


def render_batch_case_detail(case_id: str, case: dict[str, Any], metadata_facts: dict[str, Any] | None = None) -> str:
    report_status = batch_report_status(case)
    reasons = case.get("score_reasons")
    if isinstance(reasons, list):
        reason_items = "".join(f"<li>{escape_value(item)}</li>" for item in reasons)
    else:
        reason_items = "<li>unknown</li>"
    fields = [
        ("case", case_id),
        ("query id", case.get("query_id")),
        ("score", score_badge(case)),
        ("duration sec", case.get("duration_sec")),
        ("collection", status_badge(case.get("collection_status"))),
        ("analysis", status_badge(case.get("analysis_status"))),
        ("metadata", status_badge(case.get("metadata_status"))),
        ("report", report_badge(report_status)),
        ("cardinality anomalies", case.get("cardinality_anomaly_count")),
        ("memory anomalies", case.get("memory_anomaly_count")),
        ("backend data skew", case.get("backend_data_skew")),
        ("host-tail candidates", case.get("host_tail_candidate_count")),
        ("referenced tables", case.get("referenced_table_count")),
        ("collected metadata tables", case.get("collected_metadata_table_count")),
        ("too large metadata", case.get("too_large_count")),
        ("failure category", case.get("failure_category")),
        ("cm collect seconds", case.get("cm_collect_seconds")),
        ("analysis seconds", case.get("analysis_seconds")),
        ("report seconds", case.get("report_seconds")),
        ("total seconds", case.get("total_seconds")),
        ("report generated", case.get("report_generated")),
    ]
    rows = "".join(
        "<div class=\"meta-row\">"
        f"<span>{html.escape(label)}</span><strong>{value if isinstance(value, SafeHtml) else escape_value(value)}</strong>"
        "</div>"
        for label, value in fields
    )
    trust_note = (
        "Validated report exists according to the batch summary."
        if case.get("report_generated") is True and str(case.get("report_validation_status") or "") == "passed"
        else "No trusted generated report is rendered here. Partial reports remain untrusted."
    )
    return (
        "<section class=\"panel batch-panel\" aria-label=\"Batch case details\">"
        "<div class=\"batch-head\"><div><h1>Batch case details</h1>"
        "<p>Read-only deterministic summary fields from <code>batch_summary.json</code>.</p></div>"
        f"<span class=\"badge blue\">{html.escape(case_id)}</span></div>"
        "<div class=\"batch-note\">This page does not render raw SQL, profiles, metadata, or local case paths.</div>"
        f"<div class=\"meta-list\">{rows}</div>"
        "<div class=\"batch-note\">"
        f"{html.escape(trust_note)}"
        "</div>"
        f"{render_metadata_facts_section(case, metadata_facts)}"
        "<section class=\"panel docs-panel\" aria-label=\"Score reasons\">"
        "<h1>Score reasons</h1>"
        f"<div class=\"report-body\"><ul>{reason_items}</ul></div>"
        "</section>"
        "</section>"
    )


def render_metadata_facts_section(case: dict[str, Any], metadata_facts: dict[str, Any] | None) -> str:
    if not metadata_facts:
        return (
            "<section class=\"panel docs-panel\" aria-label=\"Metadata facts\">"
            "<h1>Metadata facts</h1>"
            "<div class=\"report-body\"><p>metadata facts unavailable</p>"
            "<p>Only deterministic metadata facts from <code>analysis_facts.md</code> are rendered here.</p></div>"
            "</section>"
        )
    statement_counts = metadata_facts.get("statement_counts")
    if not isinstance(statement_counts, dict):
        statement_counts = {}
    summary_items = [
        ("metadata status", case.get("metadata_status")),
        ("referenced tables", case.get("referenced_table_count")),
        ("collected metadata tables", case.get("collected_metadata_table_count")),
        ("too large metadata", case.get("too_large_count")),
        ("statement ok", statement_counts.get("ok", 0)),
        ("statement error", statement_counts.get("error", 0)),
        ("statement not_applicable", statement_counts.get("not_applicable", 0)),
        ("statement too_large", statement_counts.get("too_large", 0)),
    ]
    summary_rows = "".join(
        "<div class=\"meta-row\">"
        f"<span>{html.escape(label)}</span><strong>{escape_value(value)}</strong>"
        "</div>"
        for label, value in summary_items
    )
    tables = metadata_facts.get("tables")
    if not isinstance(tables, list):
        tables = []
    rows = "\n".join(render_metadata_fact_table_row(table) for table in tables if isinstance(table, dict))
    if not rows:
        rows = "<tr><td colspan=\"12\" class=\"empty-cell\">metadata facts unavailable</td></tr>"
    return (
        "<section class=\"panel docs-panel\" aria-label=\"Metadata facts\">"
        "<h1>Metadata facts</h1>"
        "<div class=\"report-body\">"
        "<p>Deterministic table-level metadata facts. Missing or incomplete stats are limitations/checks, not root causes.</p>"
        f"<div class=\"meta-list\">{summary_rows}</div>"
        "<div class=\"batch-table-wrap\"><table class=\"batch-table\">"
        "<thead><tr>"
        "<th>Table</th><th>Object</th><th>SHOW CREATE</th><th>TABLE STATS</th><th>COLUMN STATS</th>"
        "<th>Row-count stats</th><th>Column stats</th><th>Observed</th><th>Missing</th><th>Partitions</th><th>Format</th><th>Limitations</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
        "</div>"
        "</section>"
    )


def render_metadata_fact_table_row(table: dict[str, Any]) -> str:
    statements = table.get("statements")
    if not isinstance(statements, dict):
        statements = {}
    cells = [
        reason_cell(table.get("table")),
        compact_cell(table.get("object type")),
        compact_cell(status_badge(statements.get("SHOW CREATE TABLE"))),
        compact_cell(status_badge(statements.get("SHOW TABLE STATS"))),
        compact_cell(status_badge(statements.get("SHOW COLUMN STATS"))),
        compact_cell(table.get("table stats row-count completeness")),
        compact_cell(table.get("column stats completeness")),
        compact_cell(table.get("column stats columns observed")),
        compact_cell(table.get("column stats missing/unknown markers")),
        reason_cell(table.get("partition columns")),
        compact_cell(table.get("file format")),
        reason_cell(metadata_fact_limitations(table, statements)),
    ]
    return f"<tr>{''.join(cells)}</tr>"


def metadata_fact_limitations(table: dict[str, Any], statements: dict[Any, Any]) -> str:
    limitations: list[str] = []
    object_type = str(table.get("object type") or "unknown")
    table_stats = str(table.get("table stats row-count completeness") or "unknown")
    column_stats = str(table.get("column stats completeness") or "unknown")
    if object_type == "view":
        limitations.append("view metadata stats not applicable")
    for statement, status in statements.items():
        status_text = str(status or "unknown")
        if status_text in {"error", "too_large", "timeout", "not_applicable"}:
            limitations.append(f"{statement}: {status_text}")
    if table_stats not in {"available", "unknown"}:
        limitations.append(f"row-count stats: {table_stats}")
    if column_stats not in {"available", "unknown"}:
        limitations.append(f"column stats: {column_stats}")
    return "; ".join(limitations) if limitations else "none observed"


def compact_cell(value: Any) -> str:
    return f"<td class=\"batch-cell--compact\">{value if isinstance(value, SafeHtml) else escape_value(value)}</td>"


def reason_cell(value: Any) -> str:
    return f"<td class=\"batch-cell--reason\">{escape_value(value)}</td>"


class SafeHtml(str):
    pass


def score_badge(case: dict[str, Any]) -> SafeHtml:
    score = numeric_value(case.get("score"))
    if case.get("collection_status") == "failed" or case.get("analysis_status") == "failed":
        label = f"{display_score(case.get('score'))} failed"
        class_name = "batch-severity--failed"
    elif score >= 20:
        label = f"{display_score(case.get('score'))} high"
        class_name = "batch-severity--high"
    elif score > 0:
        label = f"{display_score(case.get('score'))} suspicious"
        class_name = "batch-severity--suspicious"
    else:
        label = f"{display_score(case.get('score'))} clean"
        class_name = "batch-severity--clean"
    return badge_html(label, class_name)


def status_badge(value: Any) -> SafeHtml:
    text = "unknown" if value is None else str(value)
    normalized = text.lower()
    if normalized in {"ok", "collected", "passed"}:
        class_name = "batch-status--ok"
    elif normalized == "failed":
        class_name = "batch-status--failed"
    elif normalized in {"skipped", "not_run", "not_observed", "unknown"}:
        class_name = "batch-status--neutral"
    else:
        class_name = "batch-status--warning"
    return badge_html(text, class_name)


def report_badge(value: str) -> SafeHtml:
    normalized = value.lower()
    if "partial" in normalized or "untrusted" in normalized:
        class_name = "batch-report--untrusted"
    elif "validated" in normalized or normalized == "passed":
        class_name = "batch-report--passed"
    elif normalized == "not_run":
        class_name = "batch-report--neutral"
    else:
        class_name = "batch-report--generated"
    return badge_html(value, class_name)


def badge_html(label: Any, class_name: str) -> SafeHtml:
    return SafeHtml(f"<span class=\"batch-mini-badge {class_name}\">{escape_value(label)}</span>")


def display_score(value: Any) -> str:
    if value is None:
        return "unknown"
    return str(value)


def batch_report_status(case: dict[str, Any]) -> str:
    validation = str(case.get("report_validation_status") or "not_run")
    generated = case.get("report_generated") is True
    if validation == "failed_partial_untrusted":
        return "partial untrusted"
    if generated and validation == "passed":
        return "validated report"
    if generated:
        return f"generated/{validation}"
    return validation


def case_has_failure(case: dict[str, Any]) -> bool:
    if case.get("failure_category"):
        return True
    return any(
        case.get(name) == "failed"
        for name in ("collection_status", "analysis_status", "metadata_status", "report_validation_status")
    )


def numeric_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def escape_value(value: Any) -> str:
    if value is None:
        return "unknown"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return html.escape(str(value))


def render_readme_card(repo_dir: Path) -> str:
    readme_text = read_repository_readme(repo_dir)
    if readme_text is None:
        readme_html = "<p>README.md не найден в корне репозитория.</p>"
    else:
        readme_html = render_report_markdown_html(readme_text)
    return (
        "<section class=\"panel docs-panel\" aria-label=\"README.md\">"
        "<h1>README.md</h1>"
        f"<div class=\"report-body\">{readme_html}</div>"
        "</section>"
    )


def read_repository_readme(repo_dir: Path) -> str | None:
    try:
        return (repo_dir / "README.md").read_text(encoding="utf-8")
    except OSError:
        return None


def render_client_script() -> str:
    return """<script>
document.addEventListener('DOMContentLoaded', function () {
  var form = document.getElementById('analyze-form');
  var pending = document.getElementById('pending-panel');
  if (form && pending) {
    form.addEventListener('submit', function () {
      pending.classList.remove('progress-card--hidden');
      var button = form.querySelector('button[type="submit"]');
      if (button) {
        button.disabled = true;
        button.textContent = 'Run';
      }
    });
  }
  var jobPanel = document.querySelector('[data-job-status-url]');
  if (!jobPanel) {
    return;
  }
  var stage = document.getElementById('job-stage');
  var fill = document.getElementById('job-progress-fill');
  var resultSlot = document.getElementById('job-result-slot');
  var errorSlot = document.getElementById('job-error-slot');
  var title = jobPanel.querySelector('.progress-title');
  var batchRunButton = document.querySelector('#batch-form button[type="submit"]');
  function poll() {
    fetch(jobPanel.getAttribute('data-job-status-url'), {cache: 'no-store'})
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (stage) { stage.textContent = data.stage || ''; }
        if (fill) { fill.style.width = String(data.progress || 0) + '%'; }
        var runningProgressSlot = document.getElementById('batch-progress-slot');
        if (runningProgressSlot) { runningProgressSlot.innerHTML = data.progress_html || ''; }
        if (data.status === 'ok') {
          if (title) { title.textContent = 'Анализ завершён'; }
          if (data.kind === 'batch' && batchRunButton) {
            batchRunButton.disabled = false;
            batchRunButton.textContent = 'Run';
          }
          if (resultSlot) { resultSlot.innerHTML = data.result_html || ''; }
          return;
        }
        if (data.status === 'failed') {
          if (title) { title.textContent = 'Анализ завершился с ошибкой'; }
          if (data.kind === 'batch' && batchRunButton) {
            batchRunButton.disabled = false;
            batchRunButton.textContent = 'Run';
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
        "<div class=\"progress-head\"><span class=\"progress-title\">Анализ запущен</span>"
        f"<span class=\"progress-stage\">{html.escape(stage[1])}</span></div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\"><span class=\"progress-fill\"></span></div>"
        "<p class=\"progress-note\">Обычно это занимает от нескольких секунд до пары минут.</p>"
        "</section>"
    )


def render_batch_progress_panel(progress_path: Path | None, job_status: str = "running") -> str:
    events = read_batch_progress_events(progress_path)
    summary = summarize_batch_progress(events, job_status=job_status)
    steps = "".join(
        "<div class=\"batch-progress-step batch-progress-step--{state}\">"
        "<strong>{icon} {label}</strong><span>{detail}</span></div>".format(
            state=html.escape(step["state"]),
            icon=html.escape(step["icon"]),
            label=html.escape(step["label"]),
            detail=html.escape(step["detail"]),
        )
        for step in summary["steps"]
    )
    metrics = "".join(
        f"<span>{html.escape(label)}: {html.escape(str(value))}</span>"
        for label, value in summary["metrics"]
    )
    metrics_html = f"<div class=\"batch-progress-metrics\">{metrics}</div>" if metrics else ""
    return (
        "<div class=\"batch-progress\" aria-label=\"Batch progress\">"
        f"<div class=\"batch-progress-steps\">{steps}</div>"
        f"{metrics_html}"
        "</div>"
    )


def read_batch_progress_events(progress_path: Path | None) -> list[dict[str, Any]]:
    if progress_path is None or not progress_path.is_file():
        return []
    events: list[dict[str, Any]] = []
    try:
        for line in progress_path.read_text(encoding="utf-8").splitlines()[-2000:]:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    except OSError:
        return []
    return events


def summarize_batch_progress(events: list[dict[str, Any]], *, job_status: str) -> dict[str, Any]:
    counters = {
        "total": 0,
        "jobs": None,
        "summaries_inspected": None,
        "candidates_selected": None,
        "duration_filter": None,
        "collection_done": 0,
        "analysis_done": 0,
        "failed": 0,
    }
    states = {
        "discovery": "pending",
        "collection": "pending",
        "analysis": "pending",
        "summary": "pending",
        "completed": "pending",
    }
    for event in events:
        stage = str(event.get("stage") or "")
        status = str(event.get("status") or "")
        if stage == "discovery":
            if status == "started":
                states["discovery"] = "running"
            elif status == "done":
                states["discovery"] = "done"
                counters["summaries_inspected"] = event.get("summaries_inspected")
                counters["candidates_selected"] = event.get("candidates_selected")
                counters["duration_filter"] = event.get("duration_filter")
            elif status == "failed":
                states["discovery"] = "failed"
        elif stage == "case_processing":
            if status == "started":
                counters["total"] = numeric_count(event.get("total"))
                counters["jobs"] = event.get("jobs")
                states["collection"] = "running"
            elif status == "done":
                states["collection"] = "done"
                states["analysis"] = "done"
        elif stage == "case":
            if status == "collection_started" and states["collection"] != "done":
                states["collection"] = "running"
            elif status == "collection_done":
                counters["collection_done"] += 1
            elif status == "analysis_started" and states["analysis"] != "done":
                states["analysis"] = "running"
            elif status == "analysis_done":
                counters["analysis_done"] += 1
            elif status == "failed":
                counters["failed"] += 1
        elif stage == "summary":
            if status == "started":
                states["collection"] = "done"
                states["analysis"] = "done"
                states["summary"] = "running"
            elif status == "done":
                states["summary"] = "done"
        elif stage == "batch":
            if status == "done":
                states["completed"] = "done"
                states["summary"] = "done"
                states["collection"] = "done"
                states["analysis"] = "done"
            elif status == "failed":
                states["completed"] = "failed"
    if job_status == "failed" and states["completed"] != "done":
        states["completed"] = "failed"
    if job_status == "ok":
        states["completed"] = "done"
    total = numeric_count(counters["total"])
    processed = counters["analysis_done"] + counters["failed"]
    metrics = []
    if counters["summaries_inspected"] is not None:
        metrics.append(("summaries", counters["summaries_inspected"]))
    if counters["candidates_selected"] is not None:
        metrics.append(("candidates", counters["candidates_selected"]))
    if counters["duration_filter"] is not None:
        metrics.append(("duration filter", counters["duration_filter"]))
    if total:
        metrics.append(("cases processed", f"{processed}/{total}"))
    if counters["failed"]:
        metrics.append(("failed cases", counters["failed"]))
    if counters["jobs"] is not None:
        metrics.append(("jobs", counters["jobs"]))
    return {
        "steps": [
            progress_step("CM discovery", states["discovery"], discovery_detail(counters)),
            progress_step("Profile collection", states["collection"], case_detail(counters, "collection_done")),
            progress_step("Analyzer / metadata pass", states["analysis"], case_detail(counters, "analysis_done")),
            progress_step("Ranking / summary", states["summary"], "summary written" if states["summary"] == "done" else "waiting"),
            progress_step("Completed", states["completed"], "batch done" if states["completed"] == "done" else "waiting"),
        ],
        "metrics": metrics,
    }


def numeric_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def progress_step(label: str, state: str, detail: str) -> dict[str, str]:
    icons = {"done": "✓", "running": "…", "failed": "!", "pending": "·"}
    return {"label": label, "state": state, "icon": icons.get(state, "·"), "detail": detail}


def discovery_detail(counters: dict[str, Any]) -> str:
    if counters["candidates_selected"] is not None:
        return f"{counters['candidates_selected']} selected"
    return "waiting"


def case_detail(counters: dict[str, Any], key: str) -> str:
    total = numeric_count(counters["total"])
    done = numeric_count(counters[key])
    if total:
        return f"{done}/{total}"
    return "waiting"


def render_job_panel(job: Any) -> str:
    result_html = job.result_html if job.status == "ok" else ""
    error_html = html.escape(job.error) if job.status == "failed" else ""
    error_hidden = "" if job.status == "failed" else " hidden"
    batch_progress_html = ""
    if getattr(job, "kind", "") == "batch":
        batch_progress_html = (
            "<div id=\"batch-progress-slot\">"
            f"{render_batch_progress_panel(getattr(job, 'batch_progress_path', None), job.status)}"
            "</div>"
        )
    progress_note = (
        "Статус обновляется по структурированным событиям batch progress."
        if getattr(job, "kind", "") == "batch"
        else "Обычно это занимает от нескольких секунд до пары минут."
    )
    if job.status == "ok":
        title = "Анализ завершён"
    elif job.status == "failed":
        title = "Анализ завершился с ошибкой"
    else:
        title = "Анализ выполняется"
    return (
        f"<section class=\"panel progress-card\" data-job-status-url=\"/jobs/{html.escape(job.job_id)}"
        "/status\" aria-live=\"polite\">"
        f"<div class=\"progress-head\"><span class=\"progress-title\">{title}</span>"
        f"<span id=\"job-stage\" class=\"progress-stage\">{html.escape(job.stage_label)}</span></div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\">"
        f"<span id=\"job-progress-fill\" class=\"progress-fill\" style=\"width:{job.progress}%\"></span>"
        "</div>"
        f"{batch_progress_html}"
        f"<p class=\"progress-note\">{progress_note}</p>"
        f"<div id=\"job-error-slot\" class=\"error-card\" role=\"alert\"{error_hidden}>{error_html}</div>"
        f"<div id=\"job-result-slot\">{result_html}</div>"
        "</section>"
    )


def render_result(result: Any) -> list[str]:
    from query_doctor_web_ui_report import render_result as _render_result

    return _render_result(result)


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
