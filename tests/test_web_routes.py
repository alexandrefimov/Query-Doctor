import json
from pathlib import Path

from query_doctor.web.action_outcomes import (
    SCHEMA_VERSION,
    ActionOutcomeRecord,
    append_action_outcome,
)
from query_doctor.web.command_builders import REPORT_VARIANT_PYTHON
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebSettings
from query_doctor.web.routes import post_route_is_allowed, route_get_request, route_post_request


def web_settings() -> WebSettings:
    return WebSettings(config=Path(".query-doctor-cm.local.json"))


def test_route_get_unknown_path_returns_none():
    response = route_get_request("/not-a-route", web_settings(), WebJobStore())

    assert response is None


def test_route_get_unknown_job_status_returns_safe_json():
    response = route_get_request(
        "/jobs/0123456789abcdef0123456789abcdef/status", web_settings(), WebJobStore()
    )

    assert response is not None
    assert response.status == 404
    assert response.content_type == "application/json; charset=utf-8"
    assert "Analysis job was not found" in response.body
    assert "/Users/" not in response.body
    assert "case_dir" not in response.body


def test_route_get_existing_job_status_returns_json_kind():
    store = WebJobStore()
    job = store.create_running_batch({"parallelism": 3})

    response = route_get_request(f"/jobs/{job.job_id}/status", web_settings(), store)

    assert response is not None
    assert response.status == 200
    assert response.content_type == "application/json; charset=utf-8"
    payload = json.loads(response.body)
    assert payload["status"] == "running"
    assert payload["kind"] == "running"
    assert payload["error"] == ""


