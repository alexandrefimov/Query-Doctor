#!/usr/bin/env python3
"""Audit release readiness for owner_raw behind a trusted SSO/auth proxy."""

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
from scripts import audit_owner_raw_d3_deployment_bundle as bundle  # noqa: E402
from scripts import audit_owner_raw_d3_post_enable as post_enable  # noqa: E402
from scripts import audit_owner_raw_live_front_door_review as live_review  # noqa: E402


SUMMARY_KIND = "owner_raw_sso_proxy_support_readiness_v1"
SUPPORT_CLAIM = "deployment_behind_trusted_sso_auth_proxy_via_viewer_identity_header"
DEPLOYMENT_CONTRACT = "trusted_auth_proxy_viewer_identity_header"
REQUIRED_GATES = (
    "front_door_review_audit",
    "readiness",
    "rehearsal",
    "source_enable",
    "post_enable",
    "launch_closure_manifest_builder",
    "launch_closure",
)
OPTIONAL_GATES = ("retained_launch_closure_manifest",)
RAW_OUTPUT_FIELDS = bundle.RAW_OUTPUT_FIELDS
SAFE_ISSUE_RE = re.compile(r"^[a-z0-9_.-]{1,160}$")
SAFE_FIELD_NAMES = frozenset(
    {
        "auth_material_printed",
        "bundle_ready",
        "canary_close_ready",
        "canary_ready",
        "canary_validated",
        "checked_required_fields",
        "counts",
        "current_config_owner_raw_source",
        "deployment",
        "failed_gates",
        "final_source_state",
        "front_door_review_audit",
        "gates",
        "header_names_printed",
        "header_values_printed",
        "issues",
        "issue_counts",
        "launch_closure",
        "launch_closure_manifest_builder",
        "launch_closure_ready",
        "live_review_required",
        "manifest_reference_mode",
        "metadata",
        "native_auth_added",
        "paths_printed",
        "planned_owner_raw_source",
        "post_enable",
        "previous_owner_raw_source",
        "query_ids_printed",
        "raw_source_printed",
        "raw_values_output",
        "readiness",
        "redaction_reviewed",
        "rehearsal",
        "rehearsal_complete",
        "retained_launch_closure_manifest",
        "review_profile",
        "source_enable",
        "source_enabled_by_script",
        "source_enable_ready",
        "status",
        "summary_kind",
        "urls_printed",
        "users_printed",
        "verdict",
    }
)
SAFE_STRING_VALUES = frozenset(
    {
        bundle.SUMMARY_KIND,
        bundle.VERDICT_READY,
        bundle.VERDICT_BLOCKED,
        bundle.launch_closure.VERDICT_CLOSED,
        bundle.launch_closure.VERDICT_BLOCKED,
        post_enable.FINAL_STATE_LEAVE_ENABLED,
        post_enable.FINAL_STATE_ROLLBACK_COMPLETED,
        live_review.PROFILE_OWNER_RAW_D3,
        "blocked",
        "disabled",
        "enabled",
        "failed",
        "generated",
        "ok",
        "ready",
        "rejected",
        "unknown",
        *REQUIRED_GATES,
        *OPTIONAL_GATES,
    }
)


class SupportReadinessInputError(RuntimeError):
    """Raised when retained support-readiness input cannot be safely read."""


