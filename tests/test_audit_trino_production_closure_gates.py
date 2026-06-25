from __future__ import annotations

import json
from pathlib import Path

from query_doctor.trino.production_closure_gates import (
    TRINO_BROADER_PRODUCTION_CLOSURE_GATES,
    TRINO_CURRENT_TRACKING_SUMMARY_KINDS,
    TRINO_PRODUCTION_CLOSURE_STATUS,
    TRINO_PRODUCTION_CLOSURE_SUMMARY_KIND,
    TRINO_SHARED_DEPLOYMENT_AUDIT_SUMMARY_KIND,
    TRINO_SUPPORT_GAP_SUMMARY_KIND,
    audit_trino_production_closure_gates,
    trino_production_closure_summary_payload,
)
from query_doctor.trino.browser_report_regression import (
    audit_trino_browser_report_regression,
    browser_report_regression_summary_payload,
)
from query_doctor.trino.product_metadata_collection import (
    audit_trino_product_metadata_collection,
    product_metadata_collection_summary_payload,
)
from query_doctor.trino.production_collector_contracts import (
    audit_trino_production_collector_contracts,
    production_collector_summary_payload,
)
from query_doctor.trino.query_linked_fact_coverage import (
    audit_trino_query_linked_fact_coverage,
    query_linked_fact_coverage_summary_payload,
)
from query_doctor.trino.representative_evidence import (
    TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE,
    TrinoRepresentativeEvidenceRequirements,
    audit_trino_representative_evidence,
    representative_evidence_requirements_for_profile,
    representative_evidence_summary_payload,
)
from query_doctor.trino.report_optimizer_safety import (
    audit_trino_report_optimizer_safety,
    report_optimizer_safety_summary_payload,
)
from scripts import audit_trino_production_closure_gates as audit_script
from scripts import audit_trino_support_gap_matrix


def test_trino_production_closure_gates_static_audit_records_open_gates() -> None:
    result = audit_trino_production_closure_gates(
        support_gap_gates=audit_trino_support_gap_matrix.TRINO_BROADER_PRODUCTION_CLOSURE_GATES
    )

    assert result.ok
    assert result.gate_count == 8
    assert result.open_gate_count == 8
    assert result.summary_backed_gate_count == 8
    assert result.unbacked_gate_count == 0
    assert result.current_tracking_summary_kind_count == 8
    assert result.support_gap_gate_count == 8
    assert result.tracking_state_counts["tracked_by_dedicated_audit"] == 6
    assert result.tracking_state_counts["tracked_by_shared_deployment_audit"] == 1
    assert result.tracking_state_counts["tracked_by_support_gap_audit"] == 1
    assert result.gate_tracking_counts["not_required"] == 8

    summary = trino_production_closure_summary_payload(
        result,
        status="ok",
        require_current_tracking_summaries=False,
    )
    assert summary["summary_kind"] == TRINO_PRODUCTION_CLOSURE_SUMMARY_KIND
    assert summary["production_closure_status"] == "not_closed"
    assert summary["broader_production_closure_status"] == "not_closed"
    assert summary["trino_sql_execution"] == "not_performed"
    assert summary["current_tracking_summary_status"] == "not_required"
    assert summary["current_tracking_summary_ready_count"] == 0
    assert summary["invalid_current_tracking_summary_count"] == 0
    assert summary["representative_evidence_linkage_status"] == "not_required"
    assert summary["representative_evidence_linkage_required"] is False
    assert summary["representative_evidence_linkage_ready_count"] == 0
    assert summary["representative_evidence_linkage_invalid_summary_count"] == 0
    assert summary["representative_evidence_linkage_missing_summary_count"] == 0
    assert summary["current_tracking_summary_kinds"] == sorted(TRINO_CURRENT_TRACKING_SUMMARY_KINDS)
    assert summary["gate_tracking_counts"] == {"not_required": 8}
    assert {
        gate_tracking["tracking_input_status"] for gate_tracking in summary["gate_tracking"]
    } == {"not_required"}
    assert [gate["gate_id"] for gate in summary["closure_gates"]] == list(
        TRINO_BROADER_PRODUCTION_CLOSURE_GATES
    )


