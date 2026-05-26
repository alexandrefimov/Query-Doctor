"""Safe storage-family context derived from analyzer-owned facts."""

from __future__ import annotations

from collections import Counter
from typing import Any


OBJECT_STORE_FAMILIES = {"s3", "adls", "ozone", "object_store"}
KNOWN_STORAGE_FAMILIES = {
    "hdfs",
    "s3",
    "adls",
    "ozone",
    "object_store",
    "local",
}


def build_storage_context(analysis: dict[str, Any]) -> dict[str, Any]:
    tables = table_metadata_rows(analysis)
    families = Counter(table_storage_family(table) for table in tables)
    view_table_count = sum(1 for table in tables if table_object_type(table) == "view")
    known_families = {
        family: count
        for family, count in families.items()
        if family in KNOWN_STORAGE_FAMILIES and count > 0
    }
    observed_locations = sum(known_families.values())
    storage_family = aggregate_storage_family(known_families)
    source = storage_context_source(tables, observed_locations, view_table_count)
    scan_operator_count = scan_operator_count_from_analysis(analysis)
    semantics = storage_semantics(storage_family)

    limitations: list[str] = []
    if not observed_locations:
        limitations.append(
            "No safe table storage location scheme was available from metadata context."
        )
    if tables and view_table_count == len(tables):
        limitations.append(
            "Metadata described views without safe physical storage locations; storage family remains unknown until base-table metadata is collected."
        )
    if storage_family == "mixed":
        limitations.append(
            "Multiple storage families were observed; HDFS locality and object-store semantics must be evaluated per input."
        )
    if storage_family in OBJECT_STORE_FAMILIES:
        limitations.append(
            "Object-store remote reads can be expected and are not HDFS locality evidence."
        )
    if scan_operator_count == 0:
        limitations.append(
            "No timed scan operator context was parsed from the selected query profile."
        )

    return {
        "status": "available" if storage_family != "unknown" else "unknown",
        "storage_family": storage_family,
        "storage_semantics": semantics,
        "source": source,
        "metadata_table_count": len(tables),
        "location_scheme_count": observed_locations,
        "hdfs_location_count": known_families.get("hdfs", 0),
        "object_store_location_count": sum(
            count for family, count in known_families.items() if family in OBJECT_STORE_FAMILIES
        ),
        "local_location_count": known_families.get("local", 0),
        "view_table_count": view_table_count,
        "unknown_table_count": max(0, len(tables) - observed_locations),
        "profile_scan_operator_count": scan_operator_count,
        "profile_scan_observed": scan_operator_count > 0,
        "hdfs_locality_applicable": hdfs_locality_applicable(storage_family),
        "remote_reads_expected": remote_reads_expected(storage_family),
        "guardrail": (
            "Storage context is a safe analyzer summary. It must not expose table locations, "
            "object URIs, paths, credentials, hosts, or daemon identifiers."
        ),
        "limitations": limitations,
    }


def table_metadata_rows(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    context = analysis.get("table_metadata_context")
    context = context if isinstance(context, dict) else {}
    return [table for table in context.get("tables") or [] if isinstance(table, dict)]


def table_storage_family(table: dict[str, Any]) -> str:
    family = str(table.get("storage_family") or "").strip().lower()
    return family if family in KNOWN_STORAGE_FAMILIES else "unknown"


def table_object_type(table: dict[str, Any]) -> str:
    text = str(table.get("object_type") or "").strip().lower()
    return text if text in {"table", "view"} else "unknown"


def aggregate_storage_family(families: dict[str, int]) -> str:
    observed = {family for family, count in families.items() if count > 0}
    if not observed:
        return "unknown"
    if observed == {"hdfs"}:
        return "hdfs"
    if observed == {"local"}:
        return "local"
    if len(observed) == 1:
        return next(iter(observed))
    if observed.issubset(OBJECT_STORE_FAMILIES):
        return "object_store"
    return "mixed"


def storage_context_source(
    tables: list[dict[str, Any]], observed_locations: int, view_table_count: int
) -> str:
    if observed_locations:
        return "table_metadata_location"
    if tables and view_table_count == len(tables):
        return "table_metadata_view_only"
    if tables:
        return "table_metadata_no_location"
    return "unknown"


def scan_operator_count_from_analysis(analysis: dict[str, Any]) -> int:
    operators = analysis.get("operators")
    operators = operators if isinstance(operators, list) else []
    count = 0
    for operator in operators:
        if not isinstance(operator, dict):
            continue
        name = str(operator.get("operator_name") or operator.get("label") or "").lower()
        if "scan" not in name and "hdfs" not in name:
            continue
        try:
            time_ms = float(operator.get("time_ms") or 0)
        except (TypeError, ValueError):
            time_ms = 0.0
        if time_ms > 0:
            count += 1
    return count


def storage_semantics(storage_family: str) -> str:
    if storage_family == "hdfs":
        return "hdfs_locality_applicable"
    if storage_family in OBJECT_STORE_FAMILIES:
        return "object_store_remote_reads_expected"
    if storage_family == "mixed":
        return "mixed_storage_semantics"
    if storage_family == "local":
        return "local_filesystem"
    return "unknown"


def hdfs_locality_applicable(storage_family: str) -> str:
    if storage_family == "hdfs":
        return "yes"
    if storage_family in OBJECT_STORE_FAMILIES or storage_family == "local":
        return "no"
    if storage_family == "mixed":
        return "partial"
    return "unknown"


def remote_reads_expected(storage_family: str) -> str:
    if storage_family in OBJECT_STORE_FAMILIES:
        return "yes"
    if storage_family in {"hdfs", "local"}:
        return "no"
    if storage_family == "mixed":
        return "partial"
    return "unknown"
