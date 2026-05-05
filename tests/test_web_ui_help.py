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


def test_web_help_page_renders_curated_static_help():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_help_page(settings)

    assert '<a class="nav-link nav-link--active" href="/help">Help</a>' in body
    assert "<h1>Help</h1>" in body
    assert "On this page" in body
    assert "Workflows" in body
    assert "Query Doctor помогает разбирать поведение запросов Apache Impala." in body
    assert "Сейчас реализован только Apache Impala" in body
    assert "Finished Queries" in body
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
    assert "Метаданные" in body
    assert "Проверенные отчеты" in body
    assert "FAQ" in body
    assert "Web scan не запускает LLM-отчеты автоматически." in body
    assert "Сейчас это отдельная заготовка workflow" not in body
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
    assert "Кейсы без triage severity" in body
    assert "не выполняет вставленный SQL" in body
    assert "не возвращает вставленный SQL обратно в браузер после submit" in body
    assert "не запускает LLM-отчеты автоматически" in body
    assert "Финальный отчет валидируется перед показом" in body
    assert "partial output скрывается" in body
    assert (
        "Metadata collection явная, ограниченная, без выполнения пользовательского SQL и allowlisted."
        in body
    )
    assert "SHOW CREATE TABLE" in body
    assert "SHOW TABLE STATS" in body
    assert "SHOW COLUMN STATS" in body
    assert "Другие движки — planned possibilities, not implemented support." in body
    for forbidden in FORBIDDEN_HELP_STRINGS:
        assert forbidden not in body


def test_web_navigation_includes_help_link():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings)

    assert '<a class="nav-link" href="/help">Help</a>' in body


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
    assert "Сейчас реализован только Apache Impala" in captured["body"]
