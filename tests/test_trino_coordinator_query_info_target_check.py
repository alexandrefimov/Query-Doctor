import json
from copy import deepcopy

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.cli import trino_coordinator_query_info_target_check
from query_doctor.cli import trino_coordinator_query_info_pruned_probe
from query_doctor.trino.coordinator_query_info_target import (
    TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION,
    TRINO_COORDINATOR_QUERY_INFO_PRUNED_PROBE_SCHEMA_VERSION,
    TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_VERSION,
    TRINO_COORDINATOR_QUERY_INFO_TARGET_CHECK_SCHEMA_VERSION,
    _open_without_redirects,
    fetch_trino_coordinator_pruned_query_info_text,
    parse_trino_coordinator_query_info_auth_header_text,
    probe_trino_coordinator_query_info_pruned,
    trino_coordinator_query_info_pruned_probe_summary_payload,
    validate_trino_coordinator_query_info_source_contract_payload,
    validate_trino_coordinator_query_info_target,
)


COORDINATOR_URL = "https://coordinator.example.test:8443"
QUERY_ID = "20260603_120102_00001_abcde"


def test_trino_coordinator_query_info_contract_maps_safe_contract():
    result = validate_trino_coordinator_query_info_source_contract_payload(_safe_contract())

    assert result.source_contract_version == TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_VERSION
    assert result.source_type == "coordinator_query_info"
    assert result.query_info_contract_version == TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION
    assert result.auth_reference_kind == "external_secret_reference"
    assert result.auth_reference_label == "external_ref_01"
    assert result.query_bound_kind == "explicit_query_id"
    assert result.max_query_ids == 1
    assert result.max_bytes == 65536
    assert result.max_query_info_depth == 16
    assert result.timeout_seconds == 30
    assert result.raw_payload_storage == "forbidden"
    assert result.normalized_fact_storage == "allowed"
    assert result.browser_report_output == "blocked"


def test_trino_coordinator_query_info_target_check_never_fetches():
    contract = validate_trino_coordinator_query_info_source_contract_payload(_safe_contract())

    result = validate_trino_coordinator_query_info_target(
        contract,
        coordinator_url=COORDINATOR_URL,
        query_id=QUERY_ID,
    )

    assert result.coordinator_base_url_checked is True
    assert result.query_id_checked is True
    assert result.network_read_performed is False
    assert result.endpoint_template == "/v1/query/{queryId}"


def test_trino_coordinator_query_info_pruned_probe_fetches_after_contract_gate():
    calls = []
    contract = validate_trino_coordinator_query_info_source_contract_payload(_safe_probe_contract())

    def fetcher(
        coordinator_url: str, *, query_id: str, max_bytes: int, timeout_seconds: int
    ) -> str:
        calls.append((coordinator_url, query_id, max_bytes, timeout_seconds))
        return _raw_query_info_text()

    result = probe_trino_coordinator_query_info_pruned(
        contract,
        coordinator_url=COORDINATOR_URL,
        query_id=QUERY_ID,
        fetcher=fetcher,
    )

    assert calls == [(COORDINATOR_URL, QUERY_ID, 65536, 30)]
    assert result.target_check.network_read_performed is True
    assert result.endpoint_template == "/v1/query/{queryId}?pruned=true"
    assert result.pruned_query_parameter is True
    assert result.query_info_json_object_checked is True
    assert result.mapped_to_facts is False
    assert result.parser_coverage == "not_mapped"


