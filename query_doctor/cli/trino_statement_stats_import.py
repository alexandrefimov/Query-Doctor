#!/usr/bin/env python3
"""Import one compact sanitized Trino statement-stats payload without echoing payloads."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.cli.trino_diagnosis_output import (
    add_trino_diagnosis_out_argument,
    same_path,
    write_trino_compact_diagnosis_out,
)
from query_doctor.trino.local_statement_stats import (
    format_trino_local_statement_stats_summary,
    load_trino_local_statement_stats,
    trino_local_statement_stats_boundary_export,
    trino_local_statement_stats_summary_payload,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import one compact, already-sanitized Trino QueryResults statementStats/rootStage "
            "JSON file. The command validates bounds, emits only a safe summary or "
            "normalized fact boundary, and never contacts Trino, calls /v1/statement, "
            "or submits SQL."
        )
    )
    parser.add_argument(
        "statement_stats_json",
        type=Path,
        help="Compact sanitized Trino statement-stats JSON file.",
    )
    parser.add_argument(
        "--redaction-reviewed",
        action="store_true",
        help="Confirm the local statement-stats payload was operator-reviewed as raw-free.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "summary-json", "boundary-json"),
        default="text",
        help=(
            "Output mode. text prints a safe summary; summary-json prints the same safe "
            "summary as JSON; boundary-json prints a raw-free normalized fact boundary."
        ),
    )
    add_trino_diagnosis_out_argument(parser)
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=None,
        help="Optional input file byte limit override for local dry runs.",
    )
    parser.add_argument(
        "--max-statement-stats-bytes",
        type=int,
        default=None,
        help="Optional compact statement-stats JSON byte limit override for local dry runs.",
    )
    parser.add_argument(
        "--max-statement-stats-depth",
        type=int,
        default=None,
        help="Optional compact statement-stats nesting-depth limit override for local dry runs.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.redaction_reviewed:
        print(
            "[trino-statement-stats] rejected: redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1
    if args.diagnosis_out and same_path(args.statement_stats_json, args.diagnosis_out):
        print(
            "[trino-statement-stats] rejected: compact diagnosis output must differ from input",
            file=sys.stderr,
        )
        return 2
    try:
        result = load_trino_local_statement_stats(
            args.statement_stats_json,
            **_limit_overrides(args),
        )
    except OSError:
        print("[trino-statement-stats] rejected: input file could not be read", file=sys.stderr)
        return 2
    except EngineFactContractError as exc:
        print(f"[trino-statement-stats] rejected: {exc}", file=sys.stderr)
        return 1

    boundary_export = None
    if args.format == "boundary-json" or args.diagnosis_out:
        boundary_export = trino_local_statement_stats_boundary_export(result)
    if args.diagnosis_out:
        try:
            write_trino_compact_diagnosis_out(
                args.diagnosis_out,
                boundary_export["statement_stats_boundary"],
            )
        except OSError:
            print(
                "[trino-statement-stats] rejected: compact diagnosis output could not be written",
                file=sys.stderr,
            )
            return 2
        except EngineFactContractError as exc:
            print(f"[trino-statement-stats] rejected: {exc}", file=sys.stderr)
            return 1

    if args.format == "summary-json":
        print(json.dumps(trino_local_statement_stats_summary_payload(result), sort_keys=True))
    elif args.format == "boundary-json":
        print(json.dumps(boundary_export, sort_keys=True))
    else:
        print(format_trino_local_statement_stats_summary(result))
    return 0


def _limit_overrides(args: argparse.Namespace) -> dict[str, int]:
    overrides: dict[str, int] = {}
    if args.max_file_bytes is not None:
        overrides["max_file_bytes"] = args.max_file_bytes
    if args.max_statement_stats_bytes is not None:
        overrides["max_statement_stats_bytes"] = args.max_statement_stats_bytes
    if args.max_statement_stats_depth is not None:
        overrides["max_statement_stats_depth"] = args.max_statement_stats_depth
    return overrides


if __name__ == "__main__":
    raise SystemExit(main())
