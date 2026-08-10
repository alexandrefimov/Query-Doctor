"""CLI entry point for raw-free web deployment readiness summaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Sequence

from query_doctor.cli import collect_cm_profiles as cm_collector
from query_doctor.cli.web import build_validated_web_runtime_settings
from query_doctor.web.deployment_readiness import (
    CHECK_READY,
    deployment_readiness_payload,
    format_deployment_readiness_text,
)
from query_doctor.web.models import WebError
from query_doctor.web.server_args import build_parser


def parse_args(argv: Sequence[str] | None = None):
    parser = build_parser(
        description=(
            "Print a raw-free Query Doctor web deployment readiness summary. "
            "This command reads the same startup settings as query-doctor-web but does not "
            "start the server, run diagnostics, contact engines, execute SQL, or call LLMs."
        )
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable raw-free JSON.",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit non-zero unless the deployment readiness status is ready.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings, startup_warnings = build_validated_web_runtime_settings(args, Path.cwd())
    except WebError as exc:
        print(f"[Query Doctor deployment readiness] ERROR: {exc}", file=sys.stderr)
        return 2
    except cm_collector.ConfigError as exc:
        print(f"[Query Doctor deployment readiness] ERROR: {exc}", file=sys.stderr)
        return 2
    payload = deployment_readiness_payload(settings)
    if startup_warnings:
        payload["startup_warnings"] = len(startup_warnings)
    if args.json:
        sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    else:
        sys.stdout.write(format_deployment_readiness_text(payload))
    if args.fail_on_warning and payload.get("status") != CHECK_READY:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
