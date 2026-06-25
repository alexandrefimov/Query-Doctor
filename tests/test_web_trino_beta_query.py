from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import pytest

from query_doctor.trino.coordinator_query_info_target import (
    TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION,
    TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_VERSION,
)
from query_doctor.trino.coordinator_query_list_target import (
    TRINO_COORDINATOR_QUERY_LIST_CONTRACT_VERSION,
    TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_VERSION,
    TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE,
    TrinoCoordinatorQueryListRecord,
)
from query_doctor.trino.kerberos_spnego import TrinoKerberosSpnegoFetcher
from query_doctor.web.batch_scan import build_batch_command, parse_batch_run_config
from query_doctor.web.batch_jobs import start_batch_job, start_running_job
from query_doctor.web.cluster_selection import settings_for_cluster_key
from query_doctor.web.config import build_web_settings, validate_web_startup_config
from query_doctor.web.jobs import WebJobStore, render_job_status_json
from query_doctor.web.models import (
    BatchRunConfig,
    WebClusterConfig,
    WebError,
    WebQueryAnalysisResult,
    WebSettings,
    WebTrinoRecentScanResult,
    WebTrinoRecentScanRow,
    WebTrinoQueryAnalysisResult,
)
from query_doctor.web.request_handlers import handle_analyze_request, start_analyze_job
from query_doctor.web.routes import route_get_request, route_post_request
from query_doctor.web.server_args import parse_args
from query_doctor.web.trino_beta_query import (
    classify_trino_engine_contract_error,
    run_trino_query_id_analysis,
)
from query_doctor.web.trino_guidance import validate_trino_optimizer_guidance_text
from query_doctor.web.trino_report import validate_trino_python_report_text
from query_doctor.web.trino_recent import run_trino_recent_scan, select_trino_recent_records
from query_doctor.web.ui.progress import render_job_panel
from query_doctor.web.ui.recent_scan_form import render_batch_run_panel
from query_doctor.web.ui.trino import (
    render_trino_query_analysis_result,
    render_trino_recent_scan_result,
)


COORDINATOR_URL = "https://coordinator.example.test:8443"
QUERY_ID = "20260603_120102_00001_abcde"


def assert_trino_beta_blocked_surfaces(
    html: str, *, details_available: bool = False, mode_label: str = "Trino Beta"
) -> None:
    assert f'aria-label="{mode_label} blocked surfaces"' in html
    assert "Running:" in html
    assert "Query-history crawl:" in html
    assert "Metadata:" in html
    assert "not collected" in html
    assert "Details:" in html
    if details_available:
        assert "raw-free case view" in html
    else:
        assert "Details:" in html and "raw-free case view" not in html
    assert "Python Report:" in html
    assert "LLM reports:" in html
    if details_available:
        assert "via Details" in html
    assert "Trusted reports:" not in html
    assert "Details/reports:" not in html
    assert "Optimizer:" in html
    assert "Generated SQL:" in html
    assert "not generated" in html
    assert "SQL execution:" in html
    assert "not performed" in html
    assert 'href="/query/details/' not in html
    assert 'href="/python-report/' not in html
    assert 'href="/optimizer"' not in html


def test_trino_beta_query_analysis_runs_one_bounded_pruned_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _trino_settings(tmp_path)
    calls: list[tuple[str, str]] = []

    def fetcher(coordinator_url: str, *, query_id: str, **_kwargs: object) -> str:
        calls.append((coordinator_url, query_id))
        return _raw_query_info_text()

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        fetcher,
    )

    result = run_trino_query_id_analysis(QUERY_ID, settings)

    assert calls == [(COORDINATOR_URL, QUERY_ID)]
    assert result.query_id == QUERY_ID
    assert result.diagnosis["schema_version"] == "trino_compact_diagnosis_v1"
    assert result.diagnosis["diagnosis_boundary"]["trino_sql_execution"] == "not_performed"


def test_trino_beta_query_analysis_materializes_raw_free_case_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _trino_settings(tmp_path)
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    result = run_trino_query_id_analysis(QUERY_ID, settings)

    artifacts = result.case_artifacts
    assert artifacts is not None
    assert artifacts.case_dir.parent == tmp_path / "cases" / "cm-corpus" / "trino-web-cases"
    assert artifacts.case_id.startswith("trino-")
    expected_paths = (
        artifacts.boundary_path,
        artifacts.compact_diagnosis_path,
        artifacts.metadata_summary_path,
        artifacts.analysis_path,
        artifacts.analysis_facts_path,
    )
    assert all(path.is_file() for path in expected_paths)

    boundary = json.loads(artifacts.boundary_path.read_text(encoding="utf-8"))
    diagnosis = json.loads(artifacts.compact_diagnosis_path.read_text(encoding="utf-8"))
    metadata_summary = json.loads(artifacts.metadata_summary_path.read_text(encoding="utf-8"))
    analysis = json.loads(artifacts.analysis_path.read_text(encoding="utf-8"))
    facts_text = artifacts.analysis_facts_path.read_text(encoding="utf-8")

    assert boundary["schema_version"] == "engine_fact_boundary_v1"
    assert boundary["identity"]["engine"] == "trino"
    assert diagnosis["schema_version"] == "trino_compact_diagnosis_v1"
    assert metadata_summary == analysis["metadata_summary"]
    assert metadata_summary["collection"] == "not_collected"
    assert analysis["schema_version"] == "trino_web_case_analysis_v1"
    assert analysis["workflow"] == "query_id"
    assert analysis["query_reference"] == {
        "kind": "explicit_query_id",
        "value": "hidden",
    }
    assert analysis["raw_source_policy"]["python_report"] == "raw_free_materialized"
    assert analysis["raw_source_policy"]["optimizer_guidance"] == "raw_free_materialized"
    assert analysis["raw_source_policy"]["llm_reports"] == "not_wired"
    assert analysis["raw_source_policy"]["trusted_reports"] == "python_report_only"
    assert analysis["raw_source_policy"]["optimizer_behavior"] == "guidance_only"
    assert "Query reference: explicit_query_id_hidden" in facts_text
    assert "Python report: raw_free_materialized" in facts_text
    assert "Optimizer guidance: raw_free_materialized" in facts_text

    serialized = "\n".join(path.read_text(encoding="utf-8") for path in expected_paths)
    forbidden_tokens = (
        QUERY_ID,
        COORDINATOR_URL,
        "SELECT",
        "sensitive_table",
        "operator_user",
        "adhoc_console",
        "stage-raw-id",
        "task-raw-id",
        "worker-a.example.net",
        "synthetic_local_path_marker",
        "Authorization",
        str(tmp_path),
    )
    for token in forbidden_tokens:
        assert token not in serialized

    html = render_trino_query_analysis_result(result)
    rendered_job = json.loads(render_job_status_json(_completed_trino_job(result)))["result_html"]
    assert f'href="/trino/details/{artifacts.case_id}"' in html
    assert f'href="/trino/details/{artifacts.case_id}"' in rendered_job
    for hidden in (
        str(artifacts.case_dir),
        "boundary.json",
        "compact_diagnosis.json",
        "metadata_summary.json",
        "analysis.json",
        "analysis_facts.md",
    ):
        assert hidden not in html
        assert hidden not in rendered_job


