"""Contract-gated Trino CLI metadata summary builder.

This module is intentionally not wired into Trino product diagnosis paths. It
uses only Python-built metadata statements from an accepted metadata allowlist
contract and emits an aggregate summary compatible with the existing local
metadata summary importer.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.trino.local_metadata_summary import (
    TRINO_METADATA_SUMMARY_VERSION,
    validate_trino_local_metadata_summary_payload,
)
from query_doctor.trino.metadata_source_contract import (
    TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
    TrinoMetadataRelationAllowlist,
    TrinoMetadataSourceContractCheckResult,
)


TRINO_METADATA_CLI_SUMMARY_SCHEMA_VERSION = "trino_metadata_cli_summary_v1"
TRINO_METADATA_CLI_SOURCE_TYPE = "trino_metadata_cli_summary"
TRINO_METADATA_CLI_CONNECTOR_FAMILIES = frozenset({"hive", "iceberg"})
TRINO_METADATA_CLI_OUTPUT_FORMAT = "JSON"
TRINO_METADATA_CLI_STATEMENT_RE = re.compile(
    r"(?:DESCRIBE|SHOW STATS FOR) "
    r"[A-Za-z][A-Za-z0-9_]{0,127}\."
    r"[A-Za-z][A-Za-z0-9_]{0,127}\."
    r"[A-Za-z][A-Za-z0-9_]{0,127}\Z"
)
TRINO_METADATA_CLI_SAFE_USER_RE = re.compile(r"[A-Za-z0-9_.@-]{1,128}\Z")
TRINO_METADATA_CLI_STAT_FIELDS = frozenset(
    {
        "data_size",
        "distinct_values_count",
        "nulls_fraction",
        "low_value",
        "high_value",
    }
)
TRINO_METADATA_CLI_SUMMARY_LIMITATIONS = (
    "metadata_values_omitted",
    "not_query_specific",
    "connector_semantics_not_modeled",
)
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


class TrinoMetadataCliError(ValueError):
    """Raised when the Trino metadata CLI reader cannot safely continue."""


@dataclass(frozen=True)
class TrinoMetadataCliStatement:
    label: str
    kind: str
    relation_index: int
    relation: TrinoMetadataRelationAllowlist
    statement: str


@dataclass(frozen=True)
class TrinoMetadataCliPlan:
    connector_family: str
    relation_count: int
    explicit_column_count: int
    statement_count: int
    statements: tuple[TrinoMetadataCliStatement, ...]


@dataclass(frozen=True)
class TrinoMetadataCliCollectionResult:
    schema_version: str
    summary: dict[str, Any]
    metadata_summary: dict[str, Any]


def build_trino_metadata_cli_plan(
    source_contract: TrinoMetadataSourceContractCheckResult,
    *,
    connector_family: str,
) -> TrinoMetadataCliPlan:
    """Build deterministic metadata statements from an accepted allowlist contract."""

    connector_family = validate_connector_family(connector_family)
    statements: list[TrinoMetadataCliStatement] = []
    for index, relation in enumerate(source_contract.relations, start=1):
        relation_name = _relation_name(relation)
        describe = f"DESCRIBE {relation_name}"
        stats = f"SHOW STATS FOR {relation_name}"
        _validate_metadata_statement(describe)
        _validate_metadata_statement(stats)
        statements.extend(
            (
                TrinoMetadataCliStatement(
                    label=f"relation_{index:03d}_describe",
                    kind="describe_relation",
                    relation_index=index,
                    relation=relation,
                    statement=describe,
                ),
                TrinoMetadataCliStatement(
                    label=f"relation_{index:03d}_stats",
                    kind="show_stats",
                    relation_index=index,
                    relation=relation,
                    statement=stats,
                ),
            )
        )
    return TrinoMetadataCliPlan(
        connector_family=connector_family,
        relation_count=source_contract.relation_count,
        explicit_column_count=source_contract.explicit_column_count,
        statement_count=len(statements),
        statements=tuple(statements),
    )


def collect_trino_metadata_summary(
    source_contract: TrinoMetadataSourceContractCheckResult,
    *,
    trino_cli: str | Path,
    server: str,
    connector_family: str,
    user: str | None = None,
    runner: Runner = subprocess.run,
) -> TrinoMetadataCliCollectionResult:
    """Run the planned metadata statements and emit only aggregate coverage counts."""

    server = validate_trino_cli_server(server)
    if user is not None:
        user = validate_trino_cli_user(user)
    plan = build_trino_metadata_cli_plan(source_contract, connector_family=connector_family)
    argv = build_trino_cli_argv(trino_cli=trino_cli, server=server, user=user)
    total_bytes = 0
    describe_columns: dict[int, set[str]] = {}
    stat_columns_present: dict[int, set[str]] = {}

    for statement in plan.statements:
        stdout = _run_trino_cli_statement(
            argv,
            statement.statement,
            timeout_seconds=source_contract.timeout_seconds,
            runner=runner,
        )
        total_bytes += len(stdout)
        if total_bytes > source_contract.max_metadata_bytes:
            raise TrinoMetadataCliError("Trino metadata CLI output exceeded the configured bound")
        rows = _parse_trino_cli_json_rows(stdout)
        if statement.kind == "describe_relation":
            describe_columns[statement.relation_index] = _describe_column_names(rows)
        elif statement.kind == "show_stats":
            stat_columns_present[statement.relation_index] = _stats_present_columns(rows)
        else:
            raise TrinoMetadataCliError("Trino metadata CLI statement kind is unsupported")

    metadata_summary = _metadata_summary_from_cli_results(
        source_contract,
        describe_columns=describe_columns,
        stat_columns_present=stat_columns_present,
    )
    validate_trino_local_metadata_summary_payload(source_contract, metadata_summary)
    return TrinoMetadataCliCollectionResult(
        schema_version=TRINO_METADATA_CLI_SUMMARY_SCHEMA_VERSION,
        summary=trino_metadata_cli_plan_summary_payload(
            source_contract,
            plan,
            mode="execute",
        ),
        metadata_summary=metadata_summary,
    )


def build_trino_cli_argv(
    *,
    trino_cli: str | Path,
    server: str,
    user: str | None = None,
) -> list[str]:
    """Return argv for Trino CLI execution; statement text is supplied on stdin."""

    server = validate_trino_cli_server(server)
    if user is not None:
        user = validate_trino_cli_user(user)
    argv = [
        str(trino_cli),
        "--server",
        server,
        "--output-format",
        TRINO_METADATA_CLI_OUTPUT_FORMAT,
    ]
    if user is not None:
        argv.extend(["--user", user])
    return argv


def validate_trino_cli_server(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if value != value.strip() or not normalized:
        raise TrinoMetadataCliError("Trino metadata CLI server is unsupported")
    if parsed.scheme != "https" or not parsed.netloc:
        raise TrinoMetadataCliError("Trino metadata CLI server must be an HTTPS URL")
    if parsed.username or parsed.password:
        raise TrinoMetadataCliError("Trino metadata CLI server credentials are unsupported")
    if parsed.params or parsed.query or parsed.fragment:
        raise TrinoMetadataCliError("Trino metadata CLI server shape is unsupported")
    if parsed.path not in {"", "/"}:
        raise TrinoMetadataCliError("Trino metadata CLI server path is unsupported")
    if re.search(r"\s|[;&|`$<>'\"(){}\\]", normalized):
        raise TrinoMetadataCliError("Trino metadata CLI server shape is unsupported")
    return normalized


def validate_trino_cli_user(value: str) -> str:
    normalized = value.strip()
    if not TRINO_METADATA_CLI_SAFE_USER_RE.fullmatch(normalized) or ":" in normalized:
        raise TrinoMetadataCliError("Trino metadata CLI user is unsupported")
    return normalized


def validate_connector_family(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in TRINO_METADATA_CLI_CONNECTOR_FAMILIES:
        allowed = ", ".join(sorted(TRINO_METADATA_CLI_CONNECTOR_FAMILIES))
        raise TrinoMetadataCliError(
            f"Trino metadata CLI connector family is unsupported; allowed: {allowed}"
        )
    return normalized


def trino_metadata_cli_plan_summary_payload(
    source_contract: TrinoMetadataSourceContractCheckResult,
    plan: TrinoMetadataCliPlan,
    *,
    mode: str,
) -> dict[str, Any]:
    """Return a path-free, identifier-free CLI metadata plan summary."""

    return {
        "schema_version": TRINO_METADATA_CLI_SUMMARY_SCHEMA_VERSION,
        "source_type": TRINO_METADATA_CLI_SOURCE_TYPE,
        "mode": mode,
        "connector_family": plan.connector_family,
        "source_contract": {
            "source_type": source_contract.source_type,
            "metadata_contract_version": source_contract.metadata_contract_version,
            "auth_reference": {
                "kind": source_contract.auth_reference_kind,
                "label": source_contract.auth_reference_label,
            },
        },
        "object_allowlist": {
            "relation_count": plan.relation_count,
            "explicit_column_count": plan.explicit_column_count,
            "relation_kind_counts": source_contract.relation_kind_counts,
        },
        "planned_metadata_reads": {
            "statement_count": plan.statement_count,
            "describe_relation_count": sum(
                1 for statement in plan.statements if statement.kind == "describe_relation"
            ),
            "show_stats_count": sum(
                1 for statement in plan.statements if statement.kind == "show_stats"
            ),
            "statement_text": "not_output",
            "object_identifiers": "not_output",
        },
        "bounds": {
            "max_relations": source_contract.max_relations,
            "max_columns_per_relation": source_contract.max_columns_per_relation,
            "max_metadata_bytes": source_contract.max_metadata_bytes,
            "timeout_seconds": source_contract.timeout_seconds,
        },
        "redaction": {
            "raw_metadata_storage": source_contract.raw_metadata_storage,
            "normalized_fact_storage": source_contract.normalized_fact_storage,
            "browser_report_output": source_contract.browser_report_output,
            "identifier_output": source_contract.identifier_output,
        },
        "limitations": [
            "local_operator_cli_only",
            "python_owned_metadata_statement_allowlist_only",
            "not_query_specific",
            "not_a_trino_product_surface",
        ],
    }


def format_trino_metadata_cli_plan_summary(
    source_contract: TrinoMetadataSourceContractCheckResult,
    plan: TrinoMetadataCliPlan,
    *,
    mode: str,
) -> str:
    relation_kind_counts = ", ".join(
        f"{kind}:{count}" for kind, count in source_contract.relation_kind_counts.items()
    )
    if not relation_kind_counts:
        relation_kind_counts = "none"
    verb = "planned" if mode == "dry_run" else "accepted"
    return "\n".join(
        (
            f"[trino-metadata-cli-summary] {verb}",
            f"source_type: {TRINO_METADATA_CLI_SOURCE_TYPE}",
            f"mode: {mode}",
            f"connector_family: {plan.connector_family}",
            f"metadata_contract_version: {source_contract.metadata_contract_version}",
            f"auth_reference_kind: {source_contract.auth_reference_kind}",
            f"auth_reference_label: {source_contract.auth_reference_label}",
            "object_allowlist:",
            f"  relation_count: {plan.relation_count}",
            f"  explicit_column_count: {plan.explicit_column_count}",
            f"  relation_kind_counts: {relation_kind_counts}",
            "planned_metadata_reads:",
            f"  statement_count: {plan.statement_count}",
            "  statement_text: not_output",
            "  object_identifiers: not_output",
            "redaction:",
            f"  raw_metadata_storage: {source_contract.raw_metadata_storage}",
            f"  normalized_fact_storage: {source_contract.normalized_fact_storage}",
            f"  browser_report_output: {source_contract.browser_report_output}",
            f"  identifier_output: {source_contract.identifier_output}",
        )
    )


def format_trino_metadata_cli_collection_summary(
    result: TrinoMetadataCliCollectionResult,
) -> str:
    coverage = result.metadata_summary["metadataCoverage"]
    object_allowlist = result.metadata_summary["objectAllowlist"]
    redaction = result.metadata_summary["redaction"]
    return "\n".join(
        (
            "[trino-metadata-cli-summary] accepted",
            f"source_type: {TRINO_METADATA_CLI_SOURCE_TYPE}",
            "metadata_summary:",
            f"  relation_count: {object_allowlist['relationCount']}",
            f"  explicit_column_count: {object_allowlist['explicitColumnCount']}",
            f"  relations_checked: {coverage['relationsChecked']}",
            f"  columns_checked: {coverage['columnsChecked']}",
            f"  column_stats_present: {coverage['columnStatsPresent']}",
            f"  column_stats_missing: {coverage['columnStatsMissing']}",
            f"  stats_completeness: {coverage['statsCompleteness']}",
            "redaction:",
            f"  raw_metadata_storage: {redaction['rawMetadataStorage']}",
            f"  identifier_output: {redaction['identifierOutput']}",
        )
    )


def metadata_cli_collection_payload(result: TrinoMetadataCliCollectionResult) -> dict[str, Any]:
    """Return the outer raw-free collection summary plus sanitized metadata summary."""

    return {
        "schema_version": result.schema_version,
        "summary": result.summary,
        "metadata_summary": result.metadata_summary,
    }


def _run_trino_cli_statement(
    argv: Sequence[str],
    statement: str,
    *,
    timeout_seconds: int,
    runner: Runner,
) -> bytes:
    try:
        proc = runner(
            list(argv),
            input=(statement + "\n").encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TrinoMetadataCliError("Trino metadata CLI statement timed out") from exc
    except OSError as exc:
        raise TrinoMetadataCliError("Trino metadata CLI could not be started") from exc
    if proc.returncode != 0:
        raise TrinoMetadataCliError("Trino metadata CLI statement failed")
    return proc.stdout or b""


def _parse_trino_cli_json_rows(stdout: bytes) -> tuple[Mapping[str, Any], ...]:
    if not stdout:
        return ()
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TrinoMetadataCliError("Trino metadata CLI output was not UTF-8") from exc
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = _parse_json_lines(text)
    return _rows_from_parsed_json(parsed)


def _parse_json_lines(text: str) -> list[Any]:
    rows: list[Any] = []
    try:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    except json.JSONDecodeError as exc:
        raise TrinoMetadataCliError("Trino metadata CLI output was not safe JSON") from exc
    return rows


def _rows_from_parsed_json(parsed: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(parsed, list):
        rows = parsed
    elif isinstance(parsed, Mapping) and isinstance(parsed.get("data"), list):
        rows = parsed["data"]
    elif isinstance(parsed, Mapping):
        rows = [parsed]
    else:
        raise TrinoMetadataCliError("Trino metadata CLI output shape is unsupported")
    if not all(isinstance(row, Mapping) for row in rows):
        raise TrinoMetadataCliError("Trino metadata CLI row shape is unsupported")
    return tuple(rows)


def _describe_column_names(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    columns: set[str] = set()
    for row in rows:
        column = _first_text_value(row, ("column", "column_name", "column_name_"))
        if column is not None:
            columns.add(column.lower())
    return columns


def _stats_present_columns(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    present: set[str] = set()
    for row in rows:
        column = _first_text_value(row, ("column_name", "column", "column_name_"))
        if column is None:
            continue
        normalized_row = {_normalize_key(key): value for key, value in row.items()}
        if any(
            _has_stats_value(normalized_row.get(field)) for field in TRINO_METADATA_CLI_STAT_FIELDS
        ):
            present.add(column.lower())
    return present


def _first_text_value(row: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    normalized = {_normalize_key(key): value for key, value in row.items()}
    for key in keys:
        value = normalized.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_key(value: object) -> str:
    text = str(value).strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _has_stats_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _metadata_summary_from_cli_results(
    source_contract: TrinoMetadataSourceContractCheckResult,
    *,
    describe_columns: Mapping[int, set[str]],
    stat_columns_present: Mapping[int, set[str]],
) -> dict[str, Any]:
    relations_checked = 0
    columns_checked = 0
    column_stats_present = 0
    for index, relation in enumerate(source_contract.relations, start=1):
        expected_columns = {column.lower() for column in relation.columns}
        described_columns = describe_columns.get(index, set())
        if expected_columns and not expected_columns.issubset(described_columns):
            raise TrinoMetadataCliError("Trino metadata CLI output missed allowlisted columns")
        relations_checked += 1
        columns_checked += len(expected_columns)
        stats_present = stat_columns_present.get(index, set())
        column_stats_present += len(expected_columns.intersection(stats_present))

    column_stats_missing = columns_checked - column_stats_present
    stats_completeness = _stats_completeness(
        columns_checked=columns_checked,
        column_stats_present=column_stats_present,
        column_stats_missing=column_stats_missing,
    )
    return {
        "metadataSummaryVersion": TRINO_METADATA_SUMMARY_VERSION,
        "sourceContractVersion": TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
        "objectAllowlist": {
            "relationCount": source_contract.relation_count,
            "explicitColumnCount": source_contract.explicit_column_count,
        },
        "metadataCoverage": {
            "relationsChecked": relations_checked,
            "columnsChecked": columns_checked,
            "columnStatsPresent": column_stats_present,
            "columnStatsMissing": column_stats_missing,
            "statsCompleteness": stats_completeness,
        },
        "redaction": {
            "redactionReviewed": True,
            "identifierOutput": "blocked",
            "rawMetadataStorage": "forbidden",
        },
        "limitations": list(TRINO_METADATA_CLI_SUMMARY_LIMITATIONS),
    }


def _stats_completeness(
    *,
    columns_checked: int,
    column_stats_present: int,
    column_stats_missing: int,
) -> str:
    if columns_checked == 0:
        return "unknown"
    if column_stats_present == columns_checked and column_stats_missing == 0:
        return "complete"
    if column_stats_present == 0 and column_stats_missing == columns_checked:
        return "absent"
    return "partial"


def _relation_name(relation: TrinoMetadataRelationAllowlist) -> str:
    return f"{relation.catalog}.{relation.schema}.{relation.relation}"


def _validate_metadata_statement(statement: str) -> None:
    if not TRINO_METADATA_CLI_STATEMENT_RE.fullmatch(statement):
        raise TrinoMetadataCliError("Trino metadata CLI statement shape is unsupported")
    if ";" in statement or "--" in statement or "/*" in statement or "*/" in statement:
        raise TrinoMetadataCliError("Trino metadata CLI statement contains unsupported syntax")
