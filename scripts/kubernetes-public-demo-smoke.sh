#!/usr/bin/env bash
set -euo pipefail

chart_dir="${QUERY_DOCTOR_K8S_SMOKE_CHART:-deploy/helm/query-doctor}"
namespace="${QUERY_DOCTOR_K8S_SMOKE_NAMESPACE:-query-doctor-smoke}"
release="${QUERY_DOCTOR_K8S_SMOKE_RELEASE:-query-doctor-smoke}"
host="${QUERY_DOCTOR_K8S_SMOKE_HOST:-127.0.0.1}"
port="${QUERY_DOCTOR_K8S_SMOKE_PORT:-18766}"
cleanup_enabled="${QUERY_DOCTOR_K8S_SMOKE_CLEANUP:-1}"
rollout_timeout="${QUERY_DOCTOR_K8S_SMOKE_ROLLOUT_TIMEOUT:-180s}"
tmp_dir="${TMPDIR:-/tmp}/query-doctor-k8s-smoke-$$"
port_forward_log="${tmp_dir}/port-forward.log"
image_repository="${QUERY_DOCTOR_K8S_SMOKE_IMAGE_REPOSITORY:-}"
image_tag="${QUERY_DOCTOR_K8S_SMOKE_IMAGE_TAG:-}"
image_digest="${QUERY_DOCTOR_K8S_SMOKE_IMAGE_DIGEST:-}"
image_pull_policy="${QUERY_DOCTOR_K8S_SMOKE_IMAGE_PULL_POLICY:-}"

cleanup() {
  if [[ -n "${port_forward_pid:-}" ]]; then
    kill "${port_forward_pid}" >/dev/null 2>&1 || true
    wait "${port_forward_pid}" >/dev/null 2>&1 || true
  fi
  if [[ "${cleanup_enabled}" == "1" ]]; then
    helm uninstall "${release}" -n "${namespace}" >/dev/null 2>&1 || true
    kubectl delete namespace "${namespace}" --ignore-not-found >/dev/null 2>&1 || true
  fi
  rm -rf "${tmp_dir}"
}

dump_diagnostics() {
  echo "[kubernetes-public-demo-smoke] diagnostics for namespace ${namespace}" >&2
  if [[ -s "${port_forward_log}" ]]; then
    echo "[kubernetes-public-demo-smoke] port-forward log" >&2
    sed -n '1,80p' "${port_forward_log}" >&2
  fi
  kubectl get deploy,pods,svc,endpoints -n "${namespace}" -o wide >&2 || true
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

mkdir -p "${tmp_dir}"

kubectl create namespace "${namespace}" --dry-run=client -o yaml \
  | kubectl label --local -f - app=query-doctor-smoke realm=query-doctor --dry-run=client -o yaml \
  | kubectl apply -f -
helm_set_args=(
  --set fullnameOverride=query-doctor-web
  --set namespace.create=false
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

kubectl -n "${namespace}" rollout status deploy/query-doctor-web --timeout="${rollout_timeout}"

kubectl -n "${namespace}" port-forward --address "${host}" svc/query-doctor-web "${port}:80" >"${port_forward_log}" 2>&1 &
port_forward_pid="$!"

health_url="http://${host}:${port}/healthz"
ready_url="http://${host}:${port}/readyz"
home_url="http://${host}:${port}/"

port_forward_ready=0
for _ in $(seq 1 30); do
  if ! kill -0 "${port_forward_pid}" >/dev/null 2>&1; then
    echo "[kubernetes-public-demo-smoke] port-forward exited before probes were reachable" >&2
    exit 1
  fi
  if curl -fsS "${health_url}" >/dev/null 2>&1; then
    port_forward_ready=1
    break
  fi
  sleep 1
done
if [[ "${port_forward_ready}" != "1" ]]; then
  echo "[kubernetes-public-demo-smoke] port-forward did not become ready before timeout" >&2
  exit 1
fi

health_payload="$(curl -fsS "${health_url}")"
ready_payload="$(curl -fsS "${ready_url}")"
home_payload="$(curl -fsS "${home_url}")"

case "${health_payload}" in
  *'"probe": "liveness"'* | *'"probe":"liveness"'*) ;;
  *) echo "[kubernetes-public-demo-smoke] healthz payload did not report liveness" >&2; exit 1 ;;
esac

case "${ready_payload}" in
  *'"probe": "readiness"'* | *'"probe":"readiness"'*) ;;
  *) echo "[kubernetes-public-demo-smoke] readyz payload did not report readiness" >&2; exit 1 ;;
esac

case "${home_payload}" in
  *"Query Doctor"* ) ;;
  *) echo "[kubernetes-public-demo-smoke] home page did not render Query Doctor" >&2; exit 1 ;;
esac

echo "[kubernetes-public-demo-smoke] ok"
