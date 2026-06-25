#!/usr/bin/env python3
"""Audit a raw-free live owner_raw front-door review summary."""

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


REVIEW_KIND = "owner_raw_live_front_door_review_v1"
AUDIT_KIND = "owner_raw_live_front_door_review_audit_v1"
PROFILE_OWNER_RAW_D3 = "owner_raw_d3"
PROFILE_TRINO_SHARED_HARDENING = "trino_shared_hardening"
SAFE_STRING_VALUES = frozenset(
    {
        REVIEW_KIND,
        PROFILE_OWNER_RAW_D3,
        PROFILE_TRINO_SHARED_HARDENING,
        "reviewed",
        "unreviewed",
        "simple_owner",
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


BASE_EXPECTATIONS = _expectations(
    (
        ("summary_kind", REVIEW_KIND, "invalid_summary_kind"),
        ("review_status", "reviewed", "review_not_marked_reviewed"),
        ("front_door.tls_terminated_at_front_door", True, "front_door_tls_not_reviewed"),
        (
            "front_door.authentication_enforced_before_query_doctor",
            True,
            "front_door_auth_not_enforced",
        ),
        (
            "front_door.direct_upstream_client_access_blocked",
            True,
            "direct_upstream_access_not_blocked",
        ),
        ("front_door.inbound_viewer_header_stripped", True, "inbound_viewer_header_not_stripped"),
        (
            "front_door.exactly_one_normalized_viewer_header",
            True,
            "single_viewer_header_not_proven",
        ),
        (
            "front_door.normalized_viewer_value_shape",
            "simple_owner",
            "viewer_value_not_simple_owner",
        ),
        ("front_door.raw_identity_tokens_forwarded", False, "raw_identity_tokens_forwarded"),
        (
            "negative_checks.unauthenticated_request_denied",
            True,
            "unauthenticated_request_not_denied",
        ),
        (
            "negative_checks.spoofed_viewer_header_not_authorizing",
            True,
            "spoofed_viewer_header_authorized",
        ),
        ("negative_checks.missing_viewer_header_denied", True, "missing_viewer_header_not_denied"),
        ("negative_checks.invalid_viewer_header_denied", True, "invalid_viewer_header_not_denied"),
        (
            "negative_checks.duplicate_viewer_header_denied_or_unforwardable",
            True,
            "duplicate_viewer_header_not_closed",
        ),
        (
            "owner_raw_checks.owner_raw_source_kill_switch_blocks_source",
            True,
            "owner_raw_kill_switch_not_verified",
        ),
        ("owner_raw_checks.audit_lines_raw_free", True, "owner_raw_audit_lines_not_raw_free"),
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

OWNER_RAW_D3_EXPECTATIONS = _expectations(
    (
        ("review_profile", PROFILE_OWNER_RAW_D3, "invalid_review_profile"),
        (
            "owner_raw_checks.matching_viewer_own_case_allowed",
            True,
            "matching_viewer_own_case_not_allowed",
        ),
        (
            "owner_raw_checks.different_viewer_same_case_denied",
            True,
            "different_viewer_same_case_not_denied",
        ),
    )
)

TRINO_SHARED_HARDENING_EXPECTATIONS = _expectations(
    (
        ("review_profile", PROFILE_TRINO_SHARED_HARDENING, "invalid_review_profile"),
        ("trino_shared_hardening.reviewed", True, "trino_shared_hardening_not_reviewed"),
        (
            "trino_shared_hardening.raw_trino_source_reveal_blocked",
            True,
            "trino_raw_source_reveal_not_blocked",
        ),
        (
            "trino_shared_hardening.owner_raw_source_enabled",
            False,
            "trino_owner_raw_source_not_disabled",
        ),
        (
            "trino_shared_hardening.details_python_report_materialized_only",
            True,
            "trino_details_report_not_materialized_only",
        ),
        (
            "trino_shared_hardening.optimizer_guidance_materialized_only",
            True,
            "trino_optimizer_not_materialized_only",
        ),
        (
            "trino_shared_hardening.metadata_cli_smoke_dev_only",
            True,
            "trino_metadata_smoke_not_dev_only",
        ),
        (
            "trino_shared_hardening.unsupported_shared_surfaces_blocked",
            True,
            "trino_unsupported_shared_surfaces_not_blocked",
        ),
        (
            "trino_shared_hardening.product_metadata_collection_wired",
            False,
            "trino_product_metadata_collection_wired",
        ),
        ("trino_shared_hardening.running_scan_wired", False, "trino_running_scan_wired"),
        (
            "trino_shared_hardening.query_history_crawling_wired",
            False,
            "trino_query_history_crawling_wired",
        ),
        (
            "trino_shared_hardening.llm_report_output_wired",
            False,
            "trino_llm_report_output_wired",
        ),
        (
            "trino_shared_hardening.query_optimizer_jobs_wired",
            False,
            "trino_query_optimizer_jobs_wired",
        ),
        ("trino_shared_hardening.generated_sql_wired", False, "trino_generated_sql_wired"),
        ("trino_shared_hardening.sql_execution_wired", False, "trino_sql_execution_wired"),
    )
)

EXPECTATIONS_BY_PROFILE = {
    PROFILE_OWNER_RAW_D3: BASE_EXPECTATIONS + OWNER_RAW_D3_EXPECTATIONS,
    PROFILE_TRINO_SHARED_HARDENING: BASE_EXPECTATIONS + TRINO_SHARED_HARDENING_EXPECTATIONS,
}
ALLOWED_PROFILE_VALUES = frozenset(EXPECTATIONS_BY_PROFILE)
ALLOWED_PATHS = frozenset(
    expectation.path
    for expectations in EXPECTATIONS_BY_PROFILE.values()
    for expectation in expectations
)
ALLOWED_PREFIXES = frozenset(
    path[:index] for path in ALLOWED_PATHS for index in range(1, len(path) + 1)
)


class ReviewInputError(RuntimeError):
    """Raised when the review input cannot be safely read or parsed."""


@dataclass
class ReviewAuditResult:
    profile: str = "unknown"
    checked_required_fields: int = 0
    issue_counts: Counter[str] = field(default_factory=Counter)

    @property
    def ok(self) -> bool:
        return not self.issue_counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a raw-free live owner_raw D3 front-door review summary. "
            "The script reads only boolean/enumerated review results and prints "
            "only raw-free counts and issue categories; it never prints paths, "
            "URLs, users, header names, query ids, command output, auth tokens, "
            "or raw source."
        )
    )
    parser.add_argument(
        "--review-json",
        type=Path,
        help=(
            "Raw-free operator review summary JSON. Required unless "
            "--list-required-fields or --template-json is used. The path is never printed."
        ),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Optional raw-free audit summary JSON. The path is never printed.",
    )
    parser.add_argument(
        "--template-json",
        type=Path,
        help=(
            "Optional raw-free fail-closed review-summary template to write. "
            "The path is never printed."
        ),
    )
    parser.add_argument(
        "--require-trino-shared-hardening",
        action="store_true",
        help=(
            "Require the review profile and fields for shared Trino hardening, "
            "including disabled raw Trino source reveal and blocked unsupported "
            "Trino shared surfaces."
        ),
    )
    parser.add_argument(
        "--list-required-fields",
        action="store_true",
        help="Print Python-owned required field labels for the selected profile.",
    )
    return parser


def load_review(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ReviewInputError("review input could not be read safely") from None
    if not isinstance(payload, Mapping):
        raise ReviewInputError("review input must be a JSON object")
    return payload


def get_path(payload: Mapping[str, Any], path: tuple[str, ...]) -> tuple[bool, Any]:
    current: Any = payload
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return False, None
        current = current[part]
    return True, current


def selected_profile(
    payload: Mapping[str, Any],
    *,
    require_trino_shared_hardening: bool,
) -> str:
    if require_trino_shared_hardening:
        return PROFILE_TRINO_SHARED_HARDENING
    found, value = get_path(payload, ("review_profile",))
    if found and isinstance(value, str) and value in ALLOWED_PROFILE_VALUES:
        return value
    return "unknown"


def add_issue(result: ReviewAuditResult, category: str) -> None:
    result.issue_counts[category] += 1


def audit_review(
    payload: Mapping[str, Any],
    *,
    require_trino_shared_hardening: bool = False,
) -> ReviewAuditResult:
    result = ReviewAuditResult(
        profile=selected_profile(
            payload,
            require_trino_shared_hardening=require_trino_shared_hardening,
        )
    )
    if result.profile not in EXPECTATIONS_BY_PROFILE:
        add_issue(result, "invalid_review_profile")
        expectations = BASE_EXPECTATIONS
    else:
        expectations = EXPECTATIONS_BY_PROFILE[result.profile]

    audit_raw_free_shape(payload, result)
    for expectation in expectations:
        result.checked_required_fields += 1
        found, value = get_path(payload, expectation.path)
        if not found:
            add_issue(result, f"missing_{expectation.category}")
            continue
        if value != expectation.expected:
            add_issue(result, expectation.category)
    return result


def audit_raw_free_shape(value: Any, result: ReviewAuditResult, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                add_issue(result, "non_string_field_name")
                continue
            child_path = path + (key,)
            if child_path not in ALLOWED_PREFIXES:
                add_issue(result, "unexpected_field")
            audit_raw_free_shape(child, result, child_path)
        return
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, str):
        if value not in SAFE_STRING_VALUES:
            add_issue(result, "unsafe_string_value")
        return
    add_issue(result, "unsafe_value_type")


def review_template(profile: str) -> dict[str, Any]:
    template: dict[str, Any] = {}
    for expectation in EXPECTATIONS_BY_PROFILE.get(profile, BASE_EXPECTATIONS):
        set_nested(template, expectation.path, template_value(expectation))
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


def summary_payload(result: ReviewAuditResult) -> dict[str, Any]:
    return {
        "summary_kind": AUDIT_KIND,
        "status": "ok" if result.ok else "failed",
        "review_profile": result.profile,
        "checked_required_fields": result.checked_required_fields,
        "issue_counts": dict(sorted(result.issue_counts.items())),
        "front_door_boundary": {
            "trusted_front_door_identity_review": "operator_review_summary",
            "direct_upstream_client_access_blocked": True,
            "inbound_viewer_header_stripping_required": True,
            "exactly_one_normalized_viewer_header_required": True,
            "raw_identity_token_forwarding": "blocked",
            "raw_values_output": False,
            "path_output": False,
            "url_output": False,
            "header_output": False,
            "user_output": False,
            "query_id_output": False,
            "source_output": False,
        },
        "trino_boundary": {
            "shared_hardening_profile": result.profile == PROFILE_TRINO_SHARED_HARDENING,
            "broader_shared_trino_support": False,
            "raw_trino_source_reveal": "blocked",
            "metadata_collection": "not_wired",
            "running_scan": "not_wired",
            "query_history_crawling": "not_wired",
            "llm_report_output": "not_wired",
            "query_optimizer_jobs": "not_wired",
            "generated_sql": "not_wired",
            "sql_execution": "not_wired",
        },
    }


def format_summary(payload: Mapping[str, Any]) -> str:
    issue_counts = payload["issue_counts"]
    if isinstance(issue_counts, Mapping) and issue_counts:
        issues = ", ".join(f"{category}={count}" for category, count in issue_counts.items())
    else:
        issues = "none"
    return "\n".join(
        (
            f"Owner raw live front-door review audit: {payload['status']}",
            f"review_profile={payload['review_profile']}",
            f"checked_required_fields={payload['checked_required_fields']}",
            "trusted_front_door_identity=operator_review_summary",
            "direct_upstream_access=blocked_required",
            "inbound_viewer_header_stripping=required",
            "single_normalized_viewer_header=required",
            "raw_identity_token_forwarding=blocked_required",
            "raw_values_output=no",
            f"issue_categories: {issues}",
        )
    )


def required_field_labels(profile: str) -> tuple[str, ...]:
    expectations = EXPECTATIONS_BY_PROFILE.get(profile, BASE_EXPECTATIONS)
    return tuple(expectation.label for expectation in expectations)


def output_overlap_error(args: argparse.Namespace) -> str | None:
    outputs = (args.summary_json, args.template_json)
    inputs = tuple(path for path in (args.review_json,) if path is not None)
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


def selected_profile_from_args(args: argparse.Namespace) -> str:
    return (
        PROFILE_TRINO_SHARED_HARDENING
        if args.require_trino_shared_hardening
        else PROFILE_OWNER_RAW_D3
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    profile = selected_profile_from_args(args)
    if args.list_required_fields:
        for label in required_field_labels(profile):
            print(label)
        return 0

    overlap_error = output_overlap_error(args)
    if overlap_error:
        print(f"Owner raw live front-door review audit: rejected: {overlap_error}", file=sys.stderr)
        return 2
    if args.template_json is not None:
        try:
            write_ascii_json_artifact(args.template_json, review_template(profile))
        except OSError:
            print(
                "Owner raw live front-door review audit: rejected: template JSON could not be written",
                file=sys.stderr,
            )
            return 2
        print("Owner raw live front-door review template: written")
        if args.review_json is None:
            return 0
    if args.review_json is None:
        parser.error(
            "--review-json is required unless --list-required-fields or --template-json is used"
        )
    try:
        payload = load_review(args.review_json)
    except ReviewInputError as exc:
        print(f"Owner raw live front-door review audit: rejected: {exc}", file=sys.stderr)
        return 2

    result = audit_review(
        payload,
        require_trino_shared_hardening=args.require_trino_shared_hardening,
    )
    summary = summary_payload(result)
    if args.summary_json is not None:
        try:
            write_ascii_json_artifact(args.summary_json, summary)
        except OSError:
            print(
                "Owner raw live front-door review audit: rejected: summary JSON could not be written",
                file=sys.stderr,
            )
            return 2
    print(format_summary(summary))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
