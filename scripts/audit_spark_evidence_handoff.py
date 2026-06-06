#!/usr/bin/env python3
"""Audit a Spark evidence package through the local fixture handoff pipeline."""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
from collections import Counter
from collections.abc import Iterable
from collections.abc import Mapping
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.analyzer.engine_facts import EngineFactContractError  # noqa: E402
from query_doctor.analyzer.spark_evidence_package import (  # noqa: E402
    SPARK_EVIDENCE_DIAGNOSTIC_LANE_READINESS_VALUES,
    SPARK_EVIDENCE_DIAGNOSTIC_LANE_SOURCE_GRANULARITIES,
    SPARK_EVIDENCE_DIAGNOSTIC_LANE_VERIFICATION_SCOPES,
    SPARK_EVIDENCE_READINESS_PROMOTION_CANDIDATE,
    SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_SIGNAL_GROUPS,
    SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_LANE_READINESS,
    spark_evidence_package_readiness_payload,
    validate_spark_evidence_package_payload,
)
from query_doctor.cli import export_spark_evidence_fixtures  # noqa: E402
from query_doctor.cli.export_spark_evidence_fixtures import (  # noqa: E402
    SPARK_FIXTURE_EXPORT_MANIFEST,
)
from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    ascii_json_artifact_text,
    path_overlaps_any,
    same_path,
    write_ascii_json_artifact,
)
from query_doctor.safety.manifest_references import (  # noqa: E402
    is_safe_relative_json_reference,
)
from query_doctor.spark.diagnosis import (  # noqa: E402
    SPARK_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
)
from scripts.audit_spark_compact_readiness import (  # noqa: E402
    ACCEPTED_SPARK_SOURCE_CONTRACTS,
    SparkCompactReadinessBatchResult,
    raw_text_violations,
    audit_fixture_export_manifest,
    contains_raw_sql_like_text,
    positive_int,
    print_suite_result,
    validate_report_internal_fingerprints,
)


SPARK_EVIDENCE_HANDOFF_SUMMARY_VERSION = "spark_evidence_handoff_summary_v1"
SPARK_EVIDENCE_HANDOFF_SUITE_SUMMARY_VERSION = "spark_evidence_handoff_suite_summary_v1"
SPARK_EVIDENCE_HANDOFF_SUITE_MANIFEST_KIND = "spark_evidence_handoff_suite_v1"
SPARK_EVIDENCE_HANDOFF_SUITE_MANIFEST_BUILDER_KIND = (
    "spark_evidence_handoff_suite_manifest_builder_v1"
)


class SparkEvidenceHandoffOutputError(RuntimeError):
    """Raised when the handoff audit cannot write safe output."""


class SparkEvidenceHandoffInputError(RuntimeError):
    """Raised when a Spark handoff suite input is not accepted."""


def spark_source_granularity_arg(value: str) -> str:
    if value in SPARK_EVIDENCE_DIAGNOSTIC_LANE_SOURCE_GRANULARITIES:
        return value
    raise argparse.ArgumentTypeError("Spark source granularity must be an accepted safe label")


@dataclass(frozen=True)
class SparkEvidenceHandoffSuiteIssue:
    category: str
    message: str


