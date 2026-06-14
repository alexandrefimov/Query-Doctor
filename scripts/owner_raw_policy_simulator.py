#!/usr/bin/env python3
"""Simulate owner-raw source policy decisions over raw-free inputs."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.source_visibility import (  # noqa: E402
    SOURCE_VISIBILITY_CHOICES,
    normalize_source_visibility,
)
from query_doctor.web.owner_raw_policy import (  # noqa: E402
    OwnerRawSourcePolicyInput,
    decide_owner_raw_source_policy,
)
from query_doctor.web.surface_taxonomy import SURFACE_CLASS_OWNER_RAW_SOURCE_WEB  # noqa: E402
from query_doctor.web.viewer_identity import (  # noqa: E402
    VIEWER_IDENTITY_AUTHENTICATED,
    VIEWER_IDENTITY_LOCAL_FIRST,
    VIEWER_IDENTITY_UNAUTHENTICATED,
    authenticated_viewer_identity,
    authenticated_viewer_identity_from_header_value,
    local_first_viewer_identity,
    unauthenticated_viewer_identity,
)


SIMULATION_KIND = "owner_raw_source_policy_simulation_v1"
VIEWER_MODE_CHOICES = (
    VIEWER_IDENTITY_UNAUTHENTICATED,
    VIEWER_IDENTITY_LOCAL_FIRST,
    VIEWER_IDENTITY_AUTHENTICATED,
)


class PolicySimulatorInputError(RuntimeError):
    """Raised when sanitized policy inputs cannot form a valid simulation."""


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the owner-raw source allow/deny matrix without reading cases, SQL, "
            "profiles, headers, credentials, or local artifacts. Output is raw-free JSON."
        )
    )
    parser.add_argument(
        "--source-visibility",
        choices=SOURCE_VISIBILITY_CHOICES,
        default="safe",
        help="Source visibility policy to simulate.",
    )
    parser.add_argument(
        "--owner-raw-source-disabled",
        action="store_false",
        dest="owner_raw_source_enabled",
        help="Simulate owner_raw_source_enabled=false.",
    )
    parser.set_defaults(owner_raw_source_enabled=True)
    parser.add_argument("--host", default="127.0.0.1", help="Sanitized bind host shape.")
    parser.add_argument(
        "--allow-nonlocal-web-bind",
        action="store_true",
        help="Simulate an explicitly reviewed non-local bind.",
    )
    parser.add_argument(
        "--viewer-identity-header-configured",
        action="store_true",
        help="Simulate D3 trusted viewer header configuration.",
    )
    parser.add_argument(
        "--viewer-header-value",
        default=None,
        help=(
            "Optional sanitized request header value to normalize through the D3 header path. "
            "The value is never echoed in output."
        ),
    )
    parser.add_argument(
        "--viewer-mode",
        choices=VIEWER_MODE_CHOICES,
        default=VIEWER_IDENTITY_UNAUTHENTICATED,
        help="Viewer identity mode used when no trusted header is configured.",
    )
    parser.add_argument(
        "--viewer-user",
        default="",
        help="Sanitized viewer user used for authenticated/local-first simulation.",
    )
    parser.add_argument(
        "--viewer-raw-subject",
        action="append",
        default=[],
        help=(
            "Sanitized owner subject visible to the viewer. Repeat for local/delegated "
            "simulations. Values are never echoed in output."
        ),
    )
    parser.add_argument(
        "--query-user",
        default="",
        help="Sanitized selected-case query user. The value is never echoed in output.",
    )
    parser.add_argument(
        "--route-class",
        default=SURFACE_CLASS_OWNER_RAW_SOURCE_WEB,
        help="Route surface class to test.",
    )
    parser.add_argument(
        "--fail-on-deny",
        action="store_true",
        help="Return exit code 1 when the simulated policy denies access.",
    )
    return parser.parse_args(argv)


def build_viewer_identity(args: argparse.Namespace):
    if args.viewer_identity_header_configured:
        return authenticated_viewer_identity_from_header_value(args.viewer_header_value)
    if args.viewer_mode == VIEWER_IDENTITY_UNAUTHENTICATED:
        return unauthenticated_viewer_identity()
    if args.viewer_mode == VIEWER_IDENTITY_LOCAL_FIRST:
        subjects = tuple(args.viewer_raw_subject) or (
            (args.viewer_user,) if args.viewer_user else ()
        )
        return local_first_viewer_identity(subjects)
    if args.viewer_mode == VIEWER_IDENTITY_AUTHENTICATED:
        if not args.viewer_user:
            raise PolicySimulatorInputError(
                "authenticated viewer simulation requires --viewer-user"
            )
        try:
            return authenticated_viewer_identity(
                args.viewer_user,
                delegated_raw_subjects=tuple(args.viewer_raw_subject),
            )
        except ValueError as exc:
            raise PolicySimulatorInputError(
                "invalid authenticated viewer simulation input"
            ) from exc
    raise PolicySimulatorInputError("unknown viewer identity mode")


def simulation_payload(args: argparse.Namespace) -> dict[str, object]:
    try:
        source_visibility = normalize_source_visibility(args.source_visibility)
    except ValueError as exc:
        raise PolicySimulatorInputError("invalid source visibility") from exc
    viewer_identity = build_viewer_identity(args)
    authenticated_viewer_configured = bool(args.viewer_identity_header_configured) or (
        viewer_identity.mode == VIEWER_IDENTITY_AUTHENTICATED
        and bool(viewer_identity.viewer_user)
        and bool(viewer_identity.viewer_raw_subjects)
    )
    decision = decide_owner_raw_source_policy(
        OwnerRawSourcePolicyInput(
            source_visibility=source_visibility,
            owner_raw_source_enabled=bool(args.owner_raw_source_enabled),
            viewer_identity=viewer_identity,
            query_user=args.query_user or None,
            route_surface_class=args.route_class,
            host=args.host,
            allow_nonlocal_web_bind=bool(args.allow_nonlocal_web_bind),
            authenticated_viewer_configured=authenticated_viewer_configured,
        )
    )
    return {
        "kind": SIMULATION_KIND,
        "decision": decision.raw_free_summary(),
        "input_shape": {
            "query_user_provided": bool(args.query_user),
            "viewer_header_configured": bool(args.viewer_identity_header_configured),
            "viewer_header_value_provided": args.viewer_header_value is not None,
            "viewer_raw_subject_count": len(tuple(args.viewer_raw_subject)),
        },
    }


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = simulation_payload(args)
    except PolicySimulatorInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
    decision = payload["decision"]
    denied = isinstance(decision, dict) and not decision.get("allowed")
    return 1 if args.fail_on_deny and denied else 0


if __name__ == "__main__":
    raise SystemExit(main())
