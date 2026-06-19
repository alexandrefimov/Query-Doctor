"""Local manual-profile inbox helpers for Known Query ID analysis."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Callable

from query_doctor.cli import collect_cm_profiles as cm_collector
from query_doctor.cli.commands import command_prefix
from query_doctor.impala.metadata_workflow import METADATA_SOURCE_TABLES_ENV
from query_doctor.web.case_files import (
    parse_output_case_dir,
    remove_path,
    replace_case_dir_after_success,
    resolve_under_repo,
)
from query_doctor.web.models import WebError, WebSettings
from query_doctor.web.subprocesses import (
    CancelCheck,
    Runner,
    run_subprocess,
    subprocess_failure_web_error,
)


MANUAL_PROFILE_FILENAME_SUFFIXES = (".txt", ".profile", ".log", ".md", ".text", "")
MISSING_MANUAL_PROFILE_MESSAGE = (
    "No matching local exported profile was found for that Query ID. "
    "Place an exported Impala text profile in the configured manual profile directory "
    "using the Query ID slug as the file name: replace the ':' separator with '_' "
    "and use a text-profile suffix such as .txt."
)
ProgressFunc = Callable[[int], None]


def manual_profile_file_for_query(validated_query_id: str, settings: WebSettings) -> Path | None:
    manual_profile_dir = resolve_manual_profile_dir(settings)
    if manual_profile_dir is None:
        return None
    try:
        slug = cm_collector.safe_case_slug(validated_query_id)
    except cm_collector.OutputError as exc:
        raise WebError(
            "Query ID could not be mapped to a safe manual profile filename.",
            title="Manual profile Query ID was rejected",
            reason_code="impala.query_id_manual_profile_path_rejected",
            stage="Checking manual profile inbox",
            next_step="Paste one explicit Impala Query ID in the expected CM-safe format.",
        ) from exc
    seen: set[str] = set()
    for suffix in MANUAL_PROFILE_FILENAME_SUFFIXES:
        filename = f"{slug}{suffix}"
        if filename in seen:
            continue
        seen.add(filename)
        candidate = manual_profile_dir / filename
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(manual_profile_dir)
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    return None


def resolve_manual_profile_dir(settings: WebSettings) -> Path | None:
    if settings.manual_profile_dir is None:
        return None
    path = settings.manual_profile_dir.expanduser()
    if not path.is_absolute():
        path = settings.config.parent / path
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise WebError(
            "Configured manual profile directory is not available.",
            title="Manual profile directory is not available",
            reason_code="web.manual_profile_dir_unavailable",
            stage="Checking manual profile inbox",
            next_step="Fix manual_profile_dir or switch to live collection.",
        ) from exc
    if not resolved.is_dir():
        raise WebError(
            "Configured manual profile directory is not available.",
            title="Manual profile directory is not available",
            reason_code="web.manual_profile_dir_unavailable",
            stage="Checking manual profile inbox",
            next_step="Fix manual_profile_dir or switch to live collection.",
        )
    return resolved


def live_query_collection_configured(settings: WebSettings) -> bool:
    if settings.query_profile_source == "impala":
        return bool(settings.impala_profile_hosts)
    return bool(settings.cm_url and settings.cm_cluster and settings.cm_service)


def analyze_manual_profile_from_directory(
    validated_query_id: str,
    profile_text_path: Path,
    expected_case_dir: Path,
    redact_identifiers: bool,
    settings: WebSettings,
    runner: Runner,
    subprocess_env: dict[str, str],
    progress: ProgressFunc | None = None,
    cancel_check: CancelCheck | None = None,
    post_analyze: Callable[[Path], None] | None = None,
) -> Path:
    corpus_dir = resolve_under_repo(settings.repo_dir, settings.corpus_dir)
    staging_root = corpus_dir / f".query-refresh-{uuid.uuid4().hex}"
    staging_case_dir = staging_root / expected_case_dir.name
    cmd = command_prefix(settings.repo_dir, "analyze") + [
        "--profile-text",
        str(profile_text_path),
        "--query-id",
        validated_query_id,
        "--out",
        str(staging_root),
    ]
    if redact_identifiers:
        cmd.append("--redact-identifiers")
    if not settings.redact_hosts:
        cmd.append("--no-redact-hosts")
    if settings.max_profile_bytes is not None:
        cmd.extend(["--max-profile-bytes", str(settings.max_profile_bytes)])
    try:
        update_progress(progress, 2)
        analyzed = run_subprocess(
            cmd,
            cwd=settings.repo_dir,
            timeout_sec=settings.timeout_sec,
            runner=runner,
            env=manual_profile_analyzer_env(subprocess_env),
            cancel_check=cancel_check,
        )
        if cancel_check is not None and cancel_check():
            raise WebError("Analysis was stopped by the user.")
        if analyzed.returncode != 0:
            raise subprocess_failure_web_error("Manual profile analysis", analyzed)
        case_dir = parse_output_case_dir(analyzed.stdout)
        if not case_dir.is_absolute():
            case_dir = (settings.repo_dir / case_dir).resolve(strict=False)
        else:
            case_dir = case_dir.resolve(strict=False)
        resolved_staging_root = staging_root.resolve(strict=False)
        resolved_staging_case_dir = staging_case_dir.resolve(strict=False)
        try:
            case_dir.relative_to(resolved_staging_root)
        except ValueError as exc:
            raise WebError(
                "Manual profile analysis returned a case directory outside staging."
            ) from exc
        if case_dir != resolved_staging_case_dir:
            raise WebError(
                "Manual profile analysis returned a case directory that does not match the requested query id."
            )
        if post_analyze is not None:
            post_analyze(case_dir)
        return replace_case_dir_after_success(case_dir, expected_case_dir)
    finally:
        if staging_root.exists():
            remove_path(staging_root)


def manual_profile_analyzer_env(env: dict[str, str]) -> dict[str, str]:
    if METADATA_SOURCE_TABLES_ENV not in env:
        return env
    analyzer_env = dict(env)
    analyzer_env.pop(METADATA_SOURCE_TABLES_ENV, None)
    return analyzer_env


def update_progress(progress: ProgressFunc | None, stage_index: int) -> None:
    if progress is not None:
        progress(stage_index)
