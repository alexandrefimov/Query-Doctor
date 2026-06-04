#!/usr/bin/env python3
"""Validate a safe Trino event-source contract without contacting Trino."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.trino.event_source_contract import (
    format_trino_event_source_contract_summary,
    load_trino_event_source_contract,
    trino_event_source_contract_summary_payload,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate one already-reviewed Trino event-source contract JSON file for a "
            "future event-store reader. The command checks source type, auth reference, "
            "schema version, bounds, and redaction rules, emits only a safe summary, "
            "and never contacts Trino, reads event records, or submits SQL."
        )
    )
    parser.add_argument(
        "contract_json",
        type=Path,
        help="Compact sanitized Trino event-source contract JSON file.",
    )
    parser.add_argument(
        "--redaction-reviewed",
        action="store_true",
        help="Confirm the local event-source contract was operator-reviewed as raw-free.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "summary-json"),
        default="text",
        help="Output mode. text prints a safe summary; summary-json prints it as JSON.",
    )
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=None,
        help="Optional input file byte limit override for local dry runs.",
    )
    parser.add_argument(
        "--max-contract-bytes",
        type=int,
        default=None,
        help="Optional contract JSON byte limit override for local dry runs.",
    )
    parser.add_argument(
        "--max-contract-depth",
        type=int,
        default=None,
        help="Optional contract JSON nesting-depth limit override for local dry runs.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.redaction_reviewed:
        print(
            "[trino-event-source-contract] rejected: redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1
    try:
        result = load_trino_event_source_contract(args.contract_json, **_limit_overrides(args))
    except OSError:
        print(
            "[trino-event-source-contract] rejected: input file could not be read",
            file=sys.stderr,
        )
        return 2
    except EngineFactContractError as exc:
        print(f"[trino-event-source-contract] rejected: {exc}", file=sys.stderr)
        return 1

    if args.format == "summary-json":
        print(json.dumps(trino_event_source_contract_summary_payload(result), sort_keys=True))
    else:
        print(format_trino_event_source_contract_summary(result))
    return 0


def _limit_overrides(args: argparse.Namespace) -> dict[str, int]:
    overrides: dict[str, int] = {}
    if args.max_file_bytes is not None:
        overrides["max_file_bytes"] = args.max_file_bytes
    if args.max_contract_bytes is not None:
        overrides["max_contract_bytes"] = args.max_contract_bytes
    if args.max_contract_depth is not None:
        overrides["max_contract_depth"] = args.max_contract_depth
    return overrides


if __name__ == "__main__":
    raise SystemExit(main())
