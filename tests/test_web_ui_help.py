from pathlib import Path

from web_server_test_support import load_web_module
from query_doctor.web.ui import layout


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
    assert "<h1>Help</h1>" in body
    assert "On this page" in body
    assert "Quick start" in body
    assert "Workflows" in body
    assert "Query Doctor is a local-first Big Data Query Diagnostic Tool" in body
    assert "The implemented engine is Apache Impala only." in body
    assert "Recent queries" in body
    assert "Finished queries" in body
    assert "Known Query ID" in body
    assert "Collect CM metrics" in body
    assert "Running now" in body
    assert "Query Optimizer" not in body
    assert "Specific Query" not in body
    assert "Known Query ID analysis" in body
    assert "LLM Report" in body
    assert "Query LLM optimizer" in body
    assert "Findings" in body
    assert "Evidence details" in body
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
    assert ".report-body a{color:var(--accent-strong);font-weight:650;text-decoration:underline;" in styles
    assert ".report-body a:hover,.report-body a:focus{color:var(--accent);" in styles
    assert "Metadata" in body
    assert "Metadata allowlist" in body
    assert "Validated reports" in body
    assert "Common questions" in body
    assert "Future scope" in body
    assert "Web scans do not auto-run LLM reports or optimizer drafts." in body
    assert "draft workflow placeholder" not in body
    assert "Metadata top cases" not in body
    assert "Queries to fetch metadata for" not in body
    assert "Main reason" not in body
    assert "Evidence count" not in body
    assert "Bad queries" in body
    assert "Suspicious queries" in body
    assert "Optimization candidates" in body
    assert "Stats refresh candidates" in body
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
    assert "Details and LLM actions" in body
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
    assert "The implemented engine is Apache Impala only." in captured["body"]
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