def test_trino_production_closure_gates_accepts_current_tracking_summaries() -> None:
    payloads = _current_tracking_summaries()

    result = audit_trino_production_closure_gates(
        payloads,
        support_gap_gates=audit_trino_support_gap_matrix.TRINO_BROADER_PRODUCTION_CLOSURE_GATES,
        require_current_tracking_summaries=True,
    )

    assert result.ok
    assert result.summary_input_count == len(TRINO_CURRENT_TRACKING_SUMMARY_KINDS)
    assert result.missing_current_tracking_summary_count == 0
    assert result.summary_kind_counts == {
        summary_kind: 1 for summary_kind in TRINO_CURRENT_TRACKING_SUMMARY_KINDS
    }
    assert result.gate_summary_counts["trino_report_optimizer_safety"] == 1
    assert result.gate_summary_counts["trino_browser_report_regression"] == 1
    assert result.gate_tracking_counts["accepted"] == 8
    assert result.open_gate_count == 0
    summary = trino_production_closure_summary_payload(
        result,
        status="ok",
        require_current_tracking_summaries=True,
    )
    assert summary["production_closure_status"] == TRINO_PRODUCTION_CLOSURE_STATUS
    assert summary["broader_production_closure_status"] == TRINO_PRODUCTION_CLOSURE_STATUS
    assert summary["current_tracking_summary_status"] == "ready"
    assert summary["current_tracking_summary_ready_count"] == len(
        TRINO_CURRENT_TRACKING_SUMMARY_KINDS
    )
    assert summary["invalid_current_tracking_summary_count"] == 0
    assert summary["representative_evidence_linkage_status"] == "ready"
    assert summary["representative_evidence_linkage_required"] is True
    assert summary["representative_evidence_linkage_ready_count"] == 1
    assert summary["representative_evidence_linkage_invalid_summary_count"] == 0
    assert summary["representative_evidence_linkage_missing_summary_count"] == 0
    assert summary["gate_tracking_counts"] == {"accepted": 8}
    assert {
        gate_tracking["tracking_input_status"] for gate_tracking in summary["gate_tracking"]
    } == {"accepted"}


def test_trino_production_closure_gates_rejects_unlinked_representative_summary() -> None:
    payloads = _current_tracking_summaries()
    payloads[0] = production_collector_summary_payload(
        audit_trino_production_collector_contracts(),
        status="ok",
    )

    result = audit_trino_production_closure_gates(
        payloads,
        support_gap_gates=audit_trino_support_gap_matrix.TRINO_BROADER_PRODUCTION_CLOSURE_GATES,
        require_current_tracking_summaries=True,
    )

    assert not result.ok
    assert (
        result.issue_counts["trino_closure_collector_representative_evidence_linkage_missing"] == 1
    )


def test_trino_production_closure_gates_rejects_missing_linked_representative_summary() -> None:
    result = audit_trino_production_closure_gates([_production_collector_summary()])

    assert not result.ok
    assert result.issue_counts["trino_closure_representative_evidence_summary_missing"] == 1
    summary = trino_production_closure_summary_payload(
        result,
        status="failed",
        require_current_tracking_summaries=False,
    )
    assert summary["representative_evidence_linkage_status"] == "failed"
    assert summary["representative_evidence_linkage_ready_count"] == 0
    assert summary["representative_evidence_linkage_invalid_summary_count"] == 0
    assert summary["representative_evidence_linkage_missing_summary_count"] == 1


def test_trino_production_closure_gates_no_longer_accepts_product_surface_summary() -> None:
    result = audit_trino_production_closure_gates(
        [
            {
                "summary_kind": "trino_product_surface_boundary_audit_v1",
                "status": "ok",
                "issues": {"counts": {}, "items": []},
            }
        ],
        support_gap_gates=audit_trino_support_gap_matrix.TRINO_BROADER_PRODUCTION_CLOSURE_GATES,
    )

    assert not result.ok
    assert result.issue_counts["trino_closure_summary_kind_unknown"] == 1


