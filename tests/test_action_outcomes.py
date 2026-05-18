import json

import pytest

from query_doctor.web.action_outcomes import (
    action_outcome_record_from_case,
    append_action_outcome,
    load_action_outcomes,
)
from query_doctor.web.models import WebError


def test_action_outcome_record_is_raw_free_and_loadable(tmp_path):
    record = action_outcome_record_from_case(
        case_id="case-001",
        case={
            "query_id": "abc:def",
            "workload_fingerprint": "wf_1234567890abcdef12345678",
        },
        recommendation_id="stats_refresh_review.v1",
        form={"applied": ["yes"], "outcome": ["improved"], "note": ["/Users/example/case"]},
    )
    path = append_action_outcome(record, path=tmp_path / "action_outcomes.jsonl")

    text = path.read_text(encoding="utf-8")
    assert "abc:def" not in text
    assert "/Users/example" not in text
    assert "case-001" in text

    loaded = load_action_outcomes(path=path)
    assert len(loaded) == 1
    assert loaded[0].recommendation_id == "stats_refresh_review.v1"
    assert loaded[0].applied == "yes"
    assert loaded[0].outcome == "improved"
    assert loaded[0].note_redacted == "<local path hidden>"


def test_action_outcomes_skip_malformed_and_unknown_records(tmp_path):
    path = tmp_path / "action_outcomes.jsonl"
    valid = {
        "schema_version": 1,
        "recorded_at_iso": "2026-05-18T00:00:00+00:00",
        "workload_fingerprint": "wf_1234567890abcdef12345678",
        "case_fingerprint": "cf_1234567890abcdef12345678",
        "case_id_local": "case-001",
        "recommendation_id": "query_optimization_review.v1",
        "applied": "skip",
        "outcome": "not_applicable",
        "note_redacted": "",
    }
    invalid = dict(valid, recommendation_id="raw_unknown.v1")
    path.write_text(
        "{not json}\n" + json.dumps(invalid) + "\n" + json.dumps(valid) + "\n",
        encoding="utf-8",
    )

    loaded = load_action_outcomes(path=path)

    assert len(loaded) == 1
    assert loaded[0].recommendation_id == "query_optimization_review.v1"


def test_action_outcome_rejects_unknown_recommendation_id():
    with pytest.raises(WebError):
        action_outcome_record_from_case(
            case_id="case-001",
            case={
                "query_id": "abc:def",
                "workload_fingerprint": "wf_1234567890abcdef12345678",
            },
            recommendation_id="freeform.v1",
            form={"applied": ["yes"], "outcome": ["improved"]},
        )
