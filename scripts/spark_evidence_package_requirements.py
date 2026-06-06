#!/usr/bin/env python3
"""Print the safe Spark evidence package requirements contract."""

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

from query_doctor.analyzer.engine_redaction_note import (  # noqa: E402
    REDACTION_NOTE_VERSION,
)
from query_doctor.analyzer.spark_evidence_package import (  # noqa: E402
    SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES,
    SPARK_EVIDENCE_DIAGNOSTIC_LANE_READINESS_VALUES,
    SPARK_EVIDENCE_DIAGNOSTIC_LANE_SOURCE_GRANULARITIES,
    SPARK_EVIDENCE_DIAGNOSTIC_LANE_VERIFICATION_SCOPES,
    SPARK_EVIDENCE_DIAGNOSTIC_SIGNAL_GROUPS,
    SPARK_EVIDENCE_DIAGNOSTIC_SIGNAL_PREFIX_GROUPS,
    SPARK_EVIDENCE_EXPECTED_DIAGNOSTIC_LANE_GATES,
    SPARK_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS,
    SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_LANE_READINESS,
    SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_SIGNAL_GROUPS,
    SPARK_EVIDENCE_REQUIRED_REDACTION_CLASSES,
    SPARK_EVIDENCE_REQUIRED_REJECTION_REASONS,
    SPARK_EVIDENCE_REQUIRED_SENTINEL_TESTS,
    SPARK_EVIDENCE_REQUIRED_SOURCE_CONTRACTS,
    SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES,
)
from query_doctor.spark.diagnosis import (  # noqa: E402
    SPARK_COMPACT_DIAGNOSTIC_LANE_NAME,
    SPARK_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
)


SPARK_EVIDENCE_REQUIREMENTS_VERSION = "spark_evidence_package_requirements_v1"


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print the raw-free Spark compact evidence-package requirements from "
            "the Python contract. This dev-only helper reads no Spark endpoints, "
            "prints no paths, and does not claim Spark product support."
        )
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable requirements JSON instead of text.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    payload = spark_evidence_package_requirements_payload()
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(format_spark_evidence_package_requirements(payload))
    return 0


def spark_evidence_package_requirements_payload() -> dict[str, Any]:
    """Return the path-free Spark evidence package requirements payload."""

    return {
        "schema_version": SPARK_EVIDENCE_REQUIREMENTS_VERSION,
        "support_status": "experimental_compact_intake",
        "support_claim": "not_claimed",
        "product_surface": "not_wired",
        "spark_job_execution": "not_performed",
        "accepted_sample_cases": list(SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES),
        "synthetic_rejection_cases": list(SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES),
        "required_source_contracts": list(SPARK_EVIDENCE_REQUIRED_SOURCE_CONTRACTS),
        "diagnostic_lane": {
            "schema_version": SPARK_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
            "lane": SPARK_COMPACT_DIAGNOSTIC_LANE_NAME,
            "promotion_status": "preview_only",
            "allowed_readiness": list(SPARK_EVIDENCE_DIAGNOSTIC_LANE_READINESS_VALUES),
            "required_readiness": list(SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_LANE_READINESS),
            "allowed_source_granularity": list(SPARK_EVIDENCE_DIAGNOSTIC_LANE_SOURCE_GRANULARITIES),
            "allowed_verification_scope": list(SPARK_EVIDENCE_DIAGNOSTIC_LANE_VERIFICATION_SCOPES),
            "required_gates": dict(SPARK_EVIDENCE_EXPECTED_DIAGNOSTIC_LANE_GATES),
        },
        "required_diagnostic_signal_groups": list(SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_SIGNAL_GROUPS),
        "diagnostic_signal_group_attention_ids": {
            group: sorted(attention_ids)
            for group, attention_ids in sorted(SPARK_EVIDENCE_DIAGNOSTIC_SIGNAL_GROUPS.items())
        },
        "diagnostic_signal_prefix_groups": dict(
            sorted(SPARK_EVIDENCE_DIAGNOSTIC_SIGNAL_PREFIX_GROUPS.items())
        ),
        "redaction_note_version": REDACTION_NOTE_VERSION,
        "required_redaction_note_fields": _required_redaction_note_fields(),
        "required_redaction_classes": sorted(SPARK_EVIDENCE_REQUIRED_REDACTION_CLASSES),
        "required_rejection_reasons": list(SPARK_EVIDENCE_REQUIRED_REJECTION_REASONS),
        "required_sentinel_tests": list(SPARK_EVIDENCE_REQUIRED_SENTINEL_TESTS),
        "required_boundary_assertions": list(SPARK_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS),
        "raw_companion_archive": "none",
        "minimum_accepted_sample_case_count": len(SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES),
        "minimum_synthetic_rejection_case_count": len(SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES),
    }


