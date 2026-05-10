from __future__ import annotations

import json

import pytest

from query_doctor.web.case_files import (
    ensure_complete_existing_case,
    read_case_metadata,
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
    outside_metadata = tmp_path / "cm_metadata.json"
    outside_profile = tmp_path / "profile_digest.md"
    outside_metadata.write_text(json.dumps({"duration_sec": 99, "user": "leaked-user"}), encoding="utf-8")
    outside_profile.write_text("User: leaked-user\nPool: leaked-pool\n", encoding="utf-8")
    (case_dir / "cm_metadata.json").symlink_to(outside_metadata)
    (case_dir / "profile_digest.md").symlink_to(outside_profile)

    assert read_case_metadata(case_dir) == {}
    assert read_profile_summary_fields(case_dir) == {}


def test_complete_existing_case_rejects_symlinked_required_files_outside_case_dir(tmp_path):
    case_dir = tmp_path / "case"
    write_collected_case_files(case_dir)
    outside_profile = tmp_path / "profile_digest.md"
    outside_profile.write_text("PROFILE\n", encoding="utf-8")
    (case_dir / "profile_digest.md").unlink()
    (case_dir / "profile_digest.md").symlink_to(outside_profile)

    with pytest.raises(WebError, match="Existing Query ID case is incomplete"):
        ensure_complete_existing_case(case_dir)


def test_replace_case_dir_after_success_rejects_symlinked_analyzer_output_outside_case_dir(tmp_path):
    staged_case_dir = tmp_path / "staged"
    expected_case_dir = tmp_path / "expected"
    write_collected_case_files(staged_case_dir)
    outside_facts = tmp_path / "analysis_facts.md"
    outside_facts.write_text("FACTS\n", encoding="utf-8")
    (staged_case_dir / "analysis_facts.md").symlink_to(outside_facts)

    with pytest.raises(WebError, match="Analyzer output was not created"):
        replace_case_dir_after_success(staged_case_dir, expected_case_dir)

    assert not expected_case_dir.exists()
