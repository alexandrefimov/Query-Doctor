"""Batch scan parsing and command construction for the local web UI."""

from __future__ import annotations

from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from query_doctor.cli.commands import command_prefix
from query_doctor.web.cluster_selection import (
    require_cm_cluster_settings,
    selected_cluster_key_from_mapping,
    settings_for_cluster_key,
)
from query_doctor.web.command_builders import (
    append_web_cm_args,
    append_web_impala_profile_args,
    append_web_metadata_args,
    display_float,
)
from query_doctor.web.config import (
    impala_profile_source_configured,
    load_web_local_config,
    metadata_configured,
    optional_config_bool,
    optional_config_int,
)
from query_doctor.web.form_helpers import (
    first_form_value,
    parse_cm_metrics_profile,
    parse_non_negative_form_float,
    parse_non_negative_form_int,
    parse_optional_non_negative_form_float,
    parse_positive_form_int,
)
from query_doctor.web.models import (
    BATCH_CM_INSPECT_LIMIT_MAX,
    WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT,
    WEB_CM_EVENTS_MAX_EVENTS_DEFAULT,
    WEB_CM_TIMESERIES_TOP_LIMIT_DEFAULT,
    BatchRunConfig,
    WebError,
    WebSettings,
    batch_output_dir,
    batch_progress_path,
)


BATCH_ORDER_VALUES = {"recent", "duration-desc", "duration-asc", "recent-duration-desc", "status-priority"}
WEB_RECENT_TRIAGE_PROFILE_LIMIT_DEFAULT = 100
BATCH_METADATA_TOP_LIMIT_MAX = 200
BATCH_CM_TIMESERIES_TOP_LIMIT_MAX = 200
BATCH_CM_EVENTS_MAX_EVENTS_MAX = 200
BATCH_JOBS_MAX = 100
BATCH_FULL_JOBS_MAX = 4
BATCH_CM_JOBS_MAX = 100
BATCH_METADATA_JOBS_MAX = 5
WEB_RUNNING_SCAN_WINDOW_MINUTES = 120
WEB_RUNNING_CM_INSPECT_LIMIT_DEFAULT = 500
RECENT_SCAN_TIMEZONE = ZoneInfo("Europe/Moscow")
RECENT_SCAN_LOOKBACK_DAYS = 2
RECENT_SCAN_BUCKET_HOURS = 1


def default_recent_scan_bucket(now: datetime | None = None) -> tuple[str, int]:
    current = now.astimezone(RECENT_SCAN_TIMEZONE) if now else datetime.now(RECENT_SCAN_TIMEZONE)
    bucket = current.replace(minute=0, second=0, microsecond=0)
    return bucket.date().isoformat(), bucket.hour


def allowed_recent_scan_dates(now: datetime | None = None) -> set[str]:
    current = now.astimezone(RECENT_SCAN_TIMEZONE).date() if now else datetime.now(RECENT_SCAN_TIMEZONE).date()
    return {(current - timedelta(days=days)).isoformat() for days in range(RECENT_SCAN_LOOKBACK_DAYS + 1)}


def parse_recent_scan_window(form: dict[str, list[str]]) -> tuple[str, int, str, str]:
    default_date, default_hour = default_recent_scan_bucket()
    scan_date = first_form_value(form, "scan_date") or default_date
    scan_hour_text = first_form_value(form, "scan_hour") or str(default_hour)
    if scan_date not in allowed_recent_scan_dates():
        raise WebError("Scan date must be today or one of the previous two days.")
    try:
        parsed_date = date.fromisoformat(scan_date)
    except ValueError as exc:
        raise WebError("Scan date must be formatted as YYYY-MM-DD.") from exc
    try:
        scan_hour = int(scan_hour_text)
    except ValueError as exc:
        raise WebError("Scan hour must be an integer from 0 to 23.") from exc
    if scan_hour < 0 or scan_hour > 23:
        raise WebError("Scan hour must be an integer from 0 to 23.")
    latest_date, latest_hour = default_recent_scan_bucket()
    if scan_date > latest_date or (scan_date == latest_date and scan_hour > latest_hour):
        raise WebError("Scan hour must not be in the future.")
    start_local = datetime.combine(parsed_date, datetime_time(scan_hour), tzinfo=RECENT_SCAN_TIMEZONE)
    end_local = start_local + timedelta(hours=RECENT_SCAN_BUCKET_HOURS)
    from_time = start_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_time = end_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return scan_date, scan_hour, from_time, to_time


