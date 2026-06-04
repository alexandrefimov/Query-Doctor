#!/usr/bin/env python3
"""Probe one Trino coordinator pruned query-info endpoint without mapping facts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.trino.coordinator_query_info_target import (
    format_trino_coordinator_query_info_pruned_probe_summary,
    load_trino_coordinator_query_info_auth_header_file,
    load_trino_coordinator_query_info_pruned_probe,
    trino_coordinator_query_info_pruned_probe_summary_payload,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Probe one Trino coordinator GET /v1/query/{queryId}?pruned=true target "
            "after validating a compact source contract. The command emits only a "
            "safe summary, does not print the coordinator URL, Query ID, or query-info "
            "payload, and does not map raw QueryInfo into diagnosis facts."
        )
    )
    parser.add_argument(
        "--source-contract",
        required=True,
        type=Path,
        help="Compact sanitized Trino coordinator query-info source-contract JSON file.",
    )
    parser.add_argument(
        "--coordinator-url",
        required=True,
        help="Explicit Trino coordinator base URL. The URL is used for the probe but never echoed.",
    )
    parser.add_argument(
        "--query-id",
        required=True,
        help="Explicit known Trino query ID. The query ID is used for the probe but never echoed.",
    )
    parser.add_argument(
        "--redaction-reviewed",
        action="store_true",
        help="Confirm the query-info source contract was operator-reviewed as raw-free.",
    )
    parser.add_argument(
        "--auth-header-file",
        type=Path,
        default=None,
        help=(
            "Optional local file containing one operator-managed Authorization header line. "
            "The file path and header value are never printed."
        ),
    )
    parser.add_argument(
        "--format",
        choices=("text", "summary-json"),
        default="text",
        help="Output mode. text prints a safe summary; summary-json prints it as JSON.",
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.redaction_reviewed:
        print(
            "[trino-coordinator-query-info-pruned-probe] rejected: "
            "redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1
    try:
        auth_headers = _auth_headers(args)
    except OSError:
        print(
            "[trino-coordinator-query-info-pruned-probe] rejected: "
            "auth header file could not be read",
            file=sys.stderr,
        )
        return 2
    except EngineFactContractError as exc:
        print(f"[trino-coordinator-query-info-pruned-probe] rejected: {exc}", file=sys.stderr)
        return 1
    try:
        result = load_trino_coordinator_query_info_pruned_probe(
            args.source_contract,
            coordinator_url=args.coordinator_url,
            query_id=args.query_id,
            auth_headers=auth_headers,
            **_limit_overrides(args),
        )
    except OSError:
        print(
            "[trino-coordinator-query-info-pruned-probe] rejected: "
            "source contract could not be read",
            file=sys.stderr,
        )
        return 2
    except EngineFactContractError as exc:
        print(f"[trino-coordinator-query-info-pruned-probe] rejected: {exc}", file=sys.stderr)
        return 1

    if args.format == "summary-json":
        print(
            json.dumps(
                trino_coordinator_query_info_pruned_probe_summary_payload(result),
                sort_keys=True,
            )
        )
    else:
        print(format_trino_coordinator_query_info_pruned_probe_summary(result))
    return 0


def _auth_headers(args: argparse.Namespace) -> dict[str, str] | None:
    if args.auth_header_file is None:
        return None
    return load_trino_coordinator_query_info_auth_header_file(args.auth_header_file)


def _limit_overrides(args: argparse.Namespace) -> dict[str, int]:
    overrides: dict[str, int] = {}
    if args.max_contract_file_bytes is not None:
        overrides["max_file_bytes"] = args.max_contract_file_bytes
    if args.max_contract_bytes is not None:
        overrides["max_contract_bytes"] = args.max_contract_bytes
    if args.max_contract_depth is not None:
        overrides["max_contract_depth"] = args.max_contract_depth
    return overrides


if __name__ == "__main__":
    raise SystemExit(main())
