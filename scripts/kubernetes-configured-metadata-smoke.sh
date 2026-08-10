#!/usr/bin/env bash
set -euo pipefail

namespace="${QUERY_DOCTOR_K8S_METADATA_SMOKE_NAMESPACE:-query-doctor}"
release="${QUERY_DOCTOR_K8S_METADATA_SMOKE_RELEASE:-query-doctor-full}"
deployment="${QUERY_DOCTOR_K8S_METADATA_SMOKE_DEPLOYMENT:-${release}}"
service="${QUERY_DOCTOR_K8S_METADATA_SMOKE_SERVICE:-${release}}"
container="${QUERY_DOCTOR_K8S_METADATA_SMOKE_CONTAINER:-web}"
host="${QUERY_DOCTOR_K8S_METADATA_SMOKE_HOST:-127.0.0.1}"
port="${QUERY_DOCTOR_K8S_METADATA_SMOKE_PORT:-18766}"
rollout_timeout="${QUERY_DOCTOR_K8S_METADATA_SMOKE_ROLLOUT_TIMEOUT:-180s}"
job_timeout_sec="${QUERY_DOCTOR_K8S_METADATA_SMOKE_JOB_TIMEOUT_SEC:-360}"
tmp_dir="${TMPDIR:-/tmp}/query-doctor-k8s-metadata-smoke-$$"
port_forward_log="${tmp_dir}/port-forward.log"
job_id_file="${tmp_dir}/job-id"

cleanup() {
  if [[ -n "${port_forward_pid:-}" ]]; then
    kill "${port_forward_pid}" >/dev/null 2>&1 || true
    wait "${port_forward_pid}" >/dev/null 2>&1 || true
  fi
  rm -rf "${tmp_dir}"
}

dump_diagnostics() {
  echo "[kubernetes-configured-metadata-smoke] diagnostics for namespace ${namespace}" >&2
  if [[ -s "${port_forward_log}" ]]; then
    echo "[kubernetes-configured-metadata-smoke] port-forward log" >&2
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

kubectl -n "${namespace}" rollout status "deploy/${deployment}" --timeout="${rollout_timeout}"

pod="$(
  kubectl -n "${namespace}" get pod \
    -l "app.kubernetes.io/instance=${release},app.kubernetes.io/component=web" \
    --field-selector=status.phase=Running \
    -o jsonpath='{.items[0].metadata.name}'
)"
if [[ -z "${pod}" ]]; then
  echo "[kubernetes-configured-metadata-smoke] no running web pod found for release" >&2
  exit 1
fi

kubectl exec -i -n "${namespace}" "${pod}" -c "${container}" -- python - <<'PY'
import os
import pathlib
import shutil
import subprocess
import sys

shell = pathlib.Path(os.environ.get("QD_IMPALA_SHELL", ""))
cache = os.environ.get("KRB5CCNAME", "")
cache_path = cache[5:] if cache.startswith("FILE:") else cache
checks = {
    "impala_shell_path_exists": shell.is_file(),
    "sasl_import": bool(shell.is_file())
    and subprocess.run([str(shell.with_name("python")), "-c", "import sasl"], check=False).returncode == 0,
    "krb5ccname_set": bool(cache),
    "krb5_cache_exists": bool(cache_path) and pathlib.Path(cache_path).is_file(),
    "klist_available": bool(shutil.which("klist")),
    "klist_valid": subprocess.run(["klist", "-s"], check=False).returncode == 0,
}
for key in sorted(checks):
    print(f"{key}={checks[key]}")
if not all(checks.values()):
    sys.exit(1)
PY

kubectl -n "${namespace}" port-forward --address "${host}" "svc/${service}" "${port}:80" >"${port_forward_log}" 2>&1 &
port_forward_pid="$!"

health_url="http://${host}:${port}/healthz"

port_forward_ready=0
for _ in $(seq 1 30); do
  if ! kill -0 "${port_forward_pid}" >/dev/null 2>&1; then
    echo "[kubernetes-configured-metadata-smoke] port-forward exited before probes were reachable" >&2
    exit 1
  fi
  if curl -fsS "${health_url}" >/dev/null 2>&1; then
    port_forward_ready=1
    break
  fi
  sleep 1
done
if [[ "${port_forward_ready}" != "1" ]]; then
  echo "[kubernetes-configured-metadata-smoke] port-forward did not become ready before timeout" >&2
  exit 1
fi

QUERY_DOCTOR_K8S_METADATA_SMOKE_HOST="${host}" \
QUERY_DOCTOR_K8S_METADATA_SMOKE_PORT="${port}" \
QUERY_DOCTOR_K8S_METADATA_SMOKE_JOB_TIMEOUT_SEC="${job_timeout_sec}" \
QUERY_DOCTOR_K8S_METADATA_SMOKE_JOB_ID_FILE="${job_id_file}" \
python3 - <<'PY'
import http.client
import json
import os
import pathlib
import time
from urllib.parse import urlencode

