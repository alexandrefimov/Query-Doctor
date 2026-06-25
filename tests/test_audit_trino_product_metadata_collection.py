from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from query_doctor.analyzer.engine_facts import engine_fact_namespace_definitions
from query_doctor.engines import get_engine_adapter
from query_doctor.trino.product_metadata_collection import (
    TRINO_PRODUCT_METADATA_COLLECTION_GATE,
    TRINO_PRODUCT_METADATA_COLLECTION_STATUS,
    TRINO_PRODUCT_METADATA_COLLECTION_SUMMARY_KIND,
    TRINO_PRODUCT_METADATA_PRODUCTION_REVIEW_PROFILE,
    TRINO_PRODUCT_METADATA_PRODUCTION_REVIEW_PROFILE_STATUS,
    TRINO_PRODUCT_METADATA_REQUIRED_OPEN_BLOCKER_FAMILIES,
    TRINO_PRODUCT_METADATA_REQUIRED_PRODUCT_SURFACE_REQUIREMENTS,
    TRINO_PRODUCT_METADATA_REQUIRED_REDACTION_FIELDS,
    TRINO_PRODUCT_METADATA_REQUIRED_SOURCE_FAMILIES,
    TRINO_PRODUCT_METADATA_REQUIRED_SOURCE_SURFACES,
    TRINO_PRODUCT_METADATA_REQUIRED_SQL_EXECUTION_STATUSES,
    TRINO_PRODUCT_METADATA_SQL_EXECUTION_STATUS,
    TRINO_USER_SQL_EXECUTION_STATUS,
    TRINO_PRODUCT_METADATA_FAMILIES,
    audit_trino_product_metadata_collection,
    product_metadata_collection_summary_payload,
)
from query_doctor.trino.source_contract_registry import trino_source_contract_registry
from scripts import audit_trino_product_metadata_collection as audit_script


