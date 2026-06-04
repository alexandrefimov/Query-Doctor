"""Minimal engine adapter contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineAdapter:
    engine_name: str
    display_name: str
    supports_recent_scan: bool
    supports_query_id_mode: bool
    supports_metadata_collection: bool
    supports_validated_reports: bool
    supports_offline_evidence_import: bool = False
    supports_local_event_store_import: bool = False
    supports_local_query_detail_import: bool = False
    supports_local_query_list_import: bool = False
    supports_local_statement_stats_import: bool = False
    supports_http_event_archive_import: bool = False
    supports_http_query_detail_archive_import: bool = False
    supports_event_source_contract_check: bool = False
    supports_local_query_info_pruned_import: bool = False
    supports_coordinator_query_info_target_check: bool = False
    supports_coordinator_query_info_pruned_probe: bool = False
    supports_coordinator_query_info_pruned_import: bool = False
    supports_compact_diagnosis: bool = False
    notes: tuple[str, ...] = ()
