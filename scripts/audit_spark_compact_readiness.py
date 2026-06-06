#!/usr/bin/env python3
"""Audit Spark compact diagnosis readiness without making a support claim."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.analyzer.engine_facts import (  # noqa: E402
    EngineFactBundle,
    EngineFactContractError,
    engine_fact_boundary_payload,
    engine_fact_namespace_definitions,
    validate_engine_fact_bundle_raw_free,
)
from query_doctor.cli.export_spark_evidence_fixtures import (  # noqa: E402
    SPARK_FIXTURE_EXPORT_MANIFEST_VERSION,
)
from query_doctor.report.safety_validation import (  # noqa: E402
    contains_raw_sql_like_text,
    validate_report_internal_fingerprints,
)
from query_doctor.safety import redaction  # noqa: E402
from query_doctor.safety.manifest_references import (  # noqa: E402
    is_safe_relative_json_reference,
)
from query_doctor.spark.diagnosis import (  # noqa: E402
    SPARK_COMPACT_DIAGNOSTIC_LANE_NAME,
    SPARK_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
    SPARK_LANE_GRANULARITY_APPLICATION,
    SPARK_LANE_GRANULARITY_EXACT_SQL,
    SPARK_LANE_GRANULARITY_FIXTURE,
    build_spark_compact_diagnosis,
    safe_fact_state_counts,
    spark_bundle_for_compact_payload,
    spark_lane_evidence_readiness,
    spark_lane_verification_scope,
    spark_source_granularity,
)


EXPECTED_SUPPORT_STATUS = "experimental_compact_intake"
EXPECTED_DIAGNOSIS_BOUNDARY = {
    "root_cause": "not_claimed",
    "details_trusted_report_surface": "not_wired",
    "optimizer_behavior": "not_wired",
    "spark_job_execution": "not_performed",
}
SPARK_COMPACT_READINESS_SUMMARY_VERSION = "spark_compact_readiness_summary_v1"
SPARK_ONE_APPLICATION_HANDOFF_SUMMARY_VERSION = "spark_one_application_handoff_summary_v1"
ACCEPTED_SPARK_SOURCE_CONTRACTS = frozenset(
    {
        "spark_history_eventlog_compact_v1",
        "spark_history_server_compact_v1",
    }
)
ACCEPTED_SPARK_SOURCE_GRANULARITIES = frozenset(
    {
        SPARK_LANE_GRANULARITY_APPLICATION,
        SPARK_LANE_GRANULARITY_EXACT_SQL,
        SPARK_LANE_GRANULARITY_FIXTURE,
    }
)
ACCEPTED_SPARK_VERIFICATION_SCOPES = frozenset(
    {
        "comparable_application_rerun",
        "comparable_sql_execution_rerun",
        "fixture_contract_review",
        "source_contract_review",
        "source_coverage_review",
    }
)
SPARK_ONE_APPLICATION_HANDOFF_SUITE_MANIFEST_KIND = "spark_one_application_handoff_suite_v1"
SPARK_ONE_APPLICATION_HANDOFF_SUITE_MANIFEST_BUILDER_KIND = (
    "spark_one_application_handoff_suite_manifest_builder_v1"
)
REQUIRED_SPARK_LIMITATION_IDS = frozenset(
    {
        "no_product_support",
        "no_browser_report_surface",
        "no_spark_job_execution",
        "no_raw_event_log",
        "structured_streaming_not_modeled",
        "cluster_manager_context",
    }
)
ALLOWED_SPARK_SUPPORT_BOUNDARY_IDS = frozenset(
    {
        "cluster_manager_context",
        "executor_loss",
        "live_history_server_collection",
        "no_browser_report_surface",
        "no_live_history_server_collection",
        "no_product_support",
        "no_raw_event_log",
        "no_spark_job_execution",
        "spark_fixture_import",
        "spark_history_source_coverage",
        "sql_execution_endpoint",
        "task_summary_endpoint",
        "structured_streaming_not_modeled",
    }
)


class SparkCompactReadinessInputError(RuntimeError):
    """Raised when compact JSON cannot be loaded safely."""


@dataclass(frozen=True)
class SparkCompactReadinessIssue:
    category: str
    message: str


@dataclass
class SparkCompactReadinessResult:
    source_contract: str = "unknown"
    spark_version_family: str = "unknown"
    support_status: str = "unknown"
    parser_coverage: str = "unknown"
    lifecycle: str = "unknown"
    fact_count: int = 0
    attention_area_count: int = 0
    supported_attention_area_count: int = 0
    source_warning_count: int = 0
    diagnostic_lane_checked: bool = False
    diagnostic_lane_readiness: str = "unknown"
    diagnostic_lane_source_granularity: str = "unknown"
    diagnostic_lane_verification_scope: str = "unknown"
    source_warning_counts: Counter[str] = field(default_factory=Counter)
    fact_scope_counts: Counter[str] = field(default_factory=Counter)
    fact_state_counts: Counter[str] = field(default_factory=Counter)
    attention_state_counts: Counter[str] = field(default_factory=Counter)
    limitation_state_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[SparkCompactReadinessIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass
class SparkCompactReadinessBatchResult:
    input_count: int = 0
    ok_count: int = 0
    failed_count: int = 0
    fact_count: int = 0
    attention_area_count: int = 0
    supported_attention_area_count: int = 0
    source_warning_count: int = 0
    diagnostic_lane_checked_count: int = 0
    source_warning_counts: Counter[str] = field(default_factory=Counter)
    diagnostic_lane_readiness_counts: Counter[str] = field(default_factory=Counter)
    diagnostic_lane_source_granularity_counts: Counter[str] = field(default_factory=Counter)
    diagnostic_lane_verification_scope_counts: Counter[str] = field(default_factory=Counter)
    source_contract_counts: Counter[str] = field(default_factory=Counter)
    spark_version_family_counts: Counter[str] = field(default_factory=Counter)
    support_status_counts: Counter[str] = field(default_factory=Counter)
    parser_coverage_counts: Counter[str] = field(default_factory=Counter)
    lifecycle_counts: Counter[str] = field(default_factory=Counter)
    fact_scope_counts: Counter[str] = field(default_factory=Counter)
    fact_state_counts: Counter[str] = field(default_factory=Counter)
    attention_state_counts: Counter[str] = field(default_factory=Counter)
    limitation_state_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[tuple[int | None, SparkCompactReadinessIssue]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class SparkFixtureExportManifestSample:
    file_name: str
    source_contract: str


@dataclass(frozen=True)
class SparkOneApplicationHandoffEntry:
    compact_json: Path
    diagnosis_json: Path
    boundary_facts_json: Path
    handoff_summary_json: Path | None = None
    product_surface_summary_json: Path | None = None


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SparkCompactReadinessInputError("compact JSON input could not be read") from exc
    except json.JSONDecodeError as exc:
        raise SparkCompactReadinessInputError("compact JSON input is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise SparkCompactReadinessInputError("compact JSON input must be an object")
    return payload


def audit_compact_json(
    compact_json: Path,
    *,
    require_supported_attention: bool = False,
    fail_on_source_warnings: bool = False,
) -> SparkCompactReadinessResult:
    return audit_compact_payload(
        load_json_object(compact_json),
        require_supported_attention=require_supported_attention,
        fail_on_source_warnings=fail_on_source_warnings,
    )


def audit_compact_json_suite(
    compact_jsons: Iterable[Path],
    *,
    require_supported_attention: bool = False,
    fail_on_source_warnings: bool = False,
    require_min_inputs: int = 1,
    required_source_contracts: Iterable[str] = (),
    require_min_spark_version_families: int = 0,
    required_spark_version_families: Iterable[str] = (),
    required_source_granularities: Iterable[str] = (),
    required_verification_scopes: Iterable[str] = (),
) -> SparkCompactReadinessBatchResult:
    batch = SparkCompactReadinessBatchResult()
    for index, compact_json in enumerate(compact_jsons, start=1):
        batch.input_count += 1
        try:
            result = audit_compact_json(
                compact_json,
                require_supported_attention=require_supported_attention,
                fail_on_source_warnings=fail_on_source_warnings,
            )
        except SparkCompactReadinessInputError:
            issue = SparkCompactReadinessIssue(
                "compact_input_unreadable",
                "One compact JSON input could not be read or parsed safely.",
            )
            batch.failed_count += 1
            batch.issue_counts[issue.category] += 1
            batch.issues.append((index, issue))
            continue
        add_suite_result(batch, index, result)
    audit_suite_breadth(
        batch,
        require_min_inputs=require_min_inputs,
        required_source_contracts=required_source_contracts,
        require_min_spark_version_families=require_min_spark_version_families,
        required_spark_version_families=required_spark_version_families,
        required_source_granularities=required_source_granularities,
        required_verification_scopes=required_verification_scopes,
    )
    return batch


def audit_fixture_export_manifest(
    manifest_path: Path,
    *,
    require_supported_attention: bool = False,
    fail_on_source_warnings: bool = False,
    require_min_inputs: int = 1,
    required_source_contracts: Iterable[str] = (),
    require_min_spark_version_families: int = 0,
    required_spark_version_families: Iterable[str] = (),
    required_source_granularities: Iterable[str] = (),
    required_verification_scopes: Iterable[str] = (),
) -> SparkCompactReadinessBatchResult:
    batch = SparkCompactReadinessBatchResult()
    try:
        manifest = load_json_object(manifest_path)
    except SparkCompactReadinessInputError:
        add_suite_issue(
            batch,
            "fixture_manifest_unreadable",
            "Spark fixture export manifest could not be read or parsed safely.",
        )
        audit_suite_breadth(
            batch,
            require_min_inputs=require_min_inputs,
            required_source_contracts=required_source_contracts,
            require_min_spark_version_families=require_min_spark_version_families,
            required_spark_version_families=required_spark_version_families,
            required_source_granularities=required_source_granularities,
            required_verification_scopes=required_verification_scopes,
        )
        return batch

    samples = validate_fixture_export_manifest(manifest, batch)
    if batch.issues:
        audit_suite_breadth(
            batch,
            require_min_inputs=require_min_inputs,
            required_source_contracts=required_source_contracts,
            require_min_spark_version_families=require_min_spark_version_families,
            required_spark_version_families=required_spark_version_families,
            required_source_granularities=required_source_granularities,
            required_verification_scopes=required_verification_scopes,
        )
        return batch

    for index, sample in enumerate(samples, start=1):
        batch.input_count += 1
        try:
            payload = load_json_object(manifest_path.parent / sample.file_name)
        except SparkCompactReadinessInputError:
            issue = SparkCompactReadinessIssue(
                "compact_input_unreadable",
                "One manifest-listed compact JSON input could not be read or parsed safely.",
            )
            batch.failed_count += 1
            batch.issue_counts[issue.category] += 1
            batch.issues.append((index, issue))
            continue
        result = audit_compact_payload(
            payload,
            require_supported_attention=require_supported_attention,
            fail_on_source_warnings=fail_on_source_warnings,
        )
        if payload.get("sourceContract") != sample.source_contract:
            add_issue(
                result,
                "fixture_manifest_payload_contract_mismatch",
                "Manifest sample source contract must match the compact payload contract.",
            )
        add_suite_result(batch, index, result)
    audit_suite_breadth(
        batch,
        require_min_inputs=require_min_inputs,
        required_source_contracts=required_source_contracts,
        require_min_spark_version_families=require_min_spark_version_families,
        required_spark_version_families=required_spark_version_families,
        required_source_granularities=required_source_granularities,
        required_verification_scopes=required_verification_scopes,
    )
    return batch


def audit_one_application_handoff_manifest(
    manifest_path: Path,
    *,
    require_supported_attention: bool = False,
    fail_on_source_warnings: bool = False,
    require_min_inputs: int = 1,
    required_source_contracts: Iterable[str] = (),
    require_min_spark_version_families: int = 0,
    required_spark_version_families: Iterable[str] = (),
    required_source_granularities: Iterable[str] = (),
    required_verification_scopes: Iterable[str] = (),
) -> SparkCompactReadinessBatchResult:
    batch = SparkCompactReadinessBatchResult()
    try:
        manifest = load_json_object(manifest_path)
    except SparkCompactReadinessInputError:
        add_suite_issue(
            batch,
            "one_application_handoff_manifest_unreadable",
            "Spark one-application handoff manifest could not be read or parsed safely.",
        )
        audit_suite_breadth(
            batch,
            require_min_inputs=require_min_inputs,
            required_source_contracts=required_source_contracts,
            require_min_spark_version_families=require_min_spark_version_families,
            required_spark_version_families=required_spark_version_families,
            required_source_granularities=required_source_granularities,
            required_verification_scopes=required_verification_scopes,
        )
        return batch

    entries = validate_one_application_handoff_manifest(
        manifest,
        batch,
        base_dir=manifest_path.parent,
    )
    if batch.issues:
        audit_suite_breadth(
            batch,
            require_min_inputs=require_min_inputs,
            required_source_contracts=required_source_contracts,
            require_min_spark_version_families=require_min_spark_version_families,
            required_spark_version_families=required_spark_version_families,
            required_source_granularities=required_source_granularities,
            required_verification_scopes=required_verification_scopes,
        )
        return batch

    for index, entry in enumerate(entries, start=1):
        batch.input_count += 1
        try:
            compact_payload = load_json_object(entry.compact_json)
            diagnosis_payload = load_json_object(entry.diagnosis_json)
            boundary_payload = load_json_object(entry.boundary_facts_json)
            summary_payload = (
                load_json_object(entry.handoff_summary_json)
                if entry.handoff_summary_json is not None
                else None
            )
            product_surface_summary_payload = (
                load_json_object(entry.product_surface_summary_json)
                if entry.product_surface_summary_json is not None
                else None
            )
        except SparkCompactReadinessInputError:
            issue = SparkCompactReadinessIssue(
                "one_application_handoff_artifact_unreadable",
                "One manifest-listed Spark one-application handoff artifact could not be read safely.",
            )
            batch.failed_count += 1
            batch.issue_counts[issue.category] += 1
            batch.issues.append((index, issue))
            continue

        result = audit_compact_payload(
            compact_payload,
            require_supported_attention=require_supported_attention,
            fail_on_source_warnings=fail_on_source_warnings,
        )
        audit_one_application_handoff_artifacts(
            result,
            compact_payload=compact_payload,
            diagnosis_payload=diagnosis_payload,
            boundary_payload=boundary_payload,
            summary_payload=summary_payload,
            product_surface_summary_payload=product_surface_summary_payload,
            require_supported_attention=require_supported_attention,
            fail_on_source_warnings=fail_on_source_warnings,
        )
        add_suite_result(batch, index, result)

    audit_suite_breadth(
        batch,
        require_min_inputs=require_min_inputs,
        required_source_contracts=required_source_contracts,
        require_min_spark_version_families=require_min_spark_version_families,
        required_spark_version_families=required_spark_version_families,
        required_source_granularities=required_source_granularities,
        required_verification_scopes=required_verification_scopes,
    )
    return batch


def validate_one_application_handoff_manifest(
    manifest: dict[str, Any],
    batch: SparkCompactReadinessBatchResult,
    *,
    base_dir: Path,
) -> tuple[SparkOneApplicationHandoffEntry, ...]:
    if set(manifest) != {"manifest_kind", "metadata", "entries"}:
        add_suite_issue(
            batch,
            "one_application_handoff_manifest_invalid",
            "Spark one-application handoff manifest must use the safe v1 schema.",
        )
        return ()
    if manifest.get("manifest_kind") != SPARK_ONE_APPLICATION_HANDOFF_SUITE_MANIFEST_KIND:
        add_suite_issue(
            batch,
            "one_application_handoff_manifest_invalid",
            "Spark one-application handoff manifest kind is not accepted.",
        )
        return ()

    metadata = manifest.get("metadata")
    if not isinstance(metadata, Mapping) or set(metadata) != {
        "builder_kind",
        "entry_count",
        "path_reference",
        "redaction_reviewed",
        "limitations",
    }:
        add_suite_issue(
            batch,
            "one_application_handoff_manifest_invalid",
            "Spark one-application handoff manifest metadata is invalid.",
        )
        return ()
    if metadata.get("builder_kind") != SPARK_ONE_APPLICATION_HANDOFF_SUITE_MANIFEST_BUILDER_KIND:
        add_suite_issue(
            batch,
            "one_application_handoff_manifest_invalid",
            "Spark one-application handoff manifest builder kind is not accepted.",
        )
        return ()
    if metadata.get("path_reference") != "relative_to_manifest":
        add_suite_issue(
            batch,
            "one_application_handoff_manifest_invalid",
            "Spark one-application handoff manifest path reference is invalid.",
        )
        return ()
    if metadata.get("redaction_reviewed") is not True:
        add_suite_issue(
            batch,
            "one_application_handoff_manifest_invalid",
            "Spark one-application handoff manifest requires redaction review.",
        )
        return ()
    limitations = metadata.get("limitations")
    if (
        not isinstance(limitations, list)
        or "retained_one_application_artifacts" not in limitations
        or "not_spark_product_support" not in limitations
    ):
        add_suite_issue(
            batch,
            "one_application_handoff_manifest_invalid",
            "Spark one-application handoff manifest limitations are invalid.",
        )
        return ()

    entries = manifest.get("entries")
    if not isinstance(entries, list):
        add_suite_issue(
            batch,
            "one_application_handoff_manifest_invalid",
            "Spark one-application handoff manifest entries must be a list.",
        )
        return ()
    entry_count = metadata.get("entry_count")
    if not isinstance(entry_count, int) or isinstance(entry_count, bool):
        add_suite_issue(
            batch,
            "one_application_handoff_manifest_invalid",
            "Spark one-application handoff manifest entry count must be an integer.",
        )
        return ()
    if entry_count != len(entries):
        add_suite_issue(
            batch,
            "one_application_handoff_manifest_entry_count_mismatch",
            "Spark one-application handoff manifest entry count must match entries.",
        )
        return ()

    parsed_entries: list[SparkOneApplicationHandoffEntry] = []
    seen_refs: set[str] = set()
    for entry in entries:
        if (
            not isinstance(entry, Mapping)
            or not {
                "compact_json",
                "diagnosis_json",
                "boundary_facts_json",
            }.issubset(entry)
            or set(entry)
            - {
                "compact_json",
                "diagnosis_json",
                "boundary_facts_json",
                "handoff_summary_json",
                "product_surface_summary_json",
            }
        ):
            add_suite_issue(
                batch,
                "one_application_handoff_manifest_invalid",
                "Spark one-application handoff manifest entries must use the safe v1 schema.",
            )
            return ()
        refs = (
            entry["compact_json"],
            entry["diagnosis_json"],
            entry["boundary_facts_json"],
            *(() if "handoff_summary_json" not in entry else (entry["handoff_summary_json"],)),
            *(
                ()
                if "product_surface_summary_json" not in entry
                else (entry["product_surface_summary_json"],)
            ),
        )
        if any(not is_safe_relative_json_reference(reference) for reference in refs):
            add_suite_issue(
                batch,
                "one_application_handoff_manifest_invalid",
                "Spark one-application handoff manifest references must be safe relative JSON paths.",
            )
            return ()
        if any(reference in seen_refs for reference in refs):
            add_suite_issue(
                batch,
                "one_application_handoff_manifest_invalid",
                "Spark one-application handoff manifest artifact references must be unique.",
            )
            return ()
        seen_refs.update(str(reference) for reference in refs)
        compact_json = base_dir / str(entry["compact_json"])
        diagnosis_json = base_dir / str(entry["diagnosis_json"])
        boundary_facts_json = base_dir / str(entry["boundary_facts_json"])
        handoff_summary_json = (
            base_dir / str(entry["handoff_summary_json"])
            if "handoff_summary_json" in entry
            else None
        )
        product_surface_summary_json = (
            base_dir / str(entry["product_surface_summary_json"])
            if "product_surface_summary_json" in entry
            else None
        )
        if (
            not compact_json.is_file()
            or not diagnosis_json.is_file()
            or not boundary_facts_json.is_file()
            or (handoff_summary_json is not None and not handoff_summary_json.is_file())
            or (
                product_surface_summary_json is not None
                and not product_surface_summary_json.is_file()
            )
        ):
            add_suite_issue(
                batch,
                "one_application_handoff_manifest_artifact_missing",
                "Spark one-application handoff manifest references unavailable artifacts.",
            )
            return ()
        parsed_entries.append(
            SparkOneApplicationHandoffEntry(
                compact_json=compact_json,
                diagnosis_json=diagnosis_json,
                boundary_facts_json=boundary_facts_json,
                handoff_summary_json=handoff_summary_json,
                product_surface_summary_json=product_surface_summary_json,
            )
        )
    return tuple(parsed_entries)


def validate_fixture_export_manifest(
    manifest: dict[str, Any],
    batch: SparkCompactReadinessBatchResult,
) -> tuple[SparkFixtureExportManifestSample, ...]:
    if set(manifest) != {
        "schema_version",
        "package_id",
        "readiness_status",
        "support_claim",
        "sample_count",
        "samples",
    }:
        add_suite_issue(
            batch,
            "fixture_manifest_invalid",
            "Spark fixture export manifest must use the safe v1 schema.",
        )
        return ()
    if manifest.get("schema_version") != SPARK_FIXTURE_EXPORT_MANIFEST_VERSION:
        add_suite_issue(
            batch,
            "fixture_manifest_invalid",
            "Spark fixture export manifest schema version is not accepted.",
        )
        return ()
    if manifest.get("readiness_status") != "promotion_candidate":
        add_suite_issue(
            batch,
            "fixture_manifest_invalid",
            "Spark fixture export manifest must come from a promotion-candidate package.",
        )
        return ()
    if manifest.get("support_claim") != "not_claimed":
        add_suite_issue(
            batch,
            "fixture_manifest_invalid",
            "Spark fixture export manifest must keep the no-support claim boundary.",
        )
        return ()
    if not is_safe_manifest_label(manifest.get("package_id")):
        add_suite_issue(
            batch,
            "fixture_manifest_invalid",
            "Spark fixture export manifest package label is not safe.",
        )
        return ()

    samples = manifest.get("samples")
    if not isinstance(samples, list):
        add_suite_issue(
            batch,
            "fixture_manifest_invalid",
            "Spark fixture export manifest samples must be a list.",
        )
        return ()
    sample_count = manifest.get("sample_count")
    if not isinstance(sample_count, int) or isinstance(sample_count, bool):
        add_suite_issue(
            batch,
            "fixture_manifest_invalid",
            "Spark fixture export manifest sample count must be an integer.",
        )
        return ()
    if sample_count != len(samples):
        add_suite_issue(
            batch,
            "fixture_manifest_sample_count_mismatch",
            "Spark fixture export manifest sample count must match its sample list.",
        )
        return ()

    parsed_samples: list[SparkFixtureExportManifestSample] = []
    seen_file_names: set[str] = set()
    for sample in samples:
        if not isinstance(sample, dict) or set(sample) != {
            "file_name",
            "case",
            "source_type",
            "source_contract",
        }:
            add_suite_issue(
                batch,
                "fixture_manifest_invalid",
                "Spark fixture export manifest sample entries must use the safe v1 schema.",
            )
            return ()
        file_name = sample["file_name"]
        source_contract = sample["source_contract"]
        if not is_safe_manifest_file_name(file_name):
            add_suite_issue(
                batch,
                "fixture_manifest_invalid",
                "Spark fixture export manifest file names must be safe relative JSON names.",
            )
            return ()
        if file_name in seen_file_names:
            add_suite_issue(
                batch,
                "fixture_manifest_invalid",
                "Spark fixture export manifest file names must be unique.",
            )
            return ()
        if not is_safe_manifest_label(sample["case"]) or not is_safe_manifest_label(
            sample["source_type"]
        ):
            add_suite_issue(
                batch,
                "fixture_manifest_invalid",
                "Spark fixture export manifest sample labels must be safe.",
            )
            return ()
        if source_contract not in ACCEPTED_SPARK_SOURCE_CONTRACTS:
            add_suite_issue(
                batch,
                "fixture_manifest_invalid",
                "Spark fixture export manifest source contracts must be accepted.",
            )
            return ()
        seen_file_names.add(file_name)
        parsed_samples.append(
            SparkFixtureExportManifestSample(
                file_name=file_name,
                source_contract=str(source_contract),
            )
        )
    return tuple(parsed_samples)


def audit_compact_payload(
    payload: dict[str, Any],
    *,
    require_supported_attention: bool = False,
    fail_on_source_warnings: bool = False,
) -> SparkCompactReadinessResult:
    result = SparkCompactReadinessResult(
        source_contract=safe_source_contract(payload),
        spark_version_family=safe_spark_version_family(payload),
    )
    try:
        bundle = spark_bundle_for_compact_payload(payload)
    except EngineFactContractError:
        add_issue(
            result,
            "compact_contract_invalid",
            "Compact Spark payload failed schema or fact validation.",
        )
        return result

    audit_engine_fact_boundary(result, bundle)

    try:
        diagnosis = build_spark_compact_diagnosis(payload)
    except EngineFactContractError:
        add_issue(
            result,
            "compact_diagnosis_invalid",
            "Compact Spark diagnosis could not be built from accepted facts.",
        )
        return result

    audit_diagnosis_boundary(result, diagnosis)
    audit_diagnostic_lane(result, diagnosis, payload=payload)
    audit_diagnosis_raw_free(result, diagnosis)
    if require_supported_attention and result.supported_attention_area_count <= 0:
        add_issue(
            result,
            "missing_supported_attention_area",
            "Strict readiness requires at least one supported Spark attention area.",
        )
    if fail_on_source_warnings and result.source_warning_count:
        add_issue(
            result,
            "spark_source_warning_present",
            "Strict readiness requires Spark compact source warnings to be cleared.",
        )
    return result


def audit_one_application_handoff_artifacts(
    result: SparkCompactReadinessResult,
    *,
    compact_payload: dict[str, Any],
    diagnosis_payload: dict[str, Any],
    boundary_payload: dict[str, Any],
    summary_payload: dict[str, Any] | None,
    product_surface_summary_payload: dict[str, Any] | None,
    require_supported_attention: bool,
    fail_on_source_warnings: bool,
) -> None:
    audit_json_artifact_raw_free(
        result,
        diagnosis_payload,
        category="one_application_handoff_diagnosis_raw_boundary",
        artifact_label="Spark one-application diagnosis artifact",
    )
    audit_json_artifact_raw_free(
        result,
        boundary_payload,
        category="one_application_handoff_boundary_raw_boundary",
        artifact_label="Spark one-application boundary artifact",
    )
    if summary_payload is not None:
        audit_json_artifact_raw_free(
            result,
            summary_payload,
            category="one_application_handoff_summary_raw_boundary",
            artifact_label="Spark one-application summary artifact",
        )
        audit_one_application_handoff_summary(
            result,
            compact_payload=compact_payload,
            summary_payload=summary_payload,
            require_supported_attention=require_supported_attention,
            fail_on_source_warnings=fail_on_source_warnings,
        )
    if product_surface_summary_payload is not None:
        audit_json_artifact_raw_free(
            result,
            product_surface_summary_payload,
            category="one_application_handoff_product_surface_summary_raw_boundary",
            artifact_label="Spark one-application product-surface summary artifact",
        )
    try:
        expected_diagnosis = build_spark_compact_diagnosis(compact_payload)
        expected_boundary = engine_fact_boundary_payload(
            spark_bundle_for_compact_payload(compact_payload)
        )
    except EngineFactContractError:
        return

    if diagnosis_payload != json_normalized_payload(expected_diagnosis):
        add_issue(
            result,
            "one_application_handoff_diagnosis_mismatch",
            "Spark one-application diagnosis artifact must match deterministic compact diagnosis.",
        )
    if boundary_payload != json_normalized_payload(expected_boundary):
        add_issue(
            result,
            "one_application_handoff_boundary_mismatch",
            "Spark one-application boundary artifact must match deterministic engine facts.",
        )


def audit_one_application_handoff_summary(
    result: SparkCompactReadinessResult,
    *,
    compact_payload: dict[str, Any],
    summary_payload: dict[str, Any],
    require_supported_attention: bool,
    fail_on_source_warnings: bool,
) -> None:
    if summary_payload.get("schema_version") != SPARK_ONE_APPLICATION_HANDOFF_SUMMARY_VERSION:
        add_issue(
            result,
            "one_application_handoff_summary_schema_mismatch",
            "Spark one-application summary artifact schema is not accepted.",
        )
    if summary_payload.get("mode") != "one_application_history_server":
        add_issue(
            result,
            "one_application_handoff_summary_schema_mismatch",
            "Spark one-application summary artifact mode is not accepted.",
        )
    if summary_payload.get("status") != "ok":
        add_issue(
            result,
            "one_application_handoff_summary_not_ok",
            "Spark one-application summary artifact must record an ok readiness result.",
        )

    if summary_payload.get("pipeline") != {
        "boundary_facts": "written",
        "collection": "accepted",
        "compact_diagnosis": "accepted",
        "readiness": "ok",
    }:
        add_issue(
            result,
            "one_application_handoff_summary_pipeline_mismatch",
            "Spark one-application summary pipeline must be fully accepted.",
        )

    source_coverage = compact_payload.get("sourceCoverage")
    if not isinstance(source_coverage, Mapping):
        return
    warning_ids = source_coverage.get("warningIds")
    safe_warning_ids = (
        sorted(warning for warning in warning_ids if isinstance(warning, str))
        if isinstance(warning_ids, list)
        else []
    )
    expected_collection = {
        "attempted_endpoint_count": safe_int_or_none(source_coverage.get("attemptedEndpointCount")),
        "successful_endpoint_count": safe_int_or_none(
            source_coverage.get("successfulEndpointCount")
        ),
        "warning_count": len(safe_warning_ids),
        "warning_ids": safe_warning_ids,
    }
    collection = summary_payload.get("collection")
    if collection != expected_collection:
        add_issue(
            result,
            "one_application_handoff_summary_collection_mismatch",
            "Spark one-application summary collection counters must match compact source coverage.",
        )

    if summary_payload.get("artifacts") != {
        "boundary_facts_json": "written",
        "compact_json": "written",
        "diagnosis_json": "written",
        "paths": "not_printed",
    }:
        add_issue(
            result,
            "one_application_handoff_summary_artifact_boundary",
            "Spark one-application summary artifact states must keep the path-free boundary.",
        )

    readiness = summary_payload.get("readiness")
    if not isinstance(readiness, Mapping):
        add_issue(
            result,
            "one_application_handoff_summary_readiness_boundary",
            "Spark one-application summary must include compact readiness evidence.",
        )
        return
    source_contract = compact_payload.get("sourceContract")
    expected_source_contract = source_contract if isinstance(source_contract, str) else "unknown"
    expected_source_contracts = (
        {expected_source_contract: 1} if expected_source_contract != "unknown" else {}
    )
    expected_warning_counts = dict(Counter(safe_warning_ids))
    legacy_requirements = {
        "fail_on_source_warnings": fail_on_source_warnings,
        "require_min_inputs": 1,
        "require_supported_attention": require_supported_attention,
        "required_source_contracts": ["spark_history_server_compact_v1"],
    }
    current_requirements = {
        **legacy_requirements,
        "require_min_spark_version_families": 0,
        "required_spark_version_families": [],
        "required_source_granularities": [],
        "required_verification_scopes": [],
    }
    expected_version_family = safe_spark_version_family(compact_payload)
    expected_version_families = (
        {expected_version_family: 1} if expected_version_family != "unknown" else {}
    )
    if (
        readiness.get("schema_version") != SPARK_COMPACT_READINESS_SUMMARY_VERSION
        or readiness.get("mode") != "one_application_history_server"
        or readiness.get("status") != "ok"
        or readiness.get("boundary") != support_boundary_payload()
        or readiness.get("requirements") not in (legacy_requirements, current_requirements)
        or readiness.get("source_contracts") != expected_source_contracts
        or (
            "spark_version_families" in readiness
            and readiness.get("spark_version_families") != expected_version_families
        )
        or readiness.get("source_warning_counts") != expected_warning_counts
    ):
        add_issue(
            result,
            "one_application_handoff_summary_readiness_boundary",
            "Spark one-application summary readiness evidence must match compact audit requirements.",
        )


def safe_int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def audit_json_artifact_raw_free(
    result: SparkCompactReadinessResult,
    payload: dict[str, Any],
    *,
    category: str,
    artifact_label: str,
) -> None:
    text = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    if contains_raw_sql_like_text(text):
        add_issue(
            result,
            category,
            f"{artifact_label} contains raw SQL-like text.",
        )
    for _violation in validate_report_internal_fingerprints(text):
        add_issue(
            result,
            category,
            f"{artifact_label} contains internal artifact or runtime fingerprints.",
        )
    for label, observed in raw_text_violations(text).items():
        if observed:
            add_issue(
                result,
                category,
                f"{artifact_label} contains raw-like {label} content.",
            )


def json_normalized_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=True, sort_keys=True))


def audit_engine_fact_boundary(
    result: SparkCompactReadinessResult,
    bundle: EngineFactBundle,
) -> None:
    try:
        facts = bundle.facts_by_id()
    except EngineFactContractError:
        add_issue(
            result,
            "engine_fact_contract_invalid",
            "Spark engine fact bundle failed namespace validation.",
        )
        return

    result.parser_coverage = bundle.identity.parser_coverage
    result.lifecycle = bundle.lifecycle.lifecycle
    result.fact_count = len(facts)
    definitions = {
        definition.fact_id: definition for definition in engine_fact_namespace_definitions()
    }

    for fact_id, fact in facts.items():
        definition = definitions.get(fact_id)
        if definition is None:
            result.fact_scope_counts["unregistered"] += 1
            add_issue(
                result,
                "spark_fact_unregistered",
                "Spark compact facts must use registered fact identifiers.",
            )
            continue
        result.fact_scope_counts[definition.scope] += 1
        result.fact_state_counts[fact.state] += 1
        if definition.scope in {"shared", "distributed_sql_family"}:
            add_issue(
                result,
                "spark_fact_promoted_to_shared_scope",
                "Spark compact facts must remain Spark-specific until a separate promotion gate.",
            )
        if definition.scope == "engine_specific" and not fact_id.startswith("spark_"):
            add_issue(
                result,
                "spark_engine_fact_without_prefix",
                "Spark engine-specific facts must keep the spark_ prefix.",
            )
        if (
            definition.scope == "support_boundary"
            and fact_id not in ALLOWED_SPARK_SUPPORT_BOUNDARY_IDS
        ):
            add_issue(
                result,
                "spark_support_boundary_id_unapproved",
                "Spark support-boundary facts must use the approved compact limitation vocabulary.",
            )

    raw_violations = validate_engine_fact_bundle_raw_free(bundle)
    for violation in raw_violations:
        add_issue(
            result,
            "engine_fact_raw_boundary",
            f"Spark engine fact boundary contains raw-like {violation} content.",
        )


def audit_diagnosis_boundary(
    result: SparkCompactReadinessResult,
    diagnosis: dict[str, Any],
) -> None:
    if diagnosis.get("engine") != "spark":
        add_issue(
            result,
            "diagnosis_engine_mismatch",
            "Spark compact diagnosis must stay on engine=spark.",
        )
    result.support_status = str(diagnosis.get("support_status") or "unknown")
    if result.support_status != EXPECTED_SUPPORT_STATUS:
        add_issue(
            result,
            "spark_support_claim_boundary",
            "Spark compact diagnosis must stay experimental and below product support.",
        )

    boundary = diagnosis.get("diagnosis_boundary")
    if not isinstance(boundary, dict):
        add_issue(
            result,
            "missing_diagnosis_boundary",
            "Spark compact diagnosis must publish an explicit no-claim boundary.",
        )
    else:
        for key, expected in EXPECTED_DIAGNOSIS_BOUNDARY.items():
            if boundary.get(key) != expected:
                add_issue(
                    result,
                    "spark_diagnosis_boundary_drift",
                    "Spark compact diagnosis boundary no longer matches the no-claim contract.",
                )

    attention_areas = list_of_mappings(diagnosis.get("attention_areas"))
    result.attention_area_count = len(attention_areas)
    for area in attention_areas:
        state = str(area.get("state") or "unknown")
        result.attention_state_counts[state] += 1
        if state == "supported":
            result.supported_attention_area_count += 1

    limitations = list_of_mappings(diagnosis.get("limitations"))
    limitation_ids: set[str] = set()
    for limitation in limitations:
        limitation_id = str(limitation.get("id") or "")
        if limitation_id:
            limitation_ids.add(limitation_id)
        result.limitation_state_counts[str(limitation.get("state") or "unknown")] += 1
    missing_limitations = REQUIRED_SPARK_LIMITATION_IDS - limitation_ids
    if missing_limitations:
        add_issue(
            result,
            "spark_limitation_boundary_missing",
            "Spark compact diagnosis must keep explicit support and source limitations.",
        )

    source_warnings = diagnosis.get("source_warnings")
    if isinstance(source_warnings, (list, tuple)):
        warning_ids = tuple(
            warning_id for warning_id in source_warnings if isinstance(warning_id, str)
        )
        result.source_warning_count = len(warning_ids)
        result.source_warning_counts.update(warning_ids)


def audit_diagnostic_lane(
    result: SparkCompactReadinessResult,
    diagnosis: dict[str, Any],
    *,
    payload: Mapping[str, Any],
) -> None:
    lane = diagnosis.get("diagnostic_lane")
    if not isinstance(lane, Mapping):
        add_issue(
            result,
            "spark_diagnostic_lane_missing",
            "Spark compact diagnosis must publish a diagnostic-lane contract.",
        )
        return

    result.diagnostic_lane_checked = True
    readiness = lane.get("evidence_readiness")
    result.diagnostic_lane_readiness = readiness if isinstance(readiness, str) else "unknown"
    expected_source_granularity = spark_source_granularity(payload)
    result.diagnostic_lane_source_granularity = expected_source_granularity
    expected_readiness = spark_lane_evidence_readiness(
        parser_coverage=result.parser_coverage,
        source_warning_count=result.source_warning_count,
        supported_attention_area_count=result.supported_attention_area_count,
    )
    expected_verification_scope = spark_lane_verification_scope(
        source_granularity=expected_source_granularity,
        evidence_readiness=expected_readiness,
    )
    result.diagnostic_lane_verification_scope = expected_verification_scope
    expected_values = {
        "schema_version": SPARK_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
        "lane": SPARK_COMPACT_DIAGNOSTIC_LANE_NAME,
        "promotion_status": "preview_only",
        "source_granularity": expected_source_granularity,
        "evidence_readiness": expected_readiness,
        "verification_scope": expected_verification_scope,
        "supported_attention_area_count": result.supported_attention_area_count,
        "source_warning_count": result.source_warning_count,
    }
    for key, expected in expected_values.items():
        if lane.get(key) != expected:
            add_issue(
                result,
                "spark_diagnostic_lane_drift",
                "Spark compact diagnosis diagnostic-lane contract no longer matches boundary evidence.",
            )
            break

    if lane.get("required_gates") != {
        "readiness_audit": "required_for_handoff",
        "surface_audit": "required_before_wiring",
    }:
        add_issue(
            result,
            "spark_diagnostic_lane_gate_drift",
            "Spark compact diagnosis diagnostic-lane required gates must stay explicit.",
        )

    if lane.get("fact_state_counts") != safe_fact_state_counts(result.fact_state_counts):
        add_issue(
            result,
            "spark_diagnostic_lane_state_count_drift",
            "Spark compact diagnosis diagnostic-lane fact-state counts must match boundary evidence.",
        )


def audit_diagnosis_raw_free(
    result: SparkCompactReadinessResult,
    diagnosis: dict[str, Any],
) -> None:
    text = json.dumps(diagnosis, ensure_ascii=True, sort_keys=True)
    if contains_raw_sql_like_text(text):
        add_issue(
            result,
            "diagnosis_raw_boundary",
            "Spark compact diagnosis contains raw SQL-like text.",
        )
    for _violation in validate_report_internal_fingerprints(text):
        add_issue(
            result,
            "diagnosis_raw_boundary",
            "Spark compact diagnosis contains internal artifact or runtime fingerprints.",
        )
    for label, observed in raw_text_violations(text).items():
        if observed:
            add_issue(
                result,
                "diagnosis_raw_boundary",
                f"Spark compact diagnosis contains raw-like {label} content.",
            )


def raw_text_violations(text: str) -> dict[str, bool]:
    return {
        "email": bool(redaction.EMAIL_RE.search(text)),
        "ipv4": bool(redaction.IPV4_RE.search(text)),
        "hostname": bool(redaction.HOSTLIKE_FQDN_RE.search(text)),
        "secret": bool(redaction.SECRET_VALUE_RE.search(text)),
    }


def safe_source_contract(payload: dict[str, Any]) -> str:
    value = payload.get("sourceContract")
    if value in ACCEPTED_SPARK_SOURCE_CONTRACTS:
        return str(value)
    return "unknown"


def safe_spark_version_family(payload: Mapping[str, Any]) -> str:
    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        return "unknown"
    value = provenance.get("sparkVersionFamily")
    if not isinstance(value, str):
        return "unknown"
    if value == "unknown" or (value.startswith("spark_") and value.replace("_", "").isalnum()):
        return value
    return "unknown"


def is_safe_manifest_label(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not value[0].isdigit()
        and value.replace("_", "").isalnum()
    )


def is_safe_manifest_file_name(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith(".json"):
        return False
    if "/" in value or "\\" in value:
        return False
    stem = value.removesuffix(".json")
    if not stem or not stem.replace("_", "").isalnum():
        return False
    path = Path(value)
    return path.name == value and value not in {".json", "..json"}


def list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def add_issue(result: SparkCompactReadinessResult, category: str, message: str) -> None:
    result.issue_counts[category] += 1
    result.issues.append(SparkCompactReadinessIssue(category, message))


def add_suite_result(
    batch: SparkCompactReadinessBatchResult,
    index: int,
    result: SparkCompactReadinessResult,
) -> None:
    if result.ok:
        batch.ok_count += 1
    else:
        batch.failed_count += 1
    batch.fact_count += result.fact_count
    batch.attention_area_count += result.attention_area_count
    batch.supported_attention_area_count += result.supported_attention_area_count
    batch.source_warning_count += result.source_warning_count
    if result.diagnostic_lane_checked:
        batch.diagnostic_lane_checked_count += 1
    batch.source_warning_counts.update(result.source_warning_counts)
    batch.diagnostic_lane_readiness_counts[result.diagnostic_lane_readiness] += 1
    batch.diagnostic_lane_source_granularity_counts[result.diagnostic_lane_source_granularity] += 1
    batch.diagnostic_lane_verification_scope_counts[result.diagnostic_lane_verification_scope] += 1
    batch.source_contract_counts[result.source_contract] += 1
    batch.spark_version_family_counts[result.spark_version_family] += 1
    batch.support_status_counts[result.support_status] += 1
    batch.parser_coverage_counts[result.parser_coverage] += 1
    batch.lifecycle_counts[result.lifecycle] += 1
    batch.fact_scope_counts.update(result.fact_scope_counts)
    batch.fact_state_counts.update(result.fact_state_counts)
    batch.attention_state_counts.update(result.attention_state_counts)
    batch.limitation_state_counts.update(result.limitation_state_counts)
    batch.issue_counts.update(result.issue_counts)
    for issue in result.issues:
        batch.issues.append((index, issue))


def audit_suite_breadth(
    batch: SparkCompactReadinessBatchResult,
    *,
    require_min_inputs: int,
    required_source_contracts: Iterable[str],
    require_min_spark_version_families: int,
    required_spark_version_families: Iterable[str],
    required_source_granularities: Iterable[str],
    required_verification_scopes: Iterable[str],
) -> None:
    if batch.input_count < require_min_inputs:
        add_suite_issue(
            batch,
            "spark_suite_input_count_gap",
            "Strict suite readiness requires more compact inputs.",
        )
    for source_contract in required_source_contracts:
        if batch.source_contract_counts[source_contract] <= 0:
            add_suite_issue(
                batch,
                "spark_suite_source_contract_gap",
                "Strict suite readiness requires each selected source contract to appear.",
            )
    observed_version_families = {
        family
        for family, count in batch.spark_version_family_counts.items()
        if count > 0 and family != "unknown"
    }
    if len(observed_version_families) < require_min_spark_version_families:
        add_suite_issue(
            batch,
            "spark_suite_version_family_gap",
            "Strict suite readiness requires more Spark version-family coverage.",
        )
    for version_family in required_spark_version_families:
        if batch.spark_version_family_counts[version_family] <= 0:
            add_suite_issue(
                batch,
                "spark_suite_version_family_gap",
                "Strict suite readiness requires each selected Spark version family to appear.",
            )
    for source_granularity in required_source_granularities:
        if batch.diagnostic_lane_source_granularity_counts[source_granularity] <= 0:
            add_suite_issue(
                batch,
                "spark_suite_source_granularity_gap",
                "Strict suite readiness requires each selected source granularity to appear.",
            )
    for verification_scope in required_verification_scopes:
        if batch.diagnostic_lane_verification_scope_counts[verification_scope] <= 0:
            add_suite_issue(
                batch,
                "spark_suite_verification_scope_gap",
                "Strict suite readiness requires each selected verification scope to appear.",
            )


def add_suite_issue(
    batch: SparkCompactReadinessBatchResult,
    category: str,
    message: str,
) -> None:
    issue = SparkCompactReadinessIssue(category, message)
    batch.issue_counts[category] += 1
    batch.issues.append((None, issue))


def print_counter(title: str, counter: Counter[str], *, out: TextIO, limit: int) -> None:
    print(f"{title}:", file=out)
    if not counter:
        print("  <none>", file=out)
        return
    for key, count in counter.most_common(limit):
        print(f"  {key}: {count}", file=out)


def print_result(
    result: SparkCompactReadinessResult,
    *,
    out: TextIO | None = None,
    limit: int = 12,
) -> None:
    if out is None:
        out = sys.stdout
    status = "ok" if result.ok else "failed"
    print(f"Spark compact readiness: {status}", file=out)
    print("Input: compact_json", file=out)
    print(
        "Boundary: "
        f"support_status={result.support_status}, "
        "root_cause=not_claimed, "
        "job_execution=not_performed",
        file=out,
    )
    print(
        "Source: "
        f"contract={result.source_contract}, "
        f"spark_version_family={result.spark_version_family}, "
        f"parser_coverage={result.parser_coverage}, "
        f"lifecycle={result.lifecycle}, "
        f"source_warnings={result.source_warning_count}",
        file=out,
    )
    print(
        "Facts: "
        f"total={result.fact_count}, "
        f"attention_areas={result.attention_area_count}, "
        f"supported_attention_areas={result.supported_attention_area_count}",
        file=out,
    )
    print(
        "Diagnostic lane: "
        f"{'checked' if result.diagnostic_lane_checked else 'not_provided'}, "
        f"readiness={result.diagnostic_lane_readiness}, "
        f"source_granularity={result.diagnostic_lane_source_granularity}, "
        f"verification_scope={result.diagnostic_lane_verification_scope}",
        file=out,
    )
    print_counter("Fact scopes", result.fact_scope_counts, out=out, limit=limit)
    print_counter("Fact states", result.fact_state_counts, out=out, limit=limit)
    print_counter("Source warnings", result.source_warning_counts, out=out, limit=limit)
    print_counter("Attention states", result.attention_state_counts, out=out, limit=limit)
    print_counter("Limitation states", result.limitation_state_counts, out=out, limit=limit)
    if result.issues:
        print_counter("Issues", result.issue_counts, out=out, limit=limit)
        print("Issue examples:", file=out)
        for issue in result.issues[:limit]:
            print(f"  {issue.category}: {issue.message}", file=out)
    else:
        print("Issues: none", file=out)


def print_suite_result(
    batch: SparkCompactReadinessBatchResult,
    *,
    out: TextIO | None = None,
    limit: int = 12,
) -> None:
    if out is None:
        out = sys.stdout
    status = "ok" if batch.ok else "failed"
    print(f"Spark compact readiness suite: {status}", file=out)
    print(
        "Inputs: "
        f"compact_json_count={batch.input_count}, "
        f"ok={batch.ok_count}, "
        f"failed={batch.failed_count}",
        file=out,
    )
    print(
        "Totals: "
        f"facts={batch.fact_count}, "
        f"attention_areas={batch.attention_area_count}, "
        f"supported_attention_areas={batch.supported_attention_area_count}, "
        f"source_warnings={batch.source_warning_count}, "
        f"diagnostic_lane_checked={batch.diagnostic_lane_checked_count}",
        file=out,
    )
    print_counter("Source contracts", batch.source_contract_counts, out=out, limit=limit)
    print_counter(
        "Spark version families",
        batch.spark_version_family_counts,
        out=out,
        limit=limit,
    )
    print_counter("Source warnings", batch.source_warning_counts, out=out, limit=limit)
    print_counter("Support statuses", batch.support_status_counts, out=out, limit=limit)
    print_counter("Parser coverage", batch.parser_coverage_counts, out=out, limit=limit)
    print_counter("Lifecycles", batch.lifecycle_counts, out=out, limit=limit)
    print_counter(
        "Diagnostic lane readiness",
        batch.diagnostic_lane_readiness_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Diagnostic lane source granularity",
        batch.diagnostic_lane_source_granularity_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Diagnostic lane verification scope",
        batch.diagnostic_lane_verification_scope_counts,
        out=out,
        limit=limit,
    )
    print_counter("Fact scopes", batch.fact_scope_counts, out=out, limit=limit)
    print_counter("Fact states", batch.fact_state_counts, out=out, limit=limit)
    print_counter("Attention states", batch.attention_state_counts, out=out, limit=limit)
    print_counter("Limitation states", batch.limitation_state_counts, out=out, limit=limit)
    if batch.issues:
        print_counter("Issues", batch.issue_counts, out=out, limit=limit)
        print("Issue examples:", file=out)
        for index, issue in batch.issues[:limit]:
            label = "suite" if index is None else f"input-{index:03d}"
            print(f"  {label}: {issue.category}: {issue.message}", file=out)
    else:
        print("Issues: none", file=out)


def compact_summary_payload(
    result: SparkCompactReadinessResult,
    *,
    mode: str,
    require_supported_attention: bool,
    fail_on_source_warnings: bool,
    required_source_contracts: Iterable[str],
    require_min_spark_version_families: int = 0,
    required_spark_version_families: Iterable[str] = (),
    required_source_granularities: Iterable[str] = (),
    required_verification_scopes: Iterable[str] = (),
) -> dict[str, Any]:
    status = "ok" if result.ok else "failed"
    return {
        "schema_version": SPARK_COMPACT_READINESS_SUMMARY_VERSION,
        "mode": mode,
        "status": status,
        "boundary": support_boundary_payload(),
        "requirements": requirements_payload(
            require_supported_attention=require_supported_attention,
            fail_on_source_warnings=fail_on_source_warnings,
            require_min_inputs=1,
            required_source_contracts=required_source_contracts,
            require_min_spark_version_families=require_min_spark_version_families,
            required_spark_version_families=required_spark_version_families,
            required_source_granularities=required_source_granularities,
            required_verification_scopes=required_verification_scopes,
        ),
        "counts": {
            "compact_json_count": 1,
            "ok_count": 1 if result.ok else 0,
            "failed_count": 0 if result.ok else 1,
            "fact_count": result.fact_count,
            "attention_area_count": result.attention_area_count,
            "supported_attention_area_count": result.supported_attention_area_count,
            "source_warning_count": result.source_warning_count,
            "diagnostic_lane_checked": 1 if result.diagnostic_lane_checked else 0,
        },
        "source_warning_counts": counter_payload(result.source_warning_counts),
        "diagnostic_lane_readiness": counter_payload(
            Counter({result.diagnostic_lane_readiness: 1})
        ),
        "diagnostic_lane_source_granularity": counter_payload(
            Counter({result.diagnostic_lane_source_granularity: 1})
        ),
        "diagnostic_lane_verification_scope": counter_payload(
            Counter({result.diagnostic_lane_verification_scope: 1})
        ),
        "source_contracts": (
            {result.source_contract: 1} if result.source_contract != "unknown" else {}
        ),
        "spark_version_families": (
            {result.spark_version_family: 1} if result.spark_version_family != "unknown" else {}
        ),
        "support_statuses": (
            {result.support_status: 1} if result.support_status != "unknown" else {}
        ),
        "parser_coverage": (
            {result.parser_coverage: 1} if result.parser_coverage != "unknown" else {}
        ),
        "lifecycles": {result.lifecycle: 1} if result.lifecycle != "unknown" else {},
        "fact_scopes": counter_payload(result.fact_scope_counts),
        "fact_states": counter_payload(result.fact_state_counts),
        "attention_states": counter_payload(result.attention_state_counts),
        "limitation_states": counter_payload(result.limitation_state_counts),
        "issues": {
            "counts": counter_payload(result.issue_counts),
            "items": [
                {"input_index": 1, "category": issue.category, "message": issue.message}
                for issue in result.issues
            ],
        },
    }


def suite_summary_payload(
    batch: SparkCompactReadinessBatchResult,
    *,
    mode: str,
    require_supported_attention: bool,
    fail_on_source_warnings: bool,
    require_min_inputs: int,
    required_source_contracts: Iterable[str],
    require_min_spark_version_families: int,
    required_spark_version_families: Iterable[str],
    required_source_granularities: Iterable[str] = (),
    required_verification_scopes: Iterable[str] = (),
) -> dict[str, Any]:
    status = "ok" if batch.ok else "failed"
    return {
        "schema_version": SPARK_COMPACT_READINESS_SUMMARY_VERSION,
        "mode": mode,
        "status": status,
        "boundary": support_boundary_payload(),
        "requirements": requirements_payload(
            require_supported_attention=require_supported_attention,
            fail_on_source_warnings=fail_on_source_warnings,
            require_min_inputs=require_min_inputs,
            required_source_contracts=required_source_contracts,
            require_min_spark_version_families=require_min_spark_version_families,
            required_spark_version_families=required_spark_version_families,
            required_source_granularities=required_source_granularities,
            required_verification_scopes=required_verification_scopes,
        ),
        "counts": {
            "compact_json_count": batch.input_count,
            "ok_count": batch.ok_count,
            "failed_count": batch.failed_count,
            "fact_count": batch.fact_count,
            "attention_area_count": batch.attention_area_count,
            "supported_attention_area_count": batch.supported_attention_area_count,
            "source_warning_count": batch.source_warning_count,
            "diagnostic_lane_checked": batch.diagnostic_lane_checked_count,
        },
        "source_warning_counts": counter_payload(batch.source_warning_counts),
        "diagnostic_lane_readiness": counter_payload(batch.diagnostic_lane_readiness_counts),
        "diagnostic_lane_source_granularity": counter_payload(
            batch.diagnostic_lane_source_granularity_counts
        ),
        "diagnostic_lane_verification_scope": counter_payload(
            batch.diagnostic_lane_verification_scope_counts
        ),
        "source_contracts": counter_payload(batch.source_contract_counts),
        "spark_version_families": counter_payload(batch.spark_version_family_counts),
        "support_statuses": counter_payload(batch.support_status_counts),
        "parser_coverage": counter_payload(batch.parser_coverage_counts),
        "lifecycles": counter_payload(batch.lifecycle_counts),
        "fact_scopes": counter_payload(batch.fact_scope_counts),
        "fact_states": counter_payload(batch.fact_state_counts),
        "attention_states": counter_payload(batch.attention_state_counts),
        "limitation_states": counter_payload(batch.limitation_state_counts),
        "issues": {
            "counts": counter_payload(batch.issue_counts),
            "items": [
                {"input_index": input_index, "category": issue.category, "message": issue.message}
                for input_index, issue in batch.issues
            ],
        },
    }


def support_boundary_payload() -> dict[str, str]:
    return {
        "support_claim": "not_claimed",
        "support_status": EXPECTED_SUPPORT_STATUS,
        "root_cause": "not_claimed",
        "product_surface": "not_wired",
        "spark_job_execution": "not_performed",
    }


def requirements_payload(
    *,
    require_supported_attention: bool,
    fail_on_source_warnings: bool,
    require_min_inputs: int,
    required_source_contracts: Iterable[str],
    require_min_spark_version_families: int,
    required_spark_version_families: Iterable[str],
    required_source_granularities: Iterable[str] = (),
    required_verification_scopes: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "require_supported_attention": require_supported_attention,
        "fail_on_source_warnings": fail_on_source_warnings,
        "require_min_inputs": require_min_inputs,
        "required_source_contracts": sorted(required_source_contracts),
        "require_min_spark_version_families": require_min_spark_version_families,
        "required_spark_version_families": sorted(required_spark_version_families),
        "required_source_granularities": sorted(required_source_granularities),
        "required_verification_scopes": sorted(required_verification_scopes),
    }


def counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: count for key, count in sorted(counter.items()) if count > 0}


def write_summary_or_reject(path: Path | None, payload: Mapping[str, Any]) -> bool:
    if path is None:
        return True
    try:
        write_summary_json(path, payload)
    except SparkCompactReadinessInputError as exc:
        print(f"[spark-compact-readiness] rejected: {exc}", file=sys.stderr)
        return False
    return True


def write_summary_json(path: Path, payload: Mapping[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if contains_raw_sql_like_text(text):
        raise SparkCompactReadinessInputError("summary JSON output would contain raw-like content")
    if validate_report_internal_fingerprints(text):
        raise SparkCompactReadinessInputError("summary JSON output would contain raw-like content")
    if any(raw_text_violations(text).values()):
        raise SparkCompactReadinessInputError("summary JSON output would contain raw-like content")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise SparkCompactReadinessInputError("summary JSON output could not be written") from exc


def reject_summary_output_any_overlap(
    summary_json: Path | None,
    input_paths: Iterable[Path],
) -> str | None:
    if summary_json is None:
        return None
    for input_path in input_paths:
        if same_path(summary_json, input_path):
            return "summary JSON output must differ from every input artifact"
    return None


def fixture_export_manifest_input_paths(manifest_path: Path) -> tuple[Path, ...]:
    input_paths: list[Path] = [manifest_path]
    try:
        manifest = load_json_object(manifest_path)
    except SparkCompactReadinessInputError:
        return tuple(input_paths)
    batch = SparkCompactReadinessBatchResult()
    samples = validate_fixture_export_manifest(manifest, batch)
    if batch.issues:
        return tuple(input_paths)
    input_paths.extend(manifest_path.parent / sample.file_name for sample in samples)
    return tuple(input_paths)


def one_application_handoff_manifest_input_paths(manifest_path: Path) -> tuple[Path, ...]:
    input_paths: list[Path] = [manifest_path]
    try:
        manifest = load_json_object(manifest_path)
    except SparkCompactReadinessInputError:
        return tuple(input_paths)
    batch = SparkCompactReadinessBatchResult()
    entries = validate_one_application_handoff_manifest(
        manifest,
        batch,
        base_dir=manifest_path.parent,
    )
    if batch.issues:
        return tuple(input_paths)
    for entry in entries:
        input_paths.extend((entry.compact_json, entry.diagnosis_json, entry.boundary_facts_json))
        if entry.handoff_summary_json is not None:
            input_paths.append(entry.handoff_summary_json)
        if entry.product_surface_summary_json is not None:
            input_paths.append(entry.product_surface_summary_json)
    return tuple(input_paths)


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def spark_version_family_arg(value: str) -> str:
    if value.startswith("spark_") and value.replace("_", "").isalnum():
        return value
    raise argparse.ArgumentTypeError("Spark version family must be a safe spark_* label")


def spark_verification_scope_arg(value: str) -> str:
    if value in ACCEPTED_SPARK_VERIFICATION_SCOPES:
        return value
    raise argparse.ArgumentTypeError("Spark verification scope must be an accepted safe label")


def spark_source_granularity_arg(value: str) -> str:
    if value in ACCEPTED_SPARK_SOURCE_GRANULARITIES:
        return value
    raise argparse.ArgumentTypeError("Spark source granularity must be an accepted safe label")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "compact_json",
        type=Path,
        nargs="*",
        help="Accepted Spark compact JSON input. Pass multiple paths for suite mode.",
    )
    parser.add_argument(
        "--fixture-export-manifest",
        type=Path,
        help=(
            "Audit the compact JSON files listed by a safe "
            "spark_fixture_export_manifest.json instead of explicit paths."
        ),
    )
    parser.add_argument(
        "--one-application-handoff-suite-manifest",
        type=Path,
        help=(
            "Audit retained raw-free Spark one-application handoff artifacts listed "
            "by a safe spark_one_application_handoff_suite_v1 manifest instead of "
            "explicit compact JSON paths."
        ),
    )
    parser.add_argument("--limit", type=int, default=12, help="Rows to print per section.")
    parser.add_argument(
        "--require-supported-attention",
        action="store_true",
        help="Return non-zero unless the diagnosis contains a supported Spark attention area.",
    )
    parser.add_argument(
        "--fail-on-source-warnings",
        action="store_true",
        help="Return non-zero when compact source warning IDs are present.",
    )
    parser.add_argument(
        "--require-min-inputs",
        type=positive_int,
        default=1,
        help="Require at least this many compact inputs in suite mode.",
    )
    parser.add_argument(
        "--require-source-contract",
        action="append",
        choices=sorted(ACCEPTED_SPARK_SOURCE_CONTRACTS),
        default=None,
        help=(
            "Require the suite to include at least one compact input with this source contract. "
            "May be repeated."
        ),
    )
    parser.add_argument(
        "--require-min-spark-version-families",
        type=positive_int,
        default=0,
        help="Require at least this many non-unknown Spark version-family labels in suite mode.",
    )
    parser.add_argument(
        "--require-spark-version-family",
        action="append",
        type=spark_version_family_arg,
        default=None,
        help=(
            "Require the suite to include at least one compact input with this safe "
            "Spark version-family label, for example spark_2_4. May be repeated."
        ),
    )
    parser.add_argument(
        "--require-verification-scope",
        action="append",
        type=spark_verification_scope_arg,
        default=None,
        help=(
            "Require the suite to include at least one diagnostic-lane verification-scope "
            "counter with this safe label. May be repeated."
        ),
    )
    parser.add_argument(
        "--require-source-granularity",
        action="append",
        type=spark_source_granularity_arg,
        default=None,
        help=(
            "Require the suite to include at least one diagnostic-lane source-granularity "
            "counter with this safe label. May be repeated."
        ),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help=(
            "Optional output path for a raw-free machine-readable compact readiness "
            "summary. The path must differ from every input artifact."
        ),
    )
    args = parser.parse_args(argv)
    selected_input_modes = sum(
        (
            bool(args.compact_json),
            bool(args.fixture_export_manifest),
            bool(args.one_application_handoff_suite_manifest),
        )
    )
    if selected_input_modes != 1:
        parser.error(
            "pass compact JSON paths, --fixture-export-manifest, or "
            "--one-application-handoff-suite-manifest"
        )
    return args


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    required_source_contracts = args.require_source_contract or ()
    required_spark_version_families = args.require_spark_version_family or ()
    required_source_granularities = args.require_source_granularity or ()
    required_verification_scopes = args.require_verification_scope or ()
    if args.fixture_export_manifest:
        overlap_error = reject_summary_output_any_overlap(
            args.summary_json,
            fixture_export_manifest_input_paths(args.fixture_export_manifest),
        )
        if overlap_error:
            print(f"[spark-compact-readiness] rejected: {overlap_error}", file=sys.stderr)
            return 2
        batch = audit_fixture_export_manifest(
            args.fixture_export_manifest,
            require_supported_attention=args.require_supported_attention,
            fail_on_source_warnings=args.fail_on_source_warnings,
            require_min_inputs=args.require_min_inputs,
            required_source_contracts=required_source_contracts,
            require_min_spark_version_families=args.require_min_spark_version_families,
            required_spark_version_families=required_spark_version_families,
            required_source_granularities=required_source_granularities,
            required_verification_scopes=required_verification_scopes,
        )
        if not write_summary_or_reject(
            args.summary_json,
            suite_summary_payload(
                batch,
                mode="fixture_export_manifest",
                require_supported_attention=args.require_supported_attention,
                fail_on_source_warnings=args.fail_on_source_warnings,
                require_min_inputs=args.require_min_inputs,
                required_source_contracts=required_source_contracts,
                require_min_spark_version_families=args.require_min_spark_version_families,
                required_spark_version_families=required_spark_version_families,
                required_source_granularities=required_source_granularities,
                required_verification_scopes=required_verification_scopes,
            ),
        ):
            return 2
        print_suite_result(batch, limit=args.limit)
        return 0 if batch.ok else 1
    if args.one_application_handoff_suite_manifest:
        overlap_error = reject_summary_output_any_overlap(
            args.summary_json,
            one_application_handoff_manifest_input_paths(
                args.one_application_handoff_suite_manifest
            ),
        )
        if overlap_error:
            print(f"[spark-compact-readiness] rejected: {overlap_error}", file=sys.stderr)
            return 2
        batch = audit_one_application_handoff_manifest(
            args.one_application_handoff_suite_manifest,
            require_supported_attention=args.require_supported_attention,
            fail_on_source_warnings=args.fail_on_source_warnings,
            require_min_inputs=args.require_min_inputs,
            required_source_contracts=required_source_contracts,
            require_min_spark_version_families=args.require_min_spark_version_families,
            required_spark_version_families=required_spark_version_families,
            required_source_granularities=required_source_granularities,
            required_verification_scopes=required_verification_scopes,
        )
        if not write_summary_or_reject(
            args.summary_json,
            suite_summary_payload(
                batch,
                mode="one_application_handoff_suite_manifest",
                require_supported_attention=args.require_supported_attention,
                fail_on_source_warnings=args.fail_on_source_warnings,
                require_min_inputs=args.require_min_inputs,
                required_source_contracts=required_source_contracts,
                require_min_spark_version_families=args.require_min_spark_version_families,
                required_spark_version_families=required_spark_version_families,
                required_source_granularities=required_source_granularities,
                required_verification_scopes=required_verification_scopes,
            ),
        ):
            return 2
        print_suite_result(batch, limit=args.limit)
        return 0 if batch.ok else 1
    if (
        len(args.compact_json) > 1
        or args.require_min_inputs > 1
        or required_source_contracts
        or args.require_min_spark_version_families > 1
        or required_spark_version_families
        or required_source_granularities
        or required_verification_scopes
    ):
        overlap_error = reject_summary_output_any_overlap(args.summary_json, args.compact_json)
        if overlap_error:
            print(f"[spark-compact-readiness] rejected: {overlap_error}", file=sys.stderr)
            return 2
        batch = audit_compact_json_suite(
            args.compact_json,
            require_supported_attention=args.require_supported_attention,
            fail_on_source_warnings=args.fail_on_source_warnings,
            require_min_inputs=args.require_min_inputs,
            required_source_contracts=required_source_contracts,
            require_min_spark_version_families=args.require_min_spark_version_families,
            required_spark_version_families=required_spark_version_families,
            required_source_granularities=required_source_granularities,
            required_verification_scopes=required_verification_scopes,
        )
        if not write_summary_or_reject(
            args.summary_json,
            suite_summary_payload(
                batch,
                mode="compact_json_suite",
                require_supported_attention=args.require_supported_attention,
                fail_on_source_warnings=args.fail_on_source_warnings,
                require_min_inputs=args.require_min_inputs,
                required_source_contracts=required_source_contracts,
                require_min_spark_version_families=args.require_min_spark_version_families,
                required_spark_version_families=required_spark_version_families,
                required_source_granularities=required_source_granularities,
                required_verification_scopes=required_verification_scopes,
            ),
        ):
            return 2
        print_suite_result(batch, limit=args.limit)
        return 0 if batch.ok else 1
    overlap_error = reject_summary_output_any_overlap(args.summary_json, args.compact_json)
    if overlap_error:
        print(f"[spark-compact-readiness] rejected: {overlap_error}", file=sys.stderr)
        return 2
    try:
        result = audit_compact_json(
            args.compact_json[0],
            require_supported_attention=args.require_supported_attention,
            fail_on_source_warnings=args.fail_on_source_warnings,
        )
    except SparkCompactReadinessInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if not write_summary_or_reject(
        args.summary_json,
        compact_summary_payload(
            result,
            mode="compact_json",
            require_supported_attention=args.require_supported_attention,
            fail_on_source_warnings=args.fail_on_source_warnings,
            required_source_contracts=required_source_contracts,
            require_min_spark_version_families=args.require_min_spark_version_families,
            required_spark_version_families=required_spark_version_families,
            required_source_granularities=required_source_granularities,
            required_verification_scopes=required_verification_scopes,
        ),
    ):
        return 2
    print_result(result, limit=args.limit)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
