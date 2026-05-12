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

from query_doctor.cli.optimize_query import (
    MARKER_NAME,
    OUTPUT_NAME,
    PARTIAL_NAME,
    RECOMMENDATIONS_NAME,
    decide_optimizer_risk_mode,
    detect_optimizer_rewrite_recipe,
    draft_has_material_change,
    validate_draft_sql,
)
from query_doctor.report.llm_client import DEFAULT_KEEP_ALIVE, DEFAULT_OLLAMA_URL


PROGRESS_PREFIX = "[Query Doctor optimizer compare]"
DEFAULT_FIXTURE_CORPUS = PROJECT_ROOT / "tests" / "fixtures" / "optimizer_cases"
HIDDEN_ERROR_PATH = "<local path hidden>"
HIDDEN_ARTIFACT = "<artifact hidden>"
SCORING_SCOPE_LABELS = {
    "deterministic_recipe": "Deterministic recipe",
    "deterministic_no_rewrite": "Deterministic no-rewrite",
    "llm_recommendations": "LLM recommendations",
    "llm_sql_draft": "LLM SQL draft",
    "llm_sql_validation": "LLM SQL validation fallback",
    "offline_validator": "Offline validator",
    "dry_run": "Dry run",
    "error": "Error",
    "unknown": "Unknown",
}
MODEL_COMPARABLE_SCOPES = frozenset(
    {
        "llm_recommendations",
        "llm_sql_draft",
        "llm_sql_validation",
        "error",
    }
)
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


def markdown_escape(value: object) -> str:
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ").strip()


def case_label(case_dir: Path) -> str:
    return f"{safe_slug(case_dir.parent.name)}:{safe_slug(case_dir.name)}"


def read_case_list_file(path: Path) -> list[str]:
    references: list[str] = []
    try:
        lines = path.expanduser().read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"cannot read cases file: {safe_error_summary(exc)}") from exc
    for line in lines:
        value = line.split("#", 1)[0].strip()
        if value:
            references.append(value)
    return references


def find_case_dir_by_id(case_root: Path, case_id: str) -> Path:
    normalized = safe_slug(case_id.replace(":", "_"))
    direct = case_root / normalized
    if direct.is_dir():
        return direct.resolve()
    matches = sorted(
        path.resolve()
        for path in case_root.rglob(normalized)
        if path.is_dir() and path.name == normalized
    )
    if not matches:
        raise ValueError(f"case id not found under --cases-root: {safe_slug(case_id)}")
    if len(matches) > 1:
        raise ValueError(f"case id is ambiguous under --cases-root: {safe_slug(case_id)}")
    return matches[0]


def resolve_case_reference(reference: str, *, case_root: Path | None) -> Path:
    expanded = Path(reference).expanduser()
    looks_like_path = (
        expanded.is_absolute()
        or reference.startswith("./")
        or reference.startswith("../")
        or reference.startswith("~")
        or "/" in reference
        or "\\" in reference
    )
    if looks_like_path:
        return expanded.resolve()
    if case_root is None:
        raise ValueError(f"bare case id requires --cases-root: {safe_slug(reference)}")
    return find_case_dir_by_id(case_root, reference)


