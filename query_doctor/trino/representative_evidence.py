"""Raw-free audit model for retained representative Trino evidence summaries.

The audit consumes already raw-free summary payloads from existing Trino dev
gates. It does not collect from Trino, reopen raw artifacts, or promote Trino
beyond the current bounded local lanes.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND = "trino_representative_evidence_audit_v1"
TRINO_REPRESENTATIVE_EVIDENCE_GATE = "trino_representative_real_cluster_evidence"
TRINO_REPRESENTATIVE_EVIDENCE_STATUS = "not_closed"
TRINO_SQL_EXECUTION_STATUS = "not_performed"

TRINO_EVIDENCE_HANDOFF_SUMMARY_KIND = "trino_evidence_handoff_summary_v1"
TRINO_EVIDENCE_HANDOFF_SUITE_SUMMARY_KIND = "trino_evidence_handoff_suite_summary_v1"
TRINO_COMPACT_READINESS_SUMMARY_KIND = "trino_compact_readiness_summary_v1"
TRINO_ONE_QUERY_HANDOFF_SUMMARY_VERSION = "trino_one_query_handoff_summary_v1"
TRINO_PRODUCT_SURFACE_AUDIT_SUMMARY_KIND = "trino_product_surface_boundary_audit_v1"
TRINO_SUPPORT_GAP_SUMMARY_KIND = "trino_support_gap_matrix_audit_v1"
TRINO_REPRESENTATIVE_EVIDENCE_CUSTOM_PROFILE = "custom"
TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE = "production_review_breadth_v1"
TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_KINDS = (
    TRINO_EVIDENCE_HANDOFF_SUITE_SUMMARY_KIND,
    TRINO_COMPACT_READINESS_SUMMARY_KIND,
    TRINO_PRODUCT_SURFACE_AUDIT_SUMMARY_KIND,
    TRINO_SUPPORT_GAP_SUMMARY_KIND,
)
TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_STATUSES = ("ok",)

_SAFE_LABEL_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}")
_SAFE_TRINO_VERSION_FAMILY_RE = re.compile(r"(unknown|[0-9]{3,4}(?:\.[0-9]{1,3})?)")


@dataclass(frozen=True)
class TrinoRepresentativeEvidenceIssue:
    category: str
    message: str


@dataclass(frozen=True)
class TrinoRepresentativeEvidenceBreadthTracking:
    requirement_id: str
    counter_name: str
    tracking_status: str
    observed_count: int
    required_count: int


@dataclass(frozen=True)
class TrinoRepresentativeEvidenceRequirements:
    requirement_profile: str = TRINO_REPRESENTATIVE_EVIDENCE_CUSTOM_PROFILE
    require_min_summary_inputs: int = 0
    require_min_summary_kinds: int = 0
    require_min_evidence_units: int = 0
    require_min_trino_version_families: int = 0
    require_min_source_contracts: int = 0
    require_min_source_schemas: int = 0
    require_min_lifecycles: int = 0
    require_min_connector_family_categories: int = 0
    require_min_source_granularities: int = 0
    require_min_verification_scopes: int = 0
    require_min_support_statuses: int = 0
    required_summary_kinds: tuple[str, ...] = ()
    required_summary_statuses: tuple[str, ...] = ()
    required_trino_version_families: tuple[str, ...] = ()
    required_source_contracts: tuple[str, ...] = ()
    required_source_schemas: tuple[str, ...] = ()
    required_lifecycles: tuple[str, ...] = ()
    required_connector_family_categories: tuple[str, ...] = ()
    required_source_granularities: tuple[str, ...] = ()
    required_verification_scopes: tuple[str, ...] = ()
    required_support_statuses: tuple[str, ...] = ()


@dataclass
class TrinoRepresentativeEvidenceAuditResult:
    summary_input_count: int = 0
    evidence_unit_count: int = 0
    summary_kind_counts: Counter[str] = field(default_factory=Counter)
    status_counts: Counter[str] = field(default_factory=Counter)
    trino_version_family_counts: Counter[str] = field(default_factory=Counter)
    source_contract_counts: Counter[str] = field(default_factory=Counter)
    source_schema_counts: Counter[str] = field(default_factory=Counter)
    lifecycle_counts: Counter[str] = field(default_factory=Counter)
    connector_family_category_counts: Counter[str] = field(default_factory=Counter)
    source_granularity_counts: Counter[str] = field(default_factory=Counter)
    verification_scope_counts: Counter[str] = field(default_factory=Counter)
    support_status_counts: Counter[str] = field(default_factory=Counter)
    breadth_requirement_tracking_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    breadth_requirement_tracking: list[TrinoRepresentativeEvidenceBreadthTracking] = field(
        default_factory=list
    )
    issues: list[TrinoRepresentativeEvidenceIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issue_counts


def audit_trino_representative_evidence(
    payloads: Iterable[Mapping[str, Any]],
    *,
    requirements: TrinoRepresentativeEvidenceRequirements | None = None,
) -> TrinoRepresentativeEvidenceAuditResult:
    result = TrinoRepresentativeEvidenceAuditResult()
    for payload in payloads:
        audit_trino_representative_evidence_payload(result, payload)
    apply_trino_representative_evidence_requirements(
        result,
        requirements or TrinoRepresentativeEvidenceRequirements(),
    )
    return result


def audit_trino_representative_evidence_payload(
    result: TrinoRepresentativeEvidenceAuditResult,
    payload: Mapping[str, Any],
) -> None:
    summary_kind = payload.get("summary_kind")
    schema_version = payload.get("schema_version")
    if summary_kind == TRINO_EVIDENCE_HANDOFF_SUITE_SUMMARY_KIND:
        result.summary_input_count += 1
        result.summary_kind_counts[TRINO_EVIDENCE_HANDOFF_SUITE_SUMMARY_KIND] += 1
        _audit_handoff_suite_summary(result, payload)
        return
    if summary_kind == TRINO_EVIDENCE_HANDOFF_SUMMARY_KIND:
        result.summary_input_count += 1
        result.summary_kind_counts[TRINO_EVIDENCE_HANDOFF_SUMMARY_KIND] += 1
        _audit_handoff_summary(result, payload)
        return
    if summary_kind == TRINO_COMPACT_READINESS_SUMMARY_KIND:
        result.summary_input_count += 1
        result.summary_kind_counts[TRINO_COMPACT_READINESS_SUMMARY_KIND] += 1
        _audit_readiness_summary(result, payload)
        return
    if schema_version == TRINO_ONE_QUERY_HANDOFF_SUMMARY_VERSION:
        result.summary_input_count += 1
        result.summary_kind_counts[TRINO_ONE_QUERY_HANDOFF_SUMMARY_VERSION] += 1
        _audit_one_query_handoff_summary(result, payload)
        return
    if summary_kind == TRINO_PRODUCT_SURFACE_AUDIT_SUMMARY_KIND:
        result.summary_input_count += 1
        result.summary_kind_counts[TRINO_PRODUCT_SURFACE_AUDIT_SUMMARY_KIND] += 1
        _audit_product_surface_summary(result, payload)
        return
    if summary_kind == TRINO_SUPPORT_GAP_SUMMARY_KIND:
        result.summary_input_count += 1
        result.summary_kind_counts[TRINO_SUPPORT_GAP_SUMMARY_KIND] += 1
        _audit_support_gap_summary(result, payload)
        return
    _add_issue(
        result,
        "trino_representative_evidence_unknown_summary_kind",
        "Representative evidence audit accepts only known raw-free Trino summary payloads.",
    )


def apply_trino_representative_evidence_requirements(
    result: TrinoRepresentativeEvidenceAuditResult,
    requirements: TrinoRepresentativeEvidenceRequirements,
) -> None:
    if result.summary_input_count < requirements.require_min_summary_inputs:
        _add_issue(
            result,
            "trino_representative_evidence_summary_count_gap",
            "Representative evidence requires more retained raw-free summary inputs.",
        )
    _require_min_distinct_labels(
        result,
        result.summary_kind_counts,
        requirements.require_min_summary_kinds,
        category="trino_representative_evidence_summary_kind_gap",
        message="Representative evidence requires broader retained summary-kind coverage.",
    )
    if result.evidence_unit_count < requirements.require_min_evidence_units:
        _add_issue(
            result,
            "trino_representative_evidence_unit_gap",
            "Representative evidence requires more retained raw-free evidence units.",
        )
    if len(result.trino_version_family_counts) < requirements.require_min_trino_version_families:
        _add_issue(
            result,
            "trino_representative_evidence_version_family_gap",
            "Representative evidence requires broader safe Trino version-family coverage.",
        )
    _require_min_distinct_labels(
        result,
        result.source_contract_counts,
        requirements.require_min_source_contracts,
        category="trino_representative_evidence_source_contract_gap",
        message="Representative evidence requires broader source-contract coverage.",
    )
    _require_min_distinct_labels(
        result,
        result.source_schema_counts,
        requirements.require_min_source_schemas,
        category="trino_representative_evidence_source_schema_gap",
        message="Representative evidence requires broader source-schema coverage.",
    )
    _require_min_distinct_labels(
        result,
        result.lifecycle_counts,
        requirements.require_min_lifecycles,
        category="trino_representative_evidence_lifecycle_gap",
        message="Representative evidence requires broader lifecycle coverage.",
    )
    _require_min_distinct_labels(
        result,
        result.connector_family_category_counts,
        requirements.require_min_connector_family_categories,
        category="trino_representative_evidence_connector_family_gap",
        message="Representative evidence requires broader connector-family coverage.",
    )
    _require_min_distinct_labels(
        result,
        result.source_granularity_counts,
        requirements.require_min_source_granularities,
        category="trino_representative_evidence_source_granularity_gap",
        message="Representative evidence requires broader source-granularity coverage.",
    )
    _require_min_distinct_labels(
        result,
        result.verification_scope_counts,
        requirements.require_min_verification_scopes,
        category="trino_representative_evidence_verification_scope_gap",
        message="Representative evidence requires broader verification-scope coverage.",
    )
    _require_min_distinct_labels(
        result,
        result.support_status_counts,
        requirements.require_min_support_statuses,
        category="trino_representative_evidence_support_status_gap",
        message="Representative evidence requires broader support-status coverage.",
    )
    _require_labels_present(
        result,
        requirements.required_summary_kinds,
        result.summary_kind_counts,
        category="trino_representative_evidence_summary_kind_gap",
        message="Representative evidence is missing a required retained summary kind.",
    )
    _require_summary_statuses(result, requirements)
    _require_labels_present(
        result,
        requirements.required_trino_version_families,
        result.trino_version_family_counts,
        category="trino_representative_evidence_version_family_gap",
        message="Representative evidence is missing a required Trino version family.",
    )
    _require_labels_present(
        result,
        requirements.required_source_contracts,
        result.source_contract_counts,
        category="trino_representative_evidence_source_contract_gap",
        message="Representative evidence is missing a required source contract.",
    )
    _require_labels_present(
        result,
        requirements.required_source_schemas,
        result.source_schema_counts,
        category="trino_representative_evidence_source_schema_gap",
        message="Representative evidence is missing a required source schema.",
    )
    _require_labels_present(
        result,
        requirements.required_lifecycles,
        result.lifecycle_counts,
        category="trino_representative_evidence_lifecycle_gap",
        message="Representative evidence is missing a required lifecycle.",
    )
    _require_labels_present(
        result,
        requirements.required_connector_family_categories,
        result.connector_family_category_counts,
        category="trino_representative_evidence_connector_family_gap",
        message="Representative evidence is missing a required connector-family category.",
    )
    _require_labels_present(
        result,
        requirements.required_source_granularities,
        result.source_granularity_counts,
        category="trino_representative_evidence_source_granularity_gap",
        message="Representative evidence is missing a required source-granularity label.",
    )
    _require_labels_present(
        result,
        requirements.required_verification_scopes,
        result.verification_scope_counts,
        category="trino_representative_evidence_verification_scope_gap",
        message="Representative evidence is missing a required verification-scope label.",
    )
    _require_labels_present(
        result,
        requirements.required_support_statuses,
        result.support_status_counts,
        category="trino_representative_evidence_support_status_gap",
        message="Representative evidence is missing a required support-status label.",
    )
    finalize_breadth_requirement_tracking(result, requirements)


def finalize_breadth_requirement_tracking(
    result: TrinoRepresentativeEvidenceAuditResult,
    requirements: TrinoRepresentativeEvidenceRequirements,
) -> None:
    result.breadth_requirement_tracking.clear()
    result.breadth_requirement_tracking_counts.clear()
    for (
        requirement_id,
        counter_name,
        observed_count,
        required_count,
    ) in _breadth_minimum_requirement_specs(result, requirements):
        _add_breadth_requirement_tracking(
            result,
            requirement_id=requirement_id,
            counter_name=counter_name,
            observed_count=observed_count,
            required_count=required_count,
        )
    for requirement_id, counter_name, counter, required_labels in _breadth_label_requirement_specs(
        result, requirements
    ):
        required_label_tuple = tuple(required_labels)
        observed_count = sum(1 for label in required_label_tuple if label in counter)
        _add_breadth_requirement_tracking(
            result,
            requirement_id=requirement_id,
            counter_name=counter_name,
            observed_count=observed_count,
            required_count=len(required_label_tuple),
        )
    _add_breadth_requirement_tracking(
        result,
        requirement_id="require_summary_statuses",
        counter_name="statuses",
        observed_count=sum(
            result.status_counts[status] for status in requirements.required_summary_statuses
        ),
        required_count=(
            max(result.summary_input_count, sum(result.status_counts.values()))
            if requirements.required_summary_statuses
            else 0
        ),
    )


def representative_evidence_summary_payload(
    result: TrinoRepresentativeEvidenceAuditResult,
    *,
    requirements: TrinoRepresentativeEvidenceRequirements,
    status: str,
) -> dict[str, Any]:
    return {
        "summary_kind": TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND,
        "status": status,
        "closure_gate": TRINO_REPRESENTATIVE_EVIDENCE_GATE,
        "representative_evidence_status": TRINO_REPRESENTATIVE_EVIDENCE_STATUS,
        "broader_production_closure_status": "not_closed",
        "trino_sql_execution": TRINO_SQL_EXECUTION_STATUS,
        "summary_input_count": result.summary_input_count,
        "evidence_unit_count": result.evidence_unit_count,
        "breadth_profile_status": _breadth_profile_status(result, requirements),
        "breadth_requirement_tracking_counts": _counter_payload(
            result.breadth_requirement_tracking_counts
        ),
        "breadth_requirement_tracking": [
            {
                "requirement_id": tracking.requirement_id,
                "counter_name": tracking.counter_name,
                "tracking_status": tracking.tracking_status,
                "observed_count": tracking.observed_count,
                "required_count": tracking.required_count,
            }
            for tracking in result.breadth_requirement_tracking
        ],
        "counters": {
            "summary_kinds": _counter_payload(result.summary_kind_counts),
            "statuses": _counter_payload(result.status_counts),
            "trino_version_families": _counter_payload(result.trino_version_family_counts),
            "source_contracts": _counter_payload(result.source_contract_counts),
            "source_schemas": _counter_payload(result.source_schema_counts),
            "lifecycles": _counter_payload(result.lifecycle_counts),
            "connector_family_categories": _counter_payload(
                result.connector_family_category_counts
            ),
            "source_granularity": _counter_payload(result.source_granularity_counts),
            "verification_scopes": _counter_payload(result.verification_scope_counts),
            "support_statuses": _counter_payload(result.support_status_counts),
            "issues": _counter_payload(result.issue_counts),
        },
        "requirements": representative_evidence_requirements_payload(requirements),
        "issues": {
            "counts": _counter_payload(result.issue_counts),
            "items": [
                {"category": issue.category, "message": issue.message} for issue in result.issues
            ],
        },
    }


def representative_evidence_requirements_payload(
    requirements: TrinoRepresentativeEvidenceRequirements,
) -> dict[str, Any]:
    return {
        "requirement_profile": requirements.requirement_profile,
        "require_min_summary_inputs": requirements.require_min_summary_inputs,
        "require_min_summary_kinds": requirements.require_min_summary_kinds,
        "require_min_evidence_units": requirements.require_min_evidence_units,
        "require_min_trino_version_families": (requirements.require_min_trino_version_families),
        "require_min_source_contracts": requirements.require_min_source_contracts,
        "require_min_source_schemas": requirements.require_min_source_schemas,
        "require_min_lifecycles": requirements.require_min_lifecycles,
        "require_min_connector_family_categories": (
            requirements.require_min_connector_family_categories
        ),
        "require_min_source_granularities": requirements.require_min_source_granularities,
        "require_min_verification_scopes": requirements.require_min_verification_scopes,
        "require_min_support_statuses": requirements.require_min_support_statuses,
        "require_summary_kinds": sorted(requirements.required_summary_kinds),
        "require_summary_statuses": sorted(requirements.required_summary_statuses),
        "require_trino_version_families": sorted(requirements.required_trino_version_families),
        "require_source_contracts": sorted(requirements.required_source_contracts),
        "require_source_schemas": sorted(requirements.required_source_schemas),
        "require_lifecycles": sorted(requirements.required_lifecycles),
        "require_connector_family_categories": sorted(
            requirements.required_connector_family_categories
        ),
        "require_source_granularities": sorted(requirements.required_source_granularities),
        "require_verification_scopes": sorted(requirements.required_verification_scopes),
        "require_support_statuses": sorted(requirements.required_support_statuses),
    }


def representative_evidence_requirements_for_profile(
    profile: str,
) -> TrinoRepresentativeEvidenceRequirements:
    if profile != TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE:
        raise ValueError("unknown representative evidence requirements profile")
    return TrinoRepresentativeEvidenceRequirements(
        requirement_profile=TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE,
        require_min_summary_inputs=4,
        require_min_evidence_units=2,
        require_min_trino_version_families=2,
        require_min_source_contracts=1,
        require_min_source_schemas=1,
        require_min_lifecycles=2,
        require_min_connector_family_categories=1,
        require_min_source_granularities=1,
        require_min_verification_scopes=1,
        require_min_support_statuses=1,
        required_summary_kinds=TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_KINDS,
        required_summary_statuses=TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_STATUSES,
        required_support_statuses=("bounded_raw_free_preview",),
    )


def accepted_safe_labels(
    values: Iterable[str],
    *,
    label_kind: str = "generic",
) -> tuple[str, ...] | None:
    labels: set[str] = set()
    for value in values:
        if not _safe_label(value, label_kind=label_kind):
            return None
        labels.add(value)
    return tuple(sorted(labels))


def _audit_handoff_suite_summary(
    result: TrinoRepresentativeEvidenceAuditResult,
    payload: Mapping[str, Any],
) -> None:
    _count_status(result, payload.get("status"))
    counts = _mapping(payload.get("counts"))
    result.evidence_unit_count += _first_positive_count(
        counts,
        ("boundary_count", "package_sample_count", "handoff_summary_count"),
    )
    _merge_counter_payload(
        result,
        payload.get("source_contracts"),
        result.source_contract_counts,
        label_kind="generic",
    )
    _merge_counter_payload(
        result,
        payload.get("connector_family_categories"),
        result.connector_family_category_counts,
        label_kind="generic",
    )
    _merge_counter_payload(
        result,
        payload.get("source_schemas"),
        result.source_schema_counts,
        label_kind="generic",
    )
    _merge_counter_payload(
        result,
        payload.get("lifecycles"),
        result.lifecycle_counts,
        label_kind="generic",
    )
    _merge_counter_payload(
        result,
        payload.get("support_statuses"),
        result.support_status_counts,
        label_kind="generic",
    )
    _merge_counter_payload(
        result,
        payload.get("source_granularity"),
        result.source_granularity_counts,
        label_kind="generic",
    )
    diagnostic_lane = _mapping(payload.get("diagnostic_lane"))
    _merge_counter_payload(
        result,
        diagnostic_lane.get("verification_scope"),
        result.verification_scope_counts,
        label_kind="generic",
    )


def _audit_handoff_summary(
    result: TrinoRepresentativeEvidenceAuditResult,
    payload: Mapping[str, Any],
) -> None:
    _count_status(result, payload.get("status"))
    result.evidence_unit_count += _first_positive_count(
        _mapping(payload.get("counts")),
        ("boundary_count",),
    )
    package = _mapping(payload.get("package"))
    source_summary = _mapping(package.get("source_summary"))
    _add_single_label(
        result,
        source_summary.get("trino_version_family"),
        result.trino_version_family_counts,
        label_kind="trino_version_family",
    )
    _add_single_label(
        result,
        source_summary.get("source_contract_version"),
        result.source_contract_counts,
        label_kind="generic",
    )
    connector_categories = source_summary.get("connector_family_categories")
    if isinstance(connector_categories, list):
        for connector_category in connector_categories:
            _add_single_label(
                result,
                connector_category,
                result.connector_family_category_counts,
                label_kind="generic",
            )
    _merge_counter_payload(
        result,
        payload.get("source_schemas"),
        result.source_schema_counts,
        label_kind="generic",
    )
    _merge_counter_payload(
        result,
        payload.get("lifecycles"),
        result.lifecycle_counts,
        label_kind="generic",
    )
    _merge_counter_payload(
        result,
        payload.get("support_statuses"),
        result.support_status_counts,
        label_kind="generic",
    )
    _merge_counter_payload(
        result,
        payload.get("source_granularity"),
        result.source_granularity_counts,
        label_kind="generic",
    )
    diagnostic_lane = _mapping(payload.get("diagnostic_lane"))
    _merge_counter_payload(
        result,
        diagnostic_lane.get("verification_scope"),
        result.verification_scope_counts,
        label_kind="generic",
    )


def _audit_readiness_summary(
    result: TrinoRepresentativeEvidenceAuditResult,
    payload: Mapping[str, Any],
) -> None:
    _count_ok_status(result, payload.get("ok"))
    result.evidence_unit_count += _non_negative_int(payload.get("input_count"), default=0)
    counters = _mapping(payload.get("counters"))
    source = _mapping(payload.get("source"))
    if counters:
        _merge_counter_payload(
            result,
            counters.get("trino_version_families"),
            result.trino_version_family_counts,
            label_kind="trino_version_family",
        )
        _merge_counter_payload(
            result,
            counters.get("source_schemas"),
            result.source_schema_counts,
            label_kind="generic",
        )
        _merge_counter_payload(
            result,
            counters.get("lifecycles"),
            result.lifecycle_counts,
            label_kind="generic",
        )
        _merge_counter_payload(
            result,
            counters.get("source_granularity"),
            result.source_granularity_counts,
            label_kind="generic",
        )
        _merge_counter_payload(
            result,
            counters.get("support_statuses"),
            result.support_status_counts,
            label_kind="generic",
        )
        _merge_counter_payload(
            result,
            counters.get("diagnostic_lane_verification_scope"),
            result.verification_scope_counts,
            label_kind="generic",
        )
    if source:
        _add_single_label(
            result,
            source.get("trino_version_family"),
            result.trino_version_family_counts,
            label_kind="trino_version_family",
        )
        _add_single_label(
            result,
            source.get("schema"),
            result.source_schema_counts,
            label_kind="generic",
        )
        _add_single_label(
            result,
            source.get("lifecycle"),
            result.lifecycle_counts,
            label_kind="generic",
        )
        _add_single_label(
            result,
            source.get("granularity"),
            result.source_granularity_counts,
            label_kind="generic",
        )
        boundary = _mapping(payload.get("boundary"))
        _add_single_label(
            result,
            boundary.get("support_status"),
            result.support_status_counts,
            label_kind="generic",
        )
        diagnostic_lane = _mapping(payload.get("diagnostic_lane"))
        _merge_counter_payload(
            result,
            diagnostic_lane.get("verification_scope"),
            result.verification_scope_counts,
            label_kind="generic",
        )


def _audit_one_query_handoff_summary(
    result: TrinoRepresentativeEvidenceAuditResult,
    payload: Mapping[str, Any],
) -> None:
    _count_status(result, payload.get("status"))
    readiness = payload.get("readiness")
    if isinstance(readiness, Mapping):
        result.summary_kind_counts[TRINO_COMPACT_READINESS_SUMMARY_KIND] += 1
        _audit_readiness_summary(result, readiness)
    else:
        _add_issue(
            result,
            "trino_representative_evidence_readiness_missing",
            "One-query handoff summary is missing its raw-free readiness summary.",
        )


def _audit_product_surface_summary(
    result: TrinoRepresentativeEvidenceAuditResult,
    payload: Mapping[str, Any],
) -> None:
    _count_status(result, payload.get("status"))
    boundary = _mapping(payload.get("boundary"))
    expected_boundary = {
        "product_surface": "recent_query_id_raw_free_details_python_report_optimizer_guidance",
        "support_claim": "local_production",
        "details_case_view": "raw_free_materialized",
        "python_report": "raw_free_materialized",
        "optimizer_guidance": "raw_free_materialized",
        "llm_reports": "not_wired",
        "optimizer_behavior": "guidance_only",
        "trino_sql_execution": TRINO_SQL_EXECUTION_STATUS,
    }
    for field_name, expected_value in expected_boundary.items():
        if boundary.get(field_name) != expected_value:
            _add_issue(
                result,
                "trino_representative_evidence_product_surface_boundary_drift",
                "Product-surface summary boundary drifted from the retained Trino contract.",
            )
    diagnostic_lane = _mapping(payload.get("diagnostic_lane"))
    _merge_counter_payload(
        result,
        diagnostic_lane.get("source_granularity"),
        result.source_granularity_counts,
        label_kind="generic",
    )
    _merge_counter_payload(
        result,
        diagnostic_lane.get("verification_scope"),
        result.verification_scope_counts,
        label_kind="generic",
    )


def _audit_support_gap_summary(
    result: TrinoRepresentativeEvidenceAuditResult,
    payload: Mapping[str, Any],
) -> None:
    _count_status(result, payload.get("status"))
    expected_fields = {
        "support_gap_status": "bounded_production_claim_pinned",
        "production_support": "local_production",
        "product_surfaces": "recent_query_id_raw_free_details_python_report_optimizer_guidance",
        "broader_production_closure_status": "bounded_production_claim_ready",
        "trino_sql_execution": TRINO_SQL_EXECUTION_STATUS,
    }
    for field_name, expected_value in expected_fields.items():
        if payload.get(field_name) != expected_value:
            _add_issue(
                result,
                "trino_representative_evidence_support_gap_boundary_drift",
                "Support-gap summary boundary drifted from the retained Trino contract.",
            )


def _require_labels_present(
    result: TrinoRepresentativeEvidenceAuditResult,
    required_labels: Iterable[str],
    counter: Counter[str],
    *,
    category: str,
    message: str,
) -> None:
    for label in required_labels:
        if label not in counter:
            _add_issue(result, category, message)


def _require_summary_statuses(
    result: TrinoRepresentativeEvidenceAuditResult,
    requirements: TrinoRepresentativeEvidenceRequirements,
) -> None:
    if not requirements.required_summary_statuses:
        return
    allowed_statuses = set(requirements.required_summary_statuses)
    accepted_count = sum(result.status_counts[status] for status in allowed_statuses)
    disallowed_count = sum(
        count for status, count in result.status_counts.items() if status not in allowed_statuses
    )
    if accepted_count < result.summary_input_count or disallowed_count:
        _add_issue(
            result,
            "trino_representative_evidence_summary_status_gap",
            "Representative evidence retained summary inputs must have accepted statuses.",
        )


def _require_min_distinct_labels(
    result: TrinoRepresentativeEvidenceAuditResult,
    counter: Counter[str],
    required_count: int,
    *,
    category: str,
    message: str,
) -> None:
    if len(counter) < required_count:
        _add_issue(result, category, message)


def _requirements_enabled(requirements: TrinoRepresentativeEvidenceRequirements) -> bool:
    return requirements != TrinoRepresentativeEvidenceRequirements()


def _breadth_profile_status(
    result: TrinoRepresentativeEvidenceAuditResult,
    requirements: TrinoRepresentativeEvidenceRequirements,
) -> str:
    if not _requirements_enabled(requirements):
        return "not_required"
    return "ready" if result.ok else "failed"


def _breadth_minimum_requirement_specs(
    result: TrinoRepresentativeEvidenceAuditResult,
    requirements: TrinoRepresentativeEvidenceRequirements,
) -> tuple[tuple[str, str, int, int], ...]:
    return (
        (
            "require_min_summary_inputs",
            "summary_inputs",
            result.summary_input_count,
            requirements.require_min_summary_inputs,
        ),
        (
            "require_min_summary_kinds",
            "summary_kinds",
            len(result.summary_kind_counts),
            requirements.require_min_summary_kinds,
        ),
        (
            "require_min_evidence_units",
            "evidence_units",
            result.evidence_unit_count,
            requirements.require_min_evidence_units,
        ),
        (
            "require_min_trino_version_families",
            "trino_version_families",
            len(result.trino_version_family_counts),
            requirements.require_min_trino_version_families,
        ),
        (
            "require_min_source_contracts",
            "source_contracts",
            len(result.source_contract_counts),
            requirements.require_min_source_contracts,
        ),
        (
            "require_min_source_schemas",
            "source_schemas",
            len(result.source_schema_counts),
            requirements.require_min_source_schemas,
        ),
        (
            "require_min_lifecycles",
            "lifecycles",
            len(result.lifecycle_counts),
            requirements.require_min_lifecycles,
        ),
        (
            "require_min_connector_family_categories",
            "connector_family_categories",
            len(result.connector_family_category_counts),
            requirements.require_min_connector_family_categories,
        ),
        (
            "require_min_source_granularities",
            "source_granularity",
            len(result.source_granularity_counts),
            requirements.require_min_source_granularities,
        ),
        (
            "require_min_verification_scopes",
            "verification_scopes",
            len(result.verification_scope_counts),
            requirements.require_min_verification_scopes,
        ),
        (
            "require_min_support_statuses",
            "support_statuses",
            len(result.support_status_counts),
            requirements.require_min_support_statuses,
        ),
    )


def _breadth_label_requirement_specs(
    result: TrinoRepresentativeEvidenceAuditResult,
    requirements: TrinoRepresentativeEvidenceRequirements,
) -> tuple[tuple[str, str, Counter[str], tuple[str, ...]], ...]:
    return (
        (
            "require_summary_kinds",
            "summary_kinds",
            result.summary_kind_counts,
            requirements.required_summary_kinds,
        ),
        (
            "require_trino_version_families",
            "trino_version_families",
            result.trino_version_family_counts,
            requirements.required_trino_version_families,
        ),
        (
            "require_source_contracts",
            "source_contracts",
            result.source_contract_counts,
            requirements.required_source_contracts,
        ),
        (
            "require_source_schemas",
            "source_schemas",
            result.source_schema_counts,
            requirements.required_source_schemas,
        ),
        (
            "require_lifecycles",
            "lifecycles",
            result.lifecycle_counts,
            requirements.required_lifecycles,
        ),
        (
            "require_connector_family_categories",
            "connector_family_categories",
            result.connector_family_category_counts,
            requirements.required_connector_family_categories,
        ),
        (
            "require_source_granularities",
            "source_granularity",
            result.source_granularity_counts,
            requirements.required_source_granularities,
        ),
        (
            "require_verification_scopes",
            "verification_scopes",
            result.verification_scope_counts,
            requirements.required_verification_scopes,
        ),
        (
            "require_support_statuses",
            "support_statuses",
            result.support_status_counts,
            requirements.required_support_statuses,
        ),
    )


def _add_breadth_requirement_tracking(
    result: TrinoRepresentativeEvidenceAuditResult,
    *,
    requirement_id: str,
    counter_name: str,
    observed_count: int,
    required_count: int,
) -> None:
    tracking_status = _breadth_requirement_tracking_status(observed_count, required_count)
    result.breadth_requirement_tracking.append(
        TrinoRepresentativeEvidenceBreadthTracking(
            requirement_id=requirement_id,
            counter_name=counter_name,
            tracking_status=tracking_status,
            observed_count=observed_count,
            required_count=required_count,
        )
    )
    result.breadth_requirement_tracking_counts[tracking_status] += 1


def _breadth_requirement_tracking_status(
    observed_count: int,
    required_count: int,
) -> str:
    if required_count <= 0:
        return "not_required"
    if observed_count >= required_count:
        return "accepted"
    return "insufficient"


def _merge_counter_payload(
    result: TrinoRepresentativeEvidenceAuditResult,
    payload: Any,
    target: Counter[str],
    *,
    label_kind: str,
) -> None:
    if payload is None:
        return
    if not isinstance(payload, Mapping):
        _add_issue(
            result,
            "trino_representative_evidence_counter_shape_invalid",
            "Representative evidence summary has an invalid counter payload shape.",
        )
        return
    for raw_label, raw_count in payload.items():
        label = raw_label if isinstance(raw_label, str) else None
        if not _safe_label(label, label_kind=label_kind):
            _add_issue(
                result,
                "trino_representative_evidence_unsafe_label",
                "Representative evidence summary contained an unsafe counter label.",
            )
            continue
        count = _non_negative_int(raw_count, default=-1)
        if count < 0:
            _add_issue(
                result,
                "trino_representative_evidence_counter_count_invalid",
                "Representative evidence summary has an invalid counter value.",
            )
            continue
        if count:
            target[label] += count


def _add_single_label(
    result: TrinoRepresentativeEvidenceAuditResult,
    raw_label: Any,
    target: Counter[str],
    *,
    label_kind: str,
) -> None:
    label = raw_label if isinstance(raw_label, str) else None
    if label is None:
        return
    if not _safe_label(label, label_kind=label_kind):
        _add_issue(
            result,
            "trino_representative_evidence_unsafe_label",
            "Representative evidence summary contained an unsafe label.",
        )
        return
    target[label] += 1


def _count_status(
    result: TrinoRepresentativeEvidenceAuditResult,
    raw_status: Any,
) -> None:
    _add_single_label(result, raw_status, result.status_counts, label_kind="generic")


def _count_ok_status(
    result: TrinoRepresentativeEvidenceAuditResult,
    raw_ok: Any,
) -> None:
    if isinstance(raw_ok, bool):
        result.status_counts["ok" if raw_ok else "failed"] += 1


def _safe_label(value: str | None, *, label_kind: str) -> bool:
    if not value:
        return False
    if label_kind == "trino_version_family":
        return _SAFE_TRINO_VERSION_FAMILY_RE.fullmatch(value) is not None
    return _SAFE_LABEL_RE.fullmatch(value) is not None


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _first_positive_count(payload: Mapping[str, Any], keys: Iterable[str]) -> int:
    for key in keys:
        count = _non_negative_int(payload.get(key), default=0)
        if count > 0:
            return count
    return 0


def _non_negative_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int) and value >= 0:
        return value
    return default


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _add_issue(
    result: TrinoRepresentativeEvidenceAuditResult,
    category: str,
    message: str,
) -> None:
    result.issue_counts[category] += 1
    result.issues.append(TrinoRepresentativeEvidenceIssue(category=category, message=message))
