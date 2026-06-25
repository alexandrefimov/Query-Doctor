from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from query_doctor.engines import get_engine_adapter
from query_doctor.engines.capabilities import engine_capabilities
from query_doctor.trino.browser_report_regression import (
    TRINO_BROWSER_REPORT_LLM_REPORTS,
    TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
    TRINO_BROWSER_REPORT_REGRESSION_GATE,
    TRINO_BROWSER_REPORT_REGRESSION_STATUS,
    TRINO_BROWSER_REPORT_REGRESSION_SUMMARY_KIND,
    TRINO_BROWSER_REPORT_SQL_EXECUTION,
    audit_trino_browser_report_regression,
    browser_report_regression_summary_payload,
)
from scripts import audit_trino_browser_report_regression as audit_script


def test_trino_browser_report_regression_audit_records_open_gate() -> None:
    result = audit_trino_browser_report_regression()

    assert result.ok
    assert result.family_count == 5
    assert result.required_test_count == 31
    assert result.present_test_count == 31
    assert result.source_file_count == 2
    assert result.required_route_capability_count == 3
    assert result.product_capability_count == 5
    assert result.open_blocker_count == 5
    assert result.adapter_validated_reports_enabled is False
    assert result.status_counts["details_raw_free_regressions_tracked"] == 1
    assert result.status_counts["python_report_raw_free_regressions_tracked"] == 1
    assert result.status_counts["optimizer_guidance_raw_free_regressions_tracked"] == 1
    assert result.status_counts["error_and_unsupported_workflow_regressions_tracked"] == 1
    assert result.status_counts["product_surface_static_boundary_regressions_tracked"] == 1
    assert result.test_family_counts["materialized_details_browser_regressions"] == 5
    assert result.test_family_counts["python_report_browser_regressions"] == 3
    assert result.test_family_counts["optimizer_guidance_browser_regressions"] == 3
    assert result.test_family_counts["error_and_unsupported_workflow_regressions"] == 10
    assert result.test_family_counts["product_surface_static_boundary_regressions"] == 10
    assert result.route_capability_counts == {
        "materialized_details": 1,
        "materialized_optimizer_guidance": 1,
        "materialized_python_report": 1,
    }
    assert result.browser_report_requirement_tracking_counts == {"accepted": 47}
    assert result.production_review_tracking_counts == {"accepted": 8}
    assert result.issue_counts == {}

    summary = browser_report_regression_summary_payload(result, status="ok")
    assert summary["summary_kind"] == TRINO_BROWSER_REPORT_REGRESSION_SUMMARY_KIND
    assert summary["closure_gate"] == TRINO_BROWSER_REPORT_REGRESSION_GATE
    assert summary["browser_report_regression_status"] == TRINO_BROWSER_REPORT_REGRESSION_STATUS
    assert summary["broader_production_closure_status"] == "not_closed"
    assert summary["details_case_view"] == "raw_free_materialized"
    assert summary["python_report"] == "raw_free_materialized"
    assert summary["optimizer_guidance"] == "raw_free_materialized"
    assert summary["llm_reports"] == TRINO_BROWSER_REPORT_LLM_REPORTS
    assert summary["trino_sql_execution"] == TRINO_BROWSER_REPORT_SQL_EXECUTION
    for key in (
        "raw_sql_output",
        "query_id_output",
        "url_output",
        "local_path_output",
        "metadata_identifier_output",
        "secret_output",
        "runtime_internal_output",
    ):
        assert summary[key] == TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS
    assert summary["adapter_validated_reports"] == "blocked"
    assert summary["browser_report_requirement_tracking_counts"] == {"accepted": 47}
    assert summary["production_review_profile"] == "production_review_browser_report_v1"
    assert summary["production_review_profile_status"] == "ready"
    assert summary["production_review_requirements"]["required_families"] == [
        "materialized_details_browser_regressions",
        "python_report_browser_regressions",
        "optimizer_guidance_browser_regressions",
        "error_and_unsupported_workflow_regressions",
        "product_surface_static_boundary_regressions",
    ]
    assert summary["production_review_requirements"]["required_route_capabilities"] == [
        "materialized_details",
        "materialized_python_report",
        "materialized_optimizer_guidance",
    ]
    assert summary["production_review_requirements"]["required_download_tests"] == [
        "web_trino_beta_query::test_trino_beta_python_report_markdown_download_stays_raw_free",
        "web_trino_beta_query::test_trino_beta_optimizer_guidance_markdown_download_stays_raw_free",
    ]
    assert summary["production_review_tracking_counts"] == {"accepted": 8}
    assert len(summary["production_review_tracking"]) == 8
    assert len(summary["browser_report_requirement_tracking"]) == 47
    assert (
        _browser_report_tracking_status(
            summary,
            family_id="materialized_details_browser_regressions",
            requirement_type="test",
            requirement_id=(
                "web_trino_beta_query::"
                "test_trino_beta_details_route_renders_raw_free_materialized_case"
            ),
        )
        == "accepted"
    )
    assert (
        _browser_report_tracking_status(
            summary,
            family_id="route_capabilities",
            requirement_type="route_capability",
            requirement_id="materialized_python_report",
        )
        == "accepted"
    )
    assert (
        _browser_report_tracking_status(
            summary,
            family_id="product_surfaces",
            requirement_type="product_surface",
            requirement_id="raw_sql_output_blocked",
        )
        == "accepted"
    )
    assert summary["issue_counts"] == {}


