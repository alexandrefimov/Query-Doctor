from __future__ import annotations

import copy
import json
from pathlib import Path

from engine_fact_contract_harness import trino_golden_cases
from query_doctor.analyzer.engine_facts import engine_fact_boundary_payload
from query_doctor.safety.browser_display import redact_browser_display_text
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebSettings
from query_doctor.web.routes import post_route_is_allowed, route_get_request, route_post_request
from trino_metadata_summary_boundary import (
    metadata_summary_boundary,
    metadata_summary_forbidden_tokens,
)


def web_settings() -> WebSettings:
    return WebSettings(config=Path(".query-doctor-cm.local.json"))


def test_trino_compact_get_route_renders_safe_form_without_product_support_claim():
    response = route_get_request("/trino/compact-diagnosis", web_settings(), WebJobStore())

    assert response is not None
    assert response.status == 200
    assert 'action="/trino/compact-diagnosis"' in response.body
    assert 'name="boundary_json"' in response.body
    assert 'name="sample_index"' in response.body
    assert "Trino compact diagnosis" in response.body
    assert "already raw-free Trino engine fact boundary" in response.body
    assert "selected sample boundary" in response.body
    assert "not Recent, materialized Details, Python Report, or optimizer support" in response.body
    assert "source_schema_version" not in response.body
    assert "trino_query_detail_fixture" not in response.body


