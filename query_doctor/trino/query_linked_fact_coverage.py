"""Raw-free audit model for Trino query-linked fact coverage closure.

This module describes the query-linked fact coverage gate. It checks current
fact/source contracts, but it does not collect from Trino, add new fact
mappings, or promote Trino beyond the current bounded local lanes.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from query_doctor.analyzer.engine_facts import (
    EngineFactDefinition,
    engine_fact_namespace_definitions,
)
from query_doctor.trino.source_contract_registry import (
    TrinoSourceContractRegistryEntry,
    trino_source_contract_registry,
)


TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND = "trino_query_linked_fact_coverage_audit_v1"
TRINO_QUERY_LINKED_FACT_COVERAGE_GATE = "trino_query_linked_fact_coverage"
TRINO_QUERY_LINKED_FACT_COVERAGE_STATUS = "not_closed"
TRINO_SQL_EXECUTION_STATUS = "not_performed"
TRINO_QUERY_LINKED_PRODUCTION_REVIEW_PROFILE = "production_review_query_linked_v1"
TRINO_QUERY_LINKED_PRODUCTION_REVIEW_PROFILE_STATUS = "ready"
TRINO_QUERY_LINKED_REQUIRED_CORE_FAMILIES = (
    "resource_group_queue_timing",
    "stage_summary_and_skew",
    "task_aggregate_failures_retries",
    "split_aggregate_count",
)
TRINO_QUERY_LINKED_REQUIRED_CORE_LINKAGE_SCOPES = (
    "resource_group_summary",
    "stage_summary",
    "task_aggregate",
    "split_aggregate",
)
TRINO_QUERY_LINKED_REQUIRED_SOURCE_GRANULARITIES = (
    "one_query_boundary",
    "one_query_summary",
)
TRINO_QUERY_LINKED_REQUIRED_OPEN_BLOCKER_FAMILIES = (
    "operator_level_metrics",
    "split_level_distribution",
    "telemetry_jmx_openmetrics",
)
TRINO_QUERY_LINKED_OPERATOR_CONNECTOR_TELEMETRY_PROFILE = "operator_connector_telemetry_decision_v1"
TRINO_QUERY_LINKED_OPERATOR_CONNECTOR_TELEMETRY_PROFILE_STATUS = "ready"
TRINO_QUERY_LINKED_BOUNDED_SUPPORTED_DECISION = "bounded_supported"
TRINO_QUERY_LINKED_UNSUPPORTED_GAP_DECISION = "deliberate_unsupported_gap"
TRINO_QUERY_LINKED_REQUIRED_OPERATOR_CONNECTOR_TELEMETRY_DECISIONS = (
    ("connector_metric_signal", TRINO_QUERY_LINKED_BOUNDED_SUPPORTED_DECISION),
    ("operator_level_metrics", TRINO_QUERY_LINKED_UNSUPPORTED_GAP_DECISION),
    ("split_level_distribution", TRINO_QUERY_LINKED_UNSUPPORTED_GAP_DECISION),
    ("telemetry_jmx_openmetrics", TRINO_QUERY_LINKED_UNSUPPORTED_GAP_DECISION),
)

TRINO_QUERY_LINKED_ALLOWED_CURRENT_LOCAL_PRODUCT_SURFACES = frozenset(
    {
        "blocked",
        "trino_query_id_local_production_details_python_report_optimizer_guidance",
    }
)
TRINO_QUERY_LINKED_ALLOWED_CURRENT_LOCAL_BROWSER_OUTPUT = frozenset(
    {
        "blocked",
        "python_report_and_optimizer_guidance_after_raw_free_case_materialization",
    }
)
TRINO_QUERY_LINKED_ALLOWED_CURRENT_LOCAL_OPTIMIZER = frozenset(
    {
        "blocked",
        "guidance_only_after_raw_free_case_materialization",
    }
)
TRINO_QUERY_LINKED_FORBIDDEN_SOURCE_TYPES = frozenset(
    {
        "trino_operator_metrics",
        "trino_operator_pipeline_metrics",
        "trino_split_detail_collection",
        "trino_task_detail_collection",
        "trino_jmx_metrics",
        "trino_openmetrics_scrape",
        "trino_opentelemetry_trace",
        "trino_query_history_resource_collection",
        "trino_broad_stage_collection",
    }
)


@dataclass(frozen=True)
class TrinoQueryLinkedSourceRequirement:
    source_type: str
    contract_family: str
    source_granularity: str
    linkage_scope: str


@dataclass(frozen=True)
class TrinoQueryLinkedFactFamily:
    family_id: str
    readiness_state: str
    production_blocker: str
    required_fact_ids: tuple[str, ...] = ()
    source_requirements: tuple[TrinoQueryLinkedSourceRequirement, ...] = ()


@dataclass(frozen=True)
class TrinoQueryLinkedFactCoverageIssue:
    category: str
    message: str
    requirement_type: str | None = None
    requirement_id: str | None = None


@dataclass(frozen=True)
class TrinoQueryLinkedRequirementTracking:
    family_id: str
    requirement_type: str
    requirement_id: str
    tracking_status: str
    issue_count: int


@dataclass(frozen=True)
class TrinoQueryLinkedCoverageProfileTracking:
    requirement_id: str
    counter_name: str
    tracking_status: str
    observed_count: int
    required_count: int


@dataclass(frozen=True)
class TrinoQueryLinkedOperatorConnectorTelemetryDecision:
    family_id: str
    decision: str
    linkage_contract: str
    reason: str


@dataclass(frozen=True)
class TrinoQueryLinkedDecisionProfileTracking:
    family_id: str
    expected_decision: str
    tracking_status: str


@dataclass
class TrinoQueryLinkedFactCoverageAuditResult:
    family_count: int = 0
    fact_requirement_count: int = 0
    source_requirement_count: int = 0
    source_backed_family_count: int = 0
    open_blocker_count: int = 0
    forbidden_source_type_count: int = 0
    status_counts: Counter[str] = field(default_factory=Counter)
    fact_scope_counts: Counter[str] = field(default_factory=Counter)
    source_contract_counts: Counter[str] = field(default_factory=Counter)
    source_surface_counts: Counter[str] = field(default_factory=Counter)
    source_granularity_counts: Counter[str] = field(default_factory=Counter)
    linkage_scope_counts: Counter[str] = field(default_factory=Counter)
    query_linked_requirement_tracking_counts: Counter[str] = field(default_factory=Counter)
    coverage_profile_tracking_counts: Counter[str] = field(default_factory=Counter)
    operator_connector_telemetry_decision_counts: Counter[str] = field(default_factory=Counter)
    operator_connector_telemetry_decision_tracking_counts: Counter[str] = field(
        default_factory=Counter
    )
    blocker_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    blockers: list[tuple[str, str]] = field(default_factory=list)
    query_linked_requirement_tracking: list[TrinoQueryLinkedRequirementTracking] = field(
        default_factory=list
    )
    coverage_profile_tracking: list[TrinoQueryLinkedCoverageProfileTracking] = field(
        default_factory=list
    )
    operator_connector_telemetry_decisions: list[
        TrinoQueryLinkedOperatorConnectorTelemetryDecision
    ] = field(default_factory=list)
    operator_connector_telemetry_decision_tracking: list[
        TrinoQueryLinkedDecisionProfileTracking
    ] = field(default_factory=list)
    issues: list[tuple[str, TrinoQueryLinkedFactCoverageIssue]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issue_counts


TRINO_QUERY_LINKED_FACT_FAMILIES = (
    TrinoQueryLinkedFactFamily(
        family_id="resource_group_queue_timing",
        readiness_state="bounded_compact_fact",
        production_blocker="summary_only_no_resource_group_history_or_full_admission_model",
        required_fact_ids=("trino_resource_group_queue_time_ms", "no_admission_model"),
        source_requirements=(
            TrinoQueryLinkedSourceRequirement(
                source_type="event_listener_export",
                contract_family="evidence_package_sample",
                source_granularity="one_query_summary",
                linkage_scope="resource_group_summary",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="http_event_listener_archive",
                contract_family="event_source_contract",
                source_granularity="one_query_summary",
                linkage_scope="resource_group_summary",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="local_event_store_import",
                contract_family="local_event_store_import",
                source_granularity="one_query_summary",
                linkage_scope="resource_group_summary",
            ),
        ),
    ),
    TrinoQueryLinkedFactFamily(
        family_id="stage_summary_and_skew",
        readiness_state="bounded_compact_fact",
        production_blocker="stage_summary_only_no_stage_lifecycle_or_operator_tree",
        required_fact_ids=(
            "trino_stage_count",
            "trino_stage_skew_candidate",
            "no_fragment_lifecycle",
        ),
        source_requirements=(
            TrinoQueryLinkedSourceRequirement(
                source_type="statement_stats_export",
                contract_family="evidence_package_sample",
                source_granularity="one_query_summary",
                linkage_scope="stage_summary",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="query_detail_export",
                contract_family="evidence_package_sample",
                source_granularity="one_query_summary",
                linkage_scope="stage_summary",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="local_statement_stats_import",
                contract_family="local_statement_stats_import",
                source_granularity="one_query_summary",
                linkage_scope="stage_summary",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="local_query_detail_import",
                contract_family="local_query_detail_import",
                source_granularity="one_query_summary",
                linkage_scope="stage_summary",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="http_query_detail_archive",
                contract_family="query_detail_archive_source_contract",
                source_granularity="one_query_summary",
                linkage_scope="stage_summary",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="local_query_info_pruned_import",
                contract_family="coordinator_query_info_source_contract",
                source_granularity="one_query_boundary",
                linkage_scope="stage_summary",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="trino_coordinator_query_info_pruned_import",
                contract_family="coordinator_query_info_source_contract",
                source_granularity="one_query_boundary",
                linkage_scope="stage_summary",
            ),
        ),
    ),
    TrinoQueryLinkedFactFamily(
        family_id="task_aggregate_failures_retries",
        readiness_state="bounded_compact_fact",
        production_blocker="task_aggregate_summary_only_no_task_identity_or_timeline",
        required_fact_ids=(
            "trino_task_count",
            "trino_failed_task_count",
            "trino_retried_task_count",
        ),
        source_requirements=(
            TrinoQueryLinkedSourceRequirement(
                source_type="query_detail_export",
                contract_family="evidence_package_sample",
                source_granularity="one_query_summary",
                linkage_scope="task_aggregate",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="local_query_detail_import",
                contract_family="local_query_detail_import",
                source_granularity="one_query_summary",
                linkage_scope="task_aggregate",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="http_query_detail_archive",
                contract_family="query_detail_archive_source_contract",
                source_granularity="one_query_summary",
                linkage_scope="task_aggregate",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="local_query_info_pruned_import",
                contract_family="coordinator_query_info_source_contract",
                source_granularity="one_query_boundary",
                linkage_scope="task_aggregate",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="trino_coordinator_query_info_pruned_import",
                contract_family="coordinator_query_info_source_contract",
                source_granularity="one_query_boundary",
                linkage_scope="task_aggregate",
            ),
        ),
    ),
    TrinoQueryLinkedFactFamily(
        family_id="split_aggregate_count",
        readiness_state="bounded_compact_fact",
        production_blocker="completed_split_count_only_no_split_distribution_or_lifecycle",
        required_fact_ids=("trino_completed_split_count", "no_fragment_lifecycle"),
        source_requirements=(
            TrinoQueryLinkedSourceRequirement(
                source_type="statement_stats_export",
                contract_family="evidence_package_sample",
                source_granularity="one_query_summary",
                linkage_scope="split_aggregate",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="query_detail_export",
                contract_family="evidence_package_sample",
                source_granularity="one_query_summary",
                linkage_scope="split_aggregate",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="local_statement_stats_import",
                contract_family="local_statement_stats_import",
                source_granularity="one_query_summary",
                linkage_scope="split_aggregate",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="local_query_detail_import",
                contract_family="local_query_detail_import",
                source_granularity="one_query_summary",
                linkage_scope="split_aggregate",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="http_query_detail_archive",
                contract_family="query_detail_archive_source_contract",
                source_granularity="one_query_summary",
                linkage_scope="split_aggregate",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="local_query_info_pruned_import",
                contract_family="coordinator_query_info_source_contract",
                source_granularity="one_query_boundary",
                linkage_scope="split_aggregate",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="trino_coordinator_query_info_pruned_import",
                contract_family="coordinator_query_info_source_contract",
                source_granularity="one_query_boundary",
                linkage_scope="split_aggregate",
            ),
        ),
    ),
    TrinoQueryLinkedFactFamily(
        family_id="connector_metric_signal",
        readiness_state="bounded_compact_fact",
        production_blocker=(
            "checked_present_absent_signal_only_no_connector_names_metric_names_or_operator_linkage"
        ),
        required_fact_ids=("trino_connector_metric_signal",),
        source_requirements=(
            TrinoQueryLinkedSourceRequirement(
                source_type="statement_stats_export",
                contract_family="evidence_package_sample",
                source_granularity="one_query_summary",
                linkage_scope="connector_signal",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="query_detail_export",
                contract_family="evidence_package_sample",
                source_granularity="one_query_summary",
                linkage_scope="connector_signal",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="local_statement_stats_import",
                contract_family="local_statement_stats_import",
                source_granularity="one_query_summary",
                linkage_scope="connector_signal",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="local_query_detail_import",
                contract_family="local_query_detail_import",
                source_granularity="one_query_summary",
                linkage_scope="connector_signal",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="http_query_detail_archive",
                contract_family="query_detail_archive_source_contract",
                source_granularity="one_query_summary",
                linkage_scope="connector_signal",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="local_query_info_pruned_import",
                contract_family="coordinator_query_info_source_contract",
                source_granularity="one_query_boundary",
                linkage_scope="connector_signal",
            ),
            TrinoQueryLinkedSourceRequirement(
                source_type="trino_coordinator_query_info_pruned_import",
                contract_family="coordinator_query_info_source_contract",
                source_granularity="one_query_boundary",
                linkage_scope="connector_signal",
            ),
        ),
    ),
    TrinoQueryLinkedFactFamily(
        family_id="operator_level_metrics",
        readiness_state="open_required_future_work",
        production_blocker="no_operator_level_source_contract_or_raw_free_mapping",
    ),
    TrinoQueryLinkedFactFamily(
        family_id="split_level_distribution",
        readiness_state="open_required_future_work",
        production_blocker="no_split_level_source_contract_or_raw_free_distribution_mapping",
    ),
    TrinoQueryLinkedFactFamily(
        family_id="telemetry_jmx_openmetrics",
        readiness_state="open_required_future_work",
        production_blocker="no_jmx_openmetrics_or_opentelemetry_query_linkage_contract",
    ),
)


def audit_trino_query_linked_fact_coverage(
    *,
    families: Iterable[TrinoQueryLinkedFactFamily] = TRINO_QUERY_LINKED_FACT_FAMILIES,
    fact_definitions: Iterable[EngineFactDefinition] | None = None,
    source_registry: Iterable[TrinoSourceContractRegistryEntry] | None = None,
) -> TrinoQueryLinkedFactCoverageAuditResult:
    result = TrinoQueryLinkedFactCoverageAuditResult()
    definitions = {
        definition.fact_id: definition
        for definition in (
            engine_fact_namespace_definitions()
            if fact_definitions is None
            else tuple(fact_definitions)
        )
    }
    registry = {
        entry.source_type: entry
        for entry in (
            trino_source_contract_registry() if source_registry is None else tuple(source_registry)
        )
    }

    family_tuple = tuple(families)
    for family in family_tuple:
        result.family_count += 1
        result.status_counts[family.readiness_state] += 1
        result.open_blocker_count += 1
        result.blocker_counts[family.production_blocker] += 1
        result.blockers.append((family.family_id, family.production_blocker))
        if family.source_requirements:
            result.source_backed_family_count += 1
        for fact_id in family.required_fact_ids:
            result.fact_requirement_count += 1
            audit_required_fact(result, family.family_id, fact_id, definitions)
        for requirement in family.source_requirements:
            result.source_requirement_count += 1
            audit_source_requirement(result, family.family_id, requirement, registry)

    audit_forbidden_sources(result, registry.values())
    finalize_query_linked_requirement_tracking(result, family_tuple)
    audit_query_linked_coverage_profile(result, family_tuple)
    audit_operator_connector_telemetry_decisions(result, family_tuple)
    return result


def audit_required_fact(
    result: TrinoQueryLinkedFactCoverageAuditResult,
    family_id: str,
    fact_id: str,
    definitions: dict[str, EngineFactDefinition],
) -> None:
    definition = definitions.get(fact_id)
    if definition is None:
        add_issue(
            result,
            family_id,
            "trino_query_linked_fact_missing",
            "A required Trino query-linked fact is not registered.",
            requirement_type="fact",
            requirement_id=fact_id,
        )
        return
    if "trino" not in definition.allowed_engines:
        add_issue(
            result,
            family_id,
            "trino_query_linked_fact_not_allowed",
            "A required Trino query-linked fact is not allowed for Trino.",
            requirement_type="fact",
            requirement_id=fact_id,
        )
        return
    result.fact_scope_counts[definition.scope] += 1


def audit_source_requirement(
    result: TrinoQueryLinkedFactCoverageAuditResult,
    family_id: str,
    requirement: TrinoQueryLinkedSourceRequirement,
    registry: dict[str, TrinoSourceContractRegistryEntry],
) -> None:
    result.source_granularity_counts[requirement.source_granularity] += 1
    result.linkage_scope_counts[requirement.linkage_scope] += 1
    entry = registry.get(requirement.source_type)
    if entry is None:
        add_issue(
            result,
            family_id,
            "trino_query_linked_source_missing",
            "A required Trino query-linked source contract is not registered.",
            requirement_type="source",
            requirement_id=requirement.source_type,
        )
        return
    result.source_contract_counts[entry.contract_family] += 1
    result.source_surface_counts[entry.surface_class] += 1
    if entry.contract_family != requirement.contract_family:
        add_issue(
            result,
            family_id,
            "trino_query_linked_source_contract_drift",
            "A Trino query-linked source moved to an unexpected contract family.",
            requirement_type="source",
            requirement_id=requirement.source_type,
        )
    if not entry.required_bounds:
        add_issue(
            result,
            family_id,
            "trino_query_linked_source_missing_bounds",
            "A Trino query-linked source must keep explicit bounds.",
            requirement_type="source",
            requirement_id=requirement.source_type,
        )
    if entry.raw_payload_storage != "forbidden":
        add_issue(
            result,
            family_id,
            "trino_query_linked_source_raw_storage_drift",
            "Trino query-linked source raw payload storage must stay forbidden.",
            requirement_type="source",
            requirement_id=requirement.source_type,
        )
    if entry.sql_execution != TRINO_SQL_EXECUTION_STATUS:
        add_issue(
            result,
            family_id,
            "trino_query_linked_source_sql_execution_drift",
            "Trino query-linked source requirements must not execute SQL.",
            requirement_type="source",
            requirement_id=requirement.source_type,
        )
    if entry.product_surfaces not in TRINO_QUERY_LINKED_ALLOWED_CURRENT_LOCAL_PRODUCT_SURFACES:
        add_issue(
            result,
            family_id,
            "trino_query_linked_source_product_surface_drift",
            "Trino query-linked source product surfaces must stay blocked or in current local lanes.",
            requirement_type="source",
            requirement_id=requirement.source_type,
        )
    if entry.browser_report_output not in TRINO_QUERY_LINKED_ALLOWED_CURRENT_LOCAL_BROWSER_OUTPUT:
        add_issue(
            result,
            family_id,
            "trino_query_linked_source_browser_output_drift",
            "Trino query-linked source browser/report output must stay blocked or raw-free local.",
            requirement_type="source",
            requirement_id=requirement.source_type,
        )
    if entry.details_report_output not in TRINO_QUERY_LINKED_ALLOWED_CURRENT_LOCAL_BROWSER_OUTPUT:
        add_issue(
            result,
            family_id,
            "trino_query_linked_source_details_output_drift",
            "Trino query-linked source Details/report output must stay blocked or raw-free local.",
            requirement_type="source",
            requirement_id=requirement.source_type,
        )
    if entry.optimizer_behavior not in TRINO_QUERY_LINKED_ALLOWED_CURRENT_LOCAL_OPTIMIZER:
        add_issue(
            result,
            family_id,
            "trino_query_linked_source_optimizer_drift",
            "Trino query-linked source optimizer behavior must stay blocked or guidance-only local.",
            requirement_type="source",
            requirement_id=requirement.source_type,
        )


def audit_forbidden_sources(
    result: TrinoQueryLinkedFactCoverageAuditResult,
    source_registry: Iterable[TrinoSourceContractRegistryEntry],
) -> None:
    for entry in source_registry:
        if entry.source_type in TRINO_QUERY_LINKED_FORBIDDEN_SOURCE_TYPES:
            result.forbidden_source_type_count += 1
            add_issue(
                result,
                "forbidden_query_linked_sources",
                "trino_forbidden_query_linked_source_registered",
                "A broad Trino query-linked source was registered before this gate closed.",
                requirement_type="forbidden_source",
                requirement_id=entry.source_type,
            )


def finalize_query_linked_requirement_tracking(
    result: TrinoQueryLinkedFactCoverageAuditResult,
    families: tuple[TrinoQueryLinkedFactFamily, ...],
) -> None:
    result.query_linked_requirement_tracking.clear()
    result.query_linked_requirement_tracking_counts.clear()
    for family in families:
        for fact_id in family.required_fact_ids:
            _append_query_linked_requirement_tracking(
                result,
                family_id=family.family_id,
                requirement_type="fact",
                requirement_id=fact_id,
            )
        for requirement in family.source_requirements:
            _append_query_linked_requirement_tracking(
                result,
                family_id=family.family_id,
                requirement_type="source",
                requirement_id=requirement.source_type,
            )


def audit_query_linked_coverage_profile(
    result: TrinoQueryLinkedFactCoverageAuditResult,
    families: tuple[TrinoQueryLinkedFactFamily, ...],
) -> None:
    families_by_id = {family.family_id: family for family in families}
    present_core_families = {
        family_id
        for family_id in TRINO_QUERY_LINKED_REQUIRED_CORE_FAMILIES
        if _family_is_bounded_source_backed(families_by_id.get(family_id))
    }
    present_blocker_families = {
        family_id
        for family_id in TRINO_QUERY_LINKED_REQUIRED_OPEN_BLOCKER_FAMILIES
        if _family_is_open_blocker(families_by_id.get(family_id))
    }
    _append_coverage_profile_tracking(
        result,
        requirement_id="require_core_fact_families",
        counter_name="families",
        observed_count=len(present_core_families),
        required_count=len(TRINO_QUERY_LINKED_REQUIRED_CORE_FAMILIES),
    )
    _append_coverage_profile_tracking(
        result,
        requirement_id="require_core_linkage_scopes",
        counter_name="linkage_scopes",
        observed_count=sum(
            1
            for scope in TRINO_QUERY_LINKED_REQUIRED_CORE_LINKAGE_SCOPES
            if result.linkage_scope_counts[scope] > 0
        ),
        required_count=len(TRINO_QUERY_LINKED_REQUIRED_CORE_LINKAGE_SCOPES),
    )
    _append_coverage_profile_tracking(
        result,
        requirement_id="require_source_granularities",
        counter_name="source_granularity",
        observed_count=sum(
            1
            for granularity in TRINO_QUERY_LINKED_REQUIRED_SOURCE_GRANULARITIES
            if result.source_granularity_counts[granularity] > 0
        ),
        required_count=len(TRINO_QUERY_LINKED_REQUIRED_SOURCE_GRANULARITIES),
    )
    _append_coverage_profile_tracking(
        result,
        requirement_id="require_open_blocker_families",
        counter_name="open_blockers",
        observed_count=len(present_blocker_families),
        required_count=len(TRINO_QUERY_LINKED_REQUIRED_OPEN_BLOCKER_FAMILIES),
    )


def audit_operator_connector_telemetry_decisions(
    result: TrinoQueryLinkedFactCoverageAuditResult,
    families: tuple[TrinoQueryLinkedFactFamily, ...],
) -> None:
    families_by_id = {family.family_id: family for family in families}
    for (
        family_id,
        expected_decision,
    ) in TRINO_QUERY_LINKED_REQUIRED_OPERATOR_CONNECTOR_TELEMETRY_DECISIONS:
        family = families_by_id.get(family_id)
        accepted = _decision_matches_family(family, expected_decision)
        if accepted and family is not None:
            _append_operator_connector_telemetry_decision(
                result,
                family=family,
                decision=expected_decision,
            )
        _append_operator_connector_telemetry_decision_tracking(
            result,
            family_id=family_id,
            expected_decision=expected_decision,
            accepted=accepted,
        )


def _decision_matches_family(
    family: TrinoQueryLinkedFactFamily | None,
    expected_decision: str,
) -> bool:
    if expected_decision == TRINO_QUERY_LINKED_BOUNDED_SUPPORTED_DECISION:
        return _family_is_bounded_source_backed(family)
    if expected_decision == TRINO_QUERY_LINKED_UNSUPPORTED_GAP_DECISION:
        return _family_is_open_blocker(family)
    return False


def _append_operator_connector_telemetry_decision(
    result: TrinoQueryLinkedFactCoverageAuditResult,
    *,
    family: TrinoQueryLinkedFactFamily,
    decision: str,
) -> None:
    if decision == TRINO_QUERY_LINKED_BOUNDED_SUPPORTED_DECISION:
        linkage_contract = "bounded_raw_free_one_query_linkage"
    else:
        linkage_contract = "missing_raw_free_query_linkage_contract"
    result.operator_connector_telemetry_decisions.append(
        TrinoQueryLinkedOperatorConnectorTelemetryDecision(
            family_id=family.family_id,
            decision=decision,
            linkage_contract=linkage_contract,
            reason=family.production_blocker,
        )
    )
    result.operator_connector_telemetry_decision_counts[decision] += 1


def _append_operator_connector_telemetry_decision_tracking(
    result: TrinoQueryLinkedFactCoverageAuditResult,
    *,
    family_id: str,
    expected_decision: str,
    accepted: bool,
) -> None:
    tracking_status = "accepted" if accepted else "insufficient"
    result.operator_connector_telemetry_decision_tracking.append(
        TrinoQueryLinkedDecisionProfileTracking(
            family_id=family_id,
            expected_decision=expected_decision,
            tracking_status=tracking_status,
        )
    )
    result.operator_connector_telemetry_decision_tracking_counts[tracking_status] += 1
    if not accepted:
        add_issue(
            result,
            "operator_connector_telemetry_decision_profile",
            "trino_query_linked_operator_connector_telemetry_decision_gap",
            "Trino operator/connector/telemetry query-linked support decision is incomplete.",
            requirement_type="operator_connector_telemetry_decision",
            requirement_id=family_id,
        )


def _family_is_bounded_source_backed(family: TrinoQueryLinkedFactFamily | None) -> bool:
    return (
        family is not None
        and family.readiness_state == "bounded_compact_fact"
        and bool(family.required_fact_ids)
        and bool(family.source_requirements)
    )


def _family_is_open_blocker(family: TrinoQueryLinkedFactFamily | None) -> bool:
    return family is not None and family.readiness_state == "open_required_future_work"


def _append_coverage_profile_tracking(
    result: TrinoQueryLinkedFactCoverageAuditResult,
    *,
    requirement_id: str,
    counter_name: str,
    observed_count: int,
    required_count: int,
) -> None:
    tracking_status = _coverage_profile_tracking_status(observed_count, required_count)
    result.coverage_profile_tracking.append(
        TrinoQueryLinkedCoverageProfileTracking(
            requirement_id=requirement_id,
            counter_name=counter_name,
            tracking_status=tracking_status,
            observed_count=observed_count,
            required_count=required_count,
        )
    )
    result.coverage_profile_tracking_counts[tracking_status] += 1
    if tracking_status != "accepted":
        add_issue(
            result,
            "coverage_profile",
            "trino_query_linked_coverage_profile_gap",
            "Trino query-linked production-review profile coverage is incomplete.",
            requirement_type="coverage_profile",
            requirement_id=requirement_id,
        )


def _coverage_profile_tracking_status(observed_count: int, required_count: int) -> str:
    if required_count <= 0:
        return "not_required"
    if observed_count >= required_count:
        return "accepted"
    return "insufficient"


def _coverage_profile_status(result: TrinoQueryLinkedFactCoverageAuditResult) -> str:
    if not result.coverage_profile_tracking:
        return "not_required"
    if set(result.coverage_profile_tracking_counts) == {"accepted"}:
        return TRINO_QUERY_LINKED_PRODUCTION_REVIEW_PROFILE_STATUS
    return "failed"


def _operator_connector_telemetry_profile_status(
    result: TrinoQueryLinkedFactCoverageAuditResult,
) -> str:
    if not result.operator_connector_telemetry_decision_tracking:
        return "not_required"
    if set(result.operator_connector_telemetry_decision_tracking_counts) == {"accepted"}:
        return TRINO_QUERY_LINKED_OPERATOR_CONNECTOR_TELEMETRY_PROFILE_STATUS
    return "failed"


def _append_query_linked_requirement_tracking(
    result: TrinoQueryLinkedFactCoverageAuditResult,
    *,
    family_id: str,
    requirement_type: str,
    requirement_id: str,
) -> None:
    issues = _issues_for_requirement(
        result,
        family_id=family_id,
        requirement_type=requirement_type,
        requirement_id=requirement_id,
    )
    tracking_status = _query_linked_requirement_tracking_status(issues)
    result.query_linked_requirement_tracking.append(
        TrinoQueryLinkedRequirementTracking(
            family_id=family_id,
            requirement_type=requirement_type,
            requirement_id=requirement_id,
            tracking_status=tracking_status,
            issue_count=len(issues),
        )
    )
    result.query_linked_requirement_tracking_counts[tracking_status] += 1


def _issues_for_requirement(
    result: TrinoQueryLinkedFactCoverageAuditResult,
    *,
    family_id: str,
    requirement_type: str,
    requirement_id: str,
) -> tuple[TrinoQueryLinkedFactCoverageIssue, ...]:
    return tuple(
        issue
        for issue_family_id, issue in result.issues
        if issue_family_id == family_id
        and issue.requirement_type == requirement_type
        and issue.requirement_id == requirement_id
    )


def _query_linked_requirement_tracking_status(
    issues: tuple[TrinoQueryLinkedFactCoverageIssue, ...],
) -> str:
    if any(
        issue.category in {"trino_query_linked_fact_missing", "trino_query_linked_source_missing"}
        for issue in issues
    ):
        return "missing"
    if issues:
        return "invalid"
    return "accepted"


def query_linked_fact_coverage_summary_payload(
    result: TrinoQueryLinkedFactCoverageAuditResult,
    *,
    status: str,
) -> dict[str, Any]:
    return {
        "summary_kind": TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
        "status": status,
        "closure_gate": TRINO_QUERY_LINKED_FACT_COVERAGE_GATE,
        "query_linked_fact_coverage_status": TRINO_QUERY_LINKED_FACT_COVERAGE_STATUS,
        "broader_production_closure_status": "not_closed",
        "trino_sql_execution": TRINO_SQL_EXECUTION_STATUS,
        "family_count": result.family_count,
        "fact_requirement_count": result.fact_requirement_count,
        "source_requirement_count": result.source_requirement_count,
        "source_backed_family_count": result.source_backed_family_count,
        "open_blocker_count": result.open_blocker_count,
        "forbidden_source_type_count": result.forbidden_source_type_count,
        "status_counts": counter_payload(result.status_counts),
        "fact_scope_counts": counter_payload(result.fact_scope_counts),
        "source_contract_counts": counter_payload(result.source_contract_counts),
        "source_surface_counts": counter_payload(result.source_surface_counts),
        "source_granularity_counts": counter_payload(result.source_granularity_counts),
        "linkage_scope_counts": counter_payload(result.linkage_scope_counts),
        "coverage_profile": TRINO_QUERY_LINKED_PRODUCTION_REVIEW_PROFILE,
        "coverage_profile_status": _coverage_profile_status(result),
        "coverage_profile_requirements": {
            "required_core_families": list(TRINO_QUERY_LINKED_REQUIRED_CORE_FAMILIES),
            "required_core_linkage_scopes": list(TRINO_QUERY_LINKED_REQUIRED_CORE_LINKAGE_SCOPES),
            "required_source_granularities": list(TRINO_QUERY_LINKED_REQUIRED_SOURCE_GRANULARITIES),
            "required_open_blocker_families": list(
                TRINO_QUERY_LINKED_REQUIRED_OPEN_BLOCKER_FAMILIES
            ),
        },
        "coverage_profile_tracking_counts": counter_payload(
            result.coverage_profile_tracking_counts
        ),
        "coverage_profile_tracking": [
            {
                "requirement_id": tracking.requirement_id,
                "counter_name": tracking.counter_name,
                "tracking_status": tracking.tracking_status,
                "observed_count": tracking.observed_count,
                "required_count": tracking.required_count,
            }
            for tracking in result.coverage_profile_tracking
        ],
        "operator_connector_telemetry_profile": (
            TRINO_QUERY_LINKED_OPERATOR_CONNECTOR_TELEMETRY_PROFILE
        ),
        "operator_connector_telemetry_profile_status": (
            _operator_connector_telemetry_profile_status(result)
        ),
        "operator_connector_telemetry_decision_requirements": {
            "required_bounded_supported_families": [
                family_id
                for family_id, decision in (
                    TRINO_QUERY_LINKED_REQUIRED_OPERATOR_CONNECTOR_TELEMETRY_DECISIONS
                )
                if decision == TRINO_QUERY_LINKED_BOUNDED_SUPPORTED_DECISION
            ],
            "required_unsupported_gap_families": [
                family_id
                for family_id, decision in (
                    TRINO_QUERY_LINKED_REQUIRED_OPERATOR_CONNECTOR_TELEMETRY_DECISIONS
                )
                if decision == TRINO_QUERY_LINKED_UNSUPPORTED_GAP_DECISION
            ],
        },
        "operator_connector_telemetry_decision_counts": counter_payload(
            result.operator_connector_telemetry_decision_counts
        ),
        "operator_connector_telemetry_decision_tracking_counts": counter_payload(
            result.operator_connector_telemetry_decision_tracking_counts
        ),
        "operator_connector_telemetry_decisions": [
            {
                "family": decision.family_id,
                "decision": decision.decision,
                "linkage_contract": decision.linkage_contract,
                "reason": decision.reason,
            }
            for decision in result.operator_connector_telemetry_decisions
        ],
        "operator_connector_telemetry_decision_tracking": [
            {
                "family": tracking.family_id,
                "expected_decision": tracking.expected_decision,
                "tracking_status": tracking.tracking_status,
            }
            for tracking in result.operator_connector_telemetry_decision_tracking
        ],
        "query_linked_requirement_tracking_counts": counter_payload(
            result.query_linked_requirement_tracking_counts
        ),
        "query_linked_requirement_tracking": [
            {
                "family": tracking.family_id,
                "requirement_type": tracking.requirement_type,
                "requirement_id": tracking.requirement_id,
                "tracking_status": tracking.tracking_status,
                "issue_count": tracking.issue_count,
            }
            for tracking in result.query_linked_requirement_tracking
        ],
        "blocker_counts": counter_payload(result.blocker_counts),
        "issue_counts": counter_payload(result.issue_counts),
        "blockers": [
            {"family": family_id, "reason": blocker} for family_id, blocker in result.blockers
        ],
        "issues": [
            {
                "family": family_id,
                "category": issue.category,
                "message": issue.message,
                "requirement_type": issue.requirement_type,
                "requirement_id": issue.requirement_id,
            }
            for family_id, issue in result.issues
        ],
    }


def counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def add_issue(
    result: TrinoQueryLinkedFactCoverageAuditResult,
    family_id: str,
    category: str,
    message: str,
    *,
    requirement_type: str | None = None,
    requirement_id: str | None = None,
) -> None:
    result.issue_counts[category] += 1
    result.issues.append(
        (
            family_id,
            TrinoQueryLinkedFactCoverageIssue(
                category=category,
                message=message,
                requirement_type=requirement_type,
                requirement_id=requirement_id,
            ),
        )
    )
