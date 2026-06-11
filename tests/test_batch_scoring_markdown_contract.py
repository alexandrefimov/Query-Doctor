import json
from pathlib import Path

from query_doctor.analyzer.facts_renderer import render_md
from query_doctor.recent.batch_models import CaseResult
from query_doctor.recent.batch_scoring import (
    extract_scoring_components,
    score_analysis_facts,
    score_case,
)


def _operator(label: str) -> dict[str, str]:
    return {
        "label": label,
        "time": "10.00s",
        "actual_rows_human": "10.00M",
        "estimated_rows_human": "10.00K",
        "rows_ratio_human": "1000.0x",
        "peak_mem_human": "8.00 GiB",
        "estimated_peak_mem_human": "512.00 MiB",
        "mem_ratio_human": "16.0x",
    }


def _rendered_scoring_analysis() -> dict[str, object]:
    return {
        "totals": {
            "TotalTime": {"raw": "3600s", "ms": 3_600_000},
            "TotalBytesRead": {"raw": "120GB", "bytes": 120 * 1024**3},
            "TotalBytesSent": {"raw": "4GB", "bytes": 4 * 1024**3},
        },
        "operators": [_operator("01:HASH JOIN"), _operator("02:SCAN")],
        "top_operators_by_time": [_operator("01:HASH JOIN")],
        "top_operators_by_peak_memory": [_operator("01:HASH JOIN")],
        "cardinality_anomalies": [_operator("01:HASH JOIN"), _operator("02:SCAN")],
        "memory_anomalies": [_operator("01:HASH JOIN")],
        "zero_row_estimate_gaps": [_operator("03:AGGREGATE")],
        "zero_memory_estimate_gaps": [_operator("04:EXCHANGE")],
        "query_context": {
            "available": True,
            "status": "succeeded",
            "query_state": "FINISHED",
            "duration_ms": 3_600_000,
        },
        "query_wall_clock": {
            "duration_human": "1.00h",
            "source": "query_context",
            "confidence": "high",
        },
        "metrics_correlation": {
            "status": "available",
            "correlated_signals": 2,
            "context_only_signals": 0,
            "signals": [],
        },
        "memory_pressure": {
            "status": "supported",
            "evidence_tier": "strong",
            "finding_supported": True,
            "spill_or_scratch_evidence_count": 1,
            "memory_estimate_anomaly_count": 1,
            "zero_memory_estimate_gap_count": 1,
        },
        "scan_skew": {
            "status": "supported",
            "evidence_tier": "strong",
            "finding_supported": True,
            "primary_supported": True,
            "skew_ratio_human": "12.0x",
        },
        "backend_tail": {
            "rows_parsed": 4,
            "tail_candidate_count": 1,
            "execution_tail_candidate_count": 1,
            "read_rate_tail_candidate_count": 0,
            "write_path_tail_candidate_count": 0,
            "data_skew": "yes",
            "data_skew_reason": "rows produced max/min ratio is 12.0x",
            "execution_skew": "yes",
            "write_path_anomaly": "no",
            "candidates": [],
        },
        "referenced_tables": ["default.fact_sales"],
        "findings": [],
        "not_supported_causes": ["No unsupported root causes are inferred."],
        "thresholds": {"report_top_n": 10},
        "case_primary_bottleneck": {
            "label": "runtime_skew",
            "confidence": "high",
            "reasons": ["scan_skew_supported"],
        },
    }


def test_rendered_analysis_facts_feed_batch_scoring_parser_contract():
    facts = render_md(_rendered_scoring_analysis(), Path("profile_digest.md"))

    for required in (
        "## Summary",
        "- Cardinality anomalies: 2",
        "- Memory anomalies: 1",
        "- Zero/unknown row estimate gaps: 1",
        "- Zero/unknown memory estimate gaps: 1",
        "## CM Query Context",
        "- duration: 1.00h",
        "## Memory Pressure Evidence",
        "- finding_supported: yes",
        "- spill_or_scratch_evidence_count: 1",
        "## Runtime Metrics Correlation",
        "- correlated_signals: 2",
        "## Scan Skew Evidence",
        "- skew_ratio: 12.0x",
        "## Backend / Host Tail Evidence",
        "- host tail candidates: 1",
        "- execution tail candidates: 1",
    ):
        assert required in facts

    assert extract_scoring_components(facts) == {
        "cardinality_anomaly_count": 2,
        "memory_anomaly_count": 1,
        "zero_row_estimate_gap_count": 1,
        "zero_memory_estimate_gap_count": 1,
        "backend_data_skew": True,
        "severe_backend_data_skew_ratio": 12.0,
        "host_tail_candidate_count": 1,
        "execution_tail_candidate_count": 1,
        "duration_sec": 3600.0,
        "cm_metrics_correlated_signals": 2,
    }

    assert score_analysis_facts(facts, metadata_status="collected") == (
        46,
        [
            "cardinality estimate anomalies: 2",
            "memory estimate anomalies: 1",
            "zero/unknown row estimate gaps: 1",
            "zero/unknown memory estimate gaps: 1",
            "spill/scratch evidence: non-zero metrics",
            "host-tail candidates: 1",
            "long-running query with host tail: 60.0m",
            "backend data skew evidence",
            "severe backend data skew ratio: 12.0x",
            "Runtime metrics correlated signals: 2",
        ],
    )


