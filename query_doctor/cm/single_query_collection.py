"""CM single-query collection workflow."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from dataclasses import replace

from query_doctor.cm.config import build_query_filters
from query_doctor.cm.models import CMClientError, CMQuerySummary, CollectorConfig, OutputError
from query_doctor.cm.profile_collection import write_collected_case
from query_doctor.cm.profile_fetchers import fetch_cm_profile_text, fetch_cm_query_details_summary
from query_doctor.cm.profile_parsing import (
    extract_statement_from_profile_text,
    merge_profile_summary_metadata,
)
from query_doctor.cm.timeseries import collect_cm_timeseries_context
from query_doctor.safety.redaction import sanitize_adapter_error_message


def run_cm_single_query_collection(
    config: CollectorConfig,
    client: object,
    *,
    secrets: Iterable[str] = (),
) -> int:
    try:
        filters = build_query_filters(config)
        summary = CMQuerySummary(query_id=config.query_id or "")
        warnings = [
            "collected by Query Doctor CM collector",
            "source query id preserved",
            "redaction enabled",
            "host redaction enabled" if config.redact_hosts else "host redaction disabled for private node diagnostics",
            "CM API endpoint family: v32 Impala query details",
            "analyzer/report were not run automatically",
        ]
        try:
            summary = fetch_cm_query_details_summary(
                client,
                filters,
                config.query_id or "",
            )
            warnings.append("CM query details metadata collected")
        except AttributeError:
            warnings.append("CM query details metadata unavailable: JSON details endpoint is not supported.")
        except CMClientError as exc:
            warnings.append(
                "CM query details metadata unavailable: "
                f"{sanitize_adapter_error_message(exc, secrets=secrets)}"
            )
        profile_text = fetch_cm_profile_text(
            client,
            filters,
            config.query_id or "",
            max_profile_bytes=config.max_profile_bytes,
        )
        summary, profile_metadata_warnings = merge_profile_summary_metadata(summary, profile_text)
        warnings.extend(profile_metadata_warnings)
        if not summary.statement:
            profile_statement = extract_statement_from_profile_text(profile_text)
            if profile_statement:
                summary = replace(summary, statement=profile_statement)
                warnings.append("CM profile text statement metadata collected")
        cm_timeseries_context = None
        if config.collect_cm_timeseries:
            cm_timeseries_context = collect_cm_timeseries_context(
                client,
                summary,
                metrics_profile=config.cm_metrics_profile,
                padding_sec=config.cm_timeseries_padding_sec,
                max_response_bytes=config.max_timeseries_bytes,
                max_points=config.max_timeseries_points,
            )
            if cm_timeseries_context.get("available"):
                warnings.append("CM time-series context collected")
            else:
                warnings.append("CM time-series context unavailable")
        case_dir = write_collected_case(
            config.out,
            summary,
            profile_digest_text=profile_text,
            cm_timeseries_context=cm_timeseries_context,
            warnings=warnings,
            secrets=secrets,
            redact=True,
            redact_identifiers=config.redact_identifiers,
            redact_hosts=config.redact_hosts,
        )
    except (CMClientError, OutputError, OSError) as exc:
        print(
            "[CM profile collector] Collection result: FAILED",
            file=sys.stderr,
        )
        print(
            "Single-query collection failed: "
            f"{sanitize_adapter_error_message(exc, secrets=secrets)}",
            file=sys.stderr,
        )
        return 4

    print("[CM profile collector] Collection result: OK")
    print("Collected count: 1")
    print(f"Output case directory: {case_dir}")
    print(f"Profile text length: {len(profile_text)}")
    print("Redaction: enabled")
    print(f"Host redaction: {'enabled' if config.redact_hosts else 'disabled'}")
    print(f"Max profile bytes: {config.max_profile_bytes}")
    if config.collect_cm_timeseries:
        print("CM time-series context: enabled")
        print(f"CM metrics profile: {config.cm_metrics_profile}")
    print("No raw JSON, SQL, profile text, analyzer output, or reports were written.")
    return 0
