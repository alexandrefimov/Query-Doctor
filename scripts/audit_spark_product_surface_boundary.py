#!/usr/bin/env python3
"""Audit Spark compact artifacts against product-surface boundaries."""

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

from query_doctor.analyzer.engine_facts import EngineFactContractError  # noqa: E402
from query_doctor.report.safety_validation import (  # noqa: E402
    contains_raw_sql_like_text,
    validate_report_internal_fingerprints,
)
from query_doctor.safety.browser_display import redact_browser_display_text  # noqa: E402
from query_doctor.spark.diagnosis import (  # noqa: E402
    SPARK_COMPACT_DIAGNOSIS_SCHEMA_VERSION,
    SPARK_COMPACT_DIAGNOSTIC_LANE_NAME,
    SPARK_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
    build_spark_compact_diagnosis,
    safe_fact_state_counts,
)
from query_doctor.web.preview_surfaces import (  # noqa: E402
    PREVIEW_WEB_POST_PATHS,
    PREVIEW_WEB_POST_SURFACES,
)
from query_doctor.web.routes import STATIC_POST_PATHS  # noqa: E402
from scripts.audit_spark_compact_readiness import (  # noqa: E402
    EXPECTED_DIAGNOSIS_BOUNDARY,
    EXPECTED_SUPPORT_STATUS,
    REQUIRED_SPARK_LIMITATION_IDS,
    SparkCompactReadinessBatchResult,
    SparkCompactReadinessInputError,
    SparkCompactReadinessResult,
    audit_compact_payload,
    audit_one_application_handoff_manifest,
    counter_payload,
    json_normalized_payload,
    load_json_object,
    one_application_handoff_manifest_input_paths,
    raw_text_violations,
    reject_summary_output_any_overlap,
    validate_one_application_handoff_manifest,
)
from scripts.audit_spark_support_boundary import (  # noqa: E402
    audit_spark_support_boundary,
)


SPARK_PRODUCT_SURFACE_AUDIT_SUMMARY_KIND = "spark_product_surface_boundary_audit_v1"
SPARK_PRODUCT_SURFACE_STATUS = "not_promoted"
ALLOWED_SPARK_POST_PATHS = frozenset({"/spark/compact-diagnosis"})
SPARK_PRODUCT_SURFACE_BOUNDARY = {
    "product_surface": SPARK_PRODUCT_SURFACE_STATUS,
    "support_claim": "not_claimed",
    "details_trusted_report_surface": "not_wired",
    "trusted_reports": "not_wired",
    "optimizer_behavior": "not_wired",
    "live_recent_scan": "not_wired",
    "live_known_query_diagnosis": "not_wired",
    "spark_job_execution": "not_performed",
}


@dataclass(frozen=True)
class SparkProductSurfaceAuditIssue:
    category: str
    message: str


