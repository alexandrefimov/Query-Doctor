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
    assert "Быстрый старт" in body
    assert "Query Doctor помогает разбирать поведение запросов Apache Impala." in body
    assert "Сейчас реализован только Apache Impala" in body
    assert "Finished Queries" in body
    assert "Specific Query" in body
    assert "Running Queries" in body
    assert "Query Optimizer" in body
    assert "Метаданные" in body
    assert "Проверенные отчеты" in body
    assert "FAQ" in body
    assert "Web scan не запускает LLM-отчеты автоматически." in body
    assert "не выполняет вставленный SQL" in body
    assert "не возвращает вставленный SQL обратно в браузер после submit" in body
    assert "не запускает LLM-отчеты автоматически" in body
    assert "Финальный отчет валидируется перед показом" in body
    assert "Metadata collection явная, ограниченная, read-only и allowlisted." in body
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
    assert "Быстрый старт" in captured["body"]
    assert "Сейчас реализован только Apache Impala" in captured["body"]
