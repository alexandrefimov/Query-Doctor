"""Bounded local import for one sanitized Trino metadata summary payload."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from query_doctor.analyzer.engine_facts import (
    EngineFactBundle,
    EngineFactContractError,
    EngineIdentityFacts,
    LimitationFact,
    MetricFact,
    QueryLifecycleFacts,
    engine_fact_boundary_payload,
)
from query_doctor.trino.metadata_source_contract import (
    TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
    TRINO_METADATA_SOURCE_CONTRACT_MAX_BYTES,
    TRINO_METADATA_SOURCE_CONTRACT_MAX_DEPTH,
    TrinoMetadataSourceContractCheckResult,
    load_trino_metadata_source_contract,
)
from query_doctor.trino.source_contract_utils import (
    allowed_text,
    bounded_int,
    mapping_required,
    required_boolean,
    required_literal,
    validate_contract_json_size,
    validate_contract_tree,
    validate_exact_keys,
)


TRINO_LOCAL_METADATA_SUMMARY_IMPORT_SCHEMA_VERSION = "trino_local_metadata_summary_import_v1"
TRINO_LOCAL_METADATA_SUMMARY_IMPORT_SOURCE = "trino_local_metadata_summary_import"
TRINO_METADATA_SUMMARY_VERSION = "trino_metadata_summary_v1"
TRINO_METADATA_SUMMARY_MAX_BYTES = 256 * 1024
TRINO_METADATA_SUMMARY_MAX_DEPTH = 8
TRINO_METADATA_STATS_COMPLETENESS_VALUES = frozenset({"complete", "partial", "absent", "unknown"})
TRINO_METADATA_SUMMARY_TOP_LEVEL_KEYS = frozenset(
    {
        "metadataSummaryVersion",
        "sourceContractVersion",
        "objectAllowlist",
        "metadataCoverage",
        "redaction",
        "limitations",
    }
)
TRINO_METADATA_SUMMARY_OBJECT_ALLOWLIST_KEYS = frozenset(
    {
        "relationCount",
        "explicitColumnCount",
    }
)
TRINO_METADATA_SUMMARY_COVERAGE_KEYS = frozenset(
    {
        "relationsChecked",
        "columnsChecked",
        "columnStatsPresent",
        "columnStatsMissing",
        "statsCompleteness",
    }
)
TRINO_METADATA_SUMMARY_REDACTION_KEYS = frozenset(
    {
        "redactionReviewed",
        "identifierOutput",
        "rawMetadataStorage",
    }
)
TRINO_METADATA_SUMMARY_LIMITATION_LABELS = frozenset(
    {
        "connector_semantics_not_modeled",
        "metadata_values_omitted",
        "not_query_specific",
    }
)
TRINO_METADATA_SUMMARY_REQUIRED_LIMITATIONS = frozenset(
    {
        "metadata_values_omitted",
        "not_query_specific",
    }
)


@dataclass(frozen=True)
class TrinoLocalMetadataSummaryImportResult:
    source_contract: TrinoMetadataSourceContractCheckResult
    metadata_summary_checked: bool
    mapped_to_facts: bool
    parser_coverage: str
    relation_count: int
    explicit_column_count: int
    relations_checked: int
    columns_checked: int
    column_stats_present: int
    column_stats_missing: int
    stats_completeness: str
    bundle: EngineFactBundle


def load_trino_local_metadata_summary_import(
    source_contract_path: Path,
    metadata_summary_path: Path,
    *,
    max_contract_file_bytes: int = TRINO_METADATA_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_bytes: int = TRINO_METADATA_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_depth: int = TRINO_METADATA_SOURCE_CONTRACT_MAX_DEPTH,
    max_metadata_summary_file_bytes: int | None = None,
    max_metadata_summary_depth: int = TRINO_METADATA_SUMMARY_MAX_DEPTH,
) -> TrinoLocalMetadataSummaryImportResult:
    """Validate a local compact metadata summary and map raw-free aggregate facts."""

    source_contract = load_trino_metadata_source_contract(
        source_contract_path,
        max_file_bytes=max_contract_file_bytes,
        max_contract_bytes=max_contract_bytes,
        max_contract_depth=max_contract_depth,
    )
    payload = _read_local_metadata_summary_payload(
        metadata_summary_path,
        max_file_bytes=(
            source_contract.max_metadata_bytes
            if max_metadata_summary_file_bytes is None
            else max_metadata_summary_file_bytes
        ),
        max_metadata_summary_depth=max_metadata_summary_depth,
    )
    return import_trino_local_metadata_summary(source_contract, payload)


def import_trino_local_metadata_summary(
    source_contract: TrinoMetadataSourceContractCheckResult,
    payload: Mapping[str, Any],
) -> TrinoLocalMetadataSummaryImportResult:
    """Map one compact sanitized metadata summary into raw-free aggregate facts."""

    summary = validate_trino_local_metadata_summary_payload(source_contract, payload)
    bundle = build_trino_local_metadata_summary_engine_facts(
        source_contract,
        summary,
    )
    engine_fact_boundary_payload(bundle)
    return TrinoLocalMetadataSummaryImportResult(
        source_contract=source_contract,
        metadata_summary_checked=True,
        mapped_to_facts=True,
        parser_coverage=bundle.identity.parser_coverage,
        relation_count=summary["relation_count"],
        explicit_column_count=summary["explicit_column_count"],
        relations_checked=summary["relations_checked"],
        columns_checked=summary["columns_checked"],
        column_stats_present=summary["column_stats_present"],
        column_stats_missing=summary["column_stats_missing"],
        stats_completeness=summary["stats_completeness"],
        bundle=bundle,
    )


def validate_trino_local_metadata_summary_payload(
    source_contract: TrinoMetadataSourceContractCheckResult,
    payload: Mapping[str, Any],
    *,
    max_metadata_summary_bytes: int = TRINO_METADATA_SUMMARY_MAX_BYTES,
    max_metadata_summary_depth: int = TRINO_METADATA_SUMMARY_MAX_DEPTH,
) -> dict[str, int | str]:
    """Validate compact aggregate metadata summary shape without exposing identifiers."""

    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino local metadata summary import needs a JSON object")
    validate_contract_json_size(
        payload,
        max_contract_bytes=max_metadata_summary_bytes,
        payload_label="Trino local metadata summary",
    )
    validate_contract_tree(
        payload,
        max_depth=max_metadata_summary_depth,
        payload_label="Trino local metadata summary",
    )
    validate_exact_keys(
        payload,
        TRINO_METADATA_SUMMARY_TOP_LEVEL_KEYS,
        "Trino local metadata summary fields are unsupported",
    )
    required_literal(
        payload,
        "metadataSummaryVersion",
        expected=TRINO_METADATA_SUMMARY_VERSION,
        message="Trino local metadata summary version is unsupported",
    )
    required_literal(
        payload,
        "sourceContractVersion",
        expected=TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
        message="Trino local metadata summary source contract version is unsupported",
    )
    if source_contract.metadata_contract_version != TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION:
        raise EngineFactContractError("Trino metadata source contract version is unsupported")

    object_allowlist = mapping_required(payload, "objectAllowlist", "Trino local metadata summary")
    validate_exact_keys(
        object_allowlist,
        TRINO_METADATA_SUMMARY_OBJECT_ALLOWLIST_KEYS,
        "Trino local metadata object allowlist fields are unsupported",
    )
    relation_count = bounded_int(
        object_allowlist,
        "relationCount",
        upper=source_contract.max_relations,
        message="Trino local metadata relation count is out of bounds",
    )
    explicit_column_count = _bounded_zero_count(
        object_allowlist,
        "explicitColumnCount",
        upper=source_contract.max_relations * source_contract.max_columns_per_relation,
        message="Trino local metadata column count is out of bounds",
    )
    if relation_count != source_contract.relation_count:
        raise EngineFactContractError("Trino local metadata relation count does not match contract")
    if explicit_column_count != source_contract.explicit_column_count:
        raise EngineFactContractError("Trino local metadata column count does not match contract")

    coverage = mapping_required(payload, "metadataCoverage", "Trino local metadata summary")
    validate_exact_keys(
        coverage,
        TRINO_METADATA_SUMMARY_COVERAGE_KEYS,
        "Trino local metadata coverage fields are unsupported",
    )
    relations_checked = bounded_int(
        coverage,
        "relationsChecked",
        upper=relation_count,
        message="Trino local metadata relations checked is out of bounds",
    )
    columns_checked = _bounded_zero_count(
        coverage,
        "columnsChecked",
        upper=explicit_column_count,
        message="Trino local metadata columns checked is out of bounds",
    )
    column_stats_present = _bounded_zero_count(
        coverage,
        "columnStatsPresent",
        upper=columns_checked,
        message="Trino local metadata column stats present is out of bounds",
    )
    column_stats_missing = _bounded_zero_count(
        coverage,
        "columnStatsMissing",
        upper=columns_checked,
        message="Trino local metadata column stats missing is out of bounds",
    )
    if column_stats_present + column_stats_missing > columns_checked:
        raise EngineFactContractError("Trino local metadata column stats counts are inconsistent")
    stats_completeness = allowed_text(
        coverage,
        "statsCompleteness",
        allowed=TRINO_METADATA_STATS_COMPLETENESS_VALUES,
        message="Trino local metadata stats completeness is unsupported",
        payload_label="Trino local metadata summary",
    )
    _validate_stats_completeness(
        stats_completeness,
        columns_checked=columns_checked,
        column_stats_present=column_stats_present,
        column_stats_missing=column_stats_missing,
    )

    redaction = mapping_required(payload, "redaction", "Trino local metadata summary")
    validate_exact_keys(
        redaction,
        TRINO_METADATA_SUMMARY_REDACTION_KEYS,
        "Trino local metadata redaction fields are unsupported",
    )
    required_boolean(
        redaction,
        "redactionReviewed",
        expected=True,
        message="Trino local metadata redaction review must be required",
    )
    required_literal(
        redaction,
        "identifierOutput",
        expected="blocked",
        message="Trino local metadata identifier output must be blocked",
    )
    required_literal(
        redaction,
        "rawMetadataStorage",
        expected="forbidden",
        message="Trino local metadata raw metadata storage must be forbidden",
    )

    _validate_limitations(payload.get("limitations"))
    return {
        "relation_count": relation_count,
        "explicit_column_count": explicit_column_count,
        "relations_checked": relations_checked,
        "columns_checked": columns_checked,
        "column_stats_present": column_stats_present,
        "column_stats_missing": column_stats_missing,
        "stats_completeness": stats_completeness,
    }


def build_trino_local_metadata_summary_engine_facts(
    source_contract: TrinoMetadataSourceContractCheckResult,
    summary: Mapping[str, int | str],
) -> EngineFactBundle:
    """Build raw-free aggregate metadata facts from the accepted local summary."""

    return EngineFactBundle(
        identity=EngineIdentityFacts(
            engine="trino",
            source=TRINO_LOCAL_METADATA_SUMMARY_IMPORT_SOURCE,
            source_version=source_contract.metadata_contract_version,
            parser_coverage="supported",
        ),
        lifecycle=QueryLifecycleFacts(
            state="unknown",
            lifecycle="unknown",
            blocked="unknown",
            failure="unknown",
            failure_category_state="unknown",
        ),
        resources=(
            MetricFact(
                fact_id="trino_metadata_summary_import",
                state="supported",
                value=True,
                summary=(
                    "A compact sanitized Trino metadata summary was accepted under an "
                    "explicit metadata source contract."
                ),
            ),
            MetricFact(
                fact_id="trino_metadata_relations_checked",
                state="supported",
                value=summary["relations_checked"],
                unit="relations",
            ),
            MetricFact(
                fact_id="trino_metadata_columns_checked",
                state="supported",
                value=summary["columns_checked"],
                unit="columns",
            ),
            MetricFact(
                fact_id="trino_metadata_column_stats_present_count",
                state="supported",
                value=summary["column_stats_present"],
                unit="columns",
            ),
            MetricFact(
                fact_id="trino_metadata_column_stats_missing_count",
                state="supported",
                value=summary["column_stats_missing"],
                unit="columns",
            ),
            MetricFact(
                fact_id="trino_metadata_stats_completeness",
                state="supported",
                value=summary["stats_completeness"],
            ),
        ),
        limitations=(
            LimitationFact(
                fact_id="source_contract",
                state="supported",
                summary=(
                    "Metadata summary import used an explicit metadata allowlist source "
                    "contract and emitted only aggregate facts."
                ),
            ),
            LimitationFact(
                fact_id="no_live_metadata_collection",
                state="supported",
                summary=(
                    "This metadata summary was imported from an operator-prepared local "
                    "payload; Query Doctor did not read metadata from Trino."
                ),
            ),
            LimitationFact(
                fact_id="no_metadata_identifier_output",
                state="supported",
                summary=(
                    "Relation and column identifiers remain outside normalized facts, "
                    "browser output, and trusted reports."
                ),
            ),
        ),
    )


def trino_local_metadata_summary_import_summary_payload(
    result: TrinoLocalMetadataSummaryImportResult,
) -> dict[str, Any]:
    """Return a path-free and identifier-free metadata summary import result."""

    contract = result.source_contract
    return {
        "schema_version": TRINO_LOCAL_METADATA_SUMMARY_IMPORT_SCHEMA_VERSION,
        "source_type": "local_metadata_summary_import",
        "source_contract": {
            "source_type": contract.source_type,
            "source_contract_version": contract.source_contract_version,
            "metadata_contract_version": contract.metadata_contract_version,
            "auth_reference": {
                "kind": contract.auth_reference_kind,
                "label": contract.auth_reference_label,
            },
        },
        "object_allowlist": {
            "relation_count": result.relation_count,
            "explicit_column_count": result.explicit_column_count,
        },
        "metadata_summary": {
            "metadata_summary_checked": result.metadata_summary_checked,
            "parser_coverage": result.parser_coverage,
            "mapped_to_facts": result.mapped_to_facts,
            "relations_checked": result.relations_checked,
            "columns_checked": result.columns_checked,
            "column_stats_present": result.column_stats_present,
            "column_stats_missing": result.column_stats_missing,
            "stats_completeness": result.stats_completeness,
        },
        "redaction": {
            "raw_metadata_storage": contract.raw_metadata_storage,
            "normalized_fact_storage": contract.normalized_fact_storage,
            "browser_report_output": contract.browser_report_output,
            "identifier_output": contract.identifier_output,
        },
    }


def trino_local_metadata_summary_import_boundary_export(
    result: TrinoLocalMetadataSummaryImportResult,
) -> dict[str, Any]:
    """Return a raw-free normalized fact boundary for one local metadata summary."""

    return {
        "schema_version": TRINO_LOCAL_METADATA_SUMMARY_IMPORT_SCHEMA_VERSION,
        "summary": trino_local_metadata_summary_import_summary_payload(result),
        "metadata_boundary": engine_fact_boundary_payload(result.bundle),
    }


def format_trino_local_metadata_summary_import_summary(
    result: TrinoLocalMetadataSummaryImportResult,
) -> str:
    """Render a path-free and identifier-free metadata summary import result."""

    contract = result.source_contract
    return "\n".join(
        (
            "[trino-metadata-summary] accepted",
            "source_type: local_metadata_summary_import",
            f"source_contract_version: {contract.source_contract_version}",
            f"metadata_contract_version: {contract.metadata_contract_version}",
            f"auth_reference_kind: {contract.auth_reference_kind}",
            f"auth_reference_label: {contract.auth_reference_label}",
            "object_allowlist:",
            f"  relation_count: {result.relation_count}",
            f"  explicit_column_count: {result.explicit_column_count}",
            "metadata_summary:",
            f"  metadata_summary_checked: {result.metadata_summary_checked}",
            f"  parser_coverage: {result.parser_coverage}",
            f"  mapped_to_facts: {result.mapped_to_facts}",
            f"  relations_checked: {result.relations_checked}",
            f"  columns_checked: {result.columns_checked}",
            f"  column_stats_present: {result.column_stats_present}",
            f"  column_stats_missing: {result.column_stats_missing}",
            f"  stats_completeness: {result.stats_completeness}",
            "redaction:",
            f"  raw_metadata_storage: {contract.raw_metadata_storage}",
            f"  normalized_fact_storage: {contract.normalized_fact_storage}",
            f"  browser_report_output: {contract.browser_report_output}",
            f"  identifier_output: {contract.identifier_output}",
        )
    )


def _read_local_metadata_summary_payload(
    path: Path,
    *,
    max_file_bytes: int,
    max_metadata_summary_depth: int,
) -> Mapping[str, Any]:
    if max_file_bytes < 1:
        raise EngineFactContractError("Trino local metadata summary byte limit must be positive")
    if path.stat().st_size > max_file_bytes:
        raise EngineFactContractError("Trino local metadata summary payload is too large")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EngineFactContractError("Trino local metadata summary is not valid JSON") from exc
    if not isinstance(parsed, Mapping):
        raise EngineFactContractError("Trino local metadata summary import needs a JSON object")
    validate_contract_tree(
        parsed,
        max_depth=max_metadata_summary_depth,
        payload_label="Trino local metadata summary",
    )
    return parsed


def _validate_stats_completeness(
    stats_completeness: str,
    *,
    columns_checked: int,
    column_stats_present: int,
    column_stats_missing: int,
) -> None:
    if stats_completeness == "complete" and (
        columns_checked == 0 or column_stats_missing != 0 or column_stats_present != columns_checked
    ):
        raise EngineFactContractError("Trino local metadata stats completeness is inconsistent")
    if stats_completeness == "partial" and (column_stats_present < 1 or column_stats_missing < 1):
        raise EngineFactContractError("Trino local metadata stats completeness is inconsistent")
    if stats_completeness == "absent" and (
        columns_checked == 0 or column_stats_present != 0 or column_stats_missing != columns_checked
    ):
        raise EngineFactContractError("Trino local metadata stats completeness is inconsistent")
    if stats_completeness == "unknown" and (column_stats_present != 0 or column_stats_missing != 0):
        raise EngineFactContractError("Trino local metadata stats completeness is inconsistent")


def _validate_limitations(value: Any) -> None:
    if not isinstance(value, list):
        raise EngineFactContractError("Trino local metadata limitations are unsupported")
    limitation_labels = set()
    for item in value:
        if not isinstance(item, str) or item not in TRINO_METADATA_SUMMARY_LIMITATION_LABELS:
            raise EngineFactContractError("Trino local metadata limitation is unsupported")
        limitation_labels.add(item)
    if not TRINO_METADATA_SUMMARY_REQUIRED_LIMITATIONS.issubset(limitation_labels):
        raise EngineFactContractError("Trino local metadata limitations are incomplete")


def _bounded_zero_count(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    upper: int,
    message: str,
) -> int:
    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise EngineFactContractError(message)
    if value < 0 or value > upper:
        raise EngineFactContractError(message)
    return value
