"""Raw-free owner-raw source authorization policy helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

from query_doctor.source_visibility import SOURCE_VISIBILITY_OWNER_RAW
from query_doctor.web.surface_taxonomy import SURFACE_CLASS_OWNER_RAW_SOURCE_WEB
from query_doctor.web.viewer_identity import (
    VIEWER_IDENTITY_AUTHENTICATED,
    ViewerIdentity,
    unauthenticated_viewer_identity,
    viewer_can_see_raw_query,
)


OWNER_RAW_SOURCE_REASON_ALLOWED = "viewer_matches_query_user"
OWNER_RAW_SOURCE_REASON_ROUTE_CLASS = "route_class_not_owner_raw_source"
OWNER_RAW_SOURCE_REASON_SOURCE_VISIBILITY = "source_visibility_not_owner_raw"
OWNER_RAW_SOURCE_REASON_NONLOCAL_WITHOUT_AUTH = "nonlocal_bind_without_authenticated_viewer"
OWNER_RAW_SOURCE_REASON_DISABLED = "owner_raw_source_disabled"
OWNER_RAW_SOURCE_REASON_OWNER_MISMATCH = "viewer_not_authorized_for_query_user"
OWNER_RAW_SOURCE_LOCAL_BIND_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True)
class OwnerRawSourcePolicyInput:
    source_visibility: str
    owner_raw_source_enabled: bool
    viewer_identity: ViewerIdentity = field(default_factory=unauthenticated_viewer_identity)
    query_user: object | None = None
    route_surface_class: str = SURFACE_CLASS_OWNER_RAW_SOURCE_WEB
    host: str = "127.0.0.1"
    allow_nonlocal_web_bind: bool = False
    authenticated_viewer_configured: bool = False


@dataclass(frozen=True)
class OwnerRawSourcePolicyDecision:
    allowed: bool
    reason_code: str
    route_surface_class: str
    source_visibility: str
    source_switch: str
    viewer_mode: str
    bind_scope: str
    authenticated_viewer_configured: bool

    def raw_free_summary(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "route_surface_class": self.route_surface_class,
            "source_visibility": self.source_visibility,
            "source_switch": self.source_switch,
            "viewer_mode": self.viewer_mode,
            "bind_scope": self.bind_scope,
            "authenticated_viewer_configured": self.authenticated_viewer_configured,
        }


def is_owner_raw_local_bind_host(host: object | None) -> bool:
    return str(host or "").strip().lower() in OWNER_RAW_SOURCE_LOCAL_BIND_HOSTS


def authenticated_viewer_identity_configured_for_policy(
    viewer_identity: ViewerIdentity,
    *,
    viewer_identity_header: object | None = None,
) -> bool:
    if viewer_identity_header:
        return True
    return (
        viewer_identity.mode == VIEWER_IDENTITY_AUTHENTICATED
        and bool(viewer_identity.viewer_user)
        and bool(viewer_identity.viewer_raw_subjects)
    )


def owner_raw_nonlocal_bind_requires_authenticated_viewer(
    *,
    host: object | None,
    allow_nonlocal_web_bind: bool,
    source_visibility_owner_raw: bool,
    authenticated_viewer_configured: bool,
) -> bool:
    return (
        not is_owner_raw_local_bind_host(host)
        and allow_nonlocal_web_bind
        and source_visibility_owner_raw
        and not authenticated_viewer_configured
    )


def decide_owner_raw_source_policy(
    policy_input: OwnerRawSourcePolicyInput,
) -> OwnerRawSourcePolicyDecision:
    reason_code = OWNER_RAW_SOURCE_REASON_ALLOWED
    allowed = True
    if policy_input.route_surface_class != SURFACE_CLASS_OWNER_RAW_SOURCE_WEB:
        allowed = False
        reason_code = OWNER_RAW_SOURCE_REASON_ROUTE_CLASS
    elif policy_input.source_visibility != SOURCE_VISIBILITY_OWNER_RAW:
        allowed = False
        reason_code = OWNER_RAW_SOURCE_REASON_SOURCE_VISIBILITY
    elif owner_raw_nonlocal_bind_requires_authenticated_viewer(
        host=policy_input.host,
        allow_nonlocal_web_bind=policy_input.allow_nonlocal_web_bind,
        source_visibility_owner_raw=True,
        authenticated_viewer_configured=policy_input.authenticated_viewer_configured,
    ):
        allowed = False
        reason_code = OWNER_RAW_SOURCE_REASON_NONLOCAL_WITHOUT_AUTH
    elif not policy_input.owner_raw_source_enabled:
        allowed = False
        reason_code = OWNER_RAW_SOURCE_REASON_DISABLED
    elif not viewer_can_see_raw_query(policy_input.viewer_identity, policy_input.query_user):
        allowed = False
        reason_code = OWNER_RAW_SOURCE_REASON_OWNER_MISMATCH

    return OwnerRawSourcePolicyDecision(
        allowed=allowed,
        reason_code=reason_code,
        route_surface_class=policy_input.route_surface_class,
        source_visibility=policy_input.source_visibility,
        source_switch="enabled" if policy_input.owner_raw_source_enabled else "disabled",
        viewer_mode=policy_viewer_mode(policy_input.viewer_identity),
        bind_scope="local" if is_owner_raw_local_bind_host(policy_input.host) else "nonlocal",
        authenticated_viewer_configured=policy_input.authenticated_viewer_configured,
    )


def policy_viewer_mode(identity: ViewerIdentity) -> str:
    if identity.mode in {"authenticated", "local_first", "unauthenticated"}:
        return identity.mode
    return "unknown"
