#!/usr/bin/env bash
set -euo pipefail

namespace="${QUERY_DOCTOR_K8S_KERBEROS_SMOKE_NAMESPACE:-query-doctor}"
release="${QUERY_DOCTOR_K8S_KERBEROS_SMOKE_RELEASE:-query-doctor-full}"
deployment="${QUERY_DOCTOR_K8S_KERBEROS_SMOKE_DEPLOYMENT:-${release}}"
web_container="${QUERY_DOCTOR_K8S_KERBEROS_SMOKE_WEB_CONTAINER:-web}"
renewer_container="${QUERY_DOCTOR_K8S_KERBEROS_SMOKE_RENEWER_CONTAINER:-kerberos-ticket-renewer}"
rollout_timeout="${QUERY_DOCTOR_K8S_KERBEROS_SMOKE_ROLLOUT_TIMEOUT:-180s}"
max_wait_seconds="${QUERY_DOCTOR_K8S_KERBEROS_SMOKE_MAX_WAIT_SECONDS:-120}"

if [[ ! "${max_wait_seconds}" =~ ^[0-9]+$ ]] || (( max_wait_seconds < 65 )); then
  echo "[kubernetes-kerberos-renewer-smoke] bounded smoke wait is invalid" >&2
  exit 2
fi

kubectl -n "${namespace}" rollout status "deploy/${deployment}" \
  --timeout="${rollout_timeout}" >/dev/null

pod="$(
  kubectl -n "${namespace}" get pod \
    -l "app.kubernetes.io/instance=${release},app.kubernetes.io/component=web" \
    --field-selector=status.phase=Running \
    -o jsonpath='{.items[0].metadata.name}'
)"
if [[ -z "${pod}" ]]; then
  echo "[kubernetes-kerberos-renewer-smoke] running web pod unavailable" >&2
  exit 1
fi

container_names="$(
  kubectl -n "${namespace}" get pod "${pod}" \
    -o jsonpath='{.spec.containers[*].name}'
)"
if [[ " ${container_names} " != *" ${renewer_container} "* ]]; then
  echo "[kubernetes-kerberos-renewer-smoke] renewer sidecar unavailable" >&2
  exit 1
fi

refresh_interval="$(
  kubectl -n "${namespace}" get deployment "${deployment}" \
    -o "jsonpath={.spec.template.spec.containers[?(@.name==\"${renewer_container}\")].env[?(@.name==\"KERBEROS_REFRESH_INTERVAL_SECONDS\")].value}"
)"
if [[ ! "${refresh_interval}" =~ ^[0-9]+$ ]] || (( refresh_interval < 60 )); then
  echo "[kubernetes-kerberos-renewer-smoke] refresh interval is unavailable or invalid" >&2
  exit 1
fi

wait_seconds=$((refresh_interval + 5))
if (( wait_seconds > max_wait_seconds )); then
  echo "[kubernetes-kerberos-renewer-smoke] refresh interval exceeds the bounded smoke wait" >&2
  echo "[kubernetes-kerberos-renewer-smoke] use a short staging-only interval, then restore the production value" >&2
  exit 2
fi

cache_mtime() {
  kubectl exec -i -n "${namespace}" "${pod}" -c "${web_container}" -- /bin/sh -ec '
    case "${KRB5CCNAME:-}" in
      FILE:/tmp/query-doctor-krb5/*) ;;
      *) exit 1 ;;
    esac
    cache_file="${KRB5CCNAME#FILE:}"
    klist -s -c "$cache_file" >/dev/null 2>&1
    stat -c %Y "$cache_file"
  '
}

before_mtime="$(cache_mtime)"
sleep "${wait_seconds}"
after_mtime="$(cache_mtime)"

if [[ ! "${before_mtime}" =~ ^[0-9]+$ ]] || [[ ! "${after_mtime}" =~ ^[0-9]+$ ]]; then
  echo "[kubernetes-kerberos-renewer-smoke] cache timestamp check failed" >&2
  exit 1
fi
if (( after_mtime <= before_mtime )); then
  echo "[kubernetes-kerberos-renewer-smoke] cache was not refreshed within the bounded interval" >&2
  exit 1
fi

echo "[kubernetes-kerberos-renewer-smoke] ok"
