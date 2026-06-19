#!/usr/bin/env python3
"""Build a local Trino evidence handoff-suite manifest."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    output_overlaps_inputs_error,
    same_path,
    write_ascii_json_artifact,
)
from query_doctor.safety.manifest_references import is_safe_relative_json_reference  # noqa: E402
from scripts.audit_trino_evidence_handoff import (  # noqa: E402
    TRINO_EVIDENCE_HANDOFF_SUITE_MANIFEST_BUILDER_KIND,
    TRINO_EVIDENCE_HANDOFF_SUITE_MANIFEST_KIND,
)


class TrinoEvidenceHandoffSuiteManifestBuilderError(RuntimeError):
    """Raised for safe, path-free manifest builder failures."""


@dataclass(frozen=True)
class TrinoEvidenceHandoffSuiteEntrySpec:
    handoff_summary_json: Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a dev-only trino_evidence_handoff_suite_v1 manifest from retained "
            "raw-free Trino evidence handoff summaries. The command does not read "
            "Trino, validate packages, execute SQL, or print artifact paths or filenames."
        )
    )
    parser.add_argument(
        "--redaction-reviewed",
        action="store_true",
        help="Confirm referenced handoff summaries were operator-reviewed for local use.",
    )
    parser.add_argument(
        "--handoff-summary-json",
        action="append",
        default=[],
        type=Path,
        help="Raw-free Trino handoff summary JSON artifact. May be repeated.",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output path for the local handoff suite manifest. The path is never printed.",
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
            "[trino-evidence-handoff-suite-manifest] rejected: redaction review "
            "confirmation is required",
            file=sys.stderr,
        )
        return 1
    try:
        entries = entry_specs(args.handoff_summary_json)
        validate_output_path(args.out, entries, replace=args.replace)
        payload = manifest_payload(entries, manifest_path=args.out)
        write_manifest(args.out, payload)
    except TrinoEvidenceHandoffSuiteManifestBuilderError as exc:
        print(f"[trino-evidence-handoff-suite-manifest] rejected: {exc}", file=sys.stderr)
        return 2
    except OSError:
        print(
            "[trino-evidence-handoff-suite-manifest] rejected: local artifact could "
            "not be read or written",
            file=sys.stderr,
        )
        return 2

    print("[trino-evidence-handoff-suite-manifest] written")
    print(f"entries: {len(entries)}")
    print("path_reference: relative_to_manifest")
    return 0


def entry_specs(
    handoff_summary_jsons: Sequence[Path],
) -> tuple[TrinoEvidenceHandoffSuiteEntrySpec, ...]:
    if not handoff_summary_jsons:
        raise TrinoEvidenceHandoffSuiteManifestBuilderError(
            "at least one handoff summary is required"
        )
    entries = tuple(
        TrinoEvidenceHandoffSuiteEntrySpec(handoff_summary_json=summary)
        for summary in handoff_summary_jsons
    )
    for artifact in entry_artifacts(entries):
        if not artifact.is_file():
            raise TrinoEvidenceHandoffSuiteManifestBuilderError(
                "referenced artifact is unavailable"
            )
    ensure_unique_entry_artifacts(entries)
    return entries


def validate_output_path(
    out_path: Path,
    entries: Sequence[TrinoEvidenceHandoffSuiteEntrySpec],
    *,
    replace: bool,
) -> None:
    overlap_error = output_overlaps_inputs_error(
        out_path,
        entry_artifacts(entries),
        message="manifest output must differ from every input artifact",
    )
    if overlap_error is not None:
        raise TrinoEvidenceHandoffSuiteManifestBuilderError(overlap_error)
    if out_path.exists() and not replace:
        raise TrinoEvidenceHandoffSuiteManifestBuilderError(
            "manifest output already exists; pass --replace to overwrite"
        )
    if out_path.exists() and not out_path.is_file():
        raise TrinoEvidenceHandoffSuiteManifestBuilderError("manifest output is unavailable")


def manifest_payload(
    entries: Sequence[TrinoEvidenceHandoffSuiteEntrySpec],
    *,
    manifest_path: Path,
) -> dict[str, object]:
    base_dir = manifest_path.parent
    manifest_entries = tuple(manifest_entry_payload(entry, base_dir=base_dir) for entry in entries)
    ensure_unique_manifest_entries(manifest_entries)
    return {
        "manifest_kind": TRINO_EVIDENCE_HANDOFF_SUITE_MANIFEST_KIND,
        "metadata": {
            "builder_kind": TRINO_EVIDENCE_HANDOFF_SUITE_MANIFEST_BUILDER_KIND,
            "entry_count": len(entries),
            "path_reference": "relative_to_manifest",
            "redaction_reviewed": True,
            "limitations": [
                "local_handoff_summary_metadata_only",
                "not_committed_public_documentation",
                "not_trino_product_support",
            ],
        },
        "entries": list(manifest_entries),
    }


def manifest_entry_payload(
    entry: TrinoEvidenceHandoffSuiteEntrySpec,
    *,
    base_dir: Path,
) -> dict[str, str]:
    reference = relative_reference(
        entry.handoff_summary_json,
        base_dir=base_dir,
    )
    if not is_safe_relative_json_reference(reference):
        raise TrinoEvidenceHandoffSuiteManifestBuilderError(
            "referenced artifact cannot be represented safely"
        )
    return {"handoff_summary_json": reference}


def relative_reference(path: Path, *, base_dir: Path) -> str:
    return Path(os.path.relpath(path, base_dir)).as_posix()


def ensure_unique_manifest_entries(entries: Sequence[dict[str, str]]) -> None:
    seen_refs: set[str] = set()
    for entry in entries:
        reference = entry["handoff_summary_json"]
        if reference in seen_refs:
            raise TrinoEvidenceHandoffSuiteManifestBuilderError(
                "referenced artifacts must be unique"
            )
        seen_refs.add(reference)


def ensure_unique_entry_artifacts(
    entries: Sequence[TrinoEvidenceHandoffSuiteEntrySpec],
) -> None:
    seen_paths: list[Path] = []
    for artifact in entry_artifacts(entries):
        if any(same_path(artifact, seen) for seen in seen_paths):
            raise TrinoEvidenceHandoffSuiteManifestBuilderError(
                "referenced artifacts must be unique"
            )
        seen_paths.append(artifact)


def entry_artifacts(entries: Sequence[TrinoEvidenceHandoffSuiteEntrySpec]) -> tuple[Path, ...]:
    return tuple(entry.handoff_summary_json for entry in entries)


def write_manifest(path: Path, payload: dict[str, object]) -> None:
    write_ascii_json_artifact(path, payload)


if __name__ == "__main__":
    raise SystemExit(main())
