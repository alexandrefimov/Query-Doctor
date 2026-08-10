from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from scripts import audit_owner_raw_d3_source_enable as source_enable


def write_json(tmp_path: Path, name: str, payload: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def source_enabled_config(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "host": "0.0.0.0",
        "source_visibility": "owner_raw",
        "viewer_identity_header": "X-Secret-Viewer",
        "owner_raw_source_enabled": True,
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
            "live_front_door_review": {
                "status": "ok",
                "issue_counts": {},
                "metadata": {"review_profile": "owner_raw_d3", "checked_required_fields": 26},
            },
            "staging_config_preflight": {
                "status": "ok",
                "issue_counts": {},
                "metadata": {
                    "source_count": 1,
                    "owner_raw_source_count": 1,
                    "nonlocal_owner_raw_source_count": 1,
                    "viewer_identity_header": "configured",
                    "owner_raw_source": "disabled",
                    "privacy_safe_count": 1,
                    "redaction_safe_count": 1,
                },
            },
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


def base_args(config: Path, rehearsal: Path, summary: Path | None = None) -> list[str]:
    args = [
        "--config",
        str(config),
        "--rehearsal-summary-json",
        str(rehearsal),
        "--allow-nonlocal-web-bind",
        "--confirm-source-enable-canary",
        "--confirm-no-disable-owner-raw-source",
        "--confirm-no-front-door-or-header-change",
        "--confirm-kill-switch-rollback-plan",
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
        "state=",
        "Authorization",
        "Cookie",
    ):
        assert forbidden not in text


def test_owner_raw_d3_source_enable_accepts_canary_config_raw_free(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_json(tmp_path, "secret-source-enabled-config.json", source_enabled_config())
    rehearsal = write_json(tmp_path, "secret-rehearsal-summary.json", rehearsal_summary())

    rc = source_enable.main(base_args(config, rehearsal))

    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    assert rc == 0
    assert "Owner raw D3 source-enable canary: ok" in captured.out
    assert "canary_ready=yes" in captured.out
    assert "rehearsal_summary=ok" in captured.out
    assert "source_enable_config=ok" in captured.out
    assert "rehearsal_config_alignment=ok" in captured.out
    assert "operator_confirmation=ok" in captured.out
    assert "previous_owner_raw_source=disabled" in captured.out
    assert "planned_owner_raw_source=enabled" in captured.out
    assert "source_enabled_by_script=no" in captured.out
    assert "native_auth_added=no" in captured.out
    assert "Failed gates: none" in captured.out
    assert "Issues: none" in captured.out
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_d3_source_enable_writes_raw_free_summary(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_json(tmp_path, "secret-source-enabled-config.json", source_enabled_config())
    rehearsal = write_json(tmp_path, "secret-rehearsal-summary.json", rehearsal_summary())
    summary = tmp_path / "secret-source-enable-summary.json"

    rc = source_enable.main(base_args(config, rehearsal, summary))

    captured = capsys.readouterr()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    rendered = captured.out + captured.err + json.dumps(payload, sort_keys=True)
    assert rc == 0
    assert payload["summary_kind"] == "owner_raw_d3_source_enable_canary_v1"
    assert payload["status"] == "ok"
    assert payload["source_enable"]["canary_ready"] is True
    assert payload["source_enable"]["source_enabled_by_script"] is False
    assert payload["source_enable"]["native_auth_added"] is False
    assert payload["source_enable"]["paths_printed"] is False
    assert payload["source_enable"]["header_names_printed"] is False
    assert payload["source_enable"]["raw_source_printed"] is False
    assert payload["gates"]["rehearsal_summary"]["status"] == "ok"
    assert payload["gates"]["source_enable_config"]["status"] == "ok"
    assert payload["gates"]["rehearsal_config_alignment"]["status"] == "ok"
    assert payload["gates"]["operator_confirmation"]["status"] == "ok"
    assert payload["issues"] == {"counts": {}, "failed_gates": []}
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_d3_source_enable_rejects_disabled_config(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_json(
        tmp_path,
        "secret-disabled-config.json",
        source_enabled_config(owner_raw_source_enabled=False),
    )
    rehearsal = write_json(tmp_path, "secret-rehearsal-summary.json", rehearsal_summary())

    rc = source_enable.main(base_args(config, rehearsal))

    captured = capsys.readouterr()
    assert rc == 1
    assert "Owner raw D3 source-enable canary: failed" in captured.out
    assert "canary_ready=no" in captured.out
    assert "source_enable_config=failed" in captured.out
    assert "planned_owner_raw_source=disabled" in captured.out
    assert "config.owner_raw_source_not_explicitly_enabled" in captured.out
    assert "alignment.planned_source_not_enabled" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_source_enable_requires_explicit_source_enabled_field(
    tmp_path: Path,
    capsys,
) -> None:
    values = source_enabled_config()
    values.pop("owner_raw_source_enabled")
    config = write_json(tmp_path, "secret-missing-enabled-config.json", values)
    rehearsal = write_json(tmp_path, "secret-rehearsal-summary.json", rehearsal_summary())

    rc = source_enable.main(base_args(config, rehearsal))

    captured = capsys.readouterr()
    assert rc == 1
    assert "config.owner_raw_source_not_explicitly_enabled" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_source_enable_rejects_missing_viewer_identity_header(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_json(
        tmp_path,
        "secret-missing-header-config.json",
        source_enabled_config(viewer_identity_header=None),
    )
    rehearsal = write_json(tmp_path, "secret-rehearsal-summary.json", rehearsal_summary())

    rc = source_enable.main(base_args(config, rehearsal))

    captured = capsys.readouterr()
    assert rc == 1
    assert "config.viewer_identity_header_missing" in captured.out
    assert "alignment.viewer_identity_header_not_configured" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_source_enable_requires_nonlocal_owner_raw_source(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_json(
        tmp_path,
        "secret-local-config.json",
        source_enabled_config(host="127.0.0.1"),
    )
    rehearsal = write_json(tmp_path, "secret-rehearsal-summary.json", rehearsal_summary())

    rc = source_enable.main(base_args(config, rehearsal))

    captured = capsys.readouterr()
    assert rc == 1
    assert "config.nonlocal_owner_raw_source_missing" in captured.out
    assert "alignment.nonlocal_owner_raw_source_count_changed" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_source_enable_requires_nonlocal_bind_review(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_json(tmp_path, "secret-config.json", source_enabled_config())
    rehearsal = write_json(tmp_path, "secret-rehearsal-summary.json", rehearsal_summary())
    args = base_args(config, rehearsal)
    args.remove("--allow-nonlocal-web-bind")

    rc = source_enable.main(args)

    captured = capsys.readouterr()
    assert rc == 1
    assert "config.nonlocal_web_bind_not_explicitly_reviewed" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_source_enable_requires_operator_confirmations(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_json(tmp_path, "secret-config.json", source_enabled_config())
    rehearsal = write_json(tmp_path, "secret-rehearsal-summary.json", rehearsal_summary())

    rc = source_enable.main(
        [
            "--config",
            str(config),
            "--rehearsal-summary-json",
            str(rehearsal),
            "--allow-nonlocal-web-bind",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "operator_confirmation=failed" in captured.out
    assert "operator.source_enable_canary_confirmation_missing" in captured.out
    assert "operator.no_disable_owner_raw_source_confirmation_missing" in captured.out
    assert "operator.no_front_door_or_header_change_confirmation_missing" in captured.out
    assert "operator.kill_switch_rollback_plan_confirmation_missing" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_source_enable_rejects_failed_rehearsal_summary(
    tmp_path: Path,
    capsys,
) -> None:
    failed_summary = rehearsal_summary(status="failed")
    readiness = failed_summary["readiness"]
    assert isinstance(readiness, dict)
    readiness["source_enable_ready"] = False
    issues = failed_summary["issues"]
    assert isinstance(issues, dict)
    issues["failed_gates"] = ["d3_readiness"]
    issues["counts"] = {"d3_readiness_not_ready": 1}
    config = write_json(tmp_path, "secret-config.json", source_enabled_config())
    rehearsal = write_json(tmp_path, "secret-failed-rehearsal.json", failed_summary)

    rc = source_enable.main(base_args(config, rehearsal))

    captured = capsys.readouterr()
    assert rc == 1
    assert "rehearsal_summary=failed" in captured.out
    assert "rehearsal.status_not_ok" in captured.out
    assert "rehearsal.source_enable_not_ready" in captured.out
    assert "rehearsal.issues_not_empty" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_source_enable_rejects_rehearsal_without_disabled_source(
    tmp_path: Path,
    capsys,
) -> None:
    summary = rehearsal_summary()
    gates = summary["gates"]
    assert isinstance(gates, dict)
    d3_gate = gates["d3_readiness"]
    staging_gate = gates["staging_config_preflight"]
    assert isinstance(d3_gate, dict)
    assert isinstance(staging_gate, dict)
    d3_metadata = d3_gate["metadata"]
    staging_metadata = staging_gate["metadata"]
    assert isinstance(d3_metadata, dict)
    assert isinstance(staging_metadata, dict)
    d3_metadata["current_config_owner_raw_source"] = "enabled"
    staging_metadata["owner_raw_source"] = "enabled"
    config = write_json(tmp_path, "secret-config.json", source_enabled_config())
    rehearsal = write_json(tmp_path, "secret-rehearsal-enabled-source.json", summary)

    rc = source_enable.main(base_args(config, rehearsal))

    captured = capsys.readouterr()
    assert rc == 1
    assert "rehearsal.previous_source_not_disabled" in captured.out
    assert "alignment.previous_source_not_disabled" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_source_enable_rejects_source_count_drift(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_json(
        tmp_path,
        "secret-cluster-config.json",
        {
            "host": "0.0.0.0",
            "viewer_identity_header": "X-Secret-Viewer",
            "owner_raw_source_enabled": True,
            "clusters": [
                {"id": "one", "label": "One", "source_visibility": "owner_raw"},
                {"id": "two", "label": "Two", "source_visibility": "owner_raw"},
            ],
        },
    )
    rehearsal = write_json(tmp_path, "secret-rehearsal-summary.json", rehearsal_summary())

    rc = source_enable.main(base_args(config, rehearsal))

    captured = capsys.readouterr()
    assert rc == 1
    assert "alignment.owner_raw_source_count_changed" in captured.out
    assert "alignment.nonlocal_owner_raw_source_count_changed" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_source_enable_rejects_raw_output_rehearsal_flags(
    tmp_path: Path,
    capsys,
) -> None:
    summary = deepcopy(rehearsal_summary())
    readiness = summary["readiness"]
    assert isinstance(readiness, dict)
    readiness["header_names_printed"] = True
    readiness["raw_source_printed"] = True
    config = write_json(tmp_path, "secret-config.json", source_enabled_config())
    rehearsal = write_json(tmp_path, "secret-raw-output-rehearsal.json", summary)

    rc = source_enable.main(base_args(config, rehearsal))

    captured = capsys.readouterr()
    assert rc == 1
    assert "rehearsal.header_names_printed" in captured.out
    assert "rehearsal.raw_source_printed" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_source_enable_rejects_summary_overlap_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_json(tmp_path, "secret-config.json", source_enabled_config())
    rehearsal = write_json(tmp_path, "secret-rehearsal-summary.json", rehearsal_summary())

    rc = source_enable.main(base_args(config, rehearsal, config))

    captured = capsys.readouterr()
    assert rc == 2
    assert "summary output must not overwrite input artifacts" in captured.err
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_d3_source_enable_docs_mention_script() -> None:
    deployment = (source_enable.ROOT / "docs" / "owner-raw-d3-deployment.md").read_text(
        encoding="utf-8"
    )
    changelog = (source_enable.ROOT / "docs" / "changelog.md").read_text(encoding="utf-8")

    assert "scripts/audit_owner_raw_d3_source_enable.py" in deployment
    assert "owner_raw_d3_source_enable_canary_v1" in changelog
