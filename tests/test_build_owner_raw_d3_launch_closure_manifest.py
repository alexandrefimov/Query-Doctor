from __future__ import annotations

import json
from pathlib import Path

from scripts import build_owner_raw_d3_launch_closure_manifest as builder


def write_json(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_text("{}\n", encoding="utf-8")
    return path


def input_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "front_door": write_json(tmp_path, "secret-front-door-summary.json"),
        "readiness": write_json(tmp_path, "secret-readiness-summary.json"),
        "rehearsal": write_json(tmp_path, "secret-rehearsal-summary.json"),
        "source_enable": write_json(tmp_path, "secret-source-enable-summary.json"),
        "post_enable": write_json(tmp_path, "secret-post-enable-summary.json"),
    }


def build_args(paths: dict[str, Path], manifest: Path, *extra: str) -> list[str]:
    return [
        "--redaction-reviewed",
        "--front-door-review-summary-json",
        str(paths["front_door"]),
        "--readiness-summary-json",
        str(paths["readiness"]),
        "--rehearsal-summary-json",
        str(paths["rehearsal"]),
        "--source-enable-summary-json",
        str(paths["source_enable"]),
        "--post-enable-summary-json",
        str(paths["post_enable"]),
        "--out",
        str(manifest),
        *extra,
    ]


def protected_fragments(tmp_path: Path) -> tuple[str, ...]:
    return (
        str(tmp_path),
        "secret",
        "front-door-summary",
        "readiness-summary",
        "rehearsal-summary",
        "source-enable-summary",
        "post-enable-summary",
        "manifest.json",
        "/private/",
        "Authorization",
        "Cookie",
    )


def test_build_owner_raw_d3_launch_closure_manifest_writes_relative_manifest_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    paths = input_paths(tmp_path)
    manifest = tmp_path / "secret-launch-manifest.json"

    rc = builder.main(build_args(paths, manifest))

    captured = capsys.readouterr()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert rc == 0
    assert payload == {
        "manifest_kind": "owner_raw_d3_launch_closure_manifest_v1",
        "metadata": {
            "builder_kind": "owner_raw_d3_launch_closure_manifest_builder_v1",
            "entry_count": 1,
            "path_reference": "relative_to_manifest",
            "redaction_reviewed": True,
            "limitations": [
                "retained_owner_raw_d3_summaries",
                "front_door_review_summary_checked",
                "readiness_summary_checked",
                "rehearsal_summary_checked",
                "source_enable_summary_checked",
                "post_enable_summary_checked",
                "not_committed_public_documentation",
                "not_native_sso",
                "not_source_reader",
            ],
        },
        "entries": [
            {
                "front_door_review_summary_json": "secret-front-door-summary.json",
                "readiness_summary_json": "secret-readiness-summary.json",
                "rehearsal_summary_json": "secret-rehearsal-summary.json",
                "source_enable_summary_json": "secret-source-enable-summary.json",
                "post_enable_summary_json": "secret-post-enable-summary.json",
            }
        ],
    }
    assert "[owner-raw-d3-launch-manifest] written" in captured.out
    assert "entries: 1" in captured.out
    assert "path_reference: relative_to_manifest" in captured.out
    assert captured.err == ""
    for fragment in protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_owner_raw_d3_launch_closure_manifest_requires_redaction_review(
    tmp_path: Path,
    capsys,
) -> None:
    paths = input_paths(tmp_path)
    manifest = tmp_path / "secret-launch-manifest.json"
    args = build_args(paths, manifest)
    args.remove("--redaction-reviewed")

    rc = builder.main(args)

    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert not manifest.exists()
    for fragment in protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_owner_raw_d3_launch_closure_manifest_rejects_missing_artifact(
    tmp_path: Path,
    capsys,
) -> None:
    paths = input_paths(tmp_path)
    paths["post_enable"] = tmp_path / "secret-missing-post-enable.json"
    manifest = tmp_path / "secret-launch-manifest.json"

    rc = builder.main(build_args(paths, manifest))

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "referenced artifact is unavailable" in captured.err
    assert not manifest.exists()
    for fragment in protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_owner_raw_d3_launch_closure_manifest_rejects_duplicate_artifact(
    tmp_path: Path,
    capsys,
) -> None:
    paths = input_paths(tmp_path)
    paths["post_enable"] = paths["source_enable"]
    manifest = tmp_path / "secret-launch-manifest.json"

    rc = builder.main(build_args(paths, manifest))

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "referenced summary artifacts must be unique" in captured.err
    assert not manifest.exists()
    for fragment in protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_owner_raw_d3_launch_closure_manifest_rejects_output_overlap(
    tmp_path: Path,
    capsys,
) -> None:
    paths = input_paths(tmp_path)

    rc = builder.main(build_args(paths, paths["post_enable"]))

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "manifest output must differ from every input artifact" in captured.err
    for fragment in protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_owner_raw_d3_launch_closure_manifest_rejects_unsafe_relative_reference(
    tmp_path: Path,
    capsys,
) -> None:
    paths = input_paths(tmp_path)
    nested = tmp_path / "nested"
    nested.mkdir()
    manifest = nested / "secret-launch-manifest.json"

    rc = builder.main(build_args(paths, manifest))

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "referenced artifact cannot be represented safely" in captured.err
    assert not manifest.exists()
    for fragment in protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_build_owner_raw_d3_launch_closure_manifest_rejects_existing_output_without_replace(
    tmp_path: Path,
    capsys,
) -> None:
    paths = input_paths(tmp_path)
    manifest = write_json(tmp_path, "secret-launch-manifest.json")

    rc = builder.main(build_args(paths, manifest))

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "manifest output already exists; pass --replace to overwrite" in captured.err
    for fragment in protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err
