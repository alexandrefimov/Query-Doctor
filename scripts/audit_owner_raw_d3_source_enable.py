#!/usr/bin/env python3
"""Audit the final owner_raw D3 source-enable canary step without enabling it."""

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

from query_doctor.config.contract import ConfigError, load_and_validate_config  # noqa: E402
from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    output_overlaps_inputs_error,
    write_ascii_json_artifact,
)
from query_doctor.source_visibility import SOURCE_VISIBILITY_OWNER_RAW  # noqa: E402
from query_doctor.web.cluster_selection import build_web_cluster_configs  # noqa: E402
from query_doctor.web.models import DEFAULT_HOST  # noqa: E402
from query_doctor.web.owner_raw_policy import is_owner_raw_local_bind_host  # noqa: E402
from scripts import audit_owner_raw_d3_rehearsal as rehearsal  # noqa: E402
from scripts import audit_owner_raw_staging_preflight as staging_preflight  # noqa: E402


SUMMARY_KIND = "owner_raw_d3_source_enable_canary_v1"


class SourceEnableInputError(RuntimeError):
    """Raised when inputs cannot be safely audited."""


@dataclass(frozen=True)
class SourceEnableSource:
    source_visibility: str
    bind_scope: str
    viewer_identity_header_configured: bool
    owner_raw_source_explicitly_enabled: bool
    allow_nonlocal_web_bind: bool
    privacy_mode_safe: bool
    redaction_safe: bool


@dataclass
class SourceEnableConfigResult:
    config_checked: bool = False
    source_count: int = 0
    owner_raw_source_count: int = 0
    nonlocal_owner_raw_source_count: int = 0
    local_owner_raw_source_count: int = 0
    viewer_identity_header_configured_count: int = 0
    owner_raw_source_enabled_count: int = 0
    privacy_safe_count: int = 0
    redaction_safe_count: int = 0
    issue_counts: Counter[str] = field(default_factory=Counter)

    @property
    def ok(self) -> bool:
        return not self.issue_counts


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
            "Audit the final owner_raw D3 source-enable canary step using an "
            "already raw-free rehearsal summary and a planned source-enabled "
            "local config. The script never enables raw source and never prints "
            "config paths, summary paths, URLs, users, header names or values, "
            "query ids, auth material, credentials, or raw source."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Ignored local Query Doctor web config planned for source-enable canary.",
    )
    parser.add_argument(
        "--rehearsal-summary-json",
        type=Path,
        required=True,
        help="Raw-free owner_raw D3 rehearsal summary. The path is never printed.",
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
        "--confirm-source-enable-canary",
        action="store_true",
        help="Confirm this is a controlled canary source-enable step, not broad rollout.",
    )
    parser.add_argument(
        "--confirm-no-disable-owner-raw-source",
        action="store_true",
        help="Confirm the planned startup does not include --disable-owner-raw-source.",
    )
    parser.add_argument(
        "--confirm-no-front-door-or-header-change",
        action="store_true",
        help="Confirm the reviewed front door and viewer-header mapping did not change.",
    )
    parser.add_argument(
        "--confirm-kill-switch-rollback-plan",
        action="store_true",
        help="Confirm the operator can immediately re-disable owner_raw source reveal.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Optional raw-free machine summary JSON. The path is never printed.",
    )
    parser.add_argument("--limit", type=positive_int, default=20, help="Maximum issues to print.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    overlap_error = output_overlaps_inputs_error(
        args.summary_json,
        (args.config, args.rehearsal_summary_json),
        message="summary output must not overwrite input artifacts",
    )
    if overlap_error:
        print(f"Owner raw D3 source-enable canary: rejected: {overlap_error}", file=sys.stderr)
        return 2

    rehearsal_gate = rehearsal_summary_gate(args.rehearsal_summary_json)
    config_gate = source_enable_config_gate(args)
    confirmation_gate = operator_confirmation_gate(args)
    alignment_gate = rehearsal_config_alignment_gate(
        rehearsal_gate=rehearsal_gate,
        config_gate=config_gate,
    )
    payload = summary_payload((rehearsal_gate, config_gate, alignment_gate, confirmation_gate))
    if args.summary_json is not None:
        try:
            write_ascii_json_artifact(args.summary_json, payload)
        except OSError:
            print(
                "Owner raw D3 source-enable canary: rejected: summary JSON could not be written",
                file=sys.stderr,
            )
            return 2

    print(format_summary(payload))
    print_issues(payload, limit=args.limit)
    return 0 if payload["status"] == "ok" else 1


