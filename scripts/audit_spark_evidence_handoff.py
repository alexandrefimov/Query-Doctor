#!/usr/bin/env python3
"""Audit a Spark evidence package through the local fixture handoff pipeline."""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
from collections.abc import Iterable
from collections.abc import Mapping
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.analyzer.engine_facts import EngineFactContractError  # noqa: E402
from query_doctor.analyzer.spark_evidence_package import (  # noqa: E402
    SPARK_EVIDENCE_READINESS_PROMOTION_CANDIDATE,
    spark_evidence_package_readiness_payload,
    validate_spark_evidence_package_payload,
)
from query_doctor.cli import export_spark_evidence_fixtures  # noqa: E402
from query_doctor.cli.export_spark_evidence_fixtures import (  # noqa: E402
    SPARK_FIXTURE_EXPORT_MANIFEST,
)
from scripts.audit_spark_compact_readiness import (  # noqa: E402
    ACCEPTED_SPARK_SOURCE_CONTRACTS,
    SparkCompactReadinessBatchResult,
    raw_text_violations,
    audit_fixture_export_manifest,
    contains_raw_sql_like_text,
    positive_int,
    print_suite_result,
    validate_report_internal_fingerprints,
)


SPARK_EVIDENCE_HANDOFF_SUMMARY_VERSION = "spark_evidence_handoff_summary_v1"


