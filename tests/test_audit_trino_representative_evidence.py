from __future__ import annotations

import json
from pathlib import Path

from query_doctor.trino.representative_evidence import (
    TRINO_COMPACT_READINESS_SUMMARY_KIND,
    TRINO_EVIDENCE_HANDOFF_SUITE_SUMMARY_KIND,
    TRINO_PRODUCT_SURFACE_AUDIT_SUMMARY_KIND,
    TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE,
    TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_KINDS,
    TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_STATUSES,
    TRINO_REPRESENTATIVE_EVIDENCE_GATE,
    TRINO_REPRESENTATIVE_EVIDENCE_STATUS,
    TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND,
    TRINO_SUPPORT_GAP_SUMMARY_KIND,
    TrinoRepresentativeEvidenceRequirements,
    audit_trino_representative_evidence,
    representative_evidence_requirements_for_profile,
    representative_evidence_summary_payload,
)
from scripts import audit_trino_representative_evidence as audit_script


def test_trino_representative_evidence_default_gate_is_not_closed() -> None:
    requirements = TrinoRepresentativeEvidenceRequirements()
    result = audit_trino_representative_evidence([], requirements=requirements)

    assert result.ok
    assert result.summary_input_count == 0
    assert result.evidence_unit_count == 0
    assert result.issue_counts == {}

    summary = representative_evidence_summary_payload(
        result,
        requirements=requirements,
        status="ok",
    )
    assert summary["summary_kind"] == TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND
    assert summary["closure_gate"] == TRINO_REPRESENTATIVE_EVIDENCE_GATE
    assert summary["representative_evidence_status"] == TRINO_REPRESENTATIVE_EVIDENCE_STATUS
    assert summary["broader_production_closure_status"] == "not_closed"
    assert summary["trino_sql_execution"] == "not_performed"
    assert summary["breadth_profile_status"] == "not_required"
    assert summary["breadth_requirement_tracking_counts"] == {"not_required": 21}
    assert summary["requirements"]["requirement_profile"] == "custom"
    assert summary["counters"]["issues"] == {}


def test_trino_representative_evidence_aggregates_retained_raw_free_summaries() -> None:
    requirements = TrinoRepresentativeEvidenceRequirements(
        require_min_summary_inputs=2,
        require_min_summary_kinds=2,
        require_min_evidence_units=7,
        require_min_trino_version_families=2,
        require_min_source_contracts=1,
        require_min_source_schemas=1,
        require_min_lifecycles=2,
        require_min_connector_family_categories=1,
        require_min_source_granularities=1,
        require_min_verification_scopes=1,
        require_min_support_statuses=1,
        required_summary_kinds=(
            TRINO_EVIDENCE_HANDOFF_SUITE_SUMMARY_KIND,
            TRINO_COMPACT_READINESS_SUMMARY_KIND,
        ),
        required_summary_statuses=("ok",),
        required_trino_version_families=("477", "478"),
        required_source_contracts=("synthetic_trino_event_listener_v1",),
        required_source_schemas=("engine_fact_boundary_v1",),
        required_lifecycles=("finished",),
        required_connector_family_categories=("lakehouse",),
        required_source_granularities=("one_query_boundary",),
        required_verification_scopes=("comparable_one_query_rerun",),
        required_support_statuses=("bounded_raw_free_preview",),
    )

    result = audit_trino_representative_evidence(
        [_handoff_suite_payload(), _readiness_suite_payload()],
        requirements=requirements,
    )

    assert result.ok
    assert result.summary_input_count == 2
    assert result.evidence_unit_count == 7
    assert result.breadth_requirement_tracking_counts == {"accepted": 21}
    assert result.summary_kind_counts == {
        TRINO_COMPACT_READINESS_SUMMARY_KIND: 1,
        TRINO_EVIDENCE_HANDOFF_SUITE_SUMMARY_KIND: 1,
    }
    assert result.status_counts == {"ok": 2}
    assert result.trino_version_family_counts == {"477": 2, "478": 1}
    assert result.source_contract_counts == {"synthetic_trino_event_listener_v1": 2}
    assert result.connector_family_category_counts == {"lakehouse": 2}
    assert result.source_granularity_counts == {"one_query_boundary": 7}
    assert result.verification_scope_counts == {"comparable_one_query_rerun": 7}
    assert result.support_status_counts == {"bounded_raw_free_preview": 7}


