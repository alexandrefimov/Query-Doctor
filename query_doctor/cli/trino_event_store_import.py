#!/usr/bin/env python3
"""Import compact sanitized Trino event-store records without echoing payloads."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.trino.local_event_store import (
    format_trino_local_event_store_summary,
    load_trino_local_event_store,
    trino_local_event_store_boundary_export,
    trino_local_event_store_summary_payload,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import compact, already-sanitized Trino event-listener records from one "
            "explicit local JSON/NDJSON file. The command validates bounds, emits only "
            "safe summaries or normalized fact boundaries, and never contacts Trino or "
            "submits SQL."
        )
    )
    parser.add_argument(
        "event_store_json",
        type=Path,
        help="Compact sanitized Trino event-store JSON, JSON array, or NDJSON file.",
    )
    parser.add_argument(
        "--redaction-reviewed",
        action="store_true",
        help="Confirm the local event-store records were operator-reviewed as raw-free.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "summary-json", "boundary-json"),
        default="text",
        help=(
            "Output mode. text prints a safe summary; summary-json prints the same safe "
            "summary as JSON; boundary-json prints raw-free normalized fact boundaries."
        ),
    )
    parser.add_argument(
        "--max-store-bytes",
        type=int,
        default=None,
        help="Optional input file byte limit override for local dry runs.",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Optional accepted event record count limit override for local dry runs.",
    )
    parser.add_argument(
        "--max-record-bytes",
        type=int,
        default=None,
        help="Optional per-record JSON byte limit override for local dry runs.",
    )
    parser.add_argument(
        "--max-record-depth",
        type=int,
        default=None,
        help="Optional per-record JSON nesting-depth limit override for local dry runs.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.redaction_reviewed:
        print(
            "[trino-event-store] rejected: redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1
    try:
        result = load_trino_local_event_store(
            args.event_store_json,
            **_limit_overrides(args),
        )
    except OSError:
        print("[trino-event-store] rejected: input file could not be read", file=sys.stderr)
        return 2
    except EngineFactContractError as exc:
        print(f"[trino-event-store] rejected: {exc}", file=sys.stderr)
        return 1

    if args.format == "summary-json":
        print(json.dumps(trino_local_event_store_summary_payload(result), sort_keys=True))
    elif args.format == "boundary-json":
        print(json.dumps(trino_local_event_store_boundary_export(result), sort_keys=True))
    else:
        print(format_trino_local_event_store_summary(result))
    return 0


def _limit_overrides(args: argparse.Namespace) -> dict[str, int]:
    overrides: dict[str, int] = {}
    if args.max_store_bytes is not None:
        overrides["max_store_bytes"] = args.max_store_bytes
    if args.max_records is not None:
        overrides["max_records"] = args.max_records
    if args.max_record_bytes is not None:
        overrides["max_record_bytes"] = args.max_record_bytes
    if args.max_record_depth is not None:
        overrides["max_record_depth"] = args.max_record_depth
    return overrides


if __name__ == "__main__":
    raise SystemExit(main())
