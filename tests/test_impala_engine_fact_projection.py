from pathlib import Path

from query_doctor.analyzer.impala_engine_facts import build_impala_engine_fact_projection
from query_doctor.analyzer.engine_facts import validate_engine_fact_bundle_raw_free
from engine_fact_contract_harness import build_impala_projection_analysis


def test_impala_projection_is_not_a_product_consumer_dependency():
    repo_root = Path(__file__).resolve().parents[1]
    projection_path = repo_root / "query_doctor" / "analyzer" / "impala_engine_facts.py"
    product_references: list[str] = []

    for path in (repo_root / "query_doctor").rglob("*.py"):
        if path == projection_path:
            continue
        text = path.read_text(encoding="utf-8")
        if (
            "query_doctor.analyzer.impala_engine_facts" in text
            or "build_impala_engine_fact_projection" in text
        ):
            product_references.append(str(path.relative_to(repo_root)))

    assert product_references == []


def test_impala_projection_maps_existing_analyzer_fields_raw_free():
    analysis = build_impala_projection_analysis()

    bundle = build_impala_engine_fact_projection(analysis)
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "impala"
    assert bundle.identity.source == "impala_analyzer_projection"
    assert bundle.identity.source_version == "5.0.0-SNAPSHOT"
    assert bundle.identity.parser_coverage == "supported"
    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.blocked == "not_observed"
    assert bundle.lifecycle.failure == "not_observed"
    assert facts["query_wall_clock_ms"].value == 2000
    assert facts["profile_total_time_ms"].value == 2000.0
    assert facts["query_timeline_duration_ms"].value == 2000.0
    assert facts["planning_time_ms"].value == 100.0
    assert facts["admission_time_ms"].value == 300.0
    assert facts["backend_start_time_ms"].value == 200.0
    assert facts["total_bytes_read"].value == 32212254720.0
    assert facts["total_bytes_sent"].value == 2147483648.0
    assert facts["admission_result"].value == "admitted_immediately"
    assert facts["admission_wait_ms"].value == 250.0
    assert facts["per_node_peak_memory_max_bytes"].value == 4294967296.0
    assert facts["per_node_bytes_read_max_bytes"].value == 21474836480.0
    assert facts["runtime_node_count"].value == 1
    assert facts["fragment_section_count"].value == 1
    assert facts["fragment_instance_count"].value == 1
    assert facts["fragment_lifecycle_instance_count"].value == 1
    assert facts["exec_node_row_count_conclusions"].value == "supported"
    assert facts["exec_node_unsafe_operator_count"].value == 0
    assert facts["backend_execution_tail_candidates"].state == "not_observed"
    assert facts["spill_or_scratch_evidence"].state == "not_observed"
    assert facts["client_fetch_wait_ms"].state == "not_observed"

    assert (
        validate_engine_fact_bundle_raw_free(
            bundle,
            forbidden_tokens=(
                "worker-a.example.net",
                "worker-b.example.net",
                "alice",
                "SELECT secret_col",
                "sensitive_table",
                "abc:def",
            ),
        )
        == []
    )


def test_impala_projection_preserves_unknowns_for_missing_analyzer_fields():
    bundle = build_impala_engine_fact_projection({})
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "impala"
    assert bundle.identity.parser_coverage == "unknown"
    assert bundle.lifecycle.lifecycle == "unknown"
    assert bundle.lifecycle.blocked == "unknown"
    assert bundle.lifecycle.failure == "unknown"
    assert facts["query_wall_clock_ms"].state == "unknown"
    assert facts["total_bytes_read"].state == "unknown"
    assert facts["admission_result"].state == "unknown"
    assert facts["runtime_node_count"].state == "unknown"
    assert facts["exec_node_row_count_conclusions"].state == "unknown"
    assert facts["profile_compatibility"].state == "unknown"
    assert facts["client_fetch_wait_ms"].state == "unknown"

    assert validate_engine_fact_bundle_raw_free(bundle) == []


def test_impala_projection_maps_client_fetch_wait_facts():
    analysis = build_impala_projection_analysis(
        profile_text="""
Summary:
  Query Timeline: 100s
    - Query Submitted: 0ns
    - Last row fetched: 100s
  TotalTime: 100s
F00:
  HDFS_SCAN_NODE (id=00)
    - RowsProduced: 10 (10)
    - TotalTime: 1s (1000000000)
    - ClientFetchWaitTimer: 45s
"""
    )

    bundle = build_impala_engine_fact_projection(analysis)
    facts = bundle.facts_by_id()

    assert facts["client_fetch_wait_ms"].state == "supported"
    assert facts["client_fetch_wait_ms"].value == 45_000
    assert facts["client_fetch_evidence_tier"].value == "strong"
    assert validate_engine_fact_bundle_raw_free(bundle) == []
