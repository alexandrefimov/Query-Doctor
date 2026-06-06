#!/usr/bin/env python3
"""Build a Spark evidence package from a retained one-application suite."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.analyzer.engine_facts import EngineFactContractError  # noqa: E402
from query_doctor.analyzer.spark_evidence_package import (  # noqa: E402
    SPARK_EVIDENCE_READINESS_PROMOTION_CANDIDATE,
    format_spark_evidence_package_summary,
    spark_evidence_package_readiness_payload,
    validate_spark_evidence_package_payload,
)
from query_doctor.analyzer.spark_evidence_package_builder import (  # noqa: E402
    SparkEvidencePackageSampleSpec,
    build_spark_evidence_package_payload,
)
from query_doctor.analyzer.spark_fixture_schema import SPARK_FAILURE_CATEGORIES  # noqa: E402
from query_doctor.spark.diagnosis import SPARK_LONG_ELAPSED_TIME_MS  # noqa: E402
from scripts.audit_spark_compact_readiness import (  # noqa: E402
    SparkCompactReadinessBatchResult,
    SparkCompactReadinessInputError,
    SparkOneApplicationHandoffEntry,
    audit_one_application_handoff_manifest,
    load_json_object,
    validate_one_application_handoff_manifest,
)


HISTORY_SERVER_SOURCE_CONTRACT = "spark_history_server_compact_v1"
HISTORY_SERVER_SAMPLE_SOURCE_TYPE = "spark_history_server_compact"
SQL_EXECUTION_SPECIFIC_SAMPLE_CASES = frozenset(
    {
        "finished_sql_exact_linkage",
        "failed_or_killed_allowlisted_category",
        "long_sql_elapsed_time_context",
        "adaptive_execution_checked_enabled",
        "adaptive_execution_checked_disabled",
    }
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build one sanitized Spark compact evidence package from a retained "
            "spark_one_application_handoff_suite_v1 manifest. The command validates "
            "compact/diagnosis/boundary consistency first, writes only after package "
            "validation accepts the wrapper, does not collect from Spark, and does not "
            "print artifact paths, filenames, raw values, or Spark support claims."
        )
    )
    parser.add_argument(
        "--handoff-suite-manifest",
        required=True,
        type=Path,
        help="Local spark_one_application_handoff_suite_v1 manifest.",
    )
    parser.add_argument(
        "--sample-case",
        action="append",
        default=[],
        help=(
            "Spark evidence package sample case for the next manifest entry. "
            "Repeat once per retained one-application handoff entry."
        ),
    )
    parser.add_argument("--out", type=Path, required=True, help="Output sanitized package JSON.")
    parser.add_argument("--package-id", required=True, help="Safe package label.")
    parser.add_argument("--prepared-date-utc", required=True, help="YYYY-MM-DD.")
    parser.add_argument("--source-type", default="history_server_compact_export")
    parser.add_argument("--prepared-by-role", default="operator")
    parser.add_argument(
        "--spark-version-family",
        action="append",
        default=[],
        help="Safe Spark version family such as spark_4_1. Defaults to sample-derived values.",
    )
    parser.add_argument("--collection-window-category", default="single_application")
    parser.add_argument("--known-omission", action="append", default=[])
    parser.add_argument("--unsupported-source", action="append", default=[])
    parser.add_argument(
        "--operator-retained-raw-exports",
        choices=("yes", "no"),
        default="no",
    )
    parser.add_argument(
        "--synthetic-rejection",
        action="append",
        default=[],
        help="Synthetic rejection manifest count as CASE:COUNT. May be repeated.",
    )
    parser.add_argument(
        "--redaction-reviewed",
        action="store_true",
        help="Confirm retained compact artifacts were manually reviewed as raw-free.",
    )
    parser.add_argument(
        "--sentinel-tests-passed",
        action="store_true",
        help="Confirm redaction sentinel tests passed outside this builder.",
    )
    parser.add_argument(
        "--partial-ok",
        action="store_true",
        help="Allow packages that omit minimum case-set samples during early dry runs.",
    )
    parser.add_argument(
        "--require-promotion-candidate",
        action="store_true",
        help=(
            "Fail without writing the package unless the package-level readiness verdict "
            "is promotion_candidate. This does not claim Spark product support."
        ),
    )
    parser.add_argument(
        "--require-supported-attention",
        action="store_true",
        help="Require every retained compact handoff entry to produce supported attention.",
    )
    parser.add_argument(
        "--fail-on-source-warnings",
        action="store_true",
        help="Reject retained handoff entries with compact source warning IDs.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        entries = accepted_handoff_entries(
            args.handoff_suite_manifest,
            require_supported_attention=args.require_supported_attention,
            fail_on_source_warnings=args.fail_on_source_warnings,
            require_min_inputs=max(1, len(args.sample_case)),
        )
        if len(args.sample_case) != len(entries):
            raise ValueError("sample case count must match handoff suite entries")
        input_paths = handoff_input_paths(args.handoff_suite_manifest, entries)
        if output_overlaps_inputs(args.out, input_paths):
            raise ValueError("output path must differ from every input artifact")
        samples = evidence_samples_from_entries(entries, args.sample_case)
        payload = build_spark_evidence_package_payload(
            package_id=args.package_id,
            prepared_date_utc=args.prepared_date_utc,
            samples=samples,
            source_type=args.source_type,
            prepared_by_role=args.prepared_by_role,
            spark_version_families=tuple(args.spark_version_family),
            collection_window_category=args.collection_window_category,
            known_omissions=tuple(args.known_omission),
            unsupported_sources=tuple(args.unsupported_source),
            operator_retained_raw_exports=args.operator_retained_raw_exports,
            synthetic_rejection_counts=parse_synthetic_rejections(args.synthetic_rejection),
            redaction_reviewed=args.redaction_reviewed,
            sentinel_tests_passed=args.sentinel_tests_passed,
        )
        result = validate_spark_evidence_package_payload(
            payload,
            require_minimum_cases=not args.partial_ok,
        )
        readiness = spark_evidence_package_readiness_payload(result)
        if (
            args.require_promotion_candidate
            and readiness["readiness_status"] != SPARK_EVIDENCE_READINESS_PROMOTION_CANDIDATE
        ):
            blockers = format_safe_labels(readiness["promotion_blockers"])
            raise EngineFactContractError(
                f"Spark evidence package is not promotion_candidate; promotion_blockers: {blockers}"
            )
        write_package(args.out, payload)
    except OSError:
        print(
            "[spark-one-app-package-builder] rejected: local artifact could not be read or written",
            file=sys.stderr,
        )
        return 2
    except SparkCompactReadinessInputError:
        print(
            "[spark-one-app-package-builder] rejected: handoff suite artifact is not accepted",
            file=sys.stderr,
        )
        return 2
    except (EngineFactContractError, ValueError) as exc:
        print(f"[spark-one-app-package-builder] rejected: {exc}", file=sys.stderr)
        return 1

    print("[spark-one-app-package-builder] written")
    print("input_mode: one_application_handoff_suite")
    print(format_spark_evidence_package_summary(result))
    return 0


def accepted_handoff_entries(
    manifest_path: Path,
    *,
    require_supported_attention: bool,
    fail_on_source_warnings: bool,
    require_min_inputs: int,
) -> tuple[SparkOneApplicationHandoffEntry, ...]:
    batch = audit_one_application_handoff_manifest(
        manifest_path,
        require_supported_attention=require_supported_attention,
        fail_on_source_warnings=fail_on_source_warnings,
        require_min_inputs=require_min_inputs,
        required_source_contracts=(HISTORY_SERVER_SOURCE_CONTRACT,),
    )
    if not batch.ok:
        categories = format_safe_labels(sorted(batch.issue_counts))
        raise EngineFactContractError(
            "Spark one-application handoff suite is not package-ready; "
            f"issue_categories: {categories}"
        )

    manifest = load_json_object(manifest_path)
    validation_batch = SparkCompactReadinessBatchResult()
    entries = validate_one_application_handoff_manifest(
        manifest,
        validation_batch,
        base_dir=manifest_path.parent,
    )
    if validation_batch.issues:
        raise EngineFactContractError("Spark one-application handoff suite is not accepted")
    return entries


def evidence_samples_from_entries(
    entries: Sequence[SparkOneApplicationHandoffEntry],
    sample_cases: Sequence[str],
) -> tuple[SparkEvidencePackageSampleSpec, ...]:
    samples: list[SparkEvidencePackageSampleSpec] = []
    for entry, sample_case in zip(entries, sample_cases):
        payload = load_json_object(entry.compact_json)
        if payload.get("sourceContract") != HISTORY_SERVER_SOURCE_CONTRACT:
            raise EngineFactContractError(
                "Spark one-application package bridge accepts only History Server compact inputs"
            )
        validate_sample_case_against_payload(sample_case, payload)
        samples.append(
            SparkEvidencePackageSampleSpec(
                case=sample_case,
                source_type=HISTORY_SERVER_SAMPLE_SOURCE_TYPE,
                payload=payload,
            )
        )
    return tuple(samples)


def validate_sample_case_against_payload(sample_case: str, payload: Mapping[str, Any]) -> None:
    if sample_case not in SQL_EXECUTION_SPECIFIC_SAMPLE_CASES:
        return
    provenance = payload.get("provenance")
    sql_execution = payload.get("sqlExecution")
    if not isinstance(provenance, Mapping) or not isinstance(sql_execution, Mapping):
        raise EngineFactContractError(
            "Spark one-application package bridge sample case needs accepted SQL execution evidence"
        )
    if (
        provenance.get("queryLinkage") != "exact_query"
        or sql_execution.get("factState") != "supported"
    ):
        raise EngineFactContractError(
            "Spark one-application package bridge sample case needs accepted SQL execution evidence"
        )
    if sample_case == "finished_sql_exact_linkage":
        if sql_execution.get("lifecycle") != "finished":
            raise EngineFactContractError(
                "Spark one-application package bridge finished sample needs finished SQL evidence"
            )
        return
    if sample_case == "failed_or_killed_allowlisted_category":
        if (
            sql_execution.get("lifecycle") != "failed"
            or sql_execution.get("failureCategoryState") != "supported"
            or sql_execution.get("failureCategory") not in SPARK_FAILURE_CATEGORIES
        ):
            raise EngineFactContractError(
                "Spark one-application package bridge failure sample needs allowlisted SQL failure evidence"
            )
        return
    if sample_case == "long_sql_elapsed_time_context":
        elapsed_ms = sql_execution.get("elapsedTimeMillis")
        if (
            isinstance(elapsed_ms, bool)
            or not isinstance(elapsed_ms, (float, int))
            or elapsed_ms < SPARK_LONG_ELAPSED_TIME_MS
        ):
            raise EngineFactContractError(
                "Spark one-application package bridge long-elapsed sample needs supported SQL elapsed context"
            )
        return
    adaptive = sql_execution.get("adaptiveExecution")
    if (
        not isinstance(adaptive, Mapping)
        or adaptive.get("checked") is not True
        or (
            sample_case == "adaptive_execution_checked_enabled"
            and adaptive.get("enabled") is not True
        )
        or (
            sample_case == "adaptive_execution_checked_disabled"
            and adaptive.get("enabled") is not False
        )
    ):
        raise EngineFactContractError(
            "Spark one-application package bridge adaptive sample needs checked SQL adaptive evidence"
        )


def handoff_input_paths(
    manifest_path: Path,
    entries: Sequence[SparkOneApplicationHandoffEntry],
) -> tuple[Path, ...]:
    paths: list[Path] = [manifest_path]
    for entry in entries:
        paths.extend((entry.compact_json, entry.diagnosis_json, entry.boundary_facts_json))
        if entry.handoff_summary_json is not None:
            paths.append(entry.handoff_summary_json)
        if entry.product_surface_summary_json is not None:
            paths.append(entry.product_surface_summary_json)
    return tuple(paths)


def parse_synthetic_rejections(raw_specs: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for raw_spec in raw_specs:
        parts = raw_spec.split(":", 1)
        if len(parts) != 2 or not all(parts):
            raise ValueError("synthetic rejection specification is invalid")
        try:
            count = int(parts[1])
        except ValueError as exc:
            raise ValueError("synthetic rejection count is invalid") from exc
        counts[parts[0]] = count
    return counts


def output_overlaps_inputs(output_path: Path, input_paths: Iterable[Path]) -> bool:
    output_resolved = safe_resolved_path(output_path)
    return any(safe_resolved_path(input_path) == output_resolved for input_path in input_paths)


def safe_resolved_path(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def write_package(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def format_safe_labels(labels: object) -> str:
    if not isinstance(labels, (list, tuple)) or not labels:
        return "none"
    return ", ".join(str(label) for label in labels)


if __name__ == "__main__":
    raise SystemExit(main())
