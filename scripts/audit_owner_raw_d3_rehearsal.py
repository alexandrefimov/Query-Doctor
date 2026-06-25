#!/usr/bin/env python3
"""Run the raw-free owner_raw D3 rehearsal gates in one command."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    output_overlaps_inputs_error,
    write_ascii_json_artifact,
)
from scripts import audit_owner_raw_d3_readiness as readiness  # noqa: E402
from scripts import dev_sso_keycloak_smoke as dev_sso  # noqa: E402


SUMMARY_KIND = "owner_raw_d3_rehearsal_v1"
SAFE_REVIEW_PROFILES = frozenset({"owner_raw_d3", "trino_shared_hardening", "unknown"})
SAFE_STATUS_VALUES = frozenset(
    {
        "configured",
        "disabled",
        "enabled",
        "failed",
        "local",
        "missing",
        "missing_or_invalid",
        "nonlocal",
        "not_checked",
        "ok",
        "rejected",
        "unknown",
    }
)


@dataclass(frozen=True)
class RehearsalGateOutcome:
    name: str
    status: str
    issue_counts: Counter[str] = field(default_factory=Counter)
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok" and not self.issue_counts


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the raw-free owner_raw D3 rehearsal sequence: dev SSO smoke, "
            "live front-door review summary audit, staging config preflight, and "
            "aggregate D3 readiness. The script never prints config paths, review "
            "paths, URLs, usernames, login secrets, header names or values, query "
            "ids, auth material, or raw source."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Ignored local Query Doctor web config to audit. The path is never printed.",
    )
    parser.add_argument(
        "--front-door-review-json",
        type=Path,
        help="Raw-free live front-door review summary. The path is never printed.",
    )
    parser.add_argument(
        "--host",
        help="Optional web bind host override matching the planned startup command.",
    )
    parser.add_argument(
        "--allow-nonlocal-web-bind",
        action="store_true",
        help="Confirm the planned web startup includes --allow-nonlocal-web-bind.",
    )
    parser.add_argument(
        "--disable-owner-raw-source",
        action="store_true",
        help="Confirm the planned web startup includes --disable-owner-raw-source.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Optional raw-free machine summary JSON. The path is never printed.",
    )
    parser.add_argument("--limit", type=positive_int, default=20, help="Maximum issues to print.")
    parser.add_argument("--dev-sso-proxy-url", default=dev_sso.DEFAULT_PROXY_URL)
    parser.add_argument(
        "--dev-sso-keycloak-discovery-url",
        default=dev_sso.DEFAULT_KEYCLOAK_DISCOVERY_URL,
    )
    parser.add_argument("--dev-sso-upstream-host", default=dev_sso.DEFAULT_UPSTREAM_HOST)
    parser.add_argument("--dev-sso-upstream-port", type=int, default=dev_sso.DEFAULT_UPSTREAM_PORT)
    parser.add_argument("--dev-sso-username", default=dev_sso.DEFAULT_USERNAME)
    parser.add_argument("--dev-sso-password", default=dev_sso.DEFAULT_PASSWORD)
    parser.add_argument("--dev-sso-timeout-sec", type=float, default=10.0)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    overlap_error = output_overlaps_inputs_error(
        args.summary_json,
        tuple(path for path in (args.config, args.front_door_review_json) if path is not None),
        message="summary output must not overwrite input artifacts",
    )
    if overlap_error:
        print(f"Owner raw D3 rehearsal: rejected: {overlap_error}", file=sys.stderr)
        return 2

    staging = readiness.staging_gate(args)
    review = readiness.front_door_review_gate(args.front_door_review_json)
    gates = (
        dev_sso_smoke_gate(args),
        convert_readiness_gate(review),
        convert_readiness_gate(staging),
        d3_readiness_gate(staging=staging, review=review),
    )
    payload = summary_payload(gates)
    if args.summary_json is not None:
        try:
            write_ascii_json_artifact(args.summary_json, payload)
        except OSError:
            print(
                "Owner raw D3 rehearsal: rejected: summary JSON could not be written",
                file=sys.stderr,
            )
            return 2

    print(format_summary(payload))
    print_issues(payload, limit=args.limit)
    return 0 if payload["status"] == "ok" else 1


def dev_sso_smoke_gate(args: argparse.Namespace) -> RehearsalGateOutcome:
    config = dev_sso.SmokeConfig(
        proxy_url=args.dev_sso_proxy_url,
        keycloak_discovery_url=args.dev_sso_keycloak_discovery_url,
        upstream_host=args.dev_sso_upstream_host,
        upstream_port=args.dev_sso_upstream_port,
        username=args.dev_sso_username,
        password=args.dev_sso_password,
        timeout_sec=args.dev_sso_timeout_sec,
    )
    try:
        checks = tuple(dev_sso.run_checks(config))
    except Exception:  # noqa: BLE001 - output stays a safe category only.
        return RehearsalGateOutcome(
            "dev_sso_keycloak_smoke",
            "rejected",
            Counter({"dev_sso.smoke_rejected": 1}),
            {"check_count": 0, "raw_values_output": False},
        )
    issues: Counter[str] = Counter()
    for check in checks:
        if not check.passed:
            issues[f"dev_sso.{safe_issue_token(check.name)}_failed"] += 1
    return RehearsalGateOutcome(
        "dev_sso_keycloak_smoke",
        "ok" if not issues else "failed",
        issues,
        {
            "check_count": len(checks),
            "raw_values_output": False,
        },
    )


def convert_readiness_gate(gate: readiness.GateOutcome) -> RehearsalGateOutcome:
    return RehearsalGateOutcome(
        gate.name,
        gate.status,
        Counter(gate.issue_counts),
        safe_gate_metadata(gate),
    )


def d3_readiness_gate(
    *,
    staging: readiness.GateOutcome,
    review: readiness.GateOutcome,
) -> RehearsalGateOutcome:
    payload = readiness.summary_payload(staging=staging, review=review)
    status = str(payload["status"])
    readiness_payload = payload["readiness"]
    assert isinstance(readiness_payload, Mapping)
    issues: Counter[str] = Counter()
    if status != "ok":
        issues["d3_readiness_not_ready"] += 1
    return RehearsalGateOutcome(
        "d3_readiness",
        status,
        issues,
        {
            "source_enable_ready": bool(readiness_payload["source_enable_ready"]),
            "staging_config_preflight": safe_status_value(
                readiness_payload["staging_config_preflight"]
            ),
            "front_door_review": safe_status_value(readiness_payload["front_door_review"]),
            "current_config_owner_raw_source": safe_status_value(
                readiness_payload["current_config_owner_raw_source"]
            ),
            "native_auth_added": False,
            "live_review_required": True,
        },
    )


def summary_payload(gates: tuple[RehearsalGateOutcome, ...]) -> dict[str, Any]:
    gate_payloads = {gate.name: gate_payload(gate) for gate in gates}
    failed_gates = tuple(gate.name for gate in gates if not gate.ok)
    issue_counts: Counter[str] = Counter()
    for gate in gates:
        issue_counts.update(gate.issue_counts)
    d3_metadata = gate_payloads["d3_readiness"]["metadata"]
    assert isinstance(d3_metadata, Mapping)
    status = "ok" if not failed_gates else "failed"
    return {
        "summary_kind": SUMMARY_KIND,
        "status": status,
        "readiness": {
            "rehearsal_complete": status == "ok",
            "source_enable_ready": status == "ok" and bool(d3_metadata["source_enable_ready"]),
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
        "gates": gate_payloads,
        "issues": {
            "failed_gates": list(failed_gates),
            "counts": counter_payload(issue_counts),
        },
    }


def gate_payload(gate: RehearsalGateOutcome) -> dict[str, object]:
    return {
        "status": gate.status,
        "issue_counts": counter_payload(gate.issue_counts),
        "metadata": gate.metadata,
    }


def safe_gate_metadata(gate: readiness.GateOutcome) -> dict[str, object]:
    if gate.name == "staging_config_preflight":
        return {
            "source_count": safe_int(gate.metadata.get("source_count")),
            "owner_raw_source_count": safe_int(gate.metadata.get("owner_raw_source_count")),
            "nonlocal_owner_raw_source_count": safe_int(
                gate.metadata.get("nonlocal_owner_raw_source_count")
            ),
            "viewer_identity_header": safe_status_value(
                gate.metadata.get("viewer_identity_header")
            ),
            "owner_raw_source": safe_status_value(gate.metadata.get("owner_raw_source")),
            "privacy_safe_count": safe_int(gate.metadata.get("privacy_safe_count")),
            "redaction_safe_count": safe_int(gate.metadata.get("redaction_safe_count")),
        }
    if gate.name == "live_front_door_review":
        return {
            "review_profile": safe_review_profile(gate.metadata.get("review_profile")),
            "checked_required_fields": safe_int(gate.metadata.get("checked_required_fields")),
        }
    return {}


def format_summary(payload: Mapping[str, Any]) -> str:
    readiness_payload = payload["readiness"]
    gates = payload["gates"]
    assert isinstance(readiness_payload, Mapping)
    assert isinstance(gates, Mapping)
    d3_gate = gates["d3_readiness"]
    assert isinstance(d3_gate, Mapping)
    d3_metadata = d3_gate["metadata"]
    assert isinstance(d3_metadata, Mapping)
    return "\n".join(
        (
            f"Owner raw D3 rehearsal: {payload['status']}",
            f"rehearsal_complete={'yes' if readiness_payload['rehearsal_complete'] else 'no'}",
            f"source_enable_ready={'yes' if readiness_payload['source_enable_ready'] else 'no'}",
            f"dev_sso_keycloak_smoke={gate_status(gates, 'dev_sso_keycloak_smoke')}",
            f"live_front_door_review={gate_status(gates, 'live_front_door_review')}",
            f"staging_config_preflight={gate_status(gates, 'staging_config_preflight')}",
            f"d3_readiness={gate_status(gates, 'd3_readiness')}",
            (f"current_config_owner_raw_source={d3_metadata['current_config_owner_raw_source']}"),
            "native_auth_added=no",
            "live_review_required=yes",
            "raw_values_output=no",
            "paths=not_printed",
            "header_names=not_printed",
            "header_values=not_printed",
            "users=not_printed",
            "urls=not_printed",
            "query_ids=not_printed",
            "auth_material=not_printed",
            "raw_source=not_printed",
        )
    )


def print_issues(payload: Mapping[str, Any], *, limit: int) -> None:
    issues = payload["issues"]
    assert isinstance(issues, Mapping)
    counts = issues["counts"]
    failed_gates = issues["failed_gates"]
    assert isinstance(counts, Mapping)
    assert isinstance(failed_gates, list)
    if not counts:
        print("Failed gates: none")
        print("Issues: none")
        return
    print("Failed gates:")
    for gate_name in failed_gates[:limit]:
        print(f"- {gate_name}")
    if len(failed_gates) > limit:
        print(f"- additional_failed_gates: {len(failed_gates) - limit}")
    print("Issues:")
    for index, category in enumerate(sorted(counts), start=1):
        if index > limit:
            print(f"- additional_issues: {len(counts) - limit}")
            break
        print(f"- {category}: {counts[category]}")


def gate_status(gates: Mapping[str, object], name: str) -> str:
    gate = gates[name]
    assert isinstance(gate, Mapping)
    return safe_status_value(gate["status"])


def safe_issue_token(value: str) -> str:
    token = "".join(
        char if char.isascii() and (char.isalnum() or char == "_") else "_"
        for char in value.lower()
    ).strip("_")
    return token[:80] if token else "check"


def safe_status_value(value: object) -> str:
    if isinstance(value, str) and value in SAFE_STATUS_VALUES:
        return value
    return "unknown"


def safe_review_profile(value: object) -> str:
    if isinstance(value, str) and value in SAFE_REVIEW_PROFILES:
        return value
    return "unknown"


def safe_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
