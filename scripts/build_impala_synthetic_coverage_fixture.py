#!/usr/bin/env python3
"""Build the committed synthetic Impala primary-coverage gate fixture."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.analyzer.client_fetch import (  # noqa: E402
    apply_client_fetch_profile_policy,
    build_client_fetch_facts,
)
from query_doctor.analyzer.profile_format import (  # noqa: E402
    ProfileDialect,
    profile_section_mappings,
)
from query_doctor.cli.demo_data import (  # noqa: E402
    SUMMARY_NAME,
    build_summary,
)
from query_doctor.demo.specs import DemoCaseSpec, demo_case_specs  # noqa: E402
from scripts.audit_impala_synthetic_coverage_gate import (  # noqa: E402
    AGGREGATE_NAME,
    build_gate_aggregate,
    load_fixture_result,
)


DEFAULT_FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "impala_synthetic_coverage_gate"


class FixtureBuildError(RuntimeError):
    """Raised when the synthetic fixture cannot be safely built."""


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_FIXTURE_ROOT,
        help="Fixture output directory. Default: tests/fixtures/impala_synthetic_coverage_gate.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace the existing fixture directory after a path safety check.",
    )
    return parser.parse_args(argv)


def build_fixture(out: Path, *, overwrite: bool) -> None:
    out = out.resolve(strict=False)
    ensure_safe_fixture_out(out)
    if out.exists():
        if not overwrite:
            raise FixtureBuildError("fixture output already exists; pass --overwrite")
        shutil.rmtree(out)
    out.mkdir(parents=True)

    specs = demo_case_specs()
    summary = build_summary(out, specs)
    summary["out"] = "tests/fixtures/impala_synthetic_coverage_gate"
    for case in summary.get("cases") or []:
        if not isinstance(case, dict):
            continue
        case_index = int(case.get("case_index") or 0)
        case["case_dir"] = f"cases/case-{case_index:03d}"
    write_json(out / SUMMARY_NAME, summary)

    cases_root = out / "cases"
    for spec in specs:
        case_dir = cases_root / f"case-{spec.case_index:03d}"
        case_dir.mkdir(parents=True)
        write_json(case_dir / "analysis.json", synthetic_analysis(spec))

    result = load_fixture_result(out)
    write_json(out / AGGREGATE_NAME, build_gate_aggregate(result))


def ensure_safe_fixture_out(out: Path) -> None:
    fixture_root = (ROOT / "tests" / "fixtures").resolve(strict=True)
    try:
        out.relative_to(fixture_root)
    except ValueError as exc:
        raise FixtureBuildError("fixture output must stay under tests/fixtures") from exc


def synthetic_analysis(spec: DemoCaseSpec) -> dict[str, Any]:
    primary = spec.case_primary_bottleneck or {
        "label": "unknown",
        "confidence": "low",
        "reasons": ["no_primary_branch_supported"],
    }
    analysis: dict[str, Any] = {
        "query_wall_clock": {
            "duration_ms": spec.duration_sec * 1000,
            "confidence": "high",
        },
        "profile_format": {
            "profile_family": "impala_runtime_profile",
            "profile_source": "synthetic_demo_pack",
            "source_label": "Synthetic demo profile facts",
            "profile_dialect": "classic_text_profile",
            "impala_distribution": "cloudera_impala",
            "impala_major_version": 4,
            "impala_build_type": "synthetic",
            "profile_response_format": "text",
            "primary_bottleneck_policy": "supported",
            "section_mappings": profile_section_mappings(ProfileDialect.CLASSIC_TEXT, {}),
            "source_capabilities": {
                "profile_response_format": "text",
                "profile_fetch_attempt_count": 1,
                "json_profile_probe": "not_configured",
                "profile_docs_probe": "not_configured",
                "json_profile_payload": "not_selected",
                "text_profile_payload": "observed",
                "primary_profile_routing": "supported",
            },
        },
        "profile_counter_registry": {
            "status": "not_observed",
            "source": "bundled",
            "missing_counter_count": 0,
        },
        "source_provenance": {
            "items": [
                {"kind": "engine", "status": "available"},
                {"kind": "profile", "status": "available"},
                {"kind": "metadata", "status": metadata_source_status(spec)},
                {"kind": "metrics", "status": "none"},
                {"kind": "events", "status": "none"},
            ],
        },
        "evidence_quality": {"level": "medium"},
        "case_primary_bottleneck": primary,
        "findings": [],
        "backend_tail": {
            "execution_skew": "yes" if spec.backend_data_skew else "no",
            "execution_tail_candidate_count": spec.host_tail_candidate_count,
        },
        "cardinality_anomalies": [
            {"operator_id": f"op_{index:02d}"} for index in range(spec.cardinality_anomaly_count)
        ],
        "stats_metadata_quality": {
            "status": "unavailable",
            "stats_primary_bottleneck": "unknown",
            "non_stats_bottleneck_categories": "none",
        },
        "data_movement": {
            "status": "not_observed",
            "evidence_tier": "unsupported",
            "finding_supported": False,
            "primary_supported": False,
            "exchange_operator_count": 0,
        },
        "memory_pressure": {
            "status": "not_observed",
            "evidence_tier": "unsupported",
            "finding_supported": False,
            "spill_or_scratch_evidence_count": 0,
        },
        "storage_context": {
            "status": "unknown",
            "storage_family": "unknown",
            "storage_semantics": "unknown",
            "source": "not_collected",
        },
        "resource_trace": {
            "status": "unknown",
            "evidence_tier": "unsupported",
            "observed_metric_count": 0,
        },
    }
    apply_primary_fixture_facts(analysis, spec, primary)
    return analysis


def metadata_source_status(spec: DemoCaseSpec) -> str:
    return "available" if spec.metadata_status == "collected" else "none"


def apply_primary_fixture_facts(
    analysis: dict[str, Any],
    spec: DemoCaseSpec,
    primary: dict[str, Any],
) -> None:
    label = str(primary.get("label") or "unknown")
    confidence = str(primary.get("confidence") or "low")
    if label == "sql_shape":
        analysis["top_elapsed_finding_id"] = "join_bottleneck"
        analysis["stats_metadata_quality"] = {
            "status": "available",
            "stats_primary_bottleneck": "not_primary_supported",
            "non_stats_bottleneck_categories": "none",
        }
    elif label == "stats":
        analysis["stats_metadata_quality"] = {
            "status": "available",
            "stats_primary_bottleneck": "candidate_supported",
            "non_stats_bottleneck_categories": "none",
        }
    elif label == "runtime_data_movement":
        analysis["top_elapsed_finding_id"] = "large_intermediate_or_exchange_traffic"
        analysis["findings"] = [{"id": "large_intermediate_or_exchange_traffic"}]
        analysis["totals"] = {"TotalBytesSent": {"bytes": 4_294_967_296}}
        analysis["top_operators_by_time"] = [{"operator_name": "EXCHANGE_NODE", "time_ms": 45_000}]
        analysis.pop("data_movement", None)
    elif label == "runtime_storage":
        analysis["top_elapsed_finding_id"] = "hdfs_or_storage_bottleneck"
        analysis["findings"] = [{"id": "hdfs_or_storage_bottleneck"}]
        analysis["totals"] = {"TotalBytesRead": {"bytes": 8_589_934_592}}
        analysis["top_operators_by_time"] = [
            {"operator_name": "HDFS_SCAN_NODE", "time_ms": 120_000}
        ]
    elif label == "runtime_admission":
        analysis["runtime_admission"] = {
            "status": "supported",
            "evidence_tier": "strong",
            "primary_supported": True,
            "primary_confidence": confidence,
            "primary_reasons": list(primary.get("reasons") or []),
            "admission_result": "admitted",
            "admission_result_source": "query_context",
            "wait_ms": max(5_000, int(spec.duration_sec * 500)),
            "wait_human": "synthetic",
            "wait_source": "query_context",
            "wait_share": 0.25,
            "wait_share_human": "25%",
            "wait_evidence": [
                {
                    "source": "query_context",
                    "wait_ms": max(5_000, int(spec.duration_sec * 500)),
                    "wait_human": "synthetic",
                }
            ],
            "guardrail": "synthetic selected-query admission evidence",
            "limitations": [],
        }
    elif label == "client_fetch_tail":
        analysis["top_elapsed_finding_id"] = "client_fetch_tail"
        analysis["findings"] = [{"id": "client_fetch_tail"}]
        analysis["top_operators_by_time"] = [{"operator_name": "HDFS_SCAN_NODE", "time_ms": 1_000}]
        analysis["client_fetch"] = apply_client_fetch_profile_policy(
            build_client_fetch_facts(
                "- ClientFetchWaitTimer: 45s",
                {},
                analysis["query_wall_clock"],
            ),
            analysis["profile_format"],
        )
    elif label == "mixed":
        analysis["top_elapsed_finding_id"] = "join_bottleneck"
        analysis["findings"] = [{"id": "large_intermediate_or_exchange_traffic"}]
        analysis["stats_metadata_quality"] = {
            "status": "available",
            "stats_primary_bottleneck": "mixed_candidate",
            "non_stats_bottleneck_categories": [
                "query_shape",
                "exchange_or_data_movement",
            ],
        }
        analysis["data_movement"] = {
            "status": "supported",
            "evidence_tier": "medium",
            "finding_supported": True,
            "primary_supported": False,
            "total_bytes_sent": 2_576_980_377,
            "exchange_operator_count": 3,
            "exchange_elapsed_ms": 44_000,
            "exchange_elapsed_share": 0.25,
        }
    elif label == "unknown":
        if "very_short_query_or_unknown_wall_clock" not in set(primary.get("reasons") or []):
            analysis["top_operators_by_time"] = [
                {"operator_name": "HDFS_SCAN_NODE", "time_ms": 1_000}
            ]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build_fixture(args.out, overwrite=args.overwrite)
    except FixtureBuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print("Built synthetic Impala coverage fixture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
