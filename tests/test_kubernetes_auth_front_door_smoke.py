from __future__ import annotations

import json
from pathlib import Path
from urllib import parse

from scripts import kubernetes_auth_front_door_smoke as smoke


def response(status: int, **headers: str) -> smoke.HttpResponse:
    normalized = {key.lower(): (value,) for key, value in headers.items()}
    return smoke.HttpResponse(status=status, headers=normalized)


def oidc_authorize_url(
    *,
    client_id: str = "private-client-id",
    redirect_uri: str = "https://private-query-doctor.example.invalid/oauth2/callback",
    issuer: str = "https://private-keycloak.example.invalid/realms/private",
) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid profile email",
        "state": "private-state-value",
        "code_challenge": "private-code-challenge",
        "code_challenge_method": "S256",
    }
    return f"{issuer}/protocol/openid-connect/auth?{parse.urlencode(params)}"


def test_kubernetes_auth_front_door_smoke_payload_is_raw_free() -> None:
    config = smoke.SmokeConfig(
        base_url="https://private-query-doctor.example.invalid/",
        expected_issuer_url="https://private-keycloak.example.invalid/realms/private",
        expected_client_id="private-client-id",
    )
    calls: list[str] = []

    def fake_fetch(url: str, _timeout_sec: float) -> smoke.HttpResponse:
        calls.append(url)
        if len(calls) == 1:
            return response(
                302,
                location="/oauth2/start?rd=%2F",
                **{"set-cookie": "_oauth2_proxy_csrf=opaque; Secure; HttpOnly"},
            )
        return response(302, location=oidc_authorize_url())

    checks = smoke.run_checks(config, fetch=fake_fetch)
    payload = smoke.smoke_payload(config, checks)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["kind"] == "kubernetes_auth_front_door_smoke_v1"
    assert payload["all_passed"] is True
    assert payload["raw_values_output"] == "no"
    assert len(calls) == 2
    for forbidden in (
        "private-query-doctor",
        "private-keycloak",
        "private-client-id",
        "private-state-value",
        "private-code-challenge",
        "state=",
    ):
        assert forbidden not in serialized


def test_kubernetes_auth_front_door_smoke_rejects_direct_success() -> None:
    config = smoke.SmokeConfig(base_url="https://query-doctor.example.invalid/")

    checks = smoke.run_checks(config, fetch=lambda _url, _timeout_sec: response(200))
    payload = smoke.smoke_payload(config, checks)

    assert payload["all_passed"] is False
    assert "front_door_requires_auth_failed" in payload["issue_codes"]
    assert "oidc_authorize_redirect_failed" in payload["issue_codes"]


def test_kubernetes_auth_front_door_smoke_rejects_bad_callback_origin() -> None:
    config = smoke.SmokeConfig(base_url="https://query-doctor.example.invalid/")

    checks = smoke.run_checks(
        config,
        fetch=lambda _url, _timeout_sec: response(
            302,
            location=oidc_authorize_url(
                redirect_uri="https://other-query-doctor.example.invalid/oauth2/callback"
            ),
        ),
    )
    payload = smoke.smoke_payload(config, checks)

    assert payload["all_passed"] is False
    assert "callback_redirect_uri_failed" in payload["issue_codes"]


def test_kubernetes_auth_front_door_smoke_cli_keeps_targets_out_of_output(
    monkeypatch,
    capsys,
) -> None:
    def fake_run_checks(_config: smoke.SmokeConfig) -> tuple[smoke.SmokeCheck, ...]:
        return (
            smoke.SmokeCheck(
                "front_door_requires_auth",
                True,
                {"status_class": "3xx", "redirect_count": 1},
            ),
        )

    monkeypatch.setattr(smoke, "run_checks", fake_run_checks)

    status = smoke.main(
        [
            "--base-url",
            "https://private-query-doctor.example.invalid/",
            "--expected-issuer-url",
            "https://private-keycloak.example.invalid/realms/private",
            "--expected-client-id",
            "private-client-id",
            "--compact",
        ]
    )
    captured = capsys.readouterr()

    assert status == 0
    assert "private-query-doctor" not in captured.out
    assert "private-keycloak" not in captured.out
    assert "private-client-id" not in captured.out
    assert captured.err == ""


def test_kubernetes_auth_front_door_smoke_docs_mention_script() -> None:
    root = Path(__file__).resolve().parents[1]
    auth_doc = (root / "docs" / "kubernetes-auth-front-door.md").read_text(encoding="utf-8")
    test_matrix = (root / "docs" / "test-matrix.md").read_text(encoding="utf-8")
    deploy_doc = (root / "deploy" / "kubernetes" / "README.md").read_text(encoding="utf-8")

    assert "scripts/kubernetes_auth_front_door_smoke.py --compact" in auth_doc
    assert "kubernetes-auth-front-door.md#live-external-smoke" in test_matrix
    assert "tests/test_kubernetes_auth_front_door_smoke.py" in test_matrix
    assert "scripts/kubernetes_auth_front_door_smoke.py" in deploy_doc