def test_trino_beta_details_route_renders_raw_free_materialized_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _trino_settings(tmp_path)
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )
    result = run_trino_query_id_analysis(QUERY_ID, settings)
    assert result.case_artifacts is not None

    response = route_get_request(
        f"/trino/details/{result.case_artifacts.case_id}",
        settings,
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 200
    body = response.body
    assert "Trino Details" in body
    assert "Decision facts" in body
    assert "Diagnosis result" in body
    assert "Python Report" in body
    assert "raw_free_materialized" in body
    assert "Optimizer guidance" in body
    assert "guidance_only" in body
    assert "LLM reports" in body
    assert "not_wired" in body
    assert "Optimizer" in body
    assert "SQL execution" in body
    assert 'href="?report=python"' in body
    assert 'href="?report=python&amp;download=1"' in body
    assert 'href="?guidance=optimizer"' in body
    assert 'href="?guidance=optimizer&amp;download=1"' in body
    assert QUERY_ID not in body
    assert result.case_artifacts.case_id not in body
    forbidden_tokens = (
        COORDINATOR_URL,
        "SELECT",
        "sensitive_table",
        "operator_user",
        "adhoc_console",
        "stage-raw-id",
        "task-raw-id",
        "worker-a.example.net",
        "synthetic_local_path_marker",
        "Authorization",
        str(tmp_path),
        "boundary.json",
        "compact_diagnosis.json",
        "metadata_summary.json",
        "analysis.json",
        "analysis_facts.md",
    )
    for token in forbidden_tokens:
        assert token not in body
    assert 'href="/query/details/' not in body
    assert 'href="/python-report/' not in body
    assert 'href="/optimizer"' not in body
    assert "Run optimizer" not in body
    assert "Run report" not in body


def test_trino_beta_optimizer_guidance_route_renders_validated_raw_free_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _trino_settings(tmp_path)
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )
    result = run_trino_query_id_analysis(QUERY_ID, settings)
    assert result.case_artifacts is not None

    response = route_get_request(
        f"/trino/details/{result.case_artifacts.case_id}?guidance=optimizer",
        settings,
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 200
    body = response.body
    assert "Trino Optimizer Guidance" in body
    assert "Review Tracks" in body
    assert "Root cause not claimed" in body
    assert "Download Markdown" in body
    assert 'href="?guidance=optimizer&amp;download=1"' in body
    assert QUERY_ID not in body
    assert result.case_artifacts.case_id not in body
    forbidden_tokens = (
        COORDINATOR_URL,
        "SELECT",
        "sensitive_table",
        "operator_user",
        "adhoc_console",
        "stage-raw-id",
        "task-raw-id",
        "worker-a.example.net",
        "synthetic_local_path_marker",
        "Authorization",
        str(tmp_path),
        "boundary.json",
        "compact_diagnosis.json",
        "metadata_summary.json",
        "analysis.json",
        "analysis_facts.md",
    )
    for token in forbidden_tokens:
        assert token not in body
    assert 'href="/query/details/' not in body
    assert 'href="/python-report/' not in body
    assert 'href="/optimizer"' not in body
    assert "Run optimizer" not in body


def test_trino_beta_optimizer_guidance_markdown_download_stays_raw_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _trino_settings(tmp_path)
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )
    result = run_trino_query_id_analysis(QUERY_ID, settings)
    assert result.case_artifacts is not None

    response = route_get_request(
        f"/trino/details/{result.case_artifacts.case_id}?guidance=optimizer&download=1",
        settings,
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 200
    assert response.content_type == "text/markdown; charset=utf-8"
    assert response.download_filename == "query-doctor-trino-optimizer-guidance.md"
    assert response.body.startswith("# Trino Optimizer Guidance")
    assert validate_trino_optimizer_guidance_text(response.body) == []
    assert QUERY_ID not in response.body
    assert result.case_artifacts.case_id not in response.body
    assert COORDINATOR_URL not in response.body
    assert str(tmp_path) not in response.body


def test_trino_beta_python_report_route_renders_validated_raw_free_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _trino_settings(tmp_path)
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )
    result = run_trino_query_id_analysis(QUERY_ID, settings)
    assert result.case_artifacts is not None

    response = route_get_request(
        f"/trino/details/{result.case_artifacts.case_id}?report=python",
        settings,
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 200
    body = response.body
    assert "Trino Python Report" in body
    assert "Root cause not claimed" in body
    assert "Attention Areas" in body
    assert "Download Markdown" in body
    assert 'href="?report=python&amp;download=1"' in body
    assert QUERY_ID not in body
    assert result.case_artifacts.case_id not in body
    forbidden_tokens = (
        COORDINATOR_URL,
        "SELECT",
        "sensitive_table",
        "operator_user",
        "adhoc_console",
        "stage-raw-id",
        "task-raw-id",
        "worker-a.example.net",
        "synthetic_local_path_marker",
        "Authorization",
        str(tmp_path),
        "boundary.json",
        "compact_diagnosis.json",
        "metadata_summary.json",
        "analysis.json",
        "analysis_facts.md",
    )
    for token in forbidden_tokens:
        assert token not in body
    assert 'href="/query/details/' not in body
    assert 'href="/python-report/' not in body
    assert 'href="/optimizer"' not in body
    assert "generated SQL" not in body


def test_trino_beta_python_report_markdown_download_stays_raw_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _trino_settings(tmp_path)
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )
    result = run_trino_query_id_analysis(QUERY_ID, settings)
    assert result.case_artifacts is not None

    response = route_get_request(
        f"/trino/details/{result.case_artifacts.case_id}?report=python&download=1",
        settings,
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 200
    assert response.content_type == "text/markdown; charset=utf-8"
    assert response.download_filename == "query-doctor-trino-python-report.md"
    assert response.body.startswith("# Trino Python Report")
    assert validate_trino_python_report_text(response.body) == []
    assert QUERY_ID not in response.body
    assert result.case_artifacts.case_id not in response.body
    assert COORDINATOR_URL not in response.body
    assert str(tmp_path) not in response.body


@pytest.mark.parametrize(
    "unsafe_text",
    (
        "Impala admission control was involved.",
        "SELECT secret_col FROM sensitive_table",
        "SHOW CREATE TABLE catalog.schema.table",
        QUERY_ID,
        "https://coordinator.example.test/ui/query.html",
        "/private/tmp/query-doctor/secret.json",
        "Authorization: Bearer secret-token",
        "The root cause is stale statistics.",
        "generated SQL draft follows",
        "connector internal stage-raw-id task-raw-id worker-a.example.net",
    ),
)
def test_trino_python_report_validator_rejects_unsafe_claims_and_payloads(
    unsafe_text: str,
) -> None:
    safe_report = "# Trino Python Report\n\n## Summary\n- Root cause not claimed.\n"

    assert validate_trino_python_report_text(safe_report) == []
    assert validate_trino_python_report_text(safe_report + unsafe_text + "\n")


@pytest.mark.parametrize(
    "unsafe_text",
    (
        "Impala admission control was involved.",
        "SELECT secret_col FROM sensitive_table",
        "SHOW CREATE TABLE catalog.schema.table",
        QUERY_ID,
        "https://coordinator.example.test/ui/query.html",
        "/private/tmp/query-doctor/secret.json",
        "Authorization: Bearer secret-token",
        "The root cause is stale statistics.",
        "generated SQL draft follows",
        "connector internal stage-raw-id task-raw-id worker-a.example.net",
    ),
)
def test_trino_optimizer_guidance_validator_rejects_unsafe_claims_and_payloads(
    unsafe_text: str,
) -> None:
    safe_guidance = "# Trino Optimizer Guidance\n\n## Scope\n- Root cause not claimed.\n"

    assert validate_trino_optimizer_guidance_text(safe_guidance) == []
    assert validate_trino_optimizer_guidance_text(safe_guidance + unsafe_text + "\n")


def test_trino_beta_details_route_rejects_invalid_case_reference_without_echo(
    tmp_path: Path,
) -> None:
    settings = _trino_settings(tmp_path)
    invalid_case_id = "trino-SELECT-sensitive_table"

    response = route_get_request(f"/trino/details/{invalid_case_id}", settings, WebJobStore())

    assert response is not None
    assert response.status == 400
    assert "Trino Details case reference was rejected." in response.body
    assert invalid_case_id not in response.body
    assert "sensitive_table" not in response.body
    assert str(tmp_path) not in response.body
    assert "analysis.json" not in response.body


def test_trino_production_mode_query_analysis_uses_bounded_raw_free_lane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _trino_settings(
        tmp_path,
        trino_support_mode="production",
        trino_beta_enabled=False,
    )
    calls: list[tuple[str, str]] = []

    def fetcher(coordinator_url: str, *, query_id: str, **_kwargs: object) -> str:
        calls.append((coordinator_url, query_id))
        return _raw_query_info_text()

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        fetcher,
    )

    result = run_trino_query_id_analysis(QUERY_ID, settings)
    html = render_trino_query_analysis_result(result)

    assert calls == [(COORDINATOR_URL, QUERY_ID)]
    assert result.support_mode == "production"
    assert "Trino Query ID diagnosis" in html
    assert "Trino Beta Query ID diagnosis" not in html
    assert 'aria-label="Trino blocked surfaces"' in html
    assert "Local boundary" in html
    assert "complete local Trino output for the selected Query ID" in html
    assert result.case_artifacts is not None
    assert f'href="/trino/details/{result.case_artifacts.case_id}"' in html
    assert_trino_beta_blocked_surfaces(html, details_available=True, mode_label="Trino")
    assert 'href="/query/details/' not in html
    assert 'href="/python-report/' not in html
    assert 'href="/optimizer"' not in html
    assert COORDINATOR_URL not in html
    assert str(tmp_path) not in html


def test_trino_beta_query_analysis_reports_beta_progress_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _trino_settings(tmp_path)
    progress_stages: list[int] = []
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    run_trino_query_id_analysis(QUERY_ID, settings, progress=progress_stages.append)

    assert progress_stages == [0, 1, 2, 3, 4]


def test_trino_beta_query_analysis_honors_cancel_before_network_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _trino_settings(tmp_path)

    def fetcher(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("cancelled Trino beta job should not read QueryInfo")

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        fetcher,
    )

    with pytest.raises(WebError, match="Analysis was stopped by the user"):
        run_trino_query_id_analysis(QUERY_ID, settings, cancel_check=lambda: True)


def test_trino_beta_query_analysis_requires_local_config(tmp_path: Path) -> None:
    settings = WebSettings(
        config=tmp_path / "web.json",
        trino_beta_enabled=True,
        trino_coordinator_url=COORDINATOR_URL,
        selected_engine="trino",
    )

    with pytest.raises(WebError, match="not configured for the selected source") as excinfo:
        run_trino_query_id_analysis(QUERY_ID, settings)

    assert excinfo.value.reason_code == "trino_beta.not_configured"
    assert "source contracts" in str(excinfo.value.next_step)


def test_trino_beta_query_analysis_rejects_invalid_query_id(tmp_path: Path) -> None:
    with pytest.raises(WebError, match="Trino Query ID"):
        run_trino_query_id_analysis("abc:def", _trino_settings(tmp_path))


@pytest.mark.parametrize(
    ("message", "expected_reason", "expected_text"),
    [
        (
            "Trino coordinator query-info authentication was rejected; refresh",
            "trino_beta.auth_rejected",
            "could not authenticate",
        ),
        (
            "Trino coordinator query-info is unavailable for the selected Query ID",
            "trino_beta.query_unavailable",
            "unavailable for the selected Query ID",
        ),
        (
            "Trino coordinator query-list could not be read",
            "trino_beta.network_read_failed",
            "bounded coordinator query list",
        ),
        (
            "Trino coordinator query-info payload is too large",
            "trino_beta.payload_rejected",
            "exceeded configured bounds",
        ),
        (
            "Trino coordinator query-info contract version is unsupported",
            "trino_beta.contract_rejected",
            "source-contract checks",
        ),
    ],
)
def test_trino_beta_error_classifier_keeps_safe_reason_codes(
    message: str,
    expected_reason: str,
    expected_text: str,
) -> None:
    reason, safe_message, next_step, detail = classify_trino_engine_contract_error(
        message,
        workflow="Trino Beta Query ID diagnosis",
    )

    rendered = " ".join((safe_message, next_step, detail))
    assert reason == expected_reason
    assert expected_text in rendered
    assert "coordinator.example" not in rendered
    assert "Authorization" not in rendered


def test_trino_beta_handle_analyze_request_renders_raw_free_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _trino_settings(tmp_path)
    auth_header = tmp_path / "operator-auth-header.txt"
    auth_header.write_text("Authorization: RedactedSecret value\n", encoding="utf-8")
    settings = WebSettings(
        config=settings.config,
        repo_dir=settings.repo_dir,
        trino_beta_enabled=True,
        trino_coordinator_url=COORDINATOR_URL,
        trino_query_info_source_contract=settings.trino_query_info_source_contract,
        trino_auth_header_file=auth_header,
    )

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    status, body = handle_analyze_request(
        {"query_id": [QUERY_ID], "engine": ["trino"]},
        settings,
    )

    assert status == 200
    assert "Trino Beta Query ID diagnosis" in body
    assert f"<code>{QUERY_ID}</code>" in body
    assert "Beta boundary" in body
    assert "complete Trino Beta product output for the selected Query ID" in body
    assert (
        "no Running scans, query-history crawling, metadata collection, "
        "LLM reports, Query Optimizer jobs, generated SQL, or SQL execution" in body
    )
    assert "raw-free case view" in body
    assert "does not create Running scans, a query-history crawl" in body
    assert "LLM reports, Query Optimizer jobs" in body
    assert "optimizer guidance" in body
    assert "generated SQL drafts, or SQL execution" in body
    assert "SQL execution" in body
    assert_trino_beta_blocked_surfaces(body, details_available=True)
    assert 'href="/trino/details/' in body
    assert 'href="/query/' not in body
    assert 'href="/optimizer"' not in body
    assert COORDINATOR_URL not in body
    assert "RedactedSecret" not in body
    assert "SELECT" not in body
    assert "sensitive_table" not in body
    assert str(tmp_path) not in body


def test_trino_beta_result_renderer_redacts_dynamic_diagnosis_text(tmp_path: Path) -> None:
    result = WebTrinoQueryAnalysisResult(
        query_id=QUERY_ID,
        diagnosis={
            "schema_version": "trino_compact_diagnosis_v1",
            "support_status": "preview",
            "parser_coverage": "known",
            "lifecycle": "failed",
            "diagnostic_lane": {
                "evidence_readiness": "one_query_attention_ready",
                "source_granularity": "one_query_boundary",
                "verification_scope": "comparable_one_query_rerun",
                "supported_attention_area_count": 1,
            },
            "attention_areas": [
                {
                    "id": "trino_spill_observed",
                    "state": "supported",
                    "summary": (
                        "SELECT secret_col FROM sensitive_table at "
                        "https://coordinator.example.test/ui/query.html"
                    ),
                    "change_direction": f"Read /private/tmp/{tmp_path.name}/secret.json",
                    "verification": "Rerun without Authorization: Bearer secret-token",
                }
            ],
            "limitations": [
                {
                    "id": "no_raw_sql",
                    "state": "not_wired",
                    "summary": "raw artifact query_info_boundary.json was not shown",
                }
            ],
            "diagnosis_boundary": {
                "root_cause": "not_claimed",
                "details_trusted_report_surface": "not_wired",
                "optimizer_behavior": "not_wired",
                "trino_sql_execution": "not_performed",
                "live_recent_scan": "not_wired",
            },
        },
    )

    html = render_trino_query_analysis_result(result)

    assert f"<code>{QUERY_ID}</code>" in html
    assert "Trino Beta Query ID diagnosis" in html
    assert_trino_beta_blocked_surfaces(html)
    assert 'href="/trino/details/' not in html
    assert "secret_col" not in html
    assert "sensitive_table" not in html
    assert "coordinator.example.test" not in html
    assert str(tmp_path) not in html
    assert "secret-token" not in html
    assert "query_info_boundary.json" not in html
    assert 'href="/query/details/' not in html
    assert 'href="/optimizer"' not in html