def test_trino_representative_evidence_production_review_profile_accepts_breadth() -> None:
    requirements = representative_evidence_requirements_for_profile(
        TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE
    )

    result = audit_trino_representative_evidence(
        [
            _handoff_suite_payload(),
            _readiness_suite_payload(),
            _product_surface_payload(),
            _support_gap_payload(),
        ],
        requirements=requirements,
    )
    summary = representative_evidence_summary_payload(
        result,
        requirements=requirements,
        status="ok",
    )

    assert result.ok
    assert summary["breadth_profile_status"] == "ready"
    assert summary["breadth_requirement_tracking_counts"] == {
        "accepted": 13,
        "not_required": 8,
    }
    assert _breadth_tracking_status(summary, "require_summary_kinds") == "accepted"
    assert _breadth_tracking_status(summary, "require_summary_statuses") == "accepted"
    assert _breadth_tracking_status(summary, "require_min_trino_version_families") == "accepted"
    assert _breadth_tracking_status(summary, "require_support_statuses") == "accepted"
    assert _breadth_tracking_status(summary, "require_source_contracts") == "not_required"
    assert summary["requirements"]["requirement_profile"] == (
        TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE
    )
    assert summary["requirements"]["require_min_summary_inputs"] == 4
    assert summary["requirements"]["require_summary_kinds"] == sorted(
        TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_KINDS
    )
    assert summary["requirements"]["require_summary_statuses"] == list(
        TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_STATUSES
    )
    assert summary["requirements"]["require_min_lifecycles"] == 2
    assert summary["requirements"]["require_support_statuses"] == ["bounded_raw_free_preview"]


def test_trino_representative_evidence_production_review_profile_rejects_gaps() -> None:
    requirements = representative_evidence_requirements_for_profile(
        TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE
    )

    result = audit_trino_representative_evidence(
        [_readiness_suite_payload()],
        requirements=requirements,
    )
    summary = representative_evidence_summary_payload(
        result,
        requirements=requirements,
        status="failed",
    )

    assert not result.ok
    assert summary["breadth_profile_status"] == "failed"
    assert summary["breadth_requirement_tracking_counts"] == {
        "accepted": 8,
        "insufficient": 5,
        "not_required": 8,
    }
    assert _breadth_tracking_status(summary, "require_min_summary_inputs") == "insufficient"
    assert _breadth_tracking_status(summary, "require_summary_kinds") == "insufficient"
    assert _breadth_tracking_status(summary, "require_min_source_contracts") == "insufficient"
    assert (
        _breadth_tracking_status(summary, "require_min_connector_family_categories")
        == "insufficient"
    )
    assert result.issue_counts["trino_representative_evidence_summary_count_gap"] == 1
    assert result.issue_counts["trino_representative_evidence_summary_kind_gap"] == 3
    assert result.issue_counts["trino_representative_evidence_source_contract_gap"] == 1
    assert result.issue_counts["trino_representative_evidence_connector_family_gap"] == 1
    assert result.issue_counts["trino_representative_evidence_lifecycle_gap"] == 1


