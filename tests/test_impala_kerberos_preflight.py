import subprocess

from query_doctor.impala.kerberos_preflight import check_kerberos_ticket_cache


def completed(returncode: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(args=["klist", "-s"], returncode=returncode)


def test_kerberos_ticket_preflight_requires_cache_env_without_echoing_paths():
    result = check_kerberos_ticket_cache({})

    assert result.ok is False
    assert result.reason == "KRB5CCNAME is required before metadata collection can use Kerberos."


def test_kerberos_ticket_preflight_accepts_valid_ticket():
    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return completed(0)

    result = check_kerberos_ticket_cache(
        {"KRB5CCNAME": "FILE:/tmp/private-cache"},
        runner=fake_runner,
    )

    assert result.ok is True
    assert calls[0][0] == ["klist", "-s"]
    assert calls[0][1]["env"]["KRB5CCNAME"] == "FILE:/tmp/private-cache"


def test_kerberos_ticket_preflight_reports_expired_cache_safely():
    result = check_kerberos_ticket_cache(
        {"KRB5CCNAME": "FILE:/tmp/private-cache"},
        runner=lambda cmd, **kwargs: completed(1),
    )

    assert result.ok is False
    assert result.reason == (
        "Kerberos ticket cache is missing or expired; refresh it before metadata collection."
    )
    assert "private-cache" not in result.reason
