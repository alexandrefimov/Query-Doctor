#!/usr/bin/env python3
"""Audit owner_raw staging config readiness without exposing deployment inputs."""

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

from query_doctor.config.contract import ConfigError, load_and_validate_config  # noqa: E402
from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    output_overlaps_inputs_error,
    write_ascii_json_artifact,
)
from query_doctor.source_visibility import SOURCE_VISIBILITY_OWNER_RAW  # noqa: E402
from query_doctor.web.cluster_selection import build_web_cluster_configs  # noqa: E402
from query_doctor.web.models import DEFAULT_HOST, WebClusterConfig  # noqa: E402
from query_doctor.web.owner_raw_policy import is_owner_raw_local_bind_host  # noqa: E402
from query_doctor.web.viewer_identity import normalize_viewer_identity_header  # noqa: E402


SUMMARY_KIND = "owner_raw_staging_preflight_v1"


class OwnerRawStagingPreflightInputError(RuntimeError):
    """Raised when inputs cannot be audited safely."""


@dataclass(frozen=True)
class OwnerRawSource:
    source_visibility: str
    bind_scope: str
    viewer_identity_header_configured: bool
    owner_raw_source_enabled: bool
    allow_nonlocal_web_bind: bool
    privacy_mode_safe: bool
    redaction_safe: bool


@dataclass(frozen=True)
class PreflightIssue:
    category: str
    message: str


@dataclass
class PreflightResult:
    config_checked: bool = False
    source_count: int = 0
    owner_raw_source_count: int = 0
    nonlocal_owner_raw_source_count: int = 0
    local_owner_raw_source_count: int = 0
    viewer_identity_header_configured_count: int = 0
    owner_raw_source_disabled_count: int = 0
    privacy_safe_count: int = 0
    redaction_safe_count: int = 0
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[tuple[int | None, PreflightIssue]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issue_counts


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a raw-free owner_raw staging/pre-proxy config preflight. "
            "The audit checks local Query Doctor config shape before live front-door "
            "review: owner_raw is configured, viewer_identity_header is present and "
            "valid, raw source reveal is disabled by the kill switch, and explicit "
            "privacy/redaction settings have not been weakened. Output never prints "
            "config paths, header names, users, URLs, local paths, credentials, query "
            "ids, or raw source."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Ignored local Query Doctor web config to audit. The path is never printed.",
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
        (args.config,),
        message="summary output must not overwrite input artifacts",
    )
    if overlap_error:
        print(f"Owner raw staging preflight: rejected: {overlap_error}", file=sys.stderr)
        return 2

    result = PreflightResult(config_checked=True)
    try:
        audit_config(result, args)
    except OwnerRawStagingPreflightInputError as exc:
        print(f"Owner raw staging preflight: rejected: {exc}", file=sys.stderr)
        return 2

    status = "ok" if result.ok else "failed"
    payload = summary_payload(result, status=status)
    if args.summary_json is not None:
        try:
            write_ascii_json_artifact(args.summary_json, payload)
        except OSError:
            print(
                "Owner raw staging preflight: rejected: summary JSON could not be written",
                file=sys.stderr,
            )
            return 2

    print(format_summary(result, status=status))
    print_issues(result, limit=args.limit)
    return 0 if result.ok else 1


def audit_config(result: PreflightResult, args: argparse.Namespace) -> None:
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
        raise OwnerRawStagingPreflightInputError(
            "config input could not be audited safely"
        ) from None

    host = args.host or optional_string(values, "host") or DEFAULT_HOST
    owner_raw_source_enabled = owner_raw_source_enabled_value(
        values,
        disable_owner_raw_source=bool(args.disable_owner_raw_source),
    )
    viewer_header_configured = viewer_identity_header_is_configured(values)
    privacy_mode_safe = optional_bool(values, "privacy_mode", default=True)
    redaction_safe = redaction_settings_safe(values, privacy_mode_safe=privacy_mode_safe)
    sources = owner_raw_sources(
        values,
        clusters=clusters,
        host=host,
        allow_nonlocal_web_bind=bool(args.allow_nonlocal_web_bind),
        viewer_identity_header_configured=viewer_header_configured,
        owner_raw_source_enabled=owner_raw_source_enabled,
        privacy_mode_safe=privacy_mode_safe,
        redaction_safe=redaction_safe,
    )
    for index, source in enumerate(sources, start=1):
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
        if not source.owner_raw_source_enabled:
            result.owner_raw_source_disabled_count += 1
        if source.privacy_mode_safe:
            result.privacy_safe_count += 1
        if source.redaction_safe:
            result.redaction_safe_count += 1
        audit_source(result, source, source_index=index)
    if result.owner_raw_source_count == 0:
        add_issue(
            result,
            "owner_raw_source_visibility_missing",
            "Staging owner_raw preflight requires at least one owner_raw source visibility.",
        )


