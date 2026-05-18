"""Browser-safe evidence inventory helpers for report UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from query_doctor.web.case_files import case_relative_file_path
from query_doctor.web.command_builders import BATCH_REPORT_NAME


@dataclass(frozen=True)
class ReportEvidenceCategory:
    label: str


@dataclass(frozen=True)
class ReportEvidenceCompleteness:
    label: str
    state: str


@dataclass(frozen=True)
class ReportEvidenceInventory:
    categories: tuple[ReportEvidenceCategory, ...]
    completeness: tuple[ReportEvidenceCompleteness, ...]
    profile_evidence_state: str
    analyzer_facts_state: str


REPORT_ARTIFACT_CANDIDATES = (
    ("Profile digest", ("profile_digest.md",)),
    ("Profile text", ("profile.txt",)),
    ("Profile JSON", ("profile.json",)),
    ("SQL", ("sql.sql",)),
    ("SQL", ("query.sql",)),
    ("SQL", ("original_query.sql",)),
    ("EXPLAIN", ("explain.txt",)),
    ("Analyzer facts", ("analysis_facts.md",)),
    ("Diagnosis", (BATCH_REPORT_NAME,)),
    ("Impala metadata", ("impala_context.md",)),
    ("Impala metadata JSON", ("impala_context.json",)),
    ("CM query details", ("cm_query_details.json",)),
    ("CM metadata", ("cm_metadata.json",)),
    ("Collection warnings", ("collection_warnings.txt",)),
)
REPORT_EVIDENCE_COMPLETENESS_GROUPS = (
    ("Profile", ("profile_digest.md", "profile.txt", "profile.json")),
    ("SQL", ("sql.sql", "query.sql", "original_query.sql")),
    ("EXPLAIN", ("explain.txt",)),
    ("Metadata", ("impala_context.md", "impala_context.json")),
    ("Host metrics", ()),
)


def report_evidence_inventory(case_dir: Path) -> ReportEvidenceInventory:
    categories = tuple(
        ReportEvidenceCategory(label)
        for label, names in REPORT_ARTIFACT_CANDIDATES
        if _case_has_any_artifact(case_dir, names)
    )
    completeness = tuple(
        ReportEvidenceCompleteness(
            label,
            "available" if names and _case_has_any_artifact(case_dir, names) else "not collected",
        )
        for label, names in REPORT_EVIDENCE_COMPLETENESS_GROUPS
    )
    return ReportEvidenceInventory(
        categories=categories,
        completeness=completeness,
        profile_evidence_state=(
            "available"
            if _case_has_any_artifact(
                case_dir, ("profile_digest.md", "profile.txt", "profile.json")
            )
            else "not observed"
        ),
        analyzer_facts_state=(
            "available"
            if case_relative_file_path(case_dir, "analysis_facts.md") is not None
            else "not observed"
        ),
    )


def _case_has_any_artifact(case_dir: Path, names: tuple[str, ...]) -> bool:
    return any(case_relative_file_path(case_dir, name) is not None for name in names)
