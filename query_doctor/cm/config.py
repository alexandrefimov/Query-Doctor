"""Configuration helpers for bounded CM profile collection."""

from __future__ import annotations

import os
from pathlib import Path

from query_doctor.config.contract import ConfigError
from query_doctor.cm.client import DEFAULT_MAX_PROFILE_BYTES, DEFAULT_MAX_TIMESERIES_BYTES
from query_doctor.cm.metrics_catalog import DEFAULT_CM_METRICS_PROFILE
from query_doctor.cm.config_defaults import (
    DEFAULT_LIMIT,
    DEFAULT_MIN_DURATION_SEC,
    DEFAULT_RECENT_LIMIT,
    DEFAULT_RECENT_SELECT,
    DEFAULT_RECENT_WINDOW_MINUTES,
    DEFAULT_SINCE_HOURS,
    MAX_RECENT_LIMIT,
    MAX_RECENT_SELECT,
)
from query_doctor.cm.models import (
    CMHttpConfig,
    CMQueryFilters,
    CollectorConfig,
    CredentialSummary,
)
from query_doctor.cm.config_values import (
    bool_setting,
    float_setting,
    int_setting,
    load_effective_local_config,
    path_string_setting,
    resolve_optional_output_json,
    string_setting,
)
from query_doctor.cm.config_validation import (
    validate_cm_metrics_profile,
    validate_output_path,
    validate_recent_duration_bounds,
    validate_recent_limit,
    validate_recent_order,
    validate_recent_select,
)
from query_doctor.cm.timeseries import (
    DEFAULT_CM_TIMESERIES_PADDING_SEC,
    DEFAULT_MAX_TIMESERIES_POINTS,
)


REPO_DIR = Path(__file__).resolve().parents[2]


def build_config(
    args: object,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    cwd: Path | None = None,
    repo_root: Path | None = None,
) -> CollectorConfig:
    env = os.environ if env is None else env
    cwd = Path.cwd() if cwd is None else cwd
    repo_root = REPO_DIR if repo_root is None else repo_root
    config_values = load_effective_local_config(
        args.config,
        cwd=cwd,
        repo_root=repo_root,
        use_repo_default=not any(
            (args.cm_url, args.cluster, args.service, args.out, args.ca_bundle)
        ),
    )

    cm_url = string_setting(
        "cm_url",
        cli_value=args.cm_url,
        config_values=config_values,
        env_value=env.get("CM_URL"),
    )
    if not cm_url:
        raise ConfigError("Missing --cm-url or CM_URL.")

    cluster = string_setting("cluster", cli_value=args.cluster, config_values=config_values)
    if not cluster:
        raise ConfigError("Missing --cluster or config field cluster.")

    service = string_setting("service", cli_value=args.service, config_values=config_values)
    if not service:
        raise ConfigError("Missing --service or config field service.")

    out_value = string_setting("out", cli_value=args.out, config_values=config_values)
    if not out_value and args.list_recent_queries:
        out_value = str(cwd / "cm-corpus")
    if not out_value:
        raise ConfigError("Missing --out or config field out.")

    ca_bundle = path_string_setting(
        "ca_bundle",
        cli_value=args.ca_bundle,
        config_values=config_values,
        env_value=env.get("CM_CA_BUNDLE"),
    )
    out = validate_output_path(out_value, cwd=cwd, repo_root=repo_root)
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
    recent_limit = validate_recent_limit(
        int_setting(
            "recent_limit",
            cli_value=args.recent_limit,
            config_values=config_values,
            default=DEFAULT_RECENT_LIMIT,
        )
    )
    recent_select_value = args.recent_select
    if recent_select_value is None and "recent_select" in config_values:
        recent_select_value = int(config_values["recent_select"])
    recent_select = validate_recent_select(recent_select_value, recent_limit)
    recent_min_duration_sec, recent_max_duration_sec = validate_recent_duration_bounds(
        float_setting(
            "recent_min_duration_sec",
            cli_value=args.recent_min_duration_sec,
            config_values=config_values,
        ),
        float_setting(
            "recent_max_duration_sec",
            cli_value=args.recent_max_duration_sec,
            config_values=config_values,
        ),
    )
    recent_order = validate_recent_order(
        string_setting(
            "recent_order",
            cli_value=args.recent_order,
            config_values=config_values,
            default="recent",
        )
    )
    privacy_mode = bool_setting(
        "privacy_mode",
        cli_value=None,
        config_values=config_values,
        default=True,
    )

    return CollectorConfig(
        cm_url=cm_url,
        cluster=cluster,
        service=service,
        out=out,
        since_hours=int_setting(
            "since_hours",
            cli_value=args.since_hours,
            config_values=config_values,
            default=DEFAULT_SINCE_HOURS,
        ),
        limit=int_setting(
            "limit",
            cli_value=args.limit,
            config_values=config_values,
            default=DEFAULT_LIMIT,
        ),
        max_profile_bytes=int_setting(
            "max_profile_bytes",
            cli_value=args.max_profile_bytes,
            config_values=config_values,
            env_value=env.get("CM_MAX_PROFILE_BYTES"),
            default=DEFAULT_MAX_PROFILE_BYTES,
        ),
        min_duration_sec=int_setting(
            "min_duration_sec",
            cli_value=args.min_duration_sec,
            config_values=config_values,
            default=DEFAULT_MIN_DURATION_SEC,
        ),
        pool=string_setting("pool", cli_value=args.pool, config_values=config_values),
        user=string_setting("user", cli_value=args.user, config_values=config_values),
        status=string_setting(
            "status",
            cli_value=args.status,
            config_values=config_values,
            default="all",
        )
        or "all",
        query_id=args.query_id,
        query_type=string_setting(
            "query_type",
            cli_value=args.query_type,
            config_values=config_values,
        ),
        cm_username=string_setting(
            "username",
            cli_value=None,
            config_values=config_values,
            env_value=env.get("CM_USERNAME"),
        ),
        dry_run=args.dry_run,
        preflight=args.preflight,
        list_recent_queries=args.list_recent_queries,
        recent_limit=recent_limit,
        recent_select=recent_select,
        recent_window_minutes=int_setting(
            "recent_window_minutes",
            cli_value=args.recent_window_minutes,
            config_values=config_values,
            default=DEFAULT_RECENT_WINDOW_MINUTES,
        ),
        recent_min_duration_sec=recent_min_duration_sec,
        recent_max_duration_sec=recent_max_duration_sec,
        recent_order=recent_order,
        recent_output_json=resolve_optional_output_json(
            string_setting(
                "recent_output_json",
                cli_value=args.recent_output_json,
                config_values=config_values,
            ),
            cwd=cwd,
        ),
        recent_include_failed=bool_setting(
            "recent_include_failed",
            cli_value=args.recent_include_failed,
            config_values=config_values,
            default=False,
        ),
        recent_include_running=bool_setting(
            "recent_include_running",
            cli_value=args.recent_include_running,
            config_values=config_values,
            default=False,
        ),
        recent_user=string_setting(
            "recent_user",
            cli_value=args.recent_user,
            config_values=config_values,
        ),
        recent_pool=string_setting(
            "recent_pool",
            cli_value=args.recent_pool,
            config_values=config_values,
        ),
        redact=bool_setting(
            "redact",
            cli_value=args.redact,
            config_values=config_values,
            default=privacy_mode,
        ),
        redact_identifiers=bool_setting(
            "redact_identifiers",
            cli_value=args.redact_identifiers,
            config_values=config_values,
            default=privacy_mode,
        ),
        redact_hosts=bool_setting(
            "redact_hosts",
            cli_value=args.redact_hosts,
            config_values=config_values,
            default=privacy_mode,
        ),
        collect_cm_timeseries=bool(args.collect_cm_timeseries)
        if args.collect_cm_timeseries is not None
        else True,
        cm_metrics_profile=validate_cm_metrics_profile(
            string_setting(
                "cm_metrics_profile",
                cli_value=args.cm_metrics_profile,
                config_values=config_values,
                env_value=env.get("CM_METRICS_PROFILE"),
                default=DEFAULT_CM_METRICS_PROFILE,
            )
        ),
        cm_timeseries_padding_sec=int_setting(
            "cm_timeseries_padding_sec",
            cli_value=args.cm_timeseries_padding_sec,
            config_values=config_values,
            default=DEFAULT_CM_TIMESERIES_PADDING_SEC,
        ),
        max_timeseries_bytes=int_setting(
            "max_timeseries_bytes",
            cli_value=args.max_timeseries_bytes,
            config_values=config_values,
            default=DEFAULT_MAX_TIMESERIES_BYTES,
        ),
        max_timeseries_points=int_setting(
            "max_timeseries_points",
            cli_value=args.max_timeseries_points,
            config_values=config_values,
            default=DEFAULT_MAX_TIMESERIES_POINTS,
        ),
        insecure_skip_verify=bool_setting(
            "insecure_skip_verify",
            cli_value=args.insecure_skip_verify,
            config_values=config_values,
            default=False,
        ),
        ca_bundle=ca_bundle,
        credentials=credentials,
    )