def owner_raw_sources(
    values: Mapping[str, object],
    *,
    clusters: tuple[WebClusterConfig, ...],
    host: str,
    allow_nonlocal_web_bind: bool,
    viewer_identity_header_configured: bool,
    owner_raw_source_enabled: bool,
    privacy_mode_safe: bool,
    redaction_safe: bool,
) -> tuple[OwnerRawSource, ...]:
    bind_scope = "local" if is_owner_raw_local_bind_host(host) else "nonlocal"
    if clusters:
        return tuple(
            OwnerRawSource(
                source_visibility=cluster.source_visibility,
                bind_scope=bind_scope,
                viewer_identity_header_configured=viewer_identity_header_configured,
                owner_raw_source_enabled=owner_raw_source_enabled,
                allow_nonlocal_web_bind=allow_nonlocal_web_bind,
                privacy_mode_safe=privacy_mode_safe,
                redaction_safe=redaction_safe,
            )
            for cluster in clusters
        )
    return (
        OwnerRawSource(
            source_visibility=optional_string(values, "source_visibility") or "safe",
            bind_scope=bind_scope,
            viewer_identity_header_configured=viewer_identity_header_configured,
            owner_raw_source_enabled=owner_raw_source_enabled,
            allow_nonlocal_web_bind=allow_nonlocal_web_bind,
            privacy_mode_safe=privacy_mode_safe,
            redaction_safe=redaction_safe,
        ),
    )


def audit_source(
    result: PreflightResult,
    source: OwnerRawSource,
    *,
    source_index: int,
) -> None:
    if not source.viewer_identity_header_configured:
        add_issue(
            result,
            "viewer_identity_header_missing",
            (
                "Shared owner_raw staging requires exactly one configured "
                "viewer_identity_header supplied by a trusted front door."
            ),
            source_index=source_index,
        )
    if source.owner_raw_source_enabled:
        add_issue(
            result,
            "owner_raw_source_kill_switch_not_disabled",
            (
                "Keep owner_raw_source_enabled=false or pass --disable-owner-raw-source "
                "until live front-door review passes."
            ),
            source_index=source_index,
        )
    if source.bind_scope == "nonlocal" and not source.allow_nonlocal_web_bind:
        add_issue(
            result,
            "nonlocal_web_bind_not_explicitly_reviewed",
            (
                "A non-local owner_raw staging bind must be paired with the planned "
                "--allow-nonlocal-web-bind startup flag."
            ),
            source_index=source_index,
        )
    if not source.privacy_mode_safe:
        add_issue(
            result,
            "privacy_mode_explicitly_disabled",
            "Do not disable privacy_mode in shared owner_raw staging config.",
            source_index=source_index,
        )
    if not source.redaction_safe:
        add_issue(
            result,
            "redaction_explicitly_disabled",
            "Do not explicitly disable redaction controls in shared owner_raw staging config.",
            source_index=source_index,
        )


