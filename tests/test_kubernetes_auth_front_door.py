from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTH_FRONT_DOOR_AUDIT = REPO_ROOT / "scripts" / "audit_kubernetes_auth_front_door.py"
KUBERNETES_SERVICE_DNS_SUFFIX = ".".join(("svc", "cluster", "local"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resource_list(*items: dict[str, Any]) -> dict[str, Any]:
    return {"apiVersion": "v1", "kind": "List", "items": list(items)}


def service(name: str, *, namespace: str = "query-doctor") -> dict[str, Any]:
    selectors = {
        "query-doctor-oauth2-proxy": {
            "app.kubernetes.io/component": "auth-proxy",
            "app.kubernetes.io/name": "query-doctor",
        },
        "query-doctor-full": {
            "app.kubernetes.io/component": "web",
            "app.kubernetes.io/instance": "query-doctor-full",
            "app.kubernetes.io/name": "query-doctor",
        },
    }
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "ports": [{"name": "http", "port": 80, "targetPort": "http"}],
            "selector": selectors.get(name, {}),
        },
    }


def ingress(
    backend_service: str = "query-doctor-oauth2-proxy",
    *,
    namespace: str = "query-doctor",
    host: str = "query-doctor.test",
) -> dict[str, Any]:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {"name": "query-doctor-full", "namespace": namespace},
        "spec": {
            "ingressClassName": "ingress-nginx",
            "tls": [{"hosts": [host], "secretName": "query-doctor-tls"}],
            "rules": [
                {
                    "host": host,
                    "http": {
                        "paths": [
                            {
                                "path": "/",
                                "pathType": "Prefix",
                                "backend": {
                                    "service": {
                                        "name": backend_service,
                                        "port": {"number": 80},
                                    }
                                },
                            }
                        ]
                    },
                }
            ],
        },
    }


def auth_proxy_deployment(
    *,
    namespace: str = "query-doctor",
    host: str = "query-doctor.test",
    secret_literal: bool = False,
    omitted_arg_prefixes: set[str] | None = None,
    trusted_proxy_ip: bool = False,
) -> dict[str, Any]:
    env: list[dict[str, Any]] = [
        {"name": "OAUTH2_PROXY_CLIENT_ID", "value": "query-doctor"},
        {
            "name": "OAUTH2_PROXY_CLIENT_SECRET",
            "valueFrom": {
                "secretKeyRef": {"name": "query-doctor-oauth2-proxy", "key": "client-secret"}
            },
        },
        {
            "name": "OAUTH2_PROXY_COOKIE_SECRET",
            "valueFrom": {
                "secretKeyRef": {"name": "query-doctor-oauth2-proxy", "key": "cookie-secret"}
            },
        },
    ]
    if secret_literal:
        env[1] = {"name": "OAUTH2_PROXY_CLIENT_SECRET", "value": "do-not-commit"}
    omitted = omitted_arg_prefixes or set()
    args = [
        "--provider=keycloak-oidc",
        "--oidc-issuer-url=https://login.test/realms/query-doctor",
        f"--upstream=http://query-doctor-full.query-doctor.{KUBERNETES_SERVICE_DNS_SUFFIX}",
        f"--redirect-url=https://{host}/oauth2/callback",
        "--reverse-proxy=true",
        "--cookie-secure=true",
        "--cookie-httponly=true",
        "--pass-access-token=false",
        "--pass-authorization-header=false",
        "--pass-basic-auth=false",
        "--set-authorization-header=false",
        "--code-challenge-method=S256",
        "--session-cookie-minimal=true",
        "--oidc-groups-claim=query_doctor_groups_disabled",
        "--skip-claims-from-profile-url=true",
    ]
    if trusted_proxy_ip:
        args.append("--trusted-proxy-ip=192.0.2.0/24")
    args = [
        arg
        for arg in args
        if not any(arg == prefix or arg.startswith(prefix + "=") for prefix in omitted)
    ]
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "query-doctor-oauth2-proxy", "namespace": namespace},
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "oauth2-proxy",
                            "image": "oauth2-proxy:test",
                            "args": args,
                            "env": env,
                        }
                    ]
                }
            }
        },
    }


