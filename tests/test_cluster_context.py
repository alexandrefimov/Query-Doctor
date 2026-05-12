import json

from query_doctor.cli import cm_events
from query_doctor.cluster.context import build_cluster_context
from query_doctor.cluster.event_context import build_cluster_event_context


def test_cluster_context_aggregates_event_context_status_and_checks():
    event_context = build_cluster_event_context(
        {
            "available": True,
            "status": "ok",
            "product_status": "degraded_service_candidate",
            "window": {
                "window_minutes": 15,
                "max_events": 20,
                "service_scope": "not_set",
                "severity_filter": ["important"],
                "category_filter": [],
                "alerts_only": False,
            },
            "event_count": 2,
            "alert_count": 0,
            "signal_counts": {"hdfs_slow_disk_event": 2},
            "signals": [
                {
                    "signal_id": "hdfs_slow_disk_event",
                    "status": "observed",
                    "severity": "important",
                    "event_count": 2,
                    "alert_count": 0,
                    "trend": "unknown",
                    "claim_level": "cluster_candidate",
                }
            ],
        }
    )

    context = build_cluster_context(event_context=event_context)

    assert context["schema_version"] == 1
    assert context["product"] == "cluster_doctor"
    assert context["available"] is True
    assert context["status"] == "degraded_service_candidate"
    assert context["sources"] == [
        {
            "source": "cm_events",
            "available": True,
            "status": "ok",
            "product_status": "degraded_service_candidate",
        }
    ]
    assert context["signal_counts"] == {"hdfs_slow_disk_event": 2}
    assert context["signals"][0]["signal_id"] == "hdfs_slow_disk_event"
    assert context["next_checks"] == ["Check HDFS/DataNode health and recent storage warnings."]


def test_cluster_context_is_inconclusive_without_sources():
    context = build_cluster_context()

    assert context["available"] is False
    assert context["status"] == "inconclusive"
    assert context["sources"] == []
    assert context["signal_counts"] == {}
    assert context["signals"] == []
    assert context["limitations"] == [
        "No cluster context sources were provided.",
        "Cluster context is not standalone root-cause proof.",
    ]


def test_cluster_context_omits_raw_source_fields():
    event_context = {
        "source": "cm_events",
        "available": True,
        "status": "ok",
        "product_status": "pressure_observed",
        "window": {
            "window_minutes": 10,
            "max_events": 5,
            "service_scope": "RAW_SERVICE_TOKEN",
        },
        "signal_counts": {"RAW_SIGNAL_TOKEN": 5, "generic_event_signal": 1},
        "signals": [
            {
                "signal_id": "RAW_SIGNAL_TOKEN",
                "status": "observed",
                "severity": "critical",
                "event_count": 5,
                "alert_count": 0,
                "trend": "unknown",
                "claim_level": "cluster_candidate",
            },
            {
                "signal_id": "generic_event_signal",
                "status": "observed",
                "severity": "warning",
                "event_count": 1,
                "alert_count": 0,
                "trend": "unknown",
                "claim_level": "cluster_candidate",
            },
        ],
        "limitations": [
            "provider path /tmp/raw-provider-detail was present",
            "RAW_LIMITATION_TOKEN",
        ],
        "raw_provider_payload": "RAW_PROVIDER_PAYLOAD_TOKEN",
    }

    context = build_cluster_context(event_context=event_context)
    rendered = json.dumps(context, sort_keys=True)

    assert context["status"] == "pressure_observed"
    assert context["signal_counts"] == {"generic_event_signal": 1}
    assert "RAW_" not in rendered
    assert "/tmp/raw-provider-detail" not in rendered
    assert "raw_provider_payload" not in rendered


def test_cm_events_cli_can_write_cluster_context_json(tmp_path, capsys):
    cluster_context_json = tmp_path / "cluster_context.json"

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
            "--cluster-context-json",
            str(cluster_context_json),
        ],
        env={"CM_TOKEN": "TOKEN_VALUE"},
        client_factory=lambda http_config: FakeClient(),
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "Cluster context JSON written:" in captured.out
    payload = json.loads(cluster_context_json.read_text(encoding="utf-8"))
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == 1
    assert payload["product"] == "cluster_doctor"
    assert payload["status"] == "degraded_service_candidate"
    assert payload["signal_counts"] == {"metastore_error_event": 1}
    assert "RAW_PROVIDER_DETAIL_TOKEN" not in rendered
