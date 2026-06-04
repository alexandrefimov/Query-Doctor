import pytest

from engine_fact_contract_harness import (
    PUBLIC_ENGINE_FACT_KEYS,
    assert_engine_fact_contract_case,
    engine_fact_contract_cases,
)


@pytest.mark.parametrize("case", engine_fact_contract_cases(), ids=lambda case: case.case_id)
def test_engine_fact_golden_cases_follow_shared_raw_free_contract(case):
    assert_engine_fact_contract_case(case)


def test_engine_fact_golden_cases_share_public_shape_without_shared_counters():
    cases = engine_fact_contract_cases()
    public_payloads = {case.case_id: case.bundle.to_public_dict() for case in cases}

    assert all(set(payload) == PUBLIC_ENGINE_FACT_KEYS for payload in public_payloads.values())
    assert {case.expected_engine for case in cases} == {"impala", "spark", "trino"}

    impala_fact_ids = {
        fact["id"]
        for section in ("timing", "resources", "stages", "limitations")
        for fact in public_payloads["impala_finished_clean"][section]
    }
    trino_fact_ids = {
        fact["id"]
        for section in ("timing", "resources", "stages", "limitations")
        for fact in public_payloads["trino_statement_stats_fixture"][section]
    }
    spark_fact_ids = {
        fact["id"]
        for section in ("timing", "resources", "stages", "limitations")
        for fact in public_payloads["spark_history_eventlog_compact_fixture"][section]
    }

    assert "admission_time_ms" in impala_fact_ids
    assert "admission_time_ms" not in trino_fact_ids
    assert "admission_time_ms" not in spark_fact_ids
    assert "trino_stage_count" in trino_fact_ids
    assert "trino_stage_count" not in impala_fact_ids
    assert "trino_stage_count" not in spark_fact_ids
    assert "spark_stage_count" in spark_fact_ids
    assert "spark_stage_count" not in trino_fact_ids
