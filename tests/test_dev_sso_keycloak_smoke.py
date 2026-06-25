import json
import socket

from scripts import dev_sso_keycloak_smoke as smoke


def test_dev_sso_keycloak_smoke_payload_is_raw_free():
    config = smoke.SmokeConfig(
        proxy_url="http://private-idp.example.invalid/app",
        keycloak_discovery_url="http://private-idp.example.invalid/realms/private",
        upstream_host="private-upstream.example.invalid",
        username="real_user_should_not_print",
        password="real_secret_should_not_print",
    )
    checks = (
        smoke.SmokeCheck(
            "proxy_requires_login",
            True,
            {"status_class": "3xx", "redirect_target": "keycloak_oidc_auth"},
        ),
        smoke.SmokeCheck(
            "keycloak_discovery_ok",
            True,
            {"status_class": "2xx"},
        ),
        smoke.SmokeCheck(
            "query_doctor_upstream_private",
            True,
            {"connection": "blocked", "blocked_category": "connection_refused"},
        ),
        smoke.SmokeCheck(
            "synthetic_oidc_login_lands_on_query_doctor",
            True,
            {
                "status_class": "2xx",
                "final_target": "query_doctor_proxy_root",
                "login_form_seen": True,
                "still_on_keycloak_login": False,
                "query_doctor_visible": True,
            },
        ),
    )

    payload = smoke.smoke_payload(config, checks)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["kind"] == "dev_sso_keycloak_smoke_v1"
    assert payload["all_passed"] is True
    assert payload["check_count"] == 4
    assert payload["raw_values_output"] == "no"
    for forbidden in (
        "private-idp",
        "private-upstream",
        "real_user_should_not_print",
        "real_secret_should_not_print",
        "Cookie",
        "Authorization",
        "code=",
        "state=",
    ):
        assert forbidden not in serialized


def test_dev_sso_keycloak_smoke_cli_returns_failure_for_failed_check(monkeypatch, capsys):
    def fake_run_checks(_config):
        return (
            smoke.SmokeCheck(
                "proxy_requires_login",
                False,
                {"error_category": "connection_refused"},
            ),
        )

    monkeypatch.setattr(smoke, "run_checks", fake_run_checks)

    status = smoke.main(["--compact"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert status == 1
    assert payload["all_passed"] is False
    assert payload["checks"][0]["error_category"] == "connection_refused"
    assert captured.err == ""


def test_dev_sso_keycloak_smoke_cli_keeps_default_login_secret_out_of_output(
    monkeypatch,
    capsys,
):
    def fake_run_checks(_config):
        return (
            smoke.SmokeCheck(
                "synthetic_oidc_login_lands_on_query_doctor",
                True,
                {"status_class": "2xx", "final_target": "query_doctor_proxy_root"},
            ),
        )

    monkeypatch.setattr(smoke, "run_checks", fake_run_checks)

    status = smoke.main(["--compact"])

    captured = capsys.readouterr()
    assert status == 0
    assert "analyst_one" not in captured.out
    assert "analyst-one-dev-login" not in captured.out
    assert "query-doctor-sso.localhost" not in captured.out


def test_dev_sso_keycloak_smoke_finds_keycloak_login_form():
    form = smoke.login_form_from_html(
        """
        <html>
          <body>
            <form action="/realms/query-doctor-dev/login-actions/authenticate">
              <input name="session_code" value="opaque" />
              <input name="username" />
              <input name="password" />
            </form>
          </body>
        </html>
        """
    )

    assert form["action"] == "/realms/query-doctor-dev/login-actions/authenticate"
    assert form["inputs"] == {
        "session_code": "opaque",
        "username": "",
        "password": "",
    }


def test_dev_sso_keycloak_smoke_error_categories_are_safe_and_python39_compatible():
    assert smoke.error_category(ConnectionRefusedError()) == "connection_refused"
    assert smoke.error_category(socket.timeout()) == "timeout"
    assert smoke.error_category(OSError()) == "network_error"


def test_dev_sso_keycloak_smoke_docs_mention_script():
    dev_doc = (smoke.ROOT / "docs" / "dev-sso-keycloak.md").read_text(encoding="utf-8")
    deployment_doc = (smoke.ROOT / "docs" / "owner-raw-d3-deployment.md").read_text(
        encoding="utf-8"
    )
    test_matrix = (smoke.ROOT / "docs" / "test-matrix.md").read_text(encoding="utf-8")
    readme = (smoke.ROOT / "README.md").read_text(encoding="utf-8")

    assert "scripts/dev_sso_keycloak_smoke.py --compact" in dev_doc
    assert "scripts/dev_sso_keycloak_smoke.py" in deployment_doc
    assert "scripts/dev_sso_keycloak_smoke.py --compact" in test_matrix
    assert "scripts/dev_sso_keycloak_smoke.py" in readme
