from pathlib import Path

from web_server_test_support import load_web_module


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
    assert "Specific Query" in body
    assert "Analyze one explicit finished Impala query by Query ID." in body
    assert (
        "one Query ID → profile collection or reuse → deterministic analyzer facts → automatic metadata"
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
    assert '<a class="nav-link nav-link--active" href="/query">Specific Query</a>' in body
    assert '<a class="nav-link" href="/">Finished Queries</a>' in body
    assert '<a class="nav-link" href="/running">Running Queries</a>' in body
    assert '<a class="nav-link" href="/help">Help</a>' in body
    assert body.index('href="/">Finished Queries</a>') < body.index('href="/running">Running Queries</a>')
    assert body.index('href="/running">Running Queries</a>') < body.index('href="/query">Specific Query</a>')
    assert body.index('href="/query">Specific Query</a>') < body.index('href="/help">Help</a>')
    assert '<a class="nav-link" href="/readme">README</a>' not in body
    assert "Settings" not in body
