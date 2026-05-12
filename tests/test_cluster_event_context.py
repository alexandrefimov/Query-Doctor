import json

from query_doctor.cluster.event_context import build_cluster_event_context
from query_doctor.cli import cm_events


def test_cluster_event_context_keeps_stable_safe_schema():
    cm_context = {
        "source": "cm_events",
        "available": True,
        "status": "ok",
        "product_status": "degraded_service_candidate",
        "window": {
            "window_minutes": 15,
            "max_events": 20,
            "service_scope": "configured",
            "severity_filter": ["critical", "warning"],
            "category_filter": ["LOG_EVENT"],
            "alerts_only": False,
        },
        "event_count": 3,
        "alert_count": 1,
        "severity_counts": {"critical": 1, "warning": 2, "RAW_HOST_TOKEN": 4},
        "signal_counts": {
            "impala_daemon_error_event": 2,
            "metastore_error_event": 1,
            "RAW_EVENT_TOKEN": 5,
        },
        "signals": [
            {
                "signal_id": "impala_daemon_error_event",
                "status": "observed",
                "severity": "critical",
                "event_count": 2,
                "alert_count": 1,
                "trend": "unknown",
                "claim_level": "cluster_candidate",
                "raw_provider_payload": "RAW_PROVIDER_PAYLOAD_TOKEN",
            }
        ],
        "raw_provider_payload": "RAW_PROVIDER_PAYLOAD_TOKEN",
        "limitations": [
            "CM events are prepared event summaries, not standalone root-cause proof.",
            "provider path /tmp/raw-provider-detail was present",
            "RAW_LIMITATION_TOKEN",
        ],
    }

    context = build_cluster_event_context(cm_context)
    rendered = json.dumps(context, sort_keys=True)

    assert context == {
        "schema_version": 1,
        "source": "cm_events",
        "available": True,
        "status": "ok",
        "product_status": "degraded_service_candidate",
        "window": {
            "window_minutes": 15,
            "max_events": 20,
            "service_scope": "configured",
            "severity_filter": ["critical", "warning"],
            "category_filter": ["LOG_EVENT"],
            "alerts_only": False,
        },
        "event_count": 3,
        "alert_count": 1,
        "severity_counts": {"critical": 1, "warning": 2},
        "signal_counts": {
            "impala_daemon_error_event": 2,
            "metastore_error_event": 1,
        },
        "signals": [
            {
                "signal_id": "impala_daemon_error_event",
                "status": "observed",
                "severity": "critical",
                "event_count": 2,
                "alert_count": 1,
                "trend": "unknown",
                "claim_level": "cluster_candidate",
            }
        ],
        "limitations": [
            "Cluster event context contains prepared event summaries, not standalone root-cause proof.",
            "A provider limitation was omitted because it contained raw details.",
        ],
        "guardrail": (
            "Cluster event context contains bounded prepared event summaries only. "
            "It is not standalone root-cause proof."
        ),
    }
    assert "RAW_" not in rendered
    assert "/tmp/raw-provider-detail" not in rendered
    assert "raw_provider_payload" not in rendered


def test_cluster_event_context_unavailable_is_inconclusive():
    context = build_cluster_event_context(
        {
            "available": False,
            "status": "unavailable",
            "product_status": "degraded_service_candidate",
            "window": {"window_minutes": 10, "max_events": 5},
            "limitations": ["CM events were unavailable: RAW_PROVIDER_ERROR_TOKEN"],
        }
    )

    assert context["available"] is False
    assert context["status"] == "unavailable"
    assert context["product_status"] == "inconclusive"
    assert context["limitations"] == [
        "Cluster event context was unavailable from the configured provider."
    ]


def test_cluster_event_context_safe_empty_text_passes():
    context = build_cluster_event_context(
        {
            "available": True,
            "status": "ok",
            "product_status": "cluster_context_clean",
            "window": {"window_minutes": 60, "max_events": 50},
            "event_count": 0,
            "alert_count": 0,
            "limitations": ["No prepared events matched the bounded window."],
        }
    )

    assert context["schema_version"] == 1
    assert context["product_status"] == "cluster_context_clean"
    assert context["limitations"] == ["No prepared events matched the bounded window."]


def test_cm_events_cli_can_write_cluster_event_context_json(tmp_path, capsys):
    output_json = tmp_path / "cm-events.json"
    cluster_context_json = tmp_path / "cluster_event_context.json"

    class FakeClient:
        def get_text(self, path, params=None, *, max_response_bytes=None):
            return json.dumps(
                {
                    "items": [
                        {
                            "category": "LOG_EVENT",
                            "severity": "IMPORTANT",
                            "content": "metastore error with RAW_PROVIDER_DETAIL_TOKEN",
                        }
                    ]
                }
            )

    result = cm_events.main(
        [
            "--cm-url",
            "https://cm.example.invalid:7183",
            "--max-events",
            "5",
            "--output-json",
            str(output_json),
            "--cluster-event-context-json",
            str(cluster_context_json),
        ],
        env={"CM_TOKEN": "TOKEN_VALUE"},
        client_factory=lambda http_config: FakeClient(),
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "Cluster event context JSON written:" in captured.out
    payload = json.loads(cluster_context_json.read_text(encoding="utf-8"))
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == 1
    assert payload["source"] == "cm_events"
    assert payload["signal_counts"] == {"metastore_error_event": 1}
    assert "RAW_PROVIDER_DETAIL_TOKEN" not in rendered
