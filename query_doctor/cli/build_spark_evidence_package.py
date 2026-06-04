"""Build sanitized Spark compact evidence packages from installed CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.spark_evidence_package import (
    format_spark_evidence_package_summary,
    validate_spark_evidence_package_payload,
)
from query_doctor.analyzer.spark_evidence_package_builder import (
    SparkEvidencePackageSampleSpec,
    build_spark_evidence_package_payload,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build one Spark compact evidence package from already-sanitized compact sample "
            "JSON files. The command does not collect from Spark, execute SQL, echo input "
            "paths or payloads, and does not claim Spark product support."
        )
    )
    parser.add_argument("--out", type=Path, required=True, help="Output sanitized package JSON.")
    parser.add_argument("--package-id", required=True, help="Safe package label.")
    parser.add_argument("--prepared-date-utc", required=True, help="YYYY-MM-DD.")
    parser.add_argument(
        "--sample",
        action="append",
        default=[],
        help="Accepted sanitized sample as CASE:SOURCE_TYPE:PATH. May be repeated.",
    )
    parser.add_argument("--source-type", default="mixed_compact_export")
    parser.add_argument("--prepared-by-role", default="operator")
    parser.add_argument(
        "--spark-version-family",
        action="append",
        default=[],
        help="Safe Spark version family such as spark_4_1. Defaults to sample-derived values.",
    )
    parser.add_argument("--collection-window-category", default="representative_sample")
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
        help="Confirm the compact samples were manually reviewed as raw-free.",
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        sample_paths = _sample_paths(args.sample)
        if _output_overlaps_samples(args.out, sample_paths):
            raise ValueError("output path must be distinct from sample inputs")
        samples = _load_samples(args.sample)
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
            synthetic_rejection_counts=_parse_synthetic_rejections(args.synthetic_rejection),
            redaction_reviewed=args.redaction_reviewed,
            sentinel_tests_passed=args.sentinel_tests_passed,
        )
        result = validate_spark_evidence_package_payload(
            payload,
            require_minimum_cases=not args.partial_ok,
        )
        _write_package(args.out, payload)
    except OSError:
        print(
            "[spark-package-builder] rejected: file could not be read or written", file=sys.stderr
        )
        return 2
    except json.JSONDecodeError:
        print("[spark-package-builder] rejected: input sample is not valid JSON", file=sys.stderr)
        return 2
    except (EngineFactContractError, ValueError) as exc:
        print(f"[spark-package-builder] rejected: {exc}", file=sys.stderr)
        return 1

    print("[spark-package-builder] written")
    print(format_spark_evidence_package_summary(result))
    return 0


def _load_samples(sample_specs: Sequence[str]) -> tuple[SparkEvidencePackageSampleSpec, ...]:
    samples: list[SparkEvidencePackageSampleSpec] = []
    for raw_spec in sample_specs:
        case, source_type, path = _parse_sample_spec(raw_spec)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise EngineFactContractError("Spark evidence package sample payload must be an object")
        samples.append(
            SparkEvidencePackageSampleSpec(
                case=case,
                source_type=source_type,
                payload=payload,
            )
        )
    return tuple(samples)


def _sample_paths(sample_specs: Sequence[str]) -> tuple[Path, ...]:
    return tuple(_parse_sample_spec(raw_spec)[2] for raw_spec in sample_specs)


def _parse_sample_spec(raw_spec: str) -> tuple[str, str, Path]:
    parts = raw_spec.split(":", 2)
    if len(parts) != 3 or not all(parts):
        raise ValueError("sample specification is invalid")
    return parts[0], parts[1], Path(parts[2])


def _parse_synthetic_rejections(raw_specs: Sequence[str]) -> dict[str, int]:
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


def _output_overlaps_samples(output_path: Path, sample_paths: Sequence[Path]) -> bool:
    output_resolved = _safe_resolved_path(output_path)
    return any(_safe_resolved_path(sample_path) == output_resolved for sample_path in sample_paths)


def _safe_resolved_path(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def _write_package(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