def test_trino_beta_async_result_json_redacts_dynamic_diagnosis_text(tmp_path: Path) -> None:
    store = WebJobStore()
    snapshot = store.create(
        QUERY_ID,
        "analysis",
        form_values={"engine": "trino"},
        kind="trino_query",
    )
    store.complete(
        snapshot.job_id,
        WebTrinoQueryAnalysisResult(
            query_id=QUERY_ID,
            diagnosis={
                "schema_version": "trino_compact_diagnosis_v1",
                "support_status": "preview",
                "parser_coverage": "known",
                "lifecycle": "failed",
                "attention_areas": [
                    {
                        "id": "trino_spill_observed",
                        "state": "supported",
                        "summary": (
                            "SELECT secret_col FROM sensitive_table at "
                            "https://coordinator.example.test/ui/query.html"
                        ),
                        "change_direction": f"Read /private/tmp/{tmp_path.name}/secret.json",
                        "verification": "Rerun without Authorization: Bearer secret-token",
                    }
                ],
                "diagnosis_boundary": {
                    "root_cause": "not_claimed",
                    "details_trusted_report_surface": "not_wired",
                    "optimizer_behavior": "not_wired",
                    "trino_sql_execution": "not_performed",
                    "live_recent_scan": "not_wired",
                },
            },
        ),
    )
    completed = store.get(snapshot.job_id)
    payload = json.loads(render_job_status_json(completed))
    rendered = json.dumps(payload, sort_keys=True)

    assert payload["kind"] == "trino_query"
    assert f"<code>{QUERY_ID}</code>" in payload["result_html"]
    assert "secret_col" not in rendered
    assert "sensitive_table" not in rendered
    assert "coordinator.example.test" not in rendered
    assert str(tmp_path) not in rendered
    assert "secret-token" not in rendered
    assert 'href="/query/details/' not in rendered
    assert 'href="/optimizer"' not in rendered


def test_mixed_source_trino_beta_query_uses_beta_path_without_impala_echo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = tmp_path / "trino-query-info-contract.json"
    auth_header = tmp_path / "trino-auth-header.txt"
    contract.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    auth_header.write_text("Authorization: RedactedSecret value\n", encoding="utf-8")
    settings = WebSettings(
        config=tmp_path / "web.json",
        repo_dir=tmp_path,
        clusters=(
            WebClusterConfig(
                key="mixed",
                label="Mixed source",
                cm_url="https://cm.example.test:7183/",
                cm_cluster="impala_cluster",
                cm_service="impala",
                trino_beta_enabled=True,
                trino_coordinator_url=COORDINATOR_URL,
                trino_query_info_source_contract=contract,
                trino_auth_header_file=auth_header,
            ),
        ),
        active_cluster_key="mixed",
    )

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    status, body = handle_analyze_request(
        {"cluster_key": ["mixed"], "query_id": [QUERY_ID], "engine": ["trino"]},
        settings,
    )

    assert status == 200
    assert "Trino Beta Query ID diagnosis" in body
    assert "Known Query ID analysis" not in body
    assert "Generating Python report" not in body
    assert 'href="/query/details/' not in body
    assert COORDINATOR_URL not in body
    assert "cm.example.test" not in body
    assert "RedactedSecret" not in body
    assert "trino-query-info-contract.json" not in body
    assert "trino-auth-header.txt" not in body
    assert str(tmp_path) not in body


def test_trino_beta_invalid_query_id_is_not_reflected_to_browser(
    tmp_path: Path,
) -> None:
    invalid_query_id = "abc:def SELECT sensitive_table"
    settings = _trino_settings(tmp_path)

    status, body = handle_analyze_request(
        {"query_id": [invalid_query_id], "engine": ["trino"]},
        settings,
    )

    assert status == 400
    assert "Trino Query ID must look like" in body
    assert invalid_query_id not in body
    assert "sensitive_table" not in body
    assert 'value=""' in body


def test_trino_beta_handle_analyze_request_hides_network_failure_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _trino_settings(tmp_path)
    auth_header = tmp_path / "operator-auth-header.txt"
    auth_header.write_text("Authorization: RedactedSecret value\n", encoding="utf-8")
    settings = WebSettings(
        config=settings.config,
        repo_dir=settings.repo_dir,
        trino_beta_enabled=True,
        trino_coordinator_url=COORDINATOR_URL,
        trino_query_info_source_contract=settings.trino_query_info_source_contract,
        trino_auth_header_file=auth_header,
    )

    def failing_fetcher(*_args: object, **_kwargs: object) -> str:
        raise OSError(f"raw failure {COORDINATOR_URL} {QUERY_ID} RedactedSecret {tmp_path}")

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        failing_fetcher,
    )

    status, body = handle_analyze_request(
        {"query_id": [QUERY_ID], "engine": ["trino"]},
        settings,
    )

    assert status == 400
    assert "Trino Beta Query ID diagnosis could not read the bounded coordinator QueryInfo" in body
    assert "trino_beta.network_read_failed" in body
    assert "Check coordinator reachability" in body
    assert COORDINATOR_URL not in body
    assert "RedactedSecret" not in body
    assert str(tmp_path) not in body


def test_trino_beta_handle_analyze_request_rejects_unconfigured_source_before_analysis(
    tmp_path: Path,
) -> None:
    settings = WebSettings(config=tmp_path / "web.json")

    def fail_if_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("Trino Beta analysis must not run without local beta config")

    status, body = handle_analyze_request(
        {"query_id": [QUERY_ID], "engine": ["trino"]},
        settings,
        analysis_func=fail_if_called,
    )

    assert status == 400
    assert "Trino Beta Query ID diagnosis is not configured for the selected source." in body
    assert "trino_coordinator_url" not in body
    assert "trino_query_info_source_contract" not in body
    assert str(tmp_path) not in body


def test_trino_beta_handle_analyze_request_rejects_partial_source_before_analysis(
    tmp_path: Path,
) -> None:
    settings = WebSettings(
        config=tmp_path / "web.json",
        clusters=(
            WebClusterConfig(
                key="partial",
                label="Partial Trino source",
                trino_beta_enabled=True,
                trino_coordinator_url=COORDINATOR_URL,
            ),
        ),
        active_cluster_key="partial",
    )

    def fail_if_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("partial Trino Beta source must fail before analysis")

    status, body = handle_analyze_request(
        {"cluster_key": ["partial"], "query_id": [QUERY_ID], "engine": ["trino"]},
        settings,
        analysis_func=fail_if_called,
    )

    assert status == 400
    assert "Trino Beta Query ID diagnosis is not configured for the selected source." in body
    assert QUERY_ID not in body
    assert COORDINATOR_URL not in body
    assert "trino_coordinator_url" not in body
    assert "trino_query_info_source_contract" not in body
    assert str(tmp_path) not in body


def test_trino_beta_async_job_uses_trino_progress_wording(tmp_path: Path) -> None:
    settings = _trino_settings(tmp_path)
    store = WebJobStore()
    started = threading.Event()
    release = threading.Event()

    def analysis_func(*_args: object) -> WebTrinoQueryAnalysisResult:
        started.set()
        release.wait(timeout=5)
        return WebTrinoQueryAnalysisResult(
            query_id=QUERY_ID,
            diagnosis={"schema_version": "trino_compact_diagnosis_v1"},
        )

    status, location = start_analyze_job(
        {"query_id": [QUERY_ID], "engine": ["trino"]},
        settings,
        store,
        analysis_func=analysis_func,
    )

    assert status == 303
    job_id = location.rsplit("/", 1)[-1]
    assert started.wait(timeout=5)
    snapshot = store.get(job_id)
    assert snapshot is not None
    payload = json.loads(render_job_status_json(snapshot))
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["kind"] == "trino_query"
    assert payload["stage"] == "Checking Trino Query ID"
    assert "Reading bounded QueryInfo" in rendered
    assert "Building compact diagnosis" in rendered
    assert "Collecting or reusing profile" not in rendered
    assert "Generating Python report" not in rendered
    assert "optimizer" not in rendered.lower()

    release.set()


def test_trino_beta_async_rejects_invalid_query_id_before_job_creation(
    tmp_path: Path,
) -> None:
    invalid_query_id = "abc:def SELECT sensitive_table"
    settings = _trino_settings(tmp_path)
    store = WebJobStore()

    def analysis_func(*_args: object) -> WebTrinoQueryAnalysisResult:
        raise AssertionError("invalid Trino Query ID must not start a job")

    status, body = start_analyze_job(
        {"query_id": [invalid_query_id], "engine": ["trino"]},
        settings,
        store,
        analysis_func=analysis_func,
    )

    assert status == 400
    assert "Trino Query ID must look like" in body
    assert invalid_query_id not in body
    assert "sensitive_table" not in body
    assert 'value=""' in body


def test_mixed_source_trino_beta_async_job_keeps_beta_form_and_result(
    tmp_path: Path,
) -> None:
    contract = tmp_path / "trino-query-info-contract.json"
    auth_header = tmp_path / "trino-auth-header.txt"
    settings = WebSettings(
        config=tmp_path / "web.json",
        repo_dir=tmp_path,
        clusters=(
            WebClusterConfig(
                key="mixed",
                label="Mixed source",
                cm_url="https://cm.example.test:7183/",
                cm_cluster="impala_cluster",
                cm_service="impala",
                trino_beta_enabled=True,
                trino_coordinator_url=COORDINATOR_URL,
                trino_query_info_source_contract=contract,
                trino_auth_header_file=auth_header,
            ),
        ),
        active_cluster_key="mixed",
    )
    store = WebJobStore()
    started = threading.Event()
    release = threading.Event()

    def analysis_func(*_args: object) -> WebTrinoQueryAnalysisResult:
        started.set()
        release.wait(timeout=5)
        return WebTrinoQueryAnalysisResult(
            query_id=QUERY_ID,
            diagnosis={"schema_version": "trino_compact_diagnosis_v1"},
        )

    status, location = start_analyze_job(
        {"cluster_key": ["mixed"], "query_id": [QUERY_ID], "engine": ["trino"]},
        settings,
        store,
        analysis_func=analysis_func,
    )

    assert status == 303
    job_id = location.rsplit("/", 1)[-1]
    assert started.wait(timeout=5)
    running = store.get(job_id)
    assert running is not None
    assert running.kind == "trino_query"
    assert running.batch_form_values == {
        "diagnosis_target": "query",
        "cluster_key": "mixed",
        "engine": "trino",
    }

    release.set()
    for _ in range(50):
        completed = store.get(job_id)
        if completed is not None and completed.status == "ok":
            break
        time.sleep(0.01)
    finished_response = route_get_request(f"/jobs/{job_id}", settings, store)

    assert finished_response is not None
    assert finished_response.status == 200
    assert "Trino Beta Query ID diagnosis" in finished_response.body
    assert '<input type="hidden" name="engine" value="trino" data-engine-hidden>' in (
        finished_response.body
    )
    assert "Known Query ID analysis" not in finished_response.body
    assert "Generating Python report" not in finished_response.body
    assert 'href="/query/details/' not in finished_response.body
    assert COORDINATOR_URL not in finished_response.body
    assert "cm.example.test" not in finished_response.body
    assert "trino-query-info-contract.json" not in finished_response.body
    assert "trino-auth-header.txt" not in finished_response.body
    assert str(tmp_path) not in finished_response.body