host = os.environ.get("QUERY_DOCTOR_K8S_METADATA_SMOKE_HOST", "127.0.0.1")
port = int(os.environ["QUERY_DOCTOR_K8S_METADATA_SMOKE_PORT"])
timeout_sec = int(os.environ.get("QUERY_DOCTOR_K8S_METADATA_SMOKE_JOB_TIMEOUT_SEC", "360"))
job_id_file = pathlib.Path(os.environ["QUERY_DOCTOR_K8S_METADATA_SMOKE_JOB_ID_FILE"])
form = {
    "engine": "impala",
    "scan_target": "finished",
    "recent_window_minutes": os.environ.get("QUERY_DOCTOR_K8S_METADATA_SMOKE_WINDOW_MINUTES", "120"),
    "triage_profile_limit": os.environ.get("QUERY_DOCTOR_K8S_METADATA_SMOKE_LIMIT", "1"),
    "metadata_top_limit": os.environ.get("QUERY_DOCTOR_K8S_METADATA_SMOKE_METADATA_TOP_LIMIT", "1"),
    "parallelism": os.environ.get("QUERY_DOCTOR_K8S_METADATA_SMOKE_PARALLELISM", "1"),
    "metadata_jobs": os.environ.get("QUERY_DOCTOR_K8S_METADATA_SMOKE_METADATA_JOBS", "1"),
    "query_type": os.environ.get("QUERY_DOCTOR_K8S_METADATA_SMOKE_QUERY_TYPE", "QUERY"),
    "order": os.environ.get("QUERY_DOCTOR_K8S_METADATA_SMOKE_ORDER", "duration-desc"),
    "cm_events_max_events": os.environ.get("QUERY_DOCTOR_K8S_METADATA_SMOKE_CM_EVENTS_MAX_EVENTS", "10"),
    "cm_timeseries_top_limit": os.environ.get("QUERY_DOCTOR_K8S_METADATA_SMOKE_CM_TIMESERIES_TOP_LIMIT", "0"),
    "publish_latest_summary": "0",
}
conn = http.client.HTTPConnection(host, port, timeout=30)
conn.request(
    "POST",
    "/batch/run",
    body=urlencode(form),
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
resp = conn.getresponse()
resp.read()
location = resp.getheader("Location")
print(f"submit_status={resp.status}")
print(f"submit_location_present={bool(location)}")
if resp.status != 303 or not location:
    raise SystemExit(1)
job_id = location.rstrip("/").split("/")[-1]
job_id_file.write_text(job_id, encoding="utf-8")
print(f"job_id_shape={len(job_id)}_chars")

deadline = time.monotonic() + timeout_sec
attempt = 0
while time.monotonic() < deadline:
    time.sleep(2)
    attempt += 1
    conn = http.client.HTTPConnection(host, port, timeout=30)
    conn.request("GET", f"/jobs/{job_id}/status")
    resp = conn.getresponse()
    payload = json.loads(resp.read().decode("utf-8", "replace"))
    status = payload.get("status")
    progress = payload.get("progress")
    stage = payload.get("stage")
    if attempt % 5 == 1 or status != "running":
        print(f"job_status={status} progress={progress} stage={stage}")
    if status in {"ok", "failed", "cancelled"}:
        if status != "ok":
            info = payload.get("error_info") or {}
            print(f"error_reason_code={info.get('reason_code') or ''}")
            print(f"error_title={info.get('title') or ''}")
        raise SystemExit(0 if status == "ok" else 1)
raise SystemExit("timed out waiting for metadata smoke job")
PY

job_id="$(cat "${job_id_file}")"

kubectl exec -i -n "${namespace}" "${pod}" -c "${container}" -- env QUERY_DOCTOR_WEB_JOB_ID="${job_id}" python - <<'PY'
import json
import os
import sys
from collections import Counter
from pathlib import Path

job_id = os.environ["QUERY_DOCTOR_WEB_JOB_ID"]
summary_path = Path("/tmp") / f"query-doctor-web-batch-{job_id}" / "batch_summary.json"
if not summary_path.is_file():
    print("summary_present=False")
    sys.exit(1)
summary = json.loads(summary_path.read_text(encoding="utf-8"))
cases = summary.get("cases") or summary.get("results") or []
if not isinstance(cases, list):
    cases = []
metadata_status = Counter()
requested = 0
collected = 0
cases_with_table_context = 0
for case in cases:
    if not isinstance(case, dict):
        continue
    status = str(case.get("metadata_status") or "<missing>").strip().lower()
    requested_case = int(case.get("collectable_metadata_table_count") or 0)
    collected_case = int(case.get("collected_metadata_table_count") or 0)
    metadata_status[status] += 1
    requested += requested_case
    collected += collected_case
    if status == "collected" or (status == "partial" and collected_case > 0):
        cases_with_table_context += 1
print("summary_present=True")
print(f"case_count={len(cases)}")
print("metadata_status_counts=" + ",".join(f"{key}:{value}" for key, value in sorted(metadata_status.items())))
print(f"metadata_cases_with_table_context={cases_with_table_context}")
print(f"metadata_tables_requested={requested}")
print(f"metadata_tables_collected={collected}")

analysis_files = list(summary_path.parent.rglob("analysis.json"))
if analysis_files:
    analysis = json.loads(analysis_files[0].read_text(encoding="utf-8"))
    table_ctx = analysis.get("table_metadata_context") if isinstance(analysis, dict) else {}
    if isinstance(table_ctx, dict):
        print(f"table_metadata_tables_requested={table_ctx.get('tables_requested')}")
        tables = table_ctx.get("tables")
        print(f"table_metadata_tables_len={len(tables) if isinstance(tables, list) else 0}")
        print(f"table_metadata_facts={table_ctx.get('table_metadata_facts')}")

if cases_with_table_context < 1 or requested < 1 or collected < 1:
    sys.exit(1)
PY

echo "[kubernetes-configured-metadata-smoke] ok"
