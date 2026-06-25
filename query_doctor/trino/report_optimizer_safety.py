"""Raw-free audit model for Trino report and optimizer safety closure.

This module tracks the report/optimizer safety gate. It does not load Trino
case artifacts, run LLM reports, create Query Optimizer jobs, generate SQL, or
execute SQL.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from query_doctor.engines import EngineAdapter, get_engine_adapter
from query_doctor.engines.capabilities import EngineCapability, engine_capabilities
from query_doctor.web.trino_case_artifacts import (
    TRINO_WEB_OPTIMIZER_BEHAVIOR_STATUS,
    TRINO_WEB_OPTIMIZER_GUIDANCE_STATUS,
    TRINO_WEB_PYTHON_REPORT_STATUS,
    TRINO_WEB_TRUSTED_REPORTS_STATUS,
    trino_web_case_analysis_payload,
)
from query_doctor.web.trino_guidance import validate_trino_optimizer_guidance_text
from query_doctor.web.trino_report import validate_trino_python_report_text


TRINO_REPORT_OPTIMIZER_SAFETY_SUMMARY_KIND = "trino_report_optimizer_safety_audit_v1"
TRINO_REPORT_OPTIMIZER_SAFETY_GATE = "trino_report_optimizer_safety"
TRINO_REPORT_OPTIMIZER_SAFETY_STATUS = "not_closed"
TRINO_REPORT_OPTIMIZER_CLOSURE_REASON = (
    "report_optimizer_safety_requires_trino_claim_validation_leak_tests_and_no_sql_execution"
)
TRINO_REPORT_OPTIMIZER_SOURCE_BOUNDARY = "materialized_raw_free_case_facts"
TRINO_REPORT_OPTIMIZER_LLM_REPORTS_STATUS = "not_wired"
TRINO_REPORT_OPTIMIZER_QUERY_OPTIMIZER_JOBS_STATUS = "blocked"
TRINO_REPORT_OPTIMIZER_GENERATED_SQL_STATUS = "blocked"
TRINO_REPORT_OPTIMIZER_SQL_EXECUTION_STATUS = "not_performed"
TRINO_REPORT_OPTIMIZER_ADAPTER_VALIDATED_REPORTS_STATUS = "blocked"
TRINO_REPORT_OPTIMIZER_PRODUCTION_REVIEW_PROFILE = "production_review_report_optimizer_v1"
TRINO_REPORT_OPTIMIZER_PRODUCTION_REVIEW_PROFILE_STATUS = "ready"

TRINO_REPORT_OPTIMIZER_ALLOWED_PRODUCT_CAPABILITY_IDS = frozenset(
    {
        "recent_scan",
        "query_id_mode",
        "materialized_details",
        "materialized_python_report",
        "materialized_optimizer_guidance",
    }
)


@dataclass(frozen=True)
class TrinoReportOptimizerCapabilityRequirement:
    surface_id: str
    input_kind: str
    route_path: str
    promotion_gate: str
    required_policy_field: str
    required_policy_status: str


@dataclass(frozen=True)
class TrinoReportOptimizerFamily:
    family_id: str
    readiness_state: str
    production_blocker: str
    capability_requirements: tuple[TrinoReportOptimizerCapabilityRequirement, ...] = ()


@dataclass(frozen=True)
class TrinoReportOptimizerIssue:
    category: str
    message: str
    requirement_type: str | None = None
    requirement_id: str | None = None


@dataclass(frozen=True)
class TrinoReportOptimizerRequirementTracking:
    family_id: str
    requirement_type: str
    requirement_id: str
    tracking_status: str
    issue_count: int


@dataclass(frozen=True)
class TrinoReportOptimizerProductionReviewTracking:
    requirement_id: str
    counter_name: str
    tracking_status: str
    observed_count: int
    required_count: int


@dataclass
class TrinoReportOptimizerAuditResult:
    family_count: int = 0
    required_capability_count: int = 0
    product_capability_count: int = 0
    policy_field_count: int = 0
    validation_sentinel_count: int = 0
    validator_check_count: int = 0
    open_blocker_count: int = 0
    adapter_validated_reports_enabled: bool = False
    status_counts: Counter[str] = field(default_factory=Counter)
    blocker_counts: Counter[str] = field(default_factory=Counter)
    capability_counts: Counter[str] = field(default_factory=Counter)
    policy_counts: Counter[str] = field(default_factory=Counter)
    validator_rejection_counts: Counter[str] = field(default_factory=Counter)
    report_optimizer_requirement_tracking_counts: Counter[str] = field(default_factory=Counter)
    production_review_tracking_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    blockers: list[tuple[str, str]] = field(default_factory=list)
    report_optimizer_requirement_tracking: list[TrinoReportOptimizerRequirementTracking] = field(
        default_factory=list
    )
    production_review_tracking: list[TrinoReportOptimizerProductionReviewTracking] = field(
        default_factory=list
    )
    issues: list[tuple[str, TrinoReportOptimizerIssue]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issue_counts


TRINO_REPORT_OPTIMIZER_REQUIRED_CAPABILITIES = (
    TrinoReportOptimizerCapabilityRequirement(
        surface_id="materialized_python_report",
        input_kind="trino_web_materialized_raw_free_case_artifacts",
        route_path="/trino/details/{case_id}?report=python",
        promotion_gate="trino_materialized_case_python_report_validation_contract",
        required_policy_field="python_report",
        required_policy_status=TRINO_WEB_PYTHON_REPORT_STATUS,
    ),
    TrinoReportOptimizerCapabilityRequirement(
        surface_id="materialized_optimizer_guidance",
        input_kind="trino_web_materialized_raw_free_case_artifacts",
        route_path="/trino/details/{case_id}?guidance=optimizer",
        promotion_gate="trino_materialized_case_optimizer_guidance_validation_contract",
        required_policy_field="optimizer_guidance",
        required_policy_status=TRINO_WEB_OPTIMIZER_GUIDANCE_STATUS,
    ),
)

TRINO_REPORT_OPTIMIZER_REQUIRED_POLICY = {
    "python_report": TRINO_WEB_PYTHON_REPORT_STATUS,
    "optimizer_guidance": TRINO_WEB_OPTIMIZER_GUIDANCE_STATUS,
    "trusted_reports": TRINO_WEB_TRUSTED_REPORTS_STATUS,
    "optimizer_behavior": TRINO_WEB_OPTIMIZER_BEHAVIOR_STATUS,
    "llm_reports": TRINO_REPORT_OPTIMIZER_LLM_REPORTS_STATUS,
    "sql_execution": TRINO_REPORT_OPTIMIZER_SQL_EXECUTION_STATUS,
}

TRINO_REPORT_OPTIMIZER_VALIDATION_SENTINELS = (
    ("sql_like_text", "SELECT * FROM unsafe_table"),
    ("trino_query_id", "20250101_010101_00001_abc123"),
    ("url", "https://coordinator.example.invalid"),
    ("local_path", "/tmp/query-info.json"),
    ("generated_sql_wording", "generated SQL"),
    ("root_cause_overclaim", "root cause is coordinator saturation"),
    ("auth_material", "Authorization Bearer token"),
    ("connector_internal", "stage-raw-id"),
)

TRINO_REPORT_OPTIMIZER_FAMILIES = (
    TrinoReportOptimizerFamily(
        family_id="python_report_validation",
        readiness_state="raw_free_materialized_python_report",
        production_blocker="python_report_requires_materialized_case_policy_and_leak_validation",
        capability_requirements=(TRINO_REPORT_OPTIMIZER_REQUIRED_CAPABILITIES[0],),
    ),
    TrinoReportOptimizerFamily(
        family_id="optimizer_guidance_validation",
        readiness_state="raw_free_guidance_only_optimizer",
        production_blocker="optimizer_guidance_requires_guidance_only_policy_and_leak_validation",
        capability_requirements=(TRINO_REPORT_OPTIMIZER_REQUIRED_CAPABILITIES[1],),
    ),
    TrinoReportOptimizerFamily(
        family_id="blocked_report_optimizer_surfaces",
        readiness_state="unsupported_surfaces_blocked",
        production_blocker="llm_reports_query_optimizer_jobs_generated_sql_and_sql_execution_remain_blocked",
    ),
)

TRINO_REPORT_OPTIMIZER_PRODUCT_SURFACE_REQUIREMENTS = (
    "adapter_validated_reports_blocked",
    "llm_reports_not_wired",
    "query_optimizer_jobs_blocked",
    "generated_sql_blocked",
    "trino_sql_execution_not_performed",
    "forbidden_report_optimizer_product_capabilities",
)
TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_FAMILIES = (
    "python_report_validation",
    "optimizer_guidance_validation",
    "blocked_report_optimizer_surfaces",
)
TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_CAPABILITIES = tuple(
    requirement.surface_id for requirement in TRINO_REPORT_OPTIMIZER_REQUIRED_CAPABILITIES
)
TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_POLICY_FIELDS = tuple(TRINO_REPORT_OPTIMIZER_REQUIRED_POLICY)
TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_VALIDATORS = ("python_report", "optimizer_guidance")
TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_VALIDATOR_SENTINELS = tuple(
    sentinel_id for sentinel_id, _sentinel_text in TRINO_REPORT_OPTIMIZER_VALIDATION_SENTINELS
)
TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_PRODUCT_SURFACE_REQUIREMENTS = (
    TRINO_REPORT_OPTIMIZER_PRODUCT_SURFACE_REQUIREMENTS
)

TRINO_REPORT_OPTIMIZER_FORBIDDEN_PRODUCT_REQUIREMENT_IDS = {
    "llm_report": "llm_reports_not_wired",
    "query_optimizer_job": "query_optimizer_jobs_blocked",
    "generated_sql": "generated_sql_blocked",
    "sql_execution": "trino_sql_execution_not_performed",
    "validated_reports": "adapter_validated_reports_blocked",
}


def audit_trino_report_optimizer_safety(
    *,
    families: Iterable[TrinoReportOptimizerFamily] = TRINO_REPORT_OPTIMIZER_FAMILIES,
    capabilities: Iterable[EngineCapability] | None = None,
    trino_adapter: EngineAdapter | None = None,
    raw_policy: Mapping[str, object] | None = None,
    report_validator: Callable[[str], list[str]] = validate_trino_python_report_text,
    guidance_validator: Callable[[str], list[str]] = validate_trino_optimizer_guidance_text,
) -> TrinoReportOptimizerAuditResult:
    result = TrinoReportOptimizerAuditResult()
    capability_tuple = engine_capabilities("trino") if capabilities is None else tuple(capabilities)
    capabilities_by_surface = {capability.surface_id: capability for capability in capability_tuple}
    trino = get_engine_adapter("trino") if trino_adapter is None else trino_adapter
    policy = _default_raw_policy() if raw_policy is None else raw_policy
    family_tuple = tuple(families)

    _audit_adapter(result, trino)
    _audit_product_capability_boundary(result, capability_tuple)
    _audit_raw_policy(result, policy)
    _audit_validators(result, report_validator, guidance_validator)
    for family in family_tuple:
        result.family_count += 1
        result.status_counts[family.readiness_state] += 1
        if family.production_blocker:
            result.open_blocker_count += 1
            result.blocker_counts[family.production_blocker] += 1
            result.blockers.append((family.family_id, family.production_blocker))
        for requirement in family.capability_requirements:
            result.required_capability_count += 1
            _audit_capability_requirement(
                result,
                family.family_id,
                requirement,
                capabilities_by_surface,
            )
    finalize_report_optimizer_requirement_tracking(result, family_tuple)
    audit_report_optimizer_production_review_profile(result, family_tuple)
    return result


def report_optimizer_safety_summary_payload(
    result: TrinoReportOptimizerAuditResult,
    *,
    status: str,
) -> dict[str, Any]:
    return {
        "summary_kind": TRINO_REPORT_OPTIMIZER_SAFETY_SUMMARY_KIND,
        "status": status,
        "closure_gate": TRINO_REPORT_OPTIMIZER_SAFETY_GATE,
        "report_optimizer_safety_status": TRINO_REPORT_OPTIMIZER_SAFETY_STATUS,
        "broader_production_closure_status": "not_closed",
        "closure_reason": TRINO_REPORT_OPTIMIZER_CLOSURE_REASON,
        "source_boundary": TRINO_REPORT_OPTIMIZER_SOURCE_BOUNDARY,
        "python_report": TRINO_WEB_PYTHON_REPORT_STATUS,
        "trusted_reports": TRINO_WEB_TRUSTED_REPORTS_STATUS,
        "optimizer_guidance": TRINO_WEB_OPTIMIZER_GUIDANCE_STATUS,
        "optimizer_behavior": TRINO_WEB_OPTIMIZER_BEHAVIOR_STATUS,
        "llm_reports": TRINO_REPORT_OPTIMIZER_LLM_REPORTS_STATUS,
        "query_optimizer_jobs": TRINO_REPORT_OPTIMIZER_QUERY_OPTIMIZER_JOBS_STATUS,
        "generated_sql": TRINO_REPORT_OPTIMIZER_GENERATED_SQL_STATUS,
        "trino_sql_execution": TRINO_REPORT_OPTIMIZER_SQL_EXECUTION_STATUS,
        "adapter_validated_reports": (
            "enabled"
            if result.adapter_validated_reports_enabled
            else TRINO_REPORT_OPTIMIZER_ADAPTER_VALIDATED_REPORTS_STATUS
        ),
        "family_count": result.family_count,
        "required_capability_count": result.required_capability_count,
        "product_capability_count": result.product_capability_count,
        "policy_field_count": result.policy_field_count,
        "validation_sentinel_count": result.validation_sentinel_count,
        "validator_check_count": result.validator_check_count,
        "open_blocker_count": result.open_blocker_count,
        "status_counts": _counter_payload(result.status_counts),
        "blocker_counts": _counter_payload(result.blocker_counts),
        "capability_counts": _counter_payload(result.capability_counts),
        "policy_counts": _counter_payload(result.policy_counts),
        "validator_rejection_counts": _counter_payload(result.validator_rejection_counts),
        "report_optimizer_requirement_tracking_counts": _counter_payload(
            result.report_optimizer_requirement_tracking_counts
        ),
        "production_review_profile": TRINO_REPORT_OPTIMIZER_PRODUCTION_REVIEW_PROFILE,
        "production_review_profile_status": _production_review_profile_status(result),
        "production_review_requirements": {
            "required_families": list(TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_FAMILIES),
            "required_capabilities": list(TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_CAPABILITIES),
            "required_policy_fields": list(TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_POLICY_FIELDS),
            "required_validators": list(TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_VALIDATORS),
            "required_validator_sentinels": list(
                TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_VALIDATOR_SENTINELS
            ),
            "required_product_surface_requirements": list(
                TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_PRODUCT_SURFACE_REQUIREMENTS
            ),
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
        "report_optimizer_requirement_tracking": [
            {
                "family_id": tracking.family_id,
                "requirement_type": tracking.requirement_type,
                "requirement_id": tracking.requirement_id,
                "tracking_status": tracking.tracking_status,
                "issue_count": tracking.issue_count,
            }
            for tracking in result.report_optimizer_requirement_tracking
        ],
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


def _default_raw_policy() -> Mapping[str, object]:
    payload = trino_web_case_analysis_payload(
        case_id="trino-" + ("0" * 32),
        diagnosis={},
        workflow="query_id",
        support_mode="production",
    )
    policy = payload.get("raw_source_policy")
    return policy if isinstance(policy, Mapping) else {}


def _audit_adapter(result: TrinoReportOptimizerAuditResult, trino_adapter: EngineAdapter) -> None:
    result.adapter_validated_reports_enabled = bool(
        getattr(trino_adapter, "supports_validated_reports", False)
    )
    if result.adapter_validated_reports_enabled:
        _add_issue(
            result,
            "product_surfaces",
            "trino_report_optimizer_adapter_validated_reports_enabled",
            "Trino adapter validated reports must stay blocked until the report optimizer gate closes.",
            requirement_type="product_surface",
            requirement_id="adapter_validated_reports_blocked",
        )


def _audit_product_capability_boundary(
    result: TrinoReportOptimizerAuditResult,
    capabilities: Iterable[EngineCapability],
) -> None:
    for capability in capabilities:
        if not capability.product_surface_allowed:
            continue
        result.product_capability_count += 1
        result.capability_counts[capability.surface_id] += 1
        forbidden_requirement_id = _forbidden_product_requirement_id(capability.surface_id)
        forbidden_surface = (
            capability.surface_id not in TRINO_REPORT_OPTIMIZER_ALLOWED_PRODUCT_CAPABILITY_IDS
            or forbidden_requirement_id is not None
        )
        if forbidden_surface:
            requirement_id = (
                forbidden_requirement_id or "forbidden_report_optimizer_product_capabilities"
            )
            _add_issue(
                result,
                "product_surfaces",
                "trino_report_optimizer_forbidden_product_capability",
                "Trino product capabilities must not include report optimizer surfaces beyond materialized Python Report and guidance.",
                requirement_type="product_surface",
                requirement_id=requirement_id,
            )


def _forbidden_product_requirement_id(surface_id: str) -> str | None:
    for token, requirement_id in TRINO_REPORT_OPTIMIZER_FORBIDDEN_PRODUCT_REQUIREMENT_IDS.items():
        if token in surface_id:
            return requirement_id
    return None


def _audit_raw_policy(
    result: TrinoReportOptimizerAuditResult,
    raw_policy: Mapping[str, object],
) -> None:
    for field_name, expected_value in TRINO_REPORT_OPTIMIZER_REQUIRED_POLICY.items():
        result.policy_field_count += 1
        value = raw_policy.get(field_name)
        result.policy_counts[f"{field_name}={value}"] += 1
        if value != expected_value:
            category = (
                "trino_report_optimizer_raw_policy_missing"
                if field_name not in raw_policy
                else "trino_report_optimizer_raw_policy_drift"
            )
            _add_issue(
                result,
                "raw_source_policy",
                category,
                "Trino report optimizer raw-source policy drifted from the materialized raw-free boundary.",
                requirement_type="policy",
                requirement_id=field_name,
            )


def _audit_validators(
    result: TrinoReportOptimizerAuditResult,
    report_validator: Callable[[str], list[str]],
    guidance_validator: Callable[[str], list[str]],
) -> None:
    result.validation_sentinel_count = len(TRINO_REPORT_OPTIMIZER_VALIDATION_SENTINELS)
    validators = (
        ("python_report", report_validator),
        ("optimizer_guidance", guidance_validator),
    )
    for sentinel_id, sentinel_text in TRINO_REPORT_OPTIMIZER_VALIDATION_SENTINELS:
        for validator_id, validator in validators:
            result.validator_check_count += 1
            if validator(sentinel_text):
                result.validator_rejection_counts[validator_id] += 1
                continue
            _add_issue(
                result,
                validator_id,
                "trino_report_optimizer_validator_failed_to_reject",
                f"Trino {validator_id} validator accepted unsafe sentinel category {sentinel_id}.",
                requirement_type="validator_sentinel",
                requirement_id=sentinel_id,
            )


def _audit_capability_requirement(
    result: TrinoReportOptimizerAuditResult,
    family_id: str,
    requirement: TrinoReportOptimizerCapabilityRequirement,
    capabilities_by_surface: Mapping[str, EngineCapability],
) -> None:
    capability = capabilities_by_surface.get(requirement.surface_id)
    if capability is None:
        _add_issue(
            result,
            family_id,
            "trino_report_optimizer_capability_missing",
            "A required Trino report optimizer product capability is missing.",
            requirement_type="capability",
            requirement_id=requirement.surface_id,
        )
        return
    expected_fields: tuple[tuple[str, object], ...] = (
        ("support_level", "production"),
        ("surface_class", "product_web"),
        ("input_kind", requirement.input_kind),
        ("raw_policy", "raw_free_summary_only"),
        ("product_surface_allowed", True),
        ("adapter_flag", None),
        ("cli_role", None),
        ("script_path", None),
        ("route_path", requirement.route_path),
        ("dev_only", False),
        ("promotion_gate", requirement.promotion_gate),
    )
    for field_name, expected_value in expected_fields:
        if getattr(capability, field_name) != expected_value:
            _add_issue(
                result,
                family_id,
                f"trino_report_optimizer_capability_{field_name}_drift",
                "A Trino report optimizer capability drifted from the materialized raw-free boundary.",
                requirement_type="capability",
                requirement_id=requirement.surface_id,
            )


def finalize_report_optimizer_requirement_tracking(
    result: TrinoReportOptimizerAuditResult,
    families: tuple[TrinoReportOptimizerFamily, ...],
) -> None:
    result.report_optimizer_requirement_tracking.clear()
    result.report_optimizer_requirement_tracking_counts.clear()
    for family in families:
        for requirement in family.capability_requirements:
            _append_report_optimizer_requirement_tracking(
                result,
                family_id=family.family_id,
                requirement_type="capability",
                requirement_id=requirement.surface_id,
            )
    for field_name in TRINO_REPORT_OPTIMIZER_REQUIRED_POLICY:
        _append_report_optimizer_requirement_tracking(
            result,
            family_id="raw_source_policy",
            requirement_type="policy",
            requirement_id=field_name,
        )
    for sentinel_id, _sentinel_text in TRINO_REPORT_OPTIMIZER_VALIDATION_SENTINELS:
        for validator_id in ("python_report", "optimizer_guidance"):
            _append_report_optimizer_requirement_tracking(
                result,
                family_id=validator_id,
                requirement_type="validator_sentinel",
                requirement_id=sentinel_id,
            )
    for requirement_id in TRINO_REPORT_OPTIMIZER_PRODUCT_SURFACE_REQUIREMENTS:
        _append_report_optimizer_requirement_tracking(
            result,
            family_id="product_surfaces",
            requirement_type="product_surface",
            requirement_id=requirement_id,
        )


def audit_report_optimizer_production_review_profile(
    result: TrinoReportOptimizerAuditResult,
    families: tuple[TrinoReportOptimizerFamily, ...],
) -> None:
    family_ids = {family.family_id for family in families}
    _append_production_review_tracking(
        result,
        requirement_id="require_review_families",
        counter_name="families",
        observed_count=sum(
            1
            for family_id in TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_FAMILIES
            if family_id in family_ids
        ),
        required_count=len(TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_FAMILIES),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_materialized_capabilities",
        counter_name="capabilities",
        observed_count=_accepted_requirement_count(
            result,
            requirement_type="capability",
            requirement_ids=TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_CAPABILITIES,
        ),
        required_count=len(TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_CAPABILITIES),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_raw_policy_fields",
        counter_name="policy_fields",
        observed_count=_accepted_requirement_count(
            result,
            requirement_type="policy",
            requirement_ids=TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_POLICY_FIELDS,
        ),
        required_count=len(TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_POLICY_FIELDS),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_validator_sentinel_matrix",
        counter_name="validator_sentinels",
        observed_count=_accepted_validator_sentinel_count(result),
        required_count=len(TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_VALIDATORS)
        * len(TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_VALIDATOR_SENTINELS),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_product_surface_blocks",
        counter_name="product_surface_requirements",
        observed_count=_accepted_requirement_count(
            result,
            requirement_type="product_surface",
            requirement_ids=TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_PRODUCT_SURFACE_REQUIREMENTS,
        ),
        required_count=len(TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_PRODUCT_SURFACE_REQUIREMENTS),
    )


def _accepted_requirement_count(
    result: TrinoReportOptimizerAuditResult,
    *,
    requirement_type: str,
    requirement_ids: tuple[str, ...],
) -> int:
    accepted_requirement_ids = {
        tracking.requirement_id
        for tracking in result.report_optimizer_requirement_tracking
        if tracking.requirement_type == requirement_type and tracking.tracking_status == "accepted"
    }
    return sum(
        1 for requirement_id in requirement_ids if requirement_id in accepted_requirement_ids
    )


def _accepted_validator_sentinel_count(result: TrinoReportOptimizerAuditResult) -> int:
    accepted_pairs = {
        (tracking.family_id, tracking.requirement_id)
        for tracking in result.report_optimizer_requirement_tracking
        if tracking.requirement_type == "validator_sentinel"
        and tracking.tracking_status == "accepted"
    }
    return sum(
        1
        for validator_id in TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_VALIDATORS
        for sentinel_id in TRINO_REPORT_OPTIMIZER_REQUIRED_REVIEW_VALIDATOR_SENTINELS
        if (validator_id, sentinel_id) in accepted_pairs
    )


def _append_production_review_tracking(
    result: TrinoReportOptimizerAuditResult,
    *,
    requirement_id: str,
    counter_name: str,
    observed_count: int,
    required_count: int,
) -> None:
    tracking_status = _production_review_tracking_status(observed_count, required_count)
    result.production_review_tracking.append(
        TrinoReportOptimizerProductionReviewTracking(
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
            "trino_report_optimizer_production_review_gap",
            "Trino report/optimizer production-review profile is incomplete.",
            requirement_type="production_review_profile",
            requirement_id=requirement_id,
        )


def _production_review_tracking_status(observed_count: int, required_count: int) -> str:
    if required_count <= 0:
        return "not_required"
    if observed_count >= required_count:
        return "accepted"
    return "insufficient"


def _production_review_profile_status(result: TrinoReportOptimizerAuditResult) -> str:
    if not result.production_review_tracking:
        return "not_required"
    if set(result.production_review_tracking_counts) == {"accepted"}:
        return TRINO_REPORT_OPTIMIZER_PRODUCTION_REVIEW_PROFILE_STATUS
    return "failed"


def _append_report_optimizer_requirement_tracking(
    result: TrinoReportOptimizerAuditResult,
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
    tracking_status = _report_optimizer_requirement_tracking_status(issues)
    result.report_optimizer_requirement_tracking.append(
        TrinoReportOptimizerRequirementTracking(
            family_id=family_id,
            requirement_type=requirement_type,
            requirement_id=requirement_id,
            tracking_status=tracking_status,
            issue_count=len(issues),
        )
    )
    result.report_optimizer_requirement_tracking_counts[tracking_status] += 1


def _issues_for_requirement(
    result: TrinoReportOptimizerAuditResult,
    *,
    family_id: str,
    requirement_type: str,
    requirement_id: str,
) -> tuple[TrinoReportOptimizerIssue, ...]:
    return tuple(
        issue
        for issue_family_id, issue in result.issues
        if issue_family_id == family_id
        and issue.requirement_type == requirement_type
        and issue.requirement_id == requirement_id
    )


def _report_optimizer_requirement_tracking_status(
    issues: tuple[TrinoReportOptimizerIssue, ...],
) -> str:
    if any(
        issue.category
        in {
            "trino_report_optimizer_capability_missing",
            "trino_report_optimizer_raw_policy_missing",
        }
        for issue in issues
    ):
        return "missing"
    if issues:
        return "invalid"
    return "accepted"


def _add_issue(
    result: TrinoReportOptimizerAuditResult,
    family_id: str,
    category: str,
    message: str,
    *,
    requirement_type: str | None = None,
    requirement_id: str | None = None,
) -> None:
    issue = TrinoReportOptimizerIssue(
        category=category,
        message=message,
        requirement_type=requirement_type,
        requirement_id=requirement_id,
    )
    result.issue_counts[category] += 1
    result.issues.append((family_id, issue))


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}
