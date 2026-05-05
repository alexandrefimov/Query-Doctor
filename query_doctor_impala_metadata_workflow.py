"""Explicit pipeline workflow for referenced-table Impala metadata collection."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from impala_shell_runner import (
    ImpalaShellConfigError,
    validate_auth,
    validate_coordinator,
    validate_protocol,
)
from query_doctor_collect_impala_context import (
    CollectorError,
    normalize_database_identifier,
    normalize_table_identifier,
)


DEFAULT_METADATA_MAX_TABLES = 5
DEFAULT_METADATA_TIMEOUT_SEC = 30
DEFAULT_METADATA_MAX_OUTPUT_BYTES = 262_144
DEFAULT_METADATA_AUTH = "kerberos"
DEFAULT_METADATA_PROTOCOL = "beeswax"
METADATA_MODES = ("auto", "on", "off", "dry-run")


@dataclass(frozen=True)
class MetadataPlan:
    selected_tables: list[str]
    skipped_tables: list[str]
    invalid_tables: list[str]
    max_tables: int
    default_database: str | None = None


@dataclass(frozen=True)
class MetadataConfigStatus:
    configured: bool
    reason: str | None = None
    fatal: bool = False


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def add_metadata_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--metadata-mode",
        choices=METADATA_MODES,
        default="auto",
        help=(
            "Impala metadata collection mode: auto collects only when configured, "
            "on requires collection, off disables it, dry-run prints the plan and exits. "
            "Default: %(default)s."
        ),
    )
    parser.add_argument(
        "--collect-impala-metadata",
        action="store_true",
        help="Legacy alias for --metadata-mode on.",
    )
    parser.add_argument(
        "--metadata-coordinator",
        default=os.environ.get("QD_METADATA_COORDINATOR"),
        help="Impala coordinator HOST:PORT for metadata collection.",
    )
    parser.add_argument(
        "--metadata-impala-shell",
        default=os.environ.get("QD_METADATA_IMPALA_SHELL", "impala-shell"),
        help="impala-shell executable for metadata collection. Default: %(default)s.",
    )
    parser.add_argument(
        "--metadata-auth",
        default=os.environ.get("QD_METADATA_AUTH", DEFAULT_METADATA_AUTH),
        help="Metadata collector auth mode. Only kerberos is supported.",
    )
    parser.add_argument(
        "--metadata-protocol",
        choices=["beeswax", "hs2", "hs2-http"],
        default=os.environ.get("QD_METADATA_PROTOCOL", DEFAULT_METADATA_PROTOCOL),
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
        default=None,
        help=f"Maximum captured metadata output bytes. Default: {DEFAULT_METADATA_MAX_OUTPUT_BYTES}.",
    )
    parser.add_argument(
        "--metadata-max-tables",
        type=int,
        default=None,
        help=f"Maximum referenced tables to collect. Default: {DEFAULT_METADATA_MAX_TABLES}.",
    )
    parser.add_argument(
        "--metadata-default-db",
        default=os.environ.get("QD_METADATA_DEFAULT_DB"),
        help=(
            "Default database used to qualify unqualified referenced table names "
            "before metadata collection. When omitted, analyzer facts may provide it."
        ),
    )
    parser.add_argument(
        "--metadata-redact",
        action="store_true",
        default=_env_bool("QD_METADATA_REDACT", True),
        help="Redact metadata output before writing. Enabled by default.",
    )
    parser.add_argument(
        "--metadata-dry-run",
        action="store_true",
        help="Show the bounded metadata collection plan without running impala-shell.",
    )


def validate_metadata_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    effective_mode = resolve_metadata_mode(args)
    _resolve_metadata_int_option(
        parser,
        args,
        attr="metadata_max_output_bytes",
        env_name="QD_METADATA_MAX_OUTPUT_BYTES",
        default=DEFAULT_METADATA_MAX_OUTPUT_BYTES,
        use_env=effective_mode != "off",
    )
    _resolve_metadata_int_option(
        parser,
        args,
        attr="metadata_max_tables",
        env_name="QD_METADATA_MAX_TABLES",
        default=DEFAULT_METADATA_MAX_TABLES,
        use_env=effective_mode != "off",
    )
    if args.metadata_timeout_sec <= 0:
        parser.error("--metadata-timeout-sec must be positive")
    if args.metadata_max_output_bytes <= 0:
        parser.error("--metadata-max-output-bytes must be positive")
    if args.metadata_max_tables <= 0:
        parser.error("--metadata-max-tables must be positive")
    if args.metadata_ca_cert and not args.metadata_ssl:
        parser.error("--metadata-ca-cert requires --metadata-ssl")
    if effective_mode != "off" and args.metadata_default_db:
        try:
            args.metadata_default_db = normalize_database_identifier(args.metadata_default_db)
        except CollectorError as exc:
            parser.error(str(exc))
    if effective_mode == "on" and not args.metadata_coordinator:
        parser.error("--metadata-coordinator is required with --metadata-mode on")
    if effective_mode in {"on", "dry-run"} and args.metadata_coordinator:
        try:
            validate_auth(args.metadata_auth)
            validate_protocol(args.metadata_protocol)
            args.metadata_coordinator = validate_coordinator(args.metadata_coordinator)
        except ImpalaShellConfigError as exc:
            parser.error(str(exc))
    elif effective_mode == "on":
        try:
            validate_auth(args.metadata_auth)
            validate_protocol(args.metadata_protocol)
        except ImpalaShellConfigError as exc:
            parser.error(str(exc))


def _resolve_metadata_int_option(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    *,
    attr: str,
    env_name: str,
    default: int,
    use_env: bool,
) -> None:
    explicit_value = getattr(args, attr)
    if explicit_value is not None:
        return
    if not use_env:
        setattr(args, attr, default)
        return
    raw_env_value = os.environ.get(env_name)
    if raw_env_value is None or not raw_env_value.strip():
        setattr(args, attr, default)
        return
    try:
        value = int(raw_env_value)
    except ValueError:
        parser.error(f"{env_name} must be a positive integer; got {raw_env_value!r}")
    if value <= 0:
        parser.error(f"{env_name} must be a positive integer; got {raw_env_value!r}")
    setattr(args, attr, value)


def resolve_metadata_mode(args: argparse.Namespace) -> str:
    if args.metadata_dry_run:
        return "dry-run"
    if args.collect_impala_metadata:
        return "on"
    return args.metadata_mode


def metadata_config_status(args: argparse.Namespace, *, base_dir: Path | None = None) -> MetadataConfigStatus:
    if not args.metadata_coordinator:
        return MetadataConfigStatus(False, "metadata coordinator is not configured")
    try:
        validate_auth(args.metadata_auth)
        validate_protocol(args.metadata_protocol)
    except ImpalaShellConfigError as exc:
        return MetadataConfigStatus(False, str(exc), fatal=True)
    try:
        args.metadata_coordinator = validate_coordinator(args.metadata_coordinator)
    except ImpalaShellConfigError as exc:
        return MetadataConfigStatus(False, str(exc), fatal=True)
    resolved_impala_shell = _resolve_impala_shell_path(args.metadata_impala_shell, base_dir=base_dir)
    if resolved_impala_shell is None:
        return MetadataConfigStatus(
            False,
            f"impala-shell executable is not available: {args.metadata_impala_shell}",
        )
    args.metadata_impala_shell = resolved_impala_shell
    return MetadataConfigStatus(True)


def _resolve_impala_shell_path(impala_shell: str, *, base_dir: Path | None = None) -> str | None:
    value = impala_shell.strip()
    if not value:
        return None
    if "/" in value or "\\" in value:
        path = Path(value).expanduser()
        if path.exists() and path.is_file():
            return str(path.resolve())
        if not path.is_absolute():
            root = base_dir or Path(__file__).resolve().parent
            repo_relative_path = (root / path).resolve()
            if repo_relative_path.exists() and repo_relative_path.is_file():
                return str(repo_relative_path)
        return None
    if shutil.which(value) is None:
        return None
    return value


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


def read_default_database_from_facts(facts_path: Path) -> str | None:
    if not facts_path.exists():
        return None
    in_section = False
    for line in facts_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped == "## SQL Context":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section or not stripped.startswith("- default_database:"):
            continue
        value = stripped.split(":", 1)[1].strip()
        if value.startswith("not_observed"):
            return None
        if value.startswith("`") and value.endswith("`"):
            value = value[1:-1]
        return value or None
    return None


def build_metadata_plan(
    raw_tables: list[str],
    max_tables: int,
    *,
    default_database: str | None = None,
) -> MetadataPlan:
    normalized_default_database: str | None = None
    if default_database:
        try:
            normalized_default_database = normalize_database_identifier(default_database)
        except CollectorError:
            normalized_default_database = None

    normalized: list[str] = []
    invalid: list[str] = []
    for table in raw_tables:
        try:
            normalized_table = normalize_table_identifier(table)
        except CollectorError:
            if not normalized_default_database:
                invalid.append(table)
                continue
            try:
                normalized_table = normalize_table_identifier(f"{normalized_default_database}.{table}")
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
        default_database=normalized_default_database,
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
        ]
    )
    if args.metadata_redact:
        cmd.append("--redact")
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
    if plan.default_database:
        print(f"[pipeline] default database for unqualified tables: {plan.default_database}")
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
