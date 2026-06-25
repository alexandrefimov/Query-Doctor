from __future__ import annotations

import json
from pathlib import Path

from scripts import audit_owner_raw_live_front_door_review as review


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


def trino_shared_review_payload() -> dict[str, object]:
    payload = owner_raw_review_payload()
    payload["review_profile"] = "trino_shared_hardening"
    owner_raw_checks = payload["owner_raw_checks"]
    assert isinstance(owner_raw_checks, dict)
    owner_raw_checks.pop("matching_viewer_own_case_allowed")
    owner_raw_checks.pop("different_viewer_same_case_denied")
    payload["trino_shared_hardening"] = {
        "reviewed": True,
        "raw_trino_source_reveal_blocked": True,
        "owner_raw_source_enabled": False,
        "details_python_report_materialized_only": True,
        "optimizer_guidance_materialized_only": True,
        "metadata_cli_smoke_dev_only": True,
        "unsupported_shared_surfaces_blocked": True,
        "product_metadata_collection_wired": False,
        "running_scan_wired": False,
        "query_history_crawling_wired": False,
        "llm_report_output_wired": False,
        "query_optimizer_jobs_wired": False,
        "generated_sql_wired": False,
        "sql_execution_wired": False,
    }
    return payload


def test_owner_raw_live_front_door_review_accepts_owner_raw_profile_raw_free() -> None:
    result = review.audit_review(owner_raw_review_payload())
    payload = review.summary_payload(result)
    text = json.dumps(payload, sort_keys=True) + review.format_summary(payload)

    assert result.ok is True
    assert result.profile == "owner_raw_d3"
    assert payload["summary_kind"] == "owner_raw_live_front_door_review_audit_v1"
    assert payload["status"] == "ok"
    assert payload["front_door_boundary"]["raw_values_output"] is False
    assert payload["trino_boundary"]["broader_shared_trino_support"] is False
    assert "issue_categories: none" in text
    assert_protected_fragments_hidden(text)


def test_owner_raw_live_front_door_review_accepts_trino_shared_profile_raw_free() -> None:
    result = review.audit_review(
        trino_shared_review_payload(),
        require_trino_shared_hardening=True,
    )
    payload = review.summary_payload(result)
    text = json.dumps(payload, sort_keys=True) + review.format_summary(payload)

    assert result.ok is True
    assert result.profile == "trino_shared_hardening"
    assert payload["trino_boundary"]["shared_hardening_profile"] is True
    assert "review_profile=trino_shared_hardening" in text
    assert_protected_fragments_hidden(text)


def test_owner_raw_live_front_door_review_rejects_unsafe_values_without_echo() -> None:
    payload = trino_shared_review_payload()
    front_door = payload["front_door"]
    assert isinstance(front_door, dict)
    front_door["normalized_viewer_value_shape"] = "analyst_one@example.invalid"
    front_door["private_proxy_url"] = "https://private-proxy.example.invalid"
    evidence = payload["evidence_retention"]
    assert isinstance(evidence, dict)
    evidence["raw_paths_retained"] = True

    result = review.audit_review(payload, require_trino_shared_hardening=True)
    summary = review.summary_payload(result)
    text = json.dumps(summary, sort_keys=True) + review.format_summary(summary)

    assert result.ok is False
    assert result.issue_counts["unsafe_string_value"] == 2
    assert result.issue_counts["unexpected_field"] == 1
    assert result.issue_counts["viewer_value_not_simple_owner"] == 1
    assert result.issue_counts["raw_paths_retained"] == 1
    assert_protected_fragments_hidden(text)


