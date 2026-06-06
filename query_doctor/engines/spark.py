"""Spark bounded compact-intake engine adapter."""

from __future__ import annotations

from query_doctor.engines.base import EngineAdapter


SPARK_ADAPTER = EngineAdapter(
    engine_name="spark",
    display_name="Apache Spark",
    supports_recent_scan=False,
    supports_query_id_mode=False,
    supports_metadata_collection=False,
    supports_validated_reports=False,
    supports_offline_evidence_import=True,
    supports_compact_diagnosis=True,
    supports_history_server_compact_intake=True,
    notes=(
        "Supports bounded compact Spark History Server intake for one explicit application.",
        "Supports compact evidence-package validation/export and raw-free compact diagnosis.",
        "Does not execute Spark jobs, collect raw event logs, expose Recent/Details/report/optimizer workflows, or claim production triage support.",
    ),
)
