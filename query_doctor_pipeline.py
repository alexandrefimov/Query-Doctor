#!/usr/bin/env python3

import argparse
import subprocess
import sys
from pathlib import Path


DEFAULT_MODEL = "qwen3-coder:30b"


def run_cmd(cmd: list[str], cwd: Path) -> None:
    print()
    print("[pipeline] running:")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=str(cwd))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
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

    args = parser.parse_args()

    repo_dir = Path(__file__).resolve().parent
    case_dir = Path(args.case_dir).expanduser()

    if not case_dir.is_absolute():
        case_dir = (Path.cwd() / case_dir).resolve()

    profile_digest = case_dir / "profile_digest.md"
    if not profile_digest.exists():
        print(f"[pipeline] ERROR: missing {profile_digest}", file=sys.stderr)
        return 2

    analyzer = repo_dir / "analyze_profile_digest.py"
    reporter = repo_dir / "query_doctor_report.py"

    if not analyzer.exists():
        print(f"[pipeline] ERROR: missing {analyzer}", file=sys.stderr)
        return 2

    if not reporter.exists():
        print(f"[pipeline] ERROR: missing {reporter}", file=sys.stderr)
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

    if args.skip_report:
        print("[pipeline] skip report requested")
        return 0

    report_cmd = [
        sys.executable,
        str(reporter),
        str(case_dir),
        "--model",
        args.model,
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
