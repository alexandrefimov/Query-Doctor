from __future__ import annotations

import json
from dataclasses import asdict

from query_doctor.recent.workload_history import (
    SCHEMA_VERSION,
    WorkloadHistoryRecord,
    append_workload_history,
    baseline_from_history,
    load_workload_history,
    update_summary_with_workload_history,
)


FP_A = "wf_aaaaaaaaaaaaaaaaaaaaaaaa"
FP_B = "wf_bbbbbbbbbbbbbbbbbbbbbbbb"


def history_record(
    *,
    fingerprint: str = FP_A,
    p95: float | None = 20.0,
    p50: float | None = 10.0,
    count: int = 2,
) -> WorkloadHistoryRecord:
    return WorkloadHistoryRecord(
        schema_version=SCHEMA_VERSION,
        recorded_at_iso="2026-05-18T12:00:00+00:00",
        workload_fingerprint=fingerprint,
        count=count,
        duration_sec_p50=p50,
        duration_sec_p95=p95,
        duration_sec_total=100.0,
        pool_top="root.analytics",
        primary_bottleneck_top="stats",
        score_top="high",
    )


def test_workload_history_load_skips_malformed_lines(tmp_path):
    path = tmp_path / "workload_history.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(asdict(history_record(p95=20.0))),
                "{not-json",
                json.dumps({**asdict(history_record(p95=30.0)), "schema_version": 999}),
                json.dumps({**asdict(history_record(p95=40.0)), "workload_fingerprint": "bad"}),
                json.dumps(asdict(history_record(p95=50.0))),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    history = load_workload_history(path, limit_per_fingerprint=10)

    assert list(history) == [FP_A]
    assert [record.duration_sec_p95 for record in history[FP_A]] == [20.0, 50.0]


def test_workload_history_baseline_regression_labels():
    strong = baseline_from_history(
        current=history_record(p95=100.0),
        history=(history_record(p95=40.0), history_record(p95=45.0)),
    )
    mild = baseline_from_history(
        current=history_record(p95=75.0),
        history=(history_record(p95=50.0), history_record(p95=55.0)),
    )
    none = baseline_from_history(
        current=history_record(p95=60.0),
        history=(history_record(p95=50.0), history_record(p95=55.0)),
    )
    unknown = baseline_from_history(current=history_record(p95=60.0), history=())

    assert strong.regression == "strong"
    assert strong.baseline_duration_sec_p95 == 40.0
    assert strong.baseline_sample_count == 2
    assert mild.regression == "mild"
    assert none.regression == "none"
    assert unknown.regression == "unknown"
    assert unknown.baseline_sample_count == 0


def test_update_summary_with_workload_history_annotates_and_appends(tmp_path):
    history_path = tmp_path / "workload_history.jsonl"
    history_path.write_text(
        "\n".join(
            [
                json.dumps(asdict(history_record(p95=20.0))),
                "{malformed",
                json.dumps(asdict(history_record(p95=25.0))),
                json.dumps(asdict(history_record(fingerprint=FP_B, p95=200.0))),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    summary = {
        "cases": [
            {
                "case_index": 1,
                "query_id": "raw-query-id-1",
                "group_fingerprint": FP_A,
                "workload_fingerprint": FP_A,
                "duration_sec": 50.0,
                "pool": "root.analytics /tmp/raw",
                "score_severity": "high",
                "case_primary_bottleneck": {"label": "stats"},
            },
            {
                "case_index": 2,
                "query_id": "raw-query-id-2",
                "group_fingerprint": FP_A,
                "workload_fingerprint": FP_A,
                "duration_sec": 100.0,
                "pool": "root.analytics",
                "score_severity": "high",
                "case_primary_bottleneck": {"label": "stats"},
            },
            {
                "case_index": 3,
                "query_id": "incomplete-query-id",
                "group_fingerprint": FP_B,
                "workload_fingerprint": FP_B,
                "workload_fingerprint_incomplete": True,
                "duration_sec": 300.0,
            },
        ],
        "workload_groups": {
            "schema_version": 1,
            "groups": [
                {
                    "fingerprint": FP_A,
                    "member_count": 2,
                    "aggregates": {"duration_sec_p95": 100.0},
                }
            ],
        },
    }

    update_summary_with_workload_history(summary, path=history_path, max_bytes=10_000)

    history_status = summary["workload_history"]
    assert history_status["enabled"] is True
    assert history_status["loaded_record_count"] == 3
    assert history_status["appended_record_count"] == 1
    assert history_status["append_status"] == "ok"
    assert history_status["regression_counts"] == {"strong": 1}
    assert summary["cases"][0]["workload_regression"] == "strong"
    assert summary["cases"][0]["workload_baseline_sample_count"] == 2
    assert summary["cases"][0]["workload_baseline_duration_sec_p95"] == 20.0
    assert "workload_regression" not in summary["cases"][2]
    assert summary["workload_groups"]["groups"][0]["baseline"] == {
        "schema_version": 1,
        "regression": "strong",
        "sample_count": 2,
        "duration_sec_p95": 20.0,
    }

    history_text = history_path.read_text(encoding="utf-8")
    assert "raw-query-id" not in history_text
    assert "incomplete-query-id" not in history_text
    assert "/tmp/raw" not in history_text
    appended_records = [
        json.loads(line)
        for line in history_text.splitlines()
        if line.startswith("{") and "malformed" not in line
    ]
    assert appended_records[-1]["workload_fingerprint"] == FP_A
    assert appended_records[-1]["count"] == 2
    assert appended_records[-1]["duration_sec_p95"] == 100.0


def test_append_workload_history_rotates_oversized_file(tmp_path):
    path = tmp_path / "workload_history.jsonl"
    path.write_text("x" * 64, encoding="utf-8")

    status = append_workload_history([history_record()], path=path, max_bytes=8)

    assert status == "ok"
    assert len(list(tmp_path.glob("workload_history-*.jsonl"))) == 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["workload_fingerprint"] == FP_A
