#!/usr/bin/env python3
"""Audit Trino shared deployment boundaries without exposing deployment inputs."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.config.contract import ConfigError, load_and_validate_config  # noqa: E402
from query_doctor.engines.capabilities import engine_capabilities  # noqa: E402
from query_doctor.safety.handoff_artifacts import write_ascii_json_artifact  # noqa: E402
from query_doctor.source_visibility import SOURCE_VISIBILITY_OWNER_RAW  # noqa: E402
from query_doctor.trino.support_mode import (  # noqa: E402
    TRINO_SUPPORT_MODE_BETA,
    TRINO_SUPPORT_MODE_OFF,
    TRINO_SUPPORT_MODE_PRODUCTION,
    trino_support_mode_enabled,
)
from query_doctor.web.cluster_selection import build_web_cluster_configs  # noqa: E402
from query_doctor.web.models import DEFAULT_HOST, WebClusterConfig  # noqa: E402
from query_doctor.web.owner_raw_policy import is_owner_raw_local_bind_host  # noqa: E402
from query_doctor.web.viewer_identity import normalize_viewer_identity_header  # noqa: E402
from scripts import audit_trino_beta_release_readiness  # noqa: E402
from scripts import audit_trino_product_surface_boundary  # noqa: E402


TRINO_SHARED_DEPLOYMENT_AUDIT_SUMMARY_KIND = "trino_shared_deployment_boundary_audit_v1"
EXPECTED_TRINO_PRODUCT_SURFACES = frozenset(
    {
        "recent_scan",
        "query_id_mode",
        "materialized_details",
        "materialized_python_report",
        "materialized_optimizer_guidance",
    }
)
UNSUPPORTED_TRINO_SHARED_SURFACES = (
    "running_scan",
    "query_history_crawling",
    "product_metadata_collection",
    "llm_reports",
    "query_optimizer_jobs",
    "generated_trino_sql",
    "sql_execution",
)
EXPECTED_UNSUPPORTED_TRINO_SHARED_SURFACES = frozenset(
    {
        "running_scan",
        "query_history_crawling",
        "product_metadata_collection",
        "llm_reports",
        "query_optimizer_jobs",
        "generated_trino_sql",
        "sql_execution",
    }
)
TRINO_SHARED_DEPLOYMENT_CONFIG_REQUIREMENTS = (
    "config_source_inventory",
    "trusted_front_door_review",
    "trusted_viewer_identity",
    "raw_source_reveal_blocked",
)
TRINO_SHARED_DEPLOYMENT_PRODUCT_BOUNDARY_REQUIREMENTS = (
    "details",
    "python_report",
    "optimizer_guidance",
    "optimizer_behavior",
    "llm_reports",
    "unsupported_surfaces_blocked",
)
TRINO_SHARED_DEPLOYMENT_CAPABILITY_REQUIREMENTS = (
    "product_capability_surface_set",
    "product_capability_classification",
    "product_capability_raw_policy",
    "dev_gate_classification",
)
TRINO_SHARED_DEPLOYMENT_RELEASE_REQUIREMENTS = ("release_bundle_shared_deployment_gate",)
TRINO_SHARED_DEPLOYMENT_PRODUCTION_REVIEW_PROFILE = "production_review_shared_deployment_v1"
TRINO_SHARED_DEPLOYMENT_PRODUCTION_REVIEW_PROFILE_STATUS = "ready"
TRINO_SHARED_DEPLOYMENT_DOC_REQUIREMENT_IDS = {
    "trino-shared-deployment-hardening.md": "trino_shared_deployment_hardening_doc",
    "trino-beta-ui-readiness.md": "trino_beta_ui_readiness_doc",
    "public-release-readiness.md": "public_release_readiness_doc",
    "release-checklist.md": "release_checklist_doc",
}
TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_FAMILIES = (
    "deployment_boundary",
    "product_boundary",
    "capability_manifest",
    "release_bundle",
    "shared_deployment_docs",
)
TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_CONFIG_REQUIREMENTS = (
    TRINO_SHARED_DEPLOYMENT_CONFIG_REQUIREMENTS
)
TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_PRODUCT_BOUNDARY_REQUIREMENTS = (
    TRINO_SHARED_DEPLOYMENT_PRODUCT_BOUNDARY_REQUIREMENTS
)
TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_CAPABILITY_REQUIREMENTS = (
    TRINO_SHARED_DEPLOYMENT_CAPABILITY_REQUIREMENTS
)
TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_RELEASE_REQUIREMENTS = (
    TRINO_SHARED_DEPLOYMENT_RELEASE_REQUIREMENTS
)
TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_DOC_REQUIREMENTS = tuple(
    TRINO_SHARED_DEPLOYMENT_DOC_REQUIREMENT_IDS.values()
)
TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_UNSUPPORTED_SURFACES = UNSUPPORTED_TRINO_SHARED_SURFACES
TRINO_SHARED_DEPLOYMENT_DOC_REQUIREMENTS: tuple[tuple[Path, tuple[str, ...]], ...] = (
    (
        ROOT / "docs" / "trino-shared-deployment-hardening.md",
        (
            "deployment hardening contract, not a support claim",
            "`trino_support_mode=production` remains local production support only",
            "trusted front-door viewer identity",
            "`viewer_identity_header`",
            "`--trusted-front-door-reviewed`",
            "strips inbound copies",
            "`source_visibility=safe`",
            "`owner_raw_source_enabled=false`",
            "raw source reveal",
            "raw-free materialized Details, deterministic Python Report, and optimizer guidance",
            "metadata CLI summary smoke",
            "dev-only",
            "not product metadata collection",
            "Running",
            "query-history crawling",
            "LLM reports",
            "Query Optimizer jobs",
            "generated SQL",
            "SQL execution",
            "python3 scripts/audit_trino_shared_deployment_preflight.py",
            "python3 scripts/audit_trino_shared_deployment_boundary.py",
            "python3 scripts/audit_trino_beta_release_readiness.py",
        ),
    ),
    (
        ROOT / "docs" / "trino-beta-ui-readiness.md",
        (
            "trino-shared-deployment-hardening.md",
            "trusted front-door viewer identity",
            "raw-source reveal to stay isolated and disabled",
            "--trusted-front-door-reviewed",
            "does not make shared Trino production support available",
        ),
    ),
    (
        ROOT / "docs" / "public-release-readiness.md",
        (
            "trino-shared-deployment-hardening.md",
            "trusted front-door viewer identity",
            "raw-source isolation",
            "--trusted-front-door-reviewed",
            "does not add broader/shared Trino production support",
        ),
    ),
    (
        ROOT / "docs" / "release-checklist.md",
        (
            "trino-shared-deployment-hardening.md",
            "trusted front-door viewer identity",
            "raw-source isolation",
            "--trusted-front-door-reviewed",
            "does not add broader/shared Trino production support",
        ),
    ),
)


class TrinoSharedDeploymentAuditInputError(RuntimeError):
    """Raised when deployment inputs cannot be audited without exposing them."""


@dataclass(frozen=True)
class TrinoSharedDeploymentAuditIssue:
    category: str
    message: str
    requirement_type: str | None = None
    requirement_id: str | None = None


@dataclass(frozen=True)
class TrinoSharedDeploymentRequirementTracking:
    family_id: str
    requirement_type: str
    requirement_id: str
    tracking_status: str
    issue_count: int


@dataclass(frozen=True)
class TrinoSharedDeploymentProductionReviewTracking:
    requirement_id: str
    counter_name: str
    tracking_status: str
    observed_count: int
    required_count: int


@dataclass(frozen=True)
class TrinoDeploymentSource:
    trino_enabled: bool
    trino_support_mode: str
    source_visibility: str
    shared_bind: bool
    viewer_identity_header_configured: bool
    owner_raw_source_enabled: bool


@dataclass
class TrinoSharedDeploymentAuditResult:
    config_checked: bool = False
    trusted_front_door_reviewed: bool = False
    config_source_count: int = 0
    trino_source_count: int = 0
    shared_trino_source_count: int = 0
    shared_owner_raw_source_count: int = 0
    shared_deployment_doc_checked_count: int = 0
    static_check_count: int = 0
    product_capability_count: int = 0
    shared_deployment_requirement_tracking_counts: Counter[str] = field(default_factory=Counter)
    production_review_tracking_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    shared_deployment_requirement_tracking: list[TrinoSharedDeploymentRequirementTracking] = field(
        default_factory=list
    )
    production_review_tracking: list[TrinoSharedDeploymentProductionReviewTracking] = field(
        default_factory=list
    )
    issues: list[tuple[int | None, TrinoSharedDeploymentAuditIssue]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issue_counts


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a dev-only static Trino shared-deployment boundary audit. The audit "
            "checks local config shape when --config is supplied and verifies that "
            "shared/non-local Trino deployment remains separated from owner-raw source "
            "reveal, product metadata collection, LLM reports, Query Optimizer jobs, "
            "generated SQL, SQL execution, Running scans, and query-history crawling. "
            "Output is raw-free and never prints config paths, header names, users, "
            "Query IDs, coordinator URLs, auth references, source-contract paths, or "
            "raw payloads."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional ignored local Query Doctor web config. The path is never printed.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Optional raw-free machine summary JSON. The path is never printed.",
    )
    parser.add_argument(
        "--trusted-front-door-reviewed",
        action="store_true",
        help=(
            "Confirm the shared/non-local deployment is behind a trusted auth front "
            "door that strips inbound viewer headers and sets exactly one normalized "
            "simple viewer identity per request. The confirmation value is raw-free."
        ),
    )
    parser.add_argument("--limit", type=positive_int, default=12, help="Maximum issues to print.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    result = TrinoSharedDeploymentAuditResult(
        config_checked=args.config is not None,
        trusted_front_door_reviewed=args.trusted_front_door_reviewed,
    )
    try:
        if args.config is not None:
            audit_config(
                result,
                args.config,
                trusted_front_door_reviewed=args.trusted_front_door_reviewed,
            )
        audit_static_boundaries(result)
        finalize_shared_deployment_requirement_tracking(result)
        audit_shared_deployment_production_review_profile(result)
    except TrinoSharedDeploymentAuditInputError as exc:
        print(f"[trino-shared-deployment-audit] rejected: {exc}", file=sys.stderr)
        return 2

    status = "ok" if result.ok else "failed"
    payload = summary_payload(result, status=status)
    if args.summary_json is not None:
        try:
            write_ascii_json_artifact(args.summary_json, payload)
        except OSError:
            print(
                "[trino-shared-deployment-audit] rejected: summary JSON could not be written",
                file=sys.stderr,
            )
            return 2

    print(f"Trino shared deployment boundary audit: {status}")
    print(
        "Deployment: "
        "config_check=reported_in_summary, "
        "trino_input_counts=reported_in_summary, "
        "shared_trino_input_counts=reported_in_summary, "
        "shared_owner_raw_input_counts=reported_in_summary, "
        "front_door_requirement=required_for_shared_trino, "
        "front_door_review=reported_in_summary, "
        "raw_reveal=blocked_for_shared_trino, "
        "path_output=none"
    )
    print(
        "Static boundary: "
        f"contract_docs={result.shared_deployment_doc_checked_count}, "
        f"static_checks={result.static_check_count}, "
        f"product_capabilities={result.product_capability_count}"
    )
    print(
        "Shared deployment requirement tracking: "
        f"shared_deployment_requirements="
        f"{counter_text(result.shared_deployment_requirement_tracking_counts) or 'none'}"
    )
    print(
        "Production review: "
        "review=shared_deployment, "
        f"status={production_review_profile_status(result)}, "
        f"requirements={counter_text(result.production_review_tracking_counts) or 'none'}"
    )
    print(
        "Product boundary: "
        f"details_case_view={audit_trino_product_surface_boundary.TRINO_DETAILS_CASE_VIEW_STATUS}, "
        f"python_report={audit_trino_product_surface_boundary.TRINO_PYTHON_REPORT_STATUS}, "
        f"optimizer_guidance={audit_trino_product_surface_boundary.TRINO_OPTIMIZER_GUIDANCE_STATUS}, "
        f"optimizer_behavior={audit_trino_product_surface_boundary.TRINO_OPTIMIZER_BEHAVIOR_STATUS}, "
        f"llm_reports={audit_trino_product_surface_boundary.TRINO_LLM_REPORTS_STATUS}, "
        "metadata_cli_smoke=dev_only_optional"
    )
    print(
        "Unsupported shared Trino surfaces: "
        + ", ".join(f"{surface}=blocked" for surface in UNSUPPORTED_TRINO_SHARED_SURFACES)
    )
    print_issues(result, limit=args.limit)
    return 0 if result.ok else 1


def audit_config(
    result: TrinoSharedDeploymentAuditResult,
    config_path: Path,
    *,
    trusted_front_door_reviewed: bool,
) -> None:
    try:
        config = load_and_validate_config(
            config_path,
            cwd=ROOT,
            repo_root=ROOT,
            use_repo_default=False,
            warn_legacy=False,
        )
        values = config.values
        clusters = build_web_cluster_configs(values)
    except (ConfigError, OSError, ValueError):
        raise TrinoSharedDeploymentAuditInputError(
            "config input could not be audited safely"
        ) from None

    host = optional_string(values, "host") or DEFAULT_HOST
    viewer_identity_header_configured = viewer_identity_header_is_configured(values)
    owner_raw_source_enabled = optional_bool(values, "owner_raw_source_enabled", default=True)
    for index, source in enumerate(
        deployment_sources(
            values,
            clusters=clusters,
            host=host,
            viewer_identity_header_configured=viewer_identity_header_configured,
            owner_raw_source_enabled=owner_raw_source_enabled,
        ),
        start=1,
    ):
        result.config_source_count += 1
        if not source.trino_enabled:
            continue
        result.trino_source_count += 1
        if not source.shared_bind:
            continue
        result.shared_trino_source_count += 1
        if not trusted_front_door_reviewed:
            add_issue(
                result,
                "shared_trino_front_door_review_missing",
                (
                    "Shared or non-local Trino web deployment requires an operator "
                    "review confirming the trusted auth front door strips inbound "
                    "viewer headers and sets exactly one normalized simple viewer."
                ),
                source_index=index,
                requirement_type="deployment_config",
                requirement_id="trusted_front_door_review",
            )
        if not source.viewer_identity_header_configured:
            add_issue(
                result,
                "shared_trino_missing_trusted_viewer_identity",
                (
                    "Shared or non-local Trino web deployment requires a trusted "
                    "front-door viewer identity contract before release hardening can pass."
                ),
                source_index=index,
                requirement_type="deployment_config",
                requirement_id="trusted_viewer_identity",
            )
        if source.source_visibility == SOURCE_VISIBILITY_OWNER_RAW:
            result.shared_owner_raw_source_count += 1
            if source.owner_raw_source_enabled:
                add_issue(
                    result,
                    "shared_trino_raw_source_reveal_not_isolated",
                    (
                        "Shared Trino deployment must keep raw source reveal isolated and "
                        "disabled; Trino Details, Python Report, and optimizer guidance "
                        "remain raw-free materialized surfaces only."
                    ),
                    source_index=index,
                    requirement_type="deployment_config",
                    requirement_id="raw_source_reveal_blocked",
                )


def deployment_sources(
    values: Mapping[str, object],
    *,
    clusters: tuple[WebClusterConfig, ...],
    host: str,
    viewer_identity_header_configured: bool,
    owner_raw_source_enabled: bool,
) -> tuple[TrinoDeploymentSource, ...]:
    shared_bind = not is_owner_raw_local_bind_host(host)
    if clusters:
        return tuple(
            TrinoDeploymentSource(
                trino_enabled=(
                    trino_support_mode_enabled(cluster.trino_support_mode)
                    or cluster.trino_beta_enabled
                ),
                trino_support_mode=str(cluster.trino_support_mode),
                source_visibility=cluster.source_visibility,
                shared_bind=shared_bind,
                viewer_identity_header_configured=viewer_identity_header_configured,
                owner_raw_source_enabled=owner_raw_source_enabled,
            )
            for cluster in clusters
        )
    support_mode = optional_string(values, "trino_support_mode") or TRINO_SUPPORT_MODE_OFF
    legacy_beta_enabled = optional_bool(values, "trino_beta_enabled", default=False)
    trino_enabled = (
        support_mode
        in {
            TRINO_SUPPORT_MODE_BETA,
            TRINO_SUPPORT_MODE_PRODUCTION,
        }
        or legacy_beta_enabled
    )
    return (
        TrinoDeploymentSource(
            trino_enabled=trino_enabled,
            trino_support_mode=support_mode,
            source_visibility=optional_string(values, "source_visibility") or "safe",
            shared_bind=shared_bind,
            viewer_identity_header_configured=viewer_identity_header_configured,
            owner_raw_source_enabled=owner_raw_source_enabled,
        ),
    )


def audit_static_boundaries(result: TrinoSharedDeploymentAuditResult) -> None:
    audit_product_surface_constants(result)
    audit_unsupported_shared_surface_constants(result)
    audit_capability_manifest(result)
    audit_release_bundle_includes_shared_gate(result)
    audit_shared_deployment_docs(result)


def audit_product_surface_constants(result: TrinoSharedDeploymentAuditResult) -> None:
    result.static_check_count += 1
    expected = {
        "details": "raw_free_materialized",
        "python_report": "raw_free_materialized",
        "optimizer_guidance": "raw_free_materialized",
        "optimizer_behavior": "guidance_only",
        "llm_reports": "not_wired",
    }
    actual = {
        "details": audit_trino_product_surface_boundary.TRINO_DETAILS_CASE_VIEW_STATUS,
        "python_report": audit_trino_product_surface_boundary.TRINO_PYTHON_REPORT_STATUS,
        "optimizer_guidance": audit_trino_product_surface_boundary.TRINO_OPTIMIZER_GUIDANCE_STATUS,
        "optimizer_behavior": audit_trino_product_surface_boundary.TRINO_OPTIMIZER_BEHAVIOR_STATUS,
        "llm_reports": audit_trino_product_surface_boundary.TRINO_LLM_REPORTS_STATUS,
    }
    for key, expected_value in expected.items():
        if actual.get(key) != expected_value:
            add_issue(
                result,
                "trino_materialized_surface_boundary_drift",
                "Trino Details, Python Report, and optimizer guidance must stay raw-free materialized surfaces.",
                requirement_type="product_boundary",
                requirement_id=key,
            )


def audit_unsupported_shared_surface_constants(result: TrinoSharedDeploymentAuditResult) -> None:
    result.static_check_count += 1
    if set(UNSUPPORTED_TRINO_SHARED_SURFACES) != EXPECTED_UNSUPPORTED_TRINO_SHARED_SURFACES:
        add_issue(
            result,
            "trino_shared_deployment_unsupported_surface_drift",
            "Shared Trino deployment must keep unsupported Trino surfaces blocked.",
            requirement_type="product_boundary",
            requirement_id="unsupported_surfaces_blocked",
        )


def audit_capability_manifest(result: TrinoSharedDeploymentAuditResult) -> None:
    result.static_check_count += 1
    capabilities = tuple(engine_capabilities("trino"))
    product_capabilities = tuple(
        capability for capability in capabilities if capability.product_surface_allowed
    )
    result.product_capability_count = len(product_capabilities)
    product_surface_ids = {capability.surface_id for capability in product_capabilities}
    if product_surface_ids != EXPECTED_TRINO_PRODUCT_SURFACES:
        add_issue(
            result,
            "trino_product_capability_surface_drift",
            (
                "Trino product capabilities must stay limited to local Recent, One Query ID, "
                "raw-free Details, Python Report, and optimizer guidance."
            ),
            requirement_type="capability",
            requirement_id="product_capability_surface_set",
        )
    for capability in product_capabilities:
        if capability.support_level != "production" or capability.surface_class != "product_web":
            add_issue(
                result,
                "trino_product_capability_classification_drift",
                "Trino product capability classification drifted from the local web-only boundary.",
                requirement_type="capability",
                requirement_id="product_capability_classification",
            )
        if capability.raw_policy != "raw_free_summary_only":
            add_issue(
                result,
                "trino_product_capability_raw_policy_drift",
                "Trino product capabilities must remain raw-free summary only.",
                requirement_type="capability",
                requirement_id="product_capability_raw_policy",
            )
    for capability in capabilities:
        if capability.surface_id in {
            "metadata_cli_summary_smoke",
            "shared_deployment_audit",
            "shared_deployment_preflight",
        }:
            if not capability.dev_only or capability.product_surface_allowed:
                add_issue(
                    result,
                    "trino_dev_gate_classification_drift",
                    "Trino metadata and shared-deployment audit gates must remain dev-only.",
                    requirement_type="capability",
                    requirement_id="dev_gate_classification",
                )


def audit_release_bundle_includes_shared_gate(result: TrinoSharedDeploymentAuditResult) -> None:
    result.static_check_count += 1
    args = audit_trino_beta_release_readiness.build_parser().parse_args(
        ["--static-only", "--skip-pytest"]
    )
    gate_names = [gate.name for gate in audit_trino_beta_release_readiness.build_gate_plan(args)]
    if "trino_shared_deployment_boundary" not in gate_names:
        add_issue(
            result,
            "release_bundle_shared_deployment_gate_missing",
            "Trino release-readiness must include the shared deployment boundary audit.",
            requirement_type="release_gate",
            requirement_id="release_bundle_shared_deployment_gate",
        )


def audit_shared_deployment_docs(result: TrinoSharedDeploymentAuditResult) -> None:
    result.static_check_count += 1
    for doc_path, required_fragments in TRINO_SHARED_DEPLOYMENT_DOC_REQUIREMENTS:
        requirement_id = doc_requirement_id(doc_path)
        try:
            normalized_doc = normalized_doc_fragment(doc_path.read_text(encoding="utf-8"))
        except OSError:
            add_issue(
                result,
                "trino_shared_deployment_doc_missing",
                "Trino shared deployment hardening docs must stay present and public-safe.",
                requirement_type="doc",
                requirement_id=requirement_id,
            )
            continue
        result.shared_deployment_doc_checked_count += 1
        if any(
            normalized_doc_fragment(fragment) not in normalized_doc
            for fragment in required_fragments
        ):
            add_issue(
                result,
                "trino_shared_deployment_doc_drift",
                (
                    "Trino shared deployment hardening docs must retain trusted "
                    "identity, raw-source isolation, dev-only metadata-smoke, and "
                    "blocked-surface wording."
                ),
                requirement_type="doc",
                requirement_id=requirement_id,
            )


def summary_payload(
    result: TrinoSharedDeploymentAuditResult,
    *,
    status: str,
) -> dict[str, Any]:
    return {
        "summary_kind": TRINO_SHARED_DEPLOYMENT_AUDIT_SUMMARY_KIND,
        "status": status,
        "deployment_boundary": {
            "config_checked": result.config_checked,
            "trino_source_count": result.trino_source_count,
            "shared_trino_source_count": result.shared_trino_source_count,
            "shared_owner_raw_source_count": result.shared_owner_raw_source_count,
            "trusted_front_door_identity": "required_for_shared_trino",
            "trusted_front_door_review": trusted_front_door_review_status(result),
            "raw_source_reveal": "blocked_for_shared_trino",
            "paths_printed": False,
            "header_values_printed": False,
            "query_ids_printed": False,
        },
        "product_boundary": {
            "details_case_view": audit_trino_product_surface_boundary.TRINO_DETAILS_CASE_VIEW_STATUS,
            "python_report": audit_trino_product_surface_boundary.TRINO_PYTHON_REPORT_STATUS,
            "optimizer_guidance": (
                audit_trino_product_surface_boundary.TRINO_OPTIMIZER_GUIDANCE_STATUS
            ),
            "optimizer_behavior": audit_trino_product_surface_boundary.TRINO_OPTIMIZER_BEHAVIOR_STATUS,
            "llm_reports": audit_trino_product_surface_boundary.TRINO_LLM_REPORTS_STATUS,
            "metadata_cli_smoke": "dev_only_optional",
            "metadata_collection": "not_wired",
        },
        "unsupported_surfaces": {
            surface: "blocked" for surface in UNSUPPORTED_TRINO_SHARED_SURFACES
        },
        "counts": {
            "config_source_count": result.config_source_count,
            "shared_deployment_doc_checked_count": (result.shared_deployment_doc_checked_count),
            "static_check_count": result.static_check_count,
            "product_capability_count": result.product_capability_count,
        },
        "shared_deployment_requirement_tracking_counts": counter_payload(
            result.shared_deployment_requirement_tracking_counts
        ),
        "production_review_profile": TRINO_SHARED_DEPLOYMENT_PRODUCTION_REVIEW_PROFILE,
        "production_review_profile_status": production_review_profile_status(result),
        "production_review_requirements": {
            "required_families": list(TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_FAMILIES),
            "required_deployment_config_requirements": list(
                TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_CONFIG_REQUIREMENTS
            ),
            "required_product_boundary_requirements": list(
                TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_PRODUCT_BOUNDARY_REQUIREMENTS
            ),
            "required_capability_requirements": list(
                TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_CAPABILITY_REQUIREMENTS
            ),
            "required_release_requirements": list(
                TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_RELEASE_REQUIREMENTS
            ),
            "required_doc_requirements": list(
                TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_DOC_REQUIREMENTS
            ),
            "required_unsupported_surfaces": list(
                TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_UNSUPPORTED_SURFACES
            ),
        },
        "production_review_tracking_counts": counter_payload(
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
        "shared_deployment_requirement_tracking": [
            {
                "family_id": tracking.family_id,
                "requirement_type": tracking.requirement_type,
                "requirement_id": tracking.requirement_id,
                "tracking_status": tracking.tracking_status,
                "issue_count": tracking.issue_count,
            }
            for tracking in result.shared_deployment_requirement_tracking
        ],
        "issues": {
            "counts": counter_payload(result.issue_counts),
            "items": [
                {
                    "source_index": source_index,
                    "category": issue.category,
                    "message": issue.message,
                    "requirement_type": issue.requirement_type,
                    "requirement_id": issue.requirement_id,
                }
                for source_index, issue in result.issues
            ],
        },
    }


def finalize_shared_deployment_requirement_tracking(
    result: TrinoSharedDeploymentAuditResult,
) -> None:
    result.shared_deployment_requirement_tracking.clear()
    result.shared_deployment_requirement_tracking_counts.clear()
    for requirement_id in TRINO_SHARED_DEPLOYMENT_CONFIG_REQUIREMENTS:
        _append_shared_deployment_requirement_tracking(
            result,
            family_id="deployment_boundary",
            requirement_type="deployment_config",
            requirement_id=requirement_id,
        )
    for requirement_id in TRINO_SHARED_DEPLOYMENT_PRODUCT_BOUNDARY_REQUIREMENTS:
        _append_shared_deployment_requirement_tracking(
            result,
            family_id="product_boundary",
            requirement_type="product_boundary",
            requirement_id=requirement_id,
        )
    for requirement_id in TRINO_SHARED_DEPLOYMENT_CAPABILITY_REQUIREMENTS:
        _append_shared_deployment_requirement_tracking(
            result,
            family_id="capability_manifest",
            requirement_type="capability",
            requirement_id=requirement_id,
        )
    for requirement_id in TRINO_SHARED_DEPLOYMENT_RELEASE_REQUIREMENTS:
        _append_shared_deployment_requirement_tracking(
            result,
            family_id="release_bundle",
            requirement_type="release_gate",
            requirement_id=requirement_id,
        )
    for doc_path, _required_fragments in TRINO_SHARED_DEPLOYMENT_DOC_REQUIREMENTS:
        _append_shared_deployment_requirement_tracking(
            result,
            family_id="shared_deployment_docs",
            requirement_type="doc",
            requirement_id=doc_requirement_id(doc_path),
        )


def audit_shared_deployment_production_review_profile(
    result: TrinoSharedDeploymentAuditResult,
) -> None:
    family_ids = {tracking.family_id for tracking in result.shared_deployment_requirement_tracking}
    _append_production_review_tracking(
        result,
        requirement_id="require_review_families",
        counter_name="families",
        observed_count=sum(
            1
            for family_id in TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_FAMILIES
            if family_id in family_ids
        ),
        required_count=len(TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_FAMILIES),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_deployment_config_requirements",
        counter_name="deployment_config_requirements",
        observed_count=_covered_requirement_count(
            result,
            requirement_type="deployment_config",
            requirement_ids=TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_CONFIG_REQUIREMENTS,
        ),
        required_count=len(TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_CONFIG_REQUIREMENTS),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_product_boundary_requirements",
        counter_name="product_boundary_requirements",
        observed_count=_covered_requirement_count(
            result,
            requirement_type="product_boundary",
            requirement_ids=TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_PRODUCT_BOUNDARY_REQUIREMENTS,
        ),
        required_count=len(TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_PRODUCT_BOUNDARY_REQUIREMENTS),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_capability_requirements",
        counter_name="capability_requirements",
        observed_count=_covered_requirement_count(
            result,
            requirement_type="capability",
            requirement_ids=TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_CAPABILITY_REQUIREMENTS,
        ),
        required_count=len(TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_CAPABILITY_REQUIREMENTS),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_release_requirements",
        counter_name="release_requirements",
        observed_count=_covered_requirement_count(
            result,
            requirement_type="release_gate",
            requirement_ids=TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_RELEASE_REQUIREMENTS,
        ),
        required_count=len(TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_RELEASE_REQUIREMENTS),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_doc_requirements",
        counter_name="doc_requirements",
        observed_count=_covered_requirement_count(
            result,
            requirement_type="doc",
            requirement_ids=TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_DOC_REQUIREMENTS,
        ),
        required_count=len(TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_DOC_REQUIREMENTS),
    )
    _append_production_review_tracking(
        result,
        requirement_id="require_unsupported_surface_blocks",
        counter_name="unsupported_surfaces",
        observed_count=sum(
            1
            for surface in TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_UNSUPPORTED_SURFACES
            if surface in UNSUPPORTED_TRINO_SHARED_SURFACES
        ),
        required_count=len(TRINO_SHARED_DEPLOYMENT_REQUIRED_REVIEW_UNSUPPORTED_SURFACES),
    )


def _covered_requirement_count(
    result: TrinoSharedDeploymentAuditResult,
    *,
    requirement_type: str,
    requirement_ids: tuple[str, ...],
) -> int:
    covered_requirement_ids = {
        tracking.requirement_id
        for tracking in result.shared_deployment_requirement_tracking
        if tracking.requirement_type == requirement_type
        and tracking.tracking_status in {"accepted", "not_required"}
    }
    return sum(1 for requirement_id in requirement_ids if requirement_id in covered_requirement_ids)


def _append_production_review_tracking(
    result: TrinoSharedDeploymentAuditResult,
    *,
    requirement_id: str,
    counter_name: str,
    observed_count: int,
    required_count: int,
) -> None:
    tracking_status = production_review_tracking_status(observed_count, required_count)
    result.production_review_tracking.append(
        TrinoSharedDeploymentProductionReviewTracking(
            requirement_id=requirement_id,
            counter_name=counter_name,
            tracking_status=tracking_status,
            observed_count=observed_count,
            required_count=required_count,
        )
    )
    result.production_review_tracking_counts[tracking_status] += 1
    if tracking_status != "accepted":
        add_issue(
            result,
            "trino_shared_deployment_production_review_gap",
            "Trino shared deployment production-review profile is incomplete.",
            requirement_type="production_review_profile",
            requirement_id=requirement_id,
        )


def production_review_tracking_status(observed_count: int, required_count: int) -> str:
    if required_count <= 0:
        return "not_required"
    if observed_count >= required_count:
        return "accepted"
    return "insufficient"


def production_review_profile_status(result: TrinoSharedDeploymentAuditResult) -> str:
    if not result.production_review_tracking:
        return "not_required"
    if set(result.production_review_tracking_counts) == {"accepted"}:
        return TRINO_SHARED_DEPLOYMENT_PRODUCTION_REVIEW_PROFILE_STATUS
    return "failed"


def _append_shared_deployment_requirement_tracking(
    result: TrinoSharedDeploymentAuditResult,
    *,
    family_id: str,
    requirement_type: str,
    requirement_id: str,
) -> None:
    issues = _issues_for_requirement(
        result,
        requirement_type=requirement_type,
        requirement_id=requirement_id,
    )
    tracking_status = _shared_deployment_requirement_tracking_status(
        result,
        requirement_type=requirement_type,
        requirement_id=requirement_id,
        issues=issues,
    )
    result.shared_deployment_requirement_tracking.append(
        TrinoSharedDeploymentRequirementTracking(
            family_id=family_id,
            requirement_type=requirement_type,
            requirement_id=requirement_id,
            tracking_status=tracking_status,
            issue_count=len(issues),
        )
    )
    result.shared_deployment_requirement_tracking_counts[tracking_status] += 1


def _issues_for_requirement(
    result: TrinoSharedDeploymentAuditResult,
    *,
    requirement_type: str,
    requirement_id: str,
) -> tuple[TrinoSharedDeploymentAuditIssue, ...]:
    return tuple(
        issue
        for _source_index, issue in result.issues
        if issue.requirement_type == requirement_type and issue.requirement_id == requirement_id
    )


def _shared_deployment_requirement_tracking_status(
    result: TrinoSharedDeploymentAuditResult,
    *,
    requirement_type: str,
    requirement_id: str,
    issues: tuple[TrinoSharedDeploymentAuditIssue, ...],
) -> str:
    if any(
        issue.category
        in {
            "shared_trino_front_door_review_missing",
            "shared_trino_missing_trusted_viewer_identity",
            "release_bundle_shared_deployment_gate_missing",
            "trino_shared_deployment_doc_missing",
        }
        for issue in issues
    ):
        return "missing"
    if issues:
        return "invalid"
    if _shared_deployment_requirement_not_required(
        result,
        requirement_type=requirement_type,
        requirement_id=requirement_id,
    ):
        return "not_required"
    return "accepted"


def _shared_deployment_requirement_not_required(
    result: TrinoSharedDeploymentAuditResult,
    *,
    requirement_type: str,
    requirement_id: str,
) -> bool:
    if requirement_type != "deployment_config":
        return False
    if requirement_id == "config_source_inventory":
        return not result.config_checked
    if requirement_id in {
        "trusted_front_door_review",
        "trusted_viewer_identity",
        "raw_source_reveal_blocked",
    }:
        return result.shared_trino_source_count == 0
    return False


def add_issue(
    result: TrinoSharedDeploymentAuditResult,
    category: str,
    message: str,
    *,
    source_index: int | None = None,
    requirement_type: str | None = None,
    requirement_id: str | None = None,
) -> None:
    issue = TrinoSharedDeploymentAuditIssue(
        category=category,
        message=message,
        requirement_type=requirement_type,
        requirement_id=requirement_id,
    )
    result.issue_counts[category] += 1
    result.issues.append((source_index, issue))


def print_issues(result: TrinoSharedDeploymentAuditResult, *, limit: int) -> None:
    if not result.issues:
        print("Issues: none")
        return
    print("Issues:")
    for source_index, issue in result.issues[:limit]:
        source_text = f"source={source_index}; " if source_index is not None else ""
        print(f"- {issue.category}: {source_text}{issue.message}")
    remaining = len(result.issues) - limit
    if remaining > 0:
        print(f"- additional_issues: {remaining}")


def trusted_front_door_review_status(result: TrinoSharedDeploymentAuditResult) -> str:
    if result.trusted_front_door_reviewed:
        return "confirmed"
    if result.shared_trino_source_count:
        return "missing_for_shared_trino"
    return "not_required_for_local_or_static"


def viewer_identity_header_is_configured(values: Mapping[str, object]) -> bool:
    value = optional_string(values, "viewer_identity_header")
    if value is None:
        return False
    try:
        return normalize_viewer_identity_header(value) is not None
    except ValueError:
        return False


def optional_string(values: Mapping[str, object], key: str) -> str | None:
    value = values.get(key)
    return value if isinstance(value, str) and value else None


def optional_bool(values: Mapping[str, object], key: str, *, default: bool) -> bool:
    value = values.get(key)
    return value if isinstance(value, bool) else default


def counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def counter_text(counter: Counter[str]) -> str:
    return ", ".join(f"{key}={counter[key]}" for key in sorted(counter))


def normalized_doc_fragment(text: str) -> str:
    return " ".join(text.split())


def doc_requirement_id(doc_path: Path) -> str:
    return TRINO_SHARED_DEPLOYMENT_DOC_REQUIREMENT_IDS.get(doc_path.name, "shared_deployment_doc")


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
