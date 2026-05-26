#!/usr/bin/env python3
"""Dev-only Kerberos/SPNEGO smoke checks for a Trino coordinator.

This script is intentionally not wired into Query Doctor product workflows. It
executes only a small built-in set of read-only smoke statements and writes a
raw-free status summary.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse


DEFAULT_TIMEOUT_SEC = 20
DEFAULT_MAX_RESPONSE_BYTES = 512 * 1024
DEFAULT_MAX_PAGES = 16
SOURCE_HEADER_VALUE = "query-doctor-dev-smoke"
SAFE_ERROR_TYPES = {"USER_ERROR", "INTERNAL_ERROR", "INSUFFICIENT_RESOURCES", "EXTERNAL"}
IDENTIFIER_PART_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
HEADER_VALUE_RE = re.compile(r"[A-Za-z0-9_.@-]{1,128}\Z")
SERVICE_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")

Runner = Callable[..., subprocess.CompletedProcess[bytes]]


class TrinoSmokeError(ValueError):
    """Raised when a smoke configuration or Trino response is unsafe."""


@dataclass(frozen=True)
class SmokeStatement:
    label: str
    statement: str


@dataclass(frozen=True)
class CurlResponse:
    stdout: bytes
    stderr: bytes
    returncode: int


def validate_server(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if value != value.strip() or not normalized:
        raise TrinoSmokeError("--server must not be empty or padded.")
    if parsed.scheme != "https" or not parsed.netloc:
        raise TrinoSmokeError("--server must be an HTTPS coordinator URL.")
    if parsed.username or parsed.password:
        raise TrinoSmokeError("--server must not contain credentials.")
    if parsed.params or parsed.query or parsed.fragment:
        raise TrinoSmokeError("--server must not include params, query, or fragment.")
    if parsed.path not in {"", "/"}:
        raise TrinoSmokeError("--server must not include a path.")
    if re.search(r"\s|[;&|`$<>'\"(){}\\]", normalized):
        raise TrinoSmokeError("--server contains unsupported characters.")
    return normalized


def validate_header_value(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not HEADER_VALUE_RE.fullmatch(normalized) or ":" in normalized:
        raise TrinoSmokeError(f"{field_name} contains unsupported characters.")
    return normalized


def validate_service_name(value: str) -> str:
    normalized = value.strip()
    if not SERVICE_NAME_RE.fullmatch(normalized):
        raise TrinoSmokeError("--service-name must be a short Kerberos service token.")
    return normalized


def validate_table_identifier(value: str) -> str:
    normalized = value.strip()
    parts = normalized.split(".")
    if len(parts) != 3 or any(not IDENTIFIER_PART_RE.fullmatch(part) for part in parts):
        raise TrinoSmokeError("Trino smoke table identifiers must be catalog.schema.table.")
    return ".".join(parts)


def build_smoke_statements(
    *,
    count_table: str | None,
    sample_table: str | None,
) -> list[SmokeStatement]:
    statements = [
        SmokeStatement("actor_identity_check", "SELECT current_user"),
        SmokeStatement("source_listing_check", "SHOW CATALOGS"),
    ]
    if count_table:
        table = validate_table_identifier(count_table)
        statements.append(SmokeStatement("count_check", f"SELECT count(*) FROM {table}"))
    if sample_table:
        table = validate_table_identifier(sample_table)
        statements.append(SmokeStatement("sample_row_check", f"SELECT * FROM {table} LIMIT 1"))
    for statement in statements:
        validate_allowlisted_statement(statement)
    return statements


def validate_allowlisted_statement(statement: SmokeStatement) -> None:
    sql = statement.statement
    if ";" in sql or "--" in sql or "/*" in sql or "*/" in sql:
        raise TrinoSmokeError("Smoke statement contains unsupported SQL separators or comments.")
    if sql in {"SELECT current_user", "SHOW CATALOGS"}:
        return
    if re.fullmatch(
        r"SELECT count\(\*\) FROM [A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*",
        sql,
    ):
        return
    if re.fullmatch(
        r"SELECT \* FROM [A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]* LIMIT 1",
        sql,
    ):
        return
    raise TrinoSmokeError("Smoke statement is not in the built-in allowlist.")


def statement_endpoint(server: str) -> str:
    return f"{server}/v1/statement"


def validate_next_uri(value: Any, *, server: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TrinoSmokeError("Trino response next page pointer has an unsafe shape.")
    parsed = urlparse(value)
    server_parsed = urlparse(server)
    if parsed.scheme != "https" or parsed.netloc != server_parsed.netloc:
        raise TrinoSmokeError("Trino response next page pointer moved outside the coordinator.")
    if not parsed.path.startswith("/v1/statement/"):
        raise TrinoSmokeError("Trino response next page pointer is outside the statement path.")
    return value


def build_curl_argv(
    *,
    args: argparse.Namespace,
    endpoint: str,
    method: str,
) -> list[str]:
    argv = [
        "curl",
        "--http1.1",
        "--negotiate",
        "--service-name",
        args.service_name,
        "-u",
        f"{args.kerberos_principal}:",
        "--max-time",
        str(args.timeout_sec),
        "--max-filesize",
        str(args.max_response_bytes),
        "--silent",
        "--show-error",
        "-H",
        f"X-Trino-User: {args.client_user}",
        "-H",
        f"X-Trino-Source: {SOURCE_HEADER_VALUE}",
    ]
    if args.insecure:
        argv.append("--insecure")
    if args.ca_cert:
        argv.extend(["--cacert", args.ca_cert])
    if method == "POST":
        argv.extend(["--data-binary", "@-"])
    argv.append(endpoint)
    return argv


def effective_env(args: argparse.Namespace) -> dict[str, str] | None:
    if not args.krb5_ccname and not args.krb5_config:
        return None
    env = os.environ.copy()
    if args.krb5_ccname:
        env["KRB5CCNAME"] = args.krb5_ccname
    if args.krb5_config:
        env["KRB5_CONFIG"] = args.krb5_config
    return env


def run_curl(
    argv: list[str],
    *,
    input_bytes: bytes | None,
    timeout_sec: int,
    runner: Runner,
    env: dict[str, str] | None,
) -> CurlResponse:
    try:
        proc = runner(
            argv,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_sec + 5,
            shell=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return CurlResponse(stdout=b"", stderr=b"", returncode=124)
    except OSError:
        return CurlResponse(stdout=b"", stderr=b"", returncode=127)
    return CurlResponse(
        stdout=proc.stdout or b"",
        stderr=proc.stderr or b"",
        returncode=proc.returncode,
    )


def parse_response(stdout: bytes, *, max_response_bytes: int) -> dict[str, Any]:
    if len(stdout) > max_response_bytes:
        raise TrinoSmokeError("Trino response exceeded the configured byte bound.")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise TrinoSmokeError("Trino response was not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise TrinoSmokeError("Trino response had an unsafe top-level shape.")
    return payload


def safe_error_category(payload: dict[str, Any]) -> str | None:
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    error_type = error.get("errorType")
    return (
        error_type if isinstance(error_type, str) and error_type in SAFE_ERROR_TYPES else "unknown"
    )


def summarize_statement(
    statement: SmokeStatement,
    *,
    args: argparse.Namespace,
    runner: Runner,
) -> dict[str, Any]:
    env = effective_env(args)
    endpoint = statement_endpoint(args.server)
    next_uri: str | None = endpoint
    method = "POST"
    pages = 0
    rows_seen = 0
    result_field_count: int | None = None
    protocol_state = "unknown"
    error_category: str | None = None
    bytes_seen = 0

    while next_uri:
        if pages >= args.max_pages:
            return result_dict(
                statement.label,
                status="too_many_pages",
                rows_seen=rows_seen,
                result_field_count=result_field_count,
                page_count=pages,
                protocol_state=protocol_state,
                error_category=error_category,
                bytes_seen=bytes_seen,
            )

        input_bytes = statement.statement.encode("utf-8") if method == "POST" else None
        response = run_curl(
            build_curl_argv(args=args, endpoint=next_uri, method=method),
            input_bytes=input_bytes,
            timeout_sec=args.timeout_sec,
            runner=runner,
            env=env,
        )
        pages += 1
        if response.returncode != 0:
            return result_dict(
                statement.label,
                status="request_failed",
                rows_seen=rows_seen,
                result_field_count=result_field_count,
                page_count=pages,
                protocol_state=protocol_state,
                error_category=error_category,
                bytes_seen=bytes_seen,
            )

        bytes_seen += len(response.stdout)
        if bytes_seen > args.max_response_bytes:
            return result_dict(
                statement.label,
                status="too_large",
                rows_seen=rows_seen,
                result_field_count=result_field_count,
                page_count=pages,
                protocol_state=protocol_state,
                error_category=error_category,
                bytes_seen=bytes_seen,
            )

        try:
            payload = parse_response(response.stdout, max_response_bytes=args.max_response_bytes)
        except TrinoSmokeError:
            return result_dict(
                statement.label,
                status="invalid_response",
                rows_seen=rows_seen,
                result_field_count=result_field_count,
                page_count=pages,
                protocol_state=protocol_state,
                error_category=error_category,
                bytes_seen=bytes_seen,
            )

        stats = payload.get("stats")
        if isinstance(stats, dict) and isinstance(stats.get("state"), str):
            protocol_state = stats["state"]
        columns = payload.get("columns")
        if isinstance(columns, list):
            result_field_count = len(columns)
        data = payload.get("data")
        if isinstance(data, list):
            rows_seen += len(data)
        error_category = safe_error_category(payload) or error_category
        if error_category:
            return result_dict(
                statement.label,
                status="trino_error",
                rows_seen=rows_seen,
                result_field_count=result_field_count,
                page_count=pages,
                protocol_state=protocol_state,
                error_category=error_category,
                bytes_seen=bytes_seen,
            )

        next_uri = validate_next_uri(payload.get("nextUri"), server=args.server)
        method = "GET"

    return result_dict(
        statement.label,
        status="ok",
        rows_seen=rows_seen,
        result_field_count=result_field_count,
        page_count=pages,
        protocol_state=protocol_state,
        error_category=error_category,
        bytes_seen=bytes_seen,
    )


def result_dict(
    label: str,
    *,
    status: str,
    rows_seen: int,
    result_field_count: int | None,
    page_count: int,
    protocol_state: str,
    error_category: str | None,
    bytes_seen: int,
) -> dict[str, Any]:
    return {
        "label": label,
        "status": status,
        "rows_seen": rows_seen,
        "result_field_count": result_field_count if result_field_count is not None else "unknown",
        "page_count": page_count,
        "protocol_state": protocol_state,
        "safe_error_category": error_category or "none",
        "response_bytes": bytes_seen,
    }


def planned_result(statement: SmokeStatement) -> dict[str, Any]:
    return {
        "label": statement.label,
        "status": "planned",
        "rows_seen": "not_run",
        "result_field_count": "not_run",
        "page_count": 0,
        "protocol_state": "not_run",
        "safe_error_category": "none",
        "response_bytes": 0,
    }


def smoke_summary(
    args: argparse.Namespace,
    checks: list[dict[str, Any]],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "summary_kind": "trino_kerberos_smoke_summary_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "dry_run" if dry_run else "execute",
        "connection": {
            "coordinator": "redacted",
            "auth_mode": "kerberos_spnego",
            "client_identity": "redacted",
            "kerberos_service_name": args.service_name,
            "tls_verification": "disabled" if args.insecure else "default",
        },
        "bounds": {
            "timeout_sec": args.timeout_sec,
            "max_response_bytes": args.max_response_bytes,
            "max_pages": args.max_pages,
            "statement_count": len(checks),
        },
        "checks": checks,
        "redaction": {
            "statement_text": "not_written",
            "result_values": "not_written",
            "query_identifiers": "not_written",
            "actor_identity_values": "not_written",
            "location_values": "not_written",
            "object_identity_values": "not_written",
            "failure_details": "not_written",
        },
        "limitations": [
            "dev_only_smoke_harness",
            "built_in_readonly_statement_allowlist_only",
            "not_query_doctor_trino_product_support",
        ],
    }


def write_summary(out_dir: Path, summary: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "trino_smoke_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_smoke(args: argparse.Namespace, *, runner: Runner = subprocess.run) -> int:
    statements = build_smoke_statements(
        count_table=args.count_table,
        sample_table=args.sample_table,
    )
    if args.dry_run:
        checks = [planned_result(statement) for statement in statements]
    else:
        checks = [
            summarize_statement(statement, args=args, runner=runner) for statement in statements
        ]

    summary = smoke_summary(args, checks, dry_run=args.dry_run)
    write_summary(Path(args.out), summary)
    print("[trino-smoke] completed")
    for check in checks:
        print(
            f"- {check['label']}: {check['status']} "
            f"rows={check['rows_seen']} fields={check['result_field_count']}"
        )
    print("[trino-smoke] safe summary written")
    bad_statuses = {
        "request_failed",
        "invalid_response",
        "too_large",
        "too_many_pages",
        "trino_error",
    }
    return 1 if any(check["status"] in bad_statuses for check in checks) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run dev-only Trino Kerberos/SPNEGO smoke checks. The script executes only "
            "built-in read-only smoke statements and writes a raw-free summary."
        )
    )
    parser.add_argument("--server", required=True, help="HTTPS Trino coordinator URL.")
    parser.add_argument("--client-user", required=True, help="Client user for the Trino header.")
    parser.add_argument(
        "--kerberos-principal",
        required=True,
        help="Kerberos client principal already present in the selected ticket cache.",
    )
    parser.add_argument(
        "--service-name",
        default="HTTP",
        help="Kerberos service name for SPNEGO. Default: HTTP.",
    )
    parser.add_argument("--krb5-config", help="Optional KRB5_CONFIG path for this smoke run.")
    parser.add_argument("--krb5-ccname", help="Optional KRB5CCNAME value for this smoke run.")
    parser.add_argument("--ca-cert", help="Optional CA certificate path for curl.")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS verification for local smoke only.",
    )
    parser.add_argument(
        "--count-table",
        help="Optional catalog.schema.table for the built-in count smoke.",
    )
    parser.add_argument(
        "--sample-table",
        help="Optional catalog.schema.table for the built-in one-row sample smoke.",
    )
    parser.add_argument(
        "--out", required=True, help="Output directory for trino_smoke_summary.json."
    )
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=DEFAULT_TIMEOUT_SEC,
        help=f"Timeout per protocol request in seconds. Default: {DEFAULT_TIMEOUT_SEC}.",
    )
    parser.add_argument(
        "--max-response-bytes",
        type=int,
        default=DEFAULT_MAX_RESPONSE_BYTES,
        help=(
            "Maximum captured Trino response bytes per statement. "
            f"Default: {DEFAULT_MAX_RESPONSE_BYTES}."
        ),
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help=f"Maximum Trino protocol pages per statement. Default: {DEFAULT_MAX_PAGES}.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan checks without connecting.")
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.server = validate_server(args.server)
        args.client_user = validate_header_value(args.client_user, field_name="--client-user")
        args.kerberos_principal = validate_header_value(
            args.kerberos_principal,
            field_name="--kerberos-principal",
        )
        args.service_name = validate_service_name(args.service_name)
        if args.count_table:
            args.count_table = validate_table_identifier(args.count_table)
        if args.sample_table:
            args.sample_table = validate_table_identifier(args.sample_table)
        if args.timeout_sec <= 0:
            parser.error("--timeout-sec must be positive")
        if args.max_response_bytes <= 0:
            parser.error("--max-response-bytes must be positive")
        if args.max_pages <= 0:
            parser.error("--max-pages must be positive")
    except TrinoSmokeError as exc:
        parser.error(str(exc))
    return args


def main(argv: list[str] | None = None, *, runner: Runner = subprocess.run) -> int:
    args = parse_args(argv)
    try:
        return run_smoke(args, runner=runner)
    except TrinoSmokeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
