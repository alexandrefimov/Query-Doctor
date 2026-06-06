from __future__ import annotations

import copy
import json
from pathlib import Path

from query_doctor.cm.models import CMClientError
from query_doctor.spark.history_server import SparkHistoryServerCompactResult
from scripts import spark_one_application_handoff


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "spark_history_server_compact_source_warning.json"
)
HISTORY_SERVER_URL = "https://spark-history.example.test:18080"
APPLICATION_ID = "application_1700000000000_0042"
APPLICATION_ATTEMPT_ID = "attempt_secret_2"
SQL_EXECUTION_ID = "sql_exec_secret_17"


def test_spark_one_application_handoff_writes_artifacts_and_runs_readiness(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    compact_path = tmp_path / "spark-secret-compact.json"
    diagnosis_path = tmp_path / "spark-secret-diagnosis.json"
    boundary_path = tmp_path / "spark-secret-boundary.json"
    summary_path = tmp_path / "spark-secret-summary.json"
    product_surface_summary_path = tmp_path / "spark-secret-surface-boundary-summary.json"
    calls: list[dict[str, object]] = []

    def fake_collect(**kwargs):
        calls.append(kwargs)
        return SparkHistoryServerCompactResult(
            payload=_history_server_payload(source_warning=False),
            warnings=(),
            attempted_endpoints=6,
            successful_endpoints=6,
        )

    monkeypatch.setattr(
        spark_one_application_handoff,
        "collect_spark_history_server_compact_summary",
        fake_collect,
    )

    exit_code = spark_one_application_handoff.main(
        [
            "--redaction-reviewed",
            "--require-supported-attention",
            "--fail-on-source-warnings",
            "--history-server-url",
            HISTORY_SERVER_URL,
            "--application-id",
            APPLICATION_ID,
            "--application-attempt-id",
            APPLICATION_ATTEMPT_ID,
            "--sql-execution-id",
            SQL_EXECUTION_ID,
            "--compact-out",
            str(compact_path),
            "--diagnosis-out",
            str(diagnosis_path),
            "--boundary-facts-out",
            str(boundary_path),
            "--summary-json",
            str(summary_path),
            "--product-surface-summary-out",
            str(product_surface_summary_path),
        ]
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    compact = json.loads(compact_path.read_text(encoding="utf-8"))
    diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
    boundary = json.loads(boundary_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    product_surface_summary = json.loads(product_surface_summary_path.read_text(encoding="utf-8"))
    rendered = json.dumps(
        {
            "boundary": boundary,
            "compact": compact,
            "diagnosis": diagnosis,
            "product_surface_summary": product_surface_summary,
            "summary": summary,
        },
        sort_keys=True,
    )
    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["history_server_url"] == HISTORY_SERVER_URL
    assert calls[0]["application_id"] == APPLICATION_ID
    assert calls[0]["application_attempt_id"] == APPLICATION_ATTEMPT_ID
    assert calls[0]["sql_execution_id"] == SQL_EXECUTION_ID
    assert "opener" not in calls[0]
    assert "[spark-one-application-handoff] collection" in captured.out
    assert "Spark History compact collection: accepted" in captured.out
    assert "warning_count=0" in captured.out
    assert "support_claim=not_claimed" in captured.out
    assert "spark_job_execution=not_performed" in captured.out
    assert "Artifact paths: not_printed" in captured.out
    assert "[spark-one-application-handoff] readiness" in captured.out
    assert "Spark compact readiness: ok" in captured.out
    assert "[spark-one-application-handoff] product-surface" in captured.out
    assert "Spark product-surface boundary audit: ok" in captured.out
    assert compact["sourceContract"] == "spark_history_server_compact_v1"
    assert compact["sourceCoverage"]["warningIds"] == []
    assert diagnosis["schema_version"] == "spark_compact_diagnosis_v1"
    assert diagnosis["support_status"] == "experimental_compact_intake"
    assert diagnosis["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert boundary["schema_version"] == "engine_fact_boundary_v1"
    assert boundary["identity"]["engine"] == "spark"
    assert summary["schema_version"] == "spark_one_application_handoff_summary_v1"
    assert summary["status"] == "ok"
    assert summary["pipeline"] == {
        "boundary_facts": "written",
        "collection": "accepted",
        "compact_diagnosis": "accepted",
        "readiness": "ok",
    }
    assert summary["collection"] == {
        "attempted_endpoint_count": 6,
        "successful_endpoint_count": 6,
        "warning_count": 0,
        "warning_ids": [],
    }
    assert summary["artifacts"] == {
        "boundary_facts_json": "written",
        "compact_json": "written",
        "diagnosis_json": "written",
        "paths": "not_printed",
    }
    assert summary["readiness"]["schema_version"] == "spark_compact_readiness_summary_v1"
    assert summary["readiness"]["status"] == "ok"
    assert summary["readiness"]["boundary"]["support_claim"] == "not_claimed"
    assert product_surface_summary["summary_kind"] == "spark_product_surface_boundary_audit_v1"
    assert product_surface_summary["status"] == "ok"
    assert product_surface_summary["boundary"]["product_surface"] == "not_promoted"
    assert product_surface_summary["boundary"]["live_known_query_diagnosis"] == "not_wired"
    assert product_surface_summary["boundary"]["spark_job_execution"] == "not_performed"
    assert product_surface_summary["counts"]["compact_json_count"] == 1
    assert product_surface_summary["counts"]["diagnosis_json_checked_count"] == 1
    assert product_surface_summary["counts"]["diagnostic_lane_checked_count"] == 1
    assert product_surface_summary["diagnostic_lane"]["schema_version"] == (
        "spark_compact_diagnostic_lane_v1"
    )
    assert product_surface_summary["diagnostic_lane"]["readiness"] == {"compact_attention_ready": 1}
    assert product_surface_summary["diagnostic_lane"]["source_granularity"] == {
        "exact_sql_execution_compact": 1
    }
    assert product_surface_summary["diagnostic_lane"]["verification_scope"] == {
        "comparable_sql_execution_rerun": 1
    }
    assert product_surface_summary["fact_states"]["supported"] >= 1
    assert product_surface_summary["registry"]["spark_product_routes"] == "blocked"
    assert product_surface_summary["registry"]["spark_product_cli"] == "blocked"
    assert product_surface_summary["issues"] == {"counts": {}, "items": []}
    assert captured.err == ""
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output
        assert fragment not in rendered


def test_spark_one_application_handoff_passes_explicit_test_opener(
    tmp_path: Path,
    monkeypatch,
) -> None:
    compact_path = tmp_path / "spark-secret-compact.json"
    diagnosis_path = tmp_path / "spark-secret-diagnosis.json"
    opener = object()
    calls: list[dict[str, object]] = []

    def fake_collect(**kwargs):
        calls.append(kwargs)
        return SparkHistoryServerCompactResult(
            payload=_history_server_payload(source_warning=False),
            warnings=(),
            attempted_endpoints=6,
            successful_endpoints=6,
        )

    monkeypatch.setattr(
        spark_one_application_handoff,
        "collect_spark_history_server_compact_summary",
        fake_collect,
    )

    exit_code = spark_one_application_handoff.main(
        [
            "--redaction-reviewed",
            "--history-server-url",
            HISTORY_SERVER_URL,
            "--application-id",
            APPLICATION_ID,
            "--compact-out",
            str(compact_path),
            "--diagnosis-out",
            str(diagnosis_path),
        ],
        opener=opener,
    )

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["opener"] is opener


def test_spark_one_application_handoff_returns_failed_readiness_for_source_warnings(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    compact_path = tmp_path / "spark-secret-compact.json"
    diagnosis_path = tmp_path / "spark-secret-diagnosis.json"
    summary_path = tmp_path / "spark-secret-summary.json"
    product_surface_summary_path = tmp_path / "spark-secret-surface-boundary-summary.json"

    def fake_collect(**_kwargs):
        return SparkHistoryServerCompactResult(
            payload=_history_server_payload(source_warning=True),
            warnings=("spark_history_stages_unavailable",),
            attempted_endpoints=6,
            successful_endpoints=5,
        )

    monkeypatch.setattr(
        spark_one_application_handoff,
        "collect_spark_history_server_compact_summary",
        fake_collect,
    )

    exit_code = spark_one_application_handoff.main(
        [
            "--redaction-reviewed",
            "--fail-on-source-warnings",
            "--history-server-url",
            HISTORY_SERVER_URL,
            "--application-id",
            APPLICATION_ID,
            "--compact-out",
            str(compact_path),
            "--diagnosis-out",
            str(diagnosis_path),
            "--summary-json",
            str(summary_path),
            "--product-surface-summary-out",
            str(product_surface_summary_path),
        ]
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    product_surface_summary = json.loads(product_surface_summary_path.read_text(encoding="utf-8"))
    rendered = json.dumps(product_surface_summary, sort_keys=True)
    assert exit_code == 1
    assert "warning_count=1" in captured.out
    assert "Spark compact readiness: failed" in captured.out
    assert "spark_source_warning_present" in captured.out
    assert "[spark-one-application-handoff] product-surface" in captured.out
    assert "Spark product-surface boundary audit: ok" in captured.out
    assert summary["status"] == "failed"
    assert summary["collection"]["warning_ids"] == ["spark_history_stages_unavailable"]
    assert summary["readiness"]["status"] == "failed"
    assert summary["readiness"]["issues"]["counts"] == {"spark_source_warning_present": 1}
    assert product_surface_summary["summary_kind"] == "spark_product_surface_boundary_audit_v1"
    assert product_surface_summary["status"] == "ok"
    assert product_surface_summary["counts"]["source_warning_count"] == 1
    assert product_surface_summary["diagnostic_lane"]["readiness"] == {
        "compact_source_warnings_present": 1
    }
    assert product_surface_summary["diagnostic_lane"]["source_granularity"] == {
        "exact_sql_execution_compact": 1
    }
    assert product_surface_summary["diagnostic_lane"]["verification_scope"] == {
        "source_coverage_review": 1
    }
    assert product_surface_summary["fact_states"]["supported"] >= 1
    assert product_surface_summary["issues"] == {"counts": {}, "items": []}
    assert compact_path.exists()
    assert diagnosis_path.exists()
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output
        assert fragment not in rendered


def test_spark_one_application_handoff_requires_redaction_review_before_collection(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        spark_one_application_handoff,
        "collect_spark_history_server_compact_summary",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("handoff must reject before collection")
        ),
    )

    exit_code = spark_one_application_handoff.main(
        [
            "--history-server-url",
            HISTORY_SERVER_URL,
            "--application-id",
            APPLICATION_ID,
            "--compact-out",
            str(tmp_path / "spark-secret-compact.json"),
            "--diagnosis-out",
            str(tmp_path / "spark-secret-diagnosis.json"),
        ]
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_spark_one_application_handoff_rejects_output_overlap_before_collection(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    compact_path = tmp_path / "spark-secret-compact.json"
    compact_path.write_text("original", encoding="utf-8")
    monkeypatch.setattr(
        spark_one_application_handoff,
        "collect_spark_history_server_compact_summary",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("handoff must reject before collection")
        ),
    )

    exit_code = spark_one_application_handoff.main(
        [
            "--redaction-reviewed",
            "--history-server-url",
            HISTORY_SERVER_URL,
            "--application-id",
            APPLICATION_ID,
            "--compact-out",
            str(compact_path),
            "--diagnosis-out",
            str(compact_path),
        ]
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 2
    assert captured.out == ""
    assert "output artifacts must be distinct" in captured.err
    assert compact_path.read_text(encoding="utf-8") == "original"
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_spark_one_application_handoff_rejects_summary_overlap_before_collection(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    compact_path = tmp_path / "spark-secret-compact.json"
    compact_path.write_text("original", encoding="utf-8")
    monkeypatch.setattr(
        spark_one_application_handoff,
        "collect_spark_history_server_compact_summary",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("handoff must reject before collection")
        ),
    )

    exit_code = spark_one_application_handoff.main(
        [
            "--redaction-reviewed",
            "--history-server-url",
            HISTORY_SERVER_URL,
            "--application-id",
            APPLICATION_ID,
            "--compact-out",
            str(compact_path),
            "--diagnosis-out",
            str(tmp_path / "spark-secret-diagnosis.json"),
            "--summary-json",
            str(compact_path),
        ]
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 2
    assert captured.out == ""
    assert "output artifacts must be distinct" in captured.err
    assert compact_path.read_text(encoding="utf-8") == "original"
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_spark_one_application_handoff_rejects_product_surface_summary_overlap_before_collection(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    compact_path = tmp_path / "spark-secret-compact.json"
    compact_path.write_text("original", encoding="utf-8")
    monkeypatch.setattr(
        spark_one_application_handoff,
        "collect_spark_history_server_compact_summary",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("handoff must reject before collection")
        ),
    )

    exit_code = spark_one_application_handoff.main(
        [
            "--redaction-reviewed",
            "--history-server-url",
            HISTORY_SERVER_URL,
            "--application-id",
            APPLICATION_ID,
            "--compact-out",
            str(compact_path),
            "--diagnosis-out",
            str(tmp_path / "spark-secret-diagnosis.json"),
            "--product-surface-summary-out",
            str(compact_path),
        ]
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 2
    assert captured.out == ""
    assert "output artifacts must be distinct" in captured.err
    assert compact_path.read_text(encoding="utf-8") == "original"
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_spark_one_application_handoff_rejects_collection_error_without_echo(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    def fake_collect(**_kwargs):
        raise CMClientError(
            f"raw failure {HISTORY_SERVER_URL} {APPLICATION_ID} spark-secret-compact.json"
        )

    monkeypatch.setattr(
        spark_one_application_handoff,
        "collect_spark_history_server_compact_summary",
        fake_collect,
    )

    exit_code = spark_one_application_handoff.main(
        [
            "--redaction-reviewed",
            "--history-server-url",
            HISTORY_SERVER_URL,
            "--application-id",
            APPLICATION_ID,
            "--compact-out",
            str(tmp_path / "spark-secret-compact.json"),
            "--diagnosis-out",
            str(tmp_path / "spark-secret-diagnosis.json"),
        ]
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 1
    assert captured.out == ""
    assert "Spark History compact collection failed" in captured.err
    assert "raw failure" not in output
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_spark_one_application_handoff_stays_dev_only_not_console_script() -> None:
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "spark_one_application_handoff" not in pyproject_text
    assert "query-doctor-spark-one-application-handoff" not in pyproject_text


def _history_server_payload(*, source_warning: bool) -> dict[str, object]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload = copy.deepcopy(payload)
    if not source_warning:
        payload["sourceCoverage"] = {
            "attemptedEndpointCount": 6,
            "factState": "supported",
            "successfulEndpointCount": 6,
            "warningIds": [],
        }
        for limitation in payload["limitations"]:
            if limitation["id"] == "spark_history_source_coverage":
                limitation["state"] = "supported"
    return payload


def _protected_fragments(tmp_path: Path) -> tuple[str, ...]:
    return (
        str(tmp_path),
        "spark-secret-compact.json",
        "spark-secret-diagnosis.json",
        "spark-secret-boundary.json",
        "spark-secret-summary.json",
        "spark-secret-surface-boundary-summary.json",
        HISTORY_SERVER_URL,
        APPLICATION_ID,
        APPLICATION_ATTEMPT_ID,
        SQL_EXECUTION_ID,
        "SELECT",
        "spark-history.example.test",
    )
