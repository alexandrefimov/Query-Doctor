#!/usr/bin/env python3
"""Print the safe Trino evidence package requirements contract."""

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
from query_doctor.analyzer.trino_evidence_package import (  # noqa: E402
    TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES,
    TRINO_EVIDENCE_CONTACT_SURFACES,
    TRINO_EVIDENCE_PACKAGE_MAX_DEPTH,
    TRINO_EVIDENCE_PACKAGE_MAX_JSON_BYTES,
    TRINO_EVIDENCE_PACKAGE_MAX_SAMPLES,
    TRINO_EVIDENCE_PACKAGE_SOURCE_TYPES,
    TRINO_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS,
    TRINO_EVIDENCE_REQUIRED_REDACTION_CLASSES,
    TRINO_EVIDENCE_REQUIRED_REJECTION_REASONS,
    TRINO_EVIDENCE_REQUIRED_SENTINEL_TESTS,
    TRINO_EVIDENCE_SAMPLE_SOURCE_TYPES,
    TRINO_EVIDENCE_SYNTHETIC_REJECTION_CASES,
)
from query_doctor.analyzer.trino_fixture_facts import (  # noqa: E402
    TRINO_EVENT_ACCEPTED_SOURCE_CONTRACT_VERSIONS,
    TRINO_QUERY_DETAIL_ACCEPTED_SOURCE_CONTRACT_VERSIONS,
    TRINO_QUERY_LIST_SUMMARY_KIND,
)


TRINO_EVIDENCE_REQUIREMENTS_VERSION = "trino_evidence_package_requirements_v1"


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print the raw-free Trino evidence-package requirements from the "
            "Python contract. This dev-only helper reads no Trino endpoints, "
            "prints no paths, and does not claim Trino product support."
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
    payload = trino_evidence_package_requirements_payload()
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(format_trino_evidence_package_requirements(payload))
    return 0


def trino_evidence_package_requirements_payload() -> dict[str, Any]:
    """Return the path-free Trino evidence package requirements payload."""

    return {
        "schema_version": TRINO_EVIDENCE_REQUIREMENTS_VERSION,
        "support_status": "private_preview_offline_evidence",
        "support_claim": "not_claimed",
        "product_surface": "not_wired",
        "trino_sql_execution": "not_performed",
        "live_collection": "not_performed",
        "accepted_sample_cases": list(TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES),
        "synthetic_rejection_cases": list(TRINO_EVIDENCE_SYNTHETIC_REJECTION_CASES),
        "accepted_package_source_types": sorted(TRINO_EVIDENCE_PACKAGE_SOURCE_TYPES),
        "accepted_sample_source_types": sorted(TRINO_EVIDENCE_SAMPLE_SOURCE_TYPES),
        "known_fixture_contract_labels": _known_fixture_contract_labels(),
        "contact_surfaces": sorted(TRINO_EVIDENCE_CONTACT_SURFACES),
        "redaction_note_version": REDACTION_NOTE_VERSION,
        "required_redaction_note_fields": _required_redaction_note_fields(),
        "required_redaction_classes": sorted(TRINO_EVIDENCE_REQUIRED_REDACTION_CLASSES),
        "required_rejection_reasons": list(TRINO_EVIDENCE_REQUIRED_REJECTION_REASONS),
        "required_sentinel_tests": list(TRINO_EVIDENCE_REQUIRED_SENTINEL_TESTS),
        "required_boundary_assertions": list(TRINO_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS),
        "raw_companion_archive": "none",
        "maximum_package_json_bytes": TRINO_EVIDENCE_PACKAGE_MAX_JSON_BYTES,
        "maximum_package_depth": TRINO_EVIDENCE_PACKAGE_MAX_DEPTH,
        "maximum_sample_count": TRINO_EVIDENCE_PACKAGE_MAX_SAMPLES,
        "minimum_accepted_sample_case_count": len(TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES),
        "minimum_synthetic_rejection_case_count": len(TRINO_EVIDENCE_SYNTHETIC_REJECTION_CASES),
    }


def format_trino_evidence_package_requirements(payload: Mapping[str, Any]) -> str:
    """Render safe human-readable Trino evidence package requirements."""

    lines = [
        "Trino evidence package requirements",
        f"schema_version: {payload['schema_version']}",
        "Boundary: "
        f"support_status={payload['support_status']}, "
        f"support_claim={payload['support_claim']}, "
        f"product_surface={payload['product_surface']}, "
        f"trino_sql_execution={payload['trino_sql_execution']}, "
        f"live_collection={payload['live_collection']}",
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
        "accepted_package_source_types",
        _string_sequence(payload["accepted_package_source_types"]),
    )
    _append_list(
        lines,
        "accepted_sample_source_types",
        _string_sequence(payload["accepted_sample_source_types"]),
    )
    _append_list(
        lines,
        "known_fixture_contract_labels",
        _string_sequence(payload["known_fixture_contract_labels"]),
    )
    _append_list(
        lines,
        "contact_surfaces",
        _string_sequence(payload["contact_surfaces"]),
    )
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
            "Limits:",
            f"  maximum_package_json_bytes: {payload['maximum_package_json_bytes']}",
            f"  maximum_package_depth: {payload['maximum_package_depth']}",
            f"  maximum_sample_count: {payload['maximum_sample_count']}",
            "Minimum counts:",
            f"  accepted_sample_cases: {payload['minimum_accepted_sample_case_count']}",
            f"  synthetic_rejection_cases: {payload['minimum_synthetic_rejection_case_count']}",
        ]
    )
    return "\n".join(lines)


def _known_fixture_contract_labels() -> list[str]:
    return sorted(
        {
            *TRINO_EVENT_ACCEPTED_SOURCE_CONTRACT_VERSIONS,
            *TRINO_QUERY_DETAIL_ACCEPTED_SOURCE_CONTRACT_VERSIONS,
            TRINO_QUERY_LIST_SUMMARY_KIND,
        }
    )


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


def _append_list(lines: list[str], label: str, values: Sequence[str]) -> None:
    lines.append(f"{label}:")
    for value in values:
        lines.append(f"  - {value}")


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value)


if __name__ == "__main__":
    raise SystemExit(main())
