from __future__ import annotations

import json
from pathlib import Path

from scripts import build_spark_one_application_handoff_suite_manifest


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_spark_one_application_handoff_suite_manifest_writes_relative_manifest_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    first_compact = _write_json(tmp_path, "first-secret-compact.json")
    second_compact = _write_json(tmp_path, "second-secret-compact.json")
    first_diagnosis = _write_json(tmp_path, "first-secret-diagnosis.json")
    second_diagnosis = _write_json(tmp_path, "second-secret-diagnosis.json")
    first_boundary = _write_json(tmp_path, "first-secret-boundary.json")
    second_boundary = _write_json(tmp_path, "second-secret-boundary.json")
    first_summary = _write_json(tmp_path, "first-secret-summary.json")
    second_summary = _write_json(tmp_path, "second-secret-summary.json")
    first_surface_summary = _write_json(tmp_path, "first-secret-surface-summary.json")
    second_surface_summary = _write_json(tmp_path, "second-secret-surface-summary.json")
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_spark_one_application_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--compact-json",
            str(first_compact),
            "--compact-json",
            str(second_compact),
            "--diagnosis-json",
            str(first_diagnosis),
            "--diagnosis-json",
            str(second_diagnosis),
            "--boundary-facts-json",
            str(first_boundary),
            "--boundary-facts-json",
            str(second_boundary),
            "--handoff-summary-json",
            str(first_summary),
            "--handoff-summary-json",
            str(second_summary),
            "--product-surface-summary-json",
            str(first_surface_summary),
            "--product-surface-summary-json",
            str(second_surface_summary),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert rc == 0
    assert payload["manifest_kind"] == "spark_one_application_handoff_suite_v1"
    assert payload["metadata"]["builder_kind"] == (
        "spark_one_application_handoff_suite_manifest_builder_v1"
    )
    assert payload["metadata"]["entry_count"] == 2
    assert payload["metadata"]["path_reference"] == "relative_to_manifest"
    assert payload["metadata"]["redaction_reviewed"] is True
    assert payload["metadata"]["limitations"] == [
        "retained_one_application_artifacts",
        "diagnosis_boundary_checked",
        "engine_fact_boundary_checked",
        "handoff_summary_checked",
        "product_surface_summary_checked",
        "not_committed_public_documentation",
        "not_spark_product_support",
    ]
    assert payload["entries"] == [
        {
            "compact_json": "first-secret-compact.json",
            "diagnosis_json": "first-secret-diagnosis.json",
            "boundary_facts_json": "first-secret-boundary.json",
            "handoff_summary_json": "first-secret-summary.json",
            "product_surface_summary_json": "first-secret-surface-summary.json",
        },
        {
            "compact_json": "second-secret-compact.json",
            "diagnosis_json": "second-secret-diagnosis.json",
            "boundary_facts_json": "second-secret-boundary.json",
            "handoff_summary_json": "second-secret-summary.json",
            "product_surface_summary_json": "second-secret-surface-summary.json",
        },
    ]
    assert "[spark-one-app-suite-manifest] written" in captured.out
    assert "entries: 2" in captured.out
    assert "path_reference: relative_to_manifest" in captured.out
    assert captured.err == ""
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_spark_one_application_handoff_suite_manifest_requires_redaction_review(
    tmp_path: Path,
    capsys,
) -> None:
    compact = _write_json(tmp_path, "secret-compact.json")
    diagnosis = _write_json(tmp_path, "secret-diagnosis.json")
    boundary = _write_json(tmp_path, "secret-boundary.json")
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_spark_one_application_handoff_suite_manifest.main(
        [
            "--compact-json",
            str(compact),
            "--diagnosis-json",
            str(diagnosis),
            "--boundary-facts-json",
            str(boundary),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_spark_one_application_handoff_suite_manifest_rejects_mismatched_counts(
    tmp_path: Path,
    capsys,
) -> None:
    first_compact = _write_json(tmp_path, "first-secret-compact.json")
    second_compact = _write_json(tmp_path, "second-secret-compact.json")
    diagnosis = _write_json(tmp_path, "secret-diagnosis.json")
    boundary = _write_json(tmp_path, "secret-boundary.json")
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_spark_one_application_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--compact-json",
            str(first_compact),
            "--compact-json",
            str(second_compact),
            "--diagnosis-json",
            str(diagnosis),
            "--boundary-facts-json",
            str(boundary),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "diagnosis artifact count must match compact artifact count" in captured.err
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_spark_one_application_handoff_suite_manifest_rejects_summary_count_mismatch(
    tmp_path: Path,
    capsys,
) -> None:
    first_compact = _write_json(tmp_path, "first-secret-compact.json")
    second_compact = _write_json(tmp_path, "second-secret-compact.json")
    first_diagnosis = _write_json(tmp_path, "first-secret-diagnosis.json")
    second_diagnosis = _write_json(tmp_path, "second-secret-diagnosis.json")
    first_boundary = _write_json(tmp_path, "first-secret-boundary.json")
    second_boundary = _write_json(tmp_path, "second-secret-boundary.json")
    summary = _write_json(tmp_path, "secret-summary.json")
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_spark_one_application_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--compact-json",
            str(first_compact),
            "--compact-json",
            str(second_compact),
            "--diagnosis-json",
            str(first_diagnosis),
            "--diagnosis-json",
            str(second_diagnosis),
            "--boundary-facts-json",
            str(first_boundary),
            "--boundary-facts-json",
            str(second_boundary),
            "--handoff-summary-json",
            str(summary),
            "--out",
            str(manifest),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "handoff summary artifact count must match compact artifact count" in captured.err
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_spark_one_application_handoff_suite_manifest_rejects_product_surface_count_mismatch(
    tmp_path: Path,
    capsys,
) -> None:
    first_compact = _write_json(tmp_path, "first-secret-compact.json")
    second_compact = _write_json(tmp_path, "second-secret-compact.json")
    first_diagnosis = _write_json(tmp_path, "first-secret-diagnosis.json")
    second_diagnosis = _write_json(tmp_path, "second-secret-diagnosis.json")
    first_boundary = _write_json(tmp_path, "first-secret-boundary.json")
    second_boundary = _write_json(tmp_path, "second-secret-boundary.json")
    product_surface_summary = _write_json(tmp_path, "secret-surface-summary.json")
    manifest = tmp_path / "secret-suite-manifest.json"

    rc = build_spark_one_application_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--compact-json",
            str(first_compact),
            "--compact-json",
            str(second_compact),
            "--diagnosis-json",
            str(first_diagnosis),
            "--diagnosis-json",
            str(second_diagnosis),
            "--boundary-facts-json",
            str(first_boundary),
            "--boundary-facts-json",
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
    assert "product-surface summary artifact count must match compact artifact count" in (
        captured.err
    )
    assert not manifest.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_spark_one_application_handoff_suite_manifest_rejects_output_overlap(
    tmp_path: Path,
    capsys,
) -> None:
    compact = _write_json(tmp_path, "secret-compact.json", marker="original")
    diagnosis = _write_json(tmp_path, "secret-diagnosis.json")
    boundary = _write_json(tmp_path, "secret-boundary.json")
    original = compact.read_text(encoding="utf-8")

    rc = build_spark_one_application_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--compact-json",
            str(compact),
            "--diagnosis-json",
            str(diagnosis),
            "--boundary-facts-json",
            str(boundary),
            "--out",
            str(compact),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "manifest output must differ from every input artifact" in captured.err
    assert compact.read_text(encoding="utf-8") == original
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_spark_one_application_handoff_suite_manifest_stays_dev_only_not_console_script() -> (
    None
):
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "build_spark_one_application_handoff_suite_manifest" not in pyproject_text
    assert "query-doctor-build-spark-one-application-handoff-suite-manifest" not in (pyproject_text)


def _write_json(tmp_path: Path, name: str, *, marker: str = "safe") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"marker": marker}) + "\n", encoding="utf-8")
    return path


def _protected_fragments(tmp_path: Path) -> tuple[str, ...]:
    return (
        str(tmp_path),
        "first-secret-compact.json",
        "second-secret-compact.json",
        "secret-compact.json",
        "first-secret-diagnosis.json",
        "second-secret-diagnosis.json",
        "secret-diagnosis.json",
        "first-secret-boundary.json",
        "second-secret-boundary.json",
        "secret-boundary.json",
        "first-secret-summary.json",
        "second-secret-summary.json",
        "secret-summary.json",
        "first-secret-surface-summary.json",
        "second-secret-surface-summary.json",
        "secret-surface-summary.json",
        "secret-suite-manifest.json",
    )