def test_trino_production_closure_gates_rejects_missing_required_tracking_summary() -> None:
    payloads = [
        payload
        for payload in _current_tracking_summaries()
        if payload["summary_kind"] != TRINO_SHARED_DEPLOYMENT_AUDIT_SUMMARY_KIND
    ]

    result = audit_trino_production_closure_gates(
        payloads,
        support_gap_gates=audit_trino_support_gap_matrix.TRINO_BROADER_PRODUCTION_CLOSURE_GATES,
        require_current_tracking_summaries=True,
    )

    assert not result.ok
    assert result.missing_current_tracking_summary_count == 1
    assert result.issue_counts["trino_closure_tracking_summary_missing"] == 1
    assert result.gate_tracking_counts["accepted"] == 7
    assert result.gate_tracking_counts["missing"] == 1
    summary = trino_production_closure_summary_payload(
        result,
        status="failed",
        require_current_tracking_summaries=True,
    )
    assert summary["current_tracking_summary_status"] == "incomplete"
    assert summary["current_tracking_summary_ready_count"] == (
        len(TRINO_CURRENT_TRACKING_SUMMARY_KINDS) - 1
    )
    assert summary["invalid_current_tracking_summary_count"] == 0
    assert summary["gate_tracking_counts"] == {"accepted": 7, "missing": 1}
    assert _gate_tracking_status(summary, "trino_shared_deployment_readiness") == "missing"


def test_trino_production_closure_gates_rejects_summary_status_drift() -> None:
    payloads = _current_tracking_summaries()
    payloads[0]["status"] = "failed"

    result = audit_trino_production_closure_gates(
        payloads,
        support_gap_gates=audit_trino_support_gap_matrix.TRINO_BROADER_PRODUCTION_CLOSURE_GATES,
        require_current_tracking_summaries=True,
    )

    assert not result.ok
    assert result.issue_counts["trino_closure_summary_status_not_ok"] == 1
    assert result.gate_tracking_counts["accepted"] == 7
    assert result.gate_tracking_counts["invalid"] == 1
    summary = trino_production_closure_summary_payload(
        result,
        status="failed",
        require_current_tracking_summaries=True,
    )
    assert summary["current_tracking_summary_status"] == "failed"
    assert summary["current_tracking_summary_ready_count"] == (
        len(TRINO_CURRENT_TRACKING_SUMMARY_KINDS) - 1
    )
    assert summary["invalid_current_tracking_summary_count"] == 1
    assert summary["representative_evidence_linkage_status"] == "failed"
    assert summary["representative_evidence_linkage_ready_count"] == 0
    assert summary["representative_evidence_linkage_invalid_summary_count"] == 1
    assert summary["gate_tracking_counts"] == {"accepted": 7, "invalid": 1}
    assert _gate_tracking_status(summary, "trino_production_collector_contracts") == "invalid"


def test_trino_production_closure_gates_rejects_required_collector_evidence_not_ready() -> None:
    payload = _production_collector_summary()
    payload["representative_evidence_required"] = True
    payload["representative_evidence_contract_status"] = "not_provided"

    result = audit_trino_production_closure_gates([payload])

    assert not result.ok
    assert (
        result.issue_counts["trino_closure_collector_representative_evidence_required_not_ready"]
        == 1
    )


def test_trino_production_closure_gates_rejects_collector_evidence_handoff_drift() -> None:
    payload = _production_collector_summary()
    payload["representative_evidence_contract_status"] = "drifted"

    result = audit_trino_production_closure_gates([payload])

    assert not result.ok
    assert result.issue_counts["trino_closure_collector_representative_evidence_drift"] == 1


def test_trino_production_closure_gates_rejects_browser_report_drift() -> None:
    payload = _browser_report_summary()
    payload["llm_reports"] = "wired"
    payload["trino_sql_execution"] = "performed"
    payload["present_test_count"] = 0

    result = audit_trino_production_closure_gates([payload])

    assert not result.ok
    assert result.issue_counts["trino_closure_browser_report_boundary_drift"] == 2
    assert result.issue_counts["trino_closure_browser_report_tests_missing"] == 1


def test_trino_production_closure_gates_rejects_browser_report_profile_drift() -> None:
    payload = _browser_report_summary()
    payload["production_review_profile"] = "legacy"
    payload["production_review_profile_status"] = "failed"
    payload["production_review_requirements"]["required_route_capabilities"] = [
        "materialized_details"
    ]
    payload["production_review_requirements"]["required_raw_output_requirements"] = [
        "raw_sql_output_blocked"
    ]
    payload["production_review_tracking_counts"] = {"insufficient": 1}

    result = audit_trino_production_closure_gates([payload])

    assert not result.ok
    assert result.issue_counts["trino_closure_browser_report_profile_drift"] == 5


