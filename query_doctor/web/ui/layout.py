"""Shared HTML layout assets for the local Query Doctor web UI."""

from __future__ import annotations

from urllib.parse import quote


BRAND_MARK_SVG = (
    "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 24 24\" fill=\"none\" "
    "stroke=\"#0f5268\" stroke-width=\"1.8\" stroke-linecap=\"round\" "
    "stroke-linejoin=\"round\"><path d=\"M5 12h3l2-5 4 10 2-5h3\"/>"
    "<path d=\"M12 3v3M12 18v3M3 12h2M19 12h2\"/></svg>"
)


def render_favicon_link() -> str:
    return (
        "<link rel=\"icon\" type=\"image/svg+xml\" "
        f"href=\"data:image/svg+xml,{quote(BRAND_MARK_SVG, safe='')}\">"
    )


def render_shared_styles() -> str:
    return """
:root{color-scheme:light;--bg:#eef2f6;--panel:#fff;--panel-muted:#f5f7fa;--border:#cfd8e3;--border-strong:#b7c4d2;--text:#111827;--muted:#586574;--muted-2:#7a8796;--accent:#0f6f83;--accent-strong:#0b4f5e;--accent-soft:#e4f1f4;--green:#166534;--green-bg:#edf7f0;--amber:#92400e;--amber-bg:#fff4dc;--red:#991b1b;--red-bg:#fceeee;--gray:#4b5563;--gray-bg:#eef2f6;--shadow:0 1px 0 rgba(17,24,39,.04),0 8px 18px rgba(17,24,39,.045);--radius:4px;--mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace;--control:#fff;--strong:#1f2937;--focus-ring:rgba(15,111,131,.12);--brand-focus:rgba(15,111,131,.28);--active-shadow:inset 0 0 0 1px rgba(183,196,210,.78);--button-shadow:0 1px 0 rgba(17,24,39,.08);--elevated-shadow:0 14px 30px rgba(17,24,39,.16);--surface-shadow:0 1px 0 rgba(17,24,39,.045);--failed-row-bg:rgba(252,238,238,.68);--code-bg:#0f1720;--code-text:#e5edf5;--quote-text:#36505c;--sans:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
html[data-theme=dark]{color-scheme:dark;--bg:#0f1419;--panel:#151b22;--panel-muted:#1c242d;--border:#303b46;--border-strong:#465461;--text:#e8edf2;--muted:#a7b2bd;--muted-2:#8795a3;--accent:#5eb9cf;--accent-strong:#94d8e8;--accent-soft:#173846;--green:#8ed7a4;--green-bg:#173622;--amber:#f0bf74;--amber-bg:#3a2b12;--red:#f2a0a0;--red-bg:#3d1f22;--gray:#c0c9d2;--gray-bg:#26303a;--shadow:0 1px 0 rgba(255,255,255,.025),0 10px 26px rgba(0,0,0,.28);--control:#111820;--strong:#dce5ee;--focus-ring:rgba(94,185,207,.2);--brand-focus:rgba(94,185,207,.38);--active-shadow:inset 0 0 0 1px rgba(148,216,232,.24);--button-shadow:0 1px 0 rgba(255,255,255,.05);--elevated-shadow:0 14px 34px rgba(0,0,0,.42);--surface-shadow:0 1px 0 rgba(255,255,255,.025);--failed-row-bg:rgba(61,31,34,.42);--code-bg:#0a0f14;--code-text:#d7e2ec;--quote-text:#b8d1dc}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);font-family:var(--sans);line-height:1.42}a{color:inherit;text-decoration:none}fieldset{border:0;margin:0;padding:0}.page{max-width:1240px;margin:0 auto;padding:20px 28px 48px}.app-header{display:flex;align-items:center;justify-content:space-between;gap:22px;margin-bottom:16px;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--panel);box-shadow:var(--surface-shadow)}.brand{display:inline-flex;align-items:center;gap:10px;min-width:0}.brand:focus{outline:2px solid var(--brand-focus);outline-offset:4px;border-radius:6px}.brand-mark{width:32px;height:32px;display:grid;place-items:center;border:1px solid var(--accent-strong);border-radius:4px;background:var(--accent-strong);box-shadow:var(--surface-shadow);color:#fff;flex:0 0 auto}.brand-mark svg{width:21px;height:21px}.brand-title{display:block;font-weight:740;letter-spacing:0;font-size:16px;line-height:1.1}.brand-subtitle{display:block;margin-top:3px;color:var(--muted);font-size:12.5px}.header-actions{display:flex;align-items:center;gap:8px;min-width:0}.top-nav{display:flex;align-items:center;gap:2px;padding:2px;border:1px solid var(--border-strong);border-radius:4px;background:var(--panel-muted)}.nav-link{padding:6px 11px;border-radius:3px;color:var(--muted);font-size:12px;font-weight:720}.nav-link:hover,.nav-link:focus{color:var(--accent-strong);outline:none}.nav-link--active{color:var(--text);background:var(--control);box-shadow:var(--active-shadow)}.theme-toggle,.design-toggle{display:inline-grid;place-items:center;width:32px;height:32px;border:1px solid var(--border-strong);border-radius:4px;background:var(--control);color:var(--accent-strong);box-shadow:var(--button-shadow);cursor:pointer}.theme-toggle:hover,.theme-toggle:focus,.design-toggle:hover,.design-toggle:focus{color:var(--accent-strong);border-color:var(--accent-strong);outline:none;box-shadow:0 0 0 3px var(--focus-ring),var(--button-shadow)}html[data-theme=dark] .theme-toggle,html[data-theme=dark] .design-toggle{border-color:var(--border-strong);background:var(--control);color:var(--accent-strong);box-shadow:var(--button-shadow)}html[data-theme=dark] .theme-toggle:hover,html[data-theme=dark] .theme-toggle:focus,html[data-theme=dark] .design-toggle:hover,html[data-theme=dark] .design-toggle:focus{color:var(--text);border-color:var(--accent-strong);box-shadow:0 0 0 3px var(--focus-ring),var(--button-shadow)}.theme-toggle svg,.design-toggle svg{width:17px;height:17px}.theme-icon-light,.design-icon-classic{display:none}.theme-icon-dark,.design-icon-serious{display:block}html[data-theme=dark] .theme-icon-light{display:block}html[data-theme=dark] .theme-icon-dark{display:none}html[data-design=classic] .design-icon-classic{display:block}html[data-design=classic] .design-icon-serious{display:none}
.panel{border:1px solid var(--border);border-radius:var(--radius);background:var(--panel);box-shadow:var(--shadow)}.badge{display:inline-flex;align-items:center;justify-content:center;min-height:21px;padding:2px 7px;border-radius:4px;border:1px solid transparent;font-family:var(--mono);font-size:10.5px;font-weight:750;line-height:1;white-space:nowrap}.badge.green{color:var(--green);background:var(--green-bg);border-color:rgba(22,101,52,.16)}.badge.amber{color:var(--amber);background:var(--amber-bg);border-color:rgba(146,64,14,.16)}.badge.red{color:var(--red);background:var(--red-bg);border-color:rgba(153,27,27,.14)}.badge.gray{color:var(--gray);background:var(--gray-bg);border-color:rgba(75,85,99,.14)}.badge.blue{color:var(--accent-strong);background:var(--accent-soft);border-color:rgba(15,111,131,.18)}code,.technical,.mono{font-family:var(--mono);color:var(--text)}
.button,.run-button{display:inline-flex;align-items:center;justify-content:center;height:30px;padding:0 11px;border:1px solid var(--border-strong);border-radius:4px;background:var(--control);color:var(--muted);font-size:12px;font-weight:720;cursor:pointer}.button.primary,.run-button{border-color:var(--accent-strong);background:var(--accent);color:#fff;box-shadow:var(--button-shadow)}.button.danger{border-color:rgba(153,27,27,.28);background:var(--red-bg);color:var(--red)}.run-button{height:36px;min-width:88px;margin-top:24px;padding:0 16px;font-size:13px}.button[disabled],.run-button[disabled]{opacity:.62;cursor:wait}
.run-panel{padding:16px 18px 18px;margin-bottom:14px}.section-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:14px}.section-title{margin:0;font-size:17px;font-weight:760;letter-spacing:0}.section-kicker{margin-top:4px;color:var(--muted);font-size:12.5px}.readiness-line,.pipeline-line,.scope-line{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;padding:8px 10px;border:1px solid var(--border);border-radius:4px;background:var(--panel-muted);color:var(--muted);font-size:12px}.readiness-line{margin-bottom:13px}.readiness-label,.pipeline-line strong,.scope-line strong{color:var(--strong);font-weight:740}.status-token{display:inline-flex;align-items:center;gap:5px;padding:3px 7px;border:1px solid var(--border);border-radius:4px;background:var(--control);font-family:var(--mono);color:var(--muted)}
.optimizer-panel,.optimizer-result{padding:18px 20px 20px;margin-bottom:14px}.optimizer-form{display:grid;gap:13px}.optimizer-sql{min-height:220px;height:auto;resize:vertical;padding:12px;line-height:1.45}.optimizer-result h3{margin:0 0 8px;font-size:13px;color:var(--strong)}.optimizer-block{display:grid;gap:8px;margin-top:14px}.optimizer-block:first-of-type{margin-top:0}.optimizer-table-list{display:flex;flex-wrap:wrap;gap:7px;margin:0;padding:0;list-style:none}.optimizer-table-list li{display:inline-flex;align-items:center;gap:7px;padding:7px 8px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);font-size:12px}.optimizer-empty{color:var(--muted)}.optimizer-findings{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.optimizer-finding{display:grid;gap:5px}.optimizer-finding .badge{justify-self:start}
.run-form{display:grid;gap:12px}.run-main-row{display:grid;grid-template-columns:minmax(280px,1fr) auto;gap:12px;align-items:start}.field{display:grid;gap:6px;min-width:0}.field label,.mode-control>span{color:var(--strong);font-size:12px;font-weight:760}.label-row{display:flex;align-items:center;gap:6px;min-width:0}.label-row label{margin:0}.info-popover{position:relative;display:inline-block;vertical-align:middle;line-height:1}.info-popover>summary{display:inline-grid;place-items:center;width:17px;height:17px;padding:0;border:1px solid var(--border);border-radius:999px;background:var(--control);color:var(--muted);font-family:var(--mono);font-size:10.5px;font-weight:800;line-height:1;cursor:pointer;list-style:none}.info-popover>summary::-webkit-details-marker{display:none}.info-popover[open]>summary{background:var(--accent-soft);border-color:rgba(15,111,131,.24);color:var(--accent-strong)}.info-popover .info-body{position:absolute;z-index:20;left:0;top:23px;width:max-content;min-width:220px;max-width:min(460px,80vw);padding:8px 9px;border:1px solid var(--border-strong);border-radius:4px;background:var(--control);box-shadow:var(--elevated-shadow);color:var(--muted);font-size:11.5px;font-weight:500;line-height:1.35}.info-popover--inline .info-body{left:0;top:23px}.batch-form-grid .field:nth-child(3n) .info-popover .info-body{left:auto;right:0}.compact-details{border:1px solid var(--border);border-radius:4px;background:var(--control);overflow:hidden}.compact-details summary{cursor:pointer;padding:9px 11px;background:var(--panel-muted);color:var(--strong);font-size:13px;font-weight:720}.compact-details-body{padding:10px 12px;color:var(--muted);font-size:12px}.input{width:100%;height:36px;border:1px solid var(--border-strong);border-radius:4px;background:var(--control);color:var(--text);font-family:var(--mono);font-size:13px;padding:0 11px;outline:none}.input:focus{border-color:rgba(15,111,131,.65);box-shadow:0 0 0 3px var(--focus-ring)}.helper{color:var(--muted);font-size:12px}.run-secondary-row{display:block}.mode-control{display:inline-grid;gap:6px}.diagnosis-target-control{margin-bottom:13px}.segmented{display:inline-grid;grid-template-columns:repeat(2,1fr);gap:2px;height:32px;padding:2px;border:1px solid var(--border-strong);border-radius:4px;background:var(--panel-muted)}.segmented input{position:absolute;opacity:0;pointer-events:none}.segmented label{min-width:58px;display:grid;place-items:stretch;border-radius:3px;color:var(--muted);cursor:pointer;font-family:var(--mono);font-size:11.5px;font-weight:720;overflow:hidden}.segmented input:checked+span,.segmented input:checked+label{color:#fff;background:var(--accent);box-shadow:0 1px 1px rgba(17,24,39,.08)}.segmented span{display:grid;place-items:center;width:100%;height:100%;min-width:58px;border-radius:3px;padding:0 10px}.mode-help{display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin-top:7px;color:var(--muted);font-size:12px}.mode-help span{display:inline-flex;align-items:center;gap:6px;padding:5px 8px;border:1px solid var(--border);border-radius:4px;background:var(--panel-muted)}.manual-inputs-hidden{display:none!important}.batch-run-panel{padding:16px 18px 18px;margin-bottom:14px}.batch-form{display:grid;gap:12px}.batch-form .input{height:32px;padding:0 10px}.batch-form .run-button{height:32px;width:148px;max-width:100%;justify-self:start;margin-top:0;padding:0 14px;font-size:12.5px}.batch-form-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.batch-form-sections{display:grid;gap:10px}.batch-form-section{display:grid;gap:10px;margin:0;padding:10px;border:1px solid var(--border);border-radius:4px;background:var(--control)}.batch-form-section legend{padding:0 4px;color:var(--strong);font-size:11.5px;font-weight:780}.batch-actions{display:flex;justify-content:flex-end;padding-top:2px}.batch-primary-row{display:grid;grid-template-columns:minmax(180px,260px) auto;gap:12px;align-items:end}.batch-advanced{border:1px solid var(--border);border-radius:4px;background:var(--control);overflow:hidden}.batch-advanced>summary{cursor:pointer;padding:9px 11px;background:var(--panel-muted);color:var(--strong);font-size:12.5px;font-weight:740}.batch-advanced-body{display:grid;gap:10px;padding:10px}.batch-checkbox-row{display:flex;flex-wrap:wrap;align-items:center;gap:10px 16px;color:var(--strong);font-size:13px;font-weight:650}.batch-checkbox-row input{margin-right:6px}.trust-strip{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;margin:14px 0;padding:9px 12px;border:1px solid var(--border);border-radius:4px;background:var(--control);color:var(--muted);font-size:12px;font-weight:650;box-shadow:var(--surface-shadow)}.trust-item{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}.trust-icon{width:14px;height:14px;display:inline-grid;place-items:center;border-radius:999px;background:var(--accent-soft);color:var(--accent-strong);font-family:var(--mono);font-size:9px;line-height:1;flex:0 0 auto}.no-reports-note{padding:10px 12px;margin-bottom:14px;color:var(--muted);font-size:12px}.no-reports-note strong{display:block;margin-bottom:2px;color:var(--text);font-size:13px}
.error-card{border:1px solid rgba(153,27,27,.18);background:var(--red-bg);padding:12px 14px;color:var(--red);border-radius:7px;margin-bottom:14px}.error-card strong{display:block;margin-bottom:4px;color:var(--red)}.success-card{border:1px solid rgba(22,101,52,.18);background:var(--green-bg);padding:12px 14px;color:var(--green);border-radius:7px;margin-bottom:14px}.success-card strong{display:block;margin-bottom:4px;color:var(--green)}.progress-card{padding:13px 14px;margin-bottom:14px}#job-result-slot:not(:empty){margin-top:16px}.progress-card--hidden{display:none}.progress-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}.progress-title{font-weight:650}.progress-stage{color:var(--muted);font-size:.84rem}.progress-bar{height:6px;border-radius:999px;background:var(--gray-bg);border:1px solid var(--border);overflow:hidden}.progress-fill{display:block;height:100%;width:4%;background:var(--accent);transition:width .2s ease}.progress-note{margin:8px 0 0;color:var(--muted);font-size:.77rem}.batch-progress{margin-top:12px;display:grid;gap:10px}.batch-progress-steps{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:6px}.batch-progress-step{border:1px solid var(--border);border-radius:7px;background:var(--panel-muted);padding:8px;min-width:0}.batch-progress-step strong{display:block;font-size:11px;color:var(--text);overflow-wrap:anywhere;line-height:1.2}.batch-progress-step span{display:block;margin-top:3px;font-size:10.5px;color:var(--muted);overflow-wrap:anywhere;line-height:1.25}.batch-progress-step--done{border-color:rgba(22,101,52,.2);background:var(--green-bg)}.batch-progress-step--running{border-color:rgba(23,107,135,.22);background:var(--accent-soft)}.batch-progress-step--failed{border-color:rgba(153,27,27,.18);background:var(--red-bg)}.batch-progress-metrics{display:flex;flex-wrap:wrap;gap:7px;color:var(--muted);font-size:12px}.batch-progress-metrics span{border:1px solid var(--border);border-radius:999px;background:var(--control);padding:4px 8px}.report-progress{display:grid;gap:10px;margin-bottom:12px}.report-progress .batch-progress{margin-top:0}.report-progress .batch-progress-steps{grid-template-columns:repeat(4,minmax(0,1fr))}
.batch-panel{padding:16px 18px;overflow:hidden}.batch-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:14px}.batch-head h1{margin:0 0 4px;font-size:20px;line-height:1.2;letter-spacing:0}.batch-head p{margin:0;color:var(--muted);font-size:13px}.batch-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(108px,1fr));gap:8px;margin-bottom:12px}.batch-metric{display:grid;gap:4px;padding:8px 10px;border:1px solid var(--border);border-radius:4px;background:var(--panel-muted);min-width:0}.batch-metric span{color:var(--muted);font-size:10.5px;font-weight:760;text-transform:uppercase}.batch-metric strong{font-family:var(--mono);font-size:13px;overflow-wrap:anywhere}.batch-note{margin-bottom:12px;padding:9px 10px;border:1px solid var(--border);border-radius:4px;background:var(--panel-muted);color:var(--muted);font-size:12px}.batch-detail-grid{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}.batch-detail-grid span{display:inline-flex;align-items:center;min-height:25px;padding:4px 8px;border:1px solid var(--border);border-radius:4px;background:var(--panel-muted);color:var(--muted);font-size:11.5px}.batch-result-filters{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:8px;margin:0 0 12px}.batch-filter-tabs{display:flex;flex-wrap:wrap;gap:6px;margin:0}.batch-filter-link,.batch-spill-toggle{display:inline-flex;align-items:center;gap:7px;min-height:30px;padding:0 10px;border:1px solid var(--border-strong);border-radius:4px;background:var(--control);color:var(--muted);font-size:12px;font-weight:720}.batch-filter-link span{display:inline-grid;place-items:center;min-width:20px;height:20px;padding:0 6px;border-radius:999px;background:var(--panel-muted);font-family:var(--mono);font-size:10.5px;color:var(--text)}.batch-filter-link--active,.batch-spill-toggle--active{background:var(--accent-soft);border-color:rgba(15,111,131,.34);color:var(--accent-strong)}.batch-spill-check{display:inline-grid;place-items:center;width:14px;height:14px;border:1px solid var(--border-strong);border-radius:3px;background:var(--control);color:var(--accent-strong);font-size:11px;line-height:1}.case-overview{display:grid;gap:10px;margin-bottom:14px}.case-query-line{display:grid;gap:4px;padding:9px 10px;border:1px solid var(--border);border-radius:4px;background:var(--control);min-width:0}.case-query-line span,.case-overview-card span{color:var(--muted);font-size:10.5px;font-weight:760;text-transform:uppercase}.case-query-line strong{font-family:var(--mono);font-size:12px;white-space:nowrap;overflow-x:auto;overflow-y:hidden}.case-overview-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.case-overview-card{display:grid;gap:4px;padding:8px 10px;border:1px solid var(--border);border-radius:4px;background:var(--panel-muted);min-width:0}.case-overview-card strong{font-family:var(--mono);font-size:12px;overflow-wrap:anywhere}.case-summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:14px}.case-summary-card{display:grid;gap:4px;padding:8px 10px;border:1px solid var(--border);border-radius:4px;background:var(--panel-muted);min-width:0}.case-summary-card span{color:var(--muted);font-size:10.5px;font-weight:760;text-transform:uppercase}.case-summary-card strong{font-family:var(--mono);font-size:12px;overflow-wrap:anywhere}.reason-list{display:grid;gap:10px;margin:0;padding:0;list-style:none}.reason-card{border:1px solid var(--border);border-radius:4px;background:var(--control);padding:10px 11px}.reason-card strong{display:block;margin-bottom:3px;font-size:13px}.reason-card p{margin:0;color:var(--muted);font-size:12px}.technical-details{overflow:hidden}.metadata-statement-line{display:inline-flex;gap:8px;flex-wrap:wrap;font-family:var(--mono);font-size:12px}.batch-table-wrap{margin-top:14px;max-width:100%;overflow-x:auto;overflow-y:visible;border:1px solid var(--border);border-radius:4px}.batch-table{min-width:0;width:100%;table-layout:auto;border-collapse:collapse;font-size:12px;background:var(--control)}.batch-table th,.batch-table td{border-bottom:1px solid var(--border);padding:7px 9px;text-align:left;vertical-align:top}.batch-table th{position:sticky;top:0;background:var(--panel-muted);color:var(--strong);font-size:10.5px;text-transform:uppercase;letter-spacing:0;font-weight:780}.batch-row{cursor:pointer}.batch-row:hover,.batch-row:focus{background:var(--panel-muted);outline:none}.batch-row--failed{background:var(--failed-row-bg)}.batch-row--failed:hover,.batch-row--failed:focus{background:var(--red-bg)}.batch-cell--compact{width:1%;font-family:var(--mono);white-space:nowrap;overflow-wrap:normal}.batch-cell--query-id{width:1%;min-width:250px;font-family:var(--mono);font-size:11px;line-height:1.3;white-space:nowrap;overflow-wrap:normal}.batch-cell--user{width:1%;min-width:120px;max-width:180px;font-family:var(--mono);font-size:11px;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.batch-cell--summary{width:100%;min-width:320px;white-space:normal}.batch-cell--summary strong{display:block;margin-bottom:3px;color:var(--text);font-size:12px;overflow-wrap:anywhere}.batch-cell--summary span{display:block;color:var(--muted);font-size:11px;overflow-wrap:anywhere}.batch-cell--reason{min-width:220px;white-space:normal;overflow-wrap:anywhere}.batch-mini-badge{display:inline-flex;align-items:center;min-height:20px;padding:2px 7px;border-radius:4px;border:1px solid transparent;font-family:var(--mono);font-size:10.5px;font-weight:750;line-height:1;white-space:nowrap}.batch-severity--high,.batch-severity--failed,.batch-status--failed,.batch-report--untrusted{color:var(--red);background:var(--red-bg);border-color:rgba(153,27,27,.14)}.batch-severity--suspicious,.batch-status--warning,.batch-report--generated{color:var(--amber);background:var(--amber-bg);border-color:rgba(146,64,14,.16)}.batch-severity--clean,.batch-status--ok,.batch-report--passed{color:var(--green);background:var(--green-bg);border-color:rgba(22,101,52,.16)}.batch-status--neutral,.batch-report--neutral{color:var(--gray);background:var(--gray-bg);border-color:rgba(75,85,99,.14)}.empty-cell{color:var(--muted);text-align:center}
.runtime-diagnosis-summary{margin-top:12px}
.report-header{margin-bottom:14px;padding:18px 20px}.breadcrumb{display:flex;align-items:center;gap:8px;margin-bottom:12px;color:var(--muted);font-size:12px;font-weight:650}.report-title-row{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.report-title-row h1{margin:0 0 8px;font-size:20px;line-height:1.2;letter-spacing:-.03em}.report-subtitle{color:var(--muted);font-size:13px}.query-line{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px 10px;color:var(--muted);font-size:12px}.status-strip{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;padding:9px 10px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);color:var(--muted);font-size:12px;font-weight:650}.status-item{display:inline-flex;align-items:center;gap:6px}.dot{width:7px;height:7px;border-radius:999px;background:var(--green)}.dot.amber{background:#d97706}.dot.gray{background:#6b7280}.report-shell{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:14px;align-items:start}.content-main{display:grid;gap:14px}.report-card,.docs-panel{padding:0;overflow:hidden}.batch-panel>.docs-panel,#evidence-details{margin-top:14px}.analysis-details-body{padding:0}.detail-toc{display:flex;align-items:flex-start;flex-wrap:wrap;gap:10px 12px;margin:0 0 14px;padding:10px 12px;border:1px solid var(--border);border-radius:7px;background:var(--panel-muted)}.detail-toc-title{font-size:12px;font-weight:760;color:var(--strong)}.detail-toc-list{display:flex;flex-wrap:wrap;gap:7px}.detail-toc-link{display:inline-flex;align-items:center;min-height:27px;padding:4px 10px;border:1px solid var(--border);border-radius:999px;background:var(--control);color:var(--muted);font-size:11.5px;font-weight:650}.detail-toc-link:hover,.detail-toc-link:focus{border-color:var(--brand-focus);color:var(--accent-strong);outline:none}.analysis-subdetails{background:var(--control);border-top:1px solid var(--border);overflow:hidden}.analysis-subdetails:first-child{border-top:0}.report-card summary,.docs-panel h1,.docs-panel>summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 18px;margin:0;border-bottom:1px solid var(--border);background:var(--panel-muted);font-size:15px;font-weight:720}.docs-panel>summary,.analysis-subdetails>summary{cursor:pointer;list-style:none;font-weight:760}.docs-panel>summary::-webkit-details-marker,.analysis-subdetails>summary::-webkit-details-marker{display:none}.docs-panel>summary::after,.analysis-subdetails>summary::after,.report-card>summary::after,.report-body>details>summary::after{content:"";width:8px;height:8px;border:solid currentColor;border-width:0 2.2px 2.2px 0;transform:rotate(45deg);transition:transform .15s ease,filter .15s ease;flex:0 0 auto;filter:brightness(0.82)}.docs-panel[open]>summary::after,.analysis-subdetails[open]>summary::after,.report-card[open]>summary::after,.report-body>details[open]>summary::after{transform:rotate(225deg);filter:brightness(1)}.analysis-subdetails>summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 18px;background:var(--control);font-size:13px;font-weight:760}.analysis-subdetails[open]>summary{border-bottom:1px solid var(--border);background:var(--panel-muted)}.analysis-subdetails>.report-body{padding:14px 18px}.report-body{padding:16px 18px;color:var(--text);font-size:13px}.report-body a{color:var(--accent-strong);font-weight:650;text-decoration:underline;text-decoration-thickness:1.5px;text-underline-offset:2px}.report-body a:hover,.report-body a:focus{color:var(--accent);outline:2px solid var(--brand-focus);outline-offset:2px;border-radius:3px}.report-body>details{margin:10px 0;border:1px solid var(--border);border-radius:7px;background:var(--control);overflow:hidden}.report-body>details>summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 13px;background:var(--panel-muted);color:var(--strong);font-size:13px;font-weight:780;cursor:pointer;list-style:none}.report-body>details>summary::-webkit-details-marker{display:none}.report-body>details[open]>summary{border-bottom:1px solid var(--border)}.report-body>details>*:not(summary){margin-left:13px;margin-right:13px}.inline-report{margin-top:14px;padding-top:14px;border-top:1px solid var(--border)}.report-body h1,.report-body h2,.report-body h3,.report-body h4{margin:1.15em 0 .5em;line-height:1.2}.report-body h1:first-child,.report-body h2:first-child,.report-body h3:first-child{margin-top:0}.report-body h1{font-size:20px}.report-body h2{font-size:17px}.report-body h3{font-size:15px}.report-body p{margin:.7em 0}.report-body ul,.report-body ol{margin:.55em 0 .8em;padding-left:1.35rem}.report-body li{margin:.32em 0;overflow-wrap:anywhere}.report-body code{background:var(--panel-muted);border:1px solid var(--border);border-radius:5px;padding:.08rem .28rem;font-family:var(--mono);font-size:.88em;overflow-wrap:anywhere}.report-body pre{margin:.75em 0;padding:12px;background:var(--code-bg);color:var(--code-text);border:1px solid var(--border);border-radius:6px;white-space:pre-wrap;overflow-wrap:anywhere}.report-body pre code{border:0;background:transparent;padding:0;color:inherit}.report-body blockquote{margin:.75em 0;padding:.35em .8em;border-left:3px solid var(--accent);background:var(--accent-soft);color:var(--quote-text)}.report-body table{width:100%;border-collapse:collapse;margin:.8em 0;font-size:.86rem}.report-body th,.report-body td{border:1px solid var(--border);padding:6px 8px;text-align:left;vertical-align:top}.report-body th{background:var(--panel-muted);color:var(--strong)}.appendix-notice{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 12px;padding:10px 12px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);color:var(--muted);font-size:12px}.side-panel{position:sticky;top:18px;display:grid;gap:14px}.side-card{padding:14px}.side-card h2{margin:0 0 10px;font-size:14px}.meta-list{display:grid;gap:8px}.meta-row{display:flex;justify-content:space-between;gap:12px;padding-bottom:8px;border-bottom:1px solid var(--border);color:var(--muted);font-size:12px}.meta-row:last-child{padding-bottom:0;border-bottom:0}.meta-row strong{color:var(--text);font-family:var(--mono);font-size:11px;text-align:right}.artifact-list,.toc-list,.timeline{display:grid;gap:7px}.artifact-item,.toc-list a{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px 10px;padding:8px 9px;border:1px solid var(--border);border-radius:6px;background:var(--panel-muted);color:var(--muted);font-size:12px;font-weight:650}.artifact-item code{display:block;margin-top:2px;font-family:var(--mono);color:var(--text);font-size:11px}.toc-list a{display:block}.timeline-item{display:grid;grid-template-columns:16px 1fr;gap:8px;color:var(--muted);font-size:12px}.timeline-dot{width:8px;height:8px;margin-top:5px;border-radius:999px;background:var(--green)}.timeline-item strong{display:block;color:var(--text);font-size:12px}
.llm-action-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:12px}.llm-action-card{display:grid;gap:8px;align-content:start;padding:10px;border:1px solid var(--border);border-radius:7px;background:var(--panel-muted);min-width:0}.llm-action-card strong{font-size:12px;color:var(--strong)}.llm-action-card form,.llm-action-card .button{width:100%}.llm-action-card .button{height:auto;min-height:32px;text-align:center;white-space:normal}.llm-result-block{margin-top:14px;padding-top:14px;border-top:1px solid var(--border)}.llm-result-block h2{margin:0 0 10px;font-size:14px}.optimized-query-copy{display:grid;gap:8px}.optimized-query-tools{display:flex;justify-content:flex-end}.copy-query-button{height:28px}.detail-toc{align-items:center}.detail-toc-title{display:inline-flex;align-items:center;min-height:27px}
.case-overview-grid{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}.case-summary-grid{grid-template-columns:repeat(auto-fit,minmax(140px,1fr))}.llm-action-grid{grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
html[data-design=classic]{--bg:#f7f8fa;--panel:#fff;--panel-muted:#f8fafc;--border:#dce3eb;--border-strong:#c8d2df;--text:#17202a;--muted:#627184;--muted-2:#7b8794;--accent:#176b87;--accent-strong:#0f5268;--accent-soft:#e7f4f7;--gray-bg:#eef1f5;--shadow:0 1px 2px rgba(15,23,42,.04),0 3px 8px rgba(15,23,42,.03);--radius:7px;--strong:#303a46;--focus-ring:rgba(23,107,135,.1);--brand-focus:rgba(23,107,135,.28);--active-shadow:inset 0 0 0 1px rgba(200,210,223,.7);--button-shadow:0 4px 10px rgba(23,107,135,.14);--elevated-shadow:0 8px 22px rgba(15,23,42,.12);--surface-shadow:0 1px 2px rgba(15,23,42,.035)}
html[data-theme=dark][data-design=classic]{--bg:#101418;--panel:#171d23;--panel-muted:#202831;--border:#303b46;--border-strong:#455260;--text:#e8edf2;--muted:#a6b2bf;--muted-2:#8795a3;--accent:#50adc8;--accent-strong:#8cd4e6;--accent-soft:#173846;--gray-bg:#28313b;--shadow:0 1px 2px rgba(0,0,0,.35),0 10px 28px rgba(0,0,0,.24);--control:#12181e;--strong:#dce5ee;--focus-ring:rgba(80,173,200,.2);--brand-focus:rgba(80,173,200,.38);--active-shadow:inset 0 0 0 1px rgba(140,212,230,.22);--button-shadow:0 6px 14px rgba(0,0,0,.2);--elevated-shadow:0 12px 30px rgba(0,0,0,.38);--surface-shadow:0 1px 1px rgba(0,0,0,.28)}
html[data-design=classic] body{line-height:1.45}html[data-design=classic] .page{max-width:1180px;padding:22px 28px 48px}html[data-design=classic] .app-header{padding:0;border:0;border-radius:0;background:transparent;box-shadow:none;margin-bottom:22px}html[data-design=classic] .brand:focus{border-radius:8px}html[data-design=classic] .brand-mark{width:36px;height:36px;border:1px solid var(--border-strong);border-radius:6px;background:var(--control);color:var(--accent-strong)}html[data-design=classic] .brand-mark svg{width:23px;height:23px}html[data-design=classic] .brand-title{font-weight:720;letter-spacing:-.03em;font-size:17px}html[data-design=classic] .brand-subtitle{font-size:13px}html[data-design=classic] .top-nav{gap:5px;padding:4px;border:1px solid var(--border);border-radius:7px;background:var(--control)}html[data-design=classic] .nav-link{padding:7px 12px;border-radius:6px;font-size:13px;font-weight:600}html[data-design=classic] .nav-link--active{background:var(--panel-muted)}
html[data-design=classic] .theme-toggle,html[data-design=classic] .design-toggle{width:36px;height:36px;border:1px solid #455260;border-radius:7px;background:#12181e;color:#8cd4e6;box-shadow:0 6px 14px rgba(0,0,0,.16)}html[data-design=classic] .theme-toggle:hover,html[data-design=classic] .theme-toggle:focus,html[data-design=classic] .design-toggle:hover,html[data-design=classic] .design-toggle:focus{color:#e8edf2;border-color:#8cd4e6;box-shadow:0 0 0 3px rgba(80,173,200,.18),0 8px 18px rgba(0,0,0,.22)}html[data-theme=dark][data-design=classic] .theme-toggle,html[data-theme=dark][data-design=classic] .design-toggle{border-color:#c8d2df;background:#fff;color:#0f5268;box-shadow:0 4px 10px rgba(232,237,242,.12)}html[data-theme=dark][data-design=classic] .theme-toggle:hover,html[data-theme=dark][data-design=classic] .theme-toggle:focus,html[data-theme=dark][data-design=classic] .design-toggle:hover,html[data-theme=dark][data-design=classic] .design-toggle:focus{color:#17202a;border-color:#176b87;box-shadow:0 0 0 3px rgba(140,212,230,.22),0 6px 14px rgba(232,237,242,.14)}html[data-design=classic] .theme-toggle svg,html[data-design=classic] .design-toggle svg{width:18px;height:18px}
html[data-design=classic] .badge{min-height:22px;border-radius:5px}html[data-design=classic] .button,html[data-design=classic] .run-button{height:32px;border-radius:6px;font-weight:700}html[data-design=classic] .run-button{height:40px;margin-top:26px;padding:0 17px}html[data-design=classic] .run-panel,html[data-design=classic] .batch-run-panel{padding:18px 20px 20px}html[data-design=classic] .section-title{font-size:16px;font-weight:720;letter-spacing:-.01em}html[data-design=classic] .section-kicker{font-size:13px}html[data-design=classic] .readiness-line,html[data-design=classic] .pipeline-line,html[data-design=classic] .scope-line{border-radius:6px}html[data-design=classic] .readiness-label,html[data-design=classic] .pipeline-line strong,html[data-design=classic] .scope-line strong{font-weight:700}
html[data-design=classic] .run-form,html[data-design=classic] .batch-form{gap:13px}html[data-design=classic] .field{gap:7px}html[data-design=classic] .field label,html[data-design=classic] .mode-control>span{font-size:13px;font-weight:650}html[data-design=classic] .info-popover[open]>summary{border-color:rgba(23,107,135,.24)}html[data-design=classic] .info-popover .info-body,html[data-design=classic] .compact-details,html[data-design=classic] .batch-form-section,html[data-design=classic] .batch-advanced{border-radius:7px}html[data-design=classic] .input{height:40px;border-radius:6px;padding:0 12px}html[data-design=classic] .input:focus{border-color:rgba(23,107,135,.65)}html[data-design=classic] .segmented{height:34px;border-radius:6px}html[data-design=classic] .segmented label{border-radius:4px;font-weight:700}html[data-design=classic] .segmented span{border-radius:4px}html[data-design=classic] .batch-form .input{height:34px}html[data-design=classic] .batch-form .run-button{height:34px;width:160px}html[data-design=classic] .batch-form-grid{gap:12px}html[data-design=classic] .batch-form-sections{gap:12px}html[data-design=classic] .batch-form-section{gap:12px;padding:12px}html[data-design=classic] .batch-form-section legend{font-size:12px;font-weight:760}html[data-design=classic] .batch-advanced>summary{padding:10px 12px;font-size:13px;font-weight:720}html[data-design=classic] .batch-advanced-body{gap:12px;padding:12px}
html[data-design=classic] .batch-panel{padding:18px 20px}html[data-design=classic] .batch-head h1{letter-spacing:-.02em}html[data-design=classic] .batch-metric{padding:9px 10px;border-radius:6px}html[data-design=classic] .batch-metric span{font-size:11px;font-weight:650}html[data-design=classic] .batch-note{border-radius:6px}html[data-design=classic] .batch-detail-grid span{min-height:26px;border-radius:6px}html[data-design=classic] .batch-filter-link,html[data-design=classic] .batch-spill-toggle{min-height:32px;border-radius:6px}html[data-design=classic] .batch-filter-link--active,html[data-design=classic] .batch-spill-toggle--active{border-color:rgba(23,107,135,.32)}html[data-design=classic] .case-query-line,html[data-design=classic] .case-overview-card,html[data-design=classic] .case-summary-card{padding:9px 10px;border-radius:6px}html[data-design=classic] .case-query-line{padding:10px 11px}html[data-design=classic] .case-query-line span,html[data-design=classic] .case-overview-card span,html[data-design=classic] .case-summary-card span{font-size:11px;font-weight:650}html[data-design=classic] .reason-card{border-radius:7px}html[data-design=classic] .batch-table-wrap{border-radius:7px}html[data-design=classic] .batch-table th,html[data-design=classic] .batch-table td{padding:8px 9px}html[data-design=classic] .batch-table th{font-size:11px;font-weight:720}html[data-design=classic] .batch-mini-badge{border-radius:5px}
@media(max-width:980px){.report-shell{grid-template-columns:1fr}.side-panel{position:static}.batch-metrics,.case-summary-grid,.case-overview-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.batch-form-grid{grid-template-columns:repeat(2,minmax(120px,1fr))}.batch-progress-steps{grid-template-columns:repeat(3,minmax(0,1fr))}.optimizer-findings,.llm-action-grid{grid-template-columns:1fr}}@media(max-width:760px){.page{padding:18px 16px 40px;width:100%;max-width:100%;overflow-x:hidden}.app-header{align-items:stretch;flex-direction:column}.header-actions{align-items:flex-start;flex-wrap:wrap;width:100%}.top-nav{display:grid;grid-template-columns:1fr;width:calc(100vw - 32px);min-width:0}.nav-link{text-align:center;white-space:nowrap}.run-main-row,.batch-primary-row{grid-template-columns:1fr}.batch-form .run-button{width:100%}.run-secondary-row{align-items:stretch;flex-direction:column}.mode-control,.run-button{width:100%}.segmented{width:100%}.report-title-row{align-items:stretch;flex-direction:column}.batch-metrics,.batch-form-grid,.case-summary-grid,.case-overview-grid{grid-template-columns:1fr}.batch-progress-steps{grid-template-columns:1fr}}
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
        "<div class=\"header-actions\">"
        f"{render_top_nav(active)}"
        f"{render_design_toggle()}"
        f"{render_theme_toggle()}"
        "</div>"
        "</header>"
    )


def render_top_nav(active: str) -> str:
    batch_class = "nav-link nav-link--active" if active in {"batch", "running", "query"} else "nav-link"
    help_class = "nav-link nav-link--active" if active == "help" else "nav-link"
    return (
        "<nav class=\"top-nav\" aria-label=\"Main navigation\">"
        f"<a class=\"{batch_class}\" href=\"/\">Diagnose</a>"
        f"<a class=\"{help_class}\" href=\"/help\">Help</a>"
        "</nav>"
    )


def render_theme_toggle() -> str:
    return (
        "<button class=\"theme-toggle\" type=\"button\" id=\"theme-toggle\" aria-label=\"Switch to dark theme\" "
        "aria-pressed=\"false\" title=\"Toggle theme\">"
        "<svg class=\"theme-icon-light\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" "
        "stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\">"
        "<circle cx=\"12\" cy=\"12\" r=\"4\"/>"
        "<path d=\"M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41\"/>"
        "</svg>"
        "<svg class=\"theme-icon-dark\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" "
        "stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\">"
        "<path d=\"M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z\"/>"
        "</svg>"
        "</button>"
    )


def render_design_toggle() -> str:
    return (
        "<button class=\"design-toggle\" type=\"button\" id=\"design-toggle\" "
        "aria-label=\"Switch to classic design\" aria-pressed=\"false\" title=\"Switch to classic design\">"
        "<svg class=\"design-icon-serious\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" "
        "stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\">"
        "<rect x=\"4\" y=\"4\" width=\"16\" height=\"16\" rx=\"1\"/>"
        "<path d=\"M4 9h16M9 4v16\"/>"
        "</svg>"
        "<svg class=\"design-icon-classic\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" "
        "stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\">"
        "<rect x=\"4\" y=\"5\" width=\"16\" height=\"14\" rx=\"4\"/>"
        "<path d=\"M8 10h8M8 14h5\"/>"
        "</svg>"
        "</button>"
    )


def render_theme_bootstrap_script() -> str:
    return """<script>
