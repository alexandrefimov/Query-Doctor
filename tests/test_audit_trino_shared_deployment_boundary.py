from __future__ import annotations

import json
from pathlib import Path

from scripts import audit_trino_shared_deployment_boundary as audit


def test_trino_shared_deployment_audit_static_mode_pins_boundaries(capsys) -> None:
    rc = audit.main([])

    captured = capsys.readouterr()
    assert rc == 0
    assert captured.err == ""
    assert "Trino shared deployment boundary audit: ok" in captured.out
    assert "front_door_requirement=required_for_shared_trino" in captured.out
    assert "front_door_review=reported_in_summary" in captured.out
    assert "raw_reveal=blocked_for_shared_trino" in captured.out
    assert "contract_docs=4" in captured.out
    assert "details_case_view=raw_free_materialized" in captured.out
    assert "python_report=raw_free_materialized" in captured.out
    assert "optimizer_guidance=raw_free_materialized" in captured.out
    assert "optimizer_behavior=guidance_only" in captured.out
    assert "llm_reports=not_wired" in captured.out
    assert "metadata_cli_smoke=dev_only_optional" in captured.out
    assert "shared_deployment_requirements=accepted=15, not_required=4" in captured.out
    assert "review=shared_deployment" in captured.out
    assert "status=ready" in captured.out
    assert "requirements=accepted=7" in captured.out
    for surface in audit.UNSUPPORTED_TRINO_SHARED_SURFACES:
        assert f"{surface}=blocked" in captured.out
    assert "Issues: none" in captured.out