@dataclass(frozen=True)
class SupportReadinessResult:
    status: str
    issue_counts: Counter[str] = field(default_factory=Counter)
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok" and not self.issue_counts


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit whether Query Doctor can make the release-facing support "
            "claim for deployment behind a trusted SSO/auth proxy via "
            "viewer_identity_header. The command reads only an already raw-free "
            "owner_raw D3 deployment-bundle summary and prints only safe status "
            "labels and issue categories. It does not add native SSO, contact a "
            "proxy, perform authentication, start Query Doctor, open cases, read "
            "source text, or print paths, URLs, users, header names or values, "
            "query ids, credentials, auth material, or raw source."
        )
    )
    parser.add_argument(
        "--deployment-bundle-summary-json",
        required=True,
        type=Path,
        help="Raw-free owner_raw D3 deployment bundle summary. The path is never printed.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Optional raw-free support-readiness summary JSON. The path is never printed.",
    )
    parser.add_argument(
        "--require-source-left-enabled",
        action="store_true",
        help=(
            "Require the canary closure to finish with owner_raw source left "
            "enabled. By default both leave_enabled and rollback_completed are "
            "accepted because both prove the reviewed support path and rollback."
        ),
    )
    parser.add_argument("--limit", type=positive_int, default=24, help="Maximum issues to print.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    overlap_error = output_overlaps_inputs_error(
        args.summary_json,
        (args.deployment_bundle_summary_json,),
        message="summary output must not overwrite input artifacts",
    )
    if overlap_error:
        print(
            f"Owner raw SSO proxy support readiness: rejected: {overlap_error}",
            file=sys.stderr,
        )
        return 2
    try:
        payload = load_json_object(args.deployment_bundle_summary_json)
    except SupportReadinessInputError:
        result = SupportReadinessResult(
            "rejected",
            Counter({"deployment_bundle_summary.input_rejected": 1}),
            default_metadata(),
        )
    else:
        result = audit_support_readiness(
            payload,
            require_source_left_enabled=args.require_source_left_enabled,
        )
    summary = summary_payload(result)
    if args.summary_json is not None:
        try:
            write_ascii_json_artifact(args.summary_json, summary)
        except OSError:
            print(
                "Owner raw SSO proxy support readiness: rejected: summary JSON could not be written",
                file=sys.stderr,
            )
            return 2
    print(format_summary(summary))
    print_issues(summary, limit=args.limit)
    return 0 if result.ok else 1


def audit_support_readiness(
    payload: Mapping[str, Any],
    *,
    require_source_left_enabled: bool,
) -> SupportReadinessResult:
    issues: Counter[str] = Counter()
    audit_raw_free_shape(payload, issues, prefix="deployment_bundle_summary")
    if payload.get("summary_kind") != bundle.SUMMARY_KIND:
        issues["deployment_bundle_summary.invalid_summary_kind"] += 1
    if payload.get("status") != "ok":
        issues["deployment_bundle_summary.status_not_ok"] += 1

    deployment = mapping_path(payload, ("deployment",))
    if deployment is None:
        issues["deployment.missing"] += 1
        deployment = {}
    gates = mapping_path(payload, ("gates",))
    if gates is None:
        issues["gates.missing"] += 1
        gates = {}
    require_deployment_contract(
        deployment,
        issues,
        require_source_left_enabled=require_source_left_enabled,
    )
    require_required_gates(gates, issues)
    require_gate_metadata(
        gates,
        issues,
        require_source_left_enabled=require_source_left_enabled,
    )
    require_empty_issues(payload, issues)

    return SupportReadinessResult(
        "ok" if not issues else "failed",
        issues,
        {
            "deployment_bundle": safe_status_value(payload.get("status")),
            "bundle_ready": deployment.get("bundle_ready") is True,
            "verdict": safe_status_value(deployment.get("verdict")),
            "final_source_state": selected_final_source_state(deployment.get("final_source_state")),
            "source_enabled_by_script": deployment.get("source_enabled_by_script") is True,
            "native_auth_added": deployment.get("native_auth_added") is True,
            "live_review_required": deployment.get("live_review_required") is True,
            "required_gate_count": len(REQUIRED_GATES),
            "ok_required_gate_count": count_ok_required_gates(gates),
            **raw_output_flags(deployment),
        },
    )


def require_deployment_contract(
    deployment: Mapping[str, Any],
    issues: Counter[str],
    *,
    require_source_left_enabled: bool,
) -> None:
    expected = {
        "bundle_ready": True,
        "verdict": bundle.VERDICT_READY,
        "source_enabled_by_script": False,
        "native_auth_added": False,
        "live_review_required": True,
    }
    for field_name, expected_value in expected.items():
        if deployment.get(field_name) != expected_value:
            issues[f"deployment.{field_name}_invalid"] += 1
    final_source_state = selected_final_source_state(deployment.get("final_source_state"))
    if final_source_state == "unknown":
        issues["deployment.invalid_final_source_state"] += 1
    elif (
        require_source_left_enabled and final_source_state != post_enable.FINAL_STATE_LEAVE_ENABLED
    ):
        issues["deployment.final_source_state_not_left_enabled"] += 1
    require_false_flags(deployment, RAW_OUTPUT_FIELDS, issues, category_prefix="deployment")


