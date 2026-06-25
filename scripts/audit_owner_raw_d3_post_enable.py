#!/usr/bin/env python3
"""Audit raw-free owner_raw D3 post-enable canary evidence."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import json
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
from scripts import audit_owner_raw_d3_source_enable as source_enable  # noqa: E402


REVIEW_KIND = "owner_raw_d3_post_enable_review_v1"
SUMMARY_KIND = "owner_raw_d3_post_enable_canary_v1"
FINAL_STATE_LEAVE_ENABLED = "leave_enabled"
FINAL_STATE_ROLLBACK_COMPLETED = "rollback_completed"
SAFE_STRING_VALUES = frozenset(
    {
        REVIEW_KIND,
        "reviewed",
        "unreviewed",
        "controlled_canary",
        FINAL_STATE_LEAVE_ENABLED,
        FINAL_STATE_ROLLBACK_COMPLETED,
    }
)


@dataclass(frozen=True)
class ReviewExpectation:
    path: tuple[str, ...]
    expected: object
    category: str

    @property
    def label(self) -> str:
        return ".".join(self.path)


def _expectations(rows: Iterable[tuple[str, object, str]]) -> tuple[ReviewExpectation, ...]:
    return tuple(
        ReviewExpectation(tuple(path.split(".")), expected, category)
        for path, expected, category in rows
    )


REVIEW_EXPECTATIONS = _expectations(
    (
        ("summary_kind", REVIEW_KIND, "invalid_summary_kind"),
        ("review_status", "reviewed", "review_not_marked_reviewed"),
        ("canary_scope", "controlled_canary", "invalid_canary_scope"),
        (
            "source_state.owner_raw_source_enabled_during_canary",
            True,
            "source_not_enabled_during_canary",
        ),
        (
            "source_state.source_enabled_by_query_doctor_script",
            False,
            "source_enabled_by_query_doctor_script",
        ),
        (
            "front_door.no_front_door_or_header_change",
            True,
            "front_door_or_header_changed",
        ),
        (
            "front_door.direct_upstream_client_access_blocked",
            True,
            "direct_upstream_access_not_blocked",
        ),
        (
            "front_door.inbound_viewer_header_stripped",
            True,
            "inbound_viewer_header_not_stripped",
        ),
        (
            "runtime_checks.matching_viewer_own_case_allowed",
            True,
            "matching_viewer_own_case_not_allowed",
        ),
        (
            "runtime_checks.different_viewer_same_case_denied",
            True,
            "different_viewer_same_case_not_denied",
        ),
        (
            "runtime_checks.unauthenticated_request_denied",
            True,
            "unauthenticated_request_not_denied",
        ),
        (
            "runtime_checks.spoofed_viewer_header_not_authorizing",
            True,
            "spoofed_viewer_header_authorized",
        ),
        (
            "runtime_checks.missing_viewer_header_denied",
            True,
            "missing_viewer_header_not_denied",
        ),
        (
            "runtime_checks.invalid_viewer_header_denied",
            True,
            "invalid_viewer_header_not_denied",
        ),
        (
            "runtime_checks.duplicate_viewer_header_denied_or_unforwardable",
            True,
            "duplicate_viewer_header_not_closed",
        ),
        ("runtime_checks.denied_pages_raw_free", True, "denied_pages_not_raw_free"),
        ("runtime_checks.audit_lines_raw_free", True, "audit_lines_not_raw_free"),
        (
            "runtime_checks.trusted_surfaces_raw_free",
            True,
            "trusted_surfaces_not_raw_free",
        ),
        ("rollback.kill_switch_rollback_verified", True, "kill_switch_rollback_not_verified"),
        ("rollback.rollback_path_ready", True, "rollback_path_not_ready"),
        ("rollback.monitoring_active", True, "monitoring_not_active"),
        ("evidence_retention.raw_logs_retained", False, "raw_logs_retained"),
        ("evidence_retention.raw_headers_retained", False, "raw_headers_retained"),
        ("evidence_retention.raw_query_ids_retained", False, "raw_query_ids_retained"),
        ("evidence_retention.raw_users_retained", False, "raw_users_retained"),
        ("evidence_retention.raw_paths_retained", False, "raw_paths_retained"),
        ("evidence_retention.raw_urls_retained", False, "raw_urls_retained"),
        (
            "evidence_retention.screenshots_with_source_retained",
            False,
            "source_screenshots_retained",
        ),
    )
)
ALLOWED_PATHS = frozenset(expectation.path for expectation in REVIEW_EXPECTATIONS) | frozenset(
    {
        ("final_source_state",),
        ("source_state", "owner_raw_source_remaining_enabled"),
    }
)
ALLOWED_PREFIXES = frozenset(
    path[:index] for path in ALLOWED_PATHS for index in range(1, len(path) + 1)
)


class PostEnableInputError(RuntimeError):
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


@dataclass
class ReviewResult:
    final_source_state: str = "unknown"
    checked_required_fields: int = 0
    issue_counts: Counter[str] = field(default_factory=Counter)

    @property
    def ok(self) -> bool:
        return not self.issue_counts


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit raw-free post-enable owner_raw D3 canary evidence. The script "
            "reads only a raw-free source-enable summary and boolean/enumerated "
            "post-enable review fields; it never starts Query Doctor, performs "
            "authentication, opens cases, reads raw source, or prints paths, URLs, "
            "users, header names or values, query ids, credentials, auth material, "
            "or raw source."
        )
    )
    parser.add_argument(
        "--source-enable-summary-json",
        type=Path,
        help="Raw-free owner_raw D3 source-enable canary summary. The path is never printed.",
    )
    parser.add_argument(
        "--post-enable-review-json",
        type=Path,
        help="Raw-free post-enable review summary. The path is never printed.",
    )
    parser.add_argument(
        "--template-json",
        type=Path,
        help="Optional raw-free fail-closed post-enable review template to write.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Optional raw-free machine audit summary JSON. The path is never printed.",
    )
    parser.add_argument(
        "--list-required-fields",
        action="store_true",
        help="Print Python-owned post-enable review field labels.",
    )
    parser.add_argument("--limit", type=positive_int, default=20, help="Maximum issues to print.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list_required_fields:
        for label in required_field_labels():
            print(label)
        return 0

    overlap_error = output_overlap_error(args)
    if overlap_error:
        print(f"Owner raw D3 post-enable canary: rejected: {overlap_error}", file=sys.stderr)
        return 2
    if args.template_json is not None:
        try:
            write_ascii_json_artifact(args.template_json, review_template())
        except OSError:
            print(
                "Owner raw D3 post-enable canary: rejected: template JSON could not be written",
                file=sys.stderr,
            )
            return 2
        print("Owner raw D3 post-enable canary template: written")
        if args.source_enable_summary_json is None and args.post_enable_review_json is None:
            return 0
    missing = []
    if args.source_enable_summary_json is None:
        missing.append("--source-enable-summary-json")
    if args.post_enable_review_json is None:
        missing.append("--post-enable-review-json")
    if missing:
        print(
            "Owner raw D3 post-enable canary: rejected: required inputs are missing",
            file=sys.stderr,
        )
        return 2

    source_enable_gate = source_enable_summary_gate(args.source_enable_summary_json)
    review_gate = post_enable_review_gate(args.post_enable_review_json)
    final_state_gate = final_state_gate_from_review(review_gate)
    payload = summary_payload((source_enable_gate, review_gate, final_state_gate))
    if args.summary_json is not None:
        try:
            write_ascii_json_artifact(args.summary_json, payload)
        except OSError:
            print(
                "Owner raw D3 post-enable canary: rejected: summary JSON could not be written",
                file=sys.stderr,
            )
            return 2
    print(format_summary(payload))
    print_issues(payload, limit=args.limit)
    return 0 if payload["status"] == "ok" else 1


def source_enable_summary_gate(path: Path) -> GateOutcome:
    try:
        payload = load_json_object(path)
    except PostEnableInputError:
        return GateOutcome(
            "source_enable_summary",
            "rejected",
            Counter({"source_enable_summary_input_rejected": 1}),
        )
    issues: Counter[str] = Counter()
    if payload.get("summary_kind") != source_enable.SUMMARY_KIND:
        issues["source_enable.invalid_summary_kind"] += 1
    if payload.get("status") != "ok":
        issues["source_enable.status_not_ok"] += 1
    source_payload = mapping_path(payload, ("source_enable",))
    if source_payload is None:
        issues["source_enable.summary_missing"] += 1
        source_payload = {}
    if source_payload.get("canary_ready") is not True:
        issues["source_enable.canary_not_ready"] += 1
    if source_payload.get("source_enabled_by_script") is not False:
        issues["source_enable.source_enabled_by_script"] += 1
    if source_payload.get("native_auth_added") is not False:
        issues["source_enable.native_auth_added"] += 1
    if source_payload.get("previous_owner_raw_source") != "disabled":
        issues["source_enable.previous_source_not_disabled"] += 1
    if source_payload.get("planned_owner_raw_source") != "enabled":
        issues["source_enable.planned_source_not_enabled"] += 1
    for field_name in (
        "raw_values_output",
        "paths_printed",
        "header_names_printed",
        "header_values_printed",
        "users_printed",
        "urls_printed",
        "query_ids_printed",
        "auth_material_printed",
        "raw_source_printed",
    ):
        if source_payload.get(field_name) is not False:
            issues[f"source_enable.{field_name}"] += 1
    gates_payload = mapping_path(payload, ("gates",))
    if gates_payload is None:
        issues["source_enable.gates_missing"] += 1
        gates_payload = {}
    for gate_name in (
        "rehearsal_summary",
        "source_enable_config",
        "rehearsal_config_alignment",
        "operator_confirmation",
    ):
        gate_payload = mapping_path(gates_payload, (gate_name,))
        if gate_payload is None:
            issues[f"source_enable.{gate_name}_missing"] += 1
        elif gate_payload.get("status") != "ok":
            issues[f"source_enable.{gate_name}_not_ok"] += 1
    issues_payload = mapping_path(payload, ("issues",))
    if issues_payload is None:
        issues["source_enable.issues_missing"] += 1
    elif issues_payload.get("counts") != {} or issues_payload.get("failed_gates") != []:
        issues["source_enable.issues_not_empty"] += 1

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
            "source_enabled_by_script": False,
        },
    )


def post_enable_review_gate(path: Path) -> GateOutcome:
    try:
        payload = load_json_object(path)
    except PostEnableInputError:
        return GateOutcome(
            "post_enable_review",
            "rejected",
            Counter({"post_enable_review_input_rejected": 1}),
        )
    result = audit_review(payload)
    return GateOutcome(
        "post_enable_review",
        "ok" if result.ok else "failed",
        Counter({f"post_enable.{key}": count for key, count in result.issue_counts.items()}),
        {
            "final_source_state": result.final_source_state,
            "checked_required_fields": result.checked_required_fields,
            "raw_values_output": False,
        },
    )


def final_state_gate_from_review(review_gate: GateOutcome) -> GateOutcome:
    final_state = str(review_gate.metadata.get("final_source_state", "unknown"))
    issues: Counter[str] = Counter()
    if final_state not in {FINAL_STATE_LEAVE_ENABLED, FINAL_STATE_ROLLBACK_COMPLETED}:
        issues["final_state.invalid"] += 1
    return GateOutcome(
        "final_state",
        "ok" if not issues else "failed",
        issues,
        {
            "final_source_state": final_state if not issues else "unknown",
            "canary_close_ready": not issues,
        },
    )


def audit_review(payload: Mapping[str, Any]) -> ReviewResult:
    result = ReviewResult(final_source_state=selected_final_source_state(payload))
    audit_raw_free_shape(payload, result)
    for expectation in REVIEW_EXPECTATIONS:
        result.checked_required_fields += 1
        found, value = get_path(payload, expectation.path)
        if not found:
            result.issue_counts[f"missing_{expectation.category}"] += 1
            continue
        if value != expectation.expected:
            result.issue_counts[expectation.category] += 1
    source_remaining_enabled = get_path(
        payload, ("source_state", "owner_raw_source_remaining_enabled")
    )[1]
    if (
        result.final_source_state == FINAL_STATE_LEAVE_ENABLED
        and source_remaining_enabled is not True
    ):
        result.issue_counts["leave_enabled_final_state_mismatch"] += 1
    if (
        result.final_source_state == FINAL_STATE_ROLLBACK_COMPLETED
        and source_remaining_enabled is not False
    ):
        result.issue_counts["rollback_completed_final_state_mismatch"] += 1
    if result.final_source_state == "unknown":
        result.issue_counts["invalid_final_source_state"] += 1
    return result


def audit_raw_free_shape(value: Any, result: ReviewResult, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                result.issue_counts["non_string_field_name"] += 1
                continue
            child_path = path + (key,)
            if child_path not in ALLOWED_PREFIXES:
                result.issue_counts["unexpected_field"] += 1
            audit_raw_free_shape(child, result, child_path)
        return
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, str):
        if value not in SAFE_STRING_VALUES:
            result.issue_counts["unsafe_string_value"] += 1
        return
    result.issue_counts["unsafe_value_type"] += 1


def selected_final_source_state(payload: Mapping[str, Any]) -> str:
    found, value = get_path(payload, ("final_source_state",))
    if (
        found
        and isinstance(value, str)
        and value
        in {
            FINAL_STATE_LEAVE_ENABLED,
            FINAL_STATE_ROLLBACK_COMPLETED,
        }
    ):
        return value
    return "unknown"


def summary_payload(gates: tuple[GateOutcome, ...]) -> dict[str, Any]:
    gate_payloads = {gate.name: gate_payload(gate) for gate in gates}
    failed_gates = tuple(gate.name for gate in gates if not gate.ok)
    issue_counts: Counter[str] = Counter()
    for gate in gates:
        issue_counts.update(gate.issue_counts)
    final_metadata = gate_payloads["final_state"]["metadata"]
    assert isinstance(final_metadata, Mapping)
    status = "ok" if not failed_gates else "failed"
    return {
        "summary_kind": SUMMARY_KIND,
        "status": status,
        "post_enable": {
            "canary_validated": status == "ok",
            "canary_close_ready": status == "ok" and bool(final_metadata["canary_close_ready"]),
            "final_source_state": final_metadata["final_source_state"],
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
    post_enable = payload["post_enable"]
    gates = payload["gates"]
    assert isinstance(post_enable, Mapping)
    assert isinstance(gates, Mapping)
    return "\n".join(
        (
            f"Owner raw D3 post-enable canary: {payload['status']}",
            f"canary_validated={'yes' if post_enable['canary_validated'] else 'no'}",
            f"canary_close_ready={'yes' if post_enable['canary_close_ready'] else 'no'}",
            f"source_enable_summary={gate_status(gates, 'source_enable_summary')}",
            f"post_enable_review={gate_status(gates, 'post_enable_review')}",
            f"final_state={gate_status(gates, 'final_state')}",
            f"final_source_state={post_enable['final_source_state']}",
            "source_enabled_by_script=no",
            "native_auth_added=no",
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


def review_template(final_source_state: str = FINAL_STATE_ROLLBACK_COMPLETED) -> dict[str, Any]:
    if final_source_state not in {FINAL_STATE_LEAVE_ENABLED, FINAL_STATE_ROLLBACK_COMPLETED}:
        final_source_state = FINAL_STATE_ROLLBACK_COMPLETED
    template: dict[str, Any] = {}
    for expectation in REVIEW_EXPECTATIONS:
        set_nested(template, expectation.path, template_value(expectation))
    template["final_source_state"] = final_source_state
    source_state = template.setdefault("source_state", {})
    assert isinstance(source_state, dict)
    source_state["owner_raw_source_remaining_enabled"] = (
        final_source_state == FINAL_STATE_LEAVE_ENABLED
    )
    return template


def template_value(expectation: ReviewExpectation) -> object:
    if expectation.path == ("review_status",):
        return "unreviewed"
    if expectation.expected is True:
        return False
    if expectation.expected is False:
        return False
    return expectation.expected


def set_nested(payload: dict[str, Any], path: tuple[str, ...], value: object) -> None:
    current = payload
    for part in path[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            raise ValueError("template path conflict")
        current = child
    current[path[-1]] = value


def required_field_labels() -> tuple[str, ...]:
    labels = [expectation.label for expectation in REVIEW_EXPECTATIONS]
    labels.extend(
        (
            "final_source_state",
            "source_state.owner_raw_source_remaining_enabled",
        )
    )
    return tuple(labels)


def get_path(payload: Mapping[str, Any], path: tuple[str, ...]) -> tuple[bool, Any]:
    current: Any = payload
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return False, None
        current = current[part]
    return True, current


def load_json_object(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise PostEnableInputError("input could not be read safely") from None
    if not isinstance(payload, Mapping):
        raise PostEnableInputError("input must be a JSON object")
    return payload


def mapping_path(payload: Mapping[str, Any], path: tuple[str, ...]) -> Mapping[str, Any] | None:
    current: Any = payload
    for part in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current if isinstance(current, Mapping) else None


def output_overlap_error(args: argparse.Namespace) -> str | None:
    outputs = (args.summary_json, args.template_json)
    inputs = tuple(
        path
        for path in (args.source_enable_summary_json, args.post_enable_review_json)
        if path is not None
    )
    for output in outputs:
        other_outputs = tuple(path for path in outputs if path is not None and path != output)
        error = output_overlaps_inputs_error(
            output,
            inputs + other_outputs,
            message="summary or template output must not overwrite input artifacts",
        )
        if error:
            return error
    return None


def gate_status(gates: Mapping[str, object], name: str) -> str:
    gate = gates[name]
    assert isinstance(gate, Mapping)
    return safe_status_value(gate["status"])


def safe_status_value(value: object) -> str:
    return source_enable.safe_status_value(value)


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
