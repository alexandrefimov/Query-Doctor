import json
from pathlib import Path

from scripts.build_recent_retry_summary import build_aggregate_summary


def write_case(case_dir: Path, *, primary: dict[str, object]) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "profile_digest.md").write_text("Profile digest\n", encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text(
        "\n".join(
            [
                "# Query Doctor Analysis Facts",
                "",
                "## Summary",
                "- Parsed operators: 1",
                "- Cardinality anomalies: 0",
                "- Memory anomalies: 0",
                "",
                "## Referenced Tables",
                "- not_observed",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (case_dir / "analysis.json").write_text(
        json.dumps(
            {
                "case_primary_bottleneck": primary,
                "query_context": {
                    "duration_ms": 120000,
                    "query_type": "DML",
                },
            }
        ),
        encoding="utf-8",
    )


def test_build_recent_retry_summary_materializes_cases_and_recomputes_severity(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    retry_root = tmp_path / "retry"
    original_case = source_root / "cases" / "case-001" / "safe-id-1"
    retry_case = retry_root / "case-002" / "safe-id-2"
    write_case(
        original_case,
        primary={
            "label": "sql_shape",
            "confidence": "low",
            "reasons": ["join_top_finding"],
        },
    )
    write_case(
        retry_case,
        primary={
            "label": "client_fetch_tail",
            "confidence": "high",
            "reasons": ["client_fetch_wait_top_finding"],
        },
    )
    source_summary = source_root / "batch_summary.json"
    source_summary.write_text(
        json.dumps(
            {
                "recent_window_minutes": 60,
                "summaries_inspected": 2,
                "cm_inspect_limit": 2,
                "triage_profile_limit": 2,
                "metadata_top_limit": 0,
                "order": "duration-desc",
                "query_profile_source": "cm",
                "cases": [
                    {
                        "case_index": 1,
                        "query_id": "safe-query-1",
                        "duration_sec": 120.0,
                        "collection_status": "ok",
                        "analysis_status": "ok",
                        "metadata_status": "not_requested",
                    },
                    {
                        "case_index": 2,
                        "query_id": "safe-query-2",
                        "duration_sec": 120.0,
                        "collection_status": "failed",
                        "analysis_status": "not_started",
                        "metadata_status": "not_observed",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    out = tmp_path / "aggregate"
    result = build_aggregate_summary(
        source_summary_path=source_summary,
        case_roots=(source_root, retry_root),
        out=out,
        overwrite=True,
    )
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    cases = {case["case_index"]: case for case in summary["cases"]}

    assert result.case_count == 2
    assert result.duplicate_case_count == 0
    assert summary["aggregate_retry_summary"]["successful_case_count"] == 2
    assert cases[1]["case_dir"] == "cases/case-001"
    assert cases[2]["case_dir"] == "cases/case-002"
    assert cases[1]["score_severity"] == "clean"
    assert cases[2]["score_severity"] == "suspicious"
    assert not (out / "cases" / "case-001").is_symlink()
    assert not (out / "cases" / "case-002").is_symlink()
    assert (out / "cases" / "case-001" / "analysis_facts.md").is_file()
    assert (out / "cases" / "case-002" / "analysis_facts.md").is_file()
