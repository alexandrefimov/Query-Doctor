"""Raw-free audit model for Trino production collector contract closure.

This module describes the first broader-production closure gate. It does not
collect from Trino, add product support, or enable new browser/report surfaces.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.util import find_spec
from typing import Any

from query_doctor.cli.commands import COMMAND_SPECS, CommandSpec
from query_doctor.engines.capabilities import EngineCapability, engine_capabilities
from query_doctor.trino.coordinator_query_info_pruned_import import (
    TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SOURCE,
)
from query_doctor.trino.coordinator_query_info_target import (
    TRINO_COORDINATOR_QUERY_INFO_SOURCE_TYPE,
)
from query_doctor.trino.coordinator_query_list_target import (
    TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE,
)
from query_doctor.trino.http_event_archive import TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE
from query_doctor.trino.http_query_detail_archive import (
    TRINO_HTTP_QUERY_DETAIL_ARCHIVE_SOURCE_TYPE,
)
from query_doctor.trino.metadata_source_contract import TRINO_METADATA_SOURCE_TYPE
from query_doctor.trino.representative_evidence import (
    TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE,
    TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_KINDS,
    TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_STATUSES,
    TRINO_REPRESENTATIVE_EVIDENCE_GATE,
    TRINO_REPRESENTATIVE_EVIDENCE_STATUS,
    TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND,
)
from query_doctor.trino.source_contract_registry import (
    TrinoSourceContractRegistryEntry,
    trino_source_contract_registry,
)


TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND = "trino_production_collector_contracts_audit_v1"
TRINO_PRODUCTION_COLLECTOR_CONTRACTS_GATE = "trino_production_collector_contracts"
TRINO_PRODUCTION_COLLECTOR_CONTRACTS_STATUS = "not_closed"
TRINO_PRODUCTION_COLLECTOR_CLOSURE_REASON = (
    "collector_contracts_require_broader_sources_evidence_and_regression_tests"
)
TRINO_PRODUCTION_COLLECTOR_REPRESENTATIVE_EVIDENCE_READY = "ready"
TRINO_PRODUCTION_COLLECTOR_REPRESENTATIVE_EVIDENCE_NOT_PROVIDED = "not_provided"
TRINO_PRODUCTION_COLLECTOR_REPRESENTATIVE_EVIDENCE_DRIFTED = "drifted"
TRINO_PRODUCTION_COLLECTOR_FORBIDDEN_SOURCE_TYPES = frozenset(
    {
        "trino_running_scan",
        "trino_query_history_crawl",
        "trino_broad_query_info_collection",
        "trino_post_statement_collection",
        "trino_explain_analyze_collection",
    }
)
TRINO_PRODUCTION_COLLECTOR_FORBIDDEN_READER_ROLES = frozenset(
    {
        "trino_running_scan",
        "trino_query_history_crawl",
        "trino_broad_query_info_collection",
        "trino_post_statement_collection",
        "trino_explain_analyze_collection",
    }
)
TRINO_PRODUCTION_COLLECTOR_FORBIDDEN_CAPABILITY_SURFACES = frozenset(
    {
        "running_scan",
        "query_history_crawl",
        "broad_query_info_collection",
        "post_statement_collection",
        "explain_analyze_collection",
    }
)


@dataclass(frozen=True)
class TrinoProductionCollectorSourceRequirement:
    source_type: str
    contract_family: str
    network_access: str
    required_bounds: tuple[str, ...]
    product_surfaces: str = "blocked"
    recent_scan: str = "blocked"
    browser_report_output: str = "blocked"
    details_report_output: str = "blocked"
    optimizer_behavior: str = "blocked"
    sql_execution: str = "not_performed"
    auth_reference_policy: str = "not_applicable"
    source_schema_gate: str = "compact_schema_required"
    retry_policy: str = "not_performed"
    failure_mode: str = "fail_closed"
    reader_status: str = "not_performed"
    reader_scope: str = "not_performed"
    reader_module: str | None = None
    reader_cli_role: str | None = None
    reader_capability_surface_id: str | None = None
    reader_capability_support_level: str | None = None
    reader_capability_product_surface_allowed: bool | None = None
    raw_payload_storage: str = "forbidden"
    raw_metadata_storage: str | None = None
    identifier_output: str | None = None


@dataclass(frozen=True)
class TrinoProductionCollectorFamily:
    family_id: str
    readiness_state: str
    production_blocker: str
    requirements: tuple[TrinoProductionCollectorSourceRequirement, ...] = ()


@dataclass(frozen=True)
class TrinoProductionCollectorIssue:
    category: str
    message: str
    source_type: str | None = None


@dataclass(frozen=True)
class TrinoProductionCollectorSourceTracking:
    family_id: str
    source_type: str
    contract_family: str
    network_access: str
    auth_reference_policy: str
    source_schema_gate: str
    retry_policy: str
    failure_mode: str
    reader_status: str
    reader_scope: str
    reader_module: str | None
    reader_cli_role: str | None
    reader_capability_surface_id: str | None
    tracking_status: str
    issue_count: int


@dataclass
class TrinoProductionCollectorAuditResult:
    family_count: int = 0
    source_requirement_count: int = 0
    source_backed_family_count: int = 0
    open_blocker_count: int = 0
    forbidden_source_type_count: int = 0
    representative_evidence_summary_count: int = 0
    representative_evidence_ready_count: int = 0
    representative_evidence_required: bool = False
    representative_evidence_contract_status: str = (
        TRINO_PRODUCTION_COLLECTOR_REPRESENTATIVE_EVIDENCE_NOT_PROVIDED
    )
    status_counts: Counter[str] = field(default_factory=Counter)
    source_contract_counts: Counter[str] = field(default_factory=Counter)
    network_access_counts: Counter[str] = field(default_factory=Counter)
    source_requirement_tracking_counts: Counter[str] = field(default_factory=Counter)
    auth_reference_policy_counts: Counter[str] = field(default_factory=Counter)
    source_schema_gate_counts: Counter[str] = field(default_factory=Counter)
    retry_policy_counts: Counter[str] = field(default_factory=Counter)
    failure_mode_counts: Counter[str] = field(default_factory=Counter)
    reader_status_counts: Counter[str] = field(default_factory=Counter)
    reader_scope_counts: Counter[str] = field(default_factory=Counter)
    reader_cli_role_counts: Counter[str] = field(default_factory=Counter)
    reader_capability_counts: Counter[str] = field(default_factory=Counter)
    blocker_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    forbidden_reader_role_count: int = 0
    forbidden_reader_capability_count: int = 0
    blockers: list[tuple[str, str]] = field(default_factory=list)
    source_requirement_tracking: list[TrinoProductionCollectorSourceTracking] = field(
        default_factory=list
    )
    issues: list[tuple[str, TrinoProductionCollectorIssue]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issue_counts


TRINO_PRODUCTION_COLLECTOR_FAMILIES = (
    TrinoProductionCollectorFamily(
        family_id="local_recent_retained_query_list",
        readiness_state="current_local_lane",
        production_blocker="bounded_retained_list_only_no_query_history_crawl_or_running",
        requirements=(
            TrinoProductionCollectorSourceRequirement(
                source_type=TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE,
                contract_family="coordinator_query_list_source_contract",
                network_access="one_bounded_retained_query_list_request",
                required_bounds=(
                    "max_query_ids",
                    "max_bytes",
                    "max_query_list_depth",
                    "timeout_seconds",
                ),
                product_surfaces="trino_recent_local_production",
                recent_scan="retained_query_list_local_production",
                auth_reference_policy="operator_managed_safe_reference_required",
                source_schema_gate="coordinator_query_list_source_contract_schema_required",
                retry_policy="explicit_bounded_retry_or_none",
                reader_status="implemented_bounded_reader",
                reader_scope="one_bounded_retained_query_list_read",
                reader_module="query_doctor.trino.coordinator_query_list_target",
                reader_capability_surface_id="recent_scan",
                reader_capability_support_level="production",
                reader_capability_product_surface_allowed=True,
            ),
        ),
    ),
    TrinoProductionCollectorFamily(
        family_id="local_one_query_pruned_query_info",
        readiness_state="current_local_lane",
        production_blocker="one_query_or_selected_rows_only_no_broad_query_history",
        requirements=(
            TrinoProductionCollectorSourceRequirement(
                source_type=TRINO_COORDINATOR_QUERY_INFO_SOURCE_TYPE,
                contract_family="coordinator_query_info_source_contract",
                network_access="optional_one_explicit_pruned_query_info_request",
                required_bounds=(
                    "max_query_ids",
                    "max_bytes",
                    "max_query_info_depth",
                    "timeout_seconds",
                ),
                auth_reference_policy="operator_managed_safe_reference_required",
                source_schema_gate="coordinator_query_info_source_contract_schema_required",
                retry_policy="explicit_bounded_retry_or_none",
                reader_status="target_check_only",
                reader_scope="one_query_pruned_query_info_target_check",
                reader_module="query_doctor.trino.coordinator_query_info_target",
                reader_cli_role="trino_coordinator_query_info_target_check",
                reader_capability_surface_id="coordinator_query_info_target_check",
                reader_capability_support_level="bounded_raw_free_preview",
                reader_capability_product_surface_allowed=False,
            ),
            TrinoProductionCollectorSourceRequirement(
                source_type=TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SOURCE,
                contract_family="coordinator_query_info_source_contract",
                network_access="one_explicit_pruned_query_info_request",
                required_bounds=(
                    "max_query_ids",
                    "max_bytes",
                    "max_query_info_depth",
                    "timeout_seconds",
                ),
                product_surfaces="trino_query_id_local_production_details_python_report_optimizer_guidance",
                browser_report_output=(
                    "python_report_and_optimizer_guidance_after_raw_free_case_materialization"
                ),
                details_report_output=(
                    "python_report_and_optimizer_guidance_after_raw_free_case_materialization"
                ),
                optimizer_behavior="guidance_only_after_raw_free_case_materialization",
                auth_reference_policy="operator_managed_safe_reference_required",
                source_schema_gate="coordinator_query_info_source_contract_schema_required",
                retry_policy="explicit_bounded_retry_or_none",
                reader_status="implemented_bounded_reader",
                reader_scope="one_explicit_pruned_query_info_read",
                reader_module="query_doctor.trino.coordinator_query_info_pruned_import",
                reader_cli_role="trino_coordinator_query_info_pruned_import",
                reader_capability_surface_id="query_id_mode",
                reader_capability_support_level="production",
                reader_capability_product_surface_allowed=True,
            ),
        ),
    ),
    TrinoProductionCollectorFamily(
        family_id="operator_http_event_archive",
        readiness_state="preview_reader",
        production_blocker="operator_sanitized_archive_only_no_installed_event_store_connector",
        requirements=(
            TrinoProductionCollectorSourceRequirement(
                source_type=TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE,
                contract_family="event_source_contract",
                network_access="one_explicit_operator_archive_url",
                required_bounds=(
                    "max_records",
                    "max_bytes",
                    "max_record_bytes",
                    "max_record_depth",
                    "timeout_seconds",
                ),
                auth_reference_policy="operator_managed_safe_reference_required",
                source_schema_gate="event_source_contract_schema_required",
                retry_policy="explicit_bounded_retry_or_none",
                reader_status="implemented_bounded_reader",
                reader_scope="one_explicit_operator_http_event_archive_read",
                reader_module="query_doctor.trino.http_event_archive",
                reader_cli_role="trino_http_event_archive_import",
                reader_capability_surface_id="http_event_archive_import",
                reader_capability_support_level="bounded_raw_free_preview",
                reader_capability_product_surface_allowed=False,
            ),
        ),
    ),
    TrinoProductionCollectorFamily(
        family_id="event_store_source_contracts",
        readiness_state="contract_check_only",
        production_blocker="kafka_and_mysql_event_listener_contracts_have_no_reader",
        requirements=(
            TrinoProductionCollectorSourceRequirement(
                source_type="kafka_event_listener",
                contract_family="event_source_contract",
                network_access="not_performed",
                required_bounds=(
                    "max_records",
                    "max_bytes",
                    "max_record_bytes",
                    "max_record_depth",
                    "timeout_seconds",
                ),
                auth_reference_policy="operator_managed_safe_reference_required",
                source_schema_gate="event_source_contract_schema_required",
                reader_status="contract_check_only_no_reader",
                reader_scope="event_store_source_contract_only",
                reader_module="query_doctor.trino.event_source_contract",
                reader_cli_role="trino_event_source_contract_check",
                reader_capability_surface_id="event_source_contract_check",
                reader_capability_support_level="bounded_raw_free_preview",
                reader_capability_product_surface_allowed=False,
            ),
            TrinoProductionCollectorSourceRequirement(
                source_type="mysql_event_listener",
                contract_family="event_source_contract",
                network_access="not_performed",
                required_bounds=(
                    "max_records",
                    "max_bytes",
                    "max_record_bytes",
                    "max_record_depth",
                    "timeout_seconds",
                ),
                auth_reference_policy="operator_managed_safe_reference_required",
                source_schema_gate="event_source_contract_schema_required",
                reader_status="contract_check_only_no_reader",
                reader_scope="event_store_source_contract_only",
                reader_module="query_doctor.trino.event_source_contract",
                reader_cli_role="trino_event_source_contract_check",
                reader_capability_surface_id="event_source_contract_check",
                reader_capability_support_level="bounded_raw_free_preview",
                reader_capability_product_surface_allowed=False,
            ),
        ),
    ),
    TrinoProductionCollectorFamily(
        family_id="operator_http_query_detail_archive",
        readiness_state="preview_reader",
        production_blocker="operator_sanitized_archive_only_no_product_detail_collector",
        requirements=(
            TrinoProductionCollectorSourceRequirement(
                source_type=TRINO_HTTP_QUERY_DETAIL_ARCHIVE_SOURCE_TYPE,
                contract_family="query_detail_archive_source_contract",
                network_access="one_explicit_operator_archive_url",
                required_bounds=("max_bytes", "max_query_detail_depth", "timeout_seconds"),
                auth_reference_policy="operator_managed_safe_reference_required",
                source_schema_gate="query_detail_archive_source_contract_schema_required",
                retry_policy="explicit_bounded_retry_or_none",
                reader_status="implemented_bounded_reader",
                reader_scope="one_explicit_operator_http_query_detail_archive_read",
                reader_module="query_doctor.trino.http_query_detail_archive",
                reader_cli_role="trino_http_query_detail_archive_import",
                reader_capability_surface_id="http_query_detail_archive_import",
                reader_capability_support_level="bounded_raw_free_preview",
                reader_capability_product_surface_allowed=False,
            ),
        ),
    ),
    TrinoProductionCollectorFamily(
        family_id="local_compact_imports",
        readiness_state="local_import_only",
        production_blocker="already_sanitized_local_files_only_no_live_collector",
        requirements=(
            TrinoProductionCollectorSourceRequirement(
                source_type="local_event_store_import",
                contract_family="local_event_store_import",
                network_access="not_performed",
                required_bounds=(
                    "max_store_bytes",
                    "max_records",
                    "max_record_bytes",
                    "max_record_depth",
                ),
                source_schema_gate="compact_local_import_schema_required",
                reader_status="local_import_only",
                reader_scope="already_sanitized_local_file_import",
                reader_module="query_doctor.trino.local_event_store",
                reader_cli_role="trino_event_store_import",
                reader_capability_surface_id="local_event_store_import",
                reader_capability_support_level="bounded_raw_free_preview",
                reader_capability_product_surface_allowed=False,
            ),
            TrinoProductionCollectorSourceRequirement(
                source_type="local_query_detail_import",
                contract_family="local_query_detail_import",
                network_access="not_performed",
                required_bounds=(
                    "max_file_bytes",
                    "max_query_detail_bytes",
                    "max_query_detail_depth",
                ),
                source_schema_gate="compact_local_import_schema_required",
                reader_status="local_import_only",
                reader_scope="already_sanitized_local_file_import",
                reader_module="query_doctor.trino.local_query_detail",
                reader_cli_role="trino_query_detail_import",
                reader_capability_surface_id="local_query_detail_import",
                reader_capability_support_level="bounded_raw_free_preview",
                reader_capability_product_surface_allowed=False,
            ),
            TrinoProductionCollectorSourceRequirement(
                source_type="local_query_list_import",
                contract_family="local_query_list_import",
                network_access="not_performed",
                required_bounds=(
                    "max_file_bytes",
                    "max_query_list_bytes",
                    "max_query_list_depth",
                ),
                source_schema_gate="compact_local_import_schema_required",
                reader_status="local_import_only",
                reader_scope="already_sanitized_local_file_import",
                reader_module="query_doctor.trino.local_query_list",
                reader_cli_role="trino_query_list_import",
                reader_capability_surface_id="local_query_list_import",
                reader_capability_support_level="bounded_raw_free_preview",
                reader_capability_product_surface_allowed=False,
            ),
            TrinoProductionCollectorSourceRequirement(
                source_type="local_statement_stats_import",
                contract_family="local_statement_stats_import",
                network_access="not_performed",
                required_bounds=(
                    "max_file_bytes",
                    "max_statement_stats_bytes",
                    "max_statement_stats_depth",
                ),
                source_schema_gate="compact_local_import_schema_required",
                reader_status="local_import_only",
                reader_scope="already_sanitized_local_file_import",
                reader_module="query_doctor.trino.local_statement_stats",
                reader_cli_role="trino_statement_stats_import",
                reader_capability_surface_id="local_statement_stats_import",
                reader_capability_support_level="bounded_raw_free_preview",
                reader_capability_product_surface_allowed=False,
            ),
            TrinoProductionCollectorSourceRequirement(
                source_type="local_query_info_pruned_import",
                contract_family="coordinator_query_info_source_contract",
                network_access="not_performed",
                required_bounds=("max_query_ids", "max_bytes", "max_query_info_depth"),
                auth_reference_policy="source_contract_safe_reference_required",
                source_schema_gate="coordinator_query_info_source_contract_schema_required",
                reader_status="local_import_only",
                reader_scope="already_sanitized_local_file_import",
                reader_module="query_doctor.trino.coordinator_query_info_pruned_import",
                reader_cli_role="trino_query_info_pruned_import",
                reader_capability_surface_id="local_query_info_pruned_import",
                reader_capability_support_level="bounded_raw_free_preview",
                reader_capability_product_surface_allowed=False,
            ),
        ),
    ),
    TrinoProductionCollectorFamily(
        family_id="metadata_collection_boundary",
        readiness_state="separate_closure_gate",
        production_blocker="aggregate_metadata_only_product_metadata_gate_open",
        requirements=(
            TrinoProductionCollectorSourceRequirement(
                source_type=TRINO_METADATA_SOURCE_TYPE,
                contract_family="metadata_source_contract",
                network_access="not_performed",
                required_bounds=(
                    "max_relations",
                    "max_columns_per_relation",
                    "max_identifier_length",
                    "max_metadata_bytes",
                    "timeout_seconds",
                ),
                auth_reference_policy="source_contract_safe_reference_required",
                source_schema_gate="metadata_allowlist_source_contract_schema_required",
                raw_payload_storage="not_applicable",
                raw_metadata_storage="forbidden",
                identifier_output="blocked",
                reader_status="contract_check_only_no_reader",
                reader_scope="metadata_allowlist_source_contract_only",
                reader_module="query_doctor.trino.metadata_source_contract",
                reader_cli_role="trino_metadata_source_contract_check",
                reader_capability_surface_id="metadata_source_contract_check",
                reader_capability_support_level="bounded_raw_free_preview",
                reader_capability_product_surface_allowed=False,
            ),
            TrinoProductionCollectorSourceRequirement(
                source_type="trino_metadata_cli_summary",
                contract_family="metadata_source_contract",
                network_access="operator_installed_trino_cli_only",
                required_bounds=(
                    "max_relations",
                    "max_columns_per_relation",
                    "max_identifier_length",
                    "max_metadata_bytes",
                    "timeout_seconds",
                ),
                auth_reference_policy="source_contract_safe_reference_required",
                source_schema_gate="metadata_allowlist_source_contract_schema_required",
                retry_policy="explicit_bounded_retry_or_none",
                raw_metadata_storage="forbidden",
                identifier_output="blocked",
                sql_execution="python_owned_metadata_statements_only",
                reader_status="aggregate_metadata_cli_reader",
                reader_scope="one_allowlisted_aggregate_metadata_cli_summary",
                reader_module="query_doctor.trino.metadata_cli_summary",
                reader_cli_role="trino_metadata_cli_summary",
                reader_capability_surface_id="metadata_cli_summary",
                reader_capability_support_level="bounded_raw_free_preview",
                reader_capability_product_surface_allowed=False,
            ),
            TrinoProductionCollectorSourceRequirement(
                source_type="local_metadata_summary_import",
                contract_family="metadata_source_contract",
                network_access="not_performed",
                required_bounds=(
                    "max_relations",
                    "max_columns_per_relation",
                    "max_metadata_bytes",
                    "max_metadata_summary_depth",
                ),
                auth_reference_policy="source_contract_safe_reference_required",
                source_schema_gate="metadata_summary_contract_schema_required",
                raw_payload_storage="not_applicable",
                raw_metadata_storage="forbidden",
                identifier_output="blocked",
                reader_status="local_import_only",
                reader_scope="already_sanitized_local_metadata_summary_import",
                reader_module="query_doctor.trino.local_metadata_summary",
                reader_cli_role="trino_metadata_summary_import",
                reader_capability_surface_id="local_metadata_summary_import",
                reader_capability_support_level="bounded_raw_free_preview",
                reader_capability_product_surface_allowed=False,
            ),
        ),
    ),
    TrinoProductionCollectorFamily(
        family_id="broad_workflow_collectors",
        readiness_state="open_required_future_work",
        production_blocker="running_query_history_sql_execution_remain_unsupported",
    ),
)


def audit_trino_production_collector_contracts(
    *,
    families: Iterable[TrinoProductionCollectorFamily] = TRINO_PRODUCTION_COLLECTOR_FAMILIES,
    source_registry: Iterable[TrinoSourceContractRegistryEntry] | None = None,
    command_specs: Mapping[str, CommandSpec] = COMMAND_SPECS,
    capabilities: Iterable[EngineCapability] | None = None,
    representative_evidence_summaries: Iterable[dict[str, Any]] = (),
    require_representative_evidence_summary: bool = False,
) -> TrinoProductionCollectorAuditResult:
    result = TrinoProductionCollectorAuditResult(
        representative_evidence_required=require_representative_evidence_summary,
    )
    family_tuple = tuple(families)
    entries_by_type = {
        entry.source_type: entry
        for entry in (
            trino_source_contract_registry() if source_registry is None else source_registry
        )
    }
    capability_tuple = (
        tuple(engine_capabilities("trino")) if capabilities is None else tuple(capabilities)
    )
    capabilities_by_id = {capability.surface_id: capability for capability in capability_tuple}

    audit_forbidden_source_types(result, entries_by_type)
    audit_forbidden_reader_wiring(result, command_specs, capabilities_by_id)
    for family in family_tuple:
        result.family_count += 1
        result.status_counts[family.readiness_state] += 1
        if family.production_blocker:
            result.open_blocker_count += 1
            result.blocker_counts[family.production_blocker] += 1
            result.blockers.append((family.family_id, family.production_blocker))
        if family.requirements:
            result.source_backed_family_count += 1
        for requirement in family.requirements:
            result.source_requirement_count += 1
            audit_source_requirement(
                result,
                family.family_id,
                requirement,
                entries_by_type,
                command_specs,
                capabilities_by_id,
            )
    audit_representative_evidence_contract(
        result,
        representative_evidence_summaries,
        require_summary=require_representative_evidence_summary,
    )
    finalize_source_requirement_tracking(result, family_tuple)
    return result


def audit_forbidden_source_types(
    result: TrinoProductionCollectorAuditResult,
    entries_by_type: dict[str, TrinoSourceContractRegistryEntry],
) -> None:
    forbidden_present = sorted(
        TRINO_PRODUCTION_COLLECTOR_FORBIDDEN_SOURCE_TYPES & entries_by_type.keys()
    )
    result.forbidden_source_type_count = len(forbidden_present)
    for _source_type in forbidden_present:
        add_issue(
            result,
            "broad_workflow_collectors",
            "trino_forbidden_production_collector_source_registered",
            "A broad Trino collector source type is registered before its closure gate is implemented.",
            source_type=_source_type,
        )


def audit_forbidden_reader_wiring(
    result: TrinoProductionCollectorAuditResult,
    command_specs: Mapping[str, CommandSpec],
    capabilities_by_id: Mapping[str, EngineCapability],
) -> None:
    forbidden_roles = sorted(
        TRINO_PRODUCTION_COLLECTOR_FORBIDDEN_READER_ROLES & command_specs.keys()
    )
    result.forbidden_reader_role_count = len(forbidden_roles)
    for role in forbidden_roles:
        add_issue(
            result,
            "broad_workflow_collectors",
            "trino_forbidden_production_collector_reader_role_registered",
            "A broad Trino collector reader role is registered before its closure gate is implemented.",
            source_type=role,
        )
    forbidden_capabilities = sorted(
        TRINO_PRODUCTION_COLLECTOR_FORBIDDEN_CAPABILITY_SURFACES & capabilities_by_id.keys()
    )
    result.forbidden_reader_capability_count = len(forbidden_capabilities)
    for surface_id in forbidden_capabilities:
        add_issue(
            result,
            "broad_workflow_collectors",
            "trino_forbidden_production_collector_reader_capability_registered",
            "A broad Trino collector reader capability is registered before its closure gate is implemented.",
            source_type=surface_id,
        )


def audit_source_requirement(
    result: TrinoProductionCollectorAuditResult,
    family_id: str,
    requirement: TrinoProductionCollectorSourceRequirement,
    entries_by_type: dict[str, TrinoSourceContractRegistryEntry],
    command_specs: Mapping[str, CommandSpec],
    capabilities_by_id: Mapping[str, EngineCapability],
) -> None:
    entry = entries_by_type.get(requirement.source_type)
    if entry is None:
        add_issue(
            result,
            family_id,
            "trino_collector_source_missing",
            "A required Trino collector contract source is not registered.",
            source_type=requirement.source_type,
        )
        return

    result.source_contract_counts[entry.contract_family] += 1
    result.network_access_counts[entry.network_access] += 1
    result.auth_reference_policy_counts[entry.auth_reference_policy] += 1
    result.source_schema_gate_counts[entry.source_schema_gate] += 1
    result.retry_policy_counts[entry.retry_policy] += 1
    result.failure_mode_counts[entry.failure_mode] += 1
    result.reader_status_counts[requirement.reader_status] += 1
    result.reader_scope_counts[requirement.reader_scope] += 1
    if requirement.reader_cli_role:
        result.reader_cli_role_counts[requirement.reader_cli_role] += 1
    if requirement.reader_capability_surface_id:
        result.reader_capability_counts[requirement.reader_capability_surface_id] += 1
    expected_fields: tuple[tuple[str, Any], ...] = (
        ("contract_family", requirement.contract_family),
        ("network_access", requirement.network_access),
        ("product_surfaces", requirement.product_surfaces),
        ("recent_scan", requirement.recent_scan),
        ("browser_report_output", requirement.browser_report_output),
        ("details_report_output", requirement.details_report_output),
        ("optimizer_behavior", requirement.optimizer_behavior),
        ("sql_execution", requirement.sql_execution),
        ("auth_reference_policy", requirement.auth_reference_policy),
        ("source_schema_gate", requirement.source_schema_gate),
        ("retry_policy", requirement.retry_policy),
        ("failure_mode", requirement.failure_mode),
        ("raw_payload_storage", requirement.raw_payload_storage),
    )
    for field_name, expected_value in expected_fields:
        if getattr(entry, field_name) != expected_value:
            add_issue(
                result,
                family_id,
                f"trino_collector_source_{field_name}_drift",
                "A Trino collector source contract drifted from the production-closure boundary.",
                source_type=requirement.source_type,
            )
    if requirement.raw_metadata_storage is not None:
        if entry.raw_metadata_storage != requirement.raw_metadata_storage:
            add_issue(
                result,
                family_id,
                "trino_collector_source_raw_metadata_storage_drift",
                "A Trino metadata collector source must keep raw metadata storage forbidden.",
                source_type=requirement.source_type,
            )
    if requirement.identifier_output is not None:
        if entry.identifier_output != requirement.identifier_output:
            add_issue(
                result,
                family_id,
                "trino_collector_source_identifier_output_drift",
                "A Trino metadata collector source must keep identifier output blocked.",
                source_type=requirement.source_type,
            )
    missing_bounds = set(requirement.required_bounds) - set(entry.required_bounds)
    if missing_bounds:
        add_issue(
            result,
            family_id,
            "trino_collector_source_bounds_missing",
            "A Trino collector source contract is missing required bounds.",
            source_type=requirement.source_type,
        )

    audit_reader_requirement(
        result,
        family_id,
        requirement,
        command_specs,
        capabilities_by_id,
    )


def audit_reader_requirement(
    result: TrinoProductionCollectorAuditResult,
    family_id: str,
    requirement: TrinoProductionCollectorSourceRequirement,
    command_specs: Mapping[str, CommandSpec],
    capabilities_by_id: Mapping[str, EngineCapability],
) -> None:
    if requirement.reader_status != "not_performed" and not requirement.reader_scope:
        add_issue(
            result,
            family_id,
            "trino_collector_reader_scope_missing",
            "A Trino collector reader requirement must pin its bounded reader scope.",
            source_type=requirement.source_type,
        )
    if requirement.reader_status in {
        "implemented_bounded_reader",
        "aggregate_metadata_cli_reader",
        "local_import_only",
        "target_check_only",
        "contract_check_only_no_reader",
    }:
        if not requirement.reader_module:
            add_issue(
                result,
                family_id,
                "trino_collector_reader_module_missing",
                "A Trino collector reader requirement must name its implementation module.",
                source_type=requirement.source_type,
            )
    if requirement.reader_module and find_spec(requirement.reader_module) is None:
        add_issue(
            result,
            family_id,
            "trino_collector_reader_module_missing",
            "A Trino collector reader module is not importable.",
            source_type=requirement.source_type,
        )
    if requirement.reader_cli_role:
        if requirement.reader_cli_role not in command_specs:
            add_issue(
                result,
                family_id,
                "trino_collector_reader_cli_role_missing",
                "A Trino collector reader CLI role is not registered.",
                source_type=requirement.source_type,
            )
    if requirement.reader_capability_surface_id:
        capability = capabilities_by_id.get(requirement.reader_capability_surface_id)
        if capability is None:
            add_issue(
                result,
                family_id,
                "trino_collector_reader_capability_missing",
                "A Trino collector reader capability is not registered.",
                source_type=requirement.source_type,
            )
        else:
            _audit_reader_capability(result, family_id, requirement, capability)


def _audit_reader_capability(
    result: TrinoProductionCollectorAuditResult,
    family_id: str,
    requirement: TrinoProductionCollectorSourceRequirement,
    capability: EngineCapability,
) -> None:
    if capability.engine != "trino":
        add_issue(
            result,
            family_id,
            "trino_collector_reader_capability_engine_drift",
            "A Trino collector reader capability must remain Trino-owned.",
            source_type=requirement.source_type,
        )
    if (
        requirement.reader_capability_support_level is not None
        and capability.support_level != requirement.reader_capability_support_level
    ):
        add_issue(
            result,
            family_id,
            "trino_collector_reader_capability_support_level_drift",
            "A Trino collector reader capability support level drifted.",
            source_type=requirement.source_type,
        )
    if (
        requirement.reader_capability_product_surface_allowed is not None
        and capability.product_surface_allowed
        != requirement.reader_capability_product_surface_allowed
    ):
        add_issue(
            result,
            family_id,
            "trino_collector_reader_capability_product_surface_drift",
            "A Trino collector reader capability product-surface policy drifted.",
            source_type=requirement.source_type,
        )
    if requirement.reader_cli_role and capability.cli_role not in {
        None,
        requirement.reader_cli_role,
    }:
        add_issue(
            result,
            family_id,
            "trino_collector_reader_capability_cli_role_drift",
            "A Trino collector reader capability CLI role drifted.",
            source_type=requirement.source_type,
        )


def finalize_source_requirement_tracking(
    result: TrinoProductionCollectorAuditResult,
    families: tuple[TrinoProductionCollectorFamily, ...],
) -> None:
    result.source_requirement_tracking.clear()
    result.source_requirement_tracking_counts.clear()
    for family in families:
        for requirement in family.requirements:
            source_issues = _issues_for_source_requirement(
                result,
                family.family_id,
                requirement.source_type,
            )
            tracking_status = _source_requirement_tracking_status(source_issues)
            result.source_requirement_tracking.append(
                TrinoProductionCollectorSourceTracking(
                    family_id=family.family_id,
                    source_type=requirement.source_type,
                    contract_family=requirement.contract_family,
                    network_access=requirement.network_access,
                    auth_reference_policy=requirement.auth_reference_policy,
                    source_schema_gate=requirement.source_schema_gate,
                    retry_policy=requirement.retry_policy,
                    failure_mode=requirement.failure_mode,
                    reader_status=requirement.reader_status,
                    reader_scope=requirement.reader_scope,
                    reader_module=requirement.reader_module,
                    reader_cli_role=requirement.reader_cli_role,
                    reader_capability_surface_id=requirement.reader_capability_surface_id,
                    tracking_status=tracking_status,
                    issue_count=len(source_issues),
                )
            )
            result.source_requirement_tracking_counts[tracking_status] += 1


def _issues_for_source_requirement(
    result: TrinoProductionCollectorAuditResult,
    family_id: str,
    source_type: str,
) -> tuple[TrinoProductionCollectorIssue, ...]:
    return tuple(
        issue
        for issue_family_id, issue in result.issues
        if issue_family_id == family_id and issue.source_type == source_type
    )


def _source_requirement_tracking_status(
    issues: tuple[TrinoProductionCollectorIssue, ...],
) -> str:
    if any(issue.category == "trino_collector_source_missing" for issue in issues):
        return "missing"
    if issues:
        return "invalid"
    return "accepted"


def audit_representative_evidence_contract(
    result: TrinoProductionCollectorAuditResult,
    summaries: Iterable[dict[str, Any]],
    *,
    require_summary: bool,
) -> None:
    summary_tuple = tuple(summaries)
    result.representative_evidence_summary_count = len(summary_tuple)
    if not summary_tuple:
        result.representative_evidence_contract_status = (
            TRINO_PRODUCTION_COLLECTOR_REPRESENTATIVE_EVIDENCE_NOT_PROVIDED
        )
        if require_summary:
            add_issue(
                result,
                "representative_evidence_handoff",
                "trino_collector_representative_evidence_summary_missing",
                "Production collector review requires a retained representative-evidence summary.",
            )
        return

    for summary in summary_tuple:
        _audit_single_representative_evidence_summary(result, summary)
    result.representative_evidence_contract_status = (
        TRINO_PRODUCTION_COLLECTOR_REPRESENTATIVE_EVIDENCE_READY
        if result.representative_evidence_ready_count
        == result.representative_evidence_summary_count
        else TRINO_PRODUCTION_COLLECTOR_REPRESENTATIVE_EVIDENCE_DRIFTED
    )


def _audit_single_representative_evidence_summary(
    result: TrinoProductionCollectorAuditResult,
    summary: dict[str, Any],
) -> None:
    expected_fields: tuple[tuple[str, Any], ...] = (
        ("summary_kind", TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND),
        ("status", "ok"),
        ("closure_gate", TRINO_REPRESENTATIVE_EVIDENCE_GATE),
        ("representative_evidence_status", TRINO_REPRESENTATIVE_EVIDENCE_STATUS),
        ("broader_production_closure_status", "not_closed"),
        ("trino_sql_execution", "not_performed"),
    )
    drifted = False
    for field_name, expected_value in expected_fields:
        if summary.get(field_name) != expected_value:
            drifted = True
            add_issue(
                result,
                "representative_evidence_handoff",
                f"trino_collector_representative_evidence_{field_name}_drift",
                "Retained representative evidence summary drifted from the collector-review contract.",
            )
    evidence_unit_count = summary.get("evidence_unit_count")
    if not isinstance(evidence_unit_count, int) or isinstance(evidence_unit_count, bool):
        evidence_unit_count = 0
    if evidence_unit_count <= 0:
        drifted = True
        add_issue(
            result,
            "representative_evidence_handoff",
            "trino_collector_representative_evidence_units_missing",
            "Retained representative evidence summary must include at least one evidence unit.",
        )
    requirements = summary.get("requirements")
    requirement_profile = (
        requirements.get("requirement_profile") if isinstance(requirements, dict) else None
    )
    if requirement_profile != TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE:
        drifted = True
        add_issue(
            result,
            "representative_evidence_handoff",
            "trino_collector_representative_evidence_breadth_profile_drift",
            "Retained representative evidence summary must use the production-review breadth profile.",
        )
    if not _summary_requirements_include(
        requirements,
        "require_summary_kinds",
        TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_KINDS,
    ):
        drifted = True
        add_issue(
            result,
            "representative_evidence_handoff",
            "trino_collector_representative_evidence_summary_kind_requirements_drift",
            "Retained representative evidence summary must require the production-review summary-kind mix.",
        )
    if not _summary_requirements_include(
        requirements,
        "require_summary_statuses",
        TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_STATUSES,
    ):
        drifted = True
        add_issue(
            result,
            "representative_evidence_handoff",
            "trino_collector_representative_evidence_summary_status_requirements_drift",
            "Retained representative evidence summary must require accepted retained input statuses.",
        )
    if summary.get("breadth_profile_status") != "ready":
        drifted = True
        add_issue(
            result,
            "representative_evidence_handoff",
            "trino_collector_representative_evidence_breadth_profile_drift",
            "Retained representative evidence summary breadth profile must be ready.",
        )
    counters = summary.get("counters")
    if not isinstance(counters, dict):
        counters = {}
    required_counter_groups = (
        "summary_kinds",
        "statuses",
        "trino_version_families",
        "source_contracts",
        "source_schemas",
        "lifecycles",
        "connector_family_categories",
        "source_granularity",
        "verification_scopes",
        "support_statuses",
    )
    for counter_group in required_counter_groups:
        counter_payload = counters.get(counter_group)
        if not isinstance(counter_payload, dict) or not counter_payload:
            drifted = True
            add_issue(
                result,
                "representative_evidence_handoff",
                f"trino_collector_representative_evidence_{counter_group}_missing",
                "Retained representative evidence summary is missing a required safe counter group.",
            )
    if not _counter_has_positive_labels(
        counters.get("summary_kinds"),
        TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_KINDS,
    ):
        drifted = True
        add_issue(
            result,
            "representative_evidence_handoff",
            "trino_collector_representative_evidence_summary_kinds_missing",
            "Retained representative evidence summary is missing required summary-kind counters.",
        )
    if not _counter_has_positive_labels(
        counters.get("statuses"),
        TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_STATUSES,
    ):
        drifted = True
        add_issue(
            result,
            "representative_evidence_handoff",
            "trino_collector_representative_evidence_summary_statuses_missing",
            "Retained representative evidence summary is missing required retained status counters.",
        )
    if not drifted:
        result.representative_evidence_ready_count += 1


def _summary_requirements_include(
    requirements: Any,
    field_name: str,
    expected_values: Iterable[str],
) -> bool:
    if not isinstance(requirements, dict):
        return False
    raw_values = requirements.get(field_name)
    if not isinstance(raw_values, list):
        return False
    return set(expected_values).issubset(value for value in raw_values if isinstance(value, str))


def _counter_has_positive_labels(payload: Any, labels: Iterable[str]) -> bool:
    if not isinstance(payload, dict):
        return False
    for label in labels:
        value = payload.get(label)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            return False
    return True


def production_collector_summary_payload(
    result: TrinoProductionCollectorAuditResult,
    *,
    status: str,
) -> dict[str, Any]:
    return {
        "summary_kind": TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND,
        "status": status,
        "closure_gate": TRINO_PRODUCTION_COLLECTOR_CONTRACTS_GATE,
        "production_collector_contracts_status": TRINO_PRODUCTION_COLLECTOR_CONTRACTS_STATUS,
        "broader_production_closure_status": "not_closed",
        "closure_reason": TRINO_PRODUCTION_COLLECTOR_CLOSURE_REASON,
        "trino_sql_execution": "not_performed",
        "family_count": result.family_count,
        "source_backed_family_count": result.source_backed_family_count,
        "source_requirement_count": result.source_requirement_count,
        "open_blocker_count": result.open_blocker_count,
        "forbidden_source_type_count": result.forbidden_source_type_count,
        "representative_evidence_summary_count": result.representative_evidence_summary_count,
        "representative_evidence_ready_count": result.representative_evidence_ready_count,
        "representative_evidence_required": result.representative_evidence_required,
        "representative_evidence_contract_status": (result.representative_evidence_contract_status),
        "status_counts": counter_payload(result.status_counts),
        "source_contract_counts": counter_payload(result.source_contract_counts),
        "network_access_counts": counter_payload(result.network_access_counts),
        "auth_reference_policy_counts": counter_payload(result.auth_reference_policy_counts),
        "source_schema_gate_counts": counter_payload(result.source_schema_gate_counts),
        "retry_policy_counts": counter_payload(result.retry_policy_counts),
        "failure_mode_counts": counter_payload(result.failure_mode_counts),
        "reader_status_counts": counter_payload(result.reader_status_counts),
        "reader_scope_counts": counter_payload(result.reader_scope_counts),
        "reader_cli_role_counts": counter_payload(result.reader_cli_role_counts),
        "reader_capability_counts": counter_payload(result.reader_capability_counts),
        "forbidden_reader_role_count": result.forbidden_reader_role_count,
        "forbidden_reader_capability_count": result.forbidden_reader_capability_count,
        "source_requirement_tracking_counts": counter_payload(
            result.source_requirement_tracking_counts
        ),
        "source_requirement_tracking": [
            {
                "family_id": tracking.family_id,
                "source_type": tracking.source_type,
                "contract_family": tracking.contract_family,
                "network_access": tracking.network_access,
                "auth_reference_policy": tracking.auth_reference_policy,
                "source_schema_gate": tracking.source_schema_gate,
                "retry_policy": tracking.retry_policy,
                "failure_mode": tracking.failure_mode,
                "reader_status": tracking.reader_status,
                "reader_scope": tracking.reader_scope,
                "reader_module": tracking.reader_module,
                "reader_cli_role": tracking.reader_cli_role,
                "reader_capability_surface_id": tracking.reader_capability_surface_id,
                "tracking_status": tracking.tracking_status,
                "issue_count": tracking.issue_count,
            }
            for tracking in result.source_requirement_tracking
        ],
        "blocker_counts": counter_payload(result.blocker_counts),
        "blockers": [
            {"family_id": family_id, "blocker": blocker} for family_id, blocker in result.blockers
        ],
        "issue_counts": counter_payload(result.issue_counts),
        "issues": [
            {
                "family_id": family_id,
                "source_type": issue.source_type,
                "category": issue.category,
                "message": issue.message,
            }
            for family_id, issue in result.issues
        ],
    }


def add_issue(
    result: TrinoProductionCollectorAuditResult,
    family_id: str,
    category: str,
    message: str,
    *,
    source_type: str | None = None,
) -> None:
    issue = TrinoProductionCollectorIssue(
        category=category,
        message=message,
        source_type=source_type,
    )
    result.issue_counts[category] += 1
    result.issues.append((family_id, issue))


def counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}
