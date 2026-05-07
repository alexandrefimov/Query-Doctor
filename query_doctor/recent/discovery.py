"""Recent query discovery helpers for Cloudera Manager."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from query_doctor.cli import collect_cm_profiles as cm_profiles
from query_doctor.recent.batch_config import MAX_RAW_CM_SUMMARY_SCAN_LIMIT, secret_values
from query_doctor.recent.batch_models import BatchConfig, DiscoveryResult

CMClientFactory = Callable[[BatchConfig, dict[str, str]], cm_profiles.CMHttpClient]


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

    def fetch_page(received_filters: cm_profiles.CMQueryFilters, page_token: str | None) -> cm_profiles.CMQueryPage:
        return cm_profiles.fetch_cm_query_summary_page(client, received_filters, page_token)

    server_filter_expression = cm_profiles.build_cm_query_filter_expression(discovery_filters)
    duration_filter_mode = classify_duration_filter_mode(
        server_filter_expression,
        min_duration_sec=config.min_duration_sec,
        max_duration_sec=config.max_duration_sec,
    )
    summaries, warnings, used_duration_fallback = cm_profiles.collect_query_summaries_with_duration_fallback(
        discovery_filters,
        fetch_page,
        secrets=secret_values(env),
    )
    if used_duration_fallback:
        duration_filter_mode = "server-side-fallback-client-side"
        discovery_filters = replace(
            discovery_filters,
            min_duration_sec=None,
            max_duration_sec=None,
            server_duration_filter=False,
        )
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
    if matching_candidate_limit_hit(candidates):
        limit = config.triage_profile_limit
        warnings.append(
            f"More than {limit} query summaries matched the current filters. Narrow the scan hour or filters and run again."
        )
        return DiscoveryResult(
            candidates=[],
            warnings=list(warnings),
            duration_filter_mode=duration_filter_mode,
            server_filter_expression=server_filter_expression,
            summaries_inspected=len(summaries),
            scan_too_broad=True,
        )
    return DiscoveryResult(
        candidates=candidates,
        warnings=list(warnings),
        duration_filter_mode=duration_filter_mode,
        server_filter_expression=server_filter_expression,
        summaries_inspected=len(summaries),
    )


def raw_cm_summary_scan_limit(candidate_limit: int) -> int:
    return min(MAX_RAW_CM_SUMMARY_SCAN_LIMIT, max(candidate_limit, candidate_limit * 4))


def matching_candidate_limit_hit(candidates: list[cm_profiles.RecentQueryCandidate]) -> bool:
    return any(candidate.reason == "eligible but not selected because recent-select limit was reached" for candidate in candidates)


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
