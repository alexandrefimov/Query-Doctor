from pathlib import Path

from web_server_test_support import load_web_module
from query_doctor.web.ui import layout
from query_doctor.web.ui.recent_scan_results import render_batch_summary


def compact_css(css: str) -> str:
    return "".join(css.split())


def assert_css_contains(styles: str, snippet: str) -> None:
    assert compact_css(snippet) in compact_css(styles)


def test_package_layout_renderers_are_available():
    from query_doctor.web.ui import layout

    assert layout.BRAND_MARK_SVG
    assert callable(layout.render_favicon_link)
    assert callable(layout.render_shared_styles)
    assert callable(layout.render_app_header)
    assert callable(layout.render_design_toggle)
    assert callable(layout.render_client_script)
    assert callable(layout.render_static_stylesheet_link)
    assert callable(layout.render_script_link)


def test_detail_job_polling_preserves_current_anchor():
    from query_doctor.web.ui import layout

    script = layout.render_client_script()

    assert "function detailJobRedirectTarget(progressElement)" in script
    assert "window.location.hash && target.indexOf('#') === -1" in script
    assert "new URL(redirectTarget, window.location.href).href === window.location.href" in script
    assert "window.location.reload()" in script


def test_detail_job_polling_applies_progress_view():
    from query_doctor.web.ui import layout

    script = layout.render_client_script()

    assert "function escapeHtml(value)" in script
    assert 'replace(/[&<>"\']/g' in script
    assert "function safeProgressStepState(value)" in script
    assert "function applyProgressView(progressElement, progressView, fallbackStage, fallbackProgress)" in script
    assert "progressElement.querySelector('.progress-stage')" in script
    assert "progressElement.querySelector('.progress-fill')" in script
    assert "progressElement.querySelector('.batch-progress-steps')" in script
    assert "batch-progress-step--' + stepState" in script
    assert "applyProgressView(progressElement, data.progress_view, data.stage, data.progress)" in script


def test_package_progress_renderers_are_available():
    from query_doctor.web.ui import progress

    assert progress.WEB_STAGES
    assert callable(progress.render_pending_progress_panel)
    assert callable(progress.render_job_panel)


def test_package_page_renderers_are_available():
    from query_doctor.web.ui import pages

    assert callable(pages.render_page)
    assert callable(pages.render_query_page)
    assert callable(pages.render_batch_page)
    assert callable(pages.render_batch_case_detail_page)
    assert callable(pages.render_error_panel)


