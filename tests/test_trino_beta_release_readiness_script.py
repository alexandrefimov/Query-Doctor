from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import audit_trino_beta_release_readiness as release_readiness


def test_trino_beta_release_readiness_static_plan_skips_local_gates() -> None:
    args = release_readiness.build_parser().parse_args(["--static-only"])

    gates = release_readiness.build_gate_plan(args)
    names = [gate.name for gate in gates]

    assert names[:4] == [
        "trino_shared_deployment_boundary",
        "trino_product_surface_boundary",
        "trino_support_gap_matrix",
        "active_docs",
    ]
    assert "trino_focused_pytest" in names
    assert "trino_web_beta_local_config_readiness" not in names
    assert "trino_metadata_cli_summary_smoke" not in names
    assert "trino_web_beta_backend_live_smoke" not in names
    assert "trino_web_beta_ui_smoke" not in names
    assert not any(gate.requires_local_config for gate in gates)
    assert not any(gate.performs_network_read for gate in gates)
    assert not any(gate.uses_operator_metadata_inputs for gate in gates)


def test_trino_beta_release_readiness_full_plan_uses_existing_gates() -> None:
    args = release_readiness.build_parser().parse_args(
        [
            "--config",
            "/private/tmp/secret-trino-config.json",
            "--cluster",
            "secret_cluster",
            "--selected-query-limit",
            "2",
            "--recent-window-minutes",
            "60",
        ]
    )

    gates = release_readiness.build_gate_plan(args)
    by_name = {gate.name: gate for gate in gates}

    assert "trino_web_beta_local_config_readiness" in by_name
    assert "trino_web_beta_backend_live_smoke" in by_name
    assert "trino_web_beta_ui_smoke" in by_name
    assert "trino_shared_deployment_boundary" in by_name
    assert by_name["trino_shared_deployment_boundary"].requires_local_config
    assert "audit_trino_shared_deployment_boundary.py" in " ".join(
        by_name["trino_shared_deployment_boundary"].command
    )
    assert "--config" in by_name["trino_shared_deployment_boundary"].command
    assert (
        "--trusted-front-door-reviewed" not in by_name["trino_shared_deployment_boundary"].command
    )
    assert by_name["trino_web_beta_local_config_readiness"].requires_local_config
    assert by_name["trino_web_beta_backend_live_smoke"].performs_network_read
    assert by_name["trino_web_beta_ui_smoke"].performs_network_read
    assert "--require-query-id" in by_name["trino_web_beta_local_config_readiness"].command
    assert "--require-recent" in by_name["trino_web_beta_local_config_readiness"].command
    assert "--selected-query-limit" in by_name["trino_web_beta_backend_live_smoke"].command
    assert "--limit" in by_name["trino_web_beta_ui_smoke"].command


def test_trino_beta_release_readiness_can_propagate_front_door_review_flag() -> None:
    args = release_readiness.build_parser().parse_args(
        [
            "--config",
            "/private/tmp/secret-trino-config.json",
            "--trusted-front-door-reviewed",
            "--skip-pytest",
            "--skip-live-smoke",
            "--skip-ui-smoke",
        ]
    )

    gates = release_readiness.build_gate_plan(args)
    by_name = {gate.name: gate for gate in gates}

    boundary_command = by_name["trino_shared_deployment_boundary"].command
    assert "--trusted-front-door-reviewed" in boundary_command
    assert "/private/tmp/secret-trino-config.json" in boundary_command

    results = tuple(release_readiness.GateResult(gate.name, "ok", 0) for gate in gates)
    payload = release_readiness.summary_payload(
        gates=gates,
        results=results,
        static_only=False,
    )
    assert payload["surface_boundary"]["trusted_front_door_review"] == "confirmed"


def test_trino_beta_release_readiness_can_add_metadata_cli_smoke_gate() -> None:
    args = release_readiness.build_parser().parse_args(
        [
            "--skip-pytest",
            "--skip-live-smoke",
            "--skip-ui-smoke",
            "--metadata-smoke-redaction-reviewed",
            "--metadata-smoke-source-contract",
            "/private/tmp/secret-metadata-source-contract.json",
            "--metadata-smoke-trino-cli",
            "/private/tmp/secret-trino-cli",
            "--metadata-smoke-server",
            "https://trino.example.test",
            "--metadata-smoke-connector-family",
            "iceberg",
            "--metadata-smoke-user",
            "secret_user",
            "--metadata-smoke-summary-json",
            "/private/tmp/secret-smoke-summary.json",
            "--metadata-smoke-summary-out",
            "/private/tmp/secret-metadata-summary.json",
        ]
    )

    gates = release_readiness.build_gate_plan(args)
    by_name = {gate.name: gate for gate in gates}

    gate = by_name["trino_metadata_cli_summary_smoke"]
    assert gate.performs_network_read
    assert gate.uses_operator_metadata_inputs
    assert not gate.requires_local_config
    assert "trino_metadata_cli_summary_smoke.py" in " ".join(gate.command)
    assert "--redaction-reviewed" in gate.command
    assert "--source-contract" in gate.command
    assert "/private/tmp/secret-metadata-source-contract.json" in gate.command
    assert "--trino-cli" in gate.command
    assert "/private/tmp/secret-trino-cli" in gate.command
    assert "--server" in gate.command
    assert "https://trino.example.test" in gate.command
    assert "--connector-family" in gate.command
    assert "iceberg" in gate.command
    assert "--user" in gate.command
    assert "secret_user" in gate.command
    assert "--summary-json" in gate.command
    assert "/private/tmp/secret-smoke-summary.json" in gate.command
    assert "--metadata-summary-out" in gate.command
    assert "/private/tmp/secret-metadata-summary.json" in gate.command