def parse_batch_run_config(
    form: dict[str, list[str]],
    *,
    settings: WebSettings | None = None,
    default_metadata_top_limit: int = WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT,
    default_parallelism: int = 50,
) -> BatchRunConfig:
    cluster_key = (
        selected_cluster_key_from_mapping(form, settings)
        if settings is not None
        else first_form_value(form, "cluster_key")
    )
    selected_settings = settings_for_cluster_key(settings, cluster_key) if settings is not None else None
    local_config = _local_config_values(settings)
    scan_date, scan_hour, from_time, to_time = parse_recent_scan_window(form)
    recent_window_minutes = RECENT_SCAN_BUCKET_HOURS * 60
    cm_inspect_limit = BATCH_CM_INSPECT_LIMIT_MAX
    triage_profile_limit = WEB_RECENT_TRIAGE_PROFILE_LIMIT_DEFAULT
    metadata_top_limit = parse_non_negative_form_int(
        form, "metadata_top_limit", default=default_metadata_top_limit, maximum=BATCH_METADATA_TOP_LIMIT_MAX
    )
    min_duration_sec = parse_optional_non_negative_form_float(form, "min_duration_sec")
    max_duration_text = first_form_value(form, "max_duration_sec")
    max_duration_sec = None
    if max_duration_text:
        max_duration_sec = parse_non_negative_form_float(form, "max_duration_sec", default=0.0)
        if min_duration_sec is not None and max_duration_sec < min_duration_sec:
            raise WebError("max_duration_sec must be greater than or equal to min_duration_sec.")
    order = first_form_value(form, "order") or "duration-desc"
    if order not in BATCH_ORDER_VALUES:
        raise WebError("Order must be one of: recent, duration-desc, duration-asc, recent-duration-desc, status-priority.")
    parallelism_text = first_form_value(form, "parallelism")
    if not parallelism_text and first_form_value(form, "jobs"):
        parallelism_text = first_form_value(form, "jobs")
    if not parallelism_text and first_form_value(form, "cm_jobs"):
        parallelism_text = first_form_value(form, "cm_jobs")
    parallelism_form = {"parallelism": [parallelism_text]} if parallelism_text else {}
    parallelism = parse_positive_form_int(
        parallelism_form,
        "parallelism",
        default=default_parallelism,
        maximum=min(BATCH_CM_JOBS_MAX, BATCH_JOBS_MAX),
    )
    metadata_jobs = parse_positive_form_int(form, "metadata_jobs", default=5, maximum=BATCH_METADATA_JOBS_MAX)
    user = first_form_value(form, "user")
    pool = first_form_value(form, "pool")
    collect_cm_events = _config_bool(
        local_config,
        "recent_collect_cm_events",
        fallback=True,
    )
    cm_events_max_events = parse_positive_form_int(
        form,
        "cm_events_max_events",
        default=_config_int(
            local_config,
            "recent_cm_events_max_events",
            fallback=WEB_CM_EVENTS_MAX_EVENTS_DEFAULT,
        ),
        maximum=BATCH_CM_EVENTS_MAX_EVENTS_MAX,
    )
    collect_cm_timeseries = _config_bool(
        local_config,
        "recent_collect_cm_timeseries",
        "collect_cm_timeseries",
        fallback=True,
    )
    cm_metrics_profile = (
        selected_settings.cm_metrics_profile
        if selected_settings is not None
        else parse_cm_metrics_profile(form)
    )
    cm_timeseries_top_limit = parse_non_negative_form_int(
        form,
        "cm_timeseries_top_limit",
        default=_config_int(
            local_config,
            "recent_cm_timeseries_top_limit",
            fallback=WEB_CM_TIMESERIES_TOP_LIMIT_DEFAULT,
        ),
        maximum=BATCH_CM_TIMESERIES_TOP_LIMIT_MAX,
    )
    return BatchRunConfig(
        recent_window_minutes=recent_window_minutes,
        scan_date=scan_date,
        scan_hour=scan_hour,
        cluster_key=cluster_key or "",
        from_time=from_time,
        to_time=to_time,
        cm_inspect_limit=cm_inspect_limit,
        triage_profile_limit=triage_profile_limit,
        metadata_top_limit=metadata_top_limit,
        min_duration_sec=min_duration_sec,
        max_duration_sec=max_duration_sec,
        order=order,
        parallelism=parallelism,
        cm_jobs=parallelism,
        jobs=parallelism,
        metadata_jobs=metadata_jobs,
        user=user,
        pool=pool,
        query_type="",
        include_failed=True,
        include_running=False,
        collect_cm_events=collect_cm_events,
        cm_events_max_events=cm_events_max_events,
        collect_cm_timeseries=collect_cm_timeseries,
        cm_metrics_profile=cm_metrics_profile,
        cm_timeseries_top_limit=cm_timeseries_top_limit,
    )