class SparkEvidenceHandoffOutputError(RuntimeError):
    """Raised when the handoff audit cannot write safe output."""


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a sanitized Spark compact evidence package, export it to "
            "temporary fixture-ready compact JSON, and run the manifest-driven "
            "Spark compact readiness audit without printing paths or claiming "
            "Spark product support."
        )
    )
    parser.add_argument("package_json", type=Path, help="Path to a sanitized package JSON file.")
    parser.add_argument("--limit", type=positive_int, default=12, help="Rows to print per section.")
    parser.add_argument(
        "--require-min-inputs",
        type=positive_int,
        default=2,
        help="Require at least this many manifest-listed compact inputs.",
    )
    parser.add_argument(
        "--require-source-contract",
        action="append",
        choices=sorted(ACCEPTED_SPARK_SOURCE_CONTRACTS),
        default=None,
        help=(
            "Require the handoff to include at least one compact input with this source "
            "contract. Defaults to all accepted Spark compact source contracts."
        ),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help=(
            "Optional output path for a raw-free machine-readable Spark handoff readiness "
            "summary. The path must differ from the package input."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    overlap_error = reject_summary_output_overlap(args.summary_json, args.package_json)
    if overlap_error:
        print(f"[spark-handoff] rejected: {overlap_error}", file=sys.stderr)
        return 2
    required_source_contracts = args.require_source_contract or sorted(
        ACCEPTED_SPARK_SOURCE_CONTRACTS
    )
    try:
        package_payload = _load_json(args.package_json)
        package_result = validate_spark_evidence_package_payload(package_payload)
    except OSError:
        print("[spark-handoff] rejected: package file could not be read", file=sys.stderr)
        return 2
    except json.JSONDecodeError:
        print("[spark-handoff] rejected: package file is not valid JSON", file=sys.stderr)
        return 2
    except EngineFactContractError as exc:
        print(f"[spark-handoff] rejected: {exc}", file=sys.stderr)
        return 1

    readiness = spark_evidence_package_readiness_payload(package_result)
    if readiness["readiness_status"] != SPARK_EVIDENCE_READINESS_PROMOTION_CANDIDATE:
        blockers = _format_safe_labels(readiness["promotion_blockers"])
        summary = rejected_handoff_summary_payload(
            readiness,
            require_min_inputs=args.require_min_inputs,
            required_source_contracts=required_source_contracts,
        )
        if not write_summary_or_reject(args.summary_json, summary):
            return 2
        print(
            "[spark-handoff] rejected: package readiness is not promotion_candidate; "
            f"promotion_blockers: {blockers}",
            file=sys.stderr,
        )
        return 1

    with tempfile.TemporaryDirectory(prefix="query-doctor-spark-handoff-") as temp_dir:
        fixture_dir = Path(temp_dir) / "fixture-ready"
        export_rc = _run_fixture_export_silently(args.package_json, fixture_dir)
        if export_rc != 0:
            print("[spark-handoff] rejected: fixture export failed safely", file=sys.stderr)
            return 1
        batch = audit_fixture_export_manifest(
            fixture_dir / SPARK_FIXTURE_EXPORT_MANIFEST,
            require_supported_attention=True,
            fail_on_source_warnings=True,
            require_min_inputs=args.require_min_inputs,
            required_source_contracts=required_source_contracts,
        )

    status = "ok" if batch.ok else "failed"
    summary = handoff_summary_payload(
        batch,
        status=status,
        require_min_inputs=args.require_min_inputs,
        required_source_contracts=required_source_contracts,
    )
    if not write_summary_or_reject(args.summary_json, summary):
        return 2
    print(f"Spark evidence handoff: {status}")
    print(
        "Pipeline: "
        "package_validation=accepted, "
        "fixture_export=accepted, "
        f"fixture_manifest_audit={status}"
    )
    print(
        "Boundary: "
        "readiness_status=promotion_candidate, "
        "support_claim=not_claimed, "
        "product_surface=not_wired, "
        "spark_job_execution=not_performed"
    )
    print("Output paths: not_printed")
    print_suite_result(batch, limit=args.limit)
    return 0 if batch.ok else 1


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_fixture_export_silently(package_json: Path, fixture_dir: Path) -> int:
    captured_out = io.StringIO()
    captured_err = io.StringIO()
    with redirect_stdout(captured_out), redirect_stderr(captured_err):
        return export_spark_evidence_fixtures.main(
            [str(package_json), "--out-dir", str(fixture_dir)]
        )


def handoff_summary_payload(
    batch: SparkCompactReadinessBatchResult,
    *,
    status: str,
    require_min_inputs: int,
    required_source_contracts: Iterable[str],
) -> dict[str, Any]:
    return {
        "schema_version": SPARK_EVIDENCE_HANDOFF_SUMMARY_VERSION,
        "mode": "spark_evidence_handoff",
        "status": status,
        "pipeline": {
            "package_validation": "accepted",
            "fixture_export": "accepted",
            "fixture_manifest_audit": status,
        },
        "boundary": support_boundary_payload(),
        "readiness": {
            "readiness_status": "promotion_candidate",
            "source_warnings_clear": batch.source_warning_count == 0,
        },
        "requirements": requirements_payload(
            require_min_inputs=require_min_inputs,
            required_source_contracts=required_source_contracts,
        ),
        "counts": {
            "compact_json_count": batch.input_count,
            "ok_count": batch.ok_count,
            "failed_count": batch.failed_count,
            "fact_count": batch.fact_count,
            "attention_area_count": batch.attention_area_count,
            "supported_attention_area_count": batch.supported_attention_area_count,
            "source_warning_count": batch.source_warning_count,
        },
        "source_contracts": counter_payload(batch.source_contract_counts),
        "support_statuses": counter_payload(batch.support_status_counts),
        "parser_coverage": counter_payload(batch.parser_coverage_counts),
        "lifecycles": counter_payload(batch.lifecycle_counts),
        "fact_scopes": counter_payload(batch.fact_scope_counts),
        "fact_states": counter_payload(batch.fact_state_counts),
        "attention_states": counter_payload(batch.attention_state_counts),
        "limitation_states": counter_payload(batch.limitation_state_counts),
        "issues": {
            "counts": counter_payload(batch.issue_counts),
            "items": [
                {
                    "input_index": input_index,
                    "category": issue.category,
                    "message": issue.message,
                }
                for input_index, issue in batch.issues
            ],
        },
    }


def rejected_handoff_summary_payload(
    readiness: Mapping[str, Any],
    *,
    require_min_inputs: int,
    required_source_contracts: Iterable[str],
) -> dict[str, Any]:
    return {
        "schema_version": SPARK_EVIDENCE_HANDOFF_SUMMARY_VERSION,
        "mode": "spark_evidence_handoff",
        "status": "rejected",
        "pipeline": {
            "package_validation": "accepted",
            "fixture_export": "not_run",
            "fixture_manifest_audit": "not_run",
        },
        "boundary": support_boundary_payload(),
        "requirements": requirements_payload(
            require_min_inputs=require_min_inputs,
            required_source_contracts=required_source_contracts,
        ),
        "readiness": {
            "readiness_status": safe_label(readiness.get("readiness_status")),
            "support_status": safe_label(readiness.get("support_status")),
            "support_claim": safe_label(readiness.get("support_claim")),
            "product_surface": safe_label(readiness.get("product_surface")),
            "spark_job_execution": safe_label(readiness.get("spark_job_execution")),
            "source_warnings_clear": bool(readiness.get("source_warnings_clear")),
            "supported_attention_area_count": safe_int(
                readiness.get("supported_attention_area_count")
            ),
            "source_warning_count": safe_int(readiness.get("source_warning_count")),
            "promotion_blockers": safe_label_list(readiness.get("promotion_blockers")),
            "missing_source_contracts": safe_label_list(readiness.get("missing_source_contracts")),
            "missing_sample_cases": safe_label_list(readiness.get("missing_sample_cases")),
            "missing_synthetic_rejection_cases": safe_label_list(
                readiness.get("missing_synthetic_rejection_cases")
            ),
        },
    }


def support_boundary_payload() -> dict[str, str]:
    return {
        "support_status": "experimental_compact_intake",
        "support_claim": "not_claimed",
        "product_surface": "not_wired",
        "details_trusted_report_surface": "not_wired",
        "optimizer_behavior": "not_wired",
        "spark_job_execution": "not_performed",
    }


def requirements_payload(
    *,
    require_min_inputs: int,
    required_source_contracts: Iterable[str],
) -> dict[str, Any]:
    return {
        "require_min_inputs": require_min_inputs,
        "require_source_contracts": sorted(required_source_contracts),
        "require_supported_attention": True,
        "fail_on_source_warnings": True,
        "require_promotion_candidate": True,
    }


def counter_payload(counter: Mapping[str, int]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def write_summary_or_reject(path: Path | None, payload: Mapping[str, Any]) -> bool:
    if path is None:
        return True
    try:
        write_handoff_summary_json(path, payload)
    except SparkEvidenceHandoffOutputError as exc:
        print(f"[spark-handoff] rejected: {exc}", file=sys.stderr)
        return False
    return True


def write_handoff_summary_json(path: Path, payload: Mapping[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if contains_raw_sql_like_text(text):
        raise SparkEvidenceHandoffOutputError("summary JSON output would contain raw-like content")
    if validate_report_internal_fingerprints(text):
        raise SparkEvidenceHandoffOutputError("summary JSON output would contain raw-like content")
    if any(raw_text_violations(text).values()):
        raise SparkEvidenceHandoffOutputError("summary JSON output would contain raw-like content")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise SparkEvidenceHandoffOutputError("summary JSON output could not be written") from exc


def reject_summary_output_overlap(
    summary_json: Path | None,
    package_json: Path,
) -> str | None:
    if summary_json is not None and same_path(summary_json, package_json):
        return "summary JSON output must differ from the package input"
    return None


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def safe_label(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "unknown"
    text = json.dumps(value, ensure_ascii=True)
    if contains_raw_sql_like_text(text) or validate_report_internal_fingerprints(text):
        return "redacted"
    if any(raw_text_violations(text).values()):
        return "redacted"
    return value


def safe_label_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [safe_label(item) for item in value]


def safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value >= 0:
        return value
    return 0


def _format_safe_labels(labels: object) -> str:
    if not isinstance(labels, list) or not labels:
        return "none"
    return ", ".join(str(label) for label in labels)


if __name__ == "__main__":
    raise SystemExit(main())
