#!/usr/bin/env python3
"""Build a local Impala north-star retained-summary suite manifest."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.safety.handoff_artifacts import same_path  # noqa: E402
from query_doctor.safety.manifest_references import (  # noqa: E402
    is_safe_relative_json_reference,
)
from scripts.audit_impala_diagnostic_loop import safe_summary_key  # noqa: E402
from scripts.audit_impala_north_star_gate import (  # noqa: E402
    SUITE_MANIFEST_BUILDER_KIND,
    SUITE_MANIFEST_KIND,
)


class ImpalaNorthStarSuiteManifestBuilderError(RuntimeError):
    """Raised for safe, path-free manifest builder failures."""


@dataclass(frozen=True)
class NorthStarSuiteEntrySpec:
    loop_summary_json: Path
    label: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a local impala_north_star_suite_v1 manifest from retained raw-free "
            "Impala diagnostic-loop summaries. The command does not read raw cases, "
            "run collectors, validate private batch summaries, or print artifact paths "
            "or filenames."
        )
    )
    parser.add_argument(
        "--redaction-reviewed",
        action="store_true",
        help="Confirm referenced loop summaries were operator-reviewed for local use.",
    )
    parser.add_argument(
        "--loop-summary-json",
        action="append",
        default=[],
        type=Path,
        help="Raw-free impala_diagnostic_loop_audit_v1 summary JSON artifact. May be repeated.",
    )
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        help=(
            "Optional safe trend label for each retained summary. If provided, pass one "
            "per --loop-summary-json in the same order."
        ),
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output path for the local suite manifest. The path is never printed.",
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
            "[impala-north-star-suite-manifest] rejected: redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1
    try:
        entries = entry_specs(args.loop_summary_json, labels=args.label)
        validate_output_path(args.out, entries, replace=args.replace)
        payload = manifest_payload(entries, manifest_path=args.out)
        write_manifest(args.out, payload)
    except ImpalaNorthStarSuiteManifestBuilderError as exc:
        print(f"[impala-north-star-suite-manifest] rejected: {exc}", file=sys.stderr)
        return 2
    except OSError:
        print(
            "[impala-north-star-suite-manifest] rejected: local artifact could not be read or written",
            file=sys.stderr,
        )
        return 2

    print("[impala-north-star-suite-manifest] written")
    print(f"entries: {len(entries)}")
    print("path_reference: relative_to_manifest")
    return 0


def entry_specs(
    loop_summary_jsons: Sequence[Path],
    *,
    labels: Sequence[str],
) -> tuple[NorthStarSuiteEntrySpec, ...]:
    if not loop_summary_jsons:
        raise ImpalaNorthStarSuiteManifestBuilderError("at least one loop summary is required")
    if labels and len(labels) != len(loop_summary_jsons):
        raise ImpalaNorthStarSuiteManifestBuilderError("label count must match loop summary count")
    entries = tuple(
        NorthStarSuiteEntrySpec(
            loop_summary_json=summary,
            label=safe_summary_key(labels[index]) if labels else f"retained_batch_{index + 1}",
        )
        for index, summary in enumerate(loop_summary_jsons)
    )
    if any(not entry.label for entry in entries):
        raise ImpalaNorthStarSuiteManifestBuilderError("trend labels must not be empty")
    for artifact in entry_artifacts(entries):
        if not artifact.is_file():
            raise ImpalaNorthStarSuiteManifestBuilderError("referenced artifact is unavailable")
    ensure_unique_entry_artifacts(entries)
    return entries


def validate_output_path(
    out_path: Path,
    entries: Sequence[NorthStarSuiteEntrySpec],
    *,
    replace: bool,
) -> None:
    for artifact in entry_artifacts(entries):
        if same_path(out_path, artifact):
            raise ImpalaNorthStarSuiteManifestBuilderError(
                "manifest output must differ from every input artifact"
            )
    if out_path.exists() and not replace:
        raise ImpalaNorthStarSuiteManifestBuilderError(
            "manifest output already exists; pass --replace to overwrite"
        )
    if out_path.exists() and not out_path.is_file():
        raise ImpalaNorthStarSuiteManifestBuilderError("manifest output is unavailable")


def manifest_payload(
    entries: Sequence[NorthStarSuiteEntrySpec],
    *,
    manifest_path: Path,
) -> dict[str, object]:
    base_dir = manifest_path.parent
    manifest_entries = tuple(manifest_entry_payload(entry, base_dir=base_dir) for entry in entries)
    ensure_unique_manifest_entries(manifest_entries)
    return {
        "manifest_kind": SUITE_MANIFEST_KIND,
        "metadata": {
            "builder_kind": SUITE_MANIFEST_BUILDER_KIND,
            "entry_count": len(entries),
            "path_reference": "relative_to_manifest",
            "redaction_reviewed": True,
            "limitations": [
                "local_raw_free_loop_summary_metadata_only",
                "not_committed_public_documentation",
                "not_private_cluster_evidence",
            ],
        },
        "entries": list(manifest_entries),
    }


def manifest_entry_payload(
    entry: NorthStarSuiteEntrySpec,
    *,
    base_dir: Path,
) -> dict[str, str]:
    reference = relative_reference(entry.loop_summary_json, base_dir=base_dir)
    if not is_safe_relative_json_reference(reference):
        raise ImpalaNorthStarSuiteManifestBuilderError(
            "referenced artifact cannot be represented safely"
        )
    return {
        "loop_summary_json": reference,
        "label": entry.label,
    }


def relative_reference(path: Path, *, base_dir: Path) -> str:
    return Path(os.path.relpath(path, base_dir)).as_posix()


def ensure_unique_entry_artifacts(entries: Sequence[NorthStarSuiteEntrySpec]) -> None:
    seen_paths: list[Path] = []
    for artifact in entry_artifacts(entries):
        if any(same_path(artifact, seen) for seen in seen_paths):
            raise ImpalaNorthStarSuiteManifestBuilderError("referenced artifacts must be unique")
        seen_paths.append(artifact)


def ensure_unique_manifest_entries(entries: Sequence[dict[str, str]]) -> None:
    seen_refs: set[str] = set()
    for entry in entries:
        reference = entry["loop_summary_json"]
        if reference in seen_refs:
            raise ImpalaNorthStarSuiteManifestBuilderError("referenced artifacts must be unique")
        seen_refs.add(reference)


def entry_artifacts(entries: Sequence[NorthStarSuiteEntrySpec]) -> tuple[Path, ...]:
    return tuple(entry.loop_summary_json for entry in entries)


def write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
