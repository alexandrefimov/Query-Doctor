from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
BUILD_IMAGE = REPO_ROOT / "scripts" / "build-image.sh"
IMAGE_SMOKE = REPO_ROOT / "scripts" / "image-smoke.sh"
BOOTSTRAP_IMPALA_SHELL = REPO_ROOT / "scripts" / "bootstrap-impala-shell"
KUBERNETES_DIR = REPO_ROOT / "deploy" / "kubernetes"
HELM_CHART_DIR = REPO_ROOT / "deploy" / "helm" / "query-doctor"
PUBLIC_DEMO_MANIFEST = KUBERNETES_DIR / "public-demo.yaml"
CONFIGURED_WEB_MANIFEST = KUBERNETES_DIR / "configured-web.yaml"
SELF_TEST_JOB_MANIFEST = KUBERNETES_DIR / "self-test-job.yaml"
KUBERNETES_README = KUBERNETES_DIR / "README.md"
KUBERNETES_AUDIT = REPO_ROOT / "scripts" / "audit_kubernetes_deployment.py"
KUBERNETES_LIVE_SMOKE = REPO_ROOT / "scripts" / "kubernetes-public-demo-smoke.sh"
KUBERNETES_SELF_TEST_SMOKE = REPO_ROOT / "scripts" / "kubernetes-self-test-smoke.sh"
KUBERNETES_METADATA_SMOKE = REPO_ROOT / "scripts" / "kubernetes-configured-metadata-smoke.sh"
KUBERNETES_RELEASE_GATE = REPO_ROOT / "scripts" / "kubernetes-configured-release-gate.sh"
KUBERNETES_KERBEROS_RENEWER_SMOKE = REPO_ROOT / "scripts" / "kubernetes-kerberos-renewer-smoke.sh"
KUBERNETES_ONLINE_HISTORY_SMOKE = REPO_ROOT / "scripts" / "kubernetes-online-history-smoke.sh"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dockerfile_runs_web_as_non_root_public_demo_by_default() -> None:
    text = read(DOCKERFILE)

    assert "ARG QUERY_DOCTOR_PYTHON_BASE_IMAGE=python:3.10-slim" in text
    assert "FROM ${QUERY_DOCTOR_PYTHON_BASE_IMAGE}" in text
    assert "AS impala-shell" in text
    assert "requirements-impala-shell.txt" in text
    assert "scripts/bootstrap-impala-shell" in text
    assert "QD_IMPALA_SHELL=/opt/query-doctor/.venv-impala-shell/bin/impala-shell" in text
    assert "PATH=/opt/query-doctor/.venv-impala-shell/bin:$PATH" not in text
    assert "krb5-user" in text
    assert "libsasl2-2" in text
    assert "libsasl2-modules-gssapi-mit" in text
    assert "ARG QUERY_DOCTOR_INSTALL_EXTRAS" in text
    assert '".[${QUERY_DOCTOR_INSTALL_EXTRAS}]"' in text
    assert "/usr/local/bin/python -m pip install --no-cache-dir --no-deps ." in text
    assert "useradd --uid 10001" in text
    assert "--uid 10001" in text
    assert "--gid 10001" in text
    assert "USER 10001:10001" in text
    assert "EXPOSE 8765" in text
    assert "HEALTHCHECK" in text
    assert "/healthz" in text
    assert 'ENTRYPOINT ["query-doctor-web"]' in text
    assert "--allow-nonlocal-web-bind" in text
    assert "--public-demo" in text
    assert "COPY . " not in text


def test_dockerignore_excludes_local_configs_secrets_and_generated_outputs() -> None:
    text = read(DOCKERIGNORE)

    for required in (
        ".git",
        ".qdcreds",
        ".query-doctor*.json",
        "query-doctor-config*.json",
        "*.keytab",
        "*.env",
        "cases",
        "reports",
        "*.sql",
        "*.log",
    ):
        assert required in text


def test_build_image_script_allows_explicit_platform_for_cluster_smoke() -> None:
    text = read(BUILD_IMAGE)

    assert "QUERY_DOCTOR_IMAGE_PLATFORM" in text
    assert "--platform" in text
    assert "QUERY_DOCTOR_INSTALL_EXTRAS" in text
    assert "--build-arg" in text
    assert "QUERY_DOCTOR_DOCKERFILE" in text
    assert '--file "${dockerfile}"' in text


def test_image_smoke_script_allows_explicit_platform_for_cluster_smoke() -> None:
    text = read(IMAGE_SMOKE)

    assert "QUERY_DOCTOR_IMAGE_PLATFORM" in text
    assert "--platform" in text
    assert "QD_IMPALA_SHELL" in text
    assert "import sasl" in text
    assert "klist" in text
    assert "/deployment/readiness.json" in text
    assert "query_doctor_deployment_readiness_v1" in text
    assert "sql_execution" in text


def test_impala_shell_bootstrap_keeps_isolated_runtime() -> None:
    text = read(BOOTSTRAP_IMPALA_SHELL)

    assert "QD_IMPALA_SHELL_VENV" in text
    assert "requirements-impala-shell.txt" in text