def test_score_case_characterizes_rendered_markdown_and_structured_primary(tmp_path):
    analysis = _rendered_scoring_analysis()
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text(
        render_md(analysis, case_dir / "profile_digest.md"),
        encoding="utf-8",
    )
    case = CaseResult(
        index=1,
        query_id="aaaaaaaaaaaaaaaa:0000000000000001",
        duration_sec=3600,
        user=None,
        pool=None,
        query_type="QUERY",
        sql_verb="SELECT",
        wrapper_dir=case_dir,
        actual_case_dir=case_dir,
        collection_status="ok",
        analysis_status="ok",
        metadata_status="collected",
    )

    score_case(case)

    assert case.score == 46
    assert case.scoring_evidence_source == "analysis_json"
    assert case.scoring_fallback_reason is None
    assert case.cardinality_anomaly_count == 2
    assert case.memory_anomaly_count == 1
    assert case.zero_row_estimate_gap_count == 1
    assert case.zero_memory_estimate_gap_count == 1
    assert case.backend_data_skew is True
    assert case.host_tail_candidate_count == 1
    assert case.execution_tail_candidate_count == 1
    assert case.case_primary_bottleneck == {
        "label": "runtime_skew",
        "confidence": "high",
        "reasons": ["scan_skew_supported"],
    }
    assert case.query_optimization_candidate is not None
    assert case.query_optimization_candidate.tier == "low"
    assert "primary_bottleneck_is_runtime_skew" in case.query_optimization_candidate.counter_signals
    assert case.stats_optimization_candidate is not None
    assert case.stats_optimization_candidate.tier == "low"
    assert "primary_bottleneck_is_runtime_skew" in case.stats_optimization_candidate.counter_signals


def test_score_case_uses_analysis_json_when_markdown_labels_change(tmp_path):
    analysis = _rendered_scoring_analysis()
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text(
        "\n".join(
            [
                "# Query Doctor Analysis Facts",
                "",
                "## Summary",
                "- Cardinality issue count: 0",
                "- Memory issue count: 0",
                "- Zero row estimate issue count: 0",
                "- Zero memory estimate issue count: 0",
                "",
                "## Runtime Context",
                "- elapsed: 1.00h",
                "",
                "## Host Tail",
                "- tail hosts: 0",
                "- data distribution: no",
            ]
        ),
        encoding="utf-8",
    )
    case = CaseResult(
        index=1,
        query_id="aaaaaaaaaaaaaaaa:0000000000000001",
        duration_sec=3600,
        user=None,
        pool=None,
        query_type="QUERY",
        sql_verb="SELECT",
        wrapper_dir=case_dir,
        actual_case_dir=case_dir,
        collection_status="ok",
        analysis_status="ok",
        metadata_status="collected",
    )

    score_case(case)

    assert case.score == 46
    assert case.score_reasons == [
        "cardinality estimate anomalies: 2",
        "memory estimate anomalies: 1",
        "zero/unknown row estimate gaps: 1",
        "zero/unknown memory estimate gaps: 1",
        "spill/scratch evidence: non-zero metrics",
        "host-tail candidates: 1",
        "long-running query with host tail: 60.0m",
        "backend data skew evidence",
        "severe backend data skew ratio: 12.0x",
        "Runtime metrics correlated signals: 2",
    ]
    assert case.scoring_evidence_source == "analysis_json"
    assert case.scoring_fallback_reason is None


def test_score_case_records_markdown_fallback_when_analysis_json_missing(tmp_path):
    analysis = _rendered_scoring_analysis()
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "analysis_facts.md").write_text(
        render_md(analysis, case_dir / "profile_digest.md"),
        encoding="utf-8",
    )
    case = CaseResult(
        index=1,
        query_id="aaaaaaaaaaaaaaaa:0000000000000001",
        duration_sec=3600,
        user=None,
        pool=None,
        query_type="QUERY",
        sql_verb="SELECT",
        wrapper_dir=case_dir,
        actual_case_dir=case_dir,
        collection_status="ok",
        analysis_status="ok",
        metadata_status="collected",
    )

    score_case(case)

    assert case.score == 46
    assert case.scoring_evidence_source == "markdown_fallback"
    assert case.scoring_fallback_reason == "analysis_json_missing"


def test_score_case_records_markdown_fallback_when_analysis_json_incomplete(tmp_path):
    analysis = _rendered_scoring_analysis()
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "analysis.json").write_text(
        json.dumps({"cardinality_anomalies": []}),
        encoding="utf-8",
    )
    (case_dir / "analysis_facts.md").write_text(
        render_md(analysis, case_dir / "profile_digest.md"),
        encoding="utf-8",
    )
    case = CaseResult(
        index=1,
        query_id="aaaaaaaaaaaaaaaa:0000000000000001",
        duration_sec=3600,
        user=None,
        pool=None,
        query_type="QUERY",
        sql_verb="SELECT",
        wrapper_dir=case_dir,
        actual_case_dir=case_dir,
        collection_status="ok",
        analysis_status="ok",
        metadata_status="collected",
    )

    score_case(case)

    assert case.score == 46
    assert case.scoring_evidence_source == "markdown_fallback"
    assert case.scoring_fallback_reason == "analysis_json_incomplete"
