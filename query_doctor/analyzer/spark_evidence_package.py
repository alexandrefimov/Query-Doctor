"""Sanitized Spark compact evidence package validation.

This module validates operator-reviewed, already-compact Spark evidence
packages for readiness work. It does not collect from Spark, execute SQL, or
expose Details, trusted-report, Recent, optimizer, or engine-registration
behavior.
"""

from __future__ import annotations

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
from query_doctor.analyzer.engine_intake_primitives import (
    SAFE_CLASS_LABEL_RE,
    format_safe_labels,
    json_size as _shared_json_size,
    max_json_depth as _shared_max_json_depth,
    non_negative_int,
    required_mapping,
    required_sequence,
    required_text,
    safe_class_label,
    safe_label_list,
    safe_package_label,
    utc_date,
    version_text,
)
from query_doctor.analyzer.engine_redaction_note import validate_redaction_note_v1
from query_doctor.analyzer.spark_fixture_schema import (
    SPARK_HISTORY_COMPACT_SOURCE_CONTRACT,
    SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT,
    validate_spark_history_compact_fixture_payload,
    validate_spark_history_server_compact_payload,
)
from query_doctor.spark.diagnosis import (
    SPARK_COMPACT_DIAGNOSTIC_LANE_NAME,
    SPARK_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
    SPARK_LANE_GRANULARITY_APPLICATION,
    SPARK_LANE_GRANULARITY_EXACT_SQL,
    SPARK_LANE_GRANULARITY_FIXTURE,
    SPARK_LANE_READINESS_ATTENTION_READY,
    SPARK_LANE_READINESS_COVERAGE_UNKNOWN,
    SPARK_LANE_READINESS_LIMITED,
    SPARK_LANE_READINESS_SOURCE_WARNING,
    build_spark_compact_diagnosis,
    safe_fact_state_counts,
    spark_bundle_for_compact_payload,
    spark_lane_evidence_readiness,
    spark_lane_verification_scope,
    spark_source_granularity,
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
SPARK_EVIDENCE_REQUIRED_SOURCE_CONTRACTS = tuple(
    sorted(set(SPARK_EVIDENCE_SAMPLE_SOURCE_CONTRACTS.values()))
)
SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_SIGNAL_GROUPS = (
    "data_movement",
    "failure",
    "runtime_context",
    "adaptive_plan_context",
)
SPARK_EVIDENCE_DIAGNOSTIC_SIGNAL_GROUPS = {
    "data_movement": frozenset(
        {
            "spark_shuffle_spill",
            "spark_stage_skew_candidate",
        }
    ),
    "failure": frozenset(
        {
            "spark_query_failed",
            "spark_job_failures",
            "spark_stage_failures",
            "spark_task_failures",
        }
    ),
    "runtime_context": frozenset(
        {
            "spark_long_elapsed_time",
            "spark_executor_memory_pressure",
            "spark_task_retries",
            "spark_task_duration_tail",
            "spark_scheduler_delay",
            "spark_executor_churn",
            "spark_executor_loss",
        }
    ),
    "adaptive_plan_context": frozenset(
        {
            "spark_adaptive_plan_change",
        }
    ),
}
SPARK_EVIDENCE_DIAGNOSTIC_SIGNAL_PREFIX_GROUPS = {
    "spark_failure_category_": "failure",
}
SPARK_EVIDENCE_READINESS_PARTIAL = "partial_evidence"
SPARK_EVIDENCE_READINESS_MINIMUM_CASE_SET_READY = "minimum_case_set_ready"
SPARK_EVIDENCE_READINESS_PROMOTION_CANDIDATE = "promotion_candidate"
SPARK_EVIDENCE_EXPECTED_DIAGNOSIS_BOUNDARY = {
    "root_cause": "not_claimed",
    "details_trusted_report_surface": "not_wired",
    "optimizer_behavior": "not_wired",
    "spark_job_execution": "not_performed",
}
SPARK_EVIDENCE_EXPECTED_DIAGNOSTIC_LANE_GATES = {
    "readiness_audit": "required_for_handoff",
    "surface_audit": "required_before_wiring",
}
SPARK_EVIDENCE_DIAGNOSTIC_LANE_READINESS_VALUES = (
    SPARK_LANE_READINESS_ATTENTION_READY,
    SPARK_LANE_READINESS_LIMITED,
    SPARK_LANE_READINESS_SOURCE_WARNING,
    SPARK_LANE_READINESS_COVERAGE_UNKNOWN,
)
SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_LANE_READINESS = (SPARK_LANE_READINESS_ATTENTION_READY,)
SPARK_EVIDENCE_DIAGNOSTIC_LANE_SOURCE_GRANULARITIES = (
    SPARK_LANE_GRANULARITY_APPLICATION,
    SPARK_LANE_GRANULARITY_EXACT_SQL,
    SPARK_LANE_GRANULARITY_FIXTURE,
)
SPARK_EVIDENCE_DIAGNOSTIC_LANE_VERIFICATION_SCOPES = (
    "comparable_application_rerun",
    "comparable_sql_execution_rerun",
    "fixture_contract_review",
    "source_contract_review",
    "source_coverage_review",
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
SPARK_EVIDENCE_REQUIRED_REJECTION_REASONS = (
    "unsafe_raw_identifier_present",
    "unsafe_raw_text_present",
    "unsafe_field_name_present",
    "unsafe_object_name_present",
    "unsafe_endpoint_or_path_present",
    "unsafe_secret_or_credential_present",
    "oversized_record",
    "over_deep_record",
    "non_finite_numeric_record",
    "unsupported_source_contract",
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

_SPARK_VERSION_FAMILY_RE = re.compile(r"^(?:unknown|spark_[0-9]+_[0-9]+)$")


@dataclass(frozen=True)
class SparkEvidencePackageSampleResult:
    case: str
    source_type: str
    source_contract: str
    parser_coverage: str
    diagnostic_lane_schema_version: str
    diagnostic_lane_readiness: str
    diagnostic_lane_source_granularity: str
    diagnostic_lane_verification_scope: str
    supported_attention_area_ids: tuple[str, ...]
    attention_area_count: int
    supported_attention_area_count: int
    source_warning_count: int
    source_warning_ids: tuple[str, ...]


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

    def diagnostic_signal_group_counts(self) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for sample in self.samples:
            for group in diagnostic_signal_groups_for_attention_ids(
                sample.supported_attention_area_ids
            ):
                counts[group] += 1
        return dict(sorted(counts.items()))

    @property
    def source_warning_count(self) -> int:
        return sum(sample.source_warning_count for sample in self.samples)

    def source_warning_counts(self) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for sample in self.samples:
            counts.update(sample.source_warning_ids)
        return dict(sorted(counts.items()))

    def diagnostic_lane_readiness_counts(self) -> dict[str, int]:
        counts = Counter(sample.diagnostic_lane_readiness for sample in self.samples)
        return dict(sorted(counts.items()))

    def diagnostic_lane_source_granularity_counts(self) -> dict[str, int]:
        counts = Counter(sample.diagnostic_lane_source_granularity for sample in self.samples)
        return dict(sorted(counts.items()))

    def diagnostic_lane_verification_scope_counts(self) -> dict[str, int]:
        counts = Counter(sample.diagnostic_lane_verification_scope for sample in self.samples)
        return dict(sorted(counts.items()))


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
        "diagnostic_signal_groups": result.diagnostic_signal_group_counts(),
        "diagnostic_lane": {
            "schema_version": SPARK_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
            "readiness": result.diagnostic_lane_readiness_counts(),
            "source_granularity": result.diagnostic_lane_source_granularity_counts(),
            "verification_scope": result.diagnostic_lane_verification_scope_counts(),
            "required_gates": dict(SPARK_EVIDENCE_EXPECTED_DIAGNOSTIC_LANE_GATES),
        },
        "supported_attention_area_count": result.supported_attention_area_count,
        "source_warning_count": result.source_warning_count,
        "source_warning_counts": result.source_warning_counts(),
        "sample_count_by_case": dict(result.sample_count_by_case),
        "readiness": spark_evidence_package_readiness_payload(result),
    }


def spark_evidence_package_readiness_payload(
    result: SparkEvidencePackageIntakeResult,
) -> dict[str, Any]:
    """Return a safe package-level readiness verdict without support claims."""

    counts = dict(result.sample_count_by_case)
    missing_sample_cases = tuple(
        case for case in SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES if counts.get(case, 0) <= 0
    )
    missing_synthetic_rejection_cases = tuple(
        case for case in SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES if counts.get(case, 0) <= 0
    )
    source_contract_counts = result.source_contract_counts()
    missing_source_contracts = tuple(
        contract
        for contract in SPARK_EVIDENCE_REQUIRED_SOURCE_CONTRACTS
        if source_contract_counts.get(contract, 0) <= 0
    )
    diagnostic_signal_group_counts = result.diagnostic_signal_group_counts()
    missing_diagnostic_signal_groups = tuple(
        group
        for group in SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_SIGNAL_GROUPS
        if diagnostic_signal_group_counts.get(group, 0) <= 0
    )
    diagnostic_lane_readiness_counts = result.diagnostic_lane_readiness_counts()
    missing_diagnostic_lane_readiness = tuple(
        readiness
        for readiness in SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_LANE_READINESS
        if diagnostic_lane_readiness_counts.get(readiness, 0) <= 0
    )
    promotion_blockers = _spark_evidence_promotion_blockers(
        missing_sample_cases=missing_sample_cases,
        missing_synthetic_rejection_cases=missing_synthetic_rejection_cases,
        missing_source_contracts=missing_source_contracts,
        missing_diagnostic_signal_groups=missing_diagnostic_signal_groups,
        missing_diagnostic_lane_readiness=missing_diagnostic_lane_readiness,
        supported_attention_area_count=result.supported_attention_area_count,
        source_warning_count=result.source_warning_count,
    )
    return {
        "readiness_status": _spark_evidence_readiness_status(
            missing_sample_cases=missing_sample_cases,
            missing_synthetic_rejection_cases=missing_synthetic_rejection_cases,
            missing_source_contracts=missing_source_contracts,
            missing_diagnostic_signal_groups=missing_diagnostic_signal_groups,
            missing_diagnostic_lane_readiness=missing_diagnostic_lane_readiness,
            supported_attention_area_count=result.supported_attention_area_count,
            source_warning_count=result.source_warning_count,
        ),
        "support_status": "experimental_compact_intake",
        "support_claim": "not_claimed",
        "product_surface": "not_wired",
        "spark_job_execution": "not_performed",
        "missing_sample_cases": list(missing_sample_cases),
        "missing_synthetic_rejection_cases": list(missing_synthetic_rejection_cases),
        "missing_source_contracts": list(missing_source_contracts),
        "diagnostic_signal_groups": diagnostic_signal_group_counts,
        "missing_diagnostic_signal_groups": list(missing_diagnostic_signal_groups),
        "diagnostic_lane_schema_version": SPARK_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
        "diagnostic_lane_readiness": diagnostic_lane_readiness_counts,
        "diagnostic_lane_source_granularity": result.diagnostic_lane_source_granularity_counts(),
        "diagnostic_lane_verification_scope": result.diagnostic_lane_verification_scope_counts(),
        "required_diagnostic_lane_readiness": list(
            SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_LANE_READINESS
        ),
        "missing_diagnostic_lane_readiness": list(missing_diagnostic_lane_readiness),
        "supported_attention_area_count": result.supported_attention_area_count,
        "source_warning_count": result.source_warning_count,
        "source_warning_counts": result.source_warning_counts(),
        "source_warnings_clear": result.source_warning_count == 0,
        "promotion_blockers": list(promotion_blockers),
    }


def format_spark_evidence_package_summary(
    result: SparkEvidencePackageIntakeResult,
) -> str:
    """Render a path-free, raw-free Spark package summary for terminal output."""

    summary = result.source_summary
    readiness = spark_evidence_package_readiness_payload(result)
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
    lines.append("diagnostic_signal_groups:")
    for group, count in result.diagnostic_signal_group_counts().items():
        lines.append(f"  {group}: {count}")
    lines.append("diagnostic_lane_readiness:")
    for lane_readiness, count in result.diagnostic_lane_readiness_counts().items():
        lines.append(f"  {lane_readiness}: {count}")
    lines.append("diagnostic_lane_source_granularity:")
    for source_granularity, count in result.diagnostic_lane_source_granularity_counts().items():
        lines.append(f"  {source_granularity}: {count}")
    lines.append("diagnostic_lane_verification_scope:")
    for verification_scope, count in result.diagnostic_lane_verification_scope_counts().items():
        lines.append(f"  {verification_scope}: {count}")
    lines.append(f"supported_attention_area_count: {result.supported_attention_area_count}")
    lines.append(f"source_warning_count: {result.source_warning_count}")
    lines.append("source_warning_counts:")
    for warning_id, count in result.source_warning_counts().items():
        lines.append(f"  {warning_id}: {count}")
    lines.append("sample_count_by_case:")
    for case, count in result.sample_count_by_case:
        lines.append(f"  {case}: {count}")
    lines.extend(
        [
            "readiness:",
            f"  readiness_status: {readiness['readiness_status']}",
            f"  support_status: {readiness['support_status']}",
            f"  support_claim: {readiness['support_claim']}",
            f"  product_surface: {readiness['product_surface']}",
            f"  spark_job_execution: {readiness['spark_job_execution']}",
            f"  missing_sample_cases: {_format_safe_labels(readiness['missing_sample_cases'])}",
            "  missing_synthetic_rejection_cases: "
            f"{_format_safe_labels(readiness['missing_synthetic_rejection_cases'])}",
            "  missing_source_contracts: "
            f"{_format_safe_labels(readiness['missing_source_contracts'])}",
            "  missing_diagnostic_signal_groups: "
            f"{_format_safe_labels(readiness['missing_diagnostic_signal_groups'])}",
            "  missing_diagnostic_lane_readiness: "
            f"{_format_safe_labels(readiness['missing_diagnostic_lane_readiness'])}",
            f"  source_warnings_clear: {str(readiness['source_warnings_clear']).lower()}",
            f"  promotion_blockers: {_format_safe_labels(readiness['promotion_blockers'])}",
        ]
    )
    return "\n".join(lines)


def _spark_evidence_readiness_status(
    *,
    missing_sample_cases: Sequence[str],
    missing_synthetic_rejection_cases: Sequence[str],
    missing_source_contracts: Sequence[str],
    missing_diagnostic_signal_groups: Sequence[str],
    missing_diagnostic_lane_readiness: Sequence[str],
    supported_attention_area_count: int,
    source_warning_count: int,
) -> str:
    if (
        missing_sample_cases
        or missing_synthetic_rejection_cases
        or missing_source_contracts
        or missing_diagnostic_signal_groups
        or missing_diagnostic_lane_readiness
        or supported_attention_area_count <= 0
    ):
        return SPARK_EVIDENCE_READINESS_PARTIAL
    if source_warning_count > 0:
        return SPARK_EVIDENCE_READINESS_MINIMUM_CASE_SET_READY
    return SPARK_EVIDENCE_READINESS_PROMOTION_CANDIDATE


def _spark_evidence_promotion_blockers(
    *,
    missing_sample_cases: Sequence[str],
    missing_synthetic_rejection_cases: Sequence[str],
    missing_source_contracts: Sequence[str],
    missing_diagnostic_signal_groups: Sequence[str],
    missing_diagnostic_lane_readiness: Sequence[str],
    supported_attention_area_count: int,
    source_warning_count: int,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if missing_sample_cases:
        blockers.append("missing_required_sample_cases")
    if missing_synthetic_rejection_cases:
        blockers.append("missing_synthetic_rejection_cases")
    if missing_source_contracts:
        blockers.append("missing_required_source_contracts")
    if missing_diagnostic_signal_groups:
        blockers.append("missing_required_diagnostic_signal_groups")
    if missing_diagnostic_lane_readiness:
        blockers.append("missing_required_diagnostic_lane_readiness")
    if supported_attention_area_count <= 0:
        blockers.append("missing_supported_attention_area")
    if source_warning_count > 0:
        blockers.append("source_warnings_present")
    return tuple(blockers)


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
        _validate_sample_diagnosis_boundary(diagnosis)
        diagnostic_lane = _validate_sample_diagnostic_lane(diagnosis, payload=payload_mapping)
        supported_attention_area_ids = _supported_attention_area_ids(diagnosis)
        source_warning_ids = _source_warning_ids(payload_mapping)
        _validate_sample_case_contract(
            case=sample["case"],
            source_type=sample["source_type"],
            payload=payload_mapping,
            bundle=bundle,
            source_warning_ids=source_warning_ids,
        )
        bundles.append(bundle)
        sample_results.append(
            SparkEvidencePackageSampleResult(
                case=sample["case"],
                source_type=sample["source_type"],
                source_contract=str(payload_mapping.get("sourceContract")),
                parser_coverage=bundle.identity.parser_coverage,
                diagnostic_lane_schema_version=str(diagnostic_lane["schema_version"]),
                diagnostic_lane_readiness=str(diagnostic_lane["evidence_readiness"]),
                diagnostic_lane_source_granularity=str(diagnostic_lane["source_granularity"]),
                diagnostic_lane_verification_scope=str(diagnostic_lane["verification_scope"]),
                supported_attention_area_ids=supported_attention_area_ids,
                attention_area_count=len(diagnosis.get("attention_areas", ())),
                supported_attention_area_count=len(supported_attention_area_ids),
                source_warning_count=len(source_warning_ids),
                source_warning_ids=source_warning_ids,
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
        label_re=SAFE_CLASS_LABEL_RE,
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
    validate_redaction_note_v1(
        redaction_note,
        package_id=package_id,
        required_classes=SPARK_EVIDENCE_REQUIRED_REDACTION_CLASSES,
        required_sentinel_tests=SPARK_EVIDENCE_REQUIRED_SENTINEL_TESTS,
        required_assertions=SPARK_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS,
        required_rejection_reasons=SPARK_EVIDENCE_REQUIRED_REJECTION_REASONS,
        engine_label="Spark",
    )


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


def _validate_sample_case_contract(
    *,
    case: str,
    source_type: str,
    payload: Mapping[str, Any],
    bundle: EngineFactBundle,
    source_warning_ids: Sequence[str],
) -> None:
    if case != "application_only_same_application":
        return
    if source_type != "spark_history_server_compact":
        raise EngineFactContractError(
            "Spark evidence package application-only sample needs History Server compact evidence"
        )
    provenance = payload.get("provenance")
    sql_execution = payload.get("sqlExecution")
    if not isinstance(provenance, Mapping) or not isinstance(sql_execution, Mapping):
        raise EngineFactContractError(
            "Spark evidence package application-only sample needs compact evidence"
        )
    if provenance.get("queryLinkage") != "same_application" or source_warning_ids:
        raise EngineFactContractError(
            "Spark evidence package application-only sample needs warning-free same_application evidence"
        )
    if (
        sql_execution.get("factState") != "unknown"
        or sql_execution.get("lifecycle") != "unknown"
        or sql_execution.get("failureCategoryState") != "unknown"
        or sql_execution.get("failureCategory") != "unknown"
        or sql_execution.get("elapsedTimeMillis") != 0
    ):
        raise EngineFactContractError(
            "Spark evidence package application-only sample must not claim SQL execution facts"
        )
    facts = bundle.facts_by_id()
    if not (
        _metric_value_supported(facts, "spark_query_linkage", "same_application")
        and _metric_state(facts, "spark_sql_elapsed_time_ms") == "unknown"
        and _metric_positive(facts, "spark_linked_job_count")
        and _metric_positive(facts, "spark_stage_count")
        and _metric_positive(facts, "spark_task_count")
        and _metric_positive(facts, "spark_sampled_task_count")
        and _metric_state(facts, "spark_scheduler_delay_ms") in {"supported", "not_observed"}
        and _metric_state(facts, "spark_spilled_bytes") in {"supported", "not_observed"}
        and _metric_state(facts, "spark_history_source_coverage") == "supported"
    ):
        raise EngineFactContractError(
            "Spark evidence package application-only sample needs application-level stage and task evidence"
        )


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


def diagnostic_signal_groups_for_attention_ids(attention_ids: Sequence[str]) -> tuple[str, ...]:
    groups: set[str] = set()
    for attention_id in attention_ids:
        for group, group_attention_ids in SPARK_EVIDENCE_DIAGNOSTIC_SIGNAL_GROUPS.items():
            if attention_id in group_attention_ids:
                groups.add(group)
        for prefix, group in SPARK_EVIDENCE_DIAGNOSTIC_SIGNAL_PREFIX_GROUPS.items():
            if attention_id.startswith(prefix):
                groups.add(group)
    return tuple(sorted(groups))


def _supported_attention_area_ids(diagnosis: Mapping[str, Any]) -> tuple[str, ...]:
    attention_areas = diagnosis.get("attention_areas", ())
    if not isinstance(attention_areas, Sequence) or isinstance(attention_areas, (str, bytes)):
        return ()
    attention_ids: set[str] = set()
    for area in attention_areas:
        if not isinstance(area, Mapping) or area.get("state") != "supported":
            continue
        attention_id = area.get("id")
        if isinstance(attention_id, str) and attention_id:
            attention_ids.add(attention_id)
    return tuple(sorted(attention_ids))


def _source_warning_ids(payload: Mapping[str, Any]) -> tuple[str, ...]:
    source_coverage = payload.get("sourceCoverage")
    if not isinstance(source_coverage, Mapping):
        return ()
    warning_ids = source_coverage.get("warningIds")
    if isinstance(warning_ids, Sequence) and not isinstance(warning_ids, (str, bytes)):
        return tuple(str(warning_id) for warning_id in warning_ids if isinstance(warning_id, str))
    return ()


def _metric_state(facts: Mapping[str, Any], fact_id: str) -> str:
    fact = facts.get(fact_id)
    state = getattr(fact, "state", None)
    return state if isinstance(state, str) else "unknown"


def _metric_value_supported(facts: Mapping[str, Any], fact_id: str, expected: object) -> bool:
    fact = facts.get(fact_id)
    return _metric_state(facts, fact_id) == "supported" and getattr(fact, "value", None) == expected


def _metric_positive(facts: Mapping[str, Any], fact_id: str) -> bool:
    fact = facts.get(fact_id)
    value = getattr(fact, "value", None)
    return (
        _metric_state(facts, fact_id) == "supported"
        and not isinstance(value, bool)
        and isinstance(value, (float, int))
        and value > 0
    )


def _validate_sample_diagnosis_boundary(diagnosis: Mapping[str, Any]) -> None:
    if diagnosis.get("engine") != "spark":
        raise EngineFactContractError("Spark evidence package diagnosis boundary drifted")
    if diagnosis.get("support_status") != "experimental_compact_intake":
        raise EngineFactContractError("Spark evidence package diagnosis boundary drifted")
    boundary = diagnosis.get("diagnosis_boundary")
    if not isinstance(boundary, Mapping):
        raise EngineFactContractError("Spark evidence package diagnosis boundary drifted")
    for key, expected in SPARK_EVIDENCE_EXPECTED_DIAGNOSIS_BOUNDARY.items():
        if boundary.get(key) != expected:
            raise EngineFactContractError("Spark evidence package diagnosis boundary drifted")


def _validate_sample_diagnostic_lane(
    diagnosis: Mapping[str, Any],
    *,
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    lane = diagnosis.get("diagnostic_lane")
    if not isinstance(lane, Mapping):
        raise EngineFactContractError("Spark evidence package diagnostic lane drifted")
    expected_pairs = {
        "schema_version": SPARK_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
        "lane": SPARK_COMPACT_DIAGNOSTIC_LANE_NAME,
        "promotion_status": "preview_only",
    }
    for key, expected in expected_pairs.items():
        if lane.get(key) != expected:
            raise EngineFactContractError("Spark evidence package diagnostic lane drifted")
    if lane.get("required_gates") != SPARK_EVIDENCE_EXPECTED_DIAGNOSTIC_LANE_GATES:
        raise EngineFactContractError("Spark evidence package diagnostic lane drifted")
    if lane.get("evidence_readiness") not in SPARK_EVIDENCE_DIAGNOSTIC_LANE_READINESS_VALUES:
        raise EngineFactContractError("Spark evidence package diagnostic lane drifted")
    if lane.get("source_granularity") not in SPARK_EVIDENCE_DIAGNOSTIC_LANE_SOURCE_GRANULARITIES:
        raise EngineFactContractError("Spark evidence package diagnostic lane drifted")
    if lane.get("verification_scope") not in SPARK_EVIDENCE_DIAGNOSTIC_LANE_VERIFICATION_SCOPES:
        raise EngineFactContractError("Spark evidence package diagnostic lane drifted")

    supported_attention_area_count = len(_supported_attention_area_ids(diagnosis))
    source_warning_count = len(_diagnosis_source_warnings(diagnosis))
    expected_source_granularity = spark_source_granularity(payload)
    expected_readiness = spark_lane_evidence_readiness(
        parser_coverage=diagnosis.get("parser_coverage"),
        source_warning_count=source_warning_count,
        supported_attention_area_count=supported_attention_area_count,
    )
    if lane.get("source_granularity") != expected_source_granularity:
        raise EngineFactContractError("Spark evidence package diagnostic lane drifted")
    if lane.get("evidence_readiness") != expected_readiness:
        raise EngineFactContractError("Spark evidence package diagnostic lane drifted")
    if lane.get("verification_scope") != spark_lane_verification_scope(
        source_granularity=expected_source_granularity,
        evidence_readiness=expected_readiness,
    ):
        raise EngineFactContractError("Spark evidence package diagnostic lane drifted")
    if lane.get("supported_attention_area_count") != supported_attention_area_count:
        raise EngineFactContractError("Spark evidence package diagnostic lane drifted")
    if lane.get("source_warning_count") != source_warning_count:
        raise EngineFactContractError("Spark evidence package diagnostic lane drifted")
    if lane.get("fact_state_counts") != safe_fact_state_counts(diagnosis.get("state_counts")):
        raise EngineFactContractError("Spark evidence package diagnostic lane drifted")
    return lane


def _diagnosis_source_warnings(diagnosis: Mapping[str, Any]) -> tuple[str, ...]:
    source_warnings = diagnosis.get("source_warnings", ())
    if isinstance(source_warnings, Sequence) and not isinstance(source_warnings, (str, bytes)):
        return tuple(warning_id for warning_id in source_warnings if isinstance(warning_id, str))
    return ()


def _validate_json_size(
    payload: Mapping[str, Any], *, max_json_bytes: int, payload_label: str
) -> None:
    if _json_size(payload, payload_label=payload_label) > max_json_bytes:
        raise EngineFactContractError(f"{payload_label} exceeds byte limit")


def _json_size(payload: Mapping[str, Any], *, payload_label: str) -> int:
    return _shared_json_size(
        payload,
        payload_label=payload_label,
        error_message=f"{payload_label} must be finite JSON",
        compact=False,
        ensure_ascii=True,
        sort_keys=True,
    )


def _max_json_depth(value: Any) -> int:
    return _shared_max_json_depth(
        value,
        count_scalar=True,
        sequence_types=(Sequence,),
    )


def _required_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    return required_mapping(
        payload,
        key,
        missing_message="Spark evidence package section must be an object",
    )


def _required_sequence(payload: Mapping[str, Any], key: str) -> Sequence[Any]:
    return required_sequence(
        payload,
        key,
        missing_message="Spark evidence package section must be a list",
    )


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    return required_text(
        payload,
        key,
        missing_message="Spark evidence package text field is invalid",
        strip=False,
    )


def _version_text(payload: Mapping[str, Any], key: str) -> str:
    return version_text(
        payload,
        key,
        missing_message="Spark evidence package text field is invalid",
        unsupported_message="Spark evidence package version is invalid",
        max_digits=1000,
        strip=False,
    )


def _safe_package_label(payload: Mapping[str, Any], key: str) -> str:
    return safe_package_label(
        payload,
        key,
        missing_message="Spark evidence package text field is invalid",
        unsafe_message="Spark evidence package label is not safe",
        strip=False,
    )


def _safe_class_label(payload: Mapping[str, Any], key: str) -> str:
    return safe_class_label(
        payload,
        key,
        missing_message="Spark evidence package text field is invalid",
        unsafe_message="Spark evidence package class label is not safe",
        strip=False,
    )


def _safe_label_list(
    payload: Mapping[str, Any],
    key: str,
    *,
    label_re: re.Pattern[str] = SAFE_CLASS_LABEL_RE,
    allow_empty: bool,
) -> list[str]:
    return list(
        safe_label_list(
            payload,
            key,
            missing_message="Spark evidence package label list is invalid",
            unsafe_message="Spark evidence package label list contains unsafe text",
            empty_message="Spark evidence package label list must not be empty",
            label_re=label_re,
            allow_empty=allow_empty,
        )
    )


def _utc_date(payload: Mapping[str, Any], key: str) -> str:
    return utc_date(
        payload,
        key,
        missing_message="Spark evidence package text field is invalid",
        invalid_message="Spark evidence package date is invalid",
        strip=False,
    )


def _non_negative_int(payload: Mapping[str, Any], key: str) -> int:
    return non_negative_int(
        payload,
        key,
        invalid_message="Spark evidence package numeric field is invalid",
    )


def _format_safe_labels(labels: Sequence[str]) -> str:
    return format_safe_labels(labels)
