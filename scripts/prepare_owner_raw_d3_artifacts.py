#!/usr/bin/env python3
"""Prepare a local owner_raw D3 artifact workspace without printing raw details."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
import io
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.safety.handoff_artifacts import write_ascii_json_artifact  # noqa: E402
from scripts import audit_owner_raw_d3_deployment_bundle as bundle  # noqa: E402
from scripts import audit_owner_raw_d3_post_enable as post_enable  # noqa: E402
from scripts import audit_owner_raw_sso_proxy_support_readiness as support_readiness  # noqa: E402
from scripts import audit_owner_raw_live_front_door_review as live_review  # noqa: E402


SAFE_STATUS_VALUES = frozenset(
    {
        "blocked",
        "failed",
        "ok",
        "prepared",
        "ready",
        "rejected",
        "leave_enabled",
        "rollback_completed",
        "skipped",
        "unknown",
    }
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


@dataclass(frozen=True)
class WorkspacePaths:
    disabled_config: Path
    source_enabled_config: Path
    front_door_review: Path
    post_enable_review: Path
    operator_checklist: Path
    bundle_summary: Path
    support_readiness_summary: Path


@dataclass(frozen=True)
class ArtifactWriteResult:
    label: str
    status: str


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create or preserve a local owner_raw D3 artifact workspace and run "
            "the raw-free deployment bundle over it. The command writes only "
            "ignored local scaffold files chosen by the operator, preserves "
            "existing review evidence by default, and never prints artifact "
            "paths, URLs, users, header names or values, query ids, credentials, "
            "auth material, or raw source."
        )
    )
    parser.add_argument(
        "--artifact-dir",
        required=True,
        type=Path,
        help="Ignored local directory for D3 artifact templates. The path is never printed.",
    )
    parser.add_argument(
        "--confirm-local-ignored-artifact-dir",
        action="store_true",
        help="Confirm the artifact directory is local, ignored, and not intended for git.",
    )
    parser.add_argument(
        "--replace-templates",
        action="store_true",
        help="Replace existing scaffold templates. Existing files are preserved by default.",
    )
    parser.add_argument(
        "--skip-bundle",
        action="store_true",
        help="Only prepare or preserve scaffold artifacts; do not run the deployment bundle.",
    )
    parser.add_argument(
        "--skip-support-readiness",
        action="store_true",
        help="Do not run the support-readiness gate after a passing deployment bundle.",
    )
    parser.add_argument(
        "--require-source-left-enabled",
        action="store_true",
        help="Require the support-readiness gate to finish with final source state leave_enabled.",
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
    parser.add_argument("--confirm-source-enable-canary", action="store_true")
    parser.add_argument("--confirm-no-disable-owner-raw-source", action="store_true")
    parser.add_argument("--confirm-no-front-door-or-header-change", action="store_true")
    parser.add_argument("--confirm-kill-switch-rollback-plan", action="store_true")
    parser.add_argument("--limit", type=positive_int, default=20, help="Maximum issues to print.")
    parser.add_argument("--dev-sso-proxy-url", default=bundle.rehearsal.dev_sso.DEFAULT_PROXY_URL)
    parser.add_argument(
        "--dev-sso-keycloak-discovery-url",
        default=bundle.rehearsal.dev_sso.DEFAULT_KEYCLOAK_DISCOVERY_URL,
    )
    parser.add_argument(
        "--dev-sso-upstream-host",
        default=bundle.rehearsal.dev_sso.DEFAULT_UPSTREAM_HOST,
    )
    parser.add_argument(
        "--dev-sso-upstream-port",
        type=int,
        default=bundle.rehearsal.dev_sso.DEFAULT_UPSTREAM_PORT,
    )
    parser.add_argument("--dev-sso-username", default=bundle.rehearsal.dev_sso.DEFAULT_USERNAME)
    parser.add_argument("--dev-sso-password", default=bundle.rehearsal.dev_sso.DEFAULT_PASSWORD)
    parser.add_argument("--dev-sso-timeout-sec", type=float, default=10.0)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.confirm_local_ignored_artifact_dir:
        print(
            "Owner raw D3 artifact workspace: rejected: local ignored artifact confirmation is required",
            file=sys.stderr,
        )
        return 2
    paths = workspace_paths(args.artifact_dir)
    try:
        write_results = prepare_workspace(paths, replace=args.replace_templates)
    except OSError:
        print(
            "Owner raw D3 artifact workspace: rejected: local artifacts could not be written",
            file=sys.stderr,
        )
        return 2

    if args.skip_bundle:
        payload = prepared_payload(write_results)
        print(format_summary(payload, write_results=write_results, support_skipped=True))
        print_issues(payload, limit=args.limit)
        return 0

    bundle_rc = run_bundle(args, paths)
    payload = load_bundle_summary(paths.bundle_summary)
    if payload is None:
        payload = rejected_payload(write_results)
    support_rc: int | None = None
    support_payload: Mapping[str, Any] | None = None
    support_skipped = True
    if payload.get("status") == "ok":
        if not args.skip_support_readiness:
            support_skipped = False
            support_rc = run_support_readiness(args, paths)
            support_payload = load_summary(paths.support_readiness_summary)
        else:
            remove_summary(paths.support_readiness_summary)
    else:
        remove_summary(paths.support_readiness_summary)
    print(
        format_summary(
            payload,
            write_results=write_results,
            bundle_rc=bundle_rc,
            support_payload=support_payload,
            support_rc=support_rc,
            support_skipped=support_skipped,
        )
    )
    print_issues(payload, limit=args.limit)
    if support_payload is not None and support_payload.get("status") != "ok":
        print("Support readiness issues:")
        print_issues(support_payload, limit=args.limit)
    if payload.get("status") != "ok":
        return 1
    if args.skip_support_readiness:
        return 0
    return 0 if support_payload and support_payload.get("status") == "ok" else 1


def workspace_paths(artifact_dir: Path) -> WorkspacePaths:
    return WorkspacePaths(
        disabled_config=artifact_dir / "d3-disabled-web-config.template.json",
        source_enabled_config=artifact_dir / "d3-source-enabled-canary-config.template.json",
        front_door_review=artifact_dir / "front-door-review.template.json",
        post_enable_review=artifact_dir / "post-enable-review.template.json",
        operator_checklist=artifact_dir / "operator-checklist.md",
        bundle_summary=artifact_dir / "deployment-bundle.summary.json",
        support_readiness_summary=artifact_dir / "support-readiness.summary.json",
    )


def prepare_workspace(paths: WorkspacePaths, *, replace: bool) -> tuple[ArtifactWriteResult, ...]:
    return (
        write_json_if_needed(
            "disabled_config",
            paths.disabled_config,
            disabled_config_template(),
            replace=replace,
        ),
        write_json_if_needed(
            "source_enabled_config",
            paths.source_enabled_config,
            source_enabled_config_template(),
            replace=replace,
        ),
        write_json_if_needed(
            "front_door_review_template",
            paths.front_door_review,
            live_review.review_template(live_review.PROFILE_OWNER_RAW_D3),
            replace=replace,
        ),
        write_json_if_needed(
            "post_enable_review_template",
            paths.post_enable_review,
            post_enable.review_template(),
            replace=replace,
        ),
        write_text_if_needed(
            "operator_checklist",
            paths.operator_checklist,
            operator_checklist_text(),
            replace=replace,
        ),
    )


def write_json_if_needed(
    label: str,
    path: Path,
    payload: Mapping[str, Any],
    *,
    replace: bool,
) -> ArtifactWriteResult:
    if path.exists() and not replace:
        return ArtifactWriteResult(label, "preserved")
    write_ascii_json_artifact(path, payload)
    return ArtifactWriteResult(label, "written")


def write_text_if_needed(
    label: str, path: Path, text: str, *, replace: bool
) -> ArtifactWriteResult:
    if path.exists() and not replace:
        return ArtifactWriteResult(label, "preserved")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return ArtifactWriteResult(label, "written")


def run_bundle(args: argparse.Namespace, paths: WorkspacePaths) -> int:
    try:
        paths.bundle_summary.unlink(missing_ok=True)
    except OSError:
        return 2
    bundle_args = [
        "--config",
        str(paths.disabled_config),
        "--source-enable-config",
        str(paths.source_enabled_config),
        "--front-door-review-json",
        str(paths.front_door_review),
        "--post-enable-review-json",
        str(paths.post_enable_review),
        "--summary-json",
        str(paths.bundle_summary),
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
    if args.host is not None:
        bundle_args.extend(["--host", str(args.host)])
    if args.allow_nonlocal_web_bind:
        bundle_args.append("--allow-nonlocal-web-bind")
    if args.disable_owner_raw_source:
        bundle_args.append("--disable-owner-raw-source")
    if args.confirm_source_enable_canary:
        bundle_args.append("--confirm-source-enable-canary")
    if args.confirm_no_disable_owner_raw_source:
        bundle_args.append("--confirm-no-disable-owner-raw-source")
    if args.confirm_no_front_door_or_header_change:
        bundle_args.append("--confirm-no-front-door-or-header-change")
    if args.confirm_kill_switch_rollback_plan:
        bundle_args.append("--confirm-kill-switch-rollback-plan")
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return bundle.main(bundle_args)
    except Exception:
        return 2


def run_support_readiness(args: argparse.Namespace, paths: WorkspacePaths) -> int:
    try:
        paths.support_readiness_summary.unlink(missing_ok=True)
    except OSError:
        return 2
    support_args = [
        "--deployment-bundle-summary-json",
        str(paths.bundle_summary),
        "--summary-json",
        str(paths.support_readiness_summary),
        "--limit",
        str(args.limit),
    ]
    if args.require_source_left_enabled:
        support_args.append("--require-source-left-enabled")
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return support_readiness.main(support_args)
    except Exception:
        return 2


def disabled_config_template() -> dict[str, object]:
    return {
        "host": ".".join(("0", "0", "0", "0")),
        "source_visibility": "owner_raw",
        "viewer_identity_header": "X-Query-Doctor-Viewer",
        "owner_raw_source_enabled": False,
        "privacy_mode": True,
        "redact": True,
        "redact_identifiers": True,
        "redact_hosts": True,
        "metadata_redact": True,
        "no_llm": True,
    }


def source_enabled_config_template() -> dict[str, object]:
    payload = disabled_config_template()
    payload["owner_raw_source_enabled"] = True
    return payload


def operator_checklist_text() -> str:
    front_door_fields = "\n".join(
        f"- `{field}`"
        for field in live_review.required_field_labels(live_review.PROFILE_OWNER_RAW_D3)
    )
    post_enable_fields = "\n".join(f"- `{field}`" for field in post_enable.required_field_labels())
    return (
        "# Owner Raw D3 Local Operator Checklist\n\n"
        "This file is local-only. Keep real hostnames, user names, query ids, "
        "source screenshots, tokens, cookies, proxy logs, and local artifact "
        "paths out of committed files.\n\n"
        "## Front-Door Review Fields\n\n"
        f"{front_door_fields}\n\n"
        "## Post-Enable Canary Review Fields\n\n"
        f"{post_enable_fields}\n\n"
        "Fill these fields only from real reviewed evidence. Do not use dev SSO "
        "smoke output as production front-door proof.\n"
    )


def prepared_payload(write_results: tuple[ArtifactWriteResult, ...]) -> dict[str, object]:
    return {
        "summary_kind": "owner_raw_d3_artifact_workspace_v1",
        "status": "ok",
        "deployment": {
            "bundle_ready": False,
            "verdict": "prepared",
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
        "artifacts": artifact_payload(write_results),
        "gates": {},
        "issues": {"failed_gates": [], "counts": {}},
    }


def rejected_payload(write_results: tuple[ArtifactWriteResult, ...]) -> dict[str, object]:
    return {
        "summary_kind": "owner_raw_d3_artifact_workspace_v1",
        "status": "failed",
        "deployment": {
            "bundle_ready": False,
            "verdict": "blocked",
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
        "artifacts": artifact_payload(write_results),
        "gates": {},
        "issues": {
            "failed_gates": ["deployment_bundle"],
            "counts": {"deployment_bundle.summary_unavailable": 1},
        },
    }


def artifact_payload(write_results: tuple[ArtifactWriteResult, ...]) -> dict[str, object]:
    return {result.label: result.status for result in write_results}


def load_bundle_summary(path: Path) -> Mapping[str, Any] | None:
    return load_summary(path)


def load_summary(path: Path) -> Mapping[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def remove_summary(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def format_summary(
    payload: Mapping[str, Any],
    *,
    write_results: tuple[ArtifactWriteResult, ...] = (),
    bundle_rc: int | None = None,
    support_payload: Mapping[str, Any] | None = None,
    support_rc: int | None = None,
    support_skipped: bool = False,
) -> str:
    deployment = mapping_value(payload, ("deployment",))
    gates = mapping_value(payload, ("gates",))
    if not isinstance(deployment, Mapping):
        deployment = {}
    if not isinstance(gates, Mapping):
        gates = {}
    lines = [
        f"Owner raw D3 artifact workspace: {safe_status_value(payload.get('status'))}",
        f"bundle_ready={'yes' if deployment.get('bundle_ready') is True else 'no'}",
        f"verdict={safe_status_value(deployment.get('verdict'))}",
    ]
    if write_results:
        for result in write_results:
            lines.append(f"{result.label}={result.status}")
    if bundle_rc is not None:
        lines.append(f"deployment_bundle_rc={safe_nonnegative_int(bundle_rc)}")
    if support_skipped:
        lines.append("support_readiness=skipped")
    elif support_payload is None:
        lines.append("support_readiness=unknown")
    else:
        lines.append(f"support_readiness={safe_status_value(support_payload.get('status'))}")
        support = mapping_value(support_payload, ("support",))
        if isinstance(support, Mapping):
            lines.append(f"support_ready={'yes' if support.get('support_ready') is True else 'no'}")
            lines.append(
                f"support_final_source_state={safe_status_value(support.get('final_source_state'))}"
            )
    if support_rc is not None:
        lines.append(f"support_readiness_rc={safe_nonnegative_int(support_rc)}")
    for gate_name in (
        "front_door_review_audit",
        "readiness",
        "rehearsal",
        "source_enable",
        "post_enable",
        "launch_closure_manifest_builder",
        "launch_closure",
    ):
        if gate_name in gates:
            lines.append(f"{gate_name}={gate_status(gates, gate_name)}")
    lines.extend(
        (
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
    return "\n".join(lines)


def print_issues(payload: Mapping[str, Any], *, limit: int) -> None:
    issues = mapping_value(payload, ("issues",))
    if not isinstance(issues, Mapping):
        print("Failed gates: deployment_bundle")
        print("Issues:")
        print("- deployment_bundle.issues_missing: 1")
        return
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
        count = counts.get(category)
        print(f"- {safe_issue_text(category)}: {safe_nonnegative_int(count)}")


def mapping_value(payload: Mapping[str, Any], path: tuple[str, ...]) -> object:
    current: object = payload
    for part in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def gate_status(gates: Mapping[str, object], name: str) -> str:
    gate = gates[name]
    if not isinstance(gate, Mapping):
        return "unknown"
    return safe_status_value(gate.get("status"))


def safe_status_value(value: object) -> str:
    if isinstance(value, str) and value in SAFE_STATUS_VALUES:
        return value
    return "unknown"


def safe_issue_text(value: str) -> str:
    return "".join(char if char.isascii() and char.isprintable() else "_" for char in value)[:160]


def safe_nonnegative_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


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
