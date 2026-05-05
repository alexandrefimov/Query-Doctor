#!/usr/bin/env python3
"""Compare Query LLM optimizer outcomes across local Ollama models."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from query_doctor_optimize_query import MARKER_NAME, OUTPUT_NAME, PARTIAL_NAME, RECOMMENDATIONS_NAME
from query_doctor_report import DEFAULT_KEEP_ALIVE, DEFAULT_OLLAMA_URL


PROGRESS_PREFIX = "[Query Doctor optimizer compare]"
HIDDEN_ERROR_PATH = "<local path hidden>"
HIDDEN_ARTIFACT = "<artifact hidden>"
GENERATED_ARTIFACT_FILENAME_RE = re.compile(
    r"\b(?:analysis_facts\.md|cm_metadata\.json|optimized_query\.sql|"
    r"optimized_query\.partial\.txt|optimized_query_recommendations\.md|"
    r"optimized_query\.validated\.json)\b",
    re.IGNORECASE,
)


def safe_slug(value: str) -> str:
    value = value.strip().replace("/", "_")
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)[:64] or "item"


def safe_error_summary(value: object, *, max_chars: int = 500) -> str:
    text = str(value).replace("\n", " ").strip()
    text = re.sub(r"(?<![\w/])(?:/private)?/tmp/[^\s<>'\"]+", HIDDEN_ERROR_PATH, text)
    text = re.sub(r"(?<![\w/])/Users/[^\s<>'\"]+", HIDDEN_ERROR_PATH, text)
    text = re.sub(r"(?<![\w/])(?:/private)?/var/folders/[^\s<>'\"]+", HIDDEN_ERROR_PATH, text)
    text = re.sub(r"(?<![\w/])[A-Za-z]:\\[^\s<>'\"]+", HIDDEN_ERROR_PATH, text)
    text = GENERATED_ARTIFACT_FILENAME_RE.sub(HIDDEN_ARTIFACT, text)
    return text[:max_chars]


def case_label(case_dir: Path) -> str:
    return f"{safe_slug(case_dir.parent.name)}:{safe_slug(case_dir.name)}"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare Query LLM optimizer outcomes across Ollama models.")
    parser.add_argument("cases", nargs="*", type=Path, help="Case directories with analysis_facts.md and source SQL context.")
    parser.add_argument("--models", nargs="+", required=True, help="Ollama model names to compare.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/tmp/query-doctor-optimizer-bakeoff"),
        help="Output directory for copied cases and summary.json.",
    )
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--keep-alive", default=DEFAULT_KEEP_ALIVE)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument(
        "--optimizer-num-predict",
        type=int,
        default=int(os.getenv("QD_OPTIMIZER_NUM_PREDICT", "4096")),
        help="QD_OPTIMIZER_NUM_PREDICT value to use for each optimizer run.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Resolve cases and write summary without calling Ollama.")
    return parser.parse_args(argv)


def read_marker(case_dir: Path) -> dict[str, Any]:
    try:
        marker = json.loads((case_dir / MARKER_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return marker if isinstance(marker, dict) else {}


def extract_error_summary(stderr: str) -> str:
    errors = []
    for line in stderr.splitlines():
        if "ERROR:" in line:
            errors.append(line.split("ERROR:", 1)[1].strip())
    if not errors:
        errors = [line.strip() for line in stderr.splitlines()[-3:] if line.strip()]
    return safe_error_summary("; ".join(errors))


def copy_case_for_run(case_dir: Path, run_dir: Path) -> None:
    if run_dir.exists():
        shutil.rmtree(run_dir)
    shutil.copytree(case_dir, run_dir)
    for name in (OUTPUT_NAME, PARTIAL_NAME, MARKER_NAME, RECOMMENDATIONS_NAME):
        path = run_dir / name
        if path.exists():
            path.unlink()


def run_case_model(
    *,
    case_dir: Path,
    model: str,
    run_index: int,
    out_dir: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    label = case_label(case_dir)
    run_dir = out_dir / "runs" / safe_slug(model) / f"{safe_slug(label)}_run{run_index:02d}"
    copy_case_for_run(case_dir, run_dir)

    common = {
        "case_name": label,
        "requested_model": model,
        "run_index": run_index,
    }
    if args.dry_run:
        return {
            **common,
            "status": "dry_run",
            "validation_status": "not_run",
            "output_kind": "",
            "elapsed_sec": 0.0,
            "error_summary": "",
        }

    env = os.environ.copy()
    env["QD_OPTIMIZER_NUM_PREDICT"] = str(args.optimizer_num_predict)
    started = time.time()
    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "query_doctor_optimize_query.py"),
            str(run_dir),
            "--model",
            model,
            "--ollama-url",
            args.ollama_url,
            "--temperature",
            str(args.temperature),
            "--keep-alive",
            args.keep_alive,
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        text=True,
        capture_output=True,
        timeout=3600,
        check=False,
    )
    elapsed = round(time.time() - started, 2)
    marker = read_marker(run_dir)
    output_kind = str(marker.get("output_kind") or "")
    fallback_reason = str(marker.get("fallback_reason") or "")
    generation_metadata = marker.get("generation_metadata")
    if not isinstance(generation_metadata, dict):
        generation_metadata = {}
    validation_errors = marker.get("validation_errors")
    if not isinstance(validation_errors, list):
        validation_errors = []
    if completed.returncode == 0 and marker:
        status = "ok"
        validation_status = "passed"
    elif completed.returncode == 4 and (run_dir / PARTIAL_NAME).is_file():
        status = "validation_failed"
        validation_status = "failed"
    else:
        status = "error"
        validation_status = "failed"
    return {
        **common,
        "status": status,
        "validation_status": validation_status,
        "output_kind": output_kind or ("partial_untrusted" if (run_dir / PARTIAL_NAME).is_file() else ""),
        "fallback_reason": fallback_reason,
        "generation_metadata": generation_metadata,
        "validation_errors": [safe_error_summary(error, max_chars=200) for error in validation_errors],
        "elapsed_sec": elapsed,
        "error_summary": "" if status == "ok" else extract_error_summary(completed.stderr),
    }


def build_aggregates(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_model: dict[str, dict[str, Any]] = {}
    for result in results:
        model = str(result.get("requested_model") or "unknown")
        bucket = by_model.setdefault(
            model,
            {
                "runs": 0,
                "status_counts": defaultdict(int),
                "output_kind_counts": defaultdict(int),
                "fallback_reason_counts": defaultdict(int),
                "elapsed_sec": [],
            },
        )
        bucket["runs"] += 1
        bucket["status_counts"][str(result.get("status") or "unknown")] += 1
        bucket["output_kind_counts"][str(result.get("output_kind") or "none")] += 1
        bucket["fallback_reason_counts"][str(result.get("fallback_reason") or "none")] += 1
        if result.get("status") == "ok" and isinstance(result.get("elapsed_sec"), (int, float)):
            bucket["elapsed_sec"].append(float(result["elapsed_sec"]))

    rendered: dict[str, Any] = {}
    for model, bucket in by_model.items():
        runs = max(1, int(bucket["runs"]))
        elapsed = bucket["elapsed_sec"]
        rendered[model] = {
            "runs": bucket["runs"],
            "trusted_outcome_rate": bucket["status_counts"].get("ok", 0) / runs,
            "trusted_sql_draft_rate": bucket["output_kind_counts"].get("sql_draft", 0) / runs,
            "trusted_no_rewrite_rate": bucket["output_kind_counts"].get("no_rewrite", 0) / runs,
            "trusted_recommendations_rate": bucket["output_kind_counts"].get("recommendations_only", 0) / runs,
            "partial_untrusted_rate": bucket["output_kind_counts"].get("partial_untrusted", 0) / runs,
            "mean_elapsed_sec": sum(elapsed) / len(elapsed) if elapsed else None,
            "status_counts": dict(bucket["status_counts"]),
            "output_kind_counts": dict(bucket["output_kind_counts"]),
            "fallback_reason_counts": dict(bucket["fallback_reason_counts"]),
        }
    return {"by_model": rendered}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.repeat < 1:
        print(f"{PROGRESS_PREFIX} ERROR: --repeat must be >= 1", file=sys.stderr)
        return 2
    if args.optimizer_num_predict < 1:
        print(f"{PROGRESS_PREFIX} ERROR: --optimizer-num-predict must be >= 1", file=sys.stderr)
        return 2
    case_dirs = [path.expanduser().resolve() for path in args.cases]
    if not case_dirs:
        print(f"{PROGRESS_PREFIX} ERROR: provide at least one case directory.", file=sys.stderr)
        return 2
    missing = [path for path in case_dirs if not path.is_dir()]
    if missing:
        print(f"{PROGRESS_PREFIX} ERROR: case directory is unavailable: {safe_error_summary(missing[0])}", file=sys.stderr)
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for case_dir in case_dirs:
        for model in args.models:
            for run_index in range(1, args.repeat + 1):
                print(
                    f"{PROGRESS_PREFIX} running case={case_label(case_dir)} model={model} run={run_index}",
                    file=sys.stderr,
                    flush=True,
                )
                results.append(run_case_model(case_dir=case_dir, model=model, run_index=run_index, out_dir=args.out_dir, args=args))
                (args.out_dir / "summary.json").write_text(
                    json.dumps(
                        {
                            "results": results,
                            "aggregates": build_aggregates(results),
                            "optimizer_num_predict": args.optimizer_num_predict,
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
