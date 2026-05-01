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
    assert "Local-first Impala query diagnostics" in body
    assert "Impala Doctor" not in body
    assert "demo-watermark" not in body
    assert "page-shell" not in body
    assert "run-panel" in body
    assert "Run diagnosis" in body
    assert '<label for="query_id">Query ID</label>' in body
    assert "Query ID or case path" not in body
    assert "Run local diagnosis for an Impala query identifier." in body
    assert "Saved case paths are supported by the CLI pipeline for now." in body
    assert "CM: unknown/not checked" in body
    assert "Kerberos: unknown/not checked" in body
    assert "Metadata collector: CLI only" in body
    assert ".hero-card:after" not in body
    assert "color-scheme:light" in body
    assert "--bg:#f7f8fa" in body
    assert "max-height:66vh" not in body
    assert "overflow-wrap:anywhere" in body
    assert "Интеллектуальный анализ Impala-запросов по Query ID" not in body
    assert "Mode" in body
    assert "Редактировать идентификаторы" not in body
    assert "Анализировать" not in body
    assert '<button class="run-button" type="submit">Run</button>' in body
    assert '<input type="radio" name="mode" value="user" checked>' in body
    assert '<input type="radio" name="mode" value="admin" checked>' not in body
    assert ".segmented label:focus-within" not in body
    assert body.index('id="query_id"') < body.index('<button class="run-button" type="submit">Run</button>')
    assert body.index('<button class="run-button" type="submit">Run</button>') < body.index('class="run-secondary-row"')
    assert body.index('class="segmented"') < body.index('class="mode-help"')
    assert "Локальный демо-сервер: только явный Query ID" not in body
    assert "Validated before render" in body
    assert "Analyzer-owned facts" in body
    assert "LLM writes wording only" in body
    assert "Local-first" in body
    assert "Safe by default" in body
    assert "Scope:" in body
    assert "current query only · referenced tables only · read-only metadata" in body
    assert "The latest validated diagnosis appears here after a run." in body
    assert "This MVP UI does not expose a separate reports list yet." in body
    assert "Проверяем Query ID" in body
    assert "Обычно это занимает от нескольких секунд до пары минут." in body


def test_web_render_page_can_select_admin_mode_explicitly():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings, report_mode="admin")

    assert '<input type="radio" name="mode" value="admin" checked>' in body
    assert '<input type="radio" name="mode" value="user" checked>' not in body


def test_web_home_page_links_brand_and_readme_navigation():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings)

    assert '<a class="brand" href="/" aria-label="Query Doctor home">' in body
    assert '<a class="nav-link nav-link--active" href="/">Run</a>' in body
    assert '<a class="nav-link" href="/readme">README</a>' in body
    assert "Settings" not in body