@dataclass
class SparkEvidenceHandoffSuiteResult:
    input_count: int = 0
    ok_count: int = 0
    failed_count: int = 0
    compact_json_count: int = 0
    fact_count: int = 0
    attention_area_count: int = 0
    supported_attention_area_count: int = 0
    source_warning_count: int = 0
    diagnostic_lane_checked_count: int = 0
    source_warning_counts: Counter[str] = field(default_factory=Counter)
    diagnostic_lane_readiness_counts: Counter[str] = field(default_factory=Counter)
    diagnostic_lane_source_granularity_counts: Counter[str] = field(default_factory=Counter)
    diagnostic_lane_verification_scope_counts: Counter[str] = field(default_factory=Counter)
    source_contract_counts: Counter[str] = field(default_factory=Counter)
    support_status_counts: Counter[str] = field(default_factory=Counter)
    parser_coverage_counts: Counter[str] = field(default_factory=Counter)
    lifecycle_counts: Counter[str] = field(default_factory=Counter)
    fact_state_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[tuple[int | None, SparkEvidenceHandoffSuiteIssue]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a sanitized Spark compact evidence package, export it to "
            "temporary fixture-ready compact JSON, and run the manifest-driven "
            "Spark compact readiness audit without printing paths or claiming "
            "Spark product support."
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
            "Optional spark_evidence_handoff_suite_v1 manifest whose entries reference "
            "retained raw-free Spark handoff summary JSON artifacts. The manifest path "
            "and referenced artifact paths are never printed."
        ),
    )
    parser.add_argument("--limit", type=positive_int, default=12, help="Rows to print per section.")
    parser.add_argument(
        "--require-min-inputs",
        type=positive_int,
        default=2,
        help="Require at least this many manifest-listed compact inputs.",
    )
    parser.add_argument(
        "--require-source-contract",
        action="append",
        choices=sorted(ACCEPTED_SPARK_SOURCE_CONTRACTS),
        default=None,
        help=(
            "Require the handoff to include at least one compact input with this source "
            "contract. Defaults to all accepted Spark compact source contracts."
        ),
    )
    parser.add_argument(
        "--require-source-granularity",
        action="append",
        type=spark_source_granularity_arg,
        default=None,
        help=(
            "Require retained handoff-suite summaries to include at least one diagnostic-lane "
            "source-granularity counter with this label. May be repeated. Only valid with "
            "--handoff-suite-manifest."
        ),
    )
    parser.add_argument(
        "--require-verification-scope",
        action="append",
        choices=sorted(SPARK_EVIDENCE_DIAGNOSTIC_LANE_VERIFICATION_SCOPES),
        default=None,
        help=(
            "Require retained handoff-suite summaries to include at least one diagnostic-lane "
            "verification-scope counter with this label. May be repeated. Only valid with "
            "--handoff-suite-manifest."
        ),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help=(
            "Optional output path for a raw-free machine-readable Spark handoff readiness "
            "summary. The path must differ from the package input."
        ),
    )
    parser.add_argument(
        "--partial-ok",
        action="store_true",
        help=(
            "Allow partial evidence packages to produce a rejected, path-free blocker "
            "summary instead of failing minimum-case validation early. This does not "
            "relax promotion-candidate handoff success."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.handoff_suite_manifest is not None:
        if args.package_json is not None:
            print(
                "[spark-handoff] rejected: handoff suite manifest cannot be combined with package input",
                file=sys.stderr,
            )
            return 2
        if args.partial_ok:
            print(
                "[spark-handoff] rejected: --partial-ok is only valid for package input",
                file=sys.stderr,
            )
            return 2
        return run_handoff_suite_mode(args)
    if args.package_json is None:
        print(
            "[spark-handoff] rejected: provide a package input or handoff suite manifest",
            file=sys.stderr,
        )
        return 2
    if args.require_source_granularity:
        print(
            "[spark-handoff] rejected: --require-source-granularity is only valid for handoff suite manifest",
            file=sys.stderr,
        )
        return 2
    if args.require_verification_scope:
        print(
            "[spark-handoff] rejected: --require-verification-scope is only valid for handoff suite manifest",
            file=sys.stderr,
        )
        return 2
    overlap_error = reject_summary_output_overlap(args.summary_json, args.package_json)
    if overlap_error:
        print(f"[spark-handoff] rejected: {overlap_error}", file=sys.stderr)
        return 2
    required_source_contracts = args.require_source_contract or sorted(
        ACCEPTED_SPARK_SOURCE_CONTRACTS
    )
    try:
        package_payload = _load_json(args.package_json)
        package_result = validate_spark_evidence_package_payload(
            package_payload,
            require_minimum_cases=not args.partial_ok,
        )
    except OSError:
        print("[spark-handoff] rejected: package file could not be read", file=sys.stderr)
        return 2
    except json.JSONDecodeError:
        print("[spark-handoff] rejected: package file is not valid JSON", file=sys.stderr)
        return 2
    except EngineFactContractError as exc:
        print(f"[spark-handoff] rejected: {exc}", file=sys.stderr)
        return 1

    readiness = spark_evidence_package_readiness_payload(package_result)
    if readiness["readiness_status"] != SPARK_EVIDENCE_READINESS_PROMOTION_CANDIDATE:
        blockers = _format_safe_labels(readiness["promotion_blockers"])
        summary = rejected_handoff_summary_payload(
            readiness,
            require_min_inputs=args.require_min_inputs,
            required_source_contracts=required_source_contracts,
            require_promotion_candidate=not args.partial_ok,
        )
        if not write_summary_or_reject(args.summary_json, summary):
            return 2
        print(
            "[spark-handoff] rejected: package readiness is not promotion_candidate; "
            f"promotion_blockers: {blockers}",
            file=sys.stderr,
        )
        return 1

    with tempfile.TemporaryDirectory(prefix="query-doctor-spark-handoff-") as temp_dir:
        fixture_dir = Path(temp_dir) / "fixture-ready"
        export_rc = _run_fixture_export_silently(args.package_json, fixture_dir)
        if export_rc != 0:
            print("[spark-handoff] rejected: fixture export failed safely", file=sys.stderr)
            return 1
        batch = audit_fixture_export_manifest(
            fixture_dir / SPARK_FIXTURE_EXPORT_MANIFEST,
            require_supported_attention=True,
            fail_on_source_warnings=True,
            require_min_inputs=args.require_min_inputs,
            required_source_contracts=required_source_contracts,
        )

    status = "ok" if batch.ok else "failed"
    summary = handoff_summary_payload(
        batch,
        package_readiness=readiness,
        status=status,
        require_min_inputs=args.require_min_inputs,
        required_source_contracts=required_source_contracts,
    )
    if not write_summary_or_reject(args.summary_json, summary):
        return 2
    print(f"Spark evidence handoff: {status}")
    print(
        "Pipeline: "
        "package_validation=accepted, "
        "fixture_export=accepted, "
        f"fixture_manifest_audit={status}"
    )
    print(
        "Boundary: "
        "readiness_status=promotion_candidate, "
        "support_claim=not_claimed, "
        "product_surface=not_wired, "
        "spark_job_execution=not_performed"
    )
    print("Output paths: not_printed")
    print_suite_result(batch, limit=args.limit)
    return 0 if batch.ok else 1


def run_handoff_suite_mode(args: argparse.Namespace) -> int:
    required_source_contracts = args.require_source_contract or sorted(
        ACCEPTED_SPARK_SOURCE_CONTRACTS
    )
    required_source_granularities = tuple(args.require_source_granularity or ())
    required_verification_scopes = tuple(args.require_verification_scope or ())
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
            print(f"[spark-handoff-suite] rejected: {overlap_error}", file=sys.stderr)
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
    except (OSError, json.JSONDecodeError, SparkEvidenceHandoffInputError):
        print(
            "[spark-handoff-suite] rejected: handoff suite manifest is not accepted",
            file=sys.stderr,
        )
        return 2
    print_handoff_suite_result(batch, limit=args.limit)
    return 0 if batch.ok else 1


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_fixture_export_silently(package_json: Path, fixture_dir: Path) -> int:
    captured_out = io.StringIO()
    captured_err = io.StringIO()
    with redirect_stdout(captured_out), redirect_stderr(captured_err):
        return export_spark_evidence_fixtures.main(
            [str(package_json), "--out-dir", str(fixture_dir)]
        )


def handoff_summary_payload(
    batch: SparkCompactReadinessBatchResult,
    *,
    package_readiness: Mapping[str, Any],
    status: str,
    require_min_inputs: int,
    required_source_contracts: Iterable[str],
) -> dict[str, Any]:
    return {
        "schema_version": SPARK_EVIDENCE_HANDOFF_SUMMARY_VERSION,
        "mode": "spark_evidence_handoff",
        "status": status,
        "pipeline": {
            "package_validation": "accepted",
            "fixture_export": "accepted",
            "fixture_manifest_audit": status,
        },
        "boundary": support_boundary_payload(),
        "readiness": {
            "readiness_status": "promotion_candidate",
            "source_warnings_clear": batch.source_warning_count == 0,
        },
        "requirements": requirements_payload(
            require_min_inputs=require_min_inputs,
            required_source_contracts=required_source_contracts,
            require_promotion_candidate=True,
        ),
        "counts": {
            "compact_json_count": batch.input_count,
            "ok_count": batch.ok_count,
            "failed_count": batch.failed_count,
            "fact_count": batch.fact_count,
            "attention_area_count": batch.attention_area_count,
            "supported_attention_area_count": batch.supported_attention_area_count,
            "source_warning_count": batch.source_warning_count,
            "diagnostic_lane_checked": batch.diagnostic_lane_checked_count,
        },
        "source_warning_counts": counter_payload(batch.source_warning_counts),
        "diagnostic_lane": {
            "schema_version": safe_label(package_readiness.get("diagnostic_lane_schema_version")),
            "readiness": counter_payload(batch.diagnostic_lane_readiness_counts),
            "source_granularity": safe_counter(
                package_readiness.get("diagnostic_lane_source_granularity")
            ),
            "verification_scope": safe_counter(
                package_readiness.get("diagnostic_lane_verification_scope")
            ),
            "required_readiness": safe_label_list(
                package_readiness.get("required_diagnostic_lane_readiness")
            ),
            "missing_readiness": safe_label_list(
                package_readiness.get("missing_diagnostic_lane_readiness")
            ),
        },
        "source_contracts": counter_payload(batch.source_contract_counts),
        "support_statuses": counter_payload(batch.support_status_counts),
        "parser_coverage": counter_payload(batch.parser_coverage_counts),
        "lifecycles": counter_payload(batch.lifecycle_counts),
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


def rejected_handoff_summary_payload(
    readiness: Mapping[str, Any],
    *,
    require_min_inputs: int,
    required_source_contracts: Iterable[str],
    require_promotion_candidate: bool,
) -> dict[str, Any]:
    return {
        "schema_version": SPARK_EVIDENCE_HANDOFF_SUMMARY_VERSION,
        "mode": "spark_evidence_handoff",
        "status": "rejected",
        "pipeline": {
            "package_validation": "accepted",
            "fixture_export": "not_run",
            "fixture_manifest_audit": "not_run",
        },
        "boundary": support_boundary_payload(),
        "requirements": requirements_payload(
            require_min_inputs=require_min_inputs,
            required_source_contracts=required_source_contracts,
            require_promotion_candidate=require_promotion_candidate,
        ),
        "readiness": {
            "readiness_status": safe_label(readiness.get("readiness_status")),
            "support_status": safe_label(readiness.get("support_status")),
            "support_claim": safe_label(readiness.get("support_claim")),
            "product_surface": safe_label(readiness.get("product_surface")),
            "spark_job_execution": safe_label(readiness.get("spark_job_execution")),
            "source_warnings_clear": bool(readiness.get("source_warnings_clear")),
            "supported_attention_area_count": safe_int(
                readiness.get("supported_attention_area_count")
            ),
            "source_warning_count": safe_int(readiness.get("source_warning_count")),
            "source_warning_counts": safe_counter(readiness.get("source_warning_counts")),
            "promotion_blockers": safe_label_list(readiness.get("promotion_blockers")),
            "diagnostic_signal_groups": safe_counter(readiness.get("diagnostic_signal_groups")),
            "missing_diagnostic_signal_groups": safe_label_list(
                readiness.get("missing_diagnostic_signal_groups")
            ),
            "missing_source_contracts": safe_label_list(readiness.get("missing_source_contracts")),
            "missing_sample_cases": safe_label_list(readiness.get("missing_sample_cases")),
            "missing_synthetic_rejection_cases": safe_label_list(
                readiness.get("missing_synthetic_rejection_cases")
            ),
        },
    }


def handoff_suite_summary_payload(
    batch: SparkEvidenceHandoffSuiteResult,
    *,
    require_min_inputs: int,
    required_source_contracts: Iterable[str],
    required_source_granularities: Iterable[str] = (),
    required_verification_scopes: Iterable[str] = (),
) -> dict[str, Any]:
    status = "ok" if batch.ok else "failed"
    return {
        "schema_version": SPARK_EVIDENCE_HANDOFF_SUITE_SUMMARY_VERSION,
        "mode": "spark_evidence_handoff_suite",
        "status": status,
        "pipeline": {
            "handoff_summary_manifest": "accepted",
            "handoff_summary_audit": status,
        },
        "boundary": support_boundary_payload(),
        "requirements": requirements_payload(
            require_min_inputs=require_min_inputs,
            required_source_contracts=required_source_contracts,
            required_source_granularities=required_source_granularities,
            required_verification_scopes=required_verification_scopes,
            require_promotion_candidate=True,
        ),
        "counts": {
            "handoff_summary_count": batch.input_count,
            "ok_count": batch.ok_count,
            "failed_count": batch.failed_count,
            "compact_json_count": batch.compact_json_count,
            "fact_count": batch.fact_count,
            "attention_area_count": batch.attention_area_count,
            "supported_attention_area_count": batch.supported_attention_area_count,
            "source_warning_count": batch.source_warning_count,
            "diagnostic_lane_checked": batch.diagnostic_lane_checked_count,
        },
        "source_warning_counts": counter_payload(batch.source_warning_counts),
        "diagnostic_lane": {
            "schema_version": SPARK_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
            "readiness": counter_payload(batch.diagnostic_lane_readiness_counts),
            "source_granularity": counter_payload(batch.diagnostic_lane_source_granularity_counts),
            "verification_scope": counter_payload(batch.diagnostic_lane_verification_scope_counts),
        },
        "source_contracts": counter_payload(batch.source_contract_counts),
        "support_statuses": counter_payload(batch.support_status_counts),
        "parser_coverage": counter_payload(batch.parser_coverage_counts),
        "lifecycles": counter_payload(batch.lifecycle_counts),
        "fact_states": counter_payload(batch.fact_state_counts),
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
        "support_status": "experimental_compact_intake",
        "support_claim": "not_claimed",
        "product_surface": "not_wired",
        "details_trusted_report_surface": "not_wired",
        "optimizer_behavior": "not_wired",
        "spark_job_execution": "not_performed",
    }


def handoff_suite_manifest_entries(manifest: Any, *, base_dir: Path) -> tuple[Path, ...]:
    if not isinstance(manifest, Mapping):
        raise SparkEvidenceHandoffInputError("Spark handoff suite manifest must be an object")
    if set(manifest) != {"manifest_kind", "metadata", "entries"}:
        raise SparkEvidenceHandoffInputError("Spark handoff suite manifest schema is invalid")
    if manifest.get("manifest_kind") != SPARK_EVIDENCE_HANDOFF_SUITE_MANIFEST_KIND:
        raise SparkEvidenceHandoffInputError("Spark handoff suite manifest kind is invalid")

    metadata = manifest.get("metadata")
    if not isinstance(metadata, Mapping) or set(metadata) != {
        "builder_kind",
        "entry_count",
        "path_reference",
        "redaction_reviewed",
        "limitations",
    }:
        raise SparkEvidenceHandoffInputError("Spark handoff suite metadata is invalid")
    if metadata.get("builder_kind") != SPARK_EVIDENCE_HANDOFF_SUITE_MANIFEST_BUILDER_KIND:
        raise SparkEvidenceHandoffInputError("Spark handoff suite builder kind is invalid")
    if metadata.get("path_reference") != "relative_to_manifest":
        raise SparkEvidenceHandoffInputError("Spark handoff suite path reference is invalid")
    if metadata.get("redaction_reviewed") is not True:
        raise SparkEvidenceHandoffInputError("Spark handoff suite redaction review is required")
    limitations = metadata.get("limitations")
    if not isinstance(limitations, list) or "not_spark_product_support" not in limitations:
        raise SparkEvidenceHandoffInputError("Spark handoff suite limitations are invalid")

    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise SparkEvidenceHandoffInputError("Spark handoff suite entries must be a list")
    entry_count = metadata.get("entry_count")
    if not isinstance(entry_count, int) or isinstance(entry_count, bool):
        raise SparkEvidenceHandoffInputError("Spark handoff suite entry count is invalid")
    if entry_count != len(entries):
        raise SparkEvidenceHandoffInputError("Spark handoff suite entry count mismatch")

    paths: list[Path] = []
    seen_refs: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != {"handoff_summary_json"}:
            raise SparkEvidenceHandoffInputError("Spark handoff suite entries are invalid")
        reference = entry["handoff_summary_json"]
        if not is_safe_relative_json_reference(reference):
            raise SparkEvidenceHandoffInputError("Spark handoff suite references are invalid")
        if reference in seen_refs:
            raise SparkEvidenceHandoffInputError("Spark handoff suite references must be unique")
        seen_refs.add(reference)
        path = base_dir / reference
        if not path.is_file():
            raise SparkEvidenceHandoffInputError(
                "Spark handoff suite referenced artifact is unavailable"
            )
        paths.append(path)
    return tuple(paths)


def audit_handoff_summary_suite(
    summary_jsons: Iterable[Path],
    *,
    require_min_inputs: int,
    required_source_contracts: Iterable[str],
    required_source_granularities: Iterable[str] = (),
    required_verification_scopes: Iterable[str] = (),
) -> SparkEvidenceHandoffSuiteResult:
    batch = SparkEvidenceHandoffSuiteResult()
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
                "One Spark handoff summary could not be read or parsed safely.",
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
    batch: SparkEvidenceHandoffSuiteResult,
    index: int,
    summary: Any,
) -> None:
    before_issue_count = len(batch.issues)
    if not isinstance(summary, Mapping):
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_invalid",
            "Spark handoff summary must be a JSON object.",
        )
        batch.failed_count += 1
        return

    text = json.dumps(summary, ensure_ascii=True, sort_keys=True)
    if contains_raw_sql_like_text(text) or validate_report_internal_fingerprints(text):
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_raw_boundary",
            "Spark handoff summary contains raw-like content.",
        )
    if any(raw_text_violations(text).values()):
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_raw_boundary",
            "Spark handoff summary contains raw-like content.",
        )

    if summary.get("schema_version") != SPARK_EVIDENCE_HANDOFF_SUMMARY_VERSION:
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_invalid",
            "Spark handoff summary schema version is not accepted.",
        )
    if summary.get("mode") != "spark_evidence_handoff" or summary.get("status") != "ok":
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_not_ready",
            "Spark handoff summary must be an accepted single-package handoff.",
        )
    if summary.get("pipeline") != {
        "package_validation": "accepted",
        "fixture_export": "accepted",
        "fixture_manifest_audit": "ok",
    }:
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_pipeline_incomplete",
            "Spark handoff summary pipeline must be fully accepted.",
        )
    if summary.get("boundary") != support_boundary_payload():
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_support_boundary",
            "Spark handoff summary must keep the no-support product boundary.",
        )

    readiness = summary.get("readiness")
    if (
        not isinstance(readiness, Mapping)
        or readiness.get("readiness_status") != SPARK_EVIDENCE_READINESS_PROMOTION_CANDIDATE
        or readiness.get("source_warnings_clear") is not True
    ):
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_readiness_gap",
            "Spark handoff summary must be warning-free promotion-candidate evidence.",
        )

    requirements = summary.get("requirements")
    if (
        not isinstance(requirements, Mapping)
        or requirements.get("require_promotion_candidate") is not True
        or requirements.get("require_supported_attention") is not True
        or requirements.get("fail_on_source_warnings") is not True
    ):
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_requirements_gap",
            "Spark handoff summary must record strict handoff requirements.",
        )

    counts = summary.get("counts")
    if isinstance(counts, Mapping):
        compact_json_count = safe_int(counts.get("compact_json_count"))
        batch.compact_json_count += compact_json_count
        batch.fact_count += safe_int(counts.get("fact_count"))
        batch.attention_area_count += safe_int(counts.get("attention_area_count"))
        supported_attention = safe_int(counts.get("supported_attention_area_count"))
        batch.supported_attention_area_count += supported_attention
        source_warnings = safe_int(counts.get("source_warning_count"))
        batch.source_warning_count += source_warnings
        diagnostic_lane_checked = safe_int(counts.get("diagnostic_lane_checked"))
        batch.diagnostic_lane_checked_count += diagnostic_lane_checked
        if supported_attention <= 0 or source_warnings != 0:
            add_handoff_suite_issue(
                batch,
                index,
                "handoff_summary_readiness_gap",
                "Spark handoff summary must include supported attention and no source warnings.",
            )
        if compact_json_count <= 0 or diagnostic_lane_checked != compact_json_count:
            add_handoff_suite_issue(
                batch,
                index,
                "handoff_summary_diagnostic_lane_gap",
                "Spark handoff summary must prove every compact input checked the diagnostic lane.",
            )
    else:
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_invalid",
            "Spark handoff summary counts must be present.",
        )

    audit_handoff_summary_diagnostic_lane(batch, index, summary.get("diagnostic_lane"))

    if summary.get("issues") != {"counts": {}, "items": []}:
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_issue_gap",
            "Spark handoff summary must not retain readiness issues.",
        )

    batch.source_warning_counts.update(safe_counter(summary.get("source_warning_counts")))
    batch.source_contract_counts.update(safe_counter(summary.get("source_contracts")))
    batch.support_status_counts.update(safe_counter(summary.get("support_statuses")))
    batch.parser_coverage_counts.update(safe_counter(summary.get("parser_coverage")))
    batch.lifecycle_counts.update(safe_counter(summary.get("lifecycles")))
    batch.fact_state_counts.update(safe_counter(summary.get("fact_states")))

    if len(batch.issues) == before_issue_count:
        batch.ok_count += 1
    else:
        batch.failed_count += 1


