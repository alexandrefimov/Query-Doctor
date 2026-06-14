"""Web surface taxonomy for product, preview, and future owner-raw views."""

from __future__ import annotations

from dataclasses import dataclass


SURFACE_CLASS_ISOLATED_PREVIEW_WEB = "isolated_preview_web"
SURFACE_CLASS_OWNER_RAW_SOURCE_WEB = "isolated_owner_raw_source_web"
TRUSTED_PRODUCT_SURFACES = (
    "recent",
    "details",
    "trusted_report",
    "optimizer",
)


@dataclass(frozen=True)
class WebSurfacePolicy:
    surface_class: str
    product_surface_allowed: bool
    forbidden_product_surfaces: tuple[str, ...] = TRUSTED_PRODUCT_SURFACES
    raw_source_display_allowed: bool = False
    requires_authenticated_viewer: bool = False
    source_allowlist_required: bool = False
    selected_case_only: bool = False
    cache_control: str = "no-store"
    download_allowed: bool = False
    handoff_export_allowed: bool = False
    llm_input_allowed: bool = False


ISOLATED_PREVIEW_WEB_POLICY = WebSurfacePolicy(
    surface_class=SURFACE_CLASS_ISOLATED_PREVIEW_WEB,
    product_surface_allowed=False,
)

OWNER_RAW_SOURCE_WEB_POLICY = WebSurfacePolicy(
    surface_class=SURFACE_CLASS_OWNER_RAW_SOURCE_WEB,
    product_surface_allowed=False,
    raw_source_display_allowed=True,
    requires_authenticated_viewer=True,
    source_allowlist_required=True,
    selected_case_only=True,
)


def policy_allows_raw_source_display(policy: WebSurfacePolicy) -> bool:
    return (
        policy.surface_class == SURFACE_CLASS_OWNER_RAW_SOURCE_WEB
        and policy.raw_source_display_allowed
        and policy.requires_authenticated_viewer
        and policy.source_allowlist_required
        and policy.selected_case_only
        and not policy.product_surface_allowed
        and policy.cache_control == "no-store"
        and not policy.download_allowed
        and not policy.handoff_export_allowed
        and not policy.llm_input_allowed
        and set(policy.forbidden_product_surfaces) >= set(TRUSTED_PRODUCT_SURFACES)
    )
