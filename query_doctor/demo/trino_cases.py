"""Synthetic raw-free Trino Beta demo cases."""

from __future__ import annotations

from typing import Any


TRINO_DEMO_SCHEMA_VERSION = "query_doctor_trino_demo_v1"


def trino_demo_payload() -> dict[str, Any]:
    cases = [trino_spill_retry_case(), trino_queue_planning_case()]
    return {
        "schema_version": TRINO_DEMO_SCHEMA_VERSION,
        "mode": "synthetic-trino-demo",
        "demo_mode": True,
        "description": (
            "Synthetic raw-free Trino Beta demo cases. No coordinator, network, "
            "metadata collection, SQL execution, LLM, Details, trusted report, or optimizer "
            "workflow is used."
        ),
        "recent": {
            "records_seen": 2,
            "records_selected": 2,
            "records_diagnosed": 2,
            "query_bound": 25,
        },
        "cases": cases,
    }


def trino_spill_retry_case() -> dict[str, Any]:
    return {
        "case_id": "trino-demo-001",
        "query_id": "20260603_120102_00001_demoa",
        "label": "Spill and retry compact diagnosis",
        "status": "diagnosed",
        "lifecycle": "finished",
        "parser_coverage": "known",
        "safe_note": "2 supported attention areas",
        "attention_areas": ("trino_spill_observed", "trino_task_retries"),
        "diagnosis": {
            "schema_version": "trino_compact_diagnosis_v1",
            "engine": "trino",
            "support_status": "bounded_compact_fact_boundary",
            "parser_coverage": "known",
            "lifecycle": "finished",
            "diagnostic_lane": trino_demo_diagnostic_lane(2),
            "attention_areas": [
                {
                    "id": "trino_spill_observed",
                    "state": "supported",
                    "summary": "Bounded compact facts show spill evidence.",
                    "evidence_fact_ids": ("trino_spilled_bytes",),
                    "observed_value": {"value": 1073741824, "unit": "bytes"},
                    "change_direction": (
                        "Review spill-heavy stages, memory pressure, and resource-group limits "
                        "with a Trino operator."
                    ),
                    "verification": (
                        "Compare a later bounded rerun against the same workload window and "
                        "confirm spill volume moved in the expected direction."
                    ),
                },
                {
                    "id": "trino_task_retries",
                    "state": "supported",
                    "summary": "Bounded compact facts show retried tasks.",
                    "evidence_fact_ids": ("trino_retried_task_count",),
                    "observed_value": {"value": 3, "unit": "tasks"},
                    "change_direction": (
                        "Review retry-heavy tasks and stage timing before changing query logic."
                    ),
                    "verification": (
                        "Use a comparable compact boundary after the change and compare retry "
                        "count, spill evidence, and lifecycle status."
                    ),
                },
            ],
            "limitations": trino_demo_limitations(),
            "diagnosis_boundary": trino_demo_boundary(),
        },
    }


def trino_queue_planning_case() -> dict[str, Any]:
    return {
        "case_id": "trino-demo-002",
        "query_id": "20260603_120212_00002_demob",
        "label": "Queue and planning compact diagnosis",
        "status": "diagnosed",
        "lifecycle": "finished",
        "parser_coverage": "known",
        "safe_note": "2 supported attention areas",
        "attention_areas": ("trino_queue_or_blocked", "trino_planning_time_heavy"),
        "diagnosis": {
            "schema_version": "trino_compact_diagnosis_v1",
            "engine": "trino",
            "support_status": "bounded_compact_fact_boundary",
            "parser_coverage": "known",
            "lifecycle": "finished",
            "diagnostic_lane": trino_demo_diagnostic_lane(2),
            "attention_areas": [
                {
                    "id": "trino_queue_or_blocked",
                    "state": "supported",
                    "summary": "Bounded compact facts show queue time before execution.",
                    "evidence_fact_ids": (
                        "trino_queued_time_ms",
                        "trino_resource_group_queue_time_ms",
                    ),
                    "observed_values": {
                        "trino_queued_time_ms": {"value": 94000, "unit": "ms"},
                        "trino_resource_group_queue_time_ms": {"value": 94000, "unit": "ms"},
                    },
                    "change_direction": (
                        "Review resource-group queueing and blocked status before SQL or "
                        "metadata follow-up."
                    ),
                    "verification": (
                        "Compare a later bounded rerun and confirm queued time no longer "
                        "dominates the compact lifecycle facts."
                    ),
                },
                {
                    "id": "trino_planning_time_heavy",
                    "state": "supported",
                    "summary": "Bounded compact facts show planning time as a large share.",
                    "evidence_fact_ids": ("planning_time_ms", "trino_elapsed_time_ms"),
                    "observed_values": {
                        "planning_time_ms": {"value": 72000, "unit": "ms"},
                        "trino_elapsed_time_ms": {"value": 180000, "unit": "ms"},
                    },
                    "change_direction": (
                        "Review connector metadata latency and planning context with a Trino "
                        "operator."
                    ),
                    "verification": (
                        "Use a comparable compact boundary after follow-up and compare planning "
                        "time share against elapsed time."
                    ),
                },
            ],
            "limitations": trino_demo_limitations(),
            "diagnosis_boundary": trino_demo_boundary(),
        },
    }


def trino_demo_diagnostic_lane(supported_attention_area_count: int) -> dict[str, Any]:
    return {
        "schema_version": "trino_compact_diagnostic_lane_v1",
        "lane": "trino_compact_preview",
        "promotion_status": "preview_only",
        "source_granularity": "one_query_boundary",
        "evidence_readiness": "one_query_attention_ready",
        "verification_scope": "comparable_one_query_rerun",
        "supported_attention_area_count": supported_attention_area_count,
        "fact_state_counts": {"supported": supported_attention_area_count, "unknown": 1},
        "required_gates": {
            "readiness_audit": "required_for_handoff",
            "surface_audit": "required_before_wiring",
        },
    }


def trino_demo_limitations() -> list[dict[str, str]]:
    return [
        {
            "id": "no_live_trino_support",
            "state": "unknown",
            "summary": (
                "This demo is a raw-free compact Trino Beta surface and does not claim "
                "production Trino support."
            ),
        },
        {
            "id": "no_metadata_collection",
            "state": "not_wired",
            "summary": "Trino Beta demo cases do not collect metadata.",
        },
    ]


def trino_demo_boundary() -> dict[str, str]:
    return {
        "root_cause": "not_claimed",
        "details_trusted_report_surface": "not_wired",
        "optimizer_behavior": "not_wired",
        "trino_sql_execution": "not_performed",
        "live_recent_scan": "retained_query_list_beta",
        "live_known_query_diagnosis": "one_query_pruned_query_info_beta",
    }
