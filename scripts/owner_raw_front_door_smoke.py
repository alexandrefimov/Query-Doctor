#!/usr/bin/env python3
"""Dev-only smoke for the owner_raw D3 front-door header contract."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.source_visibility import SOURCE_VISIBILITY_OWNER_RAW  # noqa: E402
from query_doctor.web.app import settings_for_request_headers  # noqa: E402
from query_doctor.web.models import WebSettings  # noqa: E402
from query_doctor.web.owner_raw_policy import (  # noqa: E402
    OWNER_RAW_SOURCE_REASON_ALLOWED,
    OWNER_RAW_SOURCE_REASON_OWNER_MISMATCH,
    OwnerRawSourcePolicyInput,
    decide_owner_raw_source_policy,
)
from query_doctor.web.viewer_identity import normalize_header_viewer_user  # noqa: E402


SMOKE_KIND = "owner_raw_front_door_smoke_v1"
VIEWER_HEADER_NAME = "X-Query-Doctor-Viewer"
SYNTHETIC_QUERY_USER = "analyst_one"
SYNTHETIC_OTHER_USER = "other_owner"


class HeaderBag:
    def __init__(self, values: dict[str, tuple[str, ...]]):
        self.values = values

    def get(self, name: str) -> str | None:
        values = self.values.get(name)
        if not values:
            return None
        return values[0]

    def get_all(self, name: str) -> tuple[str, ...] | None:
        return self.values.get(name)


@dataclass(frozen=True)
class FrontDoorScenario:
    name: str
    subject_kind: str
    authenticated_subject: str | None
    inbound_viewer_header_values: tuple[str, ...] = ()
    query_user: str = SYNTHETIC_QUERY_USER
    duplicate_upstream_header: bool = False
    expected_allowed: bool = False
    expected_reason_code: str = OWNER_RAW_SOURCE_REASON_OWNER_MISMATCH
    expected_upstream_header_count: int = 0


def _kerberos_human_primary(principal: str) -> str | None:
    text = principal.strip()
    if not text or "/" in text:
        return None
    primary = text.split("@", 1)[0].strip()
    return normalize_header_viewer_user(primary)


def _front_door_owner_value(scenario: FrontDoorScenario) -> str | None:
    subject = scenario.authenticated_subject
    if not subject:
        return None
    if scenario.subject_kind == "simple_owner_claim":
        return normalize_header_viewer_user(subject)
    if scenario.subject_kind == "kerberos_principal":
        return _kerberos_human_primary(subject)
    raise ValueError(f"unknown front-door subject kind: {scenario.subject_kind}")


def _upstream_headers(scenario: FrontDoorScenario) -> HeaderBag:
    viewer = _front_door_owner_value(scenario)
    values: tuple[str, ...] = ()
    if viewer and scenario.duplicate_upstream_header:
        values = (viewer, viewer)
    elif viewer:
        values = (viewer,)
    if not values:
        return HeaderBag({})
    return HeaderBag({VIEWER_HEADER_NAME: values})


def _decision_for_scenario(scenario: FrontDoorScenario):
    settings = WebSettings(
        config=Path("owner-raw-front-door-smoke.json"),
        source_visibility=SOURCE_VISIBILITY_OWNER_RAW,
        viewer_identity_header=VIEWER_HEADER_NAME,
        owner_raw_source_enabled=True,
    )
    resolved = settings_for_request_headers(settings, _upstream_headers(scenario))
    return decide_owner_raw_source_policy(
        OwnerRawSourcePolicyInput(
            source_visibility=SOURCE_VISIBILITY_OWNER_RAW,
            owner_raw_source_enabled=True,
            viewer_identity=resolved.viewer_identity,
            query_user=scenario.query_user,
            host="0.0.0.0",
            allow_nonlocal_web_bind=True,
            authenticated_viewer_configured=True,
        )
    )


def scenario_matrix() -> tuple[FrontDoorScenario, ...]:
    return (
        FrontDoorScenario(
            name="matching_header_strips_inbound_spoof",
            subject_kind="simple_owner_claim",
            authenticated_subject=SYNTHETIC_QUERY_USER,
            inbound_viewer_header_values=("spoofed_owner", SYNTHETIC_OTHER_USER),
            expected_allowed=True,
            expected_reason_code=OWNER_RAW_SOURCE_REASON_ALLOWED,
            expected_upstream_header_count=1,
        ),
        FrontDoorScenario(
            name="kerberos_primary_maps_to_simple_owner",
            subject_kind="kerberos_principal",
            authenticated_subject=f"{SYNTHETIC_QUERY_USER}@EXAMPLE.REALM",
            expected_allowed=True,
            expected_reason_code=OWNER_RAW_SOURCE_REASON_ALLOWED,
            expected_upstream_header_count=1,
        ),
        FrontDoorScenario(
            name="missing_front_door_subject_denies",
            subject_kind="simple_owner_claim",
            authenticated_subject=None,
            expected_upstream_header_count=0,
        ),
        FrontDoorScenario(
            name="mismatched_front_door_subject_denies",
            subject_kind="simple_owner_claim",
            authenticated_subject=SYNTHETIC_OTHER_USER,
            expected_upstream_header_count=1,
        ),
        FrontDoorScenario(
            name="service_principal_rejected_by_front_door",
            subject_kind="kerberos_principal",
            authenticated_subject="impala/host.example.invalid@EXAMPLE.REALM",
            expected_upstream_header_count=0,
        ),
        FrontDoorScenario(
            name="duplicate_upstream_header_denies",
            subject_kind="simple_owner_claim",
            authenticated_subject=SYNTHETIC_QUERY_USER,
            duplicate_upstream_header=True,
            expected_upstream_header_count=2,
        ),
    )


def evaluate_scenario(scenario: FrontDoorScenario) -> dict[str, object]:
    decision = _decision_for_scenario(scenario)
    upstream = _upstream_headers(scenario)
    upstream_count = len(upstream.get_all(VIEWER_HEADER_NAME) or ())
    passed = (
        decision.allowed == scenario.expected_allowed
        and decision.reason_code == scenario.expected_reason_code
        and upstream_count == scenario.expected_upstream_header_count
    )
    return {
        "name": scenario.name,
        "passed": passed,
        "front_door": {
            "authenticated_subject_provided": scenario.authenticated_subject is not None,
            "inbound_viewer_header_count": len(scenario.inbound_viewer_header_values),
            "inbound_viewer_header_stripped": bool(scenario.inbound_viewer_header_values),
            "mapped_subject_to_owner": _front_door_owner_value(scenario) is not None,
            "upstream_viewer_header_count": upstream_count,
        },
        "decision": decision.raw_free_summary(),
        "expected": {
            "allowed": scenario.expected_allowed,
            "reason_code": scenario.expected_reason_code,
            "upstream_viewer_header_count": scenario.expected_upstream_header_count,
        },
    }


def smoke_payload() -> dict[str, object]:
    scenarios = [evaluate_scenario(scenario) for scenario in scenario_matrix()]
    return {
        "kind": SMOKE_KIND,
        "all_passed": all(bool(scenario["passed"]) for scenario in scenarios),
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a synthetic, raw-free owner_raw D3 front-door smoke matrix. "
            "The smoke does not contact an IdP, proxy, Kerberos service, LDAP, "
            "or Query Doctor server."
        )
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print compact JSON instead of indented JSON.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    payload = smoke_payload()
    print(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":") if args.compact else None,
            indent=None if args.compact else 2,
        )
    )
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
