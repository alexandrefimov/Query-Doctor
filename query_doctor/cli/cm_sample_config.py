"""Configuration parsing for bounded CM sample smoke validation."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from query_doctor.cli.cm_sample_reports import REPORT_MODES
from query_doctor.cli.collect_cm_profiles import (
    DEFAULT_MAX_PROFILE_BYTES,
    load_local_config,
    validate_output_path,
)


REPO_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUT = "cases/cm-corpus"
DEFAULT_LIMIT = 5
MAX_LIMIT = 10
DEFAULT_SINCE_HOURS = 24
DEFAULT_CANDIDATE_SCAN_LIMIT = 50
MAX_CANDIDATE_SCAN_LIMIT = 200
DEFAULT_HEALTHY_MAX_DURATION_SEC = 60
DEFAULT_SLOW_MIN_DURATION_SEC = 300


class SampleSmokeError(ValueError):
    """Raised for user-facing sample smoke errors."""


class SampleSmokeConfig:
    def __init__(
        self,
        *,
        cm_url: str,
        cluster: str,
        service: str,
        out: Path,
        sample: str,
        limit: int,
        since_hours: int,
        candidate_scan_limit: int,
        max_profile_bytes: int,
        max_duration_sec: int,
        min_duration_sec: int,
        min_duration_sec_explicit: bool,
        dry_run: bool,
        keep_generated: bool,
        report_mode: str,
        show_request_plan: bool,
        fail_if_healthy_has_action_cards: bool,
        include_missing_duration: bool,
        ca_bundle: str | None,
        insecure_skip_verify: bool,
        redact_identifiers: bool,
    ) -> None:
        self.cm_url = cm_url
        self.cluster = cluster
        self.service = service
        self.out = out
        self.sample = sample
        self.limit = limit
        self.since_hours = since_hours
        self.candidate_scan_limit = candidate_scan_limit
        self.max_profile_bytes = max_profile_bytes
        self.max_duration_sec = max_duration_sec
        self.min_duration_sec = min_duration_sec
        self.min_duration_sec_explicit = min_duration_sec_explicit
        self.dry_run = dry_run
        self.keep_generated = keep_generated
        self.report_mode = report_mode
        self.show_request_plan = show_request_plan
        self.fail_if_healthy_has_action_cards = fail_if_healthy_has_action_cards
        self.include_missing_duration = include_missing_duration
        self.ca_bundle = ca_bundle
        self.insecure_skip_verify = insecure_skip_verify
        self.redact_identifiers = redact_identifiers


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Optionally sample recent CM Impala query summaries, collect a bounded redacted "
            "sample, and run analyzer-only smoke validation. Defaults to dry-run."
        )
    )
    parser.add_argument("--config", required=True, help="Local non-secret CM config JSON.")
    parser.add_argument("--sample", choices=("healthy", "slow"), default="healthy")
    parser.add_argument("--limit", type=positive_int, default=DEFAULT_LIMIT)
    parser.add_argument("--since-hours", type=positive_int, default=DEFAULT_SINCE_HOURS)
    parser.add_argument("--candidate-scan-limit", type=positive_int, default=DEFAULT_CANDIDATE_SCAN_LIMIT)
    parser.add_argument("--max-profile-bytes", type=positive_int, default=DEFAULT_MAX_PROFILE_BYTES)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--max-duration-sec", type=non_negative_int, default=DEFAULT_HEALTHY_MAX_DURATION_SEC)
    parser.add_argument("--min-duration-sec", type=non_negative_int)
    parser.add_argument("--include-missing-duration", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Fetch summaries and print selected candidates only.")
    mode.add_argument("--apply", action="store_true", help="Collect selected profiles and run analyzer smoke.")
    parser.add_argument("--keep-generated", action="store_true")
    parser.add_argument("--report-mode", choices=REPORT_MODES, default="none")
    parser.add_argument(
        "--show-request-plan",
        action="store_true",
        help="Print the sanitized query-summary endpoint path and request params.",
    )
    parser.add_argument("--fail-if-healthy-has-action-cards", action="store_true")
    parser.add_argument("--ca-bundle", help="PEM CA bundle for verified CM TLS connections.")
    parser.add_argument("--insecure-skip-verify", action="store_true")
    parser.add_argument("--redact-identifiers", action="store_true")
    return parser.parse_args(argv)


def config_string(
    name: str,
    *,
    cli_value: str | None,
    config_values: dict[str, object],
    env_value: str | None = None,
    default: str | None = None,
) -> str | None:
    for value in (cli_value, config_values.get(name), env_value, default):
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None


def config_bool(
    name: str,
    *,
    cli_value: bool,
    config_values: dict[str, object],
    default: bool = False,
) -> bool:
    if cli_value:
        return True
    return bool(config_values.get(name, default))


def build_config(
    args: argparse.Namespace,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    cwd: Path | None = None,
    repo_root: Path | None = None,
) -> SampleSmokeConfig:
    env = os.environ if env is None else env
    cwd = Path.cwd() if cwd is None else cwd
    repo_root = REPO_DIR if repo_root is None else repo_root
    config_values = load_local_config(args.config, cwd=cwd)

    if args.limit > MAX_LIMIT:
        raise SampleSmokeError(f"--limit must be <= {MAX_LIMIT}.")
    if args.candidate_scan_limit > MAX_CANDIDATE_SCAN_LIMIT:
        raise SampleSmokeError(f"--candidate-scan-limit must be <= {MAX_CANDIDATE_SCAN_LIMIT}.")

    cm_url = config_string("cm_url", cli_value=None, config_values=config_values, env_value=env.get("CM_URL"))
    cluster = config_string("cluster", cli_value=None, config_values=config_values)
    service = config_string("service", cli_value=None, config_values=config_values)
    out_value = config_string("out", cli_value=args.out, config_values=config_values, default=DEFAULT_OUT)
    ca_bundle = config_string(
        "ca_bundle",
        cli_value=args.ca_bundle,
        config_values=config_values,
        env_value=env.get("CM_CA_BUNDLE"),
    )

    if not cm_url:
        raise SampleSmokeError("Missing cm_url in config or CM_URL.")
    if not cluster:
        raise SampleSmokeError("Missing cluster in config.")
    if not service:
        raise SampleSmokeError("Missing service in config.")
    if not out_value:
        raise SampleSmokeError("Missing output path.")

    return SampleSmokeConfig(
        cm_url=cm_url,
        cluster=cluster,
        service=service,
        out=validate_output_path(out_value, cwd=cwd, repo_root=repo_root),
        sample=args.sample,
        limit=args.limit,
        since_hours=args.since_hours,
        candidate_scan_limit=args.candidate_scan_limit,
        max_profile_bytes=args.max_profile_bytes,
        max_duration_sec=args.max_duration_sec,
        min_duration_sec=(
            args.min_duration_sec if args.min_duration_sec is not None else DEFAULT_SLOW_MIN_DURATION_SEC
        ),
        min_duration_sec_explicit=args.min_duration_sec is not None,
        dry_run=not args.apply,
        keep_generated=args.keep_generated,
        report_mode=args.report_mode,
        show_request_plan=args.show_request_plan,
        fail_if_healthy_has_action_cards=args.fail_if_healthy_has_action_cards,
        include_missing_duration=args.include_missing_duration,
        ca_bundle=ca_bundle,
        insecure_skip_verify=config_bool(
            "insecure_skip_verify",
            cli_value=args.insecure_skip_verify,
            config_values=config_values,
        ),
        redact_identifiers=config_bool(
            "redact_identifiers",
            cli_value=args.redact_identifiers,
            config_values=config_values,
        ),
    )