(function () {
  try {
    var storedTheme = window.localStorage.getItem('query-doctor-theme');
    var systemTheme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    var theme = storedTheme === 'dark' || storedTheme === 'light' ? storedTheme : systemTheme;
    document.documentElement.setAttribute('data-theme', theme);
    var storedDesign = window.localStorage.getItem('query-doctor-design');
    var design = storedDesign === 'classic' ? 'classic' : 'serious';
    document.documentElement.setAttribute('data-design', design);
  } catch (error) {
    document.documentElement.setAttribute('data-theme', 'light');
    document.documentElement.setAttribute('data-design', 'serious');
  }
})();
</script>"""


def render_client_script() -> str:
    return """<script>
document.addEventListener('DOMContentLoaded', function () {
  function setTheme(theme) {
    var nextTheme = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', nextTheme);
    var toggle = document.getElementById('theme-toggle');
    if (toggle) {
      var dark = nextTheme === 'dark';
      toggle.setAttribute('aria-pressed', dark ? 'true' : 'false');
      toggle.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
      toggle.setAttribute('title', dark ? 'Switch to light theme' : 'Switch to dark theme');
    }
  }
  var themeToggle = document.getElementById('theme-toggle');
  if (themeToggle) {
    setTheme(document.documentElement.getAttribute('data-theme'));
    themeToggle.addEventListener('click', function () {
      var currentTheme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
      var nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
      setTheme(nextTheme);
      try {
        window.localStorage.setItem('query-doctor-theme', nextTheme);
      } catch (error) {
      }
    });
  }
  function setDesign(design) {
    var nextDesign = design === 'classic' ? 'classic' : 'serious';
    document.documentElement.setAttribute('data-design', nextDesign);
    var toggle = document.getElementById('design-toggle');
    if (toggle) {
      var classic = nextDesign === 'classic';
      toggle.setAttribute('aria-pressed', classic ? 'true' : 'false');
      toggle.setAttribute('aria-label', classic ? 'Switch to serious design' : 'Switch to classic design');
      toggle.setAttribute('title', classic ? 'Switch to serious design' : 'Switch to classic design');
    }
  }
  var designToggle = document.getElementById('design-toggle');
  if (designToggle) {
    setDesign(document.documentElement.getAttribute('data-design'));
    designToggle.addEventListener('click', function () {
      var currentDesign = document.documentElement.getAttribute('data-design') === 'classic' ? 'classic' : 'serious';
      var nextDesign = currentDesign === 'classic' ? 'serious' : 'classic';
      setDesign(nextDesign);
      try {
        window.localStorage.setItem('query-doctor-design', nextDesign);
      } catch (error) {
      }
    });
  }
  function setCopyButtonText(button, label, restore) {
    button.textContent = label;
    if (restore) {
      window.setTimeout(function () { button.textContent = 'Copy query'; }, 1400);
    }
  }
  document.addEventListener('click', function (event) {
    var copyButton = event.target.closest && event.target.closest('[data-copy-optimized-query]');
    if (!copyButton) {
      return;
    }
    event.preventDefault();
    var copyBlock = copyButton.closest('[data-optimized-query-block]');
    var code = copyBlock && copyBlock.querySelector('pre code');
    var text = code ? code.textContent : '';
    if (!text) {
      setCopyButtonText(copyButton, 'Nothing to copy', true);
      return;
    }
    function copied() {
      setCopyButtonText(copyButton, 'Copied', true);
    }
    function failed() {
      setCopyButtonText(copyButton, 'Copy failed', true);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(copied).catch(function () {
        fallbackCopyCode(code) ? copied() : failed();
      });
      return;
    }
    fallbackCopyCode(code) ? copied() : failed();
  });
  function fallbackCopyCode(code) {
    if (!document.createRange || !window.getSelection || !document.execCommand) {
      return false;
    }
    var selection = window.getSelection();
    var range = document.createRange();
    selection.removeAllRanges();
    range.selectNodeContents(code);
    selection.addRange(range);
    var ok = false;
    try {
      ok = document.execCommand('copy');
    } catch (error) {
      ok = false;
    }
    selection.removeAllRanges();
    return ok;
  }
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
  Array.prototype.slice.call(document.querySelectorAll('input[data-server-owned-default]')).forEach(function (input) {
    input.value = input.defaultValue || '';
  });
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
  function applyDiagnosisTarget(root) {
    var selected = root.querySelector('input[name="diagnosis_target"]:checked');
    var target = selected && selected.value === 'query' ? 'query' : 'recent';
    Array.prototype.slice.call(root.querySelectorAll('[data-diagnosis-target-field]')).forEach(function (element) {
      var visible = element.getAttribute('data-diagnosis-target-field') === target;
      element.classList.toggle('manual-inputs-hidden', !visible);
    });
  }
  Array.prototype.slice.call(document.querySelectorAll('[data-diagnosis-target-root]')).forEach(function (root) {
    applyDiagnosisTarget(root);
    Array.prototype.slice.call(root.querySelectorAll('input[name="diagnosis_target"]')).forEach(function (choice) {
      choice.addEventListener('change', function () { applyDiagnosisTarget(root); });
    });
  });
  function applyScanTarget(form) {
    var selector = form.querySelector('select[name="scan_target"]');
    if (!selector) {
      return;
    }
    var target = selector.value === 'running' ? 'running' : 'finished';
    form.setAttribute('action', target === 'running' ? '/running/run' : '/batch/run');
    Array.prototype.slice.call(form.querySelectorAll('[data-scan-target-field]')).forEach(function (element) {
      var visible = element.getAttribute('data-scan-target-field') === target;
      element.classList.toggle('manual-inputs-hidden', !visible);
    });
  }
  Array.prototype.slice.call(document.querySelectorAll('[data-scan-target-form]')).forEach(function (scanForm) {
    applyScanTarget(scanForm);
    var selector = scanForm.querySelector('select[name="scan_target"]');
    if (selector) {
      selector.addEventListener('change', function () { applyScanTarget(scanForm); });
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
  function detailJobRedirectTarget(progressElement) {
    var target = detailJobRedirectUrl(progressElement) || window.location.href;
    if (window.location.hash && target.indexOf('#') === -1) {
      target += window.location.hash;
    }
    return target;
  }
  function pollDetailJobProgress(progressElement) {
    var statusUrl = detailJobStatusUrl(progressElement);
    if (!statusUrl) {
      return;
    }
    fetch(statusUrl, {cache: 'no-store'})
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (data.status === 'ok' || data.status === 'failed' || data.status === 'cancelled') {
          var redirectTarget = detailJobRedirectTarget(progressElement);
          if (new URL(redirectTarget, window.location.href).href === window.location.href) {
            window.location.reload();
          } else {
            window.location.href = redirectTarget;
          }
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
        if (data.status === 'failed' || data.status === 'cancelled') {
          if (title) { title.textContent = data.status === 'cancelled' ? 'Analysis stopped' : 'Analysis failed'; }
          if ((data.kind === 'batch' || data.kind === 'running') && batchRunButton) {
            batchRunButton.disabled = false;
            batchRunButton.textContent = 'Run scan';
          }
          if (errorSlot) {
            errorSlot.hidden = false;
            errorSlot.textContent = data.error || (data.status === 'cancelled' ? 'Job stopped by user.' : 'Analysis failed.');
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
