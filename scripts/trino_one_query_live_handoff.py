#!/usr/bin/env python3
"""Run one bounded Trino coordinator QueryInfo handoff and readiness gate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from query_doctor.analyzer.engine_facts import EngineFactContractError  # noqa: E402
from query_doctor.cli.trino_diagnosis_output import (  # noqa: E402
    same_path,
    write_trino_boundary_out,
    write_trino_compact_diagnosis_out,
)
from query_doctor.trino.coordinator_query_info_pruned_import import (  # noqa: E402
    format_trino_coordinator_query_info_pruned_import_summary,
    load_trino_coordinator_query_info_pruned_import,
    trino_coordinator_query_info_pruned_import_boundary_export,
)
from query_doctor.trino.coordinator_query_info_target import (  # noqa: E402
    TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION,
    load_trino_coordinator_query_info_auth_header_file,
)
from scripts.audit_trino_compact_readiness import (  # noqa: E402
    TrinoCompactReadinessInputError,
    audit_boundary_payload,
    load_json_object,
    print_result,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a dev-only one-query Trino handoff: read exactly one bounded "
            "GET /v1/query/{queryId}?pruned=true response through the existing "
            "private-preview import path, write raw-free boundary and compact "
            "diagnosis JSON, then run the strict compact readiness gate. The "
            "command never submits SQL and never prints the coordinator URL, Query ID, "
            "auth header, raw QueryInfo, artifact paths, or filenames."
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
        help="Explicit Trino coordinator base URL. Used for the read but never echoed.",
    )
    parser.add_argument(
        "--query-id",
        required=True,
        help="Explicit known Trino query ID. Used for the read but never echoed.",
    )
    parser.add_argument(
        "--redaction-reviewed",
        action="store_true",
        help="Confirm the source contract and selected QueryInfo path were operator-reviewed.",
    )
    parser.add_argument(
        "--auth-header-file",
        type=Path,
        default=None,
        help=(
            "Optional local file containing one operator-managed Authorization header line. "
            "The path and value are never printed."
        ),
    )
    parser.add_argument(
        "--boundary-out",
        required=True,
        type=Path,
        help="Output path for raw-free engine_fact_boundary_v1 JSON. The path is never printed.",
    )
    parser.add_argument(
        "--diagnosis-out",
        required=True,
        type=Path,
        help="Output path for raw-free Trino compact diagnosis JSON. The path is never printed.",
    )
    parser.add_argument(
        "--smoke-summary",
        type=Path,
        default=None,
        help=("Optional dev-only trino_smoke_summary.json artifact. The path is never printed."),
    )
    parser.add_argument(
        "--require-executed-smoke",
        action="store_true",
        help="Fail unless --smoke-summary records an executed all-ok smoke.",
    )
    parser.add_argument(
        "--require-supported-attention",
        action="store_true",
        help="Fail unless the compact diagnosis contains at least one supported attention area.",
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
    parser.add_argument("--limit", type=int, default=12, help="Rows to print per section.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.redaction_reviewed:
        print(
            "[trino-one-query-handoff] rejected: redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1
    if args.require_executed_smoke and args.smoke_summary is None:
        print(
            "[trino-one-query-handoff] rejected: --require-executed-smoke requires --smoke-summary",
            file=sys.stderr,
        )
        return 2
    overlap_error = _output_overlap_error(args)
    if overlap_error:
        print(f"[trino-one-query-handoff] rejected: {overlap_error}", file=sys.stderr)
        return 2

    try:
        auth_headers = _auth_headers(args)
        result = load_trino_coordinator_query_info_pruned_import(
            args.source_contract,
            coordinator_url=args.coordinator_url,
            query_id=args.query_id,
            auth_headers=auth_headers,
            **_limit_overrides(args),
        )
        boundary_export = trino_coordinator_query_info_pruned_import_boundary_export(result)
        boundary_payload = boundary_export["query_info_boundary"]
        write_trino_boundary_out(args.boundary_out, boundary_payload)
        write_trino_compact_diagnosis_out(args.diagnosis_out, boundary_payload)
        diagnosis_payload = load_json_object(
            args.diagnosis_out, input_label="diagnosis JSON output"
        )
        smoke_summary_payload = (
            None
            if args.smoke_summary is None
            else load_json_object(args.smoke_summary, input_label="smoke summary JSON input")
        )
        readiness = audit_boundary_payload(
            boundary_payload,
            diagnosis_payload=diagnosis_payload,
            smoke_summary_payload=smoke_summary_payload,
            required_source_versions=(TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION,),
            require_executed_smoke=args.require_executed_smoke,
            require_supported_attention=args.require_supported_attention,
            fail_on_unknown_parser_coverage=True,
            require_one_query_boundary=True,
        )
    except OSError:
        print(
            "[trino-one-query-handoff] rejected: local artifact could not be read or written",
            file=sys.stderr,
        )
        return 2
    except TrinoCompactReadinessInputError as exc:
        print(f"[trino-one-query-handoff] rejected: {exc}", file=sys.stderr)
        return 2
    except EngineFactContractError as exc:
        print(f"[trino-one-query-handoff] rejected: {exc}", file=sys.stderr)
        return 1

    print("[trino-one-query-handoff] import")
    print(format_trino_coordinator_query_info_pruned_import_summary(result))
    print("[trino-one-query-handoff] readiness")
    print_result(readiness, limit=args.limit)
    return 0 if readiness.ok else 1


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


def _output_overlap_error(args: argparse.Namespace) -> str | None:
    protected_inputs = (args.source_contract, args.auth_header_file, args.smoke_summary)
    for protected_input in protected_inputs:
        if protected_input is None:
            continue
        if same_path(args.boundary_out, protected_input):
            return "boundary output must differ from every input artifact"
        if same_path(args.diagnosis_out, protected_input):
            return "compact diagnosis output must differ from every input artifact"
    if same_path(args.boundary_out, args.diagnosis_out):
        return "boundary output must differ from compact diagnosis output"
    return None


if __name__ == "__main__":
    raise SystemExit(main())