def test_web_render_page_escapes_user_input():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings, query_id="<script>alert(1)</script>")

    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_web_render_page_contains_reference_local_ui_shell():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings)
    styles = layout.render_shared_styles()

    assert "impala-query-doctor" in body
    assert "Impala query performance diagnostics" in body
    assert "Impala Doctor" not in body
    assert "demo-watermark" not in body
    assert "page-shell" not in body
    assert "run-panel" in body
    assert "Known Query ID" in body
    assert "Analyze one explicit Impala query by Query ID." in body
    assert (
        "one explicit Query ID → profile collection or reuse → deterministic analyzer facts → automatic metadata"
        in body
    )
    assert '<label for="query_id">Query ID</label>' in body
    assert "Query ID or case path" not in body
    assert "Analyze one explicit Impala query with deterministic profile facts." not in body
    assert "Saved case paths are supported by the CLI pipeline for now." not in body
    assert "case path" not in body
    assert '<details class="info-popover"><summary aria-label="Query ID help">i</summary>' not in body
    assert "CM: unknown/not checked" not in body
    assert "Kerberos: unknown/not checked" not in body
    assert "Metadata collector: CLI only" not in body
    assert ".hero-card:after" not in body
    assert '<link rel="stylesheet" href="/static/app.css">' in body
    assert '<script src="/static/theme-bootstrap.js"></script>' in body
    assert '<script src="/static/app.js"></script>' in body
    assert "<style>" not in body
    assert "color-scheme:light" not in body
    assert "color-scheme:light" in styles
    assert "html[data-theme=dark]" in styles
    assert "--bg:#eef2f6" in styles
    assert "--bg:#0f1419" in styles
    assert_css_contains(styles, "html[data-design=command]{--bg:#eef4f1")
    assert_css_contains(styles, "html[data-theme=dark][data-design=command]{--bg:#101314")
    assert_css_contains(styles, "html[data-design=command] .page{max-width:1240px;padding:20px 28px 48px}")
    assert "html[data-design=classic]" not in styles
    assert "html[data-design=review]" not in styles
    assert "design-icon-review" not in styles
    assert "max-height:66vh" not in body
    assert "overflow-wrap:anywhere" in styles
    assert "Интеллектуальный анализ Impala-запросов по Query ID" not in body
    assert "Mode" not in body
    assert "Редактировать идентификаторы" not in body
    assert "Анализировать" not in body
    assert '<button class="run-button" type="submit">Run</button>' in body
    assert 'name="mode"' not in body
    assert '<input type="radio" name="mode" value="admin" checked>' not in body
    assert ".segmented label:focus-within" not in styles
    assert_css_contains(
        styles,
        ".segmented input:checked+span,.segmented input:checked+label{color:#fff;background:var(--accent);",
    )
    assert_css_contains(styles, ".segmented label{min-width:58px;display:grid;place-items:stretch;")
    assert_css_contains(styles, ".segmented span{display:grid;place-items:center;width:100%;height:100%;")
    assert_css_contains(styles, ".manual-inputs-hidden{display:none!important}")
    assert body.index('id="query_id"') < body.index('<button class="run-button" type="submit">Run</button>')
    assert "Локальный демо-сервер: только явный Query ID" not in body
    assert "Validated before render" not in body
    assert "Analyzer-owned facts" not in body
    assert "LLM writes wording only" not in body
    assert "Local-first" not in body
    assert "Safe by default" not in body
    assert "validated report · analyzer facts · local-first · safe by default" not in body
    assert "How Query ID diagnosis works" not in body
    assert "Validated reports from this session appear after a run." not in body
    assert "This MVP UI does not expose a separate reports list yet." not in body
    assert "Checking Query ID" not in body
    assert "This usually takes a few seconds to a couple of minutes." not in body


def test_web_render_page_sets_brand_favicon():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings)

    assert '<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,' in body
    assert "%3Cpath%20d%3D%22M5%2012h3l2-5%204%2010%202-5h3%22%2F%3E" in body
    assert body.index("<title>impala-query-doctor</title>") < body.index('rel="icon"')
    assert body.index('rel="icon"') < body.index('src="/static/theme-bootstrap.js"')
    assert body.index('src="/static/theme-bootstrap.js"') < body.index('href="/static/app.css"')


def test_web_render_page_contains_theme_toggle():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings)
    styles = layout.render_shared_styles()
    scripts = layout.read_static_asset_text("theme-bootstrap.js") + layout.render_client_script()

    assert 'id="theme-toggle"' in body
    assert 'aria-label="Switch to dark theme"' in body
    assert "query-doctor-theme" in scripts
    assert "prefers-color-scheme: dark" in scripts
    assert "Switch to light theme" in scripts
    assert_css_contains(
        styles,
        ".theme-toggle,.design-toggle{display:inline-grid;place-items:center;width:34px;"
        "height:34px;min-width:34px;flex:0 0 34px;border:1px solid var(--border-strong)",
    )
    assert_css_contains(styles, "background:var(--control);color:var(--accent-strong)")
    assert_css_contains(
        styles,
        "html[data-theme=dark] .theme-toggle,html[data-theme=dark] .design-toggle{"
        "border-color:var(--border-strong);background:var(--control);color:var(--accent-strong)",
    )
    assert_css_contains(styles, ".theme-toggle svg,.design-toggle svg{width:18px;height:18px}")
    assert_css_contains(
        styles,
        ".theme-toggle .theme-icon-light,"
        ".design-toggle .design-icon-serious,"
        ".design-toggle .design-icon-command{display:none}"
    )
    assert_css_contains(styles, ".theme-toggle .theme-icon-dark{display:block}")
    assert_css_contains(styles, "html[data-theme=dark] .theme-toggle .theme-icon-light{display:block}")
    assert_css_contains(styles, "html[data-theme=dark] .theme-toggle .theme-icon-dark{display:none}")


