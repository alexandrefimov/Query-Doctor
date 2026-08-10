#!/usr/bin/env bash
set -euo pipefail

namespace="${QUERY_DOCTOR_K8S_RELEASE_GATE_NAMESPACE:-query-doctor}"
release="${QUERY_DOCTOR_K8S_RELEASE_GATE_RELEASE:-query-doctor-full}"
deployment="${QUERY_DOCTOR_K8S_RELEASE_GATE_DEPLOYMENT:-${release}}"
query_doctor_service="${QUERY_DOCTOR_K8S_RELEASE_GATE_QUERY_DOCTOR_SERVICE:-${release}}"
auth_proxy_service="${QUERY_DOCTOR_K8S_RELEASE_GATE_AUTH_PROXY_SERVICE:-query-doctor-oauth2-proxy}"
container="${QUERY_DOCTOR_K8S_RELEASE_GATE_CONTAINER:-web}"
port_forward_host="${QUERY_DOCTOR_K8S_RELEASE_GATE_PORT_FORWARD_HOST:-127.0.0.1}"
port_forward_port="${QUERY_DOCTOR_K8S_RELEASE_GATE_PORT_FORWARD_PORT:-18770}"
external_url="${QUERY_DOCTOR_K8S_RELEASE_GATE_EXTERNAL_URL:-}"
expected_issuer_url="${QUERY_DOCTOR_K8S_RELEASE_GATE_EXPECTED_ISSUER_URL:-}"
expected_client_id="${QUERY_DOCTOR_K8S_RELEASE_GATE_EXPECTED_CLIENT_ID:-}"
expected_host="${QUERY_DOCTOR_K8S_RELEASE_GATE_EXPECTED_HOST:-}"
expected_code_challenge_method="${QUERY_DOCTOR_K8S_RELEASE_GATE_EXPECTED_CODE_CHALLENGE_METHOD:-S256}"
expected_groups_claim="${QUERY_DOCTOR_K8S_RELEASE_GATE_EXPECTED_GROUPS_CLAIM:-query_doctor_groups_disabled}"
require_network_policy="${QUERY_DOCTOR_K8S_RELEASE_GATE_REQUIRE_NETWORK_POLICY:-1}"
ingress_controller_namespace_labels="${QUERY_DOCTOR_K8S_RELEASE_GATE_INGRESS_CONTROLLER_NAMESPACE_LABELS:-}"
ingress_controller_pod_labels="${QUERY_DOCTOR_K8S_RELEASE_GATE_INGRESS_CONTROLLER_POD_LABELS:-}"
tmp_dir="${TMPDIR:-/tmp}/query-doctor-k8s-release-gate-$$"
resources_json="${tmp_dir}/auth-front-door-resources.json"
readiness_json="${tmp_dir}/deployment-readiness.json"
port_forward_log="${tmp_dir}/port-forward.log"

cleanup() {
  if [[ -n "${port_forward_pid:-}" ]]; then
    kill "${port_forward_pid}" >/dev/null 2>&1 || true
    wait "${port_forward_pid}" >/dev/null 2>&1 || true
  fi
  rm -rf "${tmp_dir}"
}

