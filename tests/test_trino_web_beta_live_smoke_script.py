from __future__ import annotations

import json
from pathlib import Path

import pytest

from query_doctor.web.models import (
    BatchRunConfig,
    WebClusterConfig,
    WebError,
    WebSettings,
    WebTrinoRecentScanResult,
    WebTrinoRecentScanRow,
)
from scripts import audit_trino_web_beta_live_smoke as live_smoke


COORDINATOR_URL = "https://coordinator.example.test:8443"
QUERY_ID = "20260603_120102_00001_abcde"


def test_trino_web_beta_live_smoke_prints_safe_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "web.json"
    config_path.write_text("{}", encoding="utf-8")
    settings = WebSettings(
        config=config_path,
        trino_beta_enabled=True,
        trino_coordinator_url=COORDINATOR_URL,
        trino_query_info_source_contract=tmp_path / "query-info.json",
        trino_query_list_source_contract=tmp_path / "query-list.json",
        trino_kerberos_principal="sa@LESTA.HADOOP",
        trino_krb5_ccname="FILE:/tmp/krb5cc_qd_trino",
    )

    def fake_build_web_settings(args: object, *, cwd: Path) -> WebSettings:
        assert str(config_path) in getattr(args, "config")
        return settings

    def fake_run_trino_recent_scan(
        config: BatchRunConfig,
        settings_arg: WebSettings,
    ) -> WebTrinoRecentScanResult:
        assert settings_arg is settings
        assert config.engine == "trino"
        assert config.metadata_top_limit == 0
        assert config.triage_profile_limit == 1
        return WebTrinoRecentScanResult(
            rows=(
                WebTrinoRecentScanRow(
                    query_id=QUERY_ID,
                    status="ok",
                    lifecycle="finished",
                    parser_coverage="supported",
                    supported_attention_area_count=1,
                ),
            ),
            records_seen=100,
            records_selected=1,
            records_diagnosed=1,
            query_bound=100,
        )

    monkeypatch.setattr(live_smoke, "build_web_settings", fake_build_web_settings)
    monkeypatch.setattr(live_smoke, "run_trino_recent_scan", fake_run_trino_recent_scan)

    rc = live_smoke.main(["--config", str(config_path), "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert rc == 0
    assert payload["summary_kind"] == "trino_web_beta_live_smoke_v1"
    assert payload["status"] == "ok"
    assert payload["support_claim"] == "beta_only"
    assert payload["counts"]["records_seen"] == 100
    assert payload["counts"]["records_selected"] == 1
    assert payload["counts"]["records_diagnosed"] == 1
    assert payload["counts"]["row_status_counts"] == {"ok": 1}
    assert payload["surface_boundary"]["network_read_attempted"] is True
    assert payload["surface_boundary"]["sql_execution_performed"] is False
    assert payload["surface_boundary"]["query_id_output"] is False
    for text in (captured.out, captured.err):
        assert QUERY_ID not in text
        assert COORDINATOR_URL not in text
        assert str(tmp_path) not in text
        assert "LESTA" not in text
        assert "krb5cc" not in text


def test_trino_web_beta_live_smoke_failure_keeps_error_category_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "web.json"
    config_path.write_text("{}", encoding="utf-8")

    def fake_build_web_settings(args: object, *, cwd: Path) -> WebSettings:
        return WebSettings(
            config=config_path,
            trino_beta_enabled=True,
            trino_coordinator_url=COORDINATOR_URL,
            trino_query_info_source_contract=tmp_path / "query-info.json",
            trino_query_list_source_contract=tmp_path / "query-list.json",
        )

    def fake_run_trino_recent_scan(
        config: BatchRunConfig,
        settings_arg: WebSettings,
    ) -> WebTrinoRecentScanResult:
        raise WebError(f"{QUERY_ID} {COORDINATOR_URL} {tmp_path} SecretValue")

    monkeypatch.setattr(live_smoke, "build_web_settings", fake_build_web_settings)
    monkeypatch.setattr(live_smoke, "run_trino_recent_scan", fake_run_trino_recent_scan)

    rc = live_smoke.main(["--config", str(config_path), "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert rc == 1
    assert payload["status"] == "failed"
    assert payload["issue_counts"] == {"trino_web_beta_live_smoke_failed": 1}
    assert payload["safe_error_summary"] == "type=WebError reason=trino_beta.live_smoke_failed"
    for text in (captured.out, captured.err):
        assert QUERY_ID not in text
        assert COORDINATOR_URL not in text
        assert str(tmp_path) not in text
        assert "SecretValue" not in text


def test_trino_web_beta_live_smoke_marks_discovered_default_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "web.json"
    config_path.write_text("{}", encoding="utf-8")

    def fake_build_web_settings(args: object, *, cwd: Path) -> WebSettings:
        assert getattr(args, "config") is None
        return WebSettings(
            config=config_path,
            trino_beta_enabled=True,
            trino_coordinator_url=COORDINATOR_URL,
            trino_query_info_source_contract=tmp_path / "query-info.json",
            trino_query_list_source_contract=tmp_path / "query-list.json",
        )

    def fake_run_trino_recent_scan(
        config: BatchRunConfig,
        settings_arg: WebSettings,
    ) -> WebTrinoRecentScanResult:
        return WebTrinoRecentScanResult(
            rows=(
                WebTrinoRecentScanRow(
                    query_id=QUERY_ID,
                    status="ok",
                    lifecycle="finished",
                    parser_coverage="supported",
                ),
            ),
            records_seen=1,
            records_selected=1,
            records_diagnosed=1,
            query_bound=1,
        )

    monkeypatch.setattr(live_smoke, "build_web_settings", fake_build_web_settings)
    monkeypatch.setattr(live_smoke, "run_trino_recent_scan", fake_run_trino_recent_scan)

    rc = live_smoke.main(["--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert rc == 0
    assert payload["counts"]["config_discovered"] is True
    for text in (captured.out, captured.err):
        assert str(tmp_path) not in text
        assert QUERY_ID not in text
        assert COORDINATOR_URL not in text


def test_trino_web_beta_live_smoke_auto_selects_only_recent_ready_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "web.json"
    config_path.write_text("{}", encoding="utf-8")
    settings = WebSettings(
        config=config_path,
        clusters=(
            WebClusterConfig(key="impala", label="Impala"),
            WebClusterConfig(
                key="beta_source",
                label="Trino",
                trino_beta_enabled=True,
                trino_coordinator_url=COORDINATOR_URL,
                trino_query_info_source_contract=tmp_path / "query-info.json",
                trino_query_list_source_contract=tmp_path / "query-list.json",
            ),
        ),
    )

    def fake_build_web_settings(args: object, *, cwd: Path) -> WebSettings:
        return settings

    def fake_run_trino_recent_scan(
        config: BatchRunConfig,
        settings_arg: WebSettings,
    ) -> WebTrinoRecentScanResult:
        assert settings_arg.active_cluster_key == "beta_source"
        assert settings_arg.trino_coordinator_url == COORDINATOR_URL
        return WebTrinoRecentScanResult(
            rows=(
                WebTrinoRecentScanRow(
                    query_id=QUERY_ID,
                    status="ok",
                    lifecycle="finished",
                    parser_coverage="supported",
                ),
            ),
            records_seen=1,
            records_selected=1,
            records_diagnosed=1,
            query_bound=1,
        )

    monkeypatch.setattr(live_smoke, "build_web_settings", fake_build_web_settings)
    monkeypatch.setattr(live_smoke, "run_trino_recent_scan", fake_run_trino_recent_scan)

    rc = live_smoke.main(["--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert rc == 0
    assert payload["status"] == "ok"
    for text in (captured.out, captured.err):
        assert "beta_source" not in text
        assert COORDINATOR_URL not in text
        assert str(tmp_path) not in text


def test_trino_web_beta_live_smoke_rejects_ambiguous_recent_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "web.json"
    config_path.write_text("{}", encoding="utf-8")
    settings = WebSettings(
        config=config_path,
        clusters=(
            WebClusterConfig(
                key="first_source",
                label="First",
                trino_beta_enabled=True,
                trino_coordinator_url=COORDINATOR_URL,
                trino_query_info_source_contract=tmp_path / "first-query-info.json",
                trino_query_list_source_contract=tmp_path / "first-query-list.json",
            ),
            WebClusterConfig(
                key="second_source",
                label="Second",
                trino_beta_enabled=True,
                trino_coordinator_url="https://second.example.test",
                trino_query_info_source_contract=tmp_path / "second-query-info.json",
                trino_query_list_source_contract=tmp_path / "second-query-list.json",
            ),
        ),
    )

    def fake_build_web_settings(args: object, *, cwd: Path) -> WebSettings:
        return settings

    monkeypatch.setattr(live_smoke, "build_web_settings", fake_build_web_settings)

    rc = live_smoke.main(["--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert rc == 1
    assert payload["safe_error_summary"] == (
        "type=WebError reason=trino_beta.multiple_recent_sources "
        "stage=Selecting Trino Beta local source"
    )
    for text in (captured.out, captured.err):
        assert "first_source" not in text
        assert "second_source" not in text
        assert COORDINATOR_URL not in text
        assert "second.example" not in text
        assert str(tmp_path) not in text


def test_trino_web_beta_live_smoke_rejects_summary_over_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "web.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        live_smoke,
        "run_live_smoke",
        lambda *_args, **_kwargs: live_smoke.TrinoWebBetaLiveSmokeResult(
            config_discovered=True,
            recent_window_minutes=1,
            selected_query_limit=1,
        ),
    )

    rc = live_smoke.main(
        [
            "--config",
            str(config_path),
            "--summary-json",
            str(config_path),
        ]
    )
    captured = capsys.readouterr()

    assert rc == 2
    assert "summary output must not overwrite the input config" in captured.err
    assert str(tmp_path) not in captured.err
