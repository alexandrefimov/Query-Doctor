from __future__ import annotations

import json
from pathlib import Path

from scripts import build_trino_evidence_handoff_suite_manifest


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_trino_evidence_handoff_suite_manifest_writes_relative_manifest_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    first_summary = _write_json(tmp_path, "first-secret-trino-handoff-summary.json")
    second_summary = _write_json(tmp_path, "second-secret-trino-handoff-summary.json")
    manifest = tmp_path / "secret-trino-suite-manifest.json"

    rc = build_trino_evidence_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--handoff-summary-json",
            str(first_summary),
            "--handoff-summary-json",
            str(second_summary),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert rc == 0
    assert payload["manifest_kind"] == "trino_evidence_handoff_suite_v1"
    assert payload["metadata"]["builder_kind"] == (
        "trino_evidence_handoff_suite_manifest_builder_v1"
    )
    assert payload["metadata"]["entry_count"] == 2
    assert payload["metadata"]["path_reference"] == "relative_to_manifest"
    assert payload["metadata"]["redaction_reviewed"] is True
    assert payload["metadata"]["limitations"] == [
        "local_handoff_summary_metadata_only",
        "not_committed_public_documentation",
        "not_trino_product_support",
    ]
    assert payload["entries"] == [
        {"handoff_summary_json": "first-secret-trino-handoff-summary.json"},
        {"handoff_summary_json": "second-secret-trino-handoff-summary.json"},
    ]
    assert "[trino-evidence-handoff-suite-manifest] written" in captured.out
    assert "entries: 2" in captured.out
    assert "path_reference: relative_to_manifest" in captured.out
    assert captured.err == ""
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_evidence_handoff_suite_manifest_requires_redaction_review(
    tmp_path: Path,
    capsys,
) -> None:
    summary = _write_json(tmp_path, "secret-trino-handoff-summary.json")
    manifest = tmp_path / "secret-trino-suite-manifest.json"

    rc = build_trino_evidence_handoff_suite_manifest.main(
        ["--handoff-summary-json", str(summary), "--out", str(manifest)]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_evidence_handoff_suite_manifest_requires_input_summary(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = tmp_path / "secret-trino-suite-manifest.json"

    rc = build_trino_evidence_handoff_suite_manifest.main(
        ["--redaction-reviewed", "--out", str(manifest)]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "at least one handoff summary is required" in captured.err
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_evidence_handoff_suite_manifest_rejects_output_overlap_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    summary = _write_json(tmp_path, "secret-trino-handoff-summary.json", marker="original")
    original = summary.read_text(encoding="utf-8")

    rc = build_trino_evidence_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--handoff-summary-json",
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


def test_build_trino_evidence_handoff_suite_manifest_rejects_missing_artifact_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    missing_summary = tmp_path / "missing-secret-trino-handoff-summary.json"
    manifest = tmp_path / "secret-trino-suite-manifest.json"

    rc = build_trino_evidence_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--handoff-summary-json",
            str(missing_summary),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "referenced artifact is unavailable" in captured.err
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err
    assert "missing-secret-trino-handoff-summary.json" not in captured.err


def test_build_trino_evidence_handoff_suite_manifest_rejects_unsafe_relative_reference(
    tmp_path: Path,
    capsys,
) -> None:
    summary = _write_json(tmp_path, "secret-trino-handoff-summary.json")
    manifest_dir = tmp_path / "manifest-dir"
    manifest = manifest_dir / "secret-trino-suite-manifest.json"

    rc = build_trino_evidence_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--handoff-summary-json",
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


def test_build_trino_evidence_handoff_suite_manifest_rejects_duplicate_reference(
    tmp_path: Path,
    capsys,
) -> None:
    summary = _write_json(tmp_path, "secret-trino-handoff-summary.json")
    manifest = tmp_path / "secret-trino-suite-manifest.json"

    rc = build_trino_evidence_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--handoff-summary-json",
            str(summary),
            "--handoff-summary-json",
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


def test_build_trino_evidence_handoff_suite_manifest_rejects_alias_duplicate_reference(
    tmp_path: Path,
    capsys,
) -> None:
    summary = _write_json(tmp_path, "secret-trino-handoff-summary.json")
    alias = tmp_path / "secret-trino-handoff-summary-alias.json"
    alias.symlink_to(summary.name)
    manifest = tmp_path / "secret-trino-suite-manifest.json"

    rc = build_trino_evidence_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--handoff-summary-json",
            str(summary),
            "--handoff-summary-json",
            str(alias),
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


def test_build_trino_evidence_handoff_suite_manifest_requires_replace_for_existing_output(
    tmp_path: Path,
    capsys,
) -> None:
    summary = _write_json(tmp_path, "secret-trino-handoff-summary.json")
    manifest = _write_json(tmp_path, "secret-trino-suite-manifest.json", marker="old")
    original = manifest.read_text(encoding="utf-8")

    rc = build_trino_evidence_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--handoff-summary-json",
            str(summary),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "manifest output already exists; pass --replace to overwrite" in captured.err
    assert manifest.read_text(encoding="utf-8") == original
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_evidence_handoff_suite_manifest_replace_overwrites_existing_output(
    tmp_path: Path,
    capsys,
) -> None:
    summary = _write_json(tmp_path, "secret-trino-handoff-summary.json")
    manifest = _write_json(tmp_path, "secret-trino-suite-manifest.json", marker="old")

    rc = build_trino_evidence_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--handoff-summary-json",
            str(summary),
            "--out",
            str(manifest),
            "--replace",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert rc == 0
    assert payload["manifest_kind"] == "trino_evidence_handoff_suite_v1"
    assert payload["entries"] == [{"handoff_summary_json": "secret-trino-handoff-summary.json"}]
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_evidence_handoff_suite_manifest_stays_dev_only_not_console_script() -> None:
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "build_trino_evidence_handoff_suite_manifest" not in pyproject_text
    assert "query-doctor-build-trino-evidence-handoff-suite-manifest" not in pyproject_text


def _write_json(tmp_path: Path, name: str, *, marker: str = "safe") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"marker": marker}) + "\n", encoding="utf-8")
    return path


def _protected_fragments(tmp_path: Path) -> tuple[str, ...]:
    return (
        str(tmp_path),
        "first-secret-trino-handoff-summary.json",
        "second-secret-trino-handoff-summary.json",
        "secret-trino-handoff-summary.json",
        "secret-trino-handoff-summary-alias.json",
        "secret-trino-suite-manifest.json",
    )