def test_trino_production_closure_gates_rejects_report_optimizer_drift() -> None:
    payload = _report_optimizer_summary()
    payload["llm_reports"] = "wired"
    payload["trino_sql_execution"] = "performed"
    payload["validation_sentinel_count"] = 0

    result = audit_trino_production_closure_gates([payload])

    assert not result.ok
    assert result.issue_counts["trino_closure_report_optimizer_boundary_drift"] == 2
    assert result.issue_counts["trino_closure_report_optimizer_validation_missing"] == 1


def test_trino_production_closure_gates_rejects_report_optimizer_profile_drift() -> None:
    payload = _report_optimizer_summary()
    payload["production_review_profile"] = "legacy"
    payload["production_review_profile_status"] = "failed"
    payload["production_review_requirements"]["required_capabilities"] = [
        "materialized_python_report"
    ]
    payload["production_review_requirements"]["required_product_surface_requirements"] = []
    payload["production_review_tracking_counts"] = {"insufficient": 1}

    result = audit_trino_production_closure_gates([payload])

    assert not result.ok
    assert result.issue_counts["trino_closure_report_optimizer_profile_drift"] == 5


def test_trino_production_closure_gates_rejects_shared_deployment_profile_drift() -> None:
    payload = _shared_deployment_summary()
    payload["production_review_profile"] = "legacy"
    payload["production_review_profile_status"] = "failed"
    payload["production_review_requirements"]["required_deployment_config_requirements"] = [
        "config_source_inventory"
    ]
    payload["production_review_requirements"]["required_unsupported_surfaces"] = ["running_scan"]
    payload["production_review_tracking_counts"] = {"insufficient": 1}

    result = audit_trino_production_closure_gates([payload])

    assert not result.ok
    assert result.issue_counts["trino_closure_shared_deployment_profile_drift"] == 5


def test_trino_production_closure_gates_rejects_product_metadata_drift() -> None:
    payload = _product_metadata_summary()
    payload["adapter_metadata_collection"] = "enabled"
    payload["metadata_cli_sql_execution"] = "user_sql"

    result = audit_trino_production_closure_gates([payload])

    assert not result.ok
    assert result.issue_counts["trino_closure_product_metadata_boundary_drift"] == 2


def test_trino_production_closure_gates_rejects_product_metadata_profile_drift() -> None:
    payload = _product_metadata_summary()
    payload["production_review_profile"] = "legacy"
    payload["production_review_profile_status"] = "failed"
    payload["production_review_requirements"]["required_source_families"] = [
        "metadata_allowlist_source_contract"
    ]
    payload["production_review_requirements"]["required_redaction_fields"] = []
    payload["production_review_tracking_counts"] = {"insufficient": 1}

    result = audit_trino_production_closure_gates([payload])

    assert not result.ok
    assert result.issue_counts["trino_closure_product_metadata_profile_drift"] == 5


def test_trino_production_closure_gates_rejects_representative_breadth_profile_drift() -> None:
    payload = _representative_evidence_summary()
    payload["breadth_profile_status"] = "failed"
    payload["evidence_unit_count"] = 0

    result = audit_trino_production_closure_gates([payload])

    assert not result.ok
    assert result.issue_counts["trino_closure_representative_breadth_profile_drift"] == 2


def test_trino_production_closure_gates_rejects_representative_summary_without_profile() -> None:
    requirements = TrinoRepresentativeEvidenceRequirements()
    payload = representative_evidence_summary_payload(
        audit_trino_representative_evidence([], requirements=requirements),
        requirements=requirements,
        status="ok",
    )

    result = audit_trino_production_closure_gates([payload])

    assert not result.ok
    assert result.issue_counts["trino_closure_representative_breadth_profile_drift"] == 3


def test_trino_production_closure_gates_rejects_representative_summary_mix_drift() -> None:
    payload = _representative_evidence_summary()
    payload["requirements"]["require_summary_kinds"] = ["trino_compact_readiness_summary_v1"]
    payload["requirements"]["require_summary_statuses"] = []
    payload["counters"]["summary_kinds"] = {"trino_compact_readiness_summary_v1": 1}
    payload["counters"]["statuses"] = {"failed": 1}

    result = audit_trino_production_closure_gates([payload])

    assert not result.ok
    assert result.issue_counts["trino_closure_representative_summary_kind_drift"] == 2
    assert result.issue_counts["trino_closure_representative_summary_status_drift"] == 2


