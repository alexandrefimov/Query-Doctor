#!/usr/bin/env bash
set -euo pipefail

chart_dir="${QUERY_DOCTOR_K8S_SELF_TEST_CHART:-deploy/helm/query-doctor}"
namespace="${QUERY_DOCTOR_K8S_SELF_TEST_NAMESPACE:-query-doctor-self-test-smoke}"
release="${QUERY_DOCTOR_K8S_SELF_TEST_RELEASE:-query-doctor-self-test-smoke}"
cleanup_enabled="${QUERY_DOCTOR_K8S_SELF_TEST_CLEANUP:-1}"
test_timeout="${QUERY_DOCTOR_K8S_SELF_TEST_TIMEOUT:-300s}"
image_repository="${QUERY_DOCTOR_K8S_SELF_TEST_IMAGE_REPOSITORY:-}"
image_tag="${QUERY_DOCTOR_K8S_SELF_TEST_IMAGE_TAG:-}"
image_digest="${QUERY_DOCTOR_K8S_SELF_TEST_IMAGE_DIGEST:-}"
image_pull_policy="${QUERY_DOCTOR_K8S_SELF_TEST_IMAGE_PULL_POLICY:-}"

cleanup() {
  if [[ "${cleanup_enabled}" == "1" ]]; then
    helm uninstall "${release}" -n "${namespace}" >/dev/null 2>&1 || true
    kubectl delete namespace "${namespace}" --ignore-not-found >/dev/null 2>&1 || true
  fi
}

dump_diagnostics() {
  echo "[kubernetes-self-test-smoke] diagnostics for namespace ${namespace}" >&2
  kubectl get jobs,pods -n "${namespace}" -o wide >&2 || true
  kubectl get events -n "${namespace}" --sort-by=.lastTimestamp >&2 || true
}

finalize() {
  status=$?
  if [[ "${status}" -ne 0 ]]; then
    dump_diagnostics
  fi
  cleanup
  exit "${status}"
}
trap finalize EXIT

kubectl create namespace "${namespace}" --dry-run=client -o yaml \
  | kubectl label --local -f - app=query-doctor-self-test realm=query-doctor --dry-run=client -o yaml \
  | kubectl apply -f -

helm_set_args=(
  --set namespace.create=false
  --set selfTestJob.enabled=true
)
if [[ -n "${image_repository}" ]]; then
  helm_set_args+=(--set-string "image.repository=${image_repository}")
fi
if [[ -n "${image_tag}" ]]; then
  helm_set_args+=(--set-string "image.tag=${image_tag}")
fi
if [[ -n "${image_digest}" ]]; then
  helm_set_args+=(--set-string "image.digest=${image_digest}")
fi
if [[ -n "${image_pull_policy}" ]]; then
  helm_set_args+=(--set-string "image.pullPolicy=${image_pull_policy}")
fi

helm upgrade --install "${release}" "${chart_dir}" \
  --namespace "${namespace}" \
  "${helm_set_args[@]}"

helm test "${release}" \
  --namespace "${namespace}" \
  --timeout "${test_timeout}"

kubectl logs \
  --namespace "${namespace}" \
  -l "app.kubernetes.io/instance=${release},app.kubernetes.io/component=self-test" \
  --tail=-1

echo "[kubernetes-self-test-smoke] ok"
