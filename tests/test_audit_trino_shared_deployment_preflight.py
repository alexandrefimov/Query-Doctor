from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import audit_trino_shared_deployment_preflight as preflight


def test_preflight_plan_wraps_static_gates_and_optional_config() -> None:
    args = preflight.build_parser().parse_args(
        [
            "--config",
            "/private/tmp/secret-trino-config.json",
            "--trusted-front-door-reviewed",
        ]
    )

    gates = preflight.build_gate_plan(args)
    by_name = {gate.name: gate for gate in gates}

    assert list(by_name) == [
        "trino_shared_deployment_boundary",
        "trino_product_surface_boundary",
        "trino_support_gap_matrix",
        "active_docs",
    ]
    shared_gate = by_name["trino_shared_deployment_boundary"]
    assert shared_gate.requires_local_config
    assert not any(gate.performs_network_read for gate in gates)
    assert "audit_trino_shared_deployment_boundary.py" in " ".join(shared_gate.command)
    assert "--config" in shared_gate.command
    assert "/private/tmp/secret-trino-config.json" in shared_gate.command
    assert "--trusted-front-door-reviewed" in shared_gate.command
    assert "--registry-only" in by_name["trino_product_surface_boundary"].command


def test_preflight_summary_is_raw_free() -> None:
    args = preflight.build_parser().parse_args(
        ["--config", "/private/tmp/secret-trino-config.json"]
    )
    gates = preflight.build_gate_plan(args)
    results = tuple(preflight.PreflightGateResult(gate.name, "ok", 0) for gate in gates)

    payload = preflight.summary_payload(gates=gates, results=results)
    text = json.dumps(payload, sort_keys=True) + preflight.format_summary(payload)

    assert payload["summary_kind"] == "trino_shared_deployment_preflight_v1"
    assert payload["status"] == "ok"
    assert payload["support_claim"] == "no_broader_shared_trino_support"
    assert payload["surface_boundary"]["production_support"] == "local_only"
    assert payload["surface_boundary"]["shared_trino_requires_trusted_identity"] is True
    assert payload["surface_boundary"]["shared_trino_requires_front_door_review"] is True
    assert payload["surface_boundary"]["trusted_front_door_review"] == "not_confirmed"
    assert payload["surface_boundary"]["shared_trino_raw_source_reveal"] == "blocked"
    assert payload["surface_boundary"]["metadata_collection"] == "not_wired"
    assert payload["surface_boundary"]["query_optimizer_jobs"] == "not_wired"
    assert payload["surface_boundary"]["sql_execution_performed"] is False
    assert payload["gates"]["requires_local_config"] == ["trino_shared_deployment_boundary"]
    assert payload["gates"]["performs_network_read"] == []
    assert_protected_fragments_hidden(text)


def test_preflight_summary_records_front_door_review_confirmation() -> None:
    args = preflight.build_parser().parse_args(
        [
            "--config",
            "/private/tmp/secret-trino-config.json",
            "--trusted-front-door-reviewed",
        ]
    )
    gates = preflight.build_gate_plan(args)
    results = tuple(preflight.PreflightGateResult(gate.name, "ok", 0) for gate in gates)

    payload = preflight.summary_payload(gates=gates, results=results)
    text = json.dumps(payload, sort_keys=True) + preflight.format_summary(payload)

    assert payload["surface_boundary"]["trusted_front_door_review"] == "confirmed"
    assert "front_door_review=confirmed" in text
    assert_protected_fragments_hidden(text)


