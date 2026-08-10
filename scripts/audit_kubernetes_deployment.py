#!/usr/bin/env python3
"""Static raw-free audit for Query Doctor Kubernetes manifests."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


FORBIDDEN_KINDS = {
    "ClusterRole",
    "ClusterRoleBinding",
    "Role",
    "RoleBinding",
    "Secret",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--mode",
        required=True,
        choices=["public-demo", "configured", "self-test-job"],
    )
    parser.add_argument("--summary-json", type=Path)
    return parser.parse_args()


def split_documents(text: str) -> list[str]:
    return [doc.strip() for doc in re.split(r"(?m)^---\s*$", text) if doc.strip()]


def kind_of(document: str) -> str:
    match = re.search(r"(?m)^kind:\s*([A-Za-z0-9]+)\s*$", document)
    return match.group(1) if match else ""


def documents_with_kind(documents: list[str], kind: str) -> list[str]:
    return [document for document in documents if kind_of(document) == kind]


def has_line(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.MULTILINE) is not None


def add_issue(issues: list[str], condition: bool, code: str) -> None:
    if not condition:
        issues.append(code)


def audit(text: str, mode: str) -> dict[str, object]:
    documents = split_documents(text)
    kinds = [kind_of(doc) for doc in documents]
    rendered_forbidden = sorted({kind for kind in kinds if kind in FORBIDDEN_KINDS})
    issues: list[str] = []

    add_issue(issues, "ServiceAccount" in kinds, "missing_service_account")
    add_issue(issues, not rendered_forbidden, "forbidden_secret_or_rbac_kind")
    add_issue(
        issues, "automountServiceAccountToken: false" in text, "service_account_token_not_disabled"
    )
    add_issue(issues, "runAsNonRoot: true" in text, "run_as_non_root_missing")
    add_issue(issues, "runAsUser: 10001" in text, "run_as_user_missing")
    add_issue(issues, "runAsGroup: 10001" in text, "run_as_group_missing")
    add_issue(
        issues, "allowPrivilegeEscalation: false" in text, "privilege_escalation_not_disabled"
    )
    add_issue(issues, "readOnlyRootFilesystem: true" in text, "readonly_root_missing")
    add_issue(issues, has_line(text, r"^\s*-\s*ALL\s*$"), "capabilities_drop_all_missing")

    if mode in {"public-demo", "configured"}:
        add_issue(issues, "Deployment" in kinds, "missing_deployment")
        add_issue(issues, "Service" in kinds, "missing_service")
        add_issue(issues, "/healthz" in text, "healthz_probe_missing")
        add_issue(issues, "/readyz" in text, "readyz_probe_missing")
        add_issue(issues, "--allow-nonlocal-web-bind" in text, "nonlocal_bind_ack_missing")

    if mode == "public-demo":
        add_issue(issues, "--public-demo" in text, "public_demo_arg_missing")
        add_issue(issues, "secretRef:" not in text, "public_demo_references_secret")
        add_issue(issues, "PersistentVolumeClaim" not in kinds, "public_demo_renders_pvc")
        add_issue(issues, "NetworkPolicy" in kinds, "public_demo_network_policy_missing")
        add_issue(issues, "egress: []" in text, "public_demo_egress_not_denied")
    elif mode == "configured":
        deployment_text = "\n".join(documents_with_kind(documents, "Deployment"))
        add_issue(issues, "--config" in text, "configured_config_arg_missing")
        add_issue(issues, "secretRef:" in text, "configured_secret_ref_missing")
        add_issue(
            issues,
            "PersistentVolumeClaim" in kinds or "claimName:" in text,
            "configured_persistence_missing",
        )
        add_issue(issues, "source_visibility" in text, "configured_source_visibility_missing")
        add_issue(
            issues, '"safe"' in text or "'safe'" in text, "configured_safe_visibility_missing"
        )
        add_issue(
            issues,
            "memory: 512Mi" in deployment_text,
            "configured_memory_request_too_small",
        )
        add_issue(
            issues,
            "memory: 2Gi" in deployment_text,
            "configured_memory_limit_too_small",
        )
    else:
        add_issue(issues, "Job" in kinds, "self_test_job_missing")
        add_issue(issues, "Deployment" not in kinds, "self_test_renders_deployment")
        add_issue(issues, "Service" not in kinds, "self_test_renders_service")
        add_issue(issues, "Ingress" not in kinds, "self_test_renders_ingress")
        add_issue(issues, "ConfigMap" not in kinds, "self_test_renders_configmap")
        add_issue(issues, "PersistentVolumeClaim" not in kinds, "self_test_renders_pvc")
        add_issue(issues, "NetworkPolicy" in kinds, "self_test_network_policy_missing")
        add_issue(issues, "egress: []" in text, "self_test_egress_not_denied")
        add_issue(issues, "query-doctor-self-test" in text, "self_test_command_missing")
        add_issue(issues, "--json" in text, "self_test_json_arg_missing")
        add_issue(issues, "--timeout-sec" in text, "self_test_timeout_arg_missing")
        add_issue(issues, "--keep-work-dir" not in text, "self_test_keep_work_dir_enabled")
        add_issue(issues, "--config" not in text, "self_test_config_arg_present")
        add_issue(issues, "secretRef:" not in text, "self_test_references_secret")
        add_issue(issues, "claimName:" not in text, "self_test_references_pvc")
        add_issue(issues, "restartPolicy: Never" in text, "self_test_restart_policy_missing")
        add_issue(issues, "backoffLimit: 0" in text, "self_test_backoff_limit_not_zero")
        add_issue(
            issues,
            "ttlSecondsAfterFinished:" in text,
            "self_test_ttl_seconds_missing",
        )
        add_issue(
            issues,
            "activeDeadlineSeconds:" in text,
            "self_test_active_deadline_missing",
        )

    return {
        "kind": "query_doctor_kubernetes_deployment_audit_v1",
        "status": "passed" if not issues else "failed",
        "mode": mode,
        "document_count": len(documents),
        "resource_kinds": sorted({kind for kind in kinds if kind}),
        "issue_codes": issues,
    }


def main() -> int:
    args = parse_args()
    text = args.manifest.read_text(encoding="utf-8")
    summary = audit(text, args.mode)
    if args.summary_json:
        args.summary_json.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if summary["status"] == "passed":
        print(
            "kubernetes deployment audit: ok "
            f"mode={summary['mode']} documents={summary['document_count']}"
        )
        return 0
    print(
        "kubernetes deployment audit: failed "
        f"mode={summary['mode']} issues={','.join(summary['issue_codes'])}"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
