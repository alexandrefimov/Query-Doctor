import json

from scripts import owner_raw_policy_simulator as simulator


def run_simulator(argv):
    payload = simulator.simulation_payload(simulator.parse_args(argv))
    return payload["decision"], payload


def test_owner_raw_policy_simulator_allows_sanitized_owner_match():
    decision, payload = run_simulator(
        [
            "--source-visibility",
            "owner_raw",
            "--viewer-mode",
            "local_first",
            "--viewer-user",
            "analyst",
            "--query-user",
            "analyst",
        ]
    )

    assert payload["kind"] == "owner_raw_source_policy_simulation_v1"
    assert decision["allowed"] is True
    assert decision["reason_code"] == "viewer_matches_query_user"
    assert decision["viewer_mode"] == "local_first"
    assert payload["input_shape"]["query_user_provided"] is True


def test_owner_raw_policy_simulator_models_d3_header_shape_without_echoing_subjects(capsys):
    status = simulator.main(
        [
            "--source-visibility",
            "owner_raw",
            "--host",
            "0.0.0.0",
            "--allow-nonlocal-web-bind",
            "--viewer-identity-header-configured",
            "--viewer-header-value",
            "analyst@EXAMPLE.COM",
            "--query-user",
            "analyst",
        ]
    )

    captured = capsys.readouterr()
    assert status == 0
    payload = json.loads(captured.out)
    assert payload["decision"]["allowed"] is False
    assert payload["decision"]["reason_code"] == "viewer_not_authorized_for_query_user"
    assert payload["decision"]["authenticated_viewer_configured"] is True
    assert payload["input_shape"]["viewer_header_value_provided"] is True
    assert "analyst" not in captured.out
    assert "EXAMPLE.COM" not in captured.out


def test_owner_raw_policy_simulator_denies_nonlocal_without_auth_before_kill_switch():
    decision, _payload = run_simulator(
        [
            "--source-visibility",
            "owner_raw",
            "--host",
            "0.0.0.0",
            "--allow-nonlocal-web-bind",
            "--owner-raw-source-disabled",
            "--viewer-mode",
            "local_first",
            "--viewer-user",
            "analyst",
            "--query-user",
            "analyst",
        ]
    )

    assert decision["allowed"] is False
    assert decision["reason_code"] == "nonlocal_bind_without_authenticated_viewer"


def test_owner_raw_policy_simulator_fail_on_deny_returns_one(capsys):
    status = simulator.main(
        [
            "--source-visibility",
            "owner_raw",
            "--query-user",
            "analyst",
            "--fail-on-deny",
        ]
    )

    assert status == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"]["reason_code"] == "viewer_not_authorized_for_query_user"


def test_owner_raw_policy_simulator_rejects_invalid_authenticated_input(capsys):
    status = simulator.main(["--viewer-mode", "authenticated"])

    captured = capsys.readouterr()
    assert status == 2
    assert captured.out == ""
    assert "requires --viewer-user" in captured.err
