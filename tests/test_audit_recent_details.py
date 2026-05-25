import json
from pathlib import Path

from scripts.audit_recent_details import audit_summary


def write_summary(tmp_path: Path, cases: list[dict[str, object]]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "selected_count": len(cases),
                "summaries_inspected": len(cases),
                "cases": cases,
            }
        ),
        encoding="utf-8",
    )
    return summary_path


def write_case_dir(tmp_path: Path, index: int, *, source_sql: bool = True) -> str:
    case_dir = tmp_path / "cases" / f"case-{index:03d}"
    case_dir.mkdir(parents=True)
    (case_dir / "profile_digest.md").write_text("Profile digest\n", encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text("Analysis facts\n", encoding="utf-8")
    if source_sql:
        (case_dir / "original_query.sql").write_text(
            "SELECT key_col FROM db_name.table_name WHERE day_id = 1",
            encoding="utf-8",
        )
    return str(case_dir.relative_to(tmp_path))


def test_recent_details_audit_accepts_clean_with_hidden_optimizer(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case_dir(tmp_path, 1),
                "query_id": "clean-query",
                "user": "analyst",
                "score": 0,
                "score_severity": "clean",
                "duration_sec": 1.0,
                "collection_status": "ok",
                "analysis_status": "ok",
                "metadata_status": "not_requested",
                "report_validation_status": "not_run",
                "score_reasons": [],
            }
        ],
    )

    result = audit_summary(summary_path)

    assert result.ok
    assert result.severity_counts == {"clean": 1}
    assert result.optimizer_counts == {"clean:hidden": 1}
    assert result.action_counts == {"clean:<none>": 1}