def test_web_render_page_contains_design_toggle():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings)
    styles = layout.render_shared_styles()
    scripts = layout.render_client_script()

    assert 'id="design-toggle"' in body
    assert 'aria-label="Switch to green design"' in body
    assert "query-doctor-design" in (layout.read_static_asset_text("theme-bootstrap.js") + scripts)
    assert "data-design" in (layout.read_static_asset_text("theme-bootstrap.js") + scripts)
    assert "['serious', 'command']" in (layout.read_static_asset_text("theme-bootstrap.js") + scripts)
    assert "document.documentElement.setAttribute('data-design', 'serious')" in layout.read_static_asset_text(
        "theme-bootstrap.js"
    )
    assert "Switch to blue design" in scripts
    assert "Switch to green design" in scripts
    assert_css_contains(
        styles,
        "html[data-design=serious] .design-toggle .design-icon-serious,"
        "html[data-design=command] .design-toggle .design-icon-command{display:block}"
    )
    assert "Switch to classic design" not in scripts
    assert "Switch to command design" not in scripts
    assert "Switch to review design" not in scripts
    assert "['serious', 'classic', 'command', 'review']" not in scripts
    assert "design-icon-classic" not in body
    assert "design-icon-review" not in body
    assert body.index('id="design-toggle"') < body.index('id="theme-toggle"')


def test_web_render_page_contains_optimizer_copy_handler():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings)
    script = layout.render_client_script()

    assert "data-copy-optimized-query" in script
    assert "data-optimized-query-block" in script
    assert "navigator.clipboard.writeText" in script
    assert "fallbackCopyCode" in script
    assert "Copy query" in script


def test_web_static_script_contains_csp_safe_row_navigation_handler():
    script = layout.render_client_script()

    assert "[data-href]" in script
    assert "rowNavigationTarget" in script
    assert "window.open(row.getAttribute('data-href'), '_blank', 'noopener')" in script
    assert "onclick=" not in script
    assert "onkeydown=" not in script


def test_recent_scan_default_empty_group_points_to_follow_up_tabs():
    body = render_batch_summary(
        {
            "selected_count": 1,
            "cases": [
                {
                    "case_index": 1,
                    "query_id": "abc:def",
                    "score": 5,
                    "score_severity": "suspicious",
                    "collection_status": "ok",
                    "analysis_status": "ok",
                    "metadata_status": "skipped",
                    "score_reasons": ["memory estimate anomalies: 1"],
                }
            ],
        }
    )

    assert "No bad queries were found in this scan." in body
    assert "Check Suspicious, Optimization candidates, or Stats refresh candidates" in body
    assert "Suspicious queries <span>1</span>" in body


def test_recent_scan_optimizer_ready_group_is_removed():
    body = render_batch_summary(
        {
            "selected_count": 1,
            "cases": [
                {
                    "case_index": 1,
                    "query_id": "abc:def",
                    "score": 5,
                    "score_severity": "suspicious",
                    "collection_status": "ok",
                    "analysis_status": "ok",
                    "metadata_status": "skipped",
                    "query_optimization_candidate": {
                        "tier": "medium",
                        "score": 3,
                        "impact": "medium",
                        "confidence": "medium",
                    },
                    "score_reasons": ["memory estimate anomalies: 1"],
                }
            ],
        },
        query_group="optimizer_ready",
    )

    assert "Optimizer-ready" not in body
    assert "No bad queries were found in this scan." in body
    assert "Optimization candidates <span>1</span>" in body


def test_web_render_page_omits_modes_even_when_report_mode_is_passed():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings, report_mode="admin")

    assert 'name="mode"' not in body
    assert '<input type="radio" name="mode" value="admin" checked>' not in body
    assert '<input type="radio" name="mode" value="user" checked>' not in body


def test_web_home_page_links_brand_and_readme_navigation():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings)

    assert '<a class="brand" href="/" aria-label="Query Doctor home">' in body
    assert '<a class="nav-link nav-link--active" href="/">Diagnose</a>' in body
    assert 'href="/optimizer">Query Optimizer</a>' not in body
    assert 'href="/query">Specific Query</a>' not in body
    assert 'href="/running">Running Queries</a>' not in body
    assert '<a class="nav-link" href="/help">Help</a>' in body
    assert "Demo guide" not in body
    assert body.index('href="/">Diagnose</a>') < body.index('href="/help">Help</a>')
    assert '<a class="nav-link" href="/readme">README</a>' not in body
    assert "Settings" not in body
