import json

from primary_bottleneck_fixture_corpus import (
    PRIMARY_BOTTLENECK_EXPECTED_KEYS,
    PRIMARY_BOTTLENECK_FIXTURE_CONFIDENCES,
    PRIMARY_BOTTLENECK_FIXTURE_DIR,
    PRIMARY_BOTTLENECK_FIXTURE_KEYS,
    PRIMARY_BOTTLENECK_FIXTURE_LABELS,
    PRIMARY_BOTTLENECK_FIXTURE_NAME_PATTERN,
    UNKNOWN_PRIMARY_REASON_COVERAGE,
    primary_bottleneck_fixture_coverage,
    primary_bottleneck_fixture_expected_results,
    primary_bottleneck_fixture_names,
    primary_bottleneck_fixture_payloads,
    reason_id_is_known,
)
from query_doctor.analyzer.case_bottleneck import classify_case_primary_bottleneck


def test_primary_bottleneck_json_fixtures_match_expected_classification():
    assert primary_bottleneck_fixture_names(), "expected primary bottleneck fixtures"
    for fixture_name, payload in primary_bottleneck_fixture_payloads().items():
        result = json.loads(
            json.dumps(classify_case_primary_bottleneck(payload["analysis"]).to_dict())
        )

        assert result == payload["expected"], fixture_name


def test_primary_bottleneck_json_fixtures_are_safe_sanitized_inputs():
    fixture_text = "\n".join(
        (PRIMARY_BOTTLENECK_FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")
        for fixture_name in primary_bottleneck_fixture_names()
    )

    for forbidden in [
        "SELECT ",
        "Query (id=",
        ".example.",
        "/tmp/",
        "/Users/",
        "hdfs://",
        "RAW_",
        "Authorization",
        "profile_digest.md",
    ]:
        assert forbidden not in fixture_text


def test_primary_bottleneck_json_fixture_corpus_has_stable_schema():
    payloads = primary_bottleneck_fixture_payloads()
    assert payloads, "expected primary bottleneck fixtures"

    invalid_names = [
        fixture_name
        for fixture_name in payloads
        if not PRIMARY_BOTTLENECK_FIXTURE_NAME_PATTERN.fullmatch(fixture_name)
    ]
    assert not invalid_names

    invalid_payload_keys = {
        fixture_name: sorted(payload)
        for fixture_name, payload in payloads.items()
        if set(payload) != PRIMARY_BOTTLENECK_FIXTURE_KEYS
    }
    assert not invalid_payload_keys

    invalid_expected_keys = {
        fixture_name: sorted(payload["expected"])
        for fixture_name, payload in payloads.items()
        if set(payload["expected"]) != PRIMARY_BOTTLENECK_EXPECTED_KEYS
    }
    assert not invalid_expected_keys

    invalid_expected_values = {}
    invalid_reason_ids = {}
    for fixture_name, payload in payloads.items():
        analysis = payload["analysis"]
        expected = payload["expected"]
        reasons = expected["reasons"]

        value_errors = []
        if not isinstance(analysis, dict):
            value_errors.append("analysis_not_object")
        if expected["label"] not in PRIMARY_BOTTLENECK_FIXTURE_LABELS:
            value_errors.append(f"unknown_label:{expected['label']}")
        if expected["confidence"] not in PRIMARY_BOTTLENECK_FIXTURE_CONFIDENCES:
            value_errors.append(f"unknown_confidence:{expected['confidence']}")
        if (
            not isinstance(reasons, list)
            or not reasons
            or any(not isinstance(reason, str) or not reason for reason in reasons)
            or len(reasons) != len(set(reasons))
        ):
            value_errors.append("invalid_reasons")
        if value_errors:
            invalid_expected_values[fixture_name] = value_errors

        unknown_reasons = [
            reason
            for reason in reasons
            if isinstance(reason, str) and not reason_id_is_known(reason)
        ]
        if unknown_reasons:
            invalid_reason_ids[fixture_name] = unknown_reasons

    assert not invalid_expected_values
    assert not invalid_reason_ids


def test_primary_bottleneck_json_fixture_corpus_covers_taxonomy():
    expected_results = primary_bottleneck_fixture_expected_results()
    coverage = primary_bottleneck_fixture_coverage(expected_results)

    assert expected_results
    assert coverage.covered_labels == PRIMARY_BOTTLENECK_FIXTURE_LABELS
    assert coverage.covered_confidences == PRIMARY_BOTTLENECK_FIXTURE_CONFIDENCES
    assert coverage.unknown_reasons == UNKNOWN_PRIMARY_REASON_COVERAGE
    assert set(coverage.reasons_by_label) == PRIMARY_BOTTLENECK_FIXTURE_LABELS
    assert not coverage.missing_reason_families