def test_trino_beta_route_post_analyze_e2e_smoke_renders_final_beta_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _trino_settings(tmp_path)
    store = WebJobStore()
    calls: list[tuple[str, str]] = []

    def fetcher(coordinator_url: str, *, query_id: str, **_kwargs: object) -> str:
        calls.append((coordinator_url, query_id))
        return _raw_query_info_text()

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        fetcher,
    )

    response = route_post_request(
        "/analyze",
        {"query_id": [QUERY_ID], "engine": ["trino"]},
        settings,
        store,
    )

    assert response is not None
    assert response.status == 303
    assert response.location is not None
    assert response.location.startswith("/jobs/")
    job_id = response.location.rsplit("/", 1)[-1]
    for _ in range(50):
        snapshot = store.get(job_id)
        if snapshot is not None and snapshot.status == "ok":
            break
        time.sleep(0.01)
    snapshot = store.get(job_id)
    assert snapshot is not None
    status_response = route_get_request(f"/jobs/{job_id}/status", settings, store)
    final_response = route_get_request(f"/jobs/{job_id}", settings, store)

    assert calls == [(COORDINATOR_URL, QUERY_ID)]
    assert status_response is not None
    status_payload = json.loads(status_response.body)
    assert status_response.status == 200
    assert status_payload["status"] == "ok"
    assert status_payload["kind"] == "trino_query"
    assert "Trino Beta Query ID diagnosis" in status_payload["result_html"]
    assert 'href="/trino/details/' in status_payload["result_html"]
    assert "Known Query ID analysis" not in status_payload["result_html"]
    assert "Generating Python report" not in json.dumps(status_payload, sort_keys=True)

    assert final_response is not None
    assert final_response.status == 200
    assert "Trino Beta Query ID diagnosis" in final_response.body
    assert "Run Trino Beta" in final_response.body
    assert "complete Trino Beta product output for the selected Query ID" in final_response.body
    assert 'href="/trino/details/' in final_response.body
    assert 'href="/query/details/' not in final_response.body
    assert 'href="/optimizer"' not in final_response.body
    assert "SELECT" not in final_response.body
    assert "sensitive_table" not in final_response.body
    assert COORDINATOR_URL not in final_response.body
    assert str(tmp_path) not in final_response.body


def test_trino_beta_async_job_hides_network_failure_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _trino_settings(tmp_path)
    auth_header = tmp_path / "operator-auth-header.txt"
    auth_header.write_text("Authorization: RedactedSecret value\n", encoding="utf-8")
    settings = WebSettings(
        config=settings.config,
        repo_dir=settings.repo_dir,
        trino_beta_enabled=True,
        trino_coordinator_url=COORDINATOR_URL,
        trino_query_info_source_contract=settings.trino_query_info_source_contract,
        trino_auth_header_file=auth_header,
        selected_engine="trino",
    )
    store = WebJobStore()

    def failing_fetcher(*_args: object, **_kwargs: object) -> str:
        raise OSError(f"raw failure {COORDINATOR_URL} {QUERY_ID} RedactedSecret {tmp_path}")

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        failing_fetcher,
    )

    status, location = start_analyze_job(
        {"query_id": [QUERY_ID], "engine": ["trino"]},
        settings,
        store,
    )

    assert status == 303
    job_id = location.rsplit("/", 1)[-1]
    for _ in range(50):
        snapshot = store.get(job_id)
        if snapshot is not None and snapshot.status == "failed":
            break
        time.sleep(0.01)
    snapshot = store.get(job_id)
    assert snapshot is not None
    payload = json.loads(render_job_status_json(snapshot))
    rendered = json.dumps(payload, sort_keys=True)

    assert payload["status"] == "failed"
    assert payload["error_info"]["reason_code"] == "trino_beta.network_read_failed"
    assert (
        payload["error"]
        == "Trino Beta Query ID diagnosis could not read the bounded coordinator QueryInfo."
    )
    assert "Check coordinator reachability" in rendered
    assert COORDINATOR_URL not in rendered
    assert "RedactedSecret" not in rendered
    assert str(tmp_path) not in rendered


def test_trino_beta_failed_job_page_hides_network_failure_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _trino_settings(tmp_path)
    auth_header = tmp_path / "operator-auth-header.txt"
    auth_header.write_text("Authorization: RedactedSecret value\n", encoding="utf-8")
    settings = WebSettings(
        config=settings.config,
        repo_dir=settings.repo_dir,
        trino_beta_enabled=True,
        trino_coordinator_url=COORDINATOR_URL,
        trino_query_info_source_contract=settings.trino_query_info_source_contract,
        trino_auth_header_file=auth_header,
        selected_engine="trino",
    )
    store = WebJobStore()

    def failing_fetcher(*_args: object, **_kwargs: object) -> str:
        raise OSError(f"raw failure {COORDINATOR_URL} {QUERY_ID} RedactedSecret {tmp_path}")

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        failing_fetcher,
    )

    status, location = start_analyze_job(
        {"query_id": [QUERY_ID], "engine": ["trino"]},
        settings,
        store,
    )

    assert status == 303
    job_id = location.rsplit("/", 1)[-1]
    for _ in range(50):
        snapshot = store.get(job_id)
        if snapshot is not None and snapshot.status == "failed":
            break
        time.sleep(0.01)
    response = route_get_request(f"/jobs/{job_id}", settings, store)

    assert response is not None
    assert response.status == 200
    assert '<span class="progress-title">Trino failed</span>' in response.body
    assert (
        "Trino Beta Query ID diagnosis could not read the bounded coordinator QueryInfo"
        in response.body
    )
    assert "trino_beta.network_read_failed" in response.body
    assert "Check coordinator reachability" in response.body
    assert "Trino Beta Query ID diagnosis</h1>" not in response.body
    assert 'href="/query/details/' not in response.body
    assert 'href="/optimizer"' not in response.body
    assert COORDINATOR_URL not in response.body
    assert "RedactedSecret" not in response.body
    assert str(tmp_path) not in response.body


def test_trino_job_panel_uses_generic_title_and_trino_progress_copy() -> None:
    store = WebJobStore()
    snapshot = store.create(
        QUERY_ID,
        "analysis",
        form_values={"engine": "trino"},
        kind="trino_query",
    )
    html = render_job_panel(snapshot)
    assert '<span class="progress-title">Trino running</span>' in html
    assert "Checking Trino Query ID" in html
    assert "Reading bounded QueryInfo" in html
    assert "Building compact diagnosis" in html
    assert "Collecting or reusing profile" not in html
    assert "Generating Python report" not in html
    assert "optimizer" not in html.lower()


def test_trino_beta_job_route_preserves_beta_query_form(tmp_path: Path) -> None:
    settings = _trino_settings(tmp_path)
    store = WebJobStore()
    started = threading.Event()
    release = threading.Event()
    completed = threading.Event()

    def analysis_func(*_args: object) -> WebTrinoQueryAnalysisResult:
        started.set()
        release.wait(timeout=5)
        completed.set()
        return WebTrinoQueryAnalysisResult(
            query_id=QUERY_ID,
            diagnosis={"schema_version": "trino_compact_diagnosis_v1"},
        )

    status, location = start_analyze_job(
        {"query_id": [QUERY_ID], "engine": ["trino"]},
        settings,
        store,
        analysis_func=analysis_func,
    )

    assert status == 303
    job_id = location.rsplit("/", 1)[-1]
    assert started.wait(timeout=5)
    response = route_get_request(f"/jobs/{job_id}", settings, store)

    release.set()
    assert response is not None
    assert response.status == 200
    assert '<label for="query_id">Trino Query ID</label>' in response.body
    assert '<button class="run-button" type="submit" disabled>Running</button>' in response.body
    assert '<input type="hidden" name="engine" value="trino" data-engine-hidden>' in response.body
    assert '<span class="progress-title">Trino running</span>' in response.body
    assert "Collecting or reusing profile" not in response.body
    assert "Generating Python report" not in response.body
    assert "adds metadata when configured" not in response.body

    assert completed.wait(timeout=5)
    completed_response = route_get_request(f"/jobs/{job_id}", settings, store)
    assert completed_response is not None
    assert completed_response.status == 200
    assert '<label for="query_id">Trino Query ID</label>' in completed_response.body
    assert "Run Trino Beta" in completed_response.body
    assert '<input type="hidden" name="engine" value="trino" data-engine-hidden>' in (
        completed_response.body
    )


def test_trino_beta_cancel_route_preserves_beta_boundary(tmp_path: Path) -> None:
    settings = _trino_settings(tmp_path)
    store = WebJobStore()
    started = threading.Event()
    release = threading.Event()

    def analysis_func(*_args: object) -> WebTrinoQueryAnalysisResult:
        started.set()
        release.wait(timeout=5)
        return WebTrinoQueryAnalysisResult(
            query_id=QUERY_ID,
            diagnosis={"schema_version": "trino_compact_diagnosis_v1"},
        )

    status, location = start_analyze_job(
        {"query_id": [QUERY_ID], "engine": ["trino"]},
        settings,
        store,
        analysis_func=analysis_func,
    )

    assert status == 303
    job_id = location.rsplit("/", 1)[-1]
    assert started.wait(timeout=5)
    cancel_response = route_post_request(f"/jobs/{job_id}/cancel", {}, settings, store)
    release.set()
    snapshot = store.get(job_id)
    status_payload = json.loads(render_job_status_json(snapshot))
    page_response = route_get_request(f"/jobs/{job_id}", settings, store)

    assert cancel_response is not None
    assert cancel_response.status == 303
    assert cancel_response.location == f"/jobs/{job_id}"
    assert snapshot is not None
    assert snapshot.status == "cancelled"
    assert snapshot.kind == "trino_query"
    assert snapshot.result_html == ""
    assert status_payload["status"] == "cancelled"
    assert status_payload["kind"] == "trino_query"
    assert status_payload["result_html"] == ""
    assert status_payload["error"] == "Job stopped by user."
    assert page_response is not None
    assert page_response.status == 200
    assert '<span class="progress-title">Trino stopped</span>' in page_response.body
    assert "Job stopped by user." in page_response.body
    assert "Trino Beta Query ID diagnosis</h1>" not in page_response.body
    assert 'href="/query/details/' not in page_response.body
    assert 'href="/optimizer"' not in page_response.body
    assert COORDINATOR_URL not in page_response.body
    assert str(tmp_path) not in page_response.body