def test_recent_details_audit_accepts_clean_follow_up_candidate(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case_dir(tmp_path, 1),
                "query_id": "follow-up-query",
                "user": "analyst",
                "score": 0,
                "score_severity": "clean",
                "duration_sec": 120.0,
                "collection_status": "ok",
                "analysis_status": "ok",
                "metadata_status": "not_requested",
                "report_validation_status": "not_run",
                "score_reasons": ["no analyzer-supported suspicious facts"],
                "case_primary_bottleneck": {
                    "label": "sql_shape",
                    "confidence": "low",
                    "reasons": ["join_top_finding"],
                },
                "query_optimization_candidate": {
                    "tier": "medium",
                    "score": 47,
                    "impact": "high",
                    "confidence": "medium",
                    "reasons": ["large exchange volume before downstream processing"],
                    "suggested_review_areas": ["exchange payload"],
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert result.ok
    assert result.severity_counts == {"clean": 1}
    assert result.action_counts == {"clean:Query-shape recommendation": 1}


def test_recent_details_audit_allows_runtime_follow_up_without_optimizer_source(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case_dir(tmp_path, 1, source_sql=False),
                "query_id": "runtime-follow-up-query",
                "user": "analyst",
                "score": 2,
                "score_severity": "suspicious",
                "duration_sec": 120.0,
                "collection_status": "ok",
                "analysis_status": "ok",
                "metadata_status": "not_requested",
                "report_validation_status": "not_run",
                "score_reasons": ["backend data skew evidence"],
                "case_primary_bottleneck": {
                    "label": "mixed",
                    "confidence": "medium",
                    "reasons": ["competing_runtime_skew", "competing_client_fetch_tail"],
                },
                "query_optimization_candidate": {
                    "tier": "low",
                    "score": 1,
                    "impact": "low",
                    "confidence": "low",
                    "reasons": ["moderate runtime"],
                    "counter_signals": ["no query-shape opportunity evidence"],
                    "suggested_review_areas": [],
                },
                "optimizer_rewrite_support": {
                    "status": "not_candidate",
                    "label": "Optimizer not applicable",
                    "reason": "No supported query-shape optimizer evidence above the review threshold",
                    "rewriteability_bucket": "not_rewriteable",
                    "rewriteability_label": "Not rewriteable",
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert result.ok
    assert result.optimizer_counts == {"suspicious:unavailable": 1}
    assert result.action_counts == {"suspicious:Mixed-signal follow-up": 1}
    assert not any(
        observation.message == "optimizer is unavailable for actionable case"
        for observation in result.observations
    )


def test_recent_details_audit_uses_rendered_severity_for_strong_clean_primary(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case_dir(tmp_path, 1),
                "query_id": "client-fetch-follow-up-query",
                "user": "analyst",
                "score": 0,
                "score_severity": "clean",
                "duration_sec": 120.0,
                "collection_status": "ok",
                "analysis_status": "ok",
                "metadata_status": "not_requested",
                "report_validation_status": "not_run",
                "score_reasons": ["client fetch wait evidence"],
                "case_primary_bottleneck": {
                    "label": "client_fetch_tail",
                    "confidence": "high",
                    "reasons": ["client_fetch_wait_top_finding"],
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert result.ok
    assert result.severity_counts == {"suspicious": 1}
    assert result.action_counts == {"suspicious:Diagnostic follow-up": 1}


def test_recent_details_audit_accepts_failed_collection_with_fallbacks(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "query_id": "failed-query",
                "user": "analyst",
                "score": 0,
                "score_severity": "failed",
                "duration_sec": 1.0,
                "collection_status": "failed",
                "analysis_status": "not_started",
                "metadata_status": "not_observed",
                "report_validation_status": "not_run",
                "score_reasons": [],
            }
        ],
    )

    result = audit_summary(summary_path)

    assert result.ok
    assert result.severity_counts == {"failed": 1}
    assert result.action_counts == {"failed:Processing failure follow-up": 1}
    assert result.report_counts == {"failed:unavailable": 1}
    assert result.optimizer_counts == {"failed:unavailable": 1}


def test_recent_details_audit_requires_failed_metadata_actions_unavailable(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case_dir(tmp_path, 1),
                "query_id": "metadata-failed-query",
                "user": "analyst",
                "score": 3,
                "score_severity": "failed",
                "duration_sec": 1.0,
                "collection_status": "ok",
                "analysis_status": "ok",
                "metadata_status": "failed",
                "report_validation_status": "not_run",
                "failure_category": "metadata_collection_failed",
                "failure_reason": (
                    "Metadata collection failed for this case; deterministic profile facts may "
                    "still be available."
                ),
                "score_reasons": ["metadata collection failed for referenced table"],
            }
        ],
    )

    result = audit_summary(summary_path)

    assert result.ok
    assert result.severity_counts == {"failed": 1}
    assert result.action_counts == {"failed:Processing failure follow-up": 1}
    assert result.report_counts == {"failed:unavailable": 1}
    assert result.optimizer_counts == {"failed:unavailable": 1}


def test_recent_details_audit_tracks_and_can_exclude_baseline_overlap(tmp_path: Path):
    baseline_path = write_summary(
        tmp_path / "baseline",
        [
            {
                "case_index": 1,
                "query_id": "same-query",
                "score_severity": "clean",
            }
        ],
    )
    current_path = write_summary(
        tmp_path / "current",
        [
            {
                "case_index": 1,
                "query_id": "same-query",
                "score": 0,
                "score_severity": "clean",
                "collection_status": "ok",
                "analysis_status": "ok",
                "metadata_status": "not_requested",
            },
            {
                "case_index": 2,
                "query_id": "new-query",
                "score": 0,
                "score_severity": "clean",
                "collection_status": "ok",
                "analysis_status": "ok",
                "metadata_status": "not_requested",
            },
        ],
    )

    result = audit_summary(
        current_path,
        baseline_paths=(baseline_path,),
        exclude_baseline_overlap=True,
    )

    assert result.ok
    assert result.overlap_count == 1
    assert result.excluded_overlap_count == 1
    assert result.total_cases == 2
    assert result.audited_cases == 1
