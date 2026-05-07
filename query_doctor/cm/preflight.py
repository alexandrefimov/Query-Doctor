"""Read-only CM endpoint preflight workflow."""

from __future__ import annotations

import sys

from query_doctor.cm.client import build_cm_profile_text_request, build_cm_query_summary_page_request
from query_doctor.cm.collector_plan import ca_bundle_plan_line, tls_plan_line
from query_doctor.cm.config import build_preflight_query_filters
from query_doctor.cm.models import CMClientError, CollectorConfig, sanitize_cm_url_for_display
from query_doctor.cm.profile_fetchers import fetch_cm_profile_text, fetch_cm_query_summary_page
from query_doctor.safety.redaction import sanitize_adapter_error_message


def run_cm_preflight(config: CollectorConfig, client: object) -> int:
    """Perform read-only CM endpoint shape checks without writing output."""
    print("[CM profile collector] Preflight")
    print(f"CM URL: {sanitize_cm_url_for_display(config.cm_url)}")
    print(f"Cluster: {config.cluster}")
    print(f"Service: {config.service}")
    print(f"Output path: {config.out} (not created)")
    filters = build_preflight_query_filters(config)
    summary_path, _ = build_cm_query_summary_page_request(filters)
    print(f"Query summary endpoint: {summary_path}")
    print("Summary fetch limit: 1")
    print(f"Max profile bytes: {config.max_profile_bytes}")
    print(tls_plan_line(config))
    print(ca_bundle_plan_line(config))

    try:
        page = fetch_cm_query_summary_page(client, filters)
    except CMClientError as exc:
        print("[CM profile collector] Preflight result: FAILED")
        print(
            "Query summary check failed: "
            f"{sanitize_adapter_error_message(exc)}",
            file=sys.stderr,
        )
        print(
            "Endpoint path or response shape may need verification before collection.",
            file=sys.stderr,
        )
        return 4

    print("[CM profile collector] Preflight result: OK")
    print(f"Query summaries parsed: {len(page.items)}")
    print(f"Next page token present: {'yes' if page.next_page_token else 'no'}")
    if page.items:
        print("First query id present: yes")
    else:
        print("First query id present: no")

    if config.query_id:
        try:
            profile_path, _ = build_cm_profile_text_request(filters, config.query_id)
            print(f"Profile text endpoint: {profile_path}")
            profile_text = fetch_cm_profile_text(
                client,
                filters,
                config.query_id,
                max_profile_bytes=config.max_profile_bytes,
            )
        except CMClientError as exc:
            print(
                "Profile text check failed: "
                f"{sanitize_adapter_error_message(exc)}",
                file=sys.stderr,
            )
            print(
                "Endpoint path or response shape may need verification before collection.",
                file=sys.stderr,
            )
            return 4
        print("Profile text present: yes")
        print(f"Profile text length: {len(profile_text)}")
    else:
        print("Profile text check: skipped (no --query-id)")

    print("No raw JSON, SQL, profile text, or output files were written.")
    return 0
