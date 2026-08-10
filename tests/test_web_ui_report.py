from pathlib import Path

from web_server_test_support import load_web_module


def test_package_report_renderer_is_available():
    from query_doctor.web.ui import report

    assert callable(report.render_result)
    escaped = report.escape_report_value("qwen3-coder:30b")
    assert "qwen3-coder" not in escaped
    assert escaped


def test_web_handler_renders_mocked_analysis_result_without_raw_html():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    def fake_analysis(query_id, report_mode, redact_identifiers, received_settings):
        assert query_id == "abc:def"
        assert report_mode == "analysis"
        assert redact_identifiers is True
        assert received_settings is settings
        return module.WebQueryAnalysisResult(
            query_id=query_id,
            case={
                "query_id": "abc<script>:def",
                "score": 4,
                "duration_sec": 9.5,
                "collection_status": "ok",
                "analysis_status": "ok",
                "metadata_status": "skipped",
                "table_stats_status": "not_checked",
                "score_reasons": ["memory <script>not raw html</script>"],
                "memory_anomaly_count": 2,
                "report_generated": False,
                "report_validation_status": "not_run",
            },
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
    assert "Known Query ID analysis" in body
    assert "Deterministic analyzer result for one explicit Impala Query ID." in body
    assert "analysis only" not in body
    assert "This page does not render raw SQL" not in body
    assert "Validated diagnosis markdown" not in body
    assert "Case source" not in body
    assert 'class="panel report-card"' not in body
    assert "<pre>" not in body
    assert "<script>not raw html</script>" not in body
    assert "abc&lt;script&gt;:def" in body
    assert "not raw html" not in body
    assert ".query-doctor-cm.local.json" not in body
    assert "Case path" not in body
    assert "case_dir" not in body
    assert "/tmp/query-doctor-web" not in body
    assert "abc_def" not in body
    assert "analysis_facts.md" not in body
    assert "diagnosis.md" not in body
    assert "qwen3-coder:30b" not in body
    assert "Model" not in body


def test_web_report_markdown_renders_safe_html():
    module = load_web_module()
    from query_doctor.web.ui import markdown

    rendered = module.render_report_markdown_html(
        "# Title\n\n"
        "Paragraph with `inline_code` and <b>unsafe</b>.\n\n"
        "- item one\n"
        "- item two\n\n"
        "> quoted\n\n"
        "| Col | Value |\n"
        "| --- | --- |\n"
        "| A | B |\n\n"
        "<details>\n"
        "<summary>Admin <checks></summary>\n"
        "\n"
        "- hidden item\n"
        "\n"
        "</details>\n\n"
        "```sql\n"
        "SELECT <secret>;\n"
        "```\n"
    )

    assert "<h1>Title</h1>" in rendered
    assert (
        "<p>Paragraph with <code>inline_code</code> and &lt;b&gt;unsafe&lt;/b&gt;.</p>" in rendered
    )
    assert "<ul><li>item one</li><li>item two</li></ul>" in rendered
    assert "<blockquote>quoted</blockquote>" in rendered
    assert "<table>" in rendered
    assert "<th>Col</th>" in rendered
    assert "<td>B</td>" in rendered
    assert "<details>" in rendered
    assert "<summary>Admin &lt;checks&gt;</summary>" in rendered
    assert "<li>hidden item</li>" in rendered
    assert "SELECT &lt;secret&gt;;" in rendered
    assert "<b>unsafe</b>" not in rendered
    assert module.render_report_markdown_html is markdown.render_report_markdown_html


def test_details_inline_report_keeps_summary_open_and_appendix_collapsed():
    module = load_web_module()
    from query_doctor.web.ui import markdown

    rendered = module.render_details_inline_report_html(
        "# Query Doctor Report\n\n"
        "## Краткий вывод\n\n"
        "Safe summary.\n\n"
        "## Практические рекомендации\n\n"
        "- Safe action.\n\n"
        "## Подробный разбор\n\n"
        "Detailed evidence.\n\n"
        "### Follow-up checks\n\n"
        "- Follow-up check.\n"
    )

    summary_index = rendered.index("Safe summary.")
    recommendation_index = rendered.index("Safe action.")
    appendix_index = rendered.index("Detailed report and follow-up checks")
    assert summary_index < appendix_index
    assert recommendation_index < appendix_index
    assert (
        '<details class="analysis-subdetails report-appendix" aria-label="Report details">'
        in rendered
    )
    assert "<h1>" not in rendered
    assert "<h2>Query Doctor Report</h2>" in rendered[appendix_index:]
    assert "Detailed evidence." in rendered[appendix_index:]
    assert "Follow-up check." in rendered[appendix_index:]
    assert module.render_details_inline_report_html is markdown.render_details_inline_report_html


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
                report_text="## Краткий вывод\nok\n\n## Подробный разбор\nok\n\n## Факты анализатора\nfacts\n",
            )
        )
    )

    assert "deterministic appendix" in body
    assert "This section is not LLM-written narrative." in body
    assert '<a href="#section-1">Краткий вывод</a>' in body
    assert '<a href="#section-2">Подробный разбор</a>' in body
    assert '<a href="#section-3">Факты анализатора</a>' in body
    assert "Analyzer facts" in body
    assert "Diagnosis" in body
    assert "analysis_facts.md" not in body
    assert "diagnosis.md" not in body
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
    assert "Evidence categories" in body
    assert "Analyzer facts" in body
    assert "analysis_facts.md" not in body
    assert "Profile text<code>profile.txt</code>" not in body
    assert '<span>Profile</span><span class="badge gray">not collected</span>' in body
    assert '<span>SQL</span><span class="badge gray">not collected</span>' in body
    assert '<span>Host metrics</span><span class="badge gray">not collected</span>' in body
    assert str(case_dir) not in body
    assert "case_dir" not in body
    assert "qwen3-coder:30b" not in body
