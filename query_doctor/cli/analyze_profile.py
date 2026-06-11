"""CLI entrypoint for deterministic profile analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from query_doctor.analyzer.action_cards import DEFAULT_LARGE_BYTES_THRESHOLD, build_action_cards
from query_doctor.analyzer.case_bottleneck import classify_case_primary_bottleneck
from query_doctor.analyzer.cm_metrics import build_cm_metrics_correlation, build_cm_metrics_facts
from query_doctor.analyzer.cluster_runtime_context import build_cluster_runtime_context
from query_doctor.analyzer.context_collection import (
    MANUAL_PROFILE_TEXT_SOURCE,
    collect_admission_context,
    collect_cluster_context,
    collect_cm_query_context,
    collect_cm_timeseries_context,
    collect_impala_context,
    collect_referenced_tables,
    collect_sql_column_context,
)
from query_doctor.analyzer.data_movement import build_data_movement_facts
from query_doctor.analyzer.evidence_quality import build_evidence_quality
from query_doctor.analyzer.facts_renderer import render_md
from query_doctor.analyzer.memory_pressure import (
    apply_memory_pressure_profile_policy,
    build_memory_pressure_facts,
)
from query_doctor.analyzer.metadata_renderer import stats_metadata_quality
from query_doctor.analyzer.profile_counter_registry import (
    load_profile_counter_registry_context,
    profile_counter_registry_context_summary,
    profile_counter_registry_from_context,
)
from query_doctor.analyzer.runtime_admission import build_runtime_admission_facts
from query_doctor.analyzer.runtime_diagnosis import build_runtime_diagnosis
from query_doctor.analyzer.scan_skew import build_scan_skew_facts
from query_doctor.analyzer.service import analyze
from query_doctor.analyzer.source_provenance import build_source_provenance
from query_doctor.analyzer.storage_context import build_storage_context
from query_doctor.analyzer.sql_sources import extract_default_database
from query_doctor.cm.client import DEFAULT_MAX_PROFILE_BYTES, validate_cm_query_id_path_segment
from query_doctor.cm.models import CMAdapterError, CMQuerySummary, OutputError
from query_doctor.cm.profile_collection import write_collected_case
from query_doctor.cm.profile_parsing import (
    extract_statement_from_profile_text,
    merge_profile_summary_metadata,
)
from query_doctor.impala.table_metadata_facts import collect_table_metadata_context


__all__ = [
    "ManualProfileIntakeError",
    "main",
    "parse_args",
    "resolve_paths",
    "stage_manual_profile_case",
]


class ManualProfileIntakeError(RuntimeError):
    """Safe CLI error for local exported-profile staging failures."""


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def resolve_paths(input_path: Path, output_arg: str | None) -> tuple[Path, Path]:
    if input_path.is_dir():
        digest_path = input_path / "profile_digest.md"
        default_output = input_path / "analysis_facts.md"
    else:
        digest_path = input_path
        default_output = input_path.with_name("analysis_facts.md")
    output_path = Path(output_arg).expanduser() if output_arg else default_output
    return digest_path, output_path


def read_manual_profile_text(profile_path: Path, *, max_bytes: int) -> str:
    path = profile_path.expanduser()
    try:
        if not path.is_file():
            raise ManualProfileIntakeError("Profile text file was not found.")
        if path.stat().st_size > max_bytes:
            raise ManualProfileIntakeError(
                f"Profile text exceeds --max-profile-bytes ({max_bytes})."
            )
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ManualProfileIntakeError("Profile text file could not be read.") from exc
    if not text.strip():
        raise ManualProfileIntakeError("Profile text file is empty.")
    if text.lstrip().startswith(("{", "[")):
        raise ManualProfileIntakeError(
            "Manual profile intake accepts exported text profiles only; JSON, "
            "Thrift, and profile-v2 payloads are not supported by this command."
        )
    return text


def stage_manual_profile_case(
    *,
    profile_text_path: Path,
    query_id: str,
    out_dir: Path,
    redact_identifiers: bool = False,
    redact_hosts: bool = True,
    max_profile_bytes: int = DEFAULT_MAX_PROFILE_BYTES,
) -> Path:
    """Stage one local exported Impala text profile as a collector-shaped case."""
    validated_query_id = validate_cm_query_id_path_segment(query_id)
    profile_text = read_manual_profile_text(profile_text_path, max_bytes=max_profile_bytes)
    statement = extract_statement_from_profile_text(profile_text)
    summary = CMQuerySummary(query_id=validated_query_id, statement=statement)
    summary, profile_warnings = merge_profile_summary_metadata(summary, profile_text)
    warnings = [
        "Local exported Impala text profile staged without network collection",
        "Cloudera Manager discovery, metrics, events, and live metadata were not collected for this manual-profile case",
        *profile_warnings,
    ]
    return write_collected_case(
        out_dir,
        summary,
        profile_digest_text=profile_text,
        extra_metadata={
            "profile_source": MANUAL_PROFILE_TEXT_SOURCE,
            "profile_response_format": "text",
            "profile_fetch_attempt_count": 0,
            "profile_json_probe_enabled": False,
            "profile_docs_probe_enabled": False,
            "profile_docs_fetch_attempt_count": 0,
        },
        warnings=warnings,
        redact=True,
        redact_identifiers=redact_identifiers,
        redact_hosts=redact_hosts,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministically analyze an Impala profile_digest.md, or stage one "
            "local exported text profile into a case and analyze it."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Case directory containing profile_digest.md, or path to profile_digest.md",
    )
    parser.add_argument(
        "--profile-text",
        type=Path,
        help=(
            "Local exported Impala text profile to stage before analysis. "
            "This path performs no network collection."
        ),
    )
    parser.add_argument(
        "--query-id",
        help="Explicit Impala Query ID for --profile-text staging.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help=(
            "Output corpus directory for --profile-text staging. The case is written "
            "under this directory using the Query ID slug."
        ),
    )
    parser.add_argument(
        "--redact-identifiers",
        action="store_true",
        help="For --profile-text, redact SQL table identifiers in the staged local profile.",
    )
    parser.add_argument(
        "--no-redact-hosts",
        action="store_false",
        default=True,
        dest="redact_hosts",
        help="For --profile-text, preserve hostnames in local artifacts. Do not use for shared outputs.",
    )
    parser.add_argument(
        "--max-profile-bytes",
        type=positive_int,
        default=DEFAULT_MAX_PROFILE_BYTES,
        help=(
            "Maximum local profile text bytes accepted by --profile-text. "
            f"Default: {DEFAULT_MAX_PROFILE_BYTES}."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output markdown file. Default: <case-dir>/analysis_facts.md",
    )
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--rows-ratio-threshold", type=float, default=10.0)
    parser.add_argument("--mem-ratio-threshold", type=float, default=4.0)
    parser.add_argument("--slow-operator-ms", type=float, default=10_000.0)
    parser.add_argument("--large-rows-threshold", type=float, default=1_000_000.0)
    parser.add_argument(
        "--large-bytes-threshold", type=float, default=DEFAULT_LARGE_BYTES_THRESHOLD
    )
    parser.add_argument("--max-evidence-lines", type=int, default=30)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include raw evidence lines and parsing details in markdown",
    )
    parser.add_argument("--stdout", action="store_true", help="Also print markdown to stdout")
    parser.add_argument(
        "--json",
        nargs="?",
        const="-",
        metavar="PATH",
        help="Write machine-readable JSON to stdout, or to PATH if provided",
    )
    parser.add_argument(
        "--fail-on-empty",
        action="store_true",
        help="Exit with non-zero status if no operators were parsed",
    )
    args = parser.parse_args(argv)
    if args.profile_text:
        if args.input:
            parser.error("positional input cannot be combined with --profile-text")
        if not args.query_id:
            parser.error("--profile-text requires --query-id")
        if args.out is None:
            parser.error("--profile-text requires --out")
    elif not args.input:
        parser.error("input is required unless --profile-text is used")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.profile_text:
        try:
            input_path = stage_manual_profile_case(
                profile_text_path=args.profile_text,
                query_id=args.query_id,
                out_dir=args.out,
                redact_identifiers=args.redact_identifiers,
                redact_hosts=args.redact_hosts,
                max_profile_bytes=args.max_profile_bytes,
            )
        except (ManualProfileIntakeError, CMAdapterError, OutputError, OSError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        if args.json is None:
            args.json = str(input_path / "analysis.json")
    else:
        input_path = Path(args.input).expanduser()
    digest_path, output_path = resolve_paths(input_path, args.output)

    if not digest_path.exists():
        print(f"ERROR: digest not found: {digest_path}", file=sys.stderr)
        return 2

    text = digest_path.read_text(encoding="utf-8", errors="replace")
    collected_query_context = collect_cm_query_context(digest_path.parent)
    profile_counter_registry_context = load_profile_counter_registry_context(digest_path.parent)
    profile_counter_registry = profile_counter_registry_from_context(
        profile_counter_registry_context
    )
    analysis = analyze(
        text,
        args,
        cm_query_context=collected_query_context,
        counter_registry=profile_counter_registry,
    )
    analysis["profile_counter_registry"] = profile_counter_registry_context_summary(
        profile_counter_registry_context
    )
    analysis["query_context"] = collected_query_context
    analysis["cm_query_context"] = collected_query_context
    metrics_context = collect_cm_timeseries_context(digest_path.parent)
    analysis["metrics_context"] = metrics_context
    analysis["cm_timeseries_context"] = metrics_context
    metrics_facts = build_cm_metrics_facts(metrics_context) if metrics_context else None
    analysis["metrics_facts"] = metrics_facts
    analysis["cm_metrics_facts"] = metrics_facts
    analysis["cluster_context"] = collect_cluster_context(digest_path.parent)
    analysis["admission_context"] = collect_admission_context(digest_path.parent)
    analysis["impala_context"] = collect_impala_context(digest_path.parent)
    analysis["table_metadata_context"] = collect_table_metadata_context(digest_path.parent)
    analysis["sql_column_context"] = collect_sql_column_context(
        digest_path.parent,
        text,
        analysis["table_metadata_context"],
    )
    analysis["scan_skew"] = build_scan_skew_facts(analysis)
    analysis["storage_context"] = build_storage_context(analysis)
    analysis["data_movement"] = build_data_movement_facts(analysis)
    analysis["stats_metadata_quality"] = stats_metadata_quality(
        analysis["table_metadata_context"] or {},
        analysis,
    )
    analysis["runtime_admission"] = build_runtime_admission_facts(analysis)
    profile_format = (
        analysis.get("profile_format") if isinstance(analysis.get("profile_format"), dict) else {}
    )
    analysis["memory_pressure"] = apply_memory_pressure_profile_policy(
        build_memory_pressure_facts(analysis, counter_registry=profile_counter_registry),
        profile_format,
    )
    analysis["case_primary_bottleneck"] = classify_case_primary_bottleneck(analysis).to_dict()
    analysis["referenced_tables"] = collect_referenced_tables(digest_path.parent, text)
    analysis["default_database"] = extract_default_database(text)
    metrics_correlation = build_cm_metrics_correlation(analysis)
    analysis["metrics_correlation"] = metrics_correlation
    analysis["cm_metrics_correlation"] = metrics_correlation
    analysis["cluster_runtime_context"] = build_cluster_runtime_context(analysis)
    analysis["source_provenance"] = build_source_provenance(analysis)
    analysis["runtime_diagnosis"] = build_runtime_diagnosis(analysis)
    analysis["action_cards"] = build_action_cards(analysis)
    analysis["evidence_quality"] = build_evidence_quality(analysis)

    if args.fail_on_empty and not analysis["operators"]:
        print("ERROR: no operators parsed from digest", file=sys.stderr)
        return 3

    markdown = render_md(analysis, digest_path, verbose=args.verbose)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    json_text = json.dumps(analysis, ensure_ascii=False, indent=2)
    if args.json and args.json != "-":
        json_path = Path(args.json).expanduser()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json_text + "\n", encoding="utf-8")
    else:
        json_path = None

    status_stream = sys.stderr if args.json == "-" else sys.stdout
    if args.profile_text:
        print(f"Output case directory: {input_path}", file=status_stream)
    print(f"Wrote: {output_path}", file=status_stream)
    if json_path:
        print(f"Wrote JSON: {json_path}", file=status_stream)
    print(f"Parsed operators: {len(analysis['operators'])}", file=status_stream)
    print(f"Cardinality anomalies: {len(analysis['cardinality_anomalies'])}", file=status_stream)
    print(f"Memory anomalies: {len(analysis['memory_anomalies'])}", file=status_stream)

    if args.stdout:
        print()
        print(markdown)
    if args.json == "-":
        try:
            print(json_text)
        except BrokenPipeError:
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