def rehearsal_summary_gate(path: Path) -> GateOutcome:
    try:
        payload = load_json_object(path)
    except SourceEnableInputError:
        return GateOutcome(
            "rehearsal_summary",
            "rejected",
            Counter({"rehearsal_summary_input_rejected": 1}),
        )
    issues: Counter[str] = Counter()
    if payload.get("summary_kind") != rehearsal.SUMMARY_KIND:
        issues["rehearsal.invalid_summary_kind"] += 1
    if payload.get("status") != "ok":
        issues["rehearsal.status_not_ok"] += 1

    readiness_payload = mapping_path(payload, ("readiness",))
    if readiness_payload is None:
        issues["rehearsal.readiness_missing"] += 1
        readiness_payload = {}
    if readiness_payload.get("rehearsal_complete") is not True:
        issues["rehearsal.not_complete"] += 1
    if readiness_payload.get("source_enable_ready") is not True:
        issues["rehearsal.source_enable_not_ready"] += 1
    if readiness_payload.get("native_auth_added") is not False:
        issues["rehearsal.native_auth_added"] += 1
    if readiness_payload.get("live_review_required") is not True:
        issues["rehearsal.live_review_not_required"] += 1
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
        if readiness_payload.get(field_name) is not False:
            issues[f"rehearsal.{field_name}"] += 1

    gates_payload = mapping_path(payload, ("gates",))
    if gates_payload is None:
        issues["rehearsal.gates_missing"] += 1
        gates_payload = {}
    required_gates = (
        "dev_sso_keycloak_smoke",
        "live_front_door_review",
        "staging_config_preflight",
        "d3_readiness",
    )
    for gate_name in required_gates:
        gate_payload = mapping_path(gates_payload, (gate_name,))
        if gate_payload is None:
            issues[f"rehearsal.{gate_name}_missing"] += 1
        elif gate_payload.get("status") != "ok":
            issues[f"rehearsal.{gate_name}_not_ok"] += 1

    issues_payload = mapping_path(payload, ("issues",))
    if issues_payload is None:
        issues["rehearsal.issues_missing"] += 1
    elif issues_payload.get("counts") != {} or issues_payload.get("failed_gates") != []:
        issues["rehearsal.issues_not_empty"] += 1

    staging_metadata = (
        mapping_path(
            gates_payload,
            ("staging_config_preflight", "metadata"),
        )
        or {}
    )
    d3_metadata = mapping_path(gates_payload, ("d3_readiness", "metadata")) or {}
    previous_source = safe_status_value(d3_metadata.get("current_config_owner_raw_source"))
    if previous_source != "disabled":
        issues["rehearsal.previous_source_not_disabled"] += 1
    owner_raw_source_count = safe_int(staging_metadata.get("owner_raw_source_count"))
    nonlocal_owner_raw_source_count = safe_int(
        staging_metadata.get("nonlocal_owner_raw_source_count")
    )
    if owner_raw_source_count < 1:
        issues["rehearsal.owner_raw_source_missing"] += 1
    if nonlocal_owner_raw_source_count < 1:
        issues["rehearsal.nonlocal_owner_raw_source_missing"] += 1

    return GateOutcome(
        "rehearsal_summary",
        "ok" if not issues else "failed",
        issues,
        {
            "previous_owner_raw_source": previous_source,
            "owner_raw_source_count": owner_raw_source_count,
            "nonlocal_owner_raw_source_count": nonlocal_owner_raw_source_count,
            "viewer_identity_header": safe_status_value(
                staging_metadata.get("viewer_identity_header")
            ),
            "raw_values_output": False,
        },
    )


def source_enable_config_gate(args: argparse.Namespace) -> GateOutcome:
    result = SourceEnableConfigResult(config_checked=True)
    try:
        audit_source_enable_config(result, args)
    except SourceEnableInputError:
        return GateOutcome(
            "source_enable_config",
            "rejected",
            Counter({"source_enable_config_input_rejected": 1}),
        )
    return GateOutcome(
        "source_enable_config",
        "ok" if result.ok else "failed",
        Counter({f"config.{key}": count for key, count in result.issue_counts.items()}),
        {
            "source_count": result.source_count,
            "owner_raw_source_count": result.owner_raw_source_count,
            "nonlocal_owner_raw_source_count": result.nonlocal_owner_raw_source_count,
            "local_owner_raw_source_count": result.local_owner_raw_source_count,
            "viewer_identity_header": viewer_header_status(result),
            "owner_raw_source": owner_raw_source_status(result),
            "privacy_safe_count": result.privacy_safe_count,
            "redaction_safe_count": result.redaction_safe_count,
        },
    )


