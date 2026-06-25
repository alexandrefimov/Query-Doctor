#!/usr/bin/env python3
"""Gate the committed synthetic Impala primary-bottleneck coverage fixture."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.analyzer.unknown_primary_taxonomy import (  # noqa: E402
    top_unknown_category_payload,
    unknown_category_counts,
)
from scripts.audit_impala_coverage_gaps import (  # noqa: E402
    CoverageAuditResult,
    audit_summaries,
    rate_value,
    safe_unknown_reason_count_dict,
    safe_unknown_resolution_count_dict,
)


FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "impala_synthetic_coverage_gate"
SUMMARY_NAME = "batch_summary.json"
AGGREGATE_NAME = "coverage_aggregate.json"
AGGREGATE_SCHEMA_VERSION = "impala_synthetic_coverage_gate_aggregate_v1"
FIXTURE_SOURCE = "synthetic_demo_pack_0_5_0_primary_coverage_gate"
DEFAULT_MAX_UNKNOWN_PRIMARY_RATE = 20.0
DEFAULT_MIN_MEDIUM_PRIMARY_RATE = 70.0
BASELINE_TREND_POINTS = (
    {
        "label": "initial_synthetic_demo_gate",
        "unknown_primary_rate_percent": 27.2727,
        "medium_or_better_primary_rate_percent": 72.7273,
        "unknown_primary_cases": 3,
        "medium_or_better_primary_cases": 8,
        "total_cases": 11,
    },
)
CURRENT_TREND_LABEL = "client_fetch_tail_evidence_gate"


@dataclass(frozen=True)
class SyntheticCoverageGateResult:
    aggregate: dict[str, Any]
    issues: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


class SyntheticCoverageGateInputError(RuntimeError):
    """Raised when the synthetic coverage fixture cannot be audited."""


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=FIXTURE_ROOT,
        help="Synthetic fixture root. Default: tests/fixtures/impala_synthetic_coverage_gate.",
    )
    parser.add_argument(
        "--max-unknown-primary-rate",
        type=float,
        default=DEFAULT_MAX_UNKNOWN_PRIMARY_RATE,
        help="Maximum allowed full-batch unknown primary percentage. Default: 20.0.",
    )
    parser.add_argument(
        "--min-medium-primary-rate",
        type=float,
        default=DEFAULT_MIN_MEDIUM_PRIMARY_RATE,
        help="Minimum required full-batch medium-or-better primary percentage. Default: 70.0.",
    )
    return parser.parse_args(argv)


def audit_fixture(
    fixture_root: Path = FIXTURE_ROOT,
    *,
    max_unknown_primary_rate: float = DEFAULT_MAX_UNKNOWN_PRIMARY_RATE,
    min_medium_primary_rate: float = DEFAULT_MIN_MEDIUM_PRIMARY_RATE,
) -> SyntheticCoverageGateResult:
    result = load_fixture_result(fixture_root)
    aggregate = build_gate_aggregate(
        result,
        max_unknown_primary_rate=max_unknown_primary_rate,
        min_medium_primary_rate=min_medium_primary_rate,
    )
    expected = load_expected_aggregate(fixture_root)
    issues = list(gate_threshold_issues(aggregate))
    if expected != aggregate:
        issues.append("committed_coverage_aggregate_out_of_date")
    return SyntheticCoverageGateResult(aggregate=aggregate, issues=tuple(issues))


def load_fixture_result(fixture_root: Path) -> CoverageAuditResult:
    summary_path = fixture_root / SUMMARY_NAME
    try:
        return audit_summaries(
            [summary_path],
            fail_on_diagnostic_coverage_gaps=False,
            use_current_classifier_primary=True,
        )
    except OSError as exc:
        raise SyntheticCoverageGateInputError("synthetic coverage fixture is unreadable") from exc


def load_expected_aggregate(fixture_root: Path) -> dict[str, Any]:
    path = fixture_root / AGGREGATE_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SyntheticCoverageGateInputError("committed coverage aggregate is unreadable") from exc
    except json.JSONDecodeError as exc:
        raise SyntheticCoverageGateInputError(
            "committed coverage aggregate is invalid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise SyntheticCoverageGateInputError("committed coverage aggregate root is not an object")
    return payload


def build_gate_aggregate(
    result: CoverageAuditResult,
    *,
    max_unknown_primary_rate: float = DEFAULT_MAX_UNKNOWN_PRIMARY_RATE,
    min_medium_primary_rate: float = DEFAULT_MIN_MEDIUM_PRIMARY_RATE,
) -> dict[str, Any]:
    unknown_primary_cases = int(result.primary_counts.get("unknown", 0))
    unknown_rate = rate_value(unknown_primary_cases, result.total_cases)
    medium_rate = rate_value(result.medium_or_better_primary_count, result.total_cases)
    unknown_categories = unknown_category_counts(
        result.unknown_primary_reason_counts,
        unknown_primary_cases=unknown_primary_cases,
    )
    unsafe_unknown_primary_reason_cases = int_value(
        result.unknown_primary_reason_counts.get("unsafe_reason", 0)
    )
    gate_passed = (
        result.total_cases > 0
        and unknown_rate < max_unknown_primary_rate
        and medium_rate >= min_medium_primary_rate
        and unsafe_unknown_primary_reason_cases == 0
    )
    current = {
        "total_cases": result.total_cases,
        "analyzed_cases": result.analyzed_cases,
        "unknown_primary_cases": unknown_primary_cases,
        "unknown_primary_rate_percent": unknown_rate,
        "medium_or_better_primary_cases": result.medium_or_better_primary_count,
        "medium_or_better_primary_rate_percent": medium_rate,
        "unsafe_unknown_primary_reason_cases": unsafe_unknown_primary_reason_cases,
        "gate_passed": gate_passed,
    }
    return {
        "schema_version": AGGREGATE_SCHEMA_VERSION,
        "source_fixture": FIXTURE_SOURCE,
        "thresholds": {
            "max_unknown_primary_rate_percent": float(max_unknown_primary_rate),
            "min_medium_primary_rate_percent": float(min_medium_primary_rate),
        },
        "current": current,
        "unknown_primary_reason_counts": safe_unknown_reason_count_dict(
            result.unknown_primary_reason_counts
        ),
        "unknown_primary_category_counts": {
            key: value for key, value in sorted(unknown_categories.items()) if value > 0
        },
        "top_unknown_primary_categories": top_unknown_category_payload(
            unknown_categories,
            unknown_primary_cases=unknown_primary_cases,
        ),
        "unknown_primary_resolution_counts": safe_unknown_resolution_count_dict(
            result.unknown_primary_resolution_counts
        ),
        "trend": [
            *BASELINE_TREND_POINTS,
            {
                "label": CURRENT_TREND_LABEL,
                "unknown_primary_rate_percent": unknown_rate,
                "medium_or_better_primary_rate_percent": medium_rate,
                "unknown_primary_cases": unknown_primary_cases,
                "medium_or_better_primary_cases": result.medium_or_better_primary_count,
                "total_cases": result.total_cases,
            },
        ],
    }


def gate_threshold_issues(aggregate: dict[str, Any]) -> tuple[str, ...]:
    current = aggregate.get("current")
    current = current if isinstance(current, dict) else {}
    issues: list[str] = []
    if int_value(current.get("unsafe_unknown_primary_reason_cases")) > 0:
        issues.append("unsafe_unknown_primary_reason")
    if not current.get("gate_passed"):
        issues.append("synthetic_primary_coverage_gate_failed")
    if int_value(current.get("total_cases")) <= 0:
        issues.append("synthetic_primary_coverage_fixture_empty")
    return tuple(issues)


def int_value(value: object) -> int:
    try:
        return max(0, int(float(str(value).strip())))
    except (TypeError, ValueError):
        return 0


def print_result(result: SyntheticCoverageGateResult) -> None:
    current = result.aggregate["current"]
    print(
        "Synthetic Impala primary coverage: "
        f"unknown={current['unknown_primary_cases']}/{current['total_cases']} "
        f"({current['unknown_primary_rate_percent']}%); "
        f"medium+={current['medium_or_better_primary_cases']}/{current['total_cases']} "
        f"({current['medium_or_better_primary_rate_percent']}%)"
    )
    print(f"Gate: {'passed' if result.ok else 'failed'}")
    if result.issues:
        print("Issues:")
        for issue in result.issues:
            print(f"  {issue}")


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = audit_fixture(
            args.fixture_root,
            max_unknown_primary_rate=args.max_unknown_primary_rate,
            min_medium_primary_rate=args.min_medium_primary_rate,
        )
    except SyntheticCoverageGateInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_result(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
