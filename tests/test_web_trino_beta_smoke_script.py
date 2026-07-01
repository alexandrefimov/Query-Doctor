from __future__ import annotations

import json
import os
import subprocess
import sys
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, quote, urlencode


REPO_DIR = Path(__file__).resolve().parents[1]
SCRIPT = REPO_DIR / "scripts" / "query-doctor-web-trino-beta-smoke"
QUERY_ID = "20260603_120102_00001_abcde"
COORDINATOR_URL = "https://trino-coordinator.example.test:8443"
PRINCIPAL = "sa@LESTA.HADOOP"


def run_smoke(args, *, home: Path, env: Optional[dict[str, str]] = None):
    merged_env = dict(os.environ)
    for name in (
        "QD_CONFIG",
        "KRB5CCNAME",
        "QD_CREDS_DIR",
        "QD_KEYTAB",
        "QD_KRB5_PRINCIPAL",
        "KRB5_PRINCIPAL",
        "CM_USERNAME",
        "CM_USER",
        "CM_PASSWORD",
        "CM_TOKEN",
    ):
        merged_env.pop(name, None)
    merged_env["HOME"] = str(home)
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_DIR,
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )


def write_config(home: Path, payload: dict) -> Path:
    config_dir = home / ".qdcreds"
    config_dir.mkdir(parents=True)
    config = config_dir / "query-doctor-config.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    return config


def trino_config_payload(
    tmp_path: Path,
    *,
    trino_support_mode: str | None = None,
    trino_beta_enabled: bool = True,
) -> dict:
    cluster: dict[str, object] = {
        "id": "trino-beta-prod",
        "label": "Trino PROD",
        "trino_coordinator_url": COORDINATOR_URL,
        "trino_query_info_source_contract": str(tmp_path / "query-info-contract.json"),
        "trino_query_list_source_contract": str(tmp_path / "query-list-contract.json"),
        "trino_kerberos_principal": PRINCIPAL,
        "trino_krb5_ccname": "FILE:/tmp/krb5cc_query_doctor_trino",
    }
    if trino_support_mode is not None:
        cluster["trino_support_mode"] = trino_support_mode
    if trino_beta_enabled:
        cluster["trino_beta_enabled"] = True
    return {"clusters": [cluster]}


