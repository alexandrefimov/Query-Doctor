"""Build Trino offline evidence package wrappers from sanitized samples.

This module does not collect from Trino, execute SQL, or expose browser/report
output. It only assembles already-sanitized compact sample payloads into the
local evidence-package wrapper validated by `trino_evidence_package`.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.trino_evidence_package import (
    TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES,
    TRINO_EVIDENCE_PACKAGE_CASES,
    TRINO_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS,
    TRINO_EVIDENCE_REQUIRED_REDACTION_CLASSES,
    TRINO_EVIDENCE_REQUIRED_REJECTION_REASONS,
    TRINO_EVIDENCE_REQUIRED_SENTINEL_TESTS,
    TRINO_EVIDENCE_SAMPLE_SOURCE_TYPES,
    TRINO_EVIDENCE_SYNTHETIC_REJECTION_CASES,
)


@dataclass(frozen=True)
class TrinoEvidencePackageSampleSpec:
    case: str
    source_type: str
    payload: Mapping[str, Any]


def build_trino_evidence_package_payload(
    *,
    package_id: str,
    prepared_date_utc: str,
    export_window_start_utc: str,
    export_window_end_utc: str,
    samples: Sequence[TrinoEvidencePackageSampleSpec],
    source_type: str = "mixed_sanitized_export",
    prepared_by_role: str = "operator",
    manual_reviewer_role: str = "operator",
    trino_version_family: str = "unknown",
    source_contract_version: str = "unknown",
    connector_family_categories: Sequence[str] = ("unknown",),
    known_omissions: Sequence[str] = (),
    unsupported_sources: Sequence[str] = (),
    operator_retained_raw_exports: str = "no",
    synthetic_rejection_counts: Mapping[str, int] | None = None,
    redaction_reviewed: bool = False,
    sentinel_tests_passed: bool = False,
) -> dict[str, Any]:
    """Assemble a sanitized evidence package wrapper.

    The returned package is still validated by `validate_trino_evidence_package_payload`
    before use. Review confirmations are explicit to avoid silently stamping an
    operator handoff as checked.
    """

    if not redaction_reviewed:
        raise EngineFactContractError("Trino evidence package redaction review is required")
    if not sentinel_tests_passed:
        raise EngineFactContractError(
            "Trino evidence package sentinel test confirmation is required"
        )
    if not samples:
        raise EngineFactContractError("Trino evidence package samples must not be empty")

    sample_entries: list[dict[str, Any]] = []
    sample_counts: Counter[str] = Counter()
    total_sample_bytes = 0
    max_record_bytes = 0
    max_nested_depth = 0

    for sample in samples:
        _validate_sample_spec_labels(sample)
        sample_counts[sample.case] += 1
        sample_entries.append(
            {
                "case": sample.case,
                "source_type": sample.source_type,
                "payload": sample.payload,
            }
        )
        sample_bytes = _json_size(sample.payload)
        total_sample_bytes += sample_bytes
        max_record_bytes = max(max_record_bytes, sample_bytes)
        max_nested_depth = max(max_nested_depth, _max_json_depth(sample.payload))

    counts = {case: 0 for case in TRINO_EVIDENCE_PACKAGE_CASES}
    for case in TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES:
        counts[case] = sample_counts[case]
    for case, count in (synthetic_rejection_counts or {}).items():
        if case not in TRINO_EVIDENCE_SYNTHETIC_REJECTION_CASES:
            raise EngineFactContractError(
                "Trino evidence package synthetic rejection case is unsupported"
            )
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise EngineFactContractError(
                "Trino evidence package synthetic rejection count is invalid"
            )
        counts[case] = count

    return {
        "manifest": {
            "package_id": package_id,
            "package_version": "1",
            "prepared_by_role": prepared_by_role,
            "prepared_date_utc": prepared_date_utc,
            "source_type": source_type,
            "trino_version_family": trino_version_family,
            "source_contract_version": source_contract_version,
            "connector_family_categories": list(connector_family_categories),
            "export_window_utc": {
                "start": export_window_start_utc,
                "end": export_window_end_utc,
            },
            "sample_count_by_case": counts,
            "byte_count_compacted": total_sample_bytes,
            "max_record_bytes": max_record_bytes,
            "max_nested_depth": max_nested_depth,
            "redaction_status": "checked",
            "known_omissions": list(known_omissions),
            "unsupported_sources": list(unsupported_sources),
            "operator_retained_raw_exports": operator_retained_raw_exports,
            "query_doctor_contact_surface": "offline_evidence_import",
        },
        "redaction_note": {
            "package_id": package_id,
            "redaction_note_version": "1",
            "prepared_by_role": prepared_by_role,
            "prepared_date_utc": prepared_date_utc,
            "manual_reviewer_role": manual_reviewer_role,
            "redaction_status": "checked",
            "removed_field_classes": sorted(TRINO_EVIDENCE_REQUIRED_REDACTION_CLASSES),
            "rejected_record_counts_by_reason": {
                reason: 0 for reason in TRINO_EVIDENCE_REQUIRED_REJECTION_REASONS
            },
            "synthetic_sentinel_tests": {
                test_name: "yes" for test_name in TRINO_EVIDENCE_REQUIRED_SENTINEL_TESTS
            },
            "boundary_assertions": {
                assertion: True for assertion in TRINO_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS
            },
        },
        "samples": sample_entries,
    }


def _validate_sample_spec_labels(sample: TrinoEvidencePackageSampleSpec) -> None:
    if sample.case not in TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES:
        raise EngineFactContractError("Trino evidence package sample case is unsupported")
    if sample.source_type not in TRINO_EVIDENCE_SAMPLE_SOURCE_TYPES:
        raise EngineFactContractError("Trino evidence package sample source type is unsupported")


def _json_size(payload: Mapping[str, Any]) -> int:
    try:
        return len(
            json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise EngineFactContractError(
            "Trino evidence package sample must be JSON serializable"
        ) from exc


def _max_json_depth(value: Any, depth: int = 0) -> int:
    if isinstance(value, Mapping):
        if not value:
            return depth
        return max(_max_json_depth(nested, depth + 1) for nested in value.values())
    if isinstance(value, list):
        if not value:
            return depth
        return max(_max_json_depth(nested, depth + 1) for nested in value)
    return depth
