#!/usr/bin/env python3
"""Audit Trino compact diagnosis artifacts against product-surface boundaries."""

from __future__ import annotations

import argparse
import ast
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

from query_doctor.analyzer.engine_facts import EngineFactContractError  # noqa: E402
from query_doctor.cli.commands import COMMAND_SPECS  # noqa: E402
from query_doctor.report.safety_validation import (  # noqa: E402
    contains_raw_sql_like_text,
    validate_report_internal_fingerprints,
)
from query_doctor.safety.browser_display import redact_browser_display_text  # noqa: E402
from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    ascii_json_artifact_text,
    output_overlaps_inputs_error,
    write_ascii_json_artifact,
)
from query_doctor.trino.diagnosis import (  # noqa: E402
    TRINO_COMPACT_DIAGNOSIS_SCHEMA_VERSION,
    TRINO_COMPACT_DIAGNOSIS_SUPPORT_STATUS,
    TRINO_COMPACT_DIAGNOSTIC_LANE_NAME,
    TRINO_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
    TRINO_LANE_READINESS_AGGREGATE_SELECTION_ONLY,
    TRINO_LANE_READINESS_COVERAGE_UNKNOWN,
    TRINO_LANE_READINESS_ONE_QUERY_ATTENTION_READY,
    TRINO_LANE_READINESS_ONE_QUERY_LIMITED,
    TRINO_SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST,
    TRINO_SOURCE_GRANULARITY_ONE_QUERY_BOUNDARY,
    build_trino_compact_diagnosis_from_boundary,
    select_trino_boundary_payload,
)
from query_doctor.web.preview_surfaces import PREVIEW_WEB_POST_PATHS  # noqa: E402
from query_doctor.web.preview_surfaces import PREVIEW_WEB_SURFACES  # noqa: E402
from query_doctor.web.routes import STATIC_POST_PATHS  # noqa: E402
from scripts.audit_trino_compact_readiness import (  # noqa: E402
    EXPECTED_DIAGNOSIS_BOUNDARY,
    METADATA_SUMMARY_FACT_IDS,
    REQUIRED_TRINO_LIMITATION_IDS,
    TrinoCompactReadinessInputError,
    counter_payload,
    handoff_manifest_entries,
    raw_text_issue_categories,
)


