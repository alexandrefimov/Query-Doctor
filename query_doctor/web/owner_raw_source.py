"""Owner-gated raw SQL source surface for selected Recent cases."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

from query_doctor.optimizer.source_sql import (
    QueryOptimizationError,
    extract_optimizable_source_sql,
    read_source_sql,
)
from query_doctor.optimizer.sql import OptimizerSqlError
from query_doctor.safety.browser_display import (
    redact_credentials_for_display,
    redact_local_paths_for_display,
)
from query_doctor.source_visibility import SOURCE_VISIBILITY_OWNER_RAW
from query_doctor.web.audit import WebAuditEvent
from query_doctor.web.models import WebSettings
from query_doctor.web.presenters.recent_scan import present_source_locators
from query_doctor.web.surface_taxonomy import (
    OWNER_RAW_SOURCE_WEB_POLICY,
    SURFACE_CLASS_OWNER_RAW_SOURCE_WEB,
)
from query_doctor.web.viewer_identity import viewer_can_see_raw_query


OWNER_RAW_SOURCE_GET_RE = re.compile(r"/(?P<source>batch|running)/case/(?P<case_id>[^/]+)/source")
OWNER_RAW_SOURCE_REASON_ALLOWED = "viewer_matches_query_user"
OWNER_RAW_SOURCE_REASON_CASE_NOT_FOUND = "case_not_found"
OWNER_RAW_SOURCE_REASON_SOURCE_VISIBILITY = "source_visibility_not_owner_raw"
OWNER_RAW_SOURCE_REASON_DISABLED = "owner_raw_source_disabled"
OWNER_RAW_SOURCE_REASON_OWNER_MISMATCH = "viewer_not_authorized_for_query_user"
OWNER_RAW_SOURCE_REASON_SOURCE_UNAVAILABLE = "source_unavailable"
OWNER_RAW_SOURCE_REASON_UNSUPPORTED_SCOPE = "unsupported_source_scope"


@dataclass(frozen=True)
class OwnerRawSourceWebSurface:
    route_template: str
    surface_class: str = SURFACE_CLASS_OWNER_RAW_SOURCE_WEB
    product_surface_allowed: bool = False
    forbidden_product_surfaces: tuple[str, ...] = (
        OWNER_RAW_SOURCE_WEB_POLICY.forbidden_product_surfaces
    )


@dataclass(frozen=True)
class OwnerRawSourceHighlight:
    start_line: int
    end_line: int
    label: str
    detail: str = ""


@dataclass(frozen=True)
class OwnerRawSourceDecision:
    allowed: bool
    reason_code: str
    source_sql: str = ""
    source_scope: str = ""
    highlights: tuple[OwnerRawSourceHighlight, ...] = ()


@dataclass(frozen=True)
class OwnerRawSourceView:
    case_id: str
    query_id: object
    query_user: object
    source_sql: str
    source_scope: str
    reason_code: str
    highlights: tuple[OwnerRawSourceHighlight, ...]
    back_href: str


OWNER_RAW_SOURCE_SURFACES = (
    OwnerRawSourceWebSurface("/batch/case/<case_id>/source"),
    OwnerRawSourceWebSurface("/running/case/<case_id>/source"),
)


def owner_raw_source_surface_for_get_path(path: str) -> OwnerRawSourceWebSurface | None:
    match = OWNER_RAW_SOURCE_GET_RE.fullmatch(path)
    if not match:
        return None
    prefix = match.group("source")
    route_template = f"/{prefix}/case/<case_id>/source"
    for surface in OWNER_RAW_SOURCE_SURFACES:
        if surface.route_template == route_template:
            return surface
    return None


def owner_raw_source_path_match(path: str) -> re.Match[str] | None:
    return OWNER_RAW_SOURCE_GET_RE.fullmatch(path)


def owner_raw_source_href(case_id: str, *, detail_base_path: str) -> str:
    safe_case_id = quote(case_id, safe="")
    return f"{detail_base_path.rstrip('/')}/{safe_case_id}/source"


def owner_raw_source_detail_href(case_id: str, *, detail_base_path: str) -> str:
    safe_case_id = quote(case_id, safe="")
    return f"{detail_base_path.rstrip('/')}/{safe_case_id}"


def owner_raw_source_href_for_case(
    settings: WebSettings,
    case_id: str,
    case: dict[str, object],
    case_dir: Path | None,
    *,
    detail_base_path: str,
) -> str:
    decision = decide_owner_raw_source_access(settings, case, case_dir)
    if not decision.allowed:
        return ""
    return owner_raw_source_href(case_id, detail_base_path=detail_base_path)


def build_owner_raw_source_view(
    settings: WebSettings,
    case_id: str,
    case: dict[str, object],
    case_dir: Path | None,
    *,
    back_href: str,
) -> OwnerRawSourceView | OwnerRawSourceDecision:
    decision = decide_owner_raw_source_access(settings, case, case_dir)
    if not decision.allowed:
        return decision
    return OwnerRawSourceView(
        case_id=case_id,
        query_id=case.get("query_id") or "",
        query_user=case.get("user") or "",
        source_sql=decision.source_sql,
        source_scope=decision.source_scope,
        reason_code=decision.reason_code,
        highlights=decision.highlights,
        back_href=back_href,
    )


def decide_owner_raw_source_access(
    settings: WebSettings,
    case: dict[str, object],
    case_dir: Path | None,
) -> OwnerRawSourceDecision:
    if settings.source_visibility != SOURCE_VISIBILITY_OWNER_RAW:
        return OwnerRawSourceDecision(False, OWNER_RAW_SOURCE_REASON_SOURCE_VISIBILITY)
    if not settings.owner_raw_source_enabled:
        return OwnerRawSourceDecision(False, OWNER_RAW_SOURCE_REASON_DISABLED)
    if not viewer_can_see_raw_query(settings.viewer_identity, case.get("user")):
        return OwnerRawSourceDecision(False, OWNER_RAW_SOURCE_REASON_OWNER_MISMATCH)
    if case_dir is None:
        return OwnerRawSourceDecision(False, OWNER_RAW_SOURCE_REASON_SOURCE_UNAVAILABLE)
    try:
        source = extract_optimizable_source_sql(read_source_sql(case_dir))
    except (OSError, OptimizerSqlError, QueryOptimizationError, ValueError):
        return OwnerRawSourceDecision(False, OWNER_RAW_SOURCE_REASON_SOURCE_UNAVAILABLE)
    if source.scope != "read_only_statement":
        return OwnerRawSourceDecision(False, OWNER_RAW_SOURCE_REASON_UNSUPPORTED_SCOPE)
    safe_source_sql = redact_owner_raw_source_sql(source.sql)
    return OwnerRawSourceDecision(
        True,
        OWNER_RAW_SOURCE_REASON_ALLOWED,
        source_sql=safe_source_sql,
        source_scope=source.scope,
        highlights=owner_raw_source_highlights(case),
    )


def redact_owner_raw_source_sql(sql: str) -> str:
    safe = redact_credentials_for_display(sql)
    return redact_local_paths_for_display(safe)


def owner_raw_source_audit_event(
    settings: WebSettings,
    decision: OwnerRawSourceDecision,
    *,
    route_source: str,
    status: int,
) -> WebAuditEvent:
    return WebAuditEvent(
        name="owner_raw_source_access",
        fields=(
            ("surface", "owner_raw_source"),
            ("route_source", owner_raw_source_audit_route_source(route_source)),
            ("status", str(status)),
            ("allowed", "true" if decision.allowed else "false"),
            ("reason", decision.reason_code),
            ("source_visibility", settings.source_visibility),
            (
                "source_switch",
                "enabled" if settings.owner_raw_source_enabled else "disabled",
            ),
            ("viewer_mode", owner_raw_source_audit_viewer_mode(settings)),
            ("viewer_identity_source", owner_raw_source_audit_viewer_identity_source(settings)),
        ),
    )


def owner_raw_source_audit_route_source(value: str) -> str:
    return value if value in {"batch", "running"} else "unknown"


def owner_raw_source_audit_viewer_mode(settings: WebSettings) -> str:
    mode = settings.viewer_identity.mode
    return mode if mode in {"authenticated", "local_first", "unauthenticated"} else "unknown"


def owner_raw_source_audit_viewer_identity_source(settings: WebSettings) -> str:
    if settings.viewer_identity_header:
        return "header"
    mode = owner_raw_source_audit_viewer_mode(settings)
    return mode if mode != "unauthenticated" else "none"


def owner_raw_source_highlights(
    case: dict[str, object],
) -> tuple[OwnerRawSourceHighlight, ...]:
    locators_by_group = present_source_locators(case.get("source_locators"))
    highlights: list[OwnerRawSourceHighlight] = []
    seen: set[tuple[int, int, str, str]] = set()
    for locators in locators_by_group.values():
        for locator in locators:
            if locator.kind != "sql" or not locator.coordinate:
                continue
            line_range = line_range_from_coordinate(locator.coordinate)
            if line_range is None:
                continue
            start_line, end_line = line_range
            key = (start_line, end_line, locator.label, locator.detail)
            if key in seen:
                continue
            seen.add(key)
            highlights.append(
                OwnerRawSourceHighlight(
                    start_line=start_line,
                    end_line=end_line,
                    label=locator.label,
                    detail=locator.detail,
                )
            )
    return tuple(highlights[:8])


def line_range_from_coordinate(coordinate: str) -> tuple[int, int] | None:
    line_match = re.fullmatch(r"line ([1-9]\d{0,5})", coordinate)
    if line_match:
        line = int(line_match.group(1))
        return line, line
    range_match = re.fullmatch(r"lines ([1-9]\d{0,5})-([1-9]\d{0,5})", coordinate)
    if not range_match:
        return None
    start = int(range_match.group(1))
    end = int(range_match.group(2))
    if start > end:
        return None
    return start, end


def unquote_case_id(value: str) -> str:
    return unquote(value)
