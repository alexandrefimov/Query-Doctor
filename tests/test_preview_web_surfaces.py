from pathlib import Path

from query_doctor.engines.capabilities import engine_capabilities
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebSettings
from query_doctor.web.owner_raw_source import (
    OWNER_RAW_SOURCE_SURFACES,
    owner_raw_source_surface_for_get_path,
)
from query_doctor.web.preview_surfaces import (
    PREVIEW_WEB_GET_SURFACES,
    PREVIEW_WEB_POST_PATHS,
    PREVIEW_WEB_POST_SURFACES,
    PREVIEW_WEB_SURFACES,
    preview_surface_for_get_path,
    preview_surface_for_post_path,
)
from query_doctor.web.routes import post_route_is_allowed, route_get_request
from query_doctor.web.surface_taxonomy import (
    ISOLATED_PREVIEW_WEB_POLICY,
    OWNER_RAW_SOURCE_WEB_POLICY,
    SURFACE_CLASS_ISOLATED_PREVIEW_WEB,
    SURFACE_CLASS_OWNER_RAW_SOURCE_WEB,
    TRUSTED_PRODUCT_SURFACES,
    WebSurfacePolicy,
    policy_allows_raw_source_display,
)


def web_settings() -> WebSettings:
    return WebSettings(config=Path(".query-doctor-cm.local.json"))


def test_preview_web_surfaces_match_engine_capability_manifest_routes():
    manifest_routes = {
        capability.route_path: capability
        for capability in (*engine_capabilities("spark"), *engine_capabilities("trino"))
        if capability.route_path
    }
    registry_routes = {surface.route_path: surface for surface in PREVIEW_WEB_SURFACES}

    assert set(registry_routes) == {"/spark/compact-diagnosis", "/trino/compact-diagnosis"}
    assert set(registry_routes) == set(manifest_routes)
    for route_path, surface in registry_routes.items():
        capability = manifest_routes[route_path]
        assert surface.engine == capability.engine
        assert surface.surface_id == capability.surface_id
        assert surface.surface_class == capability.surface_class
        assert surface.product_surface_allowed is capability.product_surface_allowed
        assert capability.product_surface_allowed is False
        assert capability.promotion_gate == "isolated_compact_page_only"


def test_preview_web_route_maps_have_unique_get_and_post_paths():
    expected_get_paths = {path for surface in PREVIEW_WEB_SURFACES for path in surface.get_paths}

    assert set(PREVIEW_WEB_GET_SURFACES) == expected_get_paths
    assert set(PREVIEW_WEB_POST_SURFACES) == {
        surface.route_path for surface in PREVIEW_WEB_SURFACES
    }
    assert PREVIEW_WEB_POST_PATHS == frozenset(PREVIEW_WEB_POST_SURFACES)
    for surface in PREVIEW_WEB_SURFACES:
        assert surface.route_path in surface.get_paths
        assert preview_surface_for_post_path(surface.route_path) is surface
        for path in surface.get_paths:
            assert preview_surface_for_get_path(path) is surface


def test_preview_web_surfaces_stay_out_of_product_workflows():
    for surface in PREVIEW_WEB_SURFACES:
        assert surface.product_surface_allowed is False
        assert surface.surface_class == SURFACE_CLASS_ISOLATED_PREVIEW_WEB
        assert surface.forbidden_product_surfaces == TRUSTED_PRODUCT_SURFACES
        assert surface.forbidden_product_surfaces == (
            ISOLATED_PREVIEW_WEB_POLICY.forbidden_product_surfaces
        )
        assert policy_allows_raw_source_display(ISOLATED_PREVIEW_WEB_POLICY) is False


def test_owner_raw_source_surface_taxonomy_is_isolated_and_stricter_than_product():
    policy = OWNER_RAW_SOURCE_WEB_POLICY

    assert policy.surface_class == SURFACE_CLASS_OWNER_RAW_SOURCE_WEB
    assert policy.product_surface_allowed is False
    assert policy.forbidden_product_surfaces == TRUSTED_PRODUCT_SURFACES
    assert policy.raw_source_display_allowed is True
    assert policy.requires_authenticated_viewer is True
    assert policy.source_allowlist_required is True
    assert policy.selected_case_only is True
    assert policy.cache_control == "no-store"
    assert policy.download_allowed is False
    assert policy.handoff_export_allowed is False
    assert policy.llm_input_allowed is False
    assert policy_allows_raw_source_display(policy) is True


def test_owner_raw_source_routes_are_isolated_get_only_surfaces():
    expected_routes = {
        "/batch/case/<case_id>/source",
        "/running/case/<case_id>/source",
    }

    assert {surface.route_template for surface in OWNER_RAW_SOURCE_SURFACES} == expected_routes
    for surface in OWNER_RAW_SOURCE_SURFACES:
        route = surface.route_template.replace("<case_id>", "case-001")
        assert owner_raw_source_surface_for_get_path(route) is surface
        assert post_route_is_allowed(route) is False
        assert surface.surface_class == SURFACE_CLASS_OWNER_RAW_SOURCE_WEB
        assert surface.product_surface_allowed is False
        assert surface.forbidden_product_surfaces == TRUSTED_PRODUCT_SURFACES


def test_raw_source_display_policy_requires_owner_raw_class_and_all_guards():
    assert (
        policy_allows_raw_source_display(
            WebSurfacePolicy(
                surface_class="details",
                product_surface_allowed=False,
                raw_source_display_allowed=True,
                requires_authenticated_viewer=True,
                source_allowlist_required=True,
                selected_case_only=True,
            )
        )
        is False
    )
    assert (
        policy_allows_raw_source_display(
            WebSurfacePolicy(
                surface_class=SURFACE_CLASS_OWNER_RAW_SOURCE_WEB,
                product_surface_allowed=False,
                raw_source_display_allowed=True,
                requires_authenticated_viewer=True,
                source_allowlist_required=True,
                selected_case_only=True,
                download_allowed=True,
            )
        )
        is False
    )


def test_preview_web_routes_are_allowed_and_render_registered_pages():
    for surface in PREVIEW_WEB_SURFACES:
        assert post_route_is_allowed(surface.route_path)
        assert post_route_is_allowed(f"{surface.route_path}?ignored=1")
        for path in surface.get_paths:
            response = route_get_request(path, web_settings(), WebJobStore())
            assert response is not None
            assert response.status == 200
            assert f'action="{surface.route_path}"' in response.body