TRINO_PRODUCT_SURFACE_AUDIT_SUMMARY_KIND = "trino_product_surface_boundary_audit_v1"
TRINO_PRODUCT_SURFACE_STATUS = "recent_query_id_raw_free_details_python_report_optimizer_guidance"
TRINO_SUPPORT_CLAIM_STATUS = "local_production"
TRINO_DETAILS_CASE_VIEW_STATUS = "raw_free_materialized"
TRINO_PYTHON_REPORT_STATUS = "raw_free_materialized"
TRINO_OPTIMIZER_GUIDANCE_STATUS = "raw_free_materialized"
TRINO_OPTIMIZER_BEHAVIOR_STATUS = "guidance_only"
TRINO_LLM_REPORTS_STATUS = "not_wired"
EXPECTED_DIAGNOSTIC_LANE_GATES = {
    "readiness_audit": "required_for_handoff",
    "surface_audit": "required_before_wiring",
}
ALLOWED_DIAGNOSTIC_LANE_SOURCE_GRANULARITIES = frozenset(
    {
        TRINO_SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST,
        TRINO_SOURCE_GRANULARITY_ONE_QUERY_BOUNDARY,
    }
)
ALLOWED_DIAGNOSTIC_LANE_READINESS = frozenset(
    {
        TRINO_LANE_READINESS_AGGREGATE_SELECTION_ONLY,
        TRINO_LANE_READINESS_COVERAGE_UNKNOWN,
        TRINO_LANE_READINESS_ONE_QUERY_ATTENTION_READY,
        TRINO_LANE_READINESS_ONE_QUERY_LIMITED,
    }
)
ALLOWED_DIAGNOSTIC_LANE_VERIFICATION_SCOPES = frozenset(
    {
        "comparable_one_query_rerun",
        "representative_query_selection",
        "source_contract_review",
    }
)
ALLOWED_TRINO_POST_PATHS = frozenset({"/trino/compact-diagnosis"})
ALLOWED_TRINO_COMMAND_ROLES = frozenset(
    {
        "diagnose_trino_compact",
        "trino_coordinator_query_info_target_check",
        "trino_coordinator_query_info_pruned_probe",
        "trino_coordinator_query_info_pruned_import",
        "trino_event_store_import",
        "trino_event_source_contract_check",
        "trino_http_event_archive_import",
        "trino_http_query_detail_archive_import",
        "trino_import",
        "trino_metadata_cli_summary",
        "trino_metadata_source_contract_check",
        "trino_metadata_summary_import",
        "trino_query_detail_import",
        "trino_query_info_pruned_import",
        "trino_query_list_import",
        "trino_statement_stats_import",
    }
)
FORBIDDEN_TRINO_PRODUCT_ROLE_FRAGMENTS = (
    "trino_recent",
    "trino_report",
    "trino_optimizer",
    "trino_metadata_collection",
    "trino_metadata_import",
    "trino_metadata_report",
    "collect_trino",
)
PRODUCT_SURFACE_SOURCE_ROOTS = (
    ROOT / "query_doctor" / "web",
    ROOT / "query_doctor" / "report",
    ROOT / "query_doctor" / "optimizer",
)
TRINO_PUBLIC_CLAIM_PATHS = (
    ROOT / "README.md",
    ROOT / "README.ru.md",
    ROOT / "docs" / "changelog.md",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "i18n" / "ru" / "README.md",
    ROOT / "docs" / "configuration.md",
    ROOT / "docs" / "i18n" / "ru" / "configuration.md",
    ROOT / "docs" / "engines" / "README.md",
    ROOT / "docs" / "engine-support-gap-matrix.md",
    ROOT / "docs" / "safety-contract.md",
    ROOT / "docs" / "i18n" / "ru" / "safety-contract.md",
    ROOT / "docs" / "release-checklist.md",
    ROOT / "docs" / "public-release-readiness.md",
    ROOT / "docs" / "trino-beta-ui-readiness.md",
    ROOT / "query_doctor" / "web" / "ui" / "help.py",
    ROOT / "query_doctor" / "web" / "ui" / "recent_scan_form.py",
    ROOT / "query_doctor" / "web" / "ui" / "trino.py",
    ROOT / "query_doctor" / "web" / "ui" / "trino_demo.py",
)
REQUIRED_TRINO_PUBLIC_CLAIM_FRAGMENTS = (
    "Trino Beta",
    "local production",
    "Recent",
    "One Query ID",
    "Running",
    "query-history crawling",
    "metadata collection",
    "Details",
    "Python Report",
    "optimizer guidance",
    "LLM reports",
    "optimizer",
    "SQL execution",
)
FORBIDDEN_TRINO_PUBLIC_CLAIM_FRAGMENTS = (
    "Trino broad production support is enabled",
    "Trino broad production support is available",
    "production Trino support is enabled",
    "production Trino support is available",
    "Trino Recent scan is supported",
    "Trino Running scan is supported",
    "Trino query-history crawling is supported",
    "Trino metadata collection is supported",
    "Trino Details are supported",
    "Trino LLM reports are supported",
    "Trino optimizer is supported",
    "generated Trino SQL is supported",
    "Trino SQL execution is supported",
    "does not enable Recent/Running",
    "production Trino support доступен",
    "production Trino support включен",
    "Trino Recent scan поддерживается",
    "Trino Running scan поддерживается",
    "Trino query-history crawling поддерживается",
    "Trino metadata collection поддерживается",
    "Trino Details поддерживаются",
    "Trino LLM reports поддерживаются",
    "Trino optimizer поддерживается",
    "generated Trino SQL поддерживается",
    "Trino SQL execution поддерживается",
)
TRINO_PRODUCT_SOURCE_EXEMPT_MODULES = frozenset(
    {
        "query_doctor.web.trino_beta_query",
        "query_doctor.web.trino_case_artifacts",
        "query_doctor.web.trino_details",
        "query_doctor.web.trino_guidance",
        "query_doctor.web.trino_report",
        "query_doctor.web.trino_recent",
        "query_doctor.web.trino_compact",
        "query_doctor.web.ui.trino",
    }
)
ALLOWED_TRINO_PRODUCT_SOURCE_IMPORT_PREFIXES = {
    "query_doctor.web.cluster_selection": frozenset(
        {
            "query_doctor.trino.support_mode",
        }
    ),
    "query_doctor.web.config": frozenset(
        {
            "query_doctor.trino.support_mode",
        }
    ),
    "query_doctor.web.deployment_readiness": frozenset(
        {
            "query_doctor.trino.support_mode",
        }
    ),
    "query_doctor.web.models": frozenset(
        {
            "query_doctor.trino.support_mode",
        }
    ),
    "query_doctor.web.routes": frozenset(
        {
            "query_doctor.web.preview_surfaces",
            "query_doctor.web.trino_details",
            "query_doctor.web.trino_guidance",
            "query_doctor.web.trino_report",
        }
    ),
    "query_doctor.web.preview_surfaces": frozenset(
        {
            "query_doctor.web.trino_compact",
            "query_doctor.web.ui.trino",
        }
    ),
    "query_doctor.web.batch_scan": frozenset(
        {
            "query_doctor.web.trino_beta_query",
            "query_doctor.web.trino_recent",
        }
    ),
    "query_doctor.web.batch_jobs": frozenset(
        {
            "query_doctor.web.trino_beta_query",
            "query_doctor.web.trino_recent",
            "query_doctor.web.ui.trino",
        }
    ),
    "query_doctor.web.jobs": frozenset(
        {
            "query_doctor.web.ui.trino",
        }
    ),
    "query_doctor.web.query_analysis": frozenset(
        {
            "query_doctor.web.trino_beta_query",
        }
    ),
    "query_doctor.web.request_handlers": frozenset(
        {
            "query_doctor.web.trino_beta_query",
        }
    ),
    "query_doctor.web.ui.pages": frozenset(
        {
            "query_doctor.web.ui.trino",
            "query_doctor.web.ui.trino_demo",
        }
    ),
    "query_doctor.web.ui.recent_scan_form": frozenset(
        {
            "query_doctor.trino.support_mode",
        }
    ),
    "query_doctor.web.ui.trino_demo": frozenset(
        {
            "query_doctor.web.ui.trino",
        }
    ),
}
FORBIDDEN_TRINO_SOURCE_IMPORT_PREFIXES = (
    "query_doctor.trino",
    "query_doctor.analyzer.trino_",
    "query_doctor.cli.trino_",
    "query_doctor.web.preview_surfaces",
    "query_doctor.web.trino_compact",
    "query_doctor.web.trino_details",
    "query_doctor.web.trino_guidance",
    "query_doctor.web.trino_report",
    "query_doctor.web.ui.trino",
)
FORBIDDEN_TRINO_BETA_QUERY_IMPORT_PREFIXES = (
    "query_doctor.cli",
    "query_doctor.optimizer",
    "query_doctor.report",
    "query_doctor.web.batch_case_actions",
    "query_doctor.web.command_builders",
    "query_doctor.web.specific_query_actions",
    "query_doctor.web.subprocesses",
    "subprocess",
)
FORBIDDEN_TRINO_BETA_UI_IMPORT_PREFIXES = (
    "query_doctor.optimizer",
    "query_doctor.report",
    "query_doctor.web.batch_case_actions",
    "query_doctor.web.report_actions",
    "query_doctor.web.specific_query",
    "query_doctor.web.specific_query_actions",
    "query_doctor.web.specific_query_pages",
    "query_doctor.web.ui.report",
    "query_doctor.web.ui.specific_query",
)
FORBIDDEN_TRINO_BETA_UI_SURFACE_SNIPPETS = (
    'href="/query/details/',
    'href="/optimizer"',
    'action="/query/details/',
    "data-case-action",
    "Run report",
    "Run optimizer",
    "LLM narrative",
    "Query LLM optimizer",
    "start_specific_query",
)
FORBIDDEN_TRINO_REPORT_IMPORT_PREFIXES = (
    "query_doctor.cli",
    "query_doctor.optimizer",
    "query_doctor.web.batch_case_actions",
    "query_doctor.web.command_builders",
    "query_doctor.web.specific_query_actions",
    "query_doctor.web.subprocesses",
    "query_doctor.web.trusted_artifacts",
    "subprocess",
)
FORBIDDEN_TRINO_REPORT_SURFACE_SNIPPETS = (
    'href="/query/details/',
    'href="/python-report/',
    'href="/optimizer"',
    'action="/query/details/',
    "data-case-action",
    "LLM narrative",
    "Query LLM optimizer",
    "start_specific_query",
)
FORBIDDEN_TRINO_GUIDANCE_IMPORT_PREFIXES = (
    "query_doctor.cli",
    "query_doctor.optimizer",
    "query_doctor.web.batch_case_actions",
    "query_doctor.web.command_builders",
    "query_doctor.web.specific_query_actions",
    "query_doctor.web.subprocesses",
    "query_doctor.web.trusted_artifacts",
    "subprocess",
)
FORBIDDEN_TRINO_GUIDANCE_SURFACE_SNIPPETS = (
    'href="/query/details/',
    'href="/python-report/',
    'href="/optimizer"',
    'action="/query/details/',
    "data-case-action",
    "LLM narrative",
    "Query LLM optimizer",
    "Run optimizer",
    "start_specific_query",
    "candidate SQL",
    "optimized SQL",
    "execute this SQL",
)
FORBIDDEN_TRINO_DETAILS_IMPORT_PREFIXES = (
    "query_doctor.cli",
    "query_doctor.optimizer",
    "query_doctor.web.batch_case_actions",
    "query_doctor.web.command_builders",
    "query_doctor.web.specific_query_actions",
    "query_doctor.web.subprocesses",
    "subprocess",
)
FORBIDDEN_TRINO_DETAILS_SURFACE_SNIPPETS = (
    'href="/query/details/',
    'href="/python-report/',
    'href="/optimizer"',
    'action="/query/details/',
    "data-case-action",
    "Python Report",
    "Run report",
    "Run optimizer",
    "LLM narrative",
    "Query LLM optimizer",
    "source SQL",
)


class TrinoProductSurfaceAuditInputError(RuntimeError):
    """Raised when audit inputs cannot be read without exposing them."""


@dataclass(frozen=True)
class TrinoProductSurfaceAuditIssue:
    category: str
    message: str


@dataclass(frozen=True)
class ProductSurfaceSourceTarget:
    module_name: str
    path: Path


