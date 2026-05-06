"""Impala engine adapter."""

from __future__ import annotations

from query_doctor.engines.base import EngineAdapter


IMPALA_ADAPTER = EngineAdapter(
    engine_name="impala",
    display_name="Apache Impala",
    supports_recent_scan=True,
    supports_query_id_mode=True,
    supports_metadata_collection=True,
    supports_validated_reports=True,
    notes=(
        "Current implementation uses Cloudera Manager profile collection.",
        "Metadata collection is explicit, read-only, and bounded.",
    ),
)
