"""Explicit pipeline workflow for referenced-table Impala metadata collection."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from impala_shell_runner import (
    ImpalaShellConfigError,
    validate_auth,
    validate_coordinator,
)
from query_doctor_collect_impala_context import CollectorError, normalize_table_identifier


DEFAULT_METADATA_MAX_TABLES = 5
DEFAULT_METADATA_TIMEOUT_SEC = 30
DEFAULT_METADATA_MAX_OUTPUT_BYTES = 262_144
DEFAULT_METADATA_AUTH = "kerberos"
DEFAULT_METADATA_PROTOCOL = "beeswax"


@dataclass(frozen=True)
class MetadataPlan:
    selected_tables: list[str]
    skipped_tables: list[str]
    invalid_tables: list[str]
    max_tables: int


def add_metadata_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--collect-impala-metadata",
        action="store_true",
        help="Explicitly collect read-only Impala metadata for analyzer-referenced tables.",
    )
    parser.add_argument(
        "--metadata-coordinator",
        help="Impala coordinator HOST:PORT for metadata collection.",
    )
    parser.add_argument(
        "--metadata-impala-shell",
        default="impala-shell",
        help="impala-shell executable for metadata collection.",
    )
    parser.add_argument(
        "--metadata-auth",
        default=DEFAULT_METADATA_AUTH,
        help="Metadata collector auth mode. Only kerberos is supported.",
    )
    parser.add_argument(
        "--metadata-protocol",
        choices=["beeswax", "hs2", "hs2-http"],
        default=DEFAULT_METADATA_PROTOCOL,
        help="impala-shell protocol for metadata collection. Default: %(default)s.",
    )
    parser.add_argument(
        "--metadata-ssl",
        action="store_true",
        help="Pass --ssl to impala-shell for metadata collection.",
    )
    parser.add_argument(
        "--metadata-ca-cert",
        help="CA certificate path for --metadata-ssl connections.",
    )
    parser.add_argument(
        "--metadata-timeout-sec",
        type=int,
        default=DEFAULT_METADATA_TIMEOUT_SEC,
        help=f"Timeout per metadata statement. Default: {DEFAULT_METADATA_TIMEOUT_SEC}.",
    )
    parser.add_argument(
        "--metadata-max-output-bytes",
        type=int,
        default=DEFAULT_METADATA_MAX_OUTPUT_BYTES,
        help=f"Maximum captured metadata output bytes. Default: {DEFAULT_METADATA_MAX_OUTPUT_BYTES}.",
    )
    parser.add_argument(
        "--metadata-max-tables",
        type=int,
        default=DEFAULT_METADATA_MAX_TABLES,
        help=f"Maximum referenced tables to collect. Default: {DEFAULT_METADATA_MAX_TABLES}.",
    )
    parser.add_argument(
        "--metadata-redact",
        action="store_true",
        default=True,
        help="Redact metadata output before writing. Enabled by default.",
    )
    parser.add_argument(
        "--metadata-dry-run",
        action="store_true",
        help="Show the bounded metadata collection plan without running impala-shell.",
    )


def validate_metadata_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.metadata_timeout_sec <= 0:
        parser.error("--metadata-timeout-sec must be positive")
    if args.metadata_max_output_bytes <= 0:
        parser.error("--metadata-max-output-bytes must be positive")
    if args.metadata_max_tables <= 0:
        parser.error("--metadata-max-tables must be positive")
    if args.metadata_ca_cert and not args.metadata_ssl:
        parser.error("--metadata-ca-cert requires --metadata-ssl")
    if args.collect_impala_metadata and not args.metadata_coordinator:
        parser.error("--metadata-coordinator is required with --collect-impala-metadata")
    if args.collect_impala_metadata:
        try:
            validate_auth(args.metadata_auth)
            args.metadata_coordinator = validate_coordinator(args.metadata_coordinator)
        except ImpalaShellConfigError as exc:
            parser.error(str(exc))


def read_referenced_tables_from_facts(facts_path: Path) -> list[str]:
    if not facts_path.exists():
        return []
    tables: list[str] = []
    in_section = False
    for line in facts_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped == "## Referenced Tables":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section or not stripped.startswith("- "):
            continue
        value = stripped[2:].strip()
        if value.startswith("not_observed"):
            continue
        if value.startswith("`") and value.endswith("`"):
            value = value[1:-1]
        if value and value not in tables:
            tables.append(value)
    return tables


def build_metadata_plan(raw_tables: list[str], max_tables: int) -> MetadataPlan:
    normalized: list[str] = []
    invalid: list[str] = []
    for table in raw_tables:
        try:
            normalized_table = normalize_table_identifier(table)
        except CollectorError:
            invalid.append(table)
            continue
        if normalized_table not in normalized:
            normalized.append(normalized_table)
    return MetadataPlan(
        selected_tables=normalized[:max_tables],
        skipped_tables=normalized[max_tables:],
        invalid_tables=invalid,
        max_tables=max_tables,
    )


def build_metadata_collector_cmd(
    args: argparse.Namespace,
    *,
    collector: Path,
    case_dir: Path,
    tables: list[str],
) -> list[str]:
    cmd = [
        sys.executable,
        str(collector),
    ]
    for table in tables:
        cmd.extend(["--table", table])
    cmd.extend(
        [
            "--out",
            str(case_dir),
            "--impala-shell",
            args.metadata_impala_shell,
            "--coordinator",
            args.metadata_coordinator,
            "--auth",
            args.metadata_auth,
            "--protocol",
            args.metadata_protocol,
            "--timeout-sec",
            str(args.metadata_timeout_sec),
            "--max-output-bytes",
            str(args.metadata_max_output_bytes),
            "--redact",
        ]
    )
    if args.metadata_ssl:
        cmd.append("--ssl")
    if args.metadata_ca_cert:
        cmd.extend(["--ca-cert", args.metadata_ca_cert])
    if args.metadata_dry_run:
        cmd.append("--dry-run")
    return cmd


def print_metadata_plan(plan: MetadataPlan, *, dry_run: bool) -> None:
    print()
    print("[pipeline] Impala metadata collection plan:")
    print(f"[pipeline] selected referenced tables: {len(plan.selected_tables)}")
    for table in plan.selected_tables:
        print(f"[pipeline]   collect: {table}")
    if plan.skipped_tables:
        print(f"[pipeline] skipped due to metadata max tables ({plan.max_tables}): {len(plan.skipped_tables)}")
        for table in plan.skipped_tables:
            print(f"[pipeline]   skip: {table}")
    if plan.invalid_tables:
        print(f"[pipeline] skipped malformed referenced tables: {len(plan.invalid_tables)}")
        for table in plan.invalid_tables:
            print(f"[pipeline]   invalid: {table}")
    if dry_run:
        print("[pipeline] metadata dry-run requested; impala-shell will not run")
