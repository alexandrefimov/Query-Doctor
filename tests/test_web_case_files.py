from __future__ import annotations

import json

import pytest

from query_doctor.web.case_files import (
    case_has_any_artifact,
    ensure_complete_existing_case,
    query_metadata_file_path,
    read_case_metadata,
    read_case_relative_text,
    read_profile_summary_fields,
    replace_case_dir_after_success,
)
from query_doctor.web.models import WebError


def write_collected_case_files(case_dir):
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "profile_digest.md").write_text("PROFILE\n", encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text("{}\n", encoding="utf-8")
    (case_dir / "collection_warnings.txt").write_text("", encoding="utf-8")


def test_case_summary_readers_ignore_symlinked_inputs_outside_case_dir(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    outside_query_metadata = tmp_path / "query_metadata.json"
    outside_metadata = tmp_path / "cm_metadata.json"
    outside_profile = tmp_path / "profile_digest.md"
    outside_query_metadata.write_text(
        json.dumps({"duration_sec": 88, "user": "canonical-leak"}), encoding="utf-8"
    )
    outside_metadata.write_text(
        json.dumps({"duration_sec": 99, "user": "leaked-user"}), encoding="utf-8"
    )
    outside_profile.write_text("User: leaked-user\nPool: leaked-pool\n", encoding="utf-8")
    (case_dir / "query_metadata.json").symlink_to(outside_query_metadata)
    (case_dir / "cm_metadata.json").symlink_to(outside_metadata)
    (case_dir / "profile_digest.md").symlink_to(outside_profile)

    assert read_case_metadata(case_dir) == {}
    assert read_profile_summary_fields(case_dir) == {}


def test_read_case_metadata_prefers_canonical_and_falls_back_to_legacy(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "query_metadata.json").write_text(
        json.dumps({"duration_sec": 12, "user": "canonical-user"}), encoding="utf-8"
    )
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"duration_sec": 99, "user": "legacy-user"}), encoding="utf-8"
    )

    assert query_metadata_file_path(case_dir) == case_dir / "query_metadata.json"
    assert read_case_metadata(case_dir)["user"] == "canonical-user"

    (case_dir / "query_metadata.json").unlink()

    assert query_metadata_file_path(case_dir) == case_dir / "cm_metadata.json"
    assert read_case_metadata(case_dir)["user"] == "legacy-user"


def test_complete_existing_case_accepts_canonical_metadata_only(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "profile_digest.md").write_text("PROFILE\n", encoding="utf-8")
    (case_dir / "query_metadata.json").write_text("{}\n", encoding="utf-8")
    (case_dir / "collection_warnings.txt").write_text("", encoding="utf-8")

    ensure_complete_existing_case(case_dir)


def test_case_has_any_artifact_matches_relative_file_predicate(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "a.md").write_text("a", encoding="utf-8")

    assert case_has_any_artifact(case_dir, ("a.md",))
    assert case_has_any_artifact(case_dir, ("missing.md", "a.md"))
    assert not case_has_any_artifact(case_dir, ("missing.md",))


def test_read_case_relative_text_rejects_symlinks_outside_case_dir(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    (case_dir / "alias.md").symlink_to(outside)

    assert read_case_relative_text(case_dir, "alias.md") is None


def test_complete_existing_case_rejects_symlinked_required_files_outside_case_dir(tmp_path):
    case_dir = tmp_path / "case"
    write_collected_case_files(case_dir)
    outside_profile = tmp_path / "profile_digest.md"
    outside_profile.write_text("PROFILE\n", encoding="utf-8")
    (case_dir / "profile_digest.md").unlink()
    (case_dir / "profile_digest.md").symlink_to(outside_profile)

    with pytest.raises(WebError, match="Existing Query ID case is incomplete"):
        ensure_complete_existing_case(case_dir)


def test_replace_case_dir_after_success_rejects_symlinked_analyzer_output_outside_case_dir(
    tmp_path,
):
    staged_case_dir = tmp_path / "staged"
    expected_case_dir = tmp_path / "expected"
    write_collected_case_files(staged_case_dir)
    outside_facts = tmp_path / "analysis_facts.md"
    outside_facts.write_text("FACTS\n", encoding="utf-8")
    (staged_case_dir / "analysis_facts.md").symlink_to(outside_facts)

    with pytest.raises(WebError, match="Analyzer output was not created"):
        replace_case_dir_after_success(staged_case_dir, expected_case_dir)

    assert not expected_case_dir.exists()
