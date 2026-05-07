"""CM recent-query listing workflow."""

from __future__ import annotations

import sys
from collections.abc import Iterable

from query_doctor.cm.config import build_recent_query_filters
from query_doctor.cm.models import CollectorConfig, sanitize_cm_url_for_display
from query_doctor.cm.profile_collection import collect_query_summaries_with_duration_fallback
from query_doctor.cm.profile_fetchers import fetch_cm_query_summary_page
from query_doctor.cm.query_discovery import select_recent_query_candidates
from query_doctor.cm.recent_listing_output import (
    sanitized_recent_candidate,
    write_recent_candidates_json,
)
from query_doctor.safety.redaction import sanitize_text_for_log


def run_cm_recent_query_listing(
    config: CollectorConfig,
    client: object,
    *,
    secrets: Iterable[str] = (),
) -> int:
    filters = build_recent_query_filters(config)
    summaries, warnings, used_duration_fallback = collect_query_summaries_with_duration_fallback(
        filters,
        lambda received_filters, page_token: fetch_cm_query_summary_page(
            client,
            received_filters,
            page_token,
        ),
        secrets=secrets,
    )
    candidates = select_recent_query_candidates(
        summaries,
        select_limit=config.recent_select,
        include_failed=config.recent_include_failed,
        include_running=config.recent_include_running,
        user=config.recent_user or config.user,
        pool=config.recent_pool or config.pool,
        query_type=config.query_type,
        min_duration_sec=config.recent_min_duration_sec,
        max_duration_sec=config.recent_max_duration_sec,
        order=config.recent_order,
    )

    print("[CM profile collector] Recent query listing")
    print(f"CM URL: {sanitize_cm_url_for_display(config.cm_url)}")
    print(f"Cluster: {config.cluster}")
    print(f"Service: {config.service}")
    print(f"Recent window minutes: {config.recent_window_minutes}")
    print(f"Recent inspect limit: {config.recent_limit}")
    print(f"Recent select limit: {config.recent_select}")
    min_duration_text = (
        str(config.recent_min_duration_sec)
        if config.recent_min_duration_sec is not None
        else "<none>"
    )
    max_duration_text = (
        str(config.recent_max_duration_sec)
        if config.recent_max_duration_sec is not None
        else "<none>"
    )
    print(f"Recent minimum duration seconds: {min_duration_text}")
    print(f"Recent maximum duration seconds: {max_duration_text}")
    print(f"Recent selection order: {config.recent_order}")
    if used_duration_fallback:
        print("Recent duration filter mode: server-side-fallback-client-side")
    print(f"Summaries inspected: {len(candidates)}")
    print(f"Candidates selected: {sum(1 for candidate in candidates if candidate.selected)}")
    for warning in warnings:
        print(f"Warning: {sanitize_text_for_log(warning, secrets=secrets)}", file=sys.stderr)

    for index, candidate in enumerate(candidates, start=1):
        safe = sanitized_recent_candidate(candidate)
        selected = "yes" if candidate.selected else "no"
        duration = safe["duration_sec"]
        duration_text = f"{duration:.3f}s" if isinstance(duration, float) else "<unknown>"
        print(
            "  "
            f"{index}. selected={selected} "
            f"query_id={safe['query_id']} "
            f"type={safe['query_type'] or '<unknown>'} "
            f"status={safe['status'] or '<unknown>'} "
            f"verb={safe['sql_verb'] or '<unknown>'} "
            f"duration={duration_text} "
            f"user={safe['user'] or '<unknown>'} "
            f"pool={safe['pool'] or '<unknown>'} "
            f"reason={safe['reason']}"
        )

    if config.recent_output_json:
        write_recent_candidates_json(
            config.recent_output_json,
            config=config,
            candidates=candidates,
            warnings=warnings,
        )
        print(f"Sanitized JSON written: {config.recent_output_json}")

    print("No profile text, raw SQL, raw JSON, case directories, analyzer output, or reports were written.")
    return 0
