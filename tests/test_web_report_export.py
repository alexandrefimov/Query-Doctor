import hashlib
import io
import json
from pathlib import Path

from query_doctor.web.app import make_handler
from query_doctor.web.case_files import expected_case_dir_for_query
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebSettings
from query_doctor.web.routes import (
    post_route_is_allowed,
    report_download_filename,
    route_get_request,
)
from query_doctor.web.command_builders import (
    PYTHON_REPORT_NAME,
    PYTHON_REPORT_VALIDATION_MARKER,
    REPORT_VARIANT_PYTHON,
    WEB_REPORT_MARKER_SCHEMA_VERSION,
    WEB_REPORT_VALIDATION_MODE,
)
from query_doctor.web.trusted_artifacts import write_batch_case_report_validation_marker
from scripts.audit_recent_details import audit_summary as audit_details_summary
from scripts.audit_recent_details import forbidden_browser_leaks


def web_settings(**kwargs) -> WebSettings:
    return WebSettings(config=Path(".query-doctor-cm.local.json"), **kwargs)


def write_report_case(case_dir: Path, report_text: str, *, trusted: bool = True) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "profile_digest.md").write_text("PROFILE\n", encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")
    (case_dir / PYTHON_REPORT_NAME).write_text(report_text, encoding="utf-8")
    if trusted:
        write_batch_case_report_validation_marker(case_dir, report_variant=REPORT_VARIANT_PYTHON)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_python_report_marker_for_path(case_dir: Path, report_path: Path) -> None:
    marker = {
        "facts_sha256": sha256_file(case_dir / "analysis_facts.md"),
        "report": PYTHON_REPORT_NAME,
        "report_sha256": sha256_file(report_path),
        "report_variant": REPORT_VARIANT_PYTHON,
        "schema_version": WEB_REPORT_MARKER_SCHEMA_VERSION,
        "source": "test marker for route boundary",
        "validated": True,
        "validation_mode": WEB_REPORT_VALIDATION_MODE,
    }
    (case_dir / PYTHON_REPORT_VALIDATION_MARKER).write_text(
        json.dumps(marker, sort_keys=True), encoding="utf-8"
    )


def write_stats_metadata_analysis_facts(case_dir: Path) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "profile_digest.md").write_text("PROFILE\n", encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text(
        "# Query Doctor Analysis Facts\n\n"
        "## Table Metadata Context\n"
        "- Table metadata facts: available\n"
        "- Tables requested: 1\n"
        "- Read-only statements only: yes\n\n"
        "### Table: analytics.fact_orders\n"
        "- Object type: table\n"
        "- SHOW CREATE TABLE status: ok\n"
        "- SHOW TABLE STATS status: ok\n"
        "- SHOW COLUMN STATS status: ok\n"
        "- Table stats row-count completeness: partial\n"
        "- Partition count: 10\n"
        "- Partitions with known row count: 6\n"
        "- Partitions with unknown row count: 4\n"
        "- Partitions with zero row count: 1\n"
        "- Column stats columns observed: 4\n"
        "- Column stats missing/unknown markers: 2\n"
        "- Column stats completeness: incomplete\n"
        "- Column stats complete columns: 2\n"
        "- Column stats NDV-missing columns: 1\n"
        "- Column stats size-missing columns: 1\n"
        "- Column stats all-missing columns: 0\n"
        "- File format: parquet\n"
        "- Storage family: hdfs\n"
        "- Storage scheme: hdfs\n"
        "- Partition columns: order_date\n\n"
        "## Stats Metadata Quality\n"
        "- status: available\n"
        "- table_stats: partial\n"
        "- column_stats: incomplete\n"
        "- partition_coverage: limited\n"
        "- partition_count: 10\n"
        "- partitions_with_known_row_count: 6\n"
        "- partitions_with_unknown_row_count: 4\n"
        "- join_filter_column_relevance: observed\n"
        "- join_filter_columns_observed: 4\n"
        "- join_filter_columns_with_complete_stats: 2\n"
        "- join_filter_columns_without_stats: 2\n"
        "- stats_context: stats_gap_with_row_estimate_evidence\n"
        "- interpretation: Stats gaps align with estimate-mismatch evidence.\n"
        "- guardrail: Stats quality is follow-up evidence, not a standalone root cause.\n\n"
        "## Ignored Raw Input\n"
        "- raw profile sentinel: ROUTE_STATS_RAW_SENTINEL\n",
        encoding="utf-8",
    )


def write_batch_summary(summary_path: Path, case_dir: Path, *, query_id: str = "abc:def") -> None:
    summary_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_index": 1,
                        "query_id": query_id,
                        "score": 30,
                        "score_reasons": ["memory estimate anomalies: 1"],
                        "case_dir": str(case_dir),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def write_mixed_signal_batch_summary(
    summary_path: Path, case_dir: Path, *, query_id: str = "abc:def"
) -> None:
    summary_path.write_text(
        json.dumps(
            {
                "selected_count": 1,
                "summaries_inspected": 1,
                "query_profile_source": "impala",
                "cases": [
                    {
                        "case_index": 1,
                        "query_id": query_id,
                        "score": 38,
                        "score_severity": "high",
                        "score_reasons": ["table stats row-count completeness is partial"],
                        "collection_status": "ok",
                        "analysis_status": "ok",
                        "metadata_status": "collected",
                        "referenced_table_count": 1,
                        "collected_metadata_table_count": 1,
                        "too_large_count": 0,
                        "table_stats_status": "partial",
                        "report_validation_status": "validated",
                        "duration_sec": 42.0,
                        "case_dir": str(case_dir),
                        "case_primary_bottleneck": {
                            "label": "stats",
                            "confidence": "high",
                            "reasons": ["bounded metadata facts support a stats follow-up"],
                        },
                        "stats_optimization_candidate": {
                            "tier": "high",
                            "score": 82,
                            "confidence": "medium",
                            "impact": "medium",
                            "need_type": "table_and_column_stats",
                            "speed_benefit": "medium",
                            "summary": "stats evidence",
                            "review_areas": "table/partition row counts and join/filter column stats",
                            "suggested_review_areas": [
                                "table/partition row counts",
                                "join/filter column statistics",
                            ],
                            "required_confirmation": [
                                "compare EXPLAIN before and after stats collection",
                                "rerun under comparable load",
                            ],
                            "evidence_detail": [
                                "partition row-count coverage partial: 6/10 known, 4 unknown",
                                (
                                    "join/filter column stats coverage partial: "
                                    "2/4 complete, 2 missing or incomplete"
                                ),
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def write_no_recipe_optimizer_batch_summary(
    summary_path: Path, case_dir: Path, *, query_id: str = "abc:def"
) -> None:
    workload_fingerprint = "wf_aaaaaaaaaaaaaaaaaaaaaaaa"
    summary_path.write_text(
        json.dumps(
            {
                "selected_count": 1,
                "summaries_inspected": 1,
                "query_profile_source": "impala",
                "cases": [
                    {
                        "case_index": 1,
                        "query_id": query_id,
                        "score": 42,
                        "score_severity": "high",
                        "score_reasons": ["large exchange volume before downstream processing"],
                        "collection_status": "ok",
                        "analysis_status": "ok",
                        "metadata_status": "collected",
                        "report_validation_status": "not_run",
                        "duration_sec": 58.0,
                        "case_dir": str(case_dir),
                        "group_fingerprint": workload_fingerprint,
                        "workload_fingerprint": workload_fingerprint,
                        "workload_group_member_count": 3,
                        "workload_group_duration_sec_p95": 61.0,
                        "case_primary_bottleneck": {
                            "label": "sql_shape",
                            "confidence": "medium",
                            "reasons": ["query-shape candidate from deterministic facts"],
                        },
                        "query_optimization_candidate": {
                            "tier": "high",
                            "score": 78,
                            "confidence": "medium",
                            "impact": "high",
                            "reasons": ["large exchange volume before downstream processing"],
                            "suggested_review_areas": ["exchange payload"],
                        },
                        "optimizer_rewrite_support": {
                            "status": "guidance_only",
                            "label": "Guidance only",
                            "reason": "No Python-owned SQL rewrite recipe is available",
                            "rewriteability_bucket": "not_rewriteable",
                            "rewriteability_label": "Not rewriteable",
                            "draft_eligibility": "no_recipe",
                            "no_recipe_review_track": "single_relation_filter_review",
                            "risk_mode": "low_risk_review",
                        },
                    }
                ],
                "workload_groups": {
                    "schema_version": 1,
                    "groups": [
                        {
                            "fingerprint": workload_fingerprint,
                            "aggregates": {
                                "count": 3,
                                "member_count": 3,
                                "duration_sec_p95": 61.0,
                                "primary_bottleneck_top": "sql_shape",
                                "score_top": "high",
                            },
                            "baseline": {
                                "schema_version": 1,
                                "regression": "strong",
                                "sample_count": 3,
                                "duration_sec_p95": 30.0,
                            },
                            "member_count": 3,
                            "member_case_ids": ["case-001", "case-002", "case-003"],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )


def dispatch_get(
    settings: WebSettings, store: WebJobStore, path: str
) -> tuple[int, dict[str, str], bytes]:
    handler = make_handler(settings, job_store=store, analysis_func=lambda *args, **kwargs: None)
    request = handler.__new__(handler)
    captured: dict[str, object] = {"headers": []}
    request.path = path
    request.headers = {"Host": "localhost:8765"}
    request.send_response = lambda status: captured.__setitem__("status", status)
    request.send_header = lambda name, value: captured["headers"].append((name, value))
    request.end_headers = lambda: None
    request.wfile = io.BytesIO()

    request.do_GET()

    return captured["status"], dict(captured["headers"]), request.wfile.getvalue()


def test_trusted_batch_report_download_returns_markdown_headers_and_redacted_body(tmp_path):
    case_dir = tmp_path / "cases" / "case-001" / "abc"
    sibling_path = "/tmp/query-doctor-sibling-case/diagnosis.md"
    user_path = "/Users/example/query-doctor/leak.md"
    write_report_case(
        case_dir,
        f"# Report\n\nValidated body with {case_dir} hidden.\n{sibling_path}\n{user_path}\n",
    )
    summary = tmp_path / "batch_summary.json"
    write_batch_summary(summary, case_dir)
    settings = web_settings(batch_summary=summary)

    status, headers, body = dispatch_get(settings, WebJobStore(), "/batch/case/case-001/report.md")

    assert status == 200
    assert headers["Content-Type"] == "text/markdown; charset=utf-8"
    assert (
        headers["Content-Disposition"] == 'attachment; filename="query-doctor-report-case-001.md"'
    )
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "same-origin"
    assert int(headers["Content-Length"]) == len(body)
    text = body.decode("utf-8")
    assert "Validated body with [local case path hidden] hidden." in text
    assert str(case_dir) not in text
    assert sibling_path not in text
    assert user_path not in text

    inline = route_get_request("/batch/case/case-001/report", settings, WebJobStore())
    assert inline is not None
    assert inline.status == 200
    assert "Validated Finished Queries case report" in inline.body
    assert "Validated body with [local case path hidden] hidden." in inline.body
    assert str(case_dir) not in inline.body
    assert sibling_path not in inline.body
    assert user_path not in inline.body


def test_trusted_batch_report_download_redacts_runtime_internals_and_model_markers(
    tmp_path,
):
    case_dir = tmp_path / "cases" / "case-001" / "abc"
    write_report_case(
        case_dir,
        (
            "# Report\n\n"
            "Validated narrative.\n"
            "Model qwen3-coder:30b wrote optimized_query.sql.\n"
            "Collector raw stdout exposed profile_digest.md and raw stderr.\n"
            "Metadata probe SHOW CREATE TABLE guarded_db.secret_table.\n"
            "Raw SQL SELECT secret_col FROM guarded_db.secret_table WHERE ds = 20260603.\n"
            "Runtime field case_dir and metadata_coordinator should not be visible.\n"
        ),
    )
    summary = tmp_path / "batch_summary.json"
    write_batch_summary(summary, case_dir)
    settings = web_settings(batch_summary=summary)

    status, _headers, body = dispatch_get(settings, WebJobStore(), "/batch/case/case-001/report.md")
    inline = route_get_request("/batch/case/case-001/report", settings, WebJobStore())

    assert status == 200
    assert inline is not None
    assert inline.status == 200
    for text in (body.decode("utf-8"), inline.body):
        assert "Validated narrative." in text
        assert "[model setting hidden]" in text
        assert "[artifact name hidden]" in text
        assert "[subprocess output hidden]" in text
        assert "[SQL hidden]" in text
        assert "[hidden field]" in text
        assert "qwen3-coder" not in text
        assert "optimized_query.sql" not in text
        assert "raw stdout" not in text
        assert "raw stderr" not in text
        assert "profile_digest.md" not in text
        assert "SHOW CREATE TABLE" not in text
        assert "SELECT secret_col" not in text
        assert "guarded_db.secret_table" not in text
        assert "case_dir" not in text
        assert "metadata_coordinator" not in text
        assert str(case_dir) not in text
        assert forbidden_browser_leaks(text) == ()


def test_untrusted_batch_report_download_returns_404_without_report_body(tmp_path):
    case_dir = tmp_path / "cases" / "case-001" / "abc"
    write_report_case(case_dir, "# Report\n\nUntrusted body must stay hidden.\n", trusted=False)
    summary = tmp_path / "batch_summary.json"
    write_batch_summary(summary, case_dir)

    response = route_get_request(
        "/batch/case/case-001/report.md", web_settings(batch_summary=summary), WebJobStore()
    )

    assert response is not None
    assert response.status == 404
    assert "Untrusted body must stay hidden" not in response.body
    assert response.download_filename is None


def test_stale_batch_report_marker_returns_404(tmp_path):
    case_dir = tmp_path / "cases" / "case-001" / "abc"
    write_report_case(case_dir, "# Report\n\nOriginal trusted body.\n")
    (case_dir / PYTHON_REPORT_NAME).write_text(
        "# Report\n\nChanged stale body.\n", encoding="utf-8"
    )
    summary = tmp_path / "batch_summary.json"
    write_batch_summary(summary, case_dir)

    response = route_get_request(
        "/batch/case/case-001/report.md", web_settings(batch_summary=summary), WebJobStore()
    )

    assert response is not None
    assert response.status == 404
    assert "Changed stale body" not in response.body
    assert response.download_filename is None


def test_batch_report_routes_reject_path_shaped_case_ids(tmp_path):
    case_dir = tmp_path / "cases" / "case-001" / "abc"
    write_report_case(case_dir, "# Report\n\nTrusted batch body must stay hidden.\n")
    summary = tmp_path / "batch_summary.json"
    write_batch_summary(summary, case_dir)
    settings = web_settings(batch_summary=summary)

    encoded_traversal = route_get_request(
        "/batch/case/..%2Fcase-001/report.md", settings, WebJobStore()
    )
    slash_traversal = route_get_request(
        "/batch/case/../case-001/report.md", settings, WebJobStore()
    )

    assert encoded_traversal is not None
    assert encoded_traversal.status == 404
    assert "Trusted batch body must stay hidden" not in encoded_traversal.body
    assert encoded_traversal.download_filename is None
    assert slash_traversal is None


def test_batch_report_route_rejects_symlinked_report_outside_case_dir(tmp_path):
    case_dir = tmp_path / "cases" / "case-001" / "abc"
    case_dir.mkdir(parents=True)
    (case_dir / "profile_digest.md").write_text("PROFILE\n", encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")
    outside_report = tmp_path / "outside-report.md"
    outside_report.write_text("# Report\n\nOUTSIDE_BATCH_REPORT_SENTINEL\n", encoding="utf-8")
    (case_dir / PYTHON_REPORT_NAME).symlink_to(outside_report)
    write_python_report_marker_for_path(case_dir, outside_report)
    summary = tmp_path / "batch_summary.json"
    write_batch_summary(summary, case_dir)
    settings = web_settings(batch_summary=summary)

    download = route_get_request("/batch/case/case-001/report.md", settings, WebJobStore())
    inline = route_get_request("/batch/case/case-001/report", settings, WebJobStore())

    assert download is not None
    assert download.status == 404
    assert "OUTSIDE_BATCH_REPORT_SENTINEL" not in download.body
    assert download.download_filename is None
    assert inline is not None
    assert inline.status == 404
    assert "OUTSIDE_BATCH_REPORT_SENTINEL" not in inline.body
    assert inline.download_filename is None


def test_report_download_filename_filters_unsafe_characters():
    assert report_download_filename("abc:def$$$") == "query-doctor-report-abcdef.md"
    assert report_download_filename("$$$") == "query-doctor-report-report.md"


def test_specific_query_report_download_is_symmetric_for_trusted_and_untrusted(tmp_path):
    settings = web_settings(repo_dir=tmp_path, corpus_dir=Path("cases"))
    query_id = "abc:def"
    case_dir = expected_case_dir_for_query(query_id, settings)
    sibling_path = "/tmp/query-doctor-specific-sibling/diagnosis.md"
    user_path = "/Users/example/query-doctor/specific-leak.md"
    write_report_case(
        case_dir,
        f"# Report\n\nSpecific report with {case_dir} hidden.\n{sibling_path}\n{user_path}\n",
    )
    (case_dir / "cm_metadata.json").write_text("{}", encoding="utf-8")
    (case_dir / "collection_warnings.txt").write_text("", encoding="utf-8")

    trusted = route_get_request("/query/details/abc%3Adef/report.md", settings, WebJobStore())

    assert trusted is not None
    assert trusted.status == 200
    assert trusted.content_type == "text/markdown; charset=utf-8"
    assert trusted.download_filename == "query-doctor-report-abcdef.md"
    assert "Specific report with [local case path hidden] hidden." in trusted.body
    assert str(case_dir) not in trusted.body
    assert sibling_path not in trusted.body
    assert user_path not in trusted.body

    inline = route_get_request("/query/details/abc%3Adef/report", settings, WebJobStore())
    assert inline is not None
    assert inline.status == 200
    assert "Validated Specific Query report" in inline.body
    assert "Specific report with [local case path hidden] hidden." in inline.body
    assert str(case_dir) not in inline.body
    assert sibling_path not in inline.body
    assert user_path not in inline.body

    (case_dir / PYTHON_REPORT_NAME).write_text(
        "# Report\n\nChanged stale specific body.\n", encoding="utf-8"
    )
    untrusted = route_get_request("/query/details/abc%3Adef/report.md", settings, WebJobStore())

    assert untrusted is not None
    assert untrusted.status == 404
    assert "Changed stale specific body" not in untrusted.body
    assert untrusted.download_filename is None


def test_specific_query_report_routes_reject_path_shaped_query_ids(tmp_path):
    settings = web_settings(repo_dir=tmp_path, corpus_dir=Path("cases"))
    query_id = "abc:def"
    case_dir = expected_case_dir_for_query(query_id, settings)
    write_report_case(case_dir, "# Report\n\nTrusted specific body must stay hidden.\n")

    response = route_get_request(
        "/query/details/abc%3Adef%2F..%2Fsecret/report.md", settings, WebJobStore()
    )
    slash_traversal = route_get_request(
        "/query/details/abc%3Adef/../secret/report.md", settings, WebJobStore()
    )

    assert response is not None
    assert response.status == 400
    assert "Trusted specific body must stay hidden" not in response.body
    assert response.download_filename is None
    assert slash_traversal is None


def test_specific_query_report_route_rejects_symlinked_report_outside_case_dir(tmp_path):
    settings = web_settings(repo_dir=tmp_path, corpus_dir=Path("cases"))
    query_id = "abc:def"
    case_dir = expected_case_dir_for_query(query_id, settings)
    case_dir.mkdir(parents=True)
    (case_dir / "profile_digest.md").write_text("PROFILE\n", encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")
    outside_report = tmp_path / "outside-specific-report.md"
    outside_report.write_text("# Report\n\nOUTSIDE_SPECIFIC_REPORT_SENTINEL\n", encoding="utf-8")
    (case_dir / PYTHON_REPORT_NAME).symlink_to(outside_report)
    write_python_report_marker_for_path(case_dir, outside_report)
    (case_dir / "cm_metadata.json").write_text("{}", encoding="utf-8")
    (case_dir / "collection_warnings.txt").write_text("", encoding="utf-8")

    download = route_get_request("/query/details/abc%3Adef/report.md", settings, WebJobStore())
    inline = route_get_request("/query/details/abc%3Adef/report", settings, WebJobStore())

    assert download is not None
    assert download.status == 404
    assert "OUTSIDE_SPECIFIC_REPORT_SENTINEL" not in download.body
    assert download.download_filename is None
    assert inline is not None
    assert inline.status == 404
    assert "OUTSIDE_SPECIFIC_REPORT_SENTINEL" not in inline.body
    assert inline.download_filename is None


def test_running_report_download_uses_running_summary(tmp_path):
    finished_case_dir = tmp_path / "finished" / "case-001" / "abc"
    running_case_dir = tmp_path / "running" / "case-001" / "abc"
    write_report_case(finished_case_dir, "# Report\n\nFinished report.\n")
    write_report_case(running_case_dir, "# Report\n\nRunning report.\n")
    finished_summary = tmp_path / "finished_summary.json"
    running_summary = tmp_path / "running_summary.json"
    write_batch_summary(finished_summary, finished_case_dir, query_id="finished:def")
    write_batch_summary(running_summary, running_case_dir, query_id="running:def")
    store = WebJobStore()
    store.set_latest_running_summary(running_summary)

    response = route_get_request(
        "/running/case/case-001/report.md",
        web_settings(batch_summary=finished_summary),
        store,
    )

    assert response is not None
    assert response.status == 200
    assert "Running report." in response.body
    assert "Finished report." not in response.body


def test_report_markdown_post_route_is_not_allowed():
    assert not post_route_is_allowed("/batch/case/case-001/report.md")
    assert not post_route_is_allowed("/running/case/case-001/report.md")
    assert not post_route_is_allowed("/query/details/abc%3Adef/report.md")


def test_report_markdown_get_does_not_create_llm_jobs(tmp_path):
    case_dir = tmp_path / "cases" / "case-001" / "abc"
    write_report_case(case_dir, "# Report\n\nUntrusted body must stay hidden.\n", trusted=False)
    summary = tmp_path / "batch_summary.json"
    write_batch_summary(summary, case_dir)
    store = WebJobStore()

    response = route_get_request(
        "/batch/case/case-001/report.md", web_settings(batch_summary=summary), store
    )

    assert response is not None
    assert response.status == 404
    assert store._jobs == {}


def test_detail_pages_link_markdown_export_only_for_trusted_reports(tmp_path):
    case_dir = tmp_path / "cases" / "case-001" / "abc"
    write_report_case(case_dir, "# Report\n\nTrusted body.\n")
    summary = tmp_path / "batch_summary.json"
    write_batch_summary(summary, case_dir)

    trusted = route_get_request(
        "/batch/case/case-001", web_settings(batch_summary=summary), WebJobStore()
    )

    assert trusted is not None
    assert 'href="/batch/case/case-001/python-report.md" download' in trusted.body

    (case_dir / PYTHON_REPORT_NAME).write_text(
        "# Report\n\nChanged stale body.\n", encoding="utf-8"
    )
    untrusted = route_get_request(
        "/batch/case/case-001", web_settings(batch_summary=summary), WebJobStore()
    )

    assert untrusted is not None
    assert 'href="/batch/case/case-001/python-report.md" download' not in untrusted.body


def test_batch_case_details_render_trusted_report_raw_free_with_comparable_action(tmp_path):
    case_dir = tmp_path / "cases" / "case-001" / "abc"
    sibling_path = "/tmp/query-doctor-sibling-case/report.md"
    user_path = "/Users/example/query-doctor/report.md"
    write_report_case(
        case_dir,
        (
            "# Report\n\n"
            "Stats follow-up is ready.\n\n"
            "## Detailed report and follow-up checks\n\n"
            f"Validated body with {case_dir} hidden.\n{sibling_path}\n{user_path}\n"
        ),
    )
    summary = tmp_path / "batch_summary.json"
    write_mixed_signal_batch_summary(summary, case_dir)

    details = route_get_request(
        "/batch/case/case-001", web_settings(batch_summary=summary), WebJobStore()
    )
    inline = route_get_request(
        "/batch/case/case-001/python-report",
        web_settings(batch_summary=summary),
        WebJobStore(),
    )

    assert details is not None
    assert details.status == 200
    assert inline is not None
    assert inline.status == 200
    for body in (details.body, inline.body):
        assert "Stats follow-up is ready." in body
        assert "[local case path hidden]" in body
        assert str(case_dir) not in body
        assert sibling_path not in body
        assert user_path not in body
        assert forbidden_browser_leaks(body) == ()
    assert "Stats maintenance recommendation" in details.body
    assert "rerun under comparable load" in details.body
    assert 'href="/batch/case/case-001/python-report.md" download' in details.body


def test_batch_case_details_render_stats_metadata_gaps_raw_free(tmp_path):
    case_dir = tmp_path / "cases" / "case-001" / "abc"
    write_stats_metadata_analysis_facts(case_dir)
    summary = tmp_path / "batch_summary.json"
    write_mixed_signal_batch_summary(summary, case_dir)

    details = route_get_request(
        "/batch/case/case-001", web_settings(batch_summary=summary), WebJobStore()
    )

    assert details is not None
    assert details.status == 200
    assert "Stats maintenance recommendation" in details.body
    assert "Structured metadata detail" in details.body
    assert "partition row-count coverage partial: 6/10 known, 4 unknown" in details.body
    assert "join/filter column stats coverage partial: 2/4 complete" in details.body
    assert "Confirm and refresh the referenced table/partition row-count gaps" in details.body
    assert "compare EXPLAIN before and after stats collection" in details.body
    assert "rerun under comparable load" in details.body
    assert "Metadata facts" in details.body
    assert "analytics.fact_orders" in details.body
    assert "3 ok / 0 error / 0 not_applicable / 0 too_large" in details.body
    assert "partial" in details.body
    assert "incomplete" in details.body
    assert "partition row counts: 6/10 known, 4 unknown, 1 zero" in details.body
    assert "column stats detail: 1 NDV missing, 1 size missing" in details.body
    assert "ROUTE_STATS_RAW_SENTINEL" not in details.body
    assert "Ignored Raw Input" not in details.body
    assert str(case_dir) not in details.body
    assert forbidden_browser_leaks(details.body) == ()

    audit = audit_details_summary(
        summary,
        fail_on_stats_detail_gaps=True,
        fail_on_comparable_rerun_gaps=True,
    )

    assert audit.ok
    assert audit.action_counts == {"high:Stats maintenance recommendation": 1}
    assert audit.stats_detail_counts == {"high:with_structured_detail": 1}
    assert audit.verification_counts == {"high:comparable_rerun": 1}


def test_batch_case_details_hide_untrusted_report_body_with_raw_sentinels(tmp_path):
    case_dir = tmp_path / "cases" / "case-001" / "abc"
    write_report_case(
        case_dir,
        (
            "# Report\n\n"
            "UNTRUSTED_REPORT_RAW_SQL_SENTINEL\n"
            "UNTRUSTED_REPORT_RAW_PROFILE_SENTINEL\n"
            f"{case_dir}\n"
        ),
        trusted=False,
    )
    summary = tmp_path / "batch_summary.json"
    write_mixed_signal_batch_summary(summary, case_dir)

    details = route_get_request(
        "/batch/case/case-001", web_settings(batch_summary=summary), WebJobStore()
    )

    assert details is not None
    assert details.status == 200
    assert "UNTRUSTED_REPORT_RAW_SQL_SENTINEL" not in details.body
    assert "UNTRUSTED_REPORT_RAW_PROFILE_SENTINEL" not in details.body
    assert str(case_dir) not in details.body
    assert 'href="/batch/case/case-001/python-report.md" download' not in details.body
    assert "Stats maintenance recommendation" in details.body
    assert "rerun under comparable load" in details.body
    assert forbidden_browser_leaks(details.body) == ()


def test_batch_case_details_show_no_recipe_optimizer_guidance_without_raw_sql(tmp_path):
    case_dir = tmp_path / "cases" / "case-001" / "abc"
    case_dir.mkdir(parents=True)
    (case_dir / "profile_digest.md").write_text("PROFILE\n", encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text(
        "# Query Doctor Analysis Facts\n\n"
        "## Findings\n"
        "### Large intermediate or exchange traffic [high]\n"
        "- Deterministic facts identify large exchange volume before downstream processing.\n",
        encoding="utf-8",
    )
    (case_dir / "original_query.sql").write_text(
        "SELECT secret_col FROM guarded_orders WHERE note = 'RAW_OPTIMIZER_SOURCE_LITERAL'",
        encoding="utf-8",
    )
    summary = tmp_path / "batch_summary.json"
    write_no_recipe_optimizer_batch_summary(summary, case_dir)

    details = route_get_request(
        "/batch/case/case-001", web_settings(batch_summary=summary), WebJobStore()
    )

    assert details is not None
    assert details.status == 200
    assert "Query-shape recommendation" in details.body
    assert "Review track: single-relation filter" in details.body
    assert "Review pruning and projection first" in details.body
    assert "check partition filters, stats, and projected columns" in details.body
    assert "Compare partition pruning, scan rows, filter selectivity" in details.body
    assert "rerun under comparable load" in details.body
    assert "No trusted SQL draft shape detected" in details.body
    assert "No supported deterministic optimizer recipe is available" in details.body
    assert "Generate Python report + optimizer" not in details.body
    assert "Run Query LLM optimizer" not in details.body
    assert "Validated SQL draft" not in details.body
    assert "RAW_OPTIMIZER_SOURCE_LITERAL" not in details.body
    assert "secret_col" not in details.body
    assert "guarded_orders" not in details.body
    assert "original_query.sql" not in details.body
    assert str(case_dir) not in details.body
    assert forbidden_browser_leaks(details.body) == ()


def test_specific_query_detail_links_markdown_export_for_trusted_report(tmp_path):
    settings = web_settings(repo_dir=tmp_path, corpus_dir=Path("cases"))
    case_dir = expected_case_dir_for_query("abc:def", settings)
    write_report_case(case_dir, "# Report\n\nTrusted body.\n")
    (case_dir / "cm_metadata.json").write_text("{}", encoding="utf-8")
    (case_dir / "collection_warnings.txt").write_text("", encoding="utf-8")

    response = route_get_request("/query/details/abc%3Adef", settings, WebJobStore())

    assert response is not None
    assert response.status == 200
    assert 'href="/query/details/abc%3Adef/python-report.md" download' in response.body
