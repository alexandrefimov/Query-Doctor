#!/usr/bin/env python3
"""Import one sanitized Trino query-detail record from an HTTP archive."""

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
from query_doctor.trino.http_query_detail_archive import (
    format_trino_http_query_detail_archive_summary,
    load_trino_http_query_detail_archive,
    trino_http_query_detail_archive_boundary_export,
    trino_http_query_detail_archive_summary_payload,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import one compact, already-sanitized Trino query-detail JSON object from "
            "one explicit operator HTTP(S) archive URL. The command validates a source "
            "contract before fetching, emits only a safe summary or normalized fact "
            "boundary, and never contacts the Trino coordinator or submits SQL."
        )
    )
    parser.add_argument(
        "--source-contract",
        required=True,
        type=Path,
        help="Compact sanitized Trino query-detail archive source-contract JSON file.",
    )
    parser.add_argument(
        "--archive-url",
        required=True,
        help="Explicit operator-controlled HTTP(S) query-detail archive URL. The URL is never echoed.",
    )
    parser.add_argument(
        "--redaction-reviewed",
        action="store_true",
        help="Confirm the HTTP query-detail archive was operator-reviewed as raw-free.",
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
        "--max-contract-file-bytes",
        type=int,
        default=None,
        help="Optional source-contract file byte limit override for local dry runs.",
    )
    parser.add_argument(
        "--max-contract-bytes",
        type=int,
        default=None,
        help="Optional source-contract JSON byte limit override for local dry runs.",
    )
    parser.add_argument(
        "--max-contract-depth",
        type=int,
        default=None,
        help="Optional source-contract JSON nesting-depth limit override for local dry runs.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.redaction_reviewed:
        print(
            "[trino-http-query-detail-archive] rejected: redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1
    if args.diagnosis_out and same_path(args.source_contract, args.diagnosis_out):
        print(
            "[trino-http-query-detail-archive] rejected: "
            "compact diagnosis output must differ from input",
            file=sys.stderr,
        )
        return 2
    try:
        result = load_trino_http_query_detail_archive(
            args.source_contract,
            archive_url=args.archive_url,
            **_limit_overrides(args),
        )
    except OSError:
        print(
            "[trino-http-query-detail-archive] rejected: source contract could not be read",
            file=sys.stderr,
        )
        return 2
    except EngineFactContractError as exc:
        print(f"[trino-http-query-detail-archive] rejected: {exc}", file=sys.stderr)
        return 1

    boundary_export = None
    if args.format == "boundary-json" or args.diagnosis_out:
        boundary_export = trino_http_query_detail_archive_boundary_export(result)
    if args.diagnosis_out:
        try:
            write_trino_compact_diagnosis_out(
                args.diagnosis_out,
                boundary_export["query_detail_boundary"],
            )
        except OSError:
            print(
                "[trino-http-query-detail-archive] rejected: "
                "compact diagnosis output could not be written",
                file=sys.stderr,
            )
            return 2
        except EngineFactContractError as exc:
            print(f"[trino-http-query-detail-archive] rejected: {exc}", file=sys.stderr)
            return 1

    if args.format == "summary-json":
        print(json.dumps(trino_http_query_detail_archive_summary_payload(result), sort_keys=True))
    elif args.format == "boundary-json":
        print(json.dumps(boundary_export, sort_keys=True))
    else:
        print(format_trino_http_query_detail_archive_summary(result))
    return 0


def _limit_overrides(args: argparse.Namespace) -> dict[str, int]:
    overrides: dict[str, int] = {}
    if args.max_contract_file_bytes is not None:
        overrides["max_contract_file_bytes"] = args.max_contract_file_bytes
    if args.max_contract_bytes is not None:
        overrides["max_contract_bytes"] = args.max_contract_bytes
    if args.max_contract_depth is not None:
        overrides["max_contract_depth"] = args.max_contract_depth
    return overrides


if __name__ == "__main__":
    raise SystemExit(main())
