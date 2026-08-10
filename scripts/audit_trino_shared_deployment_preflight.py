#!/usr/bin/env python3
"""Run a dev-only Trino shared deployment hardening preflight."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    output_overlaps_inputs_error,
    write_ascii_json_artifact,
)


TRINO_SHARED_DEPLOYMENT_PREFLIGHT_SUMMARY_KIND = "trino_shared_deployment_preflight_v1"


@dataclass(frozen=True)
class PreflightGate:
    name: str
    command: tuple[str, ...]
    requires_local_config: bool = False
    requires_front_door_review_summary: bool = False
    performs_network_read: bool = False


@dataclass(frozen=True)
class PreflightGateResult:
    name: str
    status: str
    returncode: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the dev-only Trino shared/internal deployment preflight. The "
            "preflight wraps static support-boundary gates and optionally checks an "
            "ignored local web config through the shared deployment boundary audit. "
            "It captures child stdout/stderr and prints only raw-free gate names, "
            "counts, and issue categories; it never prints config paths, header "
            "names or values, users, Query IDs, coordinator URLs, auth references, "
            "source-contract paths, CLI output, metadata values, or raw payloads."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional ignored local Query Doctor web config. The path is never printed.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Optional raw-free machine summary JSON. The path is never printed.",
    )
    parser.add_argument(
        "--front-door-review-summary",
        type=Path,
        help=(
            "Optional raw-free live front-door review summary. The path is never "
            "printed. When supplied, the preflight validates it through the owner_raw "
            "live front-door review audit and passes the trusted-front-door review "
            "confirmation to the Trino shared boundary audit."
        ),
    )
    parser.add_argument(
        "--trusted-front-door-reviewed",
        action="store_true",
        help=(
            "Pass the trusted front-door review confirmation to the shared boundary "
            "audit. Use only after the operator has verified header stripping and "
            "single normalized viewer identity injection at the front door."
        ),
    )
    parser.add_argument(
        "--list-gates",
        action="store_true",
        help="Print the raw-free preflight gate names without executing them.",
    )
    return parser


def build_gate_plan(args: argparse.Namespace, *, root: Path = ROOT) -> tuple[PreflightGate, ...]:
    py = sys.executable
    gates: list[PreflightGate] = []
    if args.front_door_review_summary is not None:
        gates.append(
            PreflightGate(
                "owner_raw_live_front_door_review",
                (
                    py,
                    str(root / "scripts" / "audit_owner_raw_live_front_door_review.py"),
                    "--review-json",
                    str(args.front_door_review_summary),
                    "--require-trino-shared-hardening",
                ),
                requires_front_door_review_summary=True,
            )
        )
    shared_boundary_command = [
        py,
        str(root / "scripts" / "audit_trino_shared_deployment_boundary.py"),
    ]
    if args.config is not None:
        shared_boundary_command.extend(("--config", str(args.config)))
    if args.trusted_front_door_reviewed or args.front_door_review_summary is not None:
        shared_boundary_command.append("--trusted-front-door-reviewed")
    gates.extend(
        (
            PreflightGate(
                "trino_shared_deployment_boundary",
                tuple(shared_boundary_command),
                requires_local_config=args.config is not None,
            ),
            PreflightGate(
                "trino_product_surface_boundary",
                (
                    py,
                    str(root / "scripts" / "audit_trino_product_surface_boundary.py"),
                    "--registry-only",
                ),
            ),
            PreflightGate(
                "trino_support_gap_matrix",
                (py, str(root / "scripts" / "audit_trino_support_gap_matrix.py")),
            ),
            PreflightGate(
                "active_docs",
                (py, str(root / "scripts" / "check_active_docs.py")),
            ),
        )
    )
    return tuple(gates)


def run_gate_plan(
    gates: tuple[PreflightGate, ...],
    *,
    cwd: Path = ROOT,
    runner: Any = subprocess.run,
) -> tuple[PreflightGateResult, ...]:
    results: list[PreflightGateResult] = []
    for gate in gates:
        print(f"[trino-shared-deployment-preflight] {gate.name}=running", flush=True)
        completed = runner(
            gate.command,
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        returncode = int(getattr(completed, "returncode", 1))
        status = "ok" if returncode == 0 else "failed"
        print(f"[trino-shared-deployment-preflight] {gate.name}={status}", flush=True)
        results.append(PreflightGateResult(gate.name, status, returncode))
        if returncode != 0:
            break
    return tuple(results)


def summary_payload(
    *,
    gates: tuple[PreflightGate, ...],
    results: tuple[PreflightGateResult, ...],
) -> dict[str, Any]:
    failed = [result for result in results if result.status != "ok"]
    return {
        "summary_kind": TRINO_SHARED_DEPLOYMENT_PREFLIGHT_SUMMARY_KIND,
        "status": "ok" if not failed and len(results) == len(gates) else "failed",
        "support_claim": "no_broader_shared_trino_support",
        "mode": "shared_deployment_static_preflight",
        "gates": {
            "planned": [gate.name for gate in gates],
            "completed": [result.name for result in results],
            "failed": {result.name: result.returncode for result in failed},
            "requires_local_config": [gate.name for gate in gates if gate.requires_local_config],
            "requires_front_door_review_summary": [
                gate.name for gate in gates if gate.requires_front_door_review_summary
            ],
            "performs_network_read": [gate.name for gate in gates if gate.performs_network_read],
        },
        "surface_boundary": {
            "production_support": "local_only",
            "shared_deployment_boundary": "dev_only_static",
            "shared_trino_requires_trusted_identity": True,
            "shared_trino_requires_front_door_review": True,
            "trusted_front_door_review": front_door_review_status(gates),
            "shared_trino_raw_source_reveal": "blocked",
            "details_python_report_output": "materialized_details_only",
            "optimizer_guidance_output": "materialized_details_only",
            "metadata_cli_smoke": "dev_only_optional",
            "metadata_collection": "not_wired",
            "running_scan": "not_wired",
            "query_history_crawling": "not_wired",
            "llm_report_output": "not_wired",
            "query_optimizer_jobs": "not_wired",
            "generated_sql": "not_wired",
            "sql_execution_performed": False,
            "raw_payload_output": False,
            "query_id_output": False,
            "coordinator_url_output": False,
            "auth_reference_output": False,
            "local_path_output": False,
            "header_output": False,
            "user_output": False,
            "metadata_value_output": False,
            "cli_output": False,
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
            f"Trino shared deployment preflight: {payload['status']}",
            f"mode={payload['mode']}",
            f"gates_planned={len(gates['planned'])}",
            f"gates_completed={len(gates['completed'])}",
            f"local_config_gates={len(gates['requires_local_config'])}",
            f"front_door_review_summary_gates={len(gates['requires_front_door_review_summary'])}",
            f"network_read_gates={len(gates['performs_network_read'])}",
            "trusted_front_door_identity=required_for_shared_trino",
            f"trusted_front_door_review={payload['surface_boundary']['trusted_front_door_review']}",
            "raw_source_reveal=blocked_for_shared_trino",
            "details_python_report_output=materialized_details_only",
            "metadata_cli_smoke=dev_only_optional",
            "metadata_collection=not_wired",
            "running_scan=not_wired",
            "query_history_crawling=not_wired",
            "llm_reports=not_wired",
            "query_optimizer_jobs=not_wired",
            "generated_sql=not_wired",
            "sql_execution_performed=no",
            "query_id_output=no",
            "coordinator_url_output=no",
            "auth_reference_output=no",
            "local_path_output=no",
            f"failed_gates: {failed_text}",
        )
    )


def output_overlap_error(args: argparse.Namespace) -> str | None:
    return output_overlaps_inputs_error(
        args.summary_json,
        (args.config, args.front_door_review_summary),
        message="summary output must not overwrite input artifacts",
    )


def front_door_review_status(gates: tuple[PreflightGate, ...]) -> str:
    if any(gate.name == "owner_raw_live_front_door_review" for gate in gates):
        return "confirmed_by_review_summary"
    for gate in gates:
        if gate.name == "trino_shared_deployment_boundary":
            if "--trusted-front-door-reviewed" in gate.command:
                return "confirmed"
            if gate.requires_local_config:
                return "not_confirmed"
            return "not_required_for_static_only"
    return "not_required_for_static_only"


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    gates = build_gate_plan(args)
    if args.list_gates:
        for gate in gates:
            print(gate.name)
        return 0

    overlap_error = output_overlap_error(args)
    if overlap_error:
        print(f"Trino shared deployment preflight: rejected: {overlap_error}", file=sys.stderr)
        return 2

    results = run_gate_plan(gates)
    payload = summary_payload(gates=gates, results=results)
    if args.summary_json is not None:
        try:
            write_ascii_json_artifact(args.summary_json, payload)
        except OSError:
            print(
                "Trino shared deployment preflight: rejected: summary JSON could not be written",
                file=sys.stderr,
            )
            return 2
    print(format_summary(payload))
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
