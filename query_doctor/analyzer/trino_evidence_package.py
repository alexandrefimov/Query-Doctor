"""Fixture-only Trino evidence package intake validation.

This module validates operator-exported, already-sanitized package payloads for
future fixture work. It does not collect from Trino, execute SQL, register a
Trino engine adapter, or expose report/browser output.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from query_doctor.analyzer.engine_facts import (
    EngineFactBundle,
    EngineFactContractError,
    validate_engine_fact_bundle_raw_free,
)
from query_doctor.analyzer.trino_fixture_facts import (
    TRINO_EVENT_FIXTURE_MAX_DEPTH,
    TRINO_EVENT_FIXTURE_MAX_JSON_BYTES,
    TRINO_QUERY_LIST_FIXTURE_MAX_DEPTH,
    TRINO_QUERY_LIST_FIXTURE_MAX_JSON_BYTES,
    TRINO_STATEMENT_FIXTURE_MAX_DEPTH,
    TRINO_STATEMENT_FIXTURE_MAX_JSON_BYTES,
    build_trino_event_listener_fixture_engine_facts,
    build_trino_fixture_engine_facts,
    build_trino_query_list_contract_probe_engine_facts,
    validate_trino_event_listener_fixture_payload,
    validate_trino_query_list_contract_probe_payload,
    validate_trino_safe_fixture_json_size,
    validate_trino_safe_fixture_tree,
    validate_trino_statement_stats_fixture_payload,
)


TRINO_EVIDENCE_PACKAGE_MAX_JSON_BYTES = 512 * 1024
TRINO_EVIDENCE_PACKAGE_MAX_DEPTH = 24
TRINO_EVIDENCE_PACKAGE_MAX_SAMPLES = 64
TRINO_EVIDENCE_PACKAGE_SOURCE_TYPES = frozenset(
    {
        "event_listener_export",
        "query_detail_export",
        "query_list_summary_export",
        "statement_stats_export",
        "mixed_sanitized_export",
    }
)
TRINO_EVIDENCE_SAMPLE_SOURCE_TYPES = frozenset(
    {
        "event_listener_export",
        "query_list_summary_export",
        "statement_stats_export",
    }
)
TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES = (
    "successful_completed_query",
    "failed_query_allowlisted_category",
    "queued_or_resource_group_delayed_query",
    "blocked_query",
    "spill_observed",
    "stage_or_task_skew_candidate",
    "connector_metric_present",
    "connector_metric_absent",
    "missing_field_case",
    "unknown_or_unsupported_source_contract",
    "query_list_contract_probe",
)
TRINO_EVIDENCE_SYNTHETIC_REJECTION_CASES = (
    "oversized_or_over_deep_rejection_synthetic",
    "unsafe_raw_field_rejection_synthetic",
)
TRINO_EVIDENCE_PACKAGE_CASES = (
    *TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES,
    *TRINO_EVIDENCE_SYNTHETIC_REJECTION_CASES,
)
TRINO_EVIDENCE_REQUIRED_REDACTION_CLASSES = frozenset(
    {
        "raw_sql_or_prepared_statement",
        "query_or_trace_identifier",
        "user_group_role_or_client_identity",
        "hostname_endpoint_url_or_network_location",
        "catalog_schema_table_column_partition_or_object_name",
        "session_property_header_or_environment_metadata",
        "local_path_file_artifact_topic_or_storage_path",
        "raw_failure_message_stack_trace_warning_or_exception_detail",
        "connector_internal_payload_or_metric_name",
        "secret_credential_token_cookie_key_or_tls_material",
    }
)
TRINO_EVIDENCE_REQUIRED_REJECTION_REASONS = (
    "unsafe_raw_identifier_present",
    "unsafe_raw_text_present",
    "unsafe_field_name_present",
    "unsafe_object_name_present",
    "unsafe_endpoint_or_path_present",
    "unsafe_secret_or_credential_present",
    "oversized_record",
    "over_deep_record",
    "unsupported_source_contract",
)
TRINO_EVIDENCE_REQUIRED_SENTINEL_TESTS = (
    "raw_field_name_rejection",
    "raw_text_rejection",
    "oversized_payload_rejection",
    "over_deep_payload_rejection",
)
TRINO_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS = (
    "no_raw_sql_or_prepared_statements",
    "no_query_ids_trace_tokens_or_transaction_ids",
    "no_users_groups_roles_or_client_identity",
    "no_hostnames_endpoint_urls_or_network_locations",
    "no_catalog_schema_table_column_partition_or_object_names",
    "no_session_properties_headers_or_environment_metadata",
    "no_local_paths_file_names_artifact_names_topics_or_storage_paths",
    "no_stack_traces_exception_messages_warnings_or_connector_internals",
    "no_credentials_tokens_cookies_keys_or_tls_material",
    "no_raw_companion_archive",
)
TRINO_EVIDENCE_PACKAGE_TOP_LEVEL_KEYS = frozenset(
    {
        "manifest",
        "redaction_note",
        "samples",
    }
)

_SAFE_PACKAGE_LABEL_RE = re.compile(r"^[a-z][a-z0-9_]{2,80}$")
_SAFE_CLASS_LABEL_RE = re.compile(r"^[a-z][a-z0-9_]{1,120}$")
_TRINO_VERSION_FAMILY_RE = re.compile(r"^(unknown|[0-9]{3,4}(?:\.[0-9]{1,3})?)$")
_UTC_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_UTC_HOUR_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:00:00Z$")


@dataclass(frozen=True)
class TrinoEvidencePackageSampleResult:
    case: str
    source_type: str
    parser_coverage: str


@dataclass(frozen=True)
class TrinoEvidencePackageSourceSummary:
    trino_version_family: str
    source_contract_version: str
    connector_family_categories: tuple[str, ...]
    export_window_start_utc: str
    export_window_end_utc: str
    byte_count_compacted: int
    max_record_bytes: int
    max_nested_depth: int
    known_omissions: tuple[str, ...]
    unsupported_sources: tuple[str, ...]
    operator_retained_raw_exports: str
    query_doctor_contact_surface: str


@dataclass(frozen=True)
class TrinoEvidencePackageIntakeResult:
    package_id: str
    source_type: str
    source_summary: TrinoEvidencePackageSourceSummary
    sample_count: int
    sample_count_by_case: tuple[tuple[str, int], ...]
    samples: tuple[TrinoEvidencePackageSampleResult, ...]
    bundles: tuple[EngineFactBundle, ...]

    def parser_coverage_counts(self) -> dict[str, int]:
        counts = Counter(sample.parser_coverage for sample in self.samples)
        return dict(sorted(counts.items()))


def validate_trino_evidence_package_payload(
    payload: Mapping[str, Any],
    *,
    require_minimum_cases: bool = True,
    max_package_json_bytes: int = TRINO_EVIDENCE_PACKAGE_MAX_JSON_BYTES,
    max_package_depth: int = TRINO_EVIDENCE_PACKAGE_MAX_DEPTH,
    max_samples: int = TRINO_EVIDENCE_PACKAGE_MAX_SAMPLES,
) -> TrinoEvidencePackageIntakeResult:
    """Validate one sanitized Trino evidence package payload.

    The accepted payload is a local wrapper with `manifest`, `redaction_note`,
    and `samples` keys. Samples are still fixture inputs: this function only
    accepts source types that already have local fixture validators.
    """

    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino evidence package must be a JSON object")
    if set(payload) != TRINO_EVIDENCE_PACKAGE_TOP_LEVEL_KEYS:
        raise EngineFactContractError("Trino evidence package has unsupported top-level sections")

    validate_trino_safe_fixture_json_size(
        payload,
        max_json_bytes=max_package_json_bytes,
        payload_label="Trino evidence package payload",
    )
    validate_trino_safe_fixture_tree(
        payload,
        max_depth=max_package_depth,
        fixture_label="evidence package",
    )

    manifest = _required_mapping(payload, "manifest")
    redaction_note = _required_mapping(payload, "redaction_note")
    sample_entries = _required_sequence(payload, "samples")
    if not sample_entries:
        raise EngineFactContractError("Trino evidence package samples must not be empty")
    if len(sample_entries) > max_samples:
        raise EngineFactContractError("Trino evidence package has too many samples")

    package_id, source_type, manifest_counts, source_summary = _validate_manifest(manifest)
    _validate_redaction_note(redaction_note, package_id=package_id)

    bundles: list[EngineFactBundle] = []
    sample_results: list[TrinoEvidencePackageSampleResult] = []
    actual_counts: Counter[str] = Counter()
    max_record_bytes = 0
    max_record_depth = 0
    total_sample_bytes = 0

    for index, entry in enumerate(sample_entries):
        sample = _validate_sample_entry(entry, index=index)
        actual_counts[sample["case"]] += 1
        payload_mapping = sample["payload"]
        record_bytes = _json_size(payload_mapping, payload_label="Trino evidence package sample")
        max_record_bytes = max(max_record_bytes, record_bytes)
        max_record_depth = max(max_record_depth, _max_json_depth(payload_mapping))
        total_sample_bytes += record_bytes

        bundle = _build_sample_bundle(sample["source_type"], payload_mapping)
        violations = validate_engine_fact_bundle_raw_free(bundle)
        if violations:
            raise EngineFactContractError("Trino evidence package sample facts are not raw-free")
        bundles.append(bundle)
        sample_results.append(
            TrinoEvidencePackageSampleResult(
                case=sample["case"],
                source_type=sample["source_type"],
                parser_coverage=bundle.identity.parser_coverage,
            )
        )

    _validate_manifest_counts(
        manifest_counts,
        actual_counts=actual_counts,
        require_minimum_cases=require_minimum_cases,
    )
    _validate_declared_bounds(
        manifest,
        total_sample_bytes=total_sample_bytes,
        max_record_bytes=max_record_bytes,
        max_record_depth=max_record_depth,
    )

    return TrinoEvidencePackageIntakeResult(
        package_id=package_id,
        source_type=source_type,
        source_summary=source_summary,
        sample_count=len(sample_results),
        sample_count_by_case=tuple(
            (case, manifest_counts[case]) for case in TRINO_EVIDENCE_PACKAGE_CASES
        ),
        samples=tuple(sample_results),
        bundles=tuple(bundles),
    )


def _validate_manifest(
    manifest: Mapping[str, Any],
) -> tuple[str, str, dict[str, int], TrinoEvidencePackageSourceSummary]:
    package_id = _safe_package_label(manifest, "package_id")
    if _version_text(manifest, "package_version") != "1":
        raise EngineFactContractError("Trino evidence package manifest version is unsupported")
    _safe_class_label(manifest, "prepared_by_role")
    _utc_date(manifest, "prepared_date_utc")

    source_type = _safe_class_label(manifest, "source_type")
    if source_type not in TRINO_EVIDENCE_PACKAGE_SOURCE_TYPES:
        raise EngineFactContractError("Trino evidence package source_type is unsupported")

    version_family = _required_text(manifest, "trino_version_family")
    if not _TRINO_VERSION_FAMILY_RE.fullmatch(version_family):
        raise EngineFactContractError("Trino evidence package version family is not safe")
    source_contract_version = _safe_source_contract_label(manifest, "source_contract_version")
    connector_family_categories = _safe_label_list(
        manifest,
        "connector_family_categories",
        allow_empty=False,
    )
    export_window_start, export_window_end = _validate_export_window(
        _required_mapping(manifest, "export_window_utc")
    )

    counts = _validate_sample_count_by_case(_required_mapping(manifest, "sample_count_by_case"))
    byte_count_compacted = _non_negative_int(manifest, "byte_count_compacted")
    max_record_bytes = _non_negative_int(manifest, "max_record_bytes")
    max_nested_depth = _non_negative_int(manifest, "max_nested_depth")
    if _safe_class_label(manifest, "redaction_status") != "checked":
        raise EngineFactContractError("Trino evidence package redaction status is not checked")
    known_omissions = _safe_label_list(manifest, "known_omissions", allow_empty=True)
    unsupported_sources = _safe_label_list(manifest, "unsupported_sources", allow_empty=True)
    retained_raw = _safe_class_label(manifest, "operator_retained_raw_exports")
    if retained_raw not in {"yes", "no"}:
        raise EngineFactContractError("Trino evidence package raw-retention flag is unsupported")
    contact_surface = _safe_class_label(manifest, "query_doctor_contact_surface")
    if contact_surface != "fixture_import_only":
        raise EngineFactContractError("Trino evidence package contact surface is unsupported")
    return (
        package_id,
        source_type,
        counts,
        TrinoEvidencePackageSourceSummary(
            trino_version_family=version_family,
            source_contract_version=source_contract_version,
            connector_family_categories=connector_family_categories,
            export_window_start_utc=export_window_start,
            export_window_end_utc=export_window_end,
            byte_count_compacted=byte_count_compacted,
            max_record_bytes=max_record_bytes,
            max_nested_depth=max_nested_depth,
            known_omissions=known_omissions,
            unsupported_sources=unsupported_sources,
            operator_retained_raw_exports=retained_raw,
            query_doctor_contact_surface=contact_surface,
        ),
    )


def _validate_redaction_note(redaction_note: Mapping[str, Any], *, package_id: str) -> None:
    if _safe_package_label(redaction_note, "package_id") != package_id:
        raise EngineFactContractError("Trino evidence package id mismatch")
    if _version_text(redaction_note, "redaction_note_version") != "1":
        raise EngineFactContractError(
            "Trino evidence package redaction note version is unsupported"
        )
    _safe_class_label(redaction_note, "prepared_by_role")
    _utc_date(redaction_note, "prepared_date_utc")
    _safe_class_label(redaction_note, "manual_reviewer_role")
    if _safe_class_label(redaction_note, "redaction_status") != "checked":
        raise EngineFactContractError("Trino evidence package redaction note is not checked")

    removed_classes = set(
        _safe_label_list(redaction_note, "removed_field_classes", allow_empty=False)
    )
    missing_classes = TRINO_EVIDENCE_REQUIRED_REDACTION_CLASSES - removed_classes
    if missing_classes:
        raise EngineFactContractError("Trino evidence package redaction classes are incomplete")

    counts = _required_mapping(redaction_note, "rejected_record_counts_by_reason")
    for reason in TRINO_EVIDENCE_REQUIRED_REJECTION_REASONS:
        _non_negative_int(counts, reason)

    sentinel_tests = _required_mapping(redaction_note, "synthetic_sentinel_tests")
    for test_name in TRINO_EVIDENCE_REQUIRED_SENTINEL_TESTS:
        if _safe_class_label(sentinel_tests, test_name) != "yes":
            raise EngineFactContractError("Trino evidence package sentinel tests are incomplete")

    assertions = _required_mapping(redaction_note, "boundary_assertions")
    for assertion_name in TRINO_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS:
        if assertions.get(assertion_name) is not True:
            raise EngineFactContractError("Trino evidence package boundary assertion failed")
    for assertion_name, value in assertions.items():
        if not isinstance(assertion_name, str):
            raise EngineFactContractError(
                "Trino evidence package boundary assertion name is invalid"
            )
        if value is not True:
            raise EngineFactContractError("Trino evidence package boundary assertion failed")


def _validate_sample_entry(entry: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        raise EngineFactContractError("Trino evidence package sample must be a JSON object")

    case = _safe_class_label(entry, "case")
    if case in TRINO_EVIDENCE_SYNTHETIC_REJECTION_CASES:
        raise EngineFactContractError(
            "Trino evidence package rejection cases must stay in redaction notes"
        )
    if case not in TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES:
        raise EngineFactContractError("Trino evidence package sample case is unsupported")

    source_type = _safe_class_label(entry, "source_type")
    if source_type not in TRINO_EVIDENCE_SAMPLE_SOURCE_TYPES:
        raise EngineFactContractError("Trino evidence package sample source type is unsupported")
    payload = entry.get("payload")
    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino evidence package sample payload must be a JSON object")
    return {"case": case, "source_type": source_type, "payload": payload, "index": index}


def _build_sample_bundle(source_type: str, payload: Mapping[str, Any]) -> EngineFactBundle:
    if source_type == "statement_stats_export":
        validate_trino_statement_stats_fixture_payload(payload)
        return build_trino_fixture_engine_facts(payload)
    if source_type == "event_listener_export":
        validate_trino_event_listener_fixture_payload(payload)
        return build_trino_event_listener_fixture_engine_facts(payload)
    if source_type == "query_list_summary_export":
        validate_trino_query_list_contract_probe_payload(payload)
        return build_trino_query_list_contract_probe_engine_facts(payload)
    raise EngineFactContractError("Trino evidence package sample source type is unsupported")


def _validate_sample_count_by_case(counts: Mapping[str, Any]) -> dict[str, int]:
    normalized: dict[str, int] = {}
    extra = set(counts) - set(TRINO_EVIDENCE_PACKAGE_CASES)
    if extra:
        raise EngineFactContractError("Trino evidence package has unsupported sample case counts")
    for case in TRINO_EVIDENCE_PACKAGE_CASES:
        normalized[case] = _non_negative_int(counts, case)
    return normalized


def _validate_manifest_counts(
    manifest_counts: Mapping[str, int],
    *,
    actual_counts: Counter[str],
    require_minimum_cases: bool,
) -> None:
    for case in TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES:
        if manifest_counts[case] != actual_counts[case]:
            raise EngineFactContractError("Trino evidence package sample count mismatch")
        if require_minimum_cases and manifest_counts[case] <= 0:
            raise EngineFactContractError("Trino evidence package minimum sample case is missing")
    for case in TRINO_EVIDENCE_SYNTHETIC_REJECTION_CASES:
        if require_minimum_cases and manifest_counts[case] <= 0:
            raise EngineFactContractError(
                "Trino evidence package synthetic rejection case is missing"
            )


def _validate_declared_bounds(
    manifest: Mapping[str, Any],
    *,
    total_sample_bytes: int,
    max_record_bytes: int,
    max_record_depth: int,
) -> None:
    byte_count = _non_negative_int(manifest, "byte_count_compacted")
    declared_max_bytes = _non_negative_int(manifest, "max_record_bytes")
    declared_max_depth = _non_negative_int(manifest, "max_nested_depth")
    if byte_count < total_sample_bytes:
        raise EngineFactContractError("Trino evidence package byte count understates samples")
    if declared_max_bytes < max_record_bytes:
        raise EngineFactContractError("Trino evidence package max record bytes understates samples")
    if declared_max_depth < max_record_depth:
        raise EngineFactContractError("Trino evidence package max depth understates samples")
    if declared_max_bytes > max(
        TRINO_EVENT_FIXTURE_MAX_JSON_BYTES,
        TRINO_QUERY_LIST_FIXTURE_MAX_JSON_BYTES,
        TRINO_STATEMENT_FIXTURE_MAX_JSON_BYTES,
    ):
        raise EngineFactContractError(
            "Trino evidence package max record bytes exceeds fixture limit"
        )
    if declared_max_depth > max(
        TRINO_EVENT_FIXTURE_MAX_DEPTH,
        TRINO_QUERY_LIST_FIXTURE_MAX_DEPTH,
        TRINO_STATEMENT_FIXTURE_MAX_DEPTH,
    ):
        raise EngineFactContractError("Trino evidence package max depth exceeds fixture limit")


def _validate_export_window(window: Mapping[str, Any]) -> tuple[str, str]:
    start = _required_text(window, "start")
    end = _required_text(window, "end")
    if not _UTC_HOUR_RE.fullmatch(start) or not _UTC_HOUR_RE.fullmatch(end):
        raise EngineFactContractError(
            "Trino evidence package export window must be hour-bounded UTC"
        )
    if start >= end:
        raise EngineFactContractError("Trino evidence package export window is invalid")
    return start, end


def _required_mapping(payload: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise EngineFactContractError(f"Trino evidence package missing {field_name}")
    return value


def _required_sequence(payload: Mapping[str, Any], field_name: str) -> Sequence[Any]:
    value = payload.get(field_name)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise EngineFactContractError(f"Trino evidence package missing {field_name}")
    return value


def _required_text(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise EngineFactContractError(f"Trino evidence package missing {field_name}")
    return value.strip()


def _safe_package_label(payload: Mapping[str, Any], field_name: str) -> str:
    value = _required_text(payload, field_name)
    if not _SAFE_PACKAGE_LABEL_RE.fullmatch(value):
        raise EngineFactContractError("Trino evidence package label is not safe")
    return value


def _safe_class_label(payload: Mapping[str, Any], field_name: str) -> str:
    value = _required_text(payload, field_name)
    if not _SAFE_CLASS_LABEL_RE.fullmatch(value):
        raise EngineFactContractError(f"Trino evidence package {field_name} is not a safe label")
    return value


def _version_text(payload: Mapping[str, Any], field_name: str) -> str:
    value = _required_text(payload, field_name)
    if not re.fullmatch(r"[0-9]{1,3}", value):
        raise EngineFactContractError(f"Trino evidence package {field_name} is unsupported")
    return value


def _safe_source_contract_label(payload: Mapping[str, Any], field_name: str) -> str:
    value = _required_text(payload, field_name)
    if value == "unknown":
        return value
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,120}", value):
        raise EngineFactContractError("Trino evidence package source contract label is not safe")
    return value


def _safe_label_list(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    value = payload.get(field_name)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise EngineFactContractError(f"Trino evidence package missing {field_name}")
    labels: list[str] = []
    for item in value:
        if not isinstance(item, str) or not _SAFE_CLASS_LABEL_RE.fullmatch(item):
            raise EngineFactContractError(
                f"Trino evidence package {field_name} contains unsafe label"
            )
        labels.append(item)
    if not allow_empty and not labels:
        raise EngineFactContractError(f"Trino evidence package {field_name} must not be empty")
    return tuple(labels)


def _utc_date(payload: Mapping[str, Any], field_name: str) -> str:
    value = _required_text(payload, field_name)
    if not _UTC_DATE_RE.fullmatch(value):
        raise EngineFactContractError(f"Trino evidence package {field_name} is not a UTC date")
    return value


def _non_negative_int(payload: Mapping[str, Any], field_name: str) -> int:
    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EngineFactContractError(f"Trino evidence package {field_name} must be non-negative")
    return value


def _json_size(payload: Mapping[str, Any], *, payload_label: str) -> int:
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
        raise EngineFactContractError(f"{payload_label} must be JSON serializable") from exc


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
