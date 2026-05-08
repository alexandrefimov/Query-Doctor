from pathlib import Path

from web_server_test_support import load_web_module
from query_doctor.web.ui.recent_scan_results import render_batch_summary


def test_package_layout_renderers_are_available():
    from query_doctor.web.ui import layout

    assert layout.BRAND_MARK_SVG
    assert callable(layout.render_favicon_link)
    assert callable(layout.render_shared_styles)
    assert callable(layout.render_app_header)
    assert callable(layout.render_client_script)


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
    assert "color-scheme:light" in body
    assert "html[data-theme=dark]" in body
    assert "--bg:#f7f8fa" in body
    assert "--bg:#101418" in body
    assert "max-height:66vh" not in body
    assert "overflow-wrap:anywhere" in body
    assert "Интеллектуальный анализ Impala-запросов по Query ID" not in body
    assert "Mode" not in body
    assert "Редактировать идентификаторы" not in body
    assert "Анализировать" not in body
    assert '<button class="run-button" type="submit">Run</button>' in body
    assert 'name="mode"' not in body
    assert '<input type="radio" name="mode" value="admin" checked>' not in body
    assert ".segmented label:focus-within" not in body
    assert ".segmented input:checked+span,.segmented input:checked+label{color:#fff;background:var(--accent);" in body
    assert ".segmented label{min-width:58px;display:grid;place-items:stretch;" in body
    assert ".segmented span{display:grid;place-items:center;width:100%;height:100%;" in body
    assert ".manual-inputs-hidden{display:none!important}" in body
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
    assert body.index('rel="icon"') < body.index("<style>")


def test_web_render_page_contains_theme_toggle():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings)

    assert 'id="theme-toggle"' in body
    assert 'aria-label="Switch to dark theme"' in body
    assert "query-doctor-theme" in body
    assert "prefers-color-scheme: dark" in body
    assert "Switch to light theme" in body
    assert ".theme-toggle{display:inline-grid;place-items:center;width:36px;height:36px;border:1px solid #455260" in body
    assert "background:#12181e;color:#8cd4e6" in body
    assert "html[data-theme=dark] .theme-toggle{border-color:#c8d2df;background:#fff;color:#0f5268" in body
    assert ".theme-icon-light{display:none}.theme-icon-dark{display:block}" in body
    assert "html[data-theme=dark] .theme-icon-light{display:block}" in body
    assert "html[data-theme=dark] .theme-icon-dark{display:none}" in body


def test_web_render_page_contains_optimizer_copy_handler():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings)

    assert "data-copy-optimized-query" in body
    assert "data-optimized-query-block" in body
    assert "navigator.clipboard.writeText" in body
    assert "fallbackCopyCode" in body
    assert "Copy query" in body


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


def test_recent_scan_optimizer_ready_empty_group_explains_explicit_action():
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

    assert "No optimizer-ready cases have a trusted draft or trusted recommendations yet." in body
    assert "run the Query LLM optimizer explicitly" in body
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