def audit_source_enable_config(result: SourceEnableConfigResult, args: argparse.Namespace) -> None:
    try:
        config = load_and_validate_config(
            args.config,
            cwd=ROOT,
            repo_root=ROOT,
            use_repo_default=False,
            warn_legacy=False,
        )
        values = config.values
        clusters = build_web_cluster_configs(values)
    except (ConfigError, OSError, ValueError):
        raise SourceEnableInputError("config input could not be audited safely") from None

    host = args.host or staging_preflight.optional_string(values, "host") or DEFAULT_HOST
    bind_scope = "local" if is_owner_raw_local_bind_host(host) else "nonlocal"
    viewer_header_configured = staging_preflight.viewer_identity_header_is_configured(values)
    owner_raw_source_enabled = values.get("owner_raw_source_enabled") is True
    privacy_mode_safe = staging_preflight.optional_bool(values, "privacy_mode", default=True)
    redaction_safe = staging_preflight.redaction_settings_safe(
        values,
        privacy_mode_safe=privacy_mode_safe,
    )
    if clusters:
        sources = tuple(
            SourceEnableSource(
                source_visibility=cluster.source_visibility,
                bind_scope=bind_scope,
                viewer_identity_header_configured=viewer_header_configured,
                owner_raw_source_explicitly_enabled=owner_raw_source_enabled,
                allow_nonlocal_web_bind=bool(args.allow_nonlocal_web_bind),
                privacy_mode_safe=privacy_mode_safe,
                redaction_safe=redaction_safe,
            )
            for cluster in clusters
        )
    else:
        sources = (
            SourceEnableSource(
                source_visibility=staging_preflight.optional_string(values, "source_visibility")
                or "safe",
                bind_scope=bind_scope,
                viewer_identity_header_configured=viewer_header_configured,
                owner_raw_source_explicitly_enabled=owner_raw_source_enabled,
                allow_nonlocal_web_bind=bool(args.allow_nonlocal_web_bind),
                privacy_mode_safe=privacy_mode_safe,
                redaction_safe=redaction_safe,
            ),
        )

    for source in sources:
        result.source_count += 1
        if source.source_visibility != SOURCE_VISIBILITY_OWNER_RAW:
            continue
        result.owner_raw_source_count += 1
        if source.bind_scope == "nonlocal":
            result.nonlocal_owner_raw_source_count += 1
        else:
            result.local_owner_raw_source_count += 1
        if source.viewer_identity_header_configured:
            result.viewer_identity_header_configured_count += 1
        if source.owner_raw_source_explicitly_enabled:
            result.owner_raw_source_enabled_count += 1
        if source.privacy_mode_safe:
            result.privacy_safe_count += 1
        if source.redaction_safe:
            result.redaction_safe_count += 1
        audit_source_enable_source(result, source)
    if result.owner_raw_source_count == 0:
        result.issue_counts["owner_raw_source_visibility_missing"] += 1
    if result.nonlocal_owner_raw_source_count == 0:
        result.issue_counts["nonlocal_owner_raw_source_missing"] += 1


def audit_source_enable_source(
    result: SourceEnableConfigResult,
    source: SourceEnableSource,
) -> None:
    if not source.viewer_identity_header_configured:
        result.issue_counts["viewer_identity_header_missing"] += 1
    if not source.owner_raw_source_explicitly_enabled:
        result.issue_counts["owner_raw_source_not_explicitly_enabled"] += 1
    if source.bind_scope == "nonlocal" and not source.allow_nonlocal_web_bind:
        result.issue_counts["nonlocal_web_bind_not_explicitly_reviewed"] += 1
    if not source.privacy_mode_safe:
        result.issue_counts["privacy_mode_explicitly_disabled"] += 1
    if not source.redaction_safe:
        result.issue_counts["redaction_explicitly_disabled"] += 1


def operator_confirmation_gate(args: argparse.Namespace) -> GateOutcome:
    issues: Counter[str] = Counter()
    if not args.confirm_source_enable_canary:
        issues["operator.source_enable_canary_confirmation_missing"] += 1
    if not args.confirm_no_disable_owner_raw_source:
        issues["operator.no_disable_owner_raw_source_confirmation_missing"] += 1
    if not args.confirm_no_front_door_or_header_change:
        issues["operator.no_front_door_or_header_change_confirmation_missing"] += 1
    if not args.confirm_kill_switch_rollback_plan:
        issues["operator.kill_switch_rollback_plan_confirmation_missing"] += 1
    return GateOutcome(
        "operator_confirmation",
        "ok" if not issues else "failed",
        issues,
        {
            "source_enable_canary_confirmed": bool(args.confirm_source_enable_canary),
            "no_disable_owner_raw_source_confirmed": bool(args.confirm_no_disable_owner_raw_source),
            "no_front_door_or_header_change_confirmed": bool(
                args.confirm_no_front_door_or_header_change
            ),
            "kill_switch_rollback_plan_confirmed": bool(args.confirm_kill_switch_rollback_plan),
        },
    )


