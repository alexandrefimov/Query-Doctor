from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

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


def test_trino_product_surface_audit_includes_release_and_config_claim_surfaces() -> None:
    claim_paths = audit_trino_product_surface_boundary.TRINO_PUBLIC_CLAIM_PATHS
    changelog = REPO_ROOT / "docs" / "changelog.md"
    docs_index = REPO_ROOT / "docs" / "README.md"
    ru_docs_index = REPO_ROOT / "docs" / "i18n" / "ru" / "README.md"
    engines_index = REPO_ROOT / "docs" / "engines" / "README.md"
    ru_config = REPO_ROOT / "docs" / "i18n" / "ru" / "configuration.md"
    release_checklist = REPO_ROOT / "docs" / "release-checklist.md"
    safety_contract = REPO_ROOT / "docs" / "safety-contract.md"
    ru_safety_contract = REPO_ROOT / "docs" / "i18n" / "ru" / "safety-contract.md"
    public_readiness = REPO_ROOT / "docs" / "public-release-readiness.md"

    assert changelog in claim_paths
    assert docs_index in claim_paths
    assert ru_docs_index in claim_paths
    assert engines_index in claim_paths
    assert REPO_ROOT / "docs" / "configuration.md" in claim_paths
    assert ru_config in claim_paths
    assert REPO_ROOT / "docs" / "i18n" / "ru" / "engine-support-gap-matrix.md" not in claim_paths
    assert safety_contract in claim_paths
    assert ru_safety_contract in claim_paths
    assert release_checklist in claim_paths
    assert REPO_ROOT / "docs" / "i18n" / "ru" / "release-checklist.md" not in claim_paths
    assert public_readiness in claim_paths
    assert REPO_ROOT / "docs" / "i18n" / "ru" / "public-release-readiness.md" not in claim_paths
    assert REPO_ROOT / "query_doctor" / "web" / "ui" / "trino_demo.py" in claim_paths
    ru_text = ru_config.read_text(encoding="utf-8")
    ru_config_text = _normalized_text(ru_config)
    ru_docs_index_text = _normalized_text(ru_docs_index)
    assert "Trino Local Recent и One Query ID" in ru_text
    assert "Production mode означает local production support только для этих surfaces" in (
        ru_config_text
    )
    assert "SQL execution" in ru_text
    assert "engine deep-dive документы остаются English-only" in ru_docs_index_text
    assert "engine-support-gap-matrix.md" in ru_docs_index_text
    readiness_text = _normalized_text(public_readiness)
    assert "local production web Trino retained-list Recent" in readiness_text
    assert (
        "broader/shared Trino production support beyond the local retained-list Recent, "
        "One Query ID, raw-free materialized Details, Python Report, and optimizer "
        "guidance local production lanes" in readiness_text
    )
    checklist_text = _normalized_text(release_checklist)
    safety_text = _normalized_text(safety_contract)
    ru_safety_text = _normalized_text(ru_safety_contract)
    assert "local production web Trino retained-list Recent lane" in checklist_text
    assert (
        "broader/shared Trino production support beyond the local retained-list Recent, "
        "One Query ID, raw-free materialized Details, Python Report, and optimizer "
        "guidance local production lanes" in checklist_text
    )
    assert (
        "local web retained-list Recent over one bounded retained pruned coordinator query-list read"
        in (safety_text)
    )
    assert "Trino One Query ID uses one bounded pruned coordinator QueryInfo read" in (safety_text)
    assert "does not enable Recent/Running" not in safety_text
    assert (
        "local web retained-list Recent через один bounded retained pruned coordinator query-list read"
        in (ru_safety_text)
    )
    assert "Trino One Query ID использует один bounded pruned coordinator QueryInfo read" in (
        ru_safety_text
    )
    assert (
        "local production Trino retained-list Recent, One Query ID, raw-free materialized "
        "Details, Python Report, and optimizer guidance UI surfaces" in _normalized_text(docs_index)
    )
    engines_text = _normalized_text(engines_index)
    assert "full production triage support remains Apache Impala" in engines_text
    assert (
        "local production Trino retained-list Recent, One Query ID, raw-free materialized "
        "Details, Python Report, and optimizer guidance surfaces" in engines_text
    )
    assert "Do not add LLM reports, Query Optimizer jobs, metadata, SQL execution" in engines_text
    changelog_text = _normalized_text(changelog)
    assert "Trino Beta One Query ID" in changelog_text
    assert "broader/shared Trino expansion remain blocked" in (changelog_text)
    assert "SQL execution" in changelog_text


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
    assert (
        "product_surface=recent_query_id_raw_free_details_python_report_optimizer_guidance"
        in captured.out
    )
    assert "support_claim=local_production" in captured.out
    assert "details_case_view=raw_free_materialized" in captured.out
    assert "python_report=raw_free_materialized" in captured.out
    assert "optimizer_guidance=raw_free_materialized" in captured.out
    assert "optimizer_behavior=guidance_only" in captured.out
    assert "llm_reports=not_wired" in captured.out
    assert "live_known_query_diagnosis=one_query_pruned_query_info_local_production" in captured.out
    assert "trino_sql_execution=not_performed" in captured.out
    assert "boundary_json_count=1" in captured.out
    assert "diagnosis_json_checked=1" in captured.out
    assert (
        "trino_product_routes=recent_query_id_raw_free_details_python_report_optimizer_guidance"
        in captured.out
    )
    assert "trino_product_cli=blocked" in captured.out
    assert "details_python_report_guidance_source_imports=raw_free_materialized" in captured.out
    assert "product_source_modules_checked=" in captured.out
    assert "allowed_trino_preview_imports=" in captured.out
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
    }
    assert summary["counts"]["boundary_json_count"] == 1
    assert summary["counts"]["diagnosis_json_checked_count"] == 0
    assert summary["counts"]["diagnostic_lane_checked_count"] == 1
    assert summary["counts"]["product_source_modules_checked_count"] > 0
    assert summary["counts"]["product_source_allowed_trino_import_count"] > 0
    assert summary["counts"]["supported_attention_area_count"] >= 1
    assert summary["diagnostic_lane"] == {
        "evidence_readiness": {"one_query_attention_ready": 1},
        "fact_states": diagnosis["diagnostic_lane"]["fact_state_counts"],
        "source_granularity": {"one_query_boundary": 1},
        "verification_scope": {"comparable_one_query_rerun": 1},
    }
    assert summary["registry"]["trino_product_routes"] == (
        "recent_query_id_raw_free_details_python_report_optimizer_guidance"
    )
    assert summary["registry"]["trino_product_cli"] == "blocked"
    assert summary["registry"]["details_python_report_guidance_source_imports"] == (
        "raw_free_materialized"
    )
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
    assert (
        summary["boundary"]["live_known_query_diagnosis"]
        == "one_query_pruned_query_info_local_production"
    )
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
    assert (
        "trino_product_routes=recent_query_id_raw_free_details_python_report_optimizer_guidance"
        in captured.out
    )
    assert "trino_product_cli=blocked" in captured.out
    assert "details_python_report_guidance_source_imports=raw_free_materialized" in captured.out
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