def test_trino_representative_evidence_cli_writes_path_free_summary(
    tmp_path: Path,
    capsys,
) -> None:
    handoff_summary = tmp_path / "secret-trino-handoff-suite-summary.json"
    readiness_summary = tmp_path / "secret-trino-readiness-suite-summary.json"
    audit_summary = tmp_path / "secret-trino-representative-summary.json"
    handoff_summary.write_text(json.dumps(_handoff_suite_payload()), encoding="utf-8")
    readiness_summary.write_text(json.dumps(_readiness_suite_payload()), encoding="utf-8")
    product_surface_summary = tmp_path / "secret-trino-surface-summary.json"
    support_gap_summary = tmp_path / "secret-trino-support-gap-summary.json"
    product_surface_summary.write_text(json.dumps(_product_surface_payload()), encoding="utf-8")
    support_gap_summary.write_text(json.dumps(_support_gap_payload()), encoding="utf-8")
    capsys.readouterr()

    exit_code = audit_script.main(
        [
            "--summary-input-json",
            str(handoff_summary),
            "--summary-input-json",
            str(readiness_summary),
            "--summary-input-json",
            str(product_surface_summary),
            "--summary-input-json",
            str(support_gap_summary),
            "--require-min-summary-inputs",
            "4",
            "--require-min-summary-kinds",
            "4",
            "--require-min-evidence-units",
            "7",
            "--require-min-trino-version-families",
            "2",
            "--require-breadth-profile",
            TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE,
            "--require-summary-kind",
            TRINO_EVIDENCE_HANDOFF_SUITE_SUMMARY_KIND,
            "--require-summary-kind",
            TRINO_COMPACT_READINESS_SUMMARY_KIND,
            "--require-summary-kind",
            TRINO_PRODUCT_SURFACE_AUDIT_SUMMARY_KIND,
            "--require-summary-kind",
            TRINO_SUPPORT_GAP_SUMMARY_KIND,
            "--require-summary-status",
            "ok",
            "--require-trino-version-family",
            "477",
            "--require-trino-version-family",
            "478",
            "--require-source-contract",
            "synthetic_trino_event_listener_v1",
            "--require-source-schema",
            "engine_fact_boundary_v1",
            "--require-lifecycle",
            "finished",
            "--require-connector-family-category",
            "lakehouse",
            "--require-source-granularity",
            "one_query_boundary",
            "--require-verification-scope",
            "comparable_one_query_rerun",
            "--require-support-status",
            "bounded_raw_free_preview",
            "--summary-json",
            str(audit_summary),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(audit_summary.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "Trino representative evidence audit: ok" in captured.out
    assert "representative_evidence=not_closed" in captured.out
    assert "trino_sql_execution=not_performed" in captured.out
    assert "summary_inputs=4" in captured.out
    assert "summary_kinds=trino_compact_readiness_summary_v1=1" in captured.out
    assert "trino_product_surface_boundary_audit_v1=1" in captured.out
    assert "trino_support_gap_matrix_audit_v1=1" in captured.out
    assert "evidence_units=7" in captured.out
    assert "breadth_requirements=accepted=21" in captured.out
    assert "Issues: none" in captured.out
    assert summary["summary_kind"] == TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND
    assert summary["status"] == "ok"
    assert summary["breadth_profile_status"] == "ready"
    assert summary["breadth_requirement_tracking_counts"] == {"accepted": 21}
    assert summary["requirements"]["requirement_profile"] == (
        TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE
    )
    assert summary["summary_input_count"] == 4
    assert summary["evidence_unit_count"] == 7
    assert summary["counters"]["connector_family_categories"] == {"lakehouse": 2}
    for text in (captured.out, captured.err, json.dumps(summary, sort_keys=True)):
        assert str(tmp_path) not in text
        assert "secret-trino-handoff-suite-summary.json" not in text
        assert "secret-trino-readiness-suite-summary.json" not in text
        assert "secret-trino-surface-summary.json" not in text
        assert "secret-trino-support-gap-summary.json" not in text
        assert "secret-trino-representative-summary.json" not in text


def test_trino_representative_evidence_rejects_failed_retained_summary_status() -> None:
    requirements = representative_evidence_requirements_for_profile(
        TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE
    )
    support_gap_payload = _support_gap_payload()
    support_gap_payload["status"] = "failed"

    result = audit_trino_representative_evidence(
        [
            _handoff_suite_payload(),
            _readiness_suite_payload(),
            _product_surface_payload(),
            support_gap_payload,
        ],
        requirements=requirements,
    )
    summary = representative_evidence_summary_payload(
        result,
        requirements=requirements,
        status="failed",
    )

    assert not result.ok
    assert result.issue_counts["trino_representative_evidence_summary_status_gap"] == 1
    assert _breadth_tracking_status(summary, "require_summary_statuses") == "insufficient"


def test_trino_representative_evidence_rejects_support_gap_boundary_drift() -> None:
    payload = _support_gap_payload()
    payload["broader_production_closure_status"] = "closed"

    result = audit_trino_representative_evidence(
        [payload],
        requirements=TrinoRepresentativeEvidenceRequirements(),
    )

    assert not result.ok
    assert result.issue_counts["trino_representative_evidence_support_gap_boundary_drift"] == 1


def test_trino_representative_evidence_rejects_requirement_gap() -> None:
    requirements = TrinoRepresentativeEvidenceRequirements(
        require_min_trino_version_families=2,
        required_connector_family_categories=("iceberg",),
    )

    result = audit_trino_representative_evidence(
        [_handoff_suite_payload()],
        requirements=requirements,
    )

    assert not result.ok
    assert result.issue_counts["trino_representative_evidence_version_family_gap"] == 1
    assert result.issue_counts["trino_representative_evidence_connector_family_gap"] == 1


def test_trino_representative_evidence_rejects_unsafe_label_without_echo() -> None:
    payload = _handoff_suite_payload()
    payload["connector_family_categories"] = {"bad/value": 1}

    requirements = TrinoRepresentativeEvidenceRequirements()
    result = audit_trino_representative_evidence([payload], requirements=requirements)
    summary = representative_evidence_summary_payload(
        result,
        requirements=requirements,
        status="failed",
    )

    assert not result.ok
    assert result.issue_counts == {"trino_representative_evidence_unsafe_label": 1}
    assert "bad/value" not in json.dumps(summary, sort_keys=True)


def test_trino_representative_evidence_cli_rejects_raw_like_input_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    input_summary = tmp_path / "secret-raw-like-summary.json"
    output_summary = tmp_path / "secret-output-summary.json"
    payload = _handoff_suite_payload()
    payload["ignored"] = "token" + "=secretvalue"
    input_summary.write_text(json.dumps(payload), encoding="utf-8")
    capsys.readouterr()

    exit_code = audit_script.main(
        [
            "--summary-input-json",
            str(input_summary),
            "--summary-json",
            str(output_summary),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "summary JSON input contains raw-like content" in captured.err
    assert "secretvalue" not in captured.err
    assert "secret-raw-like-summary.json" not in captured.err
    assert str(tmp_path) not in captured.err
    assert not output_summary.exists()


def test_trino_representative_evidence_cli_rejects_output_overlap_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    input_summary = tmp_path / "secret-overlap-summary.json"
    input_summary.write_text(json.dumps(_handoff_suite_payload()), encoding="utf-8")
    capsys.readouterr()

    exit_code = audit_script.main(
        [
            "--summary-input-json",
            str(input_summary),
            "--summary-json",
            str(input_summary),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "summary JSON output must differ from every input summary" in captured.err
    assert "secret-overlap-summary.json" not in captured.err
    assert str(tmp_path) not in captured.err


def _handoff_suite_payload() -> dict[str, object]:
    return {
        "summary_kind": "trino_evidence_handoff_suite_summary_v1",
        "mode": "trino_evidence_handoff_suite",
        "status": "ok",
        "counts": {
            "handoff_summary_count": 2,
            "package_sample_count": 4,
            "boundary_count": 4,
        },
        "source_contracts": {"synthetic_trino_event_listener_v1": 2},
        "connector_family_categories": {"lakehouse": 2},
        "source_schemas": {"engine_fact_boundary_v1": 4},
        "lifecycles": {"finished": 3, "failed": 1},
        "support_statuses": {"bounded_raw_free_preview": 4},
        "source_granularity": {"one_query_boundary": 4},
        "diagnostic_lane": {
            "source_granularity": {"one_query_boundary": 4},
            "verification_scope": {"comparable_one_query_rerun": 4},
            "fact_states": {"supported": 12},
        },
    }


def _readiness_suite_payload() -> dict[str, object]:
    return {
        "summary_kind": "trino_compact_readiness_summary_v1",
        "mode": "trino_one_query_handoff_suite",
        "ok": True,
        "input_count": 3,
        "ok_count": 3,
        "failed_count": 0,
        "counters": {
            "trino_version_families": {"477": 2, "478": 1},
            "source_schemas": {"engine_fact_boundary_v1": 3},
            "lifecycles": {"finished": 3},
            "source_granularity": {"one_query_boundary": 3},
            "support_statuses": {"bounded_raw_free_preview": 3},
            "diagnostic_lane_verification_scope": {"comparable_one_query_rerun": 3},
        },
    }


def _product_surface_payload() -> dict[str, object]:
    return {
        "summary_kind": "trino_product_surface_boundary_audit_v1",
        "status": "ok",
        "mode": "trino_product_surface_boundary",
        "boundary": {
            "details_case_view": "raw_free_materialized",
            "llm_reports": "not_wired",
            "live_known_query_diagnosis": "one_query_pruned_query_info_local_production",
            "live_recent_scan": "retained_query_list_local_production",
            "optimizer_behavior": "guidance_only",
            "optimizer_guidance": "raw_free_materialized",
            "product_surface": "recent_query_id_raw_free_details_python_report_optimizer_guidance",
            "python_report": "raw_free_materialized",
            "support_claim": "local_production",
            "trino_sql_execution": "not_performed",
            "trusted_reports": "python_report_only",
        },
        "counts": {
            "boundary_json_count": 3,
            "diagnosis_json_checked_count": 3,
            "diagnostic_lane_checked_count": 3,
        },
        "diagnostic_lane": {
            "source_granularity": {"one_query_boundary": 3},
            "verification_scope": {"comparable_one_query_rerun": 3},
        },
    }


def _support_gap_payload() -> dict[str, object]:
    return {
        "summary_kind": "trino_support_gap_matrix_audit_v1",
        "status": "ok",
        "support_gap_status": "bounded_production_claim_pinned",
        "production_support": "local_production",
        "product_surfaces": "recent_query_id_raw_free_details_python_report_optimizer_guidance",
        "broader_production_closure_status": "bounded_production_claim_ready",
        "broader_production_closure_gate_count": 8,
        "trino_sql_execution": "not_performed",
        "issue_counts": {},
    }


def _breadth_tracking_status(summary: dict[str, object], requirement_id: str) -> str:
    tracking_items = summary["breadth_requirement_tracking"]
    assert isinstance(tracking_items, list)
    for item in tracking_items:
        assert isinstance(item, dict)
        if item["requirement_id"] == requirement_id:
            status = item["tracking_status"]
            assert isinstance(status, str)
            return status
    raise AssertionError(f"missing breadth tracking for {requirement_id}")
