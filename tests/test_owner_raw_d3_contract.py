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
REPO_DIR = Path(__file__).resolve().parents[1]


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


def test_owner_raw_d3_doc_pins_single_front_door_contract():
    text = (REPO_DIR / "docs" / "owner-raw-d3-deployment.md").read_text(encoding="utf-8")
    agents_text = (REPO_DIR / "AGENTS.md").read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())

    assert "Query Doctor supports one D3 application contract" in text
    assert "trusted auth front door -> exactly one normalized viewer header" in text
    assert "OIDC/SSO" in text
    assert "SPNEGO/Kerberos" in text
    assert "AD/LDAP" in text
    assert "not perform native OIDC" in normalized_text
    assert "Kerberos, LDAP, password, MFA" in normalized_text
    assert "Do not move SPNEGO negotiation into Query Doctor" in normalized_text
    assert "Do not configure Query Doctor to bind to LDAP" in normalized_text
    assert "from `viewer_identity_header`" in agents_text
    assert "Do not add native OIDC, SAML, SPNEGO" in agents_text


def test_owner_raw_d3_doc_pins_public_safe_front_door_examples():
    text = (REPO_DIR / "docs" / "owner-raw-d3-deployment.md").read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())

    assert "## Public-Safe Front Door Snippets" in text
    assert "not complete ingress or reverse-proxy configuration" in normalized_text
    assert "deny direct client network access to Query Doctor" in text
    assert "browser can spoof `viewer_identity_header`" in normalized_text
    assert 'strip_request_header("X-Query-Doctor-Viewer")' in text
    assert 'set_upstream_header("X-Query-Doctor-Viewer", viewer)' in text
    assert "drop_upstream_identity_tokens()" in text
    assert "claims = verified_oidc_or_sso_claims()" in text
    assert "principal = authenticated_kerberos_principal()" in text
    assert "reject_if_service_or_host_principal(principal)" in text
    assert "Do not use `sub`, email, UPN, display name, group, role" in normalized_text
    assert "Query Doctor should receive neither tickets nor principals" in normalized_text


def test_owner_raw_d3_validation_matrix_pins_broader_checks():
    matrix = (REPO_DIR / "docs" / "test-matrix.md").read_text(encoding="utf-8")
    deployment = (REPO_DIR / "docs" / "owner-raw-d3-deployment.md").read_text(encoding="utf-8")
    dev_sso = (REPO_DIR / "docs" / "dev-sso-keycloak.md").read_text(encoding="utf-8")
    normalized_matrix = " ".join(matrix.split())
    runbooks = "\n".join((deployment, dev_sso))

    assert "Owner-raw D3 viewer identity, front-door contract" in matrix
    assert "owner-raw-d3-deployment.md" in matrix
    assert "tests/test_*owner_raw*.py" in matrix
    assert "tests/test_viewer_identity.py" in matrix
    assert 'tests/test_web_server.py -k "owner_raw or viewer_identity_header"' in (
        normalized_matrix
    )
    assert "python3 scripts/check_staged_public_safety.py --changed" in matrix

    assert "python3 scripts/owner_raw_front_door_smoke.py --compact" in runbooks
    assert "python3 scripts/audit_owner_raw_live_front_door_review.py" in runbooks
    assert "python3 scripts/owner_raw_policy_simulator.py" in runbooks
    assert "--viewer-identity-header-configured" in runbooks
    assert "--fail-on-deny" in runbooks


def test_owner_raw_d3_docs_pin_pre_proxy_and_live_gate_boundary():
    deployment = (REPO_DIR / "docs" / "owner-raw-d3-deployment.md").read_text(encoding="utf-8")
    roadmap = (REPO_DIR / "docs" / "roadmap.md").read_text(encoding="utf-8")
    ru_roadmap = (REPO_DIR / "docs" / "i18n" / "ru" / "roadmap.md").read_text(encoding="utf-8")
    normalized = " ".join("\n".join([deployment, roadmap, ru_roadmap]).split())

    assert "## Readiness State" in deployment
    assert "## Pre-Proxy Readiness Checklist" in deployment
    assert "## Live Review Summary Gate" in deployment
    assert "## Live Front Door Validation Gate" in deployment
    assert "scripts/audit_owner_raw_live_front_door_review.py" in deployment
    assert "--template-json <raw-free-front-door-review.json>" in deployment
    assert "--require-trino-shared-hardening" in deployment
    assert "raw-free and fail-closed" in deployment
    assert "review_status=unreviewed" in deployment
    assert "A deployment is not ready for shared/non-local raw source access" in normalized
    assert "real TLS/auth, direct-network blocking, real identity claim" in normalized
    assert "Retain only raw-free validation evidence" in normalized
    assert "live owner-raw D3 front-door validation gate" in roadmap
    assert "not a general shared-deploy support claim" in normalized
    assert "Следующий D3 шаг - live validation gate" in ru_roadmap


def test_owner_raw_d3_russian_companions_pin_selective_i18n_and_contract():
    ru_index = (REPO_DIR / "docs" / "i18n" / "ru" / "README.md").read_text(encoding="utf-8")
    ru_config = (REPO_DIR / "docs" / "i18n" / "ru" / "configuration.md").read_text(encoding="utf-8")
    ru_security = (REPO_DIR / "docs" / "i18n" / "ru" / "security-model.md").read_text(
        encoding="utf-8"
    )
    ru_safety = (REPO_DIR / "docs" / "i18n" / "ru" / "safety-contract.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join("\n".join([ru_index, ru_config, ru_security, ru_safety]).split())

    assert "не полное зеркало всего дерева документации" in ru_index
    assert "user-facing и operator-facing документы" in ru_index
    assert "Owner Raw D3 Deployment Contract" in ru_index
    assert "trusted auth front door -> exactly one normalized viewer header" in normalized
    assert "ровно один normalized simple owner value" in normalized
    assert "Query Doctor не реализует native auth modes" in normalized
    assert "OIDC/SSO, SAML, SPNEGO/Kerberos" in normalized
    assert "Collection credential" in normalized
    assert "keytab owner set" in normalized


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
