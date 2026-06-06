#!/usr/bin/env python3
"""Gate the synthetic Impala workload action-outcome aggregate."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.cli.demo_data import (  # noqa: E402
    ACTION_OUTCOMES_NAME,
    SUMMARY_NAME,
    generate_demo_pack,
)
from query_doctor.web.action_outcomes import (  # noqa: E402
    DEFAULT_METRIC_MIN_APPLIED,
    load_action_outcomes,
)
from scripts.audit_workload_diagnostics import (  # noqa: E402
    audit_summary,
    safe_count_dict,
    summary_json_payload,
)


FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "impala_synthetic_outcome_gate"
AGGREGATE_NAME = "outcome_aggregate.json"
AGGREGATE_SCHEMA_VERSION = "impala_synthetic_outcome_gate_aggregate_v1"
FIXTURE_SOURCE = "synthetic_demo_pack_0_5_0_workload_outcome_gate"
BASELINE_TREND_POINTS = (
    {
        "label": "initial_synthetic_demo_outcomes",
        "recorded_action_outcomes": 5,
        "required_family_groups": 1,
        "sample_met_family_groups": 0,
        "measured_result_family_groups": 0,
        "open_family_groups": 1,
        "gate_passed": False,
    },
)
CURRENT_TREND_LABEL = "default_threshold_measured_runtime_outcome_gate"


@dataclass(frozen=True)
class SyntheticOutcomeGateResult:
    aggregate: dict[str, Any]
    issues: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


class SyntheticOutcomeGateInputError(RuntimeError):
    """Raised when the synthetic outcome gate cannot be audited."""


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=FIXTURE_ROOT,
        help="Synthetic outcome aggregate root. Default: tests/fixtures/impala_synthetic_outcome_gate.",
    )
    parser.add_argument(
        "--action-outcome-min-applied",
        type=int,
        default=DEFAULT_METRIC_MIN_APPLIED,
        help="Comparable-rerun sample threshold for the synthetic outcome gate.",
    )
    return parser.parse_args(argv)


def audit_fixture(
    fixture_root: Path = FIXTURE_ROOT,
    *,
    action_outcome_min_applied: int = DEFAULT_METRIC_MIN_APPLIED,
) -> SyntheticOutcomeGateResult:
    aggregate = build_current_aggregate(action_outcome_min_applied=action_outcome_min_applied)
    expected = load_expected_aggregate(fixture_root)
    issues = list(gate_threshold_issues(aggregate))
    if expected != aggregate:
        issues.append("committed_outcome_aggregate_out_of_date")
    return SyntheticOutcomeGateResult(aggregate=aggregate, issues=tuple(issues))


def build_current_aggregate(
    *,
    action_outcome_min_applied: int = DEFAULT_METRIC_MIN_APPLIED,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="query-doctor-synthetic-outcome-gate-") as tmp:
        out_dir = Path(tmp) / "query-doctor-demo-pack"
        try:
            generate_demo_pack(out_dir, overwrite=False)
            result = audit_summary(
                out_dir / SUMMARY_NAME,
                action_outcomes_path=out_dir / ACTION_OUTCOMES_NAME,
                fail_on_action_outcome_readiness_gaps=True,
                action_outcome_min_applied=action_outcome_min_applied,
            )
            records = load_action_outcomes(path=out_dir / ACTION_OUTCOMES_NAME, limit=1_000_000)
        except OSError as exc:
            raise SyntheticOutcomeGateInputError("synthetic outcome fixture is unreadable") from exc
    payload = summary_json_payload(result)
    gate = safe_mapping(payload.get("action_outcome_gate"))
    requirements = safe_mapping(gate.get("requirements"))
    current = {
        "total_cases": int_value(safe_mapping(payload.get("metrics")).get("total_cases")),
        "workload_groups": int_value(safe_mapping(payload.get("metrics")).get("workload_groups")),
        "action_queue": int_value(safe_mapping(payload.get("metrics")).get("action_queue")),
        "recorded_action_outcomes": len(records),
        "required_family_groups": int_value(requirements.get("required_family_groups")),
        "sample_met_family_groups": int_value(requirements.get("sample_met_family_groups")),
        "measured_result_family_groups": int_value(
            requirements.get("measured_result_family_groups")
        ),
        "unmeasured_result_family_groups": int_value(
            requirements.get("unmeasured_result_family_groups")
        ),
        "open_family_groups": int_value(requirements.get("open_family_groups")),
        "gate_evaluable": bool(gate.get("gate_evaluable")),
        "gate_passed": bool(gate.get("gate_passed")),
    }
    return {
        "schema_version": AGGREGATE_SCHEMA_VERSION,
        "source_fixture": FIXTURE_SOURCE,
        "thresholds": gate.get("thresholds", {}),
        "current": current,
        "issue_counts": safe_mapping(payload.get("issue_counts")),
        "action_outcome_gate": gate,
        "action_outcome_requirements": safe_list(payload.get("action_outcome_requirements")),
        "counters": outcome_counter_payload(payload),
        "trend": [
            *BASELINE_TREND_POINTS,
            {
                "label": CURRENT_TREND_LABEL,
                "recorded_action_outcomes": current["recorded_action_outcomes"],
                "required_family_groups": current["required_family_groups"],
                "sample_met_family_groups": current["sample_met_family_groups"],
                "measured_result_family_groups": current["measured_result_family_groups"],
                "open_family_groups": current["open_family_groups"],
                "gate_passed": current["gate_passed"],
            },
        ],
    }


def load_expected_aggregate(fixture_root: Path) -> dict[str, Any]:
    path = fixture_root / AGGREGATE_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SyntheticOutcomeGateInputError("committed outcome aggregate is unreadable") from exc
    except json.JSONDecodeError as exc:
        raise SyntheticOutcomeGateInputError("committed outcome aggregate is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise SyntheticOutcomeGateInputError("committed outcome aggregate root is not an object")
    return payload


def outcome_counter_payload(payload: dict[str, Any]) -> dict[str, dict[str, int]]:
    counters = safe_mapping(payload.get("counters"))
    selected = (
        "action_outcome_source_counts",
        "action_outcome_group_coverage_counts",
        "action_outcome_family_counts",
        "action_outcome_family_requirement_counts",
        "action_outcome_gate_counts",
        "action_outcome_verification_counts",
        "action_outcome_result_counts",
        "action_queue_outcome_counts",
        "detail_action_hint_outcome_counts",
        "readiness_gap_counts",
    )
    return {
        name: safe_count_dict(safe_mapping(counters.get(name)).items())
        for name in selected
        if safe_mapping(counters.get(name))
    }


def gate_threshold_issues(aggregate: dict[str, Any]) -> tuple[str, ...]:
    current = safe_mapping(aggregate.get("current"))
    source = safe_mapping(safe_mapping(aggregate.get("action_outcome_gate")).get("source"))
    issues: list[str] = []
    if not current.get("gate_passed"):
        issues.append("synthetic_outcome_gate_failed")
    if not source.get("raw_free_passed"):
        issues.append("synthetic_outcome_gate_raw_free_failed")
    if int_value(current.get("recorded_action_outcomes")) <= 0:
        issues.append("synthetic_outcome_fixture_empty")
    if int_value(current.get("open_family_groups")) > 0:
        issues.append("synthetic_outcome_gate_open_family_groups")
    if int_value(current.get("measured_result_family_groups")) < int_value(
        current.get("required_family_groups")
    ):
        issues.append("synthetic_outcome_gate_missing_measured_results")
    return tuple(issues)


def safe_mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def int_value(value: object) -> int:
    try:
        return max(0, int(float(str(value).strip())))
    except (TypeError, ValueError):
        return 0


def print_result(result: SyntheticOutcomeGateResult) -> None:
    current = result.aggregate["current"]
    print(
        "Synthetic Impala action outcomes: "
        f"records={current['recorded_action_outcomes']}; "
        f"required_groups={current['required_family_groups']}; "
        f"sample_met={current['sample_met_family_groups']}; "
        f"measured={current['measured_result_family_groups']}; "
        f"open={current['open_family_groups']}"
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
            action_outcome_min_applied=args.action_outcome_min_applied,
        )
    except SyntheticOutcomeGateInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_result(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
