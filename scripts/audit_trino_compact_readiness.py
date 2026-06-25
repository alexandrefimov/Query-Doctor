#!/usr/bin/env python3
"""Audit Trino compact boundary readiness without making a support claim."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.analyzer.engine_fact_consumer import (  # noqa: E402
    FACT_GROUPS,
    engine_fact_consumer_probe_from_boundary,
)
from query_doctor.analyzer.engine_facts import (  # noqa: E402
    ENGINE_FACT_BOUNDARY_SCHEMA_VERSION,
    EngineFactContractError,
    engine_fact_namespace_definitions,
)
from query_doctor.report.safety_validation import (  # noqa: E402
    contains_raw_sql_like_text,
    validate_report_internal_fingerprints,
)
from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    ascii_json_artifact_text,
    output_overlaps_inputs_error,
    same_path,
    write_ascii_json_artifact,
)
from query_doctor.safety import redaction  # noqa: E402
from query_doctor.safety.manifest_references import (  # noqa: E402
    is_safe_relative_json_reference,
)
from query_doctor.trino.diagnosis import (  # noqa: E402
    TRINO_COMPACT_DIAGNOSIS_SUPPORT_STATUS,
    TRINO_COMPACT_DIAGNOSTIC_LANE_NAME,
    TRINO_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
    TRINO_LANE_READINESS_AGGREGATE_SELECTION_ONLY,
    TRINO_LANE_READINESS_COVERAGE_UNKNOWN,
    TRINO_LANE_READINESS_ONE_QUERY_ATTENTION_READY,
    TRINO_LANE_READINESS_ONE_QUERY_LIMITED,
    build_trino_compact_diagnosis_from_boundary,
)


EXPECTED_DIAGNOSIS_BOUNDARY = {
    "root_cause": "not_claimed",
    "details_trusted_report_surface": "not_wired",
    "optimizer_behavior": "not_wired",
    "trino_sql_execution": "not_performed",
    "live_recent_scan": "not_wired",
    "live_known_query_diagnosis": "not_wired",
}
TRINO_SMOKE_SUMMARY_KIND = "trino_kerberos_smoke_summary_v1"
TRINO_SMOKE_BAD_STATUSES = frozenset(
    {
        "request_failed",
        "invalid_response",
        "too_large",
        "too_many_pages",
        "trino_error",
    }
)
TRINO_SMOKE_ALLOWED_STATUSES = TRINO_SMOKE_BAD_STATUSES | frozenset({"ok", "planned"})
TRINO_SMOKE_SAFE_ERROR_TYPES = frozenset(
    {"USER_ERROR", "INTERNAL_ERROR", "INSUFFICIENT_RESOURCES", "EXTERNAL", "unknown"}
)
TRINO_SMOKE_ALLOWED_ERROR_CATEGORIES = (
    TRINO_SMOKE_BAD_STATUSES | TRINO_SMOKE_SAFE_ERROR_TYPES | frozenset({"none"})
)
TRINO_SMOKE_REQUIRED_REDACTION_ASSERTIONS = {
    "statement_text": "not_written",
    "result_values": "not_written",
    "query_identifiers": "not_written",
    "actor_identity_values": "not_written",
    "location_values": "not_written",
    "object_identity_values": "not_written",
    "failure_details": "not_written",
}
TRINO_SMOKE_REQUIRED_LIMITATIONS = frozenset(
    {
        "dev_only_smoke_harness",
        "built_in_readonly_statement_allowlist_only",
        "not_query_doctor_trino_product_support",
    }
)
TRINO_HANDOFF_SUITE_MANIFEST_KIND = "trino_one_query_handoff_suite_v1"
TRINO_READINESS_SUMMARY_KIND = "trino_compact_readiness_summary_v1"
TRINO_ONE_QUERY_HANDOFF_SUMMARY_VERSION = "trino_one_query_handoff_summary_v1"
TRINO_PRODUCT_SURFACE_AUDIT_SUMMARY_KIND = "trino_product_surface_boundary_audit_v1"
REQUIRED_TRINO_LIMITATION_IDS = frozenset(
    {
        "no_live_trino_support",
        "no_browser_report_surface",
        "no_trino_sql_execution",
        "no_root_cause_claim",
    }
)
QUERY_LIST_FACT_PREFIX = "query_list_"
METADATA_SUMMARY_FACT_IDS = frozenset(
    {
        "trino_metadata_column_stats_missing_count",
        "trino_metadata_column_stats_present_count",
        "trino_metadata_columns_checked",
        "trino_metadata_relations_checked",
        "trino_metadata_stats_completeness",
        "trino_metadata_summary_import",
    }
)
SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST = "aggregate_query_list"
SOURCE_GRANULARITY_AGGREGATE_METADATA_SUMMARY = "aggregate_metadata_summary"
SOURCE_GRANULARITY_ONE_QUERY_BOUNDARY = "one_query_boundary"
LOCAL_PATH_RE = re.compile(
    r"(?<![\w/])(?:/private)?/(?:Users|home|tmp|var|etc)/[^\s<>'\"]+"
    r"|(?<![\w/])[A-Za-z]:\\[^\s<>'\"]+"
)
URL_RE = re.compile(r"\bhttps?://\S+", re.IGNORECASE)
TRINO_VERSION_FAMILY_RE = re.compile(r"(unknown|[0-9]{3,4}(?:\.[0-9]{1,3})?)")


class TrinoCompactReadinessInputError(RuntimeError):
    """Raised when boundary JSON cannot be loaded safely."""


@dataclass(frozen=True)
class TrinoCompactReadinessIssue:
    category: str
    message: str


@dataclass
class TrinoCompactReadinessResult:
    source_schema_version: str = "unknown"
    source_version_state: str = "missing"
    trino_version_family: str = "unknown"
    support_status: str = "unknown"
    parser_coverage: str = "unknown"
    lifecycle: str = "unknown"
    source_granularity: str = "unknown"
    diagnostic_lane_checked: bool = False
    diagnostic_lane_readiness: str = "unknown"
    diagnostic_lane_verification_scope: str = "unknown"
    diagnosis_artifact_checked: bool = False
    smoke_summary_checked: bool = False
    readiness_summary_checked: bool = False
    handoff_summary_checked: bool = False
    product_surface_summary_checked: bool = False
    smoke_mode: str = "not_provided"
    fact_count: int = 0
    attention_area_count: int = 0
    supported_attention_area_count: int = 0
    fact_group_counts: Counter[str] = field(default_factory=Counter)
    fact_scope_counts: Counter[str] = field(default_factory=Counter)
    fact_state_counts: Counter[str] = field(default_factory=Counter)
    attention_state_counts: Counter[str] = field(default_factory=Counter)
    limitation_state_counts: Counter[str] = field(default_factory=Counter)
    smoke_status_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[TrinoCompactReadinessIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass
class TrinoCompactReadinessBatchResult:
    input_count: int = 0
    ok_count: int = 0
    failed_count: int = 0
    fact_count: int = 0
    attention_area_count: int = 0
    supported_attention_area_count: int = 0
    diagnostic_lane_checked_count: int = 0
    diagnosis_artifact_checked_count: int = 0
    smoke_summary_checked_count: int = 0
    readiness_summary_checked_count: int = 0
    handoff_summary_checked_count: int = 0
    product_surface_summary_checked_count: int = 0
    source_schema_counts: Counter[str] = field(default_factory=Counter)
    source_version_state_counts: Counter[str] = field(default_factory=Counter)
    trino_version_family_counts: Counter[str] = field(default_factory=Counter)
    support_status_counts: Counter[str] = field(default_factory=Counter)
    parser_coverage_counts: Counter[str] = field(default_factory=Counter)
    lifecycle_counts: Counter[str] = field(default_factory=Counter)
    source_granularity_counts: Counter[str] = field(default_factory=Counter)
    diagnostic_lane_readiness_counts: Counter[str] = field(default_factory=Counter)
    diagnostic_lane_verification_scope_counts: Counter[str] = field(default_factory=Counter)
    fact_group_counts: Counter[str] = field(default_factory=Counter)
    fact_scope_counts: Counter[str] = field(default_factory=Counter)
    fact_state_counts: Counter[str] = field(default_factory=Counter)
    attention_state_counts: Counter[str] = field(default_factory=Counter)
    limitation_state_counts: Counter[str] = field(default_factory=Counter)
    smoke_mode_counts: Counter[str] = field(default_factory=Counter)
    smoke_status_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[tuple[int, TrinoCompactReadinessIssue]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failed_count == 0 and not self.issue_counts


@dataclass(frozen=True)
class TrinoCompactReadinessHandoffEntry:
    boundary_json: Path
    diagnosis_json: Path | None = None
    smoke_summary_json: Path | None = None
    readiness_summary_json: Path | None = None
    handoff_summary_json: Path | None = None
    product_surface_summary_json: Path | None = None


def load_json_object(path: Path, *, input_label: str = "boundary JSON input") -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TrinoCompactReadinessInputError(f"{input_label} could not be read") from exc
    except json.JSONDecodeError as exc:
        raise TrinoCompactReadinessInputError(f"{input_label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise TrinoCompactReadinessInputError(f"{input_label} must be an object")
    return payload


def audit_boundary_json(
    boundary_json: Path,
    *,
    diagnosis_json: Path | None = None,
    smoke_summary_json: Path | None = None,
    readiness_summary_json: Path | None = None,
    handoff_summary_json: Path | None = None,
    required_source_versions: tuple[str, ...] = (),
    require_executed_smoke: bool = False,
    require_supported_attention: bool = False,
    fail_on_unknown_parser_coverage: bool = False,
    require_one_query_boundary: bool = False,
) -> TrinoCompactReadinessResult:
    diagnosis_payload = (
        None
        if diagnosis_json is None
        else load_json_object(diagnosis_json, input_label="diagnosis JSON input")
    )
    smoke_summary_payload = (
        None
        if smoke_summary_json is None
        else load_json_object(smoke_summary_json, input_label="smoke summary JSON input")
    )
    readiness_summary_payload = (
        None
        if readiness_summary_json is None
        else load_json_object(
            readiness_summary_json,
            input_label="readiness summary JSON input",
        )
    )
    handoff_summary_payload = (
        None
        if handoff_summary_json is None
        else load_json_object(
            handoff_summary_json,
            input_label="handoff summary JSON input",
        )
    )
    return audit_boundary_payload(
        load_json_object(boundary_json),
        diagnosis_payload=diagnosis_payload,
        smoke_summary_payload=smoke_summary_payload,
        readiness_summary_payload=readiness_summary_payload,
        handoff_summary_payload=handoff_summary_payload,
        required_source_versions=required_source_versions,
        require_executed_smoke=require_executed_smoke,
        require_supported_attention=require_supported_attention,
        fail_on_unknown_parser_coverage=fail_on_unknown_parser_coverage,
        require_one_query_boundary=require_one_query_boundary,
    )


def audit_boundary_json_suite(
    boundary_jsons: Iterable[Path],
    *,
    required_source_versions: tuple[str, ...] = (),
    require_min_trino_version_families: int = 0,
    required_trino_version_families: tuple[str, ...] = (),
    require_supported_attention: bool = False,
    fail_on_unknown_parser_coverage: bool = False,
    require_one_query_boundary: bool = False,
) -> TrinoCompactReadinessBatchResult:
    batch = TrinoCompactReadinessBatchResult()
    for index, boundary_json in enumerate(boundary_jsons, start=1):
        batch.input_count += 1
        try:
            result = audit_boundary_json(
                boundary_json,
                required_source_versions=required_source_versions,
                require_supported_attention=require_supported_attention,
                fail_on_unknown_parser_coverage=fail_on_unknown_parser_coverage,
                require_one_query_boundary=require_one_query_boundary,
            )
        except TrinoCompactReadinessInputError:
            issue = TrinoCompactReadinessIssue(
                "boundary_input_unreadable",
                "One Trino boundary JSON input could not be read or parsed safely.",
            )
            batch.failed_count += 1
            batch.issue_counts[issue.category] += 1
            batch.issues.append((index, issue))
            continue
        add_suite_result(batch, index, result)
    audit_batch_version_family_breadth(
        batch,
        require_min_trino_version_families=require_min_trino_version_families,
        required_trino_version_families=required_trino_version_families,
    )
    return batch


def audit_handoff_manifest_suite(
    manifest_json: Path,
    *,
    required_source_versions: tuple[str, ...] = (),
    require_min_trino_version_families: int = 0,
    required_trino_version_families: tuple[str, ...] = (),
    require_diagnosis_json: bool = False,
    require_executed_smoke: bool = False,
    require_readiness_summary_json: bool = False,
    require_handoff_summary_json: bool = False,
    require_product_surface_summary_json: bool = False,
    require_supported_attention: bool = False,
    fail_on_unknown_parser_coverage: bool = False,
    require_one_query_boundary: bool = False,
) -> TrinoCompactReadinessBatchResult:
    entries = handoff_manifest_entries(
        load_json_object(manifest_json, input_label="handoff manifest JSON input"),
        base_dir=manifest_json.parent,
    )
    return audit_handoff_entries_suite(
        entries,
        required_source_versions=required_source_versions,
        require_min_trino_version_families=require_min_trino_version_families,
        required_trino_version_families=required_trino_version_families,
        require_diagnosis_json=require_diagnosis_json,
        require_executed_smoke=require_executed_smoke,
        require_readiness_summary_json=require_readiness_summary_json,
        require_handoff_summary_json=require_handoff_summary_json,
        require_product_surface_summary_json=require_product_surface_summary_json,
        require_supported_attention=require_supported_attention,
        fail_on_unknown_parser_coverage=fail_on_unknown_parser_coverage,
        require_one_query_boundary=require_one_query_boundary,
    )


def audit_handoff_entries_suite(
    entries: Iterable[TrinoCompactReadinessHandoffEntry],
    *,
    required_source_versions: tuple[str, ...] = (),
    require_min_trino_version_families: int = 0,
    required_trino_version_families: tuple[str, ...] = (),
    require_diagnosis_json: bool = False,
    require_executed_smoke: bool = False,
    require_readiness_summary_json: bool = False,
    require_handoff_summary_json: bool = False,
    require_product_surface_summary_json: bool = False,
    require_supported_attention: bool = False,
    fail_on_unknown_parser_coverage: bool = False,
    require_one_query_boundary: bool = False,
) -> TrinoCompactReadinessBatchResult:
    batch = TrinoCompactReadinessBatchResult()
    for index, entry in enumerate(entries, start=1):
        batch.input_count += 1
        try:
            result = audit_boundary_json(
                entry.boundary_json,
                diagnosis_json=entry.diagnosis_json,
                smoke_summary_json=entry.smoke_summary_json,
                readiness_summary_json=entry.readiness_summary_json,
                handoff_summary_json=entry.handoff_summary_json,
                required_source_versions=required_source_versions,
                require_executed_smoke=require_executed_smoke,
                require_supported_attention=require_supported_attention,
                fail_on_unknown_parser_coverage=(
                    fail_on_unknown_parser_coverage or entry.readiness_summary_json is not None
                ),
                require_one_query_boundary=(
                    require_one_query_boundary or entry.readiness_summary_json is not None
                ),
            )
        except TrinoCompactReadinessInputError:
            issue = TrinoCompactReadinessIssue(
                "handoff_artifact_unreadable",
                "One Trino handoff suite artifact could not be read or parsed safely.",
            )
            batch.failed_count += 1
            batch.issue_counts[issue.category] += 1
            batch.issues.append((index, issue))
            continue
        if require_diagnosis_json and entry.diagnosis_json is None:
            add_issue(
                result,
                "handoff_diagnosis_artifact_missing",
                "Strict Trino handoff suite readiness requires every entry to include a compact diagnosis artifact.",
            )
        if require_executed_smoke and entry.smoke_summary_json is None:
            add_issue(
                result,
                "handoff_smoke_summary_missing",
                "Strict Trino handoff suite readiness requires every entry to include an executed smoke summary.",
            )
        if require_readiness_summary_json and entry.readiness_summary_json is None:
            add_issue(
                result,
                "handoff_readiness_summary_missing",
                "Strict Trino handoff suite readiness requires every entry to include a readiness summary artifact.",
            )
        if require_handoff_summary_json and entry.handoff_summary_json is None:
            add_issue(
                result,
                "handoff_summary_missing",
                "Strict Trino handoff suite readiness requires every entry to include a handoff summary artifact.",
            )
        if require_product_surface_summary_json and entry.product_surface_summary_json is None:
            add_issue(
                result,
                "handoff_product_surface_summary_missing",
                "Strict Trino handoff suite readiness requires every entry to include a product-surface summary artifact.",
            )
        if entry.product_surface_summary_json is not None:
            try:
                product_surface_summary_payload = load_json_object(
                    entry.product_surface_summary_json,
                    input_label="product-surface summary JSON input",
                )
            except TrinoCompactReadinessInputError:
                add_issue(
                    result,
                    "product_surface_summary_unreadable",
                    "Stored Trino product-surface summary artifact could not be read safely.",
                )
            else:
                audit_product_surface_summary(result, product_surface_summary_payload)
        add_suite_result(batch, index, result)
    audit_batch_version_family_breadth(
        batch,
        require_min_trino_version_families=require_min_trino_version_families,
        required_trino_version_families=required_trino_version_families,
    )
    return batch


def audit_batch_min_inputs(
    batch: TrinoCompactReadinessBatchResult,
    *,
    required_min_inputs: int,
) -> None:
    if required_min_inputs > 0 and batch.input_count < required_min_inputs:
        add_batch_issue(
            batch,
            "trino_suite_min_inputs_missing",
            "Strict Trino suite readiness requires the configured minimum input count.",
        )


def audit_boundary_payload(
    payload: Mapping[str, Any],
    *,
    diagnosis_payload: Mapping[str, Any] | None = None,
    smoke_summary_payload: Mapping[str, Any] | None = None,
    readiness_summary_payload: Mapping[str, Any] | None = None,
    handoff_summary_payload: Mapping[str, Any] | None = None,
    required_source_versions: tuple[str, ...] = (),
    require_executed_smoke: bool = False,
    require_supported_attention: bool = False,
    fail_on_unknown_parser_coverage: bool = False,
    require_one_query_boundary: bool = False,
) -> TrinoCompactReadinessResult:
    result = TrinoCompactReadinessResult(
        source_schema_version=safe_label(payload.get("schema_version")),
        trino_version_family=safe_trino_version_family(payload),
    )
    audit_boundary_raw_free(result, payload)
    audit_required_source_version(
        result,
        payload,
        required_source_versions=required_source_versions,
    )

    try:
        probe = engine_fact_consumer_probe_from_boundary(payload)
    except EngineFactContractError:
        add_issue(
            result,
            "boundary_contract_invalid",
            "Trino boundary JSON failed normalized fact-boundary validation.",
        )
        return result

    audit_probe_boundary(
        result,
        payload,
        probe,
        require_one_query_boundary=require_one_query_boundary,
    )
    if (
        require_one_query_boundary
        and result.source_granularity == SOURCE_GRANULARITY_AGGREGATE_METADATA_SUMMARY
    ):
        return result

    try:
        diagnosis = build_trino_compact_diagnosis_from_boundary(payload)
    except EngineFactContractError:
        add_issue(
            result,
            "compact_diagnosis_invalid",
            "Trino compact diagnosis could not be built from accepted boundary facts.",
        )
        return result

    audit_diagnosis_boundary(result, diagnosis)
    audit_diagnosis_raw_free(result, diagnosis)
    if diagnosis_payload is not None:
        audit_diagnosis_artifact(result, diagnosis_payload, expected_diagnosis=diagnosis)
    if smoke_summary_payload is not None:
        audit_smoke_summary(
            result,
            smoke_summary_payload,
            require_executed_smoke=require_executed_smoke,
        )
    if require_supported_attention and result.supported_attention_area_count <= 0:
        add_issue(
            result,
            "missing_supported_attention_area",
            "Strict readiness requires at least one supported Trino attention area.",
        )
    if fail_on_unknown_parser_coverage and result.parser_coverage == "unknown":
        add_issue(
            result,
            "trino_parser_coverage_unknown",
            "Strict readiness requires supported Trino parser coverage.",
        )
    if readiness_summary_payload is not None:
        audit_readiness_summary(
            result,
            readiness_summary_payload,
            expected_requirements=one_query_handoff_readiness_requirements(
                require_executed_smoke=require_executed_smoke,
                require_supported_attention=require_supported_attention,
            ),
        )
    if handoff_summary_payload is not None:
        audit_handoff_summary(
            result,
            handoff_summary_payload,
            expected_requirements=one_query_handoff_readiness_requirements(
                require_executed_smoke=require_executed_smoke,
                require_supported_attention=require_supported_attention,
            ),
            readiness_summary_written=readiness_summary_payload is not None,
        )
    return result


def audit_required_source_version(
    result: TrinoCompactReadinessResult,
    payload: Mapping[str, Any],
    *,
    required_source_versions: tuple[str, ...],
) -> None:
    identity = mapping(payload.get("identity"))
    source_version = identity.get("source_version")
    if isinstance(source_version, str) and source_version:
        result.source_version_state = "present"
    if not required_source_versions:
        return
    if not isinstance(source_version, str) or not source_version:
        add_issue(
            result,
            "trino_source_version_missing",
            "Strict readiness requires the Trino boundary to carry an accepted source version.",
        )
        return
    if source_version not in required_source_versions:
        add_issue(
            result,
            "trino_source_version_mismatch",
            "Strict readiness accepts only the configured Trino boundary source version.",
        )


def audit_diagnosis_artifact(
    result: TrinoCompactReadinessResult,
    diagnosis_payload: Mapping[str, Any],
    *,
    expected_diagnosis: Mapping[str, Any],
) -> None:
    result.diagnosis_artifact_checked = True
    audit_diagnosis_raw_free(result, diagnosis_payload)
    if json_compatible(diagnosis_payload) != json_compatible(expected_diagnosis):
        add_issue(
            result,
            "diagnosis_artifact_mismatch",
            "Trino compact diagnosis artifact must match the deterministic diagnosis built from the boundary.",
        )


def audit_smoke_summary(
    result: TrinoCompactReadinessResult,
    smoke_summary_payload: Mapping[str, Any],
    *,
    require_executed_smoke: bool,
) -> None:
    result.smoke_summary_checked = True
    text = json.dumps(smoke_summary_payload, ensure_ascii=True, sort_keys=True)
    for category in raw_text_issue_categories(text):
        add_issue(
            result,
            "smoke_summary_raw_boundary",
            f"Trino smoke summary contains raw-like {category} content.",
        )
    if smoke_summary_payload.get("summary_kind") != TRINO_SMOKE_SUMMARY_KIND:
        add_issue(
            result,
            "smoke_summary_contract_invalid",
            "Trino smoke summary must use the expected summary kind.",
        )
    result.smoke_mode = safe_label(smoke_summary_payload.get("mode"))
    if result.smoke_mode not in {"dry_run", "execute"}:
        add_issue(
            result,
            "smoke_summary_contract_invalid",
            "Trino smoke summary mode must be dry_run or execute.",
        )
    if require_executed_smoke and result.smoke_mode != "execute":
        add_issue(
            result,
            "smoke_summary_not_executed",
            "Strict Trino readiness requires an executed Kerberos/SPNEGO smoke summary.",
        )
    checks = list_of_mappings(smoke_summary_payload.get("checks"))
    if not checks:
        add_issue(
            result,
            "smoke_summary_contract_invalid",
            "Trino smoke summary must contain at least one smoke check.",
        )
    bounds = mapping(smoke_summary_payload.get("bounds"))
    statement_count = bounds.get("statement_count")
    if (
        not isinstance(statement_count, int)
        or isinstance(statement_count, bool)
        or statement_count != len(checks)
    ):
        add_issue(
            result,
            "smoke_summary_contract_invalid",
            "Trino smoke summary statement count must match the retained smoke checks.",
        )
    audit_smoke_redaction_contract(result, smoke_summary_payload)
    for check in checks:
        status = safe_label(check.get("status"))
        result.smoke_status_counts[status] += 1
        safe_error_category = safe_label(check.get("safe_error_category"))
        audit_smoke_check_fields(result, check, status=status)
        if status not in TRINO_SMOKE_ALLOWED_STATUSES:
            add_issue(
                result,
                "smoke_summary_contract_invalid",
                "Trino smoke summary checks must use known smoke statuses.",
            )
        if safe_error_category not in TRINO_SMOKE_ALLOWED_ERROR_CATEGORIES:
            add_issue(
                result,
                "smoke_summary_contract_invalid",
                "Trino smoke summary checks must use known safe error categories.",
            )
        if status not in TRINO_SMOKE_BAD_STATUSES and safe_error_category != "none":
            add_issue(
                result,
                "smoke_summary_contract_invalid",
                "Trino successful or planned smoke checks must not carry failure categories.",
            )
        if status in TRINO_SMOKE_BAD_STATUSES:
            add_issue(
                result,
                "smoke_summary_failed_check",
                "Trino smoke summary must not contain failed smoke checks.",
            )
        if require_executed_smoke and status != "ok":
            add_issue(
                result,
                "smoke_summary_check_not_ok",
                "Strict Trino readiness requires every executed smoke check to finish ok.",
            )


def audit_smoke_redaction_contract(
    result: TrinoCompactReadinessResult,
    smoke_summary_payload: Mapping[str, Any],
) -> None:
    redaction_assertions = mapping(smoke_summary_payload.get("redaction"))
    for key, expected in TRINO_SMOKE_REQUIRED_REDACTION_ASSERTIONS.items():
        if redaction_assertions.get(key) != expected:
            add_issue(
                result,
                "smoke_summary_contract_invalid",
                "Trino smoke summary must retain explicit not-written redaction assertions.",
            )
    limitations = smoke_summary_payload.get("limitations")
    if not isinstance(limitations, list) or not TRINO_SMOKE_REQUIRED_LIMITATIONS.issubset(
        {item for item in limitations if isinstance(item, str)}
    ):
        add_issue(
            result,
            "smoke_summary_contract_invalid",
            "Trino smoke summary must retain dev-only and no-product-support limitations.",
        )


def audit_smoke_check_fields(
    result: TrinoCompactReadinessResult,
    check: Mapping[str, Any],
    *,
    status: str,
) -> None:
    rows_seen = check.get("rows_seen")
    result_field_count = check.get("result_field_count")
    page_count = check.get("page_count")
    response_bytes = check.get("response_bytes")
    protocol_state = check.get("protocol_state")

    if status == "planned":
        if (
            rows_seen != "not_run"
            or result_field_count != "not_run"
            or page_count != 0
            or response_bytes != 0
            or protocol_state != "not_run"
        ):
            add_issue(
                result,
                "smoke_summary_contract_invalid",
                "Trino planned smoke checks must keep not-run counters.",
            )
        return

    if not non_negative_int(rows_seen):
        add_issue(
            result,
            "smoke_summary_contract_invalid",
            "Trino executed smoke checks must report a non-negative row count.",
        )
    if result_field_count != "unknown" and not non_negative_int(result_field_count):
        add_issue(
            result,
            "smoke_summary_contract_invalid",
            "Trino executed smoke checks must report a non-negative field count or unknown.",
        )
    if not positive_int(page_count):
        add_issue(
            result,
            "smoke_summary_contract_invalid",
            "Trino executed smoke checks must report a positive page count.",
        )
    if not non_negative_int(response_bytes):
        add_issue(
            result,
            "smoke_summary_contract_invalid",
            "Trino executed smoke checks must report non-negative response bytes.",
        )
    if not isinstance(protocol_state, str) or not protocol_state:
        add_issue(
            result,
            "smoke_summary_contract_invalid",
            "Trino executed smoke checks must report a safe protocol state label.",
        )


def audit_readiness_summary(
    result: TrinoCompactReadinessResult,
    readiness_summary_payload: Mapping[str, Any],
    *,
    expected_requirements: Mapping[str, Any],
) -> None:
    result.readiness_summary_checked = True
    audit_result_version_family_breadth(
        result,
        require_min_trino_version_families=1,
        required_trino_version_families=(),
    )
    expected_payload = readiness_summary_payload_for_comparison(
        result,
        requirements=expected_requirements,
    )
    text = json.dumps(readiness_summary_payload, ensure_ascii=True, sort_keys=True)
    for category in raw_text_issue_categories(text):
        add_issue(
            result,
            "readiness_summary_raw_boundary",
            f"Trino readiness summary contains raw-like {category} content.",
        )
    if readiness_summary_payload.get("summary_kind") != TRINO_READINESS_SUMMARY_KIND:
        add_issue(
            result,
            "readiness_summary_contract_invalid",
            "Trino readiness summary must use the expected summary kind.",
        )
    if readiness_summary_payload.get("mode") != "one_query_live_handoff":
        add_issue(
            result,
            "readiness_summary_contract_invalid",
            "Trino one-query handoff readiness summary must use one_query_live_handoff mode.",
        )
    if readiness_summary_payload.get("ok") is not True:
        add_issue(
            result,
            "readiness_summary_not_ok",
            "Trino one-query handoff readiness summary must record an ok result.",
        )
    audit_readiness_summary_diagnostic_lane(
        result,
        readiness_summary_payload,
        expected_payload,
    )
    if json_compatible(readiness_summary_payload) != json_compatible(expected_payload):
        add_issue(
            result,
            "readiness_summary_artifact_mismatch",
            "Trino readiness summary artifact must match the deterministic one-query readiness audit.",
        )


def audit_readiness_summary_diagnostic_lane(
    result: TrinoCompactReadinessResult,
    readiness_summary_payload: Mapping[str, Any],
    expected_payload: Mapping[str, Any],
) -> None:
    diagnostic_lane = readiness_summary_payload.get("diagnostic_lane")
    expected_diagnostic_lane = expected_payload.get("diagnostic_lane")
    if not isinstance(diagnostic_lane, Mapping) or not isinstance(
        expected_diagnostic_lane, Mapping
    ):
        add_issue(
            result,
            "readiness_summary_diagnostic_lane_gap",
            "Trino readiness summary must retain a structured diagnostic-lane contract.",
        )
        return

    for section in (
        "source_granularity",
        "evidence_readiness",
        "verification_scope",
        "fact_states",
    ):
        section_counts = diagnostic_lane.get(section)
        expected_counts = expected_diagnostic_lane.get(section)
        if not isinstance(section_counts, Mapping) or not isinstance(expected_counts, Mapping):
            add_issue(
                result,
                "readiness_summary_diagnostic_lane_gap",
                "Trino readiness summary diagnostic-lane counters must be structured.",
            )
            continue
        if safe_counter(section_counts) != safe_counter(expected_counts):
            add_issue(
                result,
                "readiness_summary_diagnostic_lane_drift",
                "Trino readiness summary diagnostic-lane counters must match deterministic evidence.",
            )


def audit_handoff_summary(
    result: TrinoCompactReadinessResult,
    handoff_summary_payload: Mapping[str, Any],
    *,
    expected_requirements: Mapping[str, Any],
    readiness_summary_written: bool,
) -> None:
    expected_payload = one_query_handoff_summary_payload(
        result,
        requirements=expected_requirements,
        readiness_summary_written=readiness_summary_written,
    )
    result.handoff_summary_checked = True
    text = json.dumps(handoff_summary_payload, ensure_ascii=True, sort_keys=True)
    for category in raw_text_issue_categories(text):
        add_issue(
            result,
            "handoff_summary_raw_boundary",
            f"Trino one-query handoff summary contains raw-like {category} content.",
        )
    if handoff_summary_payload.get("schema_version") != TRINO_ONE_QUERY_HANDOFF_SUMMARY_VERSION:
        add_issue(
            result,
            "handoff_summary_contract_invalid",
            "Trino one-query handoff summary must use the expected schema version.",
        )
    if handoff_summary_payload.get("mode") != "one_query_pruned_coordinator":
        add_issue(
            result,
            "handoff_summary_contract_invalid",
            "Trino one-query handoff summary must use one_query_pruned_coordinator mode.",
        )
    if handoff_summary_payload.get("status") != "ok":
        add_issue(
            result,
            "handoff_summary_not_ok",
            "Trino one-query handoff summary must record an ok readiness result.",
        )
    if handoff_summary_payload.get("pipeline") != expected_payload["pipeline"]:
        add_issue(
            result,
            "handoff_summary_pipeline_mismatch",
            "Trino one-query handoff summary pipeline must match retained readiness evidence.",
        )
    if handoff_summary_payload.get("artifacts") != expected_payload["artifacts"]:
        add_issue(
            result,
            "handoff_summary_artifact_boundary",
            "Trino one-query handoff summary artifact states must keep the path-free boundary.",
        )
    if not isinstance(handoff_summary_payload.get("readiness"), Mapping):
        add_issue(
            result,
            "handoff_summary_readiness_boundary",
            "Trino one-query handoff summary must include compact readiness evidence.",
        )
    if json_compatible(handoff_summary_payload) != json_compatible(expected_payload):
        add_issue(
            result,
            "handoff_summary_artifact_mismatch",
            "Trino one-query handoff summary artifact must match deterministic handoff evidence.",
        )


def audit_product_surface_summary(
    result: TrinoCompactReadinessResult,
    product_surface_summary_payload: Mapping[str, Any],
) -> None:
    result.product_surface_summary_checked = True
    text = json.dumps(product_surface_summary_payload, ensure_ascii=True, sort_keys=True)
    for category in raw_text_issue_categories(text):
        add_issue(
            result,
            "product_surface_summary_raw_boundary",
            f"Trino product-surface summary contains raw-like {category} content.",
        )
    if (
        product_surface_summary_payload.get("summary_kind")
        != TRINO_PRODUCT_SURFACE_AUDIT_SUMMARY_KIND
    ):
        add_issue(
            result,
            "product_surface_summary_contract_invalid",
            "Trino product-surface summary must use the expected summary kind.",
        )
    if product_surface_summary_payload.get("mode") != "trino_product_surface_boundary":
        add_issue(
            result,
            "product_surface_summary_contract_invalid",
            "Trino product-surface summary must use trino_product_surface_boundary mode.",
        )
    if product_surface_summary_payload.get("status") != "ok":
        add_issue(
            result,
            "product_surface_summary_not_ok",
            "Trino product-surface summary must record an ok product-surface boundary audit.",
        )
    boundary = mapping(product_surface_summary_payload.get("boundary"))
    expected_boundary = {
        "product_surface": "recent_query_id_raw_free_details_python_report_optimizer_guidance",
        "support_claim": "local_production",
        "details_case_view": "raw_free_materialized",
        "python_report": "raw_free_materialized",
        "optimizer_guidance": "raw_free_materialized",
        "llm_reports": "not_wired",
        "trusted_reports": "python_report_only",
        "optimizer_behavior": "guidance_only",
        "live_recent_scan": "retained_query_list_local_production",
        "live_known_query_diagnosis": "one_query_pruned_query_info_local_production",
        "trino_sql_execution": "not_performed",
    }
    for key, expected in expected_boundary.items():
        if boundary.get(key) != expected:
            add_issue(
                result,
                "product_surface_summary_boundary_drift",
                "Trino product-surface summary must keep the bounded local production boundary.",
            )
    counts = mapping(product_surface_summary_payload.get("counts"))
    if counts.get("boundary_json_count") != 1:
        add_issue(
            result,
            "product_surface_summary_contract_invalid",
            "Trino retained product-surface summaries must describe one handoff entry.",
        )
    expected_counts = {
        "attention_area_count": result.attention_area_count,
        "supported_attention_area_count": result.supported_attention_area_count,
        "diagnostic_lane_checked_count": 1 if result.diagnostic_lane_checked else 0,
    }
    for key, expected in expected_counts.items():
        if counts.get(key) != expected:
            add_issue(
                result,
                "product_surface_summary_mismatch",
                "Trino product-surface summary counts must match deterministic readiness evidence.",
            )
    expected_lane = diagnostic_lane_summary_payload(
        source_granularity_counts=Counter({result.source_granularity: 1}),
        evidence_readiness_counts=Counter({result.diagnostic_lane_readiness: 1}),
        verification_scope_counts=Counter({result.diagnostic_lane_verification_scope: 1}),
        fact_state_counts=result.fact_state_counts,
    )
    if product_surface_summary_payload.get("diagnostic_lane") != expected_lane:
        add_issue(
            result,
            "product_surface_summary_mismatch",
            "Trino product-surface summary diagnostic lane must match deterministic readiness evidence.",
        )


def audit_probe_boundary(
    result: TrinoCompactReadinessResult,
    payload: Mapping[str, Any],
    probe: Mapping[str, Any],
    *,
    require_one_query_boundary: bool = False,
) -> None:
    if probe.get("engine") != "trino":
        add_issue(
            result,
            "boundary_engine_mismatch",
            "Trino readiness accepts only engine=trino boundaries.",
        )
        return
    result.source_schema_version = safe_label(probe.get("source_schema_version"))
    result.parser_coverage = safe_label(probe.get("parser_coverage"))
    result.lifecycle = safe_label(probe.get("lifecycle"))
    result.fact_state_counts.update(safe_counter(probe.get("state_counts")))

    fact_groups = mapping(payload.get("fact_groups"))
    definitions = {
        definition.fact_id: definition for definition in engine_fact_namespace_definitions()
    }
    query_list_fact_seen = False
    metadata_summary_fact_seen = False
    for group in FACT_GROUPS:
        facts = list_of_mappings(fact_groups.get(group))
        result.fact_group_counts[group] += len(facts)
        result.fact_count += len(facts)
        for fact in facts:
            fact_id = fact.get("id")
            if not isinstance(fact_id, str):
                continue
            if fact_id.startswith(QUERY_LIST_FACT_PREFIX):
                query_list_fact_seen = True
            if fact_id in METADATA_SUMMARY_FACT_IDS:
                metadata_summary_fact_seen = True
            definition = definitions.get(fact_id)
            if definition is None:
                result.fact_scope_counts["unregistered"] += 1
                add_issue(
                    result,
                    "trino_fact_unregistered",
                    "Trino boundary facts must use registered fact identifiers.",
                )
                continue
            result.fact_scope_counts[definition.scope] += 1
            if definition.scope == "shared":
                add_issue(
                    result,
                    "trino_fact_promoted_to_shared_scope",
                    "Trino facts must not move into shared scope without a promotion gate.",
                )
            if definition.scope == "engine_specific" and fact_id.startswith(("impala_", "spark_")):
                add_issue(
                    result,
                    "trino_engine_fact_foreign_prefix",
                    "Trino engine-specific facts must not borrow another engine prefix.",
                )
    if query_list_fact_seen:
        result.source_granularity = SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST
    elif metadata_summary_fact_seen:
        result.source_granularity = SOURCE_GRANULARITY_AGGREGATE_METADATA_SUMMARY
    else:
        result.source_granularity = SOURCE_GRANULARITY_ONE_QUERY_BOUNDARY
    if require_one_query_boundary and query_list_fact_seen:
        add_issue(
            result,
            "trino_query_list_aggregate_not_one_query",
            "Strict one-query readiness must not use aggregate query-list boundary facts.",
        )
    if require_one_query_boundary and metadata_summary_fact_seen:
        add_issue(
            result,
            "trino_metadata_summary_aggregate_not_one_query",
            "Strict one-query readiness must not use aggregate metadata-summary boundary facts.",
        )


def audit_diagnosis_boundary(
    result: TrinoCompactReadinessResult,
    diagnosis: Mapping[str, Any],
) -> None:
    if diagnosis.get("engine") != "trino":
        add_issue(
            result,
            "diagnosis_engine_mismatch",
            "Trino compact diagnosis must stay on engine=trino.",
        )
    result.support_status = safe_label(diagnosis.get("support_status"))
    if result.support_status != TRINO_COMPACT_DIAGNOSIS_SUPPORT_STATUS:
        add_issue(
            result,
            "trino_support_claim_boundary",
            "Trino compact diagnosis must stay below live product support.",
        )

    boundary = diagnosis.get("diagnosis_boundary")
    if not isinstance(boundary, Mapping):
        add_issue(
            result,
            "missing_diagnosis_boundary",
            "Trino compact diagnosis must publish an explicit no-claim boundary.",
        )
    else:
        for key, expected in EXPECTED_DIAGNOSIS_BOUNDARY.items():
            if boundary.get(key) != expected:
                add_issue(
                    result,
                    "trino_diagnosis_boundary_drift",
                    "Trino compact diagnosis boundary no longer matches the no-claim contract.",
                )

    attention_areas = list_of_mappings(diagnosis.get("attention_areas"))
    result.attention_area_count = len(attention_areas)
    for area in attention_areas:
        state = safe_label(area.get("state"))
        result.attention_state_counts[state] += 1
        if state == "supported":
            result.supported_attention_area_count += 1

    limitations = list_of_mappings(diagnosis.get("limitations"))
    limitation_ids: set[str] = set()
    for limitation in limitations:
        limitation_id = limitation.get("id")
        if isinstance(limitation_id, str):
            limitation_ids.add(limitation_id)
        result.limitation_state_counts[safe_label(limitation.get("state"))] += 1
    missing_limitations = REQUIRED_TRINO_LIMITATION_IDS - limitation_ids
    if missing_limitations:
        add_issue(
            result,
            "trino_limitation_boundary_missing",
            "Trino compact diagnosis must keep explicit support and no-claim limitations.",
        )
    audit_diagnostic_lane(result, diagnosis)


def audit_diagnostic_lane(
    result: TrinoCompactReadinessResult,
    diagnosis: Mapping[str, Any],
) -> None:
    lane = diagnosis.get("diagnostic_lane")
    if not isinstance(lane, Mapping):
        add_issue(
            result,
            "trino_diagnostic_lane_missing",
            "Trino compact diagnosis must publish a diagnostic-lane contract.",
        )
        return

    result.diagnostic_lane_checked = True
    result.diagnostic_lane_readiness = safe_label(lane.get("evidence_readiness"))
    result.diagnostic_lane_verification_scope = safe_label(lane.get("verification_scope"))
    expected_readiness = expected_diagnostic_lane_readiness(result)
    expected_verification_scope = expected_diagnostic_lane_verification_scope(
        result.source_granularity,
        expected_readiness,
    )

    expected_values = {
        "schema_version": TRINO_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
        "lane": TRINO_COMPACT_DIAGNOSTIC_LANE_NAME,
        "promotion_status": "preview_only",
        "source_granularity": result.source_granularity,
        "evidence_readiness": expected_readiness,
        "verification_scope": expected_verification_scope,
        "supported_attention_area_count": result.supported_attention_area_count,
    }
    for key, expected in expected_values.items():
        if lane.get(key) != expected:
            add_issue(
                result,
                "trino_diagnostic_lane_drift",
                "Trino compact diagnosis diagnostic-lane contract no longer matches boundary evidence.",
            )

    required_gates = lane.get("required_gates")
    if not isinstance(required_gates, Mapping) or required_gates != {
        "readiness_audit": "required_for_handoff",
        "surface_audit": "required_before_wiring",
    }:
        add_issue(
            result,
            "trino_diagnostic_lane_gate_drift",
            "Trino compact diagnosis must keep explicit readiness and product-surface gates.",
        )

    if lane.get("fact_state_counts") != counter_payload(result.fact_state_counts):
        add_issue(
            result,
            "trino_diagnostic_lane_state_count_drift",
            "Trino compact diagnosis diagnostic-lane fact-state counts must match boundary evidence.",
        )


def expected_diagnostic_lane_readiness(result: TrinoCompactReadinessResult) -> str:
    if result.parser_coverage == "unknown":
        return TRINO_LANE_READINESS_COVERAGE_UNKNOWN
    if result.source_granularity == SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST:
        return TRINO_LANE_READINESS_AGGREGATE_SELECTION_ONLY
    if result.supported_attention_area_count > 0:
        return TRINO_LANE_READINESS_ONE_QUERY_ATTENTION_READY
    return TRINO_LANE_READINESS_ONE_QUERY_LIMITED


def expected_diagnostic_lane_verification_scope(
    source_granularity: str,
    evidence_readiness: str,
) -> str:
    if evidence_readiness == TRINO_LANE_READINESS_COVERAGE_UNKNOWN:
        return "source_contract_review"
    if source_granularity == SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST:
        return "representative_query_selection"
    return "comparable_one_query_rerun"


def audit_boundary_raw_free(
    result: TrinoCompactReadinessResult,
    payload: Mapping[str, Any],
) -> None:
    text = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    for category in raw_text_issue_categories(text):
        add_issue(
            result,
            "boundary_raw_boundary",
            f"Trino boundary JSON contains raw-like {category} content.",
        )


def audit_diagnosis_raw_free(
    result: TrinoCompactReadinessResult,
    diagnosis: Mapping[str, Any],
) -> None:
    text = json.dumps(diagnosis, ensure_ascii=True, sort_keys=True)
    for category in raw_text_issue_categories(text):
        add_issue(
            result,
            "diagnosis_raw_boundary",
            f"Trino compact diagnosis contains raw-like {category} content.",
        )


def raw_text_issue_categories(text: str) -> tuple[str, ...]:
    categories: list[str] = []
    if contains_raw_sql_like_text(text):
        categories.append("sql")
    if validate_report_internal_fingerprints(text):
        categories.append("internal_fingerprint")
    if redaction.EMAIL_RE.search(text):
        categories.append("email")
    if redaction.IPV4_RE.search(text):
        categories.append("ipv4")
    if redaction.HOSTLIKE_FQDN_RE.search(text):
        categories.append("hostname")
    if URL_RE.search(text):
        categories.append("url")
    if LOCAL_PATH_RE.search(text):
        categories.append("local_path")
    if redaction.SECRET_VALUE_RE.search(text):
        categories.append("secret")
    return tuple(sorted(set(categories)))


def add_issue(
    result: TrinoCompactReadinessResult,
    category: str,
    message: str,
) -> None:
    result.issue_counts[category] += 1
    result.issues.append(TrinoCompactReadinessIssue(category, message))


def add_batch_issue(
    batch: TrinoCompactReadinessBatchResult,
    category: str,
    message: str,
) -> None:
    batch.issue_counts[category] += 1
    batch.issues.append((0, TrinoCompactReadinessIssue(category, message)))


def add_suite_result(
    batch: TrinoCompactReadinessBatchResult,
    index: int,
    result: TrinoCompactReadinessResult,
) -> None:
    if result.ok:
        batch.ok_count += 1
    else:
        batch.failed_count += 1
    batch.fact_count += result.fact_count
    batch.attention_area_count += result.attention_area_count
    batch.supported_attention_area_count += result.supported_attention_area_count
    if result.diagnostic_lane_checked:
        batch.diagnostic_lane_checked_count += 1
    if result.diagnosis_artifact_checked:
        batch.diagnosis_artifact_checked_count += 1
    if result.smoke_summary_checked:
        batch.smoke_summary_checked_count += 1
    if result.readiness_summary_checked:
        batch.readiness_summary_checked_count += 1
    if result.handoff_summary_checked:
        batch.handoff_summary_checked_count += 1
    if result.product_surface_summary_checked:
        batch.product_surface_summary_checked_count += 1
    batch.source_schema_counts[result.source_schema_version] += 1
    batch.source_version_state_counts[result.source_version_state] += 1
    batch.trino_version_family_counts[result.trino_version_family] += 1
    batch.support_status_counts[result.support_status] += 1
    batch.parser_coverage_counts[result.parser_coverage] += 1
    batch.lifecycle_counts[result.lifecycle] += 1
    batch.source_granularity_counts[result.source_granularity] += 1
    batch.diagnostic_lane_readiness_counts[result.diagnostic_lane_readiness] += 1
    batch.diagnostic_lane_verification_scope_counts[result.diagnostic_lane_verification_scope] += 1
    batch.fact_group_counts.update(result.fact_group_counts)
    batch.fact_scope_counts.update(result.fact_scope_counts)
    batch.fact_state_counts.update(result.fact_state_counts)
    batch.attention_state_counts.update(result.attention_state_counts)
    batch.limitation_state_counts.update(result.limitation_state_counts)
    batch.smoke_mode_counts[result.smoke_mode] += 1
    batch.smoke_status_counts.update(result.smoke_status_counts)
    batch.issue_counts.update(result.issue_counts)
    for issue in result.issues:
        batch.issues.append((index, issue))


def audit_batch_version_family_breadth(
    batch: TrinoCompactReadinessBatchResult,
    *,
    require_min_trino_version_families: int,
    required_trino_version_families: tuple[str, ...],
) -> None:
    observed_version_families = {
        family
        for family, count in batch.trino_version_family_counts.items()
        if count > 0 and family != "unknown"
    }
    if len(observed_version_families) < require_min_trino_version_families:
        add_batch_issue(
            batch,
            "trino_suite_version_family_gap",
            "Strict Trino suite readiness requires more Trino version-family coverage.",
        )
    for version_family in required_trino_version_families:
        if batch.trino_version_family_counts[version_family] <= 0:
            add_batch_issue(
                batch,
                "trino_suite_version_family_gap",
                "Strict Trino suite readiness requires each selected Trino version family to appear.",
            )


def audit_result_version_family_breadth(
    result: TrinoCompactReadinessResult,
    *,
    require_min_trino_version_families: int,
    required_trino_version_families: tuple[str, ...],
) -> None:
    observed_version_families = (
        {result.trino_version_family} if result.trino_version_family != "unknown" else set()
    )
    if len(observed_version_families) < require_min_trino_version_families:
        add_issue(
            result,
            "trino_version_family_gap",
            "Strict Trino readiness requires more Trino version-family coverage.",
        )
    for version_family in required_trino_version_families:
        if result.trino_version_family != version_family:
            add_issue(
                result,
                "trino_version_family_gap",
                "Strict Trino readiness requires the selected Trino version family to appear.",
            )


def readiness_summary_payload(
    result: TrinoCompactReadinessResult,
    *,
    mode: str,
    requirements: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "summary_kind": TRINO_READINESS_SUMMARY_KIND,
        "mode": mode,
        "ok": result.ok,
        "input_count": 1,
        "ok_count": 1 if result.ok else 0,
        "failed_count": 0 if result.ok else 1,
        "boundary": {
            "support_status": result.support_status,
            "root_cause": "not_claimed",
            "trino_sql_execution": "not_performed",
            "live_recent_scan": "not_wired",
        },
        "source": {
            "schema": result.source_schema_version,
            "source_version_state": result.source_version_state,
            "trino_version_family": result.trino_version_family,
            "parser_coverage": result.parser_coverage,
            "lifecycle": result.lifecycle,
            "granularity": result.source_granularity,
        },
        "artifacts": {
            "diagnostic_lane_checked": result.diagnostic_lane_checked,
            "diagnosis_checked": result.diagnosis_artifact_checked,
            "smoke_checked": result.smoke_summary_checked,
            "smoke_mode": result.smoke_mode,
        },
        "totals": {
            "facts": result.fact_count,
            "attention_areas": result.attention_area_count,
            "supported_attention_areas": result.supported_attention_area_count,
        },
        "diagnostic_lane": diagnostic_lane_summary_payload(
            source_granularity_counts=Counter({result.source_granularity: 1}),
            evidence_readiness_counts=Counter({result.diagnostic_lane_readiness: 1}),
            verification_scope_counts=Counter({result.diagnostic_lane_verification_scope: 1}),
            fact_state_counts=result.fact_state_counts,
        ),
        "counters": {
            "fact_groups": counter_payload(result.fact_group_counts),
            "fact_scopes": counter_payload(result.fact_scope_counts),
            "fact_states": counter_payload(result.fact_state_counts),
            "attention_states": counter_payload(result.attention_state_counts),
            "diagnostic_lane_readiness": counter_payload(
                Counter({result.diagnostic_lane_readiness: 1})
            ),
            "diagnostic_lane_verification_scope": counter_payload(
                Counter({result.diagnostic_lane_verification_scope: 1})
            ),
            "limitation_states": counter_payload(result.limitation_state_counts),
            "smoke_statuses": counter_payload(result.smoke_status_counts),
            "issues": counter_payload(result.issue_counts),
        },
        "requirements": dict(requirements),
    }


def readiness_suite_summary_payload(
    batch: TrinoCompactReadinessBatchResult,
    *,
    mode: str,
    requirements: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "summary_kind": TRINO_READINESS_SUMMARY_KIND,
        "mode": mode,
        "ok": batch.ok,
        "input_count": batch.input_count,
        "ok_count": batch.ok_count,
        "failed_count": batch.failed_count,
        "artifacts": {
            "diagnostic_lane_checked": batch.diagnostic_lane_checked_count,
            "diagnosis_checked": batch.diagnosis_artifact_checked_count,
            "smoke_checked": batch.smoke_summary_checked_count,
            "readiness_summary_checked": batch.readiness_summary_checked_count,
            "handoff_summary_checked": batch.handoff_summary_checked_count,
            "product_surface_summary_checked": batch.product_surface_summary_checked_count,
        },
        "totals": {
            "facts": batch.fact_count,
            "attention_areas": batch.attention_area_count,
            "supported_attention_areas": batch.supported_attention_area_count,
        },
        "diagnostic_lane": diagnostic_lane_summary_payload(
            source_granularity_counts=batch.source_granularity_counts,
            evidence_readiness_counts=batch.diagnostic_lane_readiness_counts,
            verification_scope_counts=batch.diagnostic_lane_verification_scope_counts,
            fact_state_counts=batch.fact_state_counts,
        ),
        "counters": {
            "source_schemas": counter_payload(batch.source_schema_counts),
            "source_version_states": counter_payload(batch.source_version_state_counts),
            "trino_version_families": counter_payload(batch.trino_version_family_counts),
            "support_statuses": counter_payload(batch.support_status_counts),
            "parser_coverage": counter_payload(batch.parser_coverage_counts),
            "lifecycles": counter_payload(batch.lifecycle_counts),
            "source_granularity": counter_payload(batch.source_granularity_counts),
            "fact_groups": counter_payload(batch.fact_group_counts),
            "fact_scopes": counter_payload(batch.fact_scope_counts),
            "fact_states": counter_payload(batch.fact_state_counts),
            "attention_states": counter_payload(batch.attention_state_counts),
            "diagnostic_lane_readiness": counter_payload(batch.diagnostic_lane_readiness_counts),
            "diagnostic_lane_verification_scope": counter_payload(
                batch.diagnostic_lane_verification_scope_counts
            ),
            "limitation_states": counter_payload(batch.limitation_state_counts),
            "smoke_modes": counter_payload(batch.smoke_mode_counts),
            "smoke_statuses": counter_payload(batch.smoke_status_counts),
            "issues": counter_payload(batch.issue_counts),
        },
        "requirements": dict(requirements),
    }


def one_query_handoff_summary_payload(
    result: TrinoCompactReadinessResult,
    *,
    requirements: Mapping[str, Any],
    readiness_summary_written: bool,
) -> dict[str, Any]:
    status = "ok" if result.ok else "failed"
    return {
        "schema_version": TRINO_ONE_QUERY_HANDOFF_SUMMARY_VERSION,
        "mode": "one_query_pruned_coordinator",
        "status": status,
        "pipeline": {
            "coordinator_query_info_import": "accepted",
            "boundary_facts": "written",
            "compact_diagnosis": "accepted",
            "readiness": status,
        },
        "artifacts": {
            "boundary_json": "written",
            "diagnosis_json": ("written" if result.diagnosis_artifact_checked else "not_provided"),
            "readiness_summary_json": ("written" if readiness_summary_written else "not_requested"),
            "smoke_summary": "checked" if result.smoke_summary_checked else "not_provided",
            "paths": "not_printed",
        },
        "readiness": readiness_summary_payload(
            result,
            mode="one_query_live_handoff",
            requirements=requirements,
        ),
    }


def diagnostic_lane_summary_payload(
    *,
    source_granularity_counts: Counter[str],
    evidence_readiness_counts: Counter[str],
    verification_scope_counts: Counter[str],
    fact_state_counts: Counter[str],
) -> dict[str, dict[str, int]]:
    return {
        "source_granularity": counter_payload(source_granularity_counts),
        "evidence_readiness": counter_payload(evidence_readiness_counts),
        "verification_scope": counter_payload(verification_scope_counts),
        "fact_states": counter_payload(fact_state_counts),
    }


def counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def write_readiness_summary_json(path: Path, payload: Mapping[str, Any]) -> None:
    text = ascii_json_artifact_text(payload)
    if raw_text_issue_categories(text):
        raise TrinoCompactReadinessInputError("summary JSON output would contain raw-like content")
    try:
        write_ascii_json_artifact(path, payload)
    except OSError as exc:
        raise TrinoCompactReadinessInputError("summary JSON output could not be written") from exc


def requirements_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "require_diagnosis_json": bool(args.require_diagnosis_json),
        "require_executed_smoke": bool(args.require_executed_smoke),
        "require_readiness_summary_json": bool(args.require_readiness_summary_json),
        "require_handoff_summary_json": bool(args.require_handoff_summary_json),
        "require_product_surface_summary_json": bool(args.require_product_surface_summary_json),
        "require_min_inputs": args.require_min_inputs,
        "require_min_trino_version_families": args.require_min_trino_version_families,
        "require_one_query_boundary": bool(args.require_one_query_boundary),
        "require_source_version": bool(args.require_source_version),
        "require_source_version_count": len(args.require_source_version),
        "require_trino_version_family": bool(args.require_trino_version_family),
        "require_trino_version_family_count": len(args.require_trino_version_family),
        "require_supported_attention": bool(args.require_supported_attention),
        "fail_on_unknown_parser_coverage": bool(args.fail_on_unknown_parser_coverage),
    }


def reject_summary_output_overlap(
    summary_json: Path | None,
    protected_inputs: Iterable[Path | None],
) -> str | None:
    return output_overlaps_inputs_error(
        summary_json,
        protected_inputs,
        message="summary JSON output must differ from every input artifact",
    )


def handoff_manifest_entries(
    payload: Mapping[str, Any],
    *,
    base_dir: Path,
) -> tuple[TrinoCompactReadinessHandoffEntry, ...]:
    if payload.get("manifest_kind") != TRINO_HANDOFF_SUITE_MANIFEST_KIND:
        raise TrinoCompactReadinessInputError(
            "handoff manifest JSON input must use the expected manifest kind"
        )
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise TrinoCompactReadinessInputError(
            "handoff manifest JSON input must contain at least one entry"
        )
    parsed: list[TrinoCompactReadinessHandoffEntry] = []
    boundary_refs: set[str] = set()
    diagnosis_refs: set[str] = set()
    readiness_summary_refs: set[str] = set()
    handoff_summary_refs: set[str] = set()
    product_surface_summary_refs: set[str] = set()
    suite_width_artifact_paths: list[Path] = []
    smoke_artifact_paths: list[Path] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise TrinoCompactReadinessInputError(
                "handoff manifest JSON input entries must be objects"
            )
        boundary_ref = manifest_reference(entry.get("boundary_json"), required=True)
        if boundary_ref is None:
            raise TrinoCompactReadinessInputError(
                "handoff manifest JSON input entries require boundary_json"
            )
        if boundary_ref in boundary_refs:
            raise TrinoCompactReadinessInputError(
                "handoff manifest JSON input boundary references must be unique"
            )
        boundary_refs.add(boundary_ref)
        diagnosis_ref = manifest_reference(entry.get("diagnosis_json"), required=False)
        if diagnosis_ref is not None:
            if diagnosis_ref in diagnosis_refs:
                raise TrinoCompactReadinessInputError(
                    "handoff manifest JSON input diagnosis references must be unique"
                )
            diagnosis_refs.add(diagnosis_ref)
        smoke_ref = manifest_reference(entry.get("smoke_summary"), required=False)
        readiness_summary_ref = manifest_reference(
            entry.get("readiness_summary_json"),
            required=False,
        )
        if readiness_summary_ref is not None:
            if readiness_summary_ref in readiness_summary_refs:
                raise TrinoCompactReadinessInputError(
                    "handoff manifest JSON input readiness summary references must be unique"
                )
            readiness_summary_refs.add(readiness_summary_ref)
        handoff_summary_ref = manifest_reference(
            entry.get("handoff_summary_json"),
            required=False,
        )
        if handoff_summary_ref is not None:
            if handoff_summary_ref in handoff_summary_refs:
                raise TrinoCompactReadinessInputError(
                    "handoff manifest JSON input handoff summary references must be unique"
                )
            handoff_summary_refs.add(handoff_summary_ref)
        product_surface_summary_ref = manifest_reference(
            entry.get("product_surface_summary_json"),
            required=False,
        )
        if product_surface_summary_ref is not None:
            if product_surface_summary_ref in product_surface_summary_refs:
                raise TrinoCompactReadinessInputError(
                    "handoff manifest JSON input product-surface summary references must be unique"
                )
            product_surface_summary_refs.add(product_surface_summary_ref)
        boundary_json = manifest_path(boundary_ref, base_dir=base_dir)
        if boundary_json is None:
            raise TrinoCompactReadinessInputError(
                "handoff manifest JSON input entries require boundary_json"
            )
        diagnosis_json = manifest_path(diagnosis_ref, base_dir=base_dir)
        readiness_summary_json = manifest_path(
            readiness_summary_ref,
            base_dir=base_dir,
        )
        handoff_summary_json = manifest_path(
            handoff_summary_ref,
            base_dir=base_dir,
        )
        product_surface_summary_json = manifest_path(
            product_surface_summary_ref,
            base_dir=base_dir,
        )
        ensure_unique_handoff_manifest_artifact_paths(
            suite_width_artifact_paths,
            smoke_artifact_paths,
            boundary_json,
            diagnosis_json,
            readiness_summary_json,
            handoff_summary_json,
            product_surface_summary_json,
        )
        smoke_summary_json = manifest_path(smoke_ref, base_dir=base_dir)
        ensure_handoff_manifest_smoke_artifact_path(
            suite_width_artifact_paths,
            smoke_artifact_paths,
            smoke_summary_json,
        )
        parsed.append(
            TrinoCompactReadinessHandoffEntry(
                boundary_json=boundary_json,
                diagnosis_json=diagnosis_json,
                smoke_summary_json=smoke_summary_json,
                readiness_summary_json=readiness_summary_json,
                handoff_summary_json=handoff_summary_json,
                product_surface_summary_json=product_surface_summary_json,
            )
        )
    return tuple(parsed)


def ensure_unique_handoff_manifest_artifact_paths(
    seen_paths: list[Path],
    smoke_paths: list[Path],
    *paths: Path | None,
) -> None:
    for path in paths:
        if path is None:
            continue
        if any(same_path(path, seen) for seen in seen_paths) or any(
            same_path(path, smoke) for smoke in smoke_paths
        ):
            raise TrinoCompactReadinessInputError(
                "handoff manifest JSON input boundary, diagnosis, readiness summary, handoff summary, and product-surface summary artifact references must be unique"
            )
        seen_paths.append(path)


def ensure_handoff_manifest_smoke_artifact_path(
    suite_width_artifact_paths: list[Path],
    smoke_artifact_paths: list[Path],
    smoke_summary_json: Path | None,
) -> None:
    if smoke_summary_json is None:
        return
    if any(same_path(smoke_summary_json, artifact) for artifact in suite_width_artifact_paths):
        raise TrinoCompactReadinessInputError(
            "handoff manifest JSON input smoke summary artifacts must differ from boundary, diagnosis, readiness summary, handoff summary, and product-surface summary artifacts"
        )
    smoke_artifact_paths.append(smoke_summary_json)


def manifest_reference(value: Any, *, required: bool) -> str | None:
    if value is None:
        if required:
            raise TrinoCompactReadinessInputError(
                "handoff manifest JSON input entries require boundary_json"
            )
        return None
    if not is_safe_relative_json_reference(value):
        raise TrinoCompactReadinessInputError(
            "handoff manifest JSON input artifact paths must be safe relative JSON references"
        )
    return value


def manifest_path(value: str | None, *, base_dir: Path) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    return base_dir / path


def print_counter(title: str, counter: Counter[str], *, out: TextIO, limit: int) -> None:
    print(f"{title}:", file=out)
    if not counter:
        print("  <none>", file=out)
        return
    for key, count in counter.most_common(limit):
        print(f"  {key}: {count}", file=out)


def print_result(
    result: TrinoCompactReadinessResult,
    *,
    out: TextIO | None = None,
    limit: int = 12,
) -> None:
    if out is None:
        out = sys.stdout
    status = "ok" if result.ok else "failed"
    print(f"Trino compact readiness: {status}", file=out)
    print("Input: boundary_json", file=out)
    print(
        "Boundary: "
        f"support_status={result.support_status}, "
        "root_cause=not_claimed, "
        "trino_sql_execution=not_performed, "
        "live_recent_scan=not_wired, "
        "live_known_query_diagnosis=not_wired",
        file=out,
    )
    print(
        "Source: "
        f"schema={result.source_schema_version}, "
        f"source_version={result.source_version_state}, "
        f"trino_version_family={result.trino_version_family}, "
        f"parser_coverage={result.parser_coverage}, "
        f"lifecycle={result.lifecycle}, "
        f"granularity={result.source_granularity}",
        file=out,
    )
    print(
        "Diagnostic lane: "
        f"{'checked' if result.diagnostic_lane_checked else 'not_provided'}, "
        f"readiness={result.diagnostic_lane_readiness}, "
        f"verification_scope={result.diagnostic_lane_verification_scope}",
        file=out,
    )
    print(
        f"Diagnosis artifact: {'checked' if result.diagnosis_artifact_checked else 'not_provided'}",
        file=out,
    )
    print(
        "Smoke summary: "
        f"{'checked' if result.smoke_summary_checked else 'not_provided'}, "
        f"mode={result.smoke_mode}",
        file=out,
    )
    print(
        "Facts: "
        f"total={result.fact_count}, "
        f"attention_areas={result.attention_area_count}, "
        f"supported_attention_areas={result.supported_attention_area_count}",
        file=out,
    )
    print_counter("Fact groups", result.fact_group_counts, out=out, limit=limit)
    print_counter("Fact scopes", result.fact_scope_counts, out=out, limit=limit)
    print_counter("Fact states", result.fact_state_counts, out=out, limit=limit)
    print_counter("Attention states", result.attention_state_counts, out=out, limit=limit)
    print_counter("Limitation states", result.limitation_state_counts, out=out, limit=limit)
    print_counter("Smoke statuses", result.smoke_status_counts, out=out, limit=limit)
    if result.issues:
        print_counter("Issues", result.issue_counts, out=out, limit=limit)
        print("Issue examples:", file=out)
        for issue in result.issues[:limit]:
            print(f"  {issue.category}: {issue.message}", file=out)
    else:
        print("Issues: none", file=out)


def print_suite_result(
    batch: TrinoCompactReadinessBatchResult,
    *,
    out: TextIO | None = None,
    limit: int = 12,
) -> None:
    if out is None:
        out = sys.stdout
    status = "ok" if batch.ok else "failed"
    print(f"Trino compact readiness suite: {status}", file=out)
    print(
        "Inputs: "
        f"boundary_json_count={batch.input_count}, "
        f"ok={batch.ok_count}, "
        f"failed={batch.failed_count}",
        file=out,
    )
    print(
        "Totals: "
        f"facts={batch.fact_count}, "
        f"attention_areas={batch.attention_area_count}, "
        f"supported_attention_areas={batch.supported_attention_area_count}",
        file=out,
    )
    print(
        "Artifacts: "
        f"diagnostic_lane_checked={batch.diagnostic_lane_checked_count}, "
        f"diagnosis_checked={batch.diagnosis_artifact_checked_count}, "
        f"smoke_checked={batch.smoke_summary_checked_count}, "
        f"readiness_summary_checked={batch.readiness_summary_checked_count}, "
        f"handoff_summary_checked={batch.handoff_summary_checked_count}",
        f", product_surface_summary_checked={batch.product_surface_summary_checked_count}",
        file=out,
    )
    print_counter("Source schemas", batch.source_schema_counts, out=out, limit=limit)
    print_counter("Source version states", batch.source_version_state_counts, out=out, limit=limit)
    print_counter("Trino version families", batch.trino_version_family_counts, out=out, limit=limit)
    print_counter("Support statuses", batch.support_status_counts, out=out, limit=limit)
    print_counter("Parser coverage", batch.parser_coverage_counts, out=out, limit=limit)
    print_counter("Lifecycles", batch.lifecycle_counts, out=out, limit=limit)
    print_counter("Source granularity", batch.source_granularity_counts, out=out, limit=limit)
    print_counter(
        "Diagnostic lane readiness",
        batch.diagnostic_lane_readiness_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Diagnostic lane verification scope",
        batch.diagnostic_lane_verification_scope_counts,
        out=out,
        limit=limit,
    )
    print_counter("Fact groups", batch.fact_group_counts, out=out, limit=limit)
    print_counter("Fact scopes", batch.fact_scope_counts, out=out, limit=limit)
    print_counter("Fact states", batch.fact_state_counts, out=out, limit=limit)
    print_counter("Attention states", batch.attention_state_counts, out=out, limit=limit)
    print_counter("Limitation states", batch.limitation_state_counts, out=out, limit=limit)
    print_counter("Smoke modes", batch.smoke_mode_counts, out=out, limit=limit)
    print_counter("Smoke statuses", batch.smoke_status_counts, out=out, limit=limit)
    if batch.issues:
        print_counter("Issues", batch.issue_counts, out=out, limit=limit)
        print("Issue examples:", file=out)
        for index, issue in batch.issues[:limit]:
            label = "suite" if index <= 0 else f"input-{index:03d}"
            print(f"  {label}: {issue.category}: {issue.message}", file=out)
    else:
        print("Issues: none", file=out)


def list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def safe_counter(value: Any) -> Counter[str]:
    counter: Counter[str] = Counter()
    if not isinstance(value, Mapping):
        return counter
    for key, count in value.items():
        if isinstance(key, str) and isinstance(count, int) and not isinstance(count, bool):
            counter[key] += count
    return counter


def safe_label(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "unknown"
    if raw_text_issue_categories(value):
        return "redacted"
    return value


def safe_trino_version_family(payload: Mapping[str, Any]) -> str:
    fact_groups = mapping(payload.get("fact_groups"))
    for group in FACT_GROUPS:
        for fact in list_of_mappings(fact_groups.get(group)):
            if fact.get("id") != "trino_version_family":
                continue
            if fact.get("state") == "unknown":
                return "unknown"
            value = fact.get("value")
            if isinstance(value, str) and TRINO_VERSION_FAMILY_RE.fullmatch(value):
                return value
            return "unknown"
    return "unknown"


def one_query_handoff_readiness_requirements(
    *,
    require_executed_smoke: bool,
    require_supported_attention: bool,
) -> dict[str, Any]:
    return {
        "require_diagnosis_json": True,
        "require_executed_smoke": bool(require_executed_smoke),
        "require_min_inputs": 1,
        "require_min_trino_version_families": 1,
        "require_one_query_boundary": True,
        "require_source_version": True,
        "require_source_version_count": 1,
        "require_trino_version_family": False,
        "require_trino_version_family_count": 0,
        "require_supported_attention": bool(require_supported_attention),
        "fail_on_unknown_parser_coverage": True,
    }


def readiness_summary_payload_for_comparison(
    result: TrinoCompactReadinessResult,
    *,
    requirements: Mapping[str, Any],
) -> dict[str, Any]:
    expected = readiness_summary_payload(
        result,
        mode="one_query_live_handoff",
        requirements=requirements,
    )
    return expected


def trino_version_family_arg(value: str) -> str:
    if value != "unknown" and TRINO_VERSION_FAMILY_RE.fullmatch(value):
        return value
    raise argparse.ArgumentTypeError(
        "Trino version family must be a safe broad version-family label"
    )


def json_compatible(value: Mapping[str, Any]) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True, sort_keys=True))


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "boundary_json",
        type=Path,
        nargs="*",
        help=(
            "Accepted Trino engine_fact_boundary_v1 JSON. Pass multiple paths for suite "
            "mode, or omit when --handoff-suite-manifest is used."
        ),
    )
    parser.add_argument(
        "--handoff-suite-manifest",
        type=Path,
        default=None,
        help=(
            "Optional trino_one_query_handoff_suite_v1 manifest whose entries reference "
            "boundary_json plus optional diagnosis_json and smoke_summary artifacts. "
            "The manifest path and referenced artifact paths are never printed."
        ),
    )
    parser.add_argument("--limit", type=int, default=12, help="Rows to print per section.")
    parser.add_argument(
        "--require-supported-attention",
        action="store_true",
        help="Return non-zero unless the diagnosis contains a supported Trino attention area.",
    )
    parser.add_argument(
        "--fail-on-unknown-parser-coverage",
        action="store_true",
        help="Return non-zero when parser coverage remains unknown.",
    )
    parser.add_argument(
        "--require-one-query-boundary",
        action="store_true",
        help=(
            "Return non-zero for aggregate query-list or metadata-summary boundaries; "
            "use this for one-query Trino diagnosis readiness gates."
        ),
    )
    parser.add_argument(
        "--require-source-version",
        action="append",
        default=[],
        help=(
            "Require the boundary identity.source_version to match this accepted value. "
            "May be repeated for suite gates; actual boundary values are never printed."
        ),
    )
    parser.add_argument(
        "--require-min-inputs",
        type=int,
        default=0,
        help=(
            "For suite gates, return non-zero unless at least this many boundary or "
            "handoff-manifest entries were checked."
        ),
    )
    parser.add_argument(
        "--require-min-trino-version-families",
        type=int,
        default=0,
        help=(
            "For suite gates, return non-zero unless at least this many non-unknown "
            "safe Trino version-family labels were observed."
        ),
    )
    parser.add_argument(
        "--require-trino-version-family",
        action="append",
        type=trino_version_family_arg,
        default=[],
        help=(
            "For suite gates, require at least one boundary with this safe Trino "
            "version-family label, for example 477. May be repeated."
        ),
    )
    parser.add_argument(
        "--require-diagnosis-json",
        action="store_true",
        help=(
            "Return non-zero unless the single-boundary or handoff-manifest entry has a "
            "matching compact diagnosis JSON artifact."
        ),
    )
    parser.add_argument(
        "--diagnosis-json",
        type=Path,
        default=None,
        help=(
            "Optional compact diagnosis JSON artifact written from the same boundary. "
            "Only valid with one boundary JSON input; the path is never printed."
        ),
    )
    parser.add_argument(
        "--smoke-summary",
        type=Path,
        default=None,
        help=(
            "Optional trino_smoke_summary.json artifact from the dev-only Kerberos/SPNEGO "
            "smoke. Only valid with one boundary JSON input; the path is never printed."
        ),
    )
    parser.add_argument(
        "--require-executed-smoke",
        action="store_true",
        help="Return non-zero unless --smoke-summary records mode=execute.",
    )
    parser.add_argument(
        "--require-readiness-summary-json",
        action="store_true",
        help=(
            "For handoff manifests, return non-zero unless every entry references a "
            "matching trino_compact_readiness_summary_v1 artifact."
        ),
    )
    parser.add_argument(
        "--require-handoff-summary-json",
        action="store_true",
        help=(
            "For handoff manifests, return non-zero unless every entry references a "
            "matching trino_one_query_handoff_summary_v1 artifact."
        ),
    )
    parser.add_argument(
        "--require-product-surface-summary-json",
        action="store_true",
        help=(
            "For handoff manifests, return non-zero unless every entry references a "
            "trino_product_surface_boundary_audit_v1 artifact that keeps Trino below "
            "product-surface promotion."
        ),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help=(
            "Optional output path for a raw-free machine-readable readiness summary. "
            "The path is never printed."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.require_min_inputs < 0:
        print(
            "[trino-compact-readiness] rejected: --require-min-inputs must be non-negative",
            file=sys.stderr,
        )
        return 2
    if args.require_min_trino_version_families < 0:
        print(
            "[trino-compact-readiness] rejected: --require-min-trino-version-families must be non-negative",
            file=sys.stderr,
        )
        return 2
    if args.handoff_suite_manifest is not None and args.boundary_json:
        print(
            "[trino-compact-readiness] rejected: handoff suite manifest cannot be combined with boundary inputs",
            file=sys.stderr,
        )
        return 2
    if args.handoff_suite_manifest is None and not args.boundary_json:
        print(
            "[trino-compact-readiness] rejected: provide a boundary input or handoff suite manifest",
            file=sys.stderr,
        )
        return 2
    if args.handoff_suite_manifest is None and args.require_readiness_summary_json:
        print(
            "[trino-compact-readiness] rejected: --require-readiness-summary-json requires --handoff-suite-manifest",
            file=sys.stderr,
        )
        return 2
    if args.handoff_suite_manifest is None and args.require_handoff_summary_json:
        print(
            "[trino-compact-readiness] rejected: --require-handoff-summary-json requires --handoff-suite-manifest",
            file=sys.stderr,
        )
        return 2
    if args.handoff_suite_manifest is None and args.require_product_surface_summary_json:
        print(
            "[trino-compact-readiness] rejected: --require-product-surface-summary-json requires --handoff-suite-manifest",
            file=sys.stderr,
        )
        return 2
    if args.handoff_suite_manifest is not None:
        if args.diagnosis_json is not None:
            print(
                "[trino-compact-readiness] rejected: use manifest entry diagnosis_json values for handoff suite checks",
                file=sys.stderr,
            )
            return 2
        if args.smoke_summary is not None:
            print(
                "[trino-compact-readiness] rejected: use manifest entry smoke_summary values for handoff suite checks",
                file=sys.stderr,
            )
            return 2
        try:
            entries = handoff_manifest_entries(
                load_json_object(
                    args.handoff_suite_manifest, input_label="handoff manifest JSON input"
                ),
                base_dir=args.handoff_suite_manifest.parent,
            )
            overlap_error = reject_summary_output_overlap(
                args.summary_json,
                (
                    args.handoff_suite_manifest,
                    *(
                        artifact
                        for entry in entries
                        for artifact in (
                            entry.boundary_json,
                            entry.diagnosis_json,
                            entry.smoke_summary_json,
                            entry.readiness_summary_json,
                            entry.handoff_summary_json,
                            entry.product_surface_summary_json,
                        )
                    ),
                ),
            )
            if overlap_error:
                print(f"[trino-compact-readiness] rejected: {overlap_error}", file=sys.stderr)
                return 2
            batch = audit_handoff_entries_suite(
                entries,
                required_source_versions=tuple(args.require_source_version),
                require_min_trino_version_families=args.require_min_trino_version_families,
                required_trino_version_families=tuple(args.require_trino_version_family),
                require_diagnosis_json=args.require_diagnosis_json,
                require_executed_smoke=args.require_executed_smoke,
                require_readiness_summary_json=args.require_readiness_summary_json,
                require_handoff_summary_json=args.require_handoff_summary_json,
                require_product_surface_summary_json=args.require_product_surface_summary_json,
                require_supported_attention=args.require_supported_attention,
                fail_on_unknown_parser_coverage=args.fail_on_unknown_parser_coverage,
                require_one_query_boundary=args.require_one_query_boundary,
            )
            audit_batch_min_inputs(batch, required_min_inputs=args.require_min_inputs)
            if args.summary_json is not None:
                write_readiness_summary_json(
                    args.summary_json,
                    readiness_suite_summary_payload(
                        batch,
                        mode="handoff_manifest_suite",
                        requirements=requirements_payload(args),
                    ),
                )
        except TrinoCompactReadinessInputError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print_suite_result(batch, limit=args.limit)
        return 0 if batch.ok else 1
    overlap_error = reject_summary_output_overlap(
        args.summary_json,
        (*args.boundary_json, args.diagnosis_json, args.smoke_summary),
    )
    if overlap_error:
        print(f"[trino-compact-readiness] rejected: {overlap_error}", file=sys.stderr)
        return 2
    if args.diagnosis_json is not None and len(args.boundary_json) > 1:
        print(
            "[trino-compact-readiness] rejected: diagnosis artifact checking accepts one boundary input",
            file=sys.stderr,
        )
        return 2
    if args.require_diagnosis_json and args.diagnosis_json is None:
        print(
            "[trino-compact-readiness] rejected: --require-diagnosis-json requires --diagnosis-json",
            file=sys.stderr,
        )
        return 2
    if args.smoke_summary is not None and len(args.boundary_json) > 1:
        print(
            "[trino-compact-readiness] rejected: smoke summary checking accepts one boundary input",
            file=sys.stderr,
        )
        return 2
    if args.require_executed_smoke and args.smoke_summary is None:
        print(
            "[trino-compact-readiness] rejected: --require-executed-smoke requires --smoke-summary",
            file=sys.stderr,
        )
        return 2
    if args.require_min_inputs > 1 and len(args.boundary_json) == 1:
        print(
            "[trino-compact-readiness] rejected: --require-min-inputs greater than one requires suite mode",
            file=sys.stderr,
        )
        return 2
    if len(args.boundary_json) > 1:
        batch = audit_boundary_json_suite(
            args.boundary_json,
            required_source_versions=tuple(args.require_source_version),
            require_min_trino_version_families=args.require_min_trino_version_families,
            required_trino_version_families=tuple(args.require_trino_version_family),
            require_supported_attention=args.require_supported_attention,
            fail_on_unknown_parser_coverage=args.fail_on_unknown_parser_coverage,
            require_one_query_boundary=args.require_one_query_boundary,
        )
        audit_batch_min_inputs(batch, required_min_inputs=args.require_min_inputs)
        try:
            if args.summary_json is not None:
                write_readiness_summary_json(
                    args.summary_json,
                    readiness_suite_summary_payload(
                        batch,
                        mode="boundary_json_suite",
                        requirements=requirements_payload(args),
                    ),
                )
        except TrinoCompactReadinessInputError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print_suite_result(batch, limit=args.limit)
        return 0 if batch.ok else 1
    try:
        result = audit_boundary_json(
            args.boundary_json[0],
            diagnosis_json=args.diagnosis_json,
            smoke_summary_json=args.smoke_summary,
            required_source_versions=tuple(args.require_source_version),
            require_executed_smoke=args.require_executed_smoke,
            require_supported_attention=args.require_supported_attention,
            fail_on_unknown_parser_coverage=args.fail_on_unknown_parser_coverage,
            require_one_query_boundary=args.require_one_query_boundary,
        )
        audit_result_version_family_breadth(
            result,
            require_min_trino_version_families=args.require_min_trino_version_families,
            required_trino_version_families=tuple(args.require_trino_version_family),
        )
        if args.summary_json is not None:
            write_readiness_summary_json(
                args.summary_json,
                readiness_summary_payload(
                    result,
                    mode="single_boundary",
                    requirements=requirements_payload(args),
                ),
            )
    except TrinoCompactReadinessInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_result(result, limit=args.limit)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
