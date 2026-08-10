"""Batch scan parsing and command construction for the local web UI."""

from __future__ import annotations

import re
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from query_doctor.cli.commands import command_prefix
from query_doctor.source_visibility import (
    SOURCE_VISIBILITY_OWNER_RAW,
    SOURCE_VISIBILITY_SAFE,
    collectable_owner_users,
)
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
    DEFAULT_RECENT_SCAN_TIMEZONE,
    WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT,
    WEB_CM_EVENTS_MAX_EVENTS_DEFAULT,
    WEB_CM_TIMESERIES_TOP_LIMIT_DEFAULT,
    BatchRunConfig,
    WebError,
    WebSettings,
    batch_output_dir,
    batch_progress_path,
    batch_reuse_root,
)
from query_doctor.web.query_inbox_time_range import command_query_inbox_time_range
from query_doctor.web.recent_scan_timezone import configured_recent_scan_timezone
from query_doctor.web.trino_beta_query import ENGINE_TRINO, normalize_query_engine
from query_doctor.web.trino_recent import validate_trino_recent_config_for_settings


BATCH_ORDER_VALUES = {
    "recent",
    "duration-desc",
    "duration-asc",
    "recent-duration-desc",
    "status-priority",
}
WEB_RECENT_TRIAGE_PROFILE_LIMIT_DEFAULT = 5000
WEB_SHARED_RECENT_TRIAGE_PROFILE_LIMIT_DEFAULT = 50
WEB_SHARED_BATCH_METADATA_TOP_LIMIT_DEFAULT = 10
BATCH_METADATA_TOP_LIMIT_MAX = 200
BATCH_CM_TIMESERIES_TOP_LIMIT_MAX = 200
BATCH_CM_EVENTS_MAX_EVENTS_MAX = 200
BATCH_JOBS_MAX = 100
BATCH_FULL_JOBS_MAX = 4
BATCH_CM_JOBS_MAX = 100
BATCH_METADATA_JOBS_MAX = 5
WEB_RECENT_PARALLELISM_DEFAULT = 50
WEB_SHARED_RECENT_PARALLELISM_DEFAULT = 4
WEB_RECENT_METADATA_JOBS_DEFAULT = 5
WEB_SHARED_RECENT_METADATA_JOBS_DEFAULT = 2
WEB_RUNNING_SCAN_WINDOW_MINUTES = 120
WEB_RUNNING_CM_INSPECT_LIMIT_DEFAULT = 500
WEB_RECENT_SCAN_WINDOW_MINUTES_DEFAULT = 60
SCAN_PRESET_STANDARD = "standard"
SCAN_PRESET_FREQUENT_SHORT = "frequent_short"
SCAN_PRESET_VALUES = {SCAN_PRESET_STANDARD, SCAN_PRESET_FREQUENT_SHORT}
RECENT_SCAN_TIMEZONE = ZoneInfo(DEFAULT_RECENT_SCAN_TIMEZONE)
RECENT_SCAN_LOOKBACK_DAYS = 2
RECENT_SCAN_BUCKET_HOURS = 1
QUERY_TYPE_FILTER_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")
FALSE_FORM_VALUES = {"0", "false", "no", "off"}


def default_recent_scan_bucket(
    now: datetime | None = None, *, scan_timezone: ZoneInfo = RECENT_SCAN_TIMEZONE
) -> tuple[str, int]:
    current = now.astimezone(scan_timezone) if now else datetime.now(scan_timezone)
    bucket = current.replace(minute=0, second=0, microsecond=0)
    return bucket.date().isoformat(), bucket.hour


def allowed_recent_scan_dates(
    now: datetime | None = None, *, scan_timezone: ZoneInfo = RECENT_SCAN_TIMEZONE
) -> set[str]:
    current = now.astimezone(scan_timezone).date() if now else datetime.now(scan_timezone).date()
    return {
        (current - timedelta(days=days)).isoformat()
        for days in range(RECENT_SCAN_LOOKBACK_DAYS + 1)
    }


