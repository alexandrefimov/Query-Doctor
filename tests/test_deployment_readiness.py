from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from query_doctor.source_visibility import SOURCE_VISIBILITY_OWNER_RAW
from query_doctor.web.deployment_readiness import (
    deployment_readiness_payload,
    format_deployment_readiness_text,
)
from query_doctor.web.models import WebSettings
from query_doctor.web.routes import route_get_request
from query_doctor.web.jobs import WebJobStore


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_deployment_readiness_payload_is_raw_free() -> None:
    settings = WebSettings(
        config=Path("/private/local/query-doctor-config.json"),
        public_demo=True,
        no_llm=True,
        allow_nonlocal_web_bind=True,
    )

    payload = deployment_readiness_payload(settings)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["kind"] == "query_doctor_deployment_readiness_v1"
    assert payload["mode"] == "public_demo"
    assert payload["web"]["post_actions"] == "disabled"
    assert payload["sources"]["configured_source_count"] == 0
    assert payload["security"]["sql_execution"] is False
    assert "/healthz" in serialized
    assert "/readyz" in serialized
    assert "/private/local" not in serialized
    assert "query-doctor-config.json" not in serialized
    assert "127.0.0.1" not in serialized
    assert "8765" not in serialized
    assert "qwen" not in serialized
    assert "ollama" not in serialized.lower()


def test_deployment_readiness_blocks_owner_raw_nonlocal_without_viewer_identity() -> None:
    settings = WebSettings(
        config=Path("/private/local/query-doctor-config.json"),
        allow_nonlocal_web_bind=True,
        source_visibility=SOURCE_VISIBILITY_OWNER_RAW,
        source_owner_user="secret_owner",
        manual_profile_dir=Path("/private/local/profile-inbox"),
        no_llm=True,
    )

    payload = deployment_readiness_payload(settings)
    serialized = json.dumps(payload, sort_keys=True)
    owner_raw_checks = {
        check["id"]: check["status"] for check in payload["checks"] if isinstance(check, dict)
    }

    assert payload["status"] == "blocked"
    assert payload["security"]["source_visibility"] == SOURCE_VISIBILITY_OWNER_RAW
    assert payload["security"]["viewer_identity_header"] == "not_configured"
    assert owner_raw_checks["owner_raw_front_door"] == "blocked"
    assert "/private/local" not in serialized
    assert "query-doctor-config.json" not in serialized
    assert "profile-inbox" not in serialized
    assert "secret_owner" not in serialized


def test_deployment_readiness_keeps_viewer_header_name_raw_free() -> None:
    settings = WebSettings(
        config=Path("/private/local/query-doctor-config.json"),
        allow_nonlocal_web_bind=True,
        source_visibility=SOURCE_VISIBILITY_OWNER_RAW,
        viewer_identity_header="X-Query-Doctor-Viewer",
        source_owner_user="secret_owner",
        no_llm=True,
    )

    payload = deployment_readiness_payload(settings)
    serialized = json.dumps(payload, sort_keys=True)
    owner_raw_checks = {
        check["id"]: check["status"] for check in payload["checks"] if isinstance(check, dict)
    }

    assert payload["status"] == "warning"
    assert payload["security"]["viewer_identity_header"] == "configured"
    assert owner_raw_checks["owner_raw_front_door"] == "warning"
    assert "X-Query-Doctor-Viewer" not in serialized
    assert "secret_owner" not in serialized
    assert "/private/local" not in serialized


def test_deployment_readiness_text_is_path_free() -> None:
    payload = deployment_readiness_payload(
        WebSettings(config=Path("/tmp/secret-config.json"), public_demo=True, no_llm=True)
    )

    text = format_deployment_readiness_text(payload)

    assert "Query Doctor deployment readiness" in text
    assert "secret-config" not in text
    assert "/tmp" not in text


def test_deployment_readiness_routes_return_raw_free_json_and_html() -> None:
    settings = WebSettings(config=Path("/tmp/secret-config.json"), public_demo=True, no_llm=True)

    json_response = route_get_request(
        "/deployment/readiness.json",
        settings,
        WebJobStore(),
    )
    html_response = route_get_request("/deployment", settings, WebJobStore())

    assert json_response is not None
    assert json_response.content_type.startswith("application/json")
    payload = json.loads(json_response.body)
    assert payload["kind"] == "query_doctor_deployment_readiness_v1"
    assert "/tmp" not in json_response.body
    assert html_response is not None
    assert "Deployment Readiness" in html_response.body
    assert "/deployment/readiness.json" in html_response.body
    assert "/tmp" not in html_response.body


def test_deployment_readiness_cli_public_demo_json_is_raw_free() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "query_doctor.cli.deployment_readiness",
            "--public-demo",
            "--json",
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "query_doctor_deployment_readiness_v1"
    assert payload["mode"] == "public_demo"
    assert payload["security"]["sql_execution"] is False
    assert str(REPO_ROOT) not in result.stdout
    assert "/private/tmp" not in result.stdout
    assert "qwen" not in result.stdout
