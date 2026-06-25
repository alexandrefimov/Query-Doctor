from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

from scripts import prepare_owner_raw_d3_artifacts as workspace


def passing_dev_sso_checks(
    _config: workspace.bundle.rehearsal.dev_sso.SmokeConfig,
) -> tuple[workspace.bundle.rehearsal.dev_sso.SmokeCheck, ...]:
    smoke_check = workspace.bundle.rehearsal.dev_sso.SmokeCheck
    return (
        smoke_check("proxy_requires_login", True, {"status_class": "3xx"}),
        smoke_check("keycloak_discovery_ok", True, {"status_class": "2xx"}),
        smoke_check("query_doctor_upstream_private", True, {"connection": "blocked"}),
        smoke_check("synthetic_oidc_login_lands_on_query_doctor", True, {"status_class": "2xx"}),
    )


def raw_output_false_flags() -> dict[str, object]:
    return {field_name: False for field_name in workspace.bundle.RAW_OUTPUT_FIELDS}


def ready_bundle_summary(final_source_state: str = "leave_enabled") -> dict[str, Any]:
    return workspace.bundle.summary_payload(
        (
            workspace.bundle.BundleGateOutcome(
                "front_door_review_audit",
                "ok",
                Counter(),
                {
                    "review_profile": workspace.live_review.PROFILE_OWNER_RAW_D3,
                    "checked_required_fields": len(
                        workspace.live_review.required_field_labels(
                            workspace.live_review.PROFILE_OWNER_RAW_D3
                        )
                    ),
                    "raw_values_output": False,
                },
            ),
            workspace.bundle.BundleGateOutcome(
                "readiness",
                "ok",
                Counter(),
                {
                    "source_enable_ready": True,
                    "current_config_owner_raw_source": "disabled",
                    "native_auth_added": False,
                    "live_review_required": True,
                    **raw_output_false_flags(),
                },
            ),
            workspace.bundle.BundleGateOutcome(
                "rehearsal",
                "ok",
                Counter(),
                {
                    "rehearsal_complete": True,
                    "source_enable_ready": True,
                    "current_config_owner_raw_source": "disabled",
                    "native_auth_added": False,
                    "live_review_required": True,
                    **raw_output_false_flags(),
                },
            ),
            workspace.bundle.BundleGateOutcome(
                "source_enable",
                "ok",
                Counter(),
                {
                    "canary_ready": True,
                    "previous_owner_raw_source": "disabled",
                    "planned_owner_raw_source": "enabled",
                    "source_enabled_by_script": False,
                    "native_auth_added": False,
                    "live_review_required": True,
                    **raw_output_false_flags(),
                },
            ),
            workspace.bundle.BundleGateOutcome(
                "post_enable",
                "ok",
                Counter(),
                {
                    "canary_validated": True,
                    "canary_close_ready": True,
                    "final_source_state": final_source_state,
                    "source_enabled_by_script": False,
                    "native_auth_added": False,
                    **raw_output_false_flags(),
                },
            ),
            workspace.bundle.BundleGateOutcome(
                "launch_closure_manifest_builder",
                "ok",
                Counter(),
                {
                    "manifest_reference_mode": "generated",
                    "redaction_reviewed": True,
                    "raw_values_output": False,
                },
            ),
            workspace.bundle.BundleGateOutcome(
                "launch_closure",
                "ok",
                Counter(),
                {
                    "launch_closure_ready": True,
                    "verdict": "closed",
                    "final_source_state": final_source_state,
                    "source_enabled_by_script": False,
                    "native_auth_added": False,
                    "live_review_required": True,
                    **raw_output_false_flags(),
                },
            ),
        )
    )


def writing_bundle_main(payload: dict[str, Any]):
    def run(argv: list[str]) -> int:
        summary_path = Path(argv[argv.index("--summary-json") + 1])
        summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return 0

    return run


def base_args(artifact_dir: Path, *extra: str) -> list[str]:
    return [
        "--artifact-dir",
        str(artifact_dir),
        "--confirm-local-ignored-artifact-dir",
        "--allow-nonlocal-web-bind",
        "--confirm-source-enable-canary",
        "--confirm-no-disable-owner-raw-source",
        "--confirm-no-front-door-or-header-change",
        "--confirm-kill-switch-rollback-plan",
        "--dev-sso-proxy-url",
        "private_idp_url_should_not_print?state=private_oauth_state_should_not_print",
        "--dev-sso-keycloak-discovery-url",
        "private_discovery_url_should_not_print?code=private_oauth_code_should_not_print",
        "--dev-sso-upstream-host",
        "private_upstream_host_should_not_print",
        "--dev-sso-username",
        "real_user_should_not_print",
        "--dev-sso-password",
        "real_secret_should_not_print",
        *extra,
    ]