def query_doctor_deployment(namespace: str = "query-doctor") -> dict[str, Any]:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "query-doctor-full", "namespace": namespace},
        "spec": {
            "selector": {
                "matchLabels": {
                    "app.kubernetes.io/component": "web",
                    "app.kubernetes.io/instance": "query-doctor-full",
                    "app.kubernetes.io/name": "query-doctor",
                }
            },
            "template": {
                "metadata": {
                    "labels": {
                        "app.kubernetes.io/component": "web",
                        "app.kubernetes.io/instance": "query-doctor-full",
                        "app.kubernetes.io/name": "query-doctor",
                    }
                },
                "spec": {
                    "containers": [
                        {
                            "name": "web",
                            "image": "query-doctor:test",
                            "ports": [{"name": "http", "containerPort": 8765}],
                        }
                    ]
                },
            },
        },
    }


def network_policy(
    name: str,
    pod_selector: dict[str, str],
    peers: list[dict[str, Any]],
    *,
    namespace: str = "query-doctor",
) -> dict[str, Any]:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "podSelector": {"matchLabels": pod_selector},
            "policyTypes": ["Ingress"],
            "ingress": [{"from": peers, "ports": [{"port": "http", "protocol": "TCP"}]}],
        },
    }


def auth_proxy_network_policy() -> dict[str, Any]:
    return network_policy(
        "query-doctor-auth-proxy-ingress",
        {
            "app.kubernetes.io/component": "auth-proxy",
            "app.kubernetes.io/name": "query-doctor",
        },
        [
            {
                "namespaceSelector": {
                    "matchLabels": {
                        "kubernetes.io/metadata.name": "system-ingress-be",
                    }
                },
                "podSelector": {
                    "matchLabels": {
                        "app.kubernetes.io/component": "controller",
                        "app.kubernetes.io/instance": "ingress-nginx-be",
                        "app.kubernetes.io/name": "ingress-nginx",
                    }
                },
            }
        ],
    )


def query_doctor_network_policy() -> dict[str, Any]:
    return network_policy(
        "query-doctor-full-from-auth-proxy",
        {
            "app.kubernetes.io/component": "web",
            "app.kubernetes.io/instance": "query-doctor-full",
            "app.kubernetes.io/name": "query-doctor",
        },
        [
            {
                "podSelector": {
                    "matchLabels": {
                        "app.kubernetes.io/component": "auth-proxy",
                        "app.kubernetes.io/name": "query-doctor",
                    }
                }
            }
        ],
    )


def readiness_payload() -> dict[str, Any]:
    return {
        "kind": "query_doctor_deployment_readiness_v1",
        "mode": "configured_private",
        "web": {"public_demo": False},
        "security": {"sql_execution": False, "raw_output": False},
    }


