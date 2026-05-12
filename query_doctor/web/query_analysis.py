"""Single-query collection and analysis workflow for the web UI."""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Callable

from query_doctor.cli import collect_cm_profiles as cm_collector
from query_doctor.cli.commands import command_prefix

from query_doctor.web.case_files import (
    build_query_id_summary_case,
    case_relative_file_path,
    ensure_complete_existing_case,
    expected_case_dir_for_query,
    parse_facts_summary,
    parse_output_case_dir,
    remove_path,
    replace_case_dir_after_success,
    resolve_under_repo,
)
from query_doctor.web.command_builders import (
    append_web_cm_args,
    build_analyzer_command,
    build_query_id_analyzer_command,
    build_report_command,
)
from query_doctor.web.config import load_web_local_config, optional_config_string
from query_doctor.web.job_workers import REPORT_VALIDATION_EXIT_CODE, REPORT_VALIDATION_FAILURE_MESSAGE
from query_doctor.web.models import WebError, WebQueryAnalysisResult, WebResult, WebSettings
from query_doctor.web.subprocesses import (
    CancelCheck,
    Runner,
    effective_subprocess_env,
    has_cm_credentials,
    run_subprocess,
    subprocess_failure_message,
)


MISSING_CM_CREDENTIALS_MESSAGE = (
    "CM credentials were not found in the web server environment. Start the "
    "server from a terminal where CM_USERNAME/CM_PASSWORD or CM_TOKEN is set."
)
MISSING_IMPALA_PROFILE_SOURCE_MESSAGE = (
    "Impala profile source is not configured for this web session. Add "
    "impala_profile_hosts to the local config or switch query_profile_source back to cm."
)
ProgressFunc = Callable[[int], None]


def validate_query_id(query_id: str) -> str:
    try:
        return cm_collector.validate_cm_query_id_path_segment(query_id)
    except cm_collector.CMAdapterError as exc:
        raise WebError(str(exc)) from exc


def run_web_analysis(
    query_id: str,
    report_mode: str,
    redact_identifiers: bool,
    settings: WebSettings,
    *,
    runner: Runner = subprocess.run,
    progress: ProgressFunc | None = None,
    cancel_check: CancelCheck | None = None,
) -> WebResult:
    update_progress(progress, 0)
    validated_query_id = validate_query_id(query_id)
    if report_mode not in {"admin", "user"}:
        raise WebError("Report mode must be admin or user.")
    subprocess_env = effective_subprocess_env(settings)

    update_progress(progress, 1)
    expected_case_dir = expected_case_dir_for_query(validated_query_id, settings)
    if expected_case_dir.exists():
        ensure_complete_existing_case(expected_case_dir)
        case_dir = expected_case_dir
        case_source = "reused existing local case"
    else:
        case_dir = collect_case(
            validated_query_id,
            expected_case_dir,
            redact_identifiers,
            settings,
            runner,
            env=subprocess_env,
            cancel_check=cancel_check,
        )
        case_source = "collected now"

    report_name = f"report_{report_mode}.md"
    update_progress(progress, 2)
    analyzed = run_subprocess(
        build_analyzer_command(case_dir, settings),
        cwd=settings.repo_dir,
        timeout_sec=settings.timeout_sec,
        runner=runner,
        env=subprocess_env,
        cancel_check=cancel_check,
    )
    if cancel_check is not None and cancel_check():
        raise WebError("Analysis was stopped by the user.")
    if analyzed.returncode != 0:
        raise WebError(subprocess_failure_message("Query Doctor analyzer", analyzed))

    update_progress(progress, 3)
    reported = run_subprocess(
        build_report_command(case_dir, report_mode, report_name, settings),
        cwd=settings.repo_dir,
        timeout_sec=settings.timeout_sec,
        runner=runner,
        env=subprocess_env,
        cancel_check=cancel_check,
    )
    if cancel_check is not None and cancel_check():
        raise WebError("Analysis was stopped by the user.")
    update_progress(progress, 4)
    report_retry = False
    if reported.returncode == REPORT_VALIDATION_EXIT_CODE:
        retried = run_subprocess(
            build_report_command(case_dir, report_mode, report_name, settings),
            cwd=settings.repo_dir,
            timeout_sec=settings.timeout_sec,
            runner=runner,
            env=subprocess_env,
            cancel_check=cancel_check,
        )
        if cancel_check is not None and cancel_check():
            raise WebError("Analysis was stopped by the user.")
        if retried.returncode == REPORT_VALIDATION_EXIT_CODE:
            raise WebError(REPORT_VALIDATION_FAILURE_MESSAGE)
        if retried.returncode != 0:
            raise WebError(subprocess_failure_message("Query Doctor report retry", retried))
        report_retry = True
    elif reported.returncode != 0:
        raise WebError(subprocess_failure_message("Query Doctor report generation", reported))

    facts_path = case_relative_file_path(case_dir, "analysis_facts.md")
    report_path = case_relative_file_path(case_dir, report_name)
    if facts_path is None or report_path is None:
        raise WebError("Analyzer/report output was not created.")

    facts_text = facts_path.read_text(encoding="utf-8", errors="replace")
    report_text = report_path.read_text(encoding="utf-8", errors="replace")
    facts = parse_facts_summary(facts_text)
    update_progress(progress, 5)
    return WebResult(
        query_id=validated_query_id,
        case_dir=case_dir,
        case_source=case_source,
        report_mode=report_mode,
        parsed_operators=facts.get("Parsed operators", "unknown"),
        cardinality_anomalies=facts.get("Cardinality anomalies", "unknown"),
        memory_anomalies=facts.get("Memory anomalies", "unknown"),
        report_text=report_text,
        report_retry=report_retry,
    )