def test_trino_coordinator_query_info_pruned_probe_summary_is_raw_free():
    contract = validate_trino_coordinator_query_info_source_contract_payload(_safe_probe_contract())
    result = probe_trino_coordinator_query_info_pruned(
        contract,
        coordinator_url=COORDINATOR_URL,
        query_id=QUERY_ID,
        fetcher=lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    payload = trino_coordinator_query_info_pruned_probe_summary_payload(result)
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == TRINO_COORDINATOR_QUERY_INFO_PRUNED_PROBE_SCHEMA_VERSION
    assert payload["target"]["endpoint_template"] == "/v1/query/{queryId}?pruned=true"
    assert payload["target"]["network_read_performed"] is True
    assert payload["query_info"]["mapped_to_facts"] is False
    assert COORDINATOR_URL not in rendered
    assert QUERY_ID not in rendered
    assert "SELECT" not in rendered
    assert "operator_user" not in rendered
    assert "sensitive_table" not in rendered


def test_trino_coordinator_query_info_fetch_uses_pruned_endpoint(monkeypatch):
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit: int) -> bytes:
            return b'{"queryId": "redacted-by-test"}'

    def fake_open_without_redirects(request, *, timeout: int):
        calls.append((request.full_url, request.get_header("Accept"), timeout))
        return Response()

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_target._open_without_redirects",
        fake_open_without_redirects,
    )

    text = fetch_trino_coordinator_pruned_query_info_text(
        COORDINATOR_URL,
        query_id=QUERY_ID,
        max_bytes=65536,
        timeout_seconds=30,
    )

    assert text == '{"queryId": "redacted-by-test"}'
    assert calls == [
        (
            f"{COORDINATOR_URL}/v1/query/{QUERY_ID}?pruned=true",
            "application/json",
            30,
        )
    ]


def test_trino_coordinator_query_info_fetch_can_use_operator_authorization_header(
    monkeypatch,
):
    calls = []
    header_value = "RedactedAuth value"

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit: int) -> bytes:
            return b'{"queryId": "redacted-by-test"}'

    def fake_open_without_redirects(request, *, timeout: int):
        calls.append(
            (
                request.full_url,
                request.get_header("Accept"),
                request.get_header("Authorization"),
                timeout,
            )
        )
        return Response()

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_target._open_without_redirects",
        fake_open_without_redirects,
    )

    text = fetch_trino_coordinator_pruned_query_info_text(
        COORDINATOR_URL,
        query_id=QUERY_ID,
        max_bytes=65536,
        timeout_seconds=30,
        auth_headers={"Authorization": header_value},
    )

    assert text == '{"queryId": "redacted-by-test"}'
    assert calls == [
        (
            f"{COORDINATOR_URL}/v1/query/{QUERY_ID}?pruned=true",
            "application/json",
            header_value,
            30,
        )
    ]


def test_trino_coordinator_query_info_open_uses_shared_diagnostic_egress(monkeypatch):
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def fake_configured_diagnostic_urlopen(request, *, timeout: int):
        calls.append((request.full_url, timeout))
        return Response()

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_target.configured_diagnostic_urlopen",
        fake_configured_diagnostic_urlopen,
    )

    with _open_without_redirects(
        type("Request", (), {"full_url": f"{COORDINATOR_URL}/v1/query/{QUERY_ID}"})(),
        timeout=30,
    ) as response:
        assert isinstance(response, Response)

    assert calls == [(f"{COORDINATOR_URL}/v1/query/{QUERY_ID}", 30)]


def test_trino_coordinator_query_info_fetch_rejects_redirect_without_echo(monkeypatch):
    def fake_open_without_redirects(_request, *, timeout: int):
        raise OSError("redirect blocked")

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_target._open_without_redirects",
        fake_open_without_redirects,
    )

    try:
        fetch_trino_coordinator_pruned_query_info_text(
            COORDINATOR_URL,
            query_id=QUERY_ID,
            max_bytes=65536,
            timeout_seconds=30,
        )
    except EngineFactContractError as exc:
        message = str(exc)
    else:
        raise AssertionError("redirect-like fetch failure must be rejected")

    assert "could not be read" in message
    assert COORDINATOR_URL not in message
    assert QUERY_ID not in message
    assert "redirect.example.test" not in message


def test_trino_coordinator_query_info_auth_header_rejects_unsupported_without_echo():
    header_value = "RedactedAuth value"

    try:
        parse_trino_coordinator_query_info_auth_header_text(f"X-Unsupported-Auth: {header_value}")
    except EngineFactContractError as exc:
        message = str(exc)
    else:
        raise AssertionError("auth parser must reject unsupported header names")

    assert "must be Authorization" in message
    assert header_value not in message


