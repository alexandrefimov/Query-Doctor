from __future__ import annotations

import json
from pathlib import Path

from scripts import build_trino_handoff_suite_manifest


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_trino_handoff_suite_manifest_writes_relative_manifest_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    first_boundary = _write_json(tmp_path, "first-secret-boundary.json")
    second_boundary = _write_json(tmp_path, "second-secret-boundary.json")
    first_diagnosis = _write_json(tmp_path, "first-secret-diagnosis.json")
    second_diagnosis = _write_json(tmp_path, "second-secret-diagnosis.json")
    smoke = _write_json(tmp_path, "secret-smoke-summary.json")
    first_readiness_summary = _write_json(tmp_path, "first-secret-readiness-summary.json")
    second_readiness_summary = _write_json(tmp_path, "second-secret-readiness-summary.json")
    first_handoff_summary = _write_json(tmp_path, "first-secret-handoff-summary.json")
    second_handoff_summary = _write_json(tmp_path, "second-secret-handoff-summary.json")
    first_product_surface_summary = _write_json(
        tmp_path,
        "first-secret-surface-summary.json",
    )
    second_product_surface_summary = _write_json(
        tmp_path,
        "second-secret-surface-summary.json",
    )
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_trino_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--boundary-json",
            str(first_boundary),
            "--boundary-json",
            str(second_boundary),
            "--diagnosis-json",
            str(first_diagnosis),
            "--diagnosis-json",
            str(second_diagnosis),
            "--smoke-summary",
            str(smoke),
            "--readiness-summary-json",
            str(first_readiness_summary),
            "--readiness-summary-json",
            str(second_readiness_summary),
            "--handoff-summary-json",
            str(first_handoff_summary),
            "--handoff-summary-json",
            str(second_handoff_summary),
            "--product-surface-summary-json",
            str(first_product_surface_summary),
            "--product-surface-summary-json",
            str(second_product_surface_summary),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert rc == 0
    assert payload["manifest_kind"] == "trino_one_query_handoff_suite_v1"
    assert payload["metadata"]["builder_kind"] == (
        "trino_one_query_handoff_suite_manifest_builder_v1"
    )
    assert payload["metadata"]["entry_count"] == 2
    assert payload["metadata"]["diagnosis_entry_count"] == 2
    assert payload["metadata"]["smoke_summary_entry_count"] == 2
    assert payload["metadata"]["readiness_summary_entry_count"] == 2
    assert payload["metadata"]["handoff_summary_entry_count"] == 2
    assert payload["metadata"]["product_surface_summary_entry_count"] == 2
    assert payload["metadata"]["path_reference"] == "relative_to_manifest"
    assert payload["metadata"]["redaction_reviewed"] is True
    assert "readiness_summary_checked" in payload["metadata"]["limitations"]
    assert "handoff_summary_checked" in payload["metadata"]["limitations"]
    assert "product_surface_summary_checked" in payload["metadata"]["limitations"]
    assert payload["entries"] == [
        {
            "boundary_json": "first-secret-boundary.json",
            "diagnosis_json": "first-secret-diagnosis.json",
            "handoff_summary_json": "first-secret-handoff-summary.json",
            "product_surface_summary_json": "first-secret-surface-summary.json",
            "readiness_summary_json": "first-secret-readiness-summary.json",
            "smoke_summary": "secret-smoke-summary.json",
        },
        {
            "boundary_json": "second-secret-boundary.json",
            "diagnosis_json": "second-secret-diagnosis.json",
            "handoff_summary_json": "second-secret-handoff-summary.json",
            "product_surface_summary_json": "second-secret-surface-summary.json",
            "readiness_summary_json": "second-secret-readiness-summary.json",
            "smoke_summary": "secret-smoke-summary.json",
        },
    ]
    assert "[trino-handoff-suite-manifest] written" in captured.out
    assert "entries: 2" in captured.out
    assert "diagnosis_entries: 2" in captured.out
    assert "smoke_summary_entries: 2" in captured.out
    assert "readiness_summary_entries: 2" in captured.out
    assert "handoff_summary_entries: 2" in captured.out
    assert "product_surface_summary_entries: 2" in captured.out
    assert captured.err == ""
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_handoff_suite_manifest_requires_redaction_review(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_json(tmp_path, "secret-boundary.json")
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_trino_handoff_suite_manifest.main(
        ["--boundary-json", str(boundary), "--out", str(manifest)]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_handoff_suite_manifest_rejects_mismatched_diagnosis_count_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    first_boundary = _write_json(tmp_path, "first-secret-boundary.json")
    second_boundary = _write_json(tmp_path, "second-secret-boundary.json")
    diagnosis = _write_json(tmp_path, "secret-diagnosis.json")
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_trino_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--boundary-json",
            str(first_boundary),
            "--boundary-json",
            str(second_boundary),
            "--diagnosis-json",
            str(diagnosis),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "diagnosis artifact count must match boundary artifact count" in captured.err
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_handoff_suite_manifest_rejects_summary_count_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    first_boundary = _write_json(tmp_path, "first-secret-boundary.json")
    second_boundary = _write_json(tmp_path, "second-secret-boundary.json")
    third_boundary = _write_json(tmp_path, "third-secret-boundary.json")
    first_smoke = _write_json(tmp_path, "first-secret-smoke.json")
    second_smoke = _write_json(tmp_path, "second-secret-smoke.json")
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_trino_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--boundary-json",
            str(first_boundary),
            "--boundary-json",
            str(second_boundary),
            "--boundary-json",
            str(third_boundary),
            "--smoke-summary",
            str(first_smoke),
            "--smoke-summary",
            str(second_smoke),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "smoke summary count must be one shared artifact or match boundary artifact count" in (
        captured.err
    )
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_handoff_suite_manifest_rejects_readiness_summary_count_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    first_boundary = _write_json(tmp_path, "first-secret-boundary.json")
    second_boundary = _write_json(tmp_path, "second-secret-boundary.json")
    readiness_summary = _write_json(tmp_path, "secret-readiness-summary.json")
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_trino_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--boundary-json",
            str(first_boundary),
            "--boundary-json",
            str(second_boundary),
            "--readiness-summary-json",
            str(readiness_summary),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "readiness summary artifact count must match boundary artifact count" in (captured.err)
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_handoff_suite_manifest_rejects_product_surface_summary_count_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    first_boundary = _write_json(tmp_path, "first-secret-boundary.json")
    second_boundary = _write_json(tmp_path, "second-secret-boundary.json")
    product_surface_summary = _write_json(tmp_path, "secret-surface-summary.json")
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_trino_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--boundary-json",
            str(first_boundary),
            "--boundary-json",
            str(second_boundary),
            "--product-surface-summary-json",
            str(product_surface_summary),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "product-surface summary artifact count must match boundary artifact count" in (
        captured.err
    )
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_handoff_suite_manifest_rejects_handoff_summary_count_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    first_boundary = _write_json(tmp_path, "first-secret-boundary.json")
    second_boundary = _write_json(tmp_path, "second-secret-boundary.json")
    handoff_summary = _write_json(tmp_path, "secret-handoff-summary.json")
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_trino_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--boundary-json",
            str(first_boundary),
            "--boundary-json",
            str(second_boundary),
            "--handoff-summary-json",
            str(handoff_summary),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "handoff summary artifact count must match boundary artifact count" in captured.err
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_handoff_suite_manifest_rejects_output_overlap_without_overwrite(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_json(tmp_path, "secret-boundary.json", marker="original")
    original = boundary.read_text(encoding="utf-8")

    rc = build_trino_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--boundary-json",
            str(boundary),
            "--out",
            str(boundary),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "manifest output must differ from every input artifact" in captured.err
    assert boundary.read_text(encoding="utf-8") == original
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_handoff_suite_manifest_rejects_parent_relative_artifact_reference(
    tmp_path: Path,
    capsys,
) -> None:
    artifact_dir = tmp_path / "secret-artifacts"
    manifest_dir = tmp_path / "secret-manifests"
    artifact_dir.mkdir()
    boundary = _write_json(artifact_dir, "secret-boundary.json")
    manifest = manifest_dir / "secret-suite-manifest.json"

    rc = build_trino_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--boundary-json",
            str(boundary),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "referenced artifact cannot be represented safely" in captured.err
    assert not manifest.exists()
    for fragment in (
        str(tmp_path),
        "secret-artifacts",
        "secret-manifests",
        "secret-boundary.json",
        "secret-suite-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_handoff_suite_manifest_rejects_duplicate_boundary_references(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_json(tmp_path, "secret-boundary.json")
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_trino_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--boundary-json",
            str(boundary),
            "--boundary-json",
            str(boundary),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert (
        "boundary, diagnosis, readiness summary, handoff summary, and product-surface summary artifacts must be unique"
        in captured.err
    )
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_handoff_suite_manifest_rejects_alias_duplicate_references(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_json(tmp_path, "secret-boundary.json")
    diagnosis_alias = tmp_path / "secret-diagnosis-alias.json"
    diagnosis_alias.symlink_to(boundary.name)
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_trino_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--boundary-json",
            str(boundary),
            "--diagnosis-json",
            str(diagnosis_alias),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert (
        "boundary, diagnosis, readiness summary, handoff summary, and product-surface summary artifacts must be unique"
        in captured.err
    )
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_handoff_suite_manifest_rejects_smoke_alias_to_boundary(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_json(tmp_path, "secret-boundary.json")
    smoke_alias = tmp_path / "secret-smoke-alias.json"
    smoke_alias.symlink_to(boundary.name)
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_trino_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--boundary-json",
            str(boundary),
            "--smoke-summary",
            str(smoke_alias),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert (
        "smoke summary artifacts must differ from boundary, diagnosis, readiness summary, handoff summary, and product-surface summary artifacts"
        in captured.err
    )
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_handoff_suite_manifest_requires_replace_for_existing_output(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_json(tmp_path, "secret-boundary.json")
    manifest = _write_json(tmp_path, "secret-suite-manifest.json", marker="old")
    original = manifest.read_text(encoding="utf-8")

    rc = build_trino_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--boundary-json",
            str(boundary),
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


def test_build_trino_handoff_suite_manifest_replace_overwrites_existing_output(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_json(tmp_path, "secret-boundary.json")
    manifest = _write_json(tmp_path, "secret-suite-manifest.json", marker="old")

    rc = build_trino_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--boundary-json",
            str(boundary),
            "--out",
            str(manifest),
            "--replace",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert rc == 0
    assert payload["manifest_kind"] == "trino_one_query_handoff_suite_v1"
    assert payload["entries"] == [{"boundary_json": "secret-boundary.json"}]
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_trino_handoff_suite_manifest_stays_dev_only_not_console_script() -> None:
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "build_trino_handoff_suite_manifest" not in pyproject_text
    assert "query-doctor-build-trino-handoff-suite-manifest" not in pyproject_text


def _write_json(directory: Path, name: str, *, marker: str = "safe") -> Path:
    path = directory / name
    path.write_text(json.dumps({"marker": marker}) + "\n", encoding="utf-8")
    return path


def _protected_fragments(tmp_path: Path) -> tuple[str, ...]:
    return (
        str(tmp_path),
        "first-secret-boundary.json",
        "second-secret-boundary.json",
        "third-secret-boundary.json",
        "first-secret-diagnosis.json",
        "second-secret-diagnosis.json",
        "secret-diagnosis.json",
        "secret-diagnosis-alias.json",
        "secret-boundary.json",
        "first-secret-smoke.json",
        "second-secret-smoke.json",
        "secret-smoke-summary.json",
        "secret-smoke-alias.json",
        "first-secret-readiness-summary.json",
        "second-secret-readiness-summary.json",
        "secret-readiness-summary.json",
        "first-secret-handoff-summary.json",
        "second-secret-handoff-summary.json",
        "secret-handoff-summary.json",
        "first-secret-surface-summary.json",
        "second-secret-surface-summary.json",
        "secret-surface-summary.json",
        "secret-suite-manifest.json",
    )
