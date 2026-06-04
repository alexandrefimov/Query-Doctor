"""Build Spark compact evidence package wrappers from sanitized samples.

This module does not collect from Spark, execute SQL, or expose product
surfaces. It only assembles already-compact sample payloads into the local
evidence-package wrapper validated by `spark_evidence_package`.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.spark_evidence_package import (
    SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES,
    SPARK_EVIDENCE_PACKAGE_CASES,
    SPARK_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS,
    SPARK_EVIDENCE_REQUIRED_REDACTION_CLASSES,
    SPARK_EVIDENCE_REQUIRED_SENTINEL_TESTS,
    SPARK_EVIDENCE_SAMPLE_SOURCE_CONTRACTS,
    SPARK_EVIDENCE_SAMPLE_SOURCE_TYPES,
    SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES,
)


@dataclass(frozen=True)
class SparkEvidencePackageSampleSpec:
    case: str
    source_type: str
    payload: Mapping[str, Any]


def build_spark_evidence_package_payload(
    *,
    package_id: str,
    prepared_date_utc: str,
    samples: Sequence[SparkEvidencePackageSampleSpec],
    source_type: str = "mixed_compact_export",
    prepared_by_role: str = "operator",
    spark_version_families: Sequence[str] = (),
    collection_window_category: str = "representative_sample",
    known_omissions: Sequence[str] = (),
    unsupported_sources: Sequence[str] = (),
    operator_retained_raw_exports: str = "no",
    synthetic_rejection_counts: Mapping[str, int] | None = None,
    redaction_reviewed: bool = False,
    sentinel_tests_passed: bool = False,
) -> dict[str, Any]:
    """Assemble a sanitized Spark compact evidence package wrapper.

    The returned package is still validated by `validate_spark_evidence_package_payload`
    before use. Review confirmations are explicit to avoid silently stamping an
    operator handoff as checked.
    """

    if not redaction_reviewed:
        raise EngineFactContractError("Spark evidence package redaction review is required")
    if not sentinel_tests_passed:
        raise EngineFactContractError(
            "Spark evidence package sentinel test confirmation is required"
        )
    if not samples:
        raise EngineFactContractError("Spark evidence package samples must not be empty")

    sample_entries: list[dict[str, Any]] = []
    sample_counts: Counter[str] = Counter()
    total_sample_bytes = 0
    max_record_bytes = 0
    max_nested_depth = 0
    source_contracts: set[str] = set()
    derived_version_families: set[str] = set()

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
        source_contracts.add(SPARK_EVIDENCE_SAMPLE_SOURCE_CONTRACTS[sample.source_type])
        derived_version_families.add(_spark_version_family(sample.payload))
        sample_bytes = _json_size(sample.payload)
        total_sample_bytes += sample_bytes
        max_record_bytes = max(max_record_bytes, sample_bytes)
        max_nested_depth = max(max_nested_depth, _max_json_depth(sample.payload))

    counts = {case: 0 for case in SPARK_EVIDENCE_PACKAGE_CASES}
    for case in SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES:
        counts[case] = sample_counts[case]
    for case, count in (synthetic_rejection_counts or {}).items():
        if case not in SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES:
            raise EngineFactContractError(
                "Spark evidence package synthetic rejection case is unsupported"
            )
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise EngineFactContractError(
                "Spark evidence package synthetic rejection count is invalid"
            )
        counts[case] = count

    version_families = tuple(spark_version_families or sorted(derived_version_families))

    return {
        "manifest": {
            "package_id": package_id,
            "package_version": "1",
            "prepared_by_role": prepared_by_role,
            "prepared_date_utc": prepared_date_utc,
            "source_type": source_type,
            "spark_version_families": list(version_families),
            "source_contracts": sorted(source_contracts),
            "collection_window_category": collection_window_category,
            "sample_count_by_case": counts,
            "byte_count_compacted": total_sample_bytes,
            "max_record_bytes": max_record_bytes,
            "max_nested_depth": max_nested_depth,
            "redaction_status": "checked",
            "known_omissions": list(known_omissions),
            "unsupported_sources": list(unsupported_sources),
            "operator_retained_raw_exports": operator_retained_raw_exports,
            "query_doctor_contact_surface": "readiness_evidence_only",
        },
        "redaction_note": {
            "package_id": package_id,
            "manual_review_status": "checked",
            "removed_field_classes": sorted(SPARK_EVIDENCE_REQUIRED_REDACTION_CLASSES),
            "boundary_assertions": sorted(SPARK_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS),
            "sentinel_tests_passed": sorted(SPARK_EVIDENCE_REQUIRED_SENTINEL_TESTS),
            "raw_companion_archive": "none",
        },
        "samples": sample_entries,
    }


def _validate_sample_spec_labels(sample: SparkEvidencePackageSampleSpec) -> None:
    if sample.case not in SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES:
        raise EngineFactContractError("Spark evidence package sample case is unsupported")
    if sample.source_type not in SPARK_EVIDENCE_SAMPLE_SOURCE_TYPES:
        raise EngineFactContractError("Spark evidence package sample source type is unsupported")


def _spark_version_family(payload: Mapping[str, Any]) -> str:
    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        return "unknown"
    value = provenance.get("sparkVersionFamily")
    if isinstance(value, str) and value:
        return value
    return "unknown"


def _json_size(payload: Mapping[str, Any]) -> int:
    try:
        return len(
            json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=True,
                sort_keys=True,
            ).encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise EngineFactContractError(
            "Spark evidence package sample must be JSON serializable"
        ) from exc


def _max_json_depth(value: Any) -> int:
    if isinstance(value, Mapping):
        if not value:
            return 1
        return 1 + max(_max_json_depth(nested) for nested in value.values())
    if isinstance(value, list):
        if not value:
            return 1
        return 1 + max(_max_json_depth(nested) for nested in value)
    return 1
