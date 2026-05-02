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
    notes: tuple[str, ...] = ()
