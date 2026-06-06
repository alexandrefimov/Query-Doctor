#!/usr/bin/env python3
"""Import one compact sanitized local Trino metadata summary without SQL execution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.trino.local_metadata_summary import (
    format_trino_local_metadata_summary_import_summary,
    load_trino_local_metadata_summary_import,
    trino_local_metadata_summary_import_boundary_export,
    trino_local_metadata_summary_import_summary_payload,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import one compact, already-sanitized local Trino metadata summary JSON file. "
            "The command validates a metadata source contract and aggregate summary counts, "
            "emits only a safe summary or normalized fact boundary, and never contacts "
            "Trino, reads metadata, executes metadata SQL, or prints object identifiers."
        )
    )
    parser.add_argument(
        "metadata_summary_json",
        type=Path,
        help="Compact sanitized local Trino metadata summary JSON file.",
    )
    parser.add_argument(
        "--source-contract",
        required=True,
        type=Path,
        help="Compact sanitized Trino metadata allowlist source-contract JSON file.",
    )
    parser.add_argument(
        "--redaction-reviewed",
        action="store_true",
        help="Confirm the local metadata summary payload was operator-reviewed as raw-free.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "summary-json", "boundary-json"),
        default="text",
        help=(
            "Output mode. text prints a safe summary; summary-json prints it as JSON; "
            "boundary-json prints a raw-free normalized fact boundary."
        ),
    )
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
    parser.add_argument(
        "--max-metadata-summary-file-bytes",
        type=int,
        default=None,
        help="Optional compact local metadata summary JSON file byte limit override.",
    )
    parser.add_argument(
        "--max-metadata-summary-depth",
        type=int,
        default=None,
        help="Optional compact local metadata summary nesting-depth limit override.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.redaction_reviewed:
        print(
            "[trino-metadata-summary] rejected: redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1
    try:
        result = load_trino_local_metadata_summary_import(
            args.source_contract,
            args.metadata_summary_json,
            **_limit_overrides(args),
        )
    except OSError:
        print("[trino-metadata-summary] rejected: input file could not be read", file=sys.stderr)
        return 2
    except EngineFactContractError as exc:
        print(f"[trino-metadata-summary] rejected: {exc}", file=sys.stderr)
        return 1

    if args.format == "summary-json":
        print(
            json.dumps(trino_local_metadata_summary_import_summary_payload(result), sort_keys=True)
        )
    elif args.format == "boundary-json":
        print(
            json.dumps(trino_local_metadata_summary_import_boundary_export(result), sort_keys=True)
        )
    else:
        print(format_trino_local_metadata_summary_import_summary(result))
    return 0


def _limit_overrides(args: argparse.Namespace) -> dict[str, int]:
    overrides: dict[str, int] = {}
    if args.max_contract_file_bytes is not None:
        overrides["max_contract_file_bytes"] = args.max_contract_file_bytes
    if args.max_contract_bytes is not None:
        overrides["max_contract_bytes"] = args.max_contract_bytes
    if args.max_contract_depth is not None:
        overrides["max_contract_depth"] = args.max_contract_depth
    if args.max_metadata_summary_file_bytes is not None:
        overrides["max_metadata_summary_file_bytes"] = args.max_metadata_summary_file_bytes
    if args.max_metadata_summary_depth is not None:
        overrides["max_metadata_summary_depth"] = args.max_metadata_summary_depth
    return overrides


if __name__ == "__main__":
    raise SystemExit(main())
