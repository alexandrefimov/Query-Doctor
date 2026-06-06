#!/usr/bin/env python3
"""Build a local Spark one-application handoff-suite manifest."""

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
from scripts.audit_spark_compact_readiness import (  # noqa: E402
    SPARK_ONE_APPLICATION_HANDOFF_SUITE_MANIFEST_BUILDER_KIND,
    SPARK_ONE_APPLICATION_HANDOFF_SUITE_MANIFEST_KIND,
)


class SparkOneApplicationHandoffSuiteManifestBuilderError(RuntimeError):
    """Raised for safe, path-free manifest builder failures."""


@dataclass(frozen=True)
class SparkOneApplicationHandoffSuiteEntrySpec:
    compact_json: Path
    diagnosis_json: Path
    boundary_facts_json: Path
    handoff_summary_json: Path | None = None
    product_surface_summary_json: Path | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a dev-only spark_one_application_handoff_suite_v1 manifest from "
            "retained raw-free Spark one-application compact, diagnosis, and boundary "
            "artifacts. The command does not read Spark, validate artifacts, execute "
            "Spark jobs, or print artifact paths or filenames."
        )
    )
    parser.add_argument(
        "--redaction-reviewed",
        action="store_true",
        help="Confirm referenced one-application handoff artifacts were operator-reviewed.",
    )
    parser.add_argument(
        "--compact-json",
        action="append",
        default=[],
        type=Path,
        help="Raw-free Spark compact JSON artifact. May be repeated.",
    )
    parser.add_argument(
        "--diagnosis-json",
        action="append",
        default=[],
        type=Path,
        help="Raw-free Spark compact diagnosis JSON artifact. Must match compact count.",
    )
    parser.add_argument(
        "--boundary-facts-json",
        action="append",
        default=[],
        type=Path,
        help="Raw-free Spark engine_fact_boundary_v1 JSON artifact. Must match compact count.",
    )
    parser.add_argument(
        "--handoff-summary-json",
        action="append",
        default=[],
        type=Path,
        help=(
            "Optional raw-free spark_one_application_handoff_summary_v1 artifact. "
            "When provided, the count must match compact count."
        ),
    )
    parser.add_argument(
        "--product-surface-summary-json",
        action="append",
        default=[],
        type=Path,
        help=(
            "Optional raw-free spark_product_surface_boundary_audit_v1 artifact. "
            "When provided, the count must match compact count."
        ),
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output path for the local one-application handoff suite manifest.",
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
            "[spark-one-app-suite-manifest] rejected: redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1
    try:
        entries = entry_specs(
            args.compact_json,
            args.diagnosis_json,
            args.boundary_facts_json,
            args.handoff_summary_json,
            args.product_surface_summary_json,
        )
        validate_output_path(args.out, entries, replace=args.replace)
        payload = manifest_payload(entries, manifest_path=args.out)
        write_manifest(args.out, payload)
    except SparkOneApplicationHandoffSuiteManifestBuilderError as exc:
        print(f"[spark-one-app-suite-manifest] rejected: {exc}", file=sys.stderr)
        return 2
    except OSError:
        print(
            "[spark-one-app-suite-manifest] rejected: local artifact could not be read or written",
            file=sys.stderr,
        )
        return 2

    print("[spark-one-app-suite-manifest] written")
    print(f"entries: {len(entries)}")
    print("path_reference: relative_to_manifest")
    return 0


def entry_specs(
    compact_jsons: Sequence[Path],
    diagnosis_jsons: Sequence[Path],
    boundary_facts_jsons: Sequence[Path],
    handoff_summary_jsons: Sequence[Path],
    product_surface_summary_jsons: Sequence[Path],
) -> tuple[SparkOneApplicationHandoffSuiteEntrySpec, ...]:
    if not compact_jsons:
        raise SparkOneApplicationHandoffSuiteManifestBuilderError(
            "at least one compact artifact is required"
        )
    if len(diagnosis_jsons) != len(compact_jsons):
        raise SparkOneApplicationHandoffSuiteManifestBuilderError(
            "diagnosis artifact count must match compact artifact count"
        )
    if len(boundary_facts_jsons) != len(compact_jsons):
        raise SparkOneApplicationHandoffSuiteManifestBuilderError(
            "boundary artifact count must match compact artifact count"
        )
    if handoff_summary_jsons and len(handoff_summary_jsons) != len(compact_jsons):
        raise SparkOneApplicationHandoffSuiteManifestBuilderError(
            "handoff summary artifact count must match compact artifact count"
        )
    if product_surface_summary_jsons and len(product_surface_summary_jsons) != len(compact_jsons):
        raise SparkOneApplicationHandoffSuiteManifestBuilderError(
            "product-surface summary artifact count must match compact artifact count"
        )
    summary_jsons = (
        tuple(handoff_summary_jsons) if handoff_summary_jsons else (None,) * len(compact_jsons)
    )
    product_summary_jsons = (
        tuple(product_surface_summary_jsons)
        if product_surface_summary_jsons
        else (None,) * len(compact_jsons)
    )
    entries = tuple(
        SparkOneApplicationHandoffSuiteEntrySpec(
            compact_json=compact,
            diagnosis_json=diagnosis,
            boundary_facts_json=boundary,
            handoff_summary_json=summary,
            product_surface_summary_json=product_summary,
        )
        for compact, diagnosis, boundary, summary, product_summary in zip(
            compact_jsons,
            diagnosis_jsons,
            boundary_facts_jsons,
            summary_jsons,
            product_summary_jsons,
        )
    )
    for artifact in entry_artifacts(entries):
        if not artifact.is_file():
            raise SparkOneApplicationHandoffSuiteManifestBuilderError(
                "referenced artifact is unavailable"
            )
    return entries


def validate_output_path(
    out_path: Path,
    entries: Sequence[SparkOneApplicationHandoffSuiteEntrySpec],
    *,
    replace: bool,
) -> None:
    for artifact in entry_artifacts(entries):
        if same_path(out_path, artifact):
            raise SparkOneApplicationHandoffSuiteManifestBuilderError(
                "manifest output must differ from every input artifact"
            )
    if out_path.exists() and not replace:
        raise SparkOneApplicationHandoffSuiteManifestBuilderError(
            "manifest output already exists; pass --replace to overwrite"
        )
    if out_path.exists() and not out_path.is_file():
        raise SparkOneApplicationHandoffSuiteManifestBuilderError("manifest output is unavailable")


def manifest_payload(
    entries: Sequence[SparkOneApplicationHandoffSuiteEntrySpec],
    *,
    manifest_path: Path,
) -> dict[str, object]:
    base_dir = manifest_path.parent
    manifest_entries = tuple(manifest_entry_payload(entry, base_dir=base_dir) for entry in entries)
    ensure_unique_manifest_references(manifest_entries)
    return {
        "manifest_kind": SPARK_ONE_APPLICATION_HANDOFF_SUITE_MANIFEST_KIND,
        "metadata": {
            "builder_kind": SPARK_ONE_APPLICATION_HANDOFF_SUITE_MANIFEST_BUILDER_KIND,
            "entry_count": len(entries),
            "path_reference": "relative_to_manifest",
            "redaction_reviewed": True,
            "limitations": [
                "retained_one_application_artifacts",
                "diagnosis_boundary_checked",
                "engine_fact_boundary_checked",
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
                "not_spark_product_support",
            ],
        },
        "entries": list(manifest_entries),
    }


def manifest_entry_payload(
    entry: SparkOneApplicationHandoffSuiteEntrySpec,
    *,
    base_dir: Path,
) -> dict[str, str]:
    payload = {
        "compact_json": relative_reference(entry.compact_json, base_dir=base_dir),
        "diagnosis_json": relative_reference(entry.diagnosis_json, base_dir=base_dir),
        "boundary_facts_json": relative_reference(entry.boundary_facts_json, base_dir=base_dir),
    }
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
        raise SparkOneApplicationHandoffSuiteManifestBuilderError(
            "referenced artifact cannot be represented safely"
        )
    return payload


def relative_reference(path: Path, *, base_dir: Path) -> str:
    return Path(os.path.relpath(path, base_dir)).as_posix()


def ensure_unique_manifest_references(entries: Sequence[dict[str, str]]) -> None:
    seen_refs: set[str] = set()
    for entry in entries:
        for reference in entry.values():
            if reference in seen_refs:
                raise SparkOneApplicationHandoffSuiteManifestBuilderError(
                    "referenced artifacts must be unique"
                )
            seen_refs.add(reference)


def entry_artifacts(
    entries: Sequence[SparkOneApplicationHandoffSuiteEntrySpec],
) -> tuple[Path, ...]:
    artifacts: list[Path] = []
    for entry in entries:
        artifacts.extend((entry.compact_json, entry.diagnosis_json, entry.boundary_facts_json))
        if entry.handoff_summary_json is not None:
            artifacts.append(entry.handoff_summary_json)
        if entry.product_surface_summary_json is not None:
            artifacts.append(entry.product_surface_summary_json)
    return tuple(artifacts)


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()


def write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
