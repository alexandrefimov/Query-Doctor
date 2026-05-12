#!/usr/bin/env python3
"""CLI for bounded Cloudera Manager event summaries."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from query_doctor.cluster.event_context import (
    build_cluster_event_context,
    write_cluster_event_context,
)
from query_doctor.cluster.context import build_cluster_context, write_cluster_context
from query_doctor.cm.events import (
    CM_EVENT_CATEGORY_CHOICES,
    CM_EVENT_SEVERITY_CHOICES,
    DEFAULT_CM_EVENT_SEVERITIES,
    DEFAULT_CM_EVENTS_MAX_EVENTS,
    DEFAULT_CM_EVENTS_WINDOW_MINUTES,
    MAX_CM_EVENTS_MAX_EVENTS,
    MAX_CM_EVENTS_WINDOW_MINUTES,
    CMEventsRequest,
    build_cm_events_request,
    collect_cm_events_context,
)
from query_doctor.cli.collect_cm_profiles import (
    CMHttpClient,
    CMHttpClientFactory,
    CMHttpConfig,
    CMClientError,
    ConfigError,
    CredentialSummary,
    bool_setting,
    cm_env_secrets,
    int_setting,
    load_effective_local_config,
    path_string_setting,
    sanitize_adapter_error_message,
    sanitize_cm_url_for_display,
    sanitize_text_for_log,
    string_setting,
)

REPO_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CMEventsCliConfig:
    cm_url: str
    cluster: str | None
    service: str | None
    cm_username: str | None
    ca_bundle: str | None
    insecure_skip_verify: bool
    window_minutes: int
    from_time: str | None
    to_time: str | None
    max_events: int
    severities: tuple[str, ...]
    categories: tuple[str, ...]
    alerts_only: bool
    output_json: Path | None
    cluster_event_context_json: Path | None
    cluster_context_json: Path | None
    dry_run: bool
    credentials: CredentialSummary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Cloudera Manager Events summary collector for future "
            "Cluster Doctor diagnostics. Emits bounded normalized summaries only; "
            "raw event payloads and log lines are not displayed."
        )
    )
    parser.add_argument(
        "--config",
        help="Local Query Doctor config with non-secret CM settings.",
    )
    parser.add_argument("--cm-url", help="Cloudera Manager base URL. May also come from CM_URL.")
    parser.add_argument("--cluster", help="Optional cluster scope label from local config or CLI.")
    parser.add_argument("--service", help="Optional CM service scope for the event query.")
    parser.add_argument(
        "--no-service-scope",
        action="store_true",
        help="Ignore service from local config and query the selected CM event window cluster-wide.",
    )
    parser.add_argument(
        "--window-minutes",
        type=positive_int,
        help=f"Look back this many minutes. Default: {DEFAULT_CM_EVENTS_WINDOW_MINUTES}.",
    )
    parser.add_argument(
        "--from-time",
        help="Explicit CM event window start, formatted as YYYY-MM-DDTHH:MM:SSZ.",
    )
    parser.add_argument(
        "--to-time",
        help="Explicit CM event window end, formatted as YYYY-MM-DDTHH:MM:SSZ.",
    )
    parser.add_argument(
        "--max-events",
        type=positive_int,
        help=f"Maximum CM events to summarize. Default: {DEFAULT_CM_EVENTS_MAX_EVENTS}; hard cap: {MAX_CM_EVENTS_MAX_EVENTS}.",
    )
    parser.add_argument(
        "--severity",
        action="append",
        choices=CM_EVENT_SEVERITY_CHOICES,
        help=(
            "CM event severity to include. May be repeated. "
            "Default: critical, important, warning, informational."
        ),
    )
    parser.add_argument(
        "--category",
        action="append",
        choices=CM_EVENT_CATEGORY_CHOICES,
        help="Optional CM event category allowlist. May be repeated.",
    )
    parser.add_argument(
        "--alerts-only",
        action="store_true",
        default=None,
        help="Restrict the CM event query to alert events.",
    )
    parser.add_argument(
        "--include-non-alert-events",
        action="store_false",
        dest="alerts_only",
        help="Include non-alert events when local config later enables alerts-only behavior.",
    )
    parser.add_argument(
        "--output-json",
        help="Optional path for sanitized normalized event summary JSON.",
    )
    parser.add_argument(
        "--cluster-event-context-json",
        help=(
            "Optional path for stable Cluster Doctor event-context JSON. "
            "This writes a raw-free schema artifact derived from the CM event summary."
        ),
    )
    parser.add_argument(
        "--cluster-context-json",
        help=(
            "Optional path for aggregate Cluster Doctor context JSON. "
            "This writes a raw-free schema artifact derived from available safe contexts."
        ),
    )
    parser.add_argument(
        "--ca-bundle",
        help="PEM CA bundle for verified CM TLS connections. May also come from CM_CA_BUNDLE.",
    )
    parser.add_argument(
        "--insecure-skip-verify",
        action="store_true",
        default=None,
        help="UNSAFE: disable TLS certificate verification for CM API calls.",
    )
    parser.add_argument(
        "--verify-tls",
        action="store_false",
        dest="insecure_skip_verify",
        help="Use TLS certificate verification when a local config disables it.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print a sanitized plan only. No CM API calls or output files are created.",
    )
    return parser.parse_args(argv)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_config(
    args: argparse.Namespace,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    cwd: Path | None = None,
    repo_root: Path | None = None,
) -> CMEventsCliConfig:
    env = os.environ if env is None else env
    cwd = Path.cwd() if cwd is None else cwd
    repo_root = REPO_DIR if repo_root is None else repo_root
    config_values = load_effective_local_config(
        args.config,
        cwd=cwd,
        repo_root=repo_root,
        use_repo_default=not any((args.cm_url, args.cluster, args.service, args.ca_bundle)),
    )
    cm_url = string_setting(
        "cm_url",
        cli_value=args.cm_url,
        config_values=config_values,
        env_value=env.get("CM_URL"),
    )
    if not cm_url:
        raise ConfigError("Missing --cm-url or CM_URL.")
    window_minutes = int_setting(
        "cm_events_window_minutes",
        cli_value=args.window_minutes,
        config_values={},
        default=DEFAULT_CM_EVENTS_WINDOW_MINUTES,
    )
    if window_minutes > MAX_CM_EVENTS_WINDOW_MINUTES:
        raise ConfigError(f"--window-minutes must be <= {MAX_CM_EVENTS_WINDOW_MINUTES}.")
    from_time = args.from_time.strip() if args.from_time else None
    to_time = args.to_time.strip() if args.to_time else None
    if bool(from_time) != bool(to_time):
        raise ConfigError("--from-time and --to-time must be provided together.")
    max_events = int_setting(
        "cm_events_max_events",
        cli_value=args.max_events,
        config_values={},
        default=DEFAULT_CM_EVENTS_MAX_EVENTS,
    )
    if max_events > MAX_CM_EVENTS_MAX_EVENTS:
        raise ConfigError(f"--max-events must be <= {MAX_CM_EVENTS_MAX_EVENTS}.")
    ca_bundle = path_string_setting(
        "ca_bundle",
        cli_value=args.ca_bundle,
        config_values=config_values,
        env_value=env.get("CM_CA_BUNDLE"),
    )
    output_json = resolve_optional_output_json(
        args.output_json, cwd=cwd, option_name="--output-json"
    )
    cluster_event_context_json = resolve_optional_output_json(
        args.cluster_event_context_json,
        cwd=cwd,
        option_name="--cluster-event-context-json",
    )
    cluster_context_json = resolve_optional_output_json(
        args.cluster_context_json,
        cwd=cwd,
        option_name="--cluster-context-json",
    )
    credentials = CredentialSummary(
        has_username=bool(
            string_setting(
                "username",
                cli_value=None,
                config_values=config_values,
                env_value=env.get("CM_USERNAME"),
            )
        ),
        has_password=bool(env.get("CM_PASSWORD")),
        has_token=bool(env.get("CM_TOKEN")),
    )
    return CMEventsCliConfig(
        cm_url=cm_url,
        cluster=string_setting("cluster", cli_value=args.cluster, config_values=config_values),
        service=None
        if args.no_service_scope
        else string_setting("service", cli_value=args.service, config_values=config_values),
        cm_username=string_setting(
            "username",
            cli_value=None,
            config_values=config_values,
            env_value=env.get("CM_USERNAME"),
        ),
        ca_bundle=ca_bundle,
        insecure_skip_verify=bool_setting(
            "insecure_skip_verify",
            cli_value=args.insecure_skip_verify,
            config_values=config_values,
            default=False,
        ),
        window_minutes=window_minutes,
        from_time=from_time,
        to_time=to_time,
        max_events=max_events,
        severities=tuple(args.severity or DEFAULT_CM_EVENT_SEVERITIES),
        categories=tuple(args.category or ()),
        alerts_only=bool(args.alerts_only) if args.alerts_only is not None else False,
        output_json=output_json,
        cluster_event_context_json=cluster_event_context_json,
        cluster_context_json=cluster_context_json,
        dry_run=bool(args.dry_run),
        credentials=credentials,
    )


def resolve_optional_output_json(value: str | None, *, cwd: Path, option_name: str) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = cwd / path
    if path.exists() and path.is_dir():
        raise ConfigError(f"{option_name} must point to a file, not a directory.")
    return path


def build_http_config(
    config: CMEventsCliConfig,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> CMHttpConfig:
    env = os.environ if env is None else env
    if not (
        env.get("CM_TOKEN")
        or (env.get("CM_PASSWORD") and (env.get("CM_USERNAME") or config.cm_username))
    ):
        raise ConfigError("CM Events collection requires CM_TOKEN or CM_USERNAME/CM_PASSWORD.")
    return CMHttpConfig(
        cm_url=config.cm_url,
        username=env.get("CM_USERNAME") or config.cm_username,
        password=env.get("CM_PASSWORD"),
        token=env.get("CM_TOKEN"),
        ca_bundle=config.ca_bundle,
        verify_tls=not config.insecure_skip_verify,
    )


def cm_events_request_from_config(config: CMEventsCliConfig) -> CMEventsRequest:
    return CMEventsRequest(
        window_minutes=config.window_minutes,
        max_events=config.max_events,
        service=config.service,
        severities=config.severities,
        categories=config.categories,
        alerts_only=config.alerts_only,
        from_time=config.from_time,
        to_time=config.to_time,
    )


def print_dry_run_plan(config: CMEventsCliConfig) -> None:
    print("[CM events] Dry-run plan")
    print(f"CM URL: {sanitize_cm_url_for_display(config.cm_url)}")
    print(f"Cluster scope: {'configured' if config.cluster else 'not set'}")
    print(f"Service scope: {'configured' if config.service else 'not set'}")
    print(f"Window minutes: {config.window_minutes}")
    if config.from_time and config.to_time:
        print("Explicit event window: configured")
    print(f"Max events: {config.max_events}")
    print("Severity filter: " + ", ".join(config.severities))
    print("Category filter: " + (", ".join(config.categories) if config.categories else "<any>"))
    print(f"Alerts only: {'yes' if config.alerts_only else 'no'}")
    print(tls_plan_line(config))
    print(ca_bundle_plan_line(config))
    print(f"Credentials: {config.credentials.display()}")
    if config.output_json:
        print(f"Sanitized JSON output: {config.output_json}")
    if config.cluster_event_context_json:
        print(f"Cluster event context output: {config.cluster_event_context_json}")
    if config.cluster_context_json:
        print(f"Cluster context output: {config.cluster_context_json}")
    print("No CM API calls are performed in dry-run mode.")
    print("No raw event payloads, log lines, hostnames, paths, query text, or reports are written.")


def run_cm_events(
    config: CMEventsCliConfig,
    client: CMHttpClient,
    *,
    secrets: tuple[str, ...] = (),
) -> int:
    request = cm_events_request_from_config(config)
    path, _ = build_cm_events_request(request)
    context = collect_cm_events_context(client, request)
    cluster_event_context = build_cluster_event_context(context)
    cluster_context = build_cluster_context(event_context=cluster_event_context)

    print("[CM events] Summary")
    print(f"CM URL: {sanitize_cm_url_for_display(config.cm_url)}")
    print(f"Endpoint: {path}")
    print(f"Cluster scope: {'configured' if config.cluster else 'not set'}")
    print(f"Service scope: {'configured' if config.service else 'not set'}")
    print(f"Window minutes: {config.window_minutes}")
    if config.from_time and config.to_time:
        print("Explicit event window: configured")
    print(f"Max events: {config.max_events}")
    print(f"Availability: {context.get('status')}")
    print(f"Product status: {context.get('product_status')}")
    print(f"Events summarized: {context.get('event_count', 0)}")
    print(f"Alerts summarized: {context.get('alert_count', 0)}")

    severity_counts = context.get("severity_counts")
    if isinstance(severity_counts, dict) and severity_counts:
        print("Severity counts:")
        for key, value in sorted(severity_counts.items()):
            print(f"  - {key}: {value}")
    signal_counts = context.get("signal_counts")
    if isinstance(signal_counts, dict) and signal_counts:
        print("Signals:")
        for key, value in sorted(signal_counts.items()):
            print(f"  - {key}: observed count={value}")
    limitations = context.get("limitations")
    if isinstance(limitations, list) and limitations:
        print("Limitations:")
        for item in limitations:
            print(f"  - {sanitize_text_for_log(item, secrets=secrets)}")

    if config.output_json:
        config.output_json.parent.mkdir(parents=True, exist_ok=True)
        config.output_json.write_text(
            json.dumps(context, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Sanitized JSON written: {config.output_json}")
    if config.cluster_event_context_json:
        write_cluster_event_context(config.cluster_event_context_json, cluster_event_context)
        print(f"Cluster event context JSON written: {config.cluster_event_context_json}")
    if config.cluster_context_json:
        write_cluster_context(config.cluster_context_json, cluster_context)
        print(f"Cluster context JSON written: {config.cluster_context_json}")

    print(
        "No raw CM JSON, raw event payloads, raw log lines, hostnames, paths, query text, or reports were written."
    )
    return 0 if context.get("available") else 4


def tls_plan_line(config: CMEventsCliConfig) -> str:
    if config.insecure_skip_verify:
        return "TLS verification: disabled by --insecure-skip-verify (UNSAFE)"
    return "TLS verification: enabled"


def ca_bundle_plan_line(config: CMEventsCliConfig) -> str:
    if config.insecure_skip_verify:
        return "CA bundle: ignored because TLS verification is disabled"
    if config.ca_bundle:
        return f"CA bundle: {config.ca_bundle}"
    return "CA bundle: system default trust store"


def main(
    argv: list[str] | None = None,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    client_factory: CMHttpClientFactory | None = None,
) -> int:
    args = parse_args(argv)
    try:
        config = build_config(args, env=env)
    except ConfigError as exc:
        print(f"[CM events] ERROR: {exc}", file=sys.stderr)
        return 2

    if config.dry_run:
        print_dry_run_plan(config)
        return 0

    try:
        http_config = build_http_config(config, env=env)
        client = (client_factory or CMHttpClient)(http_config)
    except ConfigError as exc:
        print(f"[CM events] ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        return run_cm_events(config, client, secrets=cm_env_secrets(env))
    except CMClientError as exc:
        print(
            "[CM events] Collection failed: "
            f"{sanitize_adapter_error_message(exc, secrets=cm_env_secrets(env))}",
            file=sys.stderr,
        )
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
