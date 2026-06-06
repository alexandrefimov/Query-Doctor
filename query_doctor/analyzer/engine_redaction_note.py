"""Shared raw-free evidence-package redaction note validation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.engine_intake_primitives import (
    SAFE_CLASS_LABEL_RE,
    non_negative_int,
    required_mapping,
    safe_class_label,
    safe_label_list,
    safe_package_label,
    utc_date,
    version_text,
)


REDACTION_NOTE_VERSION = "1"


def validate_redaction_note_v1(
    redaction_note: Mapping[str, Any],
    *,
    package_id: str,
    required_classes: Iterable[str],
    required_sentinel_tests: Iterable[str],
    required_assertions: Iterable[str],
    required_rejection_reasons: Iterable[str],
    engine_label: str,
) -> None:
    """Validate the shared evidence-package redaction note v1 contract."""

    required_class_set = _safe_required_labels(required_classes)
    required_sentinel_set = _safe_required_labels(required_sentinel_tests)
    required_assertion_set = _safe_required_labels(required_assertions)
    required_reason_set = _safe_required_labels(required_rejection_reasons)

    if _safe_package_label(redaction_note, "package_id", engine_label) != package_id:
        raise EngineFactContractError(f"{engine_label} evidence package redaction note id mismatch")
    if _version_text(redaction_note, "redaction_note_version", engine_label) != (
        REDACTION_NOTE_VERSION
    ):
        raise EngineFactContractError(
            f"{engine_label} evidence package redaction note version is unsupported"
        )
    _safe_class_label(redaction_note, "prepared_by_role", engine_label)
    _utc_date(redaction_note, "prepared_date_utc", engine_label)
    _safe_class_label(redaction_note, "manual_reviewer_role", engine_label)
    if _safe_class_label(redaction_note, "redaction_status", engine_label) != "checked":
        raise EngineFactContractError(
            f"{engine_label} evidence package redaction note is not checked"
        )

    removed_classes = set(
        _safe_label_list(
            redaction_note,
            "removed_field_classes",
            engine_label,
            allow_empty=False,
        )
    )
    if not required_class_set.issubset(removed_classes):
        raise EngineFactContractError(
            f"{engine_label} evidence package redaction classes are incomplete"
        )

    counts = _required_mapping(redaction_note, "rejected_record_counts_by_reason", engine_label)
    for reason, _value in counts.items():
        _safe_label(reason, f"{engine_label} evidence package rejection reason is invalid")
        _non_negative_int(counts, reason, engine_label)
    missing_reasons = required_reason_set - set(counts)
    if missing_reasons:
        raise EngineFactContractError(
            f"{engine_label} evidence package rejection counts are incomplete"
        )

    sentinel_tests = _required_mapping(redaction_note, "synthetic_sentinel_tests", engine_label)
    for test_name, value in sentinel_tests.items():
        _safe_label(test_name, f"{engine_label} evidence package sentinel test name is invalid")
        if value != "yes":
            raise EngineFactContractError(
                f"{engine_label} evidence package sentinel tests are incomplete"
            )
    if not required_sentinel_set.issubset(set(sentinel_tests)):
        raise EngineFactContractError(
            f"{engine_label} evidence package sentinel tests are incomplete"
        )

    assertions = _required_mapping(redaction_note, "boundary_assertions", engine_label)
    for assertion_name, value in assertions.items():
        _safe_label(
            assertion_name,
            f"{engine_label} evidence package boundary assertion name is invalid",
        )
        if value is not True:
            raise EngineFactContractError(
                f"{engine_label} evidence package boundary assertion failed"
            )
    if not required_assertion_set.issubset(set(assertions)):
        raise EngineFactContractError(
            f"{engine_label} evidence package boundary assertions are incomplete"
        )

    if _safe_class_label(redaction_note, "raw_companion_archive", engine_label) != "none":
        raise EngineFactContractError(
            f"{engine_label} evidence package raw companion archive is not allowed"
        )


def _safe_required_labels(values: Iterable[str]) -> set[str]:
    labels = set(values)
    for label in labels:
        _safe_label(label, "Evidence package redaction note required label is invalid")
    return labels


def _safe_package_label(payload: Mapping[str, Any], field_name: str, engine_label: str) -> str:
    return safe_package_label(
        payload,
        field_name,
        missing_message=f"{engine_label} evidence package redaction note missing {field_name}",
        unsafe_message=f"{engine_label} evidence package label is not safe",
    )


def _safe_class_label(payload: Mapping[str, Any], field_name: str, engine_label: str) -> str:
    return safe_class_label(
        payload,
        field_name,
        missing_message=f"{engine_label} evidence package redaction note missing {field_name}",
        unsafe_message=f"{engine_label} evidence package {field_name} is not a safe label",
    )


def _safe_label(value: object, message: str) -> str:
    if not isinstance(value, str) or not SAFE_CLASS_LABEL_RE.fullmatch(value):
        raise EngineFactContractError(message)
    return value


def _version_text(payload: Mapping[str, Any], field_name: str, engine_label: str) -> str:
    return version_text(
        payload,
        field_name,
        missing_message=f"{engine_label} evidence package redaction note missing {field_name}",
        unsupported_message=(
            f"{engine_label} evidence package redaction note {field_name} is unsupported"
        ),
    )


def _safe_label_list(
    payload: Mapping[str, Any],
    field_name: str,
    engine_label: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    return safe_label_list(
        payload,
        field_name,
        missing_message=f"{engine_label} evidence package redaction note missing {field_name}",
        unsafe_message=f"{engine_label} evidence package {field_name} contains unsafe label",
        empty_message=f"{engine_label} evidence package {field_name} must not be empty",
        allow_empty=allow_empty,
    )


def _utc_date(payload: Mapping[str, Any], field_name: str, engine_label: str) -> str:
    return utc_date(
        payload,
        field_name,
        missing_message=f"{engine_label} evidence package redaction note missing {field_name}",
        invalid_message=(
            f"{engine_label} evidence package redaction note {field_name} is not a UTC date"
        ),
    )


def _non_negative_int(payload: Mapping[str, Any], field_name: str, engine_label: str) -> int:
    return non_negative_int(
        payload,
        field_name,
        invalid_message=(
            f"{engine_label} evidence package redaction note {field_name} must be non-negative"
        ),
    )


def _required_mapping(
    payload: Mapping[str, Any],
    field_name: str,
    engine_label: str,
) -> Mapping[str, Any]:
    return required_mapping(
        payload,
        field_name,
        missing_message=f"{engine_label} evidence package redaction note missing {field_name}",
    )
