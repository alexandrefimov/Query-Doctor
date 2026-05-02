from pathlib import Path

from web_server_test_support import load_web_module


def test_web_handler_renders_mocked_analysis_result_without_raw_html():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    def fake_analysis(query_id, report_mode, redact_identifiers, received_settings):
        assert query_id == "abc:def"
        assert report_mode == "user"
        assert redact_identifiers is True
        assert received_settings is settings
        return module.WebResult(
            query_id=query_id,
            case_dir=Path("/tmp/query-doctor-web/abc_def"),
            case_source="reused existing local case",
            report_mode=report_mode,
            parsed_operators="2",
            cardinality_anomalies="0",
            memory_anomalies="1",
            report_text="## Report\n<script>not raw html</script>",
        )

    status, body = module.handle_analyze_request(
        {
            "query_id": ["abc:def"],
            "mode": ["user"],
            "redact_identifiers": ["on"],
        },
        settings,
        analysis_func=fake_analysis,
    )

    assert status == 200
    assert "Impala query diagnosis" in body
    assert "Validated diagnosis markdown" in body
    assert "Case source" in body
    assert "reused existing local case" in body
    assert "Parsed operators" in body
    assert "<strong>2</strong>" in body
    assert 'class="panel report-card"' in body
    assert "<summary>Validated diagnosis markdown</summary>" in body
    assert '<h2 id="section-1">Report</h2>' in body
    assert "<pre>" not in body
    assert "<script>not raw html</script>" not in body
    assert "&lt;script&gt;not raw html&lt;/script&gt;" in body
    assert ".query-doctor-cm.local.json" not in body
    assert "Case path" not in body
    assert "case_dir" not in body
    assert "/tmp/query-doctor-web" not in body
    assert "abc_def" not in body
    assert "qwen3-coder:30b" not in body
    assert "Model" not in body


def test_web_report_markdown_renders_safe_html():
    module = load_web_module()

    rendered = module.render_report_markdown_html(
        "# Title\n\n"
        "Paragraph with `inline_code` and <b>unsafe</b>.\n\n"
        "- item one\n"
        "- item two\n\n"
        "> quoted\n\n"
        "| Col | Value |\n"
        "| --- | --- |\n"
        "| A | B |\n\n"
        "```sql\n"
        "SELECT <secret>;\n"
        "```\n"
    )

    assert "<h1>Title</h1>" in rendered
    assert "<p>Paragraph with <code>inline_code</code> and &lt;b&gt;unsafe&lt;/b&gt;.</p>" in rendered
    assert "<ul><li>item one</li><li>item two</li></ul>" in rendered
    assert "<blockquote>quoted</blockquote>" in rendered
    assert "<table>" in rendered
    assert "<th>Col</th>" in rendered
    assert "<td>B</td>" in rendered
    assert "SELECT &lt;secret&gt;;" in rendered
    assert "<b>unsafe</b>" not in rendered


def test_web_result_renders_collected_source():
    module = load_web_module()

    body = "\n".join(
        module.render_result(
            module.WebResult(
                query_id="abc:def",
                case_dir=Path("/tmp/query-doctor-web/abc_def"),
                case_source="collected now",
                report_mode="admin",
                parsed_operators="1",
                cardinality_anomalies="0",
                memory_anomalies="0",
                report_text="## Report\n",
            )
        )
    )

    assert "Case source" in body
    assert "collected now" in body
    assert "<details" in body
    assert "Validated diagnosis markdown" in body
    assert "/tmp/query-doctor-web" not in body
    assert "qwen3-coder:30b" not in body
    assert "Model" not in body


def test_web_result_renders_report_retry_notice():
    module = load_web_module()

    body = "\n".join(
        module.render_result(
            module.WebResult(
                query_id="abc:def",
                case_dir=Path("/tmp/query-doctor-web/abc_def"),
                case_source="reused existing local case",
                report_mode="admin",
                parsed_operators="1",
                cardinality_anomalies="0",
                memory_anomalies="0",
                report_text="## Report\n",
                report_retry=True,
            )
        )
    )

    assert "regenerated after validator retry" in body
    assert "/tmp/query-doctor-web" not in body
    assert "qwen3-coder:30b" not in body


def test_web_report_marks_analyzer_facts_as_deterministic_appendix(tmp_path):
    module = load_web_module()
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "analysis_facts.md").write_text("facts\n", encoding="utf-8")
    (case_dir / "diagnosis.md").write_text("report\n", encoding="utf-8")

    body = "\n".join(
        module.render_result(
            module.WebResult(
                query_id="abc:def",
                case_dir=case_dir,
                case_source="reused existing local case",
                report_mode="user",
                parsed_operators="1",
                cardinality_anomalies="0",
                memory_anomalies="0",
                report_text="## Короткий вывод\nok\n\n## Подробный разбор\nok\n\n## Факты анализатора\nfacts\n",
            )
        )
    )

    assert "deterministic appendix" in body
    assert "This section is not LLM-written narrative." in body
    assert '<a href="#section-1">Короткий вывод</a>' in body
    assert '<a href="#section-2">Подробный разбор</a>' in body
    assert '<a href="#section-3">Факты анализатора</a>' in body
    assert "analysis_facts.md" in body
    assert "diagnosis.md" in body
    assert str(case_dir) not in body
    assert "Case path" not in body
    assert "qwen3-coder:30b" not in body


def test_web_report_sidebar_only_marks_existing_artifacts_available(tmp_path):
    module = load_web_module()
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "analysis_facts.md").write_text("facts\n", encoding="utf-8")

    body = "\n".join(
        module.render_result(
            module.WebResult(
                query_id="abc:def",
                case_dir=case_dir,
                case_source="reused existing local case",
                report_mode="user",
                parsed_operators="1",
                cardinality_anomalies="0",
                memory_anomalies="0",
                report_text="## Report\n",
            )
        )
    )

    assert "Evidence completeness" in body
    assert "Analyzer facts<code>analysis_facts.md</code>" in body
    assert "Profile text<code>profile.txt</code>" not in body
    assert "<span>Profile</span><span class=\"badge gray\">not collected</span>" in body
    assert "<span>SQL</span><span class=\"badge gray\">not collected</span>" in body
    assert "<span>Host metrics</span><span class=\"badge gray\">not collected</span>" in body
    assert str(case_dir) not in body
    assert "case_dir" not in body
    assert "qwen3-coder:30b" not in body
