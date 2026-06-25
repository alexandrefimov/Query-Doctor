#!/usr/bin/env python3
"""Audit raw-free owner_raw D3 launch-closure evidence."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    output_overlaps_inputs_error,
    write_ascii_json_artifact,
)
from query_doctor.safety.manifest_references import (  # noqa: E402
    is_safe_relative_json_reference,
)
from scripts import audit_owner_raw_d3_post_enable as post_enable  # noqa: E402
from scripts import audit_owner_raw_d3_readiness as readiness  # noqa: E402
from scripts import audit_owner_raw_d3_rehearsal as rehearsal  # noqa: E402
from scripts import audit_owner_raw_d3_source_enable as source_enable  # noqa: E402
from scripts import audit_owner_raw_live_front_door_review as live_review  # noqa: E402


SUMMARY_KIND = "owner_raw_d3_launch_closure_v1"
MANIFEST_KIND = "owner_raw_d3_launch_closure_manifest_v1"
MANIFEST_BUILDER_KIND = "owner_raw_d3_launch_closure_manifest_builder_v1"
VERDICT_CLOSED = "closed"
VERDICT_BLOCKED = "blocked"
MANIFEST_LIMITATIONS = (
    "retained_owner_raw_d3_summaries",
    "front_door_review_summary_checked",
    "readiness_summary_checked",
    "rehearsal_summary_checked",
    "source_enable_summary_checked",
    "post_enable_summary_checked",
    "not_committed_public_documentation",
    "not_native_sso",
    "not_source_reader",
)
MANIFEST_ENTRY_FIELDS = (
    "front_door_review_summary_json",
    "readiness_summary_json",
    "rehearsal_summary_json",
    "source_enable_summary_json",
    "post_enable_summary_json",
)

RAW_OUTPUT_FIELDS = (
    "raw_values_output",
    "paths_printed",
    "header_names_printed",
    "header_values_printed",
    "users_printed",
    "urls_printed",
    "query_ids_printed",
    "auth_material_printed",
    "raw_source_printed",
)
FRONT_DOOR_OUTPUT_FIELDS = (
    "raw_values_output",
    "path_output",
    "url_output",
    "header_output",
    "user_output",
    "query_id_output",
    "source_output",
)
SAFE_FIELD_NAMES = frozenset(
    {
        "auth_material_printed",
        "broader_shared_trino_support",
        "canary_close_ready",
        "canary_ready",
        "canary_validated",
        "check_count",
        "checked_required_fields",
        "closure",
        "counts",
        "current_config_owner_raw_source",
        "d3_readiness",
        "dev_sso_keycloak_smoke",
        "direct_upstream_client_access_blocked",
        "exactly_one_normalized_viewer_header_required",
        "failed_gates",
        "final_source_state",
        "final_state",
        "front_door_boundary",
        "front_door_review",
        "generated_sql",
        "gates",
        "header_names_printed",
        "header_output",
        "header_values_printed",
        "inbound_viewer_header_stripping_required",
        "issue_counts",
        "issues",
        "kill_switch_rollback_plan_confirmed",
        "live_front_door_review",
        "live_review_required",
        "llm_report_output",
        "local_owner_raw_source_count",
        "launch_closure_ready",
        "metadata",
        "metadata_collection",
        "native_auth_added",
        "no_disable_owner_raw_source_confirmed",
        "no_front_door_or_header_change_confirmed",
        "nonlocal_owner_raw_source_count",
        "nonlocal_owner_raw_source_count_match",
        "operator_confirmation",
        "owner_raw_source",
        "owner_raw_source_count",
        "owner_raw_source_count_match",
        "path_output",
        "paths_printed",
        "planned_owner_raw_source",
        "post_enable",
        "post_enable_review",
        "previous_owner_raw_source",
        "privacy_safe_count",
        "query_history_crawling",
        "query_id_output",
        "query_ids_printed",
        "query_optimizer_jobs",
        "raw_identity_token_forwarding",
        "raw_source_printed",
        "raw_trino_source_reveal",
        "raw_values_output",
        "readiness",
        "redaction_safe_count",
        "rehearsal_complete",
        "rehearsal_config_alignment",
        "rehearsal_summary",
        "review_profile",
        "running_scan",
        "shared_hardening_profile",
        "source_count",
        "source_enable",
        "source_enable_canary_confirmed",
        "source_enable_config",
        "source_enable_ready",
        "source_enable_summary",
        "source_enabled_by_script",
        "source_output",
        "sql_execution",
        "staging_config_preflight",
        "status",
        "summary_kind",
        "trusted_front_door_identity_review",
        "trino_boundary",
        "url_output",
        "urls_printed",
        "user_output",
        "users_printed",
        "verdict",
        "viewer_identity_header",
    }
)
SAFE_STRING_VALUES = frozenset(
    {
        SUMMARY_KIND,
        live_review.AUDIT_KIND,
        readiness.SUMMARY_KIND,
        rehearsal.SUMMARY_KIND,
        source_enable.SUMMARY_KIND,
        post_enable.SUMMARY_KIND,
        live_review.PROFILE_OWNER_RAW_D3,
        live_review.PROFILE_TRINO_SHARED_HARDENING,
        VERDICT_CLOSED,
        VERDICT_BLOCKED,
        post_enable.FINAL_STATE_LEAVE_ENABLED,
        post_enable.FINAL_STATE_ROLLBACK_COMPLETED,
        "blocked",
        "configured",
        "disabled",
        "enabled",
        "failed",
        "local",
        "missing_or_invalid",
        "nonlocal",
        "not_checked",
        "not_wired",
        "ok",
        "operator_review_summary",
        "rejected",
        "unknown",
    }
)
SAFE_ISSUE_RE = re.compile(r"^[a-z0-9_.-]{1,160}$")


class LaunchClosureInputError(RuntimeError):
    """Raised when inputs cannot be safely audited."""


@dataclass
class GateOutcome:
    name: str
    status: str
    issue_counts: Counter[str] = field(default_factory=Counter)
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok" and not self.issue_counts


@dataclass(frozen=True)
class LaunchClosureInputPaths:
    front_door_review_summary_json: Path
    readiness_summary_json: Path
    rehearsal_summary_json: Path
    source_enable_summary_json: Path
    post_enable_summary_json: Path
    manifest_json: Path | None = None

    @property
    def all_paths(self) -> tuple[Path, ...]:
        return (
            self.front_door_review_summary_json,
            self.readiness_summary_json,
            self.rehearsal_summary_json,
            self.source_enable_summary_json,
            self.post_enable_summary_json,
        )

    @property
    def overlap_inputs(self) -> tuple[Path, ...]:
        if self.manifest_json is None:
            return self.all_paths
        return (self.manifest_json, *self.all_paths)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit raw-free owner_raw D3 launch-closure evidence. The script "
            "reads only already raw-free front-door, readiness, rehearsal, "
            "source-enable, and post-enable summaries. It never contacts a "
            "proxy, performs authentication, opens cases, reads raw source, "
            "changes config, or prints paths, URLs, users, header names or "
            "values, query ids, credentials, auth material, or raw source."
        )
    )
    parser.add_argument(
        "--front-door-review-summary-json",
        type=Path,
        help="Raw-free owner_raw live front-door review audit summary.",
    )
    parser.add_argument(
        "--readiness-summary-json",
        type=Path,
        help="Raw-free owner_raw D3 readiness summary.",
    )
    parser.add_argument(
        "--rehearsal-summary-json",
        type=Path,
        help="Raw-free owner_raw D3 rehearsal summary.",
    )
    parser.add_argument(
        "--source-enable-summary-json",
        type=Path,
        help="Raw-free owner_raw D3 source-enable canary summary.",
    )
    parser.add_argument(
        "--post-enable-summary-json",
        type=Path,
        help="Raw-free owner_raw D3 post-enable canary summary.",
    )
    parser.add_argument(
        "--launch-closure-manifest",
        type=Path,
        help=(
            "Optional raw-free owner_raw D3 launch-closure manifest with safe relative "
            "summary artifact references. Cannot be combined with direct summary inputs."
        ),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Optional raw-free machine launch-closure summary JSON.",
    )
    parser.add_argument("--limit", type=positive_int, default=20, help="Maximum issues to print.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        inputs = selected_input_paths(args)
    except LaunchClosureInputError as exc:
        message = (
            "required inputs are missing"
            if str(exc) == "direct inputs are incomplete"
            else "launch closure inputs are not accepted"
        )
        print(f"Owner raw D3 launch closure: rejected: {message}", file=sys.stderr)
        return 2
    overlap_error = output_overlap_error(args, inputs)
    if overlap_error:
        print(f"Owner raw D3 launch closure: rejected: {overlap_error}", file=sys.stderr)
        return 2

    front_door_gate = front_door_review_summary_gate(inputs.front_door_review_summary_json)
    readiness_gate = readiness_summary_gate(inputs.readiness_summary_json)
    rehearsal_gate = rehearsal_summary_gate(inputs.rehearsal_summary_json)
    source_enable_gate = source_enable_summary_gate(inputs.source_enable_summary_json)
    post_enable_gate = post_enable_summary_gate(inputs.post_enable_summary_json)
    chain_gate = chain_consistency_gate(
        front_door_gate=front_door_gate,
        readiness_gate=readiness_gate,
        rehearsal_gate=rehearsal_gate,
        source_enable_gate=source_enable_gate,
        post_enable_gate=post_enable_gate,
    )
    payload = summary_payload(
        (
            front_door_gate,
            readiness_gate,
            rehearsal_gate,
            source_enable_gate,
            post_enable_gate,
            chain_gate,
        )
    )
    if args.summary_json is not None:
        try:
            write_ascii_json_artifact(args.summary_json, payload)
        except OSError:
            print(
                "Owner raw D3 launch closure: rejected: summary JSON could not be written",
                file=sys.stderr,
            )
            return 2

    print(format_summary(payload))
    print_issues(payload, limit=args.limit)
    return 0 if payload["status"] == "ok" else 1


def front_door_review_summary_gate(path: Path) -> GateOutcome:
    try:
        payload = load_json_object(path)
    except LaunchClosureInputError:
        return GateOutcome(
            "front_door_review_summary",
            "rejected",
            Counter({"front_door_summary_input_rejected": 1}),
        )
    issues: Counter[str] = Counter()
    audit_raw_free_shape(payload, issues, prefix="front_door")
    if payload.get("summary_kind") != live_review.AUDIT_KIND:
        issues["front_door.invalid_summary_kind"] += 1
    if payload.get("status") != "ok":
        issues["front_door.status_not_ok"] += 1
    if payload.get("review_profile") != live_review.PROFILE_OWNER_RAW_D3:
        issues["front_door.invalid_review_profile"] += 1
    if safe_int(payload.get("checked_required_fields")) < 1:
        issues["front_door.no_required_fields_checked"] += 1
    issue_counts = payload.get("issue_counts")
    if not isinstance(issue_counts, Mapping):
        issues["front_door.issues_missing"] += 1
    elif issue_counts:
        issues["front_door.issues_not_empty"] += 1

    boundary = mapping_path(payload, ("front_door_boundary",))
    if boundary is None:
        issues["front_door.boundary_missing"] += 1
        boundary = {}
    expected = {
        "trusted_front_door_identity_review": "operator_review_summary",
        "direct_upstream_client_access_blocked": True,
        "inbound_viewer_header_stripping_required": True,
        "exactly_one_normalized_viewer_header_required": True,
        "raw_identity_token_forwarding": "blocked",
    }
    for field_name, expected_value in expected.items():
        if boundary.get(field_name) != expected_value:
            issues[f"front_door.{field_name}_invalid"] += 1
    require_false_flags(
        boundary,
        FRONT_DOOR_OUTPUT_FIELDS,
        issues,
        category_prefix="front_door",
    )
    return GateOutcome(
        "front_door_review_summary",
        "ok" if not issues else "failed",
        issues,
        {
            "review_profile": safe_status_value(payload.get("review_profile")),
            "checked_required_fields": safe_int(payload.get("checked_required_fields")),
            "raw_values_output": False,
        },
    )


def readiness_summary_gate(path: Path) -> GateOutcome:
    try:
        payload = load_json_object(path)
    except LaunchClosureInputError:
        return GateOutcome(
            "readiness_summary",
            "rejected",
            Counter({"readiness_summary_input_rejected": 1}),
        )
    issues: Counter[str] = Counter()
    audit_raw_free_shape(payload, issues, prefix="readiness")
    if payload.get("summary_kind") != readiness.SUMMARY_KIND:
        issues["readiness.invalid_summary_kind"] += 1
    if payload.get("status") != "ok":
        issues["readiness.status_not_ok"] += 1
    readiness_payload = mapping_path(payload, ("readiness",))
    if readiness_payload is None:
        issues["readiness.summary_missing"] += 1
        readiness_payload = {}
    expected = {
        "source_enable_ready": True,
        "native_auth_added": False,
        "live_review_required": True,
        "front_door_review": "ok",
        "staging_config_preflight": "ok",
        "current_config_owner_raw_source": "disabled",
    }
    for field_name, expected_value in expected.items():
        if readiness_payload.get(field_name) != expected_value:
            issues[f"readiness.{field_name}_invalid"] += 1
    require_false_flags(readiness_payload, RAW_OUTPUT_FIELDS, issues, category_prefix="readiness")
    require_gate_statuses(
        payload,
        ("staging_config_preflight", "live_front_door_review"),
        issues,
        category_prefix="readiness",
    )
    require_empty_issues(payload, issues, category_prefix="readiness")
    return GateOutcome(
        "readiness_summary",
        "ok" if not issues else "failed",
        issues,
        {
            "current_config_owner_raw_source": safe_status_value(
                readiness_payload.get("current_config_owner_raw_source")
            ),
            "source_enable_ready": readiness_payload.get("source_enable_ready") is True,
            "native_auth_added": False,
            "live_review_required": True,
        },
    )


def rehearsal_summary_gate(path: Path) -> GateOutcome:
    try:
        payload = load_json_object(path)
    except LaunchClosureInputError:
        return GateOutcome(
            "rehearsal_summary",
            "rejected",
            Counter({"rehearsal_summary_input_rejected": 1}),
        )
    issues: Counter[str] = Counter()
    audit_raw_free_shape(payload, issues, prefix="rehearsal")
    if payload.get("summary_kind") != rehearsal.SUMMARY_KIND:
        issues["rehearsal.invalid_summary_kind"] += 1
    if payload.get("status") != "ok":
        issues["rehearsal.status_not_ok"] += 1
    rehearsal_payload = mapping_path(payload, ("readiness",))
    if rehearsal_payload is None:
        issues["rehearsal.summary_missing"] += 1
        rehearsal_payload = {}
    expected = {
        "rehearsal_complete": True,
        "source_enable_ready": True,
        "native_auth_added": False,
        "live_review_required": True,
    }
    for field_name, expected_value in expected.items():
        if rehearsal_payload.get(field_name) != expected_value:
            issues[f"rehearsal.{field_name}_invalid"] += 1
    require_false_flags(rehearsal_payload, RAW_OUTPUT_FIELDS, issues, category_prefix="rehearsal")
    require_gate_statuses(
        payload,
        (
            "dev_sso_keycloak_smoke",
            "live_front_door_review",
            "staging_config_preflight",
            "d3_readiness",
        ),
        issues,
        category_prefix="rehearsal",
    )
    d3_metadata = mapping_path(payload, ("gates", "d3_readiness", "metadata")) or {}
    if safe_status_value(d3_metadata.get("current_config_owner_raw_source")) != "disabled":
        issues["rehearsal.current_source_not_disabled"] += 1
    require_empty_issues(payload, issues, category_prefix="rehearsal")
    return GateOutcome(
        "rehearsal_summary",
        "ok" if not issues else "failed",
        issues,
        {
            "current_config_owner_raw_source": safe_status_value(
                d3_metadata.get("current_config_owner_raw_source")
            ),
            "source_enable_ready": rehearsal_payload.get("source_enable_ready") is True,
            "native_auth_added": False,
            "live_review_required": True,
        },
    )


def source_enable_summary_gate(path: Path) -> GateOutcome:
    try:
        payload = load_json_object(path)
    except LaunchClosureInputError:
        return GateOutcome(
            "source_enable_summary",
            "rejected",
            Counter({"source_enable_summary_input_rejected": 1}),
        )
    issues: Counter[str] = Counter()
    audit_raw_free_shape(payload, issues, prefix="source_enable")
    if payload.get("summary_kind") != source_enable.SUMMARY_KIND:
        issues["source_enable.invalid_summary_kind"] += 1
    if payload.get("status") != "ok":
        issues["source_enable.status_not_ok"] += 1
    source_payload = mapping_path(payload, ("source_enable",))
    if source_payload is None:
        issues["source_enable.summary_missing"] += 1
        source_payload = {}
    expected = {
        "canary_ready": True,
        "source_enabled_by_script": False,
        "native_auth_added": False,
        "live_review_required": True,
        "previous_owner_raw_source": "disabled",
        "planned_owner_raw_source": "enabled",
    }
    for field_name, expected_value in expected.items():
        if source_payload.get(field_name) != expected_value:
            issues[f"source_enable.{field_name}_invalid"] += 1
    require_false_flags(
        source_payload,
        RAW_OUTPUT_FIELDS,
        issues,
        category_prefix="source_enable",
    )
    require_gate_statuses(
        payload,
        (
            "rehearsal_summary",
            "source_enable_config",
            "rehearsal_config_alignment",
            "operator_confirmation",
        ),
        issues,
        category_prefix="source_enable",
    )
    require_empty_issues(payload, issues, category_prefix="source_enable")
    return GateOutcome(
        "source_enable_summary",
        "ok" if not issues else "failed",
        issues,
        {
            "previous_owner_raw_source": safe_status_value(
                source_payload.get("previous_owner_raw_source")
            ),
            "planned_owner_raw_source": safe_status_value(
                source_payload.get("planned_owner_raw_source")
            ),
            "source_enabled_by_script": source_payload.get("source_enabled_by_script") is True,
            "native_auth_added": False,
            "live_review_required": True,
        },
    )


def post_enable_summary_gate(path: Path) -> GateOutcome:
    try:
        payload = load_json_object(path)
    except LaunchClosureInputError:
        return GateOutcome(
            "post_enable_summary",
            "rejected",
            Counter({"post_enable_summary_input_rejected": 1}),
        )
    issues: Counter[str] = Counter()
    audit_raw_free_shape(payload, issues, prefix="post_enable")
    if payload.get("summary_kind") != post_enable.SUMMARY_KIND:
        issues["post_enable.invalid_summary_kind"] += 1
    if payload.get("status") != "ok":
        issues["post_enable.status_not_ok"] += 1
    post_payload = mapping_path(payload, ("post_enable",))
    if post_payload is None:
        issues["post_enable.summary_missing"] += 1
        post_payload = {}
    expected = {
        "canary_validated": True,
        "canary_close_ready": True,
        "source_enabled_by_script": False,
        "native_auth_added": False,
    }
    for field_name, expected_value in expected.items():
        if post_payload.get(field_name) != expected_value:
            issues[f"post_enable.{field_name}_invalid"] += 1
    final_source_state = selected_final_source_state(post_payload.get("final_source_state"))
    if final_source_state == "unknown":
        issues["post_enable.invalid_final_source_state"] += 1
    require_false_flags(post_payload, RAW_OUTPUT_FIELDS, issues, category_prefix="post_enable")
    require_gate_statuses(
        payload,
        ("source_enable_summary", "post_enable_review", "final_state"),
        issues,
        category_prefix="post_enable",
    )
    require_empty_issues(payload, issues, category_prefix="post_enable")
    return GateOutcome(
        "post_enable_summary",
        "ok" if not issues else "failed",
        issues,
        {
            "final_source_state": final_source_state,
            "source_enabled_by_script": post_payload.get("source_enabled_by_script") is True,
            "native_auth_added": False,
            "canary_close_ready": post_payload.get("canary_close_ready") is True,
        },
    )


def chain_consistency_gate(
    *,
    front_door_gate: GateOutcome,
    readiness_gate: GateOutcome,
    rehearsal_gate: GateOutcome,
    source_enable_gate: GateOutcome,
    post_enable_gate: GateOutcome,
) -> GateOutcome:
    issues: Counter[str] = Counter()
    if front_door_gate.metadata.get("review_profile") != live_review.PROFILE_OWNER_RAW_D3:
        issues["chain.front_door_profile_not_owner_raw_d3"] += 1
    if readiness_gate.metadata.get("current_config_owner_raw_source") != "disabled":
        issues["chain.readiness_source_not_disabled"] += 1
    if rehearsal_gate.metadata.get("current_config_owner_raw_source") != "disabled":
        issues["chain.rehearsal_source_not_disabled"] += 1
    if source_enable_gate.metadata.get("previous_owner_raw_source") != "disabled":
        issues["chain.source_enable_previous_source_not_disabled"] += 1
    if source_enable_gate.metadata.get("planned_owner_raw_source") != "enabled":
        issues["chain.source_enable_planned_source_not_enabled"] += 1
    if source_enable_gate.metadata.get("source_enabled_by_script") is True:
        issues["chain.source_enabled_by_script"] += 1
    if post_enable_gate.metadata.get("source_enabled_by_script") is True:
        issues["chain.post_enable_source_enabled_by_script"] += 1
    final_source_state = selected_final_source_state(
        post_enable_gate.metadata.get("final_source_state")
    )
    if final_source_state == "unknown":
        issues["chain.invalid_final_source_state"] += 1
    return GateOutcome(
        "chain_consistency",
        "ok" if not issues else "failed",
        issues,
        {
            "final_source_state": final_source_state,
            "verdict": VERDICT_CLOSED if not issues else VERDICT_BLOCKED,
        },
    )


def summary_payload(gates: tuple[GateOutcome, ...]) -> dict[str, Any]:
    gate_payloads = {gate.name: gate_payload(gate) for gate in gates}
    failed_gates = tuple(gate.name for gate in gates if not gate.ok)
    issue_counts: Counter[str] = Counter()
    for gate in gates:
        issue_counts.update(gate.issue_counts)
    chain_metadata = gate_payloads["chain_consistency"]["metadata"]
    assert isinstance(chain_metadata, Mapping)
    status = "ok" if not failed_gates else "failed"
    final_source_state = chain_metadata["final_source_state"] if status == "ok" else "unknown"
    verdict = VERDICT_CLOSED if status == "ok" else VERDICT_BLOCKED
    return {
        "summary_kind": SUMMARY_KIND,
        "status": status,
        "closure": {
            "launch_closure_ready": status == "ok",
            "verdict": verdict,
            "final_source_state": final_source_state,
            "source_enabled_by_script": False,
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


def gate_payload(gate: GateOutcome) -> dict[str, object]:
    return {
        "status": gate.status,
        "issue_counts": counter_payload(gate.issue_counts),
        "metadata": gate.metadata,
    }


def format_summary(payload: Mapping[str, Any]) -> str:
    closure = payload["closure"]
    gates = payload["gates"]
    assert isinstance(closure, Mapping)
    assert isinstance(gates, Mapping)
    return "\n".join(
        (
            f"Owner raw D3 launch closure: {payload['status']}",
            f"launch_closure_ready={'yes' if closure['launch_closure_ready'] else 'no'}",
            f"verdict={closure['verdict']}",
            f"front_door_review_summary={gate_status(gates, 'front_door_review_summary')}",
            f"readiness_summary={gate_status(gates, 'readiness_summary')}",
            f"rehearsal_summary={gate_status(gates, 'rehearsal_summary')}",
            f"source_enable_summary={gate_status(gates, 'source_enable_summary')}",
            f"post_enable_summary={gate_status(gates, 'post_enable_summary')}",
            f"chain_consistency={gate_status(gates, 'chain_consistency')}",
            f"final_source_state={closure['final_source_state']}",
            "source_enabled_by_script=no",
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


def require_false_flags(
    payload: Mapping[str, Any],
    field_names: Iterable[str],
    issues: Counter[str],
    *,
    category_prefix: str,
) -> None:
    for field_name in field_names:
        if payload.get(field_name) is not False:
            issues[f"{category_prefix}.{field_name}"] += 1


def require_gate_statuses(
    payload: Mapping[str, Any],
    gate_names: Iterable[str],
    issues: Counter[str],
    *,
    category_prefix: str,
) -> None:
    gates_payload = mapping_path(payload, ("gates",))
    if gates_payload is None:
        issues[f"{category_prefix}.gates_missing"] += 1
        return
    for gate_name in gate_names:
        gate_payload = mapping_path(gates_payload, (gate_name,))
        if gate_payload is None:
            issues[f"{category_prefix}.{gate_name}_missing"] += 1
        elif gate_payload.get("status") != "ok":
            issues[f"{category_prefix}.{gate_name}_not_ok"] += 1


def require_empty_issues(
    payload: Mapping[str, Any],
    issues: Counter[str],
    *,
    category_prefix: str,
) -> None:
    issues_payload = mapping_path(payload, ("issues",))
    if issues_payload is None:
        issues[f"{category_prefix}.issues_missing"] += 1
        return
    counts = issues_payload.get("counts")
    if not isinstance(counts, Mapping):
        issues[f"{category_prefix}.issue_counts_missing"] += 1
    elif counts:
        issues[f"{category_prefix}.issues_not_empty"] += 1
    failed_gates = issues_payload.get("failed_gates")
    if failed_gates not in (None, []):
        issues[f"{category_prefix}.failed_gates_not_empty"] += 1


def audit_raw_free_shape(
    value: Any,
    issues: Counter[str],
    *,
    prefix: str,
    path: tuple[str, ...] = (),
) -> None:
    if isinstance(value, Mapping):
        if path and path[-1] in {"issue_counts", "counts"}:
            for key, count in value.items():
                if not isinstance(key, str) or not SAFE_ISSUE_RE.fullmatch(key):
                    issues[f"{prefix}.unsafe_issue_category"] += 1
                if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                    issues[f"{prefix}.unsafe_issue_count"] += 1
            return
        for key, child in value.items():
            if not isinstance(key, str):
                issues[f"{prefix}.non_string_field_name"] += 1
                continue
            if key not in SAFE_FIELD_NAMES:
                issues[f"{prefix}.unexpected_field"] += 1
            audit_raw_free_shape(child, issues, prefix=prefix, path=path + (key,))
        return
    if path and path[-1] in {"issue_counts", "counts"}:
        issues[f"{prefix}.unsafe_issue_counts_shape"] += 1
        return
    if isinstance(value, list):
        for child in value:
            audit_raw_free_shape(child, issues, prefix=prefix, path=path)
        return
    if isinstance(value, bool):
        return
    if isinstance(value, int) and value >= 0:
        return
    if isinstance(value, str):
        if value not in SAFE_STRING_VALUES:
            issues[f"{prefix}.unsafe_string_value"] += 1
        return
    issues[f"{prefix}.unsafe_value_type"] += 1


def load_json_object(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise LaunchClosureInputError("input could not be read safely") from None
    if not isinstance(payload, Mapping):
        raise LaunchClosureInputError("input must be a JSON object") from None
    return payload


def mapping_path(payload: Mapping[str, Any], path: tuple[str, ...]) -> Mapping[str, Any] | None:
    current: Any = payload
    for part in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current if isinstance(current, Mapping) else None


def selected_final_source_state(value: object) -> str:
    if value in {
        post_enable.FINAL_STATE_LEAVE_ENABLED,
        post_enable.FINAL_STATE_ROLLBACK_COMPLETED,
    }:
        return str(value)
    return "unknown"


def gate_status(gates: Mapping[str, object], name: str) -> str:
    gate = gates[name]
    assert isinstance(gate, Mapping)
    return safe_status_value(gate["status"])


def safe_status_value(value: object) -> str:
    if isinstance(value, str) and value in SAFE_STRING_VALUES:
        return value
    return "unknown"


def safe_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def selected_input_paths(args: argparse.Namespace) -> LaunchClosureInputPaths:
    direct_paths = tuple(path for _, path in direct_input_paths(args) if path is not None)
    if args.launch_closure_manifest is not None:
        if direct_paths:
            raise LaunchClosureInputError("manifest cannot be combined with direct inputs")
        return load_launch_closure_manifest(args.launch_closure_manifest)

    missing = [flag_name for flag_name, path in direct_input_paths(args) if path is None]
    if missing:
        raise LaunchClosureInputError("direct inputs are incomplete")
    return LaunchClosureInputPaths(
        front_door_review_summary_json=args.front_door_review_summary_json,
        readiness_summary_json=args.readiness_summary_json,
        rehearsal_summary_json=args.rehearsal_summary_json,
        source_enable_summary_json=args.source_enable_summary_json,
        post_enable_summary_json=args.post_enable_summary_json,
    )


def load_launch_closure_manifest(path: Path) -> LaunchClosureInputPaths:
    payload = load_json_object(path)
    if set(payload) != {"manifest_kind", "metadata", "entries"}:
        raise LaunchClosureInputError("manifest schema is invalid")
    if payload.get("manifest_kind") != MANIFEST_KIND:
        raise LaunchClosureInputError("manifest kind is invalid")
    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        raise LaunchClosureInputError("manifest metadata is invalid")
    if metadata.get("builder_kind") != MANIFEST_BUILDER_KIND:
        raise LaunchClosureInputError("manifest builder kind is invalid")
    if metadata.get("entry_count") != 1:
        raise LaunchClosureInputError("manifest entry count is invalid")
    if metadata.get("path_reference") != "relative_to_manifest":
        raise LaunchClosureInputError("manifest path reference is invalid")
    if metadata.get("redaction_reviewed") is not True:
        raise LaunchClosureInputError("manifest redaction review is required")
    if metadata.get("limitations") != list(MANIFEST_LIMITATIONS):
        raise LaunchClosureInputError("manifest limitations are invalid")
    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) != 1:
        raise LaunchClosureInputError("manifest entries are invalid")
    entry = entries[0]
    if not isinstance(entry, Mapping) or set(entry) != set(MANIFEST_ENTRY_FIELDS):
        raise LaunchClosureInputError("manifest entry is invalid")
    references = []
    for field_name in MANIFEST_ENTRY_FIELDS:
        reference = entry.get(field_name)
        if not is_safe_relative_json_reference(reference):
            raise LaunchClosureInputError("manifest reference is unsafe")
        assert isinstance(reference, str)
        references.append(reference)
    if len(set(references)) != len(references):
        raise LaunchClosureInputError("manifest references must be unique")
    resolved = tuple(path.parent / reference for reference in references)
    if any(not artifact.is_file() for artifact in resolved):
        raise LaunchClosureInputError("manifest referenced artifact is unavailable")
    return LaunchClosureInputPaths(
        front_door_review_summary_json=resolved[0],
        readiness_summary_json=resolved[1],
        rehearsal_summary_json=resolved[2],
        source_enable_summary_json=resolved[3],
        post_enable_summary_json=resolved[4],
        manifest_json=path,
    )


def output_overlap_error(
    args: argparse.Namespace,
    inputs: LaunchClosureInputPaths,
) -> str | None:
    return output_overlaps_inputs_error(
        args.summary_json,
        inputs.overlap_inputs,
        message="summary output must not overwrite input artifacts",
    )


def direct_input_paths(args: argparse.Namespace) -> tuple[tuple[str, Path | None], ...]:
    return (
        ("--front-door-review-summary-json", args.front_door_review_summary_json),
        ("--readiness-summary-json", args.readiness_summary_json),
        ("--rehearsal-summary-json", args.rehearsal_summary_json),
        ("--source-enable-summary-json", args.source_enable_summary_json),
        ("--post-enable-summary-json", args.post_enable_summary_json),
    )


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