def test_kubernetes_public_demo_manifest_is_safe_by_default() -> None:
    text = read(PUBLIC_DEMO_MANIFEST)

    assert "kind: Deployment" in text
    assert "image: ghcr.io/alexandrefimov/query-doctor:0.11.0" in text
    assert "--public-demo" in text
    assert "--allow-nonlocal-web-bind" in text
    assert "path: /healthz" in text
    assert "path: /readyz" in text
    assert "automountServiceAccountToken: false" in text
    assert "runAsNonRoot: true" in text
    assert "runAsUser: 10001" in text
    assert "runAsGroup: 10001" in text
    assert "allowPrivilegeEscalation: false" in text
    assert "readOnlyRootFilesystem: true" in text
    assert "drop:\n                - ALL" in text
    assert "kind: NetworkPolicy" in text
    assert "egress: []" in text
    assert "kind: Secret" not in text
    assert "ClusterRole" not in text
    assert "RoleBinding" not in text


def test_kubernetes_configured_manifest_uses_external_secret_reference() -> None:
    text = read(CONFIGURED_WEB_MANIFEST)

    assert "kind: Deployment" in text
    assert "kind: ConfigMap" in text
    assert "kind: PersistentVolumeClaim" in text
    assert "kind: Ingress" in text
    assert "image: ghcr.io/alexandrefimov/query-doctor:0.11.0" in text
    assert "--config" in text
    assert "/etc/query-doctor/query-doctor-config.json" in text
    assert "--no-llm" in text
    assert "source_visibility" in text
    assert '"safe"' in text
    assert '"recent_batch_root": "/tmp/query-doctor-web-batches"' in text
    assert "secretRef:" in text
    assert "name: query-doctor-credentials" in text
    assert "kind: Secret" not in text
    assert "path: /healthz" in text
    assert "path: /readyz" in text
    assert "automountServiceAccountToken: false" in text
    assert "runAsNonRoot: true" in text
    assert "runAsUser: 10001" in text
    assert "runAsGroup: 10001" in text
    assert "fsGroup: 10001" in text
    assert "allowPrivilegeEscalation: false" in text
    assert "readOnlyRootFilesystem: true" in text
    assert "memory: 512Mi" in text
    assert "memory: 2Gi" in text
    assert "mountPath: /tmp/query-doctor-web-batches" in text


def test_kubernetes_self_test_job_manifest_is_safe_and_synthetic_only() -> None:
    text = read(SELF_TEST_JOB_MANIFEST)

    assert "kind: Job" in text
    assert "query-doctor-self-test" in text
    assert "--json" in text
    assert "--timeout-sec" in text
    assert "--keep-work-dir" not in text
    assert "--config" not in text
    assert "query-doctor-web" not in text
    assert "kind: Secret" not in text
    assert "secretRef:" not in text
    assert "PersistentVolumeClaim" not in text
    assert "claimName:" not in text
    assert "kind: Service\n" not in text
    assert "kind: Deployment" not in text
    assert "automountServiceAccountToken: false" in text
    assert "restartPolicy: Never" in text
    assert "backoffLimit: 0" in text
    assert "ttlSecondsAfterFinished: 300" in text
    assert "activeDeadlineSeconds: 300" in text
    assert "runAsNonRoot: true" in text
    assert "runAsUser: 10001" in text
    assert "runAsGroup: 10001" in text
    assert "allowPrivilegeEscalation: false" in text
    assert "readOnlyRootFilesystem: true" in text
    assert "drop:\n                - ALL" in text
    assert "kind: NetworkPolicy" in text
    assert "egress: []" in text


def test_kubernetes_docs_pin_support_boundary() -> None:
    text = read(KUBERNETES_README)

    assert "supported Kubernetes starting point" in text
    assert "do not add native" in text
    assert "public-demo.yaml" in text
    assert "configured-web.yaml" in text
    assert "self-test-job.yaml" in text
    assert "synthetic self-test" in text
    assert "/healthz" in text
    assert "/readyz" in text
    assert "trusted ingress or auth proxy" in text
    assert "owner-raw D3" in text
    assert "never executes user SQL" in text
    assert "recentHistory.postgres" in text
    assert "query-doctor-recent-history-postgres-readiness --json" in text


def test_helm_chart_defaults_to_safe_public_demo_web_deployment() -> None:
    chart = read(HELM_CHART_DIR / "Chart.yaml")
    values = read(HELM_CHART_DIR / "values.yaml")
    deployment = read(HELM_CHART_DIR / "templates" / "deployment.yaml")
    network_policy = read(HELM_CHART_DIR / "templates" / "networkpolicy.yaml")
    validation = read(HELM_CHART_DIR / "templates" / "validation.yaml")

    assert "name: query-doctor" in chart
    assert 'appVersion: "0.11.0"' in chart
    assert "mode: publicDemo" in values
    assert "repository: ghcr.io/alexandrefimov/query-doctor" in values
    assert 'tag: "0.11.0"' in values
    assert "memory: 512Mi" in values
    assert "memory: 2Gi" in values
    assert "automountServiceAccountToken: false" in values
    assert "runAsUser: 10001" in values
    assert "runAsGroup: 10001" in values
    assert "readOnlyRootFilesystem: true" in values
    assert "egressMode: denyAll" in values
    assert "kerberos:" in values
    assert "recentHistory:" in values
    assert "recentSummaryCollector:" in values
    assert "recentProfileWorker:" in values
    assert "recentBatchMountPath: /tmp/query-doctor-web-batches" in values
    assert "enabled: false" in values
    assert "selfTestJob:" in values
    assert "query-doctor-self-test" in read(HELM_CHART_DIR / "templates" / "selftest-job.yaml")
    assert "--public-demo" in deployment
    assert "/healthz" in values
    assert "/readyz" in values
    assert "egress: []" in network_policy
    assert "credentials.existingSecret must stay empty in publicDemo mode" in validation
    assert "kerberos.enabled must stay false in publicDemo mode" in validation
    assert (
        "recentHistory.postgres.profileRemediation.enabled must stay false in publicDemo mode"
        in validation
    )
    assert "recentProfileWorker.enabled must stay false in publicDemo mode" in validation
    assert "recentSummaryCollector.enabled must stay false in publicDemo mode" in validation
    assert "config values must stay empty in publicDemo mode" in validation


