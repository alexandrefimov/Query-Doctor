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
    assert "CM metrics profile" in body
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

    assert '<a class="nav-link" href="/demo">Demo guide</a>' in body
    assert '<a class="nav-link" href="/help">Help</a>' in body


def test_web_demo_guide_renders_curated_russian_demo_page():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_demo_guide_page(settings)

    assert '<a class="nav-link nav-link--active" href="/demo">Demo guide</a>' in body
    assert "<h1>Demo guide</h1>" in body
    assert body.count("<details open>") == 1
    assert "<details open>\n<summary>About this page</summary>" in body
    assert "<details>\n<summary>On this page</summary>" in body
    assert "дата-инженерам" in body
    assert "deterministic scoring" in body
    assert "Specific Query path" in body
    assert "staged case" in body
    assert "bounded CM time-series summaries включены по умолчанию" in body
    assert "Analyzer and metadata" in body
    assert "CM Metrics Correlation" in body
    assert "Details generation" in body
    assert "LLM Report prompt and validation" in body
    assert "Python-owned report contract digest" in body
    assert "Query LLM optimizer bullets and prompt" in body
    assert "rewrite_allowed" in body
    assert "recommendations_only" in body
    assert "Optimizer response validation and fallback" in body
    assert "trusted <code>no_rewrite</code> outcome with Python-owned bullets" in body
    assert "переписать запрос manually" in body
    assert "Profile signals" in body
    assert "Triage score" in body
    assert "Optimization candidates" in body
    assert "Candidate evaluation logic" in body
    assert 'href="#demo-candidate-evaluation"' in body
    assert "Query optimization evaluation" in body
    assert "Without shape evidence score is capped at <code>20</code>" in body
    assert "Stats refresh evaluation" in body
    assert "generic column-only gap caps at <code>65</code>" in body
    assert "Required confirmation всегда остается частью recommendation" in body
    assert "Read-only benchmark evidence" in body
    assert "246462725beeed0:506befef00000000" in body
    assert "CM 6.2.1 metrics compatibility smoke" in body
    assert "14/14" in body
    assert "cm_metrics_profile=cm6" in body
    assert "Optimized draft A" in body
    assert "904fb4e008edb2e1:435ee57d00000000" in body
    assert "Optimized draft B" in body
    assert "c84ac4eb1f578be7:7a5f8e0b00000000" in body
    assert "row_count=152" in body
    assert "3e8bf93ce7579564" in body
    assert "Local model benchmark run" in body
    assert 'href="#demo-local-model-benchmark"' in body
    assert "Local draft A cold" in body
    assert "9840956ed9a92bd0:56b5017f00000000" in body
    assert "Local draft B warm" in body
    assert "af4defc6ce5e610c:b4978b5900000000" in body
    assert "deafdcde158525b1" in body
    assert "RemoteScanRanges=0" in body
    assert "BytesReadRemoteUnexpected=0" in body
    assert "cold storage/cache path" in body
    assert "effective network/exchange bandwidth" in body
    assert "not proof of root cause" in body or "не доказанный root cause" in body
    assert "CPU/admission pressure was not observed" in body
    assert "Specific Query full-cycle follow-up" in body
    assert 'href="#demo-specific-followup"' in body
    assert "8d40bd516d7f45a9:4bbacbb900000000" in body
    assert "8742e82981df22d3:9d3f93b900000000" in body
    assert "Runtime улучшился, но Score не обязан падать." in body
    assert "Trusted не означает guaranteed extra speedup." in body
    assert "validation mode <code>strict_v2</code>" in body
    assert "host CPU pressure was not observed" in body
    assert "gpt55" not in body.lower()
    assert "Stats refresh candidates" in body
    assert "LLM boundaries" in body
    assert "Query LLM optimizer" in body
    assert "Trusted SQL draft" in body
    assert "Rejected unsafe draft" in body
    assert "Recommendations-only" in body
    assert "score = 55% impact + 45% query-shape opportunity" in body
    assert "Stats gap значит, что stats были root cause?" in body
    assert "Browser UI показывает safe summaries" in body
    assert "Это curated UI text, а не рендер документации из репозитория." in body
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
    assert "Сейчас реализован только Apache Impala" in captured["body"]


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
