from __future__ import annotations

import json
from pathlib import Path

from scripts import build_impala_north_star_suite_manifest


def test_build_impala_north_star_suite_manifest_writes_relative_manifest_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    first_summary = _write_json(tmp_path, "first-secret-loop-summary.json")
    second_summary = _write_json(tmp_path, "second-secret-loop-summary.json")
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_impala_north_star_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--loop-summary-json",
            str(first_summary),
            "--loop-summary-json",
            str(second_summary),
            "--label",
            "baseline retained batch",
            "--label",
            "after deterministic evidence",
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert rc == 0
    assert payload["manifest_kind"] == "impala_north_star_suite_v1"
    assert payload["metadata"] == {
        "builder_kind": "impala_north_star_suite_manifest_builder_v1",
        "entry_count": 2,
        "limitations": [
            "local_raw_free_loop_summary_metadata_only",
            "not_committed_public_documentation",
            "not_private_cluster_evidence",
        ],
        "path_reference": "relative_to_manifest",
        "redaction_reviewed": True,
    }
    assert payload["entries"] == [
        {
            "label": "baseline_retained_batch",
            "loop_summary_json": "first-secret-loop-summary.json",
        },
        {
            "label": "after_deterministic_evidence",
            "loop_summary_json": "second-secret-loop-summary.json",
        },
    ]
    assert "[impala-north-star-suite-manifest] written" in captured.out
    assert "entries: 2" in captured.out
    assert "path_reference: relative_to_manifest" in captured.out
    assert captured.err == ""
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_impala_north_star_suite_manifest_requires_redaction_review(
    tmp_path: Path,
    capsys,
) -> None:
    summary = _write_json(tmp_path, "secret-loop-summary.json")
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_impala_north_star_suite_manifest.main(
        ["--loop-summary-json", str(summary), "--out", str(manifest)]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_impala_north_star_suite_manifest_rejects_label_count_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    first_summary = _write_json(tmp_path, "first-secret-loop-summary.json")
    second_summary = _write_json(tmp_path, "second-secret-loop-summary.json")
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_impala_north_star_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--loop-summary-json",
            str(first_summary),
            "--loop-summary-json",
            str(second_summary),
            "--label",
            "only one label",
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "label count must match loop summary count" in captured.err
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_impala_north_star_suite_manifest_rejects_output_overlap_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    summary = _write_json(tmp_path, "secret-loop-summary.json", marker="original")
    original = summary.read_text(encoding="utf-8")

    rc = build_impala_north_star_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--loop-summary-json",
            str(summary),
            "--out",
            str(summary),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "manifest output must differ from every input artifact" in captured.err
    assert summary.read_text(encoding="utf-8") == original
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_impala_north_star_suite_manifest_rejects_unsafe_relative_reference_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    summary = _write_json(tmp_path, "secret-loop-summary.json")
    manifest_dir = tmp_path / "manifest-dir"
    manifest = manifest_dir / "secret-suite-manifest.json"

    rc = build_impala_north_star_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--loop-summary-json",
            str(summary),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "referenced artifact cannot be represented safely" in captured.err
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_impala_north_star_suite_manifest_rejects_duplicate_reference_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    summary = _write_json(tmp_path, "secret-loop-summary.json")
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_impala_north_star_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--loop-summary-json",
            str(summary),
            "--loop-summary-json",
            str(summary),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "referenced artifacts must be unique" in captured.err
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def _write_json(tmp_path: Path, name: str, marker: str = "ok") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"marker": marker}) + "\n", encoding="utf-8")
    return path


def _protected_fragments(tmp_path: Path) -> tuple[str, ...]:
    return (
        str(tmp_path),
        "first-secret-loop-summary.json",
        "second-secret-loop-summary.json",
        "secret-loop-summary.json",
        "secret-suite-manifest.json",
    )
