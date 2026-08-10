#!/usr/bin/env python3
"""Raw-free audit for Query Doctor Kubernetes auth-front-door wiring."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SUMMARY_KIND = "query_doctor_kubernetes_auth_front_door_audit_v1"
DEFAULT_CALLBACK_PATH = "/oauth2/callback"
KUBERNETES_SERVICE_DNS_SUFFIX = ".".join(("svc", "cluster", "local"))
SECRET_ENV_NAMES = {
    "OAUTH2_PROXY_CLIENT_SECRET",
    "OAUTH2_PROXY_COOKIE_SECRET",
}
FALSE_DEFAULT_FORWARDING_FLAGS = {
    "--pass-access-token",
    "--pass-authorization-header",
    "--set-authorization-header",
    "--set-basic-auth",
}
TRUE_DEFAULT_FORWARDING_FLAGS = {
    "--pass-basic-auth",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resources-json",
        required=True,
        type=Path,
        help=(
            "JSON from `kubectl get ingress,deploy,svc -n <namespace> -o json`. "
            "Do not include Secret objects."
        ),
    )
    parser.add_argument("--namespace", default="", help="Expected Kubernetes namespace.")
    parser.add_argument(
        "--query-doctor-service",
        required=True,
        help="Expected Query Doctor web Service name.",
    )
    parser.add_argument(
        "--auth-proxy-service",
        required=True,
        help="Expected auth-proxy Service name used by Ingress backends.",
    )
    parser.add_argument(
        "--auth-proxy-deployment",
        default="",
        help="Auth-proxy Deployment name. Defaults to --auth-proxy-service.",
    )
    parser.add_argument(
        "--expected-host",
        default="",
        help="Optional expected Ingress host. The value is checked but never printed.",
    )
    parser.add_argument(
        "--expected-issuer-url",
        default="",
        help="Optional expected OIDC issuer URL. The value is checked but never printed.",
    )
    parser.add_argument(
        "--expected-client-id",
        default="",
        help="Optional expected OIDC client ID. The value is checked but never printed.",
    )
    parser.add_argument(
        "--expected-code-challenge-method",
        default="",
        help="Optional expected OIDC PKCE code challenge method.",
    )
    parser.add_argument(
        "--require-compact-session-cookie",
        action="store_true",
        help=(
            "Fail unless oauth2-proxy avoids storing tokens and large group/profile "
            "claims in cookie-backed sessions."
        ),
    )
    parser.add_argument(
        "--expected-groups-claim",
        default="",
        help=(
            "Optional expected OIDC groups claim name for oauth2-proxy. "
            "Use an intentionally absent claim when Query Doctor does not need groups."
        ),
    )
    parser.add_argument(
        "--callback-path",
        default=DEFAULT_CALLBACK_PATH,
        help=f"Expected OAuth callback path. Default: {DEFAULT_CALLBACK_PATH}.",
    )
    parser.add_argument(
        "--deployment-readiness-json",
        type=Path,
        help="Optional raw-free /deployment/readiness.json payload.",
    )
    parser.add_argument(
        "--require-network-policy",
        action="store_true",
        help="Fail when NetworkPolicy front-door isolation is missing or incomplete.",
    )
    parser.add_argument(
        "--ingress-controller-namespace-label",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Expected namespaceSelector label for the trusted ingress controller. "
            "May be passed multiple times. Values are checked but never printed."
        ),
    )
    parser.add_argument(
        "--ingress-controller-pod-label",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Expected podSelector label for the trusted ingress controller. "
            "May be passed multiple times. Values are checked but never printed."
        ),
    )
    parser.add_argument(
        "--require-deployment-readiness",
        action="store_true",
        help="Fail if --deployment-readiness-json is omitted.",
    )
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit non-zero when non-blocking warnings are present.",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resource_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [item for item in payload["items"] if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def resource_kind(item: dict[str, Any]) -> str:
    return str(item.get("kind") or "")


def resource_name(item: dict[str, Any]) -> str:
    metadata = item.get("metadata")
    return str(metadata.get("name") or "") if isinstance(metadata, dict) else ""


def resource_namespace(item: dict[str, Any]) -> str:
    metadata = item.get("metadata")
    return str(metadata.get("namespace") or "") if isinstance(metadata, dict) else ""


def parse_label_args(values: list[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for value in values:
        key, separator, label_value = value.partition("=")
        key = key.strip()
        label_value = label_value.strip()
        if not separator or not key or not label_value:
            raise ValueError("label arguments must use KEY=VALUE")
        labels[key] = label_value
    return labels


def add_issue(issues: list[str], condition: bool, code: str) -> None:
    if not condition:
        issues.append(code)


def add_policy_finding(
    issues: list[str],
    warnings: list[str],
    condition: bool,
    code: str,
    *,
    required: bool,
) -> None:
    if condition:
        return
    if required:
        issues.append(code)
    else:
        warnings.append(code)


def find_resource(
    items: list[dict[str, Any]], kind: str, name: str, namespace: str = ""
) -> dict[str, Any] | None:
    for item in items:
        if resource_kind(item) != kind:
            continue
        if name and resource_name(item) != name:
            continue
        if namespace and resource_namespace(item) not in {"", namespace}:
            continue
        return item
    return None


def resources_by_kind(
    items: list[dict[str, Any]], kind: str, namespace: str = ""
) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if resource_kind(item) == kind
        and (not namespace or resource_namespace(item) in {"", namespace})
    ]


def ingress_hosts_and_backends(ingresses: list[dict[str, Any]]) -> tuple[set[str], list[str]]:
    hosts: set[str] = set()
    backends: list[str] = []
    for ingress in ingresses:
        spec = ingress.get("spec") if isinstance(ingress.get("spec"), dict) else {}
        for rule in spec.get("rules") or []:
            if not isinstance(rule, dict):
                continue
            host = str(rule.get("host") or "").strip()
            if host:
                hosts.add(host)
            http = rule.get("http") if isinstance(rule.get("http"), dict) else {}
            for path in http.get("paths") or []:
                if not isinstance(path, dict):
                    continue
                backend = path.get("backend") if isinstance(path.get("backend"), dict) else {}
                service = backend.get("service") if isinstance(backend.get("service"), dict) else {}
                service_name = str(service.get("name") or "").strip()
                if service_name:
                    backends.append(service_name)
    return hosts, backends


def ingress_tls_hosts(ingresses: list[dict[str, Any]]) -> set[str]:
    hosts: set[str] = set()
    for ingress in ingresses:
        spec = ingress.get("spec") if isinstance(ingress.get("spec"), dict) else {}
        for tls in spec.get("tls") or []:
            if not isinstance(tls, dict):
                continue
            for host in tls.get("hosts") or []:
                text = str(host or "").strip()
                if text:
                    hosts.add(text)
    return hosts


def first_container(deployment: dict[str, Any] | None) -> dict[str, Any]:
    if not deployment:
        return {}
    spec = deployment.get("spec") if isinstance(deployment.get("spec"), dict) else {}
    template = spec.get("template") if isinstance(spec.get("template"), dict) else {}
    pod_spec = template.get("spec") if isinstance(template.get("spec"), dict) else {}
    containers = pod_spec.get("containers")
    if isinstance(containers, list) and containers and isinstance(containers[0], dict):
        return containers[0]
    return {}


def deployment_selector_labels(deployment: dict[str, Any] | None) -> dict[str, str]:
    if not deployment:
        return {}
    spec = deployment.get("spec") if isinstance(deployment.get("spec"), dict) else {}
    selector = spec.get("selector") if isinstance(spec.get("selector"), dict) else {}
    match_labels = selector.get("matchLabels")
    if not isinstance(match_labels, dict):
        return {}
    return {str(key): str(value) for key, value in match_labels.items() if str(key) and str(value)}


def service_selector_labels(service: dict[str, Any] | None) -> dict[str, str]:
    if not service:
        return {}
    spec = service.get("spec") if isinstance(service.get("spec"), dict) else {}
    selector = spec.get("selector")
    if not isinstance(selector, dict):
        return {}
    return {str(key): str(value) for key, value in selector.items() if str(key) and str(value)}


def container_port_tokens(deployment: dict[str, Any] | None) -> set[str]:
    container = first_container(deployment)
    ports = container.get("ports")
    tokens: set[str] = set()
    if not isinstance(ports, list):
        return tokens
    for port in ports:
        if not isinstance(port, dict):
            continue
        name = str(port.get("name") or "").strip()
        if name:
            tokens.add(name)
        container_port = port.get("containerPort")
        if isinstance(container_port, int):
            tokens.add(str(container_port))
    return tokens


def arg_value(args: list[str], flag: str) -> str:
    prefix = flag + "="
    for arg in args:
        if arg == flag:
            return "true"
        if arg.startswith(prefix):
            return arg[len(prefix) :]
    return ""


def flag_effectively_false(args: list[str], flag: str, *, default: bool) -> bool:
    value = arg_value(args, flag).strip().lower()
    if not value:
        return default is False
    return value == "false"


def flag_effectively_true(args: list[str], flag: str, *, default: bool) -> bool:
    value = arg_value(args, flag).strip().lower()
    if not value:
        return default is True
    return value == "true"


def env_entries(container: dict[str, Any]) -> list[dict[str, Any]]:
    env = container.get("env")
    return [entry for entry in env if isinstance(entry, dict)] if isinstance(env, list) else []


def has_secret_env_from(container: dict[str, Any]) -> bool:
    env_from = container.get("envFrom")
    if not isinstance(env_from, list):
        return False
    return any(
        isinstance(entry, dict) and isinstance(entry.get("secretRef"), dict) for entry in env_from
    )


def secret_env_state(container: dict[str, Any], name: str) -> str:
    for entry in env_entries(container):
        if str(entry.get("name") or "") != name:
            continue
        if "value" in entry:
            return "literal"
        value_from = entry.get("valueFrom") if isinstance(entry.get("valueFrom"), dict) else {}
        secret_ref = (
            value_from.get("secretKeyRef")
            if isinstance(value_from.get("secretKeyRef"), dict)
            else {}
        )
        if secret_ref.get("name") and secret_ref.get("key"):
            return "secret_ref"
        return "invalid_ref"
    return "secret_env_from" if has_secret_env_from(container) else "missing"


def env_literal_value(container: dict[str, Any], name: str) -> str:
    for entry in env_entries(container):
        if str(entry.get("name") or "") != name:
            continue
        value = entry.get("value")
        return str(value) if isinstance(value, str) else ""
    return ""


def service_hostname_matches(hostname: str, service: str, namespace: str) -> bool:
    hostname = hostname.strip().rstrip(".")
    allowed = {service}
    if namespace:
        allowed.update(
            {
                f"{service}.{namespace}",
                f"{service}.{namespace}.svc",
                f"{service}.{namespace}.{KUBERNETES_SERVICE_DNS_SUFFIX}",
            }
        )
    return hostname in allowed


def selector_match_labels(selector: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(selector, dict):
        return {}
    match_labels = selector.get("matchLabels")
    if not isinstance(match_labels, dict):
        return {}
    return {str(key): str(value) for key, value in match_labels.items() if str(key) and str(value)}


def labels_cover(labels: dict[str, str], expected: dict[str, str]) -> bool:
    return all(labels.get(key) == value for key, value in expected.items())


def selector_selects_labels(selector: dict[str, Any] | None, labels: dict[str, str]) -> bool:
    if not labels:
        return False
    selector_labels = selector_match_labels(selector)
    return labels_cover(labels, selector_labels)


def policy_selects_labels(policy: dict[str, Any], labels: dict[str, str]) -> bool:
    spec = policy.get("spec") if isinstance(policy.get("spec"), dict) else {}
    selector = spec.get("podSelector") if isinstance(spec.get("podSelector"), dict) else {}
    return selector_selects_labels(selector, labels)


def policy_has_ingress_isolation(policy: dict[str, Any]) -> bool:
    spec = policy.get("spec") if isinstance(policy.get("spec"), dict) else {}
    policy_types = spec.get("policyTypes")
    if isinstance(policy_types, list) and any(str(item) == "Ingress" for item in policy_types):
        return True
    return "ingress" in spec


def policy_ingress_rules(policy: dict[str, Any]) -> list[dict[str, Any]]:
    spec = policy.get("spec") if isinstance(policy.get("spec"), dict) else {}
    ingress = spec.get("ingress")
    return [rule for rule in ingress if isinstance(rule, dict)] if isinstance(ingress, list) else []


def rule_allows_port(rule: dict[str, Any], tokens: set[str]) -> bool:
    ports = rule.get("ports")
    if not isinstance(ports, list) or not ports:
        return True
    for port in ports:
        if not isinstance(port, dict):
            continue
        value = port.get("port")
        if isinstance(value, int) and str(value) in tokens:
            return True
        if isinstance(value, str) and value in tokens:
            return True
    return False


def peer_matches_labels(
    peer: dict[str, Any],
    *,
    namespace_labels: dict[str, str],
    pod_labels: dict[str, str],
) -> bool:
    if namespace_labels:
        namespace_selector = peer.get("namespaceSelector")
        if not labels_cover(selector_match_labels(namespace_selector), namespace_labels):
            return False
    if pod_labels:
        pod_selector = peer.get("podSelector")
        if not labels_cover(selector_match_labels(pod_selector), pod_labels):
            return False
    return bool(namespace_labels or pod_labels)


def rule_allows_peer(
    rule: dict[str, Any],
    *,
    namespace_labels: dict[str, str],
    pod_labels: dict[str, str],
    target_port_tokens: set[str],
) -> bool:
    if not rule_allows_port(rule, target_port_tokens):
        return False
    peers = rule.get("from")
    if not isinstance(peers, list):
        return False
    return any(
        isinstance(peer, dict)
        and peer_matches_labels(
            peer,
            namespace_labels=namespace_labels,
            pod_labels=pod_labels,
        )
        for peer in peers
    )


def network_policy_state(
    policies: list[dict[str, Any]],
    *,
    auth_proxy_labels: dict[str, str],
    auth_proxy_port_tokens: set[str],
    query_doctor_labels: dict[str, str],
    query_doctor_port_tokens: set[str],
    ingress_namespace_labels: dict[str, str],
    ingress_pod_labels: dict[str, str],
) -> dict[str, bool]:
    auth_proxy_policies = [
        policy
        for policy in policies
        if policy_selects_labels(policy, auth_proxy_labels) and policy_has_ingress_isolation(policy)
    ]
    query_doctor_policies = [
        policy
        for policy in policies
        if policy_selects_labels(policy, query_doctor_labels)
        and policy_has_ingress_isolation(policy)
    ]
    auth_proxy_allows_ingress = any(
        rule_allows_peer(
            rule,
            namespace_labels=ingress_namespace_labels,
            pod_labels=ingress_pod_labels,
            target_port_tokens=auth_proxy_port_tokens,
        )
        for policy in auth_proxy_policies
        for rule in policy_ingress_rules(policy)
    )
    query_doctor_allows_auth_proxy = any(
        rule_allows_peer(
            rule,
            namespace_labels={},
            pod_labels=auth_proxy_labels,
            target_port_tokens=query_doctor_port_tokens,
        )
        for policy in query_doctor_policies
        for rule in policy_ingress_rules(policy)
    )
    return {
        "supplied": bool(policies),
        "auth_proxy_isolated": bool(auth_proxy_policies),
        "auth_proxy_allows_ingress_controller": auth_proxy_allows_ingress,
        "query_doctor_isolated": bool(query_doctor_policies),
        "query_doctor_allows_auth_proxy": query_doctor_allows_auth_proxy,
    }


def audit_deployment_readiness(payload: Any, issues: list[str]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        issues.append("deployment_readiness_invalid_json")
        return {"supplied": True, "valid": False}
    issue_count_before = len(issues)
    add_issue(
        issues,
        payload.get("kind") == "query_doctor_deployment_readiness_v1",
        "deployment_readiness_kind_invalid",
    )
    add_issue(
        issues,
        payload.get("mode") == "configured_private",
        "deployment_readiness_not_configured_private",
    )
    web = payload.get("web") if isinstance(payload.get("web"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    add_issue(
        issues,
        web.get("public_demo") is False,
        "deployment_readiness_public_demo_enabled",
    )
    add_issue(
        issues,
        security.get("sql_execution") is False,
        "deployment_readiness_sql_execution_enabled",
    )
    add_issue(
        issues,
        security.get("raw_output") is False,
        "deployment_readiness_raw_output_enabled",
    )
    return {"supplied": True, "valid": len(issues) == issue_count_before}


def audit_resources(
    payload: Any,
    *,
    namespace: str,
    query_doctor_service: str,
    auth_proxy_service: str,
    auth_proxy_deployment: str,
    expected_host: str,
    expected_issuer_url: str,
    expected_client_id: str,
    expected_code_challenge_method: str,
    require_compact_session_cookie: bool,
    expected_groups_claim: str,
    callback_path: str,
    deployment_readiness: Any | None,
    require_deployment_readiness: bool,
    require_network_policy: bool,
    ingress_controller_namespace_labels: dict[str, str],
    ingress_controller_pod_labels: dict[str, str],
) -> dict[str, Any]:
    items = resource_items(payload)
    issues: list[str] = []
    warnings: list[str] = []

    add_issue(issues, bool(items), "resource_list_empty")
    add_issue(
        issues,
        not any(resource_kind(item) == "Secret" for item in items),
        "secret_objects_in_input",
    )

    ingresses = resources_by_kind(items, "Ingress", namespace)
    hosts, backends = ingress_hosts_and_backends(ingresses)
    tls_hosts = ingress_tls_hosts(ingresses)
    add_issue(issues, bool(ingresses), "ingress_missing")
    add_issue(issues, bool(hosts), "ingress_host_missing")
    if expected_host:
        add_issue(issues, expected_host in hosts, "ingress_expected_host_missing")
        add_issue(issues, expected_host in tls_hosts, "ingress_expected_tls_host_missing")
    else:
        add_issue(issues, bool(hosts & tls_hosts), "ingress_tls_host_missing")
    add_issue(
        issues,
        query_doctor_service not in backends,
        "ingress_direct_to_query_doctor_service",
    )
    add_issue(
        issues,
        auth_proxy_service in backends,
        "ingress_backend_not_auth_proxy_service",
    )

    auth_proxy_service_resource = find_resource(items, "Service", auth_proxy_service, namespace)
    query_doctor_service_resource = find_resource(items, "Service", query_doctor_service, namespace)
    add_issue(
        issues,
        auth_proxy_service_resource is not None,
        "auth_proxy_service_missing",
    )
    add_issue(
        issues,
        query_doctor_service_resource is not None,
        "query_doctor_service_missing",
    )
    deployment = find_resource(items, "Deployment", auth_proxy_deployment, namespace)
    add_issue(issues, deployment is not None, "auth_proxy_deployment_missing")
    container = first_container(deployment)
    args = [str(arg) for arg in container.get("args") or []]
    query_doctor_deployment = find_resource(items, "Deployment", query_doctor_service, namespace)

    add_issue(issues, bool(arg_value(args, "--provider")), "auth_proxy_provider_missing")
    issuer_url = arg_value(args, "--oidc-issuer-url")
    add_issue(
        issues,
        bool(issuer_url),
        "auth_proxy_oidc_issuer_missing",
    )
    if expected_issuer_url:
        add_issue(
            issues,
            issuer_url == expected_issuer_url,
            "auth_proxy_expected_issuer_mismatch",
        )
    client_id = env_literal_value(container, "OAUTH2_PROXY_CLIENT_ID")
    add_issue(issues, bool(client_id), "auth_proxy_client_id_missing")
    if expected_client_id:
        add_issue(
            issues,
            client_id == expected_client_id,
            "auth_proxy_expected_client_id_mismatch",
        )
    code_challenge_method = arg_value(args, "--code-challenge-method")
    if expected_code_challenge_method:
        add_issue(
            issues,
            code_challenge_method == expected_code_challenge_method,
            "auth_proxy_expected_code_challenge_method_mismatch",
        )
    groups_claim = arg_value(args, "--oidc-groups-claim")
    if expected_groups_claim:
        add_issue(
            issues,
            groups_claim == expected_groups_claim,
            "auth_proxy_expected_groups_claim_mismatch",
        )
    if require_compact_session_cookie:
        add_issue(
            issues,
            flag_effectively_true(args, "--session-cookie-minimal", default=False),
            "auth_proxy_session_cookie_minimal_missing",
        )
        add_issue(
            issues,
            flag_effectively_true(args, "--skip-claims-from-profile-url", default=False),
            "auth_proxy_skip_claims_from_profile_url_missing",
        )
        add_issue(
            issues,
            bool(groups_claim) and groups_claim != "groups",
            "auth_proxy_groups_claim_not_disabled",
        )
    redirect_url = arg_value(args, "--redirect-url")
    add_issue(issues, bool(redirect_url), "auth_proxy_redirect_url_missing")
    if redirect_url:
        parsed = urlparse(redirect_url)
        add_issue(issues, parsed.scheme == "https", "auth_proxy_redirect_not_https")
        add_issue(
            issues,
            parsed.path == callback_path,
            "auth_proxy_redirect_path_mismatch",
        )
        allowed_hosts = {expected_host} if expected_host else hosts
        add_issue(
            issues,
            parsed.hostname in allowed_hosts,
            "auth_proxy_redirect_host_mismatch",
        )
    upstream_url = arg_value(args, "--upstream")
    add_issue(issues, bool(upstream_url), "auth_proxy_upstream_missing")
    if upstream_url:
        parsed = urlparse(upstream_url)
        add_issue(
            issues,
            service_hostname_matches(parsed.hostname or "", query_doctor_service, namespace),
            "auth_proxy_upstream_service_mismatch",
        )
    add_issue(
        issues,
        arg_value(args, "--cookie-secure").strip().lower() == "true",
        "auth_proxy_cookie_secure_missing",
    )
    add_issue(
        issues,
        arg_value(args, "--cookie-httponly").strip().lower() == "true",
        "auth_proxy_cookie_httponly_missing",
    )
    for flag in sorted(FALSE_DEFAULT_FORWARDING_FLAGS):
        add_issue(
            issues,
            flag_effectively_false(args, flag, default=False),
            f"{flag[2:].replace('-', '_')}_not_disabled",
        )
    for flag in sorted(TRUE_DEFAULT_FORWARDING_FLAGS):
        add_issue(
            issues,
            flag_effectively_false(args, flag, default=True),
            f"{flag[2:].replace('-', '_')}_not_disabled",
        )
    for name in sorted(SECRET_ENV_NAMES):
        state = secret_env_state(container, name)
        add_issue(
            issues,
            state in {"secret_ref", "secret_env_from"},
            f"{name.lower()}_not_secret_ref",
        )
        if state == "secret_env_from":
            warnings.append(f"{name.lower()}_secret_key_unverified")
    if arg_value(args, "--reverse-proxy").strip().lower() == "true" and not arg_value(
        args, "--trusted-proxy-ip"
    ):
        warnings.append("auth_proxy_trusted_proxy_ip_missing")

    readiness_state = {"supplied": False, "valid": False}
    if deployment_readiness is None:
        if require_deployment_readiness:
            issues.append("deployment_readiness_missing")
        else:
            warnings.append("deployment_readiness_not_supplied")
    else:
        readiness_state = audit_deployment_readiness(deployment_readiness, issues)

    network_policies = resources_by_kind(items, "NetworkPolicy", namespace)
    auth_proxy_labels = deployment_selector_labels(deployment) or service_selector_labels(
        auth_proxy_service_resource
    )
    query_doctor_labels = service_selector_labels(
        query_doctor_service_resource
    ) or deployment_selector_labels(query_doctor_deployment)
    network_policy = network_policy_state(
        network_policies,
        auth_proxy_labels=auth_proxy_labels,
        auth_proxy_port_tokens=container_port_tokens(deployment) or {"http"},
        query_doctor_labels=query_doctor_labels,
        query_doctor_port_tokens=container_port_tokens(query_doctor_deployment) or {"http"},
        ingress_namespace_labels=ingress_controller_namespace_labels,
        ingress_pod_labels=ingress_controller_pod_labels,
    )
    add_policy_finding(
        issues,
        warnings,
        network_policy["supplied"],
        "network_policy_missing",
        required=require_network_policy,
    )
    if network_policy["supplied"]:
        add_policy_finding(
            issues,
            warnings,
            network_policy["auth_proxy_isolated"],
            "auth_proxy_network_policy_missing",
            required=require_network_policy,
        )
        add_policy_finding(
            issues,
            warnings,
            bool(ingress_controller_namespace_labels or ingress_controller_pod_labels),
            "ingress_controller_labels_missing",
            required=require_network_policy,
        )
        add_policy_finding(
            issues,
            warnings,
            network_policy["auth_proxy_allows_ingress_controller"],
            "auth_proxy_network_policy_ingress_controller_missing",
            required=require_network_policy,
        )
        add_policy_finding(
            issues,
            warnings,
            network_policy["query_doctor_isolated"],
            "query_doctor_network_policy_missing",
            required=require_network_policy,
        )
        add_policy_finding(
            issues,
            warnings,
            network_policy["query_doctor_allows_auth_proxy"],
            "query_doctor_network_policy_auth_proxy_missing",
            required=require_network_policy,
        )

    status = "passed" if not issues and not warnings else "warning" if not issues else "failed"
    return {
        "kind": SUMMARY_KIND,
        "status": status,
        "resource_counts": {
            "deployments": len(resources_by_kind(items, "Deployment", namespace)),
            "ingresses": len(ingresses),
            "services": len(resources_by_kind(items, "Service", namespace)),
        },
        "checks": {
            "ingress_uses_auth_proxy": auth_proxy_service in backends
            and query_doctor_service not in backends,
            "auth_proxy_upstream_configured": bool(upstream_url),
            "expected_issuer_configured": bool(expected_issuer_url)
            and issuer_url == expected_issuer_url,
            "expected_client_id_configured": bool(expected_client_id)
            and client_id == expected_client_id,
            "expected_code_challenge_method_configured": bool(expected_code_challenge_method)
            and code_challenge_method == expected_code_challenge_method,
            "compact_session_cookie_configured": (
                flag_effectively_true(args, "--session-cookie-minimal", default=False)
                and flag_effectively_true(args, "--skip-claims-from-profile-url", default=False)
                and bool(groups_claim)
                and groups_claim != "groups"
                and (not expected_groups_claim or groups_claim == expected_groups_claim)
            ),
            "deployment_readiness": readiness_state,
            "network_policy": network_policy,
        },
        "issue_codes": issues,
        "warning_codes": warnings,
    }


def main() -> int:
    args = parse_args()
    try:
        ingress_controller_namespace_labels = parse_label_args(
            args.ingress_controller_namespace_label
        )
        ingress_controller_pod_labels = parse_label_args(args.ingress_controller_pod_label)
    except ValueError as exc:
        print(f"kubernetes auth front-door audit: failed issues={exc}", file=sys.stderr)
        return 2
    resources = load_json(args.resources_json)
    readiness = (
        load_json(args.deployment_readiness_json) if args.deployment_readiness_json else None
    )
    summary = audit_resources(
        resources,
        namespace=args.namespace,
        query_doctor_service=args.query_doctor_service,
        auth_proxy_service=args.auth_proxy_service,
        auth_proxy_deployment=args.auth_proxy_deployment or args.auth_proxy_service,
        expected_host=args.expected_host,
        expected_issuer_url=args.expected_issuer_url,
        expected_client_id=args.expected_client_id,
        expected_code_challenge_method=args.expected_code_challenge_method,
        require_compact_session_cookie=args.require_compact_session_cookie,
        expected_groups_claim=args.expected_groups_claim,
        callback_path=args.callback_path,
        deployment_readiness=readiness,
        require_deployment_readiness=args.require_deployment_readiness,
        require_network_policy=args.require_network_policy,
        ingress_controller_namespace_labels=ingress_controller_namespace_labels,
        ingress_controller_pod_labels=ingress_controller_pod_labels,
    )
    if args.summary_json:
        args.summary_json.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    status = str(summary["status"])
    if status == "passed":
        print("kubernetes auth front-door audit: ok")
        return 0
    if status == "warning":
        print(
            "kubernetes auth front-door audit: warning "
            f"warnings={','.join(summary['warning_codes'])}"
        )
        return 1 if args.fail_on_warning else 0
    print(f"kubernetes auth front-door audit: failed issues={','.join(summary['issue_codes'])}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
