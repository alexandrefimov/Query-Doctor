import json

import pytest

from engine_fact_contract_harness import engine_fact_contract_cases
from query_doctor.analyzer.engine_fact_consumer import (
    ENGINE_FACT_CONSUMER_PROBE_SCHEMA_VERSION,
    engine_fact_consumer_probe,
    engine_fact_consumer_probe_from_boundary,
    engine_fact_consumer_probe_text,
)
from query_doctor.analyzer.engine_facts import (
    ENGINE_FACT_BOUNDARY_SCHEMA_VERSION,
    EngineFactContractError,
    engine_fact_boundary_payload,
)
from query_doctor.report.safety_validation import (
    contains_raw_sql_like_text,
    validate_report_internal_fingerprints,
)
from query_doctor.safety.browser_display import redact_browser_display_text


def test_engine_fact_consumer_probe_is_raw_free_for_golden_cases():
    for case in engine_fact_contract_cases():
        probe = engine_fact_consumer_probe(case.bundle)
        text = engine_fact_consumer_probe_text(case.bundle)

        assert probe["schema_version"] == ENGINE_FACT_CONSUMER_PROBE_SCHEMA_VERSION
        assert probe["source_schema_version"] == ENGINE_FACT_BOUNDARY_SCHEMA_VERSION
        assert probe["engine"] == case.expected_engine
        assert probe["parser_coverage"] == case.expected_parser_coverage
        assert probe["lifecycle"] == case.expected_lifecycle
        assert set(probe["state_counts"]) == {"supported", "not_observed", "unknown"}
        assert sum(probe["state_counts"].values()) == (
            len(probe["supported_fact_ids"])
            + len(probe["not_observed_fact_ids"])
            + len(probe["unknown_fact_ids"])
        )

        assert not contains_raw_sql_like_text(text)
        assert validate_report_internal_fingerprints(text) == []
        assert (
            redact_browser_display_text(
                text,
                redact_field_names=True,
                redact_artifact_markers=True,
                redact_model_names=True,
                redact_sql_snippets=True,
                redact_infrastructure=True,
            )
            == text
        )

        forbidden = tuple(
            token
            for token in case.forbidden_tokens + case.forbidden_public_substrings
            if token != "schema"
        )
        for token in forbidden:
            assert token not in text
        assert "impala_analyzer_projection" not in text
        assert "trino_statement_stats_fixture" not in text
        assert "trino_event_listener_fixture" not in text


@pytest.mark.parametrize(
    ("case_id", "expected_signal"),
    (
        ("impala_admission_queued", "blocked_or_admission_wait"),
        ("impala_spill_observed", "spill_or_scratch_evidence"),
        ("impala_failed_query", "query_failed"),
        ("impala_missing_sections", "parser_coverage_unknown"),
        ("trino_statement_stats_fixture", "limitation_unknown:admission_control"),
        ("trino_failed_statement_stats_fixture", "query_failed"),
        (
            "trino_failure_category_statement_stats_fixture",
            "failure_category:resource_limit",
        ),
        ("trino_blocked_statement_stats_fixture", "blocked_or_admission_wait"),
        ("trino_stage_skew_statement_stats_fixture", "stage_skew_candidate"),
        ("trino_connector_metric_present_statement_stats_fixture", "connector_metric_signal"),
        (
            "trino_connector_metric_absent_statement_stats_fixture",
            "limitation_unknown:admission_control",
        ),
        ("trino_completed_event_fixture", "spill_or_scratch_evidence"),
        ("trino_completed_event_missing_fields_fixture", "limitation_unknown:admission_control"),
    ),
)
def test_engine_fact_consumer_probe_attention_signals_are_state_backed(
    case_id,
    expected_signal,
):
    case = next(case for case in engine_fact_contract_cases() if case.case_id == case_id)

    probe = engine_fact_consumer_probe(case.bundle)

    assert expected_signal in probe["attention_signal_ids"]


def test_engine_fact_consumer_probe_consumes_boundary_payload_without_bundle_access():
    case = next(
        case for case in engine_fact_contract_cases() if case.case_id == "impala_finished_clean"
    )
    boundary_payload = engine_fact_boundary_payload(case.bundle)

    probe = engine_fact_consumer_probe_from_boundary(json.loads(json.dumps(boundary_payload)))

    assert probe == engine_fact_consumer_probe(case.bundle)


def test_engine_fact_consumer_probe_rejects_invalid_boundary_state():
    case = next(
        case for case in engine_fact_contract_cases() if case.case_id == "impala_finished_clean"
    )
    payload = engine_fact_boundary_payload(case.bundle)
    payload["fact_groups"]["timing"][0]["state"] = "observed"

    with pytest.raises(EngineFactContractError, match="unsupported boundary diagnostic state"):
        engine_fact_consumer_probe_from_boundary(payload)


@pytest.mark.parametrize(
    ("state", "value", "expected_error"),
    (
        ("supported", "RawException", "unsafe failure category"),
        ("unknown", "resource_limit", "unsupported failure category value"),
    ),
)
def test_engine_fact_consumer_probe_rejects_invalid_failure_category(
    state,
    value,
    expected_error,
):
    case = next(
        case for case in engine_fact_contract_cases() if case.case_id == "impala_finished_clean"
    )
    payload = engine_fact_boundary_payload(case.bundle)
    payload["lifecycle"]["failure_category"] = {
        "state": state,
        "value": value,
    }

    with pytest.raises(EngineFactContractError, match=expected_error):
        engine_fact_consumer_probe_from_boundary(payload)
