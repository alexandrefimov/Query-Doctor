from __future__ import annotations

from query_doctor.safety import redaction


def test_redact_host_identifiers_redacts_ipv6_without_touching_timestamps_or_embedded_text():
    text = (
        "RPC peer 2001:db8::2\n"
        "Start Time: 2026-04-30 11:21:41.656793000\n"
        "Trace token x2001:db8::3y\n"
    )

    redacted = redaction.redact_host_identifiers(text)

    assert "RPC peer host_01" in redacted
    assert "2001:db8::2" not in redacted
    assert "11:21:41.656793000" in redacted
    assert "x2001:db8::3y" in redacted


def test_redact_ipv6_candidates_checks_long_colon_run_once(monkeypatch):
    adversarial_candidate = ":" + "0:" * 5000
    text = f"host header {adversarial_candidate} end"
    calls: list[str] = []

    def fake_ip_address(value: str) -> object:
        calls.append(value)
        raise ValueError

    monkeypatch.setattr(redaction.ipaddress, "ip_address", fake_ip_address)

    assert redaction.redact_ipv6_candidates(text, redaction.HostAliasRedactor()) == text
    assert calls == [adversarial_candidate]
