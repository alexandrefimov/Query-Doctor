from dataclasses import replace

import pytest

from engine_fact_contract_harness import engine_fact_contract_cases
from query_doctor.analyzer.engine_facts import (
    ENGINE_FACT_BOUNDARY_SCHEMA_VERSION,
    EngineFactContractError,
    engine_fact_boundary_payload,
    engine_fact_boundary_text,
)
from query_doctor.report.safety_validation import (
    contains_raw_sql_like_text,
    validate_report_internal_fingerprints,
)
from query_doctor.safety.browser_display import redact_browser_display_text


def test_engine_fact_boundary_payload_is_raw_free_for_golden_cases():
    for case in engine_fact_contract_cases():
        payload = engine_fact_boundary_payload(case.bundle)
        text = engine_fact_boundary_text(case.bundle)

        assert set(payload) == {"schema_version", "identity", "lifecycle", "fact_groups"}
        assert payload["schema_version"] == ENGINE_FACT_BOUNDARY_SCHEMA_VERSION
        assert payload["identity"]["engine"] == case.expected_engine
        assert payload["identity"]["parser_coverage"] == case.expected_parser_coverage
        assert "source" not in payload["identity"]
        assert set(payload["fact_groups"]) == {"timing", "resources", "stages", "limitations"}

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


def test_engine_fact_boundary_payload_fails_closed_for_unsafe_fact_text():
    case = next(
        case for case in engine_fact_contract_cases() if case.case_id == "impala_finished_clean"
    )
    unsafe_timing = (
        replace(
            case.bundle.timing[0],
            summary="SELECT secret_col FROM sensitive_table",
        ),
        *case.bundle.timing[1:],
    )
    unsafe_bundle = replace(case.bundle, timing=unsafe_timing)

    with pytest.raises(EngineFactContractError, match="not safe for report/browser boundary"):
        engine_fact_boundary_payload(unsafe_bundle)