def require_required_gates(gates: Mapping[str, Any], issues: Counter[str]) -> None:
    for gate_name in REQUIRED_GATES:
        gate = mapping_path(gates, (gate_name,))
        if gate is None:
            issues[f"gate.{gate_name}_missing"] += 1
        elif gate.get("status") != "ok":
            issues[f"gate.{gate_name}_not_ok"] += 1
    for gate_name in OPTIONAL_GATES:
        gate = mapping_path(gates, (gate_name,))
        if gate is not None and gate.get("status") != "ok":
            issues[f"gate.{gate_name}_not_ok"] += 1


def require_gate_metadata(
    gates: Mapping[str, Any],
    issues: Counter[str],
    *,
    require_source_left_enabled: bool,
) -> None:
    front_door = gate_metadata(gates, "front_door_review_audit")
    if front_door.get("review_profile") != live_review.PROFILE_OWNER_RAW_D3:
        issues["metadata.front_door_review_audit.invalid_review_profile"] += 1
    required_field_count = len(live_review.required_field_labels(live_review.PROFILE_OWNER_RAW_D3))
    if safe_nonnegative_int(front_door.get("checked_required_fields")) < required_field_count:
        issues["metadata.front_door_review_audit.required_fields_not_checked"] += 1
    require_metadata_flags(
        gate_metadata(gates, "readiness"),
        issues,
        gate_name="readiness",
        expected={
            "source_enable_ready": True,
            "current_config_owner_raw_source": "disabled",
            "native_auth_added": False,
            "live_review_required": True,
        },
    )
    require_metadata_flags(
        gate_metadata(gates, "rehearsal"),
        issues,
        gate_name="rehearsal",
        expected={
            "rehearsal_complete": True,
            "source_enable_ready": True,
            "current_config_owner_raw_source": "disabled",
            "native_auth_added": False,
            "live_review_required": True,
        },
    )
    require_metadata_flags(
        gate_metadata(gates, "source_enable"),
        issues,
        gate_name="source_enable",
        expected={
            "canary_ready": True,
            "previous_owner_raw_source": "disabled",
            "planned_owner_raw_source": "enabled",
            "source_enabled_by_script": False,
            "native_auth_added": False,
            "live_review_required": True,
        },
    )
    post_enable_metadata = gate_metadata(gates, "post_enable")
    require_metadata_flags(
        post_enable_metadata,
        issues,
        gate_name="post_enable",
        expected={
            "canary_validated": True,
            "canary_close_ready": True,
            "source_enabled_by_script": False,
            "native_auth_added": False,
        },
    )
    require_final_source_state(
        post_enable_metadata,
        issues,
        category_prefix="metadata.post_enable",
        require_source_left_enabled=require_source_left_enabled,
    )
    manifest_builder_metadata = gate_metadata(gates, "launch_closure_manifest_builder")
    require_metadata_flags(
        manifest_builder_metadata,
        issues,
        gate_name="launch_closure_manifest_builder",
        expected={
            "manifest_reference_mode": "generated",
            "redaction_reviewed": True,
        },
        raw_output_fields=("raw_values_output",),
    )
    launch_closure_metadata = gate_metadata(gates, "launch_closure")
    require_metadata_flags(
        launch_closure_metadata,
        issues,
        gate_name="launch_closure",
        expected={
            "launch_closure_ready": True,
            "verdict": bundle.launch_closure.VERDICT_CLOSED,
            "source_enabled_by_script": False,
            "native_auth_added": False,
            "live_review_required": True,
        },
    )
    require_final_source_state(
        launch_closure_metadata,
        issues,
        category_prefix="metadata.launch_closure",
        require_source_left_enabled=require_source_left_enabled,
    )


