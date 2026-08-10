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
    assert '<details id="workflows" class="help-topic">' in body
    assert "Quick start" in body
    assert "Workflows" in body
    assert "Query Doctor is a local-first Big Data query diagnostics tool" in body
    assert "focused on Apache Impala production triage" in body
    assert "with bounded local Trino production lanes" in body
    assert "The full production triage engine is Apache Impala." in body
    assert "Local Trino production support covers configured retained-list Recent diagnosis" in body
    assert (
        "raw-free materialized Details, deterministic Python Report, and optimizer guidance" in body
    )
    assert "trino_support_mode=beta" in body
    assert "production mode uses the same bounded local surface" in body
    assert "validated raw-free reports" in body
    assert "Recent queries" in body
    assert "flagship production triage workflow" in body
    assert "Finished queries" in body
    assert "Known Query ID" in body
    assert "Trino Recent and One Query ID" in body
    assert "one bounded retained pruned coordinator query list" in body
    assert "bounded pruned coordinator QueryInfo payloads for selected rows" in body
    assert (
        "Configured beta sources keep the Trino Beta labels in the Source cluster selector" in body
    )
    assert (
        "Engine control narrows that selector to Impala-capable sources or Trino-ready sources"
        in body
    )
    assert "Forged or stale Trino submits still fail closed before analysis" in body
    assert "It does not support Trino Running scans" in body
    assert "Python Report" in body
    assert "optimizer guidance" in body
    assert "LLM reports, Query Optimizer jobs, generated Trino SQL, or SQL execution" in body
    assert (
        "Runtime context is collected automatically when the selected source supports it." in body
    )
    assert "manual_profile_dir" in body
    assert "local profile inbox" in body
    assert "local/private <strong>Exported profile</strong> upload" in body
    assert "replacing <code>:</code> with <code>_</code>" in body
    assert "aaaaaaaaaaaaaaaa_0000000000000001.txt" in body
    assert "browser never renders the uploaded profile content" in body
    assert "Running now" in body
    assert 'href="/optimizer">Query Optimizer</a>' not in body
    assert "Run optimizer" not in body
    assert "Specific Query" not in body
    assert "Known Query ID analysis" in body
    assert "manual_profile_dir" in body
    assert "aaaaaaaaaaaaaaaa_0000000000000001.txt" in body
    assert "Python Report" in body
    assert "LLM narrative" in body
    assert "Query LLM optimizer" in body
    assert "Recommended change" in body
    assert "Diagnostics and evidence" in body
    assert 'href="/"' in body
    assert 'href="#workload-patterns"' in body
    assert "Workload patterns" in body
    assert "Workload follow-up" in body
    assert "Best Details case" in body
    assert "repeated fingerprint is not a root-cause claim by itself" in body
    assert 'href="/trino/compact-diagnosis"' not in body
    assert "Render direct or packaged raw-free boundary JSON, not product support." not in body
    assert 'href="#quick-start"' in body
    assert 'href="#results-table"' in body
    assert 'id="details-actions"' in body
    assert 'id="github-docs"' in body
    assert 'href="#common-questions"' in body
    assert "GitHub documentation" in body
    assert "Project README" in body
    assert "Documentation index" in body
    assert "Security model" in body
    assert "public security, privacy, and demo-sharing overview" in body
    assert "Safety contract" not in body
    assert "Roadmap" not in body
    assert "https://github.com/alexandrefimov/Query-Doctor/blob/main/docs/security-model.md" in body
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
    assert compact_css(".help-topic>summary::after{") in compact_styles
    assert ".help-topic-body>details" not in styles
    assert "Metadata" in body
    assert "Allowed metadata summaries" in body
    assert "Validated reports" in body
    assert "Common questions" in body
    assert "Where is future engine scope documented?" in body
    assert (
        "Recent and Running scans do not auto-run reports, LLM narratives, or optimizer drafts."
        in body
    )
    assert (
        "Trino is intentionally limited to configured retained-list Recent diagnosis, One Query ID, "
        "raw-free materialized Details, deterministic Python Report, and optimizer guidance."
        in body
    )
    assert "prepares the deterministic Python report in the same submit job" in body
    assert "draft workflow placeholder" not in body
    assert "Metadata top cases" not in body
    assert "Queries to fetch metadata for" not in body
    assert "Main reason" not in body
    assert "Evidence count" not in body
    assert "Needs attention" in body
    assert "Worth reviewing" in body
    assert "More filters" not in body
    assert "More scan options" not in body
    assert "Scan context" in body
    assert "repeated short workload patterns" in body
    assert "Rewrite opportunities" in body
    assert "Stats to check" in body
    assert "Good queries" not in body
    assert "Only queries with spills" in body
    assert "Cases without triage severity" in body
    assert "rejected partial content stays hidden" in body
    assert "Metadata collection is explicit, bounded, read-only, and allowlisted." in body
    assert "Table definition summary" in body
    assert "Table statistics summary" in body
    assert "Column statistics summary" in body
    assert "Future engine and storage scope lives in the public roadmap and support matrix" in body
    assert "StarRocks, Doris, ClickHouse, Dremio" not in body
    assert "Does the storage backend matter?" not in body
    assert "small-file risk or planning pressure" not in body
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
    assert "Recent and Running scans do not auto-run reports or optimizer jobs." in body
    assert "prepares the deterministic Python report in the same submit job" in body
    assert "Optimizer actions remain explicit." in body
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
    assert "Security model" in body
    assert "Big Data query diagnostics tool" in body
    assert "сфокусированный на Apache Impala production triage" in body
    assert "bounded local Trino production lanes" in body
    assert "validated raw-free reports" in body
    assert (
        "Local Trino production support покрывает configured retained-list Recent diagnosis" in body
    )
    assert "raw-free materialized Details, deterministic Python Report и optimizer guidance" in body
    assert "Trino Recent и One Query ID" in body
    assert "один bounded retained pruned coordinator query list" in body
    assert "bounded pruned coordinator QueryInfo payloads для выбранных rows" in body
    assert "Configured beta sources сохраняют Trino Beta labels в Source cluster selector" in body
    assert (
        "Engine control сужает selector до Impala-capable sources или Trino-ready sources" in body
    )
    assert "Forged или stale Trino submits все равно fail closed до analysis" in body
    assert "Trino не поддерживает Running scans" in body
    assert "Python Report" in body
    assert "optimizer guidance" in body
    assert "LLM reports, Query Optimizer jobs, generated Trino SQL или SQL execution" in body
    assert "Детали Known Query ID" not in body
    assert "manual_profile_dir" in body
    assert "local profile inbox" in body
    assert "local/private upload <strong>Exported profile</strong>" in body
    assert "замените <code>:</code> на <code>_</code>" in body
    assert "aaaaaaaaaaaaaaaa_0000000000000001.txt" in body
    assert "browser никогда не render uploaded profile content" in body
    assert "Python-отчет" in body
    assert "LLM narrative" in body
    assert 'href="#workload-patterns"' in body
    assert "Workload patterns" in body
    assert "Workload follow-up" in body
    assert "Best Details case" in body
    assert 'href="/trino/compact-diagnosis"' not in body
    assert "Рендерит direct или packaged raw-free boundary JSON, не product support." not in body
    assert "Полный production triage engine сейчас Apache Impala." in body
    assert "Browser UI намеренно скрывает raw query text" in body
    assert "Synthetic demo docs" in body
    assert "Почему metadata partial или skipped?" in body
    assert "Доказывает ли runtime metrics context root cause?" in body
    assert "Где описан future engine scope?" in body
    assert "Future engine и storage scope живут в roadmap и support matrix" in body
    assert (
        "Trino намеренно ограничен configured retained-list Recent diagnosis, One Query ID, "
        "raw-free materialized Details, deterministic Python Report и optimizer guidance." in body
    )
    assert "Trino, Spark SQL, StarRocks, Doris, ClickHouse, Dremio" not in body
    assert "small-file risk или planning pressure" not in body
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
    assert "focused on Apache Impala production triage" in captured["body"]
    assert "with bounded local Trino production lanes" in captured["body"]
    assert "The full production triage engine is Apache Impala." in captured["body"]
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
