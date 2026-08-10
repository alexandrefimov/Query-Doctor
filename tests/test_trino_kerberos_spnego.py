from __future__ import annotations

import subprocess

import pytest

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.trino import kerberos_spnego
from query_doctor.trino.kerberos_spnego import TrinoKerberosSpnegoFetcher


QUERY_ID = "20260603_120102_00001_abcde"


def test_trino_spnego_query_info_fetcher_builds_bounded_curl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, str] | None, int]] = []

    def fake_run(
        argv: list[str],
        *,
        stdout: int,
        stderr: int,
        timeout: int,
        check: bool,
        env: dict[str, str] | None,
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append((argv, env, timeout))
        assert stdout == subprocess.PIPE
        assert stderr == subprocess.DEVNULL
        assert check is False
        return subprocess.CompletedProcess(argv, 0, stdout=b'{"ok": true}\n200')

    monkeypatch.setattr(kerberos_spnego.subprocess, "run", fake_run)
    fetcher = TrinoKerberosSpnegoFetcher(
        kerberos_principal="sa@EXAMPLE.COM",
        service_name="HTTP",
        krb5_ccname="FILE:/tmp/krb5cc_qd_trino",
        insecure_tls=True,
    )

    text = fetcher.query_info(
        "https://coordinator.example.test",
        query_id=QUERY_ID,
        max_bytes=65536,
        timeout_seconds=30,
    )

    assert text == '{"ok": true}'
    argv, env, timeout = calls[0]
    assert "--negotiate" in argv
    assert "--service-name" in argv
    assert "HTTP" in argv
    assert "--max-filesize" in argv
    assert "65536" in argv
    assert "--insecure" in argv
    assert argv[-1].endswith(f"/v1/query/{QUERY_ID}?pruned=true")
    assert env is not None
    assert env["KRB5CCNAME"] == "FILE:/tmp/krb5cc_qd_trino"
    assert timeout == 35


def test_trino_spnego_query_list_rejects_http() -> None:
    fetcher = TrinoKerberosSpnegoFetcher(kerberos_principal="sa@EXAMPLE.COM")

    with pytest.raises(EngineFactContractError, match="requires HTTPS"):
        fetcher.query_list(
            "http://coordinator.example.test",
            max_bytes=65536,
            timeout_seconds=30,
        )


def test_trino_spnego_auth_failure_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(
        argv: list[str],
        *,
        stdout: int,
        stderr: int,
        timeout: int,
        check: bool,
        env: dict[str, str] | None,
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(argv, 0, stdout=b"raw body that must not echo\n403")

    monkeypatch.setattr(kerberos_spnego.subprocess, "run", fake_run)
    fetcher = TrinoKerberosSpnegoFetcher(kerberos_principal="sa@EXAMPLE.COM")

    with pytest.raises(EngineFactContractError) as exc_info:
        fetcher.query_list(
            "https://coordinator.example.test",
            max_bytes=65536,
            timeout_seconds=30,
        )

    message = str(exc_info.value)
    assert "authentication was rejected" in message
    assert "raw body" not in message


def test_trino_spnego_rejects_combined_auth_headers() -> None:
    fetcher = TrinoKerberosSpnegoFetcher(kerberos_principal="sa@EXAMPLE.COM")

    with pytest.raises(EngineFactContractError, match="auth mode is unsupported"):
        fetcher.query_info(
            "https://coordinator.example.test",
            query_id=QUERY_ID,
            max_bytes=65536,
            timeout_seconds=30,
            auth_headers={"Authorization": "Bearer secret"},
        )
