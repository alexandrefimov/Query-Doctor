"""Raw-free audit model for Trino browser/report regression closure.

This module tracks the browser/report regression gate. It reads only source and
test catalogs, and it does not render browser pages, load case artifacts,
collect from Trino, run report jobs, run optimizer jobs, generate SQL, or
execute SQL.
"""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from query_doctor.engines import EngineAdapter, get_engine_adapter
from query_doctor.engines.capabilities import EngineCapability, engine_capabilities


TRINO_BROWSER_REPORT_REGRESSION_SUMMARY_KIND = "trino_browser_report_regression_audit_v1"
TRINO_BROWSER_REPORT_REGRESSION_GATE = "trino_browser_report_regression"
TRINO_BROWSER_REPORT_REGRESSION_STATUS = "not_closed"
TRINO_BROWSER_REPORT_REGRESSION_CLOSURE_REASON = (
    "browser_report_regression_requires_complete_raw_free_surface_coverage"
)
TRINO_BROWSER_REPORT_PRODUCT_SURFACE = (
    "recent_query_id_raw_free_details_python_report_optimizer_guidance"
)
TRINO_BROWSER_REPORT_DETAILS_CASE_VIEW = "raw_free_materialized"
TRINO_BROWSER_REPORT_PYTHON_REPORT = "raw_free_materialized"
TRINO_BROWSER_REPORT_OPTIMIZER_GUIDANCE = "raw_free_materialized"
TRINO_BROWSER_REPORT_LLM_REPORTS = "not_wired"
TRINO_BROWSER_REPORT_SQL_EXECUTION = "not_performed"
TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS = "blocked"
TRINO_BROWSER_REPORT_ADAPTER_VALIDATED_REPORTS_STATUS = "blocked"
TRINO_BROWSER_REPORT_PRODUCTION_REVIEW_PROFILE = "production_review_browser_report_v1"
TRINO_BROWSER_REPORT_PRODUCTION_REVIEW_PROFILE_STATUS = "ready"

TRINO_BROWSER_REPORT_ALLOWED_PRODUCT_CAPABILITY_IDS = frozenset(
    {
        "recent_scan",
        "query_id_mode",
        "materialized_details",
        "materialized_python_report",
        "materialized_optimizer_guidance",
    }
)
TRINO_BROWSER_REPORT_REQUIRED_ROUTE_CAPABILITIES = {
    "materialized_details": "/trino/details/{case_id}",
    "materialized_python_report": "/trino/details/{case_id}?report=python",
    "materialized_optimizer_guidance": "/trino/details/{case_id}?guidance=optimizer",
}


@dataclass(frozen=True)
class TrinoBrowserReportRegressionTestRequirement:
    family_id: str
    test_file_label: str
    test_name: str


@dataclass(frozen=True)
class TrinoBrowserReportRegressionFamily:
    family_id: str
    readiness_state: str
    production_blocker: str
    tests: tuple[TrinoBrowserReportRegressionTestRequirement, ...]


@dataclass(frozen=True)
class TrinoBrowserReportRegressionIssue:
    category: str
    message: str
    requirement_type: str | None = None
    requirement_id: str | None = None


@dataclass(frozen=True)
class TrinoBrowserReportRequirementTracking:
    family_id: str
    requirement_type: str
    requirement_id: str
    tracking_status: str
    issue_count: int


@dataclass(frozen=True)
class TrinoBrowserReportProductionReviewTracking:
    requirement_id: str
    counter_name: str
    tracking_status: str
    observed_count: int
    required_count: int


