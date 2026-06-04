"""Sanitized Spark compact evidence package validation.

This module validates operator-reviewed, already-compact Spark evidence
packages for readiness work. It does not collect from Spark, execute SQL, or
expose Details, trusted-report, Recent, optimizer, or engine-registration
behavior.
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
from query_doctor.analyzer.spark_fixture_schema import (
    SPARK_HISTORY_COMPACT_SOURCE_CONTRACT,
    SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT,
    validate_spark_history_compact_fixture_payload,
    validate_spark_history_server_compact_payload,
)
from query_doctor.spark.diagnosis import (
    build_spark_compact_diagnosis,
    spark_bundle_for_compact_payload,
)


SPARK_EVIDENCE_PACKAGE_MAX_JSON_BYTES = 512 * 1024
SPARK_EVIDENCE_PACKAGE_MAX_DEPTH = 24
SPARK_EVIDENCE_PACKAGE_MAX_SAMPLES = 64
SPARK_EVIDENCE_PACKAGE_IMPORT_SCHEMA_VERSION = "spark_evidence_package_import_v1"
SPARK_EVIDENCE_PACKAGE_SOURCE_TYPES = frozenset(
    {
        "history_server_compact_export",
        "eventlog_compact_export",
        "mixed_compact_export",
    }
)
SPARK_EVIDENCE_SAMPLE_SOURCE_TYPES = frozenset(
    {
        "spark_history_server_compact",
        "spark_eventlog_compact",
    }
)
SPARK_EVIDENCE_SAMPLE_SOURCE_CONTRACTS = {
    "spark_history_server_compact": SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT,
    "spark_eventlog_compact": SPARK_HISTORY_COMPACT_SOURCE_CONTRACT,
}
SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES = (
    "finished_sql_exact_linkage",
    "application_only_same_application",
    "failed_or_killed_allowlisted_category",
    "missing_or_partial_history_server_endpoint",
    "unknown_spark_version_or_source_contract",
    "spill_observed",
    "shuffle_or_data_movement_heavy",
    "stage_or_task_skew_candidate",
    "failed_stage_or_task_aggregate",
    "retried_task_aggregate",
    "long_sql_elapsed_time_context",
    "scheduler_delay_context",
    "adaptive_execution_checked_enabled",
    "adaptive_execution_checked_disabled",
    "dynamic_allocation_observed",
    "dynamic_allocation_unknown",
    "executor_loss_or_churn_aggregate",
    "high_executor_memory_utilization",
    "missing_stage_task_job_or_executor_summary",
)
SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES = (
    "oversized_or_over_deep_rejection_synthetic",
    "unsafe_raw_field_rejection_synthetic",
)
SPARK_EVIDENCE_PACKAGE_CASES = (
    *SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES,
    *SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES,
)
SPARK_EVIDENCE_REQUIRED_REDACTION_CLASSES = frozenset(
    {
        "raw_sql_description_or_plan",
        "application_attempt_sql_job_stage_task_or_executor_identifier",
        "user_principal_queue_pool_or_session_label",
        "hostname_endpoint_url_ip_or_network_location",
        "object_store_uri_local_path_file_or_artifact_name",
        "table_database_schema_column_or_object_name",
        "stack_trace_raw_exception_warning_or_log_line",
        "environment_classpath_command_or_vendor_payload",
        "secret_credential_token_cookie_key_header_or_tls_material",
    }
)
SPARK_EVIDENCE_REQUIRED_SENTINEL_TESTS = (
    "raw_field_name_rejection",
    "raw_text_rejection",
    "oversized_payload_rejection",
    "over_deep_payload_rejection",
    "non_finite_numeric_rejection",
)
SPARK_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS = (
    "no_raw_sql_descriptions_or_plans",
    "no_runtime_identifiers",
    "no_users_principals_or_session_labels",
    "no_hostnames_endpoint_urls_ips_or_network_locations",
    "no_object_store_uris_local_paths_files_or_artifacts",
    "no_table_database_schema_column_or_object_names",
    "no_stack_traces_raw_exceptions_warnings_or_logs",
    "no_environment_classpath_command_or_vendor_payloads",
    "no_credentials_tokens_headers_or_tls_material",
    "no_raw_event_log_or_history_server_companion_archive",
)
SPARK_EVIDENCE_TOP_LEVEL_KEYS = frozenset({"manifest", "redaction_note", "samples"})
SPARK_EVIDENCE_CONTACT_SURFACES = frozenset(
    {
        "fixture_import_only",
        "readiness_evidence_only",
    }
)
SPARK_EVIDENCE_WINDOW_CATEGORIES = frozenset(
    {
        "single_application",
        "representative_sample",
        "synthetic_mixed",
        "unknown",
    }
)

_SAFE_PACKAGE_LABEL_RE = re.compile(r"^[a-z][a-z0-9_]{2,80}$")
_SAFE_CLASS_LABEL_RE = re.compile(r"^[a-z][a-z0-9_]{1,120}$")
_SPARK_VERSION_FAMILY_RE = re.compile(r"^(?:unknown|spark_[0-9]+_[0-9]+)$")
_UTC_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


@dataclass(frozen=True)
class SparkEvidencePackageSampleResult:
    case: str
    source_type: str
    source_contract: str
    parser_coverage: str
    attention_area_count: int
    supported_attention_area_count: int
    source_warning_count: int


@dataclass(frozen=True)
class SparkEvidencePackageSourceSummary:
    spark_version_families: tuple[str, ...]
    source_contracts: tuple[str, ...]
    collection_window_category: str
    byte_count_compacted: int
    max_record_bytes: int
    max_nested_depth: int
    known_omissions: tuple[str, ...]
    unsupported_sources: tuple[str, ...]
    operator_retained_raw_exports: str
    query_doctor_contact_surface: str


@dataclass(frozen=True)
class SparkEvidencePackageIntakeResult:
    package_id: str
    source_type: str
    source_summary: SparkEvidencePackageSourceSummary
    sample_count: int
    sample_count_by_case: tuple[tuple[str, int], ...]
    samples: tuple[SparkEvidencePackageSampleResult, ...]
    bundles: tuple[EngineFactBundle, ...]

    def parser_coverage_counts(self) -> dict[str, int]:
        counts = Counter(sample.parser_coverage for sample in self.samples)
        return dict(sorted(counts.items()))

    def source_contract_counts(self) -> dict[str, int]:
        counts = Counter(sample.source_contract for sample in self.samples)
        return dict(sorted(counts.items()))

    @property
    def supported_attention_area_count(self) -> int:
        return sum(sample.supported_attention_area_count for sample in self.samples)

    @property
    def source_warning_count(self) -> int:
        return sum(sample.source_warning_count for sample in self.samples)


def spark_evidence_package_summary_payload(
    result: SparkEvidencePackageIntakeResult,
) -> dict[str, Any]:
    """Return the safe Spark package summary for local validation output."""

    summary = result.source_summary
    return {
        "package_id": result.package_id,
        "source_type": result.source_type,
        "source_summary": {
            "spark_version_families": list(summary.spark_version_families),
            "source_contracts": list(summary.source_contracts),
            "collection_window_category": summary.collection_window_category,
            "byte_count_compacted": summary.byte_count_compacted,
            "max_record_bytes": summary.max_record_bytes,
            "max_nested_depth": summary.max_nested_depth,
            "known_omissions": list(summary.known_omissions),
            "unsupported_sources": list(summary.unsupported_sources),
            "operator_retained_raw_exports": summary.operator_retained_raw_exports,
            "contact_surface": summary.query_doctor_contact_surface,
        },
        "sample_count": result.sample_count,
        "parser_coverage": result.parser_coverage_counts(),
        "source_contracts": result.source_contract_counts(),
        "supported_attention_area_count": result.supported_attention_area_count,
        "source_warning_count": result.source_warning_count,
        "sample_count_by_case": dict(result.sample_count_by_case),
    }


def format_spark_evidence_package_summary(
    result: SparkEvidencePackageIntakeResult,
) -> str:
    """Render a path-free, raw-free Spark package summary for terminal output."""

    summary = result.source_summary
    lines = [
        "[spark-package] accepted",
        f"package_id: {result.package_id}",
        f"source_type: {result.source_type}",
        "source_summary:",
        f"  spark_version_families: {_format_safe_labels(summary.spark_version_families)}",
        f"  source_contracts: {_format_safe_labels(summary.source_contracts)}",
        f"  collection_window_category: {summary.collection_window_category}",
        f"  byte_count_compacted: {summary.byte_count_compacted}",
        f"  max_record_bytes: {summary.max_record_bytes}",
        f"  max_nested_depth: {summary.max_nested_depth}",
        f"  known_omissions: {_format_safe_labels(summary.known_omissions)}",
        f"  unsupported_sources: {_format_safe_labels(summary.unsupported_sources)}",
        f"  operator_retained_raw_exports: {summary.operator_retained_raw_exports}",
        f"  contact_surface: {summary.query_doctor_contact_surface}",
        f"sample_count: {result.sample_count}",
        "parser_coverage:",
    ]
    for state, count in result.parser_coverage_counts().items():
        lines.append(f"  {state}: {count}")
    lines.append("source_contracts:")
    for source_contract, count in result.source_contract_counts().items():
        lines.append(f"  {source_contract}: {count}")
    lines.append(f"supported_attention_area_count: {result.supported_attention_area_count}")
    lines.append(f"source_warning_count: {result.source_warning_count}")
    lines.append("sample_count_by_case:")
    for case, count in result.sample_count_by_case:
        lines.append(f"  {case}: {count}")
    return "\n".join(lines)


def validate_spark_evidence_package_payload(
    payload: Mapping[str, Any],
    *,
    require_minimum_cases: bool = True,
    max_package_json_bytes: int = SPARK_EVIDENCE_PACKAGE_MAX_JSON_BYTES,
    max_package_depth: int = SPARK_EVIDENCE_PACKAGE_MAX_DEPTH,
    max_samples: int = SPARK_EVIDENCE_PACKAGE_MAX_SAMPLES,
) -> SparkEvidencePackageIntakeResult:
    """Validate one operator-reviewed Spark compact evidence package."""

    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Spark evidence package must be a JSON object")
    if set(payload) != SPARK_EVIDENCE_TOP_LEVEL_KEYS:
        raise EngineFactContractError("Spark evidence package has unsupported top-level sections")

    _validate_json_size(
        payload,
        max_json_bytes=max_package_json_bytes,
        payload_label="Spark evidence package payload",
    )
    if _max_json_depth(payload) > max_package_depth:
        raise EngineFactContractError("Spark evidence package is too deeply nested")

    manifest = _required_mapping(payload, "manifest")
    redaction_note = _required_mapping(payload, "redaction_note")
    sample_entries = _required_sequence(payload, "samples")
    if not sample_entries:
        raise EngineFactContractError("Spark evidence package samples must not be empty")
    if len(sample_entries) > max_samples:
        raise EngineFactContractError("Spark evidence package has too many samples")

    package_id, source_type, manifest_counts, source_summary = _validate_manifest(manifest)
    _validate_redaction_note(redaction_note, package_id=package_id)

    bundles: list[EngineFactBundle] = []
    sample_results: list[SparkEvidencePackageSampleResult] = []
    actual_counts: Counter[str] = Counter()
    max_record_bytes = 0
    max_record_depth = 0
    total_sample_bytes = 0

    for index, entry in enumerate(sample_entries):
        sample = _validate_sample_entry(entry, index=index)
        actual_counts[sample["case"]] += 1
        payload_mapping = sample["payload"]
        _validate_sample_payload(sample["source_type"], payload_mapping)
        record_bytes = _json_size(payload_mapping, payload_label="Spark evidence package sample")
        max_record_bytes = max(max_record_bytes, record_bytes)
        max_record_depth = max(max_record_depth, _max_json_depth(payload_mapping))
        total_sample_bytes += record_bytes

        bundle = spark_bundle_for_compact_payload(payload_mapping)
        violations = validate_engine_fact_bundle_raw_free(bundle)
        if violations:
            raise EngineFactContractError("Spark evidence package sample facts are not raw-free")
        diagnosis = build_spark_compact_diagnosis(payload_mapping)
        bundles.append(bundle)
        sample_results.append(
            SparkEvidencePackageSampleResult(
                case=sample["case"],
                source_type=sample["source_type"],
                source_contract=str(payload_mapping.get("sourceContract")),
                parser_coverage=bundle.identity.parser_coverage,
                attention_area_count=len(diagnosis.get("attention_areas", ())),
                supported_attention_area_count=_supported_attention_area_count(diagnosis),
                source_warning_count=_source_warning_count(payload_mapping),
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

    return SparkEvidencePackageIntakeResult(
        package_id=package_id,
        source_type=source_type,
        source_summary=source_summary,
        sample_count=len(sample_results),
        sample_count_by_case=tuple(
            (case, manifest_counts[case]) for case in SPARK_EVIDENCE_PACKAGE_CASES
        ),
        samples=tuple(sample_results),
        bundles=tuple(bundles),
    )


def _validate_manifest(
    manifest: Mapping[str, Any],
) -> tuple[str, str, dict[str, int], SparkEvidencePackageSourceSummary]:
    package_id = _safe_package_label(manifest, "package_id")
    if _version_text(manifest, "package_version") != "1":
        raise EngineFactContractError("Spark evidence package manifest version is unsupported")
    _safe_class_label(manifest, "prepared_by_role")
    _utc_date(manifest, "prepared_date_utc")

    source_type = _safe_class_label(manifest, "source_type")
    if source_type not in SPARK_EVIDENCE_PACKAGE_SOURCE_TYPES:
        raise EngineFactContractError("Spark evidence package source_type is unsupported")
    spark_version_families = _safe_label_list(
        manifest,
        "spark_version_families",
        label_re=_SPARK_VERSION_FAMILY_RE,
        allow_empty=False,
    )
    source_contracts = _safe_label_list(
        manifest,
        "source_contracts",
        label_re=_SAFE_CLASS_LABEL_RE,
        allow_empty=False,
    )
    if not set(source_contracts).issubset(set(SPARK_EVIDENCE_SAMPLE_SOURCE_CONTRACTS.values())):
        raise EngineFactContractError("Spark evidence package source contract is unsupported")
    collection_window = _safe_class_label(manifest, "collection_window_category")
    if collection_window not in SPARK_EVIDENCE_WINDOW_CATEGORIES:
        raise EngineFactContractError("Spark evidence package collection window is unsupported")
    counts = _validate_sample_count_by_case(_required_mapping(manifest, "sample_count_by_case"))
    byte_count_compacted = _non_negative_int(manifest, "byte_count_compacted")
    max_record_bytes = _non_negative_int(manifest, "max_record_bytes")
    max_nested_depth = _non_negative_int(manifest, "max_nested_depth")
    if _safe_class_label(manifest, "redaction_status") != "checked":
        raise EngineFactContractError("Spark evidence package redaction status is not checked")
    known_omissions = _safe_label_list(manifest, "known_omissions", allow_empty=True)
    unsupported_sources = _safe_label_list(manifest, "unsupported_sources", allow_empty=True)
    retained_raw = _safe_class_label(manifest, "operator_retained_raw_exports")
    if retained_raw not in {"yes", "no"}:
        raise EngineFactContractError("Spark evidence package raw-retention flag is unsupported")
    contact_surface = _safe_class_label(manifest, "query_doctor_contact_surface")
    if contact_surface not in SPARK_EVIDENCE_CONTACT_SURFACES:
        raise EngineFactContractError("Spark evidence package contact surface is unsupported")
    return (
        package_id,
        source_type,
        counts,
        SparkEvidencePackageSourceSummary(
            spark_version_families=tuple(spark_version_families),
            source_contracts=tuple(source_contracts),
            collection_window_category=collection_window,
            byte_count_compacted=byte_count_compacted,
            max_record_bytes=max_record_bytes,
            max_nested_depth=max_nested_depth,
            known_omissions=tuple(known_omissions),
            unsupported_sources=tuple(unsupported_sources),
            operator_retained_raw_exports=retained_raw,
            query_doctor_contact_surface=contact_surface,
        ),
    )


def _validate_redaction_note(redaction_note: Mapping[str, Any], *, package_id: str) -> None:
    if _safe_package_label(redaction_note, "package_id") != package_id:
        raise EngineFactContractError("Spark evidence package redaction note id mismatch")
    if _safe_class_label(redaction_note, "manual_review_status") != "checked":
        raise EngineFactContractError("Spark evidence package redaction note is not checked")
    redaction_classes = set(
        _safe_label_list(redaction_note, "removed_field_classes", allow_empty=False)
    )
    if not SPARK_EVIDENCE_REQUIRED_REDACTION_CLASSES.issubset(redaction_classes):
        raise EngineFactContractError("Spark evidence package redaction classes are incomplete")
    boundary_assertions = set(
        _safe_label_list(redaction_note, "boundary_assertions", allow_empty=False)
    )
    if not set(SPARK_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS).issubset(boundary_assertions):
        raise EngineFactContractError("Spark evidence package boundary assertions are incomplete")
    sentinel_tests = set(
        _safe_label_list(redaction_note, "sentinel_tests_passed", allow_empty=False)
    )
    if not set(SPARK_EVIDENCE_REQUIRED_SENTINEL_TESTS).issubset(sentinel_tests):
        raise EngineFactContractError("Spark evidence package sentinel tests are incomplete")
    if _safe_class_label(redaction_note, "raw_companion_archive") != "none":
        raise EngineFactContractError("Spark evidence package raw companion archive is not allowed")


def _validate_sample_entry(entry: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        raise EngineFactContractError("Spark evidence package sample must be a JSON object")
    if set(entry) != {"case", "source_type", "payload"}:
        raise EngineFactContractError("Spark evidence package sample has unsupported fields")
    case = _required_text(entry, "case")
    if case not in SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES:
        raise EngineFactContractError("Spark evidence package sample case is unsupported")
    source_type = _safe_class_label(entry, "source_type")
    if source_type not in SPARK_EVIDENCE_SAMPLE_SOURCE_TYPES:
        raise EngineFactContractError("Spark evidence package sample source_type is unsupported")
    payload = entry.get("payload")
    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Spark evidence package sample payload must be an object")
    return {"case": case, "source_type": source_type, "payload": payload, "index": index}


def _validate_sample_payload(source_type: str, payload: Mapping[str, Any]) -> None:
    expected_source_contract = SPARK_EVIDENCE_SAMPLE_SOURCE_CONTRACTS[source_type]
    if payload.get("sourceContract") != expected_source_contract:
        raise EngineFactContractError("Spark evidence package sample source contract mismatch")
    if source_type == "spark_history_server_compact":
        validate_spark_history_server_compact_payload(payload)
    else:
        validate_spark_history_compact_fixture_payload(payload)


def _validate_sample_count_by_case(counts_payload: Mapping[str, Any]) -> dict[str, int]:
    if set(counts_payload) != set(SPARK_EVIDENCE_PACKAGE_CASES):
        raise EngineFactContractError("Spark evidence package sample case counts are incomplete")
    return {case: _non_negative_int(counts_payload, case) for case in SPARK_EVIDENCE_PACKAGE_CASES}


def _validate_manifest_counts(
    manifest_counts: Mapping[str, int],
    *,
    actual_counts: Counter[str],
    require_minimum_cases: bool,
) -> None:
    for case in SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES:
        if manifest_counts[case] != actual_counts.get(case, 0):
            raise EngineFactContractError("Spark evidence package sample count mismatch")
        if require_minimum_cases and manifest_counts[case] <= 0:
            raise EngineFactContractError("Spark evidence package is missing required sample cases")
    for case in SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES:
        if require_minimum_cases and manifest_counts[case] <= 0:
            raise EngineFactContractError(
                "Spark evidence package is missing synthetic rejection coverage"
            )


def _validate_declared_bounds(
    manifest: Mapping[str, Any],
    *,
    total_sample_bytes: int,
    max_record_bytes: int,
    max_record_depth: int,
) -> None:
    if _non_negative_int(manifest, "byte_count_compacted") < total_sample_bytes:
        raise EngineFactContractError("Spark evidence package byte count is below samples")
    if _non_negative_int(manifest, "max_record_bytes") < max_record_bytes:
        raise EngineFactContractError("Spark evidence package max record bytes is below samples")
    if _non_negative_int(manifest, "max_nested_depth") < max_record_depth:
        raise EngineFactContractError("Spark evidence package max nested depth is below samples")


def _supported_attention_area_count(diagnosis: Mapping[str, Any]) -> int:
    attention_areas = diagnosis.get("attention_areas", ())
    if not isinstance(attention_areas, Sequence) or isinstance(attention_areas, (str, bytes)):
        return 0
    count = 0
    for area in attention_areas:
        if isinstance(area, Mapping) and area.get("state") == "supported":
            count += 1
    return count


def _source_warning_count(payload: Mapping[str, Any]) -> int:
    source_coverage = payload.get("sourceCoverage")
    if not isinstance(source_coverage, Mapping):
        return 0
    warning_ids = source_coverage.get("warningIds")
    if isinstance(warning_ids, Sequence) and not isinstance(warning_ids, (str, bytes)):
        return len(warning_ids)
    return 0


def _validate_json_size(
    payload: Mapping[str, Any], *, max_json_bytes: int, payload_label: str
) -> None:
    _json_size(payload, payload_label=payload_label)
    if len(json.dumps(payload, allow_nan=False, sort_keys=True).encode("utf-8")) > max_json_bytes:
        raise EngineFactContractError(f"{payload_label} exceeds byte limit")


def _json_size(payload: Mapping[str, Any], *, payload_label: str) -> int:
    try:
        return len(json.dumps(payload, allow_nan=False, sort_keys=True).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise EngineFactContractError(f"{payload_label} must be finite JSON") from exc


def _max_json_depth(value: Any) -> int:
    if isinstance(value, Mapping):
        if not value:
            return 1
        return 1 + max(_max_json_depth(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            return 1
        return 1 + max(_max_json_depth(item) for item in value)
    return 1


def _required_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise EngineFactContractError("Spark evidence package section must be an object")
    return value


def _required_sequence(payload: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = payload.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise EngineFactContractError("Spark evidence package section must be a list")
    return value


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise EngineFactContractError("Spark evidence package text field is invalid")
    return value


def _version_text(payload: Mapping[str, Any], key: str) -> str:
    value = _required_text(payload, key)
    if not re.fullmatch(r"[0-9]+", value):
        raise EngineFactContractError("Spark evidence package version is invalid")
    return value


def _safe_package_label(payload: Mapping[str, Any], key: str) -> str:
    value = _required_text(payload, key)
    if not _SAFE_PACKAGE_LABEL_RE.fullmatch(value):
        raise EngineFactContractError("Spark evidence package label is not safe")
    return value


def _safe_class_label(payload: Mapping[str, Any], key: str) -> str:
    value = _required_text(payload, key)
    if not _SAFE_CLASS_LABEL_RE.fullmatch(value):
        raise EngineFactContractError("Spark evidence package class label is not safe")
    return value


def _safe_label_list(
    payload: Mapping[str, Any],
    key: str,
    *,
    label_re: re.Pattern[str] = _SAFE_CLASS_LABEL_RE,
    allow_empty: bool,
) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise EngineFactContractError("Spark evidence package label list is invalid")
    if not value and not allow_empty:
        raise EngineFactContractError("Spark evidence package label list must not be empty")
    labels: list[str] = []
    for item in value:
        if not isinstance(item, str) or not label_re.fullmatch(item):
            raise EngineFactContractError("Spark evidence package label list contains unsafe text")
        labels.append(item)
    return labels


def _utc_date(payload: Mapping[str, Any], key: str) -> str:
    value = _required_text(payload, key)
    if not _UTC_DATE_RE.fullmatch(value):
        raise EngineFactContractError("Spark evidence package date is invalid")
    return value


def _non_negative_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise EngineFactContractError("Spark evidence package numeric field is invalid")
    return value


def _format_safe_labels(labels: Sequence[str]) -> str:
    if not labels:
        return "none"
    return ", ".join(labels)