def test_helm_chart_configured_mode_requires_config_and_persistence() -> None:
    example = read(HELM_CHART_DIR / "examples" / "configured-values.yaml")
    deployment = read(HELM_CHART_DIR / "templates" / "deployment.yaml")
    validation = read(HELM_CHART_DIR / "templates" / "validation.yaml")

    assert "mode: configured" in example
    assert "config:" in example
    assert "inlineJson:" in example
    assert "source_visibility" in example
    assert '"safe"' in example
    assert "existingSecret: query-doctor-credentials" in example
    assert "existingSecret: query-doctor-kerberos" in example
    assert "persistence:" in example
    assert "enabled: true" in example
    assert '"recent_batch_root": "/tmp/query-doctor-web-batches"' in example
    assert '"recent_history_backend": "sqlite"' in example
    assert (
        '"recent_history_db": "/var/lib/query-doctor/recent-history/recent-history.sqlite3"'
        in example
    )
    assert '"recent_history_summary_retention_days": 30' in example
    assert '"recent_profile_analysis_limit": 5000' in example
    assert "recentBatchMountPath: /tmp/query-doctor-web-batches" in example
    assert "ingress:\n  enabled: false" in example
    assert "--config" in deployment
    assert "envFrom:" in deployment
    assert "mountPath: {{ $recentBatchMountPath | quote }}" in deployment
    assert "PersistentVolumeClaim" in read(HELM_CHART_DIR / "templates" / "pvc.yaml")
    assert "configured mode requires config.create=true or config.existingConfigMap" in validation
    assert (
        "configured mode requires persistence.enabled=true or persistence.existingClaim"
        in validation
    )
    assert "persistence.recentBatchMountPath must stay under /tmp/query-doctor-*" in validation
    assert "kind: Secret" not in example
    assert "platform-owned auth front door" in read(HELM_CHART_DIR / "README.md")