def test_preflight_accepts_structured_front_door_review_summary() -> None:
    args = preflight.build_parser().parse_args(
        [
            "--config",
            "/private/tmp/secret-trino-config.json",
            "--front-door-review-summary",
            "/private/tmp/secret-front-door-review.json",
        ]
    )
    gates = preflight.build_gate_plan(args)
    by_name = {gate.name: gate for gate in gates}
    results = tuple(preflight.PreflightGateResult(gate.name, "ok", 0) for gate in gates)

    payload = preflight.summary_payload(gates=gates, results=results)
    text = json.dumps(payload, sort_keys=True) + preflight.format_summary(payload)

    assert list(by_name) == [
        "owner_raw_live_front_door_review",
        "trino_shared_deployment_boundary",
        "trino_product_surface_boundary",
        "trino_support_gap_matrix",
        "active_docs",
    ]
    review_gate = by_name["owner_raw_live_front_door_review"]
    shared_gate = by_name["trino_shared_deployment_boundary"]
    assert review_gate.requires_front_door_review_summary is True
    assert "--require-trino-shared-hardening" in review_gate.command
    assert "--trusted-front-door-reviewed" in shared_gate.command
    assert payload["surface_boundary"]["trusted_front_door_review"] == (
        "confirmed_by_review_summary"
    )
    assert payload["gates"]["requires_front_door_review_summary"] == [
        "owner_raw_live_front_door_review"
    ]
    assert "front_door_review_summary_gates=1" in text
    assert_protected_fragments_hidden(text)


def test_preflight_runner_captures_child_output_and_stops_after_failure(capsys) -> None:
    gates = (
        preflight.PreflightGate("first", ("first",)),
        preflight.PreflightGate("second", ("second",)),
    )
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            returncode=1,
            stdout="secret stdout with https://trino.example.test and X-Secret-Viewer",
            stderr="secret stderr with /private/tmp/secret-config.json",
        )

    results = preflight.run_gate_plan(gates, cwd=Path("/tmp"), runner=runner)
    rendered = capsys.readouterr().out

    assert calls == [("first",)]
    assert results == (preflight.PreflightGateResult("first", "failed", 1),)
    assert "first=failed" in rendered
    assert "second=running" not in rendered
    assert_protected_fragments_hidden(rendered)


def test_preflight_rejects_summary_overlap_without_path_echo(capsys) -> None:
    rc = preflight.main(
        [
            "--config",
            "/private/tmp/secret-trino-config.json",
            "--summary-json",
            "/private/tmp/secret-trino-config.json",
        ]
    )

    captured = capsys.readouterr()
    rendered = captured.out + captured.err

    assert rc == 2
    assert captured.out == ""
    assert "summary output must not overwrite input artifacts" in captured.err
    assert_protected_fragments_hidden(rendered)


def test_preflight_main_writes_raw_free_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    summary_path = tmp_path / "secret-summary.json"

    def fake_run_gate_plan(
        gates: tuple[preflight.PreflightGate, ...],
        **_: object,
    ) -> tuple[preflight.PreflightGateResult, ...]:
        return tuple(preflight.PreflightGateResult(gate.name, "ok", 0) for gate in gates)

    monkeypatch.setattr(preflight, "run_gate_plan", fake_run_gate_plan)

    rc = preflight.main(
        [
            "--config",
            "/private/tmp/secret-trino-config.json",
            "--summary-json",
            str(summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rendered = captured.out + captured.err + json.dumps(summary, sort_keys=True)

    assert rc == 0
    assert summary["summary_kind"] == "trino_shared_deployment_preflight_v1"
    assert summary["status"] == "ok"
    assert "Trino shared deployment preflight: ok" in captured.out
    assert "failed_gates: none" in captured.out
    assert_protected_fragments_hidden(rendered, tmp_path=tmp_path)


def assert_protected_fragments_hidden(text: str, *, tmp_path: Path | None = None) -> None:
    fragments = [
        "/private/tmp",
        "secret-trino-config",
        "secret-front-door-review",
        "secret-summary",
        "trino.example.test",
        "X-Secret-Viewer",
        "secret_analyst",
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    ]
    if tmp_path is not None:
        fragments.append(str(tmp_path))
    for fragment in fragments:
        assert fragment not in text