def test_trino_beta_release_readiness_summary_is_raw_free() -> None:
    args = release_readiness.build_parser().parse_args(
        [
            "--config",
            "/private/tmp/secret-trino-config.json",
            "--cluster",
            "secret_cluster",
            "--skip-pytest",
            "--skip-live-smoke",
            "--skip-ui-smoke",
            "--metadata-smoke-redaction-reviewed",
            "--metadata-smoke-source-contract",
            "/private/tmp/secret-metadata-source-contract.json",
            "--metadata-smoke-trino-cli",
            "/private/tmp/secret-trino-cli",
            "--metadata-smoke-server",
            "https://trino.example.test",
            "--metadata-smoke-connector-family",
            "hive",
            "--metadata-smoke-user",
            "secret_user",
            "--metadata-smoke-summary-json",
            "/private/tmp/secret-smoke-summary.json",
            "--metadata-smoke-summary-out",
            "/private/tmp/secret-metadata-summary.json",
        ]
    )
    gates = release_readiness.build_gate_plan(args)
    results = tuple(release_readiness.GateResult(gate.name, "ok", 0) for gate in gates)

    payload = release_readiness.summary_payload(
        gates=gates,
        results=results,
        static_only=False,
    )
    text = json.dumps(payload, sort_keys=True) + release_readiness.format_summary(payload)

    assert payload["status"] == "ok"
    assert payload["support_claim"] == "local_production"
    assert payload["surface_boundary"]["production_support"] == "local_only"
    assert payload["surface_boundary"]["sql_execution_performed"] is False
    assert payload["surface_boundary"]["query_id_output"] is False
    assert payload["surface_boundary"]["metadata_cli_smoke"] == "dev_only_optional"
    assert payload["surface_boundary"]["shared_deployment_boundary"] == "dev_only_static"
    assert payload["surface_boundary"]["shared_trino_requires_trusted_identity"] is True
    assert payload["surface_boundary"]["shared_trino_requires_front_door_review"] is True
    assert payload["surface_boundary"]["trusted_front_door_review"] == ("not_confirmed")
    assert payload["surface_boundary"]["shared_trino_raw_source_reveal"] == "blocked"
    assert payload["gates"]["uses_operator_metadata_inputs"] == ["trino_metadata_cli_summary_smoke"]
    assert "/private/tmp" not in text
    assert "secret-trino-config" not in text
    assert "secret_cluster" not in text
    assert "secret-metadata-source-contract" not in text
    assert "secret-trino-cli" not in text
    assert "trino.example.test" not in text
    assert "secret_user" not in text
    assert "secret-smoke-summary" not in text
    assert "secret-metadata-summary" not in text


def test_trino_beta_release_readiness_rejects_partial_metadata_smoke_args(
    capsys,
) -> None:
    rc = release_readiness.main(
        [
            "--skip-pytest",
            "--skip-live-smoke",
            "--skip-ui-smoke",
            "--metadata-smoke-source-contract",
            "/private/tmp/secret-metadata-source-contract.json",
        ]
    )

    captured = capsys.readouterr()
    rendered = captured.out + captured.err

    assert rc == 2
    assert captured.out == ""
    assert "metadata CLI smoke requires" in captured.err
    assert "/private/tmp" not in rendered
    assert "secret-metadata-source-contract" not in rendered


def test_trino_beta_release_readiness_rejects_static_only_metadata_smoke(
    capsys,
) -> None:
    rc = release_readiness.main(
        [
            "--static-only",
            "--metadata-smoke-redaction-reviewed",
            "--metadata-smoke-source-contract",
            "/private/tmp/secret-metadata-source-contract.json",
            "--metadata-smoke-trino-cli",
            "/private/tmp/secret-trino-cli",
            "--metadata-smoke-server",
            "https://trino.example.test",
            "--metadata-smoke-connector-family",
            "hive",
        ]
    )

    captured = capsys.readouterr()
    rendered = captured.out + captured.err

    assert rc == 2
    assert captured.out == ""
    assert "metadata CLI smoke cannot run with static-only release readiness" in (captured.err)
    assert "/private/tmp" not in rendered
    assert "trino.example.test" not in rendered


def test_trino_beta_release_readiness_rejects_metadata_output_overlap(capsys) -> None:
    rc = release_readiness.main(
        [
            "--skip-pytest",
            "--skip-live-smoke",
            "--skip-ui-smoke",
            "--metadata-smoke-redaction-reviewed",
            "--metadata-smoke-source-contract",
            "/private/tmp/secret-metadata-source-contract.json",
            "--metadata-smoke-trino-cli",
            "/private/tmp/secret-trino-cli",
            "--metadata-smoke-server",
            "https://trino.example.test",
            "--metadata-smoke-connector-family",
            "hive",
            "--metadata-smoke-summary-json",
            "/private/tmp/secret-metadata-source-contract.json",
        ]
    )

    captured = capsys.readouterr()
    rendered = captured.out + captured.err

    assert rc == 2
    assert captured.out == ""
    assert "metadata smoke summary output must not overwrite input artifacts" in captured.err
    assert "/private/tmp" not in rendered
    assert "secret-metadata-source-contract" not in rendered
    assert "trino.example.test" not in rendered


def test_trino_beta_release_readiness_runner_stops_after_failure(
    capsys,
) -> None:
    gates = (
        release_readiness.Gate("first", ("first",)),
        release_readiness.Gate("second", ("second",)),
    )
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode=1)

    results = release_readiness.run_gate_plan(
        gates,
        cwd=Path("/tmp"),
        runner=runner,
    )
    output = capsys.readouterr().out

    assert calls == [("first",)]
    assert results == (release_readiness.GateResult("first", "failed", 1),)
    assert "first=failed" in output
    assert "second=running" not in output
