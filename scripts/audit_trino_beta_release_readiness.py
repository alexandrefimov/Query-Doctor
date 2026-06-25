#!/usr/bin/env python3
"""Run the Trino Beta demo/release readiness gate bundle."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    distinct_paths_error,
    output_overlaps_inputs_error,
    write_ascii_json_artifact,
)


TRINO_BETA_RELEASE_READINESS_SUMMARY_KIND = "trino_beta_release_readiness_v1"


@dataclass(frozen=True)
class Gate:
    name: str
    command: tuple[str, ...]
    requires_local_config: bool = False
    performs_network_read: bool = False
    uses_operator_metadata_inputs: bool = False


@dataclass(frozen=True)
class GateResult:
    name: str
    status: str
    returncode: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the dev-only Trino Beta demo/release readiness bundle. The bundle "
            "orchestrates existing static audits, focused tests, optional local "
            "Trino Beta live/UI smokes, and an optional metadata CLI smoke without "
            "printing config paths, coordinator URLs, Query IDs, auth references, "
            "local paths, or raw payloads."
        )
    )
    parser.add_argument("--config", type=Path, help="Ignored local Query Doctor config.")
    parser.add_argument(
        "--trusted-front-door-reviewed",
        action="store_true",
        help=(
            "Pass the trusted front-door review confirmation to the Trino shared "
            "deployment boundary audit when the ignored local config is a "
            "shared/non-local deployment."
        ),
    )
    parser.add_argument(
        "--cluster",
        help="Optional local Trino Beta source id to pass to live and UI smokes.",
    )
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Run only static audits and focused tests; skip local config and live/UI smokes.",
    )
    parser.add_argument(
        "--skip-pytest",
        action="store_true",
        help="Skip the focused pytest suite.",
    )
    parser.add_argument(
        "--skip-live-smoke",
        action="store_true",
        help="Skip the backend live smoke.",
    )
    parser.add_argument(
        "--skip-ui-smoke",
        action="store_true",
        help="Skip the local web UI smoke.",
    )
    parser.add_argument(
        "--selected-query-limit",
        "--limit",
        dest="selected_query_limit",
        type=positive_int,
        default=1,
        help="Selected retained Trino query count for live/UI smokes. Default: 1.",
    )
    parser.add_argument(
        "--recent-window-minutes",
        "--window-minutes",
        dest="recent_window_minutes",
        type=positive_int,
        default=1_000_000,
        help="Recent lookback window for live/UI smokes. Default: 1000000.",
    )
    parser.add_argument(
        "--order",
        choices=(
            "duration-desc",
            "duration-asc",
            "recent",
            "recent-duration-desc",
            "status-priority",
        ),
        default="recent",
        help="Selection order for live/UI smokes. Default: recent.",
    )
    parser.add_argument(
        "--ui-timeout-sec",
        type=positive_float,
        default=180.0,
        help="Overall timeout for the local web UI smoke. Default: 180.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Write a raw-free machine summary JSON artifact. The path is never printed.",
    )
    parser.add_argument(
        "--metadata-smoke-source-contract",
        type=Path,
        help=(
            "Optional compact sanitized Trino metadata allowlist source-contract JSON for "
            "the dev-only metadata CLI summary smoke. The path is never printed."
        ),
    )
    parser.add_argument(
        "--metadata-smoke-trino-cli",
        type=Path,
        help=(
            "Optional operator-installed Trino CLI executable for the dev-only metadata "
            "CLI summary smoke. The path is never printed."
        ),
    )
    parser.add_argument(
        "--metadata-smoke-server",
        help=(
            "Optional HTTPS Trino coordinator URL for the dev-only metadata CLI summary "
            "smoke. The URL is never printed."
        ),
    )
    parser.add_argument(
        "--metadata-smoke-connector-family",
        choices=("hive", "iceberg"),
        help="Optional Hive or Iceberg connector-family gate for the metadata CLI smoke.",
    )
    parser.add_argument(
        "--metadata-smoke-user",
        help="Optional safe Trino CLI user token for the metadata CLI smoke. Never printed.",
    )
    parser.add_argument(
        "--metadata-smoke-redaction-reviewed",
        action="store_true",
        help=(
            "Confirm the metadata source contract and CLI target were operator-reviewed "
            "before adding the metadata CLI smoke gate."
        ),
    )
    parser.add_argument(
        "--metadata-smoke-summary-json",
        type=Path,
        help=(
            "Optional output path for the raw-free metadata CLI smoke summary JSON. "
            "The path is never printed."
        ),
    )
    parser.add_argument(
        "--metadata-smoke-summary-out",
        type=Path,
        help=(
            "Optional output path for the sanitized aggregate metadata summary produced "
            "by the metadata CLI smoke. The path is never printed."
        ),
    )
    parser.add_argument(
        "--list-gates",
        action="store_true",
        help="Print the raw-free gate names without executing them.",
    )
    return parser


def build_gate_plan(args: argparse.Namespace, *, root: Path = ROOT) -> tuple[Gate, ...]:
    py = sys.executable
    gates: list[Gate] = [
        Gate(
            "trino_shared_deployment_boundary",
            tuple(
                item
                for item in (
                    py,
                    str(root / "scripts" / "audit_trino_shared_deployment_boundary.py"),
                    "--config" if args.config is not None else None,
                    str(args.config) if args.config is not None else None,
                    "--trusted-front-door-reviewed" if args.trusted_front_door_reviewed else None,
                )
                if item is not None
            ),
            requires_local_config=args.config is not None,
        ),
        Gate(
            "trino_product_surface_boundary",
            (
                py,
                str(root / "scripts" / "audit_trino_product_surface_boundary.py"),
                "--registry-only",
            ),
        ),
        Gate(
            "trino_support_gap_matrix",
            (py, str(root / "scripts" / "audit_trino_support_gap_matrix.py")),
        ),
        Gate(
            "active_docs",
            (py, str(root / "scripts" / "check_active_docs.py")),
        ),
    ]
    if not args.skip_pytest:
        gates.append(
            Gate(
                "trino_focused_pytest",
                (
                    py,
                    "-m",
                    "pytest",
                    "-q",
                    *trino_release_pytest_paths(root),
                ),
            )
        )
    if args.static_only:
        return tuple(gates)

    if metadata_smoke_requested(args):
        metadata_command = [
            py,
            str(root / "scripts" / "trino_metadata_cli_summary_smoke.py"),
            "--redaction-reviewed",
            "--source-contract",
            str(args.metadata_smoke_source_contract),
            "--trino-cli",
            str(args.metadata_smoke_trino_cli),
            "--server",
            args.metadata_smoke_server,
            "--connector-family",
            args.metadata_smoke_connector_family,
        ]
        if args.metadata_smoke_user:
            metadata_command.extend(("--user", args.metadata_smoke_user))
        if args.metadata_smoke_summary_json is not None:
            metadata_command.extend(("--summary-json", str(args.metadata_smoke_summary_json)))
        if args.metadata_smoke_summary_out is not None:
            metadata_command.extend(
                ("--metadata-summary-out", str(args.metadata_smoke_summary_out))
            )
        gates.append(
            Gate(
                "trino_metadata_cli_summary_smoke",
                tuple(metadata_command),
                performs_network_read=True,
                uses_operator_metadata_inputs=True,
            )
        )

    readiness_command = [
        py,
        str(root / "scripts" / "audit_trino_web_beta_readiness.py"),
        "--require-query-id",
        "--require-recent",
    ]
    if args.config is not None:
        readiness_command.extend(("--config", str(args.config)))
    gates.append(
        Gate(
            "trino_web_beta_local_config_readiness",
            tuple(readiness_command),
            requires_local_config=True,
        )
    )

    if not args.skip_live_smoke:
        live_command = [
            py,
            str(root / "scripts" / "audit_trino_web_beta_live_smoke.py"),
            "--selected-query-limit",
            str(args.selected_query_limit),
            "--recent-window-minutes",
            str(args.recent_window_minutes),
            "--order",
            args.order,
        ]
        if args.config is not None:
            live_command.extend(("--config", str(args.config)))
        if args.cluster:
            live_command.extend(("--cluster-key", args.cluster))
        gates.append(
            Gate(
                "trino_web_beta_backend_live_smoke",
                tuple(live_command),
                requires_local_config=True,
                performs_network_read=True,
            )
        )

    if not args.skip_ui_smoke:
        ui_command = [
            str(root / "scripts" / "query-doctor-web-trino-beta-smoke"),
            "--limit",
            str(args.selected_query_limit),
            "--window-minutes",
            str(args.recent_window_minutes),
            "--order",
            args.order,
            "--timeout-sec",
            str(args.ui_timeout_sec),
        ]
        if args.config is not None:
            ui_command.extend(("--config", str(args.config)))
        if args.cluster:
            ui_command.extend(("--cluster", args.cluster))
        gates.append(
            Gate(
                "trino_web_beta_ui_smoke",
                tuple(ui_command),
                requires_local_config=True,
                performs_network_read=True,
            )
        )
    return tuple(gates)


def trino_release_pytest_paths(root: Path = ROOT) -> tuple[str, ...]:
    paths = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "tests").glob("*trino*.py")
        if path.name.startswith("test_")
    )
    paths.extend(
        (
            "tests/test_engine_capabilities.py",
            "tests/test_engine_redaction_note.py",
            "tests/test_engine_intake_primitives.py",
            "tests/test_manifest_references.py",
            "tests/test_web_ui_help.py",
            "tests/test_web_ui_home.py",
        )
    )
    return tuple(dict.fromkeys(paths))


def run_gate_plan(
    gates: tuple[Gate, ...],
    *,
    cwd: Path = ROOT,
    runner: Any = subprocess.run,
) -> tuple[GateResult, ...]:
    results: list[GateResult] = []
    for gate in gates:
        print(f"[trino-beta-release-readiness] {gate.name}=running", flush=True)
        completed = runner(gate.command, cwd=cwd)
        returncode = int(getattr(completed, "returncode", 1))
        status = "ok" if returncode == 0 else "failed"
        print(f"[trino-beta-release-readiness] {gate.name}={status}", flush=True)
        results.append(GateResult(gate.name, status, returncode))
        if returncode != 0:
            break
    return tuple(results)


def summary_payload(
    *,
    gates: tuple[Gate, ...],
    results: tuple[GateResult, ...],
    static_only: bool,
) -> dict[str, Any]:
    failed = [result for result in results if result.status != "ok"]
    return {
        "summary_kind": TRINO_BETA_RELEASE_READINESS_SUMMARY_KIND,
        "status": "ok" if not failed and len(results) == len(gates) else "failed",
        "support_claim": "local_production",
        "mode": "static_only" if static_only else "local_demo_release",
        "gates": {
            "planned": [gate.name for gate in gates],
            "completed": [result.name for result in results],
            "failed": {result.name: result.returncode for result in failed},
            "requires_local_config": [gate.name for gate in gates if gate.requires_local_config],
            "performs_network_read": [gate.name for gate in gates if gate.performs_network_read],
            "uses_operator_metadata_inputs": [
                gate.name for gate in gates if gate.uses_operator_metadata_inputs
            ],
        },
        "surface_boundary": {
            "production_support": "local_only",
            "sql_execution_performed": False,
            "raw_payload_output": False,
            "query_id_output": False,
            "coordinator_url_output": False,
            "auth_reference_output": False,
            "local_path_output": False,
            "details_python_report_output": "materialized_details_only",
            "optimizer_guidance_output": "materialized_details_only",
            "llm_report_output": "not_wired",
            "optimizer_behavior": "guidance_only",
            "metadata_cli_smoke": "dev_only_optional",
            "metadata_collection": "not_wired",
            "running_scan": "not_wired",
            "shared_deployment_boundary": "dev_only_static",
            "shared_trino_requires_trusted_identity": True,
            "shared_trino_requires_front_door_review": True,
            "trusted_front_door_review": front_door_review_status(gates),
            "shared_trino_raw_source_reveal": "blocked",
        },
    }


def format_summary(payload: dict[str, Any]) -> str:
    gates = payload["gates"]
    failed = gates["failed"]
    failed_text = ", ".join(f"{name}={code}" for name, code in failed.items())
    if not failed_text:
        failed_text = "none"
    return "\n".join(
        (
            f"Trino beta release readiness: {payload['status']}",
            f"mode={payload['mode']}",
            f"gates_planned={len(gates['planned'])}",
            f"gates_completed={len(gates['completed'])}",
            f"local_config_gates={len(gates['requires_local_config'])}",
            f"network_read_gates={len(gates['performs_network_read'])}",
            f"metadata_input_gates={len(gates['uses_operator_metadata_inputs'])}",
            "sql_execution_performed=no",
            "query_id_output=no",
            "coordinator_url_output=no",
            "auth_reference_output=no",
            "local_path_output=no",
            f"failed_gates: {failed_text}",
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    metadata_error = metadata_smoke_config_error(args)
    if metadata_error:
        print(f"Trino beta release readiness: rejected: {metadata_error}", file=sys.stderr)
        return 2
    gates = build_gate_plan(args)
    if args.list_gates:
        for gate in gates:
            print(gate.name)
        return 0

    overlap_error = output_overlap_error(args)
    if overlap_error:
        print(f"Trino beta release readiness: rejected: {overlap_error}", file=sys.stderr)
        return 2

    results = run_gate_plan(gates)
    payload = summary_payload(gates=gates, results=results, static_only=args.static_only)
    if args.summary_json is not None:
        write_ascii_json_artifact(args.summary_json, payload)
    print(format_summary(payload))
    return 0 if payload["status"] == "ok" else 1


def metadata_smoke_requested(args: argparse.Namespace) -> bool:
    return any(
        (
            args.metadata_smoke_source_contract is not None,
            args.metadata_smoke_trino_cli is not None,
            bool(args.metadata_smoke_server),
            bool(args.metadata_smoke_connector_family),
            bool(args.metadata_smoke_user),
            args.metadata_smoke_redaction_reviewed,
            args.metadata_smoke_summary_json is not None,
            args.metadata_smoke_summary_out is not None,
        )
    )


def metadata_smoke_config_error(args: argparse.Namespace) -> str | None:
    if not metadata_smoke_requested(args):
        return None
    if args.static_only:
        return "metadata CLI smoke cannot run with static-only release readiness"
    missing = [
        label
        for label, value in (
            ("source contract", args.metadata_smoke_source_contract),
            ("Trino CLI", args.metadata_smoke_trino_cli),
            ("server", args.metadata_smoke_server),
            ("connector family", args.metadata_smoke_connector_family),
        )
        if value is None or value == ""
    ]
    if missing:
        return (
            "metadata CLI smoke requires source contract, Trino CLI, server, and connector family"
        )
    if not args.metadata_smoke_redaction_reviewed:
        return "metadata CLI smoke requires redaction review confirmation"
    return None


def output_overlap_error(args: argparse.Namespace) -> str | None:
    protected_inputs = (
        args.config,
        args.metadata_smoke_source_contract,
        args.metadata_smoke_trino_cli,
    )
    checks = (
        (args.summary_json, "summary output must not overwrite input artifacts"),
        (
            args.metadata_smoke_summary_json,
            "metadata smoke summary output must not overwrite input artifacts",
        ),
        (
            args.metadata_smoke_summary_out,
            "metadata summary output must not overwrite input artifacts",
        ),
    )
    for output, message in checks:
        overlap_error = output_overlaps_inputs_error(
            output,
            protected_inputs,
            message=message,
        )
        if overlap_error is not None:
            return overlap_error
    return distinct_paths_error(
        (args.summary_json, args.metadata_smoke_summary_json, args.metadata_smoke_summary_out),
        message="release readiness summary outputs must be distinct",
    )


def front_door_review_status(gates: tuple[Gate, ...]) -> str:
    for gate in gates:
        if gate.name == "trino_shared_deployment_boundary":
            if "--trusted-front-door-reviewed" in gate.command:
                return "confirmed"
            if gate.requires_local_config:
                return "not_confirmed"
            return "not_required_for_static_only"
    return "not_required_for_static_only"


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
