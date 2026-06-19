from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import audit_trino_beta_release_readiness as release_readiness


def test_trino_beta_release_readiness_static_plan_skips_local_gates() -> None:
    args = release_readiness.build_parser().parse_args(["--static-only"])

    gates = release_readiness.build_gate_plan(args)
    names = [gate.name for gate in gates]

    assert names[:3] == [
        "trino_product_surface_boundary",
        "trino_support_gap_matrix",
        "active_docs",
    ]
    assert "trino_focused_pytest" in names
    assert "trino_web_beta_local_config_readiness" not in names
    assert "trino_web_beta_backend_live_smoke" not in names
    assert "trino_web_beta_ui_smoke" not in names
    assert not any(gate.requires_local_config for gate in gates)
    assert not any(gate.performs_network_read for gate in gates)


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
    assert by_name["trino_web_beta_local_config_readiness"].requires_local_config
    assert by_name["trino_web_beta_backend_live_smoke"].performs_network_read
    assert by_name["trino_web_beta_ui_smoke"].performs_network_read
    assert "--require-query-id" in by_name["trino_web_beta_local_config_readiness"].command
    assert "--require-recent" in by_name["trino_web_beta_local_config_readiness"].command
    assert "--selected-query-limit" in by_name["trino_web_beta_backend_live_smoke"].command
    assert "--limit" in by_name["trino_web_beta_ui_smoke"].command


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
    assert payload["surface_boundary"]["sql_execution_performed"] is False
    assert payload["surface_boundary"]["query_id_output"] is False
    assert "/private/tmp" not in text
    assert "secret-trino-config" not in text
    assert "secret_cluster" not in text


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
