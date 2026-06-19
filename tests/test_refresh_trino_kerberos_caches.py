from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import refresh_trino_kerberos_caches as refresher


def test_trino_kerberos_entries_inherit_defaults_and_resolve_config_path(tmp_path: Path) -> None:
    config = tmp_path / "query-doctor-config.json"
    config.write_text(
        json.dumps(
            {
                "trino_beta_enabled": True,
                "trino_kerberos_principal": "default@EXAMPLE.COM",
                "trino_krb5_ccname": "FILE:/tmp/default-cache",
                "trino_krb5_config": "krb5.conf",
                "clusters": [
                    {"id": "impala", "cluster_type": "cm"},
                    {
                        "id": "trino",
                        "trino_kerberos_principal": "trino@EXAMPLE.COM",
                        "trino_krb5_ccname": "FILE:/tmp/trino-cache",
                    },
                    {
                        "id": "disabled",
                        "trino_beta_enabled": False,
                        "trino_kerberos_principal": "disabled@EXAMPLE.COM",
                        "trino_krb5_ccname": "FILE:/tmp/disabled-cache",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    entries = refresher.trino_kerberos_entries_from_config(config)

    assert entries == (
        refresher.TrinoKerberosEntry(
            principal="default@EXAMPLE.COM",
            krb5_ccname="FILE:/tmp/default-cache",
            krb5_config=tmp_path / "krb5.conf",
        ),
        refresher.TrinoKerberosEntry(
            principal="trino@EXAMPLE.COM",
            krb5_ccname="FILE:/tmp/trino-cache",
            krb5_config=tmp_path / "krb5.conf",
        ),
    )


def test_refresh_trino_kerberos_entries_uses_kinit_without_shell(tmp_path: Path) -> None:
    keytab = tmp_path / "query-doctor.keytab"
    keytab.write_text("not a real keytab", encoding="utf-8")
    calls: list[tuple[list[str], dict[str, str]]] = []

    def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, dict(kwargs.get("env") or {})))
        return subprocess.CompletedProcess(argv, 0, "", "")

    refreshed = refresher.refresh_trino_kerberos_entries(
        (
            refresher.TrinoKerberosEntry(
                principal="trino@EXAMPLE.COM",
                krb5_ccname="FILE:/tmp/trino-cache",
                krb5_config=tmp_path / "krb5.conf",
            ),
        ),
        keytab=keytab,
        runner=runner,
    )

    assert refreshed == 1
    assert calls[0][0] == [
        "kinit",
        "-c",
        "FILE:/tmp/trino-cache",
        "-kt",
        str(keytab),
        "trino@EXAMPLE.COM",
    ]
    assert calls[0][1]["KRB5_CONFIG"] == str(tmp_path / "krb5.conf")


def test_refresh_trino_kerberos_main_keeps_failure_message_safe(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config = tmp_path / "query-doctor-config.json"
    keytab = tmp_path / "query-doctor.keytab"
    keytab.write_text("not a real keytab", encoding="utf-8")
    config.write_text(
        json.dumps(
            {
                "trino_beta_enabled": True,
                "trino_kerberos_principal": "secret-principal@EXAMPLE.COM",
                "trino_krb5_ccname": "FILE:/tmp/secret-cache",
            }
        ),
        encoding="utf-8",
    )

    def runner(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 1, "", "sensitive stderr")

    monkeypatch.setattr(refresher.subprocess, "run", runner)

    assert refresher.main(["--config", str(config), "--keytab", str(keytab)]) == 2

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Could not refresh Trino Kerberos ticket cache" in combined
    assert "secret-principal" not in combined
    assert "secret-cache" not in combined
    assert "sensitive stderr" not in combined
    assert str(keytab) not in combined