def summary_payload(result: PreflightResult, *, status: str) -> dict[str, Any]:
    return {
        "summary_kind": SUMMARY_KIND,
        "status": status,
        "config_boundary": {
            "config_checked": result.config_checked,
            "paths_printed": False,
            "header_names_printed": False,
            "header_values_printed": False,
            "users_printed": False,
            "urls_printed": False,
            "query_ids_printed": False,
            "raw_source_printed": False,
        },
        "owner_raw_boundary": {
            "source_count": result.source_count,
            "owner_raw_source_count": result.owner_raw_source_count,
            "nonlocal_owner_raw_source_count": result.nonlocal_owner_raw_source_count,
            "local_owner_raw_source_count": result.local_owner_raw_source_count,
            "viewer_identity_header": viewer_header_status(result),
            "owner_raw_source": owner_raw_source_status(result),
            "front_door_review": "not_substituted_by_config_preflight",
            "live_review_required_before_source_enable": True,
        },
        "safety_controls": {
            "privacy_safe_count": result.privacy_safe_count,
            "redaction_safe_count": result.redaction_safe_count,
            "raw_values_output": False,
        },
        "issues": {
            "counts": counter_payload(result.issue_counts),
            "items": [
                {
                    "source_index": source_index,
                    "category": issue.category,
                    "message": issue.message,
                }
                for source_index, issue in result.issues
            ],
        },
    }


def format_summary(result: PreflightResult, *, status: str) -> str:
    return "\n".join(
        (
            f"Owner raw staging preflight: {status}",
            f"config_checked={'yes' if result.config_checked else 'no'}",
            f"source_count={result.source_count}",
            f"owner_raw_sources={result.owner_raw_source_count}",
            f"nonlocal_owner_raw_sources={result.nonlocal_owner_raw_source_count}",
            f"local_owner_raw_sources={result.local_owner_raw_source_count}",
            f"viewer_identity_header={viewer_header_status(result)}",
            f"owner_raw_source={owner_raw_source_status(result)}",
            "front_door_review=not_substituted_by_config_preflight",
            "live_review_required_before_source_enable=yes",
            "paths=not_printed",
            "header_names=not_printed",
            "header_values=not_printed",
            "users=not_printed",
            "urls=not_printed",
            "raw_source=not_printed",
        )
    )


def viewer_header_status(result: PreflightResult) -> str:
    if result.owner_raw_source_count == 0:
        return "not_checked"
    if result.viewer_identity_header_configured_count == result.owner_raw_source_count:
        return "configured"
    return "missing_or_invalid"


def owner_raw_source_status(result: PreflightResult) -> str:
    if result.owner_raw_source_count == 0:
        return "not_checked"
    if result.owner_raw_source_disabled_count == result.owner_raw_source_count:
        return "disabled"
    return "enabled"


def add_issue(
    result: PreflightResult,
    category: str,
    message: str,
    *,
    source_index: int | None = None,
) -> None:
    result.issue_counts[category] += 1
    result.issues.append((source_index, PreflightIssue(category, message)))


def print_issues(result: PreflightResult, *, limit: int) -> None:
    if not result.issues:
        print("Issues: none")
        return
    print("Issues:")
    for source_index, issue in result.issues[:limit]:
        source_text = f"source={source_index}; " if source_index is not None else ""
        print(f"- {issue.category}: {source_text}{issue.message}")
    remaining = len(result.issues) - limit
    if remaining > 0:
        print(f"- additional_issues: {remaining}")


def owner_raw_source_enabled_value(
    values: Mapping[str, object],
    *,
    disable_owner_raw_source: bool,
) -> bool:
    if disable_owner_raw_source:
        return False
    return optional_bool(values, "owner_raw_source_enabled", default=True)


def viewer_identity_header_is_configured(values: Mapping[str, object]) -> bool:
    value = optional_string(values, "viewer_identity_header")
    if value is None:
        return False
    try:
        return normalize_viewer_identity_header(value) is not None
    except ValueError:
        return False


def redaction_settings_safe(values: Mapping[str, object], *, privacy_mode_safe: bool) -> bool:
    redaction_defaults = (
        optional_bool(values, "redact", default=True),
        optional_bool(values, "redact_identifiers", default=privacy_mode_safe),
        optional_bool(values, "redact_hosts", default=privacy_mode_safe),
        optional_bool(values, "metadata_redact", default=privacy_mode_safe),
    )
    return all(redaction_defaults)


def optional_string(values: Mapping[str, object], key: str) -> str | None:
    value = values.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def optional_bool(values: Mapping[str, object], key: str, *, default: bool) -> bool:
    value = values.get(key)
    return value if isinstance(value, bool) else default


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