def audit_handoff_summary_diagnostic_lane(
    batch: SparkEvidenceHandoffSuiteResult,
    index: int,
    diagnostic_lane: Any,
) -> None:
    if not isinstance(diagnostic_lane, Mapping):
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_diagnostic_lane_gap",
            "Spark handoff summary must retain diagnostic-lane evidence.",
        )
        return

    if diagnostic_lane.get("schema_version") != SPARK_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION:
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_diagnostic_lane_gap",
            "Spark handoff summary diagnostic-lane schema version is not accepted.",
        )
    required_readiness = diagnostic_lane.get("required_readiness")
    if required_readiness != list(SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_LANE_READINESS):
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_diagnostic_lane_gap",
            "Spark handoff summary must retain required diagnostic-lane readiness.",
        )
    if diagnostic_lane.get("missing_readiness") != []:
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_diagnostic_lane_gap",
            "Spark handoff summary must not retain missing diagnostic-lane readiness.",
        )

    readiness_counts = safe_counter(diagnostic_lane.get("readiness"))
    source_granularity_counts = safe_counter(diagnostic_lane.get("source_granularity"))
    verification_scope_counts = safe_counter(diagnostic_lane.get("verification_scope"))
    batch.diagnostic_lane_readiness_counts.update(readiness_counts)
    batch.diagnostic_lane_source_granularity_counts.update(source_granularity_counts)
    batch.diagnostic_lane_verification_scope_counts.update(verification_scope_counts)
    if not readiness_counts or any(
        label not in SPARK_EVIDENCE_DIAGNOSTIC_LANE_READINESS_VALUES for label in readiness_counts
    ):
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_diagnostic_lane_gap",
            "Spark handoff summary diagnostic-lane readiness counters are not accepted.",
        )
    for required in SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_LANE_READINESS:
        if readiness_counts.get(required, 0) <= 0:
            add_handoff_suite_issue(
                batch,
                index,
                "handoff_summary_diagnostic_lane_gap",
                "Spark handoff summary must include required diagnostic-lane readiness.",
            )
    if not source_granularity_counts or any(
        label not in SPARK_EVIDENCE_DIAGNOSTIC_LANE_SOURCE_GRANULARITIES
        for label in source_granularity_counts
    ):
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_diagnostic_lane_gap",
            "Spark handoff summary diagnostic-lane source granularity is not accepted.",
        )
    if not verification_scope_counts or any(
        label not in SPARK_EVIDENCE_DIAGNOSTIC_LANE_VERIFICATION_SCOPES
        for label in verification_scope_counts
    ):
        add_handoff_suite_issue(
            batch,
            index,
            "handoff_summary_diagnostic_lane_gap",
            "Spark handoff summary diagnostic-lane verification scope is not accepted.",
        )