def test_trino_product_metadata_collection_audit_records_open_gate() -> None:
    result = audit_trino_product_metadata_collection()

    assert result.ok
    assert result.family_count == 4
    assert result.source_backed_family_count == 3
    assert result.source_requirement_count == 3
    assert result.required_fact_count == 8
    assert result.open_blocker_count == 4
    assert result.forbidden_source_type_count == 0
    assert result.product_capability_count == 5
    assert result.adapter_metadata_collection_enabled is False
    assert result.status_counts["contract_check_only"] == 1
    assert result.status_counts["dev_only_aggregate_cli_summary"] == 1
    assert result.status_counts["local_aggregate_import_only"] == 1
    assert result.status_counts["open_required_future_work"] == 1
    assert result.source_contract_counts == {"metadata_source_contract": 3}
    assert result.sql_execution_counts == {
        "not_performed": 2,
        "python_owned_metadata_statements_only": 1,
    }
    assert result.product_metadata_requirement_tracking_counts == {"accepted": 14}
    assert result.production_review_tracking_counts == {"accepted": 8}
    assert result.issue_counts == {}

    summary = product_metadata_collection_summary_payload(result, status="ok")
    assert summary["summary_kind"] == TRINO_PRODUCT_METADATA_COLLECTION_SUMMARY_KIND
    assert summary["closure_gate"] == TRINO_PRODUCT_METADATA_COLLECTION_GATE
    assert summary["product_metadata_collection_status"] == TRINO_PRODUCT_METADATA_COLLECTION_STATUS
    assert summary["broader_production_closure_status"] == "not_closed"
    assert summary["trino_sql_execution"] == TRINO_USER_SQL_EXECUTION_STATUS
    assert summary["metadata_cli_sql_execution"] == TRINO_PRODUCT_METADATA_SQL_EXECUTION_STATUS
    assert summary["product_metadata_surfaces"] == "blocked"
    assert summary["metadata_summary_boundary"] == "aggregate_only_not_diagnosis"
    assert summary["adapter_metadata_collection"] == "blocked"
    assert summary["open_blocker_count"] == 4
    assert summary["product_metadata_requirement_tracking_counts"] == {"accepted": 14}
    assert summary["production_review_profile"] == TRINO_PRODUCT_METADATA_PRODUCTION_REVIEW_PROFILE
    assert (
        summary["production_review_profile_status"]
        == TRINO_PRODUCT_METADATA_PRODUCTION_REVIEW_PROFILE_STATUS
    )
    assert summary["production_review_requirements"] == {
        "required_open_blocker_families": list(
            TRINO_PRODUCT_METADATA_REQUIRED_OPEN_BLOCKER_FAMILIES
        ),
        "required_product_surface_requirements": list(
            TRINO_PRODUCT_METADATA_REQUIRED_PRODUCT_SURFACE_REQUIREMENTS
        ),
        "required_redaction_fields": list(TRINO_PRODUCT_METADATA_REQUIRED_REDACTION_FIELDS),
        "required_source_families": list(TRINO_PRODUCT_METADATA_REQUIRED_SOURCE_FAMILIES),
        "required_source_surfaces": list(TRINO_PRODUCT_METADATA_REQUIRED_SOURCE_SURFACES),
        "required_sql_execution_statuses": list(
            TRINO_PRODUCT_METADATA_REQUIRED_SQL_EXECUTION_STATUSES
        ),
    }
    assert summary["production_review_tracking_counts"] == {"accepted": 8}
    assert len(summary["production_review_tracking"]) == 8
    assert len(summary["product_metadata_requirement_tracking"]) == 14
    assert _production_review_tracking_status(summary, "require_redaction_blocks") == "accepted"
    assert (
        _product_metadata_tracking_status(
            summary,
            family_id="metadata_fact_namespace",
            requirement_type="fact",
            requirement_id="no_metadata_identifier_output",
        )
        == "accepted"
    )
    assert (
        _product_metadata_tracking_status(
            summary,
            family_id="metadata_cli_summary_builder",
            requirement_type="source",
            requirement_id="trino_metadata_cli_summary",
        )
        == "accepted"
    )
    assert summary["issue_counts"] == {}


def test_trino_product_metadata_collection_cli_writes_path_free_summary(
    tmp_path: Path, capsys
) -> None:
    summary_path = tmp_path / "metadata-collection-summary-output"

    exit_code = audit_script.main(["--summary-json", str(summary_path)])

    captured = capsys.readouterr()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "Trino product metadata collection audit: ok" in captured.out
    assert "product_metadata_collection=not_closed" in captured.out
    assert "trino_sql_execution=not_performed" in captured.out
    assert "metadata_cli_sql_execution=python_owned_metadata_statements_only_dev_gate" in (
        captured.out
    )
    assert "adapter_metadata_collection=blocked" in captured.out
    assert "product_metadata_requirements=accepted=14" in captured.out
    assert "Production review profile: profile=production_review_metadata_v1" in captured.out
    assert "status=ready" in captured.out
    assert "requirements=accepted=8" in captured.out
    assert "Issues: none" in captured.out
    assert payload["summary_kind"] == TRINO_PRODUCT_METADATA_COLLECTION_SUMMARY_KIND
    assert payload["status"] == "ok"
    assert payload["product_metadata_requirement_tracking_counts"] == {"accepted": 14}
    assert payload["production_review_profile_status"] == "ready"
    assert payload["production_review_tracking_counts"] == {"accepted": 8}
    assert payload["issue_counts"] == {}
    assert str(tmp_path) not in captured.out
    assert "metadata-collection-summary-output" not in captured.out
    assert captured.err == ""


def test_trino_product_metadata_collection_rejects_missing_metadata_source() -> None:
    registry = tuple(
        entry
        for entry in trino_source_contract_registry()
        if entry.source_type != "local_metadata_summary_import"
    )

    result = audit_trino_product_metadata_collection(source_registry=registry)

    assert not result.ok
    assert result.issue_counts["trino_product_metadata_source_missing"] == 1
    assert result.product_metadata_requirement_tracking_counts == {
        "accepted": 13,
        "missing": 1,
    }
    assert result.production_review_tracking_counts == {
        "accepted": 6,
        "insufficient": 2,
    }


