#!/usr/bin/env python3
"""Compare report generation across local/remote LLM providers.

The script reads deterministic analysis facts from case directories, builds the
standard Query Doctor report prompt, runs generation via selected provider, and
validates the report text with the same contract used by the packaged report CLI.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from itertools import combinations
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from query_doctor.cli import report as report_writer


PROGRESS_PREFIX = "[Query Doctor model compare]"
DEFAULT_LLM_API_ENV = os.path.expanduser("~/.qdcreds/llm-api.env")
DEFAULT_LLM_API_ENV_VAR = "QD_LLM_ENV"
LLM_API_BASE_URL_ENV = "QD_LLM_API_BASE_URL"
LLM_API_KEY_ENV = "QD_LLM_API_KEY"
LLM_MODELS_PATH = "/api/v1/models"
LLM_CHAT_PATHS = ("/v1/chat/completions", "/api/v1/chat/completions")
HIDDEN_ERROR_PATH = "<local path hidden>"
HIDDEN_ARTIFACT = "<artifact hidden>"
ERROR_SUMMARY_MAX_CHARS = 500
GENERATED_ARTIFACT_FILENAME_RE = re.compile(
    r"\b(?:"
    r"analysis_facts\.md|profile_digest\.md|profile\.txt|raw_profile\.txt|"
    r"cm_metadata\.json|diagnosis\.md|diagnosis_report\.md|report_admin\.md|"
    r"report_user\.md|optimized_query\.sql|optimized_query_validation\.json|"
    r"validated_report\.json|validation_marker\.json|failed\.partial"
    r")\b",
    re.IGNORECASE,
)
REVIEW_COLUMNS = [
    "run_id",
    "case",
    "provider",
    "requested_model",
    "response_model",
    "run_index",
    "validation_mode",
    "status",
    "validator_status",
    "sections_present",
    "grounded_to_facts",
    "signal_recall",
    "unsupported_claim_risk",
    "root_cause_discipline",
    "host_tail_wording",
    "estimate_direction_handling",
    "low_signal_discipline",
    "practical_recommendation_specificity",
    "admin_checks_usefulness",
    "russian_quality",
    "verbosity_detail_balance",
    "consistency_notes",
    "manual_score_1_to_5",
    "critical_failure_yes_no",
    "reviewer_notes",
]


def safe_slug(value: str) -> str:
    value = value.strip().replace("/", "_")
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)[:64] or "model"


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _safe_error_summary(value: object, *, max_chars: int = ERROR_SUMMARY_MAX_CHARS) -> str:
    text = str(value).replace("\n", " ").strip()
    text = re.sub(r"(?<![\w/])(?:/private)?/tmp/[^\s<>'\"]+", HIDDEN_ERROR_PATH, text)
    text = re.sub(r"(?<![\w/])/Users/[^\s<>'\"]+", HIDDEN_ERROR_PATH, text)
    text = re.sub(r"(?<![\w/])(?:/private)?/var/folders/[^\s<>'\"]+", HIDDEN_ERROR_PATH, text)
    text = re.sub(r"(?<![\w/])[A-Za-z]:\\[^\s<>'\"]+", HIDDEN_ERROR_PATH, text)
    text = GENERATED_ARTIFACT_FILENAME_RE.sub(HIDDEN_ARTIFACT, text)
    return text[:max_chars]


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if not 0 <= p <= 100:
        raise ValueError("percentile must be in [0, 100]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * (p / 100.0)
    lower = int(index)
    upper = min(len(ordered) - 1, lower + 1)
    ratio = index - lower
    return ordered[lower] * (1 - ratio) + ordered[upper] * ratio


def _stddev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    average = _mean(values)
    if average is None:
        return None
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return variance**0.5


def _model_key(result: dict[str, Any], fallback: str | None = None) -> str:
    return (
        _as_str(result.get("resolved_model_id"))
        or _as_str(result.get("requested_model"))
        or _as_str(result.get("model"))
        or fallback
        or "unknown"
    )


def _case_label(case_dir: Path) -> str:
    return f"{safe_slug(case_dir.parent.name)}:{safe_slug(case_dir.name)}"


def _case_file_label(case_dir: Path) -> str:
    return safe_slug(_case_label(case_dir))


def _review_run_id(result: dict[str, Any]) -> str:
    provider = safe_slug(_as_str(result.get("provider")) or "unknown")
    model = safe_slug(_as_str(result.get("requested_model")) or _model_key(result))
    case = safe_slug(_as_str(result.get("case_name")) or "unknown")
    run_index = int(result.get("run_index") or 1)
    return f"{provider}_{model}_{case}_run{run_index:02d}"


def _write_review_template_csv(
    *,
    path: Path,
    results: list[dict[str, Any]],
    validation_mode: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for result in sorted(
            results,
            key=lambda item: (
                _as_str(item.get("case_name")) or "",
                _as_str(item.get("requested_model")) or _model_key(item),
                int(item.get("run_index") or 1),
            ),
        ):
            writer.writerow(
                {
                    "run_id": _review_run_id(result),
                    "case": _as_str(result.get("case_name")) or "",
                    "provider": _as_str(result.get("provider")) or "",
                    "requested_model": _as_str(result.get("requested_model")) or "",
                    "response_model": _as_str(result.get("response_model")) or "",
                    "run_index": result.get("run_index") or "",
                    "validation_mode": validation_mode,
                    "status": _as_str(result.get("status")) or "",
                    "validator_status": _as_str(result.get("validation_status")) or "",
                }
            )


def _read_case_list_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"case list file not found: {path}")
    entries: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0].strip()
        if not line:
            continue
        entries.append(line)
    return entries


def _find_case_dir_by_id(case_root: Path, case_id: str) -> Path:
    if not case_root.exists():
        raise FileNotFoundError(f"case root not found: {case_root}")
    if not case_root.is_dir():
        raise NotADirectoryError(f"case root is not a directory: {case_root}")

    candidates: list[Path] = []
    search_keys = [case_id]
    normalized = case_id.replace(":", "_")
    if normalized not in search_keys:
        search_keys.append(normalized)

    for key in search_keys:
        candidates.extend(p for p in case_root.rglob(key) if p.is_dir() and p.name == key)

    # Keep deterministic result set order before optional uniqueness checks.
    candidates = sorted(set(candidates))
    if not candidates:
        raise FileNotFoundError(
            f"case id {case_id!r} (or {normalized!r}) not found under {case_root}"
        )
    if len(candidates) > 1:
        locations = ", ".join(str(candidate) for candidate in sorted(candidates)[:5])
        raise RuntimeError(
            f"case id {case_id!r} is ambiguous under {case_root}; matches: {locations}"
        )
    return candidates[0]


def _resolve_case_reference(reference: str, *, case_root: Path | None) -> Path:
    value = reference.strip()
    if not value:
        raise ValueError("empty case reference")

    # Explicit paths (including nested fixture paths) are supported as-is.
    if "/" in value or value.startswith("./") or value.startswith("../") or value.startswith("~"):
        return Path(os.path.expanduser(value)).expanduser().resolve()

    # Bare ids require a root for deterministic discovery.
    if case_root is None:
        raise ValueError(
            f"case id {value!r} requires --cases-root for lookup (pass case list path root)"
        )
    return _find_case_dir_by_id(case_root.expanduser().resolve(), value)


def _as_str(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_simple_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values


def _normalize_base_url(base_url: str) -> str:
    url = base_url.strip().rstrip("/")
    for suffix in (
        "/api/v1/chat/completions",
        "/v1/chat/completions",
        "/chat/completions",
        "/api/v1",
        "/v1",
    ):
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url


def openai_compatible_chat_endpoints(base_url: str, preferred_path: str | None = None) -> list[str]:
    base = _normalize_base_url(base_url)
    if not base:
        return []
    endpoints: list[str] = []

    if preferred_path:
        path = preferred_path.strip()
        if path.startswith("http://") or path.startswith("https://"):
            return [path.rstrip("/")]
        if not path.startswith("/"):
            path = f"/{path}"
        endpoints.append(f"{base}{path}")

    for path in LLM_CHAT_PATHS:
        candidate = f"{base}{path}"
        if candidate not in endpoints:
            endpoints.append(candidate)
    return endpoints


def extract_model_list(
    llm_api_base_url: str,
    llm_api_key: str,
) -> list[str]:
    base = _normalize_base_url(llm_api_base_url)
    endpoint = f"{base}{LLM_MODELS_PATH}"
    req = urllib.request.Request(
        endpoint,
        method="GET",
        headers={
            "Authorization": f"Bearer {llm_api_key}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))

    models = payload.get("data")
    if not isinstance(models, list):
        raise RuntimeError(f"unexpected /api/v1/models response format: {payload!r}")
    return [
        item["id"] for item in models if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]


def resolve_llm_api_creds(args: argparse.Namespace) -> tuple[str, str]:
    env_file = Path(
        os.path.expanduser(
            os.environ.get(
                DEFAULT_LLM_API_ENV_VAR,
                args.llm_api_env_file or DEFAULT_LLM_API_ENV,
            )
        )
    )
    file_values = load_simple_env_file(env_file)

    api_url = (
        args.llm_api_base_url
        or os.environ.get(LLM_API_BASE_URL_ENV)
        or file_values.get(LLM_API_BASE_URL_ENV, "").strip()
    )
    api_key = (
        args.llm_api_key
        or os.environ.get(LLM_API_KEY_ENV)
        or file_values.get(LLM_API_KEY_ENV, "").strip()
    )
    if not api_url:
        raise RuntimeError(
            f"missing LLM API base URL (set {LLM_API_BASE_URL_ENV} or --llm-api-base-url or {env_file})"
        )
    if not api_key:
        raise RuntimeError(
            f"missing LLM API key (set {LLM_API_KEY_ENV} or --llm-api-key or {env_file})"
        )
    return api_url, api_key


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Query Doctor report generation across supported LLM providers."
    )
    parser.add_argument("cases", nargs="*", help="Case directories with analysis_facts.md")
    parser.add_argument(
        "--models",
        nargs="+",
        required=False,
        default=[],
        help="Model names to compare for each case.",
    )
    parser.add_argument(
        "--provider",
        choices=("ollama", "openai_compatible"),
        default="ollama",
        help="LLM provider for generation. Default: %(default)s",
    )
    parser.add_argument(
        "--mode",
        choices=("admin", "user"),
        default="admin",
        help="Report audience mode. Default: %(default)s",
    )
    parser.add_argument(
        "--validation-mode",
        choices=("strict", "relaxed", "off"),
        default=report_writer.DEFAULT_VALIDATION_MODE,
        help="Validation mode for report contract. Default: %(default)s",
    )
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/tmp/query-doctor-model-bakeoff"),
        help="Output directory for generated reports and summary.json",
    )
    parser.add_argument(
        "--facts",
        default="analysis_facts.md",
        help="Facts file path, relative to CASE_DIR by default",
    )
    parser.add_argument(
        "--ollama-url",
        default=report_writer.DEFAULT_OLLAMA_URL,
        help="Ollama base URL (used only for provider=ollama)",
    )
    parser.add_argument(
        "--keep-alive",
        default=report_writer.DEFAULT_KEEP_ALIVE,
        help="Ollama keep_alive value. Use 0 to unload model after generation.",
    )
    parser.add_argument(
        "--stop-other-models",
        action="store_true",
        help="Before generation, unload other Ollama models with `ollama ps`+`ollama stop`.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Run each case/model pair this many times (default: 1).",
    )
    parser.add_argument(
        "--llm-api-env-file",
        default=None,
        help=(
            f"Path to env file with {LLM_API_BASE_URL_ENV}/{LLM_API_KEY_ENV} "
            "(default: ~/.qdcreds/llm-api.env)."
        ),
    )
    parser.add_argument(
        "--llm-api-base-url",
        default=None,
        help=f"Override {LLM_API_BASE_URL_ENV} (required for provider=openai_compatible).",
    )
    parser.add_argument(
        "--llm-api-key",
        default=None,
        help=f"Override {LLM_API_KEY_ENV} (required for provider=openai_compatible).",
    )
    parser.add_argument(
        "--llm-chat-path",
        default=None,
        help="Override OpenAI-compatible chat-completions path.",
    )
    parser.add_argument(
        "--llm-list-models",
        action="store_true",
        help="List available OpenAI-compatible models and exit.",
    )
    parser.add_argument(
        "--cases-file",
        default=None,
        help="Path to file containing one case id or case directory per line.",
    )
    parser.add_argument(
        "--cases-root",
        default=None,
        help=(
            "Root directory for resolving bare case IDs from --cases-file. "
            "Ignored for explicit case paths."
        ),
    )
    parser.add_argument(
        "--dry-prompt",
        action="store_true",
        help="Build final prompt and exit without calling LLM.",
    )
    parser.add_argument(
        "--parallel-workers",
        type=int,
        default=1,
        help="Run case/model/repeat tasks in parallel using this many worker threads (default: 1).",
    )
    parser.add_argument(
        "--review-template",
        default=None,
        help=(
            "Write a CSV manual quality review template. Default: "
            "OUT_DIR/review_template.csv. Use 'off' to skip."
        ),
    )
    return parser.parse_args(argv)


def stream_or_blocking_prompt(
    *,
    prompt: str,
    provider: str,
    model: str,
    args: argparse.Namespace,
    llm_api_base_url: str | None = None,
    llm_api_key: str | None = None,
) -> tuple[str, dict[str, Any]]:
    if provider == "ollama":
        if args.stop_other_models and model:
            stopped = report_writer.stop_other_ollama_models(
                target_model=model,
            )
            if stopped:
                print(
                    f"{PROGRESS_PREFIX} stopped Ollama models: {', '.join(stopped)}",
                    file=sys.stderr,
                )
            else:
                print(f"{PROGRESS_PREFIX} no other Ollama models to stop", file=sys.stderr)

        return report_writer.stream_ollama_report(
            prompt=prompt,
            model=model,
            ollama_url=args.ollama_url,
            temperature=args.temperature,
            keep_alive=args.keep_alive,
        ), {"model": model, "provider": provider}

    if provider != "openai_compatible":
        raise RuntimeError(f"unsupported provider: {provider}")

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": report_writer.REPORT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": args.temperature,
    }

    last_error: str | None = None
    chat_path = args.llm_chat_path
    for endpoint in openai_compatible_chat_endpoints(llm_api_base_url or "", chat_path):
        endpoint_meta: dict[str, Any] = {}
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {llm_api_key}",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=1800) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                response = json.loads(raw)
        except urllib.error.HTTPError as exc:
            status = exc.code
            if status in {404, 405, 410}:
                last_error = f"{endpoint}: HTTP {status}"
                continue
            last_error = f"{endpoint}: HTTP {status}"
            try:
                raw = exc.read().decode("utf-8", errors="replace")
                if "Not authenticated" in raw:
                    raise RuntimeError(f"{endpoint}: not authenticated")
            except Exception:
                pass
            raise RuntimeError(last_error)
        except (OSError, json.JSONDecodeError) as exc:
            last_error = f"{endpoint}: {exc}"
            continue

        if not isinstance(response, dict):
            last_error = f"{endpoint}: unexpected response type"
            continue

        if "error" in response:
            message = response["error"]
            if isinstance(message, dict):
                message = message.get("message", "unknown error")
            raise RuntimeError(f"LLM API error: {message}")

        choice = None
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
        if not isinstance(choice, dict):
            last_error = f"{endpoint}: unexpected response format"
            continue

        message = choice.get("message")
        if isinstance(message, dict) and message.get("content"):
            endpoint_meta["response_model"] = _as_str(response.get("model"))
            usage = response.get("usage")
            if isinstance(usage, dict):
                endpoint_meta["usage"] = usage
            return str(message["content"]), endpoint_meta

        if choice.get("text"):
            endpoint_meta["response_model"] = _as_str(response.get("model"))
            usage = response.get("usage")
            if isinstance(usage, dict):
                endpoint_meta["usage"] = usage
            return str(choice["text"]), endpoint_meta

        last_error = f"{endpoint}: unexpected response format"

    if last_error is None:
        last_error = "no matching OpenAI-compatible endpoint succeeded"
    raise RuntimeError(last_error)


def _build_aggregate_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_model: dict[str, dict[str, Any]] = {}
    by_case: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for result in results:
        model = _model_key(result)
        bucket = by_model.setdefault(
            model,
            {
                "elapsed_sec": [],
                "report_chars": [],
                "status_counts": defaultdict(int),
                "validation_status_counts": defaultdict(int),
            },
        )
        status = _as_str(result.get("status")) or "unknown"
        validation_status = _as_str(result.get("validation_status")) or "not_run"
        bucket["status_counts"][status] += 1
        bucket["validation_status_counts"][validation_status] += 1
        if status == "ok" and isinstance(result.get("elapsed_sec"), (int, float)):
            bucket["elapsed_sec"].append(float(result["elapsed_sec"]))
        if status == "ok" and isinstance(result.get("report_chars"), (int, float)):
            bucket["report_chars"].append(float(result["report_chars"]))

        case = _as_str(result.get("case_name")) or _as_str(result.get("case"))
        if case:
            by_case[case][model].append(result)

    by_model_metrics: dict[str, dict[str, Any]] = {}
    for model_name, bucket in by_model.items():
        elapsed = bucket["elapsed_sec"]
        report_chars = bucket["report_chars"]
        by_model_metrics[model_name] = {
            "runs": sum(bucket["status_counts"].values()),
            "ok": bucket["status_counts"].get("ok", 0),
            "pass_rate": bucket["status_counts"].get("ok", 0)
            / max(1, sum(bucket["status_counts"].values())),
            "mean_elapsed_sec": _mean(elapsed),
            "median_elapsed_sec": _median(elapsed),
            "p95_elapsed_sec": _percentile(elapsed, 95.0),
            "stddev_elapsed_sec": _stddev(elapsed),
            "min_elapsed_sec": min(elapsed) if elapsed else None,
            "max_elapsed_sec": max(elapsed) if elapsed else None,
            "mean_report_chars": _mean(report_chars),
            "median_report_chars": _median(report_chars),
            "min_report_chars": min(report_chars) if report_chars else None,
            "max_report_chars": max(report_chars) if report_chars else None,
            "validation_status_counts": dict(bucket["validation_status_counts"]),
            "status_counts": dict(bucket["status_counts"]),
        }

    by_case_metrics: dict[str, Any] = {}
    for case_name, model_runs in by_case.items():
        model_metrics: dict[str, Any] = {}
        for model_name, runs in model_runs.items():
            elapsed = [
                float(run.get("elapsed_sec"))
                for run in runs
                if run.get("status") == "ok" and isinstance(run.get("elapsed_sec"), (int, float))
            ]
            report_chars = [
                float(run.get("report_chars"))
                for run in runs
                if run.get("status") == "ok" and isinstance(run.get("report_chars"), (int, float))
            ]
            status_counts = defaultdict(int)
            for run in runs:
                status_counts[_as_str(run.get("status")) or "unknown"] += 1
            model_metrics[model_name] = {
                "runs": len(runs),
                "ok": status_counts.get("ok", 0),
                "pass_rate": status_counts.get("ok", 0) / max(1, len(runs)),
                "mean_elapsed_sec": _mean(elapsed),
                "median_elapsed_sec": _median(elapsed),
                "p95_elapsed_sec": _percentile(elapsed, 95.0),
                "stddev_elapsed_sec": _stddev(elapsed),
                "min_elapsed_sec": min(elapsed) if elapsed else None,
                "max_elapsed_sec": max(elapsed) if elapsed else None,
                "mean_report_chars": _mean(report_chars),
                "min_report_chars": min(report_chars) if report_chars else None,
                "max_report_chars": max(report_chars) if report_chars else None,
                "status_counts": dict(status_counts),
                "status_consistency": len(status_counts) == 1,
            }
        by_case_metrics[case_name] = {"models": model_metrics}

    pair_benchmark = _build_pair_benchmark(by_model_metrics=by_model_metrics, by_case=by_case)

    return {
        "by_model": by_model_metrics,
        "by_case": by_case_metrics,
        "pair_benchmark": pair_benchmark,
    }


def _build_pair_benchmark(
    *,
    by_model_metrics: dict[str, dict[str, Any]],
    by_case: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    latency_pairs: dict[str, Any] = {}
    for baseline_model, comparison_model in combinations(sorted(by_model_metrics), 2):
        baseline_mean = by_model_metrics[baseline_model].get("mean_elapsed_sec")
        comparison_mean = by_model_metrics[comparison_model].get("mean_elapsed_sec")
        pair_metrics: dict[str, Any] = {
            "baseline_model": baseline_model,
            "comparison_model": comparison_model,
            "mean_latency_baseline_sec": baseline_mean,
            "mean_latency_comparison_sec": comparison_mean,
            "mean_chars_baseline": by_model_metrics[baseline_model].get("mean_report_chars"),
            "mean_chars_comparison": by_model_metrics[comparison_model].get("mean_report_chars"),
        }
        if (
            isinstance(baseline_mean, (int, float))
            and isinstance(comparison_mean, (int, float))
            and comparison_mean > 0
        ):
            pair_metrics["ratio_of_mean_latencies"] = baseline_mean / comparison_mean

        per_case_ratios = []
        for model_runs in by_case.values():
            baseline_elapsed = [
                float(run["elapsed_sec"])
                for run in model_runs.get(baseline_model, [])
                if run.get("status") == "ok" and isinstance(run.get("elapsed_sec"), (int, float))
            ]
            comparison_elapsed = [
                float(run["elapsed_sec"])
                for run in model_runs.get(comparison_model, [])
                if run.get("status") == "ok" and isinstance(run.get("elapsed_sec"), (int, float))
            ]
            baseline_median = _median(baseline_elapsed)
            comparison_median = _median(comparison_elapsed)
            if (
                baseline_median is not None
                and comparison_median is not None
                and comparison_median > 0
            ):
                per_case_ratios.append(baseline_median / comparison_median)
        if per_case_ratios:
            pair_metrics["mean_per_case_latency_ratio"] = _mean(per_case_ratios)

        latency_pairs[f"{baseline_model} :: {comparison_model}"] = pair_metrics

    return {
        "latency_pairs": latency_pairs,
        "mean_per_model_output_chars": {
            model: bucket.get("mean_report_chars") for model, bucket in by_model_metrics.items()
        },
    }


def run_case_model(
    *,
    case_dir: Path,
    model: str,
    run_index: int,
    facts_text: str,
    facts_sha256: str,
    facts_path: Path,
    provider: str,
    mode: str,
    out_dir: Path,
    validation_mode: str,
    args: argparse.Namespace,
    llm_api_base_url: str,
    llm_api_key: str,
) -> dict[str, Any]:
    prompt = report_writer.build_prompt(
        facts_text=facts_text,
        facts_path=facts_path,
        facts_sha256=facts_sha256,
        model=model,
        language="ru",
        mode=mode,
    )

    started = time.time()
    generated_body, generation_meta = stream_or_blocking_prompt(
        prompt=prompt,
        provider=provider,
        model=model,
        args=args,
        llm_api_base_url=llm_api_base_url,
        llm_api_key=llm_api_key,
    )
    elapsed = round(time.time() - started, 2)

    narrative_text = report_writer.normalize_report_text(
        report_writer.report_header(facts_path, facts_sha256, model) + generated_body,
        facts_text=facts_text,
        mode=mode,
    )

    resolved_model = _as_str(generation_meta.get("response_model")) or model
    elapsed_tokens = generation_meta.get("usage", {})
    tokens_total: float | None = None
    if isinstance(elapsed_tokens, dict):
        raw_tokens = elapsed_tokens.get("total_tokens")
        if isinstance(raw_tokens, (int, float)):
            tokens_total = float(raw_tokens)
    tokens_per_sec = tokens_total / elapsed if elapsed > 0 and tokens_total is not None else None

    common_fields = {
        "requested_model": model,
        "resolved_model_id": resolved_model,
        "facts_filename": facts_path.name,
        "response_model": _as_str(generation_meta.get("response_model")) or resolved_model,
        "run_index": run_index,
        "case_name": _case_label(case_dir),
    }
    if tokens_per_sec is not None:
        common_fields["tokens_per_sec"] = tokens_per_sec

    validation_errors: list[str] = []
    if validation_mode != "off":
        validation_errors = report_writer.validate_report_for_mode(
            narrative_text,
            facts_text=facts_text,
            validation_mode=validation_mode,
        )
        if validation_errors:
            report_writer.write_failed_report_to_partial(
                out_dir
                / (
                    f"report_{mode}_{provider}_{safe_slug(model)}_{_case_file_label(case_dir)}_run{run_index:02d}.md"
                ),
                narrative_text,
            )
            return {
                "requested_model": model,
                "provider": provider,
                "response_model": _as_str(generation_meta.get("response_model")) or resolved_model,
                "status": "validation_failed",
                "validation_status": "failed",
                "elapsed_sec": elapsed,
                "report_chars": len(narrative_text),
                "error_summary": _safe_error_summary("; ".join(validation_errors)),
                **common_fields,
            }

    final_report = report_writer.append_analyzer_facts_appendix(narrative_text, facts_text)
    if validation_mode != "off":
        final_validation_errors = report_writer.validate_report_for_mode(
            final_report,
            facts_text=facts_text,
            validation_mode=validation_mode,
        )
        if final_validation_errors:
            report_writer.write_failed_report_to_partial(
                out_dir
                / (
                    f"report_{mode}_{provider}_{safe_slug(model)}_{_case_file_label(case_dir)}_run{run_index:02d}.md"
                ),
                final_report,
            )
            return {
                "requested_model": model,
                "provider": provider,
                "response_model": _as_str(generation_meta.get("response_model")) or resolved_model,
                "status": "validation_failed",
                "validation_status": "failed",
                "elapsed_sec": elapsed,
                "report_chars": len(final_report),
                "error_summary": _safe_error_summary("; ".join(final_validation_errors)),
                **common_fields,
            }

    report_path = (
        out_dir
        / f"report_{mode}_{provider}_{safe_slug(model)}_{_case_file_label(case_dir)}_run{run_index:02d}.md"
    )
    report_path.write_text(final_report, encoding="utf-8")
    return {
        "requested_model": model,
        "provider": provider,
        "response_model": _as_str(generation_meta.get("response_model")) or resolved_model,
        "status": "ok",
        "validation_status": "passed",
        "elapsed_sec": elapsed,
        "report_chars": len(final_report),
        "error_summary": "",
        **common_fields,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    llm_api_base_url = ""
    llm_api_key = ""
    if args.provider == "openai_compatible":
        try:
            llm_api_base_url, llm_api_key = resolve_llm_api_creds(args)
        except Exception as exc:
            print(f"{PROGRESS_PREFIX} ERROR: {exc}", file=sys.stderr)
            return 2

        if args.llm_list_models:
            try:
                for model in sorted(extract_model_list(llm_api_base_url, llm_api_key)):
                    print(model)
            except Exception as exc:
                print(f"{PROGRESS_PREFIX} ERROR listing LLM API models: {exc}", file=sys.stderr)
                return 2
            return 0

    if not args.models:
        print(f"{PROGRESS_PREFIX} ERROR: provide at least one --model value.", file=sys.stderr)
        return 2

    if args.repeat < 1:
        print(f"{PROGRESS_PREFIX} ERROR: --repeat must be >= 1", file=sys.stderr)
        return 2

    if args.parallel_workers < 1:
        print(f"{PROGRESS_PREFIX} ERROR: --parallel-workers must be >= 1", file=sys.stderr)
        return 2

    review_template_path: Path | None
    if args.review_template == "off":
        review_template_path = None
    elif args.review_template:
        review_template_path = Path(args.review_template).expanduser()
    else:
        review_template_path = args.out_dir / "review_template.csv"

    if args.provider == "ollama" and args.parallel_workers > 1 and args.stop_other_models:
        print(
            f"{PROGRESS_PREFIX} ERROR: --stop-other-models cannot be used with --parallel-workers > 1",
            file=sys.stderr,
        )
        return 2

    case_root = Path(args.cases_root).expanduser() if args.cases_root else None
    case_refs: list[str] = []
    if args.cases_file:
        try:
            case_refs.extend(_read_case_list_file(Path(args.cases_file).expanduser()))
        except Exception as exc:
            print(f"{PROGRESS_PREFIX} ERROR: failed to read --cases-file: {exc}", file=sys.stderr)
            return 2

    case_refs.extend(args.cases)
    if not case_refs:
        print(f"{PROGRESS_PREFIX} ERROR: provide at least one case path/id.", file=sys.stderr)
        return 2

    resolved_cases: list[Path] = []
    for raw_case in case_refs:
        try:
            case_dir = _resolve_case_reference(raw_case, case_root=case_root)
        except Exception as exc:
            print(
                f"{PROGRESS_PREFIX} ERROR: invalid case reference {raw_case!r}: {exc}",
                file=sys.stderr,
            )
            return 2
        if not case_dir.exists() or not case_dir.is_dir():
            print(f"{PROGRESS_PREFIX} ERROR: missing case directory: {case_dir}", file=sys.stderr)
            return 2
        resolved_cases.append(case_dir)

    # keep source order and deduplicate identical case references
    unique_cases: list[Path] = []
    seen = set[Path]()
    for case_dir in resolved_cases:
        if case_dir in seen:
            continue
        seen.add(case_dir)
        unique_cases.append(case_dir)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"{PROGRESS_PREFIX} provider: {args.provider}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} mode: {args.mode}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} validation: {args.validation_mode}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} out_dir: {args.out_dir}", file=sys.stderr)

    prepared_cases: dict[Path, tuple[Path, str, str]] = {}
    skipped_failures: list[dict[str, Any]] = []
    for case_dir in unique_cases:
        try:
            facts_path = report_writer.resolve_case_file(case_dir, args.facts)
            facts_text, facts_sha256 = report_writer.read_required_facts(facts_path)
            prepared_cases[case_dir] = (facts_path, facts_text, facts_sha256)
        except Exception as exc:
            print(
                f"{PROGRESS_PREFIX} ERROR: unable to prepare facts for {case_dir}: {exc}",
                file=sys.stderr,
            )
            for model in args.models:
                for repeat_index in range(1, args.repeat + 1):
                    skipped_failures.append(
                        {
                            "provider": args.provider,
                            "requested_model": model,
                            "resolved_model_id": None,
                            "response_model": None,
                            "case_name": _case_label(case_dir),
                            "facts_filename": args.facts,
                            "status": "read_facts_failed",
                            "validation_status": "failed",
                            "elapsed_sec": 0.0,
                            "report_chars": 0,
                            "error_summary": _safe_error_summary(exc),
                            "run_index": repeat_index,
                        }
                    )

    def _run_single_task(task: tuple[Path, str, int]) -> dict[str, Any]:
        case_dir, model, repeat_index = task
        facts_path, facts_text, facts_sha256 = prepared_cases[case_dir]

        print(
            f"{PROGRESS_PREFIX} running model={model!r} case={case_dir.name} repeat={repeat_index}",
            file=sys.stderr,
        )

        if args.dry_prompt:
            prompt = report_writer.build_prompt(
                facts_text=facts_text,
                facts_path=facts_path,
                facts_sha256=facts_sha256,
                model=model,
                language="ru",
                mode=args.mode,
            )
            print("---")
            print(f"provider={args.provider}")
            print(f"case={case_dir.name}")
            print(f"model={model}")
            print(f"run_index={repeat_index}")
            print(prompt)
            return {
                "provider": args.provider,
                "requested_model": model,
                "resolved_model_id": None,
                "response_model": None,
                "case_name": _case_label(case_dir),
                "facts_filename": facts_path.name,
                "status": "dry_prompt",
                "validation_status": "not_run",
                "elapsed_sec": 0.0,
                "report_chars": len(prompt),
                "error_summary": "",
                "run_index": repeat_index,
            }

        try:
            return run_case_model(
                case_dir=case_dir,
                model=model,
                run_index=repeat_index,
                facts_text=facts_text,
                facts_sha256=facts_sha256,
                facts_path=facts_path,
                provider=args.provider,
                mode=args.mode,
                out_dir=args.out_dir,
                validation_mode=args.validation_mode,
                args=args,
                llm_api_base_url=llm_api_base_url,
                llm_api_key=llm_api_key,
            )
        except Exception as exc:  # pragma: no cover - passthrough for operational diagnostics
            return {
                "provider": args.provider,
                "requested_model": model,
                "resolved_model_id": None,
                "response_model": None,
                "facts_filename": facts_path.name,
                "status": "error",
                "validation_status": "failed",
                "elapsed_sec": 0.0,
                "report_chars": 0,
                "error_summary": _safe_error_summary(exc),
                "run_index": repeat_index,
                "case_name": _case_label(case_dir),
            }

    tasks: list[tuple[Path, str, int]] = []
    for case_dir in prepared_cases:
        for model in args.models:
            for repeat_index in range(1, args.repeat + 1):
                tasks.append((case_dir, model, repeat_index))

    results: list[dict[str, Any]] = []
    if tasks:
        if args.parallel_workers == 1:
            for task in tasks:
                results.append(_run_single_task(task))
        else:
            with ThreadPoolExecutor(max_workers=args.parallel_workers) as executor:
                future_to_task = {executor.submit(_run_single_task, task): task for task in tasks}
                for future in as_completed(future_to_task):
                    try:
                        result = future.result()
                    except Exception as exc:  # pragma: no cover - executor safety guard
                        task = future_to_task[future]
                        case_dir, model, repeat_index = task
                        facts_path, _, _ = prepared_cases[case_dir]
                        print(
                            f"{PROGRESS_PREFIX} ERROR: model={model!r} case={case_dir.name} repeat={repeat_index}: {exc}",
                            file=sys.stderr,
                        )
                        results.append(
                            {
                                "provider": args.provider,
                                "requested_model": model,
                                "resolved_model_id": None,
                                "response_model": None,
                                "facts_filename": facts_path.name,
                                "status": "error",
                                "validation_status": "failed",
                                "elapsed_sec": 0.0,
                                "report_chars": 0,
                                "error_summary": _safe_error_summary(exc),
                                "run_index": repeat_index,
                                "case_name": _case_label(case_dir),
                            }
                        )
                    else:
                        results.append(result)

    results.extend(skipped_failures)

    generated = sum(1 for result in results if result.get("status") == "ok")
    failed = sum(1 for result in results if result.get("status") not in {"ok", "dry_prompt"})

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "provider": args.provider,
        "mode": args.mode,
        "validation_mode": args.validation_mode,
        "models": args.models,
        "facts_file": args.facts,
        "results": results,
        "metrics": {
            "generated": generated,
            "failed": failed,
            "total": len(results),
        },
        "aggregates": _build_aggregate_metrics(results),
    }
    summary_path = args.out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    if review_template_path is not None:
        _write_review_template_csv(
            path=review_template_path,
            results=results,
            validation_mode=args.validation_mode,
        )

    print(f"{PROGRESS_PREFIX} summary: {summary_path}")
    if review_template_path is not None:
        print(f"{PROGRESS_PREFIX} review template: {review_template_path}")
    print(
        f"{PROGRESS_PREFIX} generated: {generated}, failed: {failed}, total: {len(results)}",
        file=sys.stderr,
    )
    if failed:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