def parse_running_run_config(
    form: dict[str, list[str]],
    *,
    settings: WebSettings | None = None,
    default_metadata_top_limit: int = WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT,
    default_parallelism: int = 50,
) -> BatchRunConfig:
    cluster_key = (
        selected_cluster_key_from_mapping(form, settings)
        if settings is not None
        else first_form_value(form, "cluster_key")
    )
    selected_settings = settings_for_cluster_key(settings, cluster_key) if settings is not None else None
    local_config = _local_config_values(settings)
    cm_inspect_limit = WEB_RUNNING_CM_INSPECT_LIMIT_DEFAULT
    metadata_top_limit = parse_non_negative_form_int(
        form, "metadata_top_limit", default=default_metadata_top_limit, maximum=BATCH_METADATA_TOP_LIMIT_MAX
    )
    min_duration_sec = parse_optional_non_negative_form_float(form, "min_duration_sec")
    parallelism_text = first_form_value(form, "parallelism")
    parallelism_form = {"parallelism": [parallelism_text]} if parallelism_text else {}
    parallelism = parse_positive_form_int(
        parallelism_form,
        "parallelism",
        default=default_parallelism,
        maximum=min(BATCH_CM_JOBS_MAX, BATCH_JOBS_MAX),
    )
    metadata_jobs = parse_positive_form_int(form, "metadata_jobs", default=5, maximum=BATCH_METADATA_JOBS_MAX)
    cm_events_max_events = parse_positive_form_int(
        form,
        "cm_events_max_events",
        default=_config_int(
            local_config,
            "recent_cm_events_max_events",
            fallback=WEB_CM_EVENTS_MAX_EVENTS_DEFAULT,
        ),
        maximum=BATCH_CM_EVENTS_MAX_EVENTS_MAX,
    )
    cm_metrics_profile = (
        selected_settings.cm_metrics_profile
        if selected_settings is not None
        else parse_cm_metrics_profile(form)
    )
    cm_timeseries_top_limit = parse_non_negative_form_int(
        form,
        "cm_timeseries_top_limit",
        default=_config_int(
            local_config,
            "recent_cm_timeseries_top_limit",
            fallback=WEB_CM_TIMESERIES_TOP_LIMIT_DEFAULT,
        ),
        maximum=BATCH_CM_TIMESERIES_TOP_LIMIT_MAX,
    )
    return BatchRunConfig(
        recent_window_minutes=WEB_RUNNING_SCAN_WINDOW_MINUTES,
        cluster_key=cluster_key or "",
        from_time=None,
        to_time=None,
        cm_inspect_limit=cm_inspect_limit,
        triage_profile_limit=cm_inspect_limit,
        metadata_top_limit=metadata_top_limit,
        min_duration_sec=min_duration_sec,
        max_duration_sec=None,
        order="status-priority",
        parallelism=parallelism,
        cm_jobs=parallelism,
        jobs=parallelism,
        metadata_jobs=metadata_jobs,
        user=first_form_value(form, "user"),
        pool=first_form_value(form, "pool"),
        query_type="",
        include_failed=False,
        include_running=True,
        only_running=True,
        collect_cm_events=True,
        cm_events_max_events=cm_events_max_events,
        collect_cm_timeseries=True,
        cm_metrics_profile=cm_metrics_profile,
        cm_timeseries_top_limit=cm_timeseries_top_limit,
    )


def _local_config_values(settings: WebSettings | None) -> dict[str, object]:
    if settings is None:
        return {}
    try:
        return load_web_local_config(settings.config, cwd=Path.cwd())
    except (OSError, ValueError, TypeError):
        return {}


def _config_bool(
    config_values: dict[str, object],
    primary_key: str,
    secondary_key: str | None = None,
    *,
    fallback: bool,
) -> bool:
    value = optional_config_bool(config_values, primary_key)
    if value is None and secondary_key is not None:
        value = optional_config_bool(config_values, secondary_key)
    return fallback if value is None else value


def _config_int(config_values: dict[str, object], key: str, *, fallback: int) -> int:
    value = optional_config_int(config_values, key)
    return fallback if value is None else value


