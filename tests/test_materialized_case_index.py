import json

from query_doctor.recent.materialized_case_index import (
    SCHEMA_VERSION,
    build_materialized_case_index,
    materialized_case_entries,
)
from query_doctor.web.recent_history_inbox import recent_history_summary_from_payloads
from query_doctor.web.presenters.recent_scan import present_recent_scan_summary


FORBIDDEN_INDEX_FRAGMENTS = (
    "/Users/",
    "/tmp/",
    "case_dir",
    "raw stdout",
    "raw stderr",
    "SHOW CREATE TABLE",
    "qwen",
    "raw_sql",
)


def test_materialized_case_index_is_path_free_and_allowlisted():
    summary = {
        "mode": "recent-query-batch",
        "query_profile_source": "impala",
        "runtime_metrics_provider": "cloudera-manager",
        "recent_window_minutes": 60,
        "from_time": "2026-07-03T10:00:00Z",
        "to_time": "2026-07-03T11:00:00Z",
        "selected_count": 1,
        "summaries_inspected": 4,
        "warnings": ["raw stderr /tmp/query-doctor-private"],
        "cases": [
            {
                "case_index": 1,
                "query_id": "abc /Users/example/case_dir",
                "user": "analyst",
                "case_dir": "/tmp/query-doctor-private/cases/case-001",
                "score": 35,
                "score_severity": "high",
                "duration_sec": 120,
                "start_time": "2026-07-03T10:00:00Z",
                "end_time": "2026-07-03T10:02:00Z",
                "collection_status": "ok",
                "analysis_status": "ok",
                "metadata_status": "ok",
                "score_reasons": [
                    "raw stdout /tmp/query-doctor-private",
                    "SELECT secret FROM private_table",
                ],
                "query_optimization_candidate": {
                    "tier": "high",
                    "score": 80,
                    "impact": "high",
                    "confidence": "medium",
                    "reasons": ["SHOW CREATE TABLE private_table /Users/example qwen3"],
                    "raw_sql": "SELECT should_not_copy FROM t",
                },
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "label": "raw stderr /Users/example/case_dir",
                    "reason": "manual review only",
                    "rewriteability_bucket": "human_review_only",
                    "risk_reasons": ["raw stdout /tmp/query-doctor-private"],
                    "cte_count": 2,
                    "case_dir": "/tmp/query-doctor-private",
                },
                "stats_optimization_candidate": {
                    "tier": "medium",
                    "score": 50,
                    "impact": "medium",
                    "confidence": "medium",
                    "reasons": ["metadata_path /tmp/query-doctor-private"],
                },
            }
        ],
    }

    index = build_materialized_case_index(summary)

    assert index["schema_version"] == SCHEMA_VERSION
    assert index["coverage"]["case_count"] == 1
    assert index["coverage"]["warning_count"] == 1
    assert index["cases"][0]["case_ref"] == "case-001"
    assert index["cases"][0]["start_time"] == "2026-07-03T10:00:00Z"
    assert index["cases"][0]["end_time"] == "2026-07-03T10:02:00Z"
    assert "case_dir" not in index["cases"][0]
    assert "raw_sql" not in index["cases"][0]["query_optimization_candidate"]

    rendered = json.dumps(index, sort_keys=True)
    for fragment in FORBIDDEN_INDEX_FRAGMENTS:
        assert fragment not in rendered


def test_recent_scan_summary_prefers_materialized_case_index_rows():
    summary = {
        "cases": [
            {
                "case_index": 1,
                "query_id": "legacy-query",
                "score": 99,
                "score_severity": "high",
                "duration_sec": 900,
                "collection_status": "ok",
                "analysis_status": "ok",
                "metadata_status": "ok",
            }
        ],
        "materialized_case_index": {
            "schema_version": SCHEMA_VERSION,
            "cases": [
                {
                    "case_index": 2,
                    "query_id": "indexed-query",
                    "score": 10,
                    "score_severity": "suspicious",
                    "duration_sec": 60,
                    "collection_status": "ok",
                    "analysis_status": "ok",
                    "metadata_status": "ok",
                }
            ],
        },
    }

    view = present_recent_scan_summary(summary)

    assert len(view.rows) == 1
    assert view.rows[0].case_id == "case-002"
    assert view.rows[0].query_id == "indexed-query"
    assert view.rows[0].score == 10
    assert view.rows[0].score_severity == "suspicious"


def test_online_history_reuses_in_memory_materialized_cases_without_reprojection(monkeypatch):
    from query_doctor.recent import materialized_case_index

    summary = recent_history_summary_from_payloads(
        [
            {
                "query_id": "query-safe",
                "duration_ms": 60_000,
                "profile_status": "analyzed",
                "analysis_cache_payload": {
                    "analysis_status": "ok",
                    "collection_status": "ok",
                    "score": 72,
                    "score_reasons": ["bounded runtime signal"],
                },
            }
        ],
        backend="postgres",
    )
    calls = 0
    original_project_case = materialized_case_index._project_case

    def counted_project_case(case):
        nonlocal calls
        calls += 1
        return original_project_case(case)

    monkeypatch.setattr(materialized_case_index, "_project_case", counted_project_case)

    assert isinstance(summary["materialized_case_index"]["cases"], tuple)
    entries = materialized_case_entries(summary)

    assert len(entries) == 1
    assert entries[0]["score"] == 72
    assert calls == 0


def test_serialized_materialized_cases_still_reapply_browser_redaction():
    summary = {
        "materialized_case_index": {
            "schema_version": SCHEMA_VERSION,
            "cases": [
                {
                    "case_index": 1,
                    "query_id": "query /tmp/private-case",
                    "score_reasons": ["SELECT secret_value FROM private_table"],
                }
            ],
        }
    }

    [entry] = materialized_case_entries(summary)

    assert "/tmp/private-case" not in entry["query_id"]
    assert "secret_value" not in entry["score_reasons"][0]
