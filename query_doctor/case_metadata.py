"""Provider-neutral case metadata file helpers."""

from __future__ import annotations

from pathlib import Path


QUERY_METADATA_FILENAME = "query_metadata.json"
LEGACY_CM_METADATA_FILENAME = "cm_metadata.json"
QUERY_METADATA_FILENAMES = (QUERY_METADATA_FILENAME, LEGACY_CM_METADATA_FILENAME)


def query_metadata_path(case_dir: Path) -> Path:
    return case_dir / QUERY_METADATA_FILENAME


def legacy_cm_metadata_path(case_dir: Path) -> Path:
    return case_dir / LEGACY_CM_METADATA_FILENAME


def existing_query_metadata_path(case_dir: Path) -> Path | None:
    for filename in QUERY_METADATA_FILENAMES:
        path = case_dir / filename
        if path.is_file():
            return path
    return None
