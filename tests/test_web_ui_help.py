from pathlib import Path

from web_server_test_support import load_web_module


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

    assert '<a class="nav-link nav-link--active" href="/help">Help</a>' in body
    assert "<h1>Help</h1>" in body
    assert "On this page" in body
    assert "Workflows" in body
    assert "Query Doctor is a local-first diagnostic tool for Apache Impala queries." in body
    assert "The implemented engine is Apache Impala only." in body
    assert "Finished Queries" in body
    assert "Collect CM metrics" in body
    assert "Specific Query" in body
    assert "Running Queries" in body
    assert "Query Optimizer" in body
    assert "Specific Query analysis" in body
    assert "LLM Report" in body
    assert "Query LLM optimizer" in body
    assert "Findings" in body
    assert "Evidence details" in body
    assert 'href="#results-table"' in body
    assert 'id="details-actions"' in body
    assert "Metadata" in body
    assert "Validated reports" in body
    assert "FAQ" in body
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
    assert "does not execute pasted SQL" in body
    assert "does not echo pasted SQL back into the browser after submit" in body
    assert "partial content stays untrusted and hidden" in body
    assert "Metadata collection is explicit, bounded, read-only, and allowlisted." in body
    assert "SHOW CREATE TABLE" in body
    assert "SHOW TABLE STATS" in body
    assert "SHOW COLUMN STATS" in body
    assert "Not yet. That needs a safe read-only collection contract" in body
    assert not any("А" <= ch <= "я" or ch == "ё" or ch == "Ё" for ch in body)
    for forbidden in FORBIDDEN_HELP_STRINGS:
        assert forbidden not in body


def test_web_navigation_includes_help_link():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings)

    assert '<a class="nav-link" href="/demo">Demo guide</a>' in body
    assert '<a class="nav-link" href="/help">Help</a>' in body


def test_web_demo_guide_renders_curated_english_demo_page():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_demo_guide_page(settings)

    assert '<a class="nav-link nav-link--active" href="/demo">Demo guide</a>' in body
    assert "<h1>Demo guide</h1>" in body
    assert body.count("<details open>") == 1
    assert "<details open>\n<summary>About this page</summary>" in body
    assert "<details>\n<summary>On this page</summary>" in body
    assert "curated UI text for demonstrating Query Doctor" in body
    assert "deterministic scoring" in body
    assert "Specific Query path" in body
    assert "bounded collection" in body
    assert "Analyzer" in body
    assert "CM metrics correlation" in body
    assert "LLM Report" in body
    assert "Query LLM optimizer" in body
    assert "recommendations-only" in body
    assert "Profile signals" in body
    assert "Triage score" in body
    assert "Optimization candidates" in body
    assert "Stats refresh candidates" in body
    assert "Stats refresh candidates answer a narrow question" in body
    assert "Required confirmation remains EXPLAIN comparison" in body
    assert "Trusted SQL draft" in body
    assert "Rejected unsafe draft" in body
    assert "Recommendations-only" in body
    assert "The optimizer trust chain is Python-owned" in body
    assert "analyzer selected the candidate and strategy" in body
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
    assert "Workflows" in captured["body"]
    assert "The implemented engine is Apache Impala only." in captured["body"]
    assert not any("А" <= ch <= "я" or ch == "ё" or ch == "Ё" for ch in captured["body"])


def test_web_demo_route_serves_demo_guide_without_running_analysis():
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
    assert "Demo guide" in captured["body"]
    assert "deterministic scoring" in captured["body"]
    assert "Query LLM optimizer" in captured["body"]
