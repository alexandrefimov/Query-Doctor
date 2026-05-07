"""Result models and output rendering for Impala metadata collection."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from query_doctor.impala.metadata_policy import StatementPlan


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


def planned_result(plan: StatementPlan) -> StatementResult:
    return StatementResult(
        table=plan.table,
        label=plan.label,
        sql=plan.sql,
        status="planned",
    )


def not_applicable_result(plan: StatementPlan, reason: str) -> StatementResult:
    return StatementResult(
        table=plan.table,
        label=plan.label,
        sql=plan.sql,
        status="not_applicable",
        error=reason,
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