def test_helm_chart_supports_postgres_recent_history_secret_env() -> None:
    values = read(HELM_CHART_DIR / "values.yaml")
    schema = read(HELM_CHART_DIR / "values.schema.json")
    deployment = read(HELM_CHART_DIR / "templates" / "deployment.yaml")
    validation = read(HELM_CHART_DIR / "templates" / "validation.yaml")
    smoke = read(REPO_ROOT / "scripts" / "helm-chart-smoke.sh")
    readme = read(HELM_CHART_DIR / "README.md")
    worker = read(HELM_CHART_DIR / "templates" / "recent-profile-worker-cronjob.yaml")
    worker_network_policy = read(
        HELM_CHART_DIR / "templates" / "recent-profile-worker-networkpolicy.yaml"
    )
    retention = read(HELM_CHART_DIR / "templates" / "recent-history-retention-cronjob.yaml")
    retention_network_policy = read(
        HELM_CHART_DIR / "templates" / "recent-history-retention-networkpolicy.yaml"
    )
    remediation = read(HELM_CHART_DIR / "templates" / "recent-profile-remediation-cronjob.yaml")
    remediation_network_policy = read(
        HELM_CHART_DIR / "templates" / "recent-profile-remediation-networkpolicy.yaml"
    )
    operator_readiness = read(
        HELM_CHART_DIR / "templates" / "recent-history-operator-readiness-cronjob.yaml"
    )
    operator_readiness_network_policy = read(
        HELM_CHART_DIR / "templates" / "recent-history-operator-readiness-networkpolicy.yaml"
    )
    operator_readiness_example = read(
        HELM_CHART_DIR / "examples" / "configured-postgres-operator-readiness-values.yaml"
    )

    assert "recentHistory:" in values
    assert "recentProfileWorker:" in values
    assert "dsnEnvName: QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN" in values
    assert "readiness:" in values
    assert "retention:" in values
    assert "profileRemediation:" in values
    assert "operatorReadiness:" in values
    assert 'schedule: "*/5 * * * *"' in values
    assert 'schedule: "*/15 * * * *"' in values
    assert 'schedule: "0 3 * * *"' in values
    assert "query-doctor-profile-worker" in values
    assert "operator-readiness-summary.json" in values
    assert "collector-summary.json" in values
    assert "collector-progress.jsonl" in values
    assert '"recentHistory"' in schema
    assert '"recentSummaryCollector"' in schema
    assert '"recentProfileWorker"' in schema
    assert '"dsnEnvName"' in schema
    assert '"readiness"' in schema
    assert '"retention"' in schema
    assert '"profileRemediation"' in schema
    assert '"operatorReadiness"' in schema
    assert '"summaryJson"' in schema
    assert '"progressJsonl"' in schema
    assert '"summaryRetentionDays"' in schema
    assert '"postgresReadinessSummaryJson"' in schema
    assert '"profileWorkerSummaryJson"' in schema
    assert '"collectorSummaryJson"' in schema
    assert '"profileRemediationSummaryJson"' in schema
    assert '"outputSummaryJson"' in schema
    assert '"maxJobs"' in schema
    assert ".Values.recentHistory | default dict" in deployment
    assert "secretKeyRef:" in deployment
    assert "recent-history-postgres-readiness" in deployment
    assert "query-doctor-recent-history-postgres-readiness" in deployment
    assert "--postgres-dsn-env" in deployment
    assert "postgres-readiness-summary.json" in deployment
    assert "--fail-on-warning" in deployment
    assert "recentHistory.postgres.enabled requires configured mode" in validation
    assert (
        "recentHistory.postgres.enabled requires recentHistory.postgres.existingSecret"
        in validation
    )
    assert "recentHistory.postgres.dsnEnvName must be an uppercase environment" in validation
    assert (
        "recentHistory.postgres.retention.enabled requires recentHistory.postgres.enabled=true"
        in validation
    )
    assert (
        "recentHistory.postgres.retention requires at least one retention day value" in validation
    )
    assert (
        "recentHistory.postgres.profileRemediation.enabled requires recentHistory.postgres.enabled=true"
        in validation
    )
    assert (
        "recentHistory.postgres.profileRemediation.enabled requires recentHistory.operatorReadiness.enabled=true"
        in validation
    )
    assert (
        "recentHistory.postgres.profileRemediation.enabled requires recentHistory.operatorReadiness.profileRemediationSummaryJson"
        in validation
    )
    assert "recentHistory.postgres.profileRemediation.maxJobs must be at least 1" in validation
    assert (
        "recentHistory.operatorReadiness.enabled requires recentHistory.postgres.enabled=true"
        in validation
    )
    assert (
        "recentHistory.operatorReadiness.enabled requires recentProfileWorker.enabled=true"
        in validation
    )
    assert (
        "recentHistory.operatorReadiness.outputSummaryJson must differ from profileWorkerSummaryJson"
        in validation
    )
    assert (
        "recentHistory.operatorReadiness.collectorSummaryJson must stay under persistence.mountPath"
        in validation
    )
    assert (
        "recentHistory.operatorReadiness.outputSummaryJson must differ from collectorSummaryJson"
        in validation
    )
    assert (
        "recentHistory.operatorReadiness.profileRemediationSummaryJson must stay under persistence.mountPath"
        in validation
    )
    assert (
        "recentHistory.operatorReadiness.outputSummaryJson must differ from profileRemediationSummaryJson"
        in validation
    )
    assert (
        "recentSummaryCollector.enabled requires recentHistory.postgres.enabled=true" in validation
    )
    assert "recentSummaryCollector.out must stay under /tmp/query-doctor-*" in validation
    assert "recentSummaryCollector.summaryJson must stay under persistence.mountPath" in validation
    assert (
        "recentSummaryCollector.progressJsonl must stay under persistence.mountPath" in validation
    )
    assert "recentSummaryCollector.progressJsonl must differ from summaryJson" in validation
    assert "recentProfileWorker.enabled requires recentHistory.postgres.enabled=true" in validation
    assert "recentProfileWorker.out must stay under /tmp/query-doctor-*" in validation
    assert "configured-postgres.yaml" in smoke
    assert "configured-postgres-collector.yaml" in smoke
    assert "configured-postgres-worker.yaml" in smoke
    assert "configured-postgres-retention.yaml" in smoke
    assert "configured-postgres-operator-readiness.yaml" in smoke
    assert "QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN" in smoke
    assert "recent-history-postgres-readiness" in smoke
    assert "query-doctor-recent-history-retention" in smoke
    assert "query-doctor-batch-recent" in smoke
    assert "--discover-only" in smoke
    assert "--recent-history-collector-summary-json" in smoke
    assert "--progress-jsonl" in smoke
    assert "invalid-collector-progress" in smoke
    assert "--collector-summary-json" in smoke
    assert "query-doctor-recent-profile-remediation" in smoke
    assert "--dry-run" in smoke
    assert "! grep -q -- '--apply'" in smoke
    assert "query-doctor-recent-profile-worker" in smoke
    assert "query-doctor-recent-history-operator-readiness" in smoke
    assert "kind: CronJob" in retention
    assert "query-doctor-recent-history-retention" in retention
    assert "--summary-json" in retention
    assert "--summary-retention-days" in retention
    assert "--profile-job-retention-days" in retention
    assert "--analysis-cache-retention-days" in retention
    assert "--profile-artifact-retention-days" in retention
    assert "secretKeyRef:" in retention
    assert "envFrom:" not in retention
    assert "recentHistoryRetentionSelectorLabels" in retention_network_policy
    collector = read(HELM_CHART_DIR / "templates" / "recent-summary-collector-cronjob.yaml")
    collector_network_policy = read(
        HELM_CHART_DIR / "templates" / "recent-summary-collector-networkpolicy.yaml"
    )
    assert "kind: CronJob" in collector
    assert "query-doctor-batch-recent" in collector
    assert "--discover-only" in collector
    assert "--metadata-mode" in collector
    assert '"off"' in collector
    assert "--top-reports" in collector
    assert '"0"' in collector
    assert "--recent-history-backend" in collector
    assert "postgres" in collector
    assert "--recent-history-postgres-dsn-env" in collector
    assert "--recent-history-collector-summary-json" in collector
    assert "collector-summary.json" in collector
    assert "--progress-jsonl" in collector
    assert "collector-progress.jsonl" in collector
    assert "--config" in collector
    assert "--out" in collector
    assert "secretKeyRef:" in collector
    assert "envFrom:" in collector
    assert "configMap:" in collector
    assert "persistentVolumeClaim:" in collector
    assert "claimName:" in collector
    assert "query-doctor-recent-profile-worker" not in collector
    assert "query-doctor-recent-profile-remediation" not in collector
    assert "query-doctor-recent-history-operator-readiness" not in collector
    assert "--summary-json" not in collector
    assert "--apply" not in collector
    assert "recentSummaryCollectorSelectorLabels" in collector_network_policy
    assert "kind: CronJob" in remediation
    assert "query-doctor-recent-profile-remediation" in remediation
    assert "--dry-run" in remediation
    assert "--apply" not in remediation
    assert "--summary-json" in remediation
    assert "--backend" in remediation
    assert "postgres" in remediation
    assert "--postgres-dsn-env" in remediation
    assert "--max-jobs" in remediation
    assert "--engine" in remediation
    assert "--source-kind" in remediation
    assert "--source-key" in remediation
    assert "secretKeyRef:" in remediation
    assert "envFrom:" not in remediation
    assert "configMap:" not in remediation
    assert ".Values.config.mountPath" not in remediation
    assert "kerberos" not in remediation.lower()
    assert "recentProfileRemediationSelectorLabels" in remediation_network_policy
    assert "kind: CronJob" in worker
    assert "query-doctor-recent-profile-worker" in worker
    assert "operator-readiness-summary-dir" in worker
    assert "profile-worker-summary.json" in worker
    assert "--fail-on-warning" in worker
    assert "--summary-json" in worker
    assert "--recent-history-backend" in worker
    assert "postgres" in worker
    assert "--metadata-mode" in worker
    assert '"off"' in worker
    assert "--top-reports" in worker
    assert "secretKeyRef:" in worker
    assert "envFrom:" in worker
    assert "recentProfileWorkerSelectorLabels" in worker_network_policy
    assert "kind: CronJob" in operator_readiness
    assert "query-doctor-recent-history-operator-readiness" in operator_readiness
    assert "--postgres-readiness-summary-json" in operator_readiness
    assert "--profile-worker-summary-json" in operator_readiness
    assert "--collector-summary-json" in operator_readiness
    assert "--retention-summary-json" in operator_readiness
    assert "--profile-remediation-summary-json" in operator_readiness
    assert "--summary-json" in operator_readiness
    assert "secretKeyRef:" not in operator_readiness
    assert "envFrom:" not in operator_readiness
    assert "kerberos" not in operator_readiness.lower()
    assert "recentHistoryOperatorReadinessSelectorLabels" in operator_readiness_network_policy
    assert "recent_history_operator_readiness_summary_json" in operator_readiness_example
    assert "recent_history_collector_summary_json" in operator_readiness_example
    assert 'recent_history_backend": "postgres"' in operator_readiness_example
    assert "recentHistory:\n  postgres:" in operator_readiness_example
    assert "recentSummaryCollector:\n  enabled: true" in operator_readiness_example
    assert "progressJsonl" in operator_readiness_example
    assert "operatorReadiness:" in operator_readiness_example
    assert "collectorSummaryJson" in operator_readiness_example
    assert "profileRemediationSummaryJson" in operator_readiness_example
    assert "profileRemediation:\n      enabled: true" in operator_readiness_example
    assert "recentProfileWorker:\n  enabled: true" in operator_readiness_example
    assert "recentHistory.postgres" in readme
    assert "recentProfileWorker.enabled" in readme
    assert "recentSummaryCollector.enabled" in readme
    assert "recentHistory.operatorReadiness.enabled" in readme
    assert "collectorSummaryJson" in readme
    assert "does not accept an inline DSN" in readme
    assert "query-doctor-recent-history-postgres-readiness --json" in readme
    assert "query-doctor-batch-recent --discover-only" in readme
    assert "recent_history_collector_summary_json" in readme
    assert "recentSummaryCollector.progressJsonl" in readme
    assert "query-doctor-recent-history-operator-readiness" in readme
    assert "query-doctor-recent-profile-remediation --json" in readme
    assert "profileRemediationSummaryJson" in readme
    assert "does not contact Postgres, Kubernetes" in readme
    assert "Profile-artifact metadata is `fingerprint_only`" in readme
    assert "kind: Secret" not in deployment
    assert "kind: Secret" not in collector
    assert "kind: Secret" not in worker
    assert "kind: Secret" not in retention
    assert "kind: Secret" not in remediation
    assert "kind: Secret" not in operator_readiness
    assert "kind: Secret" not in operator_readiness_example


