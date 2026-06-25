from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from scripts import audit_owner_raw_d3_deployment_bundle as bundle


def write_json(tmp_path: Path, name: str, payload: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def staging_config(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "host": "0.0.0.0",
        "source_visibility": "owner_raw",
        "viewer_identity_header": "X-Secret-Viewer",
        "owner_raw_source_enabled": False,
        "privacy_mode": True,
        "redact": True,
        "redact_identifiers": True,
        "redact_hosts": True,
        "metadata_redact": True,
        "cm_url": "https://private.example.invalid",
        "source_owner_user": "secret_analyst",
    }
    payload.update(overrides)
    return payload


def source_enabled_config(**overrides: object) -> dict[str, object]:
    payload = staging_config(owner_raw_source_enabled=True)
    payload.update(overrides)
    return payload


def owner_raw_review_payload() -> dict[str, object]:
    return {
        "summary_kind": "owner_raw_live_front_door_review_v1",
        "review_profile": "owner_raw_d3",
        "review_status": "reviewed",
        "front_door": {
            "tls_terminated_at_front_door": True,
            "authentication_enforced_before_query_doctor": True,
            "direct_upstream_client_access_blocked": True,
            "inbound_viewer_header_stripped": True,
            "exactly_one_normalized_viewer_header": True,
            "normalized_viewer_value_shape": "simple_owner",
            "raw_identity_tokens_forwarded": False,
        },
        "negative_checks": {
            "unauthenticated_request_denied": True,
            "spoofed_viewer_header_not_authorizing": True,
            "missing_viewer_header_denied": True,
            "invalid_viewer_header_denied": True,
            "duplicate_viewer_header_denied_or_unforwardable": True,
        },
        "owner_raw_checks": {
            "matching_viewer_own_case_allowed": True,
            "different_viewer_same_case_denied": True,
            "owner_raw_source_kill_switch_blocks_source": True,
            "audit_lines_raw_free": True,
        },
        "evidence_retention": {
            "raw_logs_retained": False,
            "raw_headers_retained": False,
            "raw_query_ids_retained": False,
            "raw_users_retained": False,
            "raw_paths_retained": False,
            "raw_urls_retained": False,
            "screenshots_with_source_retained": False,
        },
    }


def post_enable_review_payload(final_source_state: str = "leave_enabled") -> dict[str, object]:
    source_remaining_enabled = final_source_state == "leave_enabled"
    return {
        "summary_kind": "owner_raw_d3_post_enable_review_v1",
        "review_status": "reviewed",
        "canary_scope": "controlled_canary",
        "final_source_state": final_source_state,
        "source_state": {
            "owner_raw_source_enabled_during_canary": True,
            "owner_raw_source_remaining_enabled": source_remaining_enabled,
            "source_enabled_by_query_doctor_script": False,
        },
        "front_door": {
            "no_front_door_or_header_change": True,
            "direct_upstream_client_access_blocked": True,
            "inbound_viewer_header_stripped": True,
        },
        "runtime_checks": {
            "matching_viewer_own_case_allowed": True,
            "different_viewer_same_case_denied": True,
            "unauthenticated_request_denied": True,
            "spoofed_viewer_header_not_authorizing": True,
            "missing_viewer_header_denied": True,
            "invalid_viewer_header_denied": True,
            "duplicate_viewer_header_denied_or_unforwardable": True,
            "denied_pages_raw_free": True,
            "audit_lines_raw_free": True,
            "trusted_surfaces_raw_free": True,
        },
        "rollback": {
            "kill_switch_rollback_verified": True,
            "rollback_path_ready": True,
            "monitoring_active": True,
        },
        "evidence_retention": {
            "raw_logs_retained": False,
            "raw_headers_retained": False,
            "raw_query_ids_retained": False,
            "raw_users_retained": False,
            "raw_paths_retained": False,
            "raw_urls_retained": False,
            "screenshots_with_source_retained": False,
        },
    }


def passing_dev_sso_checks(
    _config: bundle.rehearsal.dev_sso.SmokeConfig,
) -> tuple[bundle.rehearsal.dev_sso.SmokeCheck, ...]:
    smoke_check = bundle.rehearsal.dev_sso.SmokeCheck
    return (
        smoke_check("proxy_requires_login", True, {"status_class": "3xx"}),
        smoke_check("keycloak_discovery_ok", True, {"status_class": "2xx"}),
        smoke_check("query_doctor_upstream_private", True, {"connection": "blocked"}),
        smoke_check("synthetic_oidc_login_lands_on_query_doctor", True, {"status_class": "2xx"}),
    )


def base_args(
    config: Path,
    source_config: Path,
    front_door_review: Path,
    post_enable_review: Path,
    summary: Path | None = None,
) -> list[str]:
    args = [
        "--config",
        str(config),
        "--source-enable-config",
        str(source_config),
        "--front-door-review-json",
        str(front_door_review),
        "--post-enable-review-json",
        str(post_enable_review),
        "--allow-nonlocal-web-bind",
        "--confirm-source-enable-canary",
        "--confirm-no-disable-owner-raw-source",
        "--confirm-no-front-door-or-header-change",
        "--confirm-kill-switch-rollback-plan",
        "--dev-sso-proxy-url",
        "https://private-idp.example.invalid/app",
        "--dev-sso-keycloak-discovery-url",
        "https://private-idp.example.invalid/realms/private",
        "--dev-sso-upstream-host",
        "private-upstream.example.invalid",
        "--dev-sso-username",
        "real_user_should_not_print",
        "--dev-sso-password",
        "real_secret_should_not_print",
    ]
    if summary is not None:
        args.extend(["--summary-json", str(summary)])
    return args


def assert_private_fragments_hidden(text: str, tmp_path: Path) -> None:
    for forbidden in (
        str(tmp_path),
        "secret",
        "X-Secret-Viewer",
        "secret_analyst",
        "https://private.example.invalid",
        "private-idp",
        "private-upstream",
        "real_user_should_not_print",
        "real_secret_should_not_print",
        "query-doctor-sso.localhost",
        "analyst_one",
        "analyst-one-dev-login",
        "example.invalid",
        "/private/",
        "code=",
        "oauth_state_should_not_print",
        "Authorization",
        "Cookie",
    ):
        assert forbidden not in text


def retained_front_door_summary() -> dict[str, object]:
    result = bundle.live_review.audit_review(owner_raw_review_payload())
    return bundle.live_review.summary_payload(result)


def retained_readiness_summary() -> dict[str, object]:
    staging = bundle.readiness.GateOutcome(
        "staging_config_preflight",
        "ok",
        Counter(),
        {
            "owner_raw_source": "disabled",
        },
    )
    review = bundle.readiness.GateOutcome(
        "live_front_door_review",
        "ok",
        Counter(),
        {
            "review_profile": "owner_raw_d3",
            "checked_required_fields": 26,
        },
    )
    return bundle.readiness.summary_payload(staging=staging, review=review)


def retained_rehearsal_summary() -> dict[str, object]:
    return bundle.rehearsal.summary_payload(
        (
            bundle.rehearsal.RehearsalGateOutcome("dev_sso_keycloak_smoke", "ok"),
            bundle.rehearsal.RehearsalGateOutcome("live_front_door_review", "ok"),
            bundle.rehearsal.RehearsalGateOutcome("staging_config_preflight", "ok"),
            bundle.rehearsal.RehearsalGateOutcome(
                "d3_readiness",
                "ok",
                Counter(),
                {
                    "source_enable_ready": True,
                    "current_config_owner_raw_source": "disabled",
                    "native_auth_added": False,
                    "live_review_required": True,
                },
            ),
        )
    )


def retained_source_enable_summary() -> dict[str, object]:
    return bundle.source_enable.summary_payload(
        (
            bundle.source_enable.GateOutcome("rehearsal_summary", "ok"),
            bundle.source_enable.GateOutcome("source_enable_config", "ok"),
            bundle.source_enable.GateOutcome(
                "rehearsal_config_alignment",
                "ok",
                Counter(),
                {
                    "previous_owner_raw_source": "disabled",
                    "planned_owner_raw_source": "enabled",
                },
            ),
            bundle.source_enable.GateOutcome("operator_confirmation", "ok"),
        )
    )


def retained_post_enable_summary(final_source_state: str = "leave_enabled") -> dict[str, object]:
    return bundle.post_enable.summary_payload(
        (
            bundle.post_enable.GateOutcome("source_enable_summary", "ok"),
            bundle.post_enable.GateOutcome("post_enable_review", "ok"),
            bundle.post_enable.GateOutcome(
                "final_state",
                "ok",
                Counter(),
                {
                    "final_source_state": final_source_state,
                    "canary_close_ready": True,
                },
            ),
        )
    )


def write_retained_manifest(tmp_path: Path) -> Path:
    paths = {
        "front_door": write_json(
            tmp_path,
            "retained-front-door-summary.json",
            retained_front_door_summary(),
        ),
        "readiness": write_json(
            tmp_path, "retained-readiness-summary.json", retained_readiness_summary()
        ),
        "rehearsal": write_json(
            tmp_path, "retained-rehearsal-summary.json", retained_rehearsal_summary()
        ),
        "source_enable": write_json(
            tmp_path,
            "retained-source-enable-summary.json",
            retained_source_enable_summary(),
        ),
        "post_enable": write_json(
            tmp_path,
            "retained-post-enable-summary.json",
            retained_post_enable_summary(),
        ),
    }
    entry = {
        "front_door_review_summary_json": paths["front_door"].name,
        "readiness_summary_json": paths["readiness"].name,
        "rehearsal_summary_json": paths["rehearsal"].name,
        "source_enable_summary_json": paths["source_enable"].name,
        "post_enable_summary_json": paths["post_enable"].name,
    }
    return write_json(
        tmp_path,
        "retained-launch-closure-manifest.json",
        {
            "manifest_kind": bundle.launch_closure.MANIFEST_KIND,
            "metadata": {
                "builder_kind": bundle.launch_closure.MANIFEST_BUILDER_KIND,
                "entry_count": 1,
                "path_reference": "relative_to_manifest",
                "redaction_reviewed": True,
                "limitations": list(bundle.launch_closure.MANIFEST_LIMITATIONS),
            },
            "entries": [entry],
        },
    )


def test_owner_raw_d3_deployment_bundle_accepts_full_chain_raw_free(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(bundle.rehearsal.dev_sso, "run_checks", passing_dev_sso_checks)
    config = write_json(tmp_path, "secret-disabled-config.json", staging_config())
    source_config = write_json(
        tmp_path,
        "secret-source-enabled-config.json",
        source_enabled_config(),
    )
    front_door = write_json(tmp_path, "secret-front-door-review.json", owner_raw_review_payload())
    post_review = write_json(
        tmp_path, "secret-post-enable-review.json", post_enable_review_payload()
    )
    summary = tmp_path / "secret-deployment-bundle-summary.json"

    rc = bundle.main(base_args(config, source_config, front_door, post_review, summary))

    captured = capsys.readouterr()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    rendered = captured.out + captured.err + json.dumps(payload, sort_keys=True)
    assert rc == 0
    assert "Owner raw D3 deployment bundle: ok" in captured.out
    assert "bundle_ready=yes" in captured.out
    assert "verdict=ready" in captured.out
    assert "front_door_review_audit=ok" in captured.out
    assert "readiness=ok" in captured.out
    assert "rehearsal=ok" in captured.out
    assert "source_enable=ok" in captured.out
    assert "post_enable=ok" in captured.out
    assert "launch_closure_manifest_builder=ok" in captured.out
    assert "launch_closure=ok" in captured.out
    assert "final_source_state=leave_enabled" in captured.out
    assert "source_enabled_by_script=no" in captured.out
    assert "native_auth_added=no" in captured.out
    assert "Failed gates: none" in captured.out
    assert "Issues: none" in captured.out
    assert payload["summary_kind"] == "owner_raw_d3_deployment_bundle_v1"
    assert payload["status"] == "ok"
    assert payload["deployment"]["bundle_ready"] is True
    assert payload["deployment"]["raw_source_printed"] is False
    assert payload["gates"]["launch_closure"]["status"] == "ok"
    assert payload["issues"] == {"counts": {}, "failed_gates": []}
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_d3_deployment_bundle_audits_optional_retained_manifest(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(bundle.rehearsal.dev_sso, "run_checks", passing_dev_sso_checks)
    config = write_json(tmp_path, "secret-disabled-config.json", staging_config())
    source_config = write_json(
        tmp_path, "secret-source-enabled-config.json", source_enabled_config()
    )
    front_door = write_json(tmp_path, "secret-front-door-review.json", owner_raw_review_payload())
    post_review = write_json(
        tmp_path, "secret-post-enable-review.json", post_enable_review_payload()
    )
    retained_manifest = write_retained_manifest(tmp_path)
    summary = tmp_path / "secret-deployment-bundle-summary.json"
    args = base_args(config, source_config, front_door, post_review, summary)
    args.extend(["--launch-closure-manifest", str(retained_manifest)])

    rc = bundle.main(args)

    captured = capsys.readouterr()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    rendered = captured.out + captured.err + json.dumps(payload, sort_keys=True)
    assert rc == 0
    assert "retained_launch_closure_manifest=ok" in captured.out
    assert payload["gates"]["retained_launch_closure_manifest"]["status"] == "ok"
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_d3_deployment_bundle_fails_closed_on_bad_rehearsal_config(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(bundle.rehearsal.dev_sso, "run_checks", passing_dev_sso_checks)
    config = write_json(
        tmp_path,
        "secret-missing-header-config.json",
        staging_config(viewer_identity_header=None),
    )
    source_config = write_json(
        tmp_path, "secret-source-enabled-config.json", source_enabled_config()
    )
    front_door = write_json(tmp_path, "secret-front-door-review.json", owner_raw_review_payload())
    post_review = write_json(
        tmp_path, "secret-post-enable-review.json", post_enable_review_payload()
    )
    args = base_args(config, source_config, front_door, post_review)
    args.extend(["--limit", "100"])

    rc = bundle.main(args)

    captured = capsys.readouterr()
    assert rc == 1
    assert "Owner raw D3 deployment bundle: failed" in captured.out
    assert "bundle_ready=no" in captured.out
    assert "readiness=failed" in captured.out
    assert "rehearsal=failed" in captured.out
    assert "source_enable=failed" in captured.out
    assert "launch_closure=failed" in captured.out
    assert "staging.viewer_identity_header_missing" in captured.out
    assert "rehearsal.status_not_ok" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_deployment_bundle_rejects_summary_overlap_without_path_echo(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(bundle.rehearsal.dev_sso, "run_checks", passing_dev_sso_checks)
    config = write_json(tmp_path, "secret-disabled-config.json", staging_config())
    source_config = write_json(
        tmp_path, "secret-source-enabled-config.json", source_enabled_config()
    )
    front_door = write_json(tmp_path, "secret-front-door-review.json", owner_raw_review_payload())
    post_review = write_json(
        tmp_path, "secret-post-enable-review.json", post_enable_review_payload()
    )

    rc = bundle.main(base_args(config, source_config, front_door, post_review, config))

    captured = capsys.readouterr()
    assert rc == 2
    assert "summary output must not overwrite input artifacts" in captured.err
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_deployment_bundle_docs_mention_script() -> None:
    deployment = (bundle.ROOT / "docs" / "owner-raw-d3-deployment.md").read_text(encoding="utf-8")
    matrix = (bundle.ROOT / "docs" / "test-matrix.md").read_text(encoding="utf-8")
    changelog = (bundle.ROOT / "docs" / "changelog.md").read_text(encoding="utf-8")

    assert "scripts/audit_owner_raw_d3_deployment_bundle.py" in deployment
    assert "scripts/audit_owner_raw_d3_deployment_bundle.py" in matrix
    assert "owner_raw_d3_deployment_bundle_v1" in changelog
