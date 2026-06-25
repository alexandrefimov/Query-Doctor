#!/usr/bin/env python3
"""Build a local owner_raw D3 launch-closure manifest."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    output_overlaps_inputs_error,
    same_path,
    write_ascii_json_artifact,
)
from query_doctor.safety.manifest_references import (  # noqa: E402
    is_safe_relative_json_reference,
)
from scripts.audit_owner_raw_d3_launch_closure import (  # noqa: E402
    MANIFEST_BUILDER_KIND,
    MANIFEST_ENTRY_FIELDS,
    MANIFEST_KIND,
    MANIFEST_LIMITATIONS,
)


class OwnerRawD3LaunchClosureManifestBuilderError(RuntimeError):
    """Raised for safe, path-free manifest builder failures."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a local owner_raw_d3_launch_closure_manifest_v1 manifest from "
            "retained raw-free D3 launch evidence summaries. The command does not "
            "contact a proxy, authenticate, open cases, read source text, validate "
            "summary contents, or print artifact paths or filenames."
        )
    )
    parser.add_argument(
        "--redaction-reviewed",
        action="store_true",
        help="Confirm referenced D3 launch evidence summaries were operator-reviewed.",
    )
    parser.add_argument(
        "--front-door-review-summary-json",
        required=True,
        type=Path,
        help="Raw-free owner_raw live front-door review audit summary.",
    )
    parser.add_argument(
        "--readiness-summary-json",
        required=True,
        type=Path,
        help="Raw-free owner_raw D3 readiness summary.",
    )
    parser.add_argument(
        "--rehearsal-summary-json",
        required=True,
        type=Path,
        help="Raw-free owner_raw D3 rehearsal summary.",
    )
    parser.add_argument(
        "--source-enable-summary-json",
        required=True,
        type=Path,
        help="Raw-free owner_raw D3 source-enable canary summary.",
    )
    parser.add_argument(
        "--post-enable-summary-json",
        required=True,
        type=Path,
        help="Raw-free owner_raw D3 post-enable canary summary.",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output path for the local D3 launch-closure manifest. The path is never printed.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Allow replacing an existing manifest output file.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.redaction_reviewed:
        print(
            "[owner-raw-d3-launch-manifest] rejected: redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1
    artifacts = input_artifacts(args)
    try:
        validate_input_artifacts(artifacts)
        validate_output_path(args.out, artifacts, replace=args.replace)
        payload = manifest_payload(artifacts, manifest_path=args.out)
        write_ascii_json_artifact(args.out, payload)
    except OwnerRawD3LaunchClosureManifestBuilderError as exc:
        print(f"[owner-raw-d3-launch-manifest] rejected: {exc}", file=sys.stderr)
        return 2
    except OSError:
        print(
            "[owner-raw-d3-launch-manifest] rejected: local artifact could not be read or written",
            file=sys.stderr,
        )
        return 2

    print("[owner-raw-d3-launch-manifest] written")
    print("entries: 1")
    print("path_reference: relative_to_manifest")
    return 0


def input_artifacts(args: argparse.Namespace) -> tuple[Path, ...]:
    return (
        args.front_door_review_summary_json,
        args.readiness_summary_json,
        args.rehearsal_summary_json,
        args.source_enable_summary_json,
        args.post_enable_summary_json,
    )


def validate_input_artifacts(artifacts: Sequence[Path]) -> None:
    if any(not artifact.is_file() for artifact in artifacts):
        raise OwnerRawD3LaunchClosureManifestBuilderError("referenced artifact is unavailable")
    seen: list[Path] = []
    for artifact in artifacts:
        if any(same_path(artifact, previous) for previous in seen):
            raise OwnerRawD3LaunchClosureManifestBuilderError(
                "referenced summary artifacts must be unique"
            )
        seen.append(artifact)


def validate_output_path(
    out_path: Path,
    artifacts: Sequence[Path],
    *,
    replace: bool,
) -> None:
    overlap_error = output_overlaps_inputs_error(
        out_path,
        artifacts,
        message="manifest output must differ from every input artifact",
    )
    if overlap_error is not None:
        raise OwnerRawD3LaunchClosureManifestBuilderError(overlap_error)
    if out_path.exists() and not replace:
        raise OwnerRawD3LaunchClosureManifestBuilderError(
            "manifest output already exists; pass --replace to overwrite"
        )
    if out_path.exists() and not out_path.is_file():
        raise OwnerRawD3LaunchClosureManifestBuilderError("manifest output is unavailable")


def manifest_payload(
    artifacts: Sequence[Path],
    *,
    manifest_path: Path,
) -> dict[str, object]:
    base_dir = manifest_path.parent
    entry = {
        field_name: relative_reference(artifact, base_dir=base_dir)
        for field_name, artifact in zip(MANIFEST_ENTRY_FIELDS, artifacts)
    }
    if any(not is_safe_relative_json_reference(reference) for reference in entry.values()):
        raise OwnerRawD3LaunchClosureManifestBuilderError(
            "referenced artifact cannot be represented safely"
        )
    return {
        "manifest_kind": MANIFEST_KIND,
        "metadata": {
            "builder_kind": MANIFEST_BUILDER_KIND,
            "entry_count": 1,
            "path_reference": "relative_to_manifest",
            "redaction_reviewed": True,
            "limitations": list(MANIFEST_LIMITATIONS),
        },
        "entries": [entry],
    }


def relative_reference(path: Path, *, base_dir: Path) -> str:
    return Path(os.path.relpath(path, base_dir)).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
