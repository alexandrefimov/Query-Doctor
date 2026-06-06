#!/usr/bin/env python3
"""Gate the synthetic Impala north-star aggregate."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.web.action_outcomes import DEFAULT_METRIC_MIN_APPLIED  # noqa: E402
from scripts.audit_impala_synthetic_coverage_gate import (  # noqa: E402
    DEFAULT_MAX_UNKNOWN_PRIMARY_RATE,
    DEFAULT_MIN_MEDIUM_PRIMARY_RATE,
    audit_fixture as audit_coverage_fixture,
)
from scripts.audit_impala_synthetic_outcome_gate import (  # noqa: E402
    audit_fixture as audit_outcome_fixture,
)
from scripts.audit_impala_north_star_gate import (  # noqa: E402
    top_unknown_resolution_class_payload,
    unknown_resolution_class_counts,
)


FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "impala_synthetic_north_star_gate"
AGGREGATE_NAME = "north_star_aggregate.json"
AGGREGATE_SCHEMA_VERSION = "impala_synthetic_north_star_gate_aggregate_v1"
FIXTURE_SOURCE = "synthetic_impala_primary_coverage_and_outcome_gates"
CURRENT_TREND_LABEL = "synthetic_primary_and_measured_outcome_gate"


@dataclass(frozen=True)
class SyntheticNorthStarGateResult:
    aggregate: dict[str, Any]
    issues: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


class SyntheticNorthStarGateInputError(RuntimeError):
    """Raised when the synthetic north-star gate cannot be audited."""


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=FIXTURE_ROOT,
        help="Synthetic north-star aggregate root. Default: tests/fixtures/impala_synthetic_north_star_gate.",
    )
    parser.add_argument(
        "--max-unknown-primary-rate",
        type=float,
        default=DEFAULT_MAX_UNKNOWN_PRIMARY_RATE,
        help="Maximum allowed synthetic unknown primary percentage. Default: 20.0.",
    )
    parser.add_argument(
        "--min-medium-primary-rate",
        type=float,
        default=DEFAULT_MIN_MEDIUM_PRIMARY_RATE,
        help="Minimum required synthetic medium-or-better primary percentage. Default: 70.0.",
    )
    parser.add_argument(
        "--action-outcome-min-applied",
        type=int,
        default=DEFAULT_METRIC_MIN_APPLIED,
        help="Comparable-rerun sample threshold for synthetic outcome feedback.",
    )
    return parser.parse_args(argv)


def audit_fixture(
    fixture_root: Path = FIXTURE_ROOT,
    *,
    max_unknown_primary_rate: float = DEFAULT_MAX_UNKNOWN_PRIMARY_RATE,
    min_medium_primary_rate: float = DEFAULT_MIN_MEDIUM_PRIMARY_RATE,
    action_outcome_min_applied: int = DEFAULT_METRIC_MIN_APPLIED,
) -> SyntheticNorthStarGateResult:
    coverage = audit_coverage_fixture(
        max_unknown_primary_rate=max_unknown_primary_rate,
        min_medium_primary_rate=min_medium_primary_rate,
    )
    outcome = audit_outcome_fixture(action_outcome_min_applied=action_outcome_min_applied)
    aggregate = build_gate_aggregate(
        coverage.aggregate,
        outcome.aggregate,
        coverage_ok=coverage.ok,
        outcome_ok=outcome.ok,
    )
    expected = load_expected_aggregate(fixture_root)
    issues = [
        *prefixed_issues("coverage", coverage.issues),
        *prefixed_issues("outcome", outcome.issues),
        *gate_threshold_issues(aggregate),
    ]
    if expected != aggregate:
        issues.append("committed_north_star_aggregate_out_of_date")
    return SyntheticNorthStarGateResult(aggregate=aggregate, issues=tuple(issues))


def build_gate_aggregate(
    coverage: dict[str, Any],
    outcome: dict[str, Any],
    *,
    coverage_ok: bool,
    outcome_ok: bool,
) -> dict[str, Any]:
    coverage_current = safe_mapping(coverage.get("current"))
    outcome_current = safe_mapping(outcome.get("current"))
    gate_passed = bool(coverage_ok and outcome_ok)
    unknown_primary_cases = int_value(coverage_current.get("unknown_primary_cases"))
    unknown_resolution_classes = synthetic_unknown_resolution_class_counts(
        coverage,
        unknown_primary_cases=unknown_primary_cases,
    )
    current = {
        "coverage_gate_passed": bool(coverage_ok),
        "outcome_gate_passed": bool(outcome_ok),
        "unknown_primary_cases": unknown_primary_cases,
        "unknown_primary_rate_percent": float_value(
            coverage_current.get("unknown_primary_rate_percent")
        ),
        "medium_or_better_primary_cases": int_value(
            coverage_current.get("medium_or_better_primary_cases")
        ),
        "medium_or_better_primary_rate_percent": float_value(
            coverage_current.get("medium_or_better_primary_rate_percent")
        ),
        "recorded_action_outcomes": int_value(outcome_current.get("recorded_action_outcomes")),
        "measured_result_family_groups": int_value(
            outcome_current.get("measured_result_family_groups")
        ),
        "open_outcome_family_groups": int_value(outcome_current.get("open_family_groups")),
        "unknown_primary_evidence_gap_cases": int_value(
            unknown_resolution_classes.get("deterministic_evidence_gap")
        ),
        "unknown_primary_boundary_cases": int_value(
            unknown_resolution_classes.get("no_action_boundary", 0)
            + unknown_resolution_classes.get("out_of_scope_boundary", 0)
        ),
        "unknown_primary_collector_gap_cases": int_value(
            unknown_resolution_classes.get("collector_wall_clock_gap")
        ),
        "unknown_primary_unclassified_resolution_cases": int_value(
            unknown_resolution_classes.get("unknown_resolution_not_reported", 0)
            + unknown_resolution_classes.get("unknown_resolution_unmapped", 0)
        ),
        "gate_passed": gate_passed,
    }
    return {
        "schema_version": AGGREGATE_SCHEMA_VERSION,
        "source_fixture": FIXTURE_SOURCE,
        "thresholds": {
            "coverage": safe_mapping(coverage.get("thresholds")),
            "outcome": safe_mapping(outcome.get("thresholds")),
        },
        "current": current,
        "coverage": coverage_summary_payload(
            coverage,
            unknown_resolution_classes=unknown_resolution_classes,
            unknown_primary_cases=unknown_primary_cases,
        ),
        "outcome": outcome_summary_payload(outcome),
        "trend": [
            {
                "label": CURRENT_TREND_LABEL,
                "unknown_primary_rate_percent": current["unknown_primary_rate_percent"],
                "medium_or_better_primary_rate_percent": current[
                    "medium_or_better_primary_rate_percent"
                ],
                "recorded_action_outcomes": current["recorded_action_outcomes"],
                "measured_result_family_groups": current["measured_result_family_groups"],
                "open_outcome_family_groups": current["open_outcome_family_groups"],
                "unknown_primary_evidence_gap_cases": current["unknown_primary_evidence_gap_cases"],
                "unknown_primary_boundary_cases": current["unknown_primary_boundary_cases"],
                "gate_passed": current["gate_passed"],
            }
        ],
    }


def coverage_summary_payload(
    coverage: dict[str, Any],
    *,
    unknown_resolution_classes: Counter[str],
    unknown_primary_cases: int,
) -> dict[str, Any]:
    current = safe_mapping(coverage.get("current"))
    return {
        "current": current,
        "unknown_primary_reason_counts": safe_mapping(
            coverage.get("unknown_primary_reason_counts")
        ),
        "unknown_primary_resolution_counts": safe_mapping(
            coverage.get("unknown_primary_resolution_counts")
        ),
        "unknown_primary_resolution_class_counts": {
            key: value for key, value in sorted(unknown_resolution_classes.items()) if value > 0
        },
        "top_unknown_primary_resolution_classes": top_unknown_resolution_class_payload(
            unknown_resolution_classes,
            unknown_primary_cases=unknown_primary_cases,
        ),
    }


def outcome_summary_payload(outcome: dict[str, Any]) -> dict[str, Any]:
    counters = safe_mapping(outcome.get("counters"))
    return {
        "current": safe_mapping(outcome.get("current")),
        "action_outcome_requirements": safe_list(outcome.get("action_outcome_requirements")),
        "action_outcome_gate_counts": safe_mapping(counters.get("action_outcome_gate_counts")),
        "action_outcome_result_counts": safe_mapping(counters.get("action_outcome_result_counts")),
    }


def load_expected_aggregate(fixture_root: Path) -> dict[str, Any]:
    path = fixture_root / AGGREGATE_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SyntheticNorthStarGateInputError(
            "committed north-star aggregate is unreadable"
        ) from exc
    except json.JSONDecodeError as exc:
        raise SyntheticNorthStarGateInputError(
            "committed north-star aggregate is invalid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise SyntheticNorthStarGateInputError(
            "committed north-star aggregate root is not an object"
        )
    return payload


def prefixed_issues(prefix: str, issues: Iterable[str]) -> tuple[str, ...]:
    return tuple(f"{prefix}_{issue}" for issue in issues)


def gate_threshold_issues(aggregate: dict[str, Any]) -> tuple[str, ...]:
    current = safe_mapping(aggregate.get("current"))
    issues: list[str] = []
    if not current.get("coverage_gate_passed"):
        issues.append("north_star_coverage_gate_failed")
    if not current.get("outcome_gate_passed"):
        issues.append("north_star_outcome_gate_failed")
    if not current.get("gate_passed"):
        issues.append("synthetic_north_star_gate_failed")
    return tuple(issues)


def safe_mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def synthetic_unknown_resolution_class_counts(
    coverage: dict[str, Any],
    *,
    unknown_primary_cases: int,
) -> Counter[str]:
    resolution_counts = Counter(safe_mapping(coverage.get("unknown_primary_resolution_counts")))
    return unknown_resolution_class_counts(
        resolution_counts,
        unknown_primary_cases=unknown_primary_cases,
    )


def int_value(value: object) -> int:
    try:
        return max(0, int(float(str(value).strip())))
    except (TypeError, ValueError):
        return 0


def float_value(value: object) -> float:
    try:
        return round(float(str(value).strip()), 4)
    except (TypeError, ValueError):
        return 0.0


def print_result(result: SyntheticNorthStarGateResult) -> None:
    current = result.aggregate["current"]
    print(
        "Synthetic Impala north-star: "
        f"unknown={current['unknown_primary_rate_percent']}%; "
        f"medium+={current['medium_or_better_primary_rate_percent']}%; "
        f"outcome_measured_groups={current['measured_result_family_groups']}; "
        f"outcome_open_groups={current['open_outcome_family_groups']}"
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
            action_outcome_min_applied=args.action_outcome_min_applied,
        )
    except SyntheticNorthStarGateInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_result(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