def rehearsal_config_alignment_gate(
    *,
    rehearsal_gate: GateOutcome,
    config_gate: GateOutcome,
) -> GateOutcome:
    issues: Counter[str] = Counter()
    previous_owner_raw_source = safe_status_value(
        rehearsal_gate.metadata.get("previous_owner_raw_source")
    )
    planned_owner_raw_source = safe_status_value(config_gate.metadata.get("owner_raw_source"))
    if previous_owner_raw_source != "disabled":
        issues["alignment.previous_source_not_disabled"] += 1
    if planned_owner_raw_source != "enabled":
        issues["alignment.planned_source_not_enabled"] += 1

    rehearsal_owner_count = safe_int(rehearsal_gate.metadata.get("owner_raw_source_count"))
    planned_owner_count = safe_int(config_gate.metadata.get("owner_raw_source_count"))
    if rehearsal_owner_count != planned_owner_count:
        issues["alignment.owner_raw_source_count_changed"] += 1
    rehearsal_nonlocal_count = safe_int(
        rehearsal_gate.metadata.get("nonlocal_owner_raw_source_count")
    )
    planned_nonlocal_count = safe_int(config_gate.metadata.get("nonlocal_owner_raw_source_count"))
    if rehearsal_nonlocal_count != planned_nonlocal_count:
        issues["alignment.nonlocal_owner_raw_source_count_changed"] += 1
    if safe_status_value(config_gate.metadata.get("viewer_identity_header")) != "configured":
        issues["alignment.viewer_identity_header_not_configured"] += 1
    return GateOutcome(
        "rehearsal_config_alignment",
        "ok" if not issues else "failed",
        issues,
        {
            "previous_owner_raw_source": previous_owner_raw_source,
            "planned_owner_raw_source": planned_owner_raw_source,
            "owner_raw_source_count_match": rehearsal_owner_count == planned_owner_count,
            "nonlocal_owner_raw_source_count_match": (
                rehearsal_nonlocal_count == planned_nonlocal_count
            ),
        },
    )


def summary_payload(gates: tuple[GateOutcome, ...]) -> dict[str, Any]:
    gate_payloads = {gate.name: gate_payload(gate) for gate in gates}
    failed_gates = tuple(gate.name for gate in gates if not gate.ok)
    issue_counts: Counter[str] = Counter()
    for gate in gates:
        issue_counts.update(gate.issue_counts)
    alignment_metadata = gate_payloads["rehearsal_config_alignment"]["metadata"]
    assert isinstance(alignment_metadata, Mapping)
    status = "ok" if not failed_gates else "failed"
    return {
        "summary_kind": SUMMARY_KIND,
        "status": status,
        "source_enable": {
            "canary_ready": status == "ok",
            "source_enabled_by_script": False,
            "native_auth_added": False,
            "live_review_required": True,
            "previous_owner_raw_source": alignment_metadata["previous_owner_raw_source"],
            "planned_owner_raw_source": alignment_metadata["planned_owner_raw_source"],
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
    source_enable = payload["source_enable"]
    gates = payload["gates"]
    assert isinstance(source_enable, Mapping)
    assert isinstance(gates, Mapping)
    return "\n".join(
        (
            f"Owner raw D3 source-enable canary: {payload['status']}",
            f"canary_ready={'yes' if source_enable['canary_ready'] else 'no'}",
            f"rehearsal_summary={gate_status(gates, 'rehearsal_summary')}",
            f"source_enable_config={gate_status(gates, 'source_enable_config')}",
            f"rehearsal_config_alignment={gate_status(gates, 'rehearsal_config_alignment')}",
            f"operator_confirmation={gate_status(gates, 'operator_confirmation')}",
            f"previous_owner_raw_source={source_enable['previous_owner_raw_source']}",
            f"planned_owner_raw_source={source_enable['planned_owner_raw_source']}",
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


def load_json_object(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise SourceEnableInputError("input could not be read safely") from None
    if not isinstance(payload, Mapping):
        raise SourceEnableInputError("input must be a JSON object")
    return payload


def mapping_path(payload: Mapping[str, Any], path: tuple[str, ...]) -> Mapping[str, Any] | None:
    current: Any = payload
    for part in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current if isinstance(current, Mapping) else None


def viewer_header_status(result: SourceEnableConfigResult) -> str:
    if result.owner_raw_source_count == 0:
        return "not_checked"
    if result.viewer_identity_header_configured_count == result.owner_raw_source_count:
        return "configured"
    return "missing_or_invalid"


def owner_raw_source_status(result: SourceEnableConfigResult) -> str:
    if result.owner_raw_source_count == 0:
        return "not_checked"
    if result.owner_raw_source_enabled_count == result.owner_raw_source_count:
        return "enabled"
    return "disabled"


def gate_status(gates: Mapping[str, object], name: str) -> str:
    gate = gates[name]
    assert isinstance(gate, Mapping)
    return safe_status_value(gate["status"])


def safe_status_value(value: object) -> str:
    return rehearsal.safe_status_value(value)


def safe_int(value: object) -> int:
    return rehearsal.safe_int(value)


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
