#!/usr/bin/env python3
"""Audit a Trino evidence package through the local boundary handoff pipeline."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.analyzer.engine_facts import EngineFactContractError  # noqa: E402
from query_doctor.analyzer.trino_evidence_package import (  # noqa: E402
    trino_evidence_package_summary_payload,
    validate_trino_evidence_package_payload,
)
from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    ascii_json_artifact_text,
    output_overlaps_inputs_error,
    path_overlaps_any,
    same_path,
    write_ascii_json_artifact,
)
from query_doctor.trino.diagnosis import (  # noqa: E402
    TRINO_COMPACT_DIAGNOSIS_SUPPORT_STATUS,
)
from scripts.audit_trino_compact_readiness import (  # noqa: E402
    SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST,
    SOURCE_GRANULARITY_ONE_QUERY_BOUNDARY,
    TrinoCompactReadinessBatchResult,
    add_suite_result,
    audit_batch_min_inputs,
    audit_boundary_payload,
    counter_payload,
    is_safe_relative_json_reference,
    print_suite_result,
    raw_text_issue_categories,
)


TRINO_EVIDENCE_HANDOFF_SUMMARY_KIND = "trino_evidence_handoff_summary_v1"
TRINO_EVIDENCE_HANDOFF_SUITE_SUMMARY_KIND = "trino_evidence_handoff_suite_summary_v1"
TRINO_EVIDENCE_HANDOFF_SUITE_MANIFEST_KIND = "trino_evidence_handoff_suite_v1"
TRINO_EVIDENCE_HANDOFF_SUITE_MANIFEST_BUILDER_KIND = (
    "trino_evidence_handoff_suite_manifest_builder_v1"
)
TRINO_EVIDENCE_HANDOFF_VERIFICATION_SCOPES = frozenset(
    {
        "comparable_one_query_rerun",
        "representative_query_selection",
        "source_contract_review",
    }
)
TRINO_EVIDENCE_HANDOFF_SOURCE_GRANULARITIES = frozenset(
    {
        SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST,
        SOURCE_GRANULARITY_ONE_QUERY_BOUNDARY,
    }
)
TRINO_EVIDENCE_HANDOFF_SOURCE_CONTRACT_RE = re.compile(r"[a-z][a-z0-9_]{1,120}")


class TrinoEvidenceHandoffOutputError(RuntimeError):
    """Raised when the handoff audit cannot write safe output."""


class TrinoEvidenceHandoffInputError(RuntimeError):
    """Raised when a Trino evidence handoff suite input is not accepted."""


@dataclass(frozen=True)
class TrinoEvidenceHandoffSuiteIssue:
    category: str
    message: str


@dataclass
class TrinoEvidenceHandoffSuiteResult:
    input_count: int = 0
    ok_count: int = 0
    failed_count: int = 0
    package_sample_count: int = 0
    boundary_count: int = 0
    fact_count: int = 0
    attention_area_count: int = 0
    supported_attention_area_count: int = 0
    source_contract_counts: Counter[str] = field(default_factory=Counter)
    package_source_type_counts: Counter[str] = field(default_factory=Counter)
    connector_family_counts: Counter[str] = field(default_factory=Counter)
    source_schema_counts: Counter[str] = field(default_factory=Counter)
    source_version_state_counts: Counter[str] = field(default_factory=Counter)
    support_status_counts: Counter[str] = field(default_factory=Counter)
    parser_coverage_counts: Counter[str] = field(default_factory=Counter)
    lifecycle_counts: Counter[str] = field(default_factory=Counter)
    source_granularity_counts: Counter[str] = field(default_factory=Counter)
    diagnostic_lane_readiness_counts: Counter[str] = field(default_factory=Counter)
    diagnostic_lane_verification_scope_counts: Counter[str] = field(default_factory=Counter)
    diagnostic_lane_fact_state_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[tuple[int | None, TrinoEvidenceHandoffSuiteIssue]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a sanitized Trino evidence package, convert accepted samples to "
            "raw-free boundary payloads in memory, and run the Trino compact readiness "
            "suite without printing paths or claiming Trino product support."
        )
    )
    parser.add_argument(
        "package_json",
        type=Path,
        nargs="?",
        help="Path to a sanitized package JSON file.",
    )
    parser.add_argument(
        "--handoff-suite-manifest",
        type=Path,
        default=None,
        help=(
            "Optional trino_evidence_handoff_suite_v1 manifest whose entries reference "
            "retained raw-free Trino evidence handoff summary JSON artifacts. The "
            "manifest path and referenced artifact paths are never printed."
        ),
    )
    parser.add_argument("--limit", type=positive_int, default=12, help="Rows to print per section.")
    parser.add_argument(
        "--require-min-inputs",
        type=positive_int,
        default=12,
        help="Require at least this many package sample boundaries.",
    )
    parser.add_argument(
        "--require-verification-scope",
        action="append",
        default=[],
        help=(
            "For handoff-suite manifests, require at least one retained handoff "
            "summary to carry this diagnostic-lane verification scope. May be repeated."
        ),
    )
    parser.add_argument(
        "--require-source-granularity",
        action="append",
        default=[],
        help=(
            "For handoff-suite manifests, require at least one retained handoff "
            "summary to carry this diagnostic-lane source granularity. May be repeated."
        ),
    )
    parser.add_argument(
        "--require-source-contract",
        action="append",
        default=[],
        help=(
            "For handoff-suite manifests, require at least one retained handoff "
            "summary to carry this safe source-contract label. May be repeated."
        ),
    )
    parser.add_argument(
        "--require-supported-attention",
        action="store_true",
        help=(
            "Return non-zero unless every accepted sample boundary produces a supported "
            "Trino attention area. This is intentionally off for full packages that "
            "include unknown/unsupported coverage samples."
        ),
    )
    parser.add_argument(
        "--fail-on-unknown-parser-coverage",
        action="store_true",
        help="Return non-zero when any package sample boundary has unknown parser coverage.",
    )
    parser.add_argument(
        "--require-one-query-boundary",
        action="store_true",
        help=(
            "Return non-zero for aggregate query-list boundaries. This is for one-query "
            "handoff subsets, not full evidence packages with query-list contract probes."
        ),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help=(
            "Optional output path for a raw-free machine-readable Trino evidence handoff "
            "summary. The path must differ from the package input and is never printed."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.handoff_suite_manifest is not None:
        if args.package_json is not None:
            print(
                "[trino-evidence-handoff] rejected: handoff suite manifest cannot be "
                "combined with package input",
                file=sys.stderr,
            )
            return 2
        required_verification_scopes = accepted_required_verification_scopes(
            args.require_verification_scope
        )
        if required_verification_scopes is None:
            print(
                "[trino-evidence-handoff-suite] rejected: verification scope requirement is not accepted",
                file=sys.stderr,
            )
            return 2
        required_source_granularities = accepted_required_source_granularities(
            args.require_source_granularity
        )
        if required_source_granularities is None:
            print(
                "[trino-evidence-handoff-suite] rejected: source granularity requirement is not accepted",
                file=sys.stderr,
            )
            return 2
        required_source_contracts = accepted_required_source_contracts(args.require_source_contract)
        if required_source_contracts is None:
            print(
                "[trino-evidence-handoff-suite] rejected: source contract requirement is not accepted",
                file=sys.stderr,
            )
            return 2
        return run_handoff_suite_mode(
            args,
            required_source_contracts=required_source_contracts,
            required_source_granularities=required_source_granularities,
            required_verification_scopes=required_verification_scopes,
        )
    if args.require_source_contract:
        print(
            "[trino-evidence-handoff] rejected: --require-source-contract is only "
            "valid for handoff suite manifest",
            file=sys.stderr,
        )
        return 2
    if args.require_source_granularity:
        print(
            "[trino-evidence-handoff] rejected: --require-source-granularity is only "
            "valid for handoff suite manifest",
            file=sys.stderr,
        )
        return 2
    if args.require_verification_scope:
        print(
            "[trino-evidence-handoff] rejected: --require-verification-scope is only "
            "valid for handoff suite manifest",
            file=sys.stderr,
        )
        return 2
    if args.package_json is None:
        print(
            "[trino-evidence-handoff] rejected: provide a package input or handoff suite manifest",
            file=sys.stderr,
        )
        return 2
    overlap_error = reject_summary_output_overlap(args.summary_json, args.package_json)
    if overlap_error:
        print(f"[trino-evidence-handoff] rejected: {overlap_error}", file=sys.stderr)
        return 2

    try:
        package_payload = _load_json(args.package_json)
        package_result = validate_trino_evidence_package_payload(package_payload)
    except OSError:
        print("[trino-evidence-handoff] rejected: package file could not be read", file=sys.stderr)
        return 2
    except json.JSONDecodeError:
        print("[trino-evidence-handoff] rejected: package file is not valid JSON", file=sys.stderr)
        return 2
    except EngineFactContractError as exc:
        print(f"[trino-evidence-handoff] rejected: {exc}", file=sys.stderr)
        return 1

    batch = audit_package_boundaries(
        package_result.bundles,
        require_supported_attention=args.require_supported_attention,
        fail_on_unknown_parser_coverage=args.fail_on_unknown_parser_coverage,
        require_one_query_boundary=args.require_one_query_boundary,
    )
    audit_batch_min_inputs(batch, required_min_inputs=args.require_min_inputs)

    status = "ok" if batch.ok else "failed"
    summary = handoff_summary_payload(
        package_result=package_result,
        batch=batch,
        status=status,
        require_min_inputs=args.require_min_inputs,
        require_supported_attention=args.require_supported_attention,
        fail_on_unknown_parser_coverage=args.fail_on_unknown_parser_coverage,
        require_one_query_boundary=args.require_one_query_boundary,
    )
    if not write_summary_or_reject(args.summary_json, summary):
        return 2

    print(f"Trino evidence handoff: {status}")
    print(
        "Pipeline: "
        "package_validation=accepted, "
        "boundary_export=accepted, "
        f"compact_readiness_audit={status}"
    )
    print(
        "Boundary: "
        f"support_status={TRINO_COMPACT_DIAGNOSIS_SUPPORT_STATUS}, "
        "support_claim=not_claimed, "
        "product_surface=not_wired, "
        "trino_sql_execution=not_performed"
    )
    print("Output paths: not_printed")
    print_suite_result(batch, limit=args.limit)
    return 0 if batch.ok else 1


def run_handoff_suite_mode(
    args: argparse.Namespace,
    *,
    required_source_contracts: tuple[str, ...],
    required_source_granularities: tuple[str, ...],
    required_verification_scopes: tuple[str, ...],
) -> int:
    try:
        summary_paths = handoff_suite_manifest_entries(
            _load_json(args.handoff_suite_manifest),
            base_dir=args.handoff_suite_manifest.parent,
        )
        overlap_error = reject_summary_output_any_overlap(
            args.summary_json,
            (args.handoff_suite_manifest, *summary_paths),
        )
        if overlap_error:
            print(f"[trino-evidence-handoff-suite] rejected: {overlap_error}", file=sys.stderr)
            return 2
        batch = audit_handoff_summary_suite(
            summary_paths,
            require_min_inputs=args.require_min_inputs,
            required_source_contracts=required_source_contracts,
            required_source_granularities=required_source_granularities,
            required_verification_scopes=required_verification_scopes,
        )
        if args.summary_json is not None:
            if not write_summary_or_reject(
                args.summary_json,
                handoff_suite_summary_payload(
                    batch,
                    require_min_inputs=args.require_min_inputs,
                    required_source_contracts=required_source_contracts,
                    required_source_granularities=required_source_granularities,
                    required_verification_scopes=required_verification_scopes,
                ),
            ):
                return 2
    except (OSError, json.JSONDecodeError, TrinoEvidenceHandoffInputError):
        print(
            "[trino-evidence-handoff-suite] rejected: handoff suite manifest is not accepted",
            file=sys.stderr,
        )
        return 2

    print_handoff_suite_result(batch, limit=args.limit)
    return 0 if batch.ok else 1


def audit_package_boundaries(
    bundles: Iterable[Any],
    *,
    require_supported_attention: bool,
    fail_on_unknown_parser_coverage: bool,
    require_one_query_boundary: bool,
) -> TrinoCompactReadinessBatchResult:
    from query_doctor.analyzer.engine_facts import engine_fact_boundary_payload

    batch = TrinoCompactReadinessBatchResult()
    for index, bundle in enumerate(bundles, start=1):
        batch.input_count += 1
        result = audit_boundary_payload(
            engine_fact_boundary_payload(bundle),
            require_supported_attention=require_supported_attention,
            fail_on_unknown_parser_coverage=fail_on_unknown_parser_coverage,
            require_one_query_boundary=require_one_query_boundary,
        )
        add_suite_result(batch, index, result)
    return batch


def handoff_summary_payload(
    *,
    package_result: Any,
    batch: TrinoCompactReadinessBatchResult,
    status: str,
    require_min_inputs: int,
    require_supported_attention: bool,
    fail_on_unknown_parser_coverage: bool,
    require_one_query_boundary: bool,
) -> dict[str, Any]:
    return {
        "summary_kind": TRINO_EVIDENCE_HANDOFF_SUMMARY_KIND,
        "mode": "trino_evidence_handoff",
        "status": status,
        "pipeline": {
            "package_validation": "accepted",
            "boundary_export": "accepted",
            "compact_readiness_audit": status,
        },
        "boundary": support_boundary_payload(),
        "requirements": requirements_payload(
            require_min_inputs=require_min_inputs,
            require_supported_attention=require_supported_attention,
            fail_on_unknown_parser_coverage=fail_on_unknown_parser_coverage,
            require_one_query_boundary=require_one_query_boundary,
        ),
        "package": trino_evidence_package_summary_payload(package_result),
        "counts": {
            "boundary_count": batch.input_count,
            "ok_count": batch.ok_count,
            "failed_count": batch.failed_count,
            "fact_count": batch.fact_count,
            "attention_area_count": batch.attention_area_count,
            "supported_attention_area_count": batch.supported_attention_area_count,
        },
        "source_schemas": counter_payload(batch.source_schema_counts),
        "source_version_states": counter_payload(batch.source_version_state_counts),
        "support_statuses": counter_payload(batch.support_status_counts),
        "parser_coverage": counter_payload(batch.parser_coverage_counts),
        "lifecycles": counter_payload(batch.lifecycle_counts),
        "source_granularity": counter_payload(batch.source_granularity_counts),
        "diagnostic_lane": {
            "source_granularity": counter_payload(batch.source_granularity_counts),
            "evidence_readiness": counter_payload(batch.diagnostic_lane_readiness_counts),
            "verification_scope": counter_payload(batch.diagnostic_lane_verification_scope_counts),
            "fact_states": counter_payload(batch.fact_state_counts),
        },
        "fact_scopes": counter_payload(batch.fact_scope_counts),
        "fact_states": counter_payload(batch.fact_state_counts),
        "attention_states": counter_payload(batch.attention_state_counts),
        "limitation_states": counter_payload(batch.limitation_state_counts),
        "issues": {
            "counts": counter_payload(batch.issue_counts),
            "items": [
                {
                    "input_index": input_index,
                    "category": issue.category,
                    "message": issue.message,
                }
                for input_index, issue in batch.issues
            ],
        },
    }


def handoff_suite_summary_payload(
    batch: TrinoEvidenceHandoffSuiteResult,
    *,
    require_min_inputs: int,
    required_source_contracts: Iterable[str] = (),
    required_source_granularities: Iterable[str] = (),
    required_verification_scopes: Iterable[str] = (),
) -> dict[str, Any]:
    status = "ok" if batch.ok else "failed"
    return {
        "summary_kind": TRINO_EVIDENCE_HANDOFF_SUITE_SUMMARY_KIND,
        "mode": "trino_evidence_handoff_suite",
        "status": status,
        "pipeline": {
            "handoff_summary_manifest": "accepted",
            "handoff_summary_audit": status,
        },
        "boundary": support_boundary_payload(),
        "requirements": handoff_suite_requirements_payload(
            require_min_inputs=require_min_inputs,
            required_source_contracts=required_source_contracts,
            required_source_granularities=required_source_granularities,
            required_verification_scopes=required_verification_scopes,
        ),
        "counts": {
            "handoff_summary_count": batch.input_count,
            "ok_count": batch.ok_count,
            "failed_count": batch.failed_count,
            "package_sample_count": batch.package_sample_count,
            "boundary_count": batch.boundary_count,
            "fact_count": batch.fact_count,
            "attention_area_count": batch.attention_area_count,
            "supported_attention_area_count": batch.supported_attention_area_count,
        },
        "source_contracts": counter_payload(batch.source_contract_counts),
        "package_source_types": counter_payload(batch.package_source_type_counts),
        "connector_family_categories": counter_payload(batch.connector_family_counts),
        "source_schemas": counter_payload(batch.source_schema_counts),
        "source_version_states": counter_payload(batch.source_version_state_counts),
        "support_statuses": counter_payload(batch.support_status_counts),
        "parser_coverage": counter_payload(batch.parser_coverage_counts),
        "lifecycles": counter_payload(batch.lifecycle_counts),
        "source_granularity": counter_payload(batch.source_granularity_counts),
        "diagnostic_lane": {
            "source_granularity": counter_payload(batch.source_granularity_counts),
            "evidence_readiness": counter_payload(batch.diagnostic_lane_readiness_counts),
            "verification_scope": counter_payload(batch.diagnostic_lane_verification_scope_counts),
            "fact_states": counter_payload(batch.diagnostic_lane_fact_state_counts),
        },
        "issues": {
            "counts": counter_payload(batch.issue_counts),
            "items": [
                {
                    "input_index": input_index,
                    "category": issue.category,
                    "message": issue.message,
                }
                for input_index, issue in batch.issues
            ],
        },
    }


def support_boundary_payload() -> dict[str, str]:
    return {
        "support_status": TRINO_COMPACT_DIAGNOSIS_SUPPORT_STATUS,
        "support_claim": "not_claimed",
        "product_surface": "not_wired",
        "details_trusted_report_surface": "not_wired",
        "optimizer_behavior": "not_wired",
        "trino_sql_execution": "not_performed",
        "live_recent_scan": "not_wired",
        "live_query_id_diagnosis": "not_wired",
    }


def accepted_required_verification_scopes(values: Iterable[Any]) -> tuple[str, ...] | None:
    return accepted_required_labels(values, allowed=TRINO_EVIDENCE_HANDOFF_VERIFICATION_SCOPES)


def accepted_required_source_granularities(values: Iterable[Any]) -> tuple[str, ...] | None:
    return accepted_required_labels(values, allowed=TRINO_EVIDENCE_HANDOFF_SOURCE_GRANULARITIES)


def accepted_required_source_contracts(values: Iterable[Any]) -> tuple[str, ...] | None:
    contracts: set[str] = set()
    for value in values:
        if (
            not isinstance(value, str)
            or value == "unknown"
            or not TRINO_EVIDENCE_HANDOFF_SOURCE_CONTRACT_RE.fullmatch(value)
        ):
            return None
        contracts.add(value)
    return tuple(sorted(contracts))


def accepted_required_labels(
    values: Iterable[Any],
    *,
    allowed: frozenset[str],
) -> tuple[str, ...] | None:
    labels: set[str] = set()
    for value in values:
        if not isinstance(value, str) or value not in allowed:
            return None
        labels.add(value)
    return tuple(sorted(labels))


def handoff_suite_requirements_payload(
    *,
    require_min_inputs: int,
    required_source_contracts: Iterable[str] = (),
    required_source_granularities: Iterable[str] = (),
    required_verification_scopes: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "require_min_inputs": require_min_inputs,
        "require_source_contracts": sorted(required_source_contracts),
        "require_source_granularities": sorted(required_source_granularities),
        "require_verification_scopes": sorted(required_verification_scopes),
        "require_single_handoff_status": "ok",
        "require_single_package_cases": True,
        "require_support_boundary": True,
    }


def requirements_payload(
    *,
    require_min_inputs: int,
    require_supported_attention: bool,
    fail_on_unknown_parser_coverage: bool,
    require_one_query_boundary: bool,
) -> dict[str, Any]:
    return {
        "require_min_inputs": require_min_inputs,
        "require_minimum_package_cases": True,
        "require_supported_attention_per_boundary": bool(require_supported_attention),
        "fail_on_unknown_parser_coverage": bool(fail_on_unknown_parser_coverage),
        "require_one_query_boundary": bool(require_one_query_boundary),
    }


def write_summary_or_reject(path: Path | None, payload: Mapping[str, Any]) -> bool:
    if path is None:
        return True
    try:
        write_handoff_summary_json(path, payload)
    except TrinoEvidenceHandoffOutputError as exc:
        print(f"[trino-evidence-handoff] rejected: {exc}", file=sys.stderr)
        return False
    return True


def handoff_suite_manifest_entries(manifest: Any, *, base_dir: Path) -> tuple[Path, ...]:
    if not isinstance(manifest, Mapping):
        raise TrinoEvidenceHandoffInputError(
            "Trino evidence handoff suite manifest must be an object"
        )
    if set(manifest) != {"manifest_kind", "metadata", "entries"}:
        raise TrinoEvidenceHandoffInputError(
            "Trino evidence handoff suite manifest schema is invalid"
        )
    if manifest.get("manifest_kind") != TRINO_EVIDENCE_HANDOFF_SUITE_MANIFEST_KIND:
        raise TrinoEvidenceHandoffInputError(
            "Trino evidence handoff suite manifest kind is invalid"
        )

    metadata = manifest.get("metadata")
    if not isinstance(metadata, Mapping) or set(metadata) != {
        "builder_kind",
        "entry_count",
        "path_reference",
        "redaction_reviewed",
        "limitations",
    }:
        raise TrinoEvidenceHandoffInputError("Trino evidence handoff suite metadata is invalid")
    if metadata.get("builder_kind") != TRINO_EVIDENCE_HANDOFF_SUITE_MANIFEST_BUILDER_KIND:
        raise TrinoEvidenceHandoffInputError("Trino evidence handoff suite builder kind is invalid")
    if metadata.get("path_reference") != "relative_to_manifest":
        raise TrinoEvidenceHandoffInputError(
            "Trino evidence handoff suite path reference is invalid"
        )
    if metadata.get("redaction_reviewed") is not True:
        raise TrinoEvidenceHandoffInputError(
            "Trino evidence handoff suite redaction review is required"
        )
    limitations = metadata.get("limitations")
    if not isinstance(limitations, list) or "not_trino_product_support" not in limitations:
        raise TrinoEvidenceHandoffInputError("Trino evidence handoff suite limitations are invalid")

    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise TrinoEvidenceHandoffInputError("Trino evidence handoff suite entries must be a list")
    entry_count = metadata.get("entry_count")
    if not isinstance(entry_count, int) or isinstance(entry_count, bool):
        raise TrinoEvidenceHandoffInputError("Trino evidence handoff suite entry count is invalid")
    if entry_count != len(entries):
        raise TrinoEvidenceHandoffInputError("Trino evidence handoff suite entry count mismatch")

    paths: list[Path] = []
    seen_refs: set[str] = set()
    seen_paths: list[Path] = []
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != {"handoff_summary_json"}:
            raise TrinoEvidenceHandoffInputError("Trino evidence handoff suite entries are invalid")
        reference = entry["handoff_summary_json"]
        if not is_safe_relative_json_reference(reference):
            raise TrinoEvidenceHandoffInputError(
                "Trino evidence handoff suite references are invalid"
            )
        if reference in seen_refs:
            raise TrinoEvidenceHandoffInputError(
                "Trino evidence handoff suite references must be unique"
            )
        seen_refs.add(reference)
        path = base_dir / reference
        if not path.is_file():
            raise TrinoEvidenceHandoffInputError(
                "Trino evidence handoff suite referenced artifact is unavailable"
            )
        if any(same_path(path, seen) for seen in seen_paths):
            raise TrinoEvidenceHandoffInputError(
                "Trino evidence handoff suite references must be unique"
            )
        seen_paths.append(path)
        paths.append(path)
    return tuple(paths)


def audit_handoff_summary_suite(
    summary_jsons: Iterable[Path],
    *,
    require_min_inputs: int,
    required_source_contracts: Iterable[str] = (),
    required_source_granularities: Iterable[str] = (),
    required_verification_scopes: Iterable[str] = (),
) -> TrinoEvidenceHandoffSuiteResult:
    batch = TrinoEvidenceHandoffSuiteResult()
    for index, summary_json in enumerate(summary_jsons, start=1):
        batch.input_count += 1
        try:
            summary = _load_json(summary_json)
        except (OSError, json.JSONDecodeError):
            batch.failed_count += 1
            add_handoff_suite_issue(
                batch,
                index,
                "handoff_summary_unreadable",
                "One Trino handoff summary could not be read or parsed safely.",
            )
            continue
        audit_handoff_summary_payload(batch, index, summary)
    audit_handoff_suite_breadth(
        batch,
        require_min_inputs=require_min_inputs,
        required_source_contracts=required_source_contracts,
        required_source_granularities=required_source_granularities,
        required_verification_scopes=required_verification_scopes,
    )
    return batch


def audit_handoff_summary_payload(
    batch: TrinoEvidenceHandoffSuiteResult,
    index: int,
    summary: Any,
) -> None:
    before_issue_count = len(batch.issues)
    if not isinstance(summary, Mapping):
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_invalid",
            "Trino handoff summary must be a JSON object.",
        )
        batch.failed_count += 1
        return

    text = json.dumps(summary, ensure_ascii=True, sort_keys=True)
    if raw_text_issue_categories(text):
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_raw_boundary",
            "Trino handoff summary contains raw-like content.",
        )

    if summary.get("summary_kind") != TRINO_EVIDENCE_HANDOFF_SUMMARY_KIND:
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_invalid",
            "Trino handoff summary kind is not accepted.",
        )
    if summary.get("mode") != "trino_evidence_handoff" or summary.get("status") != "ok":
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_not_ready",
            "Trino handoff summary must be an accepted single-package handoff.",
        )
    if summary.get("pipeline") != {
        "package_validation": "accepted",
        "boundary_export": "accepted",
        "compact_readiness_audit": "ok",
    }:
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_pipeline_incomplete",
            "Trino handoff summary pipeline must be fully accepted.",
        )
    if summary.get("boundary") != support_boundary_payload():
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_support_boundary",
            "Trino handoff summary must keep the no-support product boundary.",
        )

    requirements = summary.get("requirements")
    if (
        not isinstance(requirements, Mapping)
        or requirements.get("require_minimum_package_cases") is not True
        or requirements.get("require_one_query_boundary") is not False
    ):
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_requirements_gap",
            "Trino handoff summary must record package-level handoff requirements.",
        )

    counts = summary.get("counts")
    if isinstance(counts, Mapping):
        boundary_count = safe_int(counts.get("boundary_count"))
        ok_count = safe_int(counts.get("ok_count"))
        failed_count = safe_int(counts.get("failed_count"))
        batch.boundary_count += boundary_count
        batch.fact_count += safe_int(counts.get("fact_count"))
        batch.attention_area_count += safe_int(counts.get("attention_area_count"))
        batch.supported_attention_area_count += safe_int(
            counts.get("supported_attention_area_count")
        )
        if boundary_count <= 0 or ok_count != boundary_count or failed_count != 0:
            add_handoff_suite_issue(
                batch,
                index,
                "handoff_summary_readiness_gap",
                "Trino handoff summary must retain only accepted boundary readiness results.",
            )
    else:
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_invalid",
            "Trino handoff summary counts must be present.",
        )

    package = summary.get("package")
    if isinstance(package, Mapping):
        sample_count = safe_int(package.get("sample_count"))
        batch.package_sample_count += sample_count
        if sample_count <= 0:
            add_handoff_suite_issue(
                batch,
                index,
                "handoff_summary_package_gap",
                "Trino handoff summary must retain package sample counts.",
            )
        source_type = safe_label(package.get("source_type"))
        if source_type != "redacted":
            batch.package_source_type_counts[source_type] += 1
        source_summary = package.get("source_summary")
        if isinstance(source_summary, Mapping):
            source_contract = safe_label(source_summary.get("source_contract_version"))
            if source_contract != "redacted":
                batch.source_contract_counts[source_contract] += 1
            connector_categories = source_summary.get("connector_family_categories")
            if isinstance(connector_categories, list):
                for raw_connector_category in connector_categories:
                    connector_category = safe_label(raw_connector_category)
                    if connector_category != "redacted":
                        batch.connector_family_counts[connector_category] += 1
        else:
            add_handoff_suite_issue(
                batch,
                index,
                "handoff_summary_package_gap",
                "Trino handoff summary source summary must be present.",
            )
    else:
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_invalid",
            "Trino handoff summary package summary must be present.",
        )

    if summary.get("issues") != {"counts": {}, "items": []}:
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_issue_gap",
            "Trino handoff summary must not retain readiness issues.",
        )

    batch.source_schema_counts.update(safe_counter(summary.get("source_schemas")))
    batch.source_version_state_counts.update(safe_counter(summary.get("source_version_states")))
    batch.support_status_counts.update(safe_counter(summary.get("support_statuses")))
    batch.parser_coverage_counts.update(safe_counter(summary.get("parser_coverage")))
    batch.lifecycle_counts.update(safe_counter(summary.get("lifecycles")))
    top_level_source_granularity = safe_counter(summary.get("source_granularity"))
    top_level_fact_states = safe_counter(summary.get("fact_states"))
    batch.source_granularity_counts.update(top_level_source_granularity)
    diagnostic_lane = summary.get("diagnostic_lane")
    if isinstance(diagnostic_lane, Mapping):
        source_granularity = safe_counter(diagnostic_lane.get("source_granularity"))
        evidence_readiness = safe_counter(diagnostic_lane.get("evidence_readiness"))
        verification_scope = safe_counter(diagnostic_lane.get("verification_scope"))
        fact_states = safe_counter(diagnostic_lane.get("fact_states"))
        if (
            not source_granularity
            or not evidence_readiness
            or not verification_scope
            or not fact_states
        ):
            add_handoff_suite_issue(
                batch,
                index,
                "handoff_summary_diagnostic_lane_gap",
                "Trino handoff summary must retain diagnostic-lane source, readiness, verification, and fact-state counters.",
            )
        if (
            source_granularity != top_level_source_granularity
            or fact_states != top_level_fact_states
        ):
            add_handoff_suite_issue(
                batch,
                index,
                "handoff_summary_diagnostic_lane_drift",
                "Trino handoff summary diagnostic-lane counters must match the retained top-level counters.",
            )
        batch.diagnostic_lane_readiness_counts.update(evidence_readiness)
        batch.diagnostic_lane_verification_scope_counts.update(verification_scope)
        batch.diagnostic_lane_fact_state_counts.update(fact_states)
    else:
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_diagnostic_lane_gap",
            "Trino handoff summary must retain diagnostic-lane counters.",
        )

    if len(batch.issues) == before_issue_count:
        batch.ok_count += 1
    else:
        batch.failed_count += 1


def audit_handoff_suite_breadth(
    batch: TrinoEvidenceHandoffSuiteResult,
    *,
    require_min_inputs: int,
    required_source_contracts: Iterable[str],
    required_source_granularities: Iterable[str],
    required_verification_scopes: Iterable[str],
) -> None:
    if batch.input_count < require_min_inputs:
        add_handoff_suite_issue(
            batch,
            None,
            "trino_handoff_suite_input_count_gap",
            "Strict Trino handoff-suite readiness requires more retained handoff summaries.",
        )
    for source_contract in required_source_contracts:
        if batch.source_contract_counts[source_contract] <= 0:
            add_handoff_suite_issue(
                batch,
                None,
                "trino_handoff_suite_source_contract_gap",
                "Strict Trino handoff-suite readiness requires each selected source contract.",
            )
    for source_granularity in required_source_granularities:
        if batch.source_granularity_counts[source_granularity] <= 0:
            add_handoff_suite_issue(
                batch,
                None,
                "trino_handoff_suite_source_granularity_gap",
                "Strict Trino handoff-suite readiness requires each selected source granularity.",
            )
    for verification_scope in required_verification_scopes:
        if batch.diagnostic_lane_verification_scope_counts[verification_scope] <= 0:
            add_handoff_suite_issue(
                batch,
                None,
                "trino_handoff_suite_verification_scope_gap",
                "Strict Trino handoff-suite readiness requires each selected verification scope.",
            )


def add_handoff_suite_issue(
    batch: TrinoEvidenceHandoffSuiteResult,
    index: int | None,
    category: str,
    message: str,
) -> None:
    issue = TrinoEvidenceHandoffSuiteIssue(category, message)
    batch.issue_counts[category] += 1
    batch.issues.append((index, issue))


def reject_summary_output_any_overlap(
    summary_json: Path | None,
    input_paths: Iterable[Path | None],
) -> str | None:
    return output_overlaps_inputs_error(
        summary_json,
        input_paths,
        message="summary JSON output must differ from every input artifact",
    )


def write_handoff_summary_json(path: Path, payload: Mapping[str, Any]) -> None:
    text = ascii_json_artifact_text(payload)
    if raw_text_issue_categories(text):
        raise TrinoEvidenceHandoffOutputError("summary JSON output would contain raw-like content")
    try:
        write_ascii_json_artifact(path, payload)
    except OSError as exc:
        raise TrinoEvidenceHandoffOutputError("summary JSON output could not be written") from exc


def reject_summary_output_overlap(summary_json: Path | None, package_json: Path) -> str | None:
    return output_overlaps_inputs_error(
        summary_json,
        (package_json,),
        message="summary JSON output must differ from the package input",
    )


def safe_label(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "unknown"
    text = json.dumps(value, ensure_ascii=True)
    if raw_text_issue_categories(text):
        return "redacted"
    return value


def safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value >= 0:
        return value
    return 0


def safe_counter(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    counts: dict[str, int] = {}
    for key, count in value.items():
        safe_key = safe_label(key)
        if safe_key != "redacted":
            counts[safe_key] = safe_int(count)
    return counts


def print_handoff_suite_result(
    batch: TrinoEvidenceHandoffSuiteResult,
    *,
    limit: int,
    out: Any = None,
) -> None:
    if out is None:
        out = sys.stdout
    status = "ok" if batch.ok else "failed"
    print(f"Trino evidence handoff suite: {status}", file=out)
    print(
        "Inputs: "
        f"handoff_summary_count={batch.input_count}, "
        f"ok={batch.ok_count}, "
        f"failed={batch.failed_count}",
        file=out,
    )
    print(
        "Boundary: "
        f"support_status={TRINO_COMPACT_DIAGNOSIS_SUPPORT_STATUS}, "
        "support_claim=not_claimed, "
        "product_surface=not_wired, "
        "trino_sql_execution=not_performed",
        file=out,
    )
    print("Artifact paths: not_printed", file=out)
    print(
        "Totals: "
        f"package_samples={batch.package_sample_count}, "
        f"boundaries={batch.boundary_count}, "
        f"facts={batch.fact_count}, "
        f"attention_areas={batch.attention_area_count}, "
        f"supported_attention_areas={batch.supported_attention_area_count}",
        file=out,
    )
    print_counter("Source contracts", batch.source_contract_counts, out=out, limit=limit)
    print_counter("Package source types", batch.package_source_type_counts, out=out, limit=limit)
    print_counter("Source schemas", batch.source_schema_counts, out=out, limit=limit)
    print_counter("Support statuses", batch.support_status_counts, out=out, limit=limit)
    print_counter("Parser coverage", batch.parser_coverage_counts, out=out, limit=limit)
    print_counter("Lifecycles", batch.lifecycle_counts, out=out, limit=limit)
    print_counter("Source granularity", batch.source_granularity_counts, out=out, limit=limit)
    print_counter(
        "Diagnostic lane readiness",
        batch.diagnostic_lane_readiness_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Diagnostic lane verification scope",
        batch.diagnostic_lane_verification_scope_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Diagnostic lane fact states",
        batch.diagnostic_lane_fact_state_counts,
        out=out,
        limit=limit,
    )
    if batch.issues:
        print_counter("Issues", batch.issue_counts, out=out, limit=limit)
        print("Issue examples:", file=out)
        for input_index, issue in batch.issues[:limit]:
            label = "suite" if input_index is None else f"input-{input_index:03d}"
            print(f"  {label}: {issue.category}: {issue.message}", file=out)
    else:
        print("Issues: none", file=out)


def print_counter(title: str, counter: Mapping[str, int], *, out: Any, limit: int) -> None:
    print(f"{title}:", file=out)
    if not counter:
        print("  <none>", file=out)
        return
    for key, count in Counter(counter).most_common(limit):
        print(f"  {key}: {count}", file=out)


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
