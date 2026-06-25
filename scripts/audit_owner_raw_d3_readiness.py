#!/usr/bin/env python3
"""Aggregate owner_raw D3 staging and live front-door readiness gates."""

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
from scripts import audit_owner_raw_live_front_door_review as live_review  # noqa: E402
from scripts import audit_owner_raw_staging_preflight as staging_preflight  # noqa: E402


SUMMARY_KIND = "owner_raw_d3_readiness_v1"


@dataclass(frozen=True)
class GateOutcome:
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
            "Run a raw-free owner_raw D3 readiness gate over an ignored local "
            "staging config and a raw-free live front-door review summary. The "
            "gate fails closed without a live review summary and never prints "
            "config paths, review paths, header names or values, users, URLs, "
            "query ids, credentials, auth material, or raw source."
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
    parser.add_argument("--limit", type=positive_int, default=12, help="Maximum issues to print.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    overlap_error = output_overlaps_inputs_error(
        args.summary_json,
        tuple(path for path in (args.config, args.front_door_review_json) if path is not None),
        message="summary output must not overwrite input artifacts",
    )
    if overlap_error:
        print(f"Owner raw D3 readiness: rejected: {overlap_error}", file=sys.stderr)
        return 2

    staging = staging_gate(args)
    review = front_door_review_gate(args.front_door_review_json)
    payload = summary_payload(staging=staging, review=review)
    if args.summary_json is not None:
        try:
            write_ascii_json_artifact(args.summary_json, payload)
        except OSError:
            print(
                "Owner raw D3 readiness: rejected: summary JSON could not be written",
                file=sys.stderr,
            )
            return 2

    print(format_summary(payload))
    print_issues(payload, limit=args.limit)
    return 0 if payload["status"] == "ok" else 1


def staging_gate(args: argparse.Namespace) -> GateOutcome:
    result = staging_preflight.PreflightResult(config_checked=True)
    staging_args = argparse.Namespace(
        config=args.config,
        host=args.host,
        allow_nonlocal_web_bind=args.allow_nonlocal_web_bind,
        disable_owner_raw_source=args.disable_owner_raw_source,
    )
    try:
        staging_preflight.audit_config(result, staging_args)
    except staging_preflight.OwnerRawStagingPreflightInputError:
        return GateOutcome(
            "staging_config_preflight",
            "rejected",
            Counter({"staging_config_input_rejected": 1}),
        )
    status = "ok" if result.ok else "failed"
    payload = staging_preflight.summary_payload(result, status=status)
    owner_raw_boundary = payload["owner_raw_boundary"]
    safety_controls = payload["safety_controls"]
    assert isinstance(owner_raw_boundary, Mapping)
    assert isinstance(safety_controls, Mapping)
    return GateOutcome(
        "staging_config_preflight",
        status,
        Counter({f"staging.{category}": count for category, count in result.issue_counts.items()}),
        {
            "source_count": int(owner_raw_boundary["source_count"]),
            "owner_raw_source_count": int(owner_raw_boundary["owner_raw_source_count"]),
            "nonlocal_owner_raw_source_count": int(
                owner_raw_boundary["nonlocal_owner_raw_source_count"]
            ),
            "viewer_identity_header": str(owner_raw_boundary["viewer_identity_header"]),
            "owner_raw_source": str(owner_raw_boundary["owner_raw_source"]),
            "privacy_safe_count": int(safety_controls["privacy_safe_count"]),
            "redaction_safe_count": int(safety_controls["redaction_safe_count"]),
        },
    )


def front_door_review_gate(review_path: Path | None) -> GateOutcome:
    if review_path is None:
        return GateOutcome(
            "live_front_door_review",
            "missing",
            Counter({"front_door_review_summary_missing": 1}),
        )
    try:
        payload = live_review.load_review(review_path)
    except live_review.ReviewInputError:
        return GateOutcome(
            "live_front_door_review",
            "rejected",
            Counter({"front_door_review_input_rejected": 1}),
        )
    result = live_review.audit_review(payload)
    issues = Counter(
        {f"front_door.{category}": count for category, count in result.issue_counts.items()}
    )
    if result.profile != live_review.PROFILE_OWNER_RAW_D3:
        issues["front_door.invalid_review_profile"] += 1
    status = "ok" if not issues else "failed"
    return GateOutcome(
        "live_front_door_review",
        status,
        issues,
        {
            "review_profile": result.profile,
            "checked_required_fields": result.checked_required_fields,
        },
    )


def summary_payload(*, staging: GateOutcome, review: GateOutcome) -> dict[str, Any]:
    issue_counts = Counter()
    issue_counts.update(staging.issue_counts)
    issue_counts.update(review.issue_counts)
    status = "ok" if staging.ok and review.ok else "failed"
    return {
        "summary_kind": SUMMARY_KIND,
        "status": status,
        "readiness": {
            "source_enable_ready": status == "ok",
            "native_auth_added": False,
            "live_review_required": True,
            "front_door_review": review.status,
            "staging_config_preflight": staging.status,
            "current_config_owner_raw_source": staging.metadata.get("owner_raw_source", "unknown"),
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
            staging.name: gate_payload(staging),
            review.name: gate_payload(review),
        },
        "issues": {
            "counts": counter_payload(issue_counts),
        },
    }


def gate_payload(gate: GateOutcome) -> dict[str, object]:
    return {
        "status": gate.status,
        "issue_counts": counter_payload(gate.issue_counts),
        "metadata": gate.metadata,
    }


def format_summary(payload: Mapping[str, Any]) -> str:
    readiness = payload["readiness"]
    assert isinstance(readiness, Mapping)
    return "\n".join(
        (
            f"Owner raw D3 readiness: {payload['status']}",
            f"source_enable_ready={'yes' if readiness['source_enable_ready'] else 'no'}",
            f"staging_config_preflight={readiness['staging_config_preflight']}",
            f"front_door_review={readiness['front_door_review']}",
            f"current_config_owner_raw_source={readiness['current_config_owner_raw_source']}",
            "native_auth_added=no",
            "live_review_required=yes",
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
    assert isinstance(counts, Mapping)
    if not counts:
        print("Issues: none")
        return
    print("Issues:")
    for index, category in enumerate(sorted(counts), start=1):
        if index > limit:
            print(f"- additional_issues: {len(counts) - limit}")
            break
        print(f"- {category}: {counts[category]}")


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
