"""Raw-free audit model for Trino product metadata collection closure.

This module tracks the product metadata collection gate. It does not read
metadata, run Trino CLI, execute SQL, add browser/report output, or promote
Trino beyond the current local lanes.
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
from query_doctor.engines import EngineAdapter, get_engine_adapter
from query_doctor.engines.capabilities import EngineCapability, engine_capabilities
from query_doctor.trino.metadata_source_contract import TRINO_METADATA_SOURCE_TYPE
from query_doctor.trino.source_contract_registry import (
    TrinoSourceContractRegistryEntry,
    trino_source_contract_registry,
)


TRINO_PRODUCT_METADATA_COLLECTION_SUMMARY_KIND = "trino_product_metadata_collection_audit_v1"
TRINO_PRODUCT_METADATA_COLLECTION_GATE = "trino_product_metadata_collection"
TRINO_PRODUCT_METADATA_COLLECTION_STATUS = "not_closed"
TRINO_PRODUCT_METADATA_COLLECTION_CLOSURE_REASON = (
    "product_metadata_collection_requires_product_surface_design_and_browser_report_safety"
)
TRINO_PRODUCT_METADATA_SQL_EXECUTION_STATUS = "python_owned_metadata_statements_only_dev_gate"
TRINO_USER_SQL_EXECUTION_STATUS = "not_performed"
TRINO_PRODUCT_METADATA_PRODUCTION_REVIEW_PROFILE = "production_review_metadata_v1"
TRINO_PRODUCT_METADATA_PRODUCTION_REVIEW_PROFILE_STATUS = "ready"

TRINO_METADATA_REQUIRED_FACT_IDS = (
    "trino_metadata_summary_import",
    "trino_metadata_relations_checked",
    "trino_metadata_columns_checked",
    "trino_metadata_column_stats_present_count",
    "trino_metadata_column_stats_missing_count",
    "trino_metadata_stats_completeness",
    "no_live_metadata_collection",
    "no_metadata_identifier_output",
)
TRINO_PRODUCT_METADATA_FORBIDDEN_SOURCE_TYPES = frozenset(
    {
        "trino_product_metadata_collection",
        "trino_metadata_recent_scan",
        "trino_metadata_details_output",
        "trino_metadata_report_output",
        "trino_metadata_optimizer_context",
        "trino_metadata_object_crawl",
        "trino_metadata_system_table_sweep",
        "trino_metadata_user_sql",
        "trino_metadata_identifier_output",
    }
)
TRINO_METADATA_ALLOWED_PRODUCT_CAPABILITY_IDS = frozenset(
    {
        "recent_scan",
        "query_id_mode",
        "materialized_details",
        "materialized_python_report",
        "materialized_optimizer_guidance",
    }
)
TRINO_PRODUCT_METADATA_REQUIRED_SOURCE_FAMILIES = (
    "metadata_allowlist_source_contract",
    "metadata_cli_summary_builder",
    "local_metadata_summary_import",
)
TRINO_PRODUCT_METADATA_REQUIRED_OPEN_BLOCKER_FAMILIES = ("product_metadata_surfaces",)
TRINO_PRODUCT_METADATA_REQUIRED_SOURCE_SURFACES = (
    "metadata_source_contract",
    "contract_gated_metadata_cli",
    "local_contract_gated_import",
)
TRINO_PRODUCT_METADATA_REQUIRED_SQL_EXECUTION_STATUSES = (
    "not_performed",
    "python_owned_metadata_statements_only",
)
TRINO_PRODUCT_METADATA_REQUIRED_PRODUCT_SURFACE_REQUIREMENTS = (
    "adapter_metadata_collection_blocked",
    "forbidden_metadata_source_types",
    "metadata_product_capabilities_blocked",
)
TRINO_PRODUCT_METADATA_REQUIRED_REDACTION_FIELDS = (
    "raw_metadata_storage",
    "identifier_output",
    "browser_report_output",
    "details_report_output",
    "product_surfaces",
    "recent_scan",
    "optimizer_behavior",
)


@dataclass(frozen=True)
class TrinoProductMetadataSourceRequirement:
    source_type: str
    surface_class: str
    contract_family: str
    raw_policy: str
    network_access: str
    required_bounds: tuple[str, ...]
    raw_payload_storage: str
    raw_metadata_storage: str
    identifier_output: str
    browser_report_output: str
    details_report_output: str
    product_surfaces: str
    recent_scan: str
    optimizer_behavior: str
    sql_execution: str


@dataclass(frozen=True)
class TrinoProductMetadataFamily:
    family_id: str
    readiness_state: str
    production_blocker: str
    requirements: tuple[TrinoProductMetadataSourceRequirement, ...] = ()


@dataclass(frozen=True)
class TrinoProductMetadataIssue:
    category: str
    message: str
    requirement_type: str | None = None
    requirement_id: str | None = None


@dataclass(frozen=True)
class TrinoProductMetadataRequirementTracking:
    family_id: str
    requirement_type: str
    requirement_id: str
    tracking_status: str
    issue_count: int


@dataclass(frozen=True)
class TrinoProductMetadataProductionReviewTracking:
    requirement_id: str
    counter_name: str
    tracking_status: str
    observed_count: int
    required_count: int


@dataclass
class TrinoProductMetadataAuditResult:
    family_count: int = 0
    source_requirement_count: int = 0
    source_backed_family_count: int = 0
    required_fact_count: int = 0
    open_blocker_count: int = 0
    forbidden_source_type_count: int = 0
    product_capability_count: int = 0
    adapter_metadata_collection_enabled: bool = False
    status_counts: Counter[str] = field(default_factory=Counter)
    source_contract_counts: Counter[str] = field(default_factory=Counter)
    source_surface_counts: Counter[str] = field(default_factory=Counter)
    sql_execution_counts: Counter[str] = field(default_factory=Counter)
    fact_scope_counts: Counter[str] = field(default_factory=Counter)
    product_metadata_requirement_tracking_counts: Counter[str] = field(default_factory=Counter)
    production_review_tracking_counts: Counter[str] = field(default_factory=Counter)
    blocker_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    blockers: list[tuple[str, str]] = field(default_factory=list)
    product_metadata_requirement_tracking: list[TrinoProductMetadataRequirementTracking] = field(
        default_factory=list
    )
    production_review_tracking: list[TrinoProductMetadataProductionReviewTracking] = field(
        default_factory=list
    )
    issues: list[tuple[str, TrinoProductMetadataIssue]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issue_counts


TRINO_PRODUCT_METADATA_FAMILIES = (
    TrinoProductMetadataFamily(
        family_id="metadata_allowlist_source_contract",
        readiness_state="contract_check_only",
        production_blocker="allowlist_contract_only_no_product_metadata_reader",
        requirements=(
            TrinoProductMetadataSourceRequirement(
                source_type=TRINO_METADATA_SOURCE_TYPE,
                surface_class="metadata_source_contract",
                contract_family="metadata_source_contract",
                raw_policy="metadata_allowlist_contract_no_live_collection",
                network_access="not_performed",
                required_bounds=(
                    "max_relations",
                    "max_columns_per_relation",
                    "max_identifier_length",
                    "max_metadata_bytes",
                    "timeout_seconds",
                ),
                raw_payload_storage="not_applicable",
                raw_metadata_storage="forbidden",
                identifier_output="blocked",
                browser_report_output="blocked",
                details_report_output="blocked",
                product_surfaces="blocked",
                recent_scan="blocked",
                optimizer_behavior="blocked",
                sql_execution="not_performed",
            ),
        ),
    ),
    TrinoProductMetadataFamily(
        family_id="metadata_cli_summary_builder",
        readiness_state="dev_only_aggregate_cli_summary",
        production_blocker="operator_cli_summary_only_not_product_metadata_collection",
        requirements=(
            TrinoProductMetadataSourceRequirement(
                source_type="trino_metadata_cli_summary",
                surface_class="contract_gated_metadata_cli",
                contract_family="metadata_source_contract",
                raw_policy="operator_trino_cli_metadata_summary_after_allowlist_contract",
                network_access="operator_installed_trino_cli_only",
                required_bounds=(
                    "max_relations",
                    "max_columns_per_relation",
                    "max_identifier_length",
                    "max_metadata_bytes",
                    "timeout_seconds",
                ),
                raw_payload_storage="forbidden",
                raw_metadata_storage="forbidden",
                identifier_output="blocked",
                browser_report_output="blocked",
                details_report_output="blocked",
                product_surfaces="blocked",
                recent_scan="blocked",
                optimizer_behavior="blocked",
                sql_execution="python_owned_metadata_statements_only",
            ),
        ),
    ),
    TrinoProductMetadataFamily(
        family_id="local_metadata_summary_import",
        readiness_state="local_aggregate_import_only",
        production_blocker="aggregate_metadata_summary_only_not_details_report_or_optimizer_context",
        requirements=(
            TrinoProductMetadataSourceRequirement(
                source_type="local_metadata_summary_import",
                surface_class="local_contract_gated_import",
                contract_family="metadata_source_contract",
                raw_policy="already_sanitized_metadata_summary_after_allowlist_contract",
                network_access="not_performed",
                required_bounds=(
                    "max_relations",
                    "max_columns_per_relation",
                    "max_metadata_bytes",
                    "max_metadata_summary_depth",
                ),
                raw_payload_storage="not_applicable",
                raw_metadata_storage="forbidden",
                identifier_output="blocked",
                browser_report_output="blocked",
                details_report_output="blocked",
                product_surfaces="blocked",
                recent_scan="blocked",
                optimizer_behavior="blocked",
                sql_execution="not_performed",
            ),
        ),
    ),
    TrinoProductMetadataFamily(
        family_id="product_metadata_surfaces",
        readiness_state="open_required_future_work",
        production_blocker="no_recent_details_report_optimizer_or_shared_product_metadata_surface",
    ),
)


def audit_trino_product_metadata_collection(
    *,
    families: Iterable[TrinoProductMetadataFamily] = TRINO_PRODUCT_METADATA_FAMILIES,
    source_registry: Iterable[TrinoSourceContractRegistryEntry] | None = None,
    fact_definitions: Iterable[EngineFactDefinition] | None = None,
    trino_adapter: EngineAdapter | None = None,
    capabilities: Iterable[EngineCapability] | None = None,
) -> TrinoProductMetadataAuditResult:
    result = TrinoProductMetadataAuditResult()
    entries_by_type = {
        entry.source_type: entry
        for entry in (
            trino_source_contract_registry() if source_registry is None else source_registry
        )
    }
    definitions = {
        definition.fact_id: definition
        for definition in (
            engine_fact_namespace_definitions() if fact_definitions is None else fact_definitions
        )
    }
    trino = get_engine_adapter("trino") if trino_adapter is None else trino_adapter
    trino_capabilities = (
        engine_capabilities("trino") if capabilities is None else tuple(capabilities)
    )

    family_tuple = tuple(families)
    _audit_forbidden_source_types(result, entries_by_type)
    _audit_required_facts(result, definitions)
    _audit_adapter_and_capabilities(result, trino, trino_capabilities)
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
            _audit_source_requirement(result, family.family_id, requirement, entries_by_type)
    finalize_product_metadata_requirement_tracking(result, family_tuple)
    audit_product_metadata_production_review_profile(result, family_tuple)
    return result


def product_metadata_collection_summary_payload(
    result: TrinoProductMetadataAuditResult,
    *,
    status: str,
) -> dict[str, Any]:
    return {
        "summary_kind": TRINO_PRODUCT_METADATA_COLLECTION_SUMMARY_KIND,
        "status": status,
        "closure_gate": TRINO_PRODUCT_METADATA_COLLECTION_GATE,
        "product_metadata_collection_status": TRINO_PRODUCT_METADATA_COLLECTION_STATUS,
        "broader_production_closure_status": "not_closed",
        "closure_reason": TRINO_PRODUCT_METADATA_COLLECTION_CLOSURE_REASON,
        "trino_sql_execution": TRINO_USER_SQL_EXECUTION_STATUS,
        "metadata_cli_sql_execution": TRINO_PRODUCT_METADATA_SQL_EXECUTION_STATUS,
        "product_metadata_surfaces": "blocked",
        "metadata_summary_boundary": "aggregate_only_not_diagnosis",
        "adapter_metadata_collection": (
            "enabled" if result.adapter_metadata_collection_enabled else "blocked"
        ),
        "family_count": result.family_count,
        "source_backed_family_count": result.source_backed_family_count,
        "source_requirement_count": result.source_requirement_count,
        "required_fact_count": result.required_fact_count,
        "open_blocker_count": result.open_blocker_count,
        "forbidden_source_type_count": result.forbidden_source_type_count,
        "product_capability_count": result.product_capability_count,
        "status_counts": _counter_payload(result.status_counts),
        "source_contract_counts": _counter_payload(result.source_contract_counts),
        "source_surface_counts": _counter_payload(result.source_surface_counts),
        "sql_execution_counts": _counter_payload(result.sql_execution_counts),
        "fact_scope_counts": _counter_payload(result.fact_scope_counts),
        "product_metadata_requirement_tracking_counts": _counter_payload(
            result.product_metadata_requirement_tracking_counts
        ),
        "production_review_profile": TRINO_PRODUCT_METADATA_PRODUCTION_REVIEW_PROFILE,
        "production_review_profile_status": _production_review_profile_status(result),
        "production_review_requirements": {
            "required_source_families": list(TRINO_PRODUCT_METADATA_REQUIRED_SOURCE_FAMILIES),
            "required_open_blocker_families": list(
                TRINO_PRODUCT_METADATA_REQUIRED_OPEN_BLOCKER_FAMILIES
            ),
            "required_source_surfaces": list(TRINO_PRODUCT_METADATA_REQUIRED_SOURCE_SURFACES),
            "required_sql_execution_statuses": list(
                TRINO_PRODUCT_METADATA_REQUIRED_SQL_EXECUTION_STATUSES
            ),
            "required_product_surface_requirements": list(
                TRINO_PRODUCT_METADATA_REQUIRED_PRODUCT_SURFACE_REQUIREMENTS
            ),
            "required_redaction_fields": list(TRINO_PRODUCT_METADATA_REQUIRED_REDACTION_FIELDS),
        },
        "production_review_tracking_counts": _counter_payload(
            result.production_review_tracking_counts
        ),
        "production_review_tracking": [
            {
                "requirement_id": tracking.requirement_id,
                "counter_name": tracking.counter_name,
                "tracking_status": tracking.tracking_status,
                "observed_count": tracking.observed_count,
                "required_count": tracking.required_count,
            }
            for tracking in result.production_review_tracking
        ],
        "product_metadata_requirement_tracking": [
            {
                "family_id": tracking.family_id,
                "requirement_type": tracking.requirement_type,
                "requirement_id": tracking.requirement_id,
                "tracking_status": tracking.tracking_status,
                "issue_count": tracking.issue_count,
            }
            for tracking in result.product_metadata_requirement_tracking
        ],
        "blocker_counts": _counter_payload(result.blocker_counts),
        "blockers": [
            {"family_id": family_id, "blocker": blocker} for family_id, blocker in result.blockers
        ],
        "issue_counts": _counter_payload(result.issue_counts),
        "issues": [
            {
                "family_id": family_id,
                "category": issue.category,
                "message": issue.message,
                "requirement_type": issue.requirement_type,
                "requirement_id": issue.requirement_id,
            }
            for family_id, issue in result.issues
        ],
    }


def _audit_forbidden_source_types(
    result: TrinoProductMetadataAuditResult,
    entries_by_type: dict[str, TrinoSourceContractRegistryEntry],
) -> None:
    forbidden_present = sorted(
        TRINO_PRODUCT_METADATA_FORBIDDEN_SOURCE_TYPES & entries_by_type.keys()
    )
    result.forbidden_source_type_count = len(forbidden_present)
    for _source_type in forbidden_present:
        _add_issue(
            result,
            "product_metadata_surfaces",
            "trino_product_metadata_forbidden_source_registered",
            "A product metadata source type is registered before the metadata closure gate is implemented.",
            requirement_type="product_surface",
            requirement_id="forbidden_metadata_source_types",
        )


def _audit_required_facts(
    result: TrinoProductMetadataAuditResult,
    definitions: dict[str, EngineFactDefinition],
) -> None:
    for fact_id in TRINO_METADATA_REQUIRED_FACT_IDS:
        result.required_fact_count += 1
        definition = definitions.get(fact_id)
        if definition is None:
            _add_issue(
                result,
                "metadata_fact_namespace",
                "trino_product_metadata_required_fact_missing",
                "A required Trino metadata aggregate or limitation fact is not registered.",
                requirement_type="fact",
                requirement_id=fact_id,
            )
            continue
        if "trino" not in definition.allowed_engines:
            _add_issue(
                result,
                "metadata_fact_namespace",
                "trino_product_metadata_required_fact_not_allowed",
                "A required Trino metadata aggregate or limitation fact is not allowed for Trino.",
                requirement_type="fact",
                requirement_id=fact_id,
            )
        result.fact_scope_counts[definition.scope] += 1


def _audit_adapter_and_capabilities(
    result: TrinoProductMetadataAuditResult,
    trino_adapter: EngineAdapter,
    capabilities: Iterable[EngineCapability],
) -> None:
    result.adapter_metadata_collection_enabled = bool(
        getattr(trino_adapter, "supports_metadata_collection", False)
    )
    if result.adapter_metadata_collection_enabled:
        _add_issue(
            result,
            "product_metadata_surfaces",
            "trino_product_metadata_adapter_enabled",
            "Trino adapter metadata collection must stay blocked until the product gate closes.",
            requirement_type="product_surface",
            requirement_id="adapter_metadata_collection_blocked",
        )
    for capability in capabilities:
        if not capability.product_surface_allowed:
            continue
        result.product_capability_count += 1
        if capability.surface_id not in TRINO_METADATA_ALLOWED_PRODUCT_CAPABILITY_IDS:
            _add_issue(
                result,
                "product_metadata_surfaces",
                "trino_product_metadata_capability_enabled",
                "Trino product capabilities must not include product metadata collection.",
                requirement_type="product_surface",
                requirement_id="metadata_product_capabilities_blocked",
            )
        if "metadata" in capability.surface_id or "metadata" in capability.input_kind:
            _add_issue(
                result,
                "product_metadata_surfaces",
                "trino_product_metadata_capability_enabled",
                "Trino product capabilities must not include product metadata collection.",
                requirement_type="product_surface",
                requirement_id="metadata_product_capabilities_blocked",
            )


def _audit_source_requirement(
    result: TrinoProductMetadataAuditResult,
    family_id: str,
    requirement: TrinoProductMetadataSourceRequirement,
    entries_by_type: dict[str, TrinoSourceContractRegistryEntry],
) -> None:
    entry = entries_by_type.get(requirement.source_type)
    if entry is None:
        _add_issue(
            result,
            family_id,
            "trino_product_metadata_source_missing",
            "A required Trino metadata source contract registry entry is missing.",
            requirement_type="source",
            requirement_id=requirement.source_type,
        )
        return

    result.source_contract_counts[entry.contract_family] += 1
    result.source_surface_counts[entry.surface_class] += 1
    result.sql_execution_counts[entry.sql_execution] += 1
    expected_fields: tuple[tuple[str, Any], ...] = (
        ("surface_class", requirement.surface_class),
        ("contract_family", requirement.contract_family),
        ("raw_policy", requirement.raw_policy),
        ("network_access", requirement.network_access),
        ("raw_payload_storage", requirement.raw_payload_storage),
        ("raw_metadata_storage", requirement.raw_metadata_storage),
        ("identifier_output", requirement.identifier_output),
        ("browser_report_output", requirement.browser_report_output),
        ("details_report_output", requirement.details_report_output),
        ("product_surfaces", requirement.product_surfaces),
        ("recent_scan", requirement.recent_scan),
        ("optimizer_behavior", requirement.optimizer_behavior),
        ("sql_execution", requirement.sql_execution),
    )
    for field_name, expected_value in expected_fields:
        if getattr(entry, field_name) != expected_value:
            _add_issue(
                result,
                family_id,
                f"trino_product_metadata_source_{field_name}_drift",
                "A Trino metadata source registry entry drifted from the metadata closure boundary.",
                requirement_type="source",
                requirement_id=requirement.source_type,
            )
    missing_bounds = set(requirement.required_bounds) - set(entry.required_bounds)
    if missing_bounds:
        _add_issue(
            result,
            family_id,
            "trino_product_metadata_source_bounds_missing",
            "A Trino metadata source registry entry is missing required bounds.",
            requirement_type="source",
            requirement_id=requirement.source_type,
        )


def finalize_product_metadata_requirement_tracking(
    result: TrinoProductMetadataAuditResult,
    families: tuple[TrinoProductMetadataFamily, ...],
) -> None:
    result.product_metadata_requirement_tracking.clear()
    result.product_metadata_requirement_tracking_counts.clear()
    for fact_id in TRINO_METADATA_REQUIRED_FACT_IDS:
        _append_product_metadata_requirement_tracking(
            result,
            family_id="metadata_fact_namespace",
            requirement_type="fact",
            requirement_id=fact_id,
        )
    for family in families:
        for requirement in family.requirements:
            _append_product_metadata_requirement_tracking(
                result,
                family_id=family.family_id,
                requirement_type="source",
                requirement_id=requirement.source_type,
            )
    for requirement_id in (
        "adapter_metadata_collection_blocked",
        "forbidden_metadata_source_types",
        "metadata_product_capabilities_blocked",
    ):
        _append_product_metadata_requirement_tracking(
            result,
            family_id="product_metadata_surfaces",
            requirement_type="product_surface",
            requirement_id=requirement_id,
        )


def audit_product_metadata_production_review_profile(
    result: TrinoProductMetadataAuditResult,
    families: tuple[TrinoProductMetadataFamily, ...],
) -> None:
    families_by_id = {family.family_id: family for family in families}
    _append_production_review_tracking(
        result,
        requirement_id="require_source_families",
        counter_name="families",
        observed_count=sum(
            1
            for family_id in TRINO_PRODUCT_METADATA_REQUIRED_SOURCE_FAMILIES
            if _metadata_family_is_source_backed(families_by_id.get(family_id))
        ),
        required_count=len(TRINO_PRODUCT_METADATA_REQUIRED_SOURCE_FAMILIES),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_open_blocker_families",
        counter_name="open_blockers",
        observed_count=sum(
            1
            for family_id in TRINO_PRODUCT_METADATA_REQUIRED_OPEN_BLOCKER_FAMILIES
            if _metadata_family_is_open_blocker(families_by_id.get(family_id))
        ),
        required_count=len(TRINO_PRODUCT_METADATA_REQUIRED_OPEN_BLOCKER_FAMILIES),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_source_surfaces",
        counter_name="source_surfaces",
        observed_count=sum(
            1
            for surface in TRINO_PRODUCT_METADATA_REQUIRED_SOURCE_SURFACES
            if result.source_surface_counts[surface] > 0
        ),
        required_count=len(TRINO_PRODUCT_METADATA_REQUIRED_SOURCE_SURFACES),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_fact_namespace",
        counter_name="facts",
        observed_count=_accepted_requirement_count(
            result,
            family_id="metadata_fact_namespace",
            requirement_type="fact",
            requirement_ids=TRINO_METADATA_REQUIRED_FACT_IDS,
        ),
        required_count=len(TRINO_METADATA_REQUIRED_FACT_IDS),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_bounded_sources",
        counter_name="source_requirements",
        observed_count=_source_requirements_without_issue(
            result,
            families,
            issue_categories=("trino_product_metadata_source_bounds_missing",),
        ),
        required_count=result.source_requirement_count,
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_redaction_blocks",
        counter_name="redaction_fields",
        observed_count=sum(
            1
            for field_name in TRINO_PRODUCT_METADATA_REQUIRED_REDACTION_FIELDS
            if not result.issue_counts.get(f"trino_product_metadata_source_{field_name}_drift")
        ),
        required_count=len(TRINO_PRODUCT_METADATA_REQUIRED_REDACTION_FIELDS),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_sql_execution_policy",
        counter_name="sql_execution",
        observed_count=sum(
            1
            for status in TRINO_PRODUCT_METADATA_REQUIRED_SQL_EXECUTION_STATUSES
            if result.sql_execution_counts[status] > 0
        ),
        required_count=len(TRINO_PRODUCT_METADATA_REQUIRED_SQL_EXECUTION_STATUSES),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_product_surface_blocks",
        counter_name="product_surface_requirements",
        observed_count=_accepted_requirement_count(
            result,
            family_id="product_metadata_surfaces",
            requirement_type="product_surface",
            requirement_ids=TRINO_PRODUCT_METADATA_REQUIRED_PRODUCT_SURFACE_REQUIREMENTS,
        ),
        required_count=len(TRINO_PRODUCT_METADATA_REQUIRED_PRODUCT_SURFACE_REQUIREMENTS),
    )


def _metadata_family_is_source_backed(family: TrinoProductMetadataFamily | None) -> bool:
    return family is not None and bool(family.requirements)


def _metadata_family_is_open_blocker(family: TrinoProductMetadataFamily | None) -> bool:
    return family is not None and family.readiness_state == "open_required_future_work"


def _accepted_requirement_count(
    result: TrinoProductMetadataAuditResult,
    *,
    family_id: str,
    requirement_type: str,
    requirement_ids: tuple[str, ...],
) -> int:
    accepted_requirement_ids = {
        tracking.requirement_id
        for tracking in result.product_metadata_requirement_tracking
        if tracking.family_id == family_id
        and tracking.requirement_type == requirement_type
        and tracking.tracking_status == "accepted"
    }
    return sum(
        1 for requirement_id in requirement_ids if requirement_id in accepted_requirement_ids
    )


def _source_requirements_without_issue(
    result: TrinoProductMetadataAuditResult,
    families: tuple[TrinoProductMetadataFamily, ...],
    *,
    issue_categories: tuple[str, ...],
) -> int:
    accepted_count = 0
    accepted_source_requirements = {
        (tracking.family_id, tracking.requirement_id)
        for tracking in result.product_metadata_requirement_tracking
        if tracking.requirement_type == "source" and tracking.tracking_status == "accepted"
    }
    for family in families:
        for requirement in family.requirements:
            if (
                family.family_id,
                requirement.source_type,
            ) in accepted_source_requirements and not any(
                issue_family_id == family.family_id
                and issue.requirement_type == "source"
                and issue.requirement_id == requirement.source_type
                and issue.category in issue_categories
                for issue_family_id, issue in result.issues
            ):
                accepted_count += 1
    return accepted_count


def _append_production_review_tracking(
    result: TrinoProductMetadataAuditResult,
    *,
    requirement_id: str,
    counter_name: str,
    observed_count: int,
    required_count: int,
) -> None:
    tracking_status = _production_review_tracking_status(observed_count, required_count)
    result.production_review_tracking.append(
        TrinoProductMetadataProductionReviewTracking(
            requirement_id=requirement_id,
            counter_name=counter_name,
            tracking_status=tracking_status,
            observed_count=observed_count,
            required_count=required_count,
        )
    )
    result.production_review_tracking_counts[tracking_status] += 1
    if tracking_status != "accepted":
        _add_issue(
            result,
            "production_review_profile",
            "trino_product_metadata_production_review_gap",
            "Trino product metadata production-review profile is incomplete.",
            requirement_type="production_review_profile",
            requirement_id=requirement_id,
        )


def _production_review_tracking_status(observed_count: int, required_count: int) -> str:
    if required_count <= 0:
        return "not_required"
    if observed_count >= required_count:
        return "accepted"
    return "insufficient"


def _production_review_profile_status(result: TrinoProductMetadataAuditResult) -> str:
    if not result.production_review_tracking:
        return "not_required"
    if set(result.production_review_tracking_counts) == {"accepted"}:
        return TRINO_PRODUCT_METADATA_PRODUCTION_REVIEW_PROFILE_STATUS
    return "failed"


def _append_product_metadata_requirement_tracking(
    result: TrinoProductMetadataAuditResult,
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
    tracking_status = _product_metadata_requirement_tracking_status(issues)
    result.product_metadata_requirement_tracking.append(
        TrinoProductMetadataRequirementTracking(
            family_id=family_id,
            requirement_type=requirement_type,
            requirement_id=requirement_id,
            tracking_status=tracking_status,
            issue_count=len(issues),
        )
    )
    result.product_metadata_requirement_tracking_counts[tracking_status] += 1


def _issues_for_requirement(
    result: TrinoProductMetadataAuditResult,
    *,
    family_id: str,
    requirement_type: str,
    requirement_id: str,
) -> tuple[TrinoProductMetadataIssue, ...]:
    return tuple(
        issue
        for issue_family_id, issue in result.issues
        if issue_family_id == family_id
        and issue.requirement_type == requirement_type
        and issue.requirement_id == requirement_id
    )


def _product_metadata_requirement_tracking_status(
    issues: tuple[TrinoProductMetadataIssue, ...],
) -> str:
    if any(
        issue.category
        in {"trino_product_metadata_required_fact_missing", "trino_product_metadata_source_missing"}
        for issue in issues
    ):
        return "missing"
    if issues:
        return "invalid"
    return "accepted"


def _add_issue(
    result: TrinoProductMetadataAuditResult,
    family_id: str,
    category: str,
    message: str,
    *,
    requirement_type: str | None = None,
    requirement_id: str | None = None,
) -> None:
    issue = TrinoProductMetadataIssue(
        category=category,
        message=message,
        requirement_type=requirement_type,
        requirement_id=requirement_id,
    )
    result.issue_counts[category] += 1
    result.issues.append((family_id, issue))


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}