def test_trino_coordinator_query_info_cli_prints_safe_summary(tmp_path, capsys):
    contract_path = tmp_path / "operator-query-info-contract.json"
    contract_path.write_text(json.dumps(_safe_contract()), encoding="utf-8")

    exit_code = trino_coordinator_query_info_target_check.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[trino-coordinator-query-info-target] accepted" in captured.out
    assert "source_type: coordinator_query_info" in captured.out
    assert "query_bound: explicit_query_id" in captured.out
    assert "network_read_performed: False" in captured.out
    assert "operator-query-info-contract.json" not in captured.out
    assert COORDINATOR_URL not in captured.out
    assert QUERY_ID not in captured.out
    assert "SELECT" not in captured.out
    assert captured.err == ""


def test_trino_coordinator_query_info_pruned_probe_cli_prints_safe_summary(
    tmp_path, monkeypatch, capsys
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    contract_path.write_text(json.dumps(_safe_probe_contract()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_target.fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    exit_code = trino_coordinator_query_info_pruned_probe.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[trino-coordinator-query-info-pruned-probe] accepted" in captured.out
    assert "endpoint_template: /v1/query/{queryId}?pruned=true" in captured.out
    assert "network_read_performed: True" in captured.out
    assert "query_info_json_object_checked: True" in captured.out
    assert "mapped_to_facts: False" in captured.out
    assert "operator-query-info-contract.json" not in captured.out
    assert COORDINATOR_URL not in captured.out
    assert QUERY_ID not in captured.out
    assert "SELECT" not in captured.out
    assert captured.err == ""


def test_trino_coordinator_query_info_pruned_probe_cli_passes_auth_header_without_echo(
    tmp_path, monkeypatch, capsys
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    auth_path = tmp_path / "operator-auth-header.txt"
    header_value = "RedactedAuth value"
    calls = []
    contract_path.write_text(json.dumps(_safe_probe_contract()), encoding="utf-8")
    auth_path.write_text(f"Authorization: {header_value}\n", encoding="utf-8")

    def fetcher(
        coordinator_url: str,
        *,
        query_id: str,
        max_bytes: int,
        timeout_seconds: int,
        auth_headers: dict[str, str],
    ) -> str:
        calls.append((coordinator_url, query_id, max_bytes, timeout_seconds, auth_headers))
        return _raw_query_info_text()

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_target.fetch_trino_coordinator_pruned_query_info_text",
        fetcher,
    )

    exit_code = trino_coordinator_query_info_pruned_probe.main(
        [
            "--redaction-reviewed",
            "--auth-header-file",
            str(auth_path),
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [(COORDINATOR_URL, QUERY_ID, 65536, 30, {"Authorization": header_value})]
    assert "operator-auth-header.txt" not in captured.out
    assert "operator-auth-header.txt" not in captured.err
    assert header_value not in captured.out
    assert header_value not in captured.err
    assert COORDINATOR_URL not in captured.out
    assert QUERY_ID not in captured.out


def test_trino_coordinator_query_info_pruned_probe_cli_rejects_auth_header_without_echo(
    tmp_path, capsys
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    auth_path = tmp_path / "operator-auth-header.txt"
    header_value = "RedactedAuth value"
    contract_path.write_text(json.dumps(_safe_probe_contract()), encoding="utf-8")
    auth_path.write_text(f"X-Unsupported-Auth: {header_value}\n", encoding="utf-8")

    exit_code = trino_coordinator_query_info_pruned_probe.main(
        [
            "--redaction-reviewed",
            "--auth-header-file",
            str(auth_path),
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "auth header must be Authorization" in captured.err
    assert "operator-auth-header.txt" not in captured.err
    assert header_value not in captured.err
    assert COORDINATOR_URL not in captured.err
    assert QUERY_ID not in captured.err


def test_trino_coordinator_query_info_pruned_probe_cli_summary_json_is_raw_free(
    tmp_path, monkeypatch, capsys
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    contract_path.write_text(json.dumps(_safe_probe_contract()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_target.fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    exit_code = trino_coordinator_query_info_pruned_probe.main(
        [
            "--redaction-reviewed",
            "--format",
            "summary-json",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == TRINO_COORDINATOR_QUERY_INFO_PRUNED_PROBE_SCHEMA_VERSION
    assert payload["target"]["network_read_performed"] is True
    assert payload["query_info"]["parser_coverage"] == "not_mapped"
    assert COORDINATOR_URL not in rendered
    assert QUERY_ID not in rendered
    assert "SELECT" not in rendered
    assert "operator_user" not in rendered
    assert captured.err == ""


def test_trino_coordinator_query_info_pruned_probe_cli_requires_redaction_review(tmp_path, capsys):
    contract_path = tmp_path / "operator-query-info-contract.json"
    contract_path.write_text(json.dumps(_safe_probe_contract()), encoding="utf-8")

    exit_code = trino_coordinator_query_info_pruned_probe.main(
        [
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert "operator-query-info-contract.json" not in captured.err
    assert COORDINATOR_URL not in captured.err
    assert QUERY_ID not in captured.err


def test_trino_coordinator_query_info_cli_summary_json_is_raw_free(tmp_path, capsys):
    contract_path = tmp_path / "operator-query-info-contract.json"
    contract_path.write_text(json.dumps(_safe_contract()), encoding="utf-8")

    exit_code = trino_coordinator_query_info_target_check.main(
        [
            "--redaction-reviewed",
            "--format",
            "summary-json",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == TRINO_COORDINATOR_QUERY_INFO_TARGET_CHECK_SCHEMA_VERSION
    assert payload["source_type"] == "coordinator_query_info"
    assert payload["target"]["endpoint_template"] == "/v1/query/{queryId}"
    assert payload["target"]["network_read_performed"] is False
    assert "operator-query-info-contract.json" not in rendered
    assert COORDINATOR_URL not in rendered
    assert QUERY_ID not in rendered
    assert "SELECT" not in rendered
    assert captured.err == ""


def test_trino_coordinator_query_info_pruned_probe_rejects_secret_auth_before_fetch(
    tmp_path, monkeypatch, capsys
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    contract_path.write_text(json.dumps(_safe_contract()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_target.fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("probe must not fetch unsupported auth kinds")
        ),
    )

    exit_code = trino_coordinator_query_info_pruned_probe.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "probe auth reference is unsupported" in captured.err
    assert "external_secret_reference" not in captured.err
    assert COORDINATOR_URL not in captured.err
    assert QUERY_ID not in captured.err


def test_trino_coordinator_query_info_pruned_probe_rejects_non_object_without_echo():
    contract = validate_trino_coordinator_query_info_source_contract_payload(_safe_probe_contract())

    try:
        probe_trino_coordinator_query_info_pruned(
            contract,
            coordinator_url=COORDINATOR_URL,
            query_id=QUERY_ID,
            fetcher=lambda *_args, **_kwargs: '["SELECT secret_col FROM sensitive_table"]',
        )
    except EngineFactContractError as exc:
        message = str(exc)
    else:
        raise AssertionError("probe must reject non-object query-info payloads")

    assert "needs a JSON object" in message
    assert "SELECT" not in message
    assert "sensitive_table" not in message


def test_trino_coordinator_query_info_cli_requires_redaction_review(tmp_path, capsys):
    contract_path = tmp_path / "operator-query-info-contract.json"
    contract_path.write_text(json.dumps(_safe_contract()), encoding="utf-8")

    exit_code = trino_coordinator_query_info_target_check.main(
        [
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert "operator-query-info-contract.json" not in captured.err
    assert COORDINATOR_URL not in captured.err
    assert QUERY_ID not in captured.err


def test_trino_coordinator_query_info_rejects_non_coordinator_source_without_echo(tmp_path, capsys):
    payload = _safe_contract()
    payload["source_type"] = "http_query_detail_archive"
    contract_path = tmp_path / "operator-query-info-contract.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_coordinator_query_info_target_check.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "source type is unsupported" in captured.err
    assert "http_query_detail_archive" not in captured.err
    assert "operator-query-info-contract.json" not in captured.err
    assert COORDINATOR_URL not in captured.err
    assert QUERY_ID not in captured.err


def test_trino_coordinator_query_info_rejects_credentialed_url_without_echo(tmp_path, capsys):
    contract_path = tmp_path / "operator-query-info-contract.json"
    contract_path.write_text(json.dumps(_safe_contract()), encoding="utf-8")
    credential_value = "credential_value"
    raw_url = (
        "https://" + "operator" + ":" + credential_value + "@" + "coordinator.example.test:8443"
    )

    exit_code = trino_coordinator_query_info_target_check.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            raw_url,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "URL is unsupported" in captured.err
    assert raw_url not in captured.err
    assert credential_value not in captured.err
    assert "operator-query-info-contract.json" not in captured.err
    assert QUERY_ID not in captured.err


def test_trino_coordinator_query_info_rejects_query_id_path_without_echo(tmp_path, capsys):
    contract_path = tmp_path / "operator-query-info-contract.json"
    contract_path.write_text(json.dumps(_safe_contract()), encoding="utf-8")
    raw_query_id = QUERY_ID + "/queryText"

    exit_code = trino_coordinator_query_info_target_check.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            raw_query_id,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "query ID is unsupported" in captured.err
    assert raw_query_id not in captured.err
    assert "queryText" not in captured.err
    assert "operator-query-info-contract.json" not in captured.err
    assert COORDINATOR_URL not in captured.err


def test_trino_coordinator_query_info_rejects_extra_raw_fields_without_echo(tmp_path, capsys):
    payload = deepcopy(_safe_contract())
    raw_value = "SELECT " + "secret_col FROM sensitive_table"
    payload["queryText"] = raw_value
    contract_path = tmp_path / "operator-query-info-contract.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_coordinator_query_info_target_check.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "fields are unsupported" in captured.err
    assert raw_value not in captured.err
    assert "queryText" not in captured.err
    assert "operator-query-info-contract.json" not in captured.err
    assert COORDINATOR_URL not in captured.err
    assert QUERY_ID not in captured.err


def test_trino_coordinator_query_info_rejects_credential_label_without_echo(tmp_path, capsys):
    payload = _safe_contract()
    raw_value = "prod_secret_token"
    payload["auth_reference"]["label"] = raw_value
    contract_path = tmp_path / "operator-query-info-contract.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_coordinator_query_info_target_check.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "auth reference label is not safe" in captured.err
    assert raw_value not in captured.err
    assert "operator-query-info-contract.json" not in captured.err
    assert COORDINATOR_URL not in captured.err
    assert QUERY_ID not in captured.err


def _safe_contract() -> dict:
    return {
        "source_contract_version": TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_VERSION,
        "source_type": "coordinator_query_info",
        "query_info_contract_version": TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION,
        "auth_reference": {
            "kind": "external_secret_reference",
            "label": "external_ref_01",
        },
        "query_bound": {
            "kind": "explicit_query_id",
            "max_query_ids": 1,
        },
        "bounds": {
            "max_bytes": 65536,
            "max_query_info_depth": 16,
            "timeout_seconds": 30,
        },
        "redaction": {
            "redaction_review_required": True,
            "raw_payload_storage": "forbidden",
            "normalized_fact_storage": "allowed",
            "browser_report_output": "blocked",
        },
    }


def _safe_probe_contract() -> dict:
    payload = _safe_contract()
    payload["auth_reference"] = {
        "kind": "operator_managed_reference",
        "label": "external_ref_01",
    }
    return payload


def _raw_query_info_text() -> str:
    return json.dumps(
        {
            "queryId": QUERY_ID,
            "state": "FINISHED",
            "query": "SELECT secret_col FROM sensitive_table",
            "session": {
                "user": "operator_user",
                "source": "adhoc_console",
            },
            "self": COORDINATOR_URL + "/ui/query.html?" + QUERY_ID,
        }
    )