def parse_recent_scan_window(
    form: dict[str, list[str]], *, scan_timezone: ZoneInfo = RECENT_SCAN_TIMEZONE
) -> tuple[str, int, str, str]:
    default_date, default_hour = default_recent_scan_bucket(scan_timezone=scan_timezone)
    scan_date = first_form_value(form, "scan_date") or default_date
    scan_hour_text = first_form_value(form, "scan_hour") or str(default_hour)
    if scan_date not in allowed_recent_scan_dates(scan_timezone=scan_timezone):
        raise WebError(
            "Scan date must be today or one of the previous two days.",
            title="Scan date was rejected",
            reason_code="web.scan_date_out_of_range",
            stage="Checking Recent scan window",
            next_step="Choose today or one of the previous two days.",
        )
    try:
        parsed_date = date.fromisoformat(scan_date)
    except ValueError as exc:
        raise WebError(
            "Scan date must be formatted as YYYY-MM-DD.",
            title="Scan date format is invalid",
            reason_code="web.scan_date_invalid",
            stage="Checking Recent scan window",
            next_step="Use the YYYY-MM-DD date format.",
        ) from exc
    try:
        scan_hour = int(scan_hour_text)
    except ValueError as exc:
        raise WebError(
            "Scan hour must be an integer from 0 to 23.",
            title="Scan hour was rejected",
            reason_code="web.scan_hour_invalid",
            stage="Checking Recent scan window",
            next_step="Choose an hour from 0 to 23.",
        ) from exc
    if scan_hour < 0 or scan_hour > 23:
        raise WebError(
            "Scan hour must be an integer from 0 to 23.",
            title="Scan hour was rejected",
            reason_code="web.scan_hour_invalid",
            stage="Checking Recent scan window",
            next_step="Choose an hour from 0 to 23.",
        )
    latest_date, latest_hour = default_recent_scan_bucket(scan_timezone=scan_timezone)
    if scan_date > latest_date or (scan_date == latest_date and scan_hour > latest_hour):
        raise WebError(
            "Scan hour must not be in the future.",
            title="Scan hour is in the future",
            reason_code="web.scan_window_future",
            stage="Checking Recent scan window",
            next_step="Choose a completed Recent scan hour.",
        )
    start_local = datetime.combine(parsed_date, datetime_time(scan_hour), tzinfo=scan_timezone)
    end_local = start_local + timedelta(hours=RECENT_SCAN_BUCKET_HOURS)
    from_time = start_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_time = end_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return scan_date, scan_hour, from_time, to_time