def test_trino_product_metadata_collection_rejects_source_surface_drift() -> None:
    registry = tuple(
        replace(entry, product_surfaces="trino_metadata_collection")
        if entry.source_type == "local_metadata_summary_import"
        else entry
        for entry in trino_source_contract_registry()
    )

    result = audit_trino_product_metadata_collection(source_registry=registry)

    assert not result.ok
    assert result.issue_counts["trino_product_metadata_source_product_surfaces_drift"] == 1
    assert result.product_metadata_requirement_tracking_counts == {
        "accepted": 13,
        "invalid": 1,
    }
    assert result.production_review_tracking_counts == {
        "accepted": 6,
        "insufficient": 2,
    }


def test_trino_product_metadata_collection_rejects_adapter_metadata_collection() -> None:
    adapter = replace(get_engine_adapter("trino"), supports_metadata_collection=True)

    result = audit_trino_product_metadata_collection(trino_adapter=adapter)

    assert not result.ok
    assert result.adapter_metadata_collection_enabled is True
    assert result.issue_counts["trino_product_metadata_adapter_enabled"] == 1
    assert result.product_metadata_requirement_tracking_counts == {
        "accepted": 13,
        "invalid": 1,
    }


def test_trino_product_metadata_collection_rejects_forbidden_source_type() -> None:
    registry = tuple(trino_source_contract_registry())
    forbidden = replace(registry[0], source_type="trino_metadata_object_crawl")

    result = audit_trino_product_metadata_collection(source_registry=(*registry, forbidden))

    assert not result.ok
    assert result.forbidden_source_type_count == 1
    assert result.issue_counts["trino_product_metadata_forbidden_source_registered"] == 1
    assert result.product_metadata_requirement_tracking_counts == {
        "accepted": 13,
        "invalid": 1,
    }


def test_trino_product_metadata_collection_rejects_missing_fact() -> None:
    definitions = tuple(
        definition
        for definition in engine_fact_namespace_definitions()
        if definition.fact_id != "no_metadata_identifier_output"
    )

    result = audit_trino_product_metadata_collection(fact_definitions=definitions)

    assert not result.ok
    assert result.issue_counts["trino_product_metadata_required_fact_missing"] == 1
    assert result.product_metadata_requirement_tracking_counts == {
        "accepted": 13,
        "missing": 1,
    }
    assert result.production_review_tracking_counts == {
        "accepted": 7,
        "insufficient": 1,
    }


def test_trino_product_metadata_collection_rejects_missing_production_review_family() -> None:
    families = tuple(
        family
        for family in TRINO_PRODUCT_METADATA_FAMILIES
        if family.family_id != "metadata_cli_summary_builder"
    )

    result = audit_trino_product_metadata_collection(families=families)
    summary = product_metadata_collection_summary_payload(result, status="failed")

    assert not result.ok
    assert result.issue_counts["trino_product_metadata_production_review_gap"] == 3
    assert result.production_review_tracking_counts == {
        "accepted": 5,
        "insufficient": 3,
    }
    assert summary["production_review_profile_status"] == "failed"
    assert _production_review_tracking_status(summary, "require_source_families") == (
        "insufficient"
    )
    assert _production_review_tracking_status(summary, "require_source_surfaces") == (
        "insufficient"
    )
    assert _production_review_tracking_status(summary, "require_sql_execution_policy") == (
        "insufficient"
    )


def _product_metadata_tracking_status(
    summary: dict[str, object],
    *,
    family_id: str,
    requirement_type: str,
    requirement_id: str,
) -> str:
    tracking_items = summary["product_metadata_requirement_tracking"]
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
    raise AssertionError(f"missing product metadata tracking for {requirement_id}")


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
