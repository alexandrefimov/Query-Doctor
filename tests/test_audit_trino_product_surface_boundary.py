from __future__ import annotations

import copy
import json
from pathlib import Path

from engine_fact_contract_harness import trino_golden_cases
from query_doctor.analyzer.engine_facts import engine_fact_boundary_payload
from query_doctor.trino.diagnosis import build_trino_compact_diagnosis_from_boundary
from scripts import audit_trino_product_surface_boundary
from scripts.audit_trino_compact_readiness import TRINO_HANDOFF_SUITE_MANIFEST_KIND
from trino_metadata_summary_boundary import (
    metadata_summary_boundary,
    metadata_summary_forbidden_tokens,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_trino_product_surface_audit_accepts_boundary_and_diagnosis_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    boundary_payload = _boundary_for_case("trino_query_detail_export_fixture")
    boundary_path = _write_json(tmp_path, "secret-boundary.json", boundary_payload)
    diagnosis_path = _write_json(
        tmp_path,
        "secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(boundary_payload),
    )

    rc = audit_trino_product_surface_boundary.main(
        [str(boundary_path), "--diagnosis-json", str(diagnosis_path)]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Trino product-surface boundary audit: ok" in captured.out
    assert "product_surface=not_promoted" in captured.out
    assert "support_claim=not_claimed" in captured.out
    assert "details_trusted_report_surface=not_wired" in captured.out
    assert "live_known_query_diagnosis=not_wired" in captured.out
    assert "trino_sql_execution=not_performed" in captured.out
    assert "boundary_json_count=1" in captured.out
    assert "diagnosis_json_checked=1" in captured.out
    assert "trino_product_routes=blocked" in captured.out
    assert "trino_product_cli=blocked" in captured.out
    assert "details_report_source_imports=blocked" in captured.out
    assert "product_source_modules_checked=" in captured.out
    assert "Issues: none" in captured.out
    assert captured.err == ""
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_product_surface_audit_writes_raw_free_summary(
    tmp_path: Path,
    capsys,
) -> None:
    boundary_payload = _boundary_for_case("trino_query_detail_export_fixture")
    diagnosis = build_trino_compact_diagnosis_from_boundary(boundary_payload)
    boundary_path = _write_json(tmp_path, "secret-boundary.json", boundary_payload)
    summary_path = tmp_path / "secret-surface-summary.json"

    rc = audit_trino_product_surface_boundary.main(
        [str(boundary_path), "--summary-json", str(summary_path)]
    )

    captured = capsys.readouterr()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert rc == 0
    assert summary["summary_kind"] == "trino_product_surface_boundary_audit_v1"
    assert summary["status"] == "ok"
    assert summary["boundary"] == {
        "details_trusted_report_surface": "not_wired",
        "live_known_query_diagnosis": "not_wired",
        "live_recent_scan": "not_wired",
        "optimizer_behavior": "not_wired",
        "product_surface": "not_promoted",
        "support_claim": "not_claimed",
        "trino_sql_execution": "not_performed",
        "trusted_reports": "not_wired",
    }
    assert summary["counts"]["boundary_json_count"] == 1
    assert summary["counts"]["diagnosis_json_checked_count"] == 0
    assert summary["counts"]["diagnostic_lane_checked_count"] == 1
    assert summary["counts"]["product_source_modules_checked_count"] > 0
    assert summary["counts"]["supported_attention_area_count"] >= 1
    assert summary["diagnostic_lane"] == {
        "evidence_readiness": {"one_query_attention_ready": 1},
        "fact_states": diagnosis["diagnostic_lane"]["fact_state_counts"],
        "source_granularity": {"one_query_boundary": 1},
        "verification_scope": {"comparable_one_query_rerun": 1},
    }
    assert summary["registry"]["trino_product_routes"] == "blocked"
    assert summary["registry"]["trino_product_cli"] == "blocked"
    assert summary["registry"]["details_report_source_imports"] == "blocked"
    assert summary["issues"] == {"counts": {}, "items": []}
    assert "Trino product-surface boundary audit: ok" in captured.out
    for text in (captured.out, captured.err, json.dumps(summary, sort_keys=True)):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_trino_product_surface_audit_accepts_handoff_manifest_suite_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    first_payload = _boundary_for_case("trino_query_detail_export_fixture")
    second_payload = _boundary_for_case("trino_query_detail_spill_fixture")
    first_boundary = _write_json(tmp_path, "first-secret-boundary.json", first_payload)
    second_boundary = _write_json(tmp_path, "second-secret-boundary.json", second_payload)
    first_diagnosis = _write_json(
        tmp_path,
        "first-secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(first_payload),
    )
    second_diagnosis = _write_json(
        tmp_path,
        "second-secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(second_payload),
    )
    manifest = _write_json(
        tmp_path,
        "operator-secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": first_boundary.name,
                    "diagnosis_json": first_diagnosis.name,
                },
                {
                    "boundary_json": second_boundary.name,
                    "diagnosis_json": second_diagnosis.name,
                },
            ],
        },
    )
    summary_path = tmp_path / "secret-surface-summary.json"

    rc = audit_trino_product_surface_boundary.main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--summary-json",
            str(summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rendered = json.dumps(summary, sort_keys=True)
    assert rc == 0
    assert "Trino product-surface boundary audit: ok" in captured.out
    assert "boundary_json_count=2" in captured.out
    assert "diagnosis_json_checked=2" in captured.out
    assert "Issues: none" in captured.out
    assert summary["summary_kind"] == "trino_product_surface_boundary_audit_v1"
    assert summary["status"] == "ok"
    assert summary["counts"]["boundary_json_count"] == 2
    assert summary["counts"]["diagnosis_json_checked_count"] == 2
    assert summary["counts"]["diagnostic_lane_checked_count"] == 2
    assert summary["boundary"]["live_known_query_diagnosis"] == "not_wired"
    assert summary["diagnostic_lane"]["fact_states"]["supported"] > 0
    assert summary["diagnostic_lane"]["source_granularity"] == {"one_query_boundary": 2}
    assert summary["diagnostic_lane"]["verification_scope"] == {"comparable_one_query_rerun": 2}
    assert summary["issues"] == {"counts": {}, "items": []}
    for text in (captured.out, captured.err, rendered):
        for fragment in (
            *_protected_fragments(tmp_path),
            "first-secret-boundary.json",
            "second-secret-boundary.json",
            "first-secret-diagnosis.json",
            "second-secret-diagnosis.json",
            "operator-secret-handoff-manifest.json",
        ):
            assert fragment not in text


def test_trino_product_surface_audit_checks_retained_manifest_summary_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    first_payload = _boundary_for_case("trino_query_detail_export_fixture")
    second_payload = _boundary_for_case("trino_query_detail_spill_fixture")
    first_boundary = _write_json(tmp_path, "first-secret-boundary.json", first_payload)
    second_boundary = _write_json(tmp_path, "second-secret-boundary.json", second_payload)
    first_diagnosis = _write_json(
        tmp_path,
        "first-secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(first_payload),
    )
    second_diagnosis = _write_json(
        tmp_path,
        "second-secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(second_payload),
    )
    first_summary = _write_json(
        tmp_path,
        "first-secret-surface-summary.json",
        audit_trino_product_surface_boundary.expected_product_surface_summary(
            first_boundary,
            first_diagnosis,
        ),
    )
    second_summary = _write_json(
        tmp_path,
        "second-secret-surface-summary.json",
        audit_trino_product_surface_boundary.expected_product_surface_summary(
            second_boundary,
            second_diagnosis,
        ),
    )
    manifest = _write_json(
        tmp_path,
        "operator-secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": first_boundary.name,
                    "diagnosis_json": first_diagnosis.name,
                    "product_surface_summary_json": first_summary.name,
                },
                {
                    "boundary_json": second_boundary.name,
                    "diagnosis_json": second_diagnosis.name,
                    "product_surface_summary_json": second_summary.name,
                },
            ],
        },
    )

    rc = audit_trino_product_surface_boundary.main(["--handoff-suite-manifest", str(manifest)])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Trino product-surface boundary audit: ok" in captured.out
    assert "boundary_json_count=2" in captured.out
    assert "diagnosis_json_checked=2" in captured.out
    assert "Issues: none" in captured.out
    for text in (captured.out, captured.err):
        for fragment in (
            *_protected_fragments(tmp_path),
            "first-secret-boundary.json",
            "second-secret-boundary.json",
            "first-secret-diagnosis.json",
            "second-secret-diagnosis.json",
            "first-secret-surface-summary.json",
            "second-secret-surface-summary.json",
            "operator-secret-handoff-manifest.json",
        ):
            assert fragment not in text


