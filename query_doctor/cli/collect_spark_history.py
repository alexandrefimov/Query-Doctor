"""Collect a raw-free compact Spark History Server summary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from query_doctor.analyzer.engine_facts import (
    EngineFactContractError,
    engine_fact_boundary_payload,
)
from query_doctor.analyzer.spark_fixture_facts import (
    build_spark_history_server_compact_engine_facts,
)
from query_doctor.cm.models import CMClientError
from query_doctor.spark.diagnosis import build_spark_compact_diagnosis
from query_doctor.spark.history_server import (
    DEFAULT_MAX_SPARK_HISTORY_RESPONSE_BYTES,
    DEFAULT_SPARK_HISTORY_MAX_APPLICATION_ATTEMPTS,
    DEFAULT_SPARK_HISTORY_MAX_JOBS,
    DEFAULT_SPARK_HISTORY_MAX_SQL_EXECUTIONS,
    DEFAULT_SPARK_HISTORY_MAX_STAGES,
    DEFAULT_SPARK_HISTORY_MAX_TASK_SUMMARIES,
    DEFAULT_SPARK_HISTORY_MAX_TASKS_SAMPLED,
    DEFAULT_SPARK_HISTORY_TIMEOUT_SEC,
    collect_spark_history_server_compact_summary,
)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect a bounded raw-free compact summary from Spark History Server. "
            "This does not execute Spark jobs, download event logs, or collect raw SQL/plans. "
            "It does not claim Spark product support."
        )
    )
    parser.add_argument(
        "--history-server-url",
        required=True,
        help="Spark History Server base URL. Do not include credentials, query, or fragment parts.",
    )
    parser.add_argument(
        "--allow-local-history-server-target",
        action="store_true",
        help=(
            "Allow explicit loopback, RFC1918, carrier-grade NAT, or unique-local Spark History "
            "Server targets. Metadata, link-local, reserved, documentation, multicast, and "
            "unspecified targets remain blocked."
        ),
    )
    parser.add_argument(
        "--application-id",
        required=True,
        help="Explicit Spark application id. Used only as a request selector and not written out.",
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
        help=f"Maximum SQL execution summaries to inspect. Default: {DEFAULT_SPARK_HISTORY_MAX_SQL_EXECUTIONS}.",
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
        "--out",
        type=Path,
        required=True,
        help="Output compact JSON path. The file contains raw-free aggregate fields only.",
    )
    parser.add_argument(
        "--boundary-facts-out",
        type=Path,
        help=(
            "Optional output path for normalized raw-free engine fact boundary JSON. "
            "This is not wired into browser or trusted report output."
        ),
    )
    parser.add_argument(
        "--diagnosis-out",
        type=Path,
        help=(
            "Optional output path for deterministic raw-free Spark compact diagnosis JSON. "
            "This is not Details/trusted-report output and does not claim Spark product support."
        ),
    )
    return parser.parse_args(argv)


def main(
    argv: list[str] | None = None,
    *,
    opener=None,
) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if output_paths_overlap(args.out, args.boundary_facts_out, args.diagnosis_out):
            print(
                "[Spark History collector] ERROR: output paths must be distinct.",
                file=sys.stderr,
            )
            return 3
        kwargs = {
            "history_server_url": args.history_server_url,
            "application_id": args.application_id,
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
            kwargs["opener"] = opener
        result = collect_spark_history_server_compact_summary(**kwargs)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(result.payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if args.boundary_facts_out:
            bundle = build_spark_history_server_compact_engine_facts(result.payload)
            args.boundary_facts_out.parent.mkdir(parents=True, exist_ok=True)
            args.boundary_facts_out.write_text(
                json.dumps(
                    engine_fact_boundary_payload(bundle),
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        if args.diagnosis_out:
            args.diagnosis_out.parent.mkdir(parents=True, exist_ok=True)
            args.diagnosis_out.write_text(
                json.dumps(
                    build_spark_compact_diagnosis(result.payload),
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
    except (CMClientError, EngineFactContractError) as exc:
        print(f"[Spark History collector] ERROR: {exc}", file=sys.stderr)
        return 3
    except OSError:
        print(
            "[Spark History collector] ERROR: could not write JSON safely.",
            file=sys.stderr,
        )
        return 3
    print(
        "[Spark History collector] wrote compact raw-free summary; "
        f"endpoints ok: {result.successful_endpoints}/{result.attempted_endpoints}; "
        f"warnings: {len(result.warnings)}"
    )
    return 0


def output_paths_overlap(*paths: Path | None) -> bool:
    seen: set[Path] = set()
    for path in paths:
        if path is None:
            continue
        resolved = safe_resolved_path(path)
        if resolved in seen:
            return True
        seen.add(resolved)
    return False


def safe_resolved_path(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
