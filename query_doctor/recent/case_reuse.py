"""Reuse completed Recent batch case artifacts for repeated scans."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from query_doctor.recent.batch_models import BatchConfig, CaseResult
from query_doctor.recent.batch_scoring import inspect_case_outputs, score_case
from query_doctor.recent.batch_summary import profile_reuse_contract
from query_doctor.recent.progress import ProgressWriter
from query_doctor.source_visibility import SOURCE_VISIBILITY_SAFE


BATCH_SUMMARY_NAME = "batch_summary.json"
REQUIRED_ANALYZED_CASE_FILES = ("profile_digest.md", "analysis_facts.md", "analysis.json")


@dataclass(frozen=True)
class ReusableAnalyzedCase:
    wrapper_dir: Path
    case_summary: dict[str, object]


@dataclass(frozen=True)
class AnalyzedCaseReuseIndex:
    cases_by_query_id: dict[str, ReusableAnalyzedCase]
    summaries_scanned: int


def reuse_analyzed_cases(
    config: BatchConfig,
    cases: list[CaseResult],
    *,
    progress: ProgressWriter,
) -> int:
    reason = analyzed_profile_reuse_skip_reason(config)
    if reason is not None:
        progress.emit(stage="profile_reuse", status="skipped", reason=reason)
        return 0
    index = build_analyzed_case_reuse_index(config)
    reused = 0
    for case in cases:
        case.profile_reuse_status = "miss"
        reusable = index.cases_by_query_id.get(case.query_id)
        if reusable is None:
            continue
        if copy_reusable_case(reusable, case):
            reused += 1
            progress.emit(
                stage="case",
                case_id=f"case-{case.index:03d}",
                status="profile_reused",
            )
    progress.emit(
        stage="profile_reuse",
        status="done",
        total=len(cases),
        reused=reused,
        summaries_scanned=index.summaries_scanned,
    )
    return reused


def analyzed_profile_reuse_skip_reason(config: BatchConfig) -> str | None:
    if not config.analyzed_profile_reuse_roots:
        return "not_configured"
    if config.only_running or config.include_running:
        return "running_queries_are_mutable"
    if config.source_visibility != SOURCE_VISIBILITY_SAFE:
        return "source_visibility_not_safe"
    if not (config.privacy_mode and config.redact_identifiers and config.redact_hosts):
        return "redaction_not_guaranteed"
    return None


def build_analyzed_case_reuse_index(config: BatchConfig) -> AnalyzedCaseReuseIndex:
    cases_by_query_id: dict[str, ReusableAnalyzedCase] = {}
    summaries_scanned = 0
    for summary_path in reusable_summary_paths(config):
        summary = read_summary(summary_path)
        if summary is None or not summary_is_compatible(summary, config):
            continue
        summaries_scanned += 1
        summary_root = summary_path.parent
        for case_summary in summary.get("cases") or []:
            if not isinstance(case_summary, dict):
                continue
            query_id = str(case_summary.get("query_id") or "")
            if not query_id or query_id in cases_by_query_id:
                continue
            wrapper_dir = reusable_wrapper_dir(case_summary, summary_root, current_out=config.out)
            if wrapper_dir is None:
                continue
            cases_by_query_id[query_id] = ReusableAnalyzedCase(
                wrapper_dir=wrapper_dir,
                case_summary=case_summary,
            )
    return AnalyzedCaseReuseIndex(cases_by_query_id, summaries_scanned)


def reusable_summary_paths(config: BatchConfig) -> list[Path]:
    current_out = resolve_existing_or_parent(config.out)
    paths: list[Path] = []
    for root in config.analyzed_profile_reuse_roots:
        if not root.exists() or not root.is_dir():
            continue
        for summary_path in root.glob(f"query-doctor-*/{BATCH_SUMMARY_NAME}"):
            summary_parent = resolve_existing_or_parent(summary_path.parent)
            if summary_parent == current_out:
                continue
            paths.append(summary_path)
    return sorted(paths, key=summary_mtime, reverse=True)


def summary_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def read_summary(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def summary_is_compatible(summary: dict[str, Any], config: BatchConfig) -> bool:
    return (
        summary.get("mode") == "recent-query-batch"
        and not bool(summary.get("include_running"))
        and not bool(summary.get("only_running"))
        and summary.get("profile_reuse_contract") == profile_reuse_contract(config)
    )


def reusable_wrapper_dir(
    case_summary: dict[str, object],
    summary_root: Path,
    *,
    current_out: Path,
) -> Path | None:
    if case_summary.get("collection_status") != "ok" or case_summary.get("analysis_status") != "ok":
        return None
    raw_case_dir = case_summary.get("case_dir")
    if not isinstance(raw_case_dir, str) or not raw_case_dir.strip():
        return None
    wrapper_dir = Path(raw_case_dir).expanduser()
    if not wrapper_dir.is_absolute():
        wrapper_dir = summary_root / wrapper_dir
    if wrapper_dir.is_symlink():
        return None
    try:
        resolved_wrapper = wrapper_dir.resolve()
        resolved_summary_root = summary_root.resolve()
        resolved_current_out = current_out.resolve()
    except OSError:
        return None
    if not resolved_wrapper.is_dir():
        return None
    if not path_is_relative_to(resolved_wrapper, resolved_summary_root):
        return None
    if path_is_relative_to(resolved_wrapper, resolved_current_out):
        return None
    if case_tree_has_symlinks(resolved_wrapper):
        return None
    actual_case_dir = analyzed_case_dir(resolved_wrapper)
    if actual_case_dir is None:
        return None
    return resolved_wrapper


def copy_reusable_case(reusable: ReusableAnalyzedCase, case: CaseResult) -> bool:
    if case.wrapper_dir.exists():
        return False
    try:
        shutil.copytree(reusable.wrapper_dir, case.wrapper_dir)
    except OSError:
        return False
    actual_case_dir = analyzed_case_dir(case.wrapper_dir)
    if actual_case_dir is None:
        shutil.rmtree(case.wrapper_dir, ignore_errors=True)
        return False
    case.actual_case_dir = actual_case_dir
    case.collection_status = "ok"
    case.analysis_status = "ok"
    case.profile_reuse_status = "reused"
    case.cm_collect_seconds = 0.0
    case.analysis_seconds = 0.0
    case.metadata_refreshed = bool(reusable.case_summary.get("metadata_refreshed"))
    inspect_case_outputs(case)
    score_case(case)
    return True


def analyzed_case_dir(wrapper_dir: Path) -> Path | None:
    for profile_path in sorted(wrapper_dir.rglob("profile_digest.md")):
        candidate = profile_path.parent
        if all((candidate / name).is_file() for name in REQUIRED_ANALYZED_CASE_FILES):
            return candidate
    return None


def case_tree_has_symlinks(root: Path) -> bool:
    try:
        return any(path.is_symlink() for path in root.rglob("*"))
    except OSError:
        return True


def resolve_existing_or_parent(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.parent.resolve() / path.name


def path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
