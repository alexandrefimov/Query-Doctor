#!/usr/bin/env python3
"""Build a synthetic Recent batch summary from successful retry case directories."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.recent.batch_models import BatchConfig, CaseResult, DiscoveryResult
from query_doctor.recent.batch_scoring import inspect_case_outputs, score_case
from query_doctor.recent.batch_summary import build_summary, write_batch_outputs


AGGREGATE_CASE_FILES = (
    "profile_digest.md",
    "analysis_facts.md",
    "analysis.json",
    "query_metadata.json",
    "cm_metadata.json",
    "collection_warnings.txt",
    "impala_context.json",
)


@dataclass(frozen=True)
class AggregateBuildResult:
    summary_path: Path
    case_count: int
    duplicate_case_count: int
    missing_source_case_count: int


class AggregateInputError(RuntimeError):
    """Raised when retry summary inputs are not usable."""


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AggregateInputError(f"cannot read JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AggregateInputError(f"file is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise AggregateInputError(f"JSON root is not an object: {path}")
    return payload


def source_cases_by_index(summary: dict[str, Any]) -> dict[int, dict[str, Any]]:
    cases = summary.get("cases")
    if not isinstance(cases, list):
        return {}
    result: dict[int, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        index = safe_positive_int(case.get("case_index"))
        if index is not None:
            result[index] = case
    return result


def discover_successful_case_dirs(roots: Iterable[Path]) -> tuple[dict[int, Path], int]:
    case_dirs: dict[int, Path] = {}
    duplicate_count = 0
    for root in roots:
        if not root.is_dir():
            raise AggregateInputError(f"case root is not a directory: {root}")
        for analysis_path in sorted(root.rglob("analysis.json")):
            case_dir = analysis_path.parent
            if not (case_dir / "analysis_facts.md").is_file():
                continue
            if not (case_dir / "profile_digest.md").is_file():
                continue
            index = case_index_from_path(case_dir)
            if index is None:
                continue
            if index in case_dirs:
                duplicate_count += 1
                continue
            case_dirs[index] = case_dir
    return case_dirs, duplicate_count


def case_index_from_path(path: Path) -> int | None:
    for part in path.parts:
        if part.startswith("case-"):
            value = safe_positive_int(part.removeprefix("case-"))
            if value is not None:
                return value
    return None


def safe_positive_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def build_case_result(
    index: int,
    actual_case_dir: Path,
    *,
    source_case: dict[str, Any] | None,
) -> CaseResult:
    analysis = load_optional_json_object(actual_case_dir / "analysis.json")
    query_context = analysis.get("query_context") if isinstance(analysis, dict) else {}
    query_context = query_context if isinstance(query_context, dict) else {}
    source_case = source_case or {}
    case = CaseResult(
        index=index,
        query_id=safe_string(source_case.get("query_id")) or f"case-{index:03d}",
        duration_sec=safe_float(source_case.get("duration_sec"))
        or duration_from_query_context(query_context),
        user=safe_string(source_case.get("user")),
        pool=safe_string(source_case.get("pool")),
        query_type=safe_string(source_case.get("query_type"))
        or safe_string(query_context.get("query_type")),
        sql_verb=safe_string(source_case.get("sql_verb")),
        wrapper_dir=Path("cases") / f"case-{index:03d}",
        actual_case_dir=actual_case_dir,
        collection_status="ok",
        analysis_status="ok",
        metadata_status=safe_string(source_case.get("metadata_status")) or "not_requested",
        report_validation_status=safe_string(source_case.get("report_validation_status"))
        or "not_run",
    )
    inspect_case_outputs(case)
    if case.metadata_status == "skipped":
        case.metadata_status = "not_requested"
    score_case(case)
    return case


def load_optional_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def safe_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def duration_from_query_context(query_context: dict[str, Any]) -> float | None:
    duration_ms = safe_float(query_context.get("duration_ms"))
    if duration_ms is not None:
        return duration_ms / 1000.0
    return safe_float(query_context.get("duration_sec"))


def build_config(out: Path, source_summary: dict[str, Any]) -> BatchConfig:
    return BatchConfig(
        out=out,
        cm_url=None,
        cluster=None,
        service=None,
        cm_username=None,
        ca_bundle=None,
        verify_tls=True,
        recent_window_minutes=int(source_summary.get("recent_window_minutes") or 0),
        cm_inspect_limit=int(source_summary.get("cm_inspect_limit") or 0),
        triage_profile_limit=int(source_summary.get("triage_profile_limit") or 0),
        metadata_top_limit=int(source_summary.get("metadata_top_limit") or 0),
        min_duration_sec=safe_float(source_summary.get("min_duration_sec")),
        max_duration_sec=safe_float(source_summary.get("max_duration_sec")),
        order=str(source_summary.get("order") or "duration-desc"),
        include_failed=bool(source_summary.get("include_failed")),
        include_running=bool(source_summary.get("include_running")),
        user=None,
        pool=None,
        query_type=None,
        max_profile_bytes=0,
        collect_cm_events=False,
        cm_events_max_events=0,
        collect_cm_timeseries=False,
        cm_metrics_profile="default",
        cm_timeseries_top_limit=0,
        cm_timeseries_padding_sec=0,
        max_timeseries_bytes=0,
        max_timeseries_points=0,
        metadata_mode="off",
        metadata_coordinator=None,
        metadata_auth="none",
        metadata_protocol="hs2",
        metadata_kerberos_service_name=None,
        metadata_ssl=False,
        metadata_ca_cert=None,
        metadata_timeout_sec=0,
        metadata_max_tables=None,
        metadata_max_output_bytes=None,
        metadata_redact=True,
        top_reports=0,
        cm_jobs=0,
        jobs=0,
        metadata_jobs=0,
        allow_high_jobs=False,
        discover_only=False,
        overwrite=True,
        config_path=None,
        progress_jsonl=None,
        krb5ccname=None,
        from_time=safe_string(source_summary.get("from_time")),
        to_time=safe_string(source_summary.get("to_time")),
        only_running=bool(source_summary.get("only_running")),
        query_profile_source=str(source_summary.get("query_profile_source") or "cm"),
        source_visibility="safe",
    )


def build_discovery(source_summary: dict[str, Any], case_count: int) -> DiscoveryResult:
    inspected = safe_positive_int(source_summary.get("summaries_inspected")) or case_count
    return DiscoveryResult(
        candidates=[],
        warnings=[],
        duration_filter_mode=str(source_summary.get("duration_filter_mode") or "unknown"),
        server_filter_expression=None,
        summaries_inspected=inspected,
        scan_too_broad=bool(source_summary.get("scan_too_broad")),
        raw_summary_scan_cap_hit=bool(source_summary.get("cm_summary_raw_scan_cap_hit")),
        time_sharded=bool(source_summary.get("time_sharded")),
        time_shard_count=int(source_summary.get("time_shard_count") or 0),
        time_shard_minutes=safe_positive_int(source_summary.get("time_shard_minutes")),
        time_shard_min_minutes=safe_positive_int(source_summary.get("time_shard_min_minutes")),
        time_shard_scan_limit_warning_count=int(
            source_summary.get("time_shard_scan_limit_warning_count") or 0
        ),
    )


def prepare_output(out: Path, *, overwrite: bool) -> None:
    if out.exists():
        if not overwrite:
            raise AggregateInputError(f"output directory already exists: {out}")
        shutil.rmtree(out)
    (out / "cases").mkdir(parents=True, exist_ok=True)


def materialize_case_dirs(out: Path, case_dirs: dict[int, Path]) -> None:
    for index, actual_case_dir in sorted(case_dirs.items()):
        target = out / "cases" / f"case-{index:03d}"
        target.mkdir(parents=True, exist_ok=True)
        for filename in AGGREGATE_CASE_FILES:
            source = actual_case_dir / filename
            if source.is_file():
                shutil.copy2(source, target / filename)


def build_aggregate_summary(
    *,
    source_summary_path: Path,
    case_roots: tuple[Path, ...],
    out: Path,
    overwrite: bool = False,
) -> AggregateBuildResult:
    source_summary = load_json_object(source_summary_path)
    source_cases = source_cases_by_index(source_summary)
    case_dirs, duplicate_count = discover_successful_case_dirs(case_roots)
    if not case_dirs:
        raise AggregateInputError("no successful case directories found")
    prepare_output(out, overwrite=overwrite)
    materialize_case_dirs(out, case_dirs)
    cases = [
        build_case_result(index, case_dir, source_case=source_cases.get(index))
        for index, case_dir in sorted(case_dirs.items())
    ]
    missing_source_count = sum(1 for index in case_dirs if index not in source_cases)
    summary = build_summary(
        build_config(out, source_summary),
        build_discovery(source_summary, len(cases)),
        cases,
        [
            "synthetic aggregate summary built from successful retry case directories",
            "case directories are materialized under this output root for offline audits",
        ],
        discovery_seconds=None,
        total_seconds=0.0,
    )
    summary["aggregate_retry_summary"] = {
        "successful_case_count": len(cases),
        "input_case_root_count": len(case_roots),
        "duplicate_successful_case_count": duplicate_count,
        "missing_source_case_count": missing_source_count,
    }
    write_batch_outputs(out, summary)
    return AggregateBuildResult(
        summary_path=out / "batch_summary.json",
        case_count=len(cases),
        duplicate_case_count=duplicate_count,
        missing_source_case_count=missing_source_count,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a synthetic batch_summary.json from successful case directories "
            "across an original Recent scan and retry outputs."
        )
    )
    parser.add_argument("--source-summary", required=True, type=Path)
    parser.add_argument("--case-root", required=True, action="append", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = build_aggregate_summary(
            source_summary_path=args.source_summary,
            case_roots=tuple(args.case_root),
            out=args.out,
            overwrite=args.overwrite,
        )
    except AggregateInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Summary: {result.summary_path}")
    print(f"Successful cases: {result.case_count}")
    print(f"Duplicate successful case dirs skipped: {result.duplicate_case_count}")
    print(f"Cases missing from source summary: {result.missing_source_case_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
