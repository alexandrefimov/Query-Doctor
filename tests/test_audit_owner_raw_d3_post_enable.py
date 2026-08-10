from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from scripts import audit_owner_raw_d3_post_enable as post_enable


def write_json(tmp_path: Path, name: str, payload: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def source_enable_summary(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "summary_kind": "owner_raw_d3_source_enable_canary_v1",
        "status": "ok",
        "source_enable": {
            "canary_ready": True,
            "source_enabled_by_script": False,
            "native_auth_added": False,
            "live_review_required": True,
            "previous_owner_raw_source": "disabled",
            "planned_owner_raw_source": "enabled",
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
            "rehearsal_summary": {"status": "ok", "issue_counts": {}, "metadata": {}},
            "source_enable_config": {"status": "ok", "issue_counts": {}, "metadata": {}},
            "rehearsal_config_alignment": {
                "status": "ok",
                "issue_counts": {},
                "metadata": {},
            },
            "operator_confirmation": {"status": "ok", "issue_counts": {}, "metadata": {}},
        },
        "issues": {"failed_gates": [], "counts": {}},
    }
    payload.update(overrides)
    return payload


def review_payload(final_source_state: str = "leave_enabled") -> dict[str, object]:
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


def base_args(
    source_summary: Path,
    review: Path,
    summary: Path | None = None,
) -> list[str]:
    args = [
        "--source-enable-summary-json",
        str(source_summary),
        "--post-enable-review-json",
        str(review),
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
        "Authorization",
        "Cookie",
    ):
        assert forbidden not in text


def test_owner_raw_d3_post_enable_accepts_leave_enabled_review_raw_free(
    tmp_path: Path,
    capsys,
) -> None:
    source_summary = write_json(
        tmp_path,
        "secret-source-enable-summary.json",
        source_enable_summary(),
    )
    review = write_json(tmp_path, "secret-post-enable-review.json", review_payload())

    rc = post_enable.main(base_args(source_summary, review))

    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    assert rc == 0
    assert "Owner raw D3 post-enable canary: ok" in captured.out
    assert "canary_validated=yes" in captured.out
    assert "canary_close_ready=yes" in captured.out
    assert "source_enable_summary=ok" in captured.out
    assert "post_enable_review=ok" in captured.out
    assert "final_state=ok" in captured.out
    assert "final_source_state=leave_enabled" in captured.out
    assert "source_enabled_by_script=no" in captured.out
    assert "native_auth_added=no" in captured.out
    assert "Failed gates: none" in captured.out
    assert "Issues: none" in captured.out
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_d3_post_enable_accepts_rollback_completed_review(
    tmp_path: Path,
    capsys,
) -> None:
    source_summary = write_json(tmp_path, "secret-source-summary.json", source_enable_summary())
    review = write_json(
        tmp_path,
        "secret-rollback-review.json",
        review_payload(final_source_state="rollback_completed"),
    )

    rc = post_enable.main(base_args(source_summary, review))

    captured = capsys.readouterr()
    assert rc == 0
    assert "final_source_state=rollback_completed" in captured.out
    assert "canary_close_ready=yes" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_post_enable_writes_raw_free_summary(
    tmp_path: Path,
    capsys,
) -> None:
    source_summary = write_json(tmp_path, "secret-source-summary.json", source_enable_summary())
    review = write_json(tmp_path, "secret-review.json", review_payload())
    summary = tmp_path / "secret-summary.json"

    rc = post_enable.main(base_args(source_summary, review, summary))

    captured = capsys.readouterr()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    rendered = captured.out + captured.err + json.dumps(payload, sort_keys=True)
    assert rc == 0
    assert payload["summary_kind"] == "owner_raw_d3_post_enable_canary_v1"
    assert payload["status"] == "ok"
    assert payload["post_enable"]["canary_validated"] is True
    assert payload["post_enable"]["canary_close_ready"] is True
    assert payload["post_enable"]["final_source_state"] == "leave_enabled"
    assert payload["post_enable"]["source_enabled_by_script"] is False
    assert payload["post_enable"]["native_auth_added"] is False
    assert payload["post_enable"]["paths_printed"] is False
    assert payload["post_enable"]["header_names_printed"] is False
    assert payload["post_enable"]["raw_source_printed"] is False
    assert payload["issues"] == {"counts": {}, "failed_gates": []}
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_d3_post_enable_template_is_raw_free_and_fail_closed(
    tmp_path: Path,
    capsys,
) -> None:
    template = tmp_path / "secret-template.json"

    rc = post_enable.main(["--template-json", str(template)])

    captured = capsys.readouterr()
    payload = json.loads(template.read_text(encoding="utf-8"))
    result = post_enable.audit_review(payload)
    rendered = captured.out + captured.err + json.dumps(payload, sort_keys=True)
    assert rc == 0
    assert "Owner raw D3 post-enable canary template: written" in captured.out
    assert payload["review_status"] == "unreviewed"
    assert result.ok is False
    assert result.issue_counts["review_not_marked_reviewed"] == 1
    assert result.issue_counts["matching_viewer_own_case_not_allowed"] == 1
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_d3_post_enable_rejects_failed_source_enable_summary(
    tmp_path: Path,
    capsys,
) -> None:
    failed_summary = source_enable_summary(status="failed")
    source_payload = failed_summary["source_enable"]
    issues = failed_summary["issues"]
    assert isinstance(source_payload, dict)
    assert isinstance(issues, dict)
    source_payload["canary_ready"] = False
    issues["failed_gates"] = ["source_enable_config"]
    issues["counts"] = {"config.owner_raw_source_not_explicitly_enabled": 1}
    source_summary = write_json(tmp_path, "secret-source-summary.json", failed_summary)
    review = write_json(tmp_path, "secret-review.json", review_payload())

    rc = post_enable.main(base_args(source_summary, review))

    captured = capsys.readouterr()
    assert rc == 1
    assert "source_enable_summary=failed" in captured.out
    assert "source_enable.status_not_ok" in captured.out
    assert "source_enable.canary_not_ready" in captured.out
    assert "source_enable.issues_not_empty" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_post_enable_rejects_source_enabled_by_script(
    tmp_path: Path,
    capsys,
) -> None:
    summary = source_enable_summary()
    source_payload = summary["source_enable"]
    assert isinstance(source_payload, dict)
    source_payload["source_enabled_by_script"] = True
    source_summary = write_json(tmp_path, "secret-source-summary.json", summary)
    review = write_json(tmp_path, "secret-review.json", review_payload())

    rc = post_enable.main(base_args(source_summary, review))

    captured = capsys.readouterr()
    assert rc == 1
    assert "source_enable.source_enabled_by_script" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_post_enable_rejects_runtime_matrix_failure(
    tmp_path: Path,
    capsys,
) -> None:
    source_summary = write_json(tmp_path, "secret-source-summary.json", source_enable_summary())
    payload = review_payload()
    runtime = payload["runtime_checks"]
    assert isinstance(runtime, dict)
    runtime["different_viewer_same_case_denied"] = False
    runtime["spoofed_viewer_header_not_authorizing"] = False
    review = write_json(tmp_path, "secret-review.json", payload)

    rc = post_enable.main(base_args(source_summary, review))

    captured = capsys.readouterr()
    assert rc == 1
    assert "post_enable.different_viewer_same_case_not_denied" in captured.out
    assert "post_enable.spoofed_viewer_header_authorized" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_post_enable_rejects_raw_retention_and_unsafe_values(
    tmp_path: Path,
    capsys,
) -> None:
    source_summary = write_json(tmp_path, "secret-source-summary.json", source_enable_summary())
    payload = review_payload()
    evidence = payload["evidence_retention"]
    assert isinstance(evidence, dict)
    evidence["raw_paths_retained"] = True
    payload["private_proxy_url"] = "https://private-proxy.example.invalid"
    front_door = payload["front_door"]
    assert isinstance(front_door, dict)
    front_door["reviewed_subject"] = "analyst_one@example.invalid"
    review = write_json(tmp_path, "secret-review.json", payload)

    rc = post_enable.main(base_args(source_summary, review))

    captured = capsys.readouterr()
    assert rc == 1
    assert "post_enable.raw_paths_retained" in captured.out
    assert "post_enable.unexpected_field" in captured.out
    assert "post_enable.unsafe_string_value" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_post_enable_rejects_missing_rollback_verification(
    tmp_path: Path,
    capsys,
) -> None:
    source_summary = write_json(tmp_path, "secret-source-summary.json", source_enable_summary())
    payload = review_payload()
    rollback = payload["rollback"]
    assert isinstance(rollback, dict)
    rollback["kill_switch_rollback_verified"] = False
    rollback["rollback_path_ready"] = False
    review = write_json(tmp_path, "secret-review.json", payload)

    rc = post_enable.main(base_args(source_summary, review))

    captured = capsys.readouterr()
    assert rc == 1
    assert "post_enable.kill_switch_rollback_not_verified" in captured.out
    assert "post_enable.rollback_path_not_ready" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_post_enable_rejects_final_state_mismatch(
    tmp_path: Path,
    capsys,
) -> None:
    source_summary = write_json(tmp_path, "secret-source-summary.json", source_enable_summary())
    payload = review_payload(final_source_state="rollback_completed")
    source_state = payload["source_state"]
    assert isinstance(source_state, dict)
    source_state["owner_raw_source_remaining_enabled"] = True
    review = write_json(tmp_path, "secret-review.json", payload)

    rc = post_enable.main(base_args(source_summary, review))

    captured = capsys.readouterr()
    assert rc == 1
    assert "post_enable.rollback_completed_final_state_mismatch" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_post_enable_rejects_summary_overlap_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    source_summary = write_json(tmp_path, "secret-source-summary.json", source_enable_summary())
    review = write_json(tmp_path, "secret-review.json", review_payload())

    rc = post_enable.main(base_args(source_summary, review, source_summary))

    captured = capsys.readouterr()
    assert rc == 2
    assert "summary or template output must not overwrite input artifacts" in captured.err
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_post_enable_required_fields_are_safe(capsys) -> None:
    rc = post_enable.main(["--list-required-fields"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "runtime_checks.matching_viewer_own_case_allowed" in captured.out
    assert "source_state.owner_raw_source_remaining_enabled" in captured.out
    assert "header" in captured.out
    assert "https://" not in captured.out
    assert "analyst" not in captured.out


def test_owner_raw_d3_post_enable_docs_mention_script() -> None:
    deployment = (post_enable.ROOT / "docs" / "owner-raw-d3-deployment.md").read_text(
        encoding="utf-8"
    )
    changelog = (post_enable.ROOT / "docs" / "changelog.md").read_text(encoding="utf-8")

    assert "scripts/audit_owner_raw_d3_post_enable.py" in deployment
    assert "owner_raw_d3_post_enable_canary_v1" in changelog