def parse_batch_run_config(
    form: dict[str, list[str]],
    *,
    settings: WebSettings | None = None,
    default_metadata_top_limit: int = WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT,
    default_parallelism: int = WEB_RECENT_PARALLELISM_DEFAULT,
    default_metadata_jobs: int = WEB_RECENT_METADATA_JOBS_DEFAULT,
    default_triage_profile_limit: int = WEB_RECENT_TRIAGE_PROFILE_LIMIT_DEFAULT,
) -> BatchRunConfig:
    cluster_key = (
        selected_cluster_key_from_mapping(form, settings)
        if settings is not None
        else first_form_value(form, "cluster_key")
    )
    selected_settings = (
        settings_for_cluster_key(settings, cluster_key) if settings is not None else None
    )
    local_config = _local_config_values(settings)
    discover_only = recent_history_online_scan_enabled(local_config)
    requested_engine = normalize_query_engine(first_form_value(form, "engine"))
    scan_preset = normalize_scan_preset(first_form_value(form, "scan_preset"))
    scan_timezone = configured_recent_scan_timezone(selected_settings, local_config)
    scan_date, scan_hour = default_recent_scan_bucket(scan_timezone=scan_timezone)
    from_time = to_time = None
    recent_window_minutes = parse_positive_form_int(
        form,
        "recent_window_minutes",
        default=_config_int(
            local_config,
            "recent_window_minutes",
            fallback=WEB_RECENT_SCAN_WINDOW_MINUTES_DEFAULT,
        ),
    )
    inbox_from_time, inbox_to_time = command_query_inbox_time_range(
        first_form_value(form, "inbox_from"),
        first_form_value(form, "inbox_to"),
    )
    if requested_engine != ENGINE_TRINO and inbox_from_time and inbox_to_time:
        from_time = inbox_from_time
        to_time = inbox_to_time
    cm_inspect_limit = BATCH_CM_INSPECT_LIMIT_MAX
    triage_profile_limit = parse_positive_form_int(
        form,
        "triage_profile_limit",
        default=_config_int(
            local_config,
            "recent_profile_analysis_limit",
            fallback=WEB_RECENT_TRIAGE_PROFILE_LIMIT_DEFAULT
            if discover_only
            else default_triage_profile_limit,
        ),
        maximum=BATCH_CM_INSPECT_LIMIT_MAX,
    )
    metadata_top_limit = parse_non_negative_form_int(
        form,
        "metadata_top_limit",
        default=0 if discover_only else default_metadata_top_limit,
        maximum=BATCH_METADATA_TOP_LIMIT_MAX,
    )
    min_duration_sec = parse_optional_non_negative_form_float(form, "min_duration_sec")
    max_duration_text = first_form_value(form, "max_duration_sec")
    max_duration_sec = None
    if max_duration_text:
        max_duration_sec = parse_non_negative_form_float(form, "max_duration_sec", default=0.0)
        if min_duration_sec is not None and max_duration_sec < min_duration_sec:
            raise WebError(
                "max_duration_sec must be greater than or equal to min_duration_sec.",
                title="Duration filter was rejected",
                reason_code="web.duration_filter_invalid",
                stage="Checking Recent scan filters",
                next_step="Set max_duration_sec greater than or equal to min_duration_sec.",
            )
    order = first_form_value(form, "order") or "duration-desc"
    if order not in BATCH_ORDER_VALUES:
        raise WebError(
            "Order must be one of: recent, duration-desc, duration-asc, recent-duration-desc, status-priority.",
            title="Sort order was rejected",
            reason_code="web.scan_order_invalid",
            stage="Checking Recent scan filters",
            next_step="Choose one of the supported Recent scan sort orders.",
        )
    if scan_preset == SCAN_PRESET_FREQUENT_SHORT:
        min_duration_sec = None
        order = "recent"
    parallelism_text = first_form_value(form, "parallelism")
    if not parallelism_text and first_form_value(form, "jobs"):
        parallelism_text = first_form_value(form, "jobs")
    if not parallelism_text and first_form_value(form, "cm_jobs"):
        parallelism_text = first_form_value(form, "cm_jobs")
    parallelism_form = {"parallelism": [parallelism_text]} if parallelism_text else {}
    parallelism_default = _config_int(
        local_config,
        "recent_parallelism",
        fallback=_config_int(local_config, "recent_cm_jobs", fallback=default_parallelism),
    )
    parallelism = parse_positive_form_int(
        parallelism_form,
        "parallelism",
        default=parallelism_default,
        maximum=min(BATCH_CM_JOBS_MAX, BATCH_JOBS_MAX),
    )
    metadata_jobs = parse_positive_form_int(
        form,
        "metadata_jobs",
        default=_config_int(local_config, "recent_metadata_jobs", fallback=default_metadata_jobs),
        maximum=BATCH_METADATA_JOBS_MAX,
    )
    filter_config = {} if requested_engine == ENGINE_TRINO else local_config
    user = (
        first_form_value(form, "user")
        if "user" in form
        else _config_string(filter_config, "recent_user")
    )
    pool = (
        first_form_value(form, "pool")
        if "pool" in form
        else _config_string(filter_config, "recent_pool")
    )
    query_type = parse_query_type_filter(form, filter_config)
    collect_cm_events = _config_bool(
        local_config,
        "recent_collect_cm_events",
        fallback=not discover_only,
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
        fallback=not discover_only,
    )
    if discover_only:
        metadata_top_limit = 0
        collect_cm_events = False
        collect_cm_timeseries = False
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
    publish_latest_summary = parse_publish_latest_summary(form)
    return BatchRunConfig(
        engine=requested_engine,
        scan_preset=scan_preset,
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
        query_type=query_type,
        include_failed=True,
        include_running=False,
        discover_only=discover_only,
        collect_cm_events=collect_cm_events,
        cm_events_max_events=cm_events_max_events,
        collect_cm_timeseries=collect_cm_timeseries,
        cm_metrics_profile=cm_metrics_profile,
        cm_timeseries_top_limit=cm_timeseries_top_limit,
        publish_latest_summary=publish_latest_summary,
    )


