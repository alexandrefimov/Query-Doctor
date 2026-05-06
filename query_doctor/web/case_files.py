"""Case directory helpers for the local web UI."""

from __future__ import annotations

import json
import math
import re
import shutil
import uuid
from pathlib import Path

from query_doctor.cli import batch_recent
from query_doctor.cli import collect_cm_profiles as cm_collector

from query_doctor.web.models import WebError, WebSettings


OUTPUT_CASE_RE = re.compile(r"^Output case directory:\s*(?P<path>.+)$", re.MULTILINE)
COLLECTED_CASE_FILES = ("profile_digest.md", "cm_metadata.json", "collection_warnings.txt")
PROFILE_SUMMARY_READ_CHARS = 65536


def build_query_id_summary_case(
    query_id: str,
    case_dir: Path,
    *,
    collection_status: str = "ok",
    analysis_status: str = "ok",
) -> dict[str, object]:
    metadata = read_case_metadata(case_dir)
    profile_summary = read_profile_summary_fields(case_dir)
    case = batch_recent.CaseResult(
        index=1,
        query_id=query_id,
        duration_sec=case_duration_sec(metadata),
        user=profile_summary.get("user") or case_metadata_string(metadata, "user"),
        pool=profile_summary.get("pool") or case_metadata_string(metadata, "pool"),
        query_type=case_metadata_string(metadata, "query_type"),
        sql_verb=None,
        wrapper_dir=case_dir,
        actual_case_dir=case_dir,
        collection_status=collection_status,
        analysis_status=analysis_status,
        report_generated=False,
        report_validation_status="not_run",
    )
    batch_recent.inspect_case_outputs(case)
    batch_recent.score_case(case)
    summary_case = batch_recent.case_to_summary(case)
    summary_case.pop("case_index", None)
    summary_case.pop("case_dir", None)
    return summary_case


def read_case_metadata(case_dir: Path) -> dict[str, object]:
    metadata_path = case_dir / "cm_metadata.json"
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def case_metadata_string(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def read_profile_summary_fields(case_dir: Path) -> dict[str, str]:
    profile_path = case_dir / "profile_digest.md"
    try:
        with profile_path.open(encoding="utf-8", errors="replace") as handle:
            text = handle.read(PROFILE_SUMMARY_READ_CHARS)
    except OSError:
        return {}
    fields: dict[str, str] = {}
    for match in re.finditer(
        r"(?:^|\\n|\n)\s*(User|Pool|Request Pool|Resource Pool|Admission Pool)\s*:\s*([^\\\n\r\"]+)",
        text,
        flags=re.IGNORECASE,
    ):
        name = match.group(1).strip().lower()
        value = match.group(2).strip()
        if not value:
            continue
        if name == "user":
            fields["user"] = value
        elif "pool" in name:
            fields["pool"] = value
    return fields


def read_case_duration_sec(case_dir: Path) -> float | None:
    return case_duration_sec(read_case_metadata(case_dir))


def case_duration_sec(payload: dict[str, object]) -> float | None:
    if not payload:
        return None
    value = payload.get("duration_sec")
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    duration_ms = payload.get("duration_ms")
    if isinstance(duration_ms, (int, float)) and math.isfinite(float(duration_ms)):
        return float(duration_ms) / 1000
    return None


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def replace_case_dir_after_success(staged_case_dir: Path, expected_case_dir: Path) -> Path:
    ensure_complete_existing_case(staged_case_dir)
    if not (staged_case_dir / "analysis_facts.md").is_file():
        raise WebError("Analyzer output was not created.")

    expected_case_dir.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if expected_case_dir.exists() or expected_case_dir.is_symlink():
        backup_path = expected_case_dir.with_name(f".replace-{expected_case_dir.name}-{uuid.uuid4().hex}")
        expected_case_dir.rename(backup_path)
    try:
        staged_case_dir.rename(expected_case_dir)
    except Exception:
        if backup_path is not None and backup_path.exists() and not expected_case_dir.exists():
            backup_path.rename(expected_case_dir)
        raise
    if backup_path is not None:
        remove_path(backup_path)
    return expected_case_dir


def expected_case_dir_for_query(validated_query_id: str, settings: WebSettings) -> Path:
    try:
        slug = cm_collector.safe_case_slug(validated_query_id)
    except cm_collector.OutputError as exc:
        raise WebError(str(exc)) from exc
    corpus_dir = resolve_under_repo(settings.repo_dir, settings.corpus_dir)
    case_dir = (corpus_dir / slug).resolve(strict=False)
    try:
        case_dir.relative_to(corpus_dir)
    except ValueError as exc:
        raise WebError("Computed web case directory is outside the web corpus directory.") from exc
    return case_dir


def ensure_complete_existing_case(case_dir: Path) -> None:
    if not case_dir.is_dir():
        raise WebError(
            "Existing Query ID case is incomplete. "
            "Re-run analysis to regenerate required artifacts."
        )
    missing = [name for name in COLLECTED_CASE_FILES if not (case_dir / name).is_file()]
    if missing:
        raise WebError(
            "Existing Query ID case is incomplete. "
            "Re-run analysis to regenerate required artifacts."
        )


def parse_output_case_dir(stdout: str) -> Path:
    match = OUTPUT_CASE_RE.search(stdout)
    if not match:
        raise WebError("Collector output did not include a case directory.")
    return Path(match.group("path").strip())


def resolve_under_repo(repo_dir: Path, path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (repo_dir / path).resolve()


def parse_facts_summary(facts_text: str) -> dict[str, str]:
    summary: dict[str, str] = {}
    for key in ("Parsed operators", "Cardinality anomalies", "Memory anomalies"):
        match = re.search(rf"^\s*[-*]?\s*{re.escape(key)}\s*:\s*(?P<value>\d+)\s*$", facts_text, re.MULTILINE)
        if match:
            summary[key] = match.group("value")
    return summary