def require_metadata_flags(
    metadata: Mapping[str, Any],
    issues: Counter[str],
    *,
    gate_name: str,
    expected: Mapping[str, object],
    raw_output_fields: Iterable[str] = RAW_OUTPUT_FIELDS,
) -> None:
    for field_name, expected_value in expected.items():
        if metadata.get(field_name) != expected_value:
            issues[f"metadata.{gate_name}.{field_name}_invalid"] += 1
    require_false_flags(
        metadata, raw_output_fields, issues, category_prefix=f"metadata.{gate_name}"
    )


def require_final_source_state(
    metadata: Mapping[str, Any],
    issues: Counter[str],
    *,
    category_prefix: str,
    require_source_left_enabled: bool,
) -> None:
    final_source_state = selected_final_source_state(metadata.get("final_source_state"))
    if final_source_state == "unknown":
        issues[f"{category_prefix}.invalid_final_source_state"] += 1
    elif (
        require_source_left_enabled and final_source_state != post_enable.FINAL_STATE_LEAVE_ENABLED
    ):
        issues[f"{category_prefix}.final_source_state_not_left_enabled"] += 1


def require_empty_issues(payload: Mapping[str, Any], issues: Counter[str]) -> None:
    issues_payload = mapping_path(payload, ("issues",))
    if issues_payload is None:
        issues["deployment_bundle_summary.issues_missing"] += 1
        return
    counts = issues_payload.get("counts")
    if not isinstance(counts, Mapping):
        issues["deployment_bundle_summary.issue_counts_missing"] += 1
    elif counts:
        issues["deployment_bundle_summary.issues_not_empty"] += 1
    failed_gates = issues_payload.get("failed_gates")
    if failed_gates != []:
        issues["deployment_bundle_summary.failed_gates_not_empty"] += 1


