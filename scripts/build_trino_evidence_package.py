#!/usr/bin/env python3
"""Build and validate a fixture-only Trino evidence package from sanitized samples."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.trino_evidence_package import (
    validate_trino_evidence_package_payload,
)
from query_doctor.analyzer.trino_evidence_package_builder import (
    TrinoEvidencePackageSampleSpec,
    build_trino_evidence_package_payload,
)
from scripts.validate_trino_evidence_package import print_safe_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build one fixture-only Trino evidence package from already-sanitized compact "
            "sample JSON files. The command does not collect from Trino, execute SQL, or "
            "echo input paths or payloads."
        )
    )
    parser.add_argument("--out", type=Path, required=True, help="Output sanitized package JSON.")
    parser.add_argument("--package-id", required=True, help="Safe package label.")
    parser.add_argument("--prepared-date-utc", required=True, help="YYYY-MM-DD.")
    parser.add_argument("--export-window-start-utc", required=True, help="YYYY-MM-DDTHH:00:00Z.")
    parser.add_argument("--export-window-end-utc", required=True, help="YYYY-MM-DDTHH:00:00Z.")
    parser.add_argument(
        "--sample",
        action="append",
        default=[],
        help="Accepted sanitized sample as CASE:SOURCE_TYPE:PATH. May be repeated.",
    )
    parser.add_argument("--source-type", default="mixed_sanitized_export")
    parser.add_argument("--prepared-by-role", default="operator")
    parser.add_argument("--manual-reviewer-role", default="operator")
    parser.add_argument("--trino-version-family", default="unknown")
    parser.add_argument("--source-contract-version", default="unknown")
    parser.add_argument(
        "--connector-family-category",
        action="append",
        default=[],
        help="Safe broad connector family category. Defaults to unknown.",
    )
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
        help="Confirm the samples were manually reviewed as raw-free.",
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
        samples = _load_samples(args.sample)
        payload = build_trino_evidence_package_payload(
            package_id=args.package_id,
            prepared_date_utc=args.prepared_date_utc,
            export_window_start_utc=args.export_window_start_utc,
            export_window_end_utc=args.export_window_end_utc,
            samples=samples,
            source_type=args.source_type,
            prepared_by_role=args.prepared_by_role,
            manual_reviewer_role=args.manual_reviewer_role,
            trino_version_family=args.trino_version_family,
            source_contract_version=args.source_contract_version,
            connector_family_categories=tuple(args.connector_family_category or ["unknown"]),
            known_omissions=tuple(args.known_omission),
            unsupported_sources=tuple(args.unsupported_source),
            operator_retained_raw_exports=args.operator_retained_raw_exports,
            synthetic_rejection_counts=_parse_synthetic_rejections(args.synthetic_rejection),
            redaction_reviewed=args.redaction_reviewed,
            sentinel_tests_passed=args.sentinel_tests_passed,
        )
        result = validate_trino_evidence_package_payload(
            payload,
            require_minimum_cases=not args.partial_ok,
        )
        _write_package(args.out, payload)
    except OSError:
        print(
            "[trino-package-builder] rejected: file could not be read or written", file=sys.stderr
        )
        return 2
    except json.JSONDecodeError:
        print("[trino-package-builder] rejected: input sample is not valid JSON", file=sys.stderr)
        return 2
    except (EngineFactContractError, ValueError) as exc:
        print(f"[trino-package-builder] rejected: {exc}", file=sys.stderr)
        return 1

    print("[trino-package-builder] written")
    print_safe_summary(result)
    return 0


def _load_samples(sample_specs: Sequence[str]) -> tuple[TrinoEvidencePackageSampleSpec, ...]:
    samples: list[TrinoEvidencePackageSampleSpec] = []
    for raw_spec in sample_specs:
        case, source_type, path = _parse_sample_spec(raw_spec)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise EngineFactContractError(
                "Trino evidence package sample payload must be a JSON object"
            )
        samples.append(
            TrinoEvidencePackageSampleSpec(
                case=case,
                source_type=source_type,
                payload=payload,
            )
        )
    return tuple(samples)


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


def _write_package(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