def parse_running_run_config(
    form: dict[str, list[str]],
    *,
    settings: WebSettings | None = None,
    default_metadata_top_limit: int = WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT,
    default_parallelism: int = WEB_RECENT_PARALLELISM_DEFAULT,
    default_metadata_jobs: int = WEB_RECENT_METADATA_JOBS_DEFAULT,
) -> BatchRunConfig:
    cluster_key = (
        selected_cluster_key_from_mapping(form, settings)
        if settings is not None
        else first_form_value(form, "cluster_key")
    )
    selected_settings = (
        settings_for_cluster_key(settings, cluster_key) if settings is not None else None
    )
    local_config = _local_config_values(settings)
    cm_inspect_limit = WEB_RUNNING_CM_INSPECT_LIMIT_DEFAULT
    metadata_top_limit = parse_non_negative_form_int(
        form,
        "metadata_top_limit",
        default=default_metadata_top_limit,
        maximum=BATCH_METADATA_TOP_LIMIT_MAX,
    )
    min_duration_sec = parse_optional_non_negative_form_float(form, "min_duration_sec")
    parallelism_text = first_form_value(form, "parallelism")
    parallelism_form = {"parallelism": [parallelism_text]} if parallelism_text else {}
    parallelism_default = _config_int(
        local_config,
        "recent_parallelism",
        fallback=_config_int(local_config, "recent_cm_jobs", fallback=default_parallelism),
    )
    parallelism = parse_positive_form_int(
        parallelism_form,
        "parallelism",
        default=parallelism_default,
        maximum=min(BATCH_CM_JOBS_MAX, BATCH_JOBS_MAX),
    )
    metadata_jobs = parse_positive_form_int(
        form,
        "metadata_jobs",
        default=_config_int(local_config, "recent_metadata_jobs", fallback=default_metadata_jobs),
        maximum=BATCH_METADATA_JOBS_MAX,
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
    query_type = parse_query_type_filter(form, local_config)
    publish_latest_summary = parse_publish_latest_summary(form)
    return BatchRunConfig(
        engine=normalize_query_engine(first_form_value(form, "engine")),
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
        user=(
            first_form_value(form, "user")
            if "user" in form
            else _config_string(local_config, "recent_user")
        ),
        pool=(
            first_form_value(form, "pool")
            if "pool" in form
            else _config_string(local_config, "recent_pool")
        ),
        query_type=query_type,
        include_failed=False,
        include_running=True,
        only_running=True,
        collect_cm_events=True,
        cm_events_max_events=cm_events_max_events,
        collect_cm_timeseries=True,
        cm_metrics_profile=cm_metrics_profile,
        cm_timeseries_top_limit=cm_timeseries_top_limit,
        publish_latest_summary=publish_latest_summary,
    )


def _local_config_values(settings: WebSettings | None) -> dict[str, object]:
    if settings is None:
        return {}
    try:
        return load_web_local_config(settings.config, cwd=Path.cwd())
    except (OSError, ValueError, TypeError):
        return {}


def normalize_scan_preset(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in SCAN_PRESET_VALUES else SCAN_PRESET_STANDARD


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


def _config_string(config_values: dict[str, object], key: str) -> str:
    value = config_values.get(key)
    return value if isinstance(value, str) else ""


def parse_query_type_filter(form: dict[str, list[str]], config_values: dict[str, object]) -> str:
    raw_value = (
        first_form_value(form, "query_type")
        if "query_type" in form
        else _config_string(config_values, "query_type")
    )
    normalized = str(raw_value or "").strip().upper()
    if not normalized:
        return ""
    if QUERY_TYPE_FILTER_RE.fullmatch(normalized) is None:
        raise WebError(
            "Query type filter must be a short identifier such as QUERY, DML, or DDL.",
            title="Query type filter was rejected",
            reason_code="web.query_type_filter_invalid",
            stage="Checking Recent scan filters",
            next_step="Use a short query type identifier such as QUERY, DML, or DDL.",
        )
    return normalized


def parse_publish_latest_summary(form: dict[str, list[str]]) -> bool:
    raw_value = first_form_value(form, "publish_latest_summary")
    if not raw_value:
        return True
    return raw_value.strip().lower() not in FALSE_FORM_VALUES


def form_values_from_form(form: dict[str, list[str]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for name in (
        "scan_preset",
        "scan_target",
        "scan_date",
        "scan_hour",
        "recent_window_minutes",
        "cluster_key",
        "metadata_top_limit",
        "triage_profile_limit",
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
        "query_type",
        "engine",
        "publish_latest_summary",
        "inbox_source",
        "inbox_workflow",
        "inbox_window",
        "inbox_query_type",
        "inbox_from",
        "inbox_to",
    ):
        values[name] = first_form_value(form, name)
    if not values.get("parallelism"):
        values["parallelism"] = first_form_value(form, "jobs") or first_form_value(form, "cm_jobs")
    return values


def form_values_from_config(config: BatchRunConfig) -> dict[str, object]:
    return {
        "scan_preset": config.scan_preset,
        "scan_target": "running" if config.only_running else "finished",
        "scan_date": config.scan_date,
        "scan_hour": str(config.scan_hour),
        "recent_window_minutes": str(config.recent_window_minutes),
        "from_time": config.from_time or "",
        "to_time": config.to_time or "",
        "cluster_key": config.cluster_key,
        "metadata_top_limit": str(config.metadata_top_limit),
        "triage_profile_limit": str(config.triage_profile_limit),
        "min_duration_sec": ""
        if config.min_duration_sec is None
        else display_float(config.min_duration_sec),
        "max_duration_sec": ""
        if config.max_duration_sec is None
        else display_float(config.max_duration_sec),
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
        "query_type": config.query_type,
        "engine": config.engine,
        "publish_latest_summary": "1" if config.publish_latest_summary else "0",
        "discover_only": "1" if config.discover_only else "0",
    }


def validate_batch_config_for_settings(config: BatchRunConfig, settings: WebSettings) -> None:
    settings = settings_for_cluster_key(settings, config.cluster_key)
    if config.engine == ENGINE_TRINO:
        validate_trino_recent_config_for_settings(config, settings)
        return
    if settings.query_profile_source == "impala":
        if not impala_profile_source_configured(settings):
            raise WebError(
                "Selected cluster is missing impalad host settings for direct Impala discovery.",
                title="Direct Impala profile host is not configured",
                reason_code="impala.direct_profile_host_missing",
                stage="Checking scan source",
                next_step="Select or fix a direct-Impala source with impala_profile_hosts.",
            )
    elif settings.clusters or any((settings.cm_url, settings.cm_cluster, settings.cm_service)):
        require_cm_cluster_settings(settings)
    if settings.source_visibility == SOURCE_VISIBILITY_OWNER_RAW:
        owner_users = source_owner_user_choices(settings)
        if config.user and config.user not in owner_users:
            raise WebError(
                "Owner source visibility requires the User filter to match a configured source owner.",
                title="Owner source user does not match",
                reason_code="owner_raw.user_mismatch",
                stage="Checking owner source visibility",
                next_step="Choose a configured source owner in the User filter or switch source visibility.",
            )
        if not owner_users:
            raise WebError(
                "Owner source visibility requires source_owner_user, a keytab Username selection, or a simple Kerberos principal in the web environment.",
                title="Owner source user is not configured",
                reason_code="owner_raw.owner_not_configured",
                stage="Checking owner source visibility",
                next_step=(
                    "Configure source_owner_user, select a keytab Username, "
                    "or use safe source visibility."
                ),
            )
    if config.metadata_top_limit > 0:
        if not metadata_configured(settings):
            raise WebError(
                "Metadata collection is not configured for this web session. Restart with metadata options or disable metadata in config.",
                title="Metadata collection is not configured",
                reason_code="impala.metadata_not_configured",
                stage="Checking metadata request",
                next_step=(
                    "Restart with metadata coordinator and impala-shell settings, "
                    "or run in fast mode with metadata disabled."
                ),
            )
        if settings.metadata_ca_cert and not settings.metadata_ssl:
            raise WebError(
                "--metadata-ca-cert requires --metadata-ssl for web batch metadata.",
                title="Metadata TLS settings are inconsistent",
                reason_code="impala.metadata_tls_rejected",
                stage="Checking metadata request",
                next_step="Enable metadata_ssl when metadata_ca_cert is configured, or remove the CA setting.",
            )


def source_owner_user_choices(settings: WebSettings) -> tuple[str, ...]:
    return collectable_owner_users(settings.source_owner_user, settings.source_owner_user_options)


def effective_source_owner_users(config: BatchRunConfig, settings: WebSettings) -> tuple[str, ...]:
    if settings.source_visibility != SOURCE_VISIBILITY_OWNER_RAW:
        return ()
    choices = source_owner_user_choices(settings)
    if config.user:
        return (config.user,) if config.user in choices else ()
    return choices


def build_batch_command(
    job_id: str, config: BatchRunConfig, settings: WebSettings
) -> tuple[list[str], Path]:
    settings = settings_for_cluster_key(settings, config.cluster_key)
    validate_batch_config_for_settings(config, settings)
    if config.engine == ENGINE_TRINO:
        raise WebError("Trino Recent uses the local web Trino job and has no Impala batch command.")
    source_owner_users = effective_source_owner_users(config, settings)
    recent_batch_root = batch_reuse_root(settings)
    out_dir = batch_output_dir(job_id, root=recent_batch_root)
    progress_path = batch_progress_path(job_id, root=recent_batch_root)
    metadata_enabled = config.metadata_top_limit > 0
    metadata_mode = "on" if metadata_enabled else "off"
    if config.only_running:
        from_time = to_time = None
    elif config.from_time and config.to_time:
        from_time, to_time = config.from_time, config.to_time
    else:
        from_time = to_time = None
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
    if not config.only_running and settings.source_visibility == SOURCE_VISIBILITY_SAFE:
        cmd.extend(["--reuse-analyzed-profiles-from", str(recent_batch_root)])
    direct_impala_source = settings.query_profile_source == "impala"
    if direct_impala_source:
        append_web_impala_profile_args(cmd, settings)
    else:
        append_web_cm_args(cmd, settings)
    if settings.source_visibility != SOURCE_VISIBILITY_SAFE:
        cmd.extend(["--source-visibility", settings.source_visibility])
        for source_owner_user in source_owner_users:
            cmd.extend(["--source-owner-user", source_owner_user])
    if from_time and to_time:
        cmd.extend(["--from-time", str(from_time), "--to-time", str(to_time)])
    else:
        cmd.extend(["--recent-window-minutes", str(config.recent_window_minutes)])
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
    if config.discover_only:
        cmd.append("--discover-only")
    if config.collect_cm_events and not direct_impala_source:
        cmd.extend(
            ["--collect-cm-events", "--cm-events-max-events", str(config.cm_events_max_events)]
        )
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


def recent_history_online_scan_enabled(config_values: dict[str, object]) -> bool:
    backend = str(config_values.get("recent_history_backend") or "").strip().lower()
    if backend == "disabled":
        return False
    return backend in {"sqlite", "postgres"} or bool(config_values.get("recent_history_db"))
