from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from query_doctor.engines import get_engine_adapter
from query_doctor.engines.capabilities import engine_capabilities
from query_doctor.trino.report_optimizer_safety import (
    TRINO_REPORT_OPTIMIZER_GENERATED_SQL_STATUS,
    TRINO_REPORT_OPTIMIZER_LLM_REPORTS_STATUS,
    TRINO_REPORT_OPTIMIZER_PRODUCTION_REVIEW_PROFILE,
    TRINO_REPORT_OPTIMIZER_PRODUCTION_REVIEW_PROFILE_STATUS,
    TRINO_REPORT_OPTIMIZER_QUERY_OPTIMIZER_JOBS_STATUS,
    TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_CAPABILITIES,
    TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_FAMILIES,
    TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_POLICY_FIELDS,
    TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_PRODUCT_SURFACE_REQUIREMENTS,
    TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_VALIDATORS,
    TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_VALIDATOR_SENTINELS,
    TRINO_REPORT_OPTIMIZER_SAFETY_GATE,
    TRINO_REPORT_OPTIMIZER_SAFETY_STATUS,
    TRINO_REPORT_OPTIMIZER_SAFETY_SUMMARY_KIND,
    TRINO_REPORT_OPTIMIZER_SOURCE_BOUNDARY,
    TRINO_REPORT_OPTIMIZER_SQL_EXECUTION_STATUS,
    TRINO_REPORT_OPTIMIZER_FAMILIES,
    audit_trino_report_optimizer_safety,
    report_optimizer_safety_summary_payload,
)
from scripts import audit_trino_report_optimizer_safety as audit_script


def test_trino_report_optimizer_safety_audit_records_open_gate() -> None:
    result = audit_trino_report_optimizer_safety()

    assert result.ok
    assert result.family_count == 3
    assert result.required_capability_count == 2
    assert result.product_capability_count == 5
    assert result.policy_field_count == 6
    assert result.validation_sentinel_count == 8
    assert result.validator_check_count == 16
    assert result.open_blocker_count == 3
    assert result.adapter_validated_reports_enabled is False
    assert result.status_counts["raw_free_materialized_python_report"] == 1
    assert result.status_counts["raw_free_guidance_only_optimizer"] == 1
    assert result.status_counts["unsupported_surfaces_blocked"] == 1
    assert result.validator_rejection_counts == {
        "optimizer_guidance": 8,
        "python_report": 8,
    }
    assert result.report_optimizer_requirement_tracking_counts == {"accepted": 30}
    assert result.production_review_tracking_counts == {"accepted": 5}
    assert result.issue_counts == {}

    summary = report_optimizer_safety_summary_payload(result, status="ok")
    assert summary["summary_kind"] == TRINO_REPORT_OPTIMIZER_SAFETY_SUMMARY_KIND
    assert summary["closure_gate"] == TRINO_REPORT_OPTIMIZER_SAFETY_GATE
    assert summary["report_optimizer_safety_status"] == TRINO_REPORT_OPTIMIZER_SAFETY_STATUS
    assert summary["broader_production_closure_status"] == "not_closed"
    assert summary["source_boundary"] == TRINO_REPORT_OPTIMIZER_SOURCE_BOUNDARY
    assert summary["python_report"] == "raw_free_materialized"
    assert summary["trusted_reports"] == "python_report_only"
    assert summary["optimizer_guidance"] == "raw_free_materialized"
    assert summary["optimizer_behavior"] == "guidance_only"
    assert summary["llm_reports"] == TRINO_REPORT_OPTIMIZER_LLM_REPORTS_STATUS
    assert summary["query_optimizer_jobs"] == TRINO_REPORT_OPTIMIZER_QUERY_OPTIMIZER_JOBS_STATUS
    assert summary["generated_sql"] == TRINO_REPORT_OPTIMIZER_GENERATED_SQL_STATUS
    assert summary["trino_sql_execution"] == TRINO_REPORT_OPTIMIZER_SQL_EXECUTION_STATUS
    assert summary["adapter_validated_reports"] == "blocked"
    assert summary["report_optimizer_requirement_tracking_counts"] == {"accepted": 30}
    assert summary["production_review_profile"] == TRINO_REPORT_OPTIMIZER_PRODUCTION_REVIEW_PROFILE
    assert (
        summary["production_review_profile_status"]
        == TRINO_REPORT_OPTIMIZER_PRODUCTION_REVIEW_PROFILE_STATUS
    )
    assert summary["production_review_requirements"] == {
        "required_capabilities": list(TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_CAPABILITIES),
        "required_families": list(TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_FAMILIES),
        "required_policy_fields": list(TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_POLICY_FIELDS),
        "required_product_surface_requirements": list(
            TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_PRODUCT_SURFACE_REQUIREMENTS
        ),
        "required_validator_sentinels": list(
            TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_VALIDATOR_SENTINELS
        ),
        "required_validators": list(TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_VALIDATORS),
    }
    assert summary["production_review_tracking_counts"] == {"accepted": 5}
    assert len(summary["production_review_tracking"]) == 5
    assert len(summary["report_optimizer_requirement_tracking"]) == 30
    assert (
        _production_review_tracking_status(
            summary,
            "require_validator_sentinel_matrix",
        )
        == "accepted"
    )
    assert (
        _report_optimizer_tracking_status(
            summary,
            family_id="python_report_validation",
            requirement_type="capability",
            requirement_id="materialized_python_report",
        )
        == "accepted"
    )
    assert (
        _report_optimizer_tracking_status(
            summary,
            family_id="raw_source_policy",
            requirement_type="policy",
            requirement_id="llm_reports",
        )
        == "accepted"
    )
    assert (
        _report_optimizer_tracking_status(
            summary,
            family_id="optimizer_guidance",
            requirement_type="validator_sentinel",
            requirement_id="generated_sql_wording",
        )
        == "accepted"
    )
    assert (
        _report_optimizer_tracking_status(
            summary,
            family_id="product_surfaces",
            requirement_type="product_surface",
            requirement_id="query_optimizer_jobs_blocked",
        )
        == "accepted"
    )
    assert summary["issue_counts"] == {}


