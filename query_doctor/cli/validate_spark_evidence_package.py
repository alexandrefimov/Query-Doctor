"""Validate sanitized Spark compact evidence packages from the installed CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.spark_evidence_package import (
    SPARK_EVIDENCE_READINESS_PROMOTION_CANDIDATE,
    format_spark_evidence_package_summary,
    spark_evidence_package_readiness_payload,
    spark_evidence_package_summary_payload,
    validate_spark_evidence_package_payload,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate one sanitized Spark compact evidence package for readiness work. "
            "The command prints only a safe summary, never echoes input paths or payloads, "
            "and does not claim Spark product support."
        )
    )
    parser.add_argument("package_json", type=Path, help="Path to a sanitized package JSON file.")
    parser.add_argument(
        "--partial-ok",
        action="store_true",
        help="Allow packages that omit minimum case-set samples during early operator dry runs.",
    )
    parser.add_argument(
        "--max-package-bytes",
        type=int,
        default=None,
        help="Optional package JSON byte limit override for local dry runs.",
    )
    parser.add_argument(
        "--max-package-depth",
        type=int,
        default=None,
        help="Optional package JSON nesting-depth limit override for local dry runs.",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="Optional accepted sample count limit override for local dry runs.",
    )
    parser.add_argument(
        "--summary-json",
        action="store_true",
        help=(
            "Print the safe machine-readable summary JSON, including the "
            "package-level readiness verdict."
        ),
    )
    parser.add_argument(
        "--require-promotion-candidate",
        action="store_true",
        help=(
            "Fail unless the package-level readiness verdict is promotion_candidate. "
            "This does not claim Spark product support."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = _load_json(args.package_json)
        result = validate_spark_evidence_package_payload(
            payload,
            require_minimum_cases=not args.partial_ok,
            **_limit_overrides(args),
        )
    except OSError:
        print("[spark-package] rejected: input file could not be read", file=sys.stderr)
        return 2
    except json.JSONDecodeError:
        print("[spark-package] rejected: input file is not valid JSON", file=sys.stderr)
        return 2
    except EngineFactContractError as exc:
        print(f"[spark-package] rejected: {exc}", file=sys.stderr)
        return 1

    readiness = spark_evidence_package_readiness_payload(result)
    if (
        args.require_promotion_candidate
        and readiness["readiness_status"] != SPARK_EVIDENCE_READINESS_PROMOTION_CANDIDATE
    ):
        blockers = _format_safe_labels(readiness["promotion_blockers"])
        print(
            "[spark-package] rejected: package readiness is not promotion_candidate; "
            f"promotion_blockers: {blockers}",
            file=sys.stderr,
        )
        return 1

    if args.summary_json:
        print(json.dumps(spark_evidence_package_summary_payload(result), sort_keys=True))
    else:
        print(format_spark_evidence_package_summary(result))
    return 0


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _limit_overrides(args: argparse.Namespace) -> dict[str, int]:
    overrides: dict[str, int] = {}
    if args.max_package_bytes is not None:
        overrides["max_package_json_bytes"] = args.max_package_bytes
    if args.max_package_depth is not None:
        overrides["max_package_depth"] = args.max_package_depth
    if args.max_samples is not None:
        overrides["max_samples"] = args.max_samples
    return overrides


def _format_safe_labels(labels: object) -> str:
    if not isinstance(labels, list) or not labels:
        return "none"
    return ", ".join(str(label) for label in labels)


if __name__ == "__main__":
    raise SystemExit(main())