def audit_handoff_suite_breadth(
    batch: SparkEvidenceHandoffSuiteResult,
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
            "spark_handoff_suite_input_count_gap",
            "Strict Spark handoff-suite readiness requires more retained handoff summaries.",
        )
    for source_contract in required_source_contracts:
        if batch.source_contract_counts[source_contract] <= 0:
            add_handoff_suite_issue(
                batch,
                None,
                "spark_handoff_suite_source_contract_gap",
                "Strict Spark handoff-suite readiness requires each selected source contract.",
            )
    for source_granularity in required_source_granularities:
        if batch.diagnostic_lane_source_granularity_counts[source_granularity] <= 0:
            add_handoff_suite_issue(
                batch,
                None,
                "spark_handoff_suite_source_granularity_gap",
                "Strict Spark handoff-suite readiness requires each selected source granularity.",
            )
    for verification_scope in required_verification_scopes:
        if batch.diagnostic_lane_verification_scope_counts[verification_scope] <= 0:
            add_handoff_suite_issue(
                batch,
                None,
                "spark_handoff_suite_verification_scope_gap",
                "Strict Spark handoff-suite readiness requires each selected verification scope.",
            )


def add_handoff_suite_issue(
    batch: SparkEvidenceHandoffSuiteResult,
    index: int | None,
    category: str,
    message: str,
) -> None:
    issue = SparkEvidenceHandoffSuiteIssue(category, message)
    batch.issue_counts[category] += 1
    batch.issues.append((index, issue))


