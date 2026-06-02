from pathlib import Path

from web_server_test_support import load_web_module
from query_doctor.web.ui import layout


def compact_css(css: str) -> str:
    return "".join(css.split())


FORBIDDEN_HELP_STRINGS = (
    "profile.txt",
    "query.sql",
    "analysis_facts.md",
    "case_dir",
    "stdout",
    "stderr",
    "Ollama",
    "model:",
    "raw artifact",
    "local path",
)


def test_package_help_pages_are_available():
    from query_doctor.web.ui import help as help_ui

    assert callable(help_ui.render_help_page)
    assert callable(help_ui.render_demo_guide_page)


def test_web_help_page_renders_curated_static_help():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_help_page(settings)
    styles = layout.render_shared_styles()

    assert '<a class="nav-link nav-link--active" href="/help">Help</a>' in body
    assert '<section class="panel docs-panel help-panel"' in body
    assert 'class="report-body help-body"' in body
    assert "<h1>Help</h1>" in body
    assert "On this page" in body
    assert 'class="help-card-grid"' in body
    assert 'class="help-topic-stack"' in body
    assert '<details id="workflows" class="help-topic" open>' in body
    assert "Quick start" in body
    assert "Workflows" in body
    assert "Query Doctor is a local-first Big Data query diagnostics tool" in body
    assert "focused today on Apache Impala production triage" in body
    assert "The implemented production engine is Apache Impala." in body
    assert "validated raw-free reports" in body
    assert "Recent queries" in body
    assert "flagship production triage workflow" in body
    assert "Finished queries" in body
    assert "Known Query ID" in body
    assert (
        "Runtime context is collected automatically when the selected source supports it." in body
    )
    assert "Running now" in body
    assert "Query Optimizer" not in body
    assert "Specific Query" not in body
    assert "Known Query ID analysis" in body
    assert "Python Report" in body
    assert "LLM narrative" in body
    assert "Query LLM optimizer" in body
    assert "Recommended changes" in body
    assert "Diagnostics and evidence" in body
    assert 'href="/"' in body
    assert 'href="#quick-start"' in body
    assert 'href="#results-table"' in body
    assert 'id="details-actions"' in body
    assert 'id="github-docs"' in body
    assert 'href="#common-questions"' in body
    assert "GitHub documentation" in body
    assert "Project README" in body
    assert "Documentation index" in body
    assert "Safety contract" in body
    assert "Roadmap" in body
    assert "https://github.com/alexandrefimov/Query-Doctor/blob/main/docs/README.md" in body
    assert 'target="_blank" rel="noopener noreferrer"' in body
    compact_styles = compact_css(styles)
    assert (
        compact_css(
            ".report-body a{color:var(--accent-strong);font-weight:600;text-decoration:underline;"
        )
        in compact_styles
    )
    assert (
        compact_css(".report-body a:hover,.report-body a:focus{color:var(--accent);")
        in compact_styles
    )
    assert compact_css(".help-card-grid{display:grid;") in compact_styles
    assert compact_css(".help-topic>summary{display:flex;") in compact_styles
    assert (
        compact_css(".help-topic>summary::after,.help-topic-body>details>summary::after")
        in compact_styles
    )
    assert "Metadata" in body
    assert "Metadata allowlist" in body
    assert "Validated reports" in body
    assert "Common questions" in body
    assert "Future scope" in body
    assert "Web scans do not auto-run reports, LLM narratives, or optimizer drafts." in body
    assert "draft workflow placeholder" not in body
    assert "Metadata top cases" not in body
    assert "Queries to fetch metadata for" not in body
    assert "Main reason" not in body
    assert "Evidence count" not in body
    assert "Needs attention" in body
    assert "Worth reviewing" in body
    assert "More groups" in body
    assert "Rewrite opportunities" in body
    assert "Stats to check" in body
    assert "Good queries" not in body
    assert "Only queries with spills" in body
    assert "Cases without triage severity" in body
    assert "partial content stays untrusted and hidden" in body
    assert "Metadata collection is explicit, bounded, read-only, and allowlisted." in body
    assert "SHOW CREATE TABLE" in body
    assert "SHOW TABLE STATS" in body
    assert "SHOW COLUMN STATS" in body
    assert "StarRocks, Doris, ClickHouse, Dremio" in body
    assert "actively developed Big Data SQL, MPP analytical, and lakehouse runtimes" in body
    assert "Does the storage backend matter?" in body
    assert "small-file risk or planning pressure" in body
    assert not any("А" <= ch <= "я" or ch == "ё" or ch == "Ё" for ch in body)
    for forbidden in FORBIDDEN_HELP_STRINGS:
        assert forbidden not in body


