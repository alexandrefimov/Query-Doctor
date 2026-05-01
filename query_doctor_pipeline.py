#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from query_doctor_impala_metadata_workflow import (
    add_metadata_arguments,
    build_metadata_collector_cmd,
    build_metadata_plan,
    metadata_config_status,
    print_metadata_plan,
    read_referenced_tables_from_facts,
    resolve_metadata_mode,
    validate_metadata_args,
)


DEFAULT_MODEL = "qwen3-coder:30b"


def run_cmd(cmd: list[str], cwd: Path) -> None:
    print()
    print("[pipeline] running:")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=str(cwd))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def run_metadata_cmd(cmd: list[str], cwd: Path) -> None:
    print()
    print("[pipeline] running explicit read-only Impala metadata collector")
    result = subprocess.run(cmd, cwd=str(cwd))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Query Doctor pipeline: deterministic analyzer -> LLM report writer."
    )
    parser.add_argument(
        "case_dir",
        help="Path to case directory containing profile_digest.md",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Ollama model for report writer. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--mode",
        choices=("admin", "user"),
        default="admin",
        help="Report audience mode passed to query_doctor_report.py. Default: %(default)s",
    )
    parser.add_argument(
        "--out",
        default="diagnosis.md",
        help="Report output path. Relative paths are resolved by query_doctor_report.py relative to CASE_DIR.",
    )
    parser.add_argument(
        "--keep-alive",
        default="0",
        help="Ollama keep_alive value. Default: 0.",
    )
    parser.add_argument(
        "--stop-other-models",
        action="store_true",
        help="Unload other Ollama models before generation.",
    )
    parser.add_argument(
        "--skip-report",
        action="store_true",
        help="Run only deterministic analyzer.",
    )
    parser.add_argument(
        "--stop-after-analysis",
        action="store_true",
        help=(
            "Run analyzer and optional metadata collection, then stop before "
            "report generation; no LLM/Ollama call."
        ),
    )
    add_metadata_arguments(parser)

    args = parser.parse_args(argv)
    validate_metadata_args(parser, args)
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    repo_dir = Path(__file__).resolve().parent
    case_dir = Path(args.case_dir).expanduser()

    if not case_dir.is_absolute():
        case_dir = (Path.cwd() / case_dir).resolve()

    profile_digest = case_dir / "profile_digest.md"
    if not profile_digest.exists():
        print(f"[pipeline] ERROR: missing {profile_digest}", file=sys.stderr)
        return 2

    analyzer = repo_dir / "analyze_profile_digest.py"
    impala_collector = repo_dir / "query_doctor_collect_impala_context.py"

    if not analyzer.exists():
        print(f"[pipeline] ERROR: missing {analyzer}", file=sys.stderr)
        return 2

    metadata_mode = resolve_metadata_mode(args)

    if metadata_mode in {"on", "dry-run"} and not impala_collector.exists():
        print(f"[pipeline] ERROR: missing {impala_collector}", file=sys.stderr)
        return 2

    run_cmd(
        [
            sys.executable,
            str(analyzer),
            str(case_dir),
        ],
        cwd=repo_dir,
    )

    facts = case_dir / "analysis_facts.md"
    if not facts.exists():
        print(f"[pipeline] ERROR: analyzer did not create {facts}", file=sys.stderr)
        return 3

    print()
    print(f"[pipeline] facts: {facts}")

    if metadata_mode == "auto":
        config_status = metadata_config_status(args, base_dir=repo_dir)
        if config_status.configured:
            print("[pipeline] metadata collection: auto mode configured")
            metadata_mode = "on"
            if not impala_collector.exists():
                print(f"[pipeline] ERROR: missing {impala_collector}", file=sys.stderr)
                return 2
        elif config_status.fatal:
            print(f"[pipeline] ERROR: metadata configuration is invalid: {config_status.reason}", file=sys.stderr)
            return 2
        else:
            print(
                "[pipeline] metadata collection: not configured; "
                f"continuing without metadata ({config_status.reason})"
            )

    if metadata_mode in {"on", "dry-run"}:
        if metadata_mode == "on":
            config_status = metadata_config_status(args, base_dir=repo_dir)
            if not config_status.configured:
                print(f"[pipeline] ERROR: metadata collection is not configured: {config_status.reason}", file=sys.stderr)
                return 2
        raw_tables = read_referenced_tables_from_facts(facts)
        metadata_plan = build_metadata_plan(raw_tables, args.metadata_max_tables)
        print_metadata_plan(metadata_plan, dry_run=metadata_mode == "dry-run")
        if metadata_mode == "dry-run":
            print("[pipeline] metadata dry-run complete; analyzer/report were not rerun after metadata collection")
            return 0
        if metadata_plan.selected_tables:
            run_metadata_cmd(
                build_metadata_collector_cmd(
                    args,
                    collector=impala_collector,
                    case_dir=case_dir,
                    tables=metadata_plan.selected_tables,
                ),
                cwd=repo_dir,
            )
            run_cmd(
                [
                    sys.executable,
                    str(analyzer),
                    str(case_dir),
                ],
                cwd=repo_dir,
            )
            if not facts.exists():
                print(f"[pipeline] ERROR: analyzer did not create {facts}", file=sys.stderr)
                return 3
            print()
            print(f"[pipeline] facts refreshed with Impala metadata: {facts}")
        else:
            print("[pipeline] no valid referenced tables found for metadata collection")

    if args.skip_report:
        print("[pipeline] skip report requested")
        return 0

    if args.stop_after_analysis:
        print("[pipeline] stop-after-analysis requested; report generation skipped")
        return 0

    reporter = repo_dir / "query_doctor_report.py"
    if not reporter.exists():
        print(f"[pipeline] ERROR: missing {reporter}", file=sys.stderr)
        return 2

    report_cmd = [
        sys.executable,
        str(reporter),
        str(case_dir),
        "--model",
        args.model,
        "--mode",
        args.mode,
        "--out",
        args.out,
        "--keep-alive",
        args.keep_alive,
    ]

    if args.stop_other_models:
        report_cmd.append("--stop-other-models")

    run_cmd(report_cmd, cwd=repo_dir)

    print()
    print(f"[pipeline] done: {case_dir / args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
