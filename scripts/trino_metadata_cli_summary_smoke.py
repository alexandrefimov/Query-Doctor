#!/usr/bin/env python3
"""Run a dev-only Trino metadata CLI summary round-trip smoke gate."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from query_doctor.analyzer.engine_facts import EngineFactContractError  # noqa: E402
from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    distinct_paths_error,
    output_overlaps_inputs_error,
    write_ascii_json_artifact,
)
from query_doctor.trino.local_metadata_summary import (  # noqa: E402
    import_trino_local_metadata_summary,
)
from query_doctor.trino.metadata_cli_summary import (  # noqa: E402
    TrinoMetadataCliError,
    build_trino_metadata_cli_plan,
    collect_trino_metadata_summary,
    validate_connector_family,
    validate_trino_cli_server,
    validate_trino_cli_user,
)
from query_doctor.trino.metadata_source_contract import (  # noqa: E402
    load_trino_metadata_source_contract,
)


TRINO_METADATA_CLI_SUMMARY_SMOKE_VERSION = "trino_metadata_cli_summary_smoke_v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a dev-only Trino metadata CLI summary smoke gate. The gate validates "
            "one metadata allowlist contract, builds the safe dry-run statement plan, "
            "optionally executes only Python-owned metadata statements through an "
            "operator-installed Trino CLI, and round-trips the sanitized aggregate "
            "metadata summary through the local metadata-summary importer. It never "
            "prints statement text, object identifiers, endpoint URLs, local paths, "
            "raw metadata values, or CLI stdout/stderr."
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
        help="Validate and write/print the safe plan summary without executing Trino CLI.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Optional output path for the raw-free smoke summary JSON. The path is never printed.",
    )
    parser.add_argument(
        "--metadata-summary-out",
        type=Path,
        help=(
            "Optional output path for the sanitized trino_metadata_summary_v1 JSON payload. "
            "The path is never printed."
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
            "[trino-metadata-cli-summary-smoke] rejected: redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1

    overlap_error = _output_overlap_error(args)
    if overlap_error is not None:
        print(f"[trino-metadata-cli-summary-smoke] rejected: {overlap_error}", file=sys.stderr)
        return 2
    if args.dry_run and args.metadata_summary_out is not None:
        print(
            "[trino-metadata-cli-summary-smoke] rejected: metadata summary output requires execution",
            file=sys.stderr,
        )
        return 2

    try:
        validate_trino_cli_server(args.server)
        validate_connector_family(args.connector_family)
        if args.user is not None:
            validate_trino_cli_user(args.user)
        source_contract = load_trino_metadata_source_contract(
            args.source_contract,
            **_limit_overrides(args),
        )
        plan = build_trino_metadata_cli_plan(
            source_contract,
            connector_family=args.connector_family,
        )
        if args.dry_run:
            payload = _dry_run_summary_payload(
                source_contract,
                plan,
                summary_json_written=args.summary_json is not None,
            )
        else:
            result = collect_trino_metadata_summary(
                source_contract,
                trino_cli=args.trino_cli,
                server=args.server,
                connector_family=args.connector_family,
                user=args.user,
                runner=runner,
            )
            import_result = import_trino_local_metadata_summary(
                source_contract,
                result.metadata_summary,
            )
            if args.metadata_summary_out is not None:
                write_ascii_json_artifact(args.metadata_summary_out, result.metadata_summary)
            payload = _execute_summary_payload(
                source_contract,
                result.summary,
                result.metadata_summary,
                import_result=import_result,
                summary_json_written=args.summary_json is not None,
                metadata_summary_written=args.metadata_summary_out is not None,
            )
        if args.summary_json is not None:
            write_ascii_json_artifact(args.summary_json, payload)
    except OSError:
        print(
            "[trino-metadata-cli-summary-smoke] rejected: local file could not be read or written",
            file=sys.stderr,
        )
        return 2
    except (EngineFactContractError, TrinoMetadataCliError) as exc:
        print(f"[trino-metadata-cli-summary-smoke] rejected: {exc}", file=sys.stderr)
        return 1

    _print_summary(payload)
    return 0 if payload["status"] in {"ok", "planned"} else 1


def _dry_run_summary_payload(
    source_contract,
    plan,
    *,
    summary_json_written: bool,
) -> dict[str, Any]:
    return {
        "schema_version": TRINO_METADATA_CLI_SUMMARY_SMOKE_VERSION,
        "mode": "dry_run",
        "status": "planned",
        "source_contract": _source_contract_summary(source_contract),
        "connector_family": plan.connector_family,
        "checks": (
            {"name": "dry_run_plan", "status": "ok"},
            {"name": "metadata_summary_collection", "status": "skipped"},
            {"name": "metadata_summary_import", "status": "skipped"},
        ),
        "object_allowlist": {
            "relation_count": plan.relation_count,
            "explicit_column_count": plan.explicit_column_count,
            "relation_kind_counts": source_contract.relation_kind_counts,
        },
        "planned_metadata_reads": {
            "statement_count": plan.statement_count,
            "describe_relation_count": sum(
                1 for statement in plan.statements if statement.kind == "describe_relation"
            ),
            "show_stats_count": sum(
                1 for statement in plan.statements if statement.kind == "show_stats"
            ),
            "statement_text": "not_output",
            "object_identifiers": "not_output",
        },
        "artifacts": {
            "metadata_summary_written": False,
            "smoke_summary_written": summary_json_written,
        },
        "redaction": _redaction_summary(),
        "limitations": _limitations(),
    }


def _execute_summary_payload(
    source_contract,
    collection_summary: dict[str, Any],
    metadata_summary: dict[str, Any],
    *,
    import_result,
    summary_json_written: bool,
    metadata_summary_written: bool,
) -> dict[str, Any]:
    coverage = metadata_summary["metadataCoverage"]
    return {
        "schema_version": TRINO_METADATA_CLI_SUMMARY_SMOKE_VERSION,
        "mode": "execute",
        "status": "ok",
        "source_contract": _source_contract_summary(source_contract),
        "connector_family": collection_summary["connector_family"],
        "checks": (
            {"name": "dry_run_plan", "status": "ok"},
            {"name": "metadata_summary_collection", "status": "ok"},
            {"name": "metadata_summary_import", "status": "ok"},
        ),
        "object_allowlist": collection_summary["object_allowlist"],
        "planned_metadata_reads": collection_summary["planned_metadata_reads"],
        "metadata_summary": metadata_summary,
        "metadata_import": {
            "metadata_summary_checked": import_result.metadata_summary_checked,
            "mapped_to_facts": import_result.mapped_to_facts,
            "parser_coverage": import_result.parser_coverage,
            "relation_count": import_result.relation_count,
            "explicit_column_count": import_result.explicit_column_count,
            "relations_checked": import_result.relations_checked,
            "columns_checked": import_result.columns_checked,
            "column_stats_present": import_result.column_stats_present,
            "column_stats_missing": import_result.column_stats_missing,
            "stats_completeness": import_result.stats_completeness,
        },
        "coverage": {
            "relations_checked": coverage["relationsChecked"],
            "columns_checked": coverage["columnsChecked"],
            "column_stats_present": coverage["columnStatsPresent"],
            "column_stats_missing": coverage["columnStatsMissing"],
            "stats_completeness": coverage["statsCompleteness"],
        },
        "artifacts": {
            "metadata_summary_written": metadata_summary_written,
            "smoke_summary_written": summary_json_written,
        },
        "redaction": _redaction_summary(),
        "limitations": _limitations(),
    }


def _source_contract_summary(source_contract) -> dict[str, Any]:
    return {
        "source_type": source_contract.source_type,
        "metadata_contract_version": source_contract.metadata_contract_version,
        "auth_reference": {
            "kind": source_contract.auth_reference_kind,
            "label": source_contract.auth_reference_label,
        },
    }


def _redaction_summary() -> dict[str, str]:
    return {
        "statement_text": "not_output",
        "object_identifiers": "not_output",
        "endpoint_urls": "not_output",
        "local_paths": "not_output",
        "raw_metadata_values": "not_output",
        "cli_stdout_stderr": "not_output",
    }


def _limitations() -> tuple[str, ...]:
    return (
        "dev_only_smoke_gate",
        "local_operator_cli_only",
        "python_owned_metadata_statement_allowlist_only",
        "aggregate_metadata_summary_only",
        "not_query_specific",
        "not_a_trino_product_surface",
    )


def _print_summary(payload: dict[str, Any]) -> None:
    print("[trino-metadata-cli-summary-smoke] accepted")
    print(f"mode: {payload['mode']}")
    print(f"status: {payload['status']}")
    print(f"connector_family: {payload['connector_family']}")
    print("checks:")
    for check in payload["checks"]:
        print(f"  {check['name']}: {check['status']}")
    print("planned_metadata_reads:")
    print(f"  statement_count: {payload['planned_metadata_reads']['statement_count']}")
    print("  statement_text: not_output")
    print("  object_identifiers: not_output")
    if payload["mode"] == "execute":
        coverage = payload["coverage"]
        print("metadata_summary:")
        print(f"  relations_checked: {coverage['relations_checked']}")
        print(f"  columns_checked: {coverage['columns_checked']}")
        print(f"  column_stats_present: {coverage['column_stats_present']}")
        print(f"  column_stats_missing: {coverage['column_stats_missing']}")
        print(f"  stats_completeness: {coverage['stats_completeness']}")
    print("redaction:")
    print("  endpoint_urls: not_output")
    print("  local_paths: not_output")
    print("  raw_metadata_values: not_output")
    print("  cli_stdout_stderr: not_output")


def _output_overlap_error(args: argparse.Namespace) -> str | None:
    protected_inputs = (args.source_contract,)
    output_checks = (
        (args.summary_json, "smoke summary output must differ from every input artifact"),
        (
            args.metadata_summary_out,
            "metadata summary output must differ from every input artifact",
        ),
    )
    for output, message in output_checks:
        overlap_error = output_overlaps_inputs_error(output, protected_inputs, message=message)
        if overlap_error is not None:
            return overlap_error
    return distinct_paths_error(
        (args.summary_json, args.metadata_summary_out),
        message="smoke summary output must differ from metadata summary output",
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