def resolve_case_dirs(args: argparse.Namespace) -> list[Path]:
    case_root = Path(args.cases_root).expanduser().resolve() if args.cases_root else None
    references: list[str] = []
    if args.cases_file:
        references.extend(read_case_list_file(Path(args.cases_file)))
    references.extend(str(reference) for reference in args.cases)

    resolved: list[Path] = []
    seen: set[Path] = set()
    for reference in references:
        path = resolve_case_reference(reference, case_root=case_root)
        if path not in seen:
            resolved.append(path)
            seen.add(path)
    return resolved


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare Query LLM optimizer outcomes across Ollama models.")
    parser.add_argument(
        "cases",
        nargs="*",
        help="Case directories, or bare case IDs when --cases-root is provided.",
    )
    parser.add_argument("--models", nargs="+", required=True, help="Ollama model names to compare.")
    parser.add_argument(
        "--cases-file",
        type=Path,
        help="Text file with case directories or case IDs, one per line. Blank lines and # comments are ignored.",
    )
    parser.add_argument(
        "--cases-root",
        type=Path,
        help="Root directory used to resolve bare case IDs from positional cases or --cases-file.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/tmp/query-doctor-optimizer-bakeoff"),
        help="Output directory for copied cases, summary.json, summary.md, and optimizer_funnel.json.",
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
    parser.add_argument(
        "--fixture-corpus",
        nargs="?",
        const=DEFAULT_FIXTURE_CORPUS,
        type=Path,
        help=(
            "Append optimizer benchmark fixtures from this corpus directory. "
            f"Default path when passed without a value: {DEFAULT_FIXTURE_CORPUS}."
        ),
    )
    parser.add_argument(
        "--fixture-expected-output-kind",
        nargs="+",
        metavar="KIND",
        help=(
            "When --fixture-corpus is used, include only fixtures whose expected.json "
            "expected_output_kind is one of these values, for example recommendations_only."
        ),
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
    source_path = run_dir / "source.sql"
    original_query_path = run_dir / "original_query.sql"
    if source_path.is_file() and not original_query_path.exists():
        original_query_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    for name in (OUTPUT_NAME, PARTIAL_NAME, MARKER_NAME, RECOMMENDATIONS_NAME):
        path = run_dir / name
        if path.exists():
            path.unlink()


def read_expected_fixture(case_dir: Path) -> dict[str, Any]:
    expected_path = case_dir / "expected.json"
    if not expected_path.is_file():
        return {}
    try:
        payload = json.loads(expected_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def fixture_case_dirs(corpus_dir: Path) -> list[Path]:
    if not corpus_dir.is_dir():
        return []
    return sorted(
        path.resolve()
        for path in corpus_dir.iterdir()
        if path.is_dir() and (path / "expected.json").is_file() and (path / "source.sql").is_file()
    )


def filter_fixture_case_dirs(case_dirs: list[Path], expected_kinds: list[str] | None) -> list[Path]:
    if not expected_kinds:
        return case_dirs
    allowed = {str(kind).strip() for kind in expected_kinds if str(kind).strip()}
    if not allowed:
        return case_dirs
    return [
        case_dir
        for case_dir in case_dirs
        if str(read_expected_fixture(case_dir).get("expected_output_kind") or "") in allowed
    ]


def offline_fixture_outcome(case_dir: Path) -> dict[str, Any]:
    expected = read_expected_fixture(case_dir)
    if not expected:
        return {}
    try:
        source_sql = (case_dir / "source.sql").read_text(encoding="utf-8")
        facts_text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    except OSError as exc:
        return {
            "expected_output_kind": expected.get("expected_output_kind"),
            "matched_expected_outcome": False,
            "offline_error_summary": safe_error_summary(exc),
        }

    risk = decide_optimizer_risk_mode(source_sql)
    recipe = detect_optimizer_rewrite_recipe(source_sql, facts_text)
    offline_recipe = recipe.recipe_id if recipe else None
    offline: dict[str, Any] = {
        "expected_output_kind": expected.get("expected_output_kind"),
        "expected_recipe": expected.get("expected_recipe"),
        "expected_risk_mode": expected.get("expected_risk_mode"),
        "offline_risk_mode": risk.mode,
        "offline_risk_reasons": list(risk.reasons),
        "offline_recipe": offline_recipe,
    }

    draft_path = case_dir / "draft.sql"
    if not draft_path.is_file():
        offline["offline_output_kind"] = "recommendations_only"
        offline["offline_validation_errors"] = []
        offline["matched_expected_outcome"] = (
            expected.get("expected_output_kind") == "recommendations_only"
            and expected.get("expected_recipe") == offline_recipe
            and expected.get("expected_risk_mode") == risk.mode
            and list(expected.get("expected_risk_reasons", risk.reasons)) == list(risk.reasons)
        )
        return offline

    draft_sql = draft_path.read_text(encoding="utf-8")
    errors = validate_draft_sql(source_sql, draft_sql, recipe)
    material_change = draft_has_material_change(source_sql, draft_sql)
    if errors:
        output_kind = "validation_rejected"
    elif material_change:
        output_kind = "sql_draft"
    else:
        output_kind = "no_rewrite"
    offline.update(
        {
            "offline_output_kind": output_kind,
            "offline_material_change": material_change,
            "offline_validation_errors": [safe_error_summary(error, max_chars=200) for error in errors],
        }
    )
    expected_errors = expected.get("expect_validation_errors", [])
    if not isinstance(expected_errors, list):
        expected_errors = []
    offline["matched_expected_outcome"] = (
        expected.get("expected_output_kind") == output_kind
        and expected.get("expected_recipe") == offline_recipe
        and expected.get("expected_risk_mode") == risk.mode
        and bool(expected.get("expect_material_change", material_change)) == material_change
        and all(str(error) in errors for error in expected_errors)
        and (bool(expected_errors) or not errors)
    )
    return offline


def actual_matches_expected_outcome(*, status: str, marker: dict[str, Any], expected: dict[str, Any]) -> bool:
    if status != "ok":
        return False
    expected_kind = str(expected.get("expected_output_kind") or "")
    output_kind = str(marker.get("output_kind") or "")
    if expected_kind == "validation_rejected":
        return output_kind == "no_rewrite" and str(marker.get("fallback_reason") or "") == "validation_failed"
    if expected_kind != output_kind:
        return False
    expected_recipe = expected.get("expected_recipe")
    if expected_recipe is None:
        return "rewrite_recipe" not in marker
    return str(marker.get("rewrite_recipe") or "") == str(expected_recipe)


def actual_expected_outcome_applies(expected: dict[str, Any]) -> bool:
    """Return whether fixture expected output should score an actual CLI run."""
    return str(expected.get("expected_output_kind") or "") != "validation_rejected"


def optimizer_scoring_scope(result: dict[str, Any]) -> str:
    if result.get("expected_outcome_scope") == "offline_validator":
        return "offline_validator"
    status = str(result.get("status") or "")
    if status == "dry_run":
        return "dry_run"
    if status in {"error", "validation_failed"}:
        return "error"
    generation_metadata = result.get("generation_metadata")
    if not isinstance(generation_metadata, dict):
        generation_metadata = {}
    generator = str(generation_metadata.get("generator") or "")
    if generator == "deterministic_recipe":
        return "deterministic_recipe"
    if generator == "deterministic_no_rewrite":
        return "deterministic_no_rewrite"
    output_kind = str(result.get("output_kind") or "")
    if output_kind == "recommendations_only":
        return "llm_recommendations"
    if output_kind == "sql_draft" and generation_metadata:
        return "llm_sql_draft"
    if output_kind == "no_rewrite" and generation_metadata:
        return "llm_sql_validation"
    return "unknown"


def is_model_comparable_result(result: dict[str, Any]) -> bool:
    return optimizer_scoring_scope(result) in MODEL_COMPARABLE_SCOPES


def recommendation_normalization_telemetry(result: dict[str, Any]) -> dict[str, Any]:
    generation_metadata = result.get("generation_metadata")
    if not isinstance(generation_metadata, dict):
        return {}
    telemetry = generation_metadata.get("recommendation_normalization")
    return telemetry if isinstance(telemetry, dict) else {}


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
    offline = offline_fixture_outcome(case_dir)
    if offline:
        common.update(offline)
    if args.dry_run:
        return {
            **common,
            "status": "dry_run",
            "validation_status": "not_run",
            "output_kind": "",
            "scoring_scope": "dry_run",
            "elapsed_sec": 0.0,
            "error_summary": "",
        }

    env = os.environ.copy()
    env["QD_OPTIMIZER_NUM_PREDICT"] = str(args.optimizer_num_predict)
    started = time.time()
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "query_doctor.cli.optimize_query",
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
    result = {
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
    if offline:
        offline_match = result.pop("matched_expected_outcome", None)
        if offline_match is not None:
            result["offline_matched_expected_outcome"] = offline_match
        if actual_expected_outcome_applies(offline):
            result["matched_expected_outcome"] = actual_matches_expected_outcome(
                status=status,
                marker=marker,
                expected=offline,
            )
        else:
            result["expected_outcome_scope"] = "offline_validator"
    result["scoring_scope"] = optimizer_scoring_scope(result)
    return result


def build_aggregates(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_model: dict[str, dict[str, Any]] = {}
    by_case: dict[str, dict[str, Any]] = {}
    for result in results:
        model = str(result.get("requested_model") or "unknown")
        case_name = str(result.get("case_name") or "unknown")
        bucket = by_model.setdefault(
            model,
            {
                "runs": 0,
                "status_counts": defaultdict(int),
                "output_kind_counts": defaultdict(int),
                "fallback_reason_counts": defaultdict(int),
                "matched_expected_outcomes": 0,
                "expected_outcomes": 0,
                "elapsed_sec": [],
            },
        )
        update_result_bucket(bucket, result)
        if result.get("status") == "ok" and isinstance(result.get("elapsed_sec"), (int, float)):
            bucket["elapsed_sec"].append(float(result["elapsed_sec"]))

        case_bucket = by_case.setdefault(
            case_name,
            {
                "runs": 0,
                "status_counts": defaultdict(int),
                "output_kind_counts": defaultdict(int),
                "fallback_reason_counts": defaultdict(int),
                "expected_output_kind_counts": defaultdict(int),
                "matched_expected_outcomes": 0,
                "expected_outcomes": 0,
                "models": {},
            },
        )
        update_result_bucket(case_bucket, result)
        expected_kind = str(result.get("expected_output_kind") or "")
        if expected_kind:
            case_bucket["expected_output_kind_counts"][expected_kind] += 1
        case_model_bucket = case_bucket["models"].setdefault(
            model,
            {
                "runs": 0,
                "status_counts": defaultdict(int),
                "output_kind_counts": defaultdict(int),
                "fallback_reason_counts": defaultdict(int),
                "matched_expected_outcomes": 0,
                "expected_outcomes": 0,
            },
        )
        update_result_bucket(case_model_bucket, result)

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
            "expected_outcome_match_rate": (
                bucket["matched_expected_outcomes"] / bucket["expected_outcomes"]
                if bucket["expected_outcomes"]
                else None
            ),
            "mean_elapsed_sec": sum(elapsed) / len(elapsed) if elapsed else None,
            "status_counts": dict(bucket["status_counts"]),
            "output_kind_counts": dict(bucket["output_kind_counts"]),
            "fallback_reason_counts": dict(bucket["fallback_reason_counts"]),
        }
    return {"by_model": rendered, "by_case": render_case_aggregates(by_case)}


def build_optimizer_funnel(results: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: defaultdict[str, int] = defaultdict(int)
    output_kind_counts: defaultdict[str, int] = defaultdict(int)
    fallback_reason_counts: defaultdict[str, int] = defaultdict(int)
    expected_output_kind_counts: defaultdict[str, int] = defaultdict(int)
    offline_output_kind_counts: defaultdict[str, int] = defaultdict(int)
    expected_outcome_runs = 0
    expected_matched_runs = 0
    offline_validator_runs = 0
    scoring_scope_counts: defaultdict[str, int] = defaultdict(int)
    for result in results:
        status = str(result.get("status") or "unknown")
        output_kind = str(result.get("output_kind") or "none")
        fallback_reason = str(result.get("fallback_reason") or "none")
        expected_output_kind = str(result.get("expected_output_kind") or "")
        offline_output_kind = str(result.get("offline_output_kind") or "")
        status_counts[status] += 1
        output_kind_counts[output_kind] += 1
        fallback_reason_counts[fallback_reason] += 1
        if expected_output_kind:
            expected_output_kind_counts[expected_output_kind] += 1
        if offline_output_kind:
            offline_output_kind_counts[offline_output_kind] += 1
        if "matched_expected_outcome" in result:
            expected_outcome_runs += 1
            if result.get("matched_expected_outcome") is True:
                expected_matched_runs += 1
        if result.get("expected_outcome_scope") == "offline_validator":
            offline_validator_runs += 1
        scoring_scope_counts[optimizer_scoring_scope(result)] += 1
    total_runs = len(results)
    trusted_runs = status_counts.get("ok", 0)
    trusted_sql_draft_runs = output_kind_counts.get("sql_draft", 0)
    trusted_no_rewrite_runs = output_kind_counts.get("no_rewrite", 0)
    trusted_recommendations_runs = output_kind_counts.get("recommendations_only", 0)
    partial_untrusted_runs = output_kind_counts.get("partial_untrusted", 0)
    dry_run_runs = status_counts.get("dry_run", 0)
    error_runs = status_counts.get("error", 0) + status_counts.get("validation_failed", 0)
    return {
        "total_runs": total_runs,
        "trusted_outcome_runs": trusted_runs,
        "trusted_sql_draft_runs": trusted_sql_draft_runs,
        "trusted_no_rewrite_runs": trusted_no_rewrite_runs,
        "trusted_recommendations_runs": trusted_recommendations_runs,
        "partial_untrusted_runs": partial_untrusted_runs,
        "dry_run_runs": dry_run_runs,
        "error_runs": error_runs,
        "validation_failed_fallback_runs": sum(
            1
            for result in results
            if result.get("output_kind") == "no_rewrite"
            and result.get("fallback_reason") == "validation_failed"
        ),
        "expected_outcome_runs": expected_outcome_runs,
        "expected_matched_runs": expected_matched_runs,
        "offline_validator_fixture_runs": offline_validator_runs,
        "scoring_scope_counts": dict(sorted(scoring_scope_counts.items())),
        "scoring_scope_summary": build_scoring_scope_summary(results),
        "trusted_outcome_rate": ratio(trusted_runs, total_runs),
        "trusted_sql_draft_rate": ratio(trusted_sql_draft_runs, total_runs),
        "partial_untrusted_rate": ratio(partial_untrusted_runs, total_runs),
        "expected_match_rate": ratio(expected_matched_runs, expected_outcome_runs)
        if expected_outcome_runs
        else None,
        "status_counts": dict(sorted(status_counts.items())),
        "output_kind_counts": dict(sorted(output_kind_counts.items())),
        "fallback_reason_counts": dict(sorted(fallback_reason_counts.items())),
        "expected_output_kind_counts": dict(sorted(expected_output_kind_counts.items())),
        "offline_output_kind_counts": dict(sorted(offline_output_kind_counts.items())),
    }


def build_model_comparable_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_model: dict[str, dict[str, Any]] = {}
    total_runs = 0
    for result in results:
        if not is_model_comparable_result(result):
            continue
        total_runs += 1
        model = str(result.get("requested_model") or "unknown")
        bucket = by_model.setdefault(
            model,
            {
                "runs": 0,
                "status_counts": defaultdict(int),
                "output_kind_counts": defaultdict(int),
                "fallback_reason_counts": defaultdict(int),
                "scoring_scope_counts": defaultdict(int),
                "matched_expected_outcomes": 0,
                "expected_outcomes": 0,
                "elapsed_sec": [],
                "recommendation_telemetry_runs": 0,
                "recommendation_llm_bullet_count": 0,
                "recommendation_matched_candidate_bullet_count": 0,
                "recommendation_canonical_fallback_runs": 0,
                "recommendation_final_model_candidate_bullet_count": 0,
                "recommendation_final_canonical_candidate_bullet_count": 0,
            },
        )
        update_result_bucket(bucket, result)
        bucket["scoring_scope_counts"][optimizer_scoring_scope(result)] += 1
        if result.get("status") == "ok" and isinstance(result.get("elapsed_sec"), (int, float)):
            bucket["elapsed_sec"].append(float(result["elapsed_sec"]))
        telemetry = recommendation_normalization_telemetry(result)
        if telemetry:
            update_recommendation_telemetry_bucket(bucket, telemetry)

    rendered: dict[str, Any] = {}
    for model, bucket in by_model.items():
        runs = max(1, int(bucket["runs"]))
        elapsed = bucket["elapsed_sec"]
        recommendation_runs = int(bucket["recommendation_telemetry_runs"])
        recommendation_llm_bullets = int(bucket["recommendation_llm_bullet_count"])
        recommendation_matched_bullets = int(bucket["recommendation_matched_candidate_bullet_count"])
        rendered[model] = {
            "runs": bucket["runs"],
            "trusted_outcome_rate": bucket["status_counts"].get("ok", 0) / runs,
            "trusted_sql_draft_rate": bucket["output_kind_counts"].get("sql_draft", 0) / runs,
            "trusted_no_rewrite_rate": bucket["output_kind_counts"].get("no_rewrite", 0) / runs,
            "trusted_recommendations_rate": bucket["output_kind_counts"].get("recommendations_only", 0) / runs,
            "partial_untrusted_rate": bucket["output_kind_counts"].get("partial_untrusted", 0) / runs,
            "error_rate": (
                bucket["status_counts"].get("error", 0)
                + bucket["status_counts"].get("validation_failed", 0)
            )
            / runs,
            "expected_outcome_match_rate": (
                bucket["matched_expected_outcomes"] / bucket["expected_outcomes"]
                if bucket["expected_outcomes"]
                else None
            ),
            "mean_elapsed_sec": sum(elapsed) / len(elapsed) if elapsed else None,
            "recommendation_telemetry_runs": recommendation_runs,
            "recommendation_candidate_match_rate": (
                ratio(recommendation_matched_bullets, recommendation_llm_bullets)
                if recommendation_llm_bullets
                else None
            ),
            "recommendation_canonical_fallback_rate": (
                ratio(int(bucket["recommendation_canonical_fallback_runs"]), recommendation_runs)
                if recommendation_runs
                else None
            ),
            "recommendation_llm_bullet_count": recommendation_llm_bullets,
            "recommendation_matched_candidate_bullet_count": recommendation_matched_bullets,
            "recommendation_final_model_candidate_bullet_count": int(
                bucket["recommendation_final_model_candidate_bullet_count"]
            ),
            "recommendation_final_canonical_candidate_bullet_count": int(
                bucket["recommendation_final_canonical_candidate_bullet_count"]
            ),
            "status_counts": dict(bucket["status_counts"]),
            "output_kind_counts": dict(bucket["output_kind_counts"]),
            "fallback_reason_counts": dict(bucket["fallback_reason_counts"]),
            "scoring_scope_counts": dict(sorted(bucket["scoring_scope_counts"].items())),
        }
    return {
        "scopes": sorted(MODEL_COMPARABLE_SCOPES),
        "total_runs": total_runs,
        "by_model": rendered,
    }


def update_recommendation_telemetry_bucket(bucket: dict[str, Any], telemetry: dict[str, Any]) -> None:
    bucket["recommendation_telemetry_runs"] += 1
    bucket["recommendation_llm_bullet_count"] += int(telemetry.get("llm_bullet_count") or 0)
    bucket["recommendation_matched_candidate_bullet_count"] += int(
        telemetry.get("matched_candidate_bullet_count") or 0
    )
    if telemetry.get("canonical_fallback_used") is True:
        bucket["recommendation_canonical_fallback_runs"] += 1
    bucket["recommendation_final_model_candidate_bullet_count"] += int(
        telemetry.get("final_model_candidate_bullet_count") or 0
    )
    bucket["recommendation_final_canonical_candidate_bullet_count"] += int(
        telemetry.get("final_canonical_candidate_bullet_count") or 0
    )


def build_scoring_scope_summary(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for result in results:
        scope = optimizer_scoring_scope(result)
        bucket = buckets.setdefault(
            scope,
            {
                "runs": 0,
                "status_counts": defaultdict(int),
                "output_kind_counts": defaultdict(int),
                "fallback_reason_counts": defaultdict(int),
                "matched_expected_outcomes": 0,
                "expected_outcomes": 0,
            },
        )
        update_result_bucket(bucket, result)
    rendered: dict[str, dict[str, Any]] = {}
    for scope, bucket in sorted(buckets.items()):
        expected_outcomes = int(bucket["expected_outcomes"])
        matched_expected = int(bucket["matched_expected_outcomes"])
        rendered[scope] = {
            "label": SCORING_SCOPE_LABELS.get(scope, scope.replace("_", " ").title()),
            "runs": bucket["runs"],
            "expected_outcome_runs": expected_outcomes,
            "expected_matched_runs": matched_expected,
            "expected_match_rate": ratio(matched_expected, expected_outcomes)
            if expected_outcomes
            else None,
            "status_counts": dict(sorted(bucket["status_counts"].items())),
            "output_kind_counts": dict(sorted(bucket["output_kind_counts"].items())),
        }
    return rendered


def ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def update_result_bucket(bucket: dict[str, Any], result: dict[str, Any]) -> None:
    bucket["runs"] += 1
    bucket["status_counts"][str(result.get("status") or "unknown")] += 1
    bucket["output_kind_counts"][str(result.get("output_kind") or "none")] += 1
    bucket["fallback_reason_counts"][str(result.get("fallback_reason") or "none")] += 1
    if "matched_expected_outcome" in result:
        bucket["expected_outcomes"] += 1
        if result.get("matched_expected_outcome") is True:
            bucket["matched_expected_outcomes"] += 1


def expected_match_rate(bucket: dict[str, Any]) -> float | None:
    expected_outcomes = int(bucket.get("expected_outcomes") or 0)
    if not expected_outcomes:
        return None
    return int(bucket.get("matched_expected_outcomes") or 0) / expected_outcomes


def render_case_aggregates(by_case: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rendered: dict[str, Any] = {}
    for case_name, bucket in sorted(by_case.items()):
        expected_counts = dict(bucket["expected_output_kind_counts"])
        if len(expected_counts) == 1:
            expected_output_kind = next(iter(expected_counts))
        else:
            expected_output_kind = None
        rendered[case_name] = {
            "runs": bucket["runs"],
            "expected_output_kind": expected_output_kind,
            "expected_output_kind_counts": expected_counts,
            "expected_outcome_match_rate": expected_match_rate(bucket),
            "status_counts": dict(bucket["status_counts"]),
            "output_kind_counts": dict(bucket["output_kind_counts"]),
            "fallback_reason_counts": dict(bucket["fallback_reason_counts"]),
            "models": {
                model: {
                    "runs": model_bucket["runs"],
                    "expected_outcome_match_rate": expected_match_rate(model_bucket),
                    "status_counts": dict(model_bucket["status_counts"]),
                    "output_kind_counts": dict(model_bucket["output_kind_counts"]),
                    "fallback_reason_counts": dict(model_bucket["fallback_reason_counts"]),
                }
                for model, model_bucket in sorted(bucket["models"].items())
            },
        }
    return rendered


def format_rate(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{value * 100:.1f}%"


def format_seconds(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{value:.2f}"


def write_summary_outputs(out_dir: Path, payload: dict[str, Any]) -> None:
    (out_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    optimizer_funnel = payload.get("optimizer_funnel")
    if isinstance(optimizer_funnel, dict):
        (out_dir / "optimizer_funnel.json").write_text(
            json.dumps(optimizer_funnel, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    (out_dir / "summary.md").write_text(render_summary_markdown(payload), encoding="utf-8")


def render_summary_markdown(payload: dict[str, Any]) -> str:
    aggregates = payload.get("aggregates")
    if not isinstance(aggregates, dict):
        aggregates = {}
    by_model = aggregates.get("by_model")
    if not isinstance(by_model, dict):
        by_model = {}
    by_case = aggregates.get("by_case")
    if not isinstance(by_case, dict):
        by_case = {}
    results = payload.get("results")
    if not isinstance(results, list):
        results = []
    model_comparable = payload.get("model_comparable")
    if not isinstance(model_comparable, dict):
        model_comparable = build_model_comparable_summary(
            [result for result in results if isinstance(result, dict)]
        )
    model_comparable_by_model = model_comparable.get("by_model")
    if not isinstance(model_comparable_by_model, dict):
        model_comparable_by_model = {}

    lines = [
        "# Query Doctor Optimizer Model Compare",
        "",
        "This is a safety/quality benchmark for Query Doctor optimizer outcomes. It is not a SQL execution or performance benchmark.",
        "The script does not execute candidate SQL; trusted outcomes still depend on deterministic optimizer validation.",
        "",
        f"- runs: {len(results)}",
        f"- optimizer_num_predict: {payload.get('optimizer_num_predict', 'n/a')}",
        "",
        "## Model Summary",
        "",
        "| model | runs | trusted outcome | trusted SQL draft | no rewrite | recommendations | partial untrusted | expected match | mean sec |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model, metrics in sorted(by_model.items()):
        if not isinstance(metrics, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_escape(model),
                    str(metrics.get("runs", 0)),
                    format_rate(metrics.get("trusted_outcome_rate")),
                    format_rate(metrics.get("trusted_sql_draft_rate")),
                    format_rate(metrics.get("trusted_no_rewrite_rate")),
                    format_rate(metrics.get("trusted_recommendations_rate")),
                    format_rate(metrics.get("partial_untrusted_rate")),
                    format_rate(metrics.get("expected_outcome_match_rate")),
                    format_seconds(metrics.get("mean_elapsed_sec")),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Model-Comparable Summary",
            "",
            "This section excludes deterministic recipes, deterministic no-rewrite outcomes, dry-runs, and offline-validator fixtures.",
            "",
            "| model | runs | trusted outcome | trusted SQL draft | no rewrite | recommendations | partial untrusted | error | expected match | recommendation candidate match | recommendation fallback | mean sec |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    if not model_comparable_by_model:
        lines.append("| none | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
    for model, metrics in sorted(model_comparable_by_model.items()):
        if not isinstance(metrics, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_escape(model),
                    str(metrics.get("runs", 0)),
                    format_rate(metrics.get("trusted_outcome_rate")),
                    format_rate(metrics.get("trusted_sql_draft_rate")),
                    format_rate(metrics.get("trusted_no_rewrite_rate")),
                    format_rate(metrics.get("trusted_recommendations_rate")),
                    format_rate(metrics.get("partial_untrusted_rate")),
                    format_rate(metrics.get("error_rate")),
                    format_rate(metrics.get("expected_outcome_match_rate")),
                    format_rate(metrics.get("recommendation_candidate_match_rate")),
                    format_rate(metrics.get("recommendation_canonical_fallback_rate")),
                    format_seconds(metrics.get("mean_elapsed_sec")),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Optimizer Funnel",
            "",
        ]
    )
    optimizer_funnel = payload.get("optimizer_funnel")
    if isinstance(optimizer_funnel, dict):
        lines.extend(
            [
                f"- trusted outcome runs: {optimizer_funnel.get('trusted_outcome_runs', 0)} / {optimizer_funnel.get('total_runs', 0)} ({optimizer_funnel.get('trusted_outcome_rate', 0.0)})",
                f"- trusted SQL draft runs: {optimizer_funnel.get('trusted_sql_draft_runs', 0)} ({optimizer_funnel.get('trusted_sql_draft_rate', 0.0)})",
                f"- trusted no-rewrite runs: {optimizer_funnel.get('trusted_no_rewrite_runs', 0)}",
                f"- trusted recommendations-only runs: {optimizer_funnel.get('trusted_recommendations_runs', 0)}",
                f"- partial untrusted runs: {optimizer_funnel.get('partial_untrusted_runs', 0)} ({optimizer_funnel.get('partial_untrusted_rate', 0.0)})",
                f"- validation-failed fallback runs: {optimizer_funnel.get('validation_failed_fallback_runs', 0)}",
                f"- dry-run runs: {optimizer_funnel.get('dry_run_runs', 0)}",
                f"- error runs: {optimizer_funnel.get('error_runs', 0)}",
                f"- expected match runs: {optimizer_funnel.get('expected_matched_runs', 0)} / {optimizer_funnel.get('expected_outcome_runs', 0)} ({format_rate(optimizer_funnel.get('expected_match_rate'))})",
                f"- offline validator-only fixtures: {optimizer_funnel.get('offline_validator_fixture_runs', 0)}",
                f"- output counts: {format_counts(optimizer_funnel.get('output_kind_counts'))}",
                f"- expected output counts: {format_counts(optimizer_funnel.get('expected_output_kind_counts'))}",
                f"- offline output counts: {format_counts(optimizer_funnel.get('offline_output_kind_counts'))}",
                "",
            ]
        )
        scope_summary = optimizer_funnel.get("scoring_scope_summary")
        if isinstance(scope_summary, dict) and scope_summary:
            lines.extend(
                [
                    "## Scoring Scope Summary",
                    "",
                    "| scope | runs | expected match | status counts | output counts |",
                    "|---|---:|---:|---|---|",
                ]
            )
            for scope, metrics in sorted(scope_summary.items()):
                if not isinstance(metrics, dict):
                    continue
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            markdown_escape(metrics.get("label") or scope),
                            str(metrics.get("runs", 0)),
                            format_rate(metrics.get("expected_match_rate")),
                            markdown_escape(format_counts(metrics.get("status_counts"))),
                            markdown_escape(format_counts(metrics.get("output_kind_counts"))),
                        ]
                    )
                    + " |"
                )
            lines.append("")
    else:
        lines.extend(["- unavailable", ""])
    lines.extend(
        [
            "## Case Summary",
            "",
            "| case | expected | runs | expected match | status counts | output counts |",
            "|---|---|---:|---:|---|---|",
        ]
    )
    for case_name, metrics in sorted(by_case.items()):
        if not isinstance(metrics, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_escape(case_name),
                    markdown_escape(metrics.get("expected_output_kind") or "mixed"),
                    str(metrics.get("runs", 0)),
                    format_rate(metrics.get("expected_outcome_match_rate")),
                    markdown_escape(format_counts(metrics.get("status_counts"))),
                    markdown_escape(format_counts(metrics.get("output_kind_counts"))),
                ]
            )
            + " |"
        )

    mismatches = [
        result
        for result in results
        if isinstance(result, dict) and result.get("matched_expected_outcome") is False
    ]
    lines.extend(["", "## Mismatched Expected Outcomes", ""])
    if not mismatches:
        lines.append("- none")
    else:
        for result in mismatches:
            lines.append(
                "- "
                + ", ".join(
                    [
                        f"case={markdown_escape(result.get('case_name', 'unknown'))}",
                        f"model={markdown_escape(result.get('requested_model', 'unknown'))}",
                        f"run={markdown_escape(result.get('run_index', 'n/a'))}",
                        f"expected={markdown_escape(result.get('expected_output_kind', 'n/a'))}",
                        f"actual={markdown_escape(result.get('output_kind') or result.get('status') or 'n/a')}",
                    ]
                )
            )
    lines.append("")
    return "\n".join(lines)


def format_counts(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    return ", ".join(f"{key}={value[key]}" for key in sorted(value))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.repeat < 1:
        print(f"{PROGRESS_PREFIX} ERROR: --repeat must be >= 1", file=sys.stderr)
        return 2
    if args.optimizer_num_predict < 1:
        print(f"{PROGRESS_PREFIX} ERROR: --optimizer-num-predict must be >= 1", file=sys.stderr)
        return 2
    try:
        case_dirs = resolve_case_dirs(args)
    except ValueError as exc:
        print(f"{PROGRESS_PREFIX} ERROR: {safe_error_summary(exc)}", file=sys.stderr)
        return 2
    fixture_corpus = Path(args.fixture_corpus).expanduser().resolve() if args.fixture_corpus else None
    if fixture_corpus is not None:
        fixture_dirs = fixture_case_dirs(fixture_corpus)
        fixture_dirs = filter_fixture_case_dirs(fixture_dirs, args.fixture_expected_output_kind)
        if not fixture_dirs:
            reason = "fixture corpus is unavailable or empty"
            if args.fixture_expected_output_kind:
                reason = "fixture corpus has no fixtures matching --fixture-expected-output-kind"
            print(
                f"{PROGRESS_PREFIX} ERROR: {reason}: {safe_error_summary(fixture_corpus)}",
                file=sys.stderr,
            )
            return 2
        case_dirs.extend(fixture_dirs)
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
                write_summary_outputs(
                    args.out_dir,
                    {
                        "results": results,
                        "aggregates": build_aggregates(results),
                        "optimizer_funnel": build_optimizer_funnel(results),
                        "model_comparable": build_model_comparable_summary(results),
                        "optimizer_num_predict": args.optimizer_num_predict,
                    },
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
