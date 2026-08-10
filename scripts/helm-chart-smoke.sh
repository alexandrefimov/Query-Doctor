#!/usr/bin/env bash
set -euo pipefail

chart_dir="${1:-deploy/helm/query-doctor}"
tmp_dir="${TMPDIR:-/tmp}/query-doctor-helm-smoke-$$"
mkdir -p "${tmp_dir}"
cleanup() {
  rm -rf "${tmp_dir}"
}
trap cleanup EXIT

public_manifest="${tmp_dir}/public-demo.yaml"
configured_manifest="${tmp_dir}/configured.yaml"
configured_kerberos_manifest="${tmp_dir}/configured-kerberos.yaml"
configured_kerberos_no_renewer_manifest="${tmp_dir}/configured-kerberos-no-renewer.yaml"
configured_postgres_manifest="${tmp_dir}/configured-postgres.yaml"
configured_postgres_collector_manifest="${tmp_dir}/configured-postgres-collector.yaml"
configured_postgres_worker_manifest="${tmp_dir}/configured-postgres-worker.yaml"
configured_postgres_retention_manifest="${tmp_dir}/configured-postgres-retention.yaml"
configured_postgres_operator_readiness_manifest="${tmp_dir}/configured-postgres-operator-readiness.yaml"
invalid_collector_progress_err="${tmp_dir}/invalid-collector-progress.err"
invalid_pod_labels_err="${tmp_dir}/invalid-pod-labels.err"
configured_cnpg_manifest="${tmp_dir}/configured-cnpg.yaml"
configured_cnpg_generated_manifest="${tmp_dir}/configured-cnpg-generated.yaml"
configured_cnpg_generated_cluster="${tmp_dir}/configured-cnpg-generated-cluster.yaml"
self_test_manifest="${tmp_dir}/self-test-job.yaml"

helm lint "${chart_dir}"
helm template query-doctor "${chart_dir}" --namespace query-doctor >"${public_manifest}"
helm template query-doctor "${chart_dir}" \
  --namespace query-doctor \
  -f "${chart_dir}/examples/configured-values.yaml" >"${configured_manifest}"
if helm template query-doctor "${chart_dir}" \
  --namespace query-doctor \
  --set-string 'podLabels.app\.kubernetes\.io/name=override' \
  >"${tmp_dir}/invalid-pod-labels.yaml" 2>"${invalid_pod_labels_err}"; then
  echo "[helm-chart-smoke] expected selector-owned podLabels validation failure" >&2
  exit 1
fi
grep -q 'podLabels must not override selector-owned label app.kubernetes.io/name' \
  "${invalid_pod_labels_err}"
helm template query-doctor "${chart_dir}" \
  --namespace query-doctor \
  -f "${chart_dir}/examples/configured-values.yaml" \
  --set kerberos.enabled=true >"${configured_kerberos_manifest}"
helm template query-doctor "${chart_dir}" \
  --namespace query-doctor \
  -f "${chart_dir}/examples/configured-values.yaml" \
  --set kerberos.enabled=true \
  --set kerberos.renewer.enabled=false >"${configured_kerberos_no_renewer_manifest}"
helm template query-doctor "${chart_dir}" \
  --namespace query-doctor \
  -f "${chart_dir}/examples/configured-values.yaml" \
  --set recentHistory.postgres.enabled=true \
  --set-string recentHistory.postgres.existingSecret=query-doctor-recent-history-postgres \
  --set-string recentHistory.postgres.dsnKey=dsn \
  --set-string recentHistory.postgres.dsnEnvName=QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN >"${configured_postgres_manifest}"
helm template query-doctor "${chart_dir}" \
  --namespace query-doctor \
  -f "${chart_dir}/examples/configured-values.yaml" \
  --set recentHistory.postgres.enabled=true \
  --set-string recentHistory.postgres.existingSecret=query-doctor-recent-history-postgres \
  --set-string recentHistory.postgres.dsnKey=dsn \
  --set-string recentHistory.postgres.dsnEnvName=QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN \
  --set recentSummaryCollector.enabled=true >"${configured_postgres_collector_manifest}"