def run_query_id_analysis(
    query_id: str,
    report_mode: str,
    redact_identifiers: bool,
    settings: WebSettings,
    *,
    runner: Runner = subprocess.run,
    progress: ProgressFunc | None = None,
    cancel_check: CancelCheck | None = None,
) -> WebQueryAnalysisResult:
    del report_mode
    update_progress(progress, 0)
    validated_query_id = validate_query_id(query_id)
    subprocess_env = effective_subprocess_env(settings)

    update_progress(progress, 1)
    expected_case_dir = expected_case_dir_for_query(validated_query_id, settings)
    case_dir = collect_analyze_and_replace_query_case(
        validated_query_id,
        expected_case_dir,
        redact_identifiers,
        settings,
        runner,
        subprocess_env,
        progress=progress,
        cancel_check=cancel_check,
    )
    if cancel_check is not None and cancel_check():
        raise WebError("Analysis was stopped by the user.")
    collection_status = "ok"
    analysis_status = "ok"

    update_progress(progress, 3)
    summary_case = build_query_id_summary_case(
        validated_query_id,
        case_dir,
        collection_status=collection_status,
        analysis_status=analysis_status,
    )
    update_progress(progress, 4)
    return WebQueryAnalysisResult(query_id=validated_query_id, case=summary_case)


def update_progress(progress: ProgressFunc | None, stage_index: int) -> None:
    if progress is not None:
        progress(stage_index)