@dataclass
class SparkProductSurfaceAuditResult:
    input_count: int = 0
    compact_readiness_checked_count: int = 0
    diagnosis_artifact_checked_count: int = 0
    diagnostic_lane_checked_count: int = 0
    static_support_check_count: int = 0
    attention_area_count: int = 0
    supported_attention_area_count: int = 0
    limitation_count: int = 0
    source_warning_count: int = 0
    diagnostic_lane_readiness_counts: Counter[str] = field(default_factory=Counter)
    diagnostic_lane_source_granularity_counts: Counter[str] = field(default_factory=Counter)
    diagnostic_lane_verification_scope_counts: Counter[str] = field(default_factory=Counter)
    fact_state_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[tuple[int | None, SparkProductSurfaceAuditIssue]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issue_counts


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check retained raw-free Spark compact diagnosis artifacts against the current "
            "no-product-surface boundary. This does not promote Spark to Recent, Details, "
            "trusted reports, optimizer, live Query ID diagnosis, job execution, or support."
        )
    )
    parser.add_argument(
        "compact_json",
        nargs="*",
        type=Path,
        help="Accepted Spark compact JSON input. Repeat for a retained compact suite.",
    )
    parser.add_argument(
        "--diagnosis-json",
        action="append",
        type=Path,
        default=[],
        help=(
            "Optional deterministic Spark compact diagnosis JSON to compare with the matching "
            "compact input. Repeat once per compact input."
        ),
    )
    parser.add_argument(
        "--one-application-handoff-suite-manifest",
        type=Path,
        default=None,
        help=(
            "Optional spark_one_application_handoff_suite_v1 manifest whose entries reference "
            "raw-free compact, diagnosis, boundary, and optional summary artifacts."
        ),
    )
    parser.add_argument(
        "--registry-only",
        action="store_true",
        help="Run only the static support and preview route product-surface audit.",
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
    selected_inputs = sum(
        (
            bool(args.compact_json),
            args.one_application_handoff_suite_manifest is not None,
            args.registry_only,
        )
    )
    if selected_inputs != 1:
        print(
            "[spark-product-surface-audit] rejected: provide compact JSON, "
            "--one-application-handoff-suite-manifest, or --registry-only",
            file=sys.stderr,
        )
        return 2
    if args.registry_only and args.diagnosis_json:
        print(
            "[spark-product-surface-audit] rejected: --registry-only cannot use diagnosis inputs",
            file=sys.stderr,
        )
        return 2
    if args.one_application_handoff_suite_manifest is not None and args.diagnosis_json:
        print(
            "[spark-product-surface-audit] rejected: use manifest entry diagnosis_json values "
            "for handoff suite checks",
            file=sys.stderr,
        )
        return 2
    if args.diagnosis_json and len(args.diagnosis_json) != len(args.compact_json):
        print(
            "[spark-product-surface-audit] rejected: diagnosis JSON count must match compact "
            "JSON count",
            file=sys.stderr,
        )
        return 2

    input_paths: tuple[Path, ...] = ()
    if args.compact_json:
        input_paths = (*args.compact_json, *args.diagnosis_json)
    elif args.one_application_handoff_suite_manifest is not None:
        input_paths = one_application_handoff_manifest_input_paths(
            args.one_application_handoff_suite_manifest
        )
    overlap_error = reject_summary_output_any_overlap(args.summary_json, input_paths)
    if overlap_error:
        print(f"[spark-product-surface-audit] rejected: {overlap_error}", file=sys.stderr)
        return 2

    result = SparkProductSurfaceAuditResult()
    audit_static_support_boundary(result)
    audit_preview_route_boundary(result)
    if args.compact_json:
        audit_compact_inputs(
            result,
            args.compact_json,
            diagnosis_jsons=tuple(args.diagnosis_json),
        )
    elif args.one_application_handoff_suite_manifest is not None:
        if not audit_one_application_handoff_manifest_inputs(
            result,
            args.one_application_handoff_suite_manifest,
        ):
            return 2

    status = "ok" if result.ok else "failed"
    if not write_summary_or_reject(
        args.summary_json,
        product_surface_summary_payload(result, status=status),
    ):
        return 2

    print_result(result, status=status, limit=args.limit)
    return 0 if result.ok else 1


def audit_compact_inputs(
    result: SparkProductSurfaceAuditResult,
    compact_jsons: Iterable[Path],
    *,
    diagnosis_jsons: tuple[Path, ...],
) -> None:
    diagnosis_by_index = {index: path for index, path in enumerate(diagnosis_jsons, start=1)}
    for index, compact_json in enumerate(compact_jsons, start=1):
        result.input_count += 1
        try:
            compact_payload = load_json_object(compact_json)
        except SparkCompactReadinessInputError:
            add_issue(
                result,
                "compact_input_unreadable",
                "One Spark compact input could not be read or parsed safely.",
                input_index=index,
            )
            continue

        readiness = audit_compact_payload(compact_payload)
        add_readiness_result(result, readiness, input_index=index)
        try:
            expected_diagnosis = json_normalized_payload(
                build_spark_compact_diagnosis(compact_payload)
            )
        except EngineFactContractError:
            add_issue(
                result,
                "compact_diagnosis_invalid",
                "One Spark compact input could not produce deterministic compact diagnosis.",
                input_index=index,
            )
            continue

        diagnosis = expected_diagnosis
        diagnosis_json = diagnosis_by_index.get(index)
        if diagnosis_json is not None:
            try:
                diagnosis = load_json_object(diagnosis_json)
            except SparkCompactReadinessInputError:
                add_issue(
                    result,
                    "diagnosis_input_unreadable",
                    "One Spark diagnosis artifact could not be read or parsed safely.",
                    input_index=index,
                )
                audit_diagnosis_payload(result, expected_diagnosis, input_index=index)
                continue
            result.diagnosis_artifact_checked_count += 1
            if diagnosis != expected_diagnosis:
                add_issue(
                    result,
                    "diagnosis_artifact_mismatch",
                    "Stored Spark diagnosis artifact does not match deterministic compact output.",
                    input_index=index,
                )
        audit_diagnosis_payload(result, diagnosis, input_index=index)


def audit_one_application_handoff_manifest_inputs(
    result: SparkProductSurfaceAuditResult,
    manifest_json: Path,
) -> bool:
    batch = audit_one_application_handoff_manifest(manifest_json)
    add_readiness_batch(result, batch)
    try:
        manifest = load_json_object(manifest_json)
    except SparkCompactReadinessInputError:
        return True
    entry_batch = SparkCompactReadinessBatchResult()
    entries = validate_one_application_handoff_manifest(
        manifest,
        entry_batch,
        base_dir=manifest_json.parent,
    )
    if entry_batch.issues:
        return True
    for index, entry in enumerate(entries, start=1):
        try:
            diagnosis = load_json_object(entry.diagnosis_json)
            product_surface_summary = (
                load_json_object(entry.product_surface_summary_json)
                if entry.product_surface_summary_json is not None
                else None
            )
        except SparkCompactReadinessInputError:
            add_issue(
                result,
                "one_application_handoff_input_unreadable",
                "One Spark one-application handoff artifact could not be read or parsed safely.",
                input_index=index,
            )
            continue
        result.diagnosis_artifact_checked_count += 1
        audit_diagnosis_payload(result, diagnosis, input_index=index)
        if product_surface_summary is not None:
            audit_product_surface_summary_payload(
                result,
                product_surface_summary,
                compact_json=entry.compact_json,
                diagnosis_json=entry.diagnosis_json,
                input_index=index,
            )
    return True


def audit_product_surface_summary_payload(
    result: SparkProductSurfaceAuditResult,
    summary: Mapping[str, Any],
    *,
    compact_json: Path,
    diagnosis_json: Path,
    input_index: int,
) -> None:
    audit_json_artifact_raw_free(
        result,
        summary,
        category_prefix="product_surface_summary",
        artifact_label="Spark product-surface summary artifact",
        input_index=input_index,
    )
    expected = expected_product_surface_summary(compact_json, diagnosis_json)
    if summary != expected:
        add_issue(
            result,
            "product_surface_summary_mismatch",
            "Stored Spark product-surface summary must match deterministic compact output.",
            input_index=input_index,
        )


def expected_product_surface_summary(compact_json: Path, diagnosis_json: Path) -> dict[str, Any]:
    expected_result = SparkProductSurfaceAuditResult()
    audit_static_support_boundary(expected_result)
    audit_preview_route_boundary(expected_result)
    audit_compact_inputs(
        expected_result,
        (compact_json,),
        diagnosis_jsons=(diagnosis_json,),
    )
    status = "ok" if expected_result.ok else "failed"
    return product_surface_summary_payload(expected_result, status=status)


def add_readiness_result(
    result: SparkProductSurfaceAuditResult,
    readiness: SparkCompactReadinessResult,
    *,
    input_index: int,
) -> None:
    result.compact_readiness_checked_count += 1
    result.source_warning_count += readiness.source_warning_count
    for issue in readiness.issues:
        add_issue(
            result,
            f"compact_readiness_{issue.category}",
            issue.message,
            input_index=input_index,
        )


def add_readiness_batch(
    result: SparkProductSurfaceAuditResult,
    batch: SparkCompactReadinessBatchResult,
) -> None:
    result.input_count += batch.input_count
    result.compact_readiness_checked_count += batch.input_count
    result.source_warning_count += batch.source_warning_count
    for input_index, issue in batch.issues:
        add_issue(
            result,
            f"compact_readiness_{issue.category}",
            issue.message,
            input_index=input_index,
        )


def audit_diagnosis_payload(
    result: SparkProductSurfaceAuditResult,
    diagnosis: Mapping[str, Any],
    *,
    input_index: int,
) -> None:
    audit_json_artifact_raw_free(
        result,
        diagnosis,
        category_prefix="diagnosis",
        artifact_label="Spark compact diagnosis artifact",
        input_index=input_index,
    )
    if diagnosis.get("schema_version") != SPARK_COMPACT_DIAGNOSIS_SCHEMA_VERSION:
        add_issue(
            result,
            "diagnosis_schema_mismatch",
            "Spark compact diagnosis schema version is not accepted.",
            input_index=input_index,
        )
    if diagnosis.get("engine") != "spark":
        add_issue(
            result,
            "diagnosis_engine_mismatch",
            "Spark compact diagnosis must stay on engine=spark.",
            input_index=input_index,
        )
    if diagnosis.get("support_status") != EXPECTED_SUPPORT_STATUS:
        add_issue(
            result,
            "diagnosis_support_status_drift",
            "Spark compact diagnosis must stay experimental and below product support.",
            input_index=input_index,
        )
    audit_no_claim_boundary(result, diagnosis, input_index=input_index)
    audit_diagnostic_lane(result, diagnosis, input_index=input_index)
    audit_attention_and_limitations(result, diagnosis, input_index=input_index)


def audit_no_claim_boundary(
    result: SparkProductSurfaceAuditResult,
    diagnosis: Mapping[str, Any],
    *,
    input_index: int,
) -> None:
    boundary = diagnosis.get("diagnosis_boundary")
    if not isinstance(boundary, Mapping):
        add_issue(
            result,
            "missing_diagnosis_boundary",
            "Spark compact diagnosis must publish an explicit no-claim boundary.",
            input_index=input_index,
        )
        return
    if set(boundary) != set(EXPECTED_DIAGNOSIS_BOUNDARY):
        add_issue(
            result,
            "diagnosis_boundary_product_surface_drift",
            "Spark compact diagnosis boundary must not grow product-surface wiring fields.",
            input_index=input_index,
        )
    for key, expected in EXPECTED_DIAGNOSIS_BOUNDARY.items():
        if boundary.get(key) != expected:
            add_issue(
                result,
                "diagnosis_boundary_drift",
                "Spark compact diagnosis boundary no longer matches the no-product contract.",
                input_index=input_index,
            )


def audit_diagnostic_lane(
    result: SparkProductSurfaceAuditResult,
    diagnosis: Mapping[str, Any],
    *,
    input_index: int,
) -> None:
    lane = diagnosis.get("diagnostic_lane")
    if not isinstance(lane, Mapping):
        add_issue(
            result,
            "diagnostic_lane_missing",
            "Spark compact diagnosis must keep a diagnostic-lane boundary contract.",
            input_index=input_index,
        )
        return
    result.diagnostic_lane_checked_count += 1
    expected_values = {
        "schema_version": SPARK_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
        "lane": SPARK_COMPACT_DIAGNOSTIC_LANE_NAME,
        "promotion_status": "preview_only",
    }
    for key, expected in expected_values.items():
        if lane.get(key) != expected:
            add_issue(
                result,
                "diagnostic_lane_product_promotion_drift",
                "Spark diagnostic lane must stay preview-only and below product support.",
                input_index=input_index,
            )
            break
    if lane.get("required_gates") != {
        "readiness_audit": "required_for_handoff",
        "surface_audit": "required_before_wiring",
    }:
        add_issue(
            result,
            "diagnostic_lane_gate_drift",
            "Spark diagnostic lane must keep readiness and product-surface gates.",
            input_index=input_index,
        )
    lane_counter_fields = (
        ("source_granularity", result.diagnostic_lane_source_granularity_counts),
        ("evidence_readiness", result.diagnostic_lane_readiness_counts),
        ("verification_scope", result.diagnostic_lane_verification_scope_counts),
    )
    for key, counter in lane_counter_fields:
        value = lane.get(key)
        if not isinstance(value, str) or not value:
            add_issue(
                result,
                "diagnostic_lane_contract_incomplete",
                "Spark diagnostic lane must keep raw-free granularity, readiness, and scope.",
                input_index=input_index,
            )
            break
        counter[safe_label(value)] += 1

    fact_state_counts = Counter(safe_fact_state_counts(lane.get("fact_state_counts")))
    if not fact_state_counts:
        add_issue(
            result,
            "diagnostic_lane_contract_incomplete",
            "Spark diagnostic lane must keep raw-free fact-state counters.",
            input_index=input_index,
        )
    else:
        result.fact_state_counts.update(fact_state_counts)


def audit_attention_and_limitations(
    result: SparkProductSurfaceAuditResult,
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
    if REQUIRED_SPARK_LIMITATION_IDS - limitation_ids:
        add_issue(
            result,
            "missing_product_surface_limitation",
            "Spark compact diagnosis is missing a required product-surface limitation.",
            input_index=input_index,
        )


def audit_json_artifact_raw_free(
    result: SparkProductSurfaceAuditResult,
    payload: Mapping[str, Any],
    *,
    category_prefix: str,
    artifact_label: str,
    input_index: int,
) -> None:
    text = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    if contains_raw_sql_like_text(text):
        add_issue(
            result,
            f"{category_prefix}_sql_like_text",
            f"{artifact_label} contains SQL-like text.",
            input_index=input_index,
        )
    if validate_report_internal_fingerprints(text):
        add_issue(
            result,
            f"{category_prefix}_internal_fingerprint",
            f"{artifact_label} contains internal artifact or runtime fingerprints.",
            input_index=input_index,
        )
    for label, observed in raw_text_violations(text).items():
        if observed:
            add_issue(
                result,
                f"{category_prefix}_raw_like_text",
                f"{artifact_label} contains raw-like {label} content.",
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
            f"{category_prefix}_browser_redaction_required",
            f"{artifact_label} is not browser-display safe.",
            input_index=input_index,
        )


def audit_static_support_boundary(result: SparkProductSurfaceAuditResult) -> None:
    support = audit_spark_support_boundary()
    result.static_support_check_count = len(support.checks)
    for issue in support.issues:
        add_issue(
            result,
            f"support_boundary_{issue.category}",
            issue.message,
            input_index=None,
        )


def audit_preview_route_boundary(result: SparkProductSurfaceAuditResult) -> None:
    registered_post_paths = (*STATIC_POST_PATHS, *PREVIEW_WEB_POST_PATHS)
    spark_post_paths = {path for path in registered_post_paths if "spark" in path.lower()}
    unexpected_paths = spark_post_paths - ALLOWED_SPARK_POST_PATHS
    if unexpected_paths:
        add_issue(
            result,
            "unexpected_spark_post_route",
            "Spark has a POST route outside the isolated compact-diagnosis surface.",
        )
    missing_paths = ALLOWED_SPARK_POST_PATHS - spark_post_paths
    if missing_paths:
        add_issue(
            result,
            "missing_spark_post_route",
            "Spark compact diagnosis is missing from the isolated preview route registry.",
        )
    for surface in PREVIEW_WEB_POST_SURFACES.values():
        if surface.engine != "spark":
            continue
        if (
            surface.product_surface_allowed
            or surface.surface_class != "isolated_preview_web"
            or surface.route_path not in ALLOWED_SPARK_POST_PATHS
            or not {"recent", "details", "trusted_report", "optimizer"}.issubset(
                set(surface.forbidden_product_surfaces)
            )
        ):
            add_issue(
                result,
                "spark_preview_surface_contract_drift",
                "Spark preview web surface must stay isolated and below product support.",
            )


def product_surface_summary_payload(
    result: SparkProductSurfaceAuditResult,
    *,
    status: str,
) -> dict[str, Any]:
    return {
        "summary_kind": SPARK_PRODUCT_SURFACE_AUDIT_SUMMARY_KIND,
        "status": status,
        "mode": "spark_product_surface_boundary",
        "boundary": dict(SPARK_PRODUCT_SURFACE_BOUNDARY),
        "counts": {
            "compact_json_count": result.input_count,
            "compact_readiness_checked_count": result.compact_readiness_checked_count,
            "diagnosis_json_checked_count": result.diagnosis_artifact_checked_count,
            "diagnostic_lane_checked_count": result.diagnostic_lane_checked_count,
            "static_support_check_count": result.static_support_check_count,
            "attention_area_count": result.attention_area_count,
            "supported_attention_area_count": result.supported_attention_area_count,
            "limitation_count": result.limitation_count,
            "source_warning_count": result.source_warning_count,
        },
        "registry": {
            "spark_product_routes": "blocked",
            "spark_product_cli": "blocked",
            "details_report_source_imports": "blocked",
            "allowed_web_post_paths": sorted(ALLOWED_SPARK_POST_PATHS),
            "allowed_surface": "compact_diagnosis_only",
        },
        "diagnostic_lane": {
            "schema_version": SPARK_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
            "readiness": counter_payload(result.diagnostic_lane_readiness_counts),
            "source_granularity": counter_payload(result.diagnostic_lane_source_granularity_counts),
            "verification_scope": counter_payload(result.diagnostic_lane_verification_scope_counts),
        },
        "fact_states": counter_payload(result.fact_state_counts),
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


def write_summary_or_reject(path: Path | None, payload: Mapping[str, Any]) -> bool:
    if path is None:
        return True
    text = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if contains_raw_sql_like_text(text) or validate_report_internal_fingerprints(text):
        print(
            "[spark-product-surface-audit] rejected: summary JSON would contain raw-like text",
            file=sys.stderr,
        )
        return False
    if any(raw_text_violations(text).values()):
        print(
            "[spark-product-surface-audit] rejected: summary JSON would contain raw-like text",
            file=sys.stderr,
        )
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError:
        print(
            "[spark-product-surface-audit] rejected: summary JSON could not be written",
            file=sys.stderr,
        )
        return False
    return True


def print_result(
    result: SparkProductSurfaceAuditResult,
    *,
    status: str,
    limit: int,
) -> None:
    print(f"Spark product-surface boundary audit: {status}")
    print(
        "Boundary: "
        f"product_surface={SPARK_PRODUCT_SURFACE_STATUS}, "
        "support_claim=not_claimed, "
        "details_trusted_report_surface=not_wired, "
        "trusted_reports=not_wired, "
        "optimizer_behavior=not_wired, "
        "live_recent_scan=not_wired, "
        "live_known_query_diagnosis=not_wired, "
        "spark_job_execution=not_performed"
    )
    print(
        "Artifacts: "
        f"compact_json_count={result.input_count}, "
        f"diagnosis_json_checked={result.diagnosis_artifact_checked_count}, "
        f"diagnostic_lane_checked={result.diagnostic_lane_checked_count}, "
        "paths=not_printed"
    )
    print(
        "Registry: "
        "spark_product_routes=blocked, "
        "spark_product_cli=blocked, "
        "details_report_source_imports=blocked, "
        "allowed_surface=compact_diagnosis_only"
    )
    print(
        f"Static support: checks={result.static_support_check_count}, adapter=bounded_compact_only"
    )
    print_issues(result, limit=limit)


def print_issues(result: SparkProductSurfaceAuditResult, *, limit: int) -> None:
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


def add_issue(
    result: SparkProductSurfaceAuditResult,
    category: str,
    message: str,
    *,
    input_index: int | None = None,
) -> None:
    issue = SparkProductSurfaceAuditIssue(category=category, message=message)
    result.issue_counts[category] += 1
    result.issues.append((input_index, issue))


def list_of_mappings(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def safe_label(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "unknown"


def positive_int(value: str) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