helm template query-doctor "${chart_dir}" \
  --namespace query-doctor \
  -f "${chart_dir}/examples/configured-values.yaml" \
  --set recentHistory.postgres.enabled=true \
  --set-string recentHistory.postgres.existingSecret=query-doctor-recent-history-postgres \
  --set-string recentHistory.postgres.dsnKey=dsn \
  --set-string recentHistory.postgres.dsnEnvName=QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN \
  --set recentProfileWorker.enabled=true >"${configured_postgres_worker_manifest}"
helm template query-doctor "${chart_dir}" \
  --namespace query-doctor \
  -f "${chart_dir}/examples/configured-values.yaml" \
  --set recentHistory.postgres.enabled=true \
  --set-string recentHistory.postgres.existingSecret=query-doctor-recent-history-postgres \
  --set-string recentHistory.postgres.dsnKey=dsn \
  --set-string recentHistory.postgres.dsnEnvName=QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN \
  --set recentHistory.postgres.retention.enabled=true \
  --set recentHistory.postgres.retention.summaryRetentionDays=30 \
  --set recentHistory.postgres.retention.profileJobRetentionDays=14 \
  --set recentHistory.postgres.retention.analysisCacheRetentionDays=45 \
  --set recentHistory.postgres.retention.profileArtifactRetentionDays=60 >"${configured_postgres_retention_manifest}"
helm template query-doctor "${chart_dir}" \
  --namespace query-doctor \
  -f "${chart_dir}/examples/configured-postgres-operator-readiness-values.yaml" >"${configured_postgres_operator_readiness_manifest}"
if helm template query-doctor "${chart_dir}" \
  --namespace query-doctor \
  -f "${chart_dir}/examples/configured-values.yaml" \
  --set recentHistory.postgres.enabled=true \
  --set-string recentHistory.postgres.existingSecret=query-doctor-recent-history-postgres \
  --set-string recentHistory.postgres.dsnKey=dsn \
  --set recentSummaryCollector.enabled=true \
  --set-string recentSummaryCollector.progressJsonl=/var/lib/query-doctor/recent-history/collector-summary.json \
  >"${tmp_dir}/invalid-collector-progress.yaml" 2>"${invalid_collector_progress_err}"; then
  echo "[helm-chart-smoke] expected recentSummaryCollector.progressJsonl validation failure" >&2
  exit 1
fi
grep -q 'recentSummaryCollector.progressJsonl must differ from summaryJson' "${invalid_collector_progress_err}"
helm template query-doctor "${chart_dir}" \
  --namespace query-doctor \
  -f "${chart_dir}/examples/configured-values.yaml" \
  --set recentHistory.postgres.enabled=true \
  --set-string recentHistory.postgres.existingSecret=query-doctor-recent-history-postgres \
  --set recentHistory.postgres.cnpg.enabled=true \
  --set-string recentHistory.postgres.cnpg.existingOwnerSecret=query-doctor-recent-history-owner \
  --set-string recentHistory.postgres.cnpg.name=query-doctor-history \
  --set-string recentHistory.postgres.cnpg.storage.size=20Gi >"${configured_cnpg_manifest}"
helm template query-doctor "${chart_dir}" \
  --namespace query-doctor \
  -f "${chart_dir}/examples/configured-values.yaml" \
  --set recentHistory.postgres.enabled=true \
  --set-string recentHistory.postgres.existingSecret=query-doctor-history-app \
  --set-string recentHistory.postgres.dsnKey=uri \
  --set recentHistory.postgres.cnpg.enabled=true \
  --set-string recentHistory.postgres.cnpg.name=query-doctor-history \
  --set-string recentHistory.postgres.cnpg.storage.size=20Gi >"${configured_cnpg_generated_manifest}"
helm template query-doctor "${chart_dir}" \
  --namespace query-doctor \
  -f "${chart_dir}/examples/configured-values.yaml" \
  --set recentHistory.postgres.enabled=true \
  --set-string recentHistory.postgres.existingSecret=query-doctor-history-app \
  --set-string recentHistory.postgres.dsnKey=uri \
  --set recentHistory.postgres.cnpg.enabled=true \
  --set-string recentHistory.postgres.cnpg.name=query-doctor-history \
  --show-only templates/recent-history-cnpg-cluster.yaml >"${configured_cnpg_generated_cluster}"
helm template query-doctor "${chart_dir}" \
  --namespace query-doctor \
  --show-only templates/serviceaccount.yaml \
  --show-only templates/selftest-job.yaml \
  --show-only templates/selftest-networkpolicy.yaml >"${self_test_manifest}"

