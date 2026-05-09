import io
import json
from pathlib import Path

from query_doctor.web.app import make_handler
from query_doctor.web.case_files import expected_case_dir_for_query
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebSettings
from query_doctor.web.routes import post_route_is_allowed, report_download_filename, route_get_request
from query_doctor.web.trusted_artifacts import BATCH_REPORT_NAME, write_batch_case_report_validation_marker


def web_settings(**kwargs) -> WebSettings:
    return WebSettings(config=Path(".query-doctor-cm.local.json"), **kwargs)


def write_report_case(case_dir: Path, report_text: str, *, trusted: bool = True) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "profile_digest.md").write_text("PROFILE\n", encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")
    (case_dir / BATCH_REPORT_NAME).write_text(report_text, encoding="utf-8")
    if trusted:
        write_batch_case_report_validation_marker(case_dir)


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


def dispatch_get(settings: WebSettings, store: WebJobStore, path: str) -> tuple[int, dict[str, str], bytes]:
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
    write_report_case(case_dir, f"# Report\n\nValidated body with {case_dir} hidden.\n")
    summary = tmp_path / "batch_summary.json"
    write_batch_summary(summary, case_dir)
    settings = web_settings(batch_summary=summary)

    status, headers, body = dispatch_get(settings, WebJobStore(), "/batch/case/case-001/report.md")

    assert status == 200
    assert headers["Content-Type"] == "text/markdown; charset=utf-8"
    assert headers["Content-Disposition"] == 'attachment; filename="query-doctor-report-case-001.md"'
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "same-origin"
    assert int(headers["Content-Length"]) == len(body)
    text = body.decode("utf-8")
    assert "Validated body with [local case path hidden] hidden." in text
    assert str(case_dir) not in text


def test_untrusted_batch_report_download_returns_404_without_report_body(tmp_path):
    case_dir = tmp_path / "cases" / "case-001" / "abc"
    write_report_case(case_dir, "# Report\n\nUntrusted body must stay hidden.\n", trusted=False)
    summary = tmp_path / "batch_summary.json"
    write_batch_summary(summary, case_dir)

    response = route_get_request("/batch/case/case-001/report.md", web_settings(batch_summary=summary), WebJobStore())

    assert response is not None
    assert response.status == 404
    assert "Untrusted body must stay hidden" not in response.body
    assert response.download_filename is None


def test_stale_batch_report_marker_returns_404(tmp_path):
    case_dir = tmp_path / "cases" / "case-001" / "abc"
    write_report_case(case_dir, "# Report\n\nOriginal trusted body.\n")
    (case_dir / BATCH_REPORT_NAME).write_text("# Report\n\nChanged stale body.\n", encoding="utf-8")
    summary = tmp_path / "batch_summary.json"
    write_batch_summary(summary, case_dir)

    response = route_get_request("/batch/case/case-001/report.md", web_settings(batch_summary=summary), WebJobStore())

    assert response is not None
    assert response.status == 404
    assert "Changed stale body" not in response.body
    assert response.download_filename is None


def test_report_download_filename_filters_unsafe_characters():
    assert report_download_filename("abc:def$$$") == "query-doctor-report-abcdef.md"
    assert report_download_filename("$$$") == "query-doctor-report-report.md"


def test_specific_query_report_download_is_symmetric_for_trusted_and_untrusted(tmp_path):
    settings = web_settings(repo_dir=tmp_path, corpus_dir=Path("cases"))
    query_id = "abc:def"
    case_dir = expected_case_dir_for_query(query_id, settings)
    write_report_case(case_dir, f"# Report\n\nSpecific report with {case_dir} hidden.\n")
    (case_dir / "cm_metadata.json").write_text("{}", encoding="utf-8")
    (case_dir / "collection_warnings.txt").write_text("", encoding="utf-8")

    trusted = route_get_request("/query/details/abc%3Adef/report.md", settings, WebJobStore())

    assert trusted is not None
    assert trusted.status == 200
    assert trusted.content_type == "text/markdown; charset=utf-8"
    assert trusted.download_filename == "query-doctor-report-abcdef.md"
    assert "Specific report with [local case path hidden] hidden." in trusted.body
    assert str(case_dir) not in trusted.body

    (case_dir / BATCH_REPORT_NAME).write_text("# Report\n\nChanged stale specific body.\n", encoding="utf-8")
    untrusted = route_get_request("/query/details/abc%3Adef/report.md", settings, WebJobStore())

    assert untrusted is not None
    assert untrusted.status == 404
    assert "Changed stale specific body" not in untrusted.body
    assert untrusted.download_filename is None


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

    response = route_get_request("/batch/case/case-001/report.md", web_settings(batch_summary=summary), store)

    assert response is not None
    assert response.status == 404
    assert store._jobs == {}


def test_detail_pages_link_markdown_export_only_for_trusted_reports(tmp_path):
    case_dir = tmp_path / "cases" / "case-001" / "abc"
    write_report_case(case_dir, "# Report\n\nTrusted body.\n")
    summary = tmp_path / "batch_summary.json"
    write_batch_summary(summary, case_dir)

    trusted = route_get_request("/batch/case/case-001", web_settings(batch_summary=summary), WebJobStore())

    assert trusted is not None
    assert 'href="/batch/case/case-001/report.md" download' in trusted.body

    (case_dir / BATCH_REPORT_NAME).write_text("# Report\n\nChanged stale body.\n", encoding="utf-8")
    untrusted = route_get_request("/batch/case/case-001", web_settings(batch_summary=summary), WebJobStore())

    assert untrusted is not None
    assert 'href="/batch/case/case-001/report.md" download' not in untrusted.body


def test_specific_query_detail_links_markdown_export_for_trusted_report(tmp_path):
    settings = web_settings(repo_dir=tmp_path, corpus_dir=Path("cases"))
    case_dir = expected_case_dir_for_query("abc:def", settings)
    write_report_case(case_dir, "# Report\n\nTrusted body.\n")
    (case_dir / "cm_metadata.json").write_text("{}", encoding="utf-8")
    (case_dir / "collection_warnings.txt").write_text("", encoding="utf-8")

    response = route_get_request("/query/details/abc%3Adef", settings, WebJobStore())

    assert response is not None
    assert response.status == 200
    assert 'href="/query/details/abc%3Adef/report.md" download' in response.body
