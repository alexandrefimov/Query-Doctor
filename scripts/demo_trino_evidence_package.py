#!/usr/bin/env python3
"""Run a safe fixture-only Trino evidence-package walkthrough."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.trino_evidence_package import (
    validate_trino_evidence_package_payload,
)
from query_doctor.analyzer.trino_evidence_package_builder import (
    TrinoEvidencePackageSampleSpec,
    build_trino_evidence_package_payload,
)
from scripts.validate_trino_evidence_package import print_safe_summary


FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "engine_facts"
PACKAGE_FILENAME = "package.json"
SAMPLE_FIXTURES = (
    ("successful_completed_query", "statement_stats_export", "trino_statement_stats.json"),
    (
        "failed_query_allowlisted_category",
        "statement_stats_export",
        "trino_failure_category_statement_stats.json",
    ),
    (
        "failed_query_allowlisted_category",
        "query_detail_export",
        "trino_query_detail_failure_category.json",
    ),
    (
        "queued_or_resource_group_delayed_query",
        "event_listener_export",
        "trino_resource_group_queued_event.json",
    ),
    (
        "queued_or_resource_group_delayed_query",
        "query_detail_export",
        "trino_query_detail_queued.json",
    ),
    ("blocked_query", "statement_stats_export", "trino_blocked_statement_stats.json"),
    ("blocked_query", "query_detail_export", "trino_query_detail_blocked.json"),
    ("spill_observed", "event_listener_export", "trino_completed_event.json"),
    ("spill_observed", "query_detail_export", "trino_query_detail_spill_observed.json"),
    (
        "stage_or_task_skew_candidate",
        "statement_stats_export",
        "trino_stage_skew_statement_stats.json",
    ),
    (
        "stage_or_task_skew_candidate",
        "query_detail_export",
        "trino_query_detail_stage_skew.json",
    ),
    (
        "connector_metric_present",
        "statement_stats_export",
        "trino_connector_metric_present_statement_stats.json",
    ),
    (
        "connector_metric_present",
        "query_detail_export",
        "trino_query_detail_connector_metric_present.json",
    ),
    (
        "connector_metric_absent",
        "statement_stats_export",
        "trino_connector_metric_absent_statement_stats.json",
    ),
    (
        "connector_metric_absent",
        "query_detail_export",
        "trino_query_detail_connector_metric_absent.json",
    ),
    (
        "missing_field_case",
        "event_listener_export",
        "trino_completed_event_missing_fields.json",
    ),
    (
        "missing_field_case",
        "query_detail_export",
        "trino_query_detail_missing_fields.json",
    ),
    (
        "unknown_or_unsupported_source_contract",
        "event_listener_export",
        "trino_unknown_source_contract_event.json",
    ),
    (
        "unknown_or_unsupported_source_contract",
        "query_detail_export",
        "trino_query_detail_unknown_source_contract.json",
    ),
    (
        "query_list_contract_probe",
        "query_list_summary_export",
        "trino_query_list_contract_probe.json",
    ),
    (
        "query_list_contract_probe",
        "query_list_summary_export",
        "trino_query_list_heavy_bucket_contract_probe.json",
    ),
    (
        "query_detail_stage_task_summary",
        "query_detail_export",
        "trino_query_detail_export.json",
    ),
    (
        "query_detail_stage_task_summary",
        "query_detail_export",
        "trino_query_detail_task_failure_export.json",
    ),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build and validate the committed synthetic Trino evidence-package demo. "
            "The command does not contact Trino, execute SQL, or echo fixture/output paths."
        )
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Optional directory where the sanitized demo package is written.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing the demo package file in the output directory.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = build_demo_payload()
        result = validate_trino_evidence_package_payload(payload)
        package_written = _write_demo_package(args.out_dir, payload, overwrite=args.overwrite)
    except OSError:
        print(
            "[trino-package-demo] rejected: fixture or output file is unavailable", file=sys.stderr
        )
        return 2
    except json.JSONDecodeError:
        print("[trino-package-demo] rejected: committed fixture is not valid JSON", file=sys.stderr)
        return 2
    except (EngineFactContractError, ValueError) as exc:
        print(f"[trino-package-demo] rejected: {exc}", file=sys.stderr)
        return 1

    print("[trino-package-demo] built synthetic fixture package")
    print(f"package_written: {_format_yes_no(package_written)}")
    print_safe_summary(result)
    return 0


def build_demo_payload() -> dict:
    return build_trino_evidence_package_payload(
        package_id="trino_fixture_demo",
        prepared_date_utc="2026-05-26",
        export_window_start_utc="2026-05-26T09:00:00Z",
        export_window_end_utc="2026-05-26T10:00:00Z",
        samples=_load_samples(),
        trino_version_family="477",
        source_contract_version="synthetic_trino_event_listener_v1",
        connector_family_categories=("lakehouse",),
        known_omissions=("raw_identifiers",),
        unsupported_sources=(),
        synthetic_rejection_counts={
            "oversized_or_over_deep_rejection_synthetic": 1,
            "unsafe_raw_field_rejection_synthetic": 1,
        },
        redaction_reviewed=True,
        sentinel_tests_passed=True,
    )


def _load_samples() -> tuple[TrinoEvidencePackageSampleSpec, ...]:
    return tuple(
        TrinoEvidencePackageSampleSpec(
            case=case,
            source_type=source_type,
            payload=_load_fixture(fixture_name),
        )
        for case, source_type, fixture_name in SAMPLE_FIXTURES
    )


def _load_fixture(fixture_name: str) -> dict:
    payload = json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EngineFactContractError("Trino demo fixture payload must be a JSON object")
    return payload


def _write_demo_package(out_dir: Path | None, payload: dict, *, overwrite: bool) -> bool:
    if out_dir is None:
        return False
    if out_dir.exists() and not out_dir.is_dir():
        raise ValueError("output directory is unavailable")
    if out_dir.exists() and any(out_dir.iterdir()) and not overwrite:
        raise ValueError("output directory is not empty")
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / PACKAGE_FILENAME
    if output_path.exists() and not overwrite:
        raise ValueError("output package already exists")
    output_path.write_text(
        json.dumps(payload, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return True


def _format_yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    raise SystemExit(main())
