"""Export Spark compact evidence package samples as fixture-ready JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.spark_evidence_package import (
    SPARK_EVIDENCE_READINESS_PROMOTION_CANDIDATE,
    spark_evidence_package_readiness_payload,
    validate_spark_evidence_package_payload,
)

SPARK_FIXTURE_EXPORT_MANIFEST = "spark_fixture_export_manifest.json"
SPARK_FIXTURE_EXPORT_MANIFEST_VERSION = "spark_fixture_export_manifest_v1"


@dataclass(frozen=True)
class SparkFixtureExport:
    file_name: str
    case: str
    source_type: str
    source_contract: str
    payload: Mapping[str, Any]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export already-sanitized Spark compact evidence package samples as "
            "fixture-ready JSON. The command validates the package promotion gate, "
            "prints no input or output paths, and does not claim Spark product support."
        )
    )
    parser.add_argument("package_json", type=Path, help="Path to a sanitized package JSON file.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Directory where fixture-ready compact sample JSON files will be written.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        package_payload = _load_json(args.package_json)
        result = validate_spark_evidence_package_payload(package_payload)
        readiness = spark_evidence_package_readiness_payload(result)
        if readiness["readiness_status"] != SPARK_EVIDENCE_READINESS_PROMOTION_CANDIDATE:
            blockers = _format_safe_labels(readiness["promotion_blockers"])
            raise EngineFactContractError(
                f"Spark evidence package is not promotion_candidate; promotion_blockers: {blockers}"
            )
        exports = _fixture_exports(package_payload)
        manifest = _fixture_export_manifest(package_payload, exports)
        _write_exports(args.out_dir, exports, manifest)
    except OSError:
        print("[spark-fixture-export] rejected: file could not be read or written", file=sys.stderr)
        return 2
    except json.JSONDecodeError:
        print("[spark-fixture-export] rejected: package is not valid JSON", file=sys.stderr)
        return 2
    except (EngineFactContractError, ValueError) as exc:
        print(f"[spark-fixture-export] rejected: {exc}", file=sys.stderr)
        return 1

    print("[spark-fixture-export] written")
    print(f"sample_count: {len(exports)}")
    print("readiness_status: promotion_candidate")
    print("support_claim: not_claimed")
    print("manifest: written")
    print("output_paths: not_printed")
    return 0


def _load_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Spark evidence package must be a JSON object")
    return payload


def _fixture_exports(
    package_payload: Mapping[str, Any],
) -> tuple[SparkFixtureExport, ...]:
    samples = package_payload.get("samples")
    if not isinstance(samples, Sequence) or isinstance(samples, (str, bytes)):
        raise EngineFactContractError("Spark evidence package samples must be a list")
    exports: list[SparkFixtureExport] = []
    for index, sample in enumerate(samples, start=1):
        if not isinstance(sample, Mapping):
            raise EngineFactContractError("Spark evidence package sample must be an object")
        case = _safe_label(sample.get("case"))
        source_type = _safe_label(sample.get("source_type"))
        payload = sample.get("payload")
        if not isinstance(payload, Mapping):
            raise EngineFactContractError("Spark evidence package sample payload must be an object")
        source_contract = _safe_label(payload.get("sourceContract"))
        exports.append(
            SparkFixtureExport(
                file_name=f"{index:03d}_{case}_{source_type}.json",
                case=case,
                source_type=source_type,
                source_contract=source_contract,
                payload=payload,
            )
        )
    return tuple(exports)


def _fixture_export_manifest(
    package_payload: Mapping[str, Any],
    exports: Sequence[SparkFixtureExport],
) -> dict[str, Any]:
    package_manifest = package_payload.get("manifest")
    if not isinstance(package_manifest, Mapping):
        raise EngineFactContractError("Spark evidence package manifest must be an object")
    package_id = _safe_label(package_manifest.get("package_id"))
    return {
        "schema_version": SPARK_FIXTURE_EXPORT_MANIFEST_VERSION,
        "package_id": package_id,
        "readiness_status": SPARK_EVIDENCE_READINESS_PROMOTION_CANDIDATE,
        "support_claim": "not_claimed",
        "sample_count": len(exports),
        "samples": [
            {
                "file_name": export.file_name,
                "case": export.case,
                "source_type": export.source_type,
                "source_contract": export.source_contract,
            }
            for export in exports
        ],
    }


def _write_exports(
    out_dir: Path,
    exports: Sequence[SparkFixtureExport],
    manifest: Mapping[str, Any],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = (
        out_dir / SPARK_FIXTURE_EXPORT_MANIFEST,
        *tuple(out_dir / export.file_name for export in exports),
    )
    if any(target.exists() for target in targets):
        raise EngineFactContractError("Spark fixture export output already exists")
    for export in exports:
        _write_json(out_dir / export.file_name, export.payload)
    _write_json(out_dir / SPARK_FIXTURE_EXPORT_MANIFEST, manifest)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_label(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise EngineFactContractError("Spark evidence package fixture label is invalid")
    if not value.replace("_", "").isalnum() or value[0].isdigit():
        raise EngineFactContractError("Spark evidence package fixture label is invalid")
    return value


def _format_safe_labels(labels: object) -> str:
    if not isinstance(labels, list) or not labels:
        return "none"
    return ", ".join(str(label) for label in labels)


if __name__ == "__main__":
    raise SystemExit(main())
