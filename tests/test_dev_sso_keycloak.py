import json
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[1]
DEV_SSO_DIR = REPO_DIR / "dev" / "sso"


def read_text(path: str) -> str:
    return (DEV_SSO_DIR / path).read_text(encoding="utf-8")


def test_dev_sso_realm_import_pins_synthetic_oidc_client_and_users():
    realm = json.loads(read_text("keycloak/realm-query-doctor-dev.json"))

    assert realm["realm"] == "query-doctor-dev"
    assert realm["enabled"] is True

    clients = {client["clientId"]: client for client in realm["clients"]}
    client = clients["query-doctor-dev"]
    assert client["publicClient"] is False
    assert client["standardFlowEnabled"] is True
    assert client["directAccessGrantsEnabled"] is False
    assert client["serviceAccountsEnabled"] is False
    assert client["redirectUris"] == ["http://query-doctor-sso.localhost:4180/oauth2/callback"]
    assert client["webOrigins"] == ["http://query-doctor-sso.localhost:4180"]
    assert client["secret"] == "query-doctor-dev-client-secret"
    assert client["attributes"]["pkce.code.challenge.method"] == "S256"
    assert any(
        mapper["protocolMapper"] == "oidc-audience-mapper"
        and mapper["config"]["included.client.audience"] == "query-doctor-dev"
        for mapper in client["protocolMappers"]
    )

    users = {user["username"]: user for user in realm["users"]}
    assert set(users) == {"analyst_one", "other_owner"}
    for user in users.values():
        assert user["enabled"] is True
        assert user["emailVerified"] is True
        assert user["email"].endswith("@example.com")
        assert user["credentials"][0]["type"] == "password"
        assert user["credentials"][0]["temporary"] is False


def test_dev_sso_oauth2_proxy_config_preserves_query_doctor_header_contract():
    config = read_text("oauth2-proxy/oauth2-proxy.cfg")

    assert 'provider = "keycloak-oidc"' in config
    assert 'client_id = "query-doctor-dev"' in config
    assert 'redirect_url = "http://query-doctor-sso.localhost:4180/oauth2/callback"' in config
    assert (
        'oidc_issuer_url = "http://query-doctor-sso.localhost:18080/realms/query-doctor-dev"'
        in config
    )
    assert "skip_oidc_discovery = true" in config
    assert (
        'login_url = "http://query-doctor-sso.localhost:18080/realms/query-doctor-dev/protocol/openid-connect/auth"'
        in config
    )
    assert (
        'redeem_url = "http://keycloak:8080/realms/query-doctor-dev/protocol/openid-connect/token"'
        in config
    )
    assert (
        'oidc_jwks_url = "http://keycloak:8080/realms/query-doctor-dev/protocol/openid-connect/certs"'
        in config
    )
    assert 'upstreams = [ "http://query-doctor:8765" ]' in config

    assert "pass_user_headers = true" in config
    assert "prefer_email_to_user = false" in config
    assert "skip_auth_strip_headers = true" in config
    assert "pass_access_token = false" in config
    assert "pass_authorization_header = false" in config
    assert "set_authorization_header = false" in config
    assert "set_xauthrequest = false" in config
    assert "pass_basic_auth = false" in config
    assert "set_basic_auth = false" in config
    assert "show_debug_on_error = false" in config


def test_dev_sso_query_doctor_config_keeps_owner_raw_source_disabled():
    config = json.loads(read_text("query-doctor-dev-sso.config.example.json"))

    assert config["source_visibility"] == "owner_raw"
    assert config["viewer_identity_header"] == "X-Forwarded-Preferred-Username"
    assert config["owner_raw_source_enabled"] is False
    assert config["no_llm"] is True
    assert config["privacy_mode"] is True
    assert config["redact"] is True
    assert config["redact_identifiers"] is True
    assert config["redact_hosts"] is True


def test_dev_sso_compose_keeps_query_doctor_upstream_private():
    compose = read_text("compose.yaml")

    assert "quay.io/keycloak/keycloak:26.6.3" in compose
    assert "quay.io/oauth2-proxy/oauth2-proxy:v7.15.3" in compose
    assert "python:3.12-slim" in compose
    assert "127.0.0.1:${QD_SSO_KEYCLOAK_PORT:-18080}:8080" in compose
    assert "127.0.0.1:${QD_SSO_PROXY_PORT:-4180}:4180" in compose
    assert "python -m query_doctor.cli.demo_data" in compose
    assert "/tmp/query-doctor-dev-sso-demo/batch_summary.json" in compose
    assert "/workspace/dev/sso/query-doctor-dev-sso.config.example.json" in compose
    assert "--disable-owner-raw-source" in compose
    assert "8765:8765" not in compose


def test_dev_sso_docs_are_indexed_and_warn_against_production_claims():
    doc = (REPO_DIR / "docs" / "dev-sso-keycloak.md").read_text(encoding="utf-8")
    docs_index = (REPO_DIR / "docs" / "README.md").read_text(encoding="utf-8")
    deployment = (REPO_DIR / "docs" / "owner-raw-d3-deployment.md").read_text(encoding="utf-8")
    test_matrix = (REPO_DIR / "docs" / "test-matrix.md").read_text(encoding="utf-8")
    readme = (REPO_DIR / "README.md").read_text(encoding="utf-8")

    assert "developer-only SSO front-door smoke" in doc
    assert "not production SSO support" in doc
    assert "does not implement native OIDC" in doc
    assert "owner_raw_source_enabled=false" in doc
    assert "X-Forwarded-Preferred-Username" in doc
    assert "does not forward access tokens, ID tokens, Basic auth" in doc
    assert "docker compose -f dev/sso/compose.yaml up --pull missing" in doc
    assert "Do not use this dev compose file as production evidence" in doc

    assert "[dev-sso-keycloak.md](dev-sso-keycloak.md)" in docs_index
    assert "Dev Keycloak SSO Smoke" in docs_index
    assert "dev/sso/compose.yaml" in deployment
    assert "dev-sso-keycloak.md" in test_matrix
    assert "tests/test_dev_sso_keycloak*.py" in test_matrix
    assert "dev-only Keycloak/oauth2-proxy smoke" in readme
