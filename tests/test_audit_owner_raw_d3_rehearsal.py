from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from scripts import audit_owner_raw_d3_rehearsal as rehearsal
from scripts import audit_owner_raw_live_front_door_review as live_review
from scripts import dev_sso_keycloak_smoke as dev_sso


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


def passing_dev_sso_checks(_config: dev_sso.SmokeConfig) -> tuple[dev_sso.SmokeCheck, ...]:
    return (
        dev_sso.SmokeCheck(
            "proxy_requires_login",
            True,
            {"status_class": "3xx", "redirect_target": "keycloak_oidc_auth"},
        ),
        dev_sso.SmokeCheck("keycloak_discovery_ok", True, {"status_class": "2xx"}),
        dev_sso.SmokeCheck(
            "query_doctor_upstream_private",
            True,
            {"connection": "blocked", "blocked_category": "connection_refused"},
        ),
        dev_sso.SmokeCheck(
            "synthetic_oidc_login_lands_on_query_doctor",
            True,
            {
                "status_class": "2xx",
                "final_target": "query_doctor_proxy_root",
                "login_form_seen": True,
                "still_on_keycloak_login": False,
                "query_doctor_visible": True,
            },
        ),
    )


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
        "state=",
        "Authorization",
        "Cookie",
    ):
        assert forbidden not in text


