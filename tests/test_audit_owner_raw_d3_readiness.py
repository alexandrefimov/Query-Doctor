from __future__ import annotations

import json
from pathlib import Path

from scripts import audit_owner_raw_d3_readiness as readiness
from scripts import audit_owner_raw_live_front_door_review as live_review


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


def assert_private_fragments_hidden(text: str, tmp_path: Path) -> None:
    for forbidden in (
        str(tmp_path),
        "secret",
        "X-Secret-Viewer",
        "secret_analyst",
        "https://private.example.invalid",
        "analyst_one",
        "example.invalid",
        "/private/",
        "code=",
        "state=",
    ):
        assert forbidden not in text


def test_owner_raw_d3_readiness_accepts_staging_config_and_live_review(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_json(tmp_path, "secret-config.json", staging_config())
    review = write_json(tmp_path, "secret-review.json", owner_raw_review_payload())

    rc = readiness.main(
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
    assert "Owner raw D3 readiness: ok" in captured.out
    assert "source_enable_ready=yes" in captured.out
    assert "staging_config_preflight=ok" in captured.out
    assert "front_door_review=ok" in captured.out
    assert "current_config_owner_raw_source=disabled" in captured.out
    assert "native_auth_added=no" in captured.out
    assert "Issues: none" in captured.out
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_d3_readiness_fails_closed_without_live_review(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_json(tmp_path, "secret-config.json", staging_config())

    rc = readiness.main(["--config", str(config), "--allow-nonlocal-web-bind"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Owner raw D3 readiness: failed" in captured.out
    assert "source_enable_ready=no" in captured.out
    assert "front_door_review=missing" in captured.out
    assert "front_door_review_summary_missing" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_readiness_rejects_fail_closed_review_template(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_json(tmp_path, "secret-config.json", staging_config())
    review = write_json(
        tmp_path,
        "secret-template.json",
        live_review.review_template(live_review.PROFILE_OWNER_RAW_D3),
    )

    rc = readiness.main(
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
    assert "front_door_review=failed" in captured.out
    assert "front_door.review_not_marked_reviewed" in captured.out
    assert "front_door.front_door_tls_not_reviewed" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_readiness_rejects_bad_staging_config(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_json(
        tmp_path,
        "secret-bad-config.json",
        staging_config(viewer_identity_header=None),
    )
    review = write_json(tmp_path, "secret-review.json", owner_raw_review_payload())

    rc = readiness.main(
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
    assert "staging.viewer_identity_header_missing" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_readiness_accepts_cli_kill_switch(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_json(
        tmp_path,
        "secret-cli-kill-switch-config.json",
        staging_config(owner_raw_source_enabled=True),
    )
    review = write_json(tmp_path, "secret-review.json", owner_raw_review_payload())

    rc = readiness.main(
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


def test_owner_raw_d3_readiness_rejects_trino_shared_review_profile(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_json(tmp_path, "secret-config.json", staging_config())
    review_payload = owner_raw_review_payload()
    review_payload["review_profile"] = "trino_shared_hardening"
    review = write_json(tmp_path, "secret-review.json", review_payload)

    rc = readiness.main(
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
    assert "front_door.invalid_review_profile" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_readiness_writes_raw_free_summary(tmp_path: Path, capsys) -> None:
    config = write_json(tmp_path, "secret-config.json", staging_config())
    review = write_json(tmp_path, "secret-review.json", owner_raw_review_payload())
    summary = tmp_path / "secret-summary.json"

    rc = readiness.main(
        [
            "--config",
            str(config),
            "--allow-nonlocal-web-bind",
            "--front-door-review-json",
            str(review),
            "--summary-json",
            str(summary),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    rendered = captured.out + captured.err + json.dumps(payload, sort_keys=True)
    assert rc == 0
    assert payload["summary_kind"] == "owner_raw_d3_readiness_v1"
    assert payload["status"] == "ok"
    assert payload["readiness"]["source_enable_ready"] is True
    assert payload["readiness"]["native_auth_added"] is False
    assert payload["readiness"]["paths_printed"] is False
    assert payload["readiness"]["header_names_printed"] is False
    assert payload["readiness"]["raw_source_printed"] is False
    assert payload["gates"]["staging_config_preflight"]["status"] == "ok"
    assert payload["gates"]["live_front_door_review"]["status"] == "ok"
    assert payload["issues"] == {"counts": {}}
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_d3_readiness_rejects_summary_overlap_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_json(tmp_path, "secret-config.json", staging_config())
    review = write_json(tmp_path, "secret-review.json", owner_raw_review_payload())

    rc = readiness.main(
        [
            "--config",
            str(config),
            "--allow-nonlocal-web-bind",
            "--front-door-review-json",
            str(review),
            "--summary-json",
            str(review),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "summary output must not overwrite input artifacts" in captured.err
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_readiness_docs_mention_script() -> None:
    deployment = (readiness.ROOT / "docs" / "owner-raw-d3-deployment.md").read_text(
        encoding="utf-8"
    )
    matrix = (readiness.ROOT / "docs" / "test-matrix.md").read_text(encoding="utf-8")
    changelog = (readiness.ROOT / "docs" / "changelog.md").read_text(encoding="utf-8")

    assert "scripts/audit_owner_raw_d3_readiness.py" in deployment
    assert "scripts/audit_owner_raw_d3_readiness.py" in matrix
    assert "owner_raw_d3_readiness_v1" in changelog