def test_trino_compact_post_route_renders_attention_areas_without_echoing_input():
    boundary = _boundary_for_case("trino_query_detail_export_fixture")
    boundary_text = json.dumps(boundary, ensure_ascii=True, sort_keys=True)

    response = route_post_request(
        "/trino/compact-diagnosis",
        {"boundary_json": [boundary_text]},
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 200
    assert "Trino spill observed" in response.body
    assert "Trino stage skew candidate" in response.body
    assert "Trino task retries" in response.body
    assert "Diagnostic lane" in response.body
    assert "one_query_attention_ready" in response.body
    assert "one_query_boundary" in response.body
    assert "comparable_one_query_rerun" in response.body
    assert "Root cause" in response.body
    assert "not_claimed" in response.body
    assert "Trino SQL execution" in response.body
    assert "not_performed" in response.body
    assert response.body.count("<textarea") == 1
    for fragment in (
        boundary_text,
        "source_schema_version",
        "trino_query_detail_fixture",
        "engine_fact_boundary_v1",
        "fact_groups",
        "sourceContract",
    ):
        assert fragment not in response.body


def test_trino_compact_post_route_reads_selected_package_boundary_without_echoing_input():
    package_boundary = _package_boundary_export(
        [
            _boundary_for_case("trino_query_list_contract_probe_fixture"),
            _boundary_for_case("trino_query_detail_export_fixture"),
        ]
    )
    boundary_text = json.dumps(package_boundary, ensure_ascii=True, sort_keys=True)

    response = route_post_request(
        "/trino/compact-diagnosis",
        {"boundary_json": [boundary_text], "sample_index": ["1"]},
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 200
    assert "Trino spill observed" in response.body
    assert "Trino stage skew candidate" in response.body
    assert "Trino task retries" in response.body
    assert response.body.count("<textarea") == 1
    for fragment in (
        boundary_text,
        "sample_fact_boundaries",
        "trino_test_package",
        "engine_fact_boundary_v1",
        "source_schema_version",
    ):
        assert fragment not in response.body


def test_trino_compact_post_route_rejects_multi_sample_package_without_index():
    package_boundary = _package_boundary_export(
        [
            _boundary_for_case("trino_query_list_contract_probe_fixture"),
            _boundary_for_case("trino_query_detail_export_fixture"),
        ]
    )
    boundary_text = json.dumps(package_boundary, ensure_ascii=True, sort_keys=True)

    response = route_post_request(
        "/trino/compact-diagnosis",
        {"boundary_json": [boundary_text]},
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "pass --sample-index" in response.body
    assert boundary_text not in response.body
    assert "sample_fact_boundaries" not in response.body


def test_trino_compact_post_route_rejects_invalid_sample_index_without_echoing_input():
    package_boundary = _package_boundary_export(
        [_boundary_for_case("trino_query_detail_export_fixture")]
    )
    boundary_text = json.dumps(package_boundary, ensure_ascii=True, sort_keys=True)

    response = route_post_request(
        "/trino/compact-diagnosis",
        {"boundary_json": [boundary_text], "sample_index": ["not-a-number"]},
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "sample index must be a non-negative integer" in response.body
    assert boundary_text not in response.body
    assert "not-a-number" not in response.body


def test_trino_compact_post_rejects_raw_like_payload_without_echoing_fragments():
    raw_text = json.dumps(
        {
            "schema_version": "engine_fact_boundary_v1",
            "engine": "trino",
            "queryText": "SELECT secret_col FROM guarded_table",
            "queryId": "20260603_120000_00001_abcd1",
        },
        ensure_ascii=True,
        sort_keys=True,
    )
    response = route_post_request(
        "/trino/compact-diagnosis",
        {"boundary_json": [raw_text]},
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "Safe Trino compact state" in response.body
    assert "rejected input is hidden" in response.body
    for fragment in (
        raw_text,
        "SELECT",
        "secret_col",
        "guarded_table",
        "20260603_120000_00001_abcd1",
        "queryText",
        "queryId",
    ):
        assert fragment not in response.body


def test_trino_compact_post_rejects_non_trino_boundary_without_echoing_input():
    boundary = copy.deepcopy(_boundary_for_case("trino_query_detail_export_fixture"))
    boundary["identity"]["engine"] = "impala"
    boundary_text = json.dumps(boundary, ensure_ascii=True, sort_keys=True)

    response = route_post_request(
        "/trino/compact-diagnosis",
        {"boundary_json": [boundary_text]},
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "Safe Trino compact state" in response.body
    assert "rejected input is hidden" in response.body
    assert boundary_text not in response.body
    assert "trino_query_detail_fixture" not in response.body


def test_trino_compact_post_rejects_metadata_summary_boundary_without_echoing_input():
    boundary_text = json.dumps(metadata_summary_boundary(), ensure_ascii=True, sort_keys=True)

    response = route_post_request(
        "/trino/compact-diagnosis",
        {"boundary_json": [boundary_text]},
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "Safe Trino compact state" in response.body
    assert "does not accept aggregate metadata summary boundaries" in response.body
    assert "rejected input is hidden" in response.body
    assert boundary_text not in response.body
    for token in metadata_summary_forbidden_tokens():
        assert token not in response.body


def test_trino_compact_post_rejects_oversized_payload_without_echoing_input():
    response = route_post_request(
        "/trino/compact-diagnosis",
        {"boundary_json": ["x" * (256 * 1024 + 1)]},
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "accepted compact payload limit" in response.body
    assert "x" * 200 not in response.body


def test_trino_compact_post_route_is_allowed():
    assert post_route_is_allowed("/trino/compact-diagnosis")
    assert post_route_is_allowed("/trino/compact-diagnosis?ignored=1")


def test_trino_compact_result_is_browser_display_safe():
    response = route_post_request(
        "/trino/compact-diagnosis",
        {"boundary_json": [json.dumps(_boundary_for_case("trino_query_detail_export_fixture"))]},
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    redacted = redact_browser_display_text(
        response.body,
        redact_field_names=True,
        redact_artifact_markers=True,
        redact_model_names=True,
        redact_sql_snippets=True,
        redact_infrastructure=True,
    )
    assert redacted == response.body


def _boundary_for_case(case_id: str) -> dict:
    case = next(case for case in trino_golden_cases() if case.case_id == case_id)
    return engine_fact_boundary_payload(case.bundle)


def _package_boundary_export(boundaries: list[dict]) -> dict:
    return {
        "schema_version": "trino_evidence_package_import_v1",
        "summary": {"package_id": "trino_test_package"},
        "sample_fact_boundaries": [
            {"case": f"case-{index}", "source_type": "test", "boundary": boundary}
            for index, boundary in enumerate(boundaries)
        ],
    }