def collect_case(
    validated_query_id: str,
    expected_case_dir: Path,
    redact_identifiers: bool,
    settings: WebSettings,
    runner: Runner,
    env: dict[str, str] | None = None,
    out_dir: Path | None = None,
    cancel_check: CancelCheck | None = None,
) -> Path:
    config_username = settings.cm_username
    try:
        config_username = config_username or optional_config_string(
            load_web_local_config(settings.config, cwd=Path.cwd()), "username"
        )
    except cm_collector.ConfigError:
        config_username = config_username or None
    collection_out_dir = out_dir if out_dir is not None else settings.corpus_dir
    if settings.query_profile_source == "impala":
        if not settings.impala_profile_hosts:
            raise WebError(MISSING_IMPALA_PROFILE_SOURCE_MESSAGE)
        collector_stage = "Impala daemon single-query profile collection"
        collector_cmd = command_prefix(settings.repo_dir, "collect_impala_profile") + [
            "--query-id",
            validated_query_id,
            "--redact",
            "--out",
            str(collection_out_dir),
            "--port",
            str(settings.impala_profile_port),
            "--scheme",
            settings.impala_profile_scheme,
            "--timeout-sec",
            str(settings.impala_profile_timeout_sec),
        ]
        for host in settings.impala_profile_hosts:
            collector_cmd.extend(["--host", host])
        if settings.max_profile_bytes is not None:
            collector_cmd.extend(["--max-profile-bytes", str(settings.max_profile_bytes)])
        if settings.collect_prometheus_timeseries:
            if not settings.prometheus_url:
                raise WebError("Prometheus runtime metrics are enabled but prometheus_url is not configured.")
            collector_cmd.extend(
                [
                    "--prometheus-url",
                    settings.prometheus_url,
                    "--collect-prometheus-timeseries",
                    "--prometheus-metrics-profile",
                    settings.prometheus_metrics_profile,
                    "--prometheus-step-sec",
                    str(settings.prometheus_step_sec),
                    "--prometheus-timeseries-padding-sec",
                    str(settings.prometheus_timeseries_padding_sec),
                ]
            )
        if redact_identifiers:
            collector_cmd.append("--redact-identifiers")
    else:
        if not has_cm_credentials(username=config_username):
            raise WebError(MISSING_CM_CREDENTIALS_MESSAGE)
        collector_stage = "CM single-query collection"
        collector_cmd = command_prefix(settings.repo_dir, "collect_cm") + [
            "--config",
            str(settings.config),
            "--query-id",
            validated_query_id,
            "--limit",
            "1",
            "--redact",
            "--out",
            str(collection_out_dir),
        ]
        append_web_cm_args(collector_cmd, settings)
        if redact_identifiers:
            collector_cmd.append("--redact-identifiers")
        if settings.max_profile_bytes is not None:
            collector_cmd.extend(["--max-profile-bytes", str(settings.max_profile_bytes)])

    collected = run_subprocess(
        collector_cmd,
        cwd=settings.repo_dir,
        timeout_sec=settings.timeout_sec,
        runner=runner,
        env=effective_subprocess_env(settings) if env is None else env,
        cancel_check=cancel_check,
    )
    if cancel_check is not None and cancel_check():
        raise WebError("Analysis was stopped by the user.")
    if collected.returncode != 0:
        raise WebError(subprocess_failure_message(collector_stage, collected))

    case_dir = parse_output_case_dir(collected.stdout)
    if not case_dir.is_absolute():
        case_dir = (settings.repo_dir / case_dir).resolve()
    expected_corpus_dir = resolve_under_repo(settings.repo_dir, collection_out_dir)
    try:
        case_dir.relative_to(expected_corpus_dir)
    except ValueError as exc:
        raise WebError("Collector returned a case directory outside the web corpus directory.") from exc
    if case_dir != expected_case_dir:
        raise WebError("Collector returned a case directory that does not match the requested query id.")
    if not case_dir.exists():
        raise WebError("Collector did not create the expected case directory.")
    return case_dir


def collect_analyze_and_replace_query_case(
    validated_query_id: str,
    expected_case_dir: Path,
    redact_identifiers: bool,
    settings: WebSettings,
    runner: Runner,
    subprocess_env: dict[str, str],
    progress: ProgressFunc | None = None,
    cancel_check: CancelCheck | None = None,
) -> Path:
    corpus_dir = resolve_under_repo(settings.repo_dir, settings.corpus_dir)
    staging_root = corpus_dir / f".query-refresh-{uuid.uuid4().hex}"
    staging_case_dir = staging_root / expected_case_dir.name
    try:
        case_dir = collect_case(
            validated_query_id,
            staging_case_dir,
            redact_identifiers,
            settings,
            runner,
            env=subprocess_env,
            out_dir=staging_root,
            cancel_check=cancel_check,
        )
        update_progress(progress, 2)
        analyzed = run_subprocess(
            build_query_id_analyzer_command(case_dir, settings),
            cwd=settings.repo_dir,
            timeout_sec=settings.timeout_sec,
            runner=runner,
            env=subprocess_env,
            cancel_check=cancel_check,
        )
        if cancel_check is not None and cancel_check():
            raise WebError("Analysis was stopped by the user.")
        if analyzed.returncode != 0:
            raise WebError(subprocess_failure_message("Query Doctor analyzer", analyzed))
        return replace_case_dir_after_success(case_dir, expected_case_dir)
    finally:
        if staging_root.exists():
            remove_path(staging_root)