def test_helm_chart_supports_cnpg_generated_application_secret() -> None:
    values = read(HELM_CHART_DIR / "values.yaml")
    cluster = read(HELM_CHART_DIR / "templates" / "recent-history-cnpg-cluster.yaml")
    validation = read(HELM_CHART_DIR / "templates" / "validation.yaml")
    smoke = read(REPO_ROOT / "scripts" / "helm-chart-smoke.sh")
    readme = read(HELM_CHART_DIR / "README.md")

    assert "Leave empty to let CNPG create its standard application Secret" in values
    assert '{{- with (get $cnpg "existingOwnerSecret") }}' in cluster
    assert "name: {{ . | quote }}" in cluster
    assert "recentHistory.postgres.cnpg.existingOwnerSecret is required" not in validation
    assert "configured_cnpg_generated_manifest" in smoke
    assert "recentHistory.postgres.existingSecret=query-doctor-history-app" in smoke
    assert "recentHistory.postgres.dsnKey=uri" in smoke
    assert "operator-generated application Secret" in readme


def test_helm_chart_supports_optional_kerberos_ticket_init_and_web_renewal() -> None:
    values = read(HELM_CHART_DIR / "values.yaml")
    schema = read(HELM_CHART_DIR / "values.schema.json")
    deployment = read(HELM_CHART_DIR / "templates" / "deployment.yaml")
    validation = read(HELM_CHART_DIR / "templates" / "validation.yaml")
    smoke = read(REPO_ROOT / "scripts" / "helm-chart-smoke.sh")

    assert "kerberos:" in values
    assert "principalKey: principal" in values
    assert "keytabKey: query-doctor.keytab" in values
    assert "cachePath: /tmp/query-doctor-krb5/krb5cc_query_doctor" in values
    assert "refreshIntervalSeconds: 1800" in values
    assert '"kerberos"' in schema
    assert '"renewer"' in schema
    assert '"refreshIntervalSeconds"' in schema
    assert "kerberos-kinit" in deployment
    assert "kerberos-ticket-renewer" in deployment
    assert ".Values.kerberos | default dict" in deployment
    assert ".Values.kerberos | default dict" in validation
    assert 'default "principal"' in validation
    assert 'default "query-doctor.keytab"' in validation
    assert 'default "/tmp/query-doctor-krb5/krb5cc_query_doctor"' in validation
    assert "kinit -kt" in deployment
    assert 'sleep "$KERBEROS_REFRESH_INTERVAL_SECONDS"' in deployment
    assert "Kerberos credential cache refreshed" in deployment
    assert "Kerberos credential cache refresh failed" in deployment
    assert ">/dev/null 2>&1" in deployment
    assert "KRB5CCNAME" in deployment
    assert "KERBEROS_REFRESH_INTERVAL_SECONDS" in deployment
    assert "kerberos-init-secret" in deployment
    assert "kerberos-config" in deployment
    web_container = deployment.split("- name: web", 1)[1].split(
        "- name: kerberos-ticket-renewer", 1
    )[0]
    assert "kerberos-init-secret" not in web_container
    assert "kind: Secret" not in deployment
    assert "kerberos.enabled requires kerberos.existingSecret" in validation
    assert "kerberos.cachePath must stay under /tmp/query-doctor-krb5/" in validation
    assert "kerberos.renewer.refreshIntervalSeconds must be between 60 and 86400" in validation
    assert "configured-kerberos.yaml" in smoke
    assert "configured-kerberos-no-renewer.yaml" in smoke
    assert "kinit -kt" in smoke
    assert "kerberos-ticket-renewer" in smoke


