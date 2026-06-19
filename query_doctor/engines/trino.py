"""Trino engine adapter."""

from __future__ import annotations

from query_doctor.engines.base import EngineAdapter


TRINO_ADAPTER = EngineAdapter(
    engine_name="trino",
    display_name="Trino",
    supports_recent_scan=True,
    supports_query_id_mode=True,
    supports_metadata_collection=False,
    supports_validated_reports=False,
    supports_offline_evidence_import=True,
    supports_local_event_store_import=True,
    supports_local_query_detail_import=True,
    supports_local_query_list_import=True,
    supports_local_statement_stats_import=True,
    supports_http_event_archive_import=True,
    supports_http_query_detail_archive_import=True,
    supports_event_source_contract_check=True,
    supports_local_query_info_pruned_import=True,
    supports_coordinator_query_info_target_check=True,
    supports_coordinator_query_info_pruned_probe=True,
    supports_coordinator_query_info_pruned_import=True,
    supports_compact_diagnosis=True,
    notes=(
        "Supports sanitized offline evidence package, local event-store, local query-detail, local query-list, local statement-stats, local pruned QueryInfo, and bounded HTTP archive import.",
        "Supports raw-free event-source contract checks, coordinator QueryInfo target checks, pruned one-query coordinator probes/imports, and compact diagnosis over boundary JSON.",
        "Supports local web Trino Beta for retained-list Recent diagnosis and one explicit Query ID through bounded pruned coordinator QueryInfo.",
        "Does not support Running scans, submit SQL, crawl live history, collect metadata, or expose trusted report/optimizer output.",
    ),
)
