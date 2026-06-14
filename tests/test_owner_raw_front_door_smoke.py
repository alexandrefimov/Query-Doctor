import json

from scripts import owner_raw_front_door_smoke as smoke


def by_name(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, list)
    return {str(item["name"]): item for item in scenarios}


def test_owner_raw_front_door_smoke_matrix_passes_without_raw_values():
    payload = smoke.smoke_payload()
    scenarios = by_name(payload)

    assert payload["kind"] == "owner_raw_front_door_smoke_v1"
    assert payload["all_passed"] is True
    assert payload["scenario_count"] == 6
    assert set(scenarios) == {
        "matching_header_strips_inbound_spoof",
        "kerberos_primary_maps_to_simple_owner",
        "missing_front_door_subject_denies",
        "mismatched_front_door_subject_denies",
        "service_principal_rejected_by_front_door",
        "duplicate_upstream_header_denies",
    }

    stripped = scenarios["matching_header_strips_inbound_spoof"]
    assert stripped["passed"] is True
    assert stripped["front_door"]["inbound_viewer_header_count"] == 2
    assert stripped["front_door"]["upstream_viewer_header_count"] == 1
    assert stripped["decision"]["allowed"] is True
    assert stripped["decision"]["reason_code"] == "viewer_matches_query_user"

    kerberos = scenarios["kerberos_primary_maps_to_simple_owner"]
    assert kerberos["front_door"]["mapped_subject_to_owner"] is True
    assert kerberos["front_door"]["upstream_viewer_header_count"] == 1
    assert kerberos["decision"]["allowed"] is True

    missing = scenarios["missing_front_door_subject_denies"]
    assert missing["front_door"]["upstream_viewer_header_count"] == 0
    assert missing["decision"]["allowed"] is False
    assert missing["decision"]["reason_code"] == "viewer_not_authorized_for_query_user"

    service = scenarios["service_principal_rejected_by_front_door"]
    assert service["front_door"]["mapped_subject_to_owner"] is False
    assert service["front_door"]["upstream_viewer_header_count"] == 0
    assert service["decision"]["allowed"] is False

    duplicate = scenarios["duplicate_upstream_header_denies"]
    assert duplicate["front_door"]["upstream_viewer_header_count"] == 2
    assert duplicate["decision"]["allowed"] is False
    assert duplicate["decision"]["reason_code"] == "viewer_not_authorized_for_query_user"

    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "analyst_one",
        "other_owner",
        "spoofed_owner",
        "EXAMPLE.REALM",
        "impala/host",
        "X-Query-Doctor-Viewer",
    ):
        assert forbidden not in serialized


def test_owner_raw_front_door_smoke_cli_outputs_raw_free_json(capsys):
    status = smoke.main([])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert status == 0
    assert payload["all_passed"] is True
    assert "analyst_one" not in captured.out
    assert "EXAMPLE.REALM" not in captured.out
    assert captured.err == ""


def test_owner_raw_front_door_smoke_doc_mentions_script():
    doc = (smoke.ROOT / "docs" / "owner-raw-d3-deployment.md").read_text(encoding="utf-8")

    assert "scripts/owner_raw_front_door_smoke.py" in doc
