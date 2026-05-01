#!/usr/bin/env python3
"""Explicit read-only Impala metadata collector for Query Doctor."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from impala_shell_runner import (
    ImpalaShellConfigError,
    build_impala_shell_argv,
    run_impala_shell,
    validate_auth,
    validate_coordinator,
    validate_protocol,
)
from impala_shell_output import normalize_output_bytes
from query_doctor_collect_cm_profiles import HostAliasRedactor, redact_profile_text


DEFAULT_TIMEOUT_SEC = 30
DEFAULT_MAX_OUTPUT_BYTES = 262_144
ALLOWED_STATEMENTS = (
    "SHOW CREATE TABLE",
    "SHOW TABLE STATS",
    "SHOW COLUMN STATS",
)
IDENTIFIER_PART_RE = re.compile(r"(?:`([A-Za-z_][A-Za-z0-9_$]*)`|([A-Za-z_][A-Za-z0-9_$]*))\Z")
SQL_SECRET_VALUE_RE = re.compile(
    r"((?:'|\")?(?:password|passwd|pwd|token|secret|cookie|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token)(?:'|\")?[ \t]*[=:][ \t]*(?:'|\")?)([^'\"\s,;)]+)((?:'|\")?)",
    re.IGNORECASE,
)
GENERIC_URL_CREDENTIAL_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9+.-]*://)([^/\s:@]+):([^@\s/]+)@",
    re.IGNORECASE,
)
URI_HOST_RE = re.compile(
    r"\b(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)"
    r"(?P<credential><redacted>@)?"
    r"(?P<host>\[[^\]\s]+\]|[^/\s:?#'\"`]+)"
    r"(?P<port>:\d+)?"
)
USER_PATH_RE = re.compile(r"(?i)(/user/)[^/\s'\"`]+")


class CollectorError(Exception):
    """Raised for validation or collection failures that are safe to print."""


@dataclass(frozen=True)
class StatementPlan:
    table: str
    label: str
    sql: str


@dataclass
class StatementResult:
    table: str
    label: str
    sql: str
    status: str
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    error: str = ""
    stdout_raw_bytes: int = 0
    stdout_bytes: int = 0
    stdout_normalized: bool = False
    stderr_raw_bytes: int = 0
    stderr_bytes: int = 0
    stderr_normalized: bool = False


Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def redact_impala_context_text(text: object) -> str:
    redacted = redact_profile_text(str(text))
    redacted = GENERIC_URL_CREDENTIAL_RE.sub(r"\1<redacted>@", redacted)
    redacted = redact_uri_hosts(redacted)
    redacted = SQL_SECRET_VALUE_RE.sub(r"\1<redacted>\3", redacted)
    redacted = USER_PATH_RE.sub(r"\1<user>", redacted)
    return redacted


def redact_uri_hosts(text: str) -> str:
    host_redactor = HostAliasRedactor()

    def replace_host(match: re.Match[str]) -> str:
        host = match.group("host")
        if host.startswith("host_"):
            alias = host
        else:
            alias = host_redactor.alias_for(host.strip("[]"))
        return (
            f"{match.group('scheme')}{match.group('credential') or ''}"
            f"{alias}{match.group('port') or ''}"
        )

    return URI_HOST_RE.sub(replace_host, text)


def normalize_table_identifier(raw_table: str) -> str:
    table = raw_table.strip()
    if not table:
        raise CollectorError("Table identifier must not be empty.")
    if any(marker in table for marker in (";", "--", "/*", "*/")):
        raise CollectorError(f"Refusing unsafe table identifier: {raw_table!r}")
    if any(quote in table for quote in ("'", '"')):
        raise CollectorError(f"Refusing quoted table identifier: {raw_table!r}")
    if re.search(r"\s", table):
        raise CollectorError(f"Refusing table identifier with whitespace: {raw_table!r}")

    parts = table.split(".")
    if len(parts) != 2:
        raise CollectorError(
            f"Refusing table identifier {raw_table!r}; expected exactly db.table."
        )

    normalized_parts: list[str] = []
    for part in parts:
        match = IDENTIFIER_PART_RE.fullmatch(part)
        if not match:
            raise CollectorError(f"Refusing unsupported table identifier: {raw_table!r}")
        normalized_parts.append(match.group(1) or match.group(2))
    return ".".join(normalized_parts)


def dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def build_statement_plan(tables: Iterable[str]) -> list[StatementPlan]:
    plans: list[StatementPlan] = []
    for table in tables:
        normalized_table = normalize_table_identifier(table)
        plans.extend(
            [
                StatementPlan(
                    table=normalized_table,
                    label="SHOW CREATE TABLE",
                    sql=f"SHOW CREATE TABLE {normalized_table}",
                ),
                StatementPlan(
                    table=normalized_table,
                    label="SHOW TABLE STATS",
                    sql=f"SHOW TABLE STATS {normalized_table}",
                ),
                StatementPlan(
                    table=normalized_table,
                    label="SHOW COLUMN STATS",
                    sql=f"SHOW COLUMN STATS {normalized_table}",
                ),
            ]
        )
    return plans


def validate_read_only_statement(sql: str, table: str) -> None:
    normalized = " ".join(sql.strip().rstrip(";").split())
    allowed = {f"{prefix} {table}" for prefix in ALLOWED_STATEMENTS}
    if normalized not in allowed:
        raise CollectorError(f"Refusing unsupported Impala statement: {sql}")


def build_impala_shell_args(args: argparse.Namespace, sql: str) -> list[str]:
    return build_impala_shell_argv(
        impala_shell=args.impala_shell,
        coordinator=args.coordinator,
        auth=args.auth,
        sql=sql,
        protocol=args.protocol,
        ssl=args.ssl,
        ca_cert=args.ca_cert,
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
            error=redact_impala_context_text(exc),
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

    stdout = redact_impala_context_text(stdout_output.text)
    stderr = redact_impala_context_text(stderr_output.text)
    if proc.returncode != 0:
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


def planned_result(plan: StatementPlan) -> StatementResult:
    return StatementResult(
        table=plan.table,
        label=plan.label,
        sql=plan.sql,
        status="planned",
    )


def result_to_json(result: StatementResult) -> dict[str, object]:
    return {
        "table": result.table,
        "statement": result.label,
        "sql": result.sql,
        "status": result.status,
        "returncode": result.returncode,
        "error": result.error,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "stdout_raw_bytes": result.stdout_raw_bytes,
        "stdout_bytes": result.stdout_bytes,
        "stdout_normalized": result.stdout_normalized,
        "stderr_raw_bytes": result.stderr_raw_bytes,
        "stderr_bytes": result.stderr_bytes,
        "stderr_normalized": result.stderr_normalized,
    }


def render_statement_output(result: StatementResult) -> str:
    output = result.stdout.strip()
    if result.stderr.strip():
        output = (output + "\n\nstderr:\n" + result.stderr.strip()).strip()
    if result.error:
        output = (output + "\n\nerror: " + result.error).strip()
    return output or "(no output captured)"


def render_markdown(
    *,
    timestamp: str,
    tables: list[str],
    results: list[StatementResult],
    args: argparse.Namespace,
) -> str:
    lines = [
        "# Impala Context",
        "",
        "## Collection Summary",
        f"- collection timestamp: {timestamp}",
        f"- tables requested: {len(tables)}",
        "- read-only statements only: yes",
        f"- max output bytes: {args.max_output_bytes}",
        f"- timeout seconds: {args.timeout_sec}",
        "- redaction: enabled",
        f"- dry-run: {'yes' if args.dry_run else 'no'}",
        "",
    ]

    for table in tables:
        lines += [f"## Table: {table}", ""]
        for result in [item for item in results if item.table == table]:
            fence = "sql" if result.label == "SHOW CREATE TABLE" else "text"
            lines += [
                f"### {result.label}",
                f"status: {result.status}",
                "",
                f"```{fence}",
                render_statement_output(result),
                "```",
                "",
            ]
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(
    out_dir: Path,
    *,
    timestamp: str,
    tables: list[str],
    results: list[StatementResult],
    args: argparse.Namespace,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(timestamp=timestamp, tables=tables, results=results, args=args)
    payload = {
        "collection_timestamp": timestamp,
        "tables": tables,
        "read_only_statements_only": True,
        "max_output_bytes": args.max_output_bytes,
        "timeout_seconds": args.timeout_sec,
        "redaction": "enabled",
        "dry_run": args.dry_run,
        "results": [result_to_json(result) for result in results],
    }
    (out_dir / "impala_context.md").write_text(markdown, encoding="utf-8")
    (out_dir / "impala_context.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
        coordinator = redact_impala_context_text(args.coordinator) if args.coordinator else "<required for execution>"
        print(f"- coordinator: {coordinator}")
        print(f"- auth: {args.auth}")
        if args.protocol:
            print(f"- protocol: {args.protocol}")
        if args.ssl:
            print("- ssl: yes")
        if args.ca_cert:
            print(f"- ca-cert: {redact_impala_context_text(args.ca_cert)}")
        for plan in plans:
            print(f"- {plan.sql}")
        results = [planned_result(plan) for plan in plans]
    else:
        print(f"Collecting read-only Impala metadata for {len(tables)} table(s).")
        results = []
        for plan in plans:
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
        "--table",
        action="append",
        required=True,
        help="Fully qualified table name to inspect, e.g. db.table. May be repeated.",
    )
    parser.add_argument("--out", required=True, help="Output directory for impala_context.md/json.")
    parser.add_argument("--impala-shell", default="impala-shell", help="impala-shell executable.")
    parser.add_argument(
        "--coordinator",
        help="Impala coordinator HOST:PORT for real execution. Not required for --dry-run.",
    )
    parser.add_argument(
        "--auth",
        default="kerberos",
        help="Authentication mode for impala-shell. Only kerberos is supported.",
    )
    parser.add_argument(
        "--protocol",
        choices=["beeswax", "hs2", "hs2-http"],
        help="Optional impala-shell protocol.",
    )
    parser.add_argument("--ssl", action="store_true", help="Pass --ssl to impala-shell.")
    parser.add_argument("--ca-cert", help="CA certificate path for --ssl connections.")
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=DEFAULT_TIMEOUT_SEC,
        help=f"Timeout per statement in seconds (default: {DEFAULT_TIMEOUT_SEC}).",
    )
    parser.add_argument(
        "--max-output-bytes",
        type=int,
        default=DEFAULT_MAX_OUTPUT_BYTES,
        help=f"Maximum captured stdout+stderr bytes per statement (default: {DEFAULT_MAX_OUTPUT_BYTES}).",
    )
    parser.add_argument(
        "--redact",
        action="store_true",
        default=True,
        help="Redact metadata output before writing. Enabled by default.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without connecting.")
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.timeout_sec <= 0:
        parser.error("--timeout-sec must be positive")
    if args.max_output_bytes <= 0:
        parser.error("--max-output-bytes must be positive")
    try:
        validate_auth(args.auth)
        validate_protocol(args.protocol)
        if args.coordinator:
            args.coordinator = validate_coordinator(args.coordinator)
        elif not args.dry_run:
            parser.error("--coordinator is required unless --dry-run is used")
        if args.ca_cert and not args.ssl:
            parser.error("--ca-cert requires --ssl")
    except ImpalaShellConfigError as exc:
        parser.error(str(exc))
    return args


def main(argv: list[str] | None = None, *, runner: Runner = subprocess.run) -> int:
    args = parse_args(argv)
    try:
        return collect_impala_context(args, runner=runner)
    except (CollectorError, ImpalaShellConfigError) as exc:
        print(f"error: {redact_impala_context_text(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
