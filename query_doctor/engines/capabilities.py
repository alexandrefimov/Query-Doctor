"""Machine-checkable engine capability manifest."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal


SupportLevel = Literal[
    "production",
    "product_beta",
    "bounded_raw_free_preview",
    "bounded_compact_preview",
    "dev_gate",
]
SurfaceClass = Literal[
    "product_cli",
    "product_web",
    "preview_cli",
    "isolated_preview_web",
    "dev_gate",
    "dev_wrapper",
]
RawPolicy = Literal[
    "bounded_raw_redacted",
    "already_sanitized_raw_free",
    "compact_raw_free",
    "raw_free_summary_only",
]


@dataclass(frozen=True)
class EngineCapability:
    engine: str
    surface_id: str
    support_level: SupportLevel
    surface_class: SurfaceClass
    input_kind: str
    raw_policy: RawPolicy
    product_surface_allowed: bool
    adapter_flag: str | None = None
    cli_role: str | None = None
    script_path: str | None = None
    route_path: str | None = None
    dev_only: bool = False
    promotion_gate: str = ""


PRODUCT_ADAPTER_FLAGS = frozenset(
    {
        "supports_recent_scan",
        "supports_query_id_mode",
        "supports_metadata_collection",
        "supports_validated_reports",
    }
)


def _capability(
    *,
    engine: str,
    surface_id: str,
    support_level: SupportLevel,
    surface_class: SurfaceClass,
    input_kind: str,
    raw_policy: RawPolicy,
    product_surface_allowed: bool,
    adapter_flag: str | None = None,
    cli_role: str | None = None,
    script_path: str | None = None,
    route_path: str | None = None,
    dev_only: bool = False,
    promotion_gate: str = "",
) -> EngineCapability:
    return EngineCapability(
        engine=engine,
        surface_id=surface_id,
        support_level=support_level,
        surface_class=surface_class,
        input_kind=input_kind,
        raw_policy=raw_policy,
        product_surface_allowed=product_surface_allowed,
        adapter_flag=adapter_flag,
        cli_role=cli_role,
        script_path=script_path,
        route_path=route_path,
        dev_only=dev_only,
        promotion_gate=promotion_gate,
    )


def _impala_product(
    surface_id: str,
    *,
    adapter_flag: str,
    cli_role: str,
    input_kind: str,
    promotion_gate: str,
) -> EngineCapability:
    return _capability(
        engine="impala",
        surface_id=surface_id,
        support_level="production",
        surface_class="product_cli",
        input_kind=input_kind,
        raw_policy="bounded_raw_redacted",
        product_surface_allowed=True,
        adapter_flag=adapter_flag,
        cli_role=cli_role,
        promotion_gate=promotion_gate,
    )


def _trino_preview(
    surface_id: str,
    *,
    input_kind: str,
    promotion_gate: str,
    adapter_flag: str | None = None,
    cli_role: str | None = None,
    raw_policy: RawPolicy = "already_sanitized_raw_free",
    surface_class: SurfaceClass = "preview_cli",
    route_path: str | None = None,
) -> EngineCapability:
    return _capability(
        engine="trino",
        surface_id=surface_id,
        support_level="bounded_raw_free_preview",
        surface_class=surface_class,
        input_kind=input_kind,
        raw_policy=raw_policy,
        product_surface_allowed=False,
        adapter_flag=adapter_flag,
        cli_role=cli_role,
        route_path=route_path,
        promotion_gate=promotion_gate,
    )


def _trino_beta(
    surface_id: str,
    *,
    input_kind: str,
    promotion_gate: str,
    adapter_flag: str | None = None,
    raw_policy: RawPolicy = "raw_free_summary_only",
    surface_class: SurfaceClass = "product_web",
) -> EngineCapability:
    return _capability(
        engine="trino",
        surface_id=surface_id,
        support_level="product_beta",
        surface_class=surface_class,
        input_kind=input_kind,
        raw_policy=raw_policy,
        product_surface_allowed=True,
        adapter_flag=adapter_flag,
        promotion_gate=promotion_gate,
    )


def _trino_dev(
    surface_id: str,
    *,
    input_kind: str,
    script_path: str,
    promotion_gate: str,
    raw_policy: RawPolicy = "raw_free_summary_only",
    surface_class: SurfaceClass = "dev_gate",
) -> EngineCapability:
    return _capability(
        engine="trino",
        surface_id=surface_id,
        support_level="dev_gate",
        surface_class=surface_class,
        input_kind=input_kind,
        raw_policy=raw_policy,
        product_surface_allowed=False,
        script_path=script_path,
        dev_only=True,
        promotion_gate=promotion_gate,
    )


def _spark_preview(
    surface_id: str,
    *,
    input_kind: str,
    promotion_gate: str,
    adapter_flag: str | None = None,
    cli_role: str | None = None,
    script_path: str | None = None,
    surface_class: SurfaceClass = "preview_cli",
    route_path: str | None = None,
) -> EngineCapability:
    return _capability(
        engine="spark",
        surface_id=surface_id,
        support_level="bounded_compact_preview",
        surface_class=surface_class,
        input_kind=input_kind,
        raw_policy="compact_raw_free",
        product_surface_allowed=False,
        adapter_flag=adapter_flag,
        cli_role=cli_role,
        script_path=script_path,
        route_path=route_path,
        promotion_gate=promotion_gate,
    )


def _spark_dev(
    surface_id: str,
    *,
    input_kind: str,
    script_path: str,
    promotion_gate: str,
    raw_policy: RawPolicy = "raw_free_summary_only",
    surface_class: SurfaceClass = "dev_gate",
) -> EngineCapability:
    return _capability(
        engine="spark",
        surface_id=surface_id,
        support_level="dev_gate",
        surface_class=surface_class,
        input_kind=input_kind,
        raw_policy=raw_policy,
        product_surface_allowed=False,
        script_path=script_path,
        dev_only=True,
        promotion_gate=promotion_gate,
    )


ENGINE_CAPABILITIES: tuple[EngineCapability, ...] = (
    _impala_product(
        "recent_scan",
        adapter_flag="supports_recent_scan",
        cli_role="batch_recent",
        input_kind="cm_or_direct_impala_profile",
        promotion_gate="implemented_production_impala_workflow",
    ),
    _impala_product(
        "query_id_mode",
        adapter_flag="supports_query_id_mode",
        cli_role="collect_impala_profile",
        input_kind="one_known_impala_query_id",
        promotion_gate="implemented_production_impala_workflow",
    ),
    _impala_product(
        "metadata_collection",
        adapter_flag="supports_metadata_collection",
        cli_role="collect_impala_context",
        input_kind="allowlisted_impala_metadata",
        promotion_gate="implemented_production_impala_workflow",
    ),
    _impala_product(
        "validated_reports",
        adapter_flag="supports_validated_reports",
        cli_role="report",
        input_kind="validated_impala_case",
        promotion_gate="strict_report_validation",
    ),
    _trino_beta(
        "recent_scan",
        adapter_flag="supports_recent_scan",
        input_kind="bounded_trino_retained_query_list_pruned_query_info",
        promotion_gate="trino_beta_recent_retained_query_list_contract",
    ),
    _trino_beta(
        "query_id_mode",
        adapter_flag="supports_query_id_mode",
        input_kind="one_known_trino_query_id_pruned_query_info",
        promotion_gate="trino_beta_one_query_pruned_query_info_contract",
    ),
    _trino_preview(
        "offline_evidence_import",
        adapter_flag="supports_offline_evidence_import",
        cli_role="trino_import",
        input_kind="sanitized_evidence_package",
        promotion_gate="redaction_note_v1_and_package_contract",
    ),
    _trino_preview(
        "local_event_store_import",
        adapter_flag="supports_local_event_store_import",
        cli_role="trino_event_store_import",
        input_kind="sanitized_local_event_store",
        promotion_gate="accepted_event_source_contract",
    ),
    _trino_preview(
        "local_query_detail_import",
        adapter_flag="supports_local_query_detail_import",
        cli_role="trino_query_detail_import",
        input_kind="sanitized_local_query_detail",
        promotion_gate="accepted_query_detail_contract",
    ),
    _trino_preview(
        "local_query_list_import",
        adapter_flag="supports_local_query_list_import",
        cli_role="trino_query_list_import",
        input_kind="sanitized_query_list_aggregate",
        promotion_gate="aggregate_only_boundary_review",
    ),
    _trino_preview(
        "local_statement_stats_import",
        adapter_flag="supports_local_statement_stats_import",
        cli_role="trino_statement_stats_import",
        input_kind="sanitized_statement_stats",
        promotion_gate="statement_stats_contract",
    ),
    _trino_preview(
        "http_event_archive_import",
        adapter_flag="supports_http_event_archive_import",
        cli_role="trino_http_event_archive_import",
        input_kind="operator_http_event_archive",
        promotion_gate="accepted_http_event_archive_contract",
    ),
    _trino_preview(
        "http_query_detail_archive_import",
        adapter_flag="supports_http_query_detail_archive_import",
        cli_role="trino_http_query_detail_archive_import",
        input_kind="operator_http_query_detail_archive",
        promotion_gate="accepted_http_query_detail_archive_contract",
    ),
    _trino_preview(
        "event_source_contract_check",
        adapter_flag="supports_event_source_contract_check",
        cli_role="trino_event_source_contract_check",
        input_kind="event_source_contract",
        raw_policy="raw_free_summary_only",
        promotion_gate="source_contract_acceptance",
    ),
    _trino_preview(
        "local_query_info_pruned_import",
        adapter_flag="supports_local_query_info_pruned_import",
        cli_role="trino_query_info_pruned_import",
        input_kind="sanitized_local_pruned_query_info",
        promotion_gate="coordinator_query_info_contract",
    ),
    _trino_preview(
        "coordinator_query_info_target_check",
        adapter_flag="supports_coordinator_query_info_target_check",
        cli_role="trino_coordinator_query_info_target_check",
        input_kind="coordinator_query_info_source_contract",
        raw_policy="raw_free_summary_only",
        promotion_gate="dry_run_target_check_only",
    ),
    _trino_preview(
        "coordinator_query_info_pruned_probe",
        adapter_flag="supports_coordinator_query_info_pruned_probe",
        cli_role="trino_coordinator_query_info_pruned_probe",
        input_kind="one_query_pruned_query_info_probe",
        raw_policy="raw_free_summary_only",
        promotion_gate="one_bounded_read_without_fact_mapping",
    ),
    _trino_preview(
        "coordinator_query_info_pruned_import",
        adapter_flag="supports_coordinator_query_info_pruned_import",
        cli_role="trino_coordinator_query_info_pruned_import",
        input_kind="one_query_pruned_query_info_import",
        raw_policy="raw_free_summary_only",
        promotion_gate="one_query_readiness_gate",
    ),
    _trino_preview(
        "metadata_source_contract_check",
        cli_role="trino_metadata_source_contract_check",
        input_kind="metadata_allowlist_source_contract",
        raw_policy="raw_free_summary_only",
        promotion_gate="metadata_allowlist_contract_check_only",
    ),
    _trino_preview(
        "local_metadata_summary_import",
        cli_role="trino_metadata_summary_import",
        input_kind="sanitized_aggregate_metadata_summary",
        promotion_gate="aggregate_metadata_summary_not_diagnosis",
    ),
    _trino_preview(
        "compact_diagnosis",
        adapter_flag="supports_compact_diagnosis",
        cli_role="diagnose_trino_compact",
        input_kind="raw_free_engine_fact_boundary",
        surface_class="isolated_preview_web",
        route_path="/trino/compact-diagnosis",
        promotion_gate="isolated_compact_page_only",
    ),
    _trino_dev(
        "evidence_package_build",
        input_kind="sanitized_samples",
        raw_policy="already_sanitized_raw_free",
        surface_class="dev_wrapper",
        script_path="scripts/build_trino_evidence_package.py",
        promotion_gate="developer_package_fixture_workflow",
    ),
    _trino_dev(
        "evidence_package_validate",
        input_kind="sanitized_evidence_package",
        raw_policy="already_sanitized_raw_free",
        surface_class="dev_wrapper",
        script_path="scripts/validate_trino_evidence_package.py",
        promotion_gate="developer_package_fixture_workflow",
    ),
    _trino_dev(
        "evidence_package_requirements",
        input_kind="python_owned_contract_summary",
        script_path="scripts/trino_evidence_package_requirements.py",
        promotion_gate="developer_requirements_print_only",
    ),
    _trino_dev(
        "demo_evidence_package",
        input_kind="synthetic_demo_samples",
        raw_policy="already_sanitized_raw_free",
        surface_class="dev_wrapper",
        script_path="scripts/demo_trino_evidence_package.py",
        promotion_gate="synthetic_demo_only",
    ),
    _trino_dev(
        "kerberos_smoke",
        input_kind="operator_prepared_local_ticket_cache",
        surface_class="dev_wrapper",
        script_path="scripts/trino_kerberos_smoke.py",
        promotion_gate="local_private_preview_smoke_only",
    ),
    _trino_dev(
        "kerberos_cache_refresh",
        input_kind="local_web_config_and_keytab",
        surface_class="dev_wrapper",
        script_path="scripts/refresh_trino_kerberos_caches.py",
        promotion_gate="local_private_preview_smoke_only",
    ),
    _trino_dev(
        "evidence_handoff_audit",
        input_kind="sanitized_evidence_package",
        raw_policy="already_sanitized_raw_free",
        script_path="scripts/audit_trino_evidence_handoff.py",
        promotion_gate="developer_handoff_readiness_gate",
    ),
    _trino_dev(
        "evidence_handoff_suite_manifest",
        input_kind="safe_relative_json_manifest",
        script_path="scripts/build_trino_evidence_handoff_suite_manifest.py",
        promotion_gate="developer_handoff_suite_gate",
    ),
    _trino_dev(
        "one_query_live_handoff",
        input_kind="one_query_pruned_query_info_import",
        surface_class="dev_wrapper",
        script_path="scripts/trino_one_query_live_handoff.py",
        promotion_gate="developer_one_query_readiness_gate",
    ),
    _trino_dev(
        "handoff_suite_manifest",
        input_kind="safe_relative_json_manifest",
        script_path="scripts/build_trino_handoff_suite_manifest.py",
        promotion_gate="developer_one_query_suite_gate",
    ),
    _trino_dev(
        "compact_readiness_audit",
        input_kind="retained_raw_free_handoff_artifacts",
        script_path="scripts/audit_trino_compact_readiness.py",
        promotion_gate="one_query_readiness_audit",
    ),
    _trino_dev(
        "product_surface_boundary_audit",
        input_kind="retained_raw_free_compact_artifacts",
        script_path="scripts/audit_trino_product_surface_boundary.py",
        promotion_gate="product_surface_blocking_audit",
    ),
    _trino_dev(
        "support_gap_matrix_audit",
        input_kind="capability_and_fact_registry",
        script_path="scripts/audit_trino_support_gap_matrix.py",
        promotion_gate="support_gap_static_audit",
    ),
    _trino_dev(
        "web_beta_readiness_audit",
        input_kind="local_web_config_and_source_contracts",
        script_path="scripts/audit_trino_web_beta_readiness.py",
        promotion_gate="local_config_readiness_without_network_read",
    ),
    _trino_dev(
        "web_beta_live_smoke",
        input_kind="bounded_trino_retained_query_list_pruned_query_info",
        script_path="scripts/audit_trino_web_beta_live_smoke.py",
        promotion_gate="developer_web_beta_live_smoke",
    ),
    _trino_dev(
        "installed_beta_web_smoke",
        input_kind="installed_web_fake_trino_coordinator",
        script_path="scripts/installed_trino_beta_web_smoke.py",
        promotion_gate="installed_package_beta_web_regression_gate",
    ),
    _trino_dev(
        "beta_release_readiness_bundle",
        input_kind="static_audits_focused_tests_and_optional_local_smokes",
        script_path="scripts/audit_trino_beta_release_readiness.py",
        promotion_gate="developer_beta_release_handoff_gate",
    ),
    _spark_preview(
        "offline_evidence_import",
        adapter_flag="supports_offline_evidence_import",
        cli_role="validate_spark_evidence_package",
        script_path="scripts/validate_spark_evidence_package.py",
        input_kind="sanitized_compact_evidence_package",
        promotion_gate="redaction_note_v1_and_compact_package_contract",
    ),
    _spark_preview(
        "compact_diagnosis",
        adapter_flag="supports_compact_diagnosis",
        cli_role="diagnose_spark_compact",
        input_kind="spark_history_compact_summary",
        surface_class="isolated_preview_web",
        route_path="/spark/compact-diagnosis",
        promotion_gate="isolated_compact_page_only",
    ),
    _spark_preview(
        "history_server_compact_intake",
        adapter_flag="supports_history_server_compact_intake",
        cli_role="collect_spark_history",
        input_kind="one_explicit_history_server_application",
        promotion_gate="bounded_one_application_history_server_contract",
    ),
    _spark_preview(
        "evidence_package_build",
        cli_role="build_spark_evidence_package",
        script_path="scripts/build_spark_evidence_package.py",
        input_kind="already_compact_samples",
        promotion_gate="compact_package_fixture_workflow",
    ),
    _spark_preview(
        "evidence_fixtures_export",
        cli_role="export_spark_evidence_fixtures",
        script_path="scripts/export_spark_evidence_fixtures.py",
        input_kind="sanitized_compact_evidence_package",
        promotion_gate="compact_fixture_export_only",
    ),
    _spark_dev(
        "evidence_package_requirements",
        input_kind="python_owned_contract_summary",
        script_path="scripts/spark_evidence_package_requirements.py",
        promotion_gate="developer_requirements_print_only",
    ),
    _spark_dev(
        "one_application_handoff",
        input_kind="one_explicit_history_server_application",
        raw_policy="compact_raw_free",
        surface_class="dev_wrapper",
        script_path="scripts/spark_one_application_handoff.py",
        promotion_gate="developer_one_application_handoff_gate",
    ),
    _spark_dev(
        "one_application_handoff_suite_manifest",
        input_kind="safe_relative_json_manifest",
        script_path="scripts/build_spark_one_application_handoff_suite_manifest.py",
        promotion_gate="developer_one_application_suite_gate",
    ),
    _spark_dev(
        "one_application_suite_to_package",
        input_kind="retained_raw_free_one_application_suite",
        script_path="scripts/build_spark_evidence_package_from_one_application_suite.py",
        promotion_gate="developer_suite_to_package_bridge",
    ),
    _spark_dev(
        "compact_readiness_audit",
        input_kind="retained_raw_free_compact_artifacts",
        script_path="scripts/audit_spark_compact_readiness.py",
        promotion_gate="compact_readiness_audit",
    ),
    _spark_dev(
        "evidence_handoff_audit",
        input_kind="retained_raw_free_handoff_summaries",
        script_path="scripts/audit_spark_evidence_handoff.py",
        promotion_gate="developer_evidence_handoff_gate",
    ),
    _spark_dev(
        "handoff_suite_manifest",
        input_kind="safe_relative_json_manifest",
        script_path="scripts/build_spark_handoff_suite_manifest.py",
        promotion_gate="developer_handoff_suite_gate",
    ),
    _spark_dev(
        "support_boundary_audit",
        input_kind="capability_and_product_surface_registry",
        script_path="scripts/audit_spark_support_boundary.py",
        promotion_gate="support_boundary_static_audit",
    ),
    _spark_dev(
        "product_surface_boundary_audit",
        input_kind="retained_raw_free_compact_artifacts",
        script_path="scripts/audit_spark_product_surface_boundary.py",
        promotion_gate="product_surface_blocking_audit",
    ),
)


def engine_capabilities(engine: str | None = None) -> tuple[EngineCapability, ...]:
    if engine is None:
        return ENGINE_CAPABILITIES
    normalized = engine.strip().lower()
    return tuple(
        capability for capability in ENGINE_CAPABILITIES if capability.engine == normalized
    )


def adapter_flag_capabilities(engine: str | None = None) -> tuple[EngineCapability, ...]:
    return tuple(
        capability for capability in engine_capabilities(engine) if capability.adapter_flag
    )


def adapter_flags_for_engine(engine: str) -> frozenset[str]:
    return frozenset(
        capability.adapter_flag
        for capability in adapter_flag_capabilities(engine)
        if capability.adapter_flag
    )


def cli_role_capabilities(engine: str | None = None) -> tuple[EngineCapability, ...]:
    return tuple(capability for capability in engine_capabilities(engine) if capability.cli_role)


def cli_roles_for_engine(engine: str) -> frozenset[str]:
    return frozenset(
        capability.cli_role for capability in cli_role_capabilities(engine) if capability.cli_role
    )


def script_paths_for_engine(engine: str) -> frozenset[str]:
    return frozenset(
        capability.script_path
        for capability in engine_capabilities(engine)
        if capability.script_path
    )


def second_engine_cli_roles() -> frozenset[str]:
    roles: set[str] = set()
    for engine in ("spark", "trino"):
        roles.update(cli_roles_for_engine(engine))
    return frozenset(roles)


def product_adapter_flags() -> frozenset[str]:
    return PRODUCT_ADAPTER_FLAGS


def unsupported_product_capabilities(engine: str) -> tuple[EngineCapability, ...]:
    return tuple(
        capability
        for capability in engine_capabilities(engine)
        if (
            capability.adapter_flag in PRODUCT_ADAPTER_FLAGS
            and not capability.product_surface_allowed
        )
        or capability.support_level == "production"
    )


def capability_ids(capabilities: Iterable[EngineCapability]) -> frozenset[str]:
    return frozenset(capability.surface_id for capability in capabilities)