def test_trino_report_optimizer_safety_cli_writes_path_free_summary(tmp_path: Path, capsys) -> None:
    summary_path = tmp_path / "report-optimizer-summary-output"

    exit_code = audit_script.main(["--summary-json", str(summary_path)])

    captured = capsys.readouterr()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "Trino report optimizer safety audit: ok" in captured.out
    assert "report_optimizer_safety=not_closed" in captured.out
    assert "source_boundary=materialized_raw_free_case_facts" in captured.out
    assert "llm_reports=not_wired" in captured.out
    assert "query_optimizer_jobs=blocked" in captured.out
    assert "generated_sql=blocked" in captured.out
    assert "trino_sql_execution=not_performed" in captured.out
    assert "report_optimizer_requirements=accepted=30" in captured.out
    assert "Production review: review=report_optimizer" in captured.out
    assert "status=ready" in captured.out
    assert "requirements=accepted=5" in captured.out
    assert "Issues: none" in captured.out
    assert payload["summary_kind"] == TRINO_REPORT_OPTIMIZER_SAFETY_SUMMARY_KIND
    assert payload["status"] == "ok"
    assert payload["report_optimizer_requirement_tracking_counts"] == {"accepted": 30}
    assert payload["production_review_profile_status"] == "ready"
    assert payload["production_review_tracking_counts"] == {"accepted": 5}
    assert payload["issue_counts"] == {}
    assert str(tmp_path) not in captured.out
    assert "report-optimizer-summary-output" not in captured.out
    assert captured.err == ""


def test_trino_report_optimizer_safety_rejects_missing_capability() -> None:
    capabilities = tuple(
        capability
        for capability in engine_capabilities("trino")
        if capability.surface_id != "materialized_optimizer_guidance"
    )

    result = audit_trino_report_optimizer_safety(capabilities=capabilities)

    assert not result.ok
    assert result.issue_counts["trino_report_optimizer_capability_missing"] == 1
    assert result.report_optimizer_requirement_tracking_counts == {
        "accepted": 29,
        "missing": 1,
    }
    assert result.production_review_tracking_counts == {
        "accepted": 4,
        "insufficient": 1,
    }


def test_trino_report_optimizer_safety_rejects_capability_route_drift() -> None:
    capabilities = tuple(
        replace(capability, route_path="/trino/details/{case_id}/optimized-query")
        if capability.surface_id == "materialized_optimizer_guidance"
        else capability
        for capability in engine_capabilities("trino")
    )

    result = audit_trino_report_optimizer_safety(capabilities=capabilities)

    assert not result.ok
    assert result.issue_counts["trino_report_optimizer_capability_route_path_drift"] == 1
    assert result.report_optimizer_requirement_tracking_counts == {
        "accepted": 29,
        "invalid": 1,
    }
    assert result.production_review_tracking_counts == {
        "accepted": 4,
        "insufficient": 1,
    }


