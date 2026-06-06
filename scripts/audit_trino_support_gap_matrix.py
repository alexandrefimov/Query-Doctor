#!/usr/bin/env python3
"""Audit Trino support-gap coverage without promoting product support."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.analyzer.engine_facts import (  # noqa: E402
    EngineFactDefinition,
    engine_fact_namespace_definitions,
)
from query_doctor.analyzer.engine_fact_promotion_policy import (  # noqa: E402
    ENGINE_FACT_PROMOTION_GATE,
    EngineFactPromotionPolicyEntry,
    engine_fact_promotion_policy_entries,
    promotion_policy_required_for_scope,
    validate_engine_fact_promotion_policy_entry,
)
from query_doctor.analyzer.trino_evidence_package import (  # noqa: E402
    TRINO_EVIDENCE_PACKAGE_SOURCE_TYPES,
    TRINO_EVIDENCE_SAMPLE_SOURCE_TYPES,
)
from query_doctor.engines.capabilities import (  # noqa: E402
    adapter_flags_for_engine,
    product_adapter_flags,
)
from query_doctor.engines import get_engine_adapter  # noqa: E402
from query_doctor.trino.coordinator_query_info_pruned_import import (  # noqa: E402
    TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SOURCE,
)
from query_doctor.trino.coordinator_query_info_target import (  # noqa: E402
    TRINO_COORDINATOR_QUERY_INFO_SOURCE_TYPE,
)
from query_doctor.trino.event_source_contract import TRINO_EVENT_SOURCE_TYPES  # noqa: E402
from query_doctor.trino.http_event_archive import TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE  # noqa: E402
from query_doctor.trino.http_query_detail_archive import (  # noqa: E402
    TRINO_HTTP_QUERY_DETAIL_ARCHIVE_SOURCE_TYPE,
)
from query_doctor.trino.metadata_source_contract import TRINO_METADATA_SOURCE_TYPE  # noqa: E402
from query_doctor.trino.source_contract_registry import (  # noqa: E402
    TRINO_SOURCE_PROMOTION_GATE,
    TrinoSourceContractRegistryEntry,
    trino_source_contract_registry,
)


TRINO_SUPPORT_GAP_SUMMARY_KIND = "trino_support_gap_matrix_audit_v1"
TRINO_SUPPORT_GAP_STATUS = "preview_gaps_pinned"
PRODUCT_ADAPTER_FLAGS = tuple(sorted(product_adapter_flags()))
PREVIEW_ADAPTER_FLAGS = tuple(sorted(adapter_flags_for_engine("trino")))
TRINO_REQUIRED_SOURCE_REGISTRY_TYPES = frozenset(
    {
        *TRINO_EVIDENCE_PACKAGE_SOURCE_TYPES,
        *TRINO_EVIDENCE_SAMPLE_SOURCE_TYPES,
        *TRINO_EVENT_SOURCE_TYPES,
        TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE,
        TRINO_HTTP_QUERY_DETAIL_ARCHIVE_SOURCE_TYPE,
        TRINO_COORDINATOR_QUERY_INFO_SOURCE_TYPE,
        TRINO_METADATA_SOURCE_TYPE,
        "local_event_store_import",
        "local_query_detail_import",
        "local_query_list_import",
        "local_statement_stats_import",
        "local_query_info_pruned_import",
        TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SOURCE,
        "local_metadata_summary_import",
    }
)
TRINO_ALLOWED_SOURCE_REGISTRY_NETWORK_ACCESS = frozenset(
    {
        "not_performed",
        "one_explicit_operator_archive_url",
        "optional_one_explicit_pruned_query_info_request",
        "one_explicit_pruned_query_info_request",
    }
)


@dataclass(frozen=True)
class TrinoSupportGapFamily:
    family_id: str
    status: str
    required_fact_ids: tuple[str, ...] = ()
    required_limitation_fact_ids: tuple[str, ...] = ()
    forbidden_trino_fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrinoSupportGapIssue:
    category: str
    message: str


@dataclass
class TrinoSupportGapAuditResult:
    family_count: int = 0
    required_fact_count: int = 0
    required_limitation_fact_count: int = 0
    trino_allowed_fact_count: int = 0
    preview_adapter_flag_count: int = 0
    blocked_product_adapter_flag_count: int = 0
    source_registry_entry_count: int = 0
    promotion_policy_entry_count: int = 0
    status_counts: Counter[str] = field(default_factory=Counter)
    fact_scope_counts: Counter[str] = field(default_factory=Counter)
    source_registry_surface_counts: Counter[str] = field(default_factory=Counter)
    source_registry_contract_counts: Counter[str] = field(default_factory=Counter)
    promotion_policy_scope_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[tuple[str, TrinoSupportGapIssue]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issue_counts


TRINO_SUPPORT_GAP_FAMILIES = (
    TrinoSupportGapFamily(
        family_id="source_contract_boundaries",
        status="covered_preview_fact",
        required_fact_ids=("source_contract",),
    ),
    TrinoSupportGapFamily(
        family_id="query_lifecycle_and_failure",
        status="covered_preview_fact",
        required_fact_ids=("trino_statement_execution", "trino_blocked_signal"),
    ),
    TrinoSupportGapFamily(
        family_id="timing_and_queue",
        status="covered_preview_fact",
        required_fact_ids=(
            "planning_time_ms",
            "trino_elapsed_time_ms",
            "trino_execution_time_ms",
            "trino_queued_time_ms",
            "trino_resource_group_queue_time_ms",
        ),
        required_limitation_fact_ids=("no_admission_model",),
        forbidden_trino_fact_ids=(
            "admission_result",
            "admission_time_ms",
            "admission_wait_ms",
            "backend_start_time_ms",
        ),
    ),
    TrinoSupportGapFamily(
        family_id="io_memory_and_spill",
        status="covered_preview_fact",
        required_fact_ids=(
            "trino_input_bytes",
            "trino_input_rows",
            "trino_output_bytes",
            "trino_output_rows",
            "trino_peak_memory_bytes",
            "trino_spilled_bytes",
        ),
    ),
    TrinoSupportGapFamily(
        family_id="stage_task_and_skew",
        status="covered_preview_fact",
        required_fact_ids=(
            "trino_stage_count",
            "trino_completed_split_count",
            "trino_task_count",
            "trino_failed_task_count",
            "trino_retried_task_count",
            "trino_stage_skew_candidate",
        ),
        required_limitation_fact_ids=("no_fragment_lifecycle",),
        forbidden_trino_fact_ids=(
            "fragment_instance_count",
            "fragment_instances_per_host_max",
            "fragment_lifecycle_instance_count",
            "fragment_section_count",
        ),
    ),
    TrinoSupportGapFamily(
        family_id="connector_metric_signal",
        status="covered_preview_fact",
        required_fact_ids=("trino_connector_metric_signal",),
    ),
    TrinoSupportGapFamily(
        family_id="query_detail_import",
        status="covered_preview_surface",
        required_fact_ids=("query_detail_fetch", "query_detail_import"),
    ),
    TrinoSupportGapFamily(
        family_id="query_list_aggregate",
        status="aggregate_only",
        required_fact_ids=(
            "query_list_records_seen",
            "query_list_records_summarized",
            "query_list_source_granularity",
        ),
    ),
    TrinoSupportGapFamily(
        family_id="metadata_summary_aggregate",
        status="aggregate_only",
        required_fact_ids=(
            "trino_metadata_summary_import",
            "trino_metadata_relations_checked",
            "trino_metadata_columns_checked",
            "trino_metadata_stats_completeness",
        ),
        required_limitation_fact_ids=(
            "no_live_metadata_collection",
            "no_metadata_identifier_output",
        ),
        forbidden_trino_fact_ids=("metadata_context",),
    ),
    TrinoSupportGapFamily(
        family_id="profile_counter_gap",
        status="product_blocked",
        required_limitation_fact_ids=("no_profile_counters",),
        forbidden_trino_fact_ids=(
            "client_fetch_evidence_tier",
            "impala_profile_json",
            "profile_analysis_support",
            "profile_compatibility",
            "profile_dialect",
            "profile_total_time_ms",
            "runtime_metrics",
        ),
    ),
    TrinoSupportGapFamily(
        family_id="product_surfaces",
        status="product_blocked",
    ),
)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check the Trino support-gap matrix against the registered fact namespace and "
            "engine adapter flags. This preserves preview boundaries and does not promote "
            "Trino to Recent, live Query ID diagnosis, Details, trusted reports, optimizer, "
            "metadata collection, SQL execution, or production support."
        )
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional raw-free machine summary path. The path is never printed.",
    )
    parser.add_argument("--limit", type=positive_int, default=12, help="Maximum issues to print.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    result = audit_trino_support_gap_matrix()
    status = "ok" if result.ok else "failed"
    summary = support_gap_summary_payload(result, status=status)
    if not write_summary_or_reject(args.summary_json, summary):
        return 2

    print(f"Trino support-gap matrix audit: {status}")
    print(
        "Boundary: "
        f"support_gap_status={TRINO_SUPPORT_GAP_STATUS}, "
        "production_support=not_claimed, "
        "product_surfaces=blocked, "
        "trino_sql_execution=not_performed"
    )
    print(f"Families: total={result.family_count}, {counter_text(result.status_counts) or 'none'}")
    print(
        "Adapter: "
        f"preview_flags={result.preview_adapter_flag_count}, "
        f"blocked_product_flags={result.blocked_product_adapter_flag_count}"
    )
    print(
        "Facts: "
        f"trino_allowed={result.trino_allowed_fact_count}, "
        f"required={result.required_fact_count}, "
        f"required_limitations={result.required_limitation_fact_count}"
    )
    print(
        "Source registry: "
        f"entries={result.source_registry_entry_count}, "
        f"surfaces={counter_text(result.source_registry_surface_counts) or 'none'}"
    )
    print(
        "Promotion policy: "
        f"entries={result.promotion_policy_entry_count}, "
        f"scopes={counter_text(result.promotion_policy_scope_counts) or 'none'}"
    )
    print_issues(result, limit=args.limit)
    return 0 if result.ok else 1


def audit_trino_support_gap_matrix(
    *,
    families: Iterable[TrinoSupportGapFamily] = TRINO_SUPPORT_GAP_FAMILIES,
    source_registry: Iterable[TrinoSourceContractRegistryEntry] | None = None,
    promotion_policy: Iterable[EngineFactPromotionPolicyEntry] | None = None,
) -> TrinoSupportGapAuditResult:
    result = TrinoSupportGapAuditResult()
    definitions = {
        definition.fact_id: definition for definition in engine_fact_namespace_definitions()
    }
    for definition in definitions.values():
        if "trino" in definition.allowed_engines:
            result.trino_allowed_fact_count += 1
            result.fact_scope_counts[definition.scope] += 1

    for family in families:
        result.family_count += 1
        result.status_counts[family.status] += 1
        audit_family(result, family, definitions)
    audit_engine_adapters(result)
    audit_source_contract_registry(
        result,
        source_registry=(
            trino_source_contract_registry() if source_registry is None else source_registry
        ),
    )
    audit_engine_fact_promotion_policy(
        result,
        definitions=definitions,
        promotion_policy=(
            engine_fact_promotion_policy_entries() if promotion_policy is None else promotion_policy
        ),
    )
    return result


def audit_family(
    result: TrinoSupportGapAuditResult,
    family: TrinoSupportGapFamily,
    definitions: dict[str, EngineFactDefinition],
) -> None:
    for fact_id in family.required_fact_ids:
        result.required_fact_count += 1
        audit_trino_allowed_fact(result, family.family_id, fact_id, definitions)
    for fact_id in family.required_limitation_fact_ids:
        result.required_limitation_fact_count += 1
        audit_trino_allowed_fact(result, family.family_id, fact_id, definitions)
        if not fact_id.startswith("no_"):
            add_issue(
                result,
                family.family_id,
                "trino_limitation_fact_not_neutral",
                "Trino support gaps must use neutral no_* limitation fact identifiers.",
            )
    for fact_id in family.forbidden_trino_fact_ids:
        definition = definitions.get(fact_id)
        if definition is not None and "trino" in definition.allowed_engines:
            add_issue(
                result,
                family.family_id,
                "trino_forbidden_fact_allowed",
                "A fact reserved for Impala or a blocked product surface is now allowed for Trino.",
            )


def audit_trino_allowed_fact(
    result: TrinoSupportGapAuditResult,
    family_id: str,
    fact_id: str,
    definitions: dict[str, EngineFactDefinition],
) -> None:
    definition = definitions.get(fact_id)
    if definition is None:
        add_issue(
            result,
            family_id,
            "trino_required_fact_missing",
            "A required Trino support-gap fact is not registered.",
        )
        return
    if "trino" not in definition.allowed_engines:
        add_issue(
            result,
            family_id,
            "trino_required_fact_not_allowed",
            "A required Trino support-gap fact is not allowed for Trino.",
        )


def audit_engine_adapters(result: TrinoSupportGapAuditResult) -> None:
    trino = get_engine_adapter("trino")
    impala = get_engine_adapter("impala")
    for flag in PRODUCT_ADAPTER_FLAGS:
        if getattr(impala, flag) is not True:
            add_issue(
                result,
                "product_surfaces",
                "impala_reference_product_flag_changed",
                "Impala must remain the product-support reference for product adapter flags.",
            )
        if getattr(trino, flag) is not False:
            add_issue(
                result,
                "product_surfaces",
                "trino_product_surface_enabled",
                "Trino product adapter flags must stay blocked until support gates close.",
            )
        else:
            result.blocked_product_adapter_flag_count += 1
    for flag in PREVIEW_ADAPTER_FLAGS:
        if getattr(trino, flag) is not True:
            add_issue(
                result,
                "product_surfaces",
                "trino_preview_surface_missing",
                "Trino preview adapter flags must stay registered for bounded raw-free surfaces.",
            )
        else:
            result.preview_adapter_flag_count += 1


def audit_source_contract_registry(
    result: TrinoSupportGapAuditResult,
    *,
    source_registry: Iterable[TrinoSourceContractRegistryEntry],
) -> None:
    entries_by_type: dict[str, TrinoSourceContractRegistryEntry] = {}
    for entry in source_registry:
        result.source_registry_entry_count += 1
        result.source_registry_surface_counts[entry.surface_class] += 1
        result.source_registry_contract_counts[entry.contract_family] += 1
        if entry.source_type in entries_by_type:
            add_issue(
                result,
                "source_contract_registry",
                "trino_source_registry_duplicate_type",
                "A Trino source type is registered more than once.",
            )
        entries_by_type[entry.source_type] = entry
        audit_source_contract_registry_entry(result, entry)

    registered_types = frozenset(entries_by_type)
    missing_types = TRINO_REQUIRED_SOURCE_REGISTRY_TYPES - registered_types
    if missing_types:
        add_issue(
            result,
            "source_contract_registry",
            "trino_source_registry_missing_type",
            "A Trino preview source type is not represented in the source registry.",
        )
    unexpected_types = registered_types - TRINO_REQUIRED_SOURCE_REGISTRY_TYPES
    if unexpected_types:
        add_issue(
            result,
            "source_contract_registry",
            "trino_source_registry_unexpected_type",
            "The Trino source registry contains a source type outside implemented preview lanes.",
        )


def audit_source_contract_registry_entry(
    result: TrinoSupportGapAuditResult,
    entry: TrinoSourceContractRegistryEntry,
) -> None:
    if not entry.required_bounds:
        add_issue(
            result,
            "source_contract_registry",
            "trino_source_registry_missing_bounds",
            "A Trino source registry entry must name its enforcing bounds.",
        )
    if entry.network_access not in TRINO_ALLOWED_SOURCE_REGISTRY_NETWORK_ACCESS:
        add_issue(
            result,
            "source_contract_registry",
            "trino_source_registry_network_access_unsupported",
            "A Trino source registry entry uses an unsupported network-access class.",
        )
    if entry.product_surfaces != "blocked":
        add_issue(
            result,
            "source_contract_registry",
            "trino_source_registry_product_surface_enabled",
            "Trino source registry entries must not enable product surfaces.",
        )
    if entry.details_report_output != "blocked":
        add_issue(
            result,
            "source_contract_registry",
            "trino_source_registry_details_output_enabled",
            "Trino source registry entries must not enable Details or trusted report output.",
        )
    if entry.recent_scan != "blocked":
        add_issue(
            result,
            "source_contract_registry",
            "trino_source_registry_recent_enabled",
            "Trino source registry entries must not enable Recent scans.",
        )
    if entry.optimizer_behavior != "blocked":
        add_issue(
            result,
            "source_contract_registry",
            "trino_source_registry_optimizer_enabled",
            "Trino source registry entries must not enable optimizer behavior.",
        )
    if entry.sql_execution != "not_performed":
        add_issue(
            result,
            "source_contract_registry",
            "trino_source_registry_sql_execution_enabled",
            "Trino source registry entries must not perform SQL execution.",
        )
    if entry.browser_report_output != "blocked":
        add_issue(
            result,
            "source_contract_registry",
            "trino_source_registry_browser_output_enabled",
            "Trino source registry entries must block browser and report output.",
        )
    if entry.raw_payload_storage != "forbidden" and entry.raw_metadata_storage != "forbidden":
        add_issue(
            result,
            "source_contract_registry",
            "trino_source_registry_raw_storage_enabled",
            "Trino source registry entries must forbid raw payload or raw metadata storage.",
        )
    if entry.raw_metadata_storage == "forbidden" and entry.identifier_output != "blocked":
        add_issue(
            result,
            "source_contract_registry",
            "trino_source_registry_identifier_output_enabled",
            "Trino metadata source registry entries must block identifier output.",
        )
    if entry.promotion_gate != TRINO_SOURCE_PROMOTION_GATE:
        add_issue(
            result,
            "source_contract_registry",
            "trino_source_registry_promotion_gate_missing",
            "Trino source registry entries must keep the explicit preview promotion gate.",
        )


def audit_engine_fact_promotion_policy(
    result: TrinoSupportGapAuditResult,
    *,
    definitions: dict[str, EngineFactDefinition],
    promotion_policy: Iterable[EngineFactPromotionPolicyEntry],
) -> None:
    policy_by_id: dict[str, EngineFactPromotionPolicyEntry] = {}
    for entry in promotion_policy:
        result.promotion_policy_entry_count += 1
        result.promotion_policy_scope_counts[entry.scope] += 1
        if entry.fact_id in policy_by_id:
            add_issue(
                result,
                "engine_fact_promotion_policy",
                "engine_fact_promotion_policy_duplicate",
                "A normalized engine fact promotion policy entry is duplicated.",
            )
        policy_by_id[entry.fact_id] = entry
        audit_engine_fact_promotion_policy_entry(result, entry, definitions)

    for fact_id, definition in definitions.items():
        if "trino" not in definition.allowed_engines:
            continue
        if not promotion_policy_required_for_scope(definition.scope):
            continue
        if fact_id not in policy_by_id:
            add_issue(
                result,
                "engine_fact_promotion_policy",
                "engine_fact_promotion_policy_missing",
                "A Trino-visible cross-engine normalized fact lacks promotion policy.",
            )


def audit_engine_fact_promotion_policy_entry(
    result: TrinoSupportGapAuditResult,
    entry: EngineFactPromotionPolicyEntry,
    definitions: dict[str, EngineFactDefinition],
) -> None:
    for issue in validate_engine_fact_promotion_policy_entry(entry):
        add_issue(
            result,
            "engine_fact_promotion_policy",
            f"engine_fact_{issue}",
            "A normalized engine fact promotion policy entry is unsafe or incomplete.",
        )

    definition = definitions.get(entry.fact_id)
    if definition is None:
        add_issue(
            result,
            "engine_fact_promotion_policy",
            "engine_fact_promotion_policy_unknown_fact",
            "A normalized engine fact promotion policy references an unregistered fact.",
        )
        return
    if entry.scope != definition.scope:
        add_issue(
            result,
            "engine_fact_promotion_policy",
            "engine_fact_promotion_policy_scope_mismatch",
            "A normalized engine fact promotion policy scope differs from the fact registry.",
        )
    if entry.allowed_engines != definition.allowed_engines:
        add_issue(
            result,
            "engine_fact_promotion_policy",
            "engine_fact_promotion_policy_engine_mismatch",
            "A normalized engine fact promotion policy allowed-engine set differs from the fact registry.",
        )
    if "trino" in definition.allowed_engines and entry.promotion_gate != ENGINE_FACT_PROMOTION_GATE:
        add_issue(
            result,
            "engine_fact_promotion_policy",
            "engine_fact_promotion_policy_trino_gate_missing",
            "Trino-visible normalized fact promotion policies must keep the explicit gate.",
        )


def support_gap_summary_payload(
    result: TrinoSupportGapAuditResult,
    *,
    status: str,
) -> dict[str, Any]:
    return {
        "summary_kind": TRINO_SUPPORT_GAP_SUMMARY_KIND,
        "status": status,
        "support_gap_status": TRINO_SUPPORT_GAP_STATUS,
        "production_support": "not_claimed",
        "product_surfaces": "blocked",
        "trino_sql_execution": "not_performed",
        "family_count": result.family_count,
        "required_fact_count": result.required_fact_count,
        "required_limitation_fact_count": result.required_limitation_fact_count,
        "trino_allowed_fact_count": result.trino_allowed_fact_count,
        "preview_adapter_flag_count": result.preview_adapter_flag_count,
        "blocked_product_adapter_flag_count": result.blocked_product_adapter_flag_count,
        "source_registry_entry_count": result.source_registry_entry_count,
        "promotion_policy_entry_count": result.promotion_policy_entry_count,
        "status_counts": counter_payload(result.status_counts),
        "fact_scope_counts": counter_payload(result.fact_scope_counts),
        "source_registry_surface_counts": counter_payload(result.source_registry_surface_counts),
        "source_registry_contract_counts": counter_payload(result.source_registry_contract_counts),
        "promotion_policy_scope_counts": counter_payload(result.promotion_policy_scope_counts),
        "issue_counts": counter_payload(result.issue_counts),
        "issues": [
            {
                "family_id": family_id,
                "category": issue.category,
                "message": issue.message,
            }
            for family_id, issue in result.issues
        ],
    }


def print_issues(result: TrinoSupportGapAuditResult, *, limit: int) -> None:
    if not result.issues:
        print("Issues: none")
        return
    print("Issues:")
    for family_id, issue in result.issues[:limit]:
        print(f"- {issue.category}: family={family_id}; {issue.message}")
    remaining = len(result.issues) - limit
    if remaining > 0:
        print(f"- additional_issues: {remaining}")


def add_issue(
    result: TrinoSupportGapAuditResult,
    family_id: str,
    category: str,
    message: str,
) -> None:
    issue = TrinoSupportGapIssue(category=category, message=message)
    result.issue_counts[category] += 1
    result.issues.append((family_id, issue))


def write_summary_or_reject(path: Path | None, payload: dict[str, Any]) -> bool:
    if path is None:
        return True
    try:
        path.write_text(
            json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError:
        print(
            "[trino-support-gap-audit] rejected: summary JSON output could not be written",
            file=sys.stderr,
        )
        return False
    return True


def counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def counter_text(counter: Counter[str]) -> str:
    return ", ".join(f"{key}={counter[key]}" for key in sorted(counter))


def positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
