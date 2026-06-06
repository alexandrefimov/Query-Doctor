from __future__ import annotations

import json
from pathlib import Path

from query_doctor.analyzer.engine_facts import engine_fact_boundary_payload
from query_doctor.spark.diagnosis import (
    build_spark_compact_diagnosis,
    spark_bundle_for_compact_payload,
)
from scripts import audit_spark_product_surface_boundary
from scripts.audit_spark_compact_readiness import (
    SPARK_ONE_APPLICATION_HANDOFF_SUITE_MANIFEST_BUILDER_KIND,
    SPARK_ONE_APPLICATION_HANDOFF_SUITE_MANIFEST_KIND,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "spark_history_eventlog_compact.json"
)
HISTORY_SERVER_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "spark_history_server_compact_source_warning.json"
)


def test_spark_product_surface_audit_accepts_compact_and_diagnosis_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _load_fixture()
    compact = _write_json(tmp_path, "secret-compact.json", compact_payload)
    diagnosis = _write_json(
        tmp_path,
        "secret-diagnosis.json",
        build_spark_compact_diagnosis(compact_payload),
    )

    rc = audit_spark_product_surface_boundary.main(
        [str(compact), "--diagnosis-json", str(diagnosis)]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Spark product-surface boundary audit: ok" in captured.out
    assert "product_surface=not_promoted" in captured.out
    assert "support_claim=not_claimed" in captured.out
    assert "details_trusted_report_surface=not_wired" in captured.out
    assert "live_known_query_diagnosis=not_wired" in captured.out
    assert "spark_job_execution=not_performed" in captured.out
    assert "compact_json_count=1" in captured.out
    assert "diagnosis_json_checked=1" in captured.out
    assert "spark_product_routes=blocked" in captured.out
    assert "spark_product_cli=blocked" in captured.out
    assert "details_report_source_imports=blocked" in captured.out
    assert "Issues: none" in captured.out
    assert captured.err == ""
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_product_surface_audit_writes_raw_free_summary(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _load_fixture()
    compact = _write_json(tmp_path, "secret-compact.json", compact_payload)
    summary = tmp_path / "secret-summary.json"

    rc = audit_spark_product_surface_boundary.main([str(compact), "--summary-json", str(summary)])

    captured = capsys.readouterr()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    rendered = json.dumps(payload, sort_keys=True)
    assert rc == 0
    assert payload["summary_kind"] == "spark_product_surface_boundary_audit_v1"
    assert payload["status"] == "ok"
    assert payload["boundary"] == {
        "details_trusted_report_surface": "not_wired",
        "live_known_query_diagnosis": "not_wired",
        "live_recent_scan": "not_wired",
        "optimizer_behavior": "not_wired",
        "product_surface": "not_promoted",
        "spark_job_execution": "not_performed",
        "support_claim": "not_claimed",
        "trusted_reports": "not_wired",
    }
    assert payload["counts"]["compact_json_count"] == 1
    assert payload["counts"]["diagnosis_json_checked_count"] == 0
    assert payload["counts"]["diagnostic_lane_checked_count"] == 1
    assert payload["counts"]["static_support_check_count"] > 0
    assert payload["counts"]["supported_attention_area_count"] >= 1
    assert payload["registry"]["spark_product_routes"] == "blocked"
    assert payload["registry"]["spark_product_cli"] == "blocked"
    assert payload["registry"]["details_report_source_imports"] == "blocked"
    assert payload["diagnostic_lane"]["schema_version"] == "spark_compact_diagnostic_lane_v1"
    assert payload["diagnostic_lane"]["readiness"]["compact_attention_ready"] == 1
    assert payload["diagnostic_lane"]["source_granularity"]["fixture_compact"] == 1
    assert payload["diagnostic_lane"]["verification_scope"]["fixture_contract_review"] == 1
    assert payload["fact_states"]["supported"] >= 1
    assert payload["issues"] == {"counts": {}, "items": []}
    assert "Spark product-surface boundary audit: ok" in captured.out
    for text in (captured.out, captured.err, rendered):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_spark_product_surface_audit_accepts_one_application_manifest_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _load_history_server_fixture()
    manifest = _write_one_application_manifest(tmp_path, compact_payload)

    rc = audit_spark_product_surface_boundary.main(
        ["--one-application-handoff-suite-manifest", str(manifest)]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Spark product-surface boundary audit: ok" in captured.out
    assert "compact_json_count=1" in captured.out
    assert "diagnosis_json_checked=1" in captured.out
    assert "Issues: none" in captured.out
    for fragment in (
        *_protected_fragments(tmp_path),
        "secret-boundary.json",
        "secret-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_product_surface_audit_checks_retained_product_summary_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _load_history_server_fixture()
    manifest = _write_one_application_manifest(
        tmp_path,
        compact_payload,
        include_product_surface_summary=True,
    )

    rc = audit_spark_product_surface_boundary.main(
        ["--one-application-handoff-suite-manifest", str(manifest)]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Spark product-surface boundary audit: ok" in captured.out
    assert "diagnosis_json_checked=1" in captured.out
    assert "Issues: none" in captured.out
    for fragment in (
        *_protected_fragments(tmp_path),
        "secret-boundary.json",
        "secret-manifest.json",
        "secret-surface-summary.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_product_surface_audit_rejects_retained_product_summary_counter_drift(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _load_history_server_fixture()
    manifest = _write_one_application_manifest(
        tmp_path,
        compact_payload,
        include_product_surface_summary=True,
    )
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    product_summary = tmp_path / manifest_payload["entries"][0]["product_surface_summary_json"]
    payload = json.loads(product_summary.read_text(encoding="utf-8"))
    payload.pop("diagnostic_lane")
    product_summary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    rc = audit_spark_product_surface_boundary.main(
        ["--one-application-handoff-suite-manifest", str(manifest)]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Spark product-surface boundary audit: failed" in captured.out
    assert "product_surface_summary_mismatch" in captured.out
    for fragment in (
        *_protected_fragments(tmp_path),
        "secret-boundary.json",
        "secret-manifest.json",
        "secret-surface-summary.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_product_surface_audit_rejects_retained_product_summary_drift_without_value_echo(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _load_history_server_fixture()
    manifest = _write_one_application_manifest(
        tmp_path,
        compact_payload,
        include_product_surface_summary=True,
        product_summary_status="drifted",
    )

    rc = audit_spark_product_surface_boundary.main(
        ["--one-application-handoff-suite-manifest", str(manifest)]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Spark product-surface boundary audit: failed" in captured.out
    assert "product_surface_summary_mismatch" in captured.out
    for fragment in (
        *_protected_fragments(tmp_path),
        "secret-boundary.json",
        "secret-manifest.json",
        "secret-surface-summary.json",
        "drifted",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_product_surface_audit_rejects_manifest_summary_overlap_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _load_history_server_fixture()
    manifest = _write_one_application_manifest(
        tmp_path,
        compact_payload,
        include_product_surface_summary=True,
    )
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    product_summary = tmp_path / manifest_payload["entries"][0]["product_surface_summary_json"]

    rc = audit_spark_product_surface_boundary.main(
        [
            "--one-application-handoff-suite-manifest",
            str(manifest),
            "--summary-json",
            str(product_summary),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "summary JSON output must differ from every input artifact" in captured.err
    for fragment in (
        *_protected_fragments(tmp_path),
        "secret-boundary.json",
        "secret-manifest.json",
        "secret-surface-summary.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_product_surface_audit_rejects_diagnosis_lane_drift_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _load_fixture()
    diagnosis_payload = build_spark_compact_diagnosis(compact_payload)
    diagnosis_payload["diagnostic_lane"]["promotion_status"] = "supported"
    compact = _write_json(tmp_path, "secret-compact.json", compact_payload)
    diagnosis = _write_json(tmp_path, "secret-diagnosis.json", diagnosis_payload)

    rc = audit_spark_product_surface_boundary.main(
        [str(compact), "--diagnosis-json", str(diagnosis)]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Spark product-surface boundary audit: failed" in captured.out
    assert "diagnosis_artifact_mismatch" in captured.out
    assert "diagnostic_lane_product_promotion_drift" in captured.out
    for fragment in (*_protected_fragments(tmp_path), "supported"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_product_surface_audit_rejects_raw_like_diagnosis_without_value_echo(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _load_fixture()
    diagnosis_payload = build_spark_compact_diagnosis(compact_payload)
    diagnosis_payload["unsafe_note"] = "SELECT secret_col FROM guarded_table"
    compact = _write_json(tmp_path, "secret-compact.json", compact_payload)
    diagnosis = _write_json(tmp_path, "secret-diagnosis.json", diagnosis_payload)

    rc = audit_spark_product_surface_boundary.main(
        [str(compact), "--diagnosis-json", str(diagnosis)]
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


def test_spark_product_surface_audit_supports_registry_only_mode(capsys) -> None:
    rc = audit_spark_product_surface_boundary.main(["--registry-only"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "compact_json_count=0" in captured.out
    assert "spark_product_routes=blocked" in captured.out
    assert "spark_product_cli=blocked" in captured.out
    assert "details_report_source_imports=blocked" in captured.out
    assert "Issues: none" in captured.out


def test_spark_product_surface_audit_rejects_summary_overlap_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    compact = _write_json(tmp_path, "secret-compact.json", _load_fixture())

    rc = audit_spark_product_surface_boundary.main([str(compact), "--summary-json", str(compact)])

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "summary JSON output must differ from every input artifact" in captured.err
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.err


def test_spark_product_surface_audit_stays_dev_only_not_console_script() -> None:
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "audit_spark_product_surface_boundary" not in pyproject_text
    assert "query-doctor-audit-spark-product-surface-boundary" not in pyproject_text


def test_spark_product_surface_audit_registry_detects_unexpected_spark_route(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        audit_spark_product_surface_boundary,
        "STATIC_POST_PATHS",
        {"/spark/compact-diagnosis", "/spark/report"},
    )
    result = audit_spark_product_surface_boundary.SparkProductSurfaceAuditResult()

    audit_spark_product_surface_boundary.audit_preview_route_boundary(result)

    assert result.issue_counts == {"unexpected_spark_post_route": 1}


def test_spark_product_surface_audit_registry_detects_missing_preview_route(
    monkeypatch,
) -> None:
    monkeypatch.setattr(audit_spark_product_surface_boundary, "STATIC_POST_PATHS", set())
    monkeypatch.setattr(
        audit_spark_product_surface_boundary,
        "PREVIEW_WEB_POST_PATHS",
        frozenset(),
    )
    monkeypatch.setattr(
        audit_spark_product_surface_boundary,
        "PREVIEW_WEB_POST_SURFACES",
        {},
    )
    result = audit_spark_product_surface_boundary.SparkProductSurfaceAuditResult()

    audit_spark_product_surface_boundary.audit_preview_route_boundary(result)

    assert result.issue_counts == {"missing_spark_post_route": 1}


def test_spark_product_surface_audit_static_boundary_issues_are_path_free(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    compact = _write_json(tmp_path, "secret-compact.json", _load_fixture())
    support_result = audit_spark_product_surface_boundary.SparkProductSurfaceAuditResult()
    support_issue = audit_spark_product_surface_boundary.SparkProductSurfaceAuditIssue(
        category="product_surface_imports",
        message="Spark compact modules must not be imported by product surfaces.",
    )

    class StaticSupportResult:
        checks = {"product_surface_imports": "failed"}
        issues = [support_issue]

    monkeypatch.setattr(
        audit_spark_product_surface_boundary,
        "audit_spark_support_boundary",
        lambda: StaticSupportResult(),
    )
    audit_spark_product_surface_boundary.audit_static_support_boundary(support_result)
    assert support_result.issue_counts == {"support_boundary_product_surface_imports": 1}

    rc = audit_spark_product_surface_boundary.main([str(compact)])
    captured = capsys.readouterr()

    assert rc == 1
    assert "support_boundary_product_surface_imports" in captured.out
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _load_history_server_fixture() -> dict:
    return json.loads(HISTORY_SERVER_FIXTURE.read_text(encoding="utf-8"))


def _write_json(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    return path


def _write_one_application_manifest(
    tmp_path: Path,
    compact_payload: dict,
    *,
    include_product_surface_summary: bool = False,
    product_summary_status: str = "ok",
) -> Path:
    compact = _write_json(tmp_path, "secret-compact.json", compact_payload)
    diagnosis = _write_json(
        tmp_path,
        "secret-diagnosis.json",
        build_spark_compact_diagnosis(compact_payload),
    )
    boundary = _write_json(
        tmp_path,
        "secret-boundary.json",
        engine_fact_boundary_payload(spark_bundle_for_compact_payload(compact_payload)),
    )
    entry = {
        "compact_json": compact.name,
        "diagnosis_json": diagnosis.name,
        "boundary_facts_json": boundary.name,
    }
    limitations = [
        "retained_one_application_artifacts",
        "not_spark_product_support",
    ]
    if include_product_surface_summary:
        product_summary = _write_json(
            tmp_path,
            "secret-surface-summary.json",
            _product_surface_summary_payload(
                compact,
                diagnosis,
                status=product_summary_status,
            ),
        )
        entry["product_surface_summary_json"] = product_summary.name
        limitations.append("product_surface_summary_checked")
    return _write_json(
        tmp_path,
        "secret-manifest.json",
        {
            "manifest_kind": SPARK_ONE_APPLICATION_HANDOFF_SUITE_MANIFEST_KIND,
            "metadata": {
                "builder_kind": SPARK_ONE_APPLICATION_HANDOFF_SUITE_MANIFEST_BUILDER_KIND,
                "entry_count": 1,
                "path_reference": "relative_to_manifest",
                "redaction_reviewed": True,
                "limitations": limitations,
            },
            "entries": [entry],
        },
    )


def _product_surface_summary_payload(
    compact: Path,
    diagnosis: Path,
    *,
    status: str,
) -> dict[str, object]:
    result = audit_spark_product_surface_boundary.SparkProductSurfaceAuditResult()
    audit_spark_product_surface_boundary.audit_static_support_boundary(result)
    audit_spark_product_surface_boundary.audit_preview_route_boundary(result)
    audit_spark_product_surface_boundary.audit_compact_inputs(
        result,
        (compact,),
        diagnosis_jsons=(diagnosis,),
    )
    payload = audit_spark_product_surface_boundary.product_surface_summary_payload(
        result,
        status="ok" if result.ok else "failed",
    )
    payload["status"] = status
    return payload


def _protected_fragments(tmp_path: Path) -> tuple[str, ...]:
    return (
        str(tmp_path),
        "secret-compact.json",
        "secret-diagnosis.json",
        "secret-summary.json",
        "secret-surface-summary.json",
    )
