from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from scripts import audit_owner_raw_sso_proxy_support_readiness as readiness


def write_json(tmp_path: Path, name: str, payload: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def ready_bundle_summary(final_source_state: str = "leave_enabled") -> dict[str, object]:
    return {
        "summary_kind": "owner_raw_d3_deployment_bundle_v1",
        "status": "ok",
        "deployment": {
            "bundle_ready": True,
            "verdict": "ready",
            "final_source_state": final_source_state,
            "source_enabled_by_script": False,
            "native_auth_added": False,
            "live_review_required": True,
            "raw_values_output": False,
            "paths_printed": False,
            "header_names_printed": False,
            "header_values_printed": False,
            "users_printed": False,
            "urls_printed": False,
            "query_ids_printed": False,
            "auth_material_printed": False,
            "raw_source_printed": False,
        },
        "gates": {
            "front_door_review_audit": {
                "status": "ok",
                "issue_counts": {},
                "metadata": {
                    "review_profile": "owner_raw_d3",
                    "checked_required_fields": 26,
                    "raw_values_output": False,
                },
            },
            "readiness": {
                "status": "ok",
                "issue_counts": {},
                "metadata": {
                    "source_enable_ready": True,
                    "current_config_owner_raw_source": "disabled",
                    "native_auth_added": False,
                    "live_review_required": True,
                    "raw_values_output": False,
                    "paths_printed": False,
                    "header_names_printed": False,
                    "header_values_printed": False,
                    "users_printed": False,
                    "urls_printed": False,
                    "query_ids_printed": False,
                    "auth_material_printed": False,
                    "raw_source_printed": False,
                },
            },
            "rehearsal": {
                "status": "ok",
                "issue_counts": {},
                "metadata": {
                    "rehearsal_complete": True,
                    "source_enable_ready": True,
                    "current_config_owner_raw_source": "disabled",
                    "native_auth_added": False,
                    "live_review_required": True,
                    "raw_values_output": False,
                    "paths_printed": False,
                    "header_names_printed": False,
                    "header_values_printed": False,
                    "users_printed": False,
                    "urls_printed": False,
                    "query_ids_printed": False,
                    "auth_material_printed": False,
                    "raw_source_printed": False,
                },
            },
            "source_enable": {
                "status": "ok",
                "issue_counts": {},
                "metadata": {
                    "canary_ready": True,
                    "previous_owner_raw_source": "disabled",
                    "planned_owner_raw_source": "enabled",
                    "source_enabled_by_script": False,
                    "native_auth_added": False,
                    "live_review_required": True,
                    "raw_values_output": False,
                    "paths_printed": False,
                    "header_names_printed": False,
                    "header_values_printed": False,
                    "users_printed": False,
                    "urls_printed": False,
                    "query_ids_printed": False,
                    "auth_material_printed": False,
                    "raw_source_printed": False,
                },
            },
            "post_enable": {
                "status": "ok",
                "issue_counts": {},
                "metadata": {
                    "canary_validated": True,
                    "canary_close_ready": True,
                    "final_source_state": final_source_state,
                    "source_enabled_by_script": False,
                    "native_auth_added": False,
                    "raw_values_output": False,
                    "paths_printed": False,
                    "header_names_printed": False,
                    "header_values_printed": False,
                    "users_printed": False,
                    "urls_printed": False,
                    "query_ids_printed": False,
                    "auth_material_printed": False,
                    "raw_source_printed": False,
                },
            },
            "launch_closure_manifest_builder": {
                "status": "ok",
                "issue_counts": {},
                "metadata": {
                    "manifest_reference_mode": "generated",
                    "redaction_reviewed": True,
                    "raw_values_output": False,
                },
            },
            "launch_closure": {
                "status": "ok",
                "issue_counts": {},
                "metadata": {
                    "launch_closure_ready": True,
                    "verdict": "closed",
                    "final_source_state": final_source_state,
                    "source_enabled_by_script": False,
                    "native_auth_added": False,
                    "live_review_required": True,
                    "raw_values_output": False,
                    "paths_printed": False,
                    "header_names_printed": False,
                    "header_values_printed": False,
                    "users_printed": False,
                    "urls_printed": False,
                    "query_ids_printed": False,
                    "auth_material_printed": False,
                    "raw_source_printed": False,
                },
            },
        },
        "issues": {"failed_gates": [], "counts": {}},
    }


def assert_private_fragments_hidden(text: str, tmp_path: Path) -> None:
    for forbidden in (
        str(tmp_path),
        "viewer_header_should_not_print",
        "owner_value_should_not_print",
        "query_id_should_not_print",
        "auth_material_should_not_print",
        "source_sql_should_not_print",
    ):
        assert forbidden not in text


def test_sso_proxy_support_readiness_accepts_ready_bundle_summary(
    tmp_path: Path,
    capsys,
) -> None:
    input_summary = write_json(tmp_path, "input-summary.json", ready_bundle_summary())
    output_summary = tmp_path / "output-summary.json"

    rc = readiness.main(
        [
            "--deployment-bundle-summary-json",
            str(input_summary),
            "--summary-json",
            str(output_summary),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(output_summary.read_text(encoding="utf-8"))
    rendered = captured.out + captured.err + json.dumps(payload, sort_keys=True)
    assert rc == 0
    assert "Owner raw SSO proxy support readiness: ok" in captured.out
    assert "support_ready=yes" in captured.out
    assert (
        "support_claim=deployment_behind_trusted_sso_auth_proxy_via_viewer_identity_header"
        in captured.out
    )
    assert "deployment_contract=trusted_auth_proxy_viewer_identity_header" in captured.out
    assert "required_gates=7/7" in captured.out
    assert "native_sso_added=no" in captured.out
    assert "native_auth_added=no" in captured.out
    assert "source_enabled_by_script=no" in captured.out
    assert "Issues: none" in captured.out
    assert payload["summary_kind"] == "owner_raw_sso_proxy_support_readiness_v1"
    assert payload["status"] == "ok"
    assert payload["support"]["support_ready"] is True
    assert payload["support"]["native_sso_added"] is False
    assert_private_fragments_hidden(rendered, tmp_path)


def test_sso_proxy_support_readiness_rejects_dev_only_rehearsal_summary(
    tmp_path: Path,
    capsys,
) -> None:
    dev_only_summary = {
        "summary_kind": "owner_raw_d3_rehearsal_v1",
        "status": "ok",
        "readiness": {
            "rehearsal_complete": True,
            "source_enable_ready": True,
            "native_auth_added": False,
            "live_review_required": True,
        },
        "gates": {"dev_sso_keycloak_smoke": {"status": "ok", "issue_counts": {}, "metadata": {}}},
        "issues": {"failed_gates": [], "counts": {}},
    }
    input_summary = write_json(tmp_path, "dev-only-summary.json", dev_only_summary)

    rc = readiness.main(["--deployment-bundle-summary-json", str(input_summary), "--limit", "100"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "support_ready=no" in captured.out
    assert "deployment_bundle_summary.invalid_summary_kind" in captured.out
    assert "gate.front_door_review_audit_missing" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_sso_proxy_support_readiness_blocks_native_auth_and_raw_output_drift(
    tmp_path: Path,
    capsys,
) -> None:
    payload = ready_bundle_summary()
    assert isinstance(payload["deployment"], dict)
    payload["deployment"]["native_auth_added"] = True
    payload["deployment"]["paths_printed"] = True
    gates = payload["gates"]
    assert isinstance(gates, dict)
    source_enable = gates["source_enable"]
    assert isinstance(source_enable, dict)
    metadata = source_enable["metadata"]
    assert isinstance(metadata, dict)
    metadata["source_enabled_by_script"] = True
    input_summary = write_json(tmp_path, "drift-summary.json", payload)

    rc = readiness.main(["--deployment-bundle-summary-json", str(input_summary), "--limit", "100"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "deployment.native_auth_added_invalid" in captured.out
    assert "deployment.paths_printed" in captured.out
    assert "metadata.source_enable.source_enabled_by_script_invalid" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_sso_proxy_support_readiness_requires_redaction_reviewed_manifest_builder(
    tmp_path: Path,
    capsys,
) -> None:
    payload = ready_bundle_summary()
    gates = payload["gates"]
    assert isinstance(gates, dict)
    manifest_builder = gates["launch_closure_manifest_builder"]
    assert isinstance(manifest_builder, dict)
    metadata = manifest_builder["metadata"]
    assert isinstance(metadata, dict)
    metadata["redaction_reviewed"] = False
    input_summary = write_json(tmp_path, "manifest-summary.json", payload)

    rc = readiness.main(["--deployment-bundle-summary-json", str(input_summary), "--limit", "100"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "metadata.launch_closure_manifest_builder.redaction_reviewed_invalid" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_sso_proxy_support_readiness_can_require_source_left_enabled(
    tmp_path: Path,
    capsys,
) -> None:
    rollback_payload = ready_bundle_summary(final_source_state="rollback_completed")
    input_summary = write_json(tmp_path, "rollback-summary.json", rollback_payload)

    default_rc = readiness.main(["--deployment-bundle-summary-json", str(input_summary)])
    default_output = capsys.readouterr()
    strict_rc = readiness.main(
        [
            "--deployment-bundle-summary-json",
            str(input_summary),
            "--require-source-left-enabled",
            "--limit",
            "100",
        ]
    )
    strict_output = capsys.readouterr()

    assert default_rc == 0
    assert "support_ready=yes" in default_output.out
    assert strict_rc == 1
    assert "support_ready=no" in strict_output.out
    assert "deployment.final_source_state_not_left_enabled" in strict_output.out
    assert "metadata.post_enable.final_source_state_not_left_enabled" in strict_output.out
    assert "metadata.launch_closure.final_source_state_not_left_enabled" in strict_output.out
    assert_private_fragments_hidden(
        default_output.out + default_output.err + strict_output.out + strict_output.err,
        tmp_path,
    )


def test_sso_proxy_support_readiness_rejects_summary_overlap_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    input_summary = write_json(tmp_path, "input-summary.json", ready_bundle_summary())

    rc = readiness.main(
        [
            "--deployment-bundle-summary-json",
            str(input_summary),
            "--summary-json",
            str(input_summary),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "summary output must not overwrite input artifacts" in captured.err
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_sso_proxy_support_readiness_detects_unsafe_extra_string(
    tmp_path: Path,
    capsys,
) -> None:
    payload = deepcopy(ready_bundle_summary())
    payload["unexpected_rawish_field"] = "viewer_header_should_not_print"
    input_summary = write_json(tmp_path, "unsafe-summary.json", payload)

    rc = readiness.main(["--deployment-bundle-summary-json", str(input_summary), "--limit", "100"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "deployment_bundle_summary.unexpected_field" in captured.out
    assert "deployment_bundle_summary.unsafe_string_value" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_sso_proxy_support_readiness_docs_mention_script() -> None:
    deployment = (readiness.ROOT / "docs" / "owner-raw-d3-deployment.md").read_text(
        encoding="utf-8"
    )
    changelog = (readiness.ROOT / "docs" / "changelog.md").read_text(encoding="utf-8")
    release_notes = (readiness.ROOT / "docs" / "release-notes-0.9.0.md").read_text(encoding="utf-8")
    release_checklist = (readiness.ROOT / "docs" / "release-checklist.md").read_text(
        encoding="utf-8"
    )
    support_boundary = (readiness.ROOT / "docs" / "support-boundary.md").read_text(
        encoding="utf-8"
    )

    assert "scripts/audit_owner_raw_sso_proxy_support_readiness.py" in deployment
    assert "owner_raw_sso_proxy_support_readiness_v1" in changelog
    assert "Release date: TBD" in release_notes
    assert "trusted SSO/auth proxy through `viewer_identity_header`" in release_notes
    assert "raw-free D3" in release_notes
    assert "support-readiness gate" in release_notes
    assert "scripts/audit_owner_raw_sso_proxy_support_readiness.py" in release_checklist
    assert "native OIDC" in release_checklist
    assert "must not gate raw reveal on collection" in release_checklist
    assert (
        "deployment behind a trusted SSO/auth proxy via `viewer_identity_header`"
        in support_boundary
    )