def test_trino_beta_job_does_not_inherit_impala_query_result_table() -> None:
    store = WebJobStore()
    first = store.create("abc:def", "analysis")
    store.complete(
        first.job_id,
        WebQueryAnalysisResult(
            query_id="abc:def",
            case={
                "query_id": "abc:def",
                "score": 2,
                "duration_sec": 4.0,
                "collection_status": "ok",
                "analysis_status": "ok",
                "metadata_status": "skipped",
                "table_stats_status": "not_checked",
                "score_reasons": ["memory estimate anomalies: 1"],
            },
        ),
    )

    trino_job = store.create(
        QUERY_ID,
        "analysis",
        form_values={"engine": "trino"},
        kind="trino_query",
    )

    assert trino_job.result_html == ""
    payload = json.loads(render_job_status_json(trino_job))
    assert payload["result_html"] == ""
    assert "Known Query ID analysis" not in render_job_panel(trino_job)
    assert "/query/details/abc%3Adef" not in render_job_panel(trino_job)


@pytest.mark.parametrize(
    "action",
    (
        "report",
        "python-report",
        "llm-report",
        "optimized-query",
        "validate-rewrite",
        "llm-actions",
        "case-actions",
    ),
)
def test_trino_beta_query_id_is_rejected_by_specific_query_action_routes(
    tmp_path: Path,
    action: str,
) -> None:
    settings = _trino_settings(tmp_path)

    class GuardedStore(WebJobStore):
        def create_query_report(self, query_id: str, *, report_variant: str = "python") -> object:
            raise AssertionError("Trino Beta Query ID must not create a Specific Query report job")

        def create_query_optimized_query(self, query_id: str) -> object:
            raise AssertionError(
                "Trino Beta Query ID must not create a Specific Query optimizer job"
            )

        def create_query_case_actions(self, query_id: str) -> object:
            raise AssertionError("Trino Beta Query ID must not create Specific Query action jobs")

    def fail_runner(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("Trino Beta Query ID must not run Specific Query commands")

    response = route_post_request(
        f"/query/details/{QUERY_ID}/{action}",
        {"external_rewrite_sql": ["select 1"]},
        settings,
        GuardedStore(),
        runner=fail_runner,
    )

    assert response is not None
    assert response.status == 400
    assert "Impala Query ID path usage requires query id shape" in response.body
    assert COORDINATOR_URL not in response.body
    assert str(tmp_path) not in response.body


@pytest.mark.parametrize(
    "suffix",
    (
        "",
        "/report",
        "/report.md",
        "/python-report",
        "/python-report.md",
        "/llm-report",
        "/llm-report.md",
        "/optimized-query",
    ),
)
def test_trino_beta_query_id_is_rejected_by_specific_query_get_routes(
    tmp_path: Path,
    suffix: str,
) -> None:
    settings = _trino_settings(tmp_path)

    response = route_get_request(
        f"/query/details/{QUERY_ID}{suffix}",
        settings,
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "Impala Query ID path usage requires query id shape" in response.body
    assert response.download_filename is None
    assert COORDINATOR_URL not in response.body
    assert str(tmp_path) not in response.body


def test_trino_beta_async_job_rejects_unconfigured_source_before_job_creation(
    tmp_path: Path,
) -> None:
    settings = WebSettings(config=tmp_path / "web.json")
    store = WebJobStore()

    def fail_if_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("Trino Beta job must not start without local beta config")

    status, body = start_analyze_job(
        {"query_id": [QUERY_ID], "engine": ["trino"]},
        settings,
        store,
        analysis_func=fail_if_called,
    )

    assert status == 400
    assert "Trino Beta Query ID diagnosis is not configured for the selected source." in body
    assert "Checking Trino Query ID" not in body
    assert "trino_coordinator_url" not in body
    assert "trino_query_info_source_contract" not in body
    assert str(tmp_path) not in body


def test_trino_beta_async_job_rejects_partial_source_before_job_creation(
    tmp_path: Path,
) -> None:
    settings = WebSettings(
        config=tmp_path / "web.json",
        clusters=(
            WebClusterConfig(
                key="partial",
                label="Partial Trino source",
                trino_beta_enabled=True,
                trino_coordinator_url=COORDINATOR_URL,
            ),
        ),
        active_cluster_key="partial",
    )
    store = WebJobStore()

    def fail_if_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("partial Trino Beta source must fail before async job creation")

    status, body = start_analyze_job(
        {"cluster_key": ["partial"], "query_id": [QUERY_ID], "engine": ["trino"]},
        settings,
        store,
        analysis_func=fail_if_called,
    )

    assert status == 400
    assert "Trino Beta Query ID diagnosis is not configured for the selected source." in body
    assert "Checking Trino Query ID" not in body
    assert QUERY_ID not in body
    assert COORDINATOR_URL not in body
    assert "trino_coordinator_url" not in body
    assert "trino_query_info_source_contract" not in body
    assert str(tmp_path) not in body


def test_trino_beta_running_is_server_gated(tmp_path: Path) -> None:
    settings = _trino_settings(tmp_path)
    config = parse_batch_run_config(
        {"engine": ["trino"], "scan_target": ["running"]},
        settings=settings,
    )
    config = config.__class__(**{**config.__dict__, "only_running": True, "include_running": True})

    with pytest.raises(WebError, match="Trino Beta Running scans are not supported"):
        build_batch_command("jobid", config, settings)


def test_trino_beta_recent_post_creates_beta_recent_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _trino_settings(tmp_path)
    store = WebJobStore()
    called = threading.Event()

    def fake_recent(*_args: object, **_kwargs: object) -> WebTrinoRecentScanResult:
        called.set()
        return WebTrinoRecentScanResult(
            rows=(
                WebTrinoRecentScanRow(
                    query_id=QUERY_ID,
                    status="ok",
                    lifecycle="finished",
                    parser_coverage="supported",
                    supported_attention_area_count=0,
                ),
            ),
            records_seen=1,
            records_selected=1,
            records_diagnosed=1,
            query_bound=50,
        )

    monkeypatch.setattr("query_doctor.web.batch_jobs.run_trino_recent_scan", fake_recent)

    status, body = start_batch_job(
        {"engine": ["trino"], "diagnosis_target": ["recent"]},
        settings,
        store,
    )

    assert status == 303
    assert body.startswith("/jobs/")
    assert called.wait(timeout=5)
    job = store.get(body.rsplit("/", 1)[-1])
    assert job is not None
    assert job.kind == "trino_recent"
    assert "Trino Beta Recent diagnosis" in job.result_html
    assert QUERY_ID in job.result_html
    assert_trino_beta_blocked_surfaces(job.result_html)
    assert 'href="/trino/details/' not in job.result_html


def test_trino_beta_recent_materializes_case_artifacts_for_selected_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _trino_settings(tmp_path)

    monkeypatch.setattr(
        "query_doctor.web.trino_recent.load_trino_coordinator_query_list",
        lambda *_args, **_kwargs: SimpleNamespace(
            records=(
                TrinoCoordinatorQueryListRecord(
                    query_id=QUERY_ID,
                    state="FINISHED",
                    end_time=datetime.now(timezone.utc),
                    elapsed_ms=2500,
                ),
            ),
            records_seen=1,
            source_contract=SimpleNamespace(max_query_ids=50),
        ),
    )
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    result = run_trino_recent_scan(
        BatchRunConfig(
            engine="trino",
            recent_window_minutes=30,
            triage_profile_limit=50,
            metadata_top_limit=0,
        ),
        settings,
    )

    assert result.records_diagnosed == 1
    row = result.rows[0]
    assert row.case_artifacts is not None
    analysis = json.loads(row.case_artifacts.analysis_path.read_text(encoding="utf-8"))
    assert analysis["workflow"] == "recent_selected_query"
    assert analysis["query_reference"]["value"] == "hidden"
    assert QUERY_ID not in row.case_artifacts.analysis_path.read_text(encoding="utf-8")
    html = render_trino_recent_scan_result(result)
    assert f'href="/trino/details/{row.case_artifacts.case_id}"' in html
    assert_trino_beta_blocked_surfaces(html, details_available=True)


def test_trino_beta_recent_result_renderer_marks_blocked_surfaces() -> None:
    html = render_trino_recent_scan_result(
        WebTrinoRecentScanResult(
            rows=(
                WebTrinoRecentScanRow(
                    query_id=QUERY_ID,
                    status="diagnosed",
                    lifecycle="failed",
                    parser_coverage="known",
                    supported_attention_area_count=1,
                    attention_areas=("trino_spill_observed",),
                ),
            ),
            records_seen=3,
            records_selected=1,
            records_diagnosed=1,
            query_bound=1,
            cluster_key="trino_beta_fixture",
        )
    )

    assert "Trino Beta Recent diagnosis" in html
    assert f"<code>{QUERY_ID}</code>" in html
    assert 'method="post" action="/analyze"' in html
    assert 'name="engine" value="trino"' in html
    assert 'name="diagnosis_target" value="query"' in html
    assert 'name="cluster_key" value="trino_beta_fixture"' in html
    assert f'name="query_id" value="{QUERY_ID}"' in html
    assert "Retained records:" in html
    assert "Contract bound:" in html
    assert_trino_beta_blocked_surfaces(html)
    assert 'href="/trino/details/' not in html


def test_trino_production_mode_recent_renderer_marks_local_boundary() -> None:
    html = render_trino_recent_scan_result(
        WebTrinoRecentScanResult(
            rows=(
                WebTrinoRecentScanRow(
                    query_id=QUERY_ID,
                    status="diagnosed",
                    lifecycle="finished",
                    parser_coverage="known",
                    supported_attention_area_count=1,
                    attention_areas=("trino_spill_observed",),
                ),
            ),
            records_seen=3,
            records_selected=1,
            records_diagnosed=1,
            query_bound=1,
            cluster_key="trino",
            support_mode="production",
        )
    )

    assert "Trino Recent diagnosis" in html
    assert "Trino Beta Recent diagnosis" not in html
    assert 'aria-label="Trino blocked surfaces"' in html
    assert 'aria-label="Open Trino Query ID diagnosis"' in html
    assert "Local boundary" in html
    assert "Trino Recent uses only the bounded retained coordinator list" in html
    assert 'href="/query/details/' not in html
    assert 'href="/python-report/' not in html
    assert 'href="/optimizer"' not in html


def test_trino_beta_recent_result_renderer_shows_safe_row_error_reason() -> None:
    html = render_trino_recent_scan_result(
        WebTrinoRecentScanResult(
            rows=(
                WebTrinoRecentScanRow(
                    query_id=QUERY_ID,
                    status="failed",
                    error="Trino Beta could not read the bounded coordinator QueryInfo.",
                    error_reason_code="trino_beta.network_read_failed",
                    error_next_step="Check coordinator reachability and the selected local auth mode.",
                ),
            ),
            records_seen=1,
            records_selected=1,
            records_diagnosed=0,
            query_bound=1,
            cluster_key="trino_beta_fixture",
        )
    )

    assert "trino_beta.network_read_failed" in html
    assert "Check coordinator reachability" in html
    assert COORDINATOR_URL not in html
    assert 'href="/query/details/' not in html
    assert 'href="/optimizer"' not in html


def test_trino_beta_recent_selector_filters_window_and_excludes_missing_timestamps() -> None:
    now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    selected, warnings = select_trino_recent_records(
        (
            TrinoCoordinatorQueryListRecord(
                query_id="20260618_115100_00001_abcde",
                state="FINISHED",
                end_time=now - timedelta(minutes=9),
                elapsed_ms=5000,
            ),
            TrinoCoordinatorQueryListRecord(
                query_id="20260618_110000_00002_abcde",
                state="FINISHED",
                end_time=now - timedelta(minutes=60),
                elapsed_ms=5000,
            ),
            TrinoCoordinatorQueryListRecord(
                query_id="20260618_115200_00003_abcde",
                state="FINISHED",
                elapsed_ms=5000,
            ),
        ),
        config=BatchRunConfig(
            engine="trino",
            recent_window_minutes=30,
            triage_profile_limit=50,
            metadata_top_limit=0,
            order="recent",
        ),
        query_bound=50,
        now=now,
    )

    assert [record.query_id for record in selected] == ["20260618_115100_00001_abcde"]
    assert warnings == [
        "Some Trino query-list records lacked timestamps and were excluded because the "
        "Recent window could not be verified."
    ]


def test_trino_beta_running_post_rejects_before_job_creation(tmp_path: Path) -> None:
    settings = _trino_settings(tmp_path)

    class GuardedStore(WebJobStore):
        def create_running_batch(self, form_values: dict[str, object] | None = None) -> object:
            raise AssertionError("forged Trino Beta Running POST must not create a job")

    store = GuardedStore()

    def fail_runner(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("forged Trino Beta Running POST must not run a command")

    status, body = start_running_job(
        {"engine": ["trino"], "diagnosis_target": ["recent"], "scan_target": ["running"]},
        settings,
        store,
        runner=fail_runner,
    )

    assert status == 400
    assert "Trino Beta Running scans are not supported" in body


@pytest.mark.parametrize(
    ("path", "form"),
    (
        (
            "/running/run",
            {"engine": ["trino"], "diagnosis_target": ["recent"], "scan_target": ["running"]},
        ),
    ),
)
def test_trino_beta_recent_and_running_routes_reject_before_job_creation(
    tmp_path: Path,
    path: str,
    form: dict[str, list[str]],
) -> None:
    settings = _trino_settings(tmp_path)

    class GuardedStore(WebJobStore):
        def create_batch(self, form_values: dict[str, object] | None = None) -> object:
            raise AssertionError("forged Trino Beta Recent route must not create a job")

        def create_running_batch(self, form_values: dict[str, object] | None = None) -> object:
            raise AssertionError("forged Trino Beta Running route must not create a job")

    def fail_runner(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("forged Trino Beta scan route must not run a command")

    response = route_post_request(path, form, settings, GuardedStore(), runner=fail_runner)

    assert response is not None
    assert response.status == 400
    assert "Trino Beta Running scans are not supported" in response.body
    assert COORDINATOR_URL not in response.body
    assert str(tmp_path) not in response.body


@pytest.mark.parametrize(
    ("form_patch", "message"),
    (
        (
            {"metadata_top_limit": ["1"]},
            "Trino Beta Recent does not support metadata collection.",
        ),
        (
            {"user": ["raw_user"]},
            "Trino Beta Recent does not support User, Pool, or query-type filters.",
        ),
        (
            {"pool": ["raw_pool"]},
            "Trino Beta Recent does not support User, Pool, or query-type filters.",
        ),
        (
            {"query_type": ["DDL"]},
            "Trino Beta Recent does not support User, Pool, or query-type filters.",
        ),
    ),
)
def test_trino_beta_recent_forbidden_options_reject_before_job_creation(
    tmp_path: Path,
    form_patch: dict[str, list[str]],
    message: str,
) -> None:
    settings = _trino_settings(tmp_path)

    class GuardedStore(WebJobStore):
        def create_batch(self, form_values: dict[str, object] | None = None) -> object:
            raise AssertionError("forged Trino Beta Recent route must not create a job")

    def fail_runner(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("forged Trino Beta Recent route must not run a command")

    form = {"engine": ["trino"], "diagnosis_target": ["recent"], **form_patch}
    response = route_post_request("/batch/run", form, settings, GuardedStore(), runner=fail_runner)

    assert response is not None
    assert response.status == 400
    assert message in response.body
    assert "raw_user" not in response.body
    assert "raw_pool" not in response.body
    assert COORDINATOR_URL not in response.body
    assert str(tmp_path) not in response.body


def test_recent_run_panel_exposes_engine_selector_without_secret_config(tmp_path: Path) -> None:
    settings = _trino_settings(tmp_path)

    html = render_batch_run_panel(settings, {"engine": "trino"}, diagnosis_target="query")

    assert "Trino Beta" in html
    assert "<small>Configured locally</small>" not in html
    assert "<small>Production</small>" not in html
    assert (
        "Running scans, query-history crawling, metadata collection, "
        "LLM reports, Query Optimizer jobs, generated SQL, and SQL execution "
        "remain unavailable" in html
    )
    assert '<label for="query_id">Trino Query ID</label>' in html
    assert 'placeholder="20260603_120102_00001_abcde"' in html
    assert "Run Trino Beta" in html
    assert "one bounded, pruned coordinator QueryInfo payload" in html
    assert (
        "Running scans, query-history crawling, metadata collection, "
        "LLM reports, Query Optimizer jobs, generated SQL, and SQL execution "
        "remain unavailable" in html
    )
    assert "raw-free Details view" in html
    assert "optimizer guidance" in html
    assert "collects or reuses the profile" not in html
    assert "prepares the Python report" not in html
    assert "adds metadata when configured" not in html
    assert 'name="engine"' in html
    assert 'value="trino"' in html
    assert COORDINATOR_URL not in html
    assert str(tmp_path) not in html


def test_recent_run_panel_uses_plain_trino_label_in_production_mode(
    tmp_path: Path,
) -> None:
    settings = _trino_settings(
        tmp_path,
        trino_support_mode="production",
        trino_beta_enabled=False,
    )

    html = render_batch_run_panel(settings, {"engine": "trino"}, diagnosis_target="query")

    assert "Trino Beta" not in html
    assert "<strong>Trino</strong>" in html
    assert "<small>Configured locally</small>" not in html
    assert "<small>Production</small>" not in html
    assert "Run Trino" in html
    assert "Run Trino Beta" not in html
    assert "Trino supports bounded retained-list Recent diagnosis" in html
    assert COORDINATOR_URL not in html
    assert str(tmp_path) not in html


def test_recent_run_panel_allows_trino_beta_recent_when_query_list_configured(
    tmp_path: Path,
) -> None:
    settings = _trino_settings(tmp_path)

    html = render_batch_run_panel(
        settings,
        {"engine": "trino", "diagnosis_target": "recent", "scan_target": "running"},
    )

    assert (
        'name="diagnosis_workflow" value="finished" data-diagnosis-workflow-choice checked' in html
    )
    assert '<form id="batch-form" class="batch-form"' in html
    assert '<div class=" manual-inputs-hidden" data-diagnosis-target-field="query">' in html
    assert '<label for="query_id">Trino Query ID</label>' in html
    assert '<input type="hidden" name="engine" value="trino" data-engine-hidden>' in html
    assert '<input type="hidden" name="scan_target" value="finished" data-scan-target-hidden>' in (
        html
    )
    assert 'action="/running/run"' not in html
    assert "Run scan" in html


def test_recent_run_panel_marks_trino_beta_source_without_local_config_echo(
    tmp_path: Path,
) -> None:
    contract = tmp_path / "trino-query-info-contract.json"
    auth_header = tmp_path / "trino-auth-header.txt"
    settings = WebSettings(
        config=tmp_path / "web.json",
        clusters=(
            WebClusterConfig(key="impala", label="Impala production"),
            WebClusterConfig(
                key="trino",
                label="Trino coordinator",
                trino_beta_enabled=True,
                trino_coordinator_url=COORDINATOR_URL,
                trino_query_info_source_contract=contract,
                trino_auth_header_file=auth_header,
            ),
        ),
        active_cluster_key="trino",
    )

    html = render_batch_run_panel(
        settings,
        {"cluster_key": "trino", "engine": "trino"},
        diagnosis_target="query",
    )

    assert (
        '<option value="impala" data-engine-impala-ready="true" '
        'data-engine-trino-ready="false" data-trino-beta-query-ready="false" '
        'data-trino-beta-recent-ready="false">Impala production</option>' in html
    )
    assert (
        '<option value="trino" selected data-engine-impala-ready="false" '
        'data-engine-trino-ready="true" data-trino-beta-query-ready="true" '
        'data-trino-beta-recent-ready="false" data-trino-display-label="Trino Beta">'
        "Trino coordinator - Trino Beta One Query ID</option>" in html
    )
    assert "coordinator.example.test" not in html
    assert "trino-query-info-contract.json" not in html
    assert "trino-auth-header.txt" not in html
    assert str(tmp_path) not in html


def test_recent_run_panel_does_not_mark_partial_trino_beta_source_ready(
    tmp_path: Path,
) -> None:
    settings = WebSettings(
        config=tmp_path / "web.json",
        clusters=(
            WebClusterConfig(
                key="partial",
                label="Partial Trino source",
                trino_beta_enabled=True,
                trino_coordinator_url=COORDINATOR_URL,
            ),
        ),
        active_cluster_key="partial",
        selected_engine="trino",
    )

    html = render_batch_run_panel(
        settings,
        {"cluster_key": "partial", "engine": "trino"},
        diagnosis_target="query",
    )

    assert (
        '<option value="partial" selected data-engine-impala-ready="true" '
        'data-engine-trino-ready="false" data-trino-beta-query-ready="false" '
        'data-trino-beta-recent-ready="false">'
        "Partial Trino source</option>" in html
    )
    assert "Partial Trino source - Trino Beta One Query ID" not in html
    assert "Trino requires trino_support_mode, coordinator URL, and source contracts" in html
    assert "Configure local Trino first" not in html
    assert (
        'name="engine_choice" value="trino" data-engine-choice disabled aria-disabled="true"'
        in html
    )
    assert '<input type="hidden" name="engine" value="impala" data-engine-hidden>' in html
    assert COORDINATOR_URL not in html
    assert "trino_coordinator_url" not in html
    assert "trino_query_info_source_contract" not in html
    assert str(tmp_path) not in html


def test_mixed_impala_trino_beta_source_keeps_recent_command_impala_only(
    tmp_path: Path,
) -> None:
    contract = tmp_path / "trino-query-info-contract.json"
    auth_header = tmp_path / "trino-auth-header.txt"
    settings = WebSettings(
        config=tmp_path / "web.json",
        repo_dir=tmp_path,
        clusters=(
            WebClusterConfig(
                key="mixed",
                label="Mixed source",
                cm_url="https://cm.example.test:7183/",
                cm_cluster="impala_cluster",
                cm_service="impala",
                trino_beta_enabled=True,
                trino_coordinator_url=COORDINATOR_URL,
                trino_query_info_source_contract=contract,
                trino_auth_header_file=auth_header,
            ),
        ),
        active_cluster_key="mixed",
    )

    html = render_batch_run_panel(
        settings,
        {"cluster_key": "mixed", "engine": "impala", "diagnosis_target": "recent"},
    )
    config = parse_batch_run_config(
        {"cluster_key": ["mixed"], "engine": ["impala"], "metadata_top_limit": ["0"]},
        settings=settings,
    )
    cmd, _out_dir = build_batch_command("b" * 32, config, settings)
    rendered_cmd = " ".join(cmd)

    assert (
        '<option value="mixed" selected data-engine-impala-ready="true" '
        'data-engine-trino-ready="true" data-trino-beta-query-ready="true" '
        'data-trino-beta-recent-ready="false" data-trino-display-label="Trino Beta">'
        "Mixed source - Trino Beta One Query ID</option>" in html
    )
    assert 'name="engine" value="impala" data-engine-hidden' in html
    assert "Run scan" in html
    assert COORDINATOR_URL not in html
    assert "trino-query-info-contract.json" not in html
    assert "trino-auth-header.txt" not in html
    assert "--cm-url https://cm.example.test:7183/" in rendered_cmd
    assert COORDINATOR_URL not in rendered_cmd
    assert "trino-query-info-contract.json" not in rendered_cmd
    assert "trino-auth-header.txt" not in rendered_cmd
    assert str(contract) not in rendered_cmd
    assert str(auth_header) not in rendered_cmd


def test_recent_run_panel_disables_trino_beta_until_local_config_exists(
    tmp_path: Path,
) -> None:
    settings = WebSettings(config=tmp_path / "web.json", selected_engine="trino")

    html = render_batch_run_panel(settings, {"engine": "trino"}, diagnosis_target="query")

    assert "Trino Beta" not in html
    assert "Trino requires trino_support_mode, coordinator URL, and source contracts" in html
    assert "Configure local Trino first" not in html
    assert (
        'name="engine_choice" value="trino" data-engine-choice disabled aria-disabled="true"'
        in html
    )
    assert '<input type="hidden" name="engine" value="impala" data-engine-hidden>' in html
    assert "coordinator.example.test" not in html
    assert str(tmp_path) not in html


def test_trino_beta_engine_default_loads_from_local_config(tmp_path: Path) -> None:
    contract = tmp_path / "trino-query-info-contract.json"
    contract.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    config = tmp_path / "web.json"
    config.write_text(
        json.dumps(
            {
                "engine": "trino",
                "trino_beta_enabled": True,
                "trino_coordinator_url": COORDINATOR_URL,
                "trino_query_info_source_contract": "trino-query-info-contract.json",
            }
        ),
        encoding="utf-8",
    )

    settings = build_web_settings(parse_args(["--config", str(config)]), cwd=tmp_path)

    assert settings.selected_engine == "trino"
    assert settings.trino_support_mode == "beta"
    assert settings.trino_beta_enabled is True
    assert settings.trino_query_info_source_contract == contract


def test_trino_support_mode_production_loads_from_local_config_without_legacy_beta(
    tmp_path: Path,
) -> None:
    contract = tmp_path / "trino-query-info-contract.json"
    contract.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    config = tmp_path / "web.json"
    config.write_text(
        json.dumps(
            {
                "engine": "trino",
                "trino_support_mode": "production",
                "trino_coordinator_url": COORDINATOR_URL,
                "trino_query_info_source_contract": "trino-query-info-contract.json",
            }
        ),
        encoding="utf-8",
    )

    assert validate_web_startup_config(config, cwd=tmp_path, env={}, require_cm=False) == []
    settings = build_web_settings(parse_args(["--config", str(config)]), cwd=tmp_path)

    assert settings.selected_engine == "trino"
    assert settings.trino_support_mode == "production"
    assert settings.trino_beta_enabled is False
    assert settings.trino_query_info_source_contract == contract


def test_trino_beta_kerberos_config_loads_from_local_config(tmp_path: Path) -> None:
    contract = tmp_path / "trino-query-info-contract.json"
    contract.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    krb5_config = tmp_path / "krb5.conf"
    krb5_config.write_text("[libdefaults]\n", encoding="utf-8")
    ca_cert = tmp_path / "trino-ca.pem"
    ca_cert.write_text("CERT\n", encoding="utf-8")
    config = tmp_path / "web.json"
    config.write_text(
        json.dumps(
            {
                "engine": "trino",
                "trino_beta_enabled": True,
                "trino_coordinator_url": COORDINATOR_URL,
                "trino_query_info_source_contract": "trino-query-info-contract.json",
                "trino_kerberos_principal": "sa@LESTA.HADOOP",
                "trino_kerberos_service_name": "HTTP",
                "trino_krb5_ccname": "FILE:/tmp/krb5cc_qd_trino",
                "trino_krb5_config": "krb5.conf",
                "trino_kerberos_ca_cert": "trino-ca.pem",
                "trino_kerberos_insecure_tls": True,
            }
        ),
        encoding="utf-8",
    )

    settings = build_web_settings(parse_args(["--config", str(config)]), cwd=tmp_path)

    assert settings.trino_kerberos_principal == "sa@LESTA.HADOOP"
    assert settings.trino_kerberos_service_name == "HTTP"
    assert settings.trino_krb5_ccname == "FILE:/tmp/krb5cc_qd_trino"
    assert settings.trino_krb5_config == krb5_config
    assert settings.trino_kerberos_ca_cert == ca_cert
    assert settings.trino_kerberos_insecure_tls is True


def test_trino_beta_query_analysis_uses_kerberos_spnego_fetcher(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _trino_settings(tmp_path)
    settings = WebSettings(
        config=settings.config,
        repo_dir=settings.repo_dir,
        trino_beta_enabled=True,
        trino_coordinator_url=COORDINATOR_URL,
        trino_query_info_source_contract=settings.trino_query_info_source_contract,
        trino_kerberos_principal="sa@LESTA.HADOOP",
        trino_krb5_ccname="FILE:/tmp/krb5cc_qd_trino",
        selected_engine="trino",
    )
    calls: list[tuple[str, str, str | None]] = []

    def fake_query_info(
        self: TrinoKerberosSpnegoFetcher,
        coordinator_url: str,
        *,
        query_id: str,
        max_bytes: int,
        timeout_seconds: int,
        auth_headers: dict[str, str] | None = None,
    ) -> str:
        calls.append((coordinator_url, query_id, self.krb5_ccname))
        assert auth_headers is None
        assert max_bytes == 65536
        assert timeout_seconds == 30
        return _raw_query_info_text()

    monkeypatch.setattr(TrinoKerberosSpnegoFetcher, "query_info", fake_query_info)

    result = run_trino_query_id_analysis(QUERY_ID, settings)

    assert calls == [(COORDINATOR_URL, QUERY_ID, "FILE:/tmp/krb5cc_qd_trino")]
    assert result.diagnosis["lifecycle"] == "finished"


def test_trino_beta_config_matrix_loads_top_level_cluster_and_mixed_sources(
    tmp_path: Path,
) -> None:
    top_contract = tmp_path / "top-trino-contract.json"
    cluster_contract = tmp_path / "cluster-trino-contract.json"
    mixed_contract = tmp_path / "mixed-trino-contract.json"
    for contract in (top_contract, cluster_contract, mixed_contract):
        contract.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")

    top_config = tmp_path / "top-web.json"
    top_config.write_text(
        json.dumps(
            {
                "engine": "trino",
                "trino_beta_enabled": True,
                "trino_coordinator_url": COORDINATOR_URL,
                "trino_query_info_source_contract": top_contract.name,
            }
        ),
        encoding="utf-8",
    )
    cluster_config = tmp_path / "cluster-web.json"
    cluster_config.write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "id": "impala",
                        "label": "Impala production",
                        "query_profile_source": "impala",
                        "impala_profile_hosts": ["127.0.0.1"],
                    },
                    {
                        "id": "trino",
                        "label": "Trino coordinator",
                        "trino_beta_enabled": True,
                        "trino_coordinator_url": COORDINATOR_URL,
                        "trino_query_info_source_contract": cluster_contract.name,
                    },
                    {
                        "id": "mixed",
                        "label": "Mixed source",
                        "query_profile_source": "impala",
                        "impala_profile_hosts": ["127.0.0.2"],
                        "trino_beta_enabled": True,
                        "trino_coordinator_url": COORDINATOR_URL,
                        "trino_query_info_source_contract": mixed_contract.name,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    assert validate_web_startup_config(top_config, cwd=tmp_path, env={}, require_cm=False) == []
    assert validate_web_startup_config(cluster_config, cwd=tmp_path, env={}, require_cm=False) == []
    top_settings = build_web_settings(parse_args(["--config", str(top_config)]), cwd=tmp_path)
    cluster_settings = build_web_settings(
        parse_args(["--config", str(cluster_config)]), cwd=tmp_path
    )
    trino_settings = settings_for_cluster_key(cluster_settings, "trino")
    mixed_settings = settings_for_cluster_key(cluster_settings, "mixed")
    html = render_batch_run_panel(
        cluster_settings,
        {"cluster_key": "impala", "engine": "impala"},
        diagnosis_target="query",
    )

    assert top_settings.selected_engine == "trino"
    assert top_settings.trino_query_info_source_contract == top_contract
    assert cluster_settings.active_cluster_key == "impala"
    assert cluster_settings.trino_beta_enabled is False
    assert trino_settings.trino_beta_enabled is True
    assert trino_settings.trino_query_info_source_contract == cluster_contract
    assert mixed_settings.query_profile_source == "impala"
    assert mixed_settings.impala_profile_hosts == ("127.0.0.2",)
    assert mixed_settings.trino_query_info_source_contract == mixed_contract
    assert (
        '<option value="trino" data-engine-impala-ready="false" '
        'data-engine-trino-ready="true" data-trino-beta-query-ready="true" '
        'data-trino-beta-recent-ready="false" data-trino-display-label="Trino Beta">'
        "Trino coordinator - Trino Beta One Query ID</option>" in html
    )
    assert (
        '<option value="mixed" data-engine-impala-ready="true" '
        'data-engine-trino-ready="true" data-trino-beta-query-ready="true" '
        'data-trino-beta-recent-ready="false" data-trino-display-label="Trino Beta">'
        "Mixed source - Trino Beta One Query ID</option>" in html
    )
    assert "Trino Beta is configured for another local source" in html
    assert "Configure local Trino first" not in html
    assert (
        'name="engine_choice" value="trino" data-engine-choice disabled aria-disabled="true"'
        not in html
    )
    assert COORDINATOR_URL not in html
    assert top_contract.name not in html
    assert cluster_contract.name not in html
    assert mixed_contract.name not in html
    assert str(tmp_path) not in html


def test_trino_beta_startup_validation_does_not_require_cm_settings(tmp_path: Path) -> None:
    contract = tmp_path / "trino-query-info-contract.json"
    contract.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    config = tmp_path / "web.json"
    config.write_text(
        json.dumps(
            {
                "engine": "trino",
                "trino_beta_enabled": True,
                "trino_coordinator_url": COORDINATOR_URL,
                "trino_query_info_source_contract": "trino-query-info-contract.json",
            }
        ),
        encoding="utf-8",
    )

    assert validate_web_startup_config(config, cwd=tmp_path, env={}) == []


def test_trino_beta_config_matrix_rejects_partial_cluster_without_echo(
    tmp_path: Path,
) -> None:
    config = tmp_path / "web.json"
    config.write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "id": "impala",
                        "label": "Impala production",
                        "query_profile_source": "impala",
                        "impala_profile_hosts": ["127.0.0.1"],
                    },
                    {
                        "id": "partial",
                        "label": "Partial Trino source",
                        "trino_beta_enabled": True,
                        "trino_coordinator_url": COORDINATOR_URL,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(WebError) as exc:
        validate_web_startup_config(config, cwd=tmp_path, env={}, require_cm=False)

    rendered = str(exc.value)
    assert "Trino local config requires trino_query_info_source_contract." in rendered
    assert "Partial Trino source" not in rendered
    assert COORDINATOR_URL not in rendered
    assert str(tmp_path) not in rendered


def test_trino_beta_startup_validation_rejects_missing_contract_without_path_echo(
    tmp_path: Path,
) -> None:
    config = tmp_path / "web.json"
    config.write_text(
        json.dumps(
            {
                "engine": "trino",
                "trino_beta_enabled": True,
                "trino_coordinator_url": COORDINATOR_URL,
                "trino_query_info_source_contract": "missing-contract.json",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(WebError) as exc:
        validate_web_startup_config(config, cwd=tmp_path, env={})

    rendered = str(exc.value)
    assert (
        "Trino local config has an invalid source contract, coordinator URL, "
        "or auth reference." in rendered
    )
    assert str(tmp_path) not in rendered
    assert "missing-contract.json" not in rendered


def test_trino_beta_startup_validation_rejects_invalid_coordinator_url_without_echo(
    tmp_path: Path,
) -> None:
    contract = tmp_path / "trino-query-info-contract.json"
    contract.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    raw_url = "ftp://coordinator.example.test:8443/ui?token=SecretValue"
    config = tmp_path / "web.json"
    config.write_text(
        json.dumps(
            {
                "engine": "trino",
                "trino_beta_enabled": True,
                "trino_coordinator_url": raw_url,
                "trino_query_info_source_contract": "trino-query-info-contract.json",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(WebError) as exc:
        validate_web_startup_config(config, cwd=tmp_path, env={})

    rendered = str(exc.value)
    assert (
        "Trino local config has an invalid source contract, coordinator URL, "
        "or auth reference." in rendered
    )
    assert raw_url not in rendered
    assert "SecretValue" not in rendered
    assert "coordinator.example.test" not in rendered
    assert str(tmp_path) not in rendered


def test_trino_beta_startup_validation_rejects_invalid_auth_header_without_secret_echo(
    tmp_path: Path,
) -> None:
    contract = tmp_path / "trino-query-info-contract.json"
    contract.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    auth_header = tmp_path / "trino-auth-header.txt"
    auth_header.write_text("Authorization: SecretValue\nX-Other: leak\n", encoding="utf-8")
    config = tmp_path / "web.json"
    config.write_text(
        json.dumps(
            {
                "engine": "trino",
                "trino_beta_enabled": True,
                "trino_coordinator_url": COORDINATOR_URL,
                "trino_query_info_source_contract": "trino-query-info-contract.json",
                "trino_auth_header_file": "trino-auth-header.txt",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(WebError) as exc:
        validate_web_startup_config(config, cwd=tmp_path, env={})

    rendered = str(exc.value)
    assert (
        "Trino local config has an invalid source contract, coordinator URL, "
        "or auth reference." in rendered
    )
    assert "SecretValue" not in rendered
    assert str(tmp_path) not in rendered
    assert "trino-auth-header.txt" not in rendered


def test_trino_beta_startup_validation_rejects_combined_auth_modes_without_secret_echo(
    tmp_path: Path,
) -> None:
    contract = tmp_path / "trino-query-info-contract.json"
    contract.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    auth_header = tmp_path / "trino-auth-header.txt"
    auth_header.write_text("Authorization: SecretValue\n", encoding="utf-8")
    config = tmp_path / "web.json"
    config.write_text(
        json.dumps(
            {
                "engine": "trino",
                "trino_beta_enabled": True,
                "trino_coordinator_url": COORDINATOR_URL,
                "trino_query_info_source_contract": "trino-query-info-contract.json",
                "trino_auth_header_file": "trino-auth-header.txt",
                "trino_kerberos_principal": "sa@LESTA.HADOOP",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(WebError) as exc:
        validate_web_startup_config(config, cwd=tmp_path, env={})

    rendered = str(exc.value)
    assert (
        "Trino local config has an invalid source contract, coordinator URL, "
        "or auth reference." in rendered
    )
    assert "SecretValue" not in rendered
    assert str(tmp_path) not in rendered
    assert "trino-auth-header.txt" not in rendered


def test_trino_beta_startup_validation_rejects_partial_auth_config_without_echo(
    tmp_path: Path,
) -> None:
    auth_header = tmp_path / "trino-auth-header.txt"
    auth_header.write_text("Authorization: SecretValue\n", encoding="utf-8")
    config = tmp_path / "web.json"
    config.write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "id": "trino",
                        "label": "Trino coordinator",
                        "trino_auth_header_file": "trino-auth-header.txt",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(WebError) as exc:
        validate_web_startup_config(config, cwd=tmp_path, env={}, require_cm=False)

    rendered = str(exc.value)
    assert "Trino local config requires trino_support_mode=beta or production." in rendered
    assert "SecretValue" not in rendered
    assert str(tmp_path) not in rendered
    assert "trino-auth-header.txt" not in rendered


def test_trino_startup_validation_rejects_production_mode_with_legacy_beta_flag(
    tmp_path: Path,
) -> None:
    contract = tmp_path / "trino-query-info-contract.json"
    contract.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    config = tmp_path / "web.json"
    config.write_text(
        json.dumps(
            {
                "engine": "trino",
                "trino_support_mode": "production",
                "trino_beta_enabled": True,
                "trino_coordinator_url": COORDINATOR_URL,
                "trino_query_info_source_contract": "trino-query-info-contract.json",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(WebError) as exc:
        validate_web_startup_config(config, cwd=tmp_path, env={}, require_cm=False)

    rendered = str(exc.value)
    assert "trino_beta_enabled is a legacy beta-only setting" in rendered
    assert "SecretValue" not in rendered
    assert COORDINATOR_URL not in rendered
    assert str(tmp_path) not in rendered
    assert "trino-query-info-contract.json" not in rendered


def test_trino_beta_startup_validation_rejects_top_level_partial_auth_config_without_echo(
    tmp_path: Path,
) -> None:
    auth_header = tmp_path / "trino-auth-header.txt"
    auth_header.write_text("Authorization: SecretValue\n", encoding="utf-8")
    config = tmp_path / "web.json"
    config.write_text(
        json.dumps({"trino_auth_header_file": "trino-auth-header.txt"}),
        encoding="utf-8",
    )

    with pytest.raises(WebError) as exc:
        validate_web_startup_config(config, cwd=tmp_path, env={}, require_cm=False)

    rendered = str(exc.value)
    assert "Trino local config requires trino_support_mode=beta or production." in rendered
    assert "SecretValue" not in rendered
    assert str(tmp_path) not in rendered
    assert "trino-auth-header.txt" not in rendered


def _trino_settings(
    tmp_path: Path,
    *,
    trino_support_mode: Literal["off", "beta", "production"] = "beta",
    trino_beta_enabled: bool = True,
) -> WebSettings:
    config = tmp_path / "web.json"
    config.write_text("{}", encoding="utf-8")
    contract = tmp_path / "trino-query-info-contract.json"
    contract.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    query_list_contract = tmp_path / "trino-query-list-contract.json"
    query_list_contract.write_text(
        json.dumps(_safe_query_list_contract_payload()),
        encoding="utf-8",
    )
    return WebSettings(
        config=config,
        repo_dir=tmp_path,
        trino_support_mode=trino_support_mode,
        trino_beta_enabled=trino_beta_enabled,
        trino_coordinator_url=COORDINATOR_URL,
        trino_query_info_source_contract=contract,
        trino_query_list_source_contract=query_list_contract,
        selected_engine="trino",
    )


def _completed_trino_job(result: WebTrinoQueryAnalysisResult):
    store = WebJobStore()
    snapshot = store.create(
        QUERY_ID,
        "analysis",
        form_values={"engine": "trino"},
        kind="trino_query",
    )
    store.complete(snapshot.job_id, result)
    completed = store.get(snapshot.job_id)
    assert completed is not None
    return completed


def _safe_contract_payload() -> dict[str, object]:
    return {
        "source_contract_version": TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_VERSION,
        "source_type": "coordinator_query_info",
        "query_info_contract_version": TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION,
        "trino_version_family": "477",
        "auth_reference": {
            "kind": "operator_managed_reference",
            "label": "external_ref_01",
        },
        "query_bound": {
            "kind": "explicit_query_id",
            "max_query_ids": 1,
        },
        "bounds": {
            "max_bytes": 65536,
            "max_query_info_depth": 16,
            "timeout_seconds": 30,
        },
        "redaction": {
            "redaction_review_required": True,
            "raw_payload_storage": "forbidden",
            "normalized_fact_storage": "allowed",
            "browser_report_output": "blocked",
        },
    }


def _safe_query_list_contract_payload() -> dict[str, object]:
    return {
        "source_contract_version": TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_VERSION,
        "source_type": TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE,
        "query_list_contract_version": TRINO_COORDINATOR_QUERY_LIST_CONTRACT_VERSION,
        "trino_version_family": "477",
        "auth_reference": {
            "kind": "operator_managed_reference",
            "label": "external_ref_01",
        },
        "query_bound": {
            "kind": "bounded_retained_query_list",
            "max_query_ids": 50,
        },
        "bounds": {
            "max_bytes": 65536,
            "max_query_list_depth": 12,
            "timeout_seconds": 30,
        },
        "redaction": {
            "redaction_review_required": True,
            "raw_payload_storage": "forbidden",
            "normalized_fact_storage": "allowed",
            "browser_report_output": "blocked",
        },
    }


def _raw_query_info_text() -> str:
    return json.dumps(
        {
            "queryId": QUERY_ID,
            "state": "FINISHED",
            "query": "SELECT secret_col FROM sensitive_table",
            "session": {
                "user": "operator_user",
                "source": "adhoc_console",
            },
            "self": COORDINATOR_URL + "/ui/query.html?" + QUERY_ID,
            "outputStage": {
                "stageId": "stage-raw-id",
                "tasks": [
                    {
                        "taskId": "task-raw-id",
                        "worker": "worker-a.example.net",
                        "path": "synthetic_local_path_marker",
                    }
                ],
            },
            "queryStats": {
                "elapsedTime": "2.50s",
                "queuedTime": "100ms",
                "planningTime": "200ms",
                "executionTime": "2.00s",
                "totalCpuTime": "1.25s",
                "processedInputPositions": 123,
                "processedInputDataSize": "1MB",
                "outputPositions": 7,
                "outputDataSize": "2kB",
                "peakTotalMemoryReservation": "3MB",
                "spilledDataSize": "0B",
                "fullyBlocked": False,
                "totalTasks": 4,
                "failedTasks": 0,
            },
        }
    )
