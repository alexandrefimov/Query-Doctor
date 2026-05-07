"""Recent batch case collection and analyzer execution."""

from __future__ import annotations

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path

from query_doctor.cli.commands import command_prefix
from query_doctor.recent.batch_config import elapsed_seconds, format_seconds
from query_doctor.recent.batch_models import BatchConfig, CaseResult
from query_doctor.recent.batch_scoring import inspect_case_outputs, score_case
from query_doctor.recent.batch_summary import batch_ranking_key
from query_doctor.recent.command_args import append_cm_config_args, append_metadata_args
from query_doctor.recent.metadata_refresh import (
    mark_metadata_not_requested,
    metadata_refresh_skip_reason,
    rank_cases_for_metadata,
    select_metadata_refresh_candidates,
)
from query_doctor.recent.progress import ProgressWriter


def collect_case_profile(
    config: BatchConfig,
    case: CaseResult,
    *,
    env: dict[str, str],
    repo_root: Path,
) -> None:
    started = time.monotonic()
    try:
        case.wrapper_dir.mkdir(parents=True, exist_ok=True)
        cmd = command_prefix(repo_root, "collect_cm") + [
            "--query-id",
            case.query_id,
            "--out",
            str(case.wrapper_dir),
            "--redact",
            "--limit",
            "1",
            "--max-profile-bytes",
            str(config.max_profile_bytes),
        ]
        if config.collect_cm_timeseries:
            cmd.extend(
                [
                    "--collect-cm-timeseries",
                    "--cm-metrics-profile",
                    config.cm_metrics_profile,
                    "--cm-timeseries-padding-sec",
                    str(config.cm_timeseries_padding_sec),
                    "--max-timeseries-bytes",
                    str(config.max_timeseries_bytes),
                    "--max-timeseries-points",
                    str(config.max_timeseries_points),
                ]
            )
        else:
            cmd.append("--no-collect-cm-timeseries")
        append_cm_config_args(cmd, config)
        result = run_subprocess(cmd, cwd=repo_root, env=env)
        if result.returncode != 0:
            case.collection_status = "failed"
            case.failure_category = "profile_collection_failed"
            return
        profile_paths = sorted(case.wrapper_dir.rglob("profile_digest.md"))
        if not profile_paths:
            case.collection_status = "failed"
            case.failure_category = "profile_digest_missing"
            return
        case.collection_status = "ok"
        case.actual_case_dir = profile_paths[0].parent
    finally:
        case.cm_collect_seconds = elapsed_seconds(started)


def process_cases(
    config: BatchConfig,
    cases: list[CaseResult],
    *,
    env: dict[str, str],
    repo_root: Path,
    progress: ProgressWriter,
) -> None:
    collect_cases(config, cases, env=env, repo_root=repo_root, progress=progress)
    analyze_cases(config, cases, env=env, repo_root=repo_root, progress=progress)


def collect_cases(
    config: BatchConfig,
    cases: list[CaseResult],
    *,
    env: dict[str, str],
    repo_root: Path,
    progress: ProgressWriter,
) -> None:
    if config.cm_jobs == 1:
        for case in cases:
            collect_case_for_batch(config, case, env=env, repo_root=repo_root, progress=progress)
        return

    with ThreadPoolExecutor(max_workers=config.cm_jobs) as executor:
        futures = [
            executor.submit(collect_case_for_batch, config, case, env=env, repo_root=repo_root, progress=progress)
            for case in cases
        ]
        for future in as_completed(futures):
            future.result()


def analyze_cases(
    config: BatchConfig,
    cases: list[CaseResult],
    *,
    env: dict[str, str],
    repo_root: Path,
    progress: ProgressWriter,
) -> None:
    if config.jobs == 1:
        for case in cases:
            analyze_case_for_batch(config, case, env=env, repo_root=repo_root, progress=progress)
            print_case_progress(case)
        return

    with ThreadPoolExecutor(max_workers=config.jobs) as executor:
        futures = [
            executor.submit(analyze_case_for_batch, config, case, env=env, repo_root=repo_root, progress=progress)
            for case in cases
        ]
        for future in as_completed(futures):
            print_case_progress(future.result())


def collect_case_for_batch(
    config: BatchConfig,
    case: CaseResult,
    *,
    env: dict[str, str],
    repo_root: Path,
    progress: ProgressWriter,
) -> CaseResult:
    case_id = f"case-{case.index:03d}"
    progress.emit(stage="case", case_id=case_id, status="collection_started")
    collect_case_profile(config, case, env=env, repo_root=repo_root)
    if case.collection_status != "ok":
        progress.emit(
            stage="case",
            case_id=case_id,
            status="failed",
            phase="collection",
            seconds=case.cm_collect_seconds,
        )
        return case
    progress.emit(stage="case", case_id=case_id, status="collection_done", seconds=case.cm_collect_seconds)
    return case


def analyze_case_for_batch(
    config: BatchConfig,
    case: CaseResult,
    *,
    env: dict[str, str],
    repo_root: Path,
    progress: ProgressWriter,
) -> CaseResult:
    case_id = f"case-{case.index:03d}"
    if case.collection_status != "ok":
        return case
    progress.emit(stage="case", case_id=case_id, status="analysis_started")
    run_analysis_pass(config, case, env=env, repo_root=repo_root, metadata_mode="off")
    if case.analysis_status != "ok":
        progress.emit(
            stage="case",
            case_id=case_id,
            status="failed",
            phase="analysis",
            seconds=case.analysis_seconds,
        )
        return case
    if case.analysis_status == "ok":
        score_case(case)
        progress.emit(
            stage="case",
            case_id=case_id,
            status="analysis_done",
            seconds=case.analysis_seconds,
            score=case.score,
        )
    return case


