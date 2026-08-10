#!/usr/bin/env bash
set -euo pipefail

namespace="${QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_NAMESPACE:-query-doctor}"
release="${QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_RELEASE:-query-doctor-full}"
deployment="${QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_DEPLOYMENT:-${release}}"
service="${QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_SERVICE:-${release}}"
collector_cronjob="${QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_COLLECTOR_CRONJOB:-${release}-recent-summary-collector}"
worker_cronjob="${QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_WORKER_CRONJOB:-${release}-recent-profile-worker}"
readiness_cronjob="${QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_READINESS_CRONJOB:-${release}-recent-history-operator-readiness}"
rollout_timeout="${QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_ROLLOUT_TIMEOUT:-180s}"
job_timeout="${QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_JOB_TIMEOUT:-600s}"
host="${QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_HOST:-127.0.0.1}"
port="${QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_PORT:-18771}"
expected_image="${QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_EXPECTED_IMAGE:-}"
require_suspended="${QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_REQUIRE_SUSPENDED:-1}"
run_id="$(date -u +%Y%m%d%H%M%S)-$$"
collector_job="query-doctor-online-collector-${run_id}"
worker_job="query-doctor-online-worker-${run_id}"
readiness_job="query-doctor-online-readiness-${run_id}"
tmp_dir="${TMPDIR:-/tmp}/query-doctor-online-history-smoke-$$"
history_html="${tmp_dir}/online-history.html"
port_forward_log="${tmp_dir}/port-forward.log"

if [[ "${require_suspended}" != "0" && "${require_suspended}" != "1" ]]; then
  echo "[kubernetes-online-history-smoke] REQUIRE_SUSPENDED must be 0 or 1" >&2
  exit 2
fi

cleanup() {
  if [[ -n "${port_forward_pid:-}" ]]; then
    kill "${port_forward_pid}" >/dev/null 2>&1 || true
    wait "${port_forward_pid}" >/dev/null 2>&1 || true
  fi
  kubectl -n "${namespace}" delete job \
    "${collector_job}" "${worker_job}" "${readiness_job}" \
    --ignore-not-found --wait=false >/dev/null 2>&1 || true
  rm -rf "${tmp_dir}"
}
trap cleanup EXIT

mkdir -p "${tmp_dir}"

kubectl -n "${namespace}" rollout status "deploy/${deployment}" \
  --timeout="${rollout_timeout}" >/dev/null

for cronjob in "${collector_cronjob}" "${worker_cronjob}" "${readiness_cronjob}"; do
  if ! kubectl -n "${namespace}" get cronjob "${cronjob}" >/dev/null 2>&1; then
    echo "[kubernetes-online-history-smoke] required CronJob unavailable" >&2
    exit 1
  fi
  if [[ "${require_suspended}" == "1" ]]; then
    suspended="$(
      kubectl -n "${namespace}" get cronjob "${cronjob}" \
        -o jsonpath='{.spec.suspend}'
    )"
    if [[ "${suspended}" != "true" ]]; then
      echo "[kubernetes-online-history-smoke] CronJobs must be suspended for an isolated staging cycle" >&2
      exit 1
    fi
  fi
done

web_image="$(
  kubectl -n "${namespace}" get deployment "${deployment}" \
    -o jsonpath='{.spec.template.spec.containers[?(@.name=="web")].image}'
)"
if [[ -z "${web_image}" ]]; then
  echo "[kubernetes-online-history-smoke] web image reference unavailable" >&2
  exit 1
fi
for cronjob in "${collector_cronjob}" "${worker_cronjob}" "${readiness_cronjob}"; do
  job_image="$(
    kubectl -n "${namespace}" get cronjob "${cronjob}" \
      -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
  )"
  if [[ "${job_image}" != "${web_image}" ]]; then
    echo "[kubernetes-online-history-smoke] deployment and CronJob images differ" >&2
    exit 1
  fi
done
if [[ -n "${expected_image}" && "${web_image}" != "${expected_image}" ]]; then
  echo "[kubernetes-online-history-smoke] installed image is not the expected candidate" >&2
  exit 1
fi

readiness_args="$(
  kubectl -n "${namespace}" get cronjob "${readiness_cronjob}" \
    -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].args[*]}'
)"
if [[ " ${readiness_args} " != *" --collector-summary-json "* ]]; then
  echo "[kubernetes-online-history-smoke] collector summary is not wired into readiness" >&2
  exit 1
fi

run_job() {
  local cronjob="$1"
  local job="$2"
  local stage="$3"
  kubectl -n "${namespace}" create job --from="cronjob/${cronjob}" "${job}" >/dev/null
  if ! kubectl -n "${namespace}" wait --for=condition=complete "job/${job}" \
    --timeout="${job_timeout}" >/dev/null 2>&1; then
    echo "[kubernetes-online-history-smoke] ${stage} Job did not complete" >&2
    exit 1
  fi
}

run_job "${collector_cronjob}" "${collector_job}" "collector"
run_job "${worker_cronjob}" "${worker_job}" "profile worker"
run_job "${readiness_cronjob}" "${readiness_job}" "operator readiness"

kubectl -n "${namespace}" port-forward --address "${host}" \
  "svc/${service}" "${port}:80" >"${port_forward_log}" 2>&1 &
port_forward_pid="$!"

page_ready=0
for _ in $(seq 1 30); do
  if ! kill -0 "${port_forward_pid}" >/dev/null 2>&1; then
    echo "[kubernetes-online-history-smoke] port-forward exited before UI verification" >&2
    exit 1
  fi
  if curl -fsS --max-time 15 "http://${host}:${port}/batch" >"${history_html}" 2>/dev/null; then
    page_ready=1
    break
  fi
  sleep 1
done
if [[ "${page_ready}" != "1" ]]; then
  echo "[kubernetes-online-history-smoke] Online History page was unreachable" >&2
  exit 1
fi

QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_HTML="${history_html}" python3 - <<'PY'
import os
from pathlib import Path

body = Path(os.environ["QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_HTML"]).read_text(
    encoding="utf-8"
)
required = (
    "Online History",
    "operator readiness",
    "history schema",
    "operator collector",
    "profile worker",
)
missing = [marker for marker in required if marker not in body]
if missing:
    print(
        "[kubernetes-online-history-smoke] required raw-free UI markers are missing: "
        + ", ".join(missing)
    )
    raise SystemExit(1)
PY

echo "[kubernetes-online-history-smoke] ok"