def test_route_get_batch_workload_detail_renders_safe_group(tmp_path, monkeypatch):
    fingerprint = "wf_aaaaaaaaaaaaaaaaaaaaaaaa"
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_index": 1,
                        "query_id": "abc:def",
                        "user": "alice",
                        "score": 31,
                        "score_severity": "high",
                        "duration_sec": 12,
                        "workload_fingerprint": fingerprint,
                        "group_fingerprint": fingerprint,
                        "workload_group_member_count": 2,
                        "workload_group_duration_sec_p95": 24,
                    },
                    {
                        "case_index": 2,
                        "query_id": "def:abc",
                        "user": "bob /tmp/raw",
                        "score": 9,
                        "score_severity": "suspicious",
                        "duration_sec": 24,
                        "workload_fingerprint": fingerprint,
                        "group_fingerprint": fingerprint,
                        "workload_group_member_count": 2,
                        "workload_group_duration_sec_p95": 24,
                    },
                ],
                "workload_groups": {
                    "schema_version": 1,
                    "groups": [
                        {
                            "fingerprint": fingerprint,
                            "member_count": 2,
                            "member_case_ids": ["case-001", "case-002"],
                            "shape": {
                                "sql_verb": "select",
                                "query_type": "query",
                                "join_count": 0,
                                "cte_count": 0,
                                "set_operation_count": 0,
                                "scan_count": 1,
                                "exchange_count": 0,
                                "referenced_tables": ["example_warehouse.safe_table"],
                            },
                            "aggregates": {
                                "count": 2,
                                "duration_sec_total": 36,
                                "duration_sec_p50": 12,
                                "duration_sec_p95": 24,
                                "pool_top": "root.analytics /tmp/raw",
                                "primary_bottleneck_top": "stats",
                                "score_top": "high",
                            },
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    outcome_path = tmp_path / "action_outcomes.jsonl"
    monkeypatch.setenv("QUERY_DOCTOR_ACTION_OUTCOMES_PATH", str(outcome_path))
    append_action_outcome(
        ActionOutcomeRecord(
            schema_version=SCHEMA_VERSION,
            recorded_at_iso="2026-05-18T00:00:00+00:00",
            workload_fingerprint=fingerprint,
            case_fingerprint="cf_aaaaaaaaaaaaaaaaaaaaaaaa",
            case_id_local="case-001",
            recommendation_id="stats_refresh_review.v1",
            applied="yes",
            outcome="improved",
            verification_status="comparable_rerun",
        ),
        path=outcome_path,
    )

    response = route_get_request(
        f"/batch/workload/{fingerprint}?ignored=/tmp/evil",
        WebSettings(config=Path(".query-doctor-cm.local.json"), batch_summary=summary_path),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 200
    assert "Repeated workload: Stats review" in response.body
    assert "Workload decision" in response.body
    assert "Outcomes" in response.body
    assert (
        "1 recorded; 1 applied; 1 comparable reruns; improved 1; "
        "last applied action Stats refresh review: improved; "
        "family signal Stats refresh review: improved 1/1 comparable reruns; "
        "feedback sample below threshold (1/5 comparable reruns); "
        "next check stats signal count and workload p95"
    ) in response.body
    assert "What to try next" in response.body
    assert "Recommended next checks" not in response.body
    assert "Stats review" in response.body
    assert "Representative queries" in response.body
    assert 'href="/batch/case/case-002"' in response.body
    assert "local path hidden" in response.body
    assert "/tmp/raw" not in response.body
    assert "/tmp/evil" not in response.body
    assert str(outcome_path) not in response.body


def test_route_get_batch_workload_detail_rejects_unknown_or_invalid_fingerprint(tmp_path):
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text(
        json.dumps({"cases": [], "workload_groups": {"schema_version": 1, "groups": []}}),
        encoding="utf-8",
    )

    response = route_get_request(
        "/batch/workload/..%2Fsecret",
        WebSettings(config=Path(".query-doctor-cm.local.json"), batch_summary=summary_path),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 404
    assert "Workload not found" in response.body
    assert "/secret" not in response.body
    assert "case_dir" not in response.body


def test_post_route_allowed_predicate_matches_static_and_action_routes():
    assert post_route_is_allowed("/batch/run")
    assert post_route_is_allowed("/running/run")
    assert post_route_is_allowed("/optimizer?ignored=1")
    assert post_route_is_allowed("/batch/case/case-001/report")
    assert post_route_is_allowed("/batch/case/case-001/outcome/stats_refresh_review.v1")
    assert post_route_is_allowed("/batch/case/case-001/case-actions")
    assert post_route_is_allowed("/running/case/case-001/optimized-query")
    assert post_route_is_allowed("/query/details/abc%3Adef/llm-actions")
    assert post_route_is_allowed("/query/details/abc%3Adef/case-actions")

    assert not post_route_is_allowed("/not-a-route")
    assert not post_route_is_allowed("/jobs/0123456789abcdef0123456789abcdef/status")
    assert not post_route_is_allowed("/batch/case/case-001")


def test_route_post_public_demo_blocks_all_allowed_actions(tmp_path, monkeypatch):
    outcome_path = tmp_path / "action_outcomes.jsonl"
    monkeypatch.setenv("QUERY_DOCTOR_ACTION_OUTCOMES_PATH", str(outcome_path))
    settings = WebSettings(
        config=Path(".query-doctor-cm.local.json"),
        batch_summary=tmp_path / "batch_summary.json",
        public_demo=True,
        no_llm=True,
    )

    def forbidden_runner(*args, **kwargs):
        raise AssertionError("public demo must not run subprocesses")

    for path in (
        "/batch/run",
        "/running/run",
        "/optimizer",
        "/query-optimizer",
        "/analyze",
        "/batch/case/case-001/report",
        "/batch/case/case-001/optimized-query",
        "/batch/case/case-001/outcome/stats_refresh_review.v1",
        "/running/case/case-001/case-actions",
        "/query/details/abc%3Adef/llm-actions",
    ):
        response = route_post_request(
            path,
            {"query_id": ["abc:def"]},
            settings,
            WebJobStore(),
            runner=forbidden_runner,
        )

        assert response is not None
        assert response.status == 403
        assert "Public demo is read-only" in response.body
        assert "subprocess" not in response.body

    assert not outcome_path.exists()


def test_route_post_batch_case_action_outcome_records_local_jsonl(tmp_path, monkeypatch):
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_index": 1,
                        "query_id": "abc:def",
                        "workload_fingerprint": "wf_1234567890abcdef12345678",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    outcome_path = tmp_path / "action_outcomes.jsonl"
    monkeypatch.setenv("QUERY_DOCTOR_ACTION_OUTCOMES_PATH", str(outcome_path))

    response = route_post_request(
        "/batch/case/case-001/outcome/stats_refresh_review.v1",
        {
            "applied": ["yes"],
            "outcome": ["improved"],
            "verification_status": ["comparable_rerun"],
        },
        WebSettings(config=Path(".query-doctor-cm.local.json"), batch_summary=summary_path),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 303
    assert response.location == "/batch/case/case-001#findings"
    payload = json.loads(outcome_path.read_text(encoding="utf-8"))
    assert payload["recommendation_id"] == "stats_refresh_review.v1"
    assert payload["applied"] == "yes"
    assert payload["outcome"] == "improved"
    assert payload["verification_status"] == "comparable_rerun"
    assert payload["workload_fingerprint"] == "wf_1234567890abcdef12345678"
    assert "abc:def" not in outcome_path.read_text(encoding="utf-8")


def test_route_post_batch_run_dispatches_running_scan_target(monkeypatch):
    calls: list[str] = []

    def fake_start_batch_job(form, settings, store, *, runner):
        calls.append("batch")
        return 303, "/jobs/batch"

    def fake_start_running_job(form, settings, store, *, runner):
        calls.append("running")
        return 303, "/jobs/running"

    monkeypatch.setattr("query_doctor.web.routes.start_batch_job", fake_start_batch_job)
    monkeypatch.setattr("query_doctor.web.routes.start_running_job", fake_start_running_job)

    response = route_post_request(
        "/batch/run",
        {"scan_target": ["running"]},
        web_settings(),
        WebJobStore(),
        runner=lambda *args, **kwargs: None,
    )

    assert response is not None
    assert response.status == 303
    assert response.location == "/jobs/running"
    assert calls == ["running"]


def test_route_post_running_case_report_passes_running_source(monkeypatch):
    captured: dict[str, object] = {}

    def fake_start_batch_case_report_job(
        case_id, settings, store, *, runner, source, report_variant
    ):
        captured.update({"case_id": case_id, "source": source, "report_variant": report_variant})
        return 303, "/jobs/report"

    monkeypatch.setattr(
        "query_doctor.web.routes.start_batch_case_report_job", fake_start_batch_case_report_job
    )

    response = route_post_request(
        "/running/case/case-001/report",
        {},
        web_settings(),
        WebJobStore(),
        runner=lambda *args, **kwargs: None,
    )

    assert response is not None
    assert response.status == 303
    assert response.location == "/jobs/report"
    assert captured == {
        "case_id": "case-001",
        "source": "running",
        "report_variant": REPORT_VARIANT_PYTHON,
    }


def test_route_post_batch_case_validation_uses_batch_source(monkeypatch):
    captured: dict[str, object] = {}

    def fake_validate(case_id, settings, store, form, *, source):
        captured.update({"case_id": case_id, "source": source, "form": form})
        return 200, "validation body"

    monkeypatch.setattr(
        "query_doctor.web.routes.handle_batch_case_external_rewrite_validation", fake_validate
    )

    response = route_post_request(
        "/batch/case/case-002/validate-rewrite",
        {"external_rewrite_sql": ["select 1"]},
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 200
    assert response.body == "validation body"
    assert captured == {
        "case_id": "case-002",
        "source": "batch",
        "form": {"external_rewrite_sql": ["select 1"]},
    }


def test_route_post_specific_query_action_unquotes_query_id(monkeypatch):
    captured: dict[str, object] = {}

    def fake_start_specific_query_report_job(query_id, settings, store, *, runner, report_variant):
        captured["query_id"] = query_id
        captured["report_variant"] = report_variant
        return 303, "/jobs/query-report"

    monkeypatch.setattr(
        "query_doctor.web.routes.start_specific_query_report_job",
        fake_start_specific_query_report_job,
    )

    response = route_post_request(
        "/query/details/abc%3Adef/report",
        {},
        web_settings(),
        WebJobStore(),
        runner=lambda *args, **kwargs: None,
    )

    assert response is not None
    assert response.status == 303
    assert response.location == "/jobs/query-report"
    assert captured == {"query_id": "abc:def", "report_variant": REPORT_VARIANT_PYTHON}


def test_route_post_unknown_path_returns_none():
    response = route_post_request("/not-a-route", {}, web_settings(), WebJobStore())

    assert response is None