def print_case_progress(case: CaseResult) -> None:
    print(
        f"[batch] case-{case.index:03d} collection: "
        f"{format_seconds(case.cm_collect_seconds)} ({case.collection_status})"
    )
    if case.analysis_seconds is not None:
        print(
            f"[batch] case-{case.index:03d} analyzer triage: "
            f"{format_seconds(case.analysis_seconds)} ({case.analysis_status})"
        )


def run_analysis_pass(
    config: BatchConfig,
    case: CaseResult,
    *,
    env: dict[str, str],
    repo_root: Path,
    metadata_mode: str | None = None,
) -> None:
    started = time.monotonic()
    if case.actual_case_dir is None:
        case.analysis_status = "failed"
        case.failure_category = "case_dir_missing"
        case.analysis_seconds = elapsed_seconds(started)
        return
    try:
        cmd = command_prefix(repo_root, "pipeline") + [
            str(case.actual_case_dir),
            "--stop-after-analysis",
            "--metadata-failure-policy",
            "continue",
        ]
        effective_metadata_mode = config.metadata_mode if metadata_mode is None else metadata_mode
        append_metadata_args(cmd, replace(config, metadata_mode=effective_metadata_mode))
        result = run_subprocess(cmd, cwd=repo_root, env=env)
        case.analysis_status = "ok" if result.returncode == 0 else "failed"
        if result.returncode != 0:
            case.failure_category = "analysis_or_metadata_failed"
        inspect_case_outputs(case)
        if case.analysis_status == "ok" and case.metadata_status == "failed":
            case.failure_category = "metadata_collection_failed"
    finally:
        case.analysis_seconds = elapsed_seconds(started)


def refresh_top_metadata(
    config: BatchConfig,
    cases: list[CaseResult],
    *,
    env: dict[str, str],
    repo_root: Path,
    progress: ProgressWriter,
) -> None:
    ranked = rank_cases_for_metadata(cases)
    skip_reason = metadata_refresh_skip_reason(config, ranked)
    if skip_reason is not None:
        mark_metadata_not_requested(ranked)
        progress.emit(stage="metadata_refresh", status="skipped", reason=skip_reason)
        return
    candidates = select_metadata_refresh_candidates(ranked, config.metadata_top_limit)
    if not candidates:
        mark_metadata_not_requested(ranked)
        progress.emit(stage="metadata_refresh", status="skipped", reason="no bad or suspicious cases")
        return
    progress.emit(stage="metadata_refresh", status="started", total=len(candidates), metadata_jobs=config.metadata_jobs)
    if config.metadata_jobs == 1:
        for case in candidates:
            refresh_case_metadata(config, case, env=env, repo_root=repo_root, progress=progress)
    else:
        with ThreadPoolExecutor(max_workers=config.metadata_jobs) as executor:
            futures = [
                executor.submit(refresh_case_metadata, config, case, env=env, repo_root=repo_root, progress=progress)
                for case in candidates
            ]
            for future in as_completed(futures):
                future.result()
    refreshed_ids = {id(case) for case in candidates}
    mark_metadata_not_requested([case for case in cases if case.analysis_status == "ok" and id(case) not in refreshed_ids])
    progress.emit(stage="metadata_refresh", status="done", total=len(candidates))


def refresh_case_metadata(
    config: BatchConfig,
    case: CaseResult,
    *,
    env: dict[str, str],
    repo_root: Path,
    progress: ProgressWriter,
) -> CaseResult:
    case_id = f"case-{case.index:03d}"
    progress.emit(stage="metadata_refresh", case_id=case_id, status="started", triage_rank=case.triage_rank)
    run_analysis_pass(config, case, env=env, repo_root=repo_root, metadata_mode=config.metadata_mode)
    case.metadata_refreshed = True
    if case.analysis_status == "ok":
        score_case(case)
        progress.emit(
            stage="metadata_refresh",
            case_id=case_id,
            status="done",
            metadata_status=case.metadata_status,
            score=case.score,
        )
    else:
        progress.emit(
            stage="metadata_refresh",
            case_id=case_id,
            status="failed",
            metadata_status=case.metadata_status,
        )
    return case


def run_top_reports(
    config: BatchConfig,
    cases: list[CaseResult],
    *,
    env: dict[str, str],
    repo_root: Path,
) -> None:
    if config.top_reports <= 0:
        return
    ranked = sorted(
        [case for case in cases if case.analysis_status == "ok" and case.score > 0 and case.actual_case_dir],
        key=batch_ranking_key,
    )
    for case in ranked[: config.top_reports]:
        assert case.actual_case_dir is not None
        started = time.monotonic()
        try:
            cmd = command_prefix(repo_root, "pipeline") + [
                str(case.actual_case_dir),
            ]
            append_metadata_args(cmd, config)
            result = run_subprocess(cmd, cwd=repo_root, env=env)
            diagnosis = case.actual_case_dir / "diagnosis.md"
            partial = case.actual_case_dir / "diagnosis.partial.md"
            case.report_generated = diagnosis.exists()
            if result.returncode == 0 and diagnosis.exists():
                case.report_validation_status = "passed"
            elif partial.exists():
                case.report_validation_status = "failed_partial_untrusted"
                case.failure_category = case.failure_category or "report_validation_failed"
            else:
                case.report_validation_status = "failed"
                case.failure_category = case.failure_category or "report_generation_failed"
        finally:
            case.report_seconds = elapsed_seconds(started)
            print(
                f"[batch] case-{case.index:03d} report: "
                f"{format_seconds(case.report_seconds)} ({case.report_validation_status})"
            )


def run_subprocess(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        shell=False,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
