import json
from datetime import datetime, timezone

from query_doctor.cli import recent_history_retention as cli
from query_doctor.recent.history_store import RecentSummaryHistoryRecord
from query_doctor.recent.sqlite_history_store import SqliteRecentHistoryStore


SECRET_DSN = "postgresql://query_doctor:secret@private-host.example.net/query_doctor"


def summary_record(query_id: str, recorded_at_iso: str) -> RecentSummaryHistoryRecord:
    return RecentSummaryHistoryRecord(
        schema_version=1,
        engine="impala",
        source_kind="cm",
        source_key="cm:cluster:impala",
        query_id=query_id,
        recorded_at_iso=recorded_at_iso,
        start_time=None,
        end_time=None,
        duration_ms=None,
        status="finished",
        query_state="FINISHED",
        user=None,
        pool=None,
        query_type=None,
        sql_verb=None,
        statement_present=False,
        admission_result=None,
        admission_wait_ms=None,
        rows_produced=None,
        bytes_read=None,
        bytes_sent=None,
        memory_aggregate_peak=None,
        memory_per_node_peak=None,
        suspicion_score=0,
        suspicion_level="low",
        suspicion_reasons=(),
        selected=False,
        selected_reason=None,
    )


def test_recent_history_retention_cli_prunes_sqlite_without_raw_echo(tmp_path, capsys):
    db = tmp_path / "recent.sqlite"
    store = SqliteRecentHistoryStore(db)
    store.upsert_summaries(
        [
            summary_record("old-query", "2026-07-01T00:00:00+00:00"),
            summary_record("recent-query", "2026-07-03T00:00:00+00:00"),
        ]
    )
    original_policy_from_args = cli.retention_policy_from_args

    def fixed_policy(args, *, now=None):
        return original_policy_from_args(
            args,
            now=datetime(2026, 7, 3, tzinfo=timezone.utc),
        )

    cli.retention_policy_from_args = fixed_policy
    try:
        status = cli.main(
            [
                "--backend",
                "sqlite",
                "--sqlite-db",
                str(db),
                "--summary-retention-days",
                "1",
                "--json",
            ],
            env={},
        )
    finally:
        cli.retention_policy_from_args = original_policy_from_args

    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)
    assert status == 0
    assert payload["summary_kind"] == cli.SUMMARY_KIND
    assert payload["status"] == "pruned"
    assert payload["retention"]["summaries_deleted"] == 1
    assert payload["retention"]["total_deleted"] == 1
    assert payload["raw_output"] is False
    assert str(db) not in serialized
    assert "old-query" not in serialized
    assert "recent-query" not in serialized
    assert store.count_summaries() == 1


def test_recent_history_retention_cli_blocks_missing_postgres_dsn_without_echo(capsys):
    status = cli.main(
        [
            "--backend",
            "postgres",
            "--postgres-dsn-env",
            "QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN",
            "--summary-retention-days",
            "30",
            "--json",
            "--fail-on-warning",
        ],
        env={"QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN": ""},
    )

    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)
    assert status == 1
    assert payload["status"] == "blocked"
    assert payload["issue_codes"] == ["postgres_dsn_env_missing"]
    assert "QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN" not in serialized
    assert "secret" not in serialized
    assert "private-host" not in serialized