def test_trino_browser_report_regression_cli_writes_path_free_summary(
    tmp_path: Path, capsys
) -> None:
    summary_path = tmp_path / "browser-report-summary-output"

    exit_code = audit_script.main(["--summary-json", str(summary_path)])

    captured = capsys.readouterr()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "Trino browser/report regression audit: ok" in captured.out
    assert "browser_report_regression=not_closed" in captured.out
    assert "llm_reports=not_wired" in captured.out
    assert "raw_outputs=blocked" in captured.out
    assert "trino_sql_execution=not_performed" in captured.out
    assert "required_tests=31" in captured.out
    assert "present_tests=31" in captured.out
    assert "browser_report_requirements=accepted=47" in captured.out
    assert "profile=production_review_browser_report_v1" in captured.out
    assert "requirements=accepted=8" in captured.out
    assert "Issues: none" in captured.out
    assert payload["summary_kind"] == TRINO_BROWSER_REPORT_REGRESSION_SUMMARY_KIND
    assert payload["status"] == "ok"
    assert payload["browser_report_requirement_tracking_counts"] == {"accepted": 47}
    assert payload["production_review_tracking_counts"] == {"accepted": 8}
    assert payload["issue_counts"] == {}
    assert str(tmp_path) not in captured.out
    assert "browser-report-summary-output" not in captured.out
    assert captured.err == ""


def test_trino_browser_report_regression_rejects_missing_test() -> None:
    result = audit_trino_browser_report_regression(
        test_catalog={
            "web_trino_beta_query": set(),
            "product_surface_boundary_audit": set(),
        }
    )

    assert not result.ok
    assert result.issue_counts["trino_browser_report_test_missing"] == 31
    assert result.browser_report_requirement_tracking_counts == {
        "accepted": 16,
        "missing": 31,
    }
    assert result.production_review_tracking_counts == {
        "accepted": 5,
        "insufficient": 3,
    }


def test_trino_browser_report_regression_rejects_missing_test_file() -> None:
    result = audit_trino_browser_report_regression(test_catalog={})

    assert not result.ok
    assert result.issue_counts["trino_browser_report_test_file_missing"] == 31
    assert result.browser_report_requirement_tracking_counts == {
        "accepted": 16,
        "missing": 31,
    }
    assert result.production_review_tracking_counts == {
        "accepted": 4,
        "insufficient": 4,
    }


def test_trino_browser_report_regression_rejects_route_drift() -> None:
    capabilities = tuple(
        replace(capability, route_path="/trino/details/{case_id}/report")
        if capability.surface_id == "materialized_python_report"
        else capability
        for capability in engine_capabilities("trino")
    )

    result = audit_trino_browser_report_regression(capabilities=capabilities)

    assert not result.ok
    assert result.issue_counts["trino_browser_report_route_capability_route_path_drift"] == 1
    assert result.browser_report_requirement_tracking_counts == {
        "accepted": 46,
        "invalid": 1,
    }
    assert result.production_review_tracking_counts == {
        "accepted": 7,
        "insufficient": 1,
    }


def test_trino_browser_report_regression_rejects_forbidden_product_capability() -> None:
    capabilities = tuple(engine_capabilities("trino"))
    forbidden = replace(
        capabilities[0],
        surface_id="llm_report",
        route_path="/trino/details/{case_id}?report=llm",
        product_surface_allowed=True,
    )

    result = audit_trino_browser_report_regression(capabilities=(*capabilities, forbidden))

    assert not result.ok
    assert result.issue_counts["trino_browser_report_forbidden_product_capability"] == 1
    assert result.browser_report_requirement_tracking_counts == {
        "accepted": 46,
        "invalid": 1,
    }
    assert result.production_review_tracking_counts == {
        "accepted": 7,
        "insufficient": 1,
    }


def test_trino_browser_report_regression_rejects_adapter_validated_reports() -> None:
    adapter = replace(get_engine_adapter("trino"), supports_validated_reports=True)

    result = audit_trino_browser_report_regression(trino_adapter=adapter)

    assert not result.ok
    assert result.adapter_validated_reports_enabled is True
    assert result.issue_counts["trino_browser_report_adapter_validated_reports_enabled"] == 1
    assert result.browser_report_requirement_tracking_counts == {
        "accepted": 46,
        "invalid": 1,
    }
    assert result.production_review_tracking_counts == {
        "accepted": 7,
        "insufficient": 1,
    }


def test_trino_browser_report_regression_rejects_missing_review_family(
    monkeypatch,
) -> None:
    from query_doctor.trino import browser_report_regression as browser_report

    monkeypatch.setattr(
        browser_report,
        "TRINO_BROWSER_REPORT_REQUIRED_REVIEW_FAMILIES",
        (*browser_report.TRINO_BROWSER_REPORT_REQUIRED_REVIEW_FAMILIES, "missing_family"),
    )

    result = browser_report.audit_trino_browser_report_regression()

    assert not result.ok
    assert result.issue_counts["trino_browser_report_production_review_gap"] == 1
    assert result.production_review_tracking_counts == {
        "accepted": 7,
        "insufficient": 1,
    }


def _browser_report_tracking_status(
    summary: dict[str, object],
    *,
    family_id: str,
    requirement_type: str,
    requirement_id: str,
) -> str:
    tracking_items = summary["browser_report_requirement_tracking"]
    assert isinstance(tracking_items, list)
    for item in tracking_items:
        assert isinstance(item, dict)
        if (
            item["family_id"] == family_id
            and item["requirement_type"] == requirement_type
            and item["requirement_id"] == requirement_id
        ):
            status = item["tracking_status"]
            assert isinstance(status, str)
            return status
    raise AssertionError(f"missing browser/report tracking for {requirement_id}")
