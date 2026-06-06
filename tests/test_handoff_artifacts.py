from __future__ import annotations

import json
from pathlib import Path

from query_doctor.safety.handoff_artifacts import (
    ascii_json_artifact_text,
    distinct_paths_error,
    path_overlaps_any,
    same_path,
    write_ascii_json_artifact,
)


def test_handoff_artifact_json_is_ascii_sorted_and_newline_terminated(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "summary.json"
    payload = {"z": "\u043f", "a": 1}

    write_ascii_json_artifact(path, payload)

    text = path.read_text(encoding="utf-8")
    assert text == ascii_json_artifact_text(payload)
    assert text.endswith("\n")
    assert "\\u043f" in text
    assert "\u043f" not in text
    assert list(json.loads(text)) == ["a", "z"]


def test_handoff_artifact_path_overlap_uses_normalized_paths(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    alias = tmp_path / "nested" / ".." / "artifact.json"

    assert same_path(path, alias)
    assert path_overlaps_any(alias, (None, path))
    assert not path_overlaps_any(None, (path,))


def test_handoff_artifact_distinct_paths_error_reports_first_duplicate(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    duplicate = tmp_path / "nested" / ".." / "first.json"

    assert distinct_paths_error((first, second, None), message="outputs must differ") is None
    assert (
        distinct_paths_error((first, second, duplicate), message="outputs must differ")
        == "outputs must differ"
    )