def form_values_from_form(form: dict[str, list[str]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for name in (
        "scan_target",
        "scan_date",
        "scan_hour",
        "cluster_key",
        "metadata_top_limit",
        "min_duration_sec",
        "max_duration_sec",
        "order",
        "parallelism",
        "metadata_jobs",
        "collect_cm_events",
        "cm_events_max_events",
        "collect_cm_timeseries",
        "cm_metrics_profile",
        "cm_timeseries_top_limit",
        "user",
        "pool",
    ):
        values[name] = first_form_value(form, name)
    if not values.get("parallelism"):
        values["parallelism"] = first_form_value(form, "jobs") or first_form_value(form, "cm_jobs")
    return values


def form_values_from_config(config: BatchRunConfig) -> dict[str, object]:
    return {
        "scan_target": "running" if config.only_running else "finished",
        "scan_date": config.scan_date,
        "scan_hour": str(config.scan_hour),
        "cluster_key": config.cluster_key,
        "metadata_top_limit": str(config.metadata_top_limit),
        "min_duration_sec": "" if config.min_duration_sec is None else display_float(config.min_duration_sec),
        "max_duration_sec": "" if config.max_duration_sec is None else display_float(config.max_duration_sec),
        "order": config.order,
        "parallelism": str(config.parallelism),
        "metadata_jobs": str(config.metadata_jobs),
        "collect_cm_events": config.collect_cm_events,
        "cm_events_max_events": str(config.cm_events_max_events),
        "collect_cm_timeseries": config.collect_cm_timeseries,
        "cm_metrics_profile": config.cm_metrics_profile,
        "cm_timeseries_top_limit": str(config.cm_timeseries_top_limit),
        "user": config.user,
        "pool": config.pool,
    }


def validate_batch_config_for_settings(config: BatchRunConfig, settings: WebSettings) -> None:
    settings = settings_for_cluster_key(settings, config.cluster_key)
    if settings.query_profile_source == "impala":
        if not impala_profile_source_configured(settings):
            raise WebError("Selected cluster is missing impalad host settings for direct Impala discovery.")
    elif settings.clusters or any((settings.cm_url, settings.cm_cluster, settings.cm_service)):
        require_cm_cluster_settings(settings)
    if config.metadata_top_limit > 0:
        if not metadata_configured(settings):
            raise WebError("Metadata collection is not configured for this web session. Restart with metadata options or disable metadata in config.")
        if settings.metadata_ca_cert and not settings.metadata_ssl:
            raise WebError("--metadata-ca-cert requires --metadata-ssl for web batch metadata.")


def build_batch_command(job_id: str, config: BatchRunConfig, settings: WebSettings) -> tuple[list[str], Path]:
    settings = settings_for_cluster_key(settings, config.cluster_key)
    validate_batch_config_for_settings(config, settings)
    out_dir = batch_output_dir(job_id)
    progress_path = batch_progress_path(job_id)
    metadata_enabled = config.metadata_top_limit > 0
    metadata_mode = "on" if metadata_enabled else "off"
    if config.only_running:
        from_time = to_time = None
    elif config.from_time and config.to_time:
        from_time, to_time = config.from_time, config.to_time
    else:
        _, _, from_time, to_time = parse_recent_scan_window({})
    cmd = command_prefix(settings.repo_dir, "batch_recent") + [
        "--config",
        str(settings.config),
        "--out",
        str(out_dir),
        "--cm-inspect-limit",
        str(config.cm_inspect_limit),
        "--triage-profile-limit",
        str(config.triage_profile_limit),
        "--metadata-top-limit",
        str(config.metadata_top_limit if metadata_enabled else 0),
        "--order",
        config.order,
        "--metadata-mode",
        metadata_mode,
        "--top-reports",
        "0",
        "--cm-jobs",
        str(config.cm_jobs),
        "--jobs",
        str(config.jobs),
        "--metadata-jobs",
        str(config.metadata_jobs if metadata_enabled else 1),
        "--overwrite",
        "--progress-jsonl",
        str(progress_path),
    ]
    direct_impala_source = settings.query_profile_source == "impala"
    if direct_impala_source:
        append_web_impala_profile_args(cmd, settings)
    else:
        append_web_cm_args(cmd, settings)
    if config.only_running:
        cmd.extend(["--recent-window-minutes", str(config.recent_window_minutes)])
    else:
        cmd.extend(["--from-time", str(from_time), "--to-time", str(to_time)])
    if config.min_duration_sec is None:
        cmd.append("--no-min-duration-filter")
    else:
        cmd.extend(["--min-duration-sec", display_float(config.min_duration_sec)])
    if config.max_duration_sec is not None:
        cmd.extend(["--max-duration-sec", display_float(config.max_duration_sec)])
    if config.user:
        cmd.extend(["--user", config.user])
    if config.pool:
        cmd.extend(["--pool", config.pool])
    if config.query_type:
        cmd.extend(["--query-type", config.query_type])
    if config.include_failed:
        cmd.append("--include-failed")
    if config.include_running:
        cmd.append("--include-running")
    if config.only_running:
        cmd.append("--only-running")
    if config.collect_cm_events and not direct_impala_source:
        cmd.extend(["--collect-cm-events", "--cm-events-max-events", str(config.cm_events_max_events)])
    if config.collect_cm_timeseries and not direct_impala_source:
        cmd.extend(
            [
                "--collect-cm-timeseries",
                "--cm-metrics-profile",
                config.cm_metrics_profile,
                "--cm-timeseries-top-limit",
                str(config.cm_timeseries_top_limit),
            ]
        )
    if metadata_enabled:
        append_web_metadata_args(cmd, settings)
    if config.jobs > BATCH_FULL_JOBS_MAX:
        cmd.append("--allow-high-jobs")
    return cmd, out_dir