def test_kubernetes_kerberos_renewer_smoke_is_bounded_and_raw_free() -> None:
    text = read(KUBERNETES_KERBEROS_RENEWER_SMOKE)

    assert "kerberos-ticket-renewer" in text
    assert "KERBEROS_REFRESH_INTERVAL_SECONDS" in text
    assert "klist -s" in text
    assert "stat -c %Y" in text
    assert "max_wait_seconds" in text
    assert "kubectl logs" not in text
    assert "klist -e" not in text
    assert "klist -l" not in text
    assert "cat /etc/query-doctor-kerberos" not in text


def test_kubernetes_online_history_smoke_runs_only_bounded_installed_jobs() -> None:
    text = read(KUBERNETES_ONLINE_HISTORY_SMOKE)

    assert "recent-summary-collector" in text
    assert "recent-profile-worker" in text
    assert "recent-history-operator-readiness" in text
    assert 'create job --from="cronjob/${cronjob}"' in text
    assert "--for=condition=complete" in text
    assert "QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_REQUIRE_SUSPENDED" in text
    assert "CronJobs must be suspended" in text
    assert '"http://${host}:${port}/batch"' in text
    assert "Online History" in text
    assert "operator readiness" in text
    assert "kubectl logs" not in text
    assert "exec" not in text
    assert "SELECT " not in text
    assert "EXPLAIN " not in text