def test_owner_raw_live_front_door_review_template_is_raw_free_and_fail_closed() -> None:
    payload = review.review_template("trino_shared_hardening")
    result = review.audit_review(payload, require_trino_shared_hardening=True)
    summary = review.summary_payload(result)
    text = json.dumps(payload, sort_keys=True) + json.dumps(summary, sort_keys=True)

    assert payload["summary_kind"] == "owner_raw_live_front_door_review_v1"
    assert payload["review_profile"] == "trino_shared_hardening"
    assert payload["review_status"] == "unreviewed"
    assert result.ok is False
    assert result.issue_counts["review_not_marked_reviewed"] == 1
    assert result.issue_counts["front_door_tls_not_reviewed"] == 1
    assert result.issue_counts["trino_shared_hardening_not_reviewed"] == 1
    assert "unsafe_string_value" not in result.issue_counts
    assert "unexpected_field" not in result.issue_counts
    assert_protected_fragments_hidden(text)


def test_owner_raw_live_front_door_review_cli_writes_raw_free_summary(
    tmp_path: Path,
    capsys,
) -> None:
    review_path = tmp_path / "private-review.json"
    summary_path = tmp_path / "private-summary.json"
    review_path.write_text(json.dumps(trino_shared_review_payload()), encoding="utf-8")

    rc = review.main(
        [
            "--review-json",
            str(review_path),
            "--require-trino-shared-hardening",
            "--summary-json",
            str(summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    text = captured.out + captured.err + json.dumps(summary, sort_keys=True)

    assert rc == 0
    assert summary["status"] == "ok"
    assert "Owner raw live front-door review audit: ok" in captured.out
    assert_protected_fragments_hidden(text, tmp_path=tmp_path)


def test_owner_raw_live_front_door_review_cli_writes_raw_free_template(
    tmp_path: Path,
    capsys,
) -> None:
    template_path = tmp_path / "private-template.json"

    rc = review.main(
        [
            "--require-trino-shared-hardening",
            "--template-json",
            str(template_path),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(template_path.read_text(encoding="utf-8"))
    result = review.audit_review(payload, require_trino_shared_hardening=True)
    text = captured.out + captured.err + json.dumps(payload, sort_keys=True)

    assert rc == 0
    assert "Owner raw live front-door review template: written" in captured.out
    assert payload["review_status"] == "unreviewed"
    assert result.ok is False
    assert_protected_fragments_hidden(text, tmp_path=tmp_path)


def test_owner_raw_live_front_door_review_rejects_output_overlap_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    review_path = tmp_path / "private-review.json"
    review_path.write_text(json.dumps(trino_shared_review_payload()), encoding="utf-8")

    rc = review.main(
        [
            "--review-json",
            str(review_path),
            "--summary-json",
            str(review_path),
        ]
    )

    captured = capsys.readouterr()
    text = captured.out + captured.err

    assert rc == 2
    assert "summary or template output must not overwrite input artifacts" in captured.err
    assert_protected_fragments_hidden(text, tmp_path=tmp_path)


def test_owner_raw_live_front_door_review_rejects_template_overlap_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    review_path = tmp_path / "private-review.json"
    review_path.write_text(json.dumps(trino_shared_review_payload()), encoding="utf-8")

    rc = review.main(
        [
            "--review-json",
            str(review_path),
            "--template-json",
            str(review_path),
        ]
    )

    captured = capsys.readouterr()
    text = captured.out + captured.err

    assert rc == 2
    assert "summary or template output must not overwrite input artifacts" in captured.err
    assert_protected_fragments_hidden(text, tmp_path=tmp_path)


def test_owner_raw_live_front_door_review_required_fields_are_public_safe(capsys) -> None:
    rc = review.main(["--review-json", "/private/tmp/unused.json", "--list-required-fields"])

    captured = capsys.readouterr()

    assert rc == 0
    assert "front_door.inbound_viewer_header_stripped" in captured.out
    assert "owner_raw_checks.matching_viewer_own_case_allowed" in captured.out
    assert "/private/tmp/unused.json" not in captured.out


def assert_protected_fragments_hidden(text: str, *, tmp_path: Path | None = None) -> None:
    fragments = [
        "analyst_one",
        "example.invalid",
        "private-proxy",
        "private-review",
        "private-summary",
        "private-template",
        "X-Query-Doctor-Viewer",
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "/private/tmp",
    ]
    if tmp_path is not None:
        fragments.append(str(tmp_path))
    for fragment in fragments:
        assert fragment not in text
