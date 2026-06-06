#!/usr/bin/env python3
"""Build a local Spark evidence handoff-suite manifest."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from query_doctor.safety.manifest_references import (  # noqa: E402
    is_safe_relative_json_reference,
)
from scripts.audit_spark_evidence_handoff import (  # noqa: E402
    SPARK_EVIDENCE_HANDOFF_SUITE_MANIFEST_KIND,
    SPARK_EVIDENCE_HANDOFF_SUITE_MANIFEST_BUILDER_KIND,
    same_path,
)


class SparkHandoffSuiteManifestBuilderError(RuntimeError):
    """Raised for safe, path-free manifest builder failures."""


@dataclass(frozen=True)
class SparkHandoffSuiteEntrySpec:
    handoff_summary_json: Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a dev-only spark_evidence_handoff_suite_v1 manifest from retained "
            "raw-free Spark evidence handoff summaries. The command does not read "
            "Spark, validate packages, execute Spark jobs, or print artifact paths "
            "or filenames."
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
        help="Raw-free Spark handoff summary JSON artifact. May be repeated.",
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
            "[spark-handoff-suite-manifest] rejected: redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1
    try:
        entries = entry_specs(args.handoff_summary_json)
        validate_output_path(args.out, entries, replace=args.replace)
        payload = manifest_payload(entries, manifest_path=args.out)
        write_manifest(args.out, payload)
    except SparkHandoffSuiteManifestBuilderError as exc:
        print(f"[spark-handoff-suite-manifest] rejected: {exc}", file=sys.stderr)
        return 2
    except OSError:
        print(
            "[spark-handoff-suite-manifest] rejected: local artifact could not be read or written",
            file=sys.stderr,
        )
        return 2

    print("[spark-handoff-suite-manifest] written")
    print(f"entries: {len(entries)}")
    print("path_reference: relative_to_manifest")
    return 0


def entry_specs(
    handoff_summary_jsons: Sequence[Path],
) -> tuple[SparkHandoffSuiteEntrySpec, ...]:
    if not handoff_summary_jsons:
        raise SparkHandoffSuiteManifestBuilderError("at least one handoff summary is required")
    entries = tuple(
        SparkHandoffSuiteEntrySpec(handoff_summary_json=summary)
        for summary in handoff_summary_jsons
    )
    for artifact in entry_artifacts(entries):
        if not artifact.is_file():
            raise SparkHandoffSuiteManifestBuilderError("referenced artifact is unavailable")
    return entries


def validate_output_path(
    out_path: Path,
    entries: Sequence[SparkHandoffSuiteEntrySpec],
    *,
    replace: bool,
) -> None:
    for artifact in entry_artifacts(entries):
        if same_path(out_path, artifact):
            raise SparkHandoffSuiteManifestBuilderError(
                "manifest output must differ from every input artifact"
            )
    if out_path.exists() and not replace:
        raise SparkHandoffSuiteManifestBuilderError(
            "manifest output already exists; pass --replace to overwrite"
        )
    if out_path.exists() and not out_path.is_file():
        raise SparkHandoffSuiteManifestBuilderError("manifest output is unavailable")


def manifest_payload(
    entries: Sequence[SparkHandoffSuiteEntrySpec],
    *,
    manifest_path: Path,
) -> dict[str, object]:
    base_dir = manifest_path.parent
    manifest_entries = tuple(manifest_entry_payload(entry, base_dir=base_dir) for entry in entries)
    ensure_unique_manifest_entries(manifest_entries)
    return {
        "manifest_kind": SPARK_EVIDENCE_HANDOFF_SUITE_MANIFEST_KIND,
        "metadata": {
            "builder_kind": SPARK_EVIDENCE_HANDOFF_SUITE_MANIFEST_BUILDER_KIND,
            "entry_count": len(entries),
            "path_reference": "relative_to_manifest",
            "redaction_reviewed": True,
            "limitations": [
                "local_handoff_summary_metadata_only",
                "not_committed_public_documentation",
                "not_spark_product_support",
            ],
        },
        "entries": list(manifest_entries),
    }


def manifest_entry_payload(
    entry: SparkHandoffSuiteEntrySpec,
    *,
    base_dir: Path,
) -> dict[str, str]:
    reference = relative_reference(
        entry.handoff_summary_json,
        base_dir=base_dir,
    )
    if not is_safe_relative_json_reference(reference):
        raise SparkHandoffSuiteManifestBuilderError(
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
            raise SparkHandoffSuiteManifestBuilderError("referenced artifacts must be unique")
        seen_refs.add(reference)


def entry_artifacts(entries: Sequence[SparkHandoffSuiteEntrySpec]) -> tuple[Path, ...]:
    return tuple(entry.handoff_summary_json for entry in entries)


def write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
