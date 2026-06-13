#!/usr/bin/env python3
"""Explicit read-only Impala metadata collector for Query Doctor."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from query_doctor.impala.shell_runner import (
    ImpalaShellConfigError,
    build_impala_shell_argv,
    run_impala_shell,
    validate_auth,
    validate_coordinator,
    validate_kerberos_host_fqdn,
    validate_kerberos_service_name,
    validate_protocol,
)
from query_doctor.impala.shell_output import normalize_output_bytes
from query_doctor.impala.metadata_policy import (
    ALLOWED_STATEMENTS,
    CollectorError,
    StatementPlan,
    build_statement_plan,
    dedupe_preserve_order,
    normalize_database_identifier,
    normalize_table_identifier,
    validate_read_only_statement,
)
from query_doctor.impala.metadata_results import (
    StatementResult,
    not_applicable_result,
    planned_result,
    write_outputs,
)
from query_doctor.impala.metadata_redaction import redact_impala_context_text
from query_doctor.cli.collect_cm_profiles import (
    ConfigError,
    load_effective_local_config,
)
from query_doctor.config.contract import (
    DEFAULT_CONFIG_PATH,
    LEGACY_CONFIG_PATH,
    QDCREDS_CONFIG_PATH,
    merge_kerberos_cache_env,
)


DEFAULT_TIMEOUT_SEC = 30
DEFAULT_MAX_OUTPUT_BYTES = 262_144
CREATE_VIEW_RE = re.compile(
    r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\b", re.IGNORECASE | re.MULTILINE
)
VIEW_NOT_APPLICABLE_RE = re.compile(r"not\s+applicable\s+to\s+a\s+view", re.IGNORECASE)
REPO_DIR = Path(__file__).resolve().parents[2]


Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def redact_metadata_value(args: argparse.Namespace, value: object) -> str:
    if not args.redact:
        return str(value)
    return redact_impala_context_text(
        value,
        redact_identifiers=getattr(args, "redact_identifiers", True),
        redact_hosts=getattr(args, "redact_hosts", True),
    )


def build_impala_shell_args(args: argparse.Namespace, sql: str) -> list[str]:
    return build_impala_shell_argv(
        impala_shell=args.impala_shell,
        coordinator=args.coordinator,
        auth=args.auth,
        sql=sql,
        protocol=args.protocol,
        ssl=args.ssl,
        ca_cert=args.ca_cert,
        kerberos_service_name=args.kerberos_service_name,
        kerberos_host_fqdn=args.kerberos_host_fqdn,
    )


def run_statement(
    args: argparse.Namespace,
    plan: StatementPlan,
    *,
    runner: Runner = subprocess.run,
) -> StatementResult:
    validate_read_only_statement(plan.sql, plan.table)
    try:
        proc = run_impala_shell(
            build_impala_shell_args(args, plan.sql),
            timeout_sec=args.timeout_sec,
            runner=runner,
            env=effective_impala_env(args),
        )
    except subprocess.TimeoutExpired:
        return StatementResult(
            table=plan.table,
            label=plan.label,
            sql=plan.sql,
            status="timeout",
            error=f"statement timed out after {args.timeout_sec}s",
        )
    except OSError as exc:
        return StatementResult(
            table=plan.table,
            label=plan.label,
            sql=plan.sql,
            status="error",
            error=redact_metadata_value(args, exc),
        )

    stdout_bytes = proc.stdout or b""
    stderr_bytes = proc.stderr or b""
    stdout_output = normalize_output_bytes(stdout_bytes)
    stderr_output = normalize_output_bytes(stderr_bytes)

    size_metadata = {
        "stdout_raw_bytes": stdout_output.raw_bytes,
        "stdout_bytes": stdout_output.bytes,
        "stdout_normalized": stdout_output.normalized,
        "stderr_raw_bytes": stderr_output.raw_bytes,
        "stderr_bytes": stderr_output.bytes,
        "stderr_normalized": stderr_output.normalized,
    }

    if stdout_output.bytes + stderr_output.bytes > args.max_output_bytes:
        return StatementResult(
            table=plan.table,
            label=plan.label,
            sql=plan.sql,
            status="too_large",
            returncode=proc.returncode,
            error=f"captured output exceeded max-output-bytes ({args.max_output_bytes})",
            **size_metadata,
        )

    stdout = redact_metadata_value(args, stdout_output.text)
    stderr = redact_metadata_value(args, stderr_output.text)
    if proc.returncode != 0:
        if is_view_not_applicable_error(stdout, stderr):
            return StatementResult(
                table=plan.table,
                label=plan.label,
                sql=plan.sql,
                status="not_applicable",
                returncode=proc.returncode,
                error="object is a view",
                **size_metadata,
            )
        return StatementResult(
            table=plan.table,
            label=plan.label,
            sql=plan.sql,
            status="error",
            stdout=stdout,
            stderr=stderr,
            returncode=proc.returncode,
            error=f"impala-shell exited with code {proc.returncode}",
            **size_metadata,
        )

    return StatementResult(
        table=plan.table,
        label=plan.label,
        sql=plan.sql,
        status="ok",
        stdout=stdout,
        stderr=stderr,
        returncode=proc.returncode,
        **size_metadata,
    )


def is_create_view_output(text: str) -> bool:
    return bool(CREATE_VIEW_RE.search(text))


def is_view_not_applicable_error(stdout: str, stderr: str) -> bool:
    return bool(VIEW_NOT_APPLICABLE_RE.search(stdout) or VIEW_NOT_APPLICABLE_RE.search(stderr))


def collect_impala_context(
    args: argparse.Namespace,
    *,
    runner: Runner = subprocess.run,
) -> int:
    tables = dedupe_preserve_order(normalize_table_identifier(table) for table in args.table)
    plans = build_statement_plan(tables)

    if args.dry_run:
        print("Planned read-only Impala statements:")
        print(f"- impala-shell: {args.impala_shell}")
        coordinator = (
            redact_metadata_value(args, args.coordinator)
            if args.coordinator
            else "<required for execution>"
        )
        print(f"- coordinator: {coordinator}")
        print(f"- auth: {args.auth}")
        if args.protocol:
            print(f"- protocol: {args.protocol}")
        if args.kerberos_service_name:
            print(f"- kerberos service name: {args.kerberos_service_name}")
        if args.ssl:
            print("- ssl: yes")
        if args.ca_cert:
            print(f"- ca-cert: {redact_metadata_value(args, args.ca_cert)}")
        for plan in plans:
            print(f"- {redact_metadata_value(args, plan.sql)}")
        results = [planned_result(plan) for plan in plans]
    else:
        print(f"Collecting read-only Impala metadata for {len(tables)} table(s).")
        results = []
        for table in tables:
            table_plans = [plan for plan in plans if plan.table == table]
            create_plan = table_plans[0]
            print(f"- {create_plan.label} {create_plan.table}")
            create_result = run_statement(args, create_plan, runner=runner)
            print(f"  status: {create_result.status}")
            results.append(create_result)
            if create_result.status == "ok" and is_create_view_output(create_result.stdout):
                for plan in table_plans[1:]:
                    result = not_applicable_result(plan, "object is a view")
                    print(f"- {plan.label} {plan.table}")
                    print(f"  status: {result.status}")
                    results.append(result)
                continue
            for plan in table_plans[1:]:
                print(f"- {plan.label} {plan.table}")
                result = run_statement(args, plan, runner=runner)
                print(f"  status: {result.status}")
                results.append(result)

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out_dir = Path(args.out)
    write_outputs(out_dir, timestamp=timestamp, tables=tables, results=results, args=args)
    print(f"Wrote Impala context to {out_dir / 'impala_context.md'}")

    failure_statuses = {"error", "timeout", "too_large"}
    return 1 if any(result.status in failure_statuses for result in results) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect explicit read-only Impala table metadata for Query Doctor. "
            "Only SHOW CREATE TABLE, SHOW TABLE STATS, and SHOW COLUMN STATS are planned."
        )
    )
    parser.add_argument(
        "--config",
        help=(
            "Optional local config with non-secret metadata settings. If omitted, "
            f"{DEFAULT_CONFIG_PATH} is loaded when present, then {QDCREDS_CONFIG_PATH}, "
            f"then legacy {LEGACY_CONFIG_PATH}."
        ),
    )
    parser.add_argument(
        "--table",
        action="append",
        required=True,
        help="Fully qualified table name to inspect, e.g. db.table. May be repeated.",
    )
    parser.add_argument("--out", required=True, help="Output directory for impala_context.md/json.")
    parser.add_argument("--impala-shell", help="impala-shell executable.")
    parser.add_argument(
        "--coordinator",
        help="Impala coordinator HOST:PORT for real execution. Not required for --dry-run.",
    )
    parser.add_argument(
        "--auth",
        help="Authentication mode for impala-shell. Only kerberos is supported.",
    )
    parser.add_argument(
        "--protocol",
        choices=["beeswax", "hs2", "hs2-http"],
        help="Optional impala-shell protocol.",
    )
    parser.add_argument(
        "--kerberos-service-name",
        help="Kerberos service principal short name passed to impala-shell, e.g. hive or impala.",
    )
    parser.add_argument(
        "--kerberos-host-fqdn",
        help=(
            "Expected Kerberos host FQDN passed to impala-shell. Use this when the "
            "network coordinator is a load balancer address but the service principal "
            "uses a DNS hostname."
        ),
    )
    parser.add_argument(
        "--ssl", action="store_true", default=None, help="Pass --ssl to impala-shell."
    )
    parser.add_argument("--ca-cert", help="CA certificate path for --ssl connections.")
    parser.add_argument(
        "--timeout-sec",
        type=int,
        help=f"Timeout per statement in seconds (default: {DEFAULT_TIMEOUT_SEC}).",
    )
    parser.add_argument(
        "--max-output-bytes",
        type=int,
        help=f"Maximum captured stdout+stderr bytes per statement (default: {DEFAULT_MAX_OUTPUT_BYTES}).",
    )
    parser.add_argument(
        "--redact",
        action="store_true",
        default=None,
        help="Redact metadata output before writing. Enabled by default.",
    )
    parser.add_argument(
        "--no-redact",
        dest="redact",
        action="store_false",
        help="Write metadata output without redaction.",
    )
    parser.add_argument(
        "--redact-identifiers",
        action="store_true",
        default=None,
        help="Redact database and table identifiers in metadata output.",
    )
    parser.add_argument(
        "--no-redact-identifiers",
        dest="redact_identifiers",
        action="store_false",
        help="Preserve database and table identifiers in local metadata output.",
    )
    parser.add_argument(
        "--redact-hosts",
        action="store_true",
        default=None,
        help="Redact hostnames in metadata output.",
    )
    parser.add_argument(
        "--no-redact-hosts",
        dest="redact_hosts",
        action="store_false",
        help="Preserve hostnames in local metadata output.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without connecting.")
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        apply_local_config(args, cwd=Path.cwd())
    except ConfigError as exc:
        parser.error(str(exc))
    if args.timeout_sec <= 0:
        parser.error("--timeout-sec must be positive")
    if args.max_output_bytes <= 0:
        parser.error("--max-output-bytes must be positive")
    try:
        validate_auth(args.auth)
        validate_protocol(args.protocol)
        args.kerberos_service_name = validate_kerberos_service_name(args.kerberos_service_name)
        args.kerberos_host_fqdn = validate_kerberos_host_fqdn(args.kerberos_host_fqdn)
        if args.coordinator:
            args.coordinator = validate_coordinator(args.coordinator)
        elif not args.dry_run:
            parser.error("--coordinator is required unless --dry-run is used")
        if args.ca_cert and not args.ssl:
            parser.error("--ca-cert requires --ssl")
    except ImpalaShellConfigError as exc:
        parser.error(str(exc))
    return args


def apply_local_config(args: argparse.Namespace, *, cwd: Path) -> None:
    config_values = load_effective_local_config(
        args.config,
        cwd=cwd,
        repo_root=REPO_DIR,
        use_repo_default=False,
    )

    args.impala_shell = first_string(
        args.impala_shell, config_values.get("metadata_impala_shell"), "impala-shell"
    )
    args.coordinator = first_string(args.coordinator, config_values.get("metadata_coordinator"))
    args.auth = first_string(args.auth, config_values.get("metadata_auth"), "kerberos")
    args.protocol = first_string(args.protocol, config_values.get("metadata_protocol"))
    args.kerberos_service_name = first_string(
        args.kerberos_service_name,
        config_values.get("metadata_kerberos_service_name"),
        config_values.get("impala_kerberos_service_name"),
    )
    args.kerberos_host_fqdn = first_string(
        args.kerberos_host_fqdn,
        config_values.get("metadata_kerberos_host_fqdn"),
    )
    args.ssl = first_bool(args.ssl, config_values.get("metadata_ssl"), default=False)
    args.ca_cert = first_string(args.ca_cert, config_values.get("metadata_ca_cert"))
    args.timeout_sec = first_int(
        args.timeout_sec, config_values.get("metadata_timeout_sec"), default=DEFAULT_TIMEOUT_SEC
    )
    args.max_output_bytes = first_int(
        args.max_output_bytes,
        config_values.get("metadata_max_output_bytes"),
        default=DEFAULT_MAX_OUTPUT_BYTES,
    )
    privacy_mode = first_bool(config_values.get("privacy_mode"), default=True)
    args.redact = first_bool(
        args.redact, config_values.get("metadata_redact"), default=privacy_mode
    )
    args.redact_identifiers = first_bool(
        args.redact_identifiers,
        config_values.get("redact_identifiers"),
        default=privacy_mode,
    )
    args.redact_hosts = first_bool(
        args.redact_hosts,
        config_values.get("redact_hosts"),
        default=privacy_mode,
    )
    args.krb5ccname = first_string(config_values.get("krb5ccname"))
    max_tables = first_int(config_values.get("metadata_max_tables"), default=None)
    if max_tables is not None and len(args.table or []) > max_tables:
        raise ConfigError(
            f"Config field metadata_max_tables allows at most {max_tables} tables for this metadata run."
        )


def first_string(*values: object) -> str | None:
    for value in values:
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None


def first_int(*values: object, default: int | None) -> int | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            continue
        return int(value)
    return default


def first_bool(*values: object, default: bool) -> bool:
    for value in values:
        if value is None:
            continue
        return bool(value)
    return default


def effective_impala_env(args: argparse.Namespace) -> dict[str, str] | None:
    krb5ccname = getattr(args, "krb5ccname", None)
    if not krb5ccname or os.environ.get("KRB5CCNAME"):
        return None
    return merge_kerberos_cache_env(os.environ, {"krb5ccname": krb5ccname})


def main(argv: list[str] | None = None, *, runner: Runner = subprocess.run) -> int:
    args = parse_args(argv)
    try:
        return collect_impala_context(args, runner=runner)
    except (CollectorError, ImpalaShellConfigError) as exc:
        print(f"error: {redact_impala_context_text(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