def test_trino_shared_deployment_audit_accepts_local_trino_config_without_identity(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_config(
        tmp_path,
        "secret-local-config.json",
        {
            "host": "127.0.0.1",
            "trino_support_mode": "production",
            "trino_coordinator_url": "https://secret-trino.example.test",
            "trino_query_info_source_contract": "/private/tmp/secret-query-info-contract.json",
            "trino_query_list_source_contract": "/private/tmp/secret-query-list-contract.json",
        },
    )

    rc = audit.main(["--config", str(config)])

    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    assert rc == 0
    assert "shared_deployment_requirements=accepted=16, not_required=3" in captured.out
    assert "Issues: none" in captured.out
    assert_protected_fragments_hidden(rendered, tmp_path)


def test_trino_shared_deployment_audit_rejects_shared_trino_without_viewer_identity(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_config(
        tmp_path,
        "secret-shared-config.json",
        {
            "host": "0.0.0.0",
            "trino_support_mode": "production",
            "trino_coordinator_url": "https://secret-trino.example.test",
            "trino_query_info_source_contract": "/private/tmp/secret-query-info-contract.json",
            "trino_query_list_source_contract": "/private/tmp/secret-query-list-contract.json",
            "source_owner_user": "secret_analyst",
        },
    )

    rc = audit.main(["--config", str(config)])

    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    assert rc == 1
    assert "Trino shared deployment boundary audit: failed" in captured.out
    assert "shared_trino_missing_trusted_viewer_identity" in captured.out
    assert "shared_trino_front_door_review_missing" in captured.out
    assert "shared_deployment_requirements=accepted=17, missing=2" in captured.out
    assert_protected_fragments_hidden(rendered, tmp_path)


def test_trino_shared_deployment_audit_rejects_shared_owner_raw_source_reveal(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_config(
        tmp_path,
        "secret-owner-raw-config.json",
        {
            "host": "0.0.0.0",
            "viewer_identity_header": "X-Secret-Viewer",
            "source_visibility": "owner_raw",
            "owner_raw_source_enabled": True,
            "trino_support_mode": "production",
            "trino_coordinator_url": "https://secret-trino.example.test",
            "trino_query_info_source_contract": "/private/tmp/secret-query-info-contract.json",
            "trino_query_list_source_contract": "/private/tmp/secret-query-list-contract.json",
        },
    )

    rc = audit.main(["--config", str(config), "--trusted-front-door-reviewed"])

    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    assert rc == 1
    assert "shared_trino_raw_source_reveal_not_isolated" in captured.out
    assert "shared_trino_missing_trusted_viewer_identity" not in captured.out
    assert "shared_trino_front_door_review_missing" not in captured.out
    assert "shared_deployment_requirements=accepted=18, invalid=1" in captured.out
    assert_protected_fragments_hidden(rendered, tmp_path)


def test_trino_shared_deployment_audit_rejects_shared_safe_without_front_door_review(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_config(
        tmp_path,
        "secret-shared-safe-config.json",
        {
            "host": "0.0.0.0",
            "viewer_identity_header": "X-Secret-Viewer",
            "source_visibility": "safe",
            "trino_support_mode": "production",
            "trino_coordinator_url": "https://secret-trino.example.test",
            "trino_query_info_source_contract": "/private/tmp/secret-query-info-contract.json",
            "trino_query_list_source_contract": "/private/tmp/secret-query-list-contract.json",
        },
    )

    rc = audit.main(["--config", str(config)])

    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    assert rc == 1
    assert "Trino shared deployment boundary audit: failed" in captured.out
    assert "shared_trino_front_door_review_missing" in captured.out
    assert "shared_trino_missing_trusted_viewer_identity" not in captured.out
    assert "shared_deployment_requirements=accepted=18, missing=1" in captured.out
    assert_protected_fragments_hidden(rendered, tmp_path)


def test_trino_shared_deployment_audit_accepts_shared_safe_after_front_door_review(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_config(
        tmp_path,
        "secret-shared-safe-config.json",
        {
            "host": "0.0.0.0",
            "viewer_identity_header": "X-Secret-Viewer",
            "source_visibility": "safe",
            "trino_support_mode": "production",
            "trino_coordinator_url": "https://secret-trino.example.test",
            "trino_query_info_source_contract": "/private/tmp/secret-query-info-contract.json",
            "trino_query_list_source_contract": "/private/tmp/secret-query-list-contract.json",
        },
    )

    rc = audit.main(["--config", str(config), "--trusted-front-door-reviewed"])

    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    assert rc == 0
    assert "front_door_review=reported_in_summary" in captured.out
    assert "shared_deployment_requirements=accepted=19" in captured.out
    assert "Issues: none" in captured.out
    assert_protected_fragments_hidden(rendered, tmp_path)


def test_trino_shared_deployment_audit_writes_raw_free_summary(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_config(
        tmp_path,
        "secret-summary-config.json",
        {
            "host": "0.0.0.0",
            "viewer_identity_header": "X-Secret-Viewer",
            "source_visibility": "safe",
            "trino_support_mode": "production",
            "trino_coordinator_url": "https://secret-trino.example.test",
            "trino_query_info_source_contract": "/private/tmp/secret-query-info-contract.json",
            "trino_query_list_source_contract": "/private/tmp/secret-query-list-contract.json",
        },
    )
    summary_path = tmp_path / "secret-summary.json"

    rc = audit.main(
        [
            "--config",
            str(config),
            "--trusted-front-door-reviewed",
            "--summary-json",
            str(summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rendered = captured.out + captured.err + json.dumps(summary, sort_keys=True)
    assert rc == 0
    assert summary["summary_kind"] == "trino_shared_deployment_boundary_audit_v1"
    assert summary["status"] == "ok"
    assert summary["deployment_boundary"]["trusted_front_door_identity"] == (
        "required_for_shared_trino"
    )
    assert summary["deployment_boundary"]["trusted_front_door_review"] == "confirmed"
    assert summary["deployment_boundary"]["raw_source_reveal"] == "blocked_for_shared_trino"
    assert summary["product_boundary"]["details_case_view"] == "raw_free_materialized"
    assert summary["product_boundary"]["metadata_cli_smoke"] == "dev_only_optional"
    assert summary["unsupported_surfaces"]["query_optimizer_jobs"] == "blocked"
    assert summary["counts"]["shared_deployment_doc_checked_count"] == 4
    assert summary["shared_deployment_requirement_tracking_counts"] == {"accepted": 19}
    assert summary["production_review_profile"] == "production_review_shared_deployment_v1"
    assert summary["production_review_profile_status"] == "ready"
    assert summary["production_review_requirements"]["required_families"] == [
        "deployment_boundary",
        "product_boundary",
        "capability_manifest",
        "release_bundle",
        "shared_deployment_docs",
    ]
    assert summary["production_review_requirements"]["required_deployment_config_requirements"] == [
        "config_source_inventory",
        "trusted_front_door_review",
        "trusted_viewer_identity",
        "raw_source_reveal_blocked",
    ]
    assert summary["production_review_requirements"]["required_unsupported_surfaces"] == [
        "running_scan",
        "query_history_crawling",
        "product_metadata_collection",
        "llm_reports",
        "query_optimizer_jobs",
        "generated_trino_sql",
        "sql_execution",
    ]
    assert summary["production_review_tracking_counts"] == {"accepted": 7}
    assert len(summary["production_review_tracking"]) == 7
    assert len(summary["shared_deployment_requirement_tracking"]) == 19
    assert (
        _shared_deployment_tracking_status(
            summary,
            requirement_type="deployment_config",
            requirement_id="trusted_front_door_review",
        )
        == "accepted"
    )
    assert (
        _shared_deployment_tracking_status(
            summary,
            requirement_type="product_boundary",
            requirement_id="unsupported_surfaces_blocked",
        )
        == "accepted"
    )
    assert (
        _shared_deployment_tracking_status(
            summary,
            requirement_type="doc",
            requirement_id="trino_shared_deployment_hardening_doc",
        )
        == "accepted"
    )
    assert summary["issues"] == {"counts": {}, "items": []}
    assert_protected_fragments_hidden(rendered, tmp_path)


def test_trino_shared_deployment_audit_rejects_doc_drift_without_path_echo(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    secret_doc = tmp_path / "secret-hardening-doc.md"
    secret_doc.write_text("trusted front-door viewer identity\n", encoding="utf-8")
    monkeypatch.setattr(
        audit,
        "TRINO_SHARED_DEPLOYMENT_DOC_REQUIREMENTS",
        ((secret_doc, ("secret missing fragment",)),),
    )

    rc = audit.main([])

    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    assert rc == 1
    assert "trino_shared_deployment_doc_drift" in captured.out
    assert "shared_deployment_requirements=accepted=11, invalid=1, not_required=4" in (captured.out)
    assert "secret missing fragment" not in rendered
    assert "secret-hardening-doc" not in rendered
    assert_protected_fragments_hidden(rendered, tmp_path)


def test_trino_shared_deployment_audit_rejects_unsupported_surface_drift(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(audit, "UNSUPPORTED_TRINO_SHARED_SURFACES", ("running_scan",))

    rc = audit.main([])

    captured = capsys.readouterr()
    assert rc == 1
    assert "trino_shared_deployment_unsupported_surface_drift" in captured.out
    assert "shared_deployment_requirements=accepted=14, invalid=1, not_required=4" in (captured.out)


def test_trino_shared_deployment_audit_rejects_missing_review_family(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        audit,
        "TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_FAMILIES",
        (*audit.TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_FAMILIES, "missing_review_family"),
    )

    rc = audit.main([])

    captured = capsys.readouterr()
    assert rc == 1
    assert "trino_shared_deployment_production_review_gap" in captured.out
    assert "review=shared_deployment" in captured.out
    assert "requirements=accepted=6, insufficient=1" in captured.out


def write_config(tmp_path: Path, filename: str, payload: dict[str, object]) -> Path:
    path = tmp_path / filename
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def assert_protected_fragments_hidden(text: str, tmp_path: Path) -> None:
    for fragment in (
        str(tmp_path),
        "/private/tmp",
        "secret-local-config",
        "secret-shared-config",
        "secret-owner-raw-config",
        "secret-shared-safe-config",
        "secret-summary-config",
        "secret-summary",
        "secret-trino.example.test",
        "secret-query-info-contract",
        "secret-query-list-contract",
        "X-Secret-Viewer",
        "secret_analyst",
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    ):
        assert fragment not in text


def _shared_deployment_tracking_status(
    summary: dict[str, object],
    *,
    requirement_type: str,
    requirement_id: str,
) -> str:
    tracking_items = summary["shared_deployment_requirement_tracking"]
    assert isinstance(tracking_items, list)
    for item in tracking_items:
        assert isinstance(item, dict)
        if (
            item["requirement_type"] == requirement_type
            and item["requirement_id"] == requirement_id
        ):
            status = item["tracking_status"]
            assert isinstance(status, str)
            return status
    raise AssertionError(f"missing shared deployment tracking for {requirement_id}")