def requirements_payload(
    *,
    require_min_inputs: int,
    required_source_contracts: Iterable[str],
    require_promotion_candidate: bool,
    required_source_granularities: Iterable[str] = (),
    required_verification_scopes: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "require_diagnostic_signal_groups": list(SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_SIGNAL_GROUPS),
        "require_min_inputs": require_min_inputs,
        "require_source_contracts": sorted(required_source_contracts),
        "require_source_granularities": sorted(required_source_granularities),
        "require_verification_scopes": sorted(required_verification_scopes),
        "require_supported_attention": True,
        "fail_on_source_warnings": True,
        "require_promotion_candidate": require_promotion_candidate,
    }


def counter_payload(counter: Mapping[str, int]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def print_handoff_suite_result(
    batch: SparkEvidenceHandoffSuiteResult,
    *,
    limit: int,
    out: Any = None,
) -> None:
    if out is None:
        out = sys.stdout
    status = "ok" if batch.ok else "failed"
    print(f"Spark evidence handoff suite: {status}", file=out)
    print(
        "Inputs: "
        f"handoff_summary_count={batch.input_count}, "
        f"ok={batch.ok_count}, "
        f"failed={batch.failed_count}",
        file=out,
    )
    print(
        "Boundary: "
        "support_claim=not_claimed, "
        "product_surface=not_wired, "
        "spark_job_execution=not_performed",
        file=out,
    )
    print("Artifact paths: not_printed", file=out)
    print(
        "Totals: "
        f"compact_json={batch.compact_json_count}, "
        f"facts={batch.fact_count}, "
        f"attention_areas={batch.attention_area_count}, "
        f"supported_attention_areas={batch.supported_attention_area_count}, "
        f"source_warnings={batch.source_warning_count}, "
        f"diagnostic_lane_checked={batch.diagnostic_lane_checked_count}",
        file=out,
    )
    print_counter(
        "Diagnostic lane readiness",
        batch.diagnostic_lane_readiness_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Diagnostic lane source granularity",
        batch.diagnostic_lane_source_granularity_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Diagnostic lane verification scope",
        batch.diagnostic_lane_verification_scope_counts,
        out=out,
        limit=limit,
    )
    print_counter("Source contracts", batch.source_contract_counts, out=out, limit=limit)
    print_counter("Support statuses", batch.support_status_counts, out=out, limit=limit)
    print_counter("Parser coverage", batch.parser_coverage_counts, out=out, limit=limit)
    print_counter("Lifecycles", batch.lifecycle_counts, out=out, limit=limit)
    print_counter("Fact states", batch.fact_state_counts, out=out, limit=limit)
    print_counter("Source warning ids", batch.source_warning_counts, out=out, limit=limit)
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


def write_summary_or_reject(path: Path | None, payload: Mapping[str, Any]) -> bool:
    if path is None:
        return True
    try:
        write_handoff_summary_json(path, payload)
    except SparkEvidenceHandoffOutputError as exc:
        print(f"[spark-handoff] rejected: {exc}", file=sys.stderr)
        return False
    return True


def write_handoff_summary_json(path: Path, payload: Mapping[str, Any]) -> None:
    text = ascii_json_artifact_text(payload)
    if contains_raw_sql_like_text(text):
        raise SparkEvidenceHandoffOutputError("summary JSON output would contain raw-like content")
    if validate_report_internal_fingerprints(text):
        raise SparkEvidenceHandoffOutputError("summary JSON output would contain raw-like content")
    if any(raw_text_violations(text).values()):
        raise SparkEvidenceHandoffOutputError("summary JSON output would contain raw-like content")
    try:
        write_ascii_json_artifact(path, payload)
    except OSError as exc:
        raise SparkEvidenceHandoffOutputError("summary JSON output could not be written") from exc


def reject_summary_output_overlap(
    summary_json: Path | None,
    package_json: Path,
) -> str | None:
    if path_overlaps_any(summary_json, (package_json,)):
        return "summary JSON output must differ from the package input"
    return None


def reject_summary_output_any_overlap(
    summary_json: Path | None,
    input_paths: Iterable[Path | None],
) -> str | None:
    if path_overlaps_any(summary_json, input_paths):
        return "summary JSON output must differ from every input artifact"
    return None


def safe_label(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "unknown"
    text = json.dumps(value, ensure_ascii=True)
    if contains_raw_sql_like_text(text) or validate_report_internal_fingerprints(text):
        return "redacted"
    if any(raw_text_violations(text).values()):
        return "redacted"
    return value


def safe_label_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [safe_label(item) for item in value]


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


def _format_safe_labels(labels: object) -> str:
    if not isinstance(labels, list) or not labels:
        return "none"
    return ", ".join(str(label) for label in labels)


if __name__ == "__main__":
    raise SystemExit(main())