def run_audit(
    tmp_path: Path,
    resources: dict[str, Any],
    *,
    readiness: bool = True,
    readiness_payload_value: dict[str, Any] | None = None,
    require_network_policy: bool = False,
    ingress_controller_labels: bool = False,
    expected_keycloak: bool = False,
    expected_issuer_url: str = "https://login.test/realms/query-doctor",
    expected_client_id: str = "query-doctor",
    expected_code_challenge_method: str = "S256",
    require_compact_session_cookie: bool = False,
    expected_groups_claim: str = "query_doctor_groups_disabled",
) -> subprocess.CompletedProcess[str]:
    resources_path = tmp_path / "resources.json"
    summary_path = tmp_path / "summary.json"
    write_json(resources_path, resources)
    args = [
        sys.executable,
        str(AUTH_FRONT_DOOR_AUDIT),
        "--resources-json",
        str(resources_path),
        "--namespace",
        "query-doctor",
        "--query-doctor-service",
        "query-doctor-full",
        "--auth-proxy-service",
        "query-doctor-oauth2-proxy",
        "--expected-host",
        "query-doctor.test",
        "--summary-json",
        str(summary_path),
    ]
    if require_network_policy:
        args.append("--require-network-policy")
    if ingress_controller_labels:
        args.extend(
            [
                "--ingress-controller-namespace-label",
                "kubernetes.io/metadata.name=system-ingress-be",
                "--ingress-controller-pod-label",
                "app.kubernetes.io/component=controller",
                "--ingress-controller-pod-label",
                "app.kubernetes.io/instance=ingress-nginx-be",
                "--ingress-controller-pod-label",
                "app.kubernetes.io/name=ingress-nginx",
            ]
        )
    if expected_keycloak:
        args.extend(
            [
                "--expected-issuer-url",
                expected_issuer_url,
                "--expected-client-id",
                expected_client_id,
                "--expected-code-challenge-method",
                expected_code_challenge_method,
            ]
        )
    if require_compact_session_cookie:
        args.extend(
            [
                "--require-compact-session-cookie",
                "--expected-groups-claim",
                expected_groups_claim,
            ]
        )
    if readiness:
        readiness_path = tmp_path / "readiness.json"
        write_json(readiness_path, readiness_payload_value or readiness_payload())
        args.extend(["--deployment-readiness-json", str(readiness_path)])
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def supported_resources(**kwargs: Any) -> dict[str, Any]:
    resources = [
        ingress(kwargs.get("backend_service", "query-doctor-oauth2-proxy")),
        service("query-doctor-oauth2-proxy"),
        service("query-doctor-full"),
        query_doctor_deployment(),
        auth_proxy_deployment(
            secret_literal=bool(kwargs.get("secret_literal", False)),
            omitted_arg_prefixes=kwargs.get("omitted_arg_prefixes"),
            trusted_proxy_ip=bool(kwargs.get("trusted_proxy_ip", False)),
        ),
    ]
    if kwargs.get("network_policies"):
        resources.extend([auth_proxy_network_policy(), query_doctor_network_policy()])
    return resource_list(*resources)


def test_kubernetes_auth_front_door_audit_accepts_oauth2_proxy_shape(tmp_path: Path) -> None:
    result = run_audit(tmp_path, supported_resources(), expected_keycloak=True)

    assert result.returncode == 0, result.stderr
    assert "kubernetes auth front-door audit: warning" in result.stdout
    assert "auth_proxy_trusted_proxy_ip_missing" in result.stdout
    assert "query-doctor.test" not in result.stdout
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "warning"
    assert summary["checks"]["ingress_uses_auth_proxy"] is True
    assert summary["checks"]["expected_issuer_configured"] is True
    assert summary["checks"]["expected_client_id_configured"] is True
    assert summary["checks"]["expected_code_challenge_method_configured"] is True
    assert summary["checks"]["compact_session_cookie_configured"] is True
    assert summary["checks"]["deployment_readiness"]["valid"] is True
    assert summary["issue_codes"] == []


def test_kubernetes_auth_front_door_audit_rejects_direct_query_doctor_ingress(
    tmp_path: Path,
) -> None:
    result = run_audit(
        tmp_path,
        supported_resources(backend_service="query-doctor-full"),
    )

    assert result.returncode == 1
    assert "ingress_direct_to_query_doctor_service" in result.stdout
    assert "ingress_backend_not_auth_proxy_service" in result.stdout
    assert "query-doctor.test" not in result.stdout


def test_kubernetes_auth_front_door_audit_rejects_literal_client_secret(
    tmp_path: Path,
) -> None:
    result = run_audit(tmp_path, supported_resources(secret_literal=True))

    assert result.returncode == 1
    assert "oauth2_proxy_client_secret_not_secret_ref" in result.stdout
    assert "do-not-commit" not in result.stdout