def test_trino_report_optimizer_safety_rejects_forbidden_product_capability() -> None:
    capabilities = tuple(engine_capabilities("trino"))
    forbidden = replace(
        capabilities[0],
        surface_id="query_optimizer_job",
        input_kind="trino_generated_sql",
        product_surface_allowed=True,
    )

    result = audit_trino_report_optimizer_safety(capabilities=(*capabilities, forbidden))

    assert not result.ok
    assert result.issue_counts["trino_report_optimizer_forbidden_product_capability"] == 1
    assert result.report_optimizer_requirement_tracking_counts == {
        "accepted": 29,
        "invalid": 1,
    }
    assert result.production_review_tracking_counts == {
        "accepted": 4,
        "insufficient": 1,
    }


def test_trino_report_optimizer_safety_rejects_adapter_validated_reports() -> None:
    adapter = replace(get_engine_adapter("trino"), supports_validated_reports=True)

    result = audit_trino_report_optimizer_safety(trino_adapter=adapter)

    assert not result.ok
    assert result.adapter_validated_reports_enabled is True
    assert result.issue_counts["trino_report_optimizer_adapter_validated_reports_enabled"] == 1
    assert result.report_optimizer_requirement_tracking_counts == {
        "accepted": 29,
        "invalid": 1,
    }
    assert result.production_review_tracking_counts == {
        "accepted": 4,
        "insufficient": 1,
    }


def test_trino_report_optimizer_safety_rejects_raw_policy_drift() -> None:
    result = audit_trino_report_optimizer_safety(
        raw_policy={
            "python_report": "raw_free_materialized",
            "optimizer_guidance": "raw_free_materialized",
            "trusted_reports": "python_report_only",
            "optimizer_behavior": "query_optimizer_job",
            "llm_reports": "wired",
            "sql_execution": "performed",
        }
    )

    assert not result.ok
    assert result.issue_counts["trino_report_optimizer_raw_policy_drift"] == 3
    assert result.report_optimizer_requirement_tracking_counts == {
        "accepted": 27,
        "invalid": 3,
    }
    assert result.production_review_tracking_counts == {
        "accepted": 4,
        "insufficient": 1,
    }


def test_trino_report_optimizer_safety_rejects_validator_drift() -> None:
    result = audit_trino_report_optimizer_safety(report_validator=lambda _text: [])

    assert not result.ok
    assert result.issue_counts["trino_report_optimizer_validator_failed_to_reject"] == 8
    assert result.report_optimizer_requirement_tracking_counts == {
        "accepted": 22,
        "invalid": 8,
    }
    assert result.production_review_tracking_counts == {
        "accepted": 4,
        "insufficient": 1,
    }


def test_trino_report_optimizer_safety_rejects_missing_review_family() -> None:
    families = tuple(
        family
        for family in TRINO_REPORT_OPTIMIZER_FAMILIES
        if family.family_id != "blocked_report_optimizer_surfaces"
    )

    result = audit_trino_report_optimizer_safety(families=families)
    summary = report_optimizer_safety_summary_payload(result, status="failed")

    assert not result.ok
    assert result.issue_counts["trino_report_optimizer_production_review_gap"] == 1
    assert result.production_review_tracking_counts == {
        "accepted": 4,
        "insufficient": 1,
    }
    assert summary["production_review_profile_status"] == "failed"
    assert _production_review_tracking_status(summary, "require_review_families") == (
        "insufficient"
    )


def _report_optimizer_tracking_status(
    summary: dict[str, object],
    *,
    family_id: str,
    requirement_type: str,
    requirement_id: str,
) -> str:
    tracking_items = summary["report_optimizer_requirement_tracking"]
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
    raise AssertionError(f"missing report optimizer tracking for {requirement_id}")


def _production_review_tracking_status(
    summary: dict[str, object],
    requirement_id: str,
) -> str:
    tracking_items = summary["production_review_tracking"]
    assert isinstance(tracking_items, list)
    for item in tracking_items:
        assert isinstance(item, dict)
        if item["requirement_id"] == requirement_id:
            status = item["tracking_status"]
            assert isinstance(status, str)
            return status
    raise AssertionError(f"missing production review tracking for {requirement_id}")
