#!/usr/bin/env python3
"""Import one Trino coordinator pruned QueryInfo response as raw-free facts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.cli.trino_diagnosis_output import (
    add_trino_boundary_out_argument,
    add_trino_diagnosis_out_argument,
    same_path,
    write_trino_boundary_out,
    write_trino_compact_diagnosis_out,
)
from query_doctor.trino.coordinator_query_info_pruned_import import (
    format_trino_coordinator_query_info_pruned_import_summary,
    load_trino_coordinator_query_info_pruned_import,
    trino_coordinator_query_info_pruned_import_boundary_export,
    trino_coordinator_query_info_pruned_import_summary_payload,
)
from query_doctor.trino.coordinator_query_info_target import (
    load_trino_coordinator_query_info_auth_header_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import one Trino coordinator GET /v1/query/{queryId}?pruned=true response "
            "after validating a compact source contract. The command emits only a safe "
            "summary or normalized fact boundary, never prints the coordinator URL, "
            "Query ID, or query-info payload, and never submits SQL."
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
        help="Explicit Trino coordinator base URL. The URL is used for the read but never echoed.",
    )
    parser.add_argument(
        "--query-id",
        required=True,
        help="Explicit known Trino query ID. The query ID is used for the read but never echoed.",
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
        choices=("text", "summary-json", "boundary-json"),
        default="text",
        help=(
            "Output mode. text prints a safe summary; summary-json prints it as JSON; "
            "boundary-json prints a raw-free normalized fact boundary."
        ),
    )
    add_trino_diagnosis_out_argument(parser)
    add_trino_boundary_out_argument(parser)
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
            "[trino-coordinator-query-info-pruned-import] rejected: "
            "redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1
    if args.diagnosis_out and same_path(args.source_contract, args.diagnosis_out):
        print(
            "[trino-coordinator-query-info-pruned-import] rejected: "
            "compact diagnosis output must differ from input",
            file=sys.stderr,
        )
        return 2
    if args.boundary_out and same_path(args.source_contract, args.boundary_out):
        print(
            "[trino-coordinator-query-info-pruned-import] rejected: "
            "boundary output must differ from source contract",
            file=sys.stderr,
        )
        return 2
    if (
        args.boundary_out
        and args.diagnosis_out
        and same_path(args.boundary_out, args.diagnosis_out)
    ):
        print(
            "[trino-coordinator-query-info-pruned-import] rejected: "
            "boundary output must differ from compact diagnosis output",
            file=sys.stderr,
        )
        return 2
    if (
        args.diagnosis_out
        and args.auth_header_file is not None
        and same_path(args.auth_header_file, args.diagnosis_out)
    ):
        print(
            "[trino-coordinator-query-info-pruned-import] rejected: "
            "compact diagnosis output must differ from auth header file",
            file=sys.stderr,
        )
        return 2
    if (
        args.boundary_out
        and args.auth_header_file is not None
        and same_path(args.auth_header_file, args.boundary_out)
    ):
        print(
            "[trino-coordinator-query-info-pruned-import] rejected: "
            "boundary output must differ from auth header file",
            file=sys.stderr,
        )
        return 2
    try:
        auth_headers = _auth_headers(args)
    except OSError:
        print(
            "[trino-coordinator-query-info-pruned-import] rejected: "
            "auth header file could not be read",
            file=sys.stderr,
        )
        return 2
    except EngineFactContractError as exc:
        print(f"[trino-coordinator-query-info-pruned-import] rejected: {exc}", file=sys.stderr)
        return 1
    try:
        result = load_trino_coordinator_query_info_pruned_import(
            args.source_contract,
            coordinator_url=args.coordinator_url,
            query_id=args.query_id,
            auth_headers=auth_headers,
            **_limit_overrides(args),
        )
    except OSError:
        print(
            "[trino-coordinator-query-info-pruned-import] rejected: "
            "source contract could not be read",
            file=sys.stderr,
        )
        return 2
    except EngineFactContractError as exc:
        print(f"[trino-coordinator-query-info-pruned-import] rejected: {exc}", file=sys.stderr)
        return 1

    boundary_export = None
    if args.format == "boundary-json" or args.diagnosis_out or args.boundary_out:
        boundary_export = trino_coordinator_query_info_pruned_import_boundary_export(result)
    if args.boundary_out:
        try:
            write_trino_boundary_out(
                args.boundary_out,
                boundary_export["query_info_boundary"],
            )
        except OSError:
            print(
                "[trino-coordinator-query-info-pruned-import] rejected: "
                "boundary output could not be written",
                file=sys.stderr,
            )
            return 2
    if args.diagnosis_out:
        try:
            write_trino_compact_diagnosis_out(
                args.diagnosis_out,
                boundary_export["query_info_boundary"],
            )
        except OSError:
            print(
                "[trino-coordinator-query-info-pruned-import] rejected: "
                "compact diagnosis output could not be written",
                file=sys.stderr,
            )
            return 2
        except EngineFactContractError as exc:
            print(
                f"[trino-coordinator-query-info-pruned-import] rejected: {exc}",
                file=sys.stderr,
            )
            return 1

    if args.format == "summary-json":
        print(
            json.dumps(
                trino_coordinator_query_info_pruned_import_summary_payload(result),
                sort_keys=True,
            )
        )
    elif args.format == "boundary-json":
        print(json.dumps(boundary_export, sort_keys=True))
    else:
        print(format_trino_coordinator_query_info_pruned_import_summary(result))
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