def test_trino_product_surface_audit_rejects_retained_manifest_summary_drift(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _boundary_for_case("trino_query_detail_export_fixture")
    boundary = _write_json(tmp_path, "secret-boundary.json", payload)
    diagnosis = _write_json(
        tmp_path,
        "secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(payload),
    )
    summary_payload = audit_trino_product_surface_boundary.expected_product_surface_summary(
        boundary,
        diagnosis,
    )
    summary_payload.pop("diagnostic_lane")
    product_summary = _write_json(
        tmp_path,
        "secret-surface-summary.json",
        summary_payload,
    )
    manifest = _write_json(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": boundary.name,
                    "diagnosis_json": diagnosis.name,
                    "product_surface_summary_json": product_summary.name,
                }
            ],
        },
    )

    rc = audit_trino_product_surface_boundary.main(["--handoff-suite-manifest", str(manifest)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino product-surface boundary audit: failed" in captured.out
    assert "product_surface_summary_mismatch" in captured.out
    for fragment in (
        *_protected_fragments(tmp_path),
        "secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_product_surface_audit_rejects_diagnosis_boundary_drift_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    boundary_payload = _boundary_for_case("trino_query_detail_export_fixture")
    diagnosis = build_trino_compact_diagnosis_from_boundary(boundary_payload)
    diagnosis["diagnosis_boundary"]["live_known_query_diagnosis"] = "wired"
    boundary_path = _write_json(tmp_path, "secret-boundary.json", boundary_payload)
    diagnosis_path = _write_json(tmp_path, "secret-diagnosis.json", diagnosis)

    rc = audit_trino_product_surface_boundary.main(
        [str(boundary_path), "--diagnosis-json", str(diagnosis_path)]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino product-surface boundary audit: failed" in captured.out
    assert "diagnosis_artifact_mismatch" in captured.out
    assert "diagnosis_boundary_drift" in captured.out
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_product_surface_audit_rejects_raw_like_diagnosis_without_value_echo(
    tmp_path: Path,
    capsys,
) -> None:
    boundary_payload = _boundary_for_case("trino_query_detail_export_fixture")
    diagnosis = build_trino_compact_diagnosis_from_boundary(boundary_payload)
    diagnosis["unsafe_note"] = "SELECT secret_col FROM guarded_table"
    boundary_path = _write_json(tmp_path, "secret-boundary.json", boundary_payload)
    diagnosis_path = _write_json(tmp_path, "secret-diagnosis.json", diagnosis)

    rc = audit_trino_product_surface_boundary.main(
        [str(boundary_path), "--diagnosis-json", str(diagnosis_path)]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "diagnosis_artifact_mismatch" in captured.out
    assert "diagnosis_browser_redaction_required" in captured.out
    for fragment in (
        *_protected_fragments(tmp_path),
        "SELECT",
        "secret_col",
        "guarded_table",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_product_surface_audit_rejects_diagnostic_lane_drift_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    boundary_payload = _boundary_for_case("trino_query_detail_export_fixture")
    diagnosis = build_trino_compact_diagnosis_from_boundary(boundary_payload)
    diagnosis["diagnostic_lane"]["promotion_status"] = "supported"
    boundary_path = _write_json(tmp_path, "secret-boundary.json", boundary_payload)
    diagnosis_path = _write_json(tmp_path, "secret-diagnosis.json", diagnosis)

    rc = audit_trino_product_surface_boundary.main(
        [str(boundary_path), "--diagnosis-json", str(diagnosis_path)]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino product-surface boundary audit: failed" in captured.out
    assert "diagnosis_artifact_mismatch" in captured.out
    assert "diagnostic_lane_product_promotion_drift" in captured.out
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_product_surface_audit_rejects_diagnostic_lane_readiness_drift_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    boundary_payload = _boundary_for_case("trino_query_detail_export_fixture")
    diagnosis = build_trino_compact_diagnosis_from_boundary(boundary_payload)
    diagnosis["diagnostic_lane"]["evidence_readiness"] = "source_coverage_unknown"
    diagnosis["diagnostic_lane"]["verification_scope"] = "source_contract_review"
    boundary_path = _write_json(tmp_path, "secret-boundary.json", boundary_payload)
    diagnosis_path = _write_json(tmp_path, "secret-diagnosis.json", diagnosis)

    rc = audit_trino_product_surface_boundary.main(
        [str(boundary_path), "--diagnosis-json", str(diagnosis_path)]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino product-surface boundary audit: failed" in captured.out
    assert "diagnosis_artifact_mismatch" in captured.out
    assert "diagnostic_lane_readiness_drift" in captured.out
    assert "diagnostic_lane_verification_scope_drift" in captured.out
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_product_surface_audit_rejects_diagnostic_lane_source_drift_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    boundary_payload = _boundary_for_case("trino_query_detail_export_fixture")
    diagnosis = build_trino_compact_diagnosis_from_boundary(boundary_payload)
    diagnosis["diagnostic_lane"]["source_granularity"] = "aggregate_metadata_summary"
    boundary_path = _write_json(tmp_path, "secret-boundary.json", boundary_payload)
    diagnosis_path = _write_json(tmp_path, "secret-diagnosis.json", diagnosis)

    rc = audit_trino_product_surface_boundary.main(
        [str(boundary_path), "--diagnosis-json", str(diagnosis_path)]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino product-surface boundary audit: failed" in captured.out
    assert "diagnosis_artifact_mismatch" in captured.out
    assert "diagnostic_lane_source_granularity_drift" in captured.out
    for fragment in (*_protected_fragments(tmp_path), "aggregate_metadata_summary"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_product_surface_audit_rejects_diagnostic_lane_count_drift_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    boundary_payload = _boundary_for_case("trino_query_detail_export_fixture")
    diagnosis = build_trino_compact_diagnosis_from_boundary(boundary_payload)
    diagnosis["diagnostic_lane"]["supported_attention_area_count"] = True
    diagnosis["diagnostic_lane"]["fact_state_counts"] = {"supported": -1}
    boundary_path = _write_json(tmp_path, "secret-boundary.json", boundary_payload)
    diagnosis_path = _write_json(tmp_path, "secret-diagnosis.json", diagnosis)

    rc = audit_trino_product_surface_boundary.main(
        [str(boundary_path), "--diagnosis-json", str(diagnosis_path)]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino product-surface boundary audit: failed" in captured.out
    assert "diagnosis_artifact_mismatch" in captured.out
    assert "diagnostic_lane_attention_count_drift" in captured.out
    assert "diagnostic_lane_fact_state_count_drift" in captured.out
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_product_surface_audit_rejects_metadata_summary_boundary_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    boundary_path = _write_json(
        tmp_path,
        "secret-metadata-summary-boundary",
        metadata_summary_boundary(),
    )

    rc = audit_trino_product_surface_boundary.main([str(boundary_path)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino product-surface boundary audit: failed" in captured.out
    assert "metadata_summary_boundary_not_product_surface" in captured.out
    assert "boundary_input_rejected" not in captured.out
    for fragment in (
        *_protected_fragments(tmp_path),
        "secret-metadata-summary-boundary",
        *metadata_summary_forbidden_tokens(),
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_product_surface_audit_supports_registry_only_mode(capsys) -> None:
    rc = audit_trino_product_surface_boundary.main(["--registry-only"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "boundary_json_count=0" in captured.out
    assert "trino_product_routes=blocked" in captured.out
    assert "trino_product_cli=blocked" in captured.out
    assert "details_report_source_imports=blocked" in captured.out
    assert "product_source_modules_checked=" in captured.out
    assert "Issues: none" in captured.out


def test_trino_product_surface_audit_rejects_summary_overlap_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    boundary_path = _write_json(
        tmp_path,
        "secret-boundary.json",
        _boundary_for_case("trino_query_detail_export_fixture"),
    )

    rc = audit_trino_product_surface_boundary.main(
        [str(boundary_path), "--summary-json", str(boundary_path)]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "summary JSON output must differ from every input artifact" in captured.err
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.err


def test_trino_product_surface_audit_rejects_manifest_summary_overlap_without_overwrite(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _boundary_for_case("trino_query_detail_export_fixture")
    boundary = _write_json(tmp_path, "secret-boundary.json", payload)
    diagnosis = _write_json(
        tmp_path,
        "secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(payload),
    )
    smoke = _write_json(
        tmp_path,
        "secret-smoke-summary.json",
        {"summary_kind": "trino_kerberos_smoke_summary_v1"},
    )
    original = smoke.read_text(encoding="utf-8")
    manifest = _write_json(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": boundary.name,
                    "diagnosis_json": diagnosis.name,
                    "smoke_summary": smoke.name,
                }
            ],
        },
    )

    rc = audit_trino_product_surface_boundary.main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--summary-json",
            str(smoke),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "summary JSON output must differ from every input artifact" in captured.err
    assert smoke.read_text(encoding="utf-8") == original
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-diagnosis.json",
        "secret-smoke-summary.json",
        "secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_product_surface_audit_rejects_manifest_readiness_summary_overlap(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _boundary_for_case("trino_query_detail_export_fixture")
    boundary = _write_json(tmp_path, "secret-boundary.json", payload)
    diagnosis = _write_json(
        tmp_path,
        "secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(payload),
    )
    readiness_summary = _write_json(
        tmp_path,
        "secret-readiness-summary.json",
        {"summary_kind": "trino_compact_readiness_summary_v1"},
    )
    original = readiness_summary.read_text(encoding="utf-8")
    manifest = _write_json(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": boundary.name,
                    "diagnosis_json": diagnosis.name,
                    "readiness_summary_json": readiness_summary.name,
                }
            ],
        },
    )

    rc = audit_trino_product_surface_boundary.main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--summary-json",
            str(readiness_summary),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "summary JSON output must differ from every input artifact" in captured.err
    assert readiness_summary.read_text(encoding="utf-8") == original
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-diagnosis.json",
        "secret-readiness-summary.json",
        "secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_product_surface_audit_rejects_manifest_product_surface_summary_overlap(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _boundary_for_case("trino_query_detail_export_fixture")
    boundary = _write_json(tmp_path, "secret-boundary.json", payload)
    diagnosis = _write_json(
        tmp_path,
        "secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(payload),
    )
    product_surface_summary = _write_json(
        tmp_path,
        "secret-surface-summary.json",
        {"summary_kind": "trino_product_surface_boundary_audit_v1"},
    )
    original = product_surface_summary.read_text(encoding="utf-8")
    manifest = _write_json(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": boundary.name,
                    "diagnosis_json": diagnosis.name,
                    "product_surface_summary_json": product_surface_summary.name,
                }
            ],
        },
    )

    rc = audit_trino_product_surface_boundary.main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--summary-json",
            str(product_surface_summary),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "summary JSON output must differ from every input artifact" in captured.err
    assert product_surface_summary.read_text(encoding="utf-8") == original
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-diagnosis.json",
        "secret-surface-summary.json",
        "secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_product_surface_audit_rejects_manifest_handoff_summary_overlap(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _boundary_for_case("trino_query_detail_export_fixture")
    boundary = _write_json(tmp_path, "secret-boundary.json", payload)
    diagnosis = _write_json(
        tmp_path,
        "secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(payload),
    )
    handoff_summary = _write_json(
        tmp_path,
        "secret-handoff-summary.json",
        {"schema_version": "trino_one_query_handoff_summary_v1"},
    )
    original = handoff_summary.read_text(encoding="utf-8")
    manifest = _write_json(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": boundary.name,
                    "diagnosis_json": diagnosis.name,
                    "handoff_summary_json": handoff_summary.name,
                }
            ],
        },
    )

    rc = audit_trino_product_surface_boundary.main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--summary-json",
            str(handoff_summary),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "summary JSON output must differ from every input artifact" in captured.err
    assert handoff_summary.read_text(encoding="utf-8") == original
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-diagnosis.json",
        "secret-handoff-summary.json",
        "secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_product_surface_audit_handoff_manifest_requires_diagnosis_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_json(
        tmp_path,
        "secret-boundary.json",
        _boundary_for_case("trino_query_detail_export_fixture"),
    )
    manifest = _write_json(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [{"boundary_json": boundary.name}],
        },
    )

    rc = audit_trino_product_surface_boundary.main(["--handoff-suite-manifest", str(manifest)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino product-surface boundary audit: failed" in captured.out
    assert "handoff_diagnosis_artifact_missing" in captured.out
    for fragment in (str(tmp_path), "secret-boundary.json", "secret-handoff-manifest.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_product_surface_audit_handoff_manifest_rejects_bad_kind_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = _write_json(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": "https://coordinator.example.test/raw",
            "entries": [{"boundary_json": "secret-boundary.json"}],
        },
    )

    rc = audit_trino_product_surface_boundary.main(["--handoff-suite-manifest", str(manifest)])

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "handoff manifest JSON input must use the expected manifest kind" in captured.err
    for fragment in (
        str(tmp_path),
        "secret-handoff-manifest.json",
        "secret-boundary.json",
        "coordinator.example.test",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_product_surface_audit_uses_current_diagnosis_no_live_query_boundary() -> None:
    diagnosis = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_query_detail_export_fixture")
    )

    assert diagnosis["diagnosis_boundary"]["live_known_query_diagnosis"] == "not_wired"


def test_trino_product_surface_audit_stays_dev_only_not_console_script() -> None:
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "audit_trino_product_surface_boundary" not in pyproject_text
    assert "query-doctor-audit-trino-product-surface-boundary" not in pyproject_text


def test_trino_product_surface_audit_registry_detects_unexpected_trino_route(monkeypatch) -> None:
    monkeypatch.setattr(
        audit_trino_product_surface_boundary,
        "STATIC_POST_PATHS",
        {"/trino/compact-diagnosis", "/trino/report"},
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_registry_surface(result)

    assert result.issue_counts == {"unexpected_trino_post_route": 1}


def test_trino_product_surface_audit_registry_detects_missing_preview_route(
    monkeypatch,
) -> None:
    monkeypatch.setattr(audit_trino_product_surface_boundary, "STATIC_POST_PATHS", set())
    monkeypatch.setattr(
        audit_trino_product_surface_boundary,
        "PREVIEW_WEB_POST_PATHS",
        frozenset(),
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_registry_surface(result)

    assert result.issue_counts == {"missing_trino_post_route": 1}


def test_trino_product_surface_audit_registry_detects_product_cli_role(monkeypatch) -> None:
    specs = dict(audit_trino_product_surface_boundary.COMMAND_SPECS)
    spec = next(iter(specs.values()))
    specs["trino_report"] = copy.copy(spec)
    monkeypatch.setattr(audit_trino_product_surface_boundary, "COMMAND_SPECS", specs)
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_registry_surface(result)

    assert result.issue_counts["unexpected_trino_cli_role"] == 1
    assert result.issue_counts["trino_product_cli_role_present"] == 1


def test_trino_product_surface_audit_source_boundary_detects_forbidden_import_without_path_echo(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    source = tmp_path / "secret-trusted-report-source.py"
    source.write_text(
        "from query_doctor.trino.diagnosis import build_trino_compact_diagnosis_from_boundary\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        audit_trino_product_surface_boundary,
        "product_surface_source_targets",
        lambda: (
            audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
                module_name="query_doctor.report.secret_surface",
                path=source,
            ),
        ),
    )

    rc = audit_trino_product_surface_boundary.main(["--registry-only"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino product-surface boundary audit: failed" in captured.out
    assert "trino_product_surface_source_import" in captured.out
    assert "query_doctor.trino" not in captured.out
    for fragment in (str(tmp_path), "secret-trusted-report-source.py"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_product_surface_audit_source_boundary_detects_relative_web_import(
    tmp_path: Path,
) -> None:
    source = tmp_path / "secret-specific-query-pages.py"
    source.write_text(
        "from .trino_compact import handle_trino_compact_request\n",
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_product_surface_source_boundaries(
        result,
        targets=(
            audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
                module_name="query_doctor.web.specific_query_pages",
                path=source,
            ),
        ),
    )

    assert result.issue_counts == {"trino_product_surface_source_import": 1}


def test_trino_product_surface_audit_source_boundary_rejects_direct_route_import(
    tmp_path: Path,
) -> None:
    source = tmp_path / "secret-routes.py"
    source.write_text(
        "from query_doctor.web.trino_compact import handle_trino_compact_request\n"
        "from query_doctor.web.ui.trino import render_trino_compact_page\n",
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_product_surface_source_boundaries(
        result,
        targets=(
            audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
                module_name="query_doctor.web.routes",
                path=source,
            ),
        ),
    )

    assert result.issue_counts == {"trino_product_surface_source_import": 1}
    assert result.product_source_module_checked_count == 1


def test_trino_product_surface_audit_source_boundary_allows_preview_registry_import(
    tmp_path: Path,
) -> None:
    source = tmp_path / "secret-routes.py"
    source.write_text(
        "from query_doctor.web.preview_surfaces import preview_surface_for_post_path\n",
        encoding="utf-8",
    )
    registry_source = tmp_path / "secret-preview-surfaces.py"
    registry_source.write_text(
        "from query_doctor.web.trino_compact import handle_trino_compact_request\n"
        "from query_doctor.web.ui.trino import render_trino_compact_page\n",
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_product_surface_source_boundaries(
        result,
        targets=(
            audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
                module_name="query_doctor.web.routes",
                path=source,
            ),
            audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
                module_name="query_doctor.web.preview_surfaces",
                path=registry_source,
            ),
        ),
    )

    assert result.issue_counts == {}
    assert result.product_source_module_checked_count == 2


def _boundary_for_case(case_id: str) -> dict:
    case = next(case for case in trino_golden_cases() if case.case_id == case_id)
    return engine_fact_boundary_payload(case.bundle)


def _write_json(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    return path


def _protected_fragments(tmp_path: Path) -> tuple[str, ...]:
    return (
        str(tmp_path),
        "secret-boundary.json",
        "secret-diagnosis.json",
        "secret-handoff-summary.json",
        "secret-surface-summary.json",
        "first-secret-surface-summary.json",
        "second-secret-surface-summary.json",
    )