@dataclass
class TrinoBrowserReportRegressionAuditResult:
    family_count: int = 0
    required_test_count: int = 0
    present_test_count: int = 0
    source_file_count: int = 0
    required_route_capability_count: int = 0
    product_capability_count: int = 0
    open_blocker_count: int = 0
    adapter_validated_reports_enabled: bool = False
    status_counts: Counter[str] = field(default_factory=Counter)
    test_family_counts: Counter[str] = field(default_factory=Counter)
    test_file_counts: Counter[str] = field(default_factory=Counter)
    route_capability_counts: Counter[str] = field(default_factory=Counter)
    product_capability_counts: Counter[str] = field(default_factory=Counter)
    blocker_counts: Counter[str] = field(default_factory=Counter)
    browser_report_requirement_tracking_counts: Counter[str] = field(default_factory=Counter)
    production_review_tracking_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    blockers: list[tuple[str, str]] = field(default_factory=list)
    browser_report_requirement_tracking: list[TrinoBrowserReportRequirementTracking] = field(
        default_factory=list
    )
    production_review_tracking: list[TrinoBrowserReportProductionReviewTracking] = field(
        default_factory=list
    )
    issues: list[tuple[str, TrinoBrowserReportRegressionIssue]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issue_counts


TRINO_BROWSER_REPORT_TEST_FILES = {
    "web_trino_beta_query": Path("tests/test_web_trino_beta_query.py"),
    "product_surface_boundary_audit": Path("tests/test_audit_trino_product_surface_boundary.py"),
}

TRINO_BROWSER_REPORT_REGRESSION_FAMILIES = (
    TrinoBrowserReportRegressionFamily(
        family_id="materialized_details_browser_regressions",
        readiness_state="details_raw_free_regressions_tracked",
        production_blocker="details_requires_complete_raw_free_browser_regression_coverage",
        tests=(
            TrinoBrowserReportRegressionTestRequirement(
                "materialized_details_browser_regressions",
                "web_trino_beta_query",
                "test_trino_beta_query_analysis_materializes_raw_free_case_artifacts",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "materialized_details_browser_regressions",
                "web_trino_beta_query",
                "test_trino_beta_details_route_renders_raw_free_materialized_case",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "materialized_details_browser_regressions",
                "web_trino_beta_query",
                "test_trino_beta_details_route_rejects_invalid_case_reference_without_echo",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "materialized_details_browser_regressions",
                "web_trino_beta_query",
                "test_trino_beta_result_renderer_redacts_dynamic_diagnosis_text",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "materialized_details_browser_regressions",
                "web_trino_beta_query",
                "test_trino_beta_async_result_json_redacts_dynamic_diagnosis_text",
            ),
        ),
    ),
    TrinoBrowserReportRegressionFamily(
        family_id="python_report_browser_regressions",
        readiness_state="python_report_raw_free_regressions_tracked",
        production_blocker="python_report_requires_route_download_and_validator_regressions",
        tests=(
            TrinoBrowserReportRegressionTestRequirement(
                "python_report_browser_regressions",
                "web_trino_beta_query",
                "test_trino_beta_python_report_route_renders_validated_raw_free_report",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "python_report_browser_regressions",
                "web_trino_beta_query",
                "test_trino_beta_python_report_markdown_download_stays_raw_free",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "python_report_browser_regressions",
                "web_trino_beta_query",
                "test_trino_python_report_validator_rejects_unsafe_claims_and_payloads",
            ),
        ),
    ),
    TrinoBrowserReportRegressionFamily(
        family_id="optimizer_guidance_browser_regressions",
        readiness_state="optimizer_guidance_raw_free_regressions_tracked",
        production_blocker="optimizer_guidance_requires_route_download_and_validator_regressions",
        tests=(
            TrinoBrowserReportRegressionTestRequirement(
                "optimizer_guidance_browser_regressions",
                "web_trino_beta_query",
                "test_trino_beta_optimizer_guidance_route_renders_validated_raw_free_guidance",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "optimizer_guidance_browser_regressions",
                "web_trino_beta_query",
                "test_trino_beta_optimizer_guidance_markdown_download_stays_raw_free",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "optimizer_guidance_browser_regressions",
                "web_trino_beta_query",
                "test_trino_optimizer_guidance_validator_rejects_unsafe_claims_and_payloads",
            ),
        ),
    ),
    TrinoBrowserReportRegressionFamily(
        family_id="error_and_unsupported_workflow_regressions",
        readiness_state="error_and_unsupported_workflow_regressions_tracked",
        production_blocker="errors_and_unsupported_workflows_require_raw_free_browser_regressions",
        tests=(
            TrinoBrowserReportRegressionTestRequirement(
                "error_and_unsupported_workflow_regressions",
                "web_trino_beta_query",
                "test_trino_beta_invalid_query_id_is_not_reflected_to_browser",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "error_and_unsupported_workflow_regressions",
                "web_trino_beta_query",
                "test_trino_beta_handle_analyze_request_hides_network_failure_details",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "error_and_unsupported_workflow_regressions",
                "web_trino_beta_query",
                "test_trino_beta_async_job_hides_network_failure_details",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "error_and_unsupported_workflow_regressions",
                "web_trino_beta_query",
                "test_trino_beta_failed_job_page_hides_network_failure_details",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "error_and_unsupported_workflow_regressions",
                "web_trino_beta_query",
                "test_trino_beta_query_id_is_rejected_by_specific_query_action_routes",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "error_and_unsupported_workflow_regressions",
                "web_trino_beta_query",
                "test_trino_beta_query_id_is_rejected_by_specific_query_get_routes",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "error_and_unsupported_workflow_regressions",
                "web_trino_beta_query",
                "test_trino_beta_recent_and_running_routes_reject_before_job_creation",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "error_and_unsupported_workflow_regressions",
                "web_trino_beta_query",
                "test_trino_beta_recent_forbidden_options_reject_before_job_creation",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "error_and_unsupported_workflow_regressions",
                "web_trino_beta_query",
                "test_trino_beta_startup_validation_rejects_invalid_coordinator_url_without_echo",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "error_and_unsupported_workflow_regressions",
                "web_trino_beta_query",
                "test_trino_beta_startup_validation_rejects_invalid_auth_header_without_secret_echo",
            ),
        ),
    ),
    TrinoBrowserReportRegressionFamily(
        family_id="product_surface_static_boundary_regressions",
        readiness_state="product_surface_static_boundary_regressions_tracked",
        production_blocker="product_surface_boundaries_require_static_route_source_and_claim_regressions",
        tests=(
            TrinoBrowserReportRegressionTestRequirement(
                "product_surface_static_boundary_regressions",
                "product_surface_boundary_audit",
                "test_trino_product_surface_audit_accepts_boundary_and_diagnosis_without_path_echo",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "product_surface_static_boundary_regressions",
                "product_surface_boundary_audit",
                "test_trino_product_surface_audit_writes_raw_free_summary",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "product_surface_static_boundary_regressions",
                "product_surface_boundary_audit",
                "test_trino_product_surface_audit_rejects_raw_like_diagnosis_without_value_echo",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "product_surface_static_boundary_regressions",
                "product_surface_boundary_audit",
                "test_trino_product_surface_audit_rejects_metadata_summary_boundary_without_echo",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "product_surface_static_boundary_regressions",
                "product_surface_boundary_audit",
                "test_trino_product_surface_audit_supports_registry_only_mode",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "product_surface_static_boundary_regressions",
                "product_surface_boundary_audit",
                "test_trino_product_surface_audit_registry_detects_unexpected_trino_route",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "product_surface_static_boundary_regressions",
                "product_surface_boundary_audit",
                "test_trino_report_module_boundary_rejects_legacy_report_or_optimizer_markers",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "product_surface_static_boundary_regressions",
                "product_surface_boundary_audit",
                "test_trino_guidance_module_boundary_rejects_optimizer_job_markers",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "product_surface_static_boundary_regressions",
                "product_surface_boundary_audit",
                "test_trino_beta_ui_module_boundary_rejects_details_report_or_optimizer_markers",
            ),
            TrinoBrowserReportRegressionTestRequirement(
                "product_surface_static_boundary_regressions",
                "product_surface_boundary_audit",
                "test_trino_product_surface_audit_detects_public_forbidden_support_claim",
            ),
        ),
    ),
)

TRINO_BROWSER_REPORT_PRODUCT_SURFACE_REQUIREMENTS = (
    "adapter_validated_reports_blocked",
    "forbidden_browser_report_product_capabilities",
    "llm_reports_not_wired",
    "query_optimizer_jobs_not_run",
    "generated_sql_not_generated",
    "trino_sql_execution_not_performed",
    "raw_sql_output_blocked",
    "query_id_output_blocked",
    "url_output_blocked",
    "local_path_output_blocked",
    "metadata_identifier_output_blocked",
    "secret_output_blocked",
    "runtime_internal_output_blocked",
)
TRINO_BROWSER_REPORT_REQUIRED_REVIEW_FAMILIES = tuple(
    family.family_id for family in TRINO_BROWSER_REPORT_REGRESSION_FAMILIES
)
TRINO_BROWSER_REPORT_REQUIRED_REVIEW_TEST_FILES = tuple(TRINO_BROWSER_REPORT_TEST_FILES)
TRINO_BROWSER_REPORT_REQUIRED_REVIEW_ROUTE_CAPABILITIES = tuple(
    TRINO_BROWSER_REPORT_REQUIRED_ROUTE_CAPABILITIES
)
TRINO_BROWSER_REPORT_REQUIRED_REVIEW_RAW_OUTPUT_REQUIREMENTS = (
    "raw_sql_output_blocked",
    "query_id_output_blocked",
    "url_output_blocked",
    "local_path_output_blocked",
    "metadata_identifier_output_blocked",
    "secret_output_blocked",
    "runtime_internal_output_blocked",
)
TRINO_BROWSER_REPORT_REQUIRED_REVIEW_UNSUPPORTED_SURFACE_REQUIREMENTS = (
    "adapter_validated_reports_blocked",
    "llm_reports_not_wired",
    "query_optimizer_jobs_not_run",
    "generated_sql_not_generated",
    "trino_sql_execution_not_performed",
)
TRINO_BROWSER_REPORT_REQUIRED_REVIEW_DOWNLOAD_TESTS = (
    "web_trino_beta_query::test_trino_beta_python_report_markdown_download_stays_raw_free",
    "web_trino_beta_query::test_trino_beta_optimizer_guidance_markdown_download_stays_raw_free",
)
TRINO_BROWSER_REPORT_REQUIRED_REVIEW_PUBLIC_CLAIM_TESTS = (
    "product_surface_boundary_audit::"
    "test_trino_product_surface_audit_detects_public_forbidden_support_claim",
)

TRINO_BROWSER_REPORT_FORBIDDEN_PRODUCT_REQUIREMENT_IDS = {
    "llm": "llm_reports_not_wired",
    "optimizer_job": "query_optimizer_jobs_not_run",
    "generated_sql": "generated_sql_not_generated",
    "sql_execution": "trino_sql_execution_not_performed",
    "raw": "raw_sql_output_blocked",
}


def audit_trino_browser_report_regression(
    *,
    families: Iterable[
        TrinoBrowserReportRegressionFamily
    ] = TRINO_BROWSER_REPORT_REGRESSION_FAMILIES,
    test_catalog: Mapping[str, set[str]] | None = None,
    capabilities: Iterable[EngineCapability] | None = None,
    trino_adapter: EngineAdapter | None = None,
    repo_root: Path | None = None,
) -> TrinoBrowserReportRegressionAuditResult:
    result = TrinoBrowserReportRegressionAuditResult()
    catalog = (
        _load_test_catalog(repo_root or Path.cwd())
        if test_catalog is None
        else {label: set(names) for label, names in test_catalog.items()}
    )
    capability_tuple = engine_capabilities("trino") if capabilities is None else tuple(capabilities)
    capabilities_by_surface = {capability.surface_id: capability for capability in capability_tuple}
    trino = get_engine_adapter("trino") if trino_adapter is None else trino_adapter
    family_tuple = tuple(families)

    result.source_file_count = len(catalog)
    _audit_adapter(result, trino)
    _audit_product_capability_boundary(result, capability_tuple)
    _audit_route_capabilities(result, capabilities_by_surface)
    for family in family_tuple:
        result.family_count += 1
        result.status_counts[family.readiness_state] += 1
        if family.production_blocker:
            result.open_blocker_count += 1
            result.blocker_counts[family.production_blocker] += 1
            result.blockers.append((family.family_id, family.production_blocker))
        for requirement in family.tests:
            result.required_test_count += 1
            _audit_test_requirement(result, requirement, catalog)
    finalize_browser_report_requirement_tracking(result, family_tuple)
    audit_browser_report_production_review_profile(result, family_tuple, catalog)
    return result


def browser_report_regression_summary_payload(
    result: TrinoBrowserReportRegressionAuditResult,
    *,
    status: str,
) -> dict[str, Any]:
    return {
        "summary_kind": TRINO_BROWSER_REPORT_REGRESSION_SUMMARY_KIND,
        "status": status,
        "closure_gate": TRINO_BROWSER_REPORT_REGRESSION_GATE,
        "browser_report_regression_status": TRINO_BROWSER_REPORT_REGRESSION_STATUS,
        "broader_production_closure_status": "not_closed",
        "closure_reason": TRINO_BROWSER_REPORT_REGRESSION_CLOSURE_REASON,
        "product_surface": TRINO_BROWSER_REPORT_PRODUCT_SURFACE,
        "details_case_view": TRINO_BROWSER_REPORT_DETAILS_CASE_VIEW,
        "python_report": TRINO_BROWSER_REPORT_PYTHON_REPORT,
        "optimizer_guidance": TRINO_BROWSER_REPORT_OPTIMIZER_GUIDANCE,
        "llm_reports": TRINO_BROWSER_REPORT_LLM_REPORTS,
        "trino_sql_execution": TRINO_BROWSER_REPORT_SQL_EXECUTION,
        "raw_sql_output": TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
        "query_id_output": TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
        "url_output": TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
        "local_path_output": TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
        "metadata_identifier_output": TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
        "secret_output": TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
        "runtime_internal_output": TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
        "adapter_validated_reports": (
            "enabled"
            if result.adapter_validated_reports_enabled
            else TRINO_BROWSER_REPORT_ADAPTER_VALIDATED_REPORTS_STATUS
        ),
        "family_count": result.family_count,
        "required_test_count": result.required_test_count,
        "present_test_count": result.present_test_count,
        "source_file_count": result.source_file_count,
        "required_route_capability_count": result.required_route_capability_count,
        "product_capability_count": result.product_capability_count,
        "open_blocker_count": result.open_blocker_count,
        "status_counts": _counter_payload(result.status_counts),
        "test_family_counts": _counter_payload(result.test_family_counts),
        "test_file_counts": _counter_payload(result.test_file_counts),
        "route_capability_counts": _counter_payload(result.route_capability_counts),
        "product_capability_counts": _counter_payload(result.product_capability_counts),
        "browser_report_requirement_tracking_counts": _counter_payload(
            result.browser_report_requirement_tracking_counts
        ),
        "production_review_profile": TRINO_BROWSER_REPORT_PRODUCTION_REVIEW_PROFILE,
        "production_review_profile_status": _production_review_profile_status(result),
        "production_review_requirements": {
            "required_families": list(TRINO_BROWSER_REPORT_REQUIRED_REVIEW_FAMILIES),
            "required_test_files": list(TRINO_BROWSER_REPORT_REQUIRED_REVIEW_TEST_FILES),
            "required_route_capabilities": list(
                TRINO_BROWSER_REPORT_REQUIRED_REVIEW_ROUTE_CAPABILITIES
            ),
            "required_raw_output_requirements": list(
                TRINO_BROWSER_REPORT_REQUIRED_REVIEW_RAW_OUTPUT_REQUIREMENTS
            ),
            "required_unsupported_surface_requirements": list(
                TRINO_BROWSER_REPORT_REQUIRED_REVIEW_UNSUPPORTED_SURFACE_REQUIREMENTS
            ),
            "required_download_tests": list(TRINO_BROWSER_REPORT_REQUIRED_REVIEW_DOWNLOAD_TESTS),
            "required_public_claim_tests": list(
                TRINO_BROWSER_REPORT_REQUIRED_REVIEW_PUBLIC_CLAIM_TESTS
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
        "browser_report_requirement_tracking": [
            {
                "family_id": tracking.family_id,
                "requirement_type": tracking.requirement_type,
                "requirement_id": tracking.requirement_id,
                "tracking_status": tracking.tracking_status,
                "issue_count": tracking.issue_count,
            }
            for tracking in result.browser_report_requirement_tracking
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


def _load_test_catalog(repo_root: Path) -> dict[str, set[str]]:
    catalog: dict[str, set[str]] = {}
    for label, relative_path in TRINO_BROWSER_REPORT_TEST_FILES.items():
        path = repo_root / relative_path
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        catalog[label] = _test_names_from_source(source)
    return catalog


def _test_names_from_source(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }


def _audit_adapter(
    result: TrinoBrowserReportRegressionAuditResult,
    trino_adapter: EngineAdapter,
) -> None:
    result.adapter_validated_reports_enabled = bool(
        getattr(trino_adapter, "supports_validated_reports", False)
    )
    if result.adapter_validated_reports_enabled:
        _add_issue(
            result,
            "product_surfaces",
            "trino_browser_report_adapter_validated_reports_enabled",
            "Trino adapter validated reports must stay blocked until browser/report regression coverage closes.",
            requirement_type="product_surface",
            requirement_id="adapter_validated_reports_blocked",
        )


def _audit_product_capability_boundary(
    result: TrinoBrowserReportRegressionAuditResult,
    capabilities: Iterable[EngineCapability],
) -> None:
    for capability in capabilities:
        if not capability.product_surface_allowed:
            continue
        result.product_capability_count += 1
        result.product_capability_counts[capability.surface_id] += 1
        forbidden_requirement_id = _forbidden_product_requirement_id(capability.surface_id)
        forbidden_surface = (
            capability.surface_id not in (TRINO_BROWSER_REPORT_ALLOWED_PRODUCT_CAPABILITY_IDS)
            or forbidden_requirement_id is not None
        )
        route_requirement_id = _forbidden_product_requirement_id(capability.route_path)
        forbidden_route = route_requirement_id is not None
        if forbidden_surface or forbidden_route:
            requirement_id = (
                forbidden_requirement_id
                or route_requirement_id
                or "forbidden_browser_report_product_capabilities"
            )
            _add_issue(
                result,
                "product_surfaces",
                "trino_browser_report_forbidden_product_capability",
                "Trino browser/report product capabilities must stay limited to current raw-free materialized surfaces.",
                requirement_type="product_surface",
                requirement_id=requirement_id,
            )


def _forbidden_product_requirement_id(value: str | None) -> str | None:
    if not value:
        return None
    for token, requirement_id in TRINO_BROWSER_REPORT_FORBIDDEN_PRODUCT_REQUIREMENT_IDS.items():
        if token in value:
            return requirement_id
    return None


def _audit_route_capabilities(
    result: TrinoBrowserReportRegressionAuditResult,
    capabilities_by_surface: Mapping[str, EngineCapability],
) -> None:
    for surface_id, expected_route in TRINO_BROWSER_REPORT_REQUIRED_ROUTE_CAPABILITIES.items():
        result.required_route_capability_count += 1
        capability = capabilities_by_surface.get(surface_id)
        if capability is None:
            _add_issue(
                result,
                "route_capabilities",
                "trino_browser_report_route_capability_missing",
                "A required Trino browser/report product route capability is missing.",
                requirement_type="route_capability",
                requirement_id=surface_id,
            )
            continue
        result.route_capability_counts[surface_id] += 1
        expected_fields: tuple[tuple[str, object], ...] = (
            ("support_level", "production"),
            ("surface_class", "product_web"),
            ("raw_policy", "raw_free_summary_only"),
            ("product_surface_allowed", True),
            ("cli_role", None),
            ("script_path", None),
            ("route_path", expected_route),
            ("dev_only", False),
        )
        for field_name, expected_value in expected_fields:
            if getattr(capability, field_name) != expected_value:
                _add_issue(
                    result,
                    "route_capabilities",
                    f"trino_browser_report_route_capability_{field_name}_drift",
                    "A Trino browser/report route capability drifted from the raw-free product boundary.",
                    requirement_type="route_capability",
                    requirement_id=surface_id,
                )


def _audit_test_requirement(
    result: TrinoBrowserReportRegressionAuditResult,
    requirement: TrinoBrowserReportRegressionTestRequirement,
    test_catalog: Mapping[str, set[str]],
) -> None:
    tests = test_catalog.get(requirement.test_file_label)
    if tests is None:
        _add_issue(
            result,
            requirement.family_id,
            "trino_browser_report_test_file_missing",
            "A required Trino browser/report regression test file is not in the test catalog.",
            requirement_type="test",
            requirement_id=_test_requirement_id(requirement),
        )
        return
    if requirement.test_name not in tests:
        _add_issue(
            result,
            requirement.family_id,
            "trino_browser_report_test_missing",
            "A required Trino browser/report regression test is missing.",
            requirement_type="test",
            requirement_id=_test_requirement_id(requirement),
        )
        return
    result.present_test_count += 1
    result.test_family_counts[requirement.family_id] += 1
    result.test_file_counts[requirement.test_file_label] += 1


def finalize_browser_report_requirement_tracking(
    result: TrinoBrowserReportRegressionAuditResult,
    families: tuple[TrinoBrowserReportRegressionFamily, ...],
) -> None:
    result.browser_report_requirement_tracking.clear()
    result.browser_report_requirement_tracking_counts.clear()
    for family in families:
        for requirement in family.tests:
            _append_browser_report_requirement_tracking(
                result,
                family_id=family.family_id,
                requirement_type="test",
                requirement_id=_test_requirement_id(requirement),
            )
    for surface_id in TRINO_BROWSER_REPORT_REQUIRED_ROUTE_CAPABILITIES:
        _append_browser_report_requirement_tracking(
            result,
            family_id="route_capabilities",
            requirement_type="route_capability",
            requirement_id=surface_id,
        )
    for requirement_id in TRINO_BROWSER_REPORT_PRODUCT_SURFACE_REQUIREMENTS:
        _append_browser_report_requirement_tracking(
            result,
            family_id="product_surfaces",
            requirement_type="product_surface",
            requirement_id=requirement_id,
        )


def audit_browser_report_production_review_profile(
    result: TrinoBrowserReportRegressionAuditResult,
    families: tuple[TrinoBrowserReportRegressionFamily, ...],
    test_catalog: Mapping[str, set[str]],
) -> None:
    family_ids = {family.family_id for family in families}
    required_test_ids = _required_test_ids(families)
    _append_production_review_tracking(
        result,
        requirement_id="require_regression_families",
        counter_name="families",
        observed_count=sum(
            1
            for family_id in TRINO_BROWSER_REPORT_REQUIRED_REVIEW_FAMILIES
            if family_id in family_ids
        ),
        required_count=len(TRINO_BROWSER_REPORT_REQUIRED_REVIEW_FAMILIES),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_test_files",
        counter_name="test_files",
        observed_count=sum(
            1
            for test_file_label in TRINO_BROWSER_REPORT_REQUIRED_REVIEW_TEST_FILES
            if test_file_label in test_catalog
        ),
        required_count=len(TRINO_BROWSER_REPORT_REQUIRED_REVIEW_TEST_FILES),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_all_regression_tests",
        counter_name="tests",
        observed_count=_accepted_requirement_count(
            result,
            requirement_type="test",
            requirement_ids=required_test_ids,
        ),
        required_count=len(required_test_ids),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_materialized_route_capabilities",
        counter_name="route_capabilities",
        observed_count=_accepted_requirement_count(
            result,
            requirement_type="route_capability",
            requirement_ids=TRINO_BROWSER_REPORT_REQUIRED_REVIEW_ROUTE_CAPABILITIES,
        ),
        required_count=len(TRINO_BROWSER_REPORT_REQUIRED_REVIEW_ROUTE_CAPABILITIES),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_raw_output_blocks",
        counter_name="raw_output_requirements",
        observed_count=_accepted_requirement_count(
            result,
            requirement_type="product_surface",
            requirement_ids=TRINO_BROWSER_REPORT_REQUIRED_REVIEW_RAW_OUTPUT_REQUIREMENTS,
        ),
        required_count=len(TRINO_BROWSER_REPORT_REQUIRED_REVIEW_RAW_OUTPUT_REQUIREMENTS),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_unsupported_surface_blocks",
        counter_name="unsupported_surface_requirements",
        observed_count=_accepted_requirement_count(
            result,
            requirement_type="product_surface",
            requirement_ids=TRINO_BROWSER_REPORT_REQUIRED_REVIEW_UNSUPPORTED_SURFACE_REQUIREMENTS,
        ),
        required_count=len(TRINO_BROWSER_REPORT_REQUIRED_REVIEW_UNSUPPORTED_SURFACE_REQUIREMENTS),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_download_regressions",
        counter_name="download_tests",
        observed_count=_accepted_requirement_count(
            result,
            requirement_type="test",
            requirement_ids=TRINO_BROWSER_REPORT_REQUIRED_REVIEW_DOWNLOAD_TESTS,
        ),
        required_count=len(TRINO_BROWSER_REPORT_REQUIRED_REVIEW_DOWNLOAD_TESTS),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_public_claim_regressions",
        counter_name="public_claim_tests",
        observed_count=_accepted_requirement_count(
            result,
            requirement_type="test",
            requirement_ids=TRINO_BROWSER_REPORT_REQUIRED_REVIEW_PUBLIC_CLAIM_TESTS,
        ),
        required_count=len(TRINO_BROWSER_REPORT_REQUIRED_REVIEW_PUBLIC_CLAIM_TESTS),
    )


def _required_test_ids(
    families: tuple[TrinoBrowserReportRegressionFamily, ...],
) -> tuple[str, ...]:
    return tuple(
        _test_requirement_id(requirement) for family in families for requirement in family.tests
    )


def _accepted_requirement_count(
    result: TrinoBrowserReportRegressionAuditResult,
    *,
    requirement_type: str,
    requirement_ids: tuple[str, ...],
) -> int:
    accepted_requirement_ids = {
        tracking.requirement_id
        for tracking in result.browser_report_requirement_tracking
        if tracking.requirement_type == requirement_type and tracking.tracking_status == "accepted"
    }
    return sum(
        1 for requirement_id in requirement_ids if requirement_id in accepted_requirement_ids
    )


def _append_production_review_tracking(
    result: TrinoBrowserReportRegressionAuditResult,
    *,
    requirement_id: str,
    counter_name: str,
    observed_count: int,
    required_count: int,
) -> None:
    tracking_status = _production_review_tracking_status(observed_count, required_count)
    result.production_review_tracking.append(
        TrinoBrowserReportProductionReviewTracking(
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
            "trino_browser_report_production_review_gap",
            "Trino browser/report production-review profile is incomplete.",
            requirement_type="production_review_profile",
            requirement_id=requirement_id,
        )


def _production_review_tracking_status(observed_count: int, required_count: int) -> str:
    if required_count <= 0:
        return "not_required"
    if observed_count >= required_count:
        return "accepted"
    return "insufficient"


def _production_review_profile_status(result: TrinoBrowserReportRegressionAuditResult) -> str:
    if not result.production_review_tracking:
        return "not_required"
    if set(result.production_review_tracking_counts) == {"accepted"}:
        return TRINO_BROWSER_REPORT_PRODUCTION_REVIEW_PROFILE_STATUS
    return "failed"


def _append_browser_report_requirement_tracking(
    result: TrinoBrowserReportRegressionAuditResult,
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
    tracking_status = _browser_report_requirement_tracking_status(issues)
    result.browser_report_requirement_tracking.append(
        TrinoBrowserReportRequirementTracking(
            family_id=family_id,
            requirement_type=requirement_type,
            requirement_id=requirement_id,
            tracking_status=tracking_status,
            issue_count=len(issues),
        )
    )
    result.browser_report_requirement_tracking_counts[tracking_status] += 1


def _issues_for_requirement(
    result: TrinoBrowserReportRegressionAuditResult,
    *,
    family_id: str,
    requirement_type: str,
    requirement_id: str,
) -> tuple[TrinoBrowserReportRegressionIssue, ...]:
    return tuple(
        issue
        for issue_family_id, issue in result.issues
        if issue_family_id == family_id
        and issue.requirement_type == requirement_type
        and issue.requirement_id == requirement_id
    )


def _browser_report_requirement_tracking_status(
    issues: tuple[TrinoBrowserReportRegressionIssue, ...],
) -> str:
    if any(
        issue.category
        in {
            "trino_browser_report_test_file_missing",
            "trino_browser_report_test_missing",
            "trino_browser_report_route_capability_missing",
        }
        for issue in issues
    ):
        return "missing"
    if issues:
        return "invalid"
    return "accepted"


def _test_requirement_id(requirement: TrinoBrowserReportRegressionTestRequirement) -> str:
    return f"{requirement.test_file_label}::{requirement.test_name}"


def _add_issue(
    result: TrinoBrowserReportRegressionAuditResult,
    family_id: str,
    category: str,
    message: str,
    *,
    requirement_type: str | None = None,
    requirement_id: str | None = None,
) -> None:
    issue = TrinoBrowserReportRegressionIssue(
        category=category,
        message=message,
        requirement_type=requirement_type,
        requirement_id=requirement_id,
    )
    result.issue_counts[category] += 1
    result.issues.append((family_id, issue))


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}