def test_kubernetes_kerberos_renewer_smoke_accepts_synthetic_cache_refresh(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    counter = tmp_path / "mtime-counter"
    _write_executable(
        bin_dir / "kubectl",
        """#!/bin/sh
args="$*"
case "$args" in
  *"rollout status"*) exit 0 ;;
  *"get pod -l"*) printf 'synthetic-pod'; exit 0 ;;
  *"get pod synthetic-pod"*) printf 'web kerberos-ticket-renewer'; exit 0 ;;
  *"get deployment"*) printf '60'; exit 0 ;;
  *"exec "*)
    if [ -f "$FAKE_MTIME_COUNTER" ]; then
      printf '200'
    else
      : > "$FAKE_MTIME_COUNTER"
      printf '100'
    fi
    exit 0
    ;;
esac
exit 1
""",
    )
    _write_executable(bin_dir / "sleep", "#!/bin/sh\nexit 0\n")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FAKE_MTIME_COUNTER": str(counter),
        "QUERY_DOCTOR_K8S_KERBEROS_SMOKE_MAX_WAIT_SECONDS": "120",
    }

    result = subprocess.run(
        [str(KUBERNETES_KERBEROS_RENEWER_SMOKE)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[kubernetes-kerberos-renewer-smoke] ok"


def test_kubernetes_online_history_smoke_accepts_synthetic_installed_cycle(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "kubectl",
        """#!/bin/sh
args="$*"
case "$args" in
  *"rollout status"*) exit 0 ;;
  *"get deployment"*) printf 'candidate-image'; exit 0 ;;
  *"get cronjob"*"suspend"*) printf 'true'; exit 0 ;;
  *"get cronjob"*"args"*) printf '%s' '--collector-summary-json /safe/summary.json'; exit 0 ;;
  *"get cronjob"*"image"*) printf 'candidate-image'; exit 0 ;;
  *"get cronjob"*) exit 0 ;;
  *"create job"*) exit 0 ;;
  *" wait "*) exit 0 ;;
  *"port-forward"*) while true; do /bin/sleep 60; done ;;
  *"delete job"*) exit 0 ;;
esac
exit 1
""",
    )
    _write_executable(
        bin_dir / "curl",
        """#!/bin/sh
printf '%s' '<html>Online History operator readiness history schema operator collector profile worker</html>'
""",
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_EXPECTED_IMAGE": "candidate-image",
    }

    result = subprocess.run(
        [str(KUBERNETES_ONLINE_HISTORY_SMOKE)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[kubernetes-online-history-smoke] ok"


def test_helm_chart_has_no_platform_specific_controller_hooks() -> None:
    values = read(HELM_CHART_DIR / "values.yaml")
    schema = read(HELM_CHART_DIR / "values.schema.json")
    schema_payload = json.loads(schema)
    helpers = read(HELM_CHART_DIR / "templates" / "_helpers.tpl")
    deployment = read(HELM_CHART_DIR / "templates" / "deployment.yaml")
    validation = read(HELM_CHART_DIR / "templates" / "validation.yaml")
    readme = read(HELM_CHART_DIR / "README.md")

    assert "podLabels:" in values
    assert "podAnnotations:" in values
    assert schema_payload["properties"]["podAnnotations"] == {
        "type": "object",
        "additionalProperties": {"type": "string"},
    }
    assert schema_payload["properties"]["podLabels"] == {
        "type": "object",
        "additionalProperties": {"type": "string"},
    }
    assert "app.kubernetes.io/managed-by" in helpers
    assert ".Values.podAnnotations" in deployment
    assert "podLabels must not override selector-owned label" in validation
    assert "platform-neutral" in readme
    assert "controller-specific labels" in readme


def test_helm_chart_renders_safe_synthetic_self_test_hook() -> None:
    values = read(HELM_CHART_DIR / "values.yaml")
    schema = read(HELM_CHART_DIR / "values.schema.json")
    self_test_job = read(HELM_CHART_DIR / "templates" / "selftest-job.yaml")
    self_test_network_policy = read(HELM_CHART_DIR / "templates" / "selftest-networkpolicy.yaml")
    notes = read(HELM_CHART_DIR / "templates" / "NOTES.txt")
    helpers = read(HELM_CHART_DIR / "templates" / "_helpers.tpl")
    readme = read(HELM_CHART_DIR / "README.md")

    assert "selfTestJob:" in values
    assert "enabled: true" in values
    assert "timeoutSeconds: 120" in values
    assert '"selfTestJob"' in schema
    assert '"timeoutSeconds"' in schema
    assert '"minimum": 1' in schema
    assert "query-doctor.selfTestSelectorLabels" in helpers
    assert "query-doctor.selfTestLabels" in helpers
    assert '"helm.sh/hook": test' in self_test_job
    assert '"helm.sh/hook-delete-policy": before-hook-creation' in self_test_job
    assert "hook-succeeded" not in self_test_job
    assert "kind: Job" in self_test_job
    assert "command:" in self_test_job
    assert "query-doctor-self-test" in self_test_job
    assert "--json" in self_test_job
    assert "--timeout-sec" in self_test_job
    assert "--keep-work-dir" not in self_test_job
    assert "--config" not in self_test_job
    assert "envFrom:" not in self_test_job
    assert "secretRef:" not in self_test_job
    assert "persistentVolumeClaim" not in self_test_job
    assert "restartPolicy: Never" in self_test_job
    assert "automountServiceAccountToken: false" in self_test_job
    assert "containerSecurityContext" in self_test_job
    assert "readOnlyRootFilesystem: true" in values
    assert "kind: NetworkPolicy" in self_test_network_policy
    assert "egress: []" in self_test_network_policy
    assert "helm test" in readme
    assert "helm test" in notes
    assert "kubectl -n {{ .Release.Namespace }} logs job/" in notes
    assert "/deployment/readiness.json" in notes
    assert "arbitrary command" in notes
    assert "not an arbitrary command runner" in readme


def test_kubernetes_audit_accepts_supported_raw_manifests() -> None:
    for manifest, mode in (
        (PUBLIC_DEMO_MANIFEST, "public-demo"),
        (CONFIGURED_WEB_MANIFEST, "configured"),
    ):
        result = subprocess.run(
            [
                sys.executable,
                str(KUBERNETES_AUDIT),
                "--manifest",
                str(manifest),
                "--mode",
                mode,
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "kubernetes deployment audit: ok" in result.stdout
        assert str(manifest) not in result.stdout


def test_kubernetes_audit_accepts_self_test_job_manifest() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(KUBERNETES_AUDIT),
            "--manifest",
            str(SELF_TEST_JOB_MANIFEST),
            "--mode",
            "self-test-job",
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "kubernetes deployment audit: ok" in result.stdout
    assert "mode=self-test-job" in result.stdout
    assert str(SELF_TEST_JOB_MANIFEST) not in result.stdout


def test_kubernetes_audit_rejects_secret_rendering(tmp_path: Path) -> None:
    unsafe = tmp_path / "unsafe.yaml"
    unsafe.write_text(
        "\n".join(
            [
                "apiVersion: v1",
                "kind: Secret",
                "metadata:",
                "  name: query-doctor-secret",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(KUBERNETES_AUDIT),
            "--manifest",
            str(unsafe),
            "--mode",
            "public-demo",
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 1
    assert "forbidden_secret_or_rbac_kind" in result.stdout
    assert str(unsafe) not in result.stdout


def test_kubernetes_audit_rejects_underprovisioned_configured_web(tmp_path: Path) -> None:
    unsafe = tmp_path / "configured-underprovisioned.yaml"
    unsafe.write_text(
        read(CONFIGURED_WEB_MANIFEST)
        .replace("memory: 512Mi", "memory: 256Mi")
        .replace("memory: 2Gi", "memory: 1Gi"),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(KUBERNETES_AUDIT),
            "--manifest",
            str(unsafe),
            "--mode",
            "configured",
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 1
    assert "configured_memory_request_too_small" in result.stdout
    assert "configured_memory_limit_too_small" in result.stdout
    assert str(unsafe) not in result.stdout


def test_kubernetes_live_smoke_allows_pre_release_image_override() -> None:
    text = read(KUBERNETES_LIVE_SMOKE)

    assert "QUERY_DOCTOR_K8S_SMOKE_IMAGE_REPOSITORY" in text
    assert "QUERY_DOCTOR_K8S_SMOKE_IMAGE_TAG" in text
    assert "QUERY_DOCTOR_K8S_SMOKE_IMAGE_DIGEST" in text
    assert "QUERY_DOCTOR_K8S_SMOKE_IMAGE_PULL_POLICY" in text
    assert '--set-string "image.repository=${image_repository}"' in text
    assert '--set-string "image.tag=${image_tag}"' in text


def test_kubernetes_configured_metadata_smoke_is_aggregate_only() -> None:
    text = read(KUBERNETES_METADATA_SMOKE)

    assert "QUERY_DOCTOR_K8S_METADATA_SMOKE_NAMESPACE" in text
    assert "QUERY_DOCTOR_K8S_METADATA_SMOKE_RELEASE" in text
    assert "rollout status" in text
    assert "port-forward" in text
    assert "/batch/run" in text
    assert "metadata_top_limit" in text
    assert "QD_IMPALA_SHELL" in text
    assert "import sasl" in text
    assert "klist_valid" in text
    assert "metadata_status_counts" in text
    assert "metadata_cases_with_table_context" in text
    assert "metadata_tables_collected" in text
    assert "publish_latest_summary" in text
    assert "partial" in text
    assert "table_metadata_facts" in text
    assert "job_id_shape" in text
    assert "print(job_id" not in text
    assert "query_id" not in text
    assert "case_id" not in text
    assert "case_dir" not in text


def test_kubernetes_configured_release_gate_composes_safe_live_checks() -> None:
    text = read(KUBERNETES_RELEASE_GATE)

    assert "QUERY_DOCTOR_K8S_RELEASE_GATE_EXTERNAL_URL" in text
    assert "QUERY_DOCTOR_K8S_RELEASE_GATE_EXPECTED_ISSUER_URL" in text
    assert "QUERY_DOCTOR_K8S_RELEASE_GATE_EXPECTED_CLIENT_ID" in text
    assert "QUERY_DOCTOR_K8S_RELEASE_GATE_EXPECTED_HOST" in text
    assert "scripts/kubernetes-configured-metadata-smoke.sh" in text
    assert "scripts/kubernetes_auth_front_door_smoke.py" in text
    assert "scripts/audit_kubernetes_auth_front_door.py" in text
    assert "deployment/readiness.json" in text
    assert "--require-compact-session-cookie" in text
    assert "--require-network-policy" in text
    assert "QUERY_DOCTOR_K8S_RELEASE_GATE_INGRESS_CONTROLLER_NAMESPACE_LABELS" in text
    assert "QUERY_DOCTOR_K8S_RELEASE_GATE_INGRESS_CONTROLLER_POD_LABELS" in text


def test_kubernetes_self_test_smoke_runs_helm_test_without_live_diagnostics() -> None:
    text = read(KUBERNETES_SELF_TEST_SMOKE)

    assert "helm test" in text
    assert "kubectl logs" in text
    assert "--logs" not in text
    assert "QUERY_DOCTOR_K8S_SELF_TEST_IMAGE_REPOSITORY" in text
    assert "QUERY_DOCTOR_K8S_SELF_TEST_IMAGE_TAG" in text
    assert "QUERY_DOCTOR_K8S_SELF_TEST_IMAGE_DIGEST" in text
    assert "QUERY_DOCTOR_K8S_SELF_TEST_IMAGE_PULL_POLICY" in text
    assert "kubectl exec" not in text
    assert "query-doctor-web-recent" not in text
    assert "query-doctor-optimize-query" not in text
    assert "--config" not in text
    assert "CM_PASSWORD" not in text


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