def test_trino_production_closure_gates_rejects_query_linked_profile_drift() -> None:
    payload = _query_linked_summary()
    payload["coverage_profile"] = "legacy"
    payload["coverage_profile_status"] = "failed"
    payload["coverage_profile_requirements"]["required_core_families"] = ["stage_summary_and_skew"]
    payload["coverage_profile_tracking_counts"] = {"insufficient": 1}

    result = audit_trino_production_closure_gates([payload])

    assert not result.ok
    assert result.issue_counts["trino_closure_query_linked_profile_drift"] == 4


def test_trino_production_closure_gates_rejects_query_linked_decision_profile_drift() -> None:
    payload = _query_linked_summary()
    payload["operator_connector_telemetry_profile"] = "legacy"
    payload["operator_connector_telemetry_profile_status"] = "failed"
    payload["operator_connector_telemetry_decision_requirements"][
        "required_unsupported_gap_families"
    ] = ["operator_level_metrics"]
    payload["operator_connector_telemetry_decision_counts"] = {"bounded_supported": 1}
    payload["operator_connector_telemetry_decision_tracking_counts"] = {"insufficient": 1}

    result = audit_trino_production_closure_gates([payload])

    assert not result.ok
    assert result.issue_counts["trino_closure_query_linked_decision_profile_drift"] == 5


def test_trino_production_closure_gates_rejects_support_gap_gate_drift() -> None:
    result = audit_trino_production_closure_gates(
        support_gap_gates=TRINO_BROADER_PRODUCTION_CLOSURE_GATES[:-1]
    )

    assert not result.ok
    assert result.issue_counts["trino_closure_gate_list_drift"] == 1


