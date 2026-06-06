#!/usr/bin/env python3
"""Run one bounded Spark History Server application handoff and readiness gate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from query_doctor.analyzer.engine_facts import (  # noqa: E402
    EngineFactContractError,
    engine_fact_boundary_payload,
)
from query_doctor.analyzer.spark_fixture_facts import (  # noqa: E402
    build_spark_history_server_compact_engine_facts,
)
from query_doctor.cm.models import CMClientError  # noqa: E402
from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    distinct_paths_error,
    write_ascii_json_artifact,
)
from query_doctor.spark.diagnosis import build_spark_compact_diagnosis  # noqa: E402
from query_doctor.spark.history_server import (  # noqa: E402
    DEFAULT_MAX_SPARK_HISTORY_RESPONSE_BYTES,
    DEFAULT_SPARK_HISTORY_MAX_APPLICATION_ATTEMPTS,
    DEFAULT_SPARK_HISTORY_MAX_JOBS,
    DEFAULT_SPARK_HISTORY_MAX_SQL_EXECUTIONS,
    DEFAULT_SPARK_HISTORY_MAX_STAGES,
    DEFAULT_SPARK_HISTORY_MAX_TASKS_SAMPLED,
    DEFAULT_SPARK_HISTORY_MAX_TASK_SUMMARIES,
    DEFAULT_SPARK_HISTORY_TIMEOUT_SEC,
    SparkHistoryServerCompactResult,
    collect_spark_history_server_compact_summary,
)
from scripts.audit_spark_compact_readiness import (  # noqa: E402
    SparkCompactReadinessInputError,
    SparkCompactReadinessResult,
    audit_compact_payload,
    compact_summary_payload,
    print_result,
    write_summary_json,
)
from scripts import audit_spark_product_surface_boundary  # noqa: E402


SPARK_ONE_APPLICATION_HANDOFF_SUMMARY_VERSION = "spark_one_application_handoff_summary_v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a dev-only Spark handoff for one explicit History Server application: "
            "collect bounded summary-only compact JSON, write raw-free compact and "
            "diagnosis artifacts, then run the Spark compact readiness gate. The "
            "command never executes Spark jobs, fetches event logs, prints History "
            "Server URLs, application selectors, artifact paths, filenames, raw SQL, "
            "plans, logs, or a Spark support claim."
        )
    )
    parser.add_argument(
        "--redaction-reviewed",
        action="store_true",
        help="Confirm the selected Spark History Server application path was operator-reviewed.",
    )
    parser.add_argument(
        "--history-server-url",
        required=True,
        help="Spark History Server base URL. Used for bounded collection but never echoed.",
    )
    parser.add_argument(
        "--allow-local-history-server-target",
        action="store_true",
        help=(
            "Allow explicit loopback, RFC1918, carrier-grade NAT, or unique-local Spark "
            "History Server targets. Blocked target classes remain blocked."
        ),
    )
    parser.add_argument(
        "--application-id",
        required=True,
        help="Explicit Spark application id selector. Used for bounded collection but never echoed.",
    )
    parser.add_argument(
        "--application-attempt-id",
        help=(
            "Optional Spark application attempt id selector. Used for bounded collection but "
            "never echoed."
        ),
    )
    parser.add_argument(
        "--sql-execution-id",
        help="Optional Spark SQL execution id selector. Used only for bounded collection.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=positive_int,
        default=DEFAULT_SPARK_HISTORY_TIMEOUT_SEC,
        help=f"Timeout per Spark History Server endpoint. Default: {DEFAULT_SPARK_HISTORY_TIMEOUT_SEC}.",
    )
    parser.add_argument(
        "--max-response-bytes",
        type=positive_int,
        default=DEFAULT_MAX_SPARK_HISTORY_RESPONSE_BYTES,
        help=(
            "Maximum bytes per Spark History Server JSON response. "
            f"Default: {DEFAULT_MAX_SPARK_HISTORY_RESPONSE_BYTES}."
        ),
    )
    parser.add_argument(
        "--max-application-attempts",
        type=positive_int,
        default=DEFAULT_SPARK_HISTORY_MAX_APPLICATION_ATTEMPTS,
        help=(
            "Maximum Spark application attempts to compact. "
            f"Default: {DEFAULT_SPARK_HISTORY_MAX_APPLICATION_ATTEMPTS}."
        ),
    )
    parser.add_argument(
        "--max-sql-executions",
        type=positive_int,
        default=DEFAULT_SPARK_HISTORY_MAX_SQL_EXECUTIONS,
        help=(
            "Maximum SQL execution summaries to inspect. "
            f"Default: {DEFAULT_SPARK_HISTORY_MAX_SQL_EXECUTIONS}."
        ),
    )
    parser.add_argument(
        "--max-jobs",
        type=positive_int,
        default=DEFAULT_SPARK_HISTORY_MAX_JOBS,
        help=f"Maximum linked job summaries to compact. Default: {DEFAULT_SPARK_HISTORY_MAX_JOBS}.",
    )
    parser.add_argument(
        "--max-stages",
        type=positive_int,
        default=DEFAULT_SPARK_HISTORY_MAX_STAGES,
        help=f"Maximum linked stage summaries to compact. Default: {DEFAULT_SPARK_HISTORY_MAX_STAGES}.",
    )
    parser.add_argument(
        "--max-task-summaries",
        type=positive_int,
        default=DEFAULT_SPARK_HISTORY_MAX_TASK_SUMMARIES,
        help=(
            "Maximum linked stage taskSummary endpoints to inspect. "
            f"Default: {DEFAULT_SPARK_HISTORY_MAX_TASK_SUMMARIES}."
        ),
    )
    parser.add_argument(
        "--max-tasks-sampled",
        type=positive_int,
        default=DEFAULT_SPARK_HISTORY_MAX_TASKS_SAMPLED,
        help=(
            "Maximum task count recorded as sampled in compact aggregate fields. "
            f"Default: {DEFAULT_SPARK_HISTORY_MAX_TASKS_SAMPLED}."
        ),
    )
    parser.add_argument(
        "--compact-out",
        required=True,
        type=Path,
        help="Output path for raw-free Spark compact JSON. The path is never printed.",
    )
    parser.add_argument(
        "--diagnosis-out",
        required=True,
        type=Path,
        help="Output path for raw-free Spark compact diagnosis JSON. The path is never printed.",
    )
    parser.add_argument(
        "--boundary-facts-out",
        type=Path,
        default=None,
        help=(
            "Optional output path for raw-free engine_fact_boundary_v1 JSON. "
            "The path is never printed."
        ),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help=(
            "Optional output path for raw-free one-application handoff summary JSON. "
            "The path is never printed and must differ from artifact outputs."
        ),
    )
    parser.add_argument(
        "--product-surface-summary-out",
        type=Path,
        default=None,
        help=(
            "Optional output path for raw-free Spark product-surface boundary audit summary "
            "JSON over the written compact and diagnosis artifacts. The path is never "
            "printed and must differ from artifact outputs."
        ),
    )
    parser.add_argument(
        "--require-supported-attention",
        action="store_true",
        help="Fail unless the compact diagnosis contains at least one supported attention area.",
    )
    parser.add_argument(
        "--fail-on-source-warnings",
        action="store_true",
        help="Fail when compact source warning IDs are present.",
    )
    parser.add_argument("--limit", type=positive_int, default=12, help="Rows to print per section.")
    return parser


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def main(argv: Sequence[str] | None = None, *, opener=None) -> int:
    args = build_parser().parse_args(argv)
    if not args.redaction_reviewed:
        print(
            "[spark-one-application-handoff] rejected: redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1

    overlap_error = output_overlap_error(args)
    if overlap_error:
        print(f"[spark-one-application-handoff] rejected: {overlap_error}", file=sys.stderr)
        return 2

    try:
        collection_kwargs = {
            "history_server_url": args.history_server_url,
            "application_id": args.application_id,
            "application_attempt_id": args.application_attempt_id,
            "sql_execution_id": args.sql_execution_id,
            "timeout_sec": args.timeout_sec,
            "max_response_bytes": args.max_response_bytes,
            "max_application_attempts": args.max_application_attempts,
            "max_sql_executions": args.max_sql_executions,
            "max_jobs": args.max_jobs,
            "max_stages": args.max_stages,
            "max_task_summaries": args.max_task_summaries,
            "max_tasks_sampled": args.max_tasks_sampled,
            "allow_local_targets": args.allow_local_history_server_target,
        }
        if opener is not None:
            collection_kwargs["opener"] = opener
        result = collect_spark_history_server_compact_summary(**collection_kwargs)
        diagnosis = build_spark_compact_diagnosis(result.payload)
        boundary = engine_fact_boundary_payload(
            build_spark_history_server_compact_engine_facts(result.payload)
        )
        write_json(args.compact_out, result.payload)
        write_json(args.diagnosis_out, diagnosis)
        if args.boundary_facts_out is not None:
            write_json(args.boundary_facts_out, boundary)
        readiness = audit_compact_payload(
            result.payload,
            require_supported_attention=args.require_supported_attention,
            fail_on_source_warnings=args.fail_on_source_warnings,
        )
        if args.summary_json is not None:
            write_summary_json(
                args.summary_json,
                one_application_handoff_summary_payload(
                    result=result,
                    readiness=readiness,
                    require_supported_attention=args.require_supported_attention,
                    fail_on_source_warnings=args.fail_on_source_warnings,
                    boundary_written=args.boundary_facts_out is not None,
                ),
            )
    except CMClientError:
        print(
            "[spark-one-application-handoff] rejected: Spark History compact collection failed",
            file=sys.stderr,
        )
        return 1
    except EngineFactContractError:
        print(
            "[spark-one-application-handoff] rejected: Spark compact handoff boundary is not accepted",
            file=sys.stderr,
        )
        return 1
    except SparkCompactReadinessInputError:
        print(
            "[spark-one-application-handoff] rejected: summary JSON could not be written safely",
            file=sys.stderr,
        )
        return 2
    except OSError:
        print(
            "[spark-one-application-handoff] rejected: local artifact could not be written",
            file=sys.stderr,
        )
        return 2

    print("[spark-one-application-handoff] collection")
    print(
        "Spark History compact collection: accepted, "
        f"endpoints_ok={result.successful_endpoints}/{result.attempted_endpoints}, "
        f"warning_count={len(result.warnings)}"
    )
    print(
        "Boundary: support_claim=not_claimed, product_surface=not_wired, "
        "spark_job_execution=not_performed"
    )
    print("Artifact paths: not_printed")
    print("[spark-one-application-handoff] readiness")
    print_result(readiness, limit=args.limit)
    product_surface_exit = 0
    if args.product_surface_summary_out is not None:
        print("[spark-one-application-handoff] product-surface")
        product_surface_exit = audit_spark_product_surface_boundary.main(
            [
                str(args.compact_out),
                "--diagnosis-json",
                str(args.diagnosis_out),
                "--summary-json",
                str(args.product_surface_summary_out),
                "--limit",
                str(args.limit),
            ]
        )
    if product_surface_exit:
        return product_surface_exit
    return 0 if readiness.ok else 1


def one_application_handoff_summary_payload(
    *,
    result: SparkHistoryServerCompactResult,
    readiness: SparkCompactReadinessResult,
    require_supported_attention: bool,
    fail_on_source_warnings: bool,
    boundary_written: bool,
) -> dict[str, Any]:
    status = "ok" if readiness.ok else "failed"
    return {
        "schema_version": SPARK_ONE_APPLICATION_HANDOFF_SUMMARY_VERSION,
        "mode": "one_application_history_server",
        "status": status,
        "pipeline": {
            "collection": "accepted",
            "compact_diagnosis": "accepted",
            "boundary_facts": "written" if boundary_written else "generated_not_written",
            "readiness": status,
        },
        "collection": {
            "attempted_endpoint_count": result.attempted_endpoints,
            "successful_endpoint_count": result.successful_endpoints,
            "warning_count": len(result.warnings),
            "warning_ids": sorted(set(result.warnings)),
        },
        "artifacts": {
            "compact_json": "written",
            "diagnosis_json": "written",
            "boundary_facts_json": "written" if boundary_written else "not_requested",
            "paths": "not_printed",
        },
        "readiness": compact_summary_payload(
            readiness,
            mode="one_application_history_server",
            require_supported_attention=require_supported_attention,
            fail_on_source_warnings=fail_on_source_warnings,
            required_source_contracts=("spark_history_server_compact_v1",),
        ),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    write_ascii_json_artifact(path, payload)


def output_overlap_error(args: argparse.Namespace) -> str | None:
    paths = [args.compact_out, args.diagnosis_out]
    if args.boundary_facts_out is not None:
        paths.append(args.boundary_facts_out)
    if args.summary_json is not None:
        paths.append(args.summary_json)
    if args.product_surface_summary_out is not None:
        paths.append(args.product_surface_summary_out)
    return distinct_paths_error(paths, message="output artifacts must be distinct")


if __name__ == "__main__":
    raise SystemExit(main())