def test_kubernetes_auth_front_door_audit_requires_pass_basic_auth_false(
    tmp_path: Path,
) -> None:
    result = run_audit(
        tmp_path,
        supported_resources(omitted_arg_prefixes={"--pass-basic-auth"}),
    )

    assert result.returncode == 1
    assert "pass_basic_auth_not_disabled" in result.stdout


def test_kubernetes_auth_front_door_audit_marks_bad_readiness_invalid(
    tmp_path: Path,
) -> None:
    bad_readiness = readiness_payload()
    bad_readiness["web"] = {"public_demo": True}
    result = run_audit(
        tmp_path,
        supported_resources(),
        readiness_payload_value=bad_readiness,
    )

    assert result.returncode == 1
    assert "deployment_readiness_public_demo_enabled" in result.stdout
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["checks"]["deployment_readiness"]["valid"] is False


def test_kubernetes_auth_front_door_audit_accepts_strict_network_policy(
    tmp_path: Path,
) -> None:
    result = run_audit(
        tmp_path,
        supported_resources(network_policies=True, trusted_proxy_ip=True),
        require_network_policy=True,
        ingress_controller_labels=True,
        expected_keycloak=True,
        require_compact_session_cookie=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "kubernetes auth front-door audit: ok" in result.stdout
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "passed"
    assert summary["checks"]["expected_issuer_configured"] is True
    assert summary["checks"]["expected_client_id_configured"] is True
    assert summary["checks"]["expected_code_challenge_method_configured"] is True
    assert summary["checks"]["compact_session_cookie_configured"] is True
    assert summary["checks"]["network_policy"] == {
        "auth_proxy_allows_ingress_controller": True,
        "auth_proxy_isolated": True,
        "query_doctor_allows_auth_proxy": True,
        "query_doctor_isolated": True,
        "supplied": True,
    }


def test_kubernetes_auth_front_door_audit_can_require_network_policy(
    tmp_path: Path,
) -> None:
    result = run_audit(
        tmp_path,
        supported_resources(trusted_proxy_ip=True),
        require_network_policy=True,
        ingress_controller_labels=True,
    )

    assert result.returncode == 1
    assert "network_policy_missing" in result.stdout


def test_kubernetes_auth_front_door_audit_rejects_wrong_expected_keycloak(
    tmp_path: Path,
) -> None:
    result = run_audit(
        tmp_path,
        supported_resources(network_policies=True, trusted_proxy_ip=True),
        require_network_policy=True,
        ingress_controller_labels=True,
        expected_keycloak=True,
        expected_issuer_url="https://wrong-login.test/realms/query-doctor",
        expected_client_id="wrong-client",
        expected_code_challenge_method="plain",
    )

    assert result.returncode == 1
    assert "auth_proxy_expected_issuer_mismatch" in result.stdout
    assert "auth_proxy_expected_client_id_mismatch" in result.stdout
    assert "auth_proxy_expected_code_challenge_method_mismatch" in result.stdout
    assert "wrong-login.test" not in result.stdout
    assert "wrong-client" not in result.stdout
    assert "plain" not in result.stdout


def test_kubernetes_auth_front_door_audit_requires_compact_session_cookie(
    tmp_path: Path,
) -> None:
    result = run_audit(
        tmp_path,
        supported_resources(
            network_policies=True,
            trusted_proxy_ip=True,
            omitted_arg_prefixes={
                "--session-cookie-minimal",
                "--oidc-groups-claim",
                "--skip-claims-from-profile-url",
            },
        ),
        require_network_policy=True,
        ingress_controller_labels=True,
        expected_keycloak=True,
        require_compact_session_cookie=True,
    )

    assert result.returncode == 1
    assert "auth_proxy_session_cookie_minimal_missing" in result.stdout
    assert "auth_proxy_skip_claims_from_profile_url_missing" in result.stdout
    assert "auth_proxy_groups_claim_not_disabled" in result.stdout