def test_trino_production_closure_cli_writes_path_free_summary(tmp_path: Path, capsys) -> None:
    input_paths = []
    for index, payload in enumerate(_current_tracking_summaries(), start=1):
        path = tmp_path / f"closure-summary-input-{index}"
        path.write_text(json.dumps(payload), encoding="utf-8")
        input_paths.extend(["--summary-input-json", str(path)])
    output_summary = tmp_path / "production-closure-summary-output"
    capsys.readouterr()

    exit_code = audit_script.main(
        [
            *input_paths,
            "--require-current-tracking-summaries",
            "--summary-json",
            str(output_summary),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(output_summary.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "Trino production closure gates audit: ok" in captured.out
    assert "broader_production_closure=bounded_production_claim_ready" in captured.out
    assert "summary_inputs=8" in captured.out
    assert "current_tracking_summary=ready" in captured.out
    assert "missing_required_inputs=0" in captured.out
    assert "invalid_current_tracking_summaries=0" in captured.out
    assert "representative_evidence_linkage=ready" in captured.out
    assert "representative_evidence_linkage_invalid_summaries=0" in captured.out
    assert "representative_evidence_linkage_missing_summaries=0" in captured.out
    assert "Issues: none" in captured.out
    assert payload["summary_kind"] == TRINO_PRODUCTION_CLOSURE_SUMMARY_KIND
    assert payload["status"] == "ok"
    assert payload["current_tracking_summary_status"] == "ready"
    assert payload["invalid_current_tracking_summary_count"] == 0
    assert payload["missing_current_tracking_summary_count"] == 0
    assert payload["representative_evidence_linkage_status"] == "ready"
    assert payload["representative_evidence_linkage_invalid_summary_count"] == 0
    assert payload["representative_evidence_linkage_missing_summary_count"] == 0
    assert payload["gate_tracking_counts"] == {"accepted": 8}
    assert "gate_tracking=accepted=8" in captured.out
    for text in (captured.out, captured.err, json.dumps(payload, sort_keys=True)):
        assert str(tmp_path) not in text
        assert "closure-summary-input" not in text
        assert "production-closure-summary-output" not in text


def test_trino_production_closure_cli_prints_incomplete_tracking_status(
    tmp_path: Path, capsys
) -> None:
    input_paths = []
    for index, payload in enumerate(_current_tracking_summaries()[:-1], start=1):
        path = tmp_path / f"closure-summary-input-{index}"
        path.write_text(json.dumps(payload), encoding="utf-8")
        input_paths.extend(["--summary-input-json", str(path)])
    output_summary = tmp_path / "production-closure-summary-output"
    capsys.readouterr()

    exit_code = audit_script.main(
        [
            *input_paths,
            "--require-current-tracking-summaries",
            "--summary-json",
            str(output_summary),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(output_summary.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert "Trino production closure gates audit: failed" in captured.out
    assert "summary_inputs=7" in captured.out
    assert "current_tracking_summary=incomplete" in captured.out
    assert "missing_required_inputs=1" in captured.out
    assert "invalid_current_tracking_summaries=0" in captured.out
    assert "representative_evidence_linkage=ready" in captured.out
    assert "representative_evidence_linkage_invalid_summaries=0" in captured.out
    assert "representative_evidence_linkage_missing_summaries=0" in captured.out
    assert payload["status"] == "failed"
    assert payload["current_tracking_summary_status"] == "incomplete"
    assert payload["invalid_current_tracking_summary_count"] == 0
    assert payload["missing_current_tracking_summary_count"] == 1
    assert payload["gate_tracking_counts"] == {"accepted": 7, "missing": 1}
    assert "gate_tracking=accepted=7, missing=1" in captured.out
    for text in (captured.out, captured.err, json.dumps(payload, sort_keys=True)):
        assert str(tmp_path) not in text
        assert "closure-summary-input" not in text
        assert "production-closure-summary-output" not in text


def test_trino_production_closure_cli_prints_failed_linkage_status(tmp_path: Path, capsys) -> None:
    input_paths = []
    payloads = _current_tracking_summaries()
    payloads[0]["status"] = "failed"
    for index, payload in enumerate(payloads, start=1):
        path = tmp_path / f"closure-summary-input-{index}"
        path.write_text(json.dumps(payload), encoding="utf-8")
        input_paths.extend(["--summary-input-json", str(path)])
    output_summary = tmp_path / "production-closure-summary-output"
    capsys.readouterr()

    exit_code = audit_script.main(
        [
            *input_paths,
            "--require-current-tracking-summaries",
            "--summary-json",
            str(output_summary),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(output_summary.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert "current_tracking_summary=failed" in captured.out
    assert "invalid_current_tracking_summaries=1" in captured.out
    assert "representative_evidence_linkage=failed" in captured.out
    assert "representative_evidence_linkage_invalid_summaries=1" in captured.out
    assert payload["representative_evidence_linkage_status"] == "failed"
    assert payload["representative_evidence_linkage_invalid_summary_count"] == 1
    assert payload["gate_tracking_counts"] == {"accepted": 7, "invalid": 1}
    assert "gate_tracking=accepted=7, invalid=1" in captured.out
    for text in (captured.out, captured.err, json.dumps(payload, sort_keys=True)):
        assert str(tmp_path) not in text
        assert "closure-summary-input" not in text
        assert "production-closure-summary-output" not in text


def test_trino_production_closure_cli_prints_missing_linkage_summary_status(
    tmp_path: Path, capsys
) -> None:
    input_path = tmp_path / "closure-summary-input"
    output_summary = tmp_path / "production-closure-summary-output"
    input_path.write_text(json.dumps(_production_collector_summary()), encoding="utf-8")
    capsys.readouterr()

    exit_code = audit_script.main(
        [
            "--summary-input-json",
            str(input_path),
            "--summary-json",
            str(output_summary),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(output_summary.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert "representative_evidence_linkage=failed" in captured.out
    assert "representative_evidence_linkage_invalid_summaries=0" in captured.out
    assert "representative_evidence_linkage_missing_summaries=1" in captured.out
    assert payload["representative_evidence_linkage_status"] == "failed"
    assert payload["representative_evidence_linkage_invalid_summary_count"] == 0
    assert payload["representative_evidence_linkage_missing_summary_count"] == 1
    assert payload["gate_tracking_counts"] == {"accepted": 1, "missing": 1, "not_required": 6}
    assert "gate_tracking=accepted=1, missing=1, not_required=6" in captured.out
    for text in (captured.out, captured.err, json.dumps(payload, sort_keys=True)):
        assert str(tmp_path) not in text
        assert "closure-summary-input" not in text
        assert "production-closure-summary-output" not in text


def test_trino_production_closure_cli_rejects_raw_like_input_without_echo(
    tmp_path: Path, capsys
) -> None:
    input_path = tmp_path / "raw-like-closure-summary-input"
    output_path = tmp_path / "closure-summary-output"
    payload = _production_collector_summary()
    payload["ignored"] = "facts sha256: abc123"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    capsys.readouterr()

    exit_code = audit_script.main(
        [
            "--summary-input-json",
            str(input_path),
            "--summary-json",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "summary JSON input contains raw-like content" in captured.err
    assert "abc123" not in captured.err
    assert "raw-like-closure-summary-input" not in captured.err
    assert str(tmp_path) not in captured.err
    assert not output_path.exists()


def _current_tracking_summaries() -> list[dict[str, object]]:
    return [
        _production_collector_summary(),
        _representative_evidence_summary(),
        _query_linked_summary(),
        _product_metadata_summary(),
        _report_optimizer_summary(),
        _browser_report_summary(),
        _shared_deployment_summary(),
        _support_gap_summary(),
    ]


def _gate_tracking_status(summary: dict[str, object], gate_id: str) -> str:
    gate_tracking = summary["gate_tracking"]
    assert isinstance(gate_tracking, list)
    for item in gate_tracking:
        assert isinstance(item, dict)
        if item["gate_id"] == gate_id:
            status = item["tracking_input_status"]
            assert isinstance(status, str)
            return status
    raise AssertionError(f"missing gate tracking for {gate_id}")


def _production_collector_summary() -> dict[str, object]:
    return production_collector_summary_payload(
        audit_trino_production_collector_contracts(
            representative_evidence_summaries=[_representative_evidence_summary()],
            require_representative_evidence_summary=True,
        ),
        status="ok",
    )


def _representative_evidence_summary() -> dict[str, object]:
    requirements = representative_evidence_requirements_for_profile(
        TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE
    )
    return representative_evidence_summary_payload(
        audit_trino_representative_evidence(
            [
                _representative_handoff_suite_summary(),
                _representative_readiness_summary(),
                _representative_product_surface_summary(),
                _representative_support_gap_summary(),
            ],
            requirements=requirements,
        ),
        requirements=requirements,
        status="ok",
    )


def _representative_handoff_suite_summary() -> dict[str, object]:
    return {
        "summary_kind": "trino_evidence_handoff_suite_summary_v1",
        "status": "ok",
        "counts": {"handoff_summary_count": 2, "package_sample_count": 2, "boundary_count": 2},
        "source_contracts": {"synthetic_trino_event_listener_v1": 2},
        "connector_family_categories": {"lakehouse": 2},
        "source_schemas": {"engine_fact_boundary_v1": 2},
        "lifecycles": {"finished": 2},
        "support_statuses": {"bounded_raw_free_preview": 2},
        "source_granularity": {"one_query_boundary": 2},
        "diagnostic_lane": {"verification_scope": {"comparable_one_query_rerun": 2}},
    }


def _representative_readiness_summary() -> dict[str, object]:
    return {
        "summary_kind": "trino_compact_readiness_summary_v1",
        "ok": True,
        "input_count": 1,
        "counters": {
            "trino_version_families": {"477": 1, "478": 1},
            "source_schemas": {"engine_fact_boundary_v1": 1},
            "lifecycles": {"failed": 1},
            "source_granularity": {"one_query_boundary": 1},
            "support_statuses": {"bounded_raw_free_preview": 1},
            "diagnostic_lane_verification_scope": {"comparable_one_query_rerun": 1},
        },
    }


def _representative_product_surface_summary() -> dict[str, object]:
    return {
        "summary_kind": "trino_product_surface_boundary_audit_v1",
        "status": "ok",
        "boundary": {
            "details_case_view": "raw_free_materialized",
            "llm_reports": "not_wired",
            "optimizer_behavior": "guidance_only",
            "optimizer_guidance": "raw_free_materialized",
            "product_surface": "recent_query_id_raw_free_details_python_report_optimizer_guidance",
            "python_report": "raw_free_materialized",
            "support_claim": "local_production",
            "trino_sql_execution": "not_performed",
        },
        "diagnostic_lane": {
            "source_granularity": {"one_query_boundary": 1},
            "verification_scope": {"comparable_one_query_rerun": 1},
        },
    }


def _representative_support_gap_summary() -> dict[str, object]:
    return {
        "summary_kind": "trino_support_gap_matrix_audit_v1",
        "status": "ok",
        "support_gap_status": "bounded_production_claim_pinned",
        "production_support": "local_production",
        "product_surfaces": "recent_query_id_raw_free_details_python_report_optimizer_guidance",
        "broader_production_closure_status": "bounded_production_claim_ready",
        "trino_sql_execution": "not_performed",
    }


def _query_linked_summary() -> dict[str, object]:
    return query_linked_fact_coverage_summary_payload(
        audit_trino_query_linked_fact_coverage(),
        status="ok",
    )


def _product_metadata_summary() -> dict[str, object]:
    return product_metadata_collection_summary_payload(
        audit_trino_product_metadata_collection(),
        status="ok",
    )


def _report_optimizer_summary() -> dict[str, object]:
    return report_optimizer_safety_summary_payload(
        audit_trino_report_optimizer_safety(),
        status="ok",
    )


def _browser_report_summary() -> dict[str, object]:
    return browser_report_regression_summary_payload(
        audit_trino_browser_report_regression(),
        status="ok",
    )


def _shared_deployment_summary() -> dict[str, object]:
    return {
        "summary_kind": TRINO_SHARED_DEPLOYMENT_AUDIT_SUMMARY_KIND,
        "status": "ok",
        "deployment_boundary": {
            "trusted_front_door_identity": "required_for_shared_trino",
            "raw_source_reveal": "blocked_for_shared_trino",
            "paths_printed": False,
            "header_values_printed": False,
            "query_ids_printed": False,
        },
        "product_boundary": {
            "details_case_view": "raw_free_materialized",
            "python_report": "raw_free_materialized",
            "optimizer_guidance": "raw_free_materialized",
            "optimizer_behavior": "guidance_only",
            "llm_reports": "not_wired",
            "metadata_collection": "not_wired",
        },
        "unsupported_surfaces": {
            "running_scan": "blocked",
            "query_history_crawling": "blocked",
            "product_metadata_collection": "blocked",
            "llm_reports": "blocked",
            "query_optimizer_jobs": "blocked",
            "generated_trino_sql": "blocked",
            "sql_execution": "blocked",
        },
        "production_review_profile": "production_review_shared_deployment_v1",
        "production_review_profile_status": "ready",
        "production_review_requirements": {
            "required_families": [
                "deployment_boundary",
                "product_boundary",
                "capability_manifest",
                "release_bundle",
                "shared_deployment_docs",
            ],
            "required_deployment_config_requirements": [
                "config_source_inventory",
                "trusted_front_door_review",
                "trusted_viewer_identity",
                "raw_source_reveal_blocked",
            ],
            "required_product_boundary_requirements": [
                "details",
                "python_report",
                "optimizer_guidance",
                "optimizer_behavior",
                "llm_reports",
                "unsupported_surfaces_blocked",
            ],
            "required_capability_requirements": [
                "product_capability_surface_set",
                "product_capability_classification",
                "product_capability_raw_policy",
                "dev_gate_classification",
            ],
            "required_release_requirements": ["release_bundle_shared_deployment_gate"],
            "required_doc_requirements": [
                "trino_shared_deployment_hardening_doc",
                "trino_beta_ui_readiness_doc",
                "public_release_readiness_doc",
                "release_checklist_doc",
            ],
            "required_unsupported_surfaces": [
                "running_scan",
                "query_history_crawling",
                "product_metadata_collection",
                "llm_reports",
                "query_optimizer_jobs",
                "generated_trino_sql",
                "sql_execution",
            ],
        },
        "production_review_tracking_counts": {"accepted": 7},
        "issues": {"counts": {}, "items": []},
    }


def _support_gap_summary() -> dict[str, object]:
    return audit_trino_support_gap_matrix.support_gap_summary_payload(
        audit_trino_support_gap_matrix.audit_trino_support_gap_matrix(),
        status="ok",
    )
