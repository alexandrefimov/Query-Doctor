import io
import json
from pathlib import Path

import pytest

from web_server_test_support import load_web_module, write_complete_collected_case


OWNER_RAW_SQL = """
SELECT id, password = 'supersecret' AS masked_value
FROM qdleak_db_20260611.qdleak_table_20260611
WHERE scratch_path = '/tmp/owner-raw-private'
""".strip()
RAW_MARKERS = (
    "qdleak_db_20260611",
    "supersecret",
    "/tmp/owner-raw-private",
)


class MultiValueHeaders:
    def __init__(self, values):
        self.values = values

    def get(self, name):
        values = self.values.get(name)
        if not values:
            return None
        return values[0]

    def get_all(self, name):
        return self.values.get(name)


def write_owner_raw_contract_summary(tmp_path: Path, *, user: str = "analyst") -> Path:
    case_dir = tmp_path / "case-001"
    write_complete_collected_case(case_dir)
    (case_dir / "analysis_facts.md").write_text(
        "# Query Doctor deterministic analysis facts\n", encoding="utf-8"
    )
    (case_dir / "original_query.sql").write_text(OWNER_RAW_SQL, encoding="utf-8")
    summary = tmp_path / "batch_summary.json"
    summary.write_text(
        json.dumps(
            {
                "selected_count": 1,
                "cases": [
                    {
                        "case_index": 1,
                        "case_dir": "case-001",
                        "query_id": "aaaabbbbccccdddd:1111222233334444",
                        "user": user,
                        "score": 80,
                        "duration_sec": 120,
                        "collection_status": "ok",
                        "analysis_status": "ok",
                        "metadata_status": "skipped",
                        "table_stats_status": "not_checked",
                        "score_reasons": ["cardinality anomaly detected"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return summary


def make_owner_raw_d3_handler(tmp_path: Path, *, owner_raw_source_enabled: bool = True):
    module = load_web_module()
    summary = write_owner_raw_contract_summary(tmp_path)
    settings = module.WebSettings(
        config=tmp_path / "cm-config.json",
        batch_summary=summary,
        source_visibility="owner_raw",
        viewer_identity_header="X-QD-Viewer",
        owner_raw_source_enabled=owner_raw_source_enabled,
    )
    return module.make_handler(settings, job_store=module.WebJobStore())


def handler_get(handler, path: str, headers):
    request = handler.__new__(handler)
    captured: dict[str, object] = {"headers": []}
    output = io.BytesIO()
    request.path = path
    request.headers = headers
    request.wfile = output
    request.send_response = lambda status: captured.__setitem__("status", status)
    request.send_header = lambda name, value: captured["headers"].append((name, value))
    request.end_headers = lambda: None
    request.do_GET()
    return captured, output.getvalue().decode("utf-8")


def assert_raw_markers_hidden(body: str) -> None:
    for marker in RAW_MARKERS:
        assert marker not in body


@pytest.mark.parametrize(
    ("headers", "source_status", "source_allowed", "detail_link_allowed"),
    (
        ({"Host": "127.0.0.1"}, 403, False, False),
        (
            MultiValueHeaders(
                {
                    "Host": ["127.0.0.1"],
                    "X-QD-Viewer": ["analyst", "other_user"],
                }
            ),
            403,
            False,
            False,
        ),
        (
            {
                "Host": "127.0.0.1",
                "X-QD-Viewer": "impala/host.example.com@EXAMPLE.COM",
            },
            403,
            False,
            False,
        ),
        (
            {"Host": "127.0.0.1", "X-QD-Viewer": "analyst@EXAMPLE.COM"},
            403,
            False,
            False,
        ),
        (
            {
                "Host": "127.0.0.1",
                "X-QD-Viewer": "CN=Analyst One,OU=Users,DC=example,DC=com",
            },
            403,
            False,
            False,
        ),
        (
            {"Host": "127.0.0.1", "X-QD-Viewer": "group:analytics"},
            403,
            False,
            False,
        ),
        ({"Host": "127.0.0.1", "X-QD-Viewer": "other_user"}, 403, False, False),
        ({"Host": "127.0.0.1", "X-QD-Viewer": "analyst"}, 200, True, True),
    ),
    ids=(
        "missing",
        "duplicate",
        "service-principal",
        "upn",
        "ad-distinguished-name",
        "group-like",
        "mismatch",
        "match",
    ),
)
def test_owner_raw_d3_viewer_header_matrix_gates_source_and_details(
    tmp_path,
    headers,
    source_status,
    source_allowed,
    detail_link_allowed,
):
    handler = make_owner_raw_d3_handler(tmp_path)

    source_response, source_body = handler_get(handler, "/batch/case/case-001/source", headers)
    detail_response, detail_body = handler_get(handler, "/batch/case/case-001", headers)

    assert source_response["status"] == source_status
    assert detail_response["status"] == 200
    if detail_link_allowed:
        assert 'href="/batch/case/case-001/source"' in detail_body
    else:
        assert 'href="/batch/case/case-001/source"' not in detail_body
    if source_allowed:
        assert "qdleak_db_20260611.qdleak_table_20260611" in source_body
        assert "supersecret" not in source_body
        assert "/tmp/owner-raw-private" not in source_body
        assert_raw_markers_hidden(detail_body)
    else:
        assert 'data-reason-code="viewer_not_authorized_for_query_user"' in source_body
        assert_raw_markers_hidden(source_body)
        assert_raw_markers_hidden(detail_body)


def test_owner_raw_d3_kill_switch_blocks_source_and_details_link(tmp_path):
    handler = make_owner_raw_d3_handler(tmp_path, owner_raw_source_enabled=False)
    headers = {"Host": "127.0.0.1", "X-QD-Viewer": "analyst"}

    source_response, source_body = handler_get(handler, "/batch/case/case-001/source", headers)
    detail_response, detail_body = handler_get(handler, "/batch/case/case-001", headers)

    assert source_response["status"] == 403
    assert 'data-reason-code="owner_raw_source_disabled"' in source_body
    assert detail_response["status"] == 200
    assert 'href="/batch/case/case-001/source"' not in detail_body
    assert_raw_markers_hidden(source_body)
    assert_raw_markers_hidden(detail_body)
