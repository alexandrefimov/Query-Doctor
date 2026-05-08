"""CLI entrypoint for deterministic profile analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from query_doctor.analyzer.action_cards import DEFAULT_LARGE_BYTES_THRESHOLD, build_action_cards
from query_doctor.analyzer.cm_metrics import build_cm_metrics_correlation
from query_doctor.analyzer.cluster_runtime_context import build_cluster_runtime_context
from query_doctor.analyzer.context_collection import (
    collect_cluster_context,
    collect_cm_query_context,
    collect_cm_timeseries_context,
    collect_impala_context,
    collect_referenced_tables,
)
from query_doctor.analyzer.evidence_quality import build_evidence_quality
from query_doctor.analyzer.facts_renderer import render_md
from query_doctor.analyzer.runtime_diagnosis import build_runtime_diagnosis
from query_doctor.analyzer.service import analyze
from query_doctor.analyzer.sql_sources import extract_default_database
from query_doctor.impala.table_metadata_facts import collect_table_metadata_context


__all__ = ["main", "parse_args", "resolve_paths"]


def resolve_paths(input_path: Path, output_arg: str | None) -> tuple[Path, Path]:
    if input_path.is_dir():
        digest_path = input_path / "profile_digest.md"
        default_output = input_path / "analysis_facts.md"
    else:
        digest_path = input_path
        default_output = input_path.with_name("analysis_facts.md")
    output_path = Path(output_arg).expanduser() if output_arg else default_output
    return digest_path, output_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministically analyze an Impala profile_digest.md and write analysis_facts.md."
    )
    parser.add_argument(
        "input",
        help="Case directory containing profile_digest.md, or path to profile_digest.md",
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
    parser.add_argument("--large-bytes-threshold", type=float, default=DEFAULT_LARGE_BYTES_THRESHOLD)
    parser.add_argument("--max-evidence-lines", type=int, default=30)
    parser.add_argument("--verbose", action="store_true", help="Include raw evidence lines and parsing details in markdown")
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    input_path = Path(args.input).expanduser()
    digest_path, output_path = resolve_paths(input_path, args.output)

    if not digest_path.exists():
        print(f"ERROR: digest not found: {digest_path}", file=sys.stderr)
        return 2

    text = digest_path.read_text(encoding="utf-8", errors="replace")
    cm_query_context = collect_cm_query_context(digest_path.parent)
    analysis = analyze(text, args, cm_query_context=cm_query_context)
    analysis["cm_query_context"] = cm_query_context
    analysis["cm_timeseries_context"] = collect_cm_timeseries_context(digest_path.parent)
    analysis["cluster_context"] = collect_cluster_context(digest_path.parent)
    analysis["impala_context"] = collect_impala_context(digest_path.parent)
    analysis["table_metadata_context"] = collect_table_metadata_context(digest_path.parent)
    analysis["referenced_tables"] = collect_referenced_tables(digest_path.parent, text)
    analysis["default_database"] = extract_default_database(text)
    analysis["cm_metrics_correlation"] = build_cm_metrics_correlation(analysis)
    analysis["cluster_runtime_context"] = build_cluster_runtime_context(analysis)
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