@dataclass
class TrinoProductSurfaceAuditResult:
    input_count: int = 0
    diagnosis_artifact_checked_count: int = 0
    product_source_module_checked_count: int = 0
    product_source_allowed_trino_import_count: int = 0
    public_claim_surface_checked_count: int = 0
    attention_area_count: int = 0
    supported_attention_area_count: int = 0
    diagnostic_lane_checked_count: int = 0
    limitation_count: int = 0
    diagnostic_lane_source_granularity_counts: Counter[str] = field(default_factory=Counter)
    diagnostic_lane_readiness_counts: Counter[str] = field(default_factory=Counter)
    diagnostic_lane_verification_scope_counts: Counter[str] = field(default_factory=Counter)
    diagnostic_lane_fact_state_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[tuple[int | None, TrinoProductSurfaceAuditIssue]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issue_counts


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check retained raw-free Trino compact diagnosis artifacts against the current "
            "bounded product-surface boundary. This allows only local raw-free Details over "
            "materialized Trino web cases plus deterministic Python Report, and does not "
            "promote Trino to LLM reports, optimizer, metadata, Running, SQL execution, or "
            "broad support."
        )
    )
    parser.add_argument(
        "boundary_json",
        nargs="*",
        type=Path,
        help="Raw-free Trino boundary JSON file, or package boundary export with --sample-index.",
    )
    parser.add_argument(
        "--diagnosis-json",
        action="append",
        type=Path,
        default=[],
        help=(
            "Optional deterministic Trino compact diagnosis JSON to compare with the matching "
            "boundary input. Repeat once per boundary input."
        ),
    )
    parser.add_argument(
        "--sample-index",
        type=non_negative_int,
        default=None,
        help="Sample index for package boundary exports. Applies to every package input.",
    )
    parser.add_argument(
        "--handoff-suite-manifest",
        type=Path,
        default=None,
        help=(
            "Optional trino_one_query_handoff_suite_v1 manifest whose entries reference "
            "raw-free boundary_json plus diagnosis_json artifacts. The manifest path and "
            "referenced artifact paths are never printed."
        ),
    )
    parser.add_argument(
        "--registry-only",
        action="store_true",
        help="Run only the command/web product-surface registry audit.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional raw-free machine summary path. The path is never printed.",
    )
    parser.add_argument("--limit", type=positive_int, default=12, help="Maximum issues to print.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    input_paths = (args.handoff_suite_manifest, *args.boundary_json, *args.diagnosis_json)
    overlap_error = reject_summary_output_overlap(args.summary_json, input_paths)
    if overlap_error:
        print(f"[trino-product-surface-audit] rejected: {overlap_error}", file=sys.stderr)
        return 2
    if args.registry_only and (
        args.boundary_json or args.diagnosis_json or args.handoff_suite_manifest
    ):
        print(
            "[trino-product-surface-audit] rejected: --registry-only cannot use boundary inputs",
            file=sys.stderr,
        )
        return 2
    if args.handoff_suite_manifest is not None and args.boundary_json:
        print(
            "[trino-product-surface-audit] rejected: use either boundary JSON inputs or --handoff-suite-manifest",
            file=sys.stderr,
        )
        return 2
    if args.handoff_suite_manifest is not None and args.diagnosis_json:
        print(
            "[trino-product-surface-audit] rejected: use manifest entry diagnosis_json values for handoff suite checks",
            file=sys.stderr,
        )
        return 2
    if not args.registry_only and not args.boundary_json and args.handoff_suite_manifest is None:
        print(
            "[trino-product-surface-audit] rejected: provide boundary JSON, --handoff-suite-manifest, or --registry-only",
            file=sys.stderr,
        )
        return 2
    if args.diagnosis_json and len(args.diagnosis_json) != len(args.boundary_json):
        print(
            "[trino-product-surface-audit] rejected: diagnosis JSON count must match boundary count",
            file=sys.stderr,
        )
        return 2

    result = TrinoProductSurfaceAuditResult()
    audit_registry_surface(result)
    audit_product_surface_source_boundaries(result)
    audit_trino_beta_query_module_boundary(result)
    audit_trino_details_module_boundary(result)
    audit_trino_report_module_boundary(result)
    audit_trino_guidance_module_boundary(result)
    audit_trino_beta_ui_modules_boundary(result)
    audit_public_trino_claim_boundaries(result)
    if not args.registry_only:
        if args.handoff_suite_manifest is not None:
            if args.sample_index is not None:
                print(
                    "[trino-product-surface-audit] rejected: --sample-index is not used with handoff suite manifests",
                    file=sys.stderr,
                )
                return 2
            if not audit_handoff_manifest(
                result,
                args.handoff_suite_manifest,
                summary_json=args.summary_json,
            ):
                return 2
        else:
            audit_inputs(
                result,
                args.boundary_json,
                diagnosis_jsons=tuple(args.diagnosis_json),
                sample_index=args.sample_index,
            )

    status = "ok" if result.ok else "failed"
    summary = product_surface_summary_payload(result, status=status)
    if not write_summary_or_reject(args.summary_json, summary):
        return 2

    print(f"Trino product-surface boundary audit: {status}")
    print(
        "Boundary: "
        f"product_surface={TRINO_PRODUCT_SURFACE_STATUS}, "
        f"support_claim={TRINO_SUPPORT_CLAIM_STATUS}, "
        f"details_case_view={TRINO_DETAILS_CASE_VIEW_STATUS}, "
        f"python_report={TRINO_PYTHON_REPORT_STATUS}, "
        f"optimizer_guidance={TRINO_OPTIMIZER_GUIDANCE_STATUS}, "
        f"llm_reports={TRINO_LLM_REPORTS_STATUS}, "
        f"optimizer_behavior={TRINO_OPTIMIZER_BEHAVIOR_STATUS}, "
        "live_recent_scan=retained_query_list_local_production, "
        "live_known_query_diagnosis=one_query_pruned_query_info_local_production, "
        "trino_sql_execution=not_performed"
    )
    print(
        "Artifacts: "
        f"boundary_json_count={result.input_count}, "
        f"diagnosis_json_checked={result.diagnosis_artifact_checked_count}, "
        f"diagnostic_lane_checked={result.diagnostic_lane_checked_count}, "
        "paths=not_printed"
    )
    print(
        "Registry: "
        "trino_product_routes=recent_query_id_raw_free_details_python_report_optimizer_guidance, "
        "trino_product_cli=blocked, "
        "details_python_report_guidance_source_imports=raw_free_materialized, "
        "allowed_surface=compact_diagnosis_recent_query_id_raw_free_details_python_report_optimizer_guidance"
    )
    print(
        "Source boundaries: "
        f"product_source_modules_checked={result.product_source_module_checked_count}, "
        f"allowed_trino_preview_imports={result.product_source_allowed_trino_import_count}, "
        f"public_claim_surfaces_checked={result.public_claim_surface_checked_count}, "
        "paths=not_printed"
    )
    print_issues(result, limit=args.limit)
    return 0 if result.ok else 1


def audit_inputs(
    result: TrinoProductSurfaceAuditResult,
    boundary_jsons: Iterable[Path],
    *,
    diagnosis_jsons: tuple[Path, ...],
    sample_index: int | None,
    start_index: int = 1,
) -> None:
    diagnosis_by_index = {start_index + offset: path for offset, path in enumerate(diagnosis_jsons)}
    for index, boundary_json in enumerate(boundary_jsons, start=start_index):
        result.input_count += 1
        try:
            boundary = select_trino_boundary_payload(
                load_json_object(boundary_json, input_label="boundary JSON input"),
                sample_index=sample_index,
            )
            if has_metadata_summary_facts(boundary):
                add_issue(
                    result,
                    "metadata_summary_boundary_not_product_surface",
                    (
                        "Trino metadata-summary boundaries are aggregate coverage evidence, "
                        "not product-surface diagnosis artifacts."
                    ),
                    input_index=index,
                )
                continue
            diagnosis = json_normalized_payload(
                build_trino_compact_diagnosis_from_boundary(boundary)
            )
        except (TrinoProductSurfaceAuditInputError, EngineFactContractError, ValueError):
            add_issue(
                result,
                "boundary_input_rejected",
                "One Trino boundary input could not be converted to compact diagnosis safely.",
                input_index=index,
            )
            continue
        diagnosis_json = diagnosis_by_index.get(index)
        expected_diagnosis = diagnosis
        if diagnosis_json is not None:
            try:
                stored_diagnosis = load_json_object(
                    diagnosis_json,
                    input_label="diagnosis JSON input",
                )
            except TrinoProductSurfaceAuditInputError:
                add_issue(
                    result,
                    "diagnosis_input_unreadable",
                    "One Trino diagnosis artifact could not be read or parsed safely.",
                    input_index=index,
                )
                continue
            result.diagnosis_artifact_checked_count += 1
            if stored_diagnosis != diagnosis:
                add_issue(
                    result,
                    "diagnosis_artifact_mismatch",
                    "Stored Trino diagnosis artifact does not match deterministic boundary output.",
                    input_index=index,
                )
            diagnosis = stored_diagnosis
        audit_diagnosis_payload(
            result,
            diagnosis,
            input_index=index,
            expected_diagnosis=expected_diagnosis,
        )


def audit_handoff_manifest(
    result: TrinoProductSurfaceAuditResult,
    manifest_json: Path,
    *,
    summary_json: Path | None,
) -> bool:
    try:
        entries = handoff_manifest_entries(
            load_json_object(manifest_json, input_label="handoff manifest JSON input"),
            base_dir=manifest_json.parent,
        )
    except (TrinoProductSurfaceAuditInputError, TrinoCompactReadinessInputError) as exc:
        print(f"[trino-product-surface-audit] rejected: {exc}", file=sys.stderr)
        return False
    overlap_error = reject_summary_output_overlap(
        summary_json,
        (
            manifest_json,
            *(
                artifact
                for entry in entries
                for artifact in (
                    entry.boundary_json,
                    entry.diagnosis_json,
                    entry.smoke_summary_json,
                    entry.readiness_summary_json,
                    entry.handoff_summary_json,
                    entry.product_surface_summary_json,
                )
            ),
        ),
    )
    if overlap_error:
        print(f"[trino-product-surface-audit] rejected: {overlap_error}", file=sys.stderr)
        return False
    for index, entry in enumerate(entries, start=1):
        if entry.diagnosis_json is None:
            result.input_count += 1
            add_issue(
                result,
                "handoff_diagnosis_artifact_missing",
                "Product-surface handoff suite audit requires every entry to include a compact diagnosis artifact.",
                input_index=index,
            )
            continue
        audit_inputs(
            result,
            (entry.boundary_json,),
            diagnosis_jsons=(entry.diagnosis_json,),
            sample_index=None,
            start_index=index,
        )
        if entry.product_surface_summary_json is not None:
            try:
                product_surface_summary = load_json_object(
                    entry.product_surface_summary_json,
                    input_label="product-surface summary JSON input",
                )
            except TrinoProductSurfaceAuditInputError:
                add_issue(
                    result,
                    "product_surface_summary_unreadable",
                    "Stored Trino product-surface summary artifact could not be read safely.",
                    input_index=index,
                )
                continue
            audit_product_surface_summary_payload(
                result,
                product_surface_summary,
                boundary_json=entry.boundary_json,
                diagnosis_json=entry.diagnosis_json,
                input_index=index,
            )
    return True


def audit_product_surface_summary_payload(
    result: TrinoProductSurfaceAuditResult,
    summary: Mapping[str, Any],
    *,
    boundary_json: Path,
    diagnosis_json: Path,
    input_index: int,
) -> None:
    text = json.dumps(summary, ensure_ascii=True, sort_keys=True)
    for category in raw_text_issue_categories(text):
        add_issue(
            result,
            "product_surface_summary_raw_boundary",
            f"Trino product-surface summary artifact contains raw-like {category} content.",
            input_index=input_index,
        )
    if contains_raw_sql_like_text(text):
        add_issue(
            result,
            "product_surface_summary_sql_like_text",
            "Trino product-surface summary artifact contains SQL-like text.",
            input_index=input_index,
        )
    if validate_report_internal_fingerprints(text):
        add_issue(
            result,
            "product_surface_summary_internal_fingerprint",
            "Trino product-surface summary artifact contains internal report fingerprints.",
            input_index=input_index,
        )
    if (
        redact_browser_display_text(
            text,
            redact_field_names=True,
            redact_artifact_markers=True,
            redact_model_names=True,
            redact_sql_snippets=True,
            redact_infrastructure=True,
        )
        != text
    ):
        add_issue(
            result,
            "product_surface_summary_browser_redaction_required",
            "Trino product-surface summary artifact is not browser-display safe.",
            input_index=input_index,
        )

    expected = expected_product_surface_summary(boundary_json, diagnosis_json)
    if json_normalized_payload(summary) != json_normalized_payload(expected):
        add_issue(
            result,
            "product_surface_summary_mismatch",
            "Stored Trino product-surface summary must match deterministic compact output.",
            input_index=input_index,
        )


def expected_product_surface_summary(boundary_json: Path, diagnosis_json: Path) -> dict[str, Any]:
    expected_result = TrinoProductSurfaceAuditResult()
    audit_registry_surface(expected_result)
    audit_product_surface_source_boundaries(expected_result)
    audit_inputs(
        expected_result,
        (boundary_json,),
        diagnosis_jsons=(diagnosis_json,),
        sample_index=None,
    )
    status = "ok" if expected_result.ok else "failed"
    return product_surface_summary_payload(expected_result, status=status)


def audit_diagnosis_payload(
    result: TrinoProductSurfaceAuditResult,
    diagnosis: Mapping[str, Any],
    *,
    input_index: int,
    expected_diagnosis: Mapping[str, Any],
) -> None:
    text = json.dumps(diagnosis, ensure_ascii=True, sort_keys=True)
    for category in raw_text_issue_categories(text):
        add_issue(
            result,
            f"diagnosis_{category}",
            "Trino compact diagnosis artifact contains raw-like text.",
            input_index=input_index,
        )
    if contains_raw_sql_like_text(text):
        add_issue(
            result,
            "diagnosis_sql_like_text",
            "Trino compact diagnosis artifact contains SQL-like text.",
            input_index=input_index,
        )
    if validate_report_internal_fingerprints(text):
        add_issue(
            result,
            "diagnosis_internal_fingerprint",
            "Trino compact diagnosis artifact contains internal report fingerprints.",
            input_index=input_index,
        )
    if (
        redact_browser_display_text(
            text,
            redact_field_names=True,
            redact_artifact_markers=True,
            redact_model_names=True,
            redact_sql_snippets=True,
            redact_infrastructure=True,
        )
        != text
    ):
        add_issue(
            result,
            "diagnosis_browser_redaction_required",
            "Trino compact diagnosis artifact is not browser-display safe.",
            input_index=input_index,
        )

    if diagnosis.get("schema_version") != TRINO_COMPACT_DIAGNOSIS_SCHEMA_VERSION:
        add_issue(
            result,
            "diagnosis_schema_mismatch",
            "Trino compact diagnosis schema version is not accepted.",
            input_index=input_index,
        )
    if diagnosis.get("engine") != "trino":
        add_issue(
            result,
            "diagnosis_engine_mismatch",
            "Trino compact diagnosis must stay on engine=trino.",
            input_index=input_index,
        )
    if diagnosis.get("support_status") != TRINO_COMPACT_DIAGNOSIS_SUPPORT_STATUS:
        add_issue(
            result,
            "diagnosis_support_status_drift",
            "Trino compact diagnosis must stay below product support.",
            input_index=input_index,
        )
    audit_no_claim_boundary(result, diagnosis, input_index=input_index)
    audit_diagnostic_lane(
        result,
        diagnosis,
        input_index=input_index,
        expected_diagnosis=expected_diagnosis,
    )
    audit_attention_and_limitations(result, diagnosis, input_index=input_index)


def audit_no_claim_boundary(
    result: TrinoProductSurfaceAuditResult,
    diagnosis: Mapping[str, Any],
    *,
    input_index: int,
) -> None:
    boundary = diagnosis.get("diagnosis_boundary")
    if not isinstance(boundary, Mapping):
        add_issue(
            result,
            "missing_diagnosis_boundary",
            "Trino compact diagnosis must publish an explicit no-claim boundary.",
            input_index=input_index,
        )
        return
    for key, expected in EXPECTED_DIAGNOSIS_BOUNDARY.items():
        if boundary.get(key) != expected:
            add_issue(
                result,
                "diagnosis_boundary_drift",
                "Trino compact diagnosis boundary no longer matches the no-product contract.",
                input_index=input_index,
            )


def audit_attention_and_limitations(
    result: TrinoProductSurfaceAuditResult,
    diagnosis: Mapping[str, Any],
    *,
    input_index: int,
) -> None:
    attention_areas = list_of_mappings(diagnosis.get("attention_areas"))
    result.attention_area_count += len(attention_areas)
    for area in attention_areas:
        if safe_label(area.get("state")) == "supported":
            result.supported_attention_area_count += 1
    limitations = list_of_mappings(diagnosis.get("limitations"))
    result.limitation_count += len(limitations)
    limitation_ids = {safe_label(limitation.get("id")) for limitation in limitations}
    missing = REQUIRED_TRINO_LIMITATION_IDS - limitation_ids
    if missing:
        add_issue(
            result,
            "missing_product_surface_limitation",
            "Trino compact diagnosis is missing a required product-surface limitation.",
            input_index=input_index,
        )


def audit_diagnostic_lane(
    result: TrinoProductSurfaceAuditResult,
    diagnosis: Mapping[str, Any],
    *,
    input_index: int,
    expected_diagnosis: Mapping[str, Any],
) -> None:
    lane = diagnosis.get("diagnostic_lane")
    if not isinstance(lane, Mapping):
        add_issue(
            result,
            "diagnostic_lane_missing",
            "Trino compact diagnosis must keep a diagnostic-lane boundary contract.",
            input_index=input_index,
        )
        return
    result.diagnostic_lane_checked_count += 1
    source_granularity = safe_label(lane.get("source_granularity"))
    evidence_readiness = safe_label(lane.get("evidence_readiness"))
    verification_scope = safe_label(lane.get("verification_scope"))
    result.diagnostic_lane_source_granularity_counts[source_granularity] += 1
    result.diagnostic_lane_readiness_counts[evidence_readiness] += 1
    result.diagnostic_lane_verification_scope_counts[verification_scope] += 1

    expected_values = {
        "schema_version": TRINO_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
        "lane": TRINO_COMPACT_DIAGNOSTIC_LANE_NAME,
        "promotion_status": "preview_only",
    }
    for key, expected in expected_values.items():
        if lane.get(key) != expected:
            add_issue(
                result,
                "diagnostic_lane_product_promotion_drift",
                "Trino diagnostic lane must stay preview-only and below product support.",
                input_index=input_index,
            )
    if source_granularity not in ALLOWED_DIAGNOSTIC_LANE_SOURCE_GRANULARITIES:
        add_issue(
            result,
            "diagnostic_lane_source_granularity_drift",
            "Trino diagnostic lane source granularity is outside the compact preview contract.",
            input_index=input_index,
        )
    if evidence_readiness not in ALLOWED_DIAGNOSTIC_LANE_READINESS:
        add_issue(
            result,
            "diagnostic_lane_readiness_drift",
            "Trino diagnostic lane readiness is outside the compact preview contract.",
            input_index=input_index,
        )
    if verification_scope not in ALLOWED_DIAGNOSTIC_LANE_VERIFICATION_SCOPES:
        add_issue(
            result,
            "diagnostic_lane_verification_scope_drift",
            "Trino diagnostic lane verification scope is outside the compact preview contract.",
            input_index=input_index,
        )

    expected_lane = mapping(expected_diagnosis.get("diagnostic_lane"))
    expected_source_granularity = expected_lane.get("source_granularity")
    expected_readiness = expected_lane.get("evidence_readiness")
    expected_verification_scope = expected_lane.get("verification_scope")
    if (
        expected_source_granularity is not None
        and source_granularity != expected_source_granularity
    ):
        add_issue(
            result,
            "diagnostic_lane_source_granularity_drift",
            "Trino diagnostic lane source granularity must match deterministic boundary evidence.",
            input_index=input_index,
        )
    if expected_readiness is not None and evidence_readiness != expected_readiness:
        add_issue(
            result,
            "diagnostic_lane_readiness_drift",
            "Trino diagnostic lane readiness must match deterministic boundary evidence.",
            input_index=input_index,
        )
    if (
        expected_verification_scope is not None
        and verification_scope != expected_verification_scope
    ):
        add_issue(
            result,
            "diagnostic_lane_verification_scope_drift",
            "Trino diagnostic lane verification scope must match deterministic boundary evidence.",
            input_index=input_index,
        )

    expected_supported_attention_count = supported_attention_area_count(expected_diagnosis)
    lane_supported_attention_count = lane.get("supported_attention_area_count")
    if (
        not isinstance(lane_supported_attention_count, int)
        or isinstance(lane_supported_attention_count, bool)
        or lane_supported_attention_count != expected_supported_attention_count
    ):
        add_issue(
            result,
            "diagnostic_lane_attention_count_drift",
            "Trino diagnostic lane supported-attention count must match deterministic diagnosis evidence.",
            input_index=input_index,
        )

    expected_fact_state_counts = safe_fact_state_counts(expected_lane.get("fact_state_counts"))
    result.diagnostic_lane_fact_state_counts.update(expected_fact_state_counts)
    if lane.get("fact_state_counts") != expected_fact_state_counts:
        add_issue(
            result,
            "diagnostic_lane_fact_state_count_drift",
            "Trino diagnostic lane fact-state counts must match deterministic boundary evidence.",
            input_index=input_index,
        )

    expected_verification = expected_diagnostic_lane_verification_scope(
        source_granularity,
        evidence_readiness,
    )
    if expected_verification is not None and verification_scope != expected_verification:
        add_issue(
            result,
            "diagnostic_lane_verification_scope_drift",
            "Trino diagnostic lane verification scope must match source granularity and readiness.",
            input_index=input_index,
        )

    required_gates = lane.get("required_gates")
    if not isinstance(required_gates, Mapping) or required_gates != EXPECTED_DIAGNOSTIC_LANE_GATES:
        add_issue(
            result,
            "diagnostic_lane_gate_drift",
            "Trino diagnostic lane must keep readiness and product-surface gates.",
            input_index=input_index,
        )


def audit_registry_surface(result: TrinoProductSurfaceAuditResult) -> None:
    registered_post_paths = (*STATIC_POST_PATHS, *PREVIEW_WEB_POST_PATHS)
    trino_post_paths = {path for path in registered_post_paths if "trino" in path.lower()}
    unexpected_paths = trino_post_paths - ALLOWED_TRINO_POST_PATHS
    if unexpected_paths:
        add_issue(
            result,
            "unexpected_trino_post_route",
            "Trino has a POST route outside the isolated compact-diagnosis surface.",
        )
    missing_paths = ALLOWED_TRINO_POST_PATHS - trino_post_paths
    if missing_paths:
        add_issue(
            result,
            "missing_trino_post_route",
            "Trino compact diagnosis is missing from the isolated preview route registry.",
        )
    trino_preview_surfaces = tuple(
        surface for surface in PREVIEW_WEB_SURFACES if surface.engine.lower() == "trino"
    )
    unexpected_preview_surfaces = tuple(
        surface
        for surface in trino_preview_surfaces
        if surface.surface_id != "compact_diagnosis"
        or surface.route_path not in ALLOWED_TRINO_POST_PATHS
    )
    if unexpected_preview_surfaces:
        add_issue(
            result,
            "unexpected_trino_preview_surface",
            "Trino preview registry contains a surface outside isolated compact diagnosis.",
        )
    if any(surface.product_surface_allowed for surface in trino_preview_surfaces):
        add_issue(
            result,
            "trino_preview_surface_product_allowed",
            "Trino preview registry must not mark isolated preview routes as product surfaces.",
        )
    trino_roles = {
        role
        for role, spec in COMMAND_SPECS.items()
        if "trino" in role.lower() or "trino" in spec.console_script.lower()
    }
    unexpected_roles = trino_roles - ALLOWED_TRINO_COMMAND_ROLES
    if unexpected_roles:
        add_issue(
            result,
            "unexpected_trino_cli_role",
            "Trino has a CLI role outside the bounded preview allowlist.",
        )
    for role in trino_roles:
        if any(fragment in role for fragment in FORBIDDEN_TRINO_PRODUCT_ROLE_FRAGMENTS):
            add_issue(
                result,
                "trino_product_cli_role_present",
                "Trino has a CLI role shaped like a production workflow.",
            )


def audit_product_surface_source_boundaries(
    result: TrinoProductSurfaceAuditResult,
    *,
    targets: Iterable[ProductSurfaceSourceTarget] | None = None,
) -> None:
    source_targets = tuple(targets) if targets is not None else product_surface_source_targets()
    for target in source_targets:
        result.product_source_module_checked_count += 1
        try:
            source = target.path.read_text(encoding="utf-8")
        except OSError:
            add_issue(
                result,
                "product_surface_source_unreadable",
                "One product-surface source module could not be inspected.",
            )
            continue
        try:
            imported_names = source_import_names(target.module_name, source)
        except SyntaxError:
            add_issue(
                result,
                "product_surface_source_unparseable",
                "One product-surface source module could not be parsed for imports.",
            )
            continue
        if any(
            is_forbidden_trino_product_source_import(target.module_name, imported_name)
            for imported_name in imported_names
        ):
            add_issue(
                result,
                "trino_product_surface_source_import",
                (
                    "A product-surface source module imports a Trino preview module "
                    "outside the isolated compact surface."
                ),
            )
        result.product_source_allowed_trino_import_count += sum(
            1
            for imported_name in imported_names
            if is_allowed_trino_product_source_import_root(target.module_name, imported_name)
        )


def audit_trino_beta_query_module_boundary(
    result: TrinoProductSurfaceAuditResult,
    *,
    target: ProductSurfaceSourceTarget | None = None,
) -> None:
    if target is None:
        target = ProductSurfaceSourceTarget(
            module_name="query_doctor.web.trino_beta_query",
            path=ROOT / "query_doctor" / "web" / "trino_beta_query.py",
        )
    try:
        source = target.path.read_text(encoding="utf-8")
    except OSError:
        add_issue(
            result,
            "trino_beta_query_module_unreadable",
            "The Trino Beta Query ID module could not be inspected.",
        )
        return
    try:
        imported_names = source_import_names(target.module_name, source)
    except SyntaxError:
        add_issue(
            result,
            "trino_beta_query_module_unparseable",
            "The Trino Beta Query ID module could not be parsed for imports.",
        )
        return
    if any(
        is_forbidden_import_prefix(imported_name, FORBIDDEN_TRINO_BETA_QUERY_IMPORT_PREFIXES)
        for imported_name in imported_names
    ):
        add_issue(
            result,
            "trino_beta_query_forbidden_import",
            (
                "The Trino Beta Query ID module imports report, optimizer, CLI, "
                "subprocess, or product action dependencies."
            ),
        )


def audit_trino_details_module_boundary(
    result: TrinoProductSurfaceAuditResult,
    *,
    target: ProductSurfaceSourceTarget | None = None,
) -> None:
    if target is None:
        target = ProductSurfaceSourceTarget(
            module_name="query_doctor.web.trino_details",
            path=ROOT / "query_doctor" / "web" / "trino_details.py",
        )
    try:
        source = target.path.read_text(encoding="utf-8")
    except OSError:
        add_issue(
            result,
            "trino_details_module_unreadable",
            "The Trino Details module could not be inspected.",
        )
        return
    try:
        imported_names = source_import_names(target.module_name, source)
    except SyntaxError:
        add_issue(
            result,
            "trino_details_module_unparseable",
            "The Trino Details module could not be parsed for imports.",
        )
        return
    if any(
        is_forbidden_import_prefix(imported_name, FORBIDDEN_TRINO_DETAILS_IMPORT_PREFIXES)
        for imported_name in imported_names
    ):
        add_issue(
            result,
            "trino_details_forbidden_import",
            (
                "The Trino Details module imports CLI, subprocess, optimizer, "
                "or selected-case action dependencies."
            ),
        )
    if any(snippet in source for snippet in FORBIDDEN_TRINO_DETAILS_SURFACE_SNIPPETS):
        add_issue(
            result,
            "trino_details_forbidden_surface_marker",
            (
                "The Trino Details module contains report, optimizer, raw source, "
                "or selected-case action surface markers."
            ),
        )


def audit_trino_report_module_boundary(
    result: TrinoProductSurfaceAuditResult,
    *,
    target: ProductSurfaceSourceTarget | None = None,
) -> None:
    if target is None:
        target = ProductSurfaceSourceTarget(
            module_name="query_doctor.web.trino_report",
            path=ROOT / "query_doctor" / "web" / "trino_report.py",
        )
    try:
        source = target.path.read_text(encoding="utf-8")
    except OSError:
        add_issue(
            result,
            "trino_report_module_unreadable",
            "The Trino Python Report module could not be inspected.",
        )
        return
    try:
        imported_names = source_import_names(target.module_name, source)
    except SyntaxError:
        add_issue(
            result,
            "trino_report_module_unparseable",
            "The Trino Python Report module could not be parsed for imports.",
        )
        return
    if any(
        is_forbidden_import_prefix(imported_name, FORBIDDEN_TRINO_REPORT_IMPORT_PREFIXES)
        for imported_name in imported_names
    ):
        add_issue(
            result,
            "trino_report_forbidden_import",
            (
                "The Trino Python Report module imports CLI, subprocess, optimizer, "
                "selected-case actions, or trusted Impala report artifacts."
            ),
        )
    if any(snippet in source for snippet in FORBIDDEN_TRINO_REPORT_SURFACE_SNIPPETS):
        add_issue(
            result,
            "trino_report_forbidden_surface_marker",
            (
                "The Trino Python Report module contains optimizer, LLM, selected-case "
                "action, or legacy report route surface markers."
            ),
        )


def audit_trino_guidance_module_boundary(
    result: TrinoProductSurfaceAuditResult,
    *,
    target: ProductSurfaceSourceTarget | None = None,
) -> None:
    if target is None:
        target = ProductSurfaceSourceTarget(
            module_name="query_doctor.web.trino_guidance",
            path=ROOT / "query_doctor" / "web" / "trino_guidance.py",
        )
    try:
        source = target.path.read_text(encoding="utf-8")
    except OSError:
        add_issue(
            result,
            "trino_guidance_module_unreadable",
            "The Trino optimizer guidance module could not be inspected.",
        )
        return
    try:
        imported_names = source_import_names(target.module_name, source)
    except SyntaxError:
        add_issue(
            result,
            "trino_guidance_module_unparseable",
            "The Trino optimizer guidance module could not be parsed for imports.",
        )
        return
    if any(
        is_forbidden_import_prefix(imported_name, FORBIDDEN_TRINO_GUIDANCE_IMPORT_PREFIXES)
        for imported_name in imported_names
    ):
        add_issue(
            result,
            "trino_guidance_forbidden_import",
            (
                "The Trino optimizer guidance module imports CLI, subprocess, optimizer, "
                "selected-case actions, or trusted Impala report artifacts."
            ),
        )
    if any(snippet in source for snippet in FORBIDDEN_TRINO_GUIDANCE_SURFACE_SNIPPETS):
        add_issue(
            result,
            "trino_guidance_forbidden_surface_marker",
            (
                "The Trino optimizer guidance module contains optimizer-job, LLM, "
                "selected-case action, or legacy route surface markers."
            ),
        )


def audit_trino_beta_ui_modules_boundary(result: TrinoProductSurfaceAuditResult) -> None:
    for target in trino_beta_ui_module_targets():
        audit_trino_beta_ui_module_boundary(result, target=target)


def trino_beta_ui_module_targets() -> tuple[ProductSurfaceSourceTarget, ...]:
    return (
        ProductSurfaceSourceTarget(
            module_name="query_doctor.web.ui.trino",
            path=ROOT / "query_doctor" / "web" / "ui" / "trino.py",
        ),
        ProductSurfaceSourceTarget(
            module_name="query_doctor.web.ui.trino_demo",
            path=ROOT / "query_doctor" / "web" / "ui" / "trino_demo.py",
        ),
    )


def audit_trino_beta_ui_module_boundary(
    result: TrinoProductSurfaceAuditResult,
    *,
    target: ProductSurfaceSourceTarget | None = None,
) -> None:
    if target is None:
        target = ProductSurfaceSourceTarget(
            module_name="query_doctor.web.ui.trino",
            path=ROOT / "query_doctor" / "web" / "ui" / "trino.py",
        )
    try:
        source = target.path.read_text(encoding="utf-8")
    except OSError:
        add_issue(
            result,
            "trino_beta_ui_module_unreadable",
            "The Trino Beta UI module could not be inspected.",
        )
        return
    try:
        imported_names = source_import_names(target.module_name, source)
    except SyntaxError:
        add_issue(
            result,
            "trino_beta_ui_module_unparseable",
            "The Trino Beta UI module could not be parsed for imports.",
        )
        return
    if any(
        is_forbidden_import_prefix(imported_name, FORBIDDEN_TRINO_BETA_UI_IMPORT_PREFIXES)
        for imported_name in imported_names
    ):
        add_issue(
            result,
            "trino_beta_ui_forbidden_import",
            (
                "The Trino Beta UI module imports Details, report, optimizer, "
                "or product action rendering dependencies."
            ),
        )
    if any(snippet in source for snippet in FORBIDDEN_TRINO_BETA_UI_SURFACE_SNIPPETS):
        add_issue(
            result,
            "trino_beta_ui_forbidden_surface_marker",
            (
                "The Trino Beta UI module contains Details, report, optimizer, "
                "or selected-case action surface markers."
            ),
        )


def audit_public_trino_claim_boundaries(
    result: TrinoProductSurfaceAuditResult,
    *,
    paths: Iterable[Path] | None = None,
) -> None:
    claim_paths = tuple(paths) if paths is not None else TRINO_PUBLIC_CLAIM_PATHS
    aggregate_text_parts: list[str] = []
    for path in claim_paths:
        result.public_claim_surface_checked_count += 1
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            add_issue(
                result,
                "trino_public_claim_surface_unreadable",
                "One public Trino claim surface could not be inspected.",
            )
            continue
        normalized = " ".join(text.split())
        aggregate_text_parts.append(normalized)
        if any(fragment in normalized for fragment in FORBIDDEN_TRINO_PUBLIC_CLAIM_FRAGMENTS):
            add_issue(
                result,
                "trino_public_forbidden_support_claim",
                "A public Trino claim surface contains wording shaped like unsupported product support.",
            )
    aggregate_text = " ".join(aggregate_text_parts)
    missing_required = [
        fragment
        for fragment in REQUIRED_TRINO_PUBLIC_CLAIM_FRAGMENTS
        if fragment not in aggregate_text
    ]
    if missing_required:
        add_issue(
            result,
            "trino_public_claim_boundary_incomplete",
            (
                "The public Trino claim surfaces are missing required local-production "
                "or blocked-surface wording."
            ),
        )


def product_surface_source_targets() -> tuple[ProductSurfaceSourceTarget, ...]:
    targets: list[ProductSurfaceSourceTarget] = []
    for root in PRODUCT_SURFACE_SOURCE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            module_name = module_name_for_source_path(path)
            if module_name in TRINO_PRODUCT_SOURCE_EXEMPT_MODULES:
                continue
            targets.append(ProductSurfaceSourceTarget(module_name=module_name, path=path))
    return tuple(targets)


def module_name_for_source_path(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    return ".".join(relative.parts)


def source_import_names(module_name: str, source: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_module = resolve_import_from_module(module_name, node)
            if imported_module:
                imports.append(imported_module)
                imports.extend(
                    f"{imported_module}.{alias.name}" for alias in node.names if alias.name != "*"
                )
    return tuple(imports)


def resolve_import_from_module(module_name: str, node: ast.ImportFrom) -> str:
    if node.level <= 0:
        return node.module or ""
    current_parts = module_name.split(".")
    if node.level > len(current_parts):
        return node.module or ""
    package_parts = current_parts[: -node.level]
    if node.module:
        package_parts.extend(node.module.split("."))
    return ".".join(part for part in package_parts if part)


def is_forbidden_trino_product_source_import(
    module_name: str,
    imported_name: str,
) -> bool:
    if not is_trino_preview_import(imported_name):
        return False
    if module_name in TRINO_PRODUCT_SOURCE_EXEMPT_MODULES:
        return False
    allowed_prefixes = ALLOWED_TRINO_PRODUCT_SOURCE_IMPORT_PREFIXES.get(module_name, ())
    return not any(
        imported_name == prefix or imported_name.startswith(f"{prefix}.")
        for prefix in allowed_prefixes
    )


def is_allowed_trino_product_source_import_root(
    module_name: str,
    imported_name: str,
) -> bool:
    if not is_trino_preview_import(imported_name):
        return False
    if module_name in TRINO_PRODUCT_SOURCE_EXEMPT_MODULES:
        return False
    return imported_name in ALLOWED_TRINO_PRODUCT_SOURCE_IMPORT_PREFIXES.get(module_name, ())


def is_trino_preview_import(imported_name: str) -> bool:
    return any(
        imported_name == prefix or imported_name.startswith(prefix)
        for prefix in FORBIDDEN_TRINO_SOURCE_IMPORT_PREFIXES
    )


def is_forbidden_import_prefix(imported_name: str, prefixes: Iterable[str]) -> bool:
    return any(
        imported_name == prefix or imported_name.startswith(f"{prefix}.") for prefix in prefixes
    )


def product_surface_summary_payload(
    result: TrinoProductSurfaceAuditResult,
    *,
    status: str,
) -> dict[str, Any]:
    return {
        "summary_kind": TRINO_PRODUCT_SURFACE_AUDIT_SUMMARY_KIND,
        "status": status,
        "mode": "trino_product_surface_boundary",
        "boundary": {
            "product_surface": TRINO_PRODUCT_SURFACE_STATUS,
            "support_claim": TRINO_SUPPORT_CLAIM_STATUS,
            "details_case_view": TRINO_DETAILS_CASE_VIEW_STATUS,
            "python_report": TRINO_PYTHON_REPORT_STATUS,
            "optimizer_guidance": TRINO_OPTIMIZER_GUIDANCE_STATUS,
            "llm_reports": TRINO_LLM_REPORTS_STATUS,
            "trusted_reports": "python_report_only",
            "optimizer_behavior": TRINO_OPTIMIZER_BEHAVIOR_STATUS,
            "live_recent_scan": "retained_query_list_local_production",
            "live_known_query_diagnosis": "one_query_pruned_query_info_local_production",
            "trino_sql_execution": "not_performed",
        },
        "counts": {
            "boundary_json_count": result.input_count,
            "diagnosis_json_checked_count": result.diagnosis_artifact_checked_count,
            "product_source_modules_checked_count": result.product_source_module_checked_count,
            "product_source_allowed_trino_import_count": (
                result.product_source_allowed_trino_import_count
            ),
            "public_claim_surface_checked_count": result.public_claim_surface_checked_count,
            "attention_area_count": result.attention_area_count,
            "supported_attention_area_count": result.supported_attention_area_count,
            "diagnostic_lane_checked_count": result.diagnostic_lane_checked_count,
            "limitation_count": result.limitation_count,
        },
        "diagnostic_lane": {
            "source_granularity": counter_payload(result.diagnostic_lane_source_granularity_counts),
            "evidence_readiness": counter_payload(result.diagnostic_lane_readiness_counts),
            "verification_scope": counter_payload(result.diagnostic_lane_verification_scope_counts),
            "fact_states": counter_payload(result.diagnostic_lane_fact_state_counts),
        },
        "registry": {
            "trino_product_routes": TRINO_PRODUCT_SURFACE_STATUS,
            "trino_product_cli": "blocked",
            "details_python_report_guidance_source_imports": TRINO_PYTHON_REPORT_STATUS,
            "allowed_web_post_paths": sorted(ALLOWED_TRINO_POST_PATHS),
            "allowed_cli_roles": sorted(ALLOWED_TRINO_COMMAND_ROLES),
        },
        "issues": {
            "counts": counter_payload(result.issue_counts),
            "items": [
                {
                    "input_index": input_index,
                    "category": issue.category,
                    "message": issue.message,
                }
                for input_index, issue in result.issues
            ],
        },
    }


def load_json_object(path: Path, *, input_label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TrinoProductSurfaceAuditInputError(f"{input_label} could not be read") from exc
    except json.JSONDecodeError as exc:
        raise TrinoProductSurfaceAuditInputError(f"{input_label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise TrinoProductSurfaceAuditInputError(f"{input_label} must be an object")
    return payload


def json_normalized_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return the artifact shape after JSON serialization."""

    return json.loads(json.dumps(payload, ensure_ascii=True, sort_keys=True))


def has_metadata_summary_facts(payload: Mapping[str, Any]) -> bool:
    fact_groups = payload.get("fact_groups")
    if not isinstance(fact_groups, Mapping):
        return False
    for facts in fact_groups.values():
        if not isinstance(facts, list):
            continue
        for fact in facts:
            if isinstance(fact, Mapping) and fact.get("id") in METADATA_SUMMARY_FACT_IDS:
                return True
    return False


def supported_attention_area_count(diagnosis: Mapping[str, Any]) -> int:
    return sum(
        1
        for area in list_of_mappings(diagnosis.get("attention_areas"))
        if safe_label(area.get("state")) == "supported"
    )


def safe_fact_state_counts(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    counts: dict[str, int] = {}
    for state in ("not_observed", "supported", "unknown"):
        count = value.get(state)
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            counts[state] = count
    return counts


def expected_diagnostic_lane_verification_scope(
    source_granularity: str,
    evidence_readiness: str,
) -> str | None:
    if evidence_readiness == TRINO_LANE_READINESS_COVERAGE_UNKNOWN:
        return "source_contract_review"
    if source_granularity == TRINO_SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST:
        return "representative_query_selection"
    if source_granularity == TRINO_SOURCE_GRANULARITY_ONE_QUERY_BOUNDARY:
        return "comparable_one_query_rerun"
    return None


def write_summary_or_reject(path: Path | None, payload: Mapping[str, Any]) -> bool:
    if path is None:
        return True
    text = ascii_json_artifact_text(payload)
    if raw_text_issue_categories(text):
        print(
            "[trino-product-surface-audit] rejected: summary JSON would contain raw-like text",
            file=sys.stderr,
        )
        return False
    try:
        write_ascii_json_artifact(path, payload)
    except OSError:
        print(
            "[trino-product-surface-audit] rejected: summary JSON could not be written",
            file=sys.stderr,
        )
        return False
    return True


def reject_summary_output_overlap(
    summary_json: Path | None,
    inputs: Iterable[Path | None],
) -> str | None:
    return output_overlaps_inputs_error(
        summary_json,
        inputs,
        message="summary JSON output must differ from every input artifact",
    )


def add_issue(
    result: TrinoProductSurfaceAuditResult,
    category: str,
    message: str,
    *,
    input_index: int | None = None,
) -> None:
    issue = TrinoProductSurfaceAuditIssue(category=category, message=message)
    result.issue_counts[category] += 1
    result.issues.append((input_index, issue))


def print_issues(result: TrinoProductSurfaceAuditResult, *, limit: int) -> None:
    if not result.issues:
        print("Issues: none")
        return
    print("Issues:")
    for input_index, issue in result.issues[:limit]:
        prefix = "registry" if input_index is None else f"input_{input_index}"
        print(f"- {prefix}: {issue.category}: {issue.message}")
    remaining = len(result.issues) - limit
    if remaining > 0:
        print(f"- ... {remaining} more issue(s)")


def list_of_mappings(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def safe_label(value: object) -> str:
    if isinstance(value, str) and value.strip():
        label = value.strip()
        if raw_text_issue_categories(label):
            return "redacted"
        return label
    return "unknown"


def positive_int(value: str) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def non_negative_int(value: str) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a non-negative integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
