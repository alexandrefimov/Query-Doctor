#!/usr/bin/env python3
"""Audit retained raw-free Trino representative evidence summaries."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.report.safety_validation import (  # noqa: E402
    contains_raw_sql_like_text,
    validate_report_internal_fingerprints,
)
from query_doctor.safety import redaction  # noqa: E402
from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    output_overlaps_inputs_error,
    write_ascii_json_artifact,
)
from query_doctor.trino.representative_evidence import (  # noqa: E402
    TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE,
    TRINO_REPRESENTATIVE_EVIDENCE_GATE,
    TRINO_REPRESENTATIVE_EVIDENCE_STATUS,
    TRINO_SQL_EXECUTION_STATUS,
    TrinoRepresentativeEvidenceRequirements,
    accepted_safe_labels,
    audit_trino_representative_evidence,
    representative_evidence_requirements_for_profile,
    representative_evidence_summary_payload,
)


LOCAL_PATH_RE = re.compile(
    r"(?<![\w/])(?:/private)?/(?:Users|home|tmp|var|etc)/[^\s<>'\"]+"
    r"|(?<![\w/])[A-Za-z]:\\[^\s<>'\"]+"
)
URL_RE = re.compile(r"\bhttps?://\S+", re.IGNORECASE)


class TrinoRepresentativeEvidenceInputError(RuntimeError):
    """Raised when retained summary input cannot be accepted safely."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check retained raw-free Trino representative evidence summaries without "
            "collecting from Trino, reopening packages, executing SQL, or promoting "
            "broader Trino production support."
        )
    )
    parser.add_argument(
        "--summary-input-json",
        action="append",
        type=Path,
        default=[],
        help=(
            "Already raw-free Trino summary JSON to include. Repeat for retained suites. "
            "Input paths are never printed."
        ),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional raw-free machine summary path. The path is never printed.",
    )
    parser.add_argument("--require-min-summary-inputs", type=non_negative_int, default=0)
    parser.add_argument("--require-min-summary-kinds", type=non_negative_int, default=0)
    parser.add_argument("--require-min-evidence-units", type=non_negative_int, default=0)
    parser.add_argument(
        "--require-breadth-profile",
        choices=[TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE],
        default=None,
        help=(
            "Apply a named retained-evidence breadth profile. Profiles check only "
            "already raw-free summary counters."
        ),
    )
    parser.add_argument(
        "--require-min-trino-version-families",
        type=non_negative_int,
        default=0,
    )
    parser.add_argument("--require-min-source-contracts", type=non_negative_int, default=0)
    parser.add_argument("--require-min-source-schemas", type=non_negative_int, default=0)
    parser.add_argument("--require-min-lifecycles", type=non_negative_int, default=0)
    parser.add_argument(
        "--require-min-connector-family-categories",
        type=non_negative_int,
        default=0,
    )
    parser.add_argument("--require-min-source-granularities", type=non_negative_int, default=0)
    parser.add_argument("--require-min-verification-scopes", type=non_negative_int, default=0)
    parser.add_argument("--require-min-support-statuses", type=non_negative_int, default=0)
    parser.add_argument("--require-summary-kind", action="append", default=[])
    parser.add_argument("--require-summary-status", action="append", default=[])
    parser.add_argument("--require-trino-version-family", action="append", default=[])
    parser.add_argument("--require-source-contract", action="append", default=[])
    parser.add_argument("--require-source-schema", action="append", default=[])
    parser.add_argument("--require-lifecycle", action="append", default=[])
    parser.add_argument("--require-connector-family-category", action="append", default=[])
    parser.add_argument("--require-source-granularity", action="append", default=[])
    parser.add_argument("--require-verification-scope", action="append", default=[])
    parser.add_argument("--require-support-status", action="append", default=[])
    parser.add_argument("--limit", type=positive_int, default=12, help="Maximum issues to print.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    requirements = requirements_from_args(args)
    if requirements is None:
        return 2
    payloads: list[dict[str, Any]] = []
    for path in args.summary_input_json:
        try:
            payloads.append(load_summary_payload(path))
        except TrinoRepresentativeEvidenceInputError as exc:
            print(f"[trino-representative-evidence-audit] rejected: {exc}", file=sys.stderr)
            return 2

    result = audit_trino_representative_evidence(payloads, requirements=requirements)
    status = "ok" if result.ok else "failed"
    summary = representative_evidence_summary_payload(
        result,
        requirements=requirements,
        status=status,
    )
    if not write_summary_or_reject(args.summary_json, args.summary_input_json, summary):
        return 2

    print(f"Trino representative evidence audit: {status}")
    print(
        "Boundary: "
        f"closure_gate={TRINO_REPRESENTATIVE_EVIDENCE_GATE}, "
        f"representative_evidence={TRINO_REPRESENTATIVE_EVIDENCE_STATUS}, "
        "broader_production_closure=not_closed, "
        f"trino_sql_execution={TRINO_SQL_EXECUTION_STATUS}"
    )
    print(
        "Inputs: "
        f"summary_inputs={result.summary_input_count}, "
        f"summary_kinds={counter_text(result.summary_kind_counts) or 'none'}, "
        f"evidence_units={result.evidence_unit_count}, "
        f"statuses={counter_text(result.status_counts) or 'none'}"
    )
    print(
        "Coverage: "
        f"trino_versions={counter_text(result.trino_version_family_counts) or 'none'}; "
        f"source_contracts={counter_text(result.source_contract_counts) or 'none'}; "
        "connector_family_categories="
        f"{counter_text(result.connector_family_category_counts) or 'none'}"
    )
    print(
        "Diagnostic lanes: "
        f"source_granularity={counter_text(result.source_granularity_counts) or 'none'}; "
        f"verification_scopes={counter_text(result.verification_scope_counts) or 'none'}"
    )
    print(
        "Breadth requirement tracking: "
        f"breadth_requirements={counter_text(result.breadth_requirement_tracking_counts) or 'none'}"
    )
    print_issues(result.issues, limit=args.limit)
    return 0 if result.ok else 1


def requirements_from_args(
    args: argparse.Namespace,
) -> TrinoRepresentativeEvidenceRequirements | None:
    required_summary_kinds = accepted_safe_labels(args.require_summary_kind)
    required_summary_statuses = accepted_safe_labels(args.require_summary_status)
    required_trino_version_families = accepted_safe_labels(
        args.require_trino_version_family,
        label_kind="trino_version_family",
    )
    required_source_contracts = accepted_safe_labels(args.require_source_contract)
    required_source_schemas = accepted_safe_labels(args.require_source_schema)
    required_lifecycles = accepted_safe_labels(args.require_lifecycle)
    required_connector_family_categories = accepted_safe_labels(
        args.require_connector_family_category
    )
    required_source_granularities = accepted_safe_labels(args.require_source_granularity)
    required_verification_scopes = accepted_safe_labels(args.require_verification_scope)
    required_support_statuses = accepted_safe_labels(args.require_support_status)
    if any(
        value is None
        for value in (
            required_summary_kinds,
            required_summary_statuses,
            required_trino_version_families,
            required_source_contracts,
            required_source_schemas,
            required_lifecycles,
            required_connector_family_categories,
            required_source_granularities,
            required_verification_scopes,
            required_support_statuses,
        )
    ):
        print(
            "[trino-representative-evidence-audit] rejected: unsafe requirement label",
            file=sys.stderr,
        )
        return None
    profile_requirements = (
        representative_evidence_requirements_for_profile(args.require_breadth_profile)
        if args.require_breadth_profile
        else TrinoRepresentativeEvidenceRequirements()
    )
    return TrinoRepresentativeEvidenceRequirements(
        requirement_profile=profile_requirements.requirement_profile,
        require_min_summary_inputs=max(
            args.require_min_summary_inputs,
            profile_requirements.require_min_summary_inputs,
        ),
        require_min_summary_kinds=max(
            args.require_min_summary_kinds,
            profile_requirements.require_min_summary_kinds,
        ),
        require_min_evidence_units=max(
            args.require_min_evidence_units,
            profile_requirements.require_min_evidence_units,
        ),
        require_min_trino_version_families=max(
            args.require_min_trino_version_families,
            profile_requirements.require_min_trino_version_families,
        ),
        require_min_source_contracts=max(
            args.require_min_source_contracts,
            profile_requirements.require_min_source_contracts,
        ),
        require_min_source_schemas=max(
            args.require_min_source_schemas,
            profile_requirements.require_min_source_schemas,
        ),
        require_min_lifecycles=max(
            args.require_min_lifecycles,
            profile_requirements.require_min_lifecycles,
        ),
        require_min_connector_family_categories=max(
            args.require_min_connector_family_categories,
            profile_requirements.require_min_connector_family_categories,
        ),
        require_min_source_granularities=max(
            args.require_min_source_granularities,
            profile_requirements.require_min_source_granularities,
        ),
        require_min_verification_scopes=max(
            args.require_min_verification_scopes,
            profile_requirements.require_min_verification_scopes,
        ),
        require_min_support_statuses=max(
            args.require_min_support_statuses,
            profile_requirements.require_min_support_statuses,
        ),
        required_summary_kinds=_merge_label_requirements(
            required_summary_kinds or (),
            profile_requirements.required_summary_kinds,
        ),
        required_summary_statuses=_merge_label_requirements(
            required_summary_statuses or (),
            profile_requirements.required_summary_statuses,
        ),
        required_trino_version_families=_merge_label_requirements(
            required_trino_version_families or (),
            profile_requirements.required_trino_version_families,
        ),
        required_source_contracts=_merge_label_requirements(
            required_source_contracts or (),
            profile_requirements.required_source_contracts,
        ),
        required_source_schemas=_merge_label_requirements(
            required_source_schemas or (),
            profile_requirements.required_source_schemas,
        ),
        required_lifecycles=_merge_label_requirements(
            required_lifecycles or (),
            profile_requirements.required_lifecycles,
        ),
        required_connector_family_categories=_merge_label_requirements(
            required_connector_family_categories or (),
            profile_requirements.required_connector_family_categories,
        ),
        required_source_granularities=_merge_label_requirements(
            required_source_granularities or (),
            profile_requirements.required_source_granularities,
        ),
        required_verification_scopes=_merge_label_requirements(
            required_verification_scopes or (),
            profile_requirements.required_verification_scopes,
        ),
        required_support_statuses=_merge_label_requirements(
            required_support_statuses or (),
            profile_requirements.required_support_statuses,
        ),
    )


def _merge_label_requirements(*groups: Iterable[str]) -> tuple[str, ...]:
    labels: set[str] = set()
    for group in groups:
        labels.update(group)
    return tuple(sorted(labels))


def load_summary_payload(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TrinoRepresentativeEvidenceInputError("summary JSON input could not be read") from exc
    raw_categories = raw_text_issue_categories(text)
    if raw_categories:
        raise TrinoRepresentativeEvidenceInputError("summary JSON input contains raw-like content")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TrinoRepresentativeEvidenceInputError("summary JSON input is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise TrinoRepresentativeEvidenceInputError("summary JSON input must be a JSON object")
    return payload


def write_summary_or_reject(
    path: Path | None,
    inputs: Iterable[Path],
    payload: dict[str, Any],
) -> bool:
    if path is None:
        return True
    overlap_error = output_overlaps_inputs_error(
        path,
        inputs,
        message="summary JSON output must differ from every input summary",
    )
    if overlap_error:
        print(f"[trino-representative-evidence-audit] rejected: {overlap_error}", file=sys.stderr)
        return False
    raw_categories = raw_text_issue_categories(json.dumps(payload, ensure_ascii=True))
    if raw_categories:
        print(
            "[trino-representative-evidence-audit] rejected: summary JSON output "
            "would contain raw-like content",
            file=sys.stderr,
        )
        return False
    try:
        write_ascii_json_artifact(path, payload)
    except OSError:
        print(
            "[trino-representative-evidence-audit] rejected: summary JSON output "
            "could not be written",
            file=sys.stderr,
        )
        return False
    return True


def raw_text_issue_categories(text: str) -> tuple[str, ...]:
    categories: list[str] = []
    if contains_raw_sql_like_text(text):
        categories.append("sql")
    if validate_report_internal_fingerprints(text):
        categories.append("internal_fingerprint")
    if redaction.EMAIL_RE.search(text):
        categories.append("email")
    if redaction.IPV4_RE.search(text):
        categories.append("ipv4")
    if redaction.HOSTLIKE_FQDN_RE.search(text):
        categories.append("hostname")
    if URL_RE.search(text):
        categories.append("url")
    if LOCAL_PATH_RE.search(text):
        categories.append("local_path")
    if redaction.SECRET_VALUE_RE.search(text):
        categories.append("secret")
    return tuple(sorted(set(categories)))


def print_issues(
    issues: list[Any],
    *,
    limit: int,
) -> None:
    if not issues:
        print("Issues: none")
        return
    print("Issues:")
    for issue in issues[:limit]:
        print(f"- {issue.category}: {issue.message}")
    remaining = len(issues) - limit
    if remaining > 0:
        print(f"- additional_issues: {remaining}")


def counter_text(counter: Counter[str]) -> str:
    return ", ".join(f"{key}={counter[key]}" for key in sorted(counter))


def non_negative_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if value < 0:
        raise argparse.ArgumentTypeError("must be at least 0")
    return value


def positive_int(raw: str) -> int:
    value = non_negative_int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
