from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from scripts import audit_owner_raw_d3_launch_closure as closure


def write_json(tmp_path: Path, name: str, payload: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def front_door_summary(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "summary_kind": "owner_raw_live_front_door_review_audit_v1",
        "status": "ok",
        "review_profile": "owner_raw_d3",
        "checked_required_fields": 17,
        "issue_counts": {},
        "front_door_boundary": {
            "trusted_front_door_identity_review": "operator_review_summary",
            "direct_upstream_client_access_blocked": True,
            "inbound_viewer_header_stripping_required": True,
            "exactly_one_normalized_viewer_header_required": True,
            "raw_identity_token_forwarding": "blocked",
            "raw_values_output": False,
            "path_output": False,
            "url_output": False,
            "header_output": False,
            "user_output": False,
            "query_id_output": False,
            "source_output": False,
        },
        "trino_boundary": {
            "shared_hardening_profile": False,
            "broader_shared_trino_support": False,
            "raw_trino_source_reveal": "blocked",
            "metadata_collection": "not_wired",
            "running_scan": "not_wired",
            "query_history_crawling": "not_wired",
            "llm_report_output": "not_wired",
            "query_optimizer_jobs": "not_wired",
            "generated_sql": "not_wired",
            "sql_execution": "not_wired",
        },
    }
    payload.update(overrides)
    return payload


def readiness_summary(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "summary_kind": "owner_raw_d3_readiness_v1",
        "status": "ok",
        "readiness": {
            "source_enable_ready": True,
            "native_auth_added": False,
            "live_review_required": True,
            "front_door_review": "ok",
            "staging_config_preflight": "ok",
            "current_config_owner_raw_source": "disabled",
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
            "staging_config_preflight": {"status": "ok", "issue_counts": {}, "metadata": {}},
            "live_front_door_review": {"status": "ok", "issue_counts": {}, "metadata": {}},
        },
        "issues": {"counts": {}},
    }
    payload.update(overrides)
    return payload


def rehearsal_summary(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "summary_kind": "owner_raw_d3_rehearsal_v1",
        "status": "ok",
        "readiness": {
            "rehearsal_complete": True,
            "source_enable_ready": True,
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
            "dev_sso_keycloak_smoke": {
                "status": "ok",
                "issue_counts": {},
                "metadata": {"check_count": 4, "raw_values_output": False},
            },
            "live_front_door_review": {"status": "ok", "issue_counts": {}, "metadata": {}},
            "staging_config_preflight": {"status": "ok", "issue_counts": {}, "metadata": {}},
            "d3_readiness": {
                "status": "ok",
                "issue_counts": {},
                "metadata": {
                    "source_enable_ready": True,
                    "staging_config_preflight": "ok",
                    "front_door_review": "ok",
                    "current_config_owner_raw_source": "disabled",
                    "native_auth_added": False,
                    "live_review_required": True,
                },
            },
        },
        "issues": {"failed_gates": [], "counts": {}},
    }
    payload.update(overrides)
    return payload


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


def post_enable_summary(final_source_state: str = "leave_enabled") -> dict[str, object]:
    return {
        "summary_kind": "owner_raw_d3_post_enable_canary_v1",
        "status": "ok",
        "post_enable": {
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
        "gates": {
            "source_enable_summary": {"status": "ok", "issue_counts": {}, "metadata": {}},
            "post_enable_review": {"status": "ok", "issue_counts": {}, "metadata": {}},
            "final_state": {"status": "ok", "issue_counts": {}, "metadata": {}},
        },
        "issues": {"failed_gates": [], "counts": {}},
    }


def write_inputs(
    tmp_path: Path,
    *,
    front_door: dict[str, object] | None = None,
    readiness: dict[str, object] | None = None,
    rehearsal: dict[str, object] | None = None,
    source_enable: dict[str, object] | None = None,
    post_enable: dict[str, object] | None = None,
) -> dict[str, Path]:
    return {
        "front_door": write_json(
            tmp_path,
            "secret-front-door-review-summary.json",
            front_door or front_door_summary(),
        ),
        "readiness": write_json(
            tmp_path,
            "secret-readiness-summary.json",
            readiness or readiness_summary(),
        ),
        "rehearsal": write_json(
            tmp_path,
            "secret-rehearsal-summary.json",
            rehearsal or rehearsal_summary(),
        ),
        "source_enable": write_json(
            tmp_path,
            "secret-source-enable-summary.json",
            source_enable or source_enable_summary(),
        ),
        "post_enable": write_json(
            tmp_path,
            "secret-post-enable-summary.json",
            post_enable or post_enable_summary(),
        ),
    }


def base_args(paths: dict[str, Path], summary: Path | None = None) -> list[str]:
    args = [
        "--front-door-review-summary-json",
        str(paths["front_door"]),
        "--readiness-summary-json",
        str(paths["readiness"]),
        "--rehearsal-summary-json",
        str(paths["rehearsal"]),
        "--source-enable-summary-json",
        str(paths["source_enable"]),
        "--post-enable-summary-json",
        str(paths["post_enable"]),
    ]
    if summary is not None:
        args.extend(["--summary-json", str(summary)])
    return args


def write_manifest(
    tmp_path: Path,
    paths: dict[str, Path],
    *,
    entry_overrides: dict[str, str] | None = None,
    metadata_overrides: dict[str, object] | None = None,
) -> Path:
    entry = {
        "front_door_review_summary_json": paths["front_door"].name,
        "readiness_summary_json": paths["readiness"].name,
        "rehearsal_summary_json": paths["rehearsal"].name,
        "source_enable_summary_json": paths["source_enable"].name,
        "post_enable_summary_json": paths["post_enable"].name,
    }
    if entry_overrides:
        entry.update(entry_overrides)
    metadata: dict[str, object] = {
        "builder_kind": "owner_raw_d3_launch_closure_manifest_builder_v1",
        "entry_count": 1,
        "path_reference": "relative_to_manifest",
        "redaction_reviewed": True,
        "limitations": [
            "retained_owner_raw_d3_summaries",
            "front_door_review_summary_checked",
            "readiness_summary_checked",
            "rehearsal_summary_checked",
            "source_enable_summary_checked",
            "post_enable_summary_checked",
            "not_committed_public_documentation",
            "not_native_sso",
            "not_source_reader",
        ],
    }
    if metadata_overrides:
        metadata.update(metadata_overrides)
    manifest = tmp_path / "secret-launch-closure-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_kind": "owner_raw_d3_launch_closure_manifest_v1",
                "metadata": metadata,
                "entries": [entry],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


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


def test_owner_raw_d3_launch_closure_accepts_leave_enabled_chain_raw_free(
    tmp_path: Path,
    capsys,
) -> None:
    paths = write_inputs(tmp_path)
    summary = tmp_path / "secret-launch-closure-summary.json"

    rc = closure.main(base_args(paths, summary))

    captured = capsys.readouterr()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    rendered = captured.out + captured.err + json.dumps(payload, sort_keys=True)
    assert rc == 0
    assert "Owner raw D3 launch closure: ok" in captured.out
    assert "launch_closure_ready=yes" in captured.out
    assert "verdict=closed" in captured.out
    assert "front_door_review_summary=ok" in captured.out
    assert "readiness_summary=ok" in captured.out
    assert "rehearsal_summary=ok" in captured.out
    assert "source_enable_summary=ok" in captured.out
    assert "post_enable_summary=ok" in captured.out
    assert "chain_consistency=ok" in captured.out
    assert "final_source_state=leave_enabled" in captured.out
    assert "source_enabled_by_script=no" in captured.out
    assert "native_auth_added=no" in captured.out
    assert "Failed gates: none" in captured.out
    assert "Issues: none" in captured.out
    assert payload["summary_kind"] == "owner_raw_d3_launch_closure_v1"
    assert payload["status"] == "ok"
    assert payload["closure"]["launch_closure_ready"] is True
    assert payload["closure"]["verdict"] == "closed"
    assert payload["closure"]["final_source_state"] == "leave_enabled"
    assert payload["closure"]["source_enabled_by_script"] is False
    assert payload["closure"]["native_auth_added"] is False
    assert payload["closure"]["raw_source_printed"] is False
    assert payload["issues"] == {"counts": {}, "failed_gates": []}
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_d3_launch_closure_accepts_rollback_completed_chain(
    tmp_path: Path,
    capsys,
) -> None:
    paths = write_inputs(tmp_path, post_enable=post_enable_summary("rollback_completed"))

    rc = closure.main(base_args(paths))

    captured = capsys.readouterr()
    assert rc == 0
    assert "verdict=closed" in captured.out
    assert "final_source_state=rollback_completed" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_launch_closure_accepts_manifest_mode(
    tmp_path: Path,
    capsys,
) -> None:
    paths = write_inputs(tmp_path)
    manifest = write_manifest(tmp_path, paths)
    summary = tmp_path / "secret-launch-closure-summary.json"

    rc = closure.main(
        [
            "--launch-closure-manifest",
            str(manifest),
            "--summary-json",
            str(summary),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    rendered = captured.out + captured.err + json.dumps(payload, sort_keys=True)
    assert rc == 0
    assert "Owner raw D3 launch closure: ok" in captured.out
    assert "launch_closure_ready=yes" in captured.out
    assert "verdict=closed" in captured.out
    assert "front_door_review_summary=ok" in captured.out
    assert "chain_consistency=ok" in captured.out
    assert payload["summary_kind"] == "owner_raw_d3_launch_closure_v1"
    assert payload["status"] == "ok"
    assert payload["closure"]["final_source_state"] == "leave_enabled"
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_d3_launch_closure_rejects_failed_readiness_summary(
    tmp_path: Path,
    capsys,
) -> None:
    broken = readiness_summary(status="failed")
    broken["issues"] = {"counts": {"front_door.status_not_ok": 1}}
    paths = write_inputs(tmp_path, readiness=broken)

    rc = closure.main(base_args(paths))

    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    assert rc == 1
    assert "Owner raw D3 launch closure: failed" in captured.out
    assert "launch_closure_ready=no" in captured.out
    assert "verdict=blocked" in captured.out
    assert "readiness_summary=failed" in captured.out
    assert "readiness.status_not_ok" in captured.out
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_d3_launch_closure_rejects_source_enabled_by_script(
    tmp_path: Path,
    capsys,
) -> None:
    broken = source_enable_summary()
    source_payload = broken["source_enable"]
    assert isinstance(source_payload, dict)
    source_payload["source_enabled_by_script"] = True
    paths = write_inputs(tmp_path, source_enable=broken)

    rc = closure.main(base_args(paths))

    captured = capsys.readouterr()
    assert rc == 1
    assert "source_enable_summary=failed" in captured.out
    assert "chain_consistency=failed" in captured.out
    assert "source_enable.source_enabled_by_script_invalid" in captured.out
    assert "chain.source_enabled_by_script" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_launch_closure_rejects_invalid_final_source_state(
    tmp_path: Path,
    capsys,
) -> None:
    broken = post_enable_summary("pending_review")
    paths = write_inputs(tmp_path, post_enable=broken)

    rc = closure.main(base_args(paths))

    captured = capsys.readouterr()
    assert rc == 1
    assert "post_enable_summary=failed" in captured.out
    assert "chain_consistency=failed" in captured.out
    assert "final_source_state=unknown" in captured.out
    assert "post_enable.invalid_final_source_state" in captured.out
    assert "pending_review" not in captured.out + captured.err
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_launch_closure_rejects_raw_field_contamination(
    tmp_path: Path,
    capsys,
) -> None:
    contaminated = deepcopy(readiness_summary())
    contaminated["raw_url"] = "https://private.example.invalid/source?code=secret"
    paths = write_inputs(tmp_path, readiness=contaminated)

    rc = closure.main(base_args(paths))

    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    assert rc == 1
    assert "readiness_summary=failed" in captured.out
    assert "readiness.unexpected_field" in captured.out
    assert "readiness.unsafe_string_value" in captured.out
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_d3_launch_closure_rejects_malformed_issue_counts(
    tmp_path: Path,
    capsys,
) -> None:
    malformed = front_door_summary(issue_counts=[])
    paths = write_inputs(tmp_path, front_door=malformed)

    rc = closure.main(base_args(paths))

    captured = capsys.readouterr()
    assert rc == 1
    assert "front_door_review_summary=failed" in captured.out
    assert "front_door.issues_missing" in captured.out
    assert "front_door.unsafe_issue_counts_shape" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_launch_closure_requires_all_inputs(tmp_path: Path, capsys) -> None:
    paths = write_inputs(tmp_path)
    args = base_args(paths)
    args = args[:-2]

    rc = closure.main(args)

    captured = capsys.readouterr()
    assert rc == 2
    assert "required inputs are missing" in captured.err
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_launch_closure_rejects_manifest_combined_with_direct_inputs(
    tmp_path: Path,
    capsys,
) -> None:
    paths = write_inputs(tmp_path)
    manifest = write_manifest(tmp_path, paths)

    rc = closure.main(["--launch-closure-manifest", str(manifest), *base_args(paths)])

    captured = capsys.readouterr()
    assert rc == 2
    assert "launch closure inputs are not accepted" in captured.err
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_launch_closure_rejects_manifest_summary_output_overlap(
    tmp_path: Path,
    capsys,
) -> None:
    paths = write_inputs(tmp_path)
    manifest = write_manifest(tmp_path, paths)

    rc = closure.main(
        [
            "--launch-closure-manifest",
            str(manifest),
            "--summary-json",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "summary output must not overwrite input artifacts" in captured.err
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_launch_closure_rejects_manifest_unsafe_reference(
    tmp_path: Path,
    capsys,
) -> None:
    paths = write_inputs(tmp_path)
    manifest = write_manifest(
        tmp_path,
        paths,
        entry_overrides={"post_enable_summary_json": "../secret-post-enable-summary.json"},
    )

    rc = closure.main(["--launch-closure-manifest", str(manifest)])

    captured = capsys.readouterr()
    assert rc == 2
    assert "launch closure inputs are not accepted" in captured.err
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_launch_closure_rejects_manifest_duplicate_reference(
    tmp_path: Path,
    capsys,
) -> None:
    paths = write_inputs(tmp_path)
    manifest = write_manifest(
        tmp_path,
        paths,
        entry_overrides={"post_enable_summary_json": paths["source_enable"].name},
    )

    rc = closure.main(["--launch-closure-manifest", str(manifest)])

    captured = capsys.readouterr()
    assert rc == 2
    assert "launch closure inputs are not accepted" in captured.err
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_launch_closure_rejects_manifest_without_redaction_review(
    tmp_path: Path,
    capsys,
) -> None:
    paths = write_inputs(tmp_path)
    manifest = write_manifest(tmp_path, paths, metadata_overrides={"redaction_reviewed": False})

    rc = closure.main(["--launch-closure-manifest", str(manifest)])

    captured = capsys.readouterr()
    assert rc == 2
    assert "launch closure inputs are not accepted" in captured.err
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_launch_closure_rejects_summary_overwriting_input(
    tmp_path: Path,
    capsys,
) -> None:
    paths = write_inputs(tmp_path)

    rc = closure.main(base_args(paths, summary=paths["post_enable"]))

    captured = capsys.readouterr()
    assert rc == 2
    assert "summary output must not overwrite input artifacts" in captured.err
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)
