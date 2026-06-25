#!/usr/bin/env python3
"""Build a sanitized aggregate Trino metadata summary through an operator CLI."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.trino.metadata_cli_summary import (
    TrinoMetadataCliError,
    build_trino_metadata_cli_plan,
    collect_trino_metadata_summary,
    format_trino_metadata_cli_collection_summary,
    format_trino_metadata_cli_plan_summary,
    metadata_cli_collection_payload,
    trino_metadata_cli_plan_summary_payload,
    validate_connector_family,
    validate_trino_cli_server,
    validate_trino_cli_user,
)
from query_doctor.trino.metadata_source_contract import load_trino_metadata_source_contract


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build one sanitized aggregate Trino metadata summary through an operator-installed "
            "Trino CLI. The command first validates a metadata allowlist contract, then uses "
            "only Python-owned read-only metadata statements for Hive or Iceberg connector "
            "families. Statement text, object identifiers, server URLs, local paths, raw "
            "metadata values, and CLI stdout/stderr are never printed."
        )
    )
    parser.add_argument(
        "--source-contract",
        required=True,
        type=Path,
        help="Compact sanitized Trino metadata allowlist source-contract JSON file.",
    )
    parser.add_argument(
        "--trino-cli",
        required=True,
        type=Path,
        help="Local operator-installed Trino CLI executable path.",
    )
    parser.add_argument(
        "--server",
        required=True,
        help="HTTPS Trino coordinator base URL for the local operator CLI run.",
    )
    parser.add_argument(
        "--connector-family",
        required=True,
        choices=("hive", "iceberg"),
        help="First-gate connector family for the allowlisted metadata read.",
    )
    parser.add_argument(
        "--user",
        help="Optional safe Trino CLI user token. Secrets and passwords are unsupported.",
    )
    parser.add_argument(
        "--redaction-reviewed",
        action="store_true",
        help="Confirm the local source contract and CLI target were operator-reviewed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the safe plan summary without executing Trino CLI.",
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        help="Optional output path for the sanitized trino_metadata_summary_v1 JSON payload.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "summary-json", "metadata-summary-json"),
        default="text",
        help=(
            "Output mode. text and summary-json are safe collection summaries; "
            "metadata-summary-json prints the sanitized aggregate metadata summary."
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
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    runner=subprocess.run,
) -> int:
    args = build_parser().parse_args(argv)
    if not args.redaction_reviewed:
        print(
            "[trino-metadata-cli-summary] rejected: redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1

    try:
        validate_trino_cli_server(args.server)
        validate_connector_family(args.connector_family)
        if args.user is not None:
            validate_trino_cli_user(args.user)
        source_contract = load_trino_metadata_source_contract(
            args.source_contract,
            **_limit_overrides(args),
        )
        if args.dry_run:
            plan = build_trino_metadata_cli_plan(
                source_contract,
                connector_family=args.connector_family,
            )
            if args.format == "metadata-summary-json":
                raise TrinoMetadataCliError(
                    "Trino metadata summary JSON requires executing the metadata CLI"
                )
            _print_plan(source_contract, plan, format_name=args.format)
            return 0
        if args.summary_out is not None:
            _validate_summary_out(args.summary_out, args.source_contract)
        result = collect_trino_metadata_summary(
            source_contract,
            trino_cli=args.trino_cli,
            server=args.server,
            connector_family=args.connector_family,
            user=args.user,
            runner=runner,
        )
        if args.summary_out is not None:
            _write_metadata_summary(args.summary_out, result.metadata_summary)
        _print_collection(result, format_name=args.format)
        return 0
    except OSError:
        print(
            "[trino-metadata-cli-summary] rejected: local file could not be read or written",
            file=sys.stderr,
        )
        return 2
    except (EngineFactContractError, TrinoMetadataCliError) as exc:
        print(f"[trino-metadata-cli-summary] rejected: {exc}", file=sys.stderr)
        return 1


def _print_plan(source_contract, plan, *, format_name: str) -> None:
    if format_name == "summary-json":
        print(
            json.dumps(
                trino_metadata_cli_plan_summary_payload(
                    source_contract,
                    plan,
                    mode="dry_run",
                ),
                sort_keys=True,
            )
        )
    else:
        print(format_trino_metadata_cli_plan_summary(source_contract, plan, mode="dry_run"))


def _print_collection(result, *, format_name: str) -> None:
    if format_name == "summary-json":
        print(json.dumps(metadata_cli_collection_payload(result), sort_keys=True))
    elif format_name == "metadata-summary-json":
        print(json.dumps(result.metadata_summary, sort_keys=True))
    else:
        print(format_trino_metadata_cli_collection_summary(result))


def _write_metadata_summary(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validate_summary_out(summary_out: Path, source_contract: Path) -> None:
    if summary_out.resolve(strict=False) == source_contract.resolve(strict=False):
        raise TrinoMetadataCliError(
            "Trino metadata summary output must differ from the source contract"
        )


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
