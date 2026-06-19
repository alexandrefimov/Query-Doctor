#!/usr/bin/env python3
"""Audit local Trino Beta web readiness without contacting Trino."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    ascii_json_artifact_text,
    output_overlaps_inputs_error,
    write_ascii_json_artifact,
)
from query_doctor.trino.web_beta_readiness import (  # noqa: E402
    audit_trino_web_beta_readiness,
    format_trino_web_beta_readiness,
    trino_web_beta_readiness_summary_payload,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check local Trino Beta web readiness from config and source contracts only. "
            "The audit performs no coordinator network read and prints no configured values."
        )
    )
    parser.add_argument("--config", help="Local Query Doctor config path.")
    parser.add_argument(
        "--require-query-id",
        action="store_true",
        help="Fail unless at least one source is ready for Trino Beta One Query ID.",
    )
    parser.add_argument(
        "--require-recent",
        action="store_true",
        help="Fail unless at least one source is ready for Trino Beta Recent.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the raw-free machine summary JSON to stdout.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Write the raw-free machine summary JSON artifact.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = Path(args.config) if args.config else None
    result = audit_trino_web_beta_readiness(
        config_path,
        cwd=Path.cwd(),
        require_query_id=args.require_query_id,
        require_recent=args.require_recent,
    )
    payload = trino_web_beta_readiness_summary_payload(result)

    overlap_error = output_overlaps_inputs_error(
        args.summary_json,
        (config_path,),
        message="summary output must not overwrite the input config",
    )
    if overlap_error:
        print(f"Trino web beta readiness: rejected: {overlap_error}", file=sys.stderr)
        return 2
    if args.summary_json is not None:
        write_ascii_json_artifact(args.summary_json, payload)

    if args.json:
        print(ascii_json_artifact_text(payload), end="")
    else:
        print(format_trino_web_beta_readiness(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