def build_http_config(
    config: CollectorConfig,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> CMHttpConfig:
    env = os.environ if env is None else env
    return CMHttpConfig(
        cm_url=config.cm_url,
        username=env.get("CM_USERNAME") or config.cm_username,
        password=env.get("CM_PASSWORD"),
        token=env.get("CM_TOKEN"),
        ca_bundle=config.ca_bundle,
        verify_tls=not config.insecure_skip_verify,
    )


def cm_env_secrets(env: dict[str, str] | os._Environ[str] | None = None) -> tuple[str, ...]:
    env = os.environ if env is None else env
    return tuple(value for value in (env.get("CM_PASSWORD"), env.get("CM_TOKEN")) if value)


def build_query_filters(config: CollectorConfig) -> CMQueryFilters:
    return CMQueryFilters(
        cluster=config.cluster,
        service=config.service,
        since_hours=config.since_hours,
        limit=config.limit,
        min_duration_sec=config.min_duration_sec,
        pool=config.pool,
        user=config.user,
        status=config.status,
        query_id=config.query_id,
        query_type=config.query_type,
    )


def build_recent_query_filters(config: CollectorConfig) -> CMQueryFilters:
    return CMQueryFilters(
        cluster=config.cluster,
        service=config.service,
        since_hours=max(1, (config.recent_window_minutes + 59) // 60),
        since_minutes=config.recent_window_minutes,
        limit=config.recent_limit,
        min_duration_sec=config.recent_min_duration_sec,
        max_duration_sec=config.recent_max_duration_sec,
        server_duration_filter=True,
        pool=config.recent_pool or config.pool,
        user=config.recent_user or config.user,
        status="all",
        query_id=None,
        query_type=config.query_type,
        executing=None if config.recent_include_running else False,
    )


def build_preflight_query_filters(config: CollectorConfig) -> CMQueryFilters:
    return CMQueryFilters(
        cluster=config.cluster,
        service=config.service,
        since_hours=config.since_hours,
        limit=1,
        min_duration_sec=config.min_duration_sec,
        pool=config.pool,
        user=config.user,
        status=config.status,
        query_id=config.query_id,
        query_type=config.query_type,
    )