def summary_payload(result: SupportReadinessResult) -> dict[str, object]:
    support_ready = result.ok
    return {
        "summary_kind": SUMMARY_KIND,
        "status": "ok" if support_ready else "failed",
        "support": {
            "support_ready": support_ready,
            "support_claim": SUPPORT_CLAIM,
            "deployment_contract": DEPLOYMENT_CONTRACT,
            "deployment_bundle": result.metadata.get("deployment_bundle", "unknown"),
            "bundle_ready": result.metadata.get("bundle_ready") is True,
            "verdict": result.metadata.get("verdict", "unknown"),
            "final_source_state": result.metadata.get("final_source_state", "unknown"),
            "required_gate_count": safe_nonnegative_int(result.metadata.get("required_gate_count")),
            "ok_required_gate_count": safe_nonnegative_int(
                result.metadata.get("ok_required_gate_count")
            ),
            "native_sso_added": False,
            "native_auth_added": result.metadata.get("native_auth_added") is True,
            "live_review_required": result.metadata.get("live_review_required") is True,
            "source_enabled_by_script": result.metadata.get("source_enabled_by_script") is True,
            "requires_trusted_front_door": True,
            "requires_inbound_header_stripping": True,
            "requires_exactly_one_normalized_viewer_header": True,
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
        "issues": {
            "failed_gates": [] if support_ready else ["sso_proxy_support_readiness"],
            "counts": counter_payload(result.issue_counts),
        },
    }


def format_summary(payload: Mapping[str, Any]) -> str:
    support = mapping_path(payload, ("support",)) or {}
    return "\n".join(
        (
            f"Owner raw SSO proxy support readiness: {payload.get('status', 'failed')}",
            f"support_ready={'yes' if support.get('support_ready') is True else 'no'}",
            f"support_claim={safe_output_value(support.get('support_claim'))}",
            f"deployment_contract={safe_output_value(support.get('deployment_contract'))}",
            f"deployment_bundle={safe_output_value(support.get('deployment_bundle'))}",
            f"bundle_ready={'yes' if support.get('bundle_ready') is True else 'no'}",
            f"verdict={safe_output_value(support.get('verdict'))}",
            f"final_source_state={safe_output_value(support.get('final_source_state'))}",
            f"required_gates={safe_nonnegative_int(support.get('ok_required_gate_count'))}/"
            f"{safe_nonnegative_int(support.get('required_gate_count'))}",
            "native_sso_added=no",
            f"native_auth_added={'yes' if support.get('native_auth_added') is True else 'no'}",
            f"live_review_required={'yes' if support.get('live_review_required') is True else 'no'}",
            f"source_enabled_by_script="
            f"{'yes' if support.get('source_enabled_by_script') is True else 'no'}",
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
    issues = mapping_path(payload, ("issues",)) or {}
    counts = issues.get("counts")
    failed_gates = issues.get("failed_gates")
    if not isinstance(counts, Mapping):
        counts = {}
    if not isinstance(failed_gates, list):
        failed_gates = []
    if not counts and not failed_gates:
        print("Failed gates: none")
        print("Issues: none")
        return
    print("Failed gates:")
    for gate_name in failed_gates[:limit]:
        if isinstance(gate_name, str):
            print(f"- {safe_issue_text(gate_name)}")
    if len(failed_gates) > limit:
        print(f"- additional_failed_gates: {len(failed_gates) - limit}")
    if not counts:
        print("Issues: none")
        return
    print("Issues:")
    for index, category in enumerate(sorted(str(key) for key in counts), start=1):
        if index > limit:
            print(f"- additional_issues: {len(counts) - limit}")
            break
        print(f"- {safe_issue_text(category)}: {safe_nonnegative_int(counts.get(category))}")


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


def gate_metadata(gates: Mapping[str, Any], gate_name: str) -> Mapping[str, Any]:
    metadata = mapping_path(gates, (gate_name, "metadata"))
    return metadata or {}


def raw_output_flags(payload: Mapping[str, Any]) -> dict[str, object]:
    return {field_name: payload.get(field_name) is True for field_name in RAW_OUTPUT_FIELDS}


def mapping_path(payload: Mapping[str, Any], path: tuple[str, ...]) -> Mapping[str, Any] | None:
    current: Any = payload
    for part in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current if isinstance(current, Mapping) else None


def load_json_object(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise SupportReadinessInputError("input could not be read safely") from None
    if not isinstance(payload, Mapping):
        raise SupportReadinessInputError("input must be a JSON object") from None
    return payload


def count_ok_required_gates(gates: Mapping[str, Any]) -> int:
    return sum(
        1
        for gate_name in REQUIRED_GATES
        if (mapping_path(gates, (gate_name,)) or {}).get("status") == "ok"
    )


def selected_final_source_state(value: object) -> str:
    if value in {
        post_enable.FINAL_STATE_LEAVE_ENABLED,
        post_enable.FINAL_STATE_ROLLBACK_COMPLETED,
    }:
        return str(value)
    return "unknown"


def safe_status_value(value: object) -> str:
    if isinstance(value, str) and value in SAFE_STRING_VALUES:
        return value
    return "unknown"


def safe_output_value(value: object) -> str:
    if isinstance(value, str) and value in SAFE_STRING_VALUES | {
        SUPPORT_CLAIM,
        DEPLOYMENT_CONTRACT,
    }:
        return value
    return "unknown"


def safe_issue_text(value: str) -> str:
    return "".join(char if char.isascii() and char.isprintable() else "_" for char in value)[:160]


def safe_nonnegative_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def default_metadata() -> dict[str, object]:
    return {
        "deployment_bundle": "rejected",
        "bundle_ready": False,
        "verdict": "unknown",
        "final_source_state": "unknown",
        "source_enabled_by_script": False,
        "native_auth_added": False,
        "live_review_required": True,
        "required_gate_count": len(REQUIRED_GATES),
        "ok_required_gate_count": 0,
        "raw_values_output": False,
        "paths_printed": False,
        "header_names_printed": False,
        "header_values_printed": False,
        "users_printed": False,
        "urls_printed": False,
        "query_ids_printed": False,
        "auth_material_printed": False,
        "raw_source_printed": False,
    }


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