dump_diagnostics() {
  echo "[kubernetes-configured-release-gate] diagnostics" >&2
  if [[ -s "${port_forward_log}" ]]; then
    echo "[kubernetes-configured-release-gate] port-forward log" >&2
    sed -n '1,80p' "${port_forward_log}" >&2
  fi
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

require_value() {
  local value="$1"
  local name="$2"
  if [[ -z "${value}" ]]; then
    echo "[kubernetes-configured-release-gate] ${name} is required" >&2
    exit 2
  fi
}

append_csv_label_args() {
  local flag="$1"
  local labels="$2"
  if [[ -z "${labels}" ]]; then
    return
  fi
  local old_ifs="${IFS}"
  IFS=','
  read -r -a label_parts <<< "${labels}"
  IFS="${old_ifs}"
  local label
  for label in "${label_parts[@]}"; do
    if [[ -n "${label}" ]]; then
      auth_audit_args+=("${flag}" "${label}")
    fi
  done
}

require_value "${external_url}" "QUERY_DOCTOR_K8S_RELEASE_GATE_EXTERNAL_URL"
require_value "${expected_issuer_url}" "QUERY_DOCTOR_K8S_RELEASE_GATE_EXPECTED_ISSUER_URL"
require_value "${expected_client_id}" "QUERY_DOCTOR_K8S_RELEASE_GATE_EXPECTED_CLIENT_ID"
require_value "${expected_host}" "QUERY_DOCTOR_K8S_RELEASE_GATE_EXPECTED_HOST"
if [[ "${require_network_policy}" == "1" ]]; then
  require_value \
    "${ingress_controller_namespace_labels}" \
    "QUERY_DOCTOR_K8S_RELEASE_GATE_INGRESS_CONTROLLER_NAMESPACE_LABELS"
  require_value \
    "${ingress_controller_pod_labels}" \
    "QUERY_DOCTOR_K8S_RELEASE_GATE_INGRESS_CONTROLLER_POD_LABELS"
fi

mkdir -p "${tmp_dir}"

echo "[kubernetes-configured-release-gate] configured metadata smoke"
QUERY_DOCTOR_K8S_METADATA_SMOKE_NAMESPACE="${namespace}" \
QUERY_DOCTOR_K8S_METADATA_SMOKE_RELEASE="${release}" \
QUERY_DOCTOR_K8S_METADATA_SMOKE_DEPLOYMENT="${deployment}" \
QUERY_DOCTOR_K8S_METADATA_SMOKE_SERVICE="${query_doctor_service}" \
QUERY_DOCTOR_K8S_METADATA_SMOKE_CONTAINER="${container}" \
scripts/kubernetes-configured-metadata-smoke.sh

echo "[kubernetes-configured-release-gate] external auth redirect smoke"
python3 scripts/kubernetes_auth_front_door_smoke.py --compact \
  --base-url "${external_url}" \
  --expected-issuer-url "${expected_issuer_url}" \
  --expected-client-id "${expected_client_id}" \
  --expected-code-challenge-method "${expected_code_challenge_method}"

echo "[kubernetes-configured-release-gate] auth front-door resource audit"
kubectl -n "${namespace}" get ingress,deploy,svc,networkpolicy -o json > "${resources_json}"

kubectl -n "${namespace}" port-forward \
  --address "${port_forward_host}" \
  "svc/${query_doctor_service}" \
  "${port_forward_port}:80" >"${port_forward_log}" 2>&1 &
port_forward_pid="$!"

readiness_ready=0
for _ in $(seq 1 30); do
  if ! kill -0 "${port_forward_pid}" >/dev/null 2>&1; then
    echo "[kubernetes-configured-release-gate] port-forward exited before readiness was reachable" >&2
    exit 1
  fi
  if curl -fsS \
    "http://${port_forward_host}:${port_forward_port}/deployment/readiness.json" \
    > "${readiness_json}" 2>/dev/null; then
    readiness_ready=1
    break
  fi
  sleep 1
done
if [[ "${readiness_ready}" != "1" ]]; then
  echo "[kubernetes-configured-release-gate] deployment readiness did not become reachable" >&2
  exit 1
fi

auth_audit_args=(
  --resources-json "${resources_json}"
  --namespace "${namespace}"
  --query-doctor-service "${query_doctor_service}"
  --auth-proxy-service "${auth_proxy_service}"
  --expected-host "${expected_host}"
  --expected-issuer-url "${expected_issuer_url}"
  --expected-client-id "${expected_client_id}"
  --expected-code-challenge-method "${expected_code_challenge_method}"
  --require-compact-session-cookie
  --expected-groups-claim "${expected_groups_claim}"
  --deployment-readiness-json "${readiness_json}"
)
if [[ "${require_network_policy}" == "1" ]]; then
  auth_audit_args+=(--require-network-policy)
fi
append_csv_label_args \
  --ingress-controller-namespace-label \
  "${ingress_controller_namespace_labels}"
append_csv_label_args \
  --ingress-controller-pod-label \
  "${ingress_controller_pod_labels}"

python3 scripts/audit_kubernetes_auth_front_door.py "${auth_audit_args[@]}"

echo "[kubernetes-configured-release-gate] ok"
