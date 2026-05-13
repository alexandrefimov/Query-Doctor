"""Recent query discovery helpers for Cloudera Manager."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import re

from query_doctor.cli import collect_cm_profiles as cm_profiles
from query_doctor.recent.batch_config import MAX_RAW_CM_SUMMARY_SCAN_LIMIT, secret_values
from query_doctor.recent.batch_models import BatchConfig, DiscoveryResult

CMClientFactory = Callable[[BatchConfig, dict[str, str]], cm_profiles.CMHttpClient]
CM_SUMMARY_SCAN_LIMIT_WARNING_RE = re.compile(
    r"\bquery scan limit reached\b|\bscan limit reached\b", re.IGNORECASE
)
CM_SUMMARY_TIME_SHARD_MINUTES = 60
CM_SUMMARY_MIN_TIME_SHARD_MINUTES = 15
CM_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class _DiscoveryCollection:
    summaries: list[cm_profiles.CMQuerySummary]
    warnings: list[str]
    duration_filter_mode: str
    filters: cm_profiles.CMQueryFilters
    raw_scan_cap_hit: bool = False


def make_cm_http_client(config: BatchConfig, env: dict[str, str]) -> cm_profiles.CMHttpClient:
    http_config = cm_profiles.CMHttpConfig(
        cm_url=config.cm_url,
        username=config.cm_username,
        password=env.get("CM_PASSWORD"),
        token=env.get("CM_TOKEN"),
        ca_bundle=config.ca_bundle,
        verify_tls=config.verify_tls,
    )
    return cm_profiles.CMHttpClient(http_config)


def build_recent_filters(config: BatchConfig) -> cm_profiles.CMQueryFilters:
    return cm_profiles.CMQueryFilters(
        cluster=config.cluster,
        service=config.service,
        since_hours=max(1, (config.recent_window_minutes + 59) // 60),
        since_minutes=None if config.from_time and config.to_time else config.recent_window_minutes,
        from_time=config.from_time,
        to_time=config.to_time,
        limit=config.cm_inspect_limit,
        min_duration_sec=config.min_duration_sec,
        max_duration_sec=config.max_duration_sec,
        server_duration_filter=True,
        pool=config.pool,
        user=config.user,
        status="all",
        query_id=None,
        query_type=config.query_type,
        executing=True if config.only_running else (None if config.include_running else False),
    )


def discover_candidates(
    config: BatchConfig,
    *,
    env: dict[str, str],
    make_client: CMClientFactory = make_cm_http_client,
) -> DiscoveryResult:
    client = make_client(config, env)
    filters = build_recent_filters(config)
    discovery_filters = replace(filters, limit=raw_cm_summary_scan_limit(config.cm_inspect_limit))

    def fetch_page(
        received_filters: cm_profiles.CMQueryFilters, page_token: str | None
    ) -> cm_profiles.CMQueryPage:
        return cm_profiles.fetch_cm_query_summary_page(client, received_filters, page_token)

    server_filter_expression = cm_profiles.build_cm_query_filter_expression(discovery_filters)
    collection = collect_discovery_summaries(
        discovery_filters,
        fetch_page,
        env=env,
    )
    summaries = collection.summaries
    warnings = collection.warnings
    duration_filter_mode = collection.duration_filter_mode
    time_sharded = False
    time_shard_count = 0
    time_shard_scan_limit_warning_count = 0
    raw_scan_cap_hit = collection.raw_scan_cap_hit
    if should_time_shard_discovery(config, warnings):
        sharded_collection, time_shard_count, time_shard_scan_limit_warning_count = (
            collect_time_sharded_summaries(
                config,
                collection.filters,
                fetch_page,
                env=env,
            )
        )
        summaries = sharded_collection.summaries
        non_scan_limit_warnings = [
            warning
            for warning in collection.warnings
            if not is_cm_summary_scan_limit_warning(warning)
        ]
        warnings = [
            f"CM query summary scan limit was reported; retried discovery with {time_shard_count} time shards.",
            *non_scan_limit_warnings,
            *sharded_collection.warnings,
        ]
        duration_filter_mode = sharded_collection.duration_filter_mode
        time_sharded = True
        raw_scan_cap_hit = sharded_collection.raw_scan_cap_hit
    candidates = cm_profiles.select_recent_query_candidates(
        summaries,
        select_limit=config.triage_profile_limit,
        include_failed=config.include_failed,
        include_running=config.include_running or config.only_running,
        only_running=config.only_running,
        user=config.user,
        pool=config.pool,
        query_type=config.query_type,
        min_duration_sec=config.min_duration_sec,
        max_duration_sec=config.max_duration_sec,
        order=config.order,
    )
    if raw_scan_cap_hit:
        warnings.append(
            "CM summary raw scan cap was reached before discovery completed. Narrow the scan window or filters and run again."
        )
    candidate_limit_hit = matching_candidate_limit_hit(candidates)
    if candidate_limit_hit and not raw_scan_cap_hit:
        warnings.append(
            f"More than {config.triage_profile_limit} query summaries matched "
            f"the current filters; selected the top {config.triage_profile_limit} by scan order."
        )
    if raw_scan_cap_hit:
        return DiscoveryResult(
            candidates=[],
            warnings=list(warnings),
            duration_filter_mode=duration_filter_mode,
            server_filter_expression=server_filter_expression,
            summaries_inspected=len(summaries),
            scan_too_broad=True,
            raw_summary_scan_cap_hit=raw_scan_cap_hit,
            time_sharded=time_sharded,
            time_shard_count=time_shard_count,
            time_shard_minutes=CM_SUMMARY_TIME_SHARD_MINUTES if time_sharded else None,
            time_shard_min_minutes=CM_SUMMARY_MIN_TIME_SHARD_MINUTES if time_sharded else None,
            time_shard_scan_limit_warning_count=time_shard_scan_limit_warning_count,
        )
    return DiscoveryResult(
        candidates=candidates,
        warnings=list(warnings),
        duration_filter_mode=duration_filter_mode,
        server_filter_expression=server_filter_expression,
        summaries_inspected=len(summaries),
        raw_summary_scan_cap_hit=raw_scan_cap_hit,
        time_sharded=time_sharded,
        time_shard_count=time_shard_count,
        time_shard_minutes=CM_SUMMARY_TIME_SHARD_MINUTES if time_sharded else None,
        time_shard_min_minutes=CM_SUMMARY_MIN_TIME_SHARD_MINUTES if time_sharded else None,
        time_shard_scan_limit_warning_count=time_shard_scan_limit_warning_count,
    )


def raw_cm_summary_scan_limit(candidate_limit: int) -> int:
    return min(MAX_RAW_CM_SUMMARY_SCAN_LIMIT, max(candidate_limit, candidate_limit * 4))


def collect_discovery_summaries(
    filters: cm_profiles.CMQueryFilters,
    fetch_page: cm_profiles.CMQueryPageFetcher,
    *,
    env: dict[str, str],
) -> _DiscoveryCollection:
    filter_expression = cm_profiles.build_cm_query_filter_expression(filters)
    duration_filter_mode = classify_duration_filter_mode(
        filter_expression,
        min_duration_sec=filters.min_duration_sec,
        max_duration_sec=filters.max_duration_sec,
    )
    summaries, warnings, used_duration_fallback = (
        cm_profiles.collect_query_summaries_with_duration_fallback(
            filters,
            fetch_page,
            secrets=secret_values(env),
        )
    )
    if not used_duration_fallback:
        return _DiscoveryCollection(
            summaries=summaries,
            warnings=warnings,
            duration_filter_mode=duration_filter_mode,
            filters=filters,
            raw_scan_cap_hit=len(summaries) >= filters.limit,
        )
    fallback_filters = replace(
        filters,
        min_duration_sec=None,
        max_duration_sec=None,
        server_duration_filter=False,
    )
    return _DiscoveryCollection(
        summaries=summaries,
        warnings=warnings,
        duration_filter_mode="server-side-fallback-client-side",
        filters=fallback_filters,
        raw_scan_cap_hit=len(summaries) >= filters.limit,
    )


def should_time_shard_discovery(config: BatchConfig, warnings: list[str]) -> bool:
    if not any_cm_summary_scan_limit_warning(warnings):
        return False
    start, end = discovery_window_bounds(config)
    return end - start > timedelta(minutes=CM_SUMMARY_TIME_SHARD_MINUTES)


def collect_time_sharded_summaries(
    config: BatchConfig,
    filters: cm_profiles.CMQueryFilters,
    fetch_page: cm_profiles.CMQueryPageFetcher,
    *,
    env: dict[str, str],
) -> tuple[_DiscoveryCollection, int, int]:
    summaries_by_query_id: dict[str, cm_profiles.CMQuerySummary] = {}
    warnings: list[str] = []
    duration_filter_mode = classify_duration_filter_mode(
        cm_profiles.build_cm_query_filter_expression(filters),
        min_duration_sec=filters.min_duration_sec,
        max_duration_sec=filters.max_duration_sec,
    )
    effective_filters = filters
    shard_count = 0
    scan_limit_warning_count = 0
    raw_scan_cap_hit = False

    pending_shards = discovery_time_shards(config, shard_minutes=CM_SUMMARY_TIME_SHARD_MINUTES)
    while pending_shards:
        start, end = pending_shards.pop(0)
        remaining = max(0, filters.limit - len(summaries_by_query_id))
        if remaining <= 0:
            raw_scan_cap_hit = True
            break
        shard_count += 1
        shard_filters = replace(
            filters,
            limit=remaining,
            since_minutes=None,
            from_time=format_cm_time(start),
            to_time=format_cm_time(end),
        )
        collection = collect_discovery_summaries(shard_filters, fetch_page, env=env)
        shard_scan_limit_warnings = count_cm_summary_scan_limit_warnings(collection.warnings)
        scan_limit_warning_count += shard_scan_limit_warnings
        if shard_scan_limit_warnings and can_split_time_shard(start, end):
            warnings.extend(
                warning
                for warning in collection.warnings
                if not is_cm_summary_scan_limit_warning(warning)
            )
            pending_shards[:0] = split_time_shard(start, end)
            continue
        warnings.extend(collection.warnings)
        if collection.duration_filter_mode == "server-side-fallback-client-side":
            duration_filter_mode = collection.duration_filter_mode
            effective_filters = replace(
                effective_filters,
                min_duration_sec=None,
                max_duration_sec=None,
                server_duration_filter=False,
            )
        for summary in collection.summaries:
            summaries_by_query_id.setdefault(summary.query_id, summary)
        if len(summaries_by_query_id) >= filters.limit and pending_shards:
            raw_scan_cap_hit = True
            break

    return (
        _DiscoveryCollection(
            summaries=list(summaries_by_query_id.values()),
            warnings=warnings,
            duration_filter_mode=duration_filter_mode,
            filters=effective_filters,
            raw_scan_cap_hit=raw_scan_cap_hit,
        ),
        shard_count,
        scan_limit_warning_count,
    )


def discovery_time_shards(
    config: BatchConfig,
    *,
    shard_minutes: int,
) -> list[tuple[datetime, datetime]]:
    start, end = discovery_window_bounds(config)
    shard_delta = timedelta(minutes=max(1, shard_minutes))
    shards: list[tuple[datetime, datetime]] = []
    cursor = end
    while cursor > start:
        shard_start = max(start, cursor - shard_delta)
        shards.append((shard_start, cursor))
        cursor = shard_start
    return shards


def split_time_shard(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    midpoint = start + timedelta(seconds=max(1, int((end - start).total_seconds() // 2)))
    return [(midpoint, end), (start, midpoint)]


def can_split_time_shard(start: datetime, end: datetime) -> bool:
    return end - start > timedelta(minutes=CM_SUMMARY_MIN_TIME_SHARD_MINUTES)


def discovery_window_bounds(config: BatchConfig) -> tuple[datetime, datetime]:
    if config.from_time and config.to_time:
        return parse_cm_time(config.from_time), parse_cm_time(config.to_time)
    end = datetime.now(timezone.utc).replace(microsecond=0)
    return end - timedelta(minutes=config.recent_window_minutes), end


def parse_cm_time(value: str) -> datetime:
    return datetime.strptime(value, CM_TIME_FORMAT).replace(tzinfo=timezone.utc)


def format_cm_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime(CM_TIME_FORMAT)


def any_cm_summary_scan_limit_warning(warnings: list[str]) -> bool:
    return count_cm_summary_scan_limit_warnings(warnings) > 0


def count_cm_summary_scan_limit_warnings(warnings: list[str]) -> int:
    return sum(1 for warning in warnings if is_cm_summary_scan_limit_warning(warning))


def is_cm_summary_scan_limit_warning(warning: str) -> bool:
    return bool(CM_SUMMARY_SCAN_LIMIT_WARNING_RE.search(warning))


def matching_candidate_limit_hit(candidates: list[cm_profiles.RecentQueryCandidate]) -> bool:
    return any(
        candidate.reason == "eligible but not selected because recent-select limit was reached"
        for candidate in candidates
    )


def classify_duration_filter_mode(
    filter_expression: str | None,
    *,
    min_duration_sec: float | None,
    max_duration_sec: float | None = None,
) -> str:
    if min_duration_sec is None and max_duration_sec is None:
        return "none"
    if filter_expression and "duration" in filter_expression.lower():
        return "server-side"
    return "client-side"
