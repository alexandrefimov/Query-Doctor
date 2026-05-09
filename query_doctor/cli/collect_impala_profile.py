"""Collect one profile from direct Impala daemon web endpoints."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from query_doctor.cm.models import CMClientError, CMQuerySummary, OutputError
from query_doctor.cm.profile_collection import write_collected_case
from query_doctor.cm.profile_parsing import (
    extract_statement_from_profile_text,
    merge_profile_summary_metadata,
)
from query_doctor.impala.profile_source import (
    DEFAULT_IMPALA_PROFILE_PORT,
    DEFAULT_IMPALA_PROFILE_SCHEME,
    DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC,
    fetch_impala_profile_text,
)
from query_doctor.impala.daemon_identity import fetch_impala_daemon_identity, identity_metadata
from query_doctor.safety.redaction import sanitize_adapter_error_message


DEFAULT_MAX_PROFILE_BYTES = 50 * 1024 * 1024


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect one Apache Impala runtime profile from configured impalad "
            "debug web endpoints. This does not execute SQL."
        )
    )
    parser.add_argument("--query-id", required=True, help="Explicit Impala query id.")
    parser.add_argument("--host", action="append", default=[], help="impalad web host or host:port.")
    parser.add_argument(
        "--port",
        type=positive_int,
        default=DEFAULT_IMPALA_PROFILE_PORT,
        help=f"impalad web port for hosts without an explicit port. Default: {DEFAULT_IMPALA_PROFILE_PORT}.",
    )
    parser.add_argument(
        "--scheme",
        choices=("http", "https"),
        default=DEFAULT_IMPALA_PROFILE_SCHEME,
        help=f"impalad web scheme. Default: {DEFAULT_IMPALA_PROFILE_SCHEME}.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=positive_int,
        default=DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC,
        help=f"Timeout per impalad profile endpoint. Default: {DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC}.",
    )
    parser.add_argument(
        "--max-profile-bytes",
        type=positive_int,
        default=DEFAULT_MAX_PROFILE_BYTES,
        help=f"Maximum profile response bytes. Default: {DEFAULT_MAX_PROFILE_BYTES}.",
    )
    parser.add_argument("--out", type=Path, required=True, help="Output corpus directory.")
    parser.add_argument("--redact", action="store_true", help="Required for real profile collection.")
    parser.add_argument("--redact-identifiers", action="store_true", help="Redact usernames and pools.")
    return parser.parse_args(argv)


def main(
    argv: list[str] | None = None,
    *,
    opener=None,
) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if not args.redact:
        print("[Impala profile collector] ERROR: real Impala collection requires --redact.", file=sys.stderr)
        return 3
    try:
        fetch_kwargs = {
            "query_id": args.query_id,
            "hosts": args.host,
            "port": args.port,
            "scheme": args.scheme,
            "timeout_sec": args.timeout_sec,
            "max_profile_bytes": args.max_profile_bytes,
        }
        if opener is not None:
            fetch_kwargs["opener"] = opener
        result = fetch_impala_profile_text(**fetch_kwargs)
        summary = CMQuerySummary(query_id=result.query_id)
        summary, profile_metadata_warnings = merge_profile_summary_metadata(summary, result.profile_text)
        profile_metadata_warnings = [
            warning.replace("CM profile text", "Impala profile text")
            for warning in profile_metadata_warnings
        ]
        if not summary.statement:
            profile_statement = extract_statement_from_profile_text(result.profile_text)
            if profile_statement:
                summary = replace(summary, statement=profile_statement)
                profile_metadata_warnings.append("Impala profile text statement metadata collected")
        identity_kwargs = {
            "hosts": args.host,
            "port": args.port,
            "scheme": args.scheme,
            "timeout_sec": args.timeout_sec,
        }
        if opener is not None:
            identity_kwargs["opener"] = opener
        try:
            identity = fetch_impala_daemon_identity(**identity_kwargs)
        except CMClientError:
            identity = None
        warnings = [
            "collected by Query Doctor direct Impala profile collector",
            "source query id preserved",
            "redaction enabled",
            "Impala daemon profile endpoint",
            f"attempted impalad profile endpoint count: {result.attempted_endpoints}",
            "analyzer/report were not run automatically",
        ]
        warnings.extend(profile_metadata_warnings)
        if identity is None:
            warnings.append("Impala daemon identity unavailable")
        case_dir = write_collected_case(
            args.out,
            summary,
            profile_digest_text=result.profile_text,
            extra_metadata={
                "profile_source": "impala_daemon",
                "profile_source_label": "Impala daemon profile endpoint",
                **identity_metadata(identity),
            },
            warnings=warnings,
            redact=True,
            redact_identifiers=args.redact_identifiers,
            redact_hosts=True,
        )
    except (CMClientError, OutputError, OSError) as exc:
        print("[Impala profile collector] Collection result: FAILED", file=sys.stderr)
        print(
            "Single-query Impala profile collection failed: "
            f"{sanitize_adapter_error_message(exc)}",
            file=sys.stderr,
        )
        return 4

    print("[Impala profile collector] Collection result: OK")
    print("Collected count: 1")
    print(f"Output case directory: {case_dir}")
    print(f"Profile text length: {len(result.profile_text)}")
    print("Redaction: enabled")
    print(f"Max profile bytes: {args.max_profile_bytes}")
    print("Raw provider output was not printed to stdout.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
