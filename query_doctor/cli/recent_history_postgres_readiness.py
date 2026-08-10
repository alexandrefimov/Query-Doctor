"""CLI for raw-free Recent history Postgres readiness checks."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Mapping, Sequence

from query_doctor.recent.batch_config import DEFAULT_RECENT_HISTORY_POSTGRES_DSN_ENV
from query_doctor.recent.postgres_history_store import ConnectFactory
from query_doctor.recent.postgres_readiness import (
    STATUS_READY,
    format_recent_history_postgres_readiness,
    readiness_payload_json,
    recent_history_postgres_readiness,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check raw-free Recent history Postgres readiness. The command reads the DSN "
            "only from an environment variable, does not print the DSN value, and does not "
            "contact query engines, execute SQL against engines, or run profile collection."
        )
    )
    parser.add_argument(
        "--postgres-dsn-env",
        default=DEFAULT_RECENT_HISTORY_POSTGRES_DSN_ENV,
        help="Environment variable name containing the Postgres DSN.",
    )
    parser.add_argument("--json", action="store_true", help="Print raw-free JSON.")
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Write raw-free readiness summary JSON.",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit non-zero unless readiness status is ready.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    connect: ConnectFactory | None = None,
) -> int:
    args = parse_args(argv)
    effective_env = dict(os.environ if env is None else env)
    result = recent_history_postgres_readiness(
        dsn_env=args.postgres_dsn_env,
        env=effective_env,
        connect=connect,
    )
    payload = result.payload()
    if args.summary_json:
        try:
            args.summary_json.write_text(readiness_payload_json(payload), encoding="utf-8")
        except OSError:
            print(
                "[Recent history Postgres readiness] ERROR: could not write summary JSON",
                file=sys.stderr,
            )
            return 2
    if args.json:
        sys.stdout.write(readiness_payload_json(payload))
    else:
        sys.stdout.write(format_recent_history_postgres_readiness(payload))
    if args.fail_on_warning and payload.get("status") != STATUS_READY:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
