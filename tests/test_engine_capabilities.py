from dataclasses import fields
from pathlib import Path

from query_doctor.cli.commands import COMMAND_SPECS, command_spec
from query_doctor.engines import EngineAdapter, get_engine_adapter
from query_doctor.engines.capabilities import (
    adapter_flag_capabilities,
    adapter_flags_for_engine,
    cli_role_capabilities,
    cli_roles_for_engine,
    engine_capabilities,
    product_adapter_flags,
    script_paths_for_engine,
    second_engine_cli_roles,
    unsupported_product_capabilities,
)


REPO_DIR = Path(__file__).resolve().parents[1]


def test_capability_manifest_matches_adapter_flags():
    for engine in ("impala", "spark", "trino"):
        adapter = get_engine_adapter(engine)
        manifest_flags = adapter_flags_for_engine(engine)
        true_adapter_flags = {
            field.name
            for field in fields(EngineAdapter)
            if field.name.startswith("supports_") and getattr(adapter, field.name)
        }
        assert true_adapter_flags == manifest_flags
        for capability in adapter_flag_capabilities(engine):
            assert capability.adapter_flag is not None
            assert getattr(adapter, capability.adapter_flag) is True
        for flag in product_adapter_flags():
            assert getattr(adapter, flag) is (engine == "impala")
        for flag in manifest_flags:
            assert getattr(adapter, flag) is True


def test_second_engine_capabilities_do_not_claim_product_surfaces():
    for engine in ("spark", "trino"):
        assert unsupported_product_capabilities(engine) == ()
        assert all(
            not capability.product_surface_allowed for capability in engine_capabilities(engine)
        )
        assert all(
            capability.support_level != "production" for capability in engine_capabilities(engine)
        )


def test_second_engine_cli_roles_are_classified_by_manifest():
    manifest_roles = second_engine_cli_roles()
    command_roles = {
        role
        for role in COMMAND_SPECS
        if "spark" in role
        or role.startswith("trino_")
        or role in {"collect_spark_history", "diagnose_spark_compact", "diagnose_trino_compact"}
    }

    assert command_roles == manifest_roles
    for capability in cli_role_capabilities():
        assert capability.cli_role is not None
        spec = command_spec(capability.cli_role)
        assert spec.console_script.startswith("query-doctor-")
        assert spec.module.startswith("query_doctor.cli.")


def test_spark_cli_roles_stay_bounded_to_manifest():
    assert cli_roles_for_engine("spark") == {
        "build_spark_evidence_package",
        "collect_spark_history",
        "diagnose_spark_compact",
        "export_spark_evidence_fixtures",
        "validate_spark_evidence_package",
    }


def test_trino_cli_roles_stay_bounded_to_manifest():
    assert cli_roles_for_engine("trino") == {
        "diagnose_trino_compact",
        "trino_coordinator_query_info_pruned_import",
        "trino_coordinator_query_info_pruned_probe",
        "trino_coordinator_query_info_target_check",
        "trino_event_source_contract_check",
        "trino_event_store_import",
        "trino_http_event_archive_import",
        "trino_http_query_detail_archive_import",
        "trino_import",
        "trino_metadata_source_contract_check",
        "trino_metadata_summary_import",
        "trino_query_detail_import",
        "trino_query_info_pruned_import",
        "trino_query_list_import",
        "trino_statement_stats_import",
    }


def test_trino_and_spark_scripts_are_classified_by_manifest():
    expected_trino_scripts = {
        path.as_posix()
        for path in (REPO_DIR / "scripts").glob("*trino*.py")
        if path.name != "__init__.py"
    }
    expected_spark_scripts = {
        path.as_posix()
        for path in (REPO_DIR / "scripts").glob("*spark*.py")
        if path.name != "__init__.py"
    }

    assert expected_trino_scripts == {
        (REPO_DIR / script_path).as_posix() for script_path in script_paths_for_engine("trino")
    }
    assert expected_spark_scripts == {
        (REPO_DIR / script_path).as_posix() for script_path in script_paths_for_engine("spark")
    }


def test_manifest_marks_preview_web_routes_as_isolated_not_product():
    route_capabilities = {
        capability.route_path: capability
        for capability in (*engine_capabilities("spark"), *engine_capabilities("trino"))
        if capability.route_path
    }

    assert set(route_capabilities) == {"/spark/compact-diagnosis", "/trino/compact-diagnosis"}
    for capability in route_capabilities.values():
        assert capability.surface_class == "isolated_preview_web"
        assert capability.product_surface_allowed is False
        assert capability.promotion_gate == "isolated_compact_page_only"
