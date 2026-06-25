"""Raw-free audit model for Trino bounded production claim closure gates.

This module ties the bounded Trino production claim to the current raw-free
tracking summaries. It does not collect from Trino, execute SQL, add
browser/report surfaces, or promote broader/shared production expansion.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from query_doctor.engines.capabilities import (
    EngineCapability,
    engine_capabilities,
)
from query_doctor.trino.browser_report_regression import (
    TRINO_BROWSER_REPORT_DETAILS_CASE_VIEW,
    TRINO_BROWSER_REPORT_LLM_REPORTS,
    TRINO_BROWSER_REPORT_OPTIMIZER_GUIDANCE,
    TRINO_BROWSER_REPORT_PRODUCTION_REVIEW_PROFILE,
    TRINO_BROWSER_REPORT_PRODUCTION_REVIEW_PROFILE_STATUS,
    TRINO_BROWSER_REPORT_PRODUCT_SURFACE,
    TRINO_BROWSER_REPORT_PYTHON_REPORT,
    TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
    TRINO_BROWSER_REPORT_REGRESSION_GATE,
    TRINO_BROWSER_REPORT_REGRESSION_STATUS,
    TRINO_BROWSER_REPORT_REGRESSION_SUMMARY_KIND,
    TRINO_BROWSER_REPORT_REQUIRED_REVIEW_DOWNLOAD_TESTS,
    TRINO_BROWSER_REPORT_REQUIRED_REVIEW_FAMILIES,
    TRINO_BROWSER_REPORT_REQUIRED_REVIEW_PUBLIC_CLAIM_TESTS,
    TRINO_BROWSER_REPORT_REQUIRED_REVIEW_RAW_OUTPUT_REQUIREMENTS,
    TRINO_BROWSER_REPORT_REQUIRED_REVIEW_ROUTE_CAPABILITIES,
    TRINO_BROWSER_REPORT_REQUIRED_REVIEW_TEST_FILES,
    TRINO_BROWSER_REPORT_REQUIRED_REVIEW_UNSUPPORTED_SURFACE_REQUIREMENTS,
    TRINO_BROWSER_REPORT_SQL_EXECUTION,
)
from query_doctor.trino.product_metadata_collection import (
    TRINO_PRODUCT_METADATA_COLLECTION_GATE,
    TRINO_PRODUCT_METADATA_COLLECTION_STATUS,
    TRINO_PRODUCT_METADATA_COLLECTION_SUMMARY_KIND,
    TRINO_PRODUCT_METADATA_PRODUCTION_REVIEW_PROFILE,
    TRINO_PRODUCT_METADATA_PRODUCTION_REVIEW_PROFILE_STATUS,
    TRINO_PRODUCT_METADATA_REQUIRED_OPEN_BLOCKER_FAMILIES,
    TRINO_PRODUCT_METADATA_REQUIRED_PRODUCT_SURFACE_REQUIREMENTS,
    TRINO_PRODUCT_METADATA_REQUIRED_REDACTION_FIELDS,
    TRINO_PRODUCT_METADATA_REQUIRED_SOURCE_FAMILIES,
    TRINO_PRODUCT_METADATA_REQUIRED_SOURCE_SURFACES,
    TRINO_PRODUCT_METADATA_REQUIRED_SQL_EXECUTION_STATUSES,
    TRINO_PRODUCT_METADATA_SQL_EXECUTION_STATUS,
)
from query_doctor.trino.production_collector_contracts import (
    TRINO_PRODUCTION_COLLECTOR_CONTRACTS_GATE,
    TRINO_PRODUCTION_COLLECTOR_CONTRACTS_STATUS,
    TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND,
    TRINO_PRODUCTION_COLLECTOR_REPRESENTATIVE_EVIDENCE_NOT_PROVIDED,
    TRINO_PRODUCTION_COLLECTOR_REPRESENTATIVE_EVIDENCE_READY,
)
from query_doctor.trino.query_linked_fact_coverage import (
    TRINO_QUERY_LINKED_BOUNDED_SUPPORTED_DECISION,
    TRINO_QUERY_LINKED_OPERATOR_CONNECTOR_TELEMETRY_PROFILE,
    TRINO_QUERY_LINKED_OPERATOR_CONNECTOR_TELEMETRY_PROFILE_STATUS,
    TRINO_QUERY_LINKED_PRODUCTION_REVIEW_PROFILE,
    TRINO_QUERY_LINKED_PRODUCTION_REVIEW_PROFILE_STATUS,
    TRINO_QUERY_LINKED_REQUIRED_OPERATOR_CONNECTOR_TELEMETRY_DECISIONS,
    TRINO_QUERY_LINKED_UNSUPPORTED_GAP_DECISION,
    TRINO_QUERY_LINKED_REQUIRED_CORE_FAMILIES,
    TRINO_QUERY_LINKED_REQUIRED_CORE_LINKAGE_SCOPES,
    TRINO_QUERY_LINKED_REQUIRED_OPEN_BLOCKER_FAMILIES,
    TRINO_QUERY_LINKED_REQUIRED_SOURCE_GRANULARITIES,
    TRINO_QUERY_LINKED_FACT_COVERAGE_GATE,
    TRINO_QUERY_LINKED_FACT_COVERAGE_STATUS,
    TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
)
from query_doctor.trino.representative_evidence import (
    TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE,
    TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_KINDS,
    TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_STATUSES,
    TRINO_REPRESENTATIVE_EVIDENCE_GATE,
    TRINO_REPRESENTATIVE_EVIDENCE_STATUS,
    TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND,
    TRINO_SQL_EXECUTION_STATUS,
)
from query_doctor.trino.report_optimizer_safety import (
    TRINO_REPORT_OPTIMIZER_GENERATED_SQL_STATUS,
    TRINO_REPORT_OPTIMIZER_LLM_REPORTS_STATUS,
    TRINO_REPORT_OPTIMIZER_PRODUCTION_REVIEW_PROFILE,
    TRINO_REPORT_OPTIMIZER_PRODUCTION_REVIEW_PROFILE_STATUS,
    TRINO_REPORT_OPTIMIZER_QUERY_OPTIMIZER_JOBS_STATUS,
    TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_CAPABILITIES,
    TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_FAMILIES,
    TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_POLICY_FIELDS,
    TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_PRODUCT_SURFACE_REQUIREMENTS,
    TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_VALIDATORS,
    TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_VALIDATOR_SENTINELS,
    TRINO_REPORT_OPTIMIZER_SAFETY_GATE,
    TRINO_REPORT_OPTIMIZER_SAFETY_STATUS,
    TRINO_REPORT_OPTIMIZER_SAFETY_SUMMARY_KIND,
    TRINO_REPORT_OPTIMIZER_SOURCE_BOUNDARY,
    TRINO_REPORT_OPTIMIZER_SQL_EXECUTION_STATUS,
)


TRINO_PRODUCTION_CLOSURE_SUMMARY_KIND = "trino_production_closure_audit_v1"
TRINO_PRODUCTION_CLOSURE_STATUS = "bounded_production_claim_ready"
TRINO_PRODUCTION_CLOSURE_NOT_READY_STATUS = "not_closed"

TRINO_PRODUCT_SURFACE_AUDIT_SUMMARY_KIND = "trino_product_surface_boundary_audit_v1"
TRINO_SHARED_DEPLOYMENT_AUDIT_SUMMARY_KIND = "trino_shared_deployment_boundary_audit_v1"
TRINO_SUPPORT_GAP_SUMMARY_KIND = "trino_support_gap_matrix_audit_v1"
TRINO_SHARED_DEPLOYMENT_PRODUCTION_REVIEW_PROFILE = "production_review_shared_deployment_v1"
TRINO_SHARED_DEPLOYMENT_PRODUCTION_REVIEW_PROFILE_STATUS = "ready"

TRINO_PRODUCT_SURFACES_STATUS = "recent_query_id_raw_free_details_python_report_optimizer_guidance"
TRINO_LOCAL_PRODUCTION_SUPPORT_STATUS = "local_production"
TRINO_DETAILS_CASE_VIEW_STATUS = "raw_free_materialized"
TRINO_PYTHON_REPORT_STATUS = "raw_free_materialized"
TRINO_OPTIMIZER_GUIDANCE_STATUS = "raw_free_materialized"
TRINO_OPTIMIZER_BEHAVIOR_STATUS = "guidance_only"
TRINO_LLM_REPORTS_STATUS = "not_wired"
TRINO_LIVE_RECENT_SCAN_STATUS = "retained_query_list_local_production"
TRINO_LIVE_KNOWN_QUERY_DIAGNOSIS_STATUS = "one_query_pruned_query_info_local_production"
TRINO_SUPPORT_GAP_STATUS = "bounded_production_claim_pinned"

TRINO_BROADER_PRODUCTION_CLOSURE_GATES = (
    "trino_production_collector_contracts",
    "trino_representative_real_cluster_evidence",
    "trino_query_linked_fact_coverage",
    "trino_product_metadata_collection",
    "trino_report_optimizer_safety",
    "trino_shared_deployment_readiness",
    "trino_browser_report_regression",
    "trino_support_claim_update",
)
TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_FAMILIES = (
    "deployment_boundary",
    "product_boundary",
    "capability_manifest",
    "release_bundle",
    "shared_deployment_docs",
)
TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_CONFIG_REQUIREMENTS = (
    "config_source_inventory",
    "trusted_front_door_review",
    "trusted_viewer_identity",
    "raw_source_reveal_blocked",
)
TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_PRODUCT_BOUNDARY_REQUIREMENTS = (
    "details",
    "python_report",
    "optimizer_guidance",
    "optimizer_behavior",
    "llm_reports",
    "unsupported_surfaces_blocked",
)
TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_CAPABILITY_REQUIREMENTS = (
    "product_capability_surface_set",
    "product_capability_classification",
    "product_capability_raw_policy",
    "dev_gate_classification",
)
TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_RELEASE_REQUIREMENTS = (
    "release_bundle_shared_deployment_gate",
)
TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_DOC_REQUIREMENTS = (
    "trino_shared_deployment_hardening_doc",
    "trino_beta_ui_readiness_doc",
    "public_release_readiness_doc",
    "release_checklist_doc",
)
TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_UNSUPPORTED_SURFACES = (
    "running_scan",
    "query_history_crawling",
    "product_metadata_collection",
    "llm_reports",
    "query_optimizer_jobs",
    "generated_trino_sql",
    "sql_execution",
)


@dataclass(frozen=True)
class TrinoProductionClosureGate:
    gate_id: str
    tracking_state: str
    blocker: str
    summary_kind: str | None = None
    script_path: str | None = None
    capability_surface_id: str | None = None
    status_field: str | None = None
    expected_status: str | None = None


@dataclass(frozen=True)
class TrinoProductionClosureIssue:
    category: str
    message: str
    gate_id: str | None = None
    summary_kind: str | None = None


@dataclass(frozen=True)
class TrinoProductionClosureGateTracking:
    gate_id: str
    summary_kind: str | None
    tracking_input_status: str
    issue_count: int


@dataclass
class TrinoProductionClosureAuditResult:
    gate_count: int = 0
    open_gate_count: int = 0
    summary_backed_gate_count: int = 0
    unbacked_gate_count: int = 0
    summary_input_count: int = 0
    current_tracking_summary_kind_count: int = 0
    current_tracking_summary_ready_count: int = 0
    current_tracking_summary_status: str = "not_required"
    invalid_current_tracking_summary_count: int = 0
    missing_current_tracking_summary_count: int = 0
    support_gap_gate_count: int = 0
    representative_evidence_linkage_required: bool = False
    representative_evidence_linkage_ready_count: int = 0
    representative_evidence_linkage_invalid_summary_count: int = 0
    representative_evidence_linkage_missing_summary_count: int = 0
    representative_evidence_linkage_status: str = "not_required"
    status_counts: Counter[str] = field(default_factory=Counter)
    tracking_state_counts: Counter[str] = field(default_factory=Counter)
    gate_tracking_counts: Counter[str] = field(default_factory=Counter)
    summary_kind_counts: Counter[str] = field(default_factory=Counter)
    gate_summary_counts: Counter[str] = field(default_factory=Counter)
    blocker_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    gate_tracking: list[TrinoProductionClosureGateTracking] = field(default_factory=list)
    issues: list[TrinoProductionClosureIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issue_counts


TRINO_PRODUCTION_CLOSURE_GATE_SPECS = (
    TrinoProductionClosureGate(
        gate_id=TRINO_PRODUCTION_COLLECTOR_CONTRACTS_GATE,
        tracking_state="tracked_by_dedicated_audit",
        blocker="collector_contracts_require_broader_sources_evidence_and_regression_tests",
        summary_kind=TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND,
        script_path="scripts/audit_trino_production_collector_contracts.py",
        capability_surface_id="production_collector_contracts_audit",
        status_field="production_collector_contracts_status",
        expected_status=TRINO_PRODUCTION_COLLECTOR_CONTRACTS_STATUS,
    ),
    TrinoProductionClosureGate(
        gate_id=TRINO_REPRESENTATIVE_EVIDENCE_GATE,
        tracking_state="tracked_by_dedicated_audit",
        blocker="representative_evidence_requires_retained_real_cluster_breadth",
        summary_kind=TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND,
        script_path="scripts/audit_trino_representative_evidence.py",
        capability_surface_id="representative_evidence_audit",
        status_field="representative_evidence_status",
        expected_status=TRINO_REPRESENTATIVE_EVIDENCE_STATUS,
    ),
    TrinoProductionClosureGate(
        gate_id=TRINO_QUERY_LINKED_FACT_COVERAGE_GATE,
        tracking_state="tracked_by_dedicated_audit",
        blocker="query_linked_fact_coverage_requires_operator_split_and_telemetry_sources",
        summary_kind=TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
        script_path="scripts/audit_trino_query_linked_fact_coverage.py",
        capability_surface_id="query_linked_fact_coverage_audit",
        status_field="query_linked_fact_coverage_status",
        expected_status=TRINO_QUERY_LINKED_FACT_COVERAGE_STATUS,
    ),
    TrinoProductionClosureGate(
        gate_id=TRINO_PRODUCT_METADATA_COLLECTION_GATE,
        tracking_state="tracked_by_dedicated_audit",
        blocker="product_metadata_collection_requires_allowlisted_python_owned_read_only_statements",
        summary_kind=TRINO_PRODUCT_METADATA_COLLECTION_SUMMARY_KIND,
        script_path="scripts/audit_trino_product_metadata_collection.py",
        capability_surface_id="product_metadata_collection_audit",
        status_field="product_metadata_collection_status",
        expected_status=TRINO_PRODUCT_METADATA_COLLECTION_STATUS,
    ),
    TrinoProductionClosureGate(
        gate_id=TRINO_REPORT_OPTIMIZER_SAFETY_GATE,
        tracking_state="tracked_by_dedicated_audit",
        blocker="report_optimizer_safety_requires_trino_claim_validation_and_leak_tests",
        summary_kind=TRINO_REPORT_OPTIMIZER_SAFETY_SUMMARY_KIND,
        script_path="scripts/audit_trino_report_optimizer_safety.py",
        capability_surface_id="report_optimizer_safety_audit",
        status_field="report_optimizer_safety_status",
        expected_status=TRINO_REPORT_OPTIMIZER_SAFETY_STATUS,
    ),
    TrinoProductionClosureGate(
        gate_id="trino_shared_deployment_readiness",
        tracking_state="tracked_by_shared_deployment_audit",
        blocker="shared_deployment_requires_front_door_identity_and_operator_review",
        summary_kind=TRINO_SHARED_DEPLOYMENT_AUDIT_SUMMARY_KIND,
        script_path="scripts/audit_trino_shared_deployment_boundary.py",
        capability_surface_id="shared_deployment_audit",
    ),
    TrinoProductionClosureGate(
        gate_id=TRINO_BROWSER_REPORT_REGRESSION_GATE,
        tracking_state="tracked_by_dedicated_audit",
        blocker="browser_report_regression_requires_raw_free_surface_coverage",
        summary_kind=TRINO_BROWSER_REPORT_REGRESSION_SUMMARY_KIND,
        script_path="scripts/audit_trino_browser_report_regression.py",
        capability_surface_id="browser_report_regression_audit",
        status_field="browser_report_regression_status",
        expected_status=TRINO_BROWSER_REPORT_REGRESSION_STATUS,
    ),
    TrinoProductionClosureGate(
        gate_id="trino_support_claim_update",
        tracking_state="tracked_by_support_gap_audit",
        blocker="support_claim_update_requires_matrix_readme_docs_manifest_and_audit_update",
        summary_kind=TRINO_SUPPORT_GAP_SUMMARY_KIND,
        script_path="scripts/audit_trino_support_gap_matrix.py",
        capability_surface_id="support_gap_matrix_audit",
    ),
)

TRINO_CURRENT_TRACKING_SUMMARY_KINDS = frozenset(
    gate.summary_kind for gate in TRINO_PRODUCTION_CLOSURE_GATE_SPECS if gate.summary_kind
)
TRINO_ACCEPTED_CLOSURE_SUMMARY_KINDS = TRINO_CURRENT_TRACKING_SUMMARY_KINDS
TRINO_GATE_TRACKING_MISSING_ISSUE_CATEGORIES = frozenset(
    {
        "trino_closure_tracking_summary_missing",
        "trino_closure_representative_evidence_summary_missing",
    }
)


def audit_trino_production_closure_gates(
    summary_payloads: Iterable[Mapping[str, Any]] = (),
    *,
    support_gap_gates: Iterable[str] = TRINO_BROADER_PRODUCTION_CLOSURE_GATES,
    capabilities: Iterable[EngineCapability] | None = None,
    require_current_tracking_summaries: bool = False,
) -> TrinoProductionClosureAuditResult:
    result = TrinoProductionClosureAuditResult(
        current_tracking_summary_kind_count=len(TRINO_CURRENT_TRACKING_SUMMARY_KINDS),
    )
    support_gap_gate_tuple = tuple(support_gap_gates)
    result.support_gap_gate_count = len(support_gap_gate_tuple)
    if support_gap_gate_tuple != TRINO_BROADER_PRODUCTION_CLOSURE_GATES:
        _add_issue(
            result,
            "trino_closure_gate_list_drift",
            "The support-gap broader production closure gate list drifted from the closure audit.",
        )

    capabilities_by_surface = _capabilities_by_surface(
        engine_capabilities("trino") if capabilities is None else capabilities
    )
    _audit_gate_specs(result, capabilities_by_surface)
    seen_summary_kinds: set[str] = set()
    summary_payloads_by_kind: dict[str, Mapping[str, Any]] = {}
    for payload in summary_payloads:
        _audit_summary_payload(result, payload, seen_summary_kinds, summary_payloads_by_kind)

    if require_current_tracking_summaries:
        missing = sorted(TRINO_CURRENT_TRACKING_SUMMARY_KINDS - seen_summary_kinds)
        result.missing_current_tracking_summary_count = len(missing)
        for summary_kind in missing:
            _add_issue(
                result,
                "trino_closure_tracking_summary_missing",
                "A current Trino closure tracking summary input is required.",
                summary_kind=summary_kind,
            )
    _audit_cross_summary_linkage(result, summary_payloads_by_kind)
    if require_current_tracking_summaries:
        _finalize_current_tracking_summary_status(result, seen_summary_kinds)
    _finalize_gate_tracking(
        result,
        seen_summary_kinds,
        require_current_tracking_summaries=require_current_tracking_summaries,
    )
    return result


def trino_production_closure_summary_payload(
    result: TrinoProductionClosureAuditResult,
    *,
    status: str,
    require_current_tracking_summaries: bool,
) -> dict[str, Any]:
    production_closure_status = _production_closure_status(
        result,
        require_current_tracking_summaries=require_current_tracking_summaries,
    )
    return {
        "summary_kind": TRINO_PRODUCTION_CLOSURE_SUMMARY_KIND,
        "status": status,
        "production_closure_status": production_closure_status,
        "broader_production_closure_status": production_closure_status,
        "trino_sql_execution": TRINO_SQL_EXECUTION_STATUS,
        "gate_count": result.gate_count,
        "open_gate_count": result.open_gate_count,
        "summary_backed_gate_count": result.summary_backed_gate_count,
        "unbacked_gate_count": result.unbacked_gate_count,
        "summary_input_count": result.summary_input_count,
        "current_tracking_summary_kind_count": result.current_tracking_summary_kind_count,
        "current_tracking_summary_ready_count": result.current_tracking_summary_ready_count,
        "current_tracking_summary_status": result.current_tracking_summary_status,
        "invalid_current_tracking_summary_count": result.invalid_current_tracking_summary_count,
        "missing_current_tracking_summary_count": result.missing_current_tracking_summary_count,
        "support_gap_gate_count": result.support_gap_gate_count,
        "representative_evidence_linkage_required": (
            result.representative_evidence_linkage_required
        ),
        "representative_evidence_linkage_ready_count": (
            result.representative_evidence_linkage_ready_count
        ),
        "representative_evidence_linkage_invalid_summary_count": (
            result.representative_evidence_linkage_invalid_summary_count
        ),
        "representative_evidence_linkage_missing_summary_count": (
            result.representative_evidence_linkage_missing_summary_count
        ),
        "representative_evidence_linkage_status": result.representative_evidence_linkage_status,
        "require_current_tracking_summaries": require_current_tracking_summaries,
        "current_tracking_summary_kinds": sorted(TRINO_CURRENT_TRACKING_SUMMARY_KINDS),
        "gate_tracking_counts": _counter_payload(result.gate_tracking_counts),
        "gate_tracking": [
            {
                "gate_id": gate_tracking.gate_id,
                "summary_kind": gate_tracking.summary_kind,
                "tracking_input_status": gate_tracking.tracking_input_status,
                "issue_count": gate_tracking.issue_count,
            }
            for gate_tracking in result.gate_tracking
        ],
        "closure_gates": [
            {
                "gate_id": gate.gate_id,
                "tracking_state": gate.tracking_state,
                "summary_kind": gate.summary_kind,
                "script_path": gate.script_path,
                "capability_surface_id": gate.capability_surface_id,
                "blocker": gate.blocker,
            }
            for gate in TRINO_PRODUCTION_CLOSURE_GATE_SPECS
        ],
        "counters": {
            "statuses": _counter_payload(result.status_counts),
            "tracking_states": _counter_payload(result.tracking_state_counts),
            "gate_tracking": _counter_payload(result.gate_tracking_counts),
            "summary_kinds": _counter_payload(result.summary_kind_counts),
            "gate_summaries": _counter_payload(result.gate_summary_counts),
            "blockers": _counter_payload(result.blocker_counts),
            "issues": _counter_payload(result.issue_counts),
        },
        "issues": {
            "counts": _counter_payload(result.issue_counts),
            "items": [
                {
                    "category": issue.category,
                    "message": issue.message,
                    "gate_id": issue.gate_id,
                    "summary_kind": issue.summary_kind,
                }
                for issue in result.issues
            ],
        },
    }


def _audit_gate_specs(
    result: TrinoProductionClosureAuditResult,
    capabilities_by_surface: Mapping[str, EngineCapability],
) -> None:
    for gate in TRINO_PRODUCTION_CLOSURE_GATE_SPECS:
        result.gate_count += 1
        result.tracking_state_counts[gate.tracking_state] += 1
        result.blocker_counts[gate.blocker] += 1
        if gate.summary_kind:
            result.summary_backed_gate_count += 1
        else:
            result.unbacked_gate_count += 1
        if gate.capability_surface_id is not None:
            _audit_tracking_capability(result, gate, capabilities_by_surface)


def _audit_tracking_capability(
    result: TrinoProductionClosureAuditResult,
    gate: TrinoProductionClosureGate,
    capabilities_by_surface: Mapping[str, EngineCapability],
) -> None:
    capability = capabilities_by_surface.get(gate.capability_surface_id or "")
    if capability is None:
        _add_issue(
            result,
            "trino_closure_tracking_capability_missing",
            "A Trino closure tracking audit is missing from the capability manifest.",
            gate_id=gate.gate_id,
            summary_kind=gate.summary_kind,
        )
        return
    if capability.script_path != gate.script_path:
        _add_issue(
            result,
            "trino_closure_tracking_script_drift",
            "A Trino closure tracking audit script path drifted from the closure gate plan.",
            gate_id=gate.gate_id,
            summary_kind=gate.summary_kind,
        )
    if (
        capability.support_level != "dev_gate"
        or capability.surface_class != "dev_gate"
        or not capability.dev_only
        or capability.product_surface_allowed
    ):
        _add_issue(
            result,
            "trino_closure_tracking_capability_promoted",
            "A Trino closure tracking audit must remain a dev-only non-product gate.",
            gate_id=gate.gate_id,
            summary_kind=gate.summary_kind,
        )


def _audit_summary_payload(
    result: TrinoProductionClosureAuditResult,
    payload: Mapping[str, Any],
    seen_summary_kinds: set[str],
    summary_payloads_by_kind: dict[str, Mapping[str, Any]],
) -> None:
    result.summary_input_count += 1
    summary_kind = payload.get("summary_kind")
    if not isinstance(summary_kind, str):
        _add_issue(
            result,
            "trino_closure_summary_kind_missing",
            "A closure summary input must carry a string summary_kind.",
        )
        return
    if summary_kind not in TRINO_ACCEPTED_CLOSURE_SUMMARY_KINDS:
        _add_issue(
            result,
            "trino_closure_summary_kind_unknown",
            "A closure summary input has no current Trino production closure role.",
            summary_kind=summary_kind,
        )
        return
    if summary_kind in seen_summary_kinds:
        _add_issue(
            result,
            "trino_closure_summary_kind_duplicate",
            "A closure summary kind may be provided only once for a promotion decision.",
            summary_kind=summary_kind,
        )
    seen_summary_kinds.add(summary_kind)
    summary_payloads_by_kind.setdefault(summary_kind, payload)
    result.summary_kind_counts[summary_kind] += 1
    for gate in _gates_for_summary_kind(summary_kind):
        result.gate_summary_counts[gate.gate_id] += 1

    if payload.get("status") != "ok":
        _add_issue(
            result,
            "trino_closure_summary_status_not_ok",
            "A closure tracking summary must have status ok before it can be retained.",
            summary_kind=summary_kind,
        )
    _audit_summary_issues_empty(result, payload, summary_kind=summary_kind)
    if summary_kind == TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND:
        _audit_production_collector_summary(result, payload)
    elif summary_kind == TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND:
        _audit_representative_evidence_summary(result, payload)
    elif summary_kind == TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND:
        _audit_query_linked_fact_coverage_summary(result, payload)
    elif summary_kind == TRINO_PRODUCT_METADATA_COLLECTION_SUMMARY_KIND:
        _audit_product_metadata_collection_summary(result, payload)
    elif summary_kind == TRINO_REPORT_OPTIMIZER_SAFETY_SUMMARY_KIND:
        _audit_report_optimizer_safety_summary(result, payload)
    elif summary_kind == TRINO_BROWSER_REPORT_REGRESSION_SUMMARY_KIND:
        _audit_browser_report_regression_summary(result, payload)
    elif summary_kind == TRINO_PRODUCT_SURFACE_AUDIT_SUMMARY_KIND:
        _audit_product_surface_summary(result, payload)
    elif summary_kind == TRINO_SHARED_DEPLOYMENT_AUDIT_SUMMARY_KIND:
        _audit_shared_deployment_summary(result, payload)
    elif summary_kind == TRINO_SUPPORT_GAP_SUMMARY_KIND:
        _audit_support_gap_summary(result, payload)


def _audit_cross_summary_linkage(
    result: TrinoProductionClosureAuditResult,
    summary_payloads_by_kind: Mapping[str, Mapping[str, Any]],
) -> None:
    collector_summary = summary_payloads_by_kind.get(
        TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND
    )
    representative_summary = summary_payloads_by_kind.get(
        TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND
    )
    if collector_summary is None:
        return
    collector_links_representative = _collector_summary_links_representative_evidence(
        collector_summary
    )
    if representative_summary is not None or collector_links_representative:
        result.representative_evidence_linkage_required = True
    linkage_summary_kinds = {TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND}
    if representative_summary is not None:
        linkage_summary_kinds.add(TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND)
    result.representative_evidence_linkage_invalid_summary_count = len(
        _summary_kinds_with_issues(result, linkage_summary_kinds)
    )
    if representative_summary is not None and not collector_links_representative:
        _add_issue(
            result,
            "trino_closure_collector_representative_evidence_linkage_missing",
            "The collector closure summary must link the retained representative evidence summary.",
            summary_kind=TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND,
        )
        result.representative_evidence_linkage_status = "failed"
    elif representative_summary is None and collector_links_representative:
        result.representative_evidence_linkage_missing_summary_count = 1
        _add_issue(
            result,
            "trino_closure_representative_evidence_summary_missing",
            "A collector summary with ready representative evidence must be paired with that summary input.",
            summary_kind=TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND,
        )
        result.representative_evidence_linkage_status = "failed"
    elif representative_summary is not None and collector_links_representative:
        if result.representative_evidence_linkage_invalid_summary_count:
            result.representative_evidence_linkage_status = "failed"
        else:
            result.representative_evidence_linkage_ready_count = 1
            result.representative_evidence_linkage_status = "ready"


def _finalize_current_tracking_summary_status(
    result: TrinoProductionClosureAuditResult,
    seen_summary_kinds: set[str],
) -> None:
    present_summary_kinds = TRINO_CURRENT_TRACKING_SUMMARY_KINDS & seen_summary_kinds
    invalid_present_summary_kinds = _summary_kinds_with_issues(result, present_summary_kinds)
    result.invalid_current_tracking_summary_count = len(invalid_present_summary_kinds)
    result.current_tracking_summary_ready_count = len(
        present_summary_kinds - invalid_present_summary_kinds
    )
    if result.missing_current_tracking_summary_count:
        result.current_tracking_summary_status = "incomplete"
    elif result.invalid_current_tracking_summary_count:
        result.current_tracking_summary_status = "failed"
    else:
        result.current_tracking_summary_status = "ready"


def _finalize_gate_tracking(
    result: TrinoProductionClosureAuditResult,
    seen_summary_kinds: set[str],
    *,
    require_current_tracking_summaries: bool,
) -> None:
    result.gate_tracking.clear()
    result.gate_tracking_counts.clear()
    for gate in TRINO_PRODUCTION_CLOSURE_GATE_SPECS:
        issues = _issues_for_gate(result, gate)
        tracking_input_status = _gate_tracking_input_status(
            gate,
            issues,
            seen_summary_kinds,
        )
        result.gate_tracking.append(
            TrinoProductionClosureGateTracking(
                gate_id=gate.gate_id,
                summary_kind=gate.summary_kind,
                tracking_input_status=tracking_input_status,
                issue_count=len(issues),
            )
        )
        result.gate_tracking_counts[tracking_input_status] += 1
    if require_current_tracking_summaries:
        result.open_gate_count = result.gate_count - result.gate_tracking_counts.get("accepted", 0)
    else:
        result.open_gate_count = result.gate_count
    result.status_counts.clear()
    result.status_counts[
        _production_closure_status(
            result,
            require_current_tracking_summaries=require_current_tracking_summaries,
        )
    ] = result.gate_count


def _production_closure_status(
    result: TrinoProductionClosureAuditResult,
    *,
    require_current_tracking_summaries: bool,
) -> str:
    if (
        require_current_tracking_summaries
        and result.ok
        and result.current_tracking_summary_status == "ready"
        and result.gate_tracking_counts.get("accepted") == result.gate_count
        and result.representative_evidence_linkage_status in {"ready", "not_required"}
    ):
        return TRINO_PRODUCTION_CLOSURE_STATUS
    return TRINO_PRODUCTION_CLOSURE_NOT_READY_STATUS


def _gate_tracking_input_status(
    gate: TrinoProductionClosureGate,
    issues: tuple[TrinoProductionClosureIssue, ...],
    seen_summary_kinds: set[str],
) -> str:
    summary_kind = gate.summary_kind
    summary_present = summary_kind in seen_summary_kinds if summary_kind is not None else False
    if not summary_present and any(
        issue.category in TRINO_GATE_TRACKING_MISSING_ISSUE_CATEGORIES for issue in issues
    ):
        return "missing"
    if issues:
        return "invalid"
    if summary_present:
        return "accepted"
    return "not_required"


def _issues_for_gate(
    result: TrinoProductionClosureAuditResult,
    gate: TrinoProductionClosureGate,
) -> tuple[TrinoProductionClosureIssue, ...]:
    return tuple(
        issue
        for issue in result.issues
        if issue.gate_id == gate.gate_id
        or (gate.summary_kind is not None and issue.summary_kind == gate.summary_kind)
    )


def _summary_kinds_with_issues(
    result: TrinoProductionClosureAuditResult,
    summary_kinds: set[str],
) -> set[str]:
    return {issue.summary_kind for issue in result.issues if issue.summary_kind in summary_kinds}


def _collector_summary_links_representative_evidence(
    collector_summary: Mapping[str, Any],
) -> bool:
    return (
        collector_summary.get("representative_evidence_required") is True
        and collector_summary.get("representative_evidence_contract_status")
        == TRINO_PRODUCTION_COLLECTOR_REPRESENTATIVE_EVIDENCE_READY
        and _positive_int(collector_summary.get("representative_evidence_summary_count"))
        and _positive_int(collector_summary.get("representative_evidence_ready_count"))
    )


def _audit_production_collector_summary(
    result: TrinoProductionClosureAuditResult,
    payload: Mapping[str, Any],
) -> None:
    _expect_payload_value(
        result,
        payload,
        ("closure_gate",),
        TRINO_PRODUCTION_COLLECTOR_CONTRACTS_GATE,
        category="trino_closure_collector_gate_drift",
        summary_kind=TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND,
    )
    _expect_payload_value(
        result,
        payload,
        ("production_collector_contracts_status",),
        TRINO_PRODUCTION_COLLECTOR_CONTRACTS_STATUS,
        category="trino_closure_collector_status_drift",
        summary_kind=TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND,
    )
    _audit_common_not_closed_sql_free(
        result,
        payload,
        summary_kind=TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND,
    )
    if not _positive_int(payload.get("open_blocker_count")):
        _add_issue(
            result,
            "trino_closure_collector_blocker_missing",
            "The collector closure summary must retain open production blockers.",
            summary_kind=TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND,
        )
    representative_evidence_status = payload.get("representative_evidence_contract_status")
    if representative_evidence_status not in {
        TRINO_PRODUCTION_COLLECTOR_REPRESENTATIVE_EVIDENCE_NOT_PROVIDED,
        TRINO_PRODUCTION_COLLECTOR_REPRESENTATIVE_EVIDENCE_READY,
    }:
        _add_issue(
            result,
            "trino_closure_collector_representative_evidence_drift",
            "The collector closure summary must retain a known representative-evidence handoff status.",
            summary_kind=TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND,
        )
    if (
        payload.get("representative_evidence_required") is True
        and representative_evidence_status
        != TRINO_PRODUCTION_COLLECTOR_REPRESENTATIVE_EVIDENCE_READY
    ):
        _add_issue(
            result,
            "trino_closure_collector_representative_evidence_required_not_ready",
            "Required retained representative evidence must be ready before collector promotion review.",
            summary_kind=TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND,
        )
    if (
        representative_evidence_status == TRINO_PRODUCTION_COLLECTOR_REPRESENTATIVE_EVIDENCE_READY
        and not _positive_int(payload.get("representative_evidence_ready_count"))
    ):
        _add_issue(
            result,
            "trino_closure_collector_representative_evidence_drift",
            "Ready retained representative evidence must include a positive ready summary count.",
            summary_kind=TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND,
        )


def _audit_representative_evidence_summary(
    result: TrinoProductionClosureAuditResult,
    payload: Mapping[str, Any],
) -> None:
    _expect_payload_value(
        result,
        payload,
        ("closure_gate",),
        TRINO_REPRESENTATIVE_EVIDENCE_GATE,
        category="trino_closure_representative_gate_drift",
        summary_kind=TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND,
    )
    _expect_payload_value(
        result,
        payload,
        ("representative_evidence_status",),
        TRINO_REPRESENTATIVE_EVIDENCE_STATUS,
        category="trino_closure_representative_status_drift",
        summary_kind=TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND,
    )
    _audit_common_not_closed_sql_free(
        result,
        payload,
        summary_kind=TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND,
    )
    requirements = payload.get("requirements")
    requirement_profile = (
        requirements.get("requirement_profile") if isinstance(requirements, Mapping) else None
    )
    if requirement_profile != TRINO_REPRESENTATIVE_EVIDENCE_PRODUCTION_REVIEW_PROFILE:
        _add_issue(
            result,
            "trino_closure_representative_breadth_profile_drift",
            "Representative evidence closure summaries must use the production-review breadth profile.",
            summary_kind=TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND,
        )
    if not _summary_requirements_include(
        requirements,
        "require_summary_kinds",
        TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_KINDS,
    ):
        _add_issue(
            result,
            "trino_closure_representative_summary_kind_drift",
            "Representative evidence closure summaries must require the production-review summary-kind mix.",
            summary_kind=TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND,
        )
    if not _summary_requirements_include(
        requirements,
        "require_summary_statuses",
        TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_STATUSES,
    ):
        _add_issue(
            result,
            "trino_closure_representative_summary_status_drift",
            "Representative evidence closure summaries must require accepted retained input statuses.",
            summary_kind=TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND,
        )
    _expect_payload_value(
        result,
        payload,
        ("breadth_profile_status",),
        "ready",
        category="trino_closure_representative_breadth_profile_drift",
        summary_kind=TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND,
    )
    if not _positive_int(payload.get("evidence_unit_count")):
        _add_issue(
            result,
            "trino_closure_representative_breadth_profile_drift",
            "A production-review representative evidence summary must retain evidence units.",
            summary_kind=TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND,
        )
    counters = payload.get("counters")
    if not isinstance(counters, Mapping):
        counters = {}
    if not _counter_has_positive_labels(
        counters.get("summary_kinds"),
        TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_KINDS,
    ):
        _add_issue(
            result,
            "trino_closure_representative_summary_kind_drift",
            "Representative evidence closure summaries must retain required summary-kind counters.",
            summary_kind=TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND,
        )
    if not _counter_has_positive_labels(
        counters.get("statuses"),
        TRINO_REPRESENTATIVE_EVIDENCE_REQUIRED_SUMMARY_STATUSES,
    ):
        _add_issue(
            result,
            "trino_closure_representative_summary_status_drift",
            "Representative evidence closure summaries must retain accepted input-status counters.",
            summary_kind=TRINO_REPRESENTATIVE_EVIDENCE_SUMMARY_KIND,
        )


def _audit_query_linked_fact_coverage_summary(
    result: TrinoProductionClosureAuditResult,
    payload: Mapping[str, Any],
) -> None:
    _expect_payload_value(
        result,
        payload,
        ("closure_gate",),
        TRINO_QUERY_LINKED_FACT_COVERAGE_GATE,
        category="trino_closure_query_linked_gate_drift",
        summary_kind=TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
    )
    _expect_payload_value(
        result,
        payload,
        ("query_linked_fact_coverage_status",),
        TRINO_QUERY_LINKED_FACT_COVERAGE_STATUS,
        category="trino_closure_query_linked_status_drift",
        summary_kind=TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
    )
    _audit_common_not_closed_sql_free(
        result,
        payload,
        summary_kind=TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
    )
    if not _positive_int(payload.get("open_blocker_count")):
        _add_issue(
            result,
            "trino_closure_query_linked_blocker_missing",
            "The query-linked coverage summary must retain open production blockers.",
            summary_kind=TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
        )
    _expect_payload_value(
        result,
        payload,
        ("coverage_profile",),
        TRINO_QUERY_LINKED_PRODUCTION_REVIEW_PROFILE,
        category="trino_closure_query_linked_profile_drift",
        summary_kind=TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
    )
    _expect_payload_value(
        result,
        payload,
        ("coverage_profile_status",),
        TRINO_QUERY_LINKED_PRODUCTION_REVIEW_PROFILE_STATUS,
        category="trino_closure_query_linked_profile_drift",
        summary_kind=TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
    )
    requirements = payload.get("coverage_profile_requirements")
    expected_requirement_fields = (
        ("required_core_families", TRINO_QUERY_LINKED_REQUIRED_CORE_FAMILIES),
        ("required_core_linkage_scopes", TRINO_QUERY_LINKED_REQUIRED_CORE_LINKAGE_SCOPES),
        ("required_source_granularities", TRINO_QUERY_LINKED_REQUIRED_SOURCE_GRANULARITIES),
        ("required_open_blocker_families", TRINO_QUERY_LINKED_REQUIRED_OPEN_BLOCKER_FAMILIES),
    )
    for field_name, expected_values in expected_requirement_fields:
        if not _summary_requirements_include(requirements, field_name, expected_values):
            _add_issue(
                result,
                "trino_closure_query_linked_profile_drift",
                "The query-linked coverage summary must retain production-review coverage requirements.",
                summary_kind=TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
            )
    coverage_tracking_counts = payload.get("coverage_profile_tracking_counts")
    if not _counter_has_positive_labels(coverage_tracking_counts, ("accepted",)):
        _add_issue(
            result,
            "trino_closure_query_linked_profile_drift",
            "The query-linked coverage summary must retain accepted production-review coverage tracking.",
            summary_kind=TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
        )
    _expect_payload_value(
        result,
        payload,
        ("operator_connector_telemetry_profile",),
        TRINO_QUERY_LINKED_OPERATOR_CONNECTOR_TELEMETRY_PROFILE,
        category="trino_closure_query_linked_decision_profile_drift",
        summary_kind=TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
    )
    _expect_payload_value(
        result,
        payload,
        ("operator_connector_telemetry_profile_status",),
        TRINO_QUERY_LINKED_OPERATOR_CONNECTOR_TELEMETRY_PROFILE_STATUS,
        category="trino_closure_query_linked_decision_profile_drift",
        summary_kind=TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
    )
    decision_requirements = payload.get("operator_connector_telemetry_decision_requirements")
    expected_decision_requirement_fields = (
        (
            "required_bounded_supported_families",
            tuple(
                family_id
                for family_id, decision in (
                    TRINO_QUERY_LINKED_REQUIRED_OPERATOR_CONNECTOR_TELEMETRY_DECISIONS
                )
                if decision == TRINO_QUERY_LINKED_BOUNDED_SUPPORTED_DECISION
            ),
        ),
        (
            "required_unsupported_gap_families",
            tuple(
                family_id
                for family_id, decision in (
                    TRINO_QUERY_LINKED_REQUIRED_OPERATOR_CONNECTOR_TELEMETRY_DECISIONS
                )
                if decision == TRINO_QUERY_LINKED_UNSUPPORTED_GAP_DECISION
            ),
        ),
    )
    for field_name, expected_values in expected_decision_requirement_fields:
        if not _summary_requirements_include(
            decision_requirements,
            field_name,
            expected_values,
        ):
            _add_issue(
                result,
                "trino_closure_query_linked_decision_profile_drift",
                "The query-linked coverage summary must retain operator/connector/telemetry decisions.",
                summary_kind=TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
            )
    decision_counts = payload.get("operator_connector_telemetry_decision_counts")
    if not _counter_has_positive_labels(
        decision_counts,
        (
            TRINO_QUERY_LINKED_BOUNDED_SUPPORTED_DECISION,
            TRINO_QUERY_LINKED_UNSUPPORTED_GAP_DECISION,
        ),
    ):
        _add_issue(
            result,
            "trino_closure_query_linked_decision_profile_drift",
            "The query-linked coverage summary must retain supported and unsupported decision counts.",
            summary_kind=TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
        )
    decision_tracking_counts = payload.get("operator_connector_telemetry_decision_tracking_counts")
    if not _counter_has_positive_labels(decision_tracking_counts, ("accepted",)):
        _add_issue(
            result,
            "trino_closure_query_linked_decision_profile_drift",
            "The query-linked coverage summary must retain accepted decision tracking.",
            summary_kind=TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
        )


def _audit_product_metadata_collection_summary(
    result: TrinoProductionClosureAuditResult,
    payload: Mapping[str, Any],
) -> None:
    expected = {
        ("closure_gate",): TRINO_PRODUCT_METADATA_COLLECTION_GATE,
        ("product_metadata_collection_status",): TRINO_PRODUCT_METADATA_COLLECTION_STATUS,
        ("broader_production_closure_status",): TRINO_PRODUCTION_CLOSURE_NOT_READY_STATUS,
        ("trino_sql_execution",): TRINO_SQL_EXECUTION_STATUS,
        ("metadata_cli_sql_execution",): TRINO_PRODUCT_METADATA_SQL_EXECUTION_STATUS,
        ("product_metadata_surfaces",): "blocked",
        ("metadata_summary_boundary",): "aggregate_only_not_diagnosis",
        ("adapter_metadata_collection",): "blocked",
    }
    for path, expected_value in expected.items():
        _expect_payload_value(
            result,
            payload,
            path,
            expected_value,
            category="trino_closure_product_metadata_boundary_drift",
            summary_kind=TRINO_PRODUCT_METADATA_COLLECTION_SUMMARY_KIND,
        )
    if not _positive_int(payload.get("open_blocker_count")):
        _add_issue(
            result,
            "trino_closure_product_metadata_blocker_missing",
            "The product metadata collection summary must retain open production blockers.",
            summary_kind=TRINO_PRODUCT_METADATA_COLLECTION_SUMMARY_KIND,
        )
    _expect_payload_value(
        result,
        payload,
        ("production_review_profile",),
        TRINO_PRODUCT_METADATA_PRODUCTION_REVIEW_PROFILE,
        category="trino_closure_product_metadata_profile_drift",
        summary_kind=TRINO_PRODUCT_METADATA_COLLECTION_SUMMARY_KIND,
    )
    _expect_payload_value(
        result,
        payload,
        ("production_review_profile_status",),
        TRINO_PRODUCT_METADATA_PRODUCTION_REVIEW_PROFILE_STATUS,
        category="trino_closure_product_metadata_profile_drift",
        summary_kind=TRINO_PRODUCT_METADATA_COLLECTION_SUMMARY_KIND,
    )
    requirements = payload.get("production_review_requirements")
    expected_requirement_fields = (
        ("required_source_families", TRINO_PRODUCT_METADATA_REQUIRED_SOURCE_FAMILIES),
        (
            "required_open_blocker_families",
            TRINO_PRODUCT_METADATA_REQUIRED_OPEN_BLOCKER_FAMILIES,
        ),
        ("required_source_surfaces", TRINO_PRODUCT_METADATA_REQUIRED_SOURCE_SURFACES),
        (
            "required_sql_execution_statuses",
            TRINO_PRODUCT_METADATA_REQUIRED_SQL_EXECUTION_STATUSES,
        ),
        (
            "required_product_surface_requirements",
            TRINO_PRODUCT_METADATA_REQUIRED_PRODUCT_SURFACE_REQUIREMENTS,
        ),
        ("required_redaction_fields", TRINO_PRODUCT_METADATA_REQUIRED_REDACTION_FIELDS),
    )
    for field_name, expected_values in expected_requirement_fields:
        if not _summary_requirements_include(requirements, field_name, expected_values):
            _add_issue(
                result,
                "trino_closure_product_metadata_profile_drift",
                "The product metadata summary must retain production-review metadata requirements.",
                summary_kind=TRINO_PRODUCT_METADATA_COLLECTION_SUMMARY_KIND,
            )
    production_review_tracking_counts = payload.get("production_review_tracking_counts")
    if not _counter_has_positive_labels(production_review_tracking_counts, ("accepted",)):
        _add_issue(
            result,
            "trino_closure_product_metadata_profile_drift",
            "The product metadata summary must retain accepted production-review tracking.",
            summary_kind=TRINO_PRODUCT_METADATA_COLLECTION_SUMMARY_KIND,
        )


def _audit_report_optimizer_safety_summary(
    result: TrinoProductionClosureAuditResult,
    payload: Mapping[str, Any],
) -> None:
    expected = {
        ("closure_gate",): TRINO_REPORT_OPTIMIZER_SAFETY_GATE,
        ("report_optimizer_safety_status",): TRINO_REPORT_OPTIMIZER_SAFETY_STATUS,
        ("broader_production_closure_status",): TRINO_PRODUCTION_CLOSURE_NOT_READY_STATUS,
        ("source_boundary",): TRINO_REPORT_OPTIMIZER_SOURCE_BOUNDARY,
        ("python_report",): TRINO_PYTHON_REPORT_STATUS,
        ("trusted_reports",): "python_report_only",
        ("optimizer_guidance",): TRINO_OPTIMIZER_GUIDANCE_STATUS,
        ("optimizer_behavior",): TRINO_OPTIMIZER_BEHAVIOR_STATUS,
        ("llm_reports",): TRINO_REPORT_OPTIMIZER_LLM_REPORTS_STATUS,
        ("query_optimizer_jobs",): TRINO_REPORT_OPTIMIZER_QUERY_OPTIMIZER_JOBS_STATUS,
        ("generated_sql",): TRINO_REPORT_OPTIMIZER_GENERATED_SQL_STATUS,
        ("trino_sql_execution",): TRINO_REPORT_OPTIMIZER_SQL_EXECUTION_STATUS,
        ("adapter_validated_reports",): "blocked",
    }
    for path, expected_value in expected.items():
        _expect_payload_value(
            result,
            payload,
            path,
            expected_value,
            category="trino_closure_report_optimizer_boundary_drift",
            summary_kind=TRINO_REPORT_OPTIMIZER_SAFETY_SUMMARY_KIND,
        )
    if not _positive_int(payload.get("open_blocker_count")):
        _add_issue(
            result,
            "trino_closure_report_optimizer_blocker_missing",
            "The report optimizer safety summary must retain open production blockers.",
            summary_kind=TRINO_REPORT_OPTIMIZER_SAFETY_SUMMARY_KIND,
        )
    if not _positive_int(payload.get("validation_sentinel_count")):
        _add_issue(
            result,
            "trino_closure_report_optimizer_validation_missing",
            "The report optimizer safety summary must retain validation sentinel coverage.",
            summary_kind=TRINO_REPORT_OPTIMIZER_SAFETY_SUMMARY_KIND,
        )
    _expect_payload_value(
        result,
        payload,
        ("production_review_profile",),
        TRINO_REPORT_OPTIMIZER_PRODUCTION_REVIEW_PROFILE,
        category="trino_closure_report_optimizer_profile_drift",
        summary_kind=TRINO_REPORT_OPTIMIZER_SAFETY_SUMMARY_KIND,
    )
    _expect_payload_value(
        result,
        payload,
        ("production_review_profile_status",),
        TRINO_REPORT_OPTIMIZER_PRODUCTION_REVIEW_PROFILE_STATUS,
        category="trino_closure_report_optimizer_profile_drift",
        summary_kind=TRINO_REPORT_OPTIMIZER_SAFETY_SUMMARY_KIND,
    )
    requirements = payload.get("production_review_requirements")
    expected_requirement_fields = (
        ("required_families", TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_FAMILIES),
        ("required_capabilities", TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_CAPABILITIES),
        ("required_policy_fields", TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_POLICY_FIELDS),
        ("required_validators", TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_VALIDATORS),
        (
            "required_validator_sentinels",
            TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_VALIDATOR_SENTINELS,
        ),
        (
            "required_product_surface_requirements",
            TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_PRODUCT_SURFACE_REQUIREMENTS,
        ),
    )
    for field_name, expected_values in expected_requirement_fields:
        if not _summary_requirements_include(requirements, field_name, expected_values):
            _add_issue(
                result,
                "trino_closure_report_optimizer_profile_drift",
                "The report optimizer summary must retain production-review requirements.",
                summary_kind=TRINO_REPORT_OPTIMIZER_SAFETY_SUMMARY_KIND,
            )
    production_review_tracking_counts = payload.get("production_review_tracking_counts")
    if not _counter_has_positive_labels(production_review_tracking_counts, ("accepted",)):
        _add_issue(
            result,
            "trino_closure_report_optimizer_profile_drift",
            "The report optimizer summary must retain accepted production-review tracking.",
            summary_kind=TRINO_REPORT_OPTIMIZER_SAFETY_SUMMARY_KIND,
        )


def _audit_browser_report_regression_summary(
    result: TrinoProductionClosureAuditResult,
    payload: Mapping[str, Any],
) -> None:
    expected = {
        ("closure_gate",): TRINO_BROWSER_REPORT_REGRESSION_GATE,
        ("browser_report_regression_status",): TRINO_BROWSER_REPORT_REGRESSION_STATUS,
        ("broader_production_closure_status",): TRINO_PRODUCTION_CLOSURE_NOT_READY_STATUS,
        ("product_surface",): TRINO_BROWSER_REPORT_PRODUCT_SURFACE,
        ("details_case_view",): TRINO_BROWSER_REPORT_DETAILS_CASE_VIEW,
        ("python_report",): TRINO_BROWSER_REPORT_PYTHON_REPORT,
        ("optimizer_guidance",): TRINO_BROWSER_REPORT_OPTIMIZER_GUIDANCE,
        ("llm_reports",): TRINO_BROWSER_REPORT_LLM_REPORTS,
        ("trino_sql_execution",): TRINO_BROWSER_REPORT_SQL_EXECUTION,
        ("raw_sql_output",): TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
        ("query_id_output",): TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
        ("url_output",): TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
        ("local_path_output",): TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
        ("metadata_identifier_output",): TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
        ("secret_output",): TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
        ("runtime_internal_output",): TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
        ("adapter_validated_reports",): "blocked",
    }
    for path, expected_value in expected.items():
        _expect_payload_value(
            result,
            payload,
            path,
            expected_value,
            category="trino_closure_browser_report_boundary_drift",
            summary_kind=TRINO_BROWSER_REPORT_REGRESSION_SUMMARY_KIND,
        )
    if not _positive_int(payload.get("open_blocker_count")):
        _add_issue(
            result,
            "trino_closure_browser_report_blocker_missing",
            "The browser/report regression summary must retain open production blockers.",
            summary_kind=TRINO_BROWSER_REPORT_REGRESSION_SUMMARY_KIND,
        )
    if not _positive_int(payload.get("required_test_count")):
        _add_issue(
            result,
            "trino_closure_browser_report_tests_missing",
            "The browser/report regression summary must retain required test coverage.",
            summary_kind=TRINO_BROWSER_REPORT_REGRESSION_SUMMARY_KIND,
        )
    if payload.get("present_test_count") != payload.get("required_test_count"):
        _add_issue(
            result,
            "trino_closure_browser_report_tests_missing",
            "The browser/report regression summary must have every required test present.",
            summary_kind=TRINO_BROWSER_REPORT_REGRESSION_SUMMARY_KIND,
        )
    _expect_payload_value(
        result,
        payload,
        ("production_review_profile",),
        TRINO_BROWSER_REPORT_PRODUCTION_REVIEW_PROFILE,
        category="trino_closure_browser_report_profile_drift",
        summary_kind=TRINO_BROWSER_REPORT_REGRESSION_SUMMARY_KIND,
    )
    _expect_payload_value(
        result,
        payload,
        ("production_review_profile_status",),
        TRINO_BROWSER_REPORT_PRODUCTION_REVIEW_PROFILE_STATUS,
        category="trino_closure_browser_report_profile_drift",
        summary_kind=TRINO_BROWSER_REPORT_REGRESSION_SUMMARY_KIND,
    )
    requirements = payload.get("production_review_requirements")
    expected_requirement_fields = (
        ("required_families", TRINO_BROWSER_REPORT_REQUIRED_REVIEW_FAMILIES),
        ("required_test_files", TRINO_BROWSER_REPORT_REQUIRED_REVIEW_TEST_FILES),
        (
            "required_route_capabilities",
            TRINO_BROWSER_REPORT_REQUIRED_REVIEW_ROUTE_CAPABILITIES,
        ),
        (
            "required_raw_output_requirements",
            TRINO_BROWSER_REPORT_REQUIRED_REVIEW_RAW_OUTPUT_REQUIREMENTS,
        ),
        (
            "required_unsupported_surface_requirements",
            TRINO_BROWSER_REPORT_REQUIRED_REVIEW_UNSUPPORTED_SURFACE_REQUIREMENTS,
        ),
        ("required_download_tests", TRINO_BROWSER_REPORT_REQUIRED_REVIEW_DOWNLOAD_TESTS),
        (
            "required_public_claim_tests",
            TRINO_BROWSER_REPORT_REQUIRED_REVIEW_PUBLIC_CLAIM_TESTS,
        ),
    )
    for field_name, expected_values in expected_requirement_fields:
        if not _summary_requirements_include(requirements, field_name, expected_values):
            _add_issue(
                result,
                "trino_closure_browser_report_profile_drift",
                "The browser/report summary must retain production-review requirements.",
                summary_kind=TRINO_BROWSER_REPORT_REGRESSION_SUMMARY_KIND,
            )
    production_review_tracking_counts = payload.get("production_review_tracking_counts")
    if not _counter_has_positive_labels(production_review_tracking_counts, ("accepted",)):
        _add_issue(
            result,
            "trino_closure_browser_report_profile_drift",
            "The browser/report summary must retain accepted production-review tracking.",
            summary_kind=TRINO_BROWSER_REPORT_REGRESSION_SUMMARY_KIND,
        )


def _audit_product_surface_summary(
    result: TrinoProductionClosureAuditResult,
    payload: Mapping[str, Any],
) -> None:
    expected = {
        ("boundary", "product_surface"): TRINO_PRODUCT_SURFACES_STATUS,
        ("boundary", "support_claim"): TRINO_LOCAL_PRODUCTION_SUPPORT_STATUS,
        ("boundary", "details_case_view"): TRINO_DETAILS_CASE_VIEW_STATUS,
        ("boundary", "python_report"): TRINO_PYTHON_REPORT_STATUS,
        ("boundary", "optimizer_guidance"): TRINO_OPTIMIZER_GUIDANCE_STATUS,
        ("boundary", "optimizer_behavior"): TRINO_OPTIMIZER_BEHAVIOR_STATUS,
        ("boundary", "llm_reports"): TRINO_LLM_REPORTS_STATUS,
        ("boundary", "live_recent_scan"): TRINO_LIVE_RECENT_SCAN_STATUS,
        ("boundary", "live_known_query_diagnosis"): TRINO_LIVE_KNOWN_QUERY_DIAGNOSIS_STATUS,
        ("boundary", "trino_sql_execution"): TRINO_SQL_EXECUTION_STATUS,
        ("registry", "trino_product_cli"): "blocked",
    }
    for path, expected_value in expected.items():
        _expect_payload_value(
            result,
            payload,
            path,
            expected_value,
            category="trino_closure_product_surface_boundary_drift",
            summary_kind=TRINO_PRODUCT_SURFACE_AUDIT_SUMMARY_KIND,
        )


def _audit_shared_deployment_summary(
    result: TrinoProductionClosureAuditResult,
    payload: Mapping[str, Any],
) -> None:
    expected = {
        ("deployment_boundary", "trusted_front_door_identity"): "required_for_shared_trino",
        ("deployment_boundary", "raw_source_reveal"): "blocked_for_shared_trino",
        ("deployment_boundary", "paths_printed"): False,
        ("deployment_boundary", "header_values_printed"): False,
        ("deployment_boundary", "query_ids_printed"): False,
        ("product_boundary", "details_case_view"): TRINO_DETAILS_CASE_VIEW_STATUS,
        ("product_boundary", "python_report"): TRINO_PYTHON_REPORT_STATUS,
        ("product_boundary", "optimizer_guidance"): TRINO_OPTIMIZER_GUIDANCE_STATUS,
        ("product_boundary", "optimizer_behavior"): TRINO_OPTIMIZER_BEHAVIOR_STATUS,
        ("product_boundary", "llm_reports"): TRINO_LLM_REPORTS_STATUS,
        ("product_boundary", "metadata_collection"): "not_wired",
    }
    for path, expected_value in expected.items():
        _expect_payload_value(
            result,
            payload,
            path,
            expected_value,
            category="trino_closure_shared_deployment_boundary_drift",
            summary_kind=TRINO_SHARED_DEPLOYMENT_AUDIT_SUMMARY_KIND,
        )
    _expect_payload_value(
        result,
        payload,
        ("production_review_profile",),
        TRINO_SHARED_DEPLOYMENT_PRODUCTION_REVIEW_PROFILE,
        category="trino_closure_shared_deployment_profile_drift",
        summary_kind=TRINO_SHARED_DEPLOYMENT_AUDIT_SUMMARY_KIND,
    )
    _expect_payload_value(
        result,
        payload,
        ("production_review_profile_status",),
        TRINO_SHARED_DEPLOYMENT_PRODUCTION_REVIEW_PROFILE_STATUS,
        category="trino_closure_shared_deployment_profile_drift",
        summary_kind=TRINO_SHARED_DEPLOYMENT_AUDIT_SUMMARY_KIND,
    )
    requirements = payload.get("production_review_requirements")
    expected_requirement_fields = (
        ("required_families", TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_FAMILIES),
        (
            "required_deployment_config_requirements",
            TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_CONFIG_REQUIREMENTS,
        ),
        (
            "required_product_boundary_requirements",
            TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_PRODUCT_BOUNDARY_REQUIREMENTS,
        ),
        (
            "required_capability_requirements",
            TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_CAPABILITY_REQUIREMENTS,
        ),
        (
            "required_release_requirements",
            TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_RELEASE_REQUIREMENTS,
        ),
        ("required_doc_requirements", TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_DOC_REQUIREMENTS),
        (
            "required_unsupported_surfaces",
            TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_UNSUPPORTED_SURFACES,
        ),
    )
    for field_name, expected_values in expected_requirement_fields:
        if not _summary_requirements_include(requirements, field_name, expected_values):
            _add_issue(
                result,
                "trino_closure_shared_deployment_profile_drift",
                "The shared deployment summary must retain production-review requirements.",
                summary_kind=TRINO_SHARED_DEPLOYMENT_AUDIT_SUMMARY_KIND,
            )
    production_review_tracking_counts = payload.get("production_review_tracking_counts")
    if not _counter_has_positive_labels(production_review_tracking_counts, ("accepted",)):
        _add_issue(
            result,
            "trino_closure_shared_deployment_profile_drift",
            "The shared deployment summary must retain accepted production-review tracking.",
            summary_kind=TRINO_SHARED_DEPLOYMENT_AUDIT_SUMMARY_KIND,
        )
    unsupported = payload.get("unsupported_surfaces")
    if not isinstance(unsupported, Mapping) or any(
        value != "blocked" for value in unsupported.values()
    ):
        _add_issue(
            result,
            "trino_closure_shared_deployment_unsupported_surface_drift",
            "Shared deployment summary must keep unsupported Trino surfaces blocked.",
            summary_kind=TRINO_SHARED_DEPLOYMENT_AUDIT_SUMMARY_KIND,
        )


def _audit_support_gap_summary(
    result: TrinoProductionClosureAuditResult,
    payload: Mapping[str, Any],
) -> None:
    expected = {
        ("support_gap_status",): TRINO_SUPPORT_GAP_STATUS,
        ("production_support",): TRINO_LOCAL_PRODUCTION_SUPPORT_STATUS,
        ("product_surfaces",): TRINO_PRODUCT_SURFACES_STATUS,
        ("broader_production_closure_status",): TRINO_PRODUCTION_CLOSURE_STATUS,
        ("trino_sql_execution",): TRINO_SQL_EXECUTION_STATUS,
    }
    for path, expected_value in expected.items():
        _expect_payload_value(
            result,
            payload,
            path,
            expected_value,
            category="trino_closure_support_gap_boundary_drift",
            summary_kind=TRINO_SUPPORT_GAP_SUMMARY_KIND,
        )
    gates = payload.get("broader_production_closure_gates")
    if tuple(gates) != TRINO_BROADER_PRODUCTION_CLOSURE_GATES:
        _add_issue(
            result,
            "trino_closure_support_gap_gate_list_drift",
            "Support-gap summary must carry the current broader production closure gate list.",
            summary_kind=TRINO_SUPPORT_GAP_SUMMARY_KIND,
        )
    if payload.get("broader_production_closure_gate_count") != len(
        TRINO_BROADER_PRODUCTION_CLOSURE_GATES
    ):
        _add_issue(
            result,
            "trino_closure_support_gap_gate_count_drift",
            "Support-gap summary must carry the current broader production closure gate count.",
            summary_kind=TRINO_SUPPORT_GAP_SUMMARY_KIND,
        )


def _audit_common_not_closed_sql_free(
    result: TrinoProductionClosureAuditResult,
    payload: Mapping[str, Any],
    *,
    summary_kind: str,
) -> None:
    _expect_payload_value(
        result,
        payload,
        ("broader_production_closure_status",),
        TRINO_PRODUCTION_CLOSURE_NOT_READY_STATUS,
        category="trino_closure_summary_closed",
        summary_kind=summary_kind,
    )
    _expect_payload_value(
        result,
        payload,
        ("trino_sql_execution",),
        TRINO_SQL_EXECUTION_STATUS,
        category="trino_closure_summary_sql_execution_drift",
        summary_kind=summary_kind,
    )


def _audit_summary_issues_empty(
    result: TrinoProductionClosureAuditResult,
    payload: Mapping[str, Any],
    *,
    summary_kind: str,
) -> None:
    issue_counts = payload.get("issue_counts")
    if isinstance(issue_counts, Mapping) and issue_counts:
        _add_issue(
            result,
            "trino_closure_summary_has_issues",
            "A closure tracking summary must not carry issue counts.",
            summary_kind=summary_kind,
        )
    issues = payload.get("issues")
    if isinstance(issues, Mapping):
        nested_counts = issues.get("counts")
        nested_items = issues.get("items")
        if (isinstance(nested_counts, Mapping) and nested_counts) or (
            isinstance(nested_items, list) and nested_items
        ):
            _add_issue(
                result,
                "trino_closure_summary_has_issues",
                "A closure tracking summary must not carry issue counts.",
                summary_kind=summary_kind,
            )
    elif isinstance(issues, list) and issues:
        _add_issue(
            result,
            "trino_closure_summary_has_issues",
            "A closure tracking summary must not carry issue counts.",
            summary_kind=summary_kind,
        )
    counters = payload.get("counters")
    if isinstance(counters, Mapping):
        counter_issues = counters.get("issues")
        if isinstance(counter_issues, Mapping) and counter_issues:
            _add_issue(
                result,
                "trino_closure_summary_has_issues",
                "A closure tracking summary must not carry issue counts.",
                summary_kind=summary_kind,
            )


def _expect_payload_value(
    result: TrinoProductionClosureAuditResult,
    payload: Mapping[str, Any],
    path: tuple[str, ...],
    expected: Any,
    *,
    category: str,
    summary_kind: str,
) -> None:
    value: Any = payload
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            _add_issue(
                result,
                category,
                "A closure tracking summary is missing a required raw-free boundary field.",
                summary_kind=summary_kind,
            )
            return
        value = value[key]
    if value != expected:
        _add_issue(
            result,
            category,
            "A closure tracking summary drifted from the required raw-free boundary value.",
            summary_kind=summary_kind,
        )


def _capabilities_by_surface(
    capabilities: Iterable[EngineCapability],
) -> dict[str, EngineCapability]:
    return {capability.surface_id: capability for capability in capabilities}


def _gates_for_summary_kind(summary_kind: str) -> tuple[TrinoProductionClosureGate, ...]:
    return tuple(
        gate for gate in TRINO_PRODUCTION_CLOSURE_GATE_SPECS if gate.summary_kind == summary_kind
    )


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and value > 0


def _summary_requirements_include(
    requirements: Any,
    field_name: str,
    expected_values: Iterable[str],
) -> bool:
    if not isinstance(requirements, Mapping):
        return False
    raw_values = requirements.get(field_name)
    if not isinstance(raw_values, list):
        return False
    return set(expected_values).issubset(value for value in raw_values if isinstance(value, str))


def _counter_has_positive_labels(payload: Any, labels: Iterable[str]) -> bool:
    if not isinstance(payload, Mapping):
        return False
    for label in labels:
        value = payload.get(label)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            return False
    return True


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _add_issue(
    result: TrinoProductionClosureAuditResult,
    category: str,
    message: str,
    *,
    gate_id: str | None = None,
    summary_kind: str | None = None,
) -> None:
    result.issue_counts[category] += 1
    result.issues.append(
        TrinoProductionClosureIssue(
            category=category,
            message=message,
            gate_id=gate_id,
            summary_kind=summary_kind,
        )
    )
