import json
from datetime import datetime, timezone

import pytest

from query_doctor.cm import events
from query_doctor.cli import cm_events


def test_build_cm_events_request_is_bounded_and_scoped():
    request = events.CMEventsRequest(
        window_minutes=30,
        max_events=25,
        service="IMPALA_SERVICE_1",
        severities=("critical", "warning"),
        categories=("LOG_EVENT",),
        alerts_only=True,
        now=datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
    )

    path, params = events.build_cm_events_request(request)

    assert path == "/api/v32/events"
    assert params["maxResults"] == 25
    assert params["resultOffset"] == 0
    assert params["contentType"] == "application/json"
    query = params["query"]
    assert "timeReceived=ge=2026-05-06T11:30:00Z" in query
    assert "timeReceived=lt=2026-05-06T12:00:00Z" in query
    assert "severity==" not in query
    assert "category==LOG_EVENT" in query
    assert "attributes.service==IMPALA_SERVICE_1" in query
    assert "alert==true" in query


def test_build_cm_events_request_rejects_query_injection():
    request = events.CMEventsRequest(service="IMPALA;severity==critical")

    with pytest.raises(events.CMAdapterError):
        events.build_cm_events_request(request)


def test_summarize_cm_events_excludes_raw_event_content():
    raw = {
        "items": [
            {
                "id": "RAW_EVENT_ID_TOKEN",
                "category": "LOG_EVENT",
                "severity": "CRITICAL",
                "alert": True,
                "content": (
                    "impalad backend failed on RAW_HOST_TOKEN with "
                    "RAW_PRINCIPAL_TOKEN and RAW_QUERY_TEXT_TOKEN"
                ),
                "attributes": [
                    {"name": "host", "values": ["RAW_HOST_TOKEN"]},
                    {"name": "user", "values": ["RAW_USER_TOKEN"]},
                    {"name": "path", "values": ["RAW_PATH_TOKEN"]},
                ],
            },
            {
                "category": "HEALTH_EVENT",
                "severity": "WARNING",
                "content": "role health warning for RAW_HOST_TOKEN",
            },
        ],
        "totalResults": 5,
    }

    summary = events.summarize_cm_events_response(raw, events.CMEventsRequest(max_events=2))
    rendered = json.dumps(summary, sort_keys=True)

    assert summary["available"] is True
    assert summary["product_status"] == "degraded_service_candidate"
    assert summary["event_count"] == 2
    assert summary["alert_count"] == 1
    assert summary["severity_counts"] == {"critical": 1, "warning": 1}
    assert summary["signal_counts"]["impala_daemon_error_event"] == 1
    assert summary["signal_counts"]["role_unhealthy_event"] == 1
    assert "RAW_EVENT_ID_TOKEN" not in rendered
    assert "RAW_HOST_TOKEN" not in rendered
    assert "RAW_PRINCIPAL_TOKEN" not in rendered
    assert "RAW_QUERY_TEXT_TOKEN" not in rendered
    assert "RAW_USER_TOKEN" not in rendered
    assert "RAW_PATH_TOKEN" not in rendered


def test_summarize_cm_events_filters_severity_after_bounded_fetch():
    raw = {
        "items": [
            {
                "category": "LOG_EVENT",
                "severity": "INFORMATIONAL",
                "content": "impalad informational event",
            },
            {
                "category": "LOG_EVENT",
                "severity": "WARNING",
                "content": "impalad warning event",
            },
        ]
    }

    summary = events.summarize_cm_events_response(
        raw,
        events.CMEventsRequest(severities=("warning",)),
    )

    assert summary["event_count"] == 1
    assert summary["severity_counts"] == {"warning": 1}


def test_empty_cm_events_response_is_clean_context():
    summary = events.summarize_cm_events_response({"items": []}, events.CMEventsRequest())

    assert summary["available"] is True
    assert summary["product_status"] == "cluster_context_clean"
    assert summary["event_count"] == 0
    assert summary["signals"] == []


def test_cli_dry_run_uses_config_without_credentials(tmp_path, capsys):
    config = tmp_path / "query-doctor-config.json"
    config.write_text(
        json.dumps(
            {
                "cm_url": "https://cm.example.invalid:7183",
                "cluster": "CLUSTER_1",
                "service": "IMPALA_SERVICE_1",
            }
        ),
        encoding="utf-8",
    )

    result = cm_events.main(["--config", str(config), "--dry-run"], env={})

    captured = capsys.readouterr()
    assert result == 0
    assert "[CM events] Dry-run plan" in captured.out
    assert "Service scope: configured" in captured.out
    assert "No CM API calls are performed" in captured.out
    assert captured.err == ""


def test_cli_can_ignore_config_service_scope(tmp_path, capsys):
    config = tmp_path / "query-doctor-config.json"
    config.write_text(
        json.dumps(
            {
                "cm_url": "https://cm.example.invalid:7183",
                "cluster": "CLUSTER_1",
                "service": "IMPALA_SERVICE_1",
            }
        ),
        encoding="utf-8",
    )

    result = cm_events.main(["--config", str(config), "--no-service-scope", "--dry-run"], env={})

    captured = capsys.readouterr()
    assert result == 0
    assert "Cluster scope: configured" in captured.out
    assert "Service scope: not set" in captured.out


def test_cli_collects_with_injected_client_and_writes_sanitized_json(tmp_path, capsys):
    output_json = tmp_path / "cm-events.json"

    class FakeClient:
        def get_text(self, path, params=None, *, max_response_bytes=None):
            assert path == "/api/v32/events"
            assert params["maxResults"] == 5
            assert params["contentType"] == "application/json"
            assert "attributes.service==IMPALA_SERVICE_1" in params["query"]
            return json.dumps({
                "items": [
                    {
                        "category": "LOG_EVENT",
                        "severity": "IMPORTANT",
                        "content": "metastore error with RAW_QUERY_TEXT_TOKEN",
                    }
                ]
            })

    def client_factory(http_config):
        assert http_config.token == "TOKEN_VALUE"
        return FakeClient()

    result = cm_events.main(
        [
            "--cm-url",
            "https://cm.example.invalid:7183",
            "--service",
            "IMPALA_SERVICE_1",
            "--max-events",
            "5",
            "--output-json",
            str(output_json),
        ],
        env={"CM_TOKEN": "TOKEN_VALUE"},
        client_factory=client_factory,
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "Product status: degraded_service_candidate" in captured.out
    assert "RAW_QUERY_TEXT_TOKEN" not in captured.out
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["signal_counts"]["metastore_error_event"] == 1
    assert "RAW_QUERY_TEXT_TOKEN" not in rendered


def test_cli_requires_credentials_for_real_collection(capsys):
    result = cm_events.main(
        ["--cm-url", "https://cm.example.invalid:7183"],
        env={},
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "requires CM_TOKEN or CM_USERNAME/CM_PASSWORD" in captured.err