def protected_fragments(tmp_path: Path) -> tuple[str, ...]:
    return (
        str(tmp_path),
        "secret",
        "private_idp_url_should_not_print",
        "private_discovery_url_should_not_print",
        "private_upstream_host_should_not_print",
        "real_user_should_not_print",
        "real_secret_should_not_print",
        "X-Query-Doctor-Viewer",
        "/private/",
        "Authorization",
        "Cookie",
        "private_oauth_code_should_not_print",
        "private_oauth_state_should_not_print",
    )


def assert_private_fragments_hidden(text: str, tmp_path: Path) -> None:
    for fragment in protected_fragments(tmp_path):
        assert fragment not in text


def test_prepare_owner_raw_d3_artifacts_creates_fail_closed_workspace(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(workspace.bundle.rehearsal.dev_sso, "run_checks", passing_dev_sso_checks)
    artifact_dir = tmp_path / "secret-d3-artifacts"

    rc = workspace.main(base_args(artifact_dir, "--limit", "100"))

    captured = capsys.readouterr()
    summary = json.loads((artifact_dir / "deployment-bundle.summary.json").read_text())
    rendered = captured.out + captured.err + json.dumps(summary, sort_keys=True)
    assert rc == 1
    assert "Owner raw D3 artifact workspace: failed" in captured.out
    assert "bundle_ready=no" in captured.out
    assert "verdict=blocked" in captured.out
    assert "disabled_config=written" in captured.out
    assert "source_enabled_config=written" in captured.out
    assert "front_door_review_template=written" in captured.out
    assert "post_enable_review_template=written" in captured.out
    assert "operator_checklist=written" in captured.out
    assert "front_door_review_audit=failed" in captured.out
    assert "post_enable=failed" in captured.out
    assert "support_readiness=skipped" in captured.out
    assert "dev_sso.proxy_requires_login_failed" not in captured.out
    assert summary["summary_kind"] == "owner_raw_d3_deployment_bundle_v1"
    assert summary["status"] == "failed"
    assert (artifact_dir / "d3-disabled-web-config.template.json").is_file()
    assert (artifact_dir / "d3-source-enabled-canary-config.template.json").is_file()
    assert (artifact_dir / "front-door-review.template.json").is_file()
    assert (artifact_dir / "post-enable-review.template.json").is_file()
    assert (artifact_dir / "operator-checklist.md").is_file()
    assert not (artifact_dir / "support-readiness.summary.json").exists()
    assert_private_fragments_hidden(rendered, tmp_path)


def test_prepare_owner_raw_d3_artifacts_preserves_existing_templates_by_default(
    tmp_path: Path,
    capsys,
) -> None:
    artifact_dir = tmp_path / "secret-d3-artifacts"
    artifact_dir.mkdir()
    front_door = artifact_dir / "front-door-review.template.json"
    front_door.write_text('{"review_status": "reviewed"}\n', encoding="utf-8")

    rc = workspace.main(
        [
            "--artifact-dir",
            str(artifact_dir),
            "--confirm-local-ignored-artifact-dir",
            "--skip-bundle",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "front_door_review_template=preserved" in captured.out
    assert "support_readiness=skipped" in captured.out
    assert json.loads(front_door.read_text()) == {"review_status": "reviewed"}
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_prepare_owner_raw_d3_artifacts_replace_templates_is_explicit(
    tmp_path: Path,
    capsys,
) -> None:
    artifact_dir = tmp_path / "secret-d3-artifacts"
    artifact_dir.mkdir()
    front_door = artifact_dir / "front-door-review.template.json"
    front_door.write_text('{"review_status": "reviewed"}\n', encoding="utf-8")

    rc = workspace.main(
        [
            "--artifact-dir",
            str(artifact_dir),
            "--confirm-local-ignored-artifact-dir",
            "--replace-templates",
            "--skip-bundle",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(front_door.read_text())
    assert rc == 0
    assert "front_door_review_template=written" in captured.out
    assert "support_readiness=skipped" in captured.out
    assert payload["review_status"] == "unreviewed"
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_prepare_owner_raw_d3_artifacts_runs_support_readiness_after_passing_bundle(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    artifact_dir = tmp_path / "secret-d3-artifacts"
    monkeypatch.setattr(workspace.bundle, "main", writing_bundle_main(ready_bundle_summary()))

    rc = workspace.main(base_args(artifact_dir, "--limit", "100"))

    captured = capsys.readouterr()
    support_summary = json.loads((artifact_dir / "support-readiness.summary.json").read_text())
    rendered = captured.out + captured.err + json.dumps(support_summary, sort_keys=True)
    assert rc == 0
    assert "Owner raw D3 artifact workspace: ok" in captured.out
    assert "bundle_ready=yes" in captured.out
    assert "support_readiness=ok" in captured.out
    assert "support_ready=yes" in captured.out
    assert "support_final_source_state=leave_enabled" in captured.out
    assert "support_readiness_rc=0" in captured.out
    assert support_summary["summary_kind"] == "owner_raw_sso_proxy_support_readiness_v1"
    assert support_summary["status"] == "ok"
    assert support_summary["support"]["support_ready"] is True
    assert_private_fragments_hidden(rendered, tmp_path)


def test_prepare_owner_raw_d3_artifacts_skip_support_readiness_is_explicit(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    artifact_dir = tmp_path / "secret-d3-artifacts"
    monkeypatch.setattr(workspace.bundle, "main", writing_bundle_main(ready_bundle_summary()))

    rc = workspace.main(base_args(artifact_dir, "--skip-support-readiness"))

    captured = capsys.readouterr()
    assert rc == 0
    assert "Owner raw D3 artifact workspace: ok" in captured.out
    assert "bundle_ready=yes" in captured.out
    assert "support_readiness=skipped" in captured.out
    assert not (artifact_dir / "support-readiness.summary.json").exists()
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_prepare_owner_raw_d3_artifacts_require_source_left_enabled_fails_rollback_summary(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    artifact_dir = tmp_path / "secret-d3-artifacts"
    monkeypatch.setattr(
        workspace.bundle,
        "main",
        writing_bundle_main(ready_bundle_summary(final_source_state="rollback_completed")),
    )

    rc = workspace.main(base_args(artifact_dir, "--require-source-left-enabled", "--limit", "100"))

    captured = capsys.readouterr()
    support_summary = json.loads((artifact_dir / "support-readiness.summary.json").read_text())
    rendered = captured.out + captured.err + json.dumps(support_summary, sort_keys=True)
    assert rc == 1
    assert "Owner raw D3 artifact workspace: ok" in captured.out
    assert "bundle_ready=yes" in captured.out
    assert "support_readiness=failed" in captured.out
    assert "support_ready=no" in captured.out
    assert "support_final_source_state=rollback_completed" in captured.out
    assert "support_readiness_rc=1" in captured.out
    assert "Support readiness issues:" in captured.out
    assert "deployment.final_source_state_not_left_enabled" in captured.out
    assert support_summary["summary_kind"] == "owner_raw_sso_proxy_support_readiness_v1"
    assert support_summary["status"] == "failed"
    assert support_summary["support"]["support_ready"] is False
    assert_private_fragments_hidden(rendered, tmp_path)


def test_prepare_owner_raw_d3_artifacts_ignores_stale_summary_after_bundle_exception(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    artifact_dir = tmp_path / "secret-d3-artifacts"
    artifact_dir.mkdir()
    stale_summary = artifact_dir / "deployment-bundle.summary.json"
    stale_summary.write_text(
        json.dumps(
            {
                "summary_kind": "owner_raw_d3_deployment_bundle_v1",
                "status": "ok",
                "deployment": {"bundle_ready": True, "verdict": "ready"},
                "issues": {"failed_gates": [], "counts": {}},
            }
        ),
        encoding="utf-8",
    )

    def raise_bundle(_argv: list[str]) -> int:
        raise RuntimeError("real_secret_should_not_print")

    monkeypatch.setattr(workspace.bundle, "main", raise_bundle)

    rc = workspace.main(base_args(artifact_dir, "--limit", "100"))

    captured = capsys.readouterr()
    assert rc == 1
    assert "Owner raw D3 artifact workspace: failed" in captured.out
    assert "bundle_ready=no" in captured.out
    assert "deployment_bundle_rc=2" in captured.out
    assert "deployment_bundle.summary_unavailable: 1" in captured.out
    assert not stale_summary.exists()
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_prepare_owner_raw_d3_artifacts_requires_local_ignored_confirmation(
    tmp_path: Path,
    capsys,
) -> None:
    rc = workspace.main(["--artifact-dir", str(tmp_path / "secret-d3-artifacts")])

    captured = capsys.readouterr()
    assert rc == 2
    assert "local ignored artifact confirmation is required" in captured.err
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_prepare_owner_raw_d3_artifacts_docs_mention_script() -> None:
    deployment = (workspace.ROOT / "docs" / "owner-raw-d3-deployment.md").read_text(
        encoding="utf-8"
    )
    matrix = (workspace.ROOT / "docs" / "test-matrix.md").read_text(encoding="utf-8")
    changelog = (workspace.ROOT / "docs" / "changelog.md").read_text(encoding="utf-8")

    assert "scripts/prepare_owner_raw_d3_artifacts.py" in deployment
    assert "support-readiness.summary.json" in deployment
    assert "--skip-support-readiness" in deployment
    assert "scripts/prepare_owner_raw_d3_artifacts.py" in matrix
    assert "support-readiness gate by default" in matrix
    assert "owner_raw_d3_artifact_workspace_v1" in changelog
    assert "support-readiness.summary.json" in changelog