def test_owner_raw_d3_rehearsal_accepts_all_gates_raw_free(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(rehearsal.dev_sso, "run_checks", passing_dev_sso_checks)
    config = write_json(tmp_path, "secret-config.json", staging_config())
    review = write_json(tmp_path, "secret-review.json", owner_raw_review_payload())

    rc = rehearsal.main(
        [
            "--config",
            str(config),
            "--allow-nonlocal-web-bind",
            "--front-door-review-json",
            str(review),
        ]
    )

    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    assert rc == 0
    assert "Owner raw D3 rehearsal: ok" in captured.out
    assert "rehearsal_complete=yes" in captured.out
    assert "source_enable_ready=yes" in captured.out
    assert "dev_sso_keycloak_smoke=ok" in captured.out
    assert "live_front_door_review=ok" in captured.out
    assert "staging_config_preflight=ok" in captured.out
    assert "d3_readiness=ok" in captured.out
    assert "native_auth_added=no" in captured.out
    assert "Failed gates: none" in captured.out
    assert "Issues: none" in captured.out
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_d3_rehearsal_writes_raw_free_summary(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(rehearsal.dev_sso, "run_checks", passing_dev_sso_checks)
    config = write_json(tmp_path, "secret-config.json", staging_config())
    review = write_json(tmp_path, "secret-review.json", owner_raw_review_payload())
    summary = tmp_path / "secret-summary.json"

    rc = rehearsal.main(
        [
            "--config",
            str(config),
            "--allow-nonlocal-web-bind",
            "--front-door-review-json",
            str(review),
            "--summary-json",
            str(summary),
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
    )

    captured = capsys.readouterr()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    rendered = captured.out + captured.err + json.dumps(payload, sort_keys=True)
    assert rc == 0
    assert payload["summary_kind"] == "owner_raw_d3_rehearsal_v1"
    assert payload["status"] == "ok"
    assert payload["readiness"]["source_enable_ready"] is True
    assert payload["readiness"]["native_auth_added"] is False
    assert payload["readiness"]["paths_printed"] is False
    assert payload["readiness"]["header_names_printed"] is False
    assert payload["readiness"]["raw_source_printed"] is False
    assert payload["gates"]["dev_sso_keycloak_smoke"]["status"] == "ok"
    assert payload["gates"]["live_front_door_review"]["status"] == "ok"
    assert payload["gates"]["staging_config_preflight"]["status"] == "ok"
    assert payload["gates"]["d3_readiness"]["status"] == "ok"
    assert payload["issues"] == {"counts": {}, "failed_gates": []}
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_d3_rehearsal_fails_closed_without_viewer_identity_header(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(rehearsal.dev_sso, "run_checks", passing_dev_sso_checks)
    config = write_json(
        tmp_path,
        "secret-missing-header-config.json",
        staging_config(viewer_identity_header=None),
    )
    review = write_json(tmp_path, "secret-review.json", owner_raw_review_payload())

    rc = rehearsal.main(
        [
            "--config",
            str(config),
            "--allow-nonlocal-web-bind",
            "--front-door-review-json",
            str(review),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Owner raw D3 rehearsal: failed" in captured.out
    assert "source_enable_ready=no" in captured.out
    assert "staging_config_preflight=failed" in captured.out
    assert "d3_readiness=failed" in captured.out
    assert "staging.viewer_identity_header_missing" in captured.out
    assert "d3_readiness_not_ready" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_rehearsal_fails_closed_without_live_review(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(rehearsal.dev_sso, "run_checks", passing_dev_sso_checks)
    config = write_json(tmp_path, "secret-config.json", staging_config())

    rc = rehearsal.main(["--config", str(config), "--allow-nonlocal-web-bind"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "live_front_door_review=missing" in captured.out
    assert "d3_readiness=failed" in captured.out
    assert "front_door_review_summary_missing" in captured.out
    assert "source_enable_ready=no" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_rehearsal_rejects_unreviewed_front_door_template(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(rehearsal.dev_sso, "run_checks", passing_dev_sso_checks)
    config = write_json(tmp_path, "secret-config.json", staging_config())
    review = write_json(
        tmp_path,
        "secret-template.json",
        live_review.review_template(live_review.PROFILE_OWNER_RAW_D3),
    )

    rc = rehearsal.main(
        [
            "--config",
            str(config),
            "--allow-nonlocal-web-bind",
            "--front-door-review-json",
            str(review),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "live_front_door_review=failed" in captured.out
    assert "front_door.review_not_marked_reviewed" in captured.out
    assert "front_door.front_door_tls_not_reviewed" in captured.out
    assert "source_enable_ready=no" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_rehearsal_rejects_enabled_raw_source_without_kill_switch(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(rehearsal.dev_sso, "run_checks", passing_dev_sso_checks)
    config = write_json(
        tmp_path,
        "secret-enabled-source-config.json",
        staging_config(owner_raw_source_enabled=True),
    )
    review = write_json(tmp_path, "secret-review.json", owner_raw_review_payload())

    rc = rehearsal.main(
        [
            "--config",
            str(config),
            "--allow-nonlocal-web-bind",
            "--front-door-review-json",
            str(review),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "staging_config_preflight=failed" in captured.out
    assert "current_config_owner_raw_source=enabled" in captured.out
    assert "staging.owner_raw_source_kill_switch_not_disabled" in captured.out
    assert "source_enable_ready=no" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_rehearsal_accepts_cli_kill_switch(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(rehearsal.dev_sso, "run_checks", passing_dev_sso_checks)
    config = write_json(
        tmp_path,
        "secret-cli-kill-switch-config.json",
        staging_config(owner_raw_source_enabled=True),
    )
    review = write_json(tmp_path, "secret-review.json", owner_raw_review_payload())

    rc = rehearsal.main(
        [
            "--config",
            str(config),
            "--allow-nonlocal-web-bind",
            "--disable-owner-raw-source",
            "--front-door-review-json",
            str(review),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "source_enable_ready=yes" in captured.out
    assert "current_config_owner_raw_source=disabled" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_rehearsal_fails_closed_when_spoofed_header_strip_unproven(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(rehearsal.dev_sso, "run_checks", passing_dev_sso_checks)
    config = write_json(tmp_path, "secret-config.json", staging_config())
    review_payload = deepcopy(owner_raw_review_payload())
    front_door = review_payload["front_door"]
    negative_checks = review_payload["negative_checks"]
    assert isinstance(front_door, dict)
    assert isinstance(negative_checks, dict)
    front_door["inbound_viewer_header_stripped"] = False
    negative_checks["spoofed_viewer_header_not_authorizing"] = False
    review = write_json(tmp_path, "secret-review.json", review_payload)

    rc = rehearsal.main(
        [
            "--config",
            str(config),
            "--allow-nonlocal-web-bind",
            "--front-door-review-json",
            str(review),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "live_front_door_review=failed" in captured.out
    assert "front_door.inbound_viewer_header_not_stripped" in captured.out
    assert "front_door.spoofed_viewer_header_authorized" in captured.out
    assert "source_enable_ready=no" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_rehearsal_fails_when_dev_sso_smoke_fails(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    def failing_dev_sso_checks(_config: dev_sso.SmokeConfig) -> tuple[dev_sso.SmokeCheck, ...]:
        return (
            dev_sso.SmokeCheck(
                "proxy_requires_login",
                False,
                {"error_category": "connection_refused"},
            ),
        )

    monkeypatch.setattr(rehearsal.dev_sso, "run_checks", failing_dev_sso_checks)
    config = write_json(tmp_path, "secret-config.json", staging_config())
    review = write_json(tmp_path, "secret-review.json", owner_raw_review_payload())

    rc = rehearsal.main(
        [
            "--config",
            str(config),
            "--allow-nonlocal-web-bind",
            "--front-door-review-json",
            str(review),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "dev_sso_keycloak_smoke=failed" in captured.out
    assert "dev_sso.proxy_requires_login_failed" in captured.out
    assert "source_enable_ready=no" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_rehearsal_rejects_summary_overlap_without_path_echo(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(rehearsal.dev_sso, "run_checks", passing_dev_sso_checks)
    config = write_json(tmp_path, "secret-config.json", staging_config())
    review = write_json(tmp_path, "secret-review.json", owner_raw_review_payload())

    rc = rehearsal.main(
        [
            "--config",
            str(config),
            "--allow-nonlocal-web-bind",
            "--front-door-review-json",
            str(review),
            "--summary-json",
            str(config),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "summary output must not overwrite input artifacts" in captured.err
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_rehearsal_docs_mention_script() -> None:
    deployment = (rehearsal.ROOT / "docs" / "owner-raw-d3-deployment.md").read_text(
        encoding="utf-8"
    )
    matrix = (rehearsal.ROOT / "docs" / "test-matrix.md").read_text(encoding="utf-8")
    changelog = (rehearsal.ROOT / "docs" / "changelog.md").read_text(encoding="utf-8")

    assert "scripts/audit_owner_raw_d3_rehearsal.py" in deployment
    assert "scripts/audit_owner_raw_d3_rehearsal.py" in matrix
    assert "owner_raw_d3_rehearsal_v1" in changelog
