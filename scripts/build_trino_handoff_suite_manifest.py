#!/usr/bin/env python3
"""Build a local Trino one-query handoff-suite manifest."""

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
from query_doctor.safety.manifest_references import (  # noqa: E402
    is_safe_relative_json_reference,
)
from scripts.audit_trino_compact_readiness import (  # noqa: E402
    TRINO_HANDOFF_SUITE_MANIFEST_KIND,
)


MANIFEST_BUILDER_KIND = "trino_one_query_handoff_suite_manifest_builder_v1"


class TrinoHandoffSuiteManifestBuilderError(RuntimeError):
    """Raised for safe, path-free manifest builder failures."""


@dataclass(frozen=True)
class HandoffSuiteEntrySpec:
    boundary_json: Path
    diagnosis_json: Path | None = None
    smoke_summary: Path | None = None
    readiness_summary_json: Path | None = None
    handoff_summary_json: Path | None = None
    product_surface_summary_json: Path | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a dev-only trino_one_query_handoff_suite_v1 manifest from retained "
            "one-query handoff artifacts. The command does not read Trino, execute SQL, "
            "validate raw payloads, or print artifact paths or filenames."
        )
    )
    parser.add_argument(
        "--redaction-reviewed",
        action="store_true",
        help="Confirm referenced handoff artifacts were operator-reviewed for local use.",
    )
    parser.add_argument(
        "--boundary-json",
        action="append",
        default=[],
        type=Path,
        help="Raw-free one-query boundary JSON artifact. May be repeated.",
    )
    parser.add_argument(
        "--diagnosis-json",
        action="append",
        default=[],
        type=Path,
        help=(
            "Optional compact diagnosis JSON artifact. If provided, pass one per "
            "boundary in the same order."
        ),
    )
    parser.add_argument(
        "--smoke-summary",
        action="append",
        default=[],
        type=Path,
        help=(
            "Optional trino_smoke_summary.json artifact. Pass one shared smoke summary "
            "or one per boundary in the same order."
        ),
    )
    parser.add_argument(
        "--readiness-summary-json",
        action="append",
        default=[],
        type=Path,
        help=(
            "Optional raw-free trino_compact_readiness_summary_v1 artifact. "
            "If provided, pass one per boundary in the same order."
        ),
    )
    parser.add_argument(
        "--handoff-summary-json",
        action="append",
        default=[],
        type=Path,
        help=(
            "Optional raw-free trino_one_query_handoff_summary_v1 artifact. "
            "If provided, pass one per boundary in the same order."
        ),
    )
    parser.add_argument(
        "--product-surface-summary-json",
        action="append",
        default=[],
        type=Path,
        help=(
            "Optional raw-free trino_product_surface_boundary_audit_v1 artifact. "
            "If provided, pass one per boundary in the same order."
        ),
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
            "[trino-handoff-suite-manifest] rejected: redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1
    try:
        entries = entry_specs(
            args.boundary_json,
            diagnosis_jsons=args.diagnosis_json,
            smoke_summaries=args.smoke_summary,
            readiness_summary_jsons=args.readiness_summary_json,
            handoff_summary_jsons=args.handoff_summary_json,
            product_surface_summary_jsons=args.product_surface_summary_json,
        )
        validate_output_path(args.out, entries, replace=args.replace)
        payload = manifest_payload(entries, manifest_path=args.out)
        write_manifest(args.out, payload)
    except TrinoHandoffSuiteManifestBuilderError as exc:
        print(f"[trino-handoff-suite-manifest] rejected: {exc}", file=sys.stderr)
        return 2
    except OSError:
        print(
            "[trino-handoff-suite-manifest] rejected: local artifact could not be read or written",
            file=sys.stderr,
        )
        return 2

    print("[trino-handoff-suite-manifest] written")
    print(f"entries: {len(entries)}")
    print(f"diagnosis_entries: {sum(1 for entry in entries if entry.diagnosis_json is not None)}")
    print(
        f"smoke_summary_entries: {sum(1 for entry in entries if entry.smoke_summary is not None)}"
    )
    print(
        "readiness_summary_entries: "
        f"{sum(1 for entry in entries if entry.readiness_summary_json is not None)}"
    )
    print(
        "handoff_summary_entries: "
        f"{sum(1 for entry in entries if entry.handoff_summary_json is not None)}"
    )
    print(
        "product_surface_summary_entries: "
        f"{sum(1 for entry in entries if entry.product_surface_summary_json is not None)}"
    )
    print("path_reference: relative_to_manifest")
    return 0


def entry_specs(
    boundary_jsons: Sequence[Path],
    *,
    diagnosis_jsons: Sequence[Path],
    smoke_summaries: Sequence[Path],
    readiness_summary_jsons: Sequence[Path],
    handoff_summary_jsons: Sequence[Path],
    product_surface_summary_jsons: Sequence[Path],
) -> tuple[HandoffSuiteEntrySpec, ...]:
    if not boundary_jsons:
        raise TrinoHandoffSuiteManifestBuilderError("at least one boundary artifact is required")
    if diagnosis_jsons and len(diagnosis_jsons) != len(boundary_jsons):
        raise TrinoHandoffSuiteManifestBuilderError(
            "diagnosis artifact count must match boundary artifact count"
        )
    if smoke_summaries and len(smoke_summaries) not in {1, len(boundary_jsons)}:
        raise TrinoHandoffSuiteManifestBuilderError(
            "smoke summary count must be one shared artifact or match boundary artifact count"
        )
    if readiness_summary_jsons and len(readiness_summary_jsons) != len(boundary_jsons):
        raise TrinoHandoffSuiteManifestBuilderError(
            "readiness summary artifact count must match boundary artifact count"
        )
    if handoff_summary_jsons and len(handoff_summary_jsons) != len(boundary_jsons):
        raise TrinoHandoffSuiteManifestBuilderError(
            "handoff summary artifact count must match boundary artifact count"
        )
    if product_surface_summary_jsons and len(product_surface_summary_jsons) != len(boundary_jsons):
        raise TrinoHandoffSuiteManifestBuilderError(
            "product-surface summary artifact count must match boundary artifact count"
        )

    entries: list[HandoffSuiteEntrySpec] = []
    for index, boundary_json in enumerate(boundary_jsons):
        entries.append(
            HandoffSuiteEntrySpec(
                boundary_json=boundary_json,
                diagnosis_json=diagnosis_jsons[index] if diagnosis_jsons else None,
                smoke_summary=(
                    None
                    if not smoke_summaries
                    else smoke_summaries[0 if len(smoke_summaries) == 1 else index]
                ),
                readiness_summary_json=(
                    readiness_summary_jsons[index] if readiness_summary_jsons else None
                ),
                handoff_summary_json=(
                    handoff_summary_jsons[index] if handoff_summary_jsons else None
                ),
                product_surface_summary_json=(
                    product_surface_summary_jsons[index] if product_surface_summary_jsons else None
                ),
            )
        )
    for artifact in entry_artifacts(entries):
        if not artifact.is_file():
            raise TrinoHandoffSuiteManifestBuilderError("referenced artifact is unavailable")
    ensure_unique_entry_artifacts(entries)
    ensure_smoke_artifacts_do_not_overlap_suite_artifacts(entries)
    return tuple(entries)


def validate_output_path(
    out_path: Path,
    entries: Sequence[HandoffSuiteEntrySpec],
    *,
    replace: bool,
) -> None:
    overlap_error = output_overlaps_inputs_error(
        out_path,
        entry_artifacts(entries),
        message="manifest output must differ from every input artifact",
    )
    if overlap_error is not None:
        raise TrinoHandoffSuiteManifestBuilderError(overlap_error)
    if out_path.exists() and not replace:
        raise TrinoHandoffSuiteManifestBuilderError(
            "manifest output already exists; pass --replace to overwrite"
        )
    if out_path.exists() and not out_path.is_file():
        raise TrinoHandoffSuiteManifestBuilderError("manifest output is unavailable")


def manifest_payload(
    entries: Sequence[HandoffSuiteEntrySpec],
    *,
    manifest_path: Path,
) -> dict[str, object]:
    base_dir = manifest_path.parent
    manifest_entries = tuple(manifest_entry_payload(entry, base_dir=base_dir) for entry in entries)
    ensure_unique_manifest_references(manifest_entries)
    return {
        "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
        "metadata": {
            "builder_kind": MANIFEST_BUILDER_KIND,
            "entry_count": len(entries),
            "diagnosis_entry_count": sum(
                1 for entry in entries if entry.diagnosis_json is not None
            ),
            "smoke_summary_entry_count": sum(
                1 for entry in entries if entry.smoke_summary is not None
            ),
            "readiness_summary_entry_count": sum(
                1 for entry in entries if entry.readiness_summary_json is not None
            ),
            "handoff_summary_entry_count": sum(
                1 for entry in entries if entry.handoff_summary_json is not None
            ),
            "product_surface_summary_entry_count": sum(
                1 for entry in entries if entry.product_surface_summary_json is not None
            ),
            "path_reference": "relative_to_manifest",
            "redaction_reviewed": True,
            "limitations": [
                "local_handoff_metadata_only",
                *(
                    ["readiness_summary_checked"]
                    if any(entry.readiness_summary_json is not None for entry in entries)
                    else []
                ),
                *(
                    ["handoff_summary_checked"]
                    if any(entry.handoff_summary_json is not None for entry in entries)
                    else []
                ),
                *(
                    ["product_surface_summary_checked"]
                    if any(entry.product_surface_summary_json is not None for entry in entries)
                    else []
                ),
                "not_committed_public_documentation",
                "not_trino_product_support",
            ],
        },
        "entries": list(manifest_entries),
    }


def manifest_entry_payload(
    entry: HandoffSuiteEntrySpec,
    *,
    base_dir: Path,
) -> dict[str, str]:
    payload = {"boundary_json": relative_reference(entry.boundary_json, base_dir=base_dir)}
    if entry.diagnosis_json is not None:
        payload["diagnosis_json"] = relative_reference(entry.diagnosis_json, base_dir=base_dir)
    if entry.smoke_summary is not None:
        payload["smoke_summary"] = relative_reference(entry.smoke_summary, base_dir=base_dir)
    if entry.readiness_summary_json is not None:
        payload["readiness_summary_json"] = relative_reference(
            entry.readiness_summary_json,
            base_dir=base_dir,
        )
    if entry.handoff_summary_json is not None:
        payload["handoff_summary_json"] = relative_reference(
            entry.handoff_summary_json,
            base_dir=base_dir,
        )
    if entry.product_surface_summary_json is not None:
        payload["product_surface_summary_json"] = relative_reference(
            entry.product_surface_summary_json,
            base_dir=base_dir,
        )
    if any(not is_safe_relative_json_reference(reference) for reference in payload.values()):
        raise TrinoHandoffSuiteManifestBuilderError(
            "referenced artifact cannot be represented safely"
        )
    return payload


def relative_reference(path: Path, *, base_dir: Path) -> str:
    return Path(os.path.relpath(path, base_dir)).as_posix()


def ensure_unique_manifest_references(entries: Sequence[dict[str, str]]) -> None:
    seen_refs: set[str] = set()
    for entry in entries:
        for field in (
            "boundary_json",
            "diagnosis_json",
            "readiness_summary_json",
            "handoff_summary_json",
            "product_surface_summary_json",
        ):
            reference = entry.get(field)
            if reference is None:
                continue
            if reference in seen_refs:
                raise TrinoHandoffSuiteManifestBuilderError(
                    "boundary, diagnosis, readiness summary, handoff summary, and product-surface summary artifacts must be unique"
                )
            seen_refs.add(reference)


def ensure_unique_entry_artifacts(entries: Sequence[HandoffSuiteEntrySpec]) -> None:
    seen_paths: list[Path] = []
    for artifact in suite_width_entry_artifacts(entries):
        if any(same_path(artifact, seen) for seen in seen_paths):
            raise TrinoHandoffSuiteManifestBuilderError(
                "boundary, diagnosis, readiness summary, handoff summary, and product-surface summary artifacts must be unique"
            )
        seen_paths.append(artifact)


def ensure_smoke_artifacts_do_not_overlap_suite_artifacts(
    entries: Sequence[HandoffSuiteEntrySpec],
) -> None:
    suite_artifacts = suite_width_entry_artifacts(entries)
    for entry in entries:
        if entry.smoke_summary is None:
            continue
        if any(same_path(entry.smoke_summary, artifact) for artifact in suite_artifacts):
            raise TrinoHandoffSuiteManifestBuilderError(
                "smoke summary artifacts must differ from boundary, diagnosis, readiness summary, handoff summary, and product-surface summary artifacts"
            )


def suite_width_entry_artifacts(entries: Sequence[HandoffSuiteEntrySpec]) -> tuple[Path, ...]:
    artifacts: list[Path] = []
    for entry in entries:
        artifacts.append(entry.boundary_json)
        if entry.diagnosis_json is not None:
            artifacts.append(entry.diagnosis_json)
        if entry.readiness_summary_json is not None:
            artifacts.append(entry.readiness_summary_json)
        if entry.handoff_summary_json is not None:
            artifacts.append(entry.handoff_summary_json)
        if entry.product_surface_summary_json is not None:
            artifacts.append(entry.product_surface_summary_json)
    return tuple(artifacts)


def entry_artifacts(entries: Sequence[HandoffSuiteEntrySpec]) -> tuple[Path, ...]:
    artifacts: list[Path] = []
    for entry in entries:
        artifacts.append(entry.boundary_json)
        if entry.diagnosis_json is not None:
            artifacts.append(entry.diagnosis_json)
        if entry.smoke_summary is not None:
            artifacts.append(entry.smoke_summary)
        if entry.readiness_summary_json is not None:
            artifacts.append(entry.readiness_summary_json)
        if entry.handoff_summary_json is not None:
            artifacts.append(entry.handoff_summary_json)
        if entry.product_surface_summary_json is not None:
            artifacts.append(entry.product_surface_summary_json)
    return tuple(artifacts)


def write_manifest(path: Path, payload: dict[str, object]) -> None:
    write_ascii_json_artifact(path, payload)


if __name__ == "__main__":
    raise SystemExit(main())