def format_spark_evidence_package_requirements(payload: Mapping[str, Any]) -> str:
    """Render safe human-readable Spark evidence package requirements."""

    lines = [
        "Spark evidence package requirements",
        f"schema_version: {payload['schema_version']}",
        "Boundary: "
        f"support_status={payload['support_status']}, "
        f"support_claim={payload['support_claim']}, "
        f"product_surface={payload['product_surface']}, "
        f"spark_job_execution={payload['spark_job_execution']}",
    ]
    _append_list(
        lines,
        "accepted_sample_cases",
        _string_sequence(payload["accepted_sample_cases"]),
    )
    _append_list(
        lines,
        "synthetic_rejection_cases",
        _string_sequence(payload["synthetic_rejection_cases"]),
    )
    _append_list(
        lines,
        "required_source_contracts",
        _string_sequence(payload["required_source_contracts"]),
    )
    diagnostic_lane = _string_mapping(payload["diagnostic_lane"])
    lines.extend(
        [
            "diagnostic_lane:",
            f"  schema_version: {diagnostic_lane['schema_version']}",
            f"  lane: {diagnostic_lane['lane']}",
            f"  promotion_status: {diagnostic_lane['promotion_status']}",
            "  allowed_readiness: "
            f"{_format_labels(_string_sequence(diagnostic_lane['allowed_readiness']))}",
            "  required_readiness: "
            f"{_format_labels(_string_sequence(diagnostic_lane['required_readiness']))}",
            "  allowed_source_granularity: "
            f"{_format_labels(_string_sequence(diagnostic_lane['allowed_source_granularity']))}",
            "  allowed_verification_scope: "
            f"{_format_labels(_string_sequence(diagnostic_lane['allowed_verification_scope']))}",
            "  required_gates: "
            f"{_format_mapping(_string_mapping(diagnostic_lane['required_gates']))}",
        ]
    )
    _append_list(
        lines,
        "required_diagnostic_signal_groups",
        _string_sequence(payload["required_diagnostic_signal_groups"]),
    )
    lines.append("diagnostic_signal_group_attention_ids:")
    for group, attention_ids in payload["diagnostic_signal_group_attention_ids"].items():
        lines.append(f"  {group}: {_format_labels(_string_sequence(attention_ids))}")
    lines.append("diagnostic_signal_prefix_groups:")
    for prefix, group in payload["diagnostic_signal_prefix_groups"].items():
        lines.append(f"  {prefix}: {group}")
    lines.append(f"redaction_note_version: {payload['redaction_note_version']}")
    _append_list(
        lines,
        "required_redaction_note_fields",
        _string_sequence(payload["required_redaction_note_fields"]),
    )
    _append_list(
        lines,
        "required_redaction_classes",
        _string_sequence(payload["required_redaction_classes"]),
    )
    _append_list(
        lines,
        "required_rejection_reasons",
        _string_sequence(payload["required_rejection_reasons"]),
    )
    _append_list(
        lines,
        "required_sentinel_tests",
        _string_sequence(payload["required_sentinel_tests"]),
    )
    _append_list(
        lines,
        "required_boundary_assertions",
        _string_sequence(payload["required_boundary_assertions"]),
    )
    lines.append(f"raw_companion_archive: {payload['raw_companion_archive']}")
    lines.extend(
        [
            "Minimum counts:",
            f"  accepted_sample_cases: {payload['minimum_accepted_sample_case_count']}",
            f"  synthetic_rejection_cases: {payload['minimum_synthetic_rejection_case_count']}",
        ]
    )
    return "\n".join(lines)


def _append_list(lines: list[str], label: str, values: Sequence[str]) -> None:
    lines.append(f"{label}:")
    for value in values:
        lines.append(f"  - {value}")


def _required_redaction_note_fields() -> list[str]:
    return [
        "package_id",
        "redaction_note_version",
        "prepared_by_role",
        "prepared_date_utc",
        "manual_reviewer_role",
        "redaction_status",
        "removed_field_classes",
        "rejected_record_counts_by_reason",
        "synthetic_sentinel_tests",
        "boundary_assertions",
        "raw_companion_archive",
    ]


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value)


def _string_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items() if isinstance(key, str)}


def _format_labels(labels: Sequence[str]) -> str:
    return ", ".join(labels) if labels else "none"


def _format_mapping(value: Mapping[str, Any]) -> str:
    if not value:
        return "none"
    return ", ".join(f"{key}={value[key]}" for key in sorted(value))


if __name__ == "__main__":
    raise SystemExit(main())
