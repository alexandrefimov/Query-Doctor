"""Registered isolated preview web surfaces for non-production engines."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from query_doctor.web.models import WebSettings
from query_doctor.web.surface_taxonomy import (
    ISOLATED_PREVIEW_WEB_POLICY,
    SURFACE_CLASS_ISOLATED_PREVIEW_WEB,
)
from query_doctor.web.spark_compact import handle_spark_compact_request
from query_doctor.web.trino_compact import handle_trino_compact_request
from query_doctor.web.ui.spark import render_spark_compact_page
from query_doctor.web.ui.trino import render_trino_compact_page


PreviewRenderer = Callable[[WebSettings], str]
PreviewPostHandler = Callable[[dict[str, list[str]], WebSettings], tuple[int, str]]


@dataclass(frozen=True)
class PreviewWebSurface:
    engine: str
    surface_id: str
    route_path: str
    get_paths: tuple[str, ...]
    render_get: PreviewRenderer
    handle_post: PreviewPostHandler
    surface_class: str = SURFACE_CLASS_ISOLATED_PREVIEW_WEB
    product_surface_allowed: bool = False
    forbidden_product_surfaces: tuple[str, ...] = (
        ISOLATED_PREVIEW_WEB_POLICY.forbidden_product_surfaces
    )


PREVIEW_WEB_SURFACES: tuple[PreviewWebSurface, ...] = (
    PreviewWebSurface(
        engine="spark",
        surface_id="compact_diagnosis",
        route_path="/spark/compact-diagnosis",
        get_paths=("/spark", "/spark/compact-diagnosis"),
        render_get=render_spark_compact_page,
        handle_post=handle_spark_compact_request,
    ),
    PreviewWebSurface(
        engine="trino",
        surface_id="compact_diagnosis",
        route_path="/trino/compact-diagnosis",
        get_paths=("/trino", "/trino/compact-diagnosis"),
        render_get=render_trino_compact_page,
        handle_post=handle_trino_compact_request,
    ),
)


def _build_get_surface_map() -> Mapping[str, PreviewWebSurface]:
    surfaces: dict[str, PreviewWebSurface] = {}
    for surface in PREVIEW_WEB_SURFACES:
        if surface.route_path not in surface.get_paths:
            raise ValueError(f"{surface.engine} preview route is missing from GET paths")
        for path in surface.get_paths:
            if path in surfaces:
                raise ValueError(f"duplicate preview GET path: {path}")
            surfaces[path] = surface
    return MappingProxyType(surfaces)


def _build_post_surface_map() -> Mapping[str, PreviewWebSurface]:
    surfaces: dict[str, PreviewWebSurface] = {}
    for surface in PREVIEW_WEB_SURFACES:
        if surface.route_path in surfaces:
            raise ValueError(f"duplicate preview POST path: {surface.route_path}")
        surfaces[surface.route_path] = surface
    return MappingProxyType(surfaces)


PREVIEW_WEB_GET_SURFACES = _build_get_surface_map()
PREVIEW_WEB_POST_SURFACES = _build_post_surface_map()
PREVIEW_WEB_POST_PATHS = frozenset(PREVIEW_WEB_POST_SURFACES)


def preview_surface_for_get_path(path: str) -> PreviewWebSurface | None:
    return PREVIEW_WEB_GET_SURFACES.get(path)


def preview_surface_for_post_path(path: str) -> PreviewWebSurface | None:
    return PREVIEW_WEB_POST_SURFACES.get(path)