def load_smoke_module():
    loader = SourceFileLoader("web_trino_beta_smoke_script", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_web_trino_beta_smoke_dry_run_without_private_echo(tmp_path):
    home = tmp_path / "home"
    config = write_config(home, trino_config_payload(tmp_path))

    result = run_smoke(["--dry-run", "--config", str(config)], home=home)

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert os.access(SCRIPT, os.X_OK)
    assert "dry_run=ok" in result.stdout
    assert "recent=true one_query=true" in result.stdout
    for marker in (
        COORDINATOR_URL,
        PRINCIPAL,
        "trino-beta-prod",
        "query-info-contract",
        "query-list-contract",
        "krb5cc",
        str(config),
        str(tmp_path),
    ):
        assert marker not in combined


def test_web_trino_beta_smoke_dry_run_accepts_production_support_mode(tmp_path):
    home = tmp_path / "home"
    config = write_config(
        home,
        trino_config_payload(
            tmp_path,
            trino_support_mode="production",
            trino_beta_enabled=False,
        ),
    )

    result = run_smoke(["--dry-run", "--config", str(config)], home=home)

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "dry_run=ok" in result.stdout
    assert "recent=true one_query=true" in result.stdout
    for marker in (
        COORDINATOR_URL,
        PRINCIPAL,
        "trino-beta-prod",
        "query-info-contract",
        "query-list-contract",
        "krb5cc",
        str(config),
        str(tmp_path),
    ):
        assert marker not in combined


def test_web_trino_beta_smoke_requires_cluster_without_listing_private_ids(tmp_path):
    home = tmp_path / "home"
    payload = {
        "clusters": [
            {
                "id": "first-secret-trino",
                "label": "First",
                "trino_beta_enabled": True,
                "trino_coordinator_url": COORDINATOR_URL,
                "trino_query_info_source_contract": "query-info-contract.json",
                "trino_query_list_source_contract": "query-list-contract.json",
            },
            {
                "id": "second-secret-trino",
                "label": "Second",
                "trino_beta_enabled": True,
                "trino_coordinator_url": "https://second.example.test",
                "trino_query_info_source_contract": "second-query-info-contract.json",
                "trino_query_list_source_contract": "second-query-list-contract.json",
            },
        ]
    }
    write_config(home, payload)

    result = run_smoke(["--dry-run"], home=home)

    combined = result.stdout + result.stderr
    assert result.returncode == 2
    assert "Multiple Trino Beta sources are configured" in result.stderr
    for marker in (
        "first-secret-trino",
        "second-secret-trino",
        COORDINATOR_URL,
        "second.example.test",
        "query-info-contract",
    ):
        assert marker not in combined


def trino_result_html(title: str, *, recent_extra: str = "") -> str:
    boundary = (
        "Running scans, query-history crawling, metadata collection, LLM reports, "
        "Query Optimizer jobs, generated SQL, and SQL execution remain unavailable. "
        "Python Report and optimizer guidance are available only from materialized Details."
    )
    if title in {"Trino Beta Recent diagnosis", "Trino Recent diagnosis"}:
        return (
            f"<section><h1>{title}</h1><p>{boundary}</p><table><tr><td><code>{QUERY_ID}</code>"
            f"</td><td>ok</td></tr></table>{recent_extra}</section>"
        )
    return (
        f"<section><h1>{title}</h1><p>{boundary}</p>"
        f"<div class='query-line'><span>Query:</span><code>{QUERY_ID}</code></div></section>"
    )


class FakeProcess:
    def poll(self):
        return None


def install_fake_web(
    monkeypatch,
    smoke,
    *,
    recent_extra: str = "",
    production_headings: bool = False,
) -> dict[str, dict[str, str]]:
    captures: dict[str, dict[str, str]] = {}
    recent_job_id = "1234567890abcdef1234567890abcdef"
    query_job_id = "abcdef1234567890abcdef1234567890"

    def fake_request(
        host: str,
        port: int,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout_sec: float = 5.0,
    ):
        if method == "GET" and path == "/":
            return smoke.HttpResponse(200, {}, "ok")
        if method == "POST" and path == "/batch/run":
            assert body is not None
            captures["recent"] = {
                key: values[0]
                for key, values in parse_qs(body.decode(), keep_blank_values=True).items()
            }
            return smoke.HttpResponse(303, {"location": f"/jobs/{recent_job_id}"}, "")
        if method == "POST" and path == "/analyze":
            assert body is not None
            captures["query"] = {
                key: values[0]
                for key, values in parse_qs(body.decode(), keep_blank_values=True).items()
            }
            return smoke.HttpResponse(303, {"location": f"/jobs/{query_job_id}"}, "")
        if method == "GET" and path == f"/jobs/{recent_job_id}/status":
            recent_title = (
                "Trino Recent diagnosis" if production_headings else "Trino Beta Recent diagnosis"
            )
            payload = {
                "status": "ok",
                "stage": "Done",
                "progress": 100,
                "kind": "trino_recent",
                "result_html": trino_result_html(recent_title, recent_extra=recent_extra),
            }
            return smoke.HttpResponse(
                200, {"content-type": "application/json"}, json.dumps(payload)
            )
        if method == "GET" and path == f"/jobs/{query_job_id}/status":
            query_title = (
                "Trino Query ID diagnosis"
                if production_headings
                else "Trino Beta Query ID diagnosis"
            )
            payload = {
                "status": "ok",
                "stage": "Done",
                "progress": 100,
                "kind": "trino_query",
                "result_html": trino_result_html(query_title),
            }
            return smoke.HttpResponse(
                200, {"content-type": "application/json"}, json.dumps(payload)
            )
        return smoke.HttpResponse(404, {}, "")

    monkeypatch.setattr(smoke, "start_web", lambda *_args, **_kwargs: FakeProcess())
    monkeypatch.setattr(smoke, "stop_web", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(smoke, "wait_for_web_ready", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(smoke, "request", fake_request)
    return captures


def test_web_trino_beta_smoke_runs_recent_and_query_id_without_echo(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    config = write_config(home, trino_config_payload(tmp_path))
    smoke = load_smoke_module()
    captures = install_fake_web(monkeypatch, smoke)

    rc = smoke.main(
        [
            "--config",
            str(config),
            "--port",
            "12345",
            "--timeout-sec",
            "10",
            "--poll-interval-sec",
            "0.05",
        ]
    )
    captured = capsys.readouterr()

    combined = captured.out + captured.err
    assert rc == 0, combined
    assert "[web-trino-beta-smoke] web=ready" in captured.out
    assert "[web-trino-beta-smoke] recent=ok query_id_selected=hidden" in captured.out
    assert "[web-trino-beta-smoke] query_id=ok" in captured.out
    assert "[web-trino-beta-smoke] ok" in captured.out
    for marker in (
        QUERY_ID,
        quote(QUERY_ID, safe=""),
        COORDINATOR_URL,
        PRINCIPAL,
        "trino-beta-prod",
        "query-info-contract",
        "query-list-contract",
        "krb5cc",
        str(config),
        str(tmp_path),
    ):
        assert marker not in combined

    recent_form = captures["recent"]
    query_form = captures["query"]
    assert recent_form["engine"] == "trino"
    assert recent_form["scan_target"] == "finished"
    assert recent_form["cluster_key"] == "trino-beta-prod"
    assert recent_form["metadata_top_limit"] == "0"
    assert "query_type" not in recent_form
    assert query_form["engine"] == "trino"
    assert query_form["query_id"] == QUERY_ID
    assert query_form["cluster_key"] == "trino-beta-prod"


def test_web_trino_beta_smoke_accepts_production_result_headings(
    tmp_path,
    monkeypatch,
    capsys,
):
    home = tmp_path / "home"
    config = write_config(
        home,
        trino_config_payload(
            tmp_path,
            trino_support_mode="production",
            trino_beta_enabled=False,
        ),
    )
    smoke = load_smoke_module()
    captures = install_fake_web(monkeypatch, smoke, production_headings=True)

    rc = smoke.main(
        [
            "--config",
            str(config),
            "--port",
            "12345",
            "--timeout-sec",
            "10",
            "--poll-interval-sec",
            "0.05",
        ]
    )
    captured = capsys.readouterr()

    combined = captured.out + captured.err
    assert rc == 0, combined
    assert "[web-trino-beta-smoke] ok" in captured.out
    assert captures["recent"]["engine"] == "trino"
    assert captures["query"]["engine"] == "trino"
    for marker in (QUERY_ID, COORDINATOR_URL, PRINCIPAL, str(config), str(tmp_path)):
        assert marker not in combined


def test_web_trino_beta_smoke_rejects_unsupported_result_link(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    config = write_config(home, trino_config_payload(tmp_path))
    smoke = load_smoke_module()
    install_fake_web(
        monkeypatch,
        smoke,
        recent_extra='<a href="/query/details/secret">Details</a>',
    )

    rc = smoke.main(
        [
            "--config",
            str(config),
            "--port",
            "12345",
            "--timeout-sec",
            "10",
            "--poll-interval-sec",
            "0.05",
            "--skip-query-id-check",
        ]
    )
    captured = capsys.readouterr()

    combined = captured.out + captured.err
    assert rc == 2
    assert "unsupported product action link" in captured.err
    assert QUERY_ID not in combined
    assert str(tmp_path) not in combined


def test_web_trino_beta_smoke_port_failure_is_safe(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    config = write_config(home, trino_config_payload(tmp_path))
    smoke = load_smoke_module()

    def fail_port(host: str) -> int:
        raise smoke.SmokeError("Could not allocate a local web port.")

    monkeypatch.setattr(smoke, "free_local_port", fail_port)

    rc = smoke.main(["--config", str(config)])
    captured = capsys.readouterr()

    combined = captured.out + captured.err
    assert rc == 2
    assert "Could not allocate a local web port." in captured.err
    assert "Traceback" not in combined
    assert str(tmp_path) not in combined


def test_web_trino_beta_smoke_startup_failure_is_safe(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    config = write_config(home, trino_config_payload(tmp_path))
    smoke = load_smoke_module()

    def fail_popen(*args, **kwargs):
        raise OSError(f"secret startup path {tmp_path}")

    monkeypatch.setattr(smoke.subprocess, "Popen", fail_popen)

    rc = smoke.main(["--config", str(config), "--port", "12345"])
    captured = capsys.readouterr()

    combined = captured.out + captured.err
    assert rc == 2
    assert "Local web server could not be started." in captured.err
    assert "Traceback" not in combined
    assert str(tmp_path) not in combined
