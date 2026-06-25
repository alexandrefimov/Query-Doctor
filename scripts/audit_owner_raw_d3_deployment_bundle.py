#!/usr/bin/env python3
"""Run the owner_raw D3 deployment bundle gates without exposing raw evidence."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
import io
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    output_overlaps_inputs_error,
    write_ascii_json_artifact,
)
from scripts import audit_owner_raw_d3_launch_closure as launch_closure  # noqa: E402
from scripts import audit_owner_raw_d3_post_enable as post_enable  # noqa: E402
from scripts import audit_owner_raw_d3_readiness as readiness  # noqa: E402
from scripts import audit_owner_raw_d3_rehearsal as rehearsal  # noqa: E402
from scripts import audit_owner_raw_d3_source_enable as source_enable  # noqa: E402
from scripts import audit_owner_raw_live_front_door_review as live_review  # noqa: E402
from scripts import build_owner_raw_d3_launch_closure_manifest as manifest_builder  # noqa: E402


SUMMARY_KIND = "owner_raw_d3_deployment_bundle_v1"
VERDICT_READY = "ready"
VERDICT_BLOCKED = "blocked"
SAFE_STATUS_VALUES = frozenset(
    {
        "blocked",
        "closed",
        "configured",
        "disabled",
        "enabled",
        "failed",
        "leave_enabled",
        "missing",
        "missing_or_invalid",
        "nonlocal",
        "not_checked",
        "ok",
        "ready",
        "rejected",
        "rollback_completed",
        "unknown",
    }
)
SAFE_ISSUE_RE = re.compile(r"^[a-z0-9_.-]{1,160}$")
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


@dataclass(frozen=True)
class BundleGateOutcome:
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
            "Run the raw-free owner_raw D3 deployment bundle. The command "
            "orchestrates existing front-door review, readiness, rehearsal, "
            "source-enable, post-enable, manifest, and launch-closure gates; it "
            "does not add native auth, start Query Doctor, open cases, read raw "
            "source, or print paths, URLs, users, header names or values, query "
            "ids, credentials, auth material, or raw source."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Ignored local disabled-source Query Doctor web config. The path is never printed.",
    )
    parser.add_argument(
        "--source-enable-config",
        type=Path,
        required=True,
        help="Ignored local source-enabled canary config. The path is never printed.",
    )
    parser.add_argument(
        "--front-door-review-json",
        type=Path,
        required=True,
        help="Raw-free live front-door review summary. The path is never printed.",
    )
    parser.add_argument(
        "--post-enable-review-json",
        type=Path,
        required=True,
        help="Raw-free post-enable canary review summary. The path is never printed.",
    )
    parser.add_argument(
        "--launch-closure-manifest",
        type=Path,
        help=(
            "Optional retained raw-free launch-closure manifest to audit in "
            "addition to the bundle-generated closure. The path is never printed."
        ),
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
        help="Confirm the rehearsal startup includes --disable-owner-raw-source.",
    )
    parser.add_argument(
        "--confirm-source-enable-canary",
        action="store_true",
        help="Confirm this is a controlled canary source-enable step, not broad rollout.",
    )
    parser.add_argument(
        "--confirm-no-disable-owner-raw-source",
        action="store_true",
        help="Confirm the canary startup does not include --disable-owner-raw-source.",
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
        help="Optional raw-free machine deployment-bundle summary. The path is never printed.",
    )
    parser.add_argument("--limit", type=positive_int, default=30, help="Maximum issues to print.")
    parser.add_argument("--dev-sso-proxy-url", default=rehearsal.dev_sso.DEFAULT_PROXY_URL)
    parser.add_argument(
        "--dev-sso-keycloak-discovery-url",
        default=rehearsal.dev_sso.DEFAULT_KEYCLOAK_DISCOVERY_URL,
    )
    parser.add_argument("--dev-sso-upstream-host", default=rehearsal.dev_sso.DEFAULT_UPSTREAM_HOST)
    parser.add_argument(
        "--dev-sso-upstream-port",
        type=int,
        default=rehearsal.dev_sso.DEFAULT_UPSTREAM_PORT,
    )
    parser.add_argument("--dev-sso-username", default=rehearsal.dev_sso.DEFAULT_USERNAME)
    parser.add_argument("--dev-sso-password", default=rehearsal.dev_sso.DEFAULT_PASSWORD)
    parser.add_argument("--dev-sso-timeout-sec", type=float, default=10.0)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    overlap_error = output_overlaps_inputs_error(
        args.summary_json,
        tuple(
            path
            for path in (
                args.config,
                args.source_enable_config,
                args.front_door_review_json,
                args.post_enable_review_json,
                args.launch_closure_manifest,
            )
            if path is not None
        ),
        message="summary output must not overwrite input artifacts",
    )
    if overlap_error:
        print(f"Owner raw D3 deployment bundle: rejected: {overlap_error}", file=sys.stderr)
        return 2

    with TemporaryDirectory(prefix="query-doctor-owner-raw-d3-bundle-") as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        gates = run_bundle_gates(args, tmp_dir=tmp_dir)

    payload = summary_payload(gates)
    if args.summary_json is not None:
        try:
            write_ascii_json_artifact(args.summary_json, payload)
        except OSError:
            print(
                "Owner raw D3 deployment bundle: rejected: summary JSON could not be written",
                file=sys.stderr,
            )
            return 2

    print(format_summary(payload))
    print_issues(payload, limit=args.limit)
    return 0 if payload["status"] == "ok" else 1


def run_bundle_gates(args: argparse.Namespace, *, tmp_dir: Path) -> tuple[BundleGateOutcome, ...]:
    front_door_summary = tmp_dir / "front-door-review-summary.json"
    readiness_summary = tmp_dir / "readiness-summary.json"
    rehearsal_summary = tmp_dir / "rehearsal-summary.json"
    source_enable_summary = tmp_dir / "source-enable-summary.json"
    post_enable_summary = tmp_dir / "post-enable-summary.json"
    generated_manifest = tmp_dir / "launch-closure-manifest.json"
    launch_closure_summary = tmp_dir / "launch-closure-summary.json"
    retained_closure_summary = tmp_dir / "retained-launch-closure-summary.json"

    gates: list[BundleGateOutcome] = [
        run_summary_gate(
            "front_door_review_audit",
            live_review.main,
            [
                "--review-json",
                str(args.front_door_review_json),
                "--summary-json",
                str(front_door_summary),
            ],
            front_door_summary,
            extract_front_door_review_metadata,
            issue_counts_path=("issue_counts",),
        ),
        run_summary_gate(
            "readiness",
            readiness.main,
            readiness_args(args, readiness_summary),
            readiness_summary,
            extract_readiness_metadata,
        ),
        run_summary_gate(
            "rehearsal",
            rehearsal.main,
            rehearsal_args(args, rehearsal_summary),
            rehearsal_summary,
            extract_rehearsal_metadata,
        ),
        run_summary_gate(
            "source_enable",
            source_enable.main,
            source_enable_args(args, rehearsal_summary, source_enable_summary),
            source_enable_summary,
            extract_source_enable_metadata,
        ),
        run_summary_gate(
            "post_enable",
            post_enable.main,
            [
                "--source-enable-summary-json",
                str(source_enable_summary),
                "--post-enable-review-json",
                str(args.post_enable_review_json),
                "--summary-json",
                str(post_enable_summary),
                "--limit",
                str(args.limit),
            ],
            post_enable_summary,
            extract_post_enable_metadata,
        ),
        run_manifest_builder_gate(
            generated_manifest,
            front_door_summary=front_door_summary,
            readiness_summary=readiness_summary,
            rehearsal_summary=rehearsal_summary,
            source_enable_summary=source_enable_summary,
            post_enable_summary=post_enable_summary,
        ),
        run_summary_gate(
            "launch_closure",
            launch_closure.main,
            [
                "--launch-closure-manifest",
                str(generated_manifest),
                "--summary-json",
                str(launch_closure_summary),
                "--limit",
                str(args.limit),
            ],
            launch_closure_summary,
            extract_launch_closure_metadata,
        ),
    ]
    if args.launch_closure_manifest is not None:
        gates.append(
            run_summary_gate(
                "retained_launch_closure_manifest",
                launch_closure.main,
                [
                    "--launch-closure-manifest",
                    str(args.launch_closure_manifest),
                    "--summary-json",
                    str(retained_closure_summary),
                    "--limit",
                    str(args.limit),
                ],
                retained_closure_summary,
                extract_launch_closure_metadata,
            )
        )
    return tuple(gates)


def readiness_args(args: argparse.Namespace, summary: Path) -> list[str]:
    gate_args = [
        "--config",
        str(args.config),
        "--front-door-review-json",
        str(args.front_door_review_json),
        "--summary-json",
        str(summary),
        "--limit",
        str(args.limit),
    ]
    add_common_web_args(gate_args, args)
    if args.disable_owner_raw_source:
        gate_args.append("--disable-owner-raw-source")
    return gate_args


def rehearsal_args(args: argparse.Namespace, summary: Path) -> list[str]:
    gate_args = [
        "--config",
        str(args.config),
        "--front-door-review-json",
        str(args.front_door_review_json),
        "--summary-json",
        str(summary),
        "--limit",
        str(args.limit),
        "--dev-sso-proxy-url",
        str(args.dev_sso_proxy_url),
        "--dev-sso-keycloak-discovery-url",
        str(args.dev_sso_keycloak_discovery_url),
        "--dev-sso-upstream-host",
        str(args.dev_sso_upstream_host),
        "--dev-sso-upstream-port",
        str(args.dev_sso_upstream_port),
        "--dev-sso-username",
        str(args.dev_sso_username),
        "--dev-sso-password",
        str(args.dev_sso_password),
        "--dev-sso-timeout-sec",
        str(args.dev_sso_timeout_sec),
    ]
    add_common_web_args(gate_args, args)
    if args.disable_owner_raw_source:
        gate_args.append("--disable-owner-raw-source")
    return gate_args


def source_enable_args(
    args: argparse.Namespace, rehearsal_summary: Path, summary: Path
) -> list[str]:
    gate_args = [
        "--config",
        str(args.source_enable_config),
        "--rehearsal-summary-json",
        str(rehearsal_summary),
        "--summary-json",
        str(summary),
        "--limit",
        str(args.limit),
    ]
    add_common_web_args(gate_args, args)
    if args.confirm_source_enable_canary:
        gate_args.append("--confirm-source-enable-canary")
    if args.confirm_no_disable_owner_raw_source:
        gate_args.append("--confirm-no-disable-owner-raw-source")
    if args.confirm_no_front_door_or_header_change:
        gate_args.append("--confirm-no-front-door-or-header-change")
    if args.confirm_kill_switch_rollback_plan:
        gate_args.append("--confirm-kill-switch-rollback-plan")
    return gate_args


def add_common_web_args(gate_args: list[str], args: argparse.Namespace) -> None:
    if args.host is not None:
        gate_args.extend(["--host", str(args.host)])
    if args.allow_nonlocal_web_bind:
        gate_args.append("--allow-nonlocal-web-bind")


def run_summary_gate(
    name: str,
    main_func: Callable[[Iterable[str] | None], int],
    argv: list[str],
    summary_path: Path,
    metadata_extractor: Callable[[Mapping[str, Any]], dict[str, object]],
    *,
    issue_counts_path: tuple[str, ...] = ("issues", "counts"),
) -> BundleGateOutcome:
    rc = run_child_main(main_func, argv)
    payload = load_summary(summary_path)
    if payload is None:
        return BundleGateOutcome(
            name,
            "rejected",
            Counter({f"{name}.summary_unavailable": 1}),
            {"raw_values_output": False},
        )

    child_status = safe_status_value(payload.get("status"))
    issues = safe_issue_counts(mapping_value(payload, issue_counts_path), category_prefix=name)
    status = selected_child_status(rc, child_status)
    if rc == 0 and child_status == "ok" and issues:
        status = "failed"
        issues[f"{name}.issue_count_mismatch"] += 1
    if status == "rejected" and not issues:
        issues[f"{name}.rejected"] += 1

    return BundleGateOutcome(
        name,
        status,
        issues,
        metadata_extractor(payload),
    )


def run_manifest_builder_gate(
    manifest_path: Path,
    *,
    front_door_summary: Path,
    readiness_summary: Path,
    rehearsal_summary: Path,
    source_enable_summary: Path,
    post_enable_summary: Path,
) -> BundleGateOutcome:
    rc = run_child_main(
        manifest_builder.main,
        [
            "--redaction-reviewed",
            "--front-door-review-summary-json",
            str(front_door_summary),
            "--readiness-summary-json",
            str(readiness_summary),
            "--rehearsal-summary-json",
            str(rehearsal_summary),
            "--source-enable-summary-json",
            str(source_enable_summary),
            "--post-enable-summary-json",
            str(post_enable_summary),
            "--out",
            str(manifest_path),
        ],
    )
    if rc == 0 and manifest_path.is_file():
        return BundleGateOutcome(
            "launch_closure_manifest_builder",
            "ok",
            Counter(),
            {
                "manifest_reference_mode": "generated",
                "redaction_reviewed": True,
                "raw_values_output": False,
            },
        )
    status = "rejected" if rc >= 2 else "failed"
    return BundleGateOutcome(
        "launch_closure_manifest_builder",
        status,
        Counter({"launch_closure_manifest_builder.rejected": 1}),
        {
            "manifest_reference_mode": "generated",
            "redaction_reviewed": False,
            "raw_values_output": False,
        },
    )


def run_child_main(main_func: Callable[[Iterable[str] | None], int], argv: list[str]) -> int:
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return int(main_func(argv))
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        return 2
    except Exception:  # noqa: BLE001 - fail closed without leaking exception details.
        return 2


def load_summary(path: Path) -> Mapping[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def mapping_value(payload: Mapping[str, Any], path: tuple[str, ...]) -> object:
    current: object = payload
    for part in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def selected_child_status(rc: int, child_status: str) -> str:
    if rc >= 2 or child_status == "rejected":
        return "rejected"
    if child_status == "ok" and rc == 0:
        return "ok"
    if child_status in {"ok", "failed"} or rc == 1:
        return "failed"
    return "rejected"


def extract_front_door_review_metadata(payload: Mapping[str, Any]) -> dict[str, object]:
    return {
        "review_profile": safe_review_profile(payload.get("review_profile")),
        "checked_required_fields": safe_int(payload.get("checked_required_fields")),
        "raw_values_output": False,
    }


def extract_readiness_metadata(payload: Mapping[str, Any]) -> dict[str, object]:
    readiness_payload = mapping_value(payload, ("readiness",))
    if not isinstance(readiness_payload, Mapping):
        readiness_payload = {}
    return {
        "source_enable_ready": readiness_payload.get("source_enable_ready") is True,
        "current_config_owner_raw_source": safe_status_value(
            readiness_payload.get("current_config_owner_raw_source")
        ),
        "native_auth_added": readiness_payload.get("native_auth_added") is True,
        "live_review_required": readiness_payload.get("live_review_required") is True,
        **raw_output_flags(readiness_payload),
    }


def extract_rehearsal_metadata(payload: Mapping[str, Any]) -> dict[str, object]:
    readiness_payload = mapping_value(payload, ("readiness",))
    d3_metadata = mapping_value(payload, ("gates", "d3_readiness", "metadata"))
    if not isinstance(readiness_payload, Mapping):
        readiness_payload = {}
    if not isinstance(d3_metadata, Mapping):
        d3_metadata = {}
    return {
        "rehearsal_complete": readiness_payload.get("rehearsal_complete") is True,
        "source_enable_ready": readiness_payload.get("source_enable_ready") is True,
        "current_config_owner_raw_source": safe_status_value(
            d3_metadata.get("current_config_owner_raw_source")
        ),
        "native_auth_added": readiness_payload.get("native_auth_added") is True,
        "live_review_required": readiness_payload.get("live_review_required") is True,
        **raw_output_flags(readiness_payload),
    }


def extract_source_enable_metadata(payload: Mapping[str, Any]) -> dict[str, object]:
    source_payload = mapping_value(payload, ("source_enable",))
    if not isinstance(source_payload, Mapping):
        source_payload = {}
    return {
        "canary_ready": source_payload.get("canary_ready") is True,
        "previous_owner_raw_source": safe_status_value(
            source_payload.get("previous_owner_raw_source")
        ),
        "planned_owner_raw_source": safe_status_value(
            source_payload.get("planned_owner_raw_source")
        ),
        "source_enabled_by_script": source_payload.get("source_enabled_by_script") is True,
        "native_auth_added": source_payload.get("native_auth_added") is True,
        "live_review_required": source_payload.get("live_review_required") is True,
        **raw_output_flags(source_payload),
    }


def extract_post_enable_metadata(payload: Mapping[str, Any]) -> dict[str, object]:
    post_payload = mapping_value(payload, ("post_enable",))
    if not isinstance(post_payload, Mapping):
        post_payload = {}
    return {
        "canary_validated": post_payload.get("canary_validated") is True,
        "canary_close_ready": post_payload.get("canary_close_ready") is True,
        "final_source_state": safe_final_source_state(post_payload.get("final_source_state")),
        "source_enabled_by_script": post_payload.get("source_enabled_by_script") is True,
        "native_auth_added": post_payload.get("native_auth_added") is True,
        **raw_output_flags(post_payload),
    }


def extract_launch_closure_metadata(payload: Mapping[str, Any]) -> dict[str, object]:
    closure_payload = mapping_value(payload, ("closure",))
    if not isinstance(closure_payload, Mapping):
        closure_payload = {}
    return {
        "launch_closure_ready": closure_payload.get("launch_closure_ready") is True,
        "verdict": safe_status_value(closure_payload.get("verdict")),
        "final_source_state": safe_final_source_state(closure_payload.get("final_source_state")),
        "source_enabled_by_script": closure_payload.get("source_enabled_by_script") is True,
        "native_auth_added": closure_payload.get("native_auth_added") is True,
        "live_review_required": closure_payload.get("live_review_required") is True,
        **raw_output_flags(closure_payload),
    }


def summary_payload(gates: tuple[BundleGateOutcome, ...]) -> dict[str, Any]:
    gate_payloads = {gate.name: gate_payload(gate) for gate in gates}
    failed_gates = tuple(gate.name for gate in gates if not gate.ok)
    issue_counts: Counter[str] = Counter()
    for gate in gates:
        issue_counts.update(gate.issue_counts)
    closure_metadata = gates_by_name(gates).get("launch_closure", {}).get("metadata", {})
    assert isinstance(closure_metadata, Mapping)
    status = "ok" if not failed_gates else "failed"
    final_source_state = (
        safe_final_source_state(closure_metadata.get("final_source_state"))
        if status == "ok"
        else "unknown"
    )
    return {
        "summary_kind": SUMMARY_KIND,
        "status": status,
        "deployment": {
            "bundle_ready": status == "ok",
            "verdict": VERDICT_READY if status == "ok" else VERDICT_BLOCKED,
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


def gate_payload(gate: BundleGateOutcome) -> dict[str, object]:
    return {
        "status": gate.status,
        "issue_counts": counter_payload(gate.issue_counts),
        "metadata": gate.metadata,
    }


def gates_by_name(gates: tuple[BundleGateOutcome, ...]) -> dict[str, Mapping[str, object]]:
    return {gate.name: gate_payload(gate) for gate in gates}


def format_summary(payload: Mapping[str, Any]) -> str:
    deployment = payload["deployment"]
    gates = payload["gates"]
    assert isinstance(deployment, Mapping)
    assert isinstance(gates, Mapping)
    lines = [
        f"Owner raw D3 deployment bundle: {payload['status']}",
        f"bundle_ready={'yes' if deployment['bundle_ready'] else 'no'}",
        f"verdict={deployment['verdict']}",
        f"front_door_review_audit={gate_status(gates, 'front_door_review_audit')}",
        f"readiness={gate_status(gates, 'readiness')}",
        f"rehearsal={gate_status(gates, 'rehearsal')}",
        f"source_enable={gate_status(gates, 'source_enable')}",
        f"post_enable={gate_status(gates, 'post_enable')}",
        f"launch_closure_manifest_builder={gate_status(gates, 'launch_closure_manifest_builder')}",
        f"launch_closure={gate_status(gates, 'launch_closure')}",
    ]
    if "retained_launch_closure_manifest" in gates:
        lines.append(
            "retained_launch_closure_manifest="
            f"{gate_status(gates, 'retained_launch_closure_manifest')}"
        )
    lines.extend(
        [
            f"final_source_state={deployment['final_source_state']}",
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
        ]
    )
    return "\n".join(lines)


def print_issues(payload: Mapping[str, Any], *, limit: int) -> None:
    issues = payload["issues"]
    assert isinstance(issues, Mapping)
    counts = issues["counts"]
    failed_gates = issues["failed_gates"]
    assert isinstance(counts, Mapping)
    assert isinstance(failed_gates, list)
    if not counts and not failed_gates:
        print("Failed gates: none")
        print("Issues: none")
        return
    print("Failed gates:")
    for gate_name in failed_gates[:limit]:
        print(f"- {gate_name}")
    if len(failed_gates) > limit:
        print(f"- additional_failed_gates: {len(failed_gates) - limit}")
    if not counts:
        print("Issues: none")
        return
    print("Issues:")
    for index, category in enumerate(sorted(counts), start=1):
        if index > limit:
            print(f"- additional_issues: {len(counts) - limit}")
            break
        print(f"- {category}: {counts[category]}")


def raw_output_flags(payload: Mapping[str, object]) -> dict[str, object]:
    return {field_name: payload.get(field_name) is True for field_name in RAW_OUTPUT_FIELDS}


def safe_issue_counts(value: object, *, category_prefix: str) -> Counter[str]:
    if not isinstance(value, Mapping):
        return Counter()
    counter: Counter[str] = Counter()
    for category, count in value.items():
        if not isinstance(category, str) or not SAFE_ISSUE_RE.fullmatch(category):
            counter[f"{category_prefix}.unsafe_issue_category"] += 1
            continue
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            counter[f"{category_prefix}.unsafe_issue_count"] += 1
            continue
        if count:
            counter[category] += count
    return counter


def gate_status(gates: Mapping[str, object], name: str) -> str:
    gate = gates[name]
    assert isinstance(gate, Mapping)
    return safe_status_value(gate["status"])


def safe_status_value(value: object) -> str:
    if isinstance(value, str) and value in SAFE_STATUS_VALUES:
        return value
    return "unknown"


def safe_review_profile(value: object) -> str:
    if value == live_review.PROFILE_OWNER_RAW_D3:
        return live_review.PROFILE_OWNER_RAW_D3
    if value == live_review.PROFILE_TRINO_SHARED_HARDENING:
        return live_review.PROFILE_TRINO_SHARED_HARDENING
    return "unknown"


def safe_final_source_state(value: object) -> str:
    if value in {
        post_enable.FINAL_STATE_LEAVE_ENABLED,
        post_enable.FINAL_STATE_ROLLBACK_COMPLETED,
    }:
        return str(value)
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
