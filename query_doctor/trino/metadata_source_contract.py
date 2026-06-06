"""Safe Trino metadata allowlist contract validation for future readers."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.trino.source_contract_utils import (
    allowed_text,
    bounded_int,
    mapping_required,
    required_boolean,
    required_literal,
    required_text,
    safe_source_label,
    validate_contract_json_size,
    validate_contract_tree,
    validate_exact_keys,
)
from query_doctor.trino.source_contract_registry import trino_source_type_for_contract_family


TRINO_METADATA_SOURCE_CONTRACT_CHECK_SCHEMA_VERSION = "trino_metadata_source_contract_check_v1"
TRINO_METADATA_SOURCE_CONTRACT_VERSION = "trino_metadata_source_contract_v1"
TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION = "trino_metadata_allowlist_v1"
TRINO_METADATA_SOURCE_TYPE = trino_source_type_for_contract_family(
    "metadata_source_contract",
    surface_class="metadata_source_contract",
)
TRINO_METADATA_SOURCE_CONTRACT_MAX_BYTES = 32 * 1024
TRINO_METADATA_SOURCE_CONTRACT_MAX_DEPTH = 10
TRINO_METADATA_SOURCE_CONTRACT_MAX_RELATIONS = 100
TRINO_METADATA_SOURCE_CONTRACT_MAX_COLUMNS_PER_RELATION = 200
TRINO_METADATA_SOURCE_CONTRACT_MAX_METADATA_BYTES = 256 * 1024
TRINO_METADATA_SOURCE_CONTRACT_MAX_TIMEOUT_SECONDS = 60
TRINO_METADATA_SOURCE_CONTRACT_MAX_IDENTIFIER_LENGTH = 128
TRINO_METADATA_SOURCE_CONTRACT_TOP_LEVEL_KEYS = frozenset(
    {
        "source_contract_version",
        "source_type",
        "metadata_contract_version",
        "auth_reference",
        "object_allowlist",
        "bounds",
        "redaction",
    }
)
TRINO_METADATA_SOURCE_CONTRACT_AUTH_KEYS = frozenset({"kind", "label"})
TRINO_METADATA_SOURCE_CONTRACT_OBJECT_ALLOWLIST_KEYS = frozenset({"kind", "relations"})
TRINO_METADATA_SOURCE_CONTRACT_RELATION_KEYS = frozenset(
    {"catalog", "schema", "relation", "relation_kind", "columns"}
)
TRINO_METADATA_SOURCE_CONTRACT_BOUNDS_KEYS = frozenset(
    {
        "max_relations",
        "max_columns_per_relation",
        "max_identifier_length",
        "max_metadata_bytes",
        "timeout_seconds",
    }
)
TRINO_METADATA_SOURCE_CONTRACT_REDACTION_KEYS = frozenset(
    {
        "redaction_review_required",
        "raw_metadata_storage",
        "normalized_fact_storage",
        "browser_report_output",
        "identifier_output",
    }
)
TRINO_METADATA_SOURCE_AUTH_KINDS = frozenset(
    {
        "external_secret_reference",
        "kerberos_service_reference",
        "operator_managed_reference",
        "tls_client_certificate_reference",
    }
)
TRINO_METADATA_RELATION_KINDS = frozenset({"table", "view", "materialized_view"})
SAFE_TRINO_IDENTIFIER_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,127}")
TRINO_IDENTIFIER_SQL_WORDS = frozenset(
    {
        "alter",
        "analyze",
        "call",
        "create",
        "delete",
        "describe",
        "drop",
        "execute",
        "explain",
        "from",
        "insert",
        "merge",
        "select",
        "show",
        "table",
        "update",
        "use",
        "where",
        "with",
    }
)


@dataclass(frozen=True)
class TrinoMetadataRelationAllowlist:
    catalog: str
    schema: str
    relation: str
    relation_kind: str
    columns: tuple[str, ...]


@dataclass(frozen=True)
class TrinoMetadataSourceContractCheckResult:
    source_contract_version: str
    source_type: str
    metadata_contract_version: str
    auth_reference_kind: str
    auth_reference_label: str
    object_allowlist_kind: str
    relations: tuple[TrinoMetadataRelationAllowlist, ...]
    max_relations: int
    max_columns_per_relation: int
    max_identifier_length: int
    max_metadata_bytes: int
    timeout_seconds: int
    raw_metadata_storage: str
    normalized_fact_storage: str
    browser_report_output: str
    identifier_output: str

    @property
    def relation_count(self) -> int:
        return len(self.relations)

    @property
    def explicit_column_count(self) -> int:
        return sum(len(relation.columns) for relation in self.relations)

    @property
    def relation_kind_counts(self) -> dict[str, int]:
        counts = Counter(relation.relation_kind for relation in self.relations)
        return {kind: counts[kind] for kind in sorted(counts)}


def load_trino_metadata_source_contract(
    path: Path,
    *,
    max_file_bytes: int = TRINO_METADATA_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_bytes: int = TRINO_METADATA_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_depth: int = TRINO_METADATA_SOURCE_CONTRACT_MAX_DEPTH,
) -> TrinoMetadataSourceContractCheckResult:
    """Read and validate one explicit local Trino metadata allowlist contract JSON."""

    payload = _read_metadata_source_contract_payload(path, max_file_bytes=max_file_bytes)
    return validate_trino_metadata_source_contract_payload(
        payload,
        max_contract_bytes=max_contract_bytes,
        max_contract_depth=max_contract_depth,
    )


def validate_trino_metadata_source_contract_payload(
    payload: Mapping[str, Any],
    *,
    max_contract_bytes: int = TRINO_METADATA_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_depth: int = TRINO_METADATA_SOURCE_CONTRACT_MAX_DEPTH,
) -> TrinoMetadataSourceContractCheckResult:
    """Validate a future Trino metadata allowlist contract without contacting Trino."""

    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino metadata source contract needs a JSON object")
    validate_contract_json_size(
        payload,
        max_contract_bytes=max_contract_bytes,
        payload_label="Trino metadata source contract",
    )
    validate_contract_tree(
        payload,
        max_depth=max_contract_depth,
        payload_label="Trino metadata source contract",
    )
    validate_exact_keys(
        payload,
        TRINO_METADATA_SOURCE_CONTRACT_TOP_LEVEL_KEYS,
        "Trino metadata source contract fields are unsupported",
    )

    source_contract_version = required_text(
        payload,
        "source_contract_version",
        payload_label="Trino metadata source contract",
    )
    if source_contract_version != TRINO_METADATA_SOURCE_CONTRACT_VERSION:
        raise EngineFactContractError("Trino metadata source contract version is unsupported")

    source_type = required_literal(
        payload,
        "source_type",
        expected=TRINO_METADATA_SOURCE_TYPE,
        message="Trino metadata source type is unsupported",
    )
    metadata_contract_version = required_literal(
        payload,
        "metadata_contract_version",
        expected=TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
        message="Trino metadata allowlist contract version is unsupported",
    )

    auth_reference = mapping_required(payload, "auth_reference", "Trino metadata source contract")
    validate_exact_keys(
        auth_reference,
        TRINO_METADATA_SOURCE_CONTRACT_AUTH_KEYS,
        "Trino metadata auth reference fields are unsupported",
    )
    auth_reference_kind = allowed_text(
        auth_reference,
        "kind",
        allowed=TRINO_METADATA_SOURCE_AUTH_KINDS,
        message="Trino metadata auth reference kind is unsupported",
        payload_label="Trino metadata source contract",
    )
    auth_reference_label = safe_source_label(
        auth_reference,
        "label",
        message="Trino metadata auth reference label is not safe",
        payload_label="Trino metadata source contract",
    )

    bounds = mapping_required(payload, "bounds", "Trino metadata source contract")
    validate_exact_keys(
        bounds,
        TRINO_METADATA_SOURCE_CONTRACT_BOUNDS_KEYS,
        "Trino metadata bounds fields are unsupported",
    )
    max_relations = bounded_int(
        bounds,
        "max_relations",
        upper=TRINO_METADATA_SOURCE_CONTRACT_MAX_RELATIONS,
        message="Trino metadata max relations is out of bounds",
    )
    max_columns_per_relation = bounded_int(
        bounds,
        "max_columns_per_relation",
        upper=TRINO_METADATA_SOURCE_CONTRACT_MAX_COLUMNS_PER_RELATION,
        message="Trino metadata max columns per relation is out of bounds",
    )
    max_identifier_length = bounded_int(
        bounds,
        "max_identifier_length",
        upper=TRINO_METADATA_SOURCE_CONTRACT_MAX_IDENTIFIER_LENGTH,
        message="Trino metadata identifier length is out of bounds",
    )
    max_metadata_bytes = bounded_int(
        bounds,
        "max_metadata_bytes",
        upper=TRINO_METADATA_SOURCE_CONTRACT_MAX_METADATA_BYTES,
        message="Trino metadata max bytes is out of bounds",
    )
    timeout_seconds = bounded_int(
        bounds,
        "timeout_seconds",
        upper=TRINO_METADATA_SOURCE_CONTRACT_MAX_TIMEOUT_SECONDS,
        message="Trino metadata timeout is out of bounds",
    )

    object_allowlist = mapping_required(
        payload, "object_allowlist", "Trino metadata source contract"
    )
    validate_exact_keys(
        object_allowlist,
        TRINO_METADATA_SOURCE_CONTRACT_OBJECT_ALLOWLIST_KEYS,
        "Trino metadata object allowlist fields are unsupported",
    )
    object_allowlist_kind = required_literal(
        object_allowlist,
        "kind",
        expected="explicit_relation_identifiers",
        message="Trino metadata object allowlist kind is unsupported",
    )
    relations = _validate_relation_allowlist(
        object_allowlist.get("relations"),
        max_relations=max_relations,
        max_columns_per_relation=max_columns_per_relation,
        max_identifier_length=max_identifier_length,
    )

    redaction_contract = mapping_required(payload, "redaction", "Trino metadata source contract")
    validate_exact_keys(
        redaction_contract,
        TRINO_METADATA_SOURCE_CONTRACT_REDACTION_KEYS,
        "Trino metadata redaction fields are unsupported",
    )
    required_boolean(
        redaction_contract,
        "redaction_review_required",
        expected=True,
        message="Trino metadata redaction review must be required",
    )
    raw_metadata_storage = required_literal(
        redaction_contract,
        "raw_metadata_storage",
        expected="forbidden",
        message="Trino metadata raw metadata storage must be forbidden",
    )
    normalized_fact_storage = required_literal(
        redaction_contract,
        "normalized_fact_storage",
        expected="allowed",
        message="Trino metadata normalized fact storage must be allowed",
    )
    browser_report_output = required_literal(
        redaction_contract,
        "browser_report_output",
        expected="blocked",
        message="Trino metadata browser/report output must be blocked",
    )
    identifier_output = required_literal(
        redaction_contract,
        "identifier_output",
        expected="blocked",
        message="Trino metadata identifier output must be blocked",
    )

    return TrinoMetadataSourceContractCheckResult(
        source_contract_version=source_contract_version,
        source_type=source_type,
        metadata_contract_version=metadata_contract_version,
        auth_reference_kind=auth_reference_kind,
        auth_reference_label=auth_reference_label,
        object_allowlist_kind=object_allowlist_kind,
        relations=relations,
        max_relations=max_relations,
        max_columns_per_relation=max_columns_per_relation,
        max_identifier_length=max_identifier_length,
        max_metadata_bytes=max_metadata_bytes,
        timeout_seconds=timeout_seconds,
        raw_metadata_storage=raw_metadata_storage,
        normalized_fact_storage=normalized_fact_storage,
        browser_report_output=browser_report_output,
        identifier_output=identifier_output,
    )


def trino_metadata_source_contract_summary_payload(
    result: TrinoMetadataSourceContractCheckResult,
) -> dict[str, Any]:
    """Return a path-free, identifier-free metadata source-contract summary."""

    return {
        "schema_version": TRINO_METADATA_SOURCE_CONTRACT_CHECK_SCHEMA_VERSION,
        "source_type": result.source_type,
        "source_contract_version": result.source_contract_version,
        "metadata_contract_version": result.metadata_contract_version,
        "auth_reference": {
            "kind": result.auth_reference_kind,
            "label": result.auth_reference_label,
        },
        "object_allowlist": {
            "kind": result.object_allowlist_kind,
            "relation_count": result.relation_count,
            "explicit_column_count": result.explicit_column_count,
            "relation_kind_counts": result.relation_kind_counts,
        },
        "bounds": {
            "max_relations": result.max_relations,
            "max_columns_per_relation": result.max_columns_per_relation,
            "max_identifier_length": result.max_identifier_length,
            "max_metadata_bytes": result.max_metadata_bytes,
            "timeout_seconds": result.timeout_seconds,
        },
        "redaction": {
            "raw_metadata_storage": result.raw_metadata_storage,
            "normalized_fact_storage": result.normalized_fact_storage,
            "browser_report_output": result.browser_report_output,
            "identifier_output": result.identifier_output,
        },
    }


def format_trino_metadata_source_contract_summary(
    result: TrinoMetadataSourceContractCheckResult,
) -> str:
    """Render a path-free, identifier-free metadata source-contract summary."""

    relation_kind_counts = ", ".join(
        f"{kind}:{count}" for kind, count in result.relation_kind_counts.items()
    )
    if not relation_kind_counts:
        relation_kind_counts = "none"
    return "\n".join(
        (
            "[trino-metadata-source-contract] accepted",
            f"source_type: {result.source_type}",
            f"source_contract_version: {result.source_contract_version}",
            f"metadata_contract_version: {result.metadata_contract_version}",
            f"auth_reference_kind: {result.auth_reference_kind}",
            f"auth_reference_label: {result.auth_reference_label}",
            "object_allowlist:",
            f"  kind: {result.object_allowlist_kind}",
            f"  relation_count: {result.relation_count}",
            f"  explicit_column_count: {result.explicit_column_count}",
            f"  relation_kind_counts: {relation_kind_counts}",
            "bounds:",
            f"  max_relations: {result.max_relations}",
            f"  max_columns_per_relation: {result.max_columns_per_relation}",
            f"  max_identifier_length: {result.max_identifier_length}",
            f"  max_metadata_bytes: {result.max_metadata_bytes}",
            f"  timeout_seconds: {result.timeout_seconds}",
            "redaction:",
            f"  raw_metadata_storage: {result.raw_metadata_storage}",
            f"  normalized_fact_storage: {result.normalized_fact_storage}",
            f"  browser_report_output: {result.browser_report_output}",
            f"  identifier_output: {result.identifier_output}",
        )
    )


def _validate_relation_allowlist(
    value: Any,
    *,
    max_relations: int,
    max_columns_per_relation: int,
    max_identifier_length: int,
) -> tuple[TrinoMetadataRelationAllowlist, ...]:
    if not isinstance(value, list):
        raise EngineFactContractError("Trino metadata relation allowlist is unsupported")
    if not value or len(value) > max_relations:
        raise EngineFactContractError("Trino metadata relation allowlist is out of bounds")

    relations: list[TrinoMetadataRelationAllowlist] = []
    relation_keys: set[tuple[str, str, str]] = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise EngineFactContractError(
                "Trino metadata relation allowlist entries are unsupported"
            )
        validate_exact_keys(
            item,
            TRINO_METADATA_SOURCE_CONTRACT_RELATION_KEYS,
            "Trino metadata relation allowlist fields are unsupported",
        )
        catalog = _safe_identifier(item.get("catalog"), max_identifier_length=max_identifier_length)
        schema = _safe_identifier(item.get("schema"), max_identifier_length=max_identifier_length)
        relation = _safe_identifier(
            item.get("relation"), max_identifier_length=max_identifier_length
        )
        relation_kind = allowed_text(
            item,
            "relation_kind",
            allowed=TRINO_METADATA_RELATION_KINDS,
            message="Trino metadata relation kind is unsupported",
            payload_label="Trino metadata relation allowlist",
        )
        columns = _validate_columns(
            item.get("columns"),
            max_columns_per_relation=max_columns_per_relation,
            max_identifier_length=max_identifier_length,
        )
        relation_key = (catalog.lower(), schema.lower(), relation.lower())
        if relation_key in relation_keys:
            raise EngineFactContractError("Trino metadata relation allowlist has duplicates")
        relation_keys.add(relation_key)
        relations.append(
            TrinoMetadataRelationAllowlist(
                catalog=catalog,
                schema=schema,
                relation=relation,
                relation_kind=relation_kind,
                columns=columns,
            )
        )
    return tuple(relations)


def _validate_columns(
    value: Any,
    *,
    max_columns_per_relation: int,
    max_identifier_length: int,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise EngineFactContractError("Trino metadata column allowlist is unsupported")
    if len(value) > max_columns_per_relation:
        raise EngineFactContractError("Trino metadata column allowlist is out of bounds")
    columns = tuple(
        _safe_identifier(item, max_identifier_length=max_identifier_length) for item in value
    )
    if len({column.lower() for column in columns}) != len(columns):
        raise EngineFactContractError("Trino metadata column allowlist has duplicates")
    return columns


def _safe_identifier(value: Any, *, max_identifier_length: int) -> str:
    if not isinstance(value, str):
        raise EngineFactContractError("Trino metadata identifiers are unsupported")
    identifier = value.strip()
    if (
        not identifier
        or len(identifier) > max_identifier_length
        or not SAFE_TRINO_IDENTIFIER_RE.fullmatch(identifier)
        or identifier.lower() in TRINO_IDENTIFIER_SQL_WORDS
    ):
        raise EngineFactContractError("Trino metadata identifiers are unsupported")
    return identifier


def _read_metadata_source_contract_payload(path: Path, *, max_file_bytes: int) -> Mapping[str, Any]:
    if max_file_bytes < 1:
        raise EngineFactContractError("Trino metadata source contract file limit must be positive")
    if path.stat().st_size > max_file_bytes:
        raise EngineFactContractError("Trino metadata source contract file is too large")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EngineFactContractError("Trino metadata source contract is not valid JSON") from exc
    if not isinstance(parsed, Mapping):
        raise EngineFactContractError("Trino metadata source contract needs a JSON object")
    return parsed