def test_web_help_page_uses_python_only_copy_when_no_llm():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"), no_llm=True)

    body = module.render_help_page(settings)

    assert "Reports and optimizer" in body
    assert "Python Report" in body
    assert "LLM narrative" not in body
    assert "Query optimizer" in body
    assert "without LLM calls" in body
    assert "Web scans do not auto-run reports or optimizer jobs." in body
    assert "without automatic report or optimizer execution" in body
    assert "LLM Report" not in body
    assert "Query LLM optimizer" not in body
    assert "Details and LLM actions" not in body
    assert "Details and Python-only actions" not in body
    assert "mass LLM execution" not in body
    for forbidden in FORBIDDEN_HELP_STRINGS:
        assert forbidden not in body


def test_web_help_page_uses_configured_russian_language():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"), language="ru")

    body = module.render_help_page(settings)

    assert '<html lang="ru">' in body
    assert "<h1>Справка</h1>" in body
    assert "Быстрый старт" in body
    assert "Рабочие режимы" in body
    assert "Таблица результатов" in body
    assert "Граница безопасности" in body
    assert "Документация GitHub" in body
    assert "Big Data query diagnostics tool" in body
    assert "сфокусированный сегодня на Apache Impala production triage" in body
    assert "validated raw-free reports" in body
    assert "Детали Known Query ID" not in body
    assert "Python-отчет" in body
    assert "LLM narrative" in body
    assert "Реализованный production engine сейчас Apache Impala." in body
    assert "Browser UI намеренно скрывает raw query text" in body
    assert "Synthetic demo docs" in body
    assert "Почему metadata partial или skipped?" in body
    assert "Доказывает ли runtime metrics context root cause?" in body
    assert "Trino, Spark SQL, StarRocks, Doris, ClickHouse, Dremio" in body
    assert "small-file risk или planning pressure" in body
    assert "query-doctor-config" not in body
    for forbidden in FORBIDDEN_HELP_STRINGS:
        assert forbidden not in body


def test_web_navigation_includes_help_link():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings)

    assert '<a class="nav-link" href="/help">Help</a>' in body
    assert "Demo guide" not in body


def test_web_demo_guide_page_is_legacy_help_alias():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_demo_guide_page(settings)

    assert '<a class="nav-link nav-link--active" href="/help">Help</a>' in body
    assert '<a class="nav-link" href="/demo">Demo guide</a>' not in body
    assert "<h1>Help</h1>" in body
    assert "<h1>Demo guide</h1>" not in body
    assert "curated UI text for demonstrating Query Doctor" not in body
    assert "Workflows" in body
    assert "Reports and optimizer" in body
    assert "GitHub documentation" in body
    assert "gpt55" not in body.lower()
    assert not any("А" <= ch <= "я" or ch == "ё" or ch == "Ё" for ch in body)
    for forbidden in FORBIDDEN_HELP_STRINGS:
        assert forbidden not in body


def test_web_help_route_serves_help_without_running_analysis():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))
    handler = module.make_handler(settings, analysis_func=lambda *args, **kwargs: None)
    request = handler.__new__(handler)
    captured: dict[str, object] = {}

    def write_html(status, body):
        captured["status"] = status
        captured["body"] = body

    request.path = "/help"
    request.write_html = write_html

    request.do_GET()

    assert captured["status"] == 200
    assert "On this page" in captured["body"]
    assert "Quick start" in captured["body"]
    assert "Workflows" in captured["body"]
    assert "Big Data query diagnostics tool" in captured["body"]
    assert "focused today on Apache Impala production triage" in captured["body"]
    assert "The implemented production engine is Apache Impala." in captured["body"]
    assert "GitHub documentation" in captured["body"]
    assert "Common questions" in captured["body"]
    assert not any("А" <= ch <= "я" or ch == "ё" or ch == "Ё" for ch in captured["body"])


def test_web_demo_route_serves_help_alias_without_running_analysis():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))
    handler = module.make_handler(settings, analysis_func=lambda *args, **kwargs: None)
    request = handler.__new__(handler)
    captured: dict[str, object] = {}

    def write_html(status, body):
        captured["status"] = status
        captured["body"] = body

    request.path = "/demo"
    request.write_html = write_html

    request.do_GET()

    assert captured["status"] == 200
    assert "<h1>Help</h1>" in captured["body"]
    assert "Demo guide" not in captured["body"]
    assert "Workflows" in captured["body"]
    assert "Query LLM optimizer" in captured["body"]
