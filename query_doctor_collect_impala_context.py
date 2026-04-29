#!/usr/bin/env python3
"""
Read-only Impala context collector for Query Doctor cases.

Collects metadata for tables referenced by CASE_DIR/profile_digest.md without
executing the original query or running state-changing/heavy diagnostics.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_MAX_OUTPUT_CHARS = 200_000

ALLOWED_COMMAND_PREFIXES = (
    "SHOW CREATE TABLE",
    "SHOW TABLE STATS",
    "SHOW COLUMN STATS",
    "DESCRIBE FORMATTED",
    "EXPLAIN",
)

FORBIDDEN_COMMAND_PATTERNS = (
    re.compile(r"\bINSERT\b", re.IGNORECASE),
    re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bDROP\b", re.IGNORECASE),
    re.compile(r"\bALTER\b", re.IGNORECASE),
    re.compile(r"\bCOMPUTE\s+(?:INCREMENTAL\s+)?STATS\b", re.IGNORECASE),
    re.compile(r"\bINVALIDATE\b", re.IGNORECASE),
    re.compile(r"\bREFRESH\b", re.IGNORECASE),
    re.compile(r"\bDELETE\b", re.IGNORECASE),
    re.compile(r"\bUPDATE\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
)

IDENTIFIER_PART_RE = re.compile(r"`?([A-Za-z_][A-Za-z0-9_$]*)`?")
TABLE_REF_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+"
    r"(?P<table>"
    r"`?[A-Za-z_][A-Za-z0-9_$]*`?"
    r"(?:\s*\.\s*`?[A-Za-z_][A-Za-z0-9_$]*`?)?"
    r")",
    re.IGNORECASE,
)
CTE_RE = re.compile(
    r"(?:\bWITH\b|,)\s*"
    r"(?P<name>`?[A-Za-z_][A-Za-z0-9_$]*`?)"
    r"(?:\s*\([^)]*\))?\s+AS\s*\(",
    re.IGNORECASE,
)


@dataclass
class TableExtraction:
    tables: list[str]
    warnings: list[str] = field(default_factory=list)


@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    output_path: Path

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


def extract_original_sql(profile_digest_text: str) -> str | None:
    """Extract the original SQL from common profile_digest.md layouts."""
    heading_match = re.search(
        r"(?ims)^##\s+SQL\s*$\s*```(?:sql)?\s*(?P<sql>.*?)\s*```",
        profile_digest_text,
    )
    if heading_match:
        return normalize_sql(heading_match.group("sql"))

    labeled_fence_match = re.search(
        r"(?ims)^\s*(?:#+\s*)?(?:Original\s+)?(?:SQL|Query)\s*:?\s*$"
        r"\s*```(?:sql)?\s*(?P<sql>.*?)\s*```",
        profile_digest_text,
    )
    if labeled_fence_match:
        return normalize_sql(labeled_fence_match.group("sql"))

    first_sql_fence_match = re.search(
        r"(?is)```sql\s*(?P<sql>.*?)\s*```",
        profile_digest_text,
    )
    if first_sql_fence_match:
        return normalize_sql(first_sql_fence_match.group("sql"))

    inline_match = re.search(
        r"(?ims)^\s*(?:Original\s+)?(?:SQL|Query)\s*:\s*(?P<sql>SELECT\b.*?)(?:\n\s*\n|$)",
        profile_digest_text,
    )
    if inline_match:
        return normalize_sql(inline_match.group("sql"))

    return None


def normalize_sql(sql: str) -> str:
    return sql.strip().rstrip(";") + "\n"


def strip_sql_comments_and_strings(sql: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    text = re.sub(r"--[^\n\r]*", " ", text)
    text = re.sub(r"'(?:''|[^'])*'", "''", text)
    text = re.sub(r'"(?:""|[^"])*"', '""', text)
    return text


def normalize_identifier(identifier: str) -> str | None:
    parts = [part.strip() for part in identifier.split(".")]
    if not 1 <= len(parts) <= 2:
        return None

    normalized_parts: list[str] = []
    for part in parts:
        match = IDENTIFIER_PART_RE.fullmatch(part)
        if not match:
            return None
        normalized_parts.append(match.group(1))

    return ".".join(normalized_parts)


def extract_cte_names(clean_sql: str) -> set[str]:
    cte_names: set[str] = set()
    for match in CTE_RE.finditer(clean_sql):
        name = normalize_identifier(match.group("name"))
        if name:
            cte_names.add(name.lower())
    return cte_names


def extract_referenced_tables(sql: str, default_database: str | None = None) -> TableExtraction:
    clean_sql = strip_sql_comments_and_strings(sql)
    cte_names = extract_cte_names(clean_sql)
    warnings: list[str] = []
    found: list[str] = []

    if re.search(r"\b(?:FROM|JOIN)\s*\(", clean_sql, flags=re.IGNORECASE):
        warnings.append("SQL contains FROM/JOIN subqueries; table extraction is best-effort.")

    for match in TABLE_REF_RE.finditer(clean_sql):
        raw_table = match.group("table")
        table = normalize_identifier(raw_table)
        if not table:
            warnings.append(f"Skipped unsupported table reference: {raw_table!r}")
            continue

        if table.lower() in cte_names:
            continue

        if "." not in table:
            if default_database:
                table = f"{default_database}.{table}"
            else:
                warnings.append(
                    f"Unqualified table {table!r} found; pass --database to resolve it."
                )

        if table not in found:
            found.append(table)

    if cte_names:
        warnings.append(
            "CTE names were detected and ignored where possible: "
            + ", ".join(sorted(cte_names))
        )

    if not found:
        warnings.append("No referenced tables were found by the best-effort parser.")

    return TableExtraction(tables=found, warnings=dedupe_preserve_order(warnings))


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def validate_impala_command(command: str) -> None:
    normalized = " ".join(command.strip().rstrip(";").split())
    upper = normalized.upper()

    if not any(upper.startswith(prefix) for prefix in ALLOWED_COMMAND_PREFIXES):
        raise ValueError(f"Refusing unsupported Impala command: {command}")

    # SHOW CREATE TABLE is metadata-only and is one of the explicit allowlisted
    # commands. Keep CREATE TABLE blocked everywhere else, including EXPLAIN.
    forbidden_subject = normalized
    if upper.startswith("SHOW CREATE TABLE "):
        forbidden_subject = normalized[len("SHOW CREATE TABLE ") :]

    for pattern in FORBIDDEN_COMMAND_PATTERNS:
        if pattern.search(forbidden_subject):
            raise ValueError(f"Refusing dangerous Impala command: {command}")


def validate_table_name(table: str) -> None:
    if normalize_identifier(table) != table:
        raise ValueError(f"Refusing unsupported table identifier: {table}")


def safe_table_filename(table: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", table).strip("._") or "table"


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[truncated to {max_chars} characters]\n"


def build_impala_shell_args(args: argparse.Namespace, command: str) -> list[str]:
    shell_args = [args.impala_shell]
    if args.impala_host:
        shell_args.extend(["-i", args.impala_host])
    if args.kerberos:
        shell_args.append("-k")
    if args.database:
        shell_args.extend(["-d", args.database])
    shell_args.extend(["-q", command])
    return shell_args


def run_impala_command(
    args: argparse.Namespace,
    command: str,
    output_path: Path,
    max_output_chars: int,
) -> CommandResult:
    validate_impala_command(command)
    try:
        proc = subprocess.run(
            build_impala_shell_args(args, command),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        stderr = truncate_text(str(exc), max_output_chars)
        write_command_output(output_path, command, 127, "", stderr)
        return CommandResult(
            command=command,
            returncode=127,
            stdout="",
            stderr=stderr,
            output_path=output_path,
        )

    stdout = truncate_text(proc.stdout, max_output_chars)
    stderr = truncate_text(proc.stderr, max_output_chars)
    write_command_output(output_path, command, proc.returncode, stdout, stderr)
    return CommandResult(
        command=command,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
        output_path=output_path,
    )


def write_command_output(
    path: Path,
    command: str,
    returncode: int,
    stdout: str,
    stderr: str,
) -> None:
    lines = [
        f"-- Command: {command}",
        f"-- Return code: {returncode}",
        "",
        stdout.rstrip(),
    ]
    if stderr.strip():
        lines.extend(["", "-- STDERR:", stderr.rstrip()])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_referenced_tables(path: Path, extraction: TableExtraction) -> None:
    lines: list[str] = []
    if extraction.tables:
        lines.extend(extraction.tables)
    else:
        lines.append("# No referenced tables found.")
    if extraction.warnings:
        lines.append("")
        lines.append("# Warnings")
        lines.extend(f"# {warning}" for warning in extraction.warnings)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_summary(
    path: Path,
    *,
    sql_found: bool,
    original_query_path: Path,
    referenced_tables_path: Path,
    extraction: TableExtraction | None,
    results: list[CommandResult],
) -> None:
    lines = [
        "# Impala Context",
        "",
        f"- SQL found: {'yes' if sql_found else 'no'}",
        f"- Original query: `{original_query_path}`",
        f"- Referenced tables: `{referenced_tables_path}`",
        "- Safety: COMPUTE STATS, COMPUTE INCREMENTAL STATS, REFRESH, "
        "INVALIDATE METADATA, and data-scanning diagnostics were not executed.",
    ]

    if extraction:
        lines.append("")
        lines.append("## Referenced Tables")
        if extraction.tables:
            lines.extend(f"- `{table}`" for table in extraction.tables)
        else:
            lines.append("- None found")

        if extraction.warnings:
            lines.append("")
            lines.append("## Warnings")
            lines.extend(f"- {warning}" for warning in extraction.warnings)

    if results:
        lines.append("")
        lines.append("## Metadata Commands")
        for result in results:
            status = "succeeded" if result.succeeded else f"failed rc={result.returncode}"
            lines.append(f"- `{result.command}`: {status}; `{result.output_path}`")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def collect_context(args: argparse.Namespace) -> int:
    case_dir = Path(args.case_dir)
    output_dir_arg = Path(args.output_dir)
    if output_dir_arg.is_absolute() or ".." in output_dir_arg.parts:
        print("--output-dir must be a directory name inside CASE_DIR", file=sys.stderr)
        return 2
    if args.max_output_chars <= 0:
        print("--max-output-chars must be positive", file=sys.stderr)
        return 2
    if args.database and not normalize_identifier(args.database):
        print("--database must be a simple Impala identifier", file=sys.stderr)
        return 2

    digest_path = case_dir / "profile_digest.md"
    output_dir = case_dir / output_dir_arg
    tables_dir = output_dir / "tables"
    original_query_path = output_dir / "original_query.sql"
    referenced_tables_path = output_dir / "referenced_tables.txt"
    summary_path = output_dir / "impala_context.md"

    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    if not digest_path.exists():
        original_query_path.write_text(
            "-- SQL could not be found because profile_digest.md does not exist.\n",
            encoding="utf-8",
        )
        extraction = TableExtraction(tables=[], warnings=["profile_digest.md does not exist."])
        write_referenced_tables(referenced_tables_path, extraction)
        write_summary(
            summary_path,
            sql_found=False,
            original_query_path=original_query_path,
            referenced_tables_path=referenced_tables_path,
            extraction=extraction,
            results=[],
        )
        print(f"No profile_digest.md found: {digest_path}", file=sys.stderr)
        return 0

    profile_text = digest_path.read_text(encoding="utf-8", errors="replace")
    original_sql = extract_original_sql(profile_text)
    if not original_sql:
        original_query_path.write_text(
            "-- Original SQL could not be found in profile_digest.md.\n",
            encoding="utf-8",
        )
        extraction = TableExtraction(
            tables=[],
            warnings=["Original SQL could not be found in profile_digest.md."],
        )
        write_referenced_tables(referenced_tables_path, extraction)
        write_summary(
            summary_path,
            sql_found=False,
            original_query_path=original_query_path,
            referenced_tables_path=referenced_tables_path,
            extraction=extraction,
            results=[],
        )
        print(f"Original SQL not found. Wrote placeholder to {original_query_path}")
        return 0

    original_query_path.write_text(original_sql, encoding="utf-8")
    extraction = extract_referenced_tables(original_sql, default_database=args.database)
    write_referenced_tables(referenced_tables_path, extraction)

    results: list[CommandResult] = []
    for table in extraction.tables:
        validate_table_name(table)
        safe_name = safe_table_filename(table)
        commands = [
            (f"SHOW CREATE TABLE {table}", tables_dir / f"{safe_name}.show_create.sql"),
            (f"SHOW TABLE STATS {table}", tables_dir / f"{safe_name}.table_stats.txt"),
            (f"SHOW COLUMN STATS {table}", tables_dir / f"{safe_name}.column_stats.txt"),
            (f"DESCRIBE FORMATTED {table}", tables_dir / f"{safe_name}.describe_formatted.txt"),
        ]
        for command, output_path in commands:
            results.append(
                run_impala_command(args, command, output_path, args.max_output_chars)
            )

    explain_command = "EXPLAIN " + original_sql.strip()
    results.append(
        run_impala_command(
            args,
            explain_command,
            output_dir / "explain.txt",
            args.max_output_chars,
        )
    )

    write_summary(
        summary_path,
        sql_found=True,
        original_query_path=original_query_path,
        referenced_tables_path=referenced_tables_path,
        extraction=extraction,
        results=results,
    )

    failures = sum(1 for result in results if not result.succeeded)
    print(f"Wrote Impala context to {output_dir}")
    if failures:
        print(f"{failures} metadata command(s) failed; see {summary_path}", file=sys.stderr)
        return 1
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect read-only Impala metadata for a Query Doctor case."
    )
    parser.add_argument("case_dir", metavar="CASE_DIR", help="Query Doctor case directory")
    parser.add_argument(
        "--impala-shell",
        default="impala-shell",
        help="impala-shell path or executable name (default: impala-shell)",
    )
    parser.add_argument("--impala-host", help="Impala daemon host[:port] passed as -i")
    parser.add_argument("--kerberos", action="store_true", help="Use Kerberos mode (-k)")
    parser.add_argument(
        "--database",
        help="Default database for impala-shell and unqualified table references",
    )
    parser.add_argument(
        "--output-dir",
        default="impala_context",
        help="Output directory name inside CASE_DIR (default: impala_context)",
    )
    parser.add_argument(
        "--max-output-chars",
        type=int,
        default=DEFAULT_MAX_OUTPUT_CHARS,
        help=f"Maximum captured stdout/stderr chars per command (default: {DEFAULT_MAX_OUTPUT_CHARS})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return collect_context(args)


if __name__ == "__main__":
    raise SystemExit(main())