python3 scripts/audit_kubernetes_deployment.py --manifest "${public_manifest}" --mode public-demo
python3 scripts/audit_kubernetes_deployment.py --manifest "${configured_manifest}" --mode configured
python3 scripts/audit_kubernetes_deployment.py --manifest "${configured_kerberos_manifest}" --mode configured
python3 scripts/audit_kubernetes_deployment.py --manifest "${configured_kerberos_no_renewer_manifest}" --mode configured
python3 scripts/audit_kubernetes_deployment.py --manifest "${configured_postgres_manifest}" --mode configured
python3 scripts/audit_kubernetes_deployment.py --manifest "${configured_postgres_collector_manifest}" --mode configured
python3 scripts/audit_kubernetes_deployment.py --manifest "${configured_postgres_worker_manifest}" --mode configured
python3 scripts/audit_kubernetes_deployment.py --manifest "${configured_postgres_retention_manifest}" --mode configured
python3 scripts/audit_kubernetes_deployment.py --manifest "${configured_postgres_operator_readiness_manifest}" --mode configured
python3 scripts/audit_kubernetes_deployment.py --manifest "${configured_cnpg_manifest}" --mode configured
python3 scripts/audit_kubernetes_deployment.py --manifest "${configured_cnpg_generated_manifest}" --mode configured
python3 scripts/audit_kubernetes_deployment.py --manifest "${self_test_manifest}" --mode self-test-job
grep -q 'name: kerberos-kinit' "${configured_kerberos_manifest}"
grep -q 'name: kerberos-ticket-renewer' "${configured_kerberos_manifest}"
grep -q 'name: KRB5CCNAME' "${configured_kerberos_manifest}"
grep -q 'name: KERBEROS_REFRESH_INTERVAL_SECONDS' "${configured_kerberos_manifest}"
grep -q 'kinit -kt' "${configured_kerberos_manifest}"
! grep -q '^kind: Secret$' "${configured_kerberos_manifest}"
grep -q 'name: kerberos-kinit' "${configured_kerberos_no_renewer_manifest}"
! grep -q 'name: kerberos-ticket-renewer' "${configured_kerberos_no_renewer_manifest}"
grep -q 'QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN' "${configured_postgres_manifest}"
grep -q 'secretKeyRef:' "${configured_postgres_manifest}"
grep -q 'name: recent-history-postgres-readiness' "${configured_postgres_manifest}"
grep -q 'query-doctor-recent-history-postgres-readiness' "${configured_postgres_manifest}"
grep -q -- '--fail-on-warning' "${configured_postgres_manifest}"
! grep -q '^kind: Secret$' "${configured_postgres_manifest}"
grep -q '^kind: CronJob$' "${configured_postgres_collector_manifest}"
grep -q 'query-doctor-batch-recent' "${configured_postgres_collector_manifest}"
grep -q -- '--discover-only' "${configured_postgres_collector_manifest}"
grep -q -- '--metadata-mode' "${configured_postgres_collector_manifest}"
grep -q -- '--top-reports' "${configured_postgres_collector_manifest}"
grep -q -- '--recent-history-backend' "${configured_postgres_collector_manifest}"
grep -q -- '--recent-history-postgres-dsn-env' "${configured_postgres_collector_manifest}"
grep -q -- '--recent-history-collector-summary-json' "${configured_postgres_collector_manifest}"
grep -q 'collector-summary.json' "${configured_postgres_collector_manifest}"
grep -q -- '--progress-jsonl' "${configured_postgres_collector_manifest}"
grep -q 'collector-progress.jsonl' "${configured_postgres_collector_manifest}"
grep -q 'secretKeyRef:' "${configured_postgres_collector_manifest}"
grep -q 'envFrom:' "${configured_postgres_collector_manifest}"
grep -q 'configMap:' "${configured_postgres_collector_manifest}"
grep -q 'persistentVolumeClaim:' "${configured_postgres_collector_manifest}"
! grep -q 'query-doctor-recent-profile-worker' "${configured_postgres_collector_manifest}"
! grep -q 'query-doctor-recent-profile-remediation' "${configured_postgres_collector_manifest}"
! grep -q 'query-doctor-recent-history-operator-readiness' "${configured_postgres_collector_manifest}"
! grep -q '^kind: Secret$' "${configured_postgres_collector_manifest}"
grep -q '^kind: CronJob$' "${configured_postgres_worker_manifest}"
grep -q 'query-doctor-recent-profile-worker' "${configured_postgres_worker_manifest}"
grep -q -- '--fail-on-warning' "${configured_postgres_worker_manifest}"
grep -q -- '--metadata-mode' "${configured_postgres_worker_manifest}"
grep -q 'secretKeyRef:' "${configured_postgres_worker_manifest}"
! grep -q '^kind: Secret$' "${configured_postgres_worker_manifest}"
grep -q '^kind: CronJob$' "${configured_postgres_retention_manifest}"
grep -q 'query-doctor-recent-history-retention' "${configured_postgres_retention_manifest}"
grep -q -- '--summary-retention-days' "${configured_postgres_retention_manifest}"
grep -q -- '--profile-artifact-retention-days' "${configured_postgres_retention_manifest}"
grep -q 'secretKeyRef:' "${configured_postgres_retention_manifest}"
! grep -q '^kind: Secret$' "${configured_postgres_retention_manifest}"
grep -q '^kind: CronJob$' "${configured_postgres_operator_readiness_manifest}"
grep -q 'query-doctor-recent-history-operator-readiness' "${configured_postgres_operator_readiness_manifest}"
grep -q 'query-doctor-recent-profile-remediation' "${configured_postgres_operator_readiness_manifest}"
grep -q 'recent_history_operator_readiness_summary_json' "${configured_postgres_operator_readiness_manifest}"
grep -q -- '--dry-run' "${configured_postgres_operator_readiness_manifest}"
grep -q -- '--summary-json' "${configured_postgres_operator_readiness_manifest}"
grep -q 'remediation-summary.json' "${configured_postgres_operator_readiness_manifest}"
! grep -q -- '--apply' "${configured_postgres_operator_readiness_manifest}"
grep -q -- '--postgres-readiness-summary-json' "${configured_postgres_operator_readiness_manifest}"
grep -q -- '--profile-worker-summary-json' "${configured_postgres_operator_readiness_manifest}"
grep -q -- '--collector-summary-json' "${configured_postgres_operator_readiness_manifest}"
grep -q 'collector-summary.json' "${configured_postgres_operator_readiness_manifest}"
grep -q -- '--retention-summary-json' "${configured_postgres_operator_readiness_manifest}"
grep -q -- '--summary-json' "${configured_postgres_operator_readiness_manifest}"
grep -q 'operator-readiness-summary.json' "${configured_postgres_operator_readiness_manifest}"
! grep -q '^kind: Secret$' "${configured_postgres_operator_readiness_manifest}"
grep -q 'apiVersion: postgresql.cnpg.io/v1' "${configured_cnpg_manifest}"
grep -q '^kind: Cluster$' "${configured_cnpg_manifest}"
grep -Eq 'name: "?query-doctor-recent-history-owner"?' "${configured_cnpg_manifest}"
! grep -q '^kind: Secret$' "${configured_cnpg_manifest}"
grep -q '^kind: Cluster$' "${configured_cnpg_generated_cluster}"
grep -Eq 'name: "?query-doctor-history-app"?' "${configured_cnpg_generated_manifest}"
grep -Eq 'key: "?uri"?' "${configured_cnpg_generated_manifest}"
! grep -q 'secret:' "${configured_cnpg_generated_cluster}"
! grep -q '^kind: Secret$' "${configured_cnpg_generated_manifest}"
grep -q 'helm.sh/hook' "${self_test_manifest}"
grep -q 'query-doctor-self-test' "${self_test_manifest}"

if command -v kubeconform >/dev/null 2>&1; then
  kubeconform -strict -summary \
    "${public_manifest}" \
    "${configured_manifest}" \
    "${configured_kerberos_manifest}" \
    "${configured_kerberos_no_renewer_manifest}" \
    "${configured_postgres_manifest}" \
    "${configured_postgres_collector_manifest}" \
    "${configured_postgres_worker_manifest}" \
    "${configured_postgres_retention_manifest}" \
    "${configured_postgres_operator_readiness_manifest}" \
    "${self_test_manifest}"
else
  echo "[helm-chart-smoke] kubeconform not found; skipped manifest schema validation"
fi

echo "[helm-chart-smoke] ok"