def test_trino_product_surface_audit_rejects_manifest_smoke_overlap_with_diagnosis(
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
    manifest = _write_json(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": boundary.name,
                    "diagnosis_json": diagnosis.name,
                    "smoke_summary": diagnosis.name,
                }
            ],
        },
    )

    rc = audit_trino_product_surface_boundary.main(["--handoff-suite-manifest", str(manifest)])

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert (
        "handoff manifest JSON input smoke summary artifacts must differ from boundary, diagnosis, readiness summary, handoff summary, and product-surface summary artifacts"
        in captured.err
    )
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-diagnosis.json",
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


def test_trino_product_surface_audit_registry_detects_product_allowed_preview_surface(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        audit_trino_product_surface_boundary,
        "PREVIEW_WEB_SURFACES",
        (
            SimpleNamespace(
                engine="trino",
                surface_id="compact_diagnosis",
                route_path="/trino/compact-diagnosis",
                product_surface_allowed=True,
            ),
        ),
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_registry_surface(result)

    assert result.issue_counts == {"trino_preview_surface_product_allowed": 1}


def test_trino_product_surface_audit_registry_detects_unexpected_preview_surface(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        audit_trino_product_surface_boundary,
        "PREVIEW_WEB_SURFACES",
        (
            SimpleNamespace(
                engine="trino",
                surface_id="details",
                route_path="/trino/details",
                product_surface_allowed=False,
            ),
        ),
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_registry_surface(result)

    assert result.issue_counts == {"unexpected_trino_preview_surface": 1}


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
    assert result.product_source_allowed_trino_import_count == 0


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
    assert result.product_source_allowed_trino_import_count == 3


def test_trino_product_surface_audit_source_boundary_allows_readiness_support_mode_import(
    tmp_path: Path,
) -> None:
    source = tmp_path / "secret-deployment-readiness.py"
    source.write_text(
        "from query_doctor.trino.support_mode import trino_support_mode_enabled\n",
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_product_surface_source_boundaries(
        result,
        targets=(
            audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
                module_name="query_doctor.web.deployment_readiness",
                path=source,
            ),
        ),
    )

    assert result.issue_counts == {}
    assert result.product_source_module_checked_count == 1
    assert result.product_source_allowed_trino_import_count == 1


def test_trino_product_surface_audit_source_boundary_allows_read_only_trino_demo_imports(
    tmp_path: Path,
) -> None:
    pages_source = tmp_path / "secret-pages.py"
    pages_source.write_text(
        "from query_doctor.web.ui.trino_demo import render_trino_demo_sections\n",
        encoding="utf-8",
    )
    demo_source = tmp_path / "secret-trino-demo.py"
    demo_source.write_text(
        "from query_doctor.web.ui.trino import render_trino_boundary\n",
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_product_surface_source_boundaries(
        result,
        targets=(
            audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
                module_name="query_doctor.web.ui.pages",
                path=pages_source,
            ),
            audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
                module_name="query_doctor.web.ui.trino_demo",
                path=demo_source,
            ),
        ),
    )

    assert result.issue_counts == {}
    assert result.product_source_module_checked_count == 2
    assert result.product_source_allowed_trino_import_count == 2


def test_trino_beta_query_module_boundary_rejects_report_optimizer_or_action_imports(
    tmp_path: Path,
) -> None:
    source = tmp_path / "trino_beta_query.py"
    source.write_text(
        "\n".join(
            (
                "from query_doctor.report.markdown import render_report",
                "from query_doctor.optimizer.analysis import analyze_query_optimizer",
                "from query_doctor.web.specific_query_actions import start_specific_query_report_job",
            )
        ),
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_trino_beta_query_module_boundary(
        result,
        target=audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
            module_name="query_doctor.web.trino_beta_query",
            path=source,
        ),
    )

    assert result.issue_counts == {"trino_beta_query_forbidden_import": 1}


def test_trino_beta_query_module_boundary_allows_bounded_query_info_imports(
    tmp_path: Path,
) -> None:
    source = tmp_path / "trino_beta_query.py"
    source.write_text(
        "\n".join(
            (
                "from query_doctor.trino.coordinator_query_info_pruned_import import load_trino_coordinator_query_info_pruned_import",
                "from query_doctor.trino.coordinator_query_info_target import validate_trino_coordinator_query_info_target",
                "from query_doctor.trino.diagnosis import build_trino_compact_diagnosis_from_boundary",
                "from query_doctor.web.models import WebError",
            )
        ),
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_trino_beta_query_module_boundary(
        result,
        target=audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
            module_name="query_doctor.web.trino_beta_query",
            path=source,
        ),
    )

    assert result.issue_counts == {}


def test_trino_report_module_boundary_rejects_optimizer_or_action_imports(
    tmp_path: Path,
) -> None:
    source = tmp_path / "trino_report.py"
    source.write_text(
        "\n".join(
            (
                "from query_doctor.optimizer.analysis import analyze_query_optimizer",
                "from query_doctor.web.batch_case_actions import start_batch_case_report_job",
                "from query_doctor.web.trusted_artifacts import load_specific_query_trusted_report_artifact",
                "import subprocess",
            )
        ),
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_trino_report_module_boundary(
        result,
        target=audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
            module_name="query_doctor.web.trino_report",
            path=source,
        ),
    )

    assert result.issue_counts == {"trino_report_forbidden_import": 1}


def test_trino_report_module_boundary_rejects_legacy_report_or_optimizer_markers(
    tmp_path: Path,
) -> None:
    source = tmp_path / "trino_report.py"
    source.write_text(
        "\n".join(
            (
                "def render():",
                "    return (",
                "        '<a href=\"/python-report/secret\">Python Report</a>'",
                "        '<a href=\"/optimizer\">Run optimizer</a>'",
                "        '<button data-case-action=\"llm-report\">LLM narrative</button>'",
                "    )",
            )
        ),
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_trino_report_module_boundary(
        result,
        target=audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
            module_name="query_doctor.web.trino_report",
            path=source,
        ),
    )

    assert result.issue_counts == {"trino_report_forbidden_surface_marker": 1}


def test_trino_report_module_boundary_allows_raw_free_report_validation_imports(
    tmp_path: Path,
) -> None:
    source = tmp_path / "trino_report.py"
    source.write_text(
        "\n".join(
            (
                "import html",
                "from query_doctor.report.safety_validation import contains_raw_sql_like_text",
                "from query_doctor.safety.browser_display import redact_browser_display_text",
                "from query_doctor.web.trino_details import load_trino_details_view",
                "from query_doctor.web.ui.markdown import render_report_markdown_html",
                "REPORT_LINK = '?report=python'",
            )
        ),
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_trino_report_module_boundary(
        result,
        target=audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
            module_name="query_doctor.web.trino_report",
            path=source,
        ),
    )

    assert result.issue_counts == {}


def test_trino_guidance_module_boundary_rejects_optimizer_job_or_action_imports(
    tmp_path: Path,
) -> None:
    source = tmp_path / "trino_guidance.py"
    source.write_text(
        "\n".join(
            (
                "from query_doctor.optimizer.analysis import analyze_query_optimizer",
                "from query_doctor.web.batch_case_actions import start_batch_case_optimized_query_job",
                "from query_doctor.web.trusted_artifacts import load_specific_query_trusted_report_artifact",
                "import subprocess",
            )
        ),
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_trino_guidance_module_boundary(
        result,
        target=audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
            module_name="query_doctor.web.trino_guidance",
            path=source,
        ),
    )

    assert result.issue_counts == {"trino_guidance_forbidden_import": 1}


def test_trino_guidance_module_boundary_rejects_optimizer_job_markers(
    tmp_path: Path,
) -> None:
    source = tmp_path / "trino_guidance.py"
    source.write_text(
        "\n".join(
            (
                "def render():",
                "    return (",
                "        '<a href=\"/optimizer\">Run optimizer</a>'",
                "        '<button data-case-action=\"optimized-query\">Query LLM optimizer</button>'",
                "    )",
            )
        ),
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_trino_guidance_module_boundary(
        result,
        target=audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
            module_name="query_doctor.web.trino_guidance",
            path=source,
        ),
    )

    assert result.issue_counts == {"trino_guidance_forbidden_surface_marker": 1}


def test_trino_guidance_module_boundary_allows_raw_free_guidance_validation_imports(
    tmp_path: Path,
) -> None:
    source = tmp_path / "trino_guidance.py"
    source.write_text(
        "\n".join(
            (
                "import html",
                "from query_doctor.report.safety_validation import contains_raw_sql_like_text",
                "from query_doctor.safety.browser_display import redact_browser_display_text",
                "from query_doctor.web.trino_details import load_trino_details_view",
                "from query_doctor.web.ui.markdown import render_report_markdown_html",
                "GUIDANCE_LINK = '?guidance=optimizer'",
            )
        ),
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_trino_guidance_module_boundary(
        result,
        target=audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
            module_name="query_doctor.web.trino_guidance",
            path=source,
        ),
    )

    assert result.issue_counts == {}


def test_trino_beta_ui_module_boundary_rejects_details_report_or_optimizer_imports(
    tmp_path: Path,
) -> None:
    source = tmp_path / "trino.py"
    source.write_text(
        "\n".join(
            (
                "from query_doctor.web.ui.specific_query import render_specific_query_detail",
                "from query_doctor.web.ui.report import render_report_page",
                "from query_doctor.optimizer.analysis import analyze_query_optimizer",
            )
        ),
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_trino_beta_ui_module_boundary(
        result,
        target=audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
            module_name="query_doctor.web.ui.trino",
            path=source,
        ),
    )

    assert result.issue_counts == {"trino_beta_ui_forbidden_import": 1}


def test_trino_beta_ui_module_boundary_rejects_details_report_or_optimizer_markers(
    tmp_path: Path,
) -> None:
    source = tmp_path / "trino.py"
    source.write_text(
        "\n".join(
            (
                "def render():",
                "    return (",
                "        '<a href=\"/query/details/20260603_120102_00001_abcde\">Details</a>'",
                "        '<a href=\"/optimizer\">Run optimizer</a>'",
                "        '<button data-case-action=\"report\">Python Report</button>'",
                "    )",
            )
        ),
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_trino_beta_ui_module_boundary(
        result,
        target=audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
            module_name="query_doctor.web.ui.trino",
            path=source,
        ),
    )

    assert result.issue_counts == {"trino_beta_ui_forbidden_surface_marker": 1}


def test_trino_beta_ui_modules_boundary_checks_read_only_demo_renderer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    trino_source = tmp_path / "trino.py"
    trino_source.write_text("import html\n", encoding="utf-8")
    demo_source = tmp_path / "trino_demo.py"
    demo_source.write_text(
        "\n".join(
            (
                "def render():",
                "    return '<a href=\"/query/details/20260603_120102_00001_abcde\">Details</a>'",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        audit_trino_product_surface_boundary,
        "trino_beta_ui_module_targets",
        lambda: (
            audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
                module_name="query_doctor.web.ui.trino",
                path=trino_source,
            ),
            audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
                module_name="query_doctor.web.ui.trino_demo",
                path=demo_source,
            ),
        ),
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_trino_beta_ui_modules_boundary(result)

    assert result.issue_counts == {"trino_beta_ui_forbidden_surface_marker": 1}


def test_trino_beta_ui_module_boundary_allows_safe_rendering_imports(tmp_path: Path) -> None:
    source = tmp_path / "trino.py"
    source.write_text(
        "\n".join(
            (
                "import html",
                "from collections.abc import Mapping",
                "from query_doctor.web.display_safety import sanitize_browser_error_text",
                "from query_doctor.web.ui.pages import render_page",
                "BOUNDARY_COPY = 'not Recent, Details, trusted report, or optimizer support'",
            )
        ),
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_trino_beta_ui_module_boundary(
        result,
        target=audit_trino_product_surface_boundary.ProductSurfaceSourceTarget(
            module_name="query_doctor.web.ui.trino",
            path=source,
        ),
    )

    assert result.issue_counts == {}


def test_trino_product_surface_audit_detects_public_claim_boundary_gaps(
    tmp_path: Path,
) -> None:
    claim_surface = tmp_path / "secret-public-claim.md"
    claim_surface.write_text(
        "Trino Beta One Query ID and Recent are available.\n", encoding="utf-8"
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_public_trino_claim_boundaries(
        result,
        paths=(claim_surface,),
    )

    assert result.public_claim_surface_checked_count == 1
    assert result.issue_counts == {"trino_public_claim_boundary_incomplete": 1}


def test_trino_product_surface_audit_detects_public_forbidden_support_claim(
    tmp_path: Path,
) -> None:
    claim_surface = tmp_path / "secret-public-claim.md"
    claim_surface.write_text(
        (
            "Trino Beta Recent and One Query ID local production. Running query-history crawling "
            "metadata collection Details Python Report optimizer guidance LLM reports optimizer SQL execution. "
            "Trino broad production support is enabled."
        ),
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_public_trino_claim_boundaries(
        result,
        paths=(claim_surface,),
    )

    assert result.public_claim_surface_checked_count == 1
    assert result.issue_counts == {"trino_public_forbidden_support_claim": 1}


def test_trino_product_surface_audit_detects_stale_recent_denial(
    tmp_path: Path,
) -> None:
    claim_surface = tmp_path / "secret-public-claim.md"
    claim_surface.write_text(
        (
            "Trino Beta Recent and One Query ID local production. Running query-history crawling "
            "metadata collection Details Python Report optimizer guidance LLM reports optimizer SQL execution. "
            "The old Query ID exception does not enable Recent/Running."
        ),
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_public_trino_claim_boundaries(
        result,
        paths=(claim_surface,),
    )

    assert result.public_claim_surface_checked_count == 1
    assert result.issue_counts == {"trino_public_forbidden_support_claim": 1}


def test_trino_product_surface_audit_detects_russian_forbidden_support_claim(
    tmp_path: Path,
) -> None:
    claim_surface = tmp_path / "secret-public-claim-ru.md"
    claim_surface.write_text(
        (
            "Trino Beta Recent and One Query ID local production. Running query-history crawling "
            "metadata collection Details Python Report optimizer guidance LLM reports optimizer SQL execution. "
            "production Trino support доступен."
        ),
        encoding="utf-8",
    )
    result = audit_trino_product_surface_boundary.TrinoProductSurfaceAuditResult()

    audit_trino_product_surface_boundary.audit_public_trino_claim_boundaries(
        result,
        paths=(claim_surface,),
    )

    assert result.public_claim_surface_checked_count == 1
    assert result.issue_counts == {"trino_public_forbidden_support_claim": 1}


def _boundary_for_case(case_id: str) -> dict:
    case = next(case for case in trino_golden_cases() if case.case_id == case_id)
    return engine_fact_boundary_payload(case.bundle)


def _write_json(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    return path


def _normalized_text(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


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
