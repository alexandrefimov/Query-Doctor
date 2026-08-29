#!/usr/bin/env bash
set -euo pipefail

image_tag="${1:-query-doctor:dev}"
host="${QUERY_DOCTOR_IMAGE_SMOKE_HOST:-127.0.0.1}"
port="${QUERY_DOCTOR_IMAGE_SMOKE_PORT:-18765}"
container_name="query-doctor-image-smoke-$$"
platform="${QUERY_DOCTOR_IMAGE_PLATFORM:-}"

cleanup() {
  docker rm -f "${container_name}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

run_args=(
  --rm
  -d
  --name
  "${container_name}"
  -p
  "${host}:${port}:8765"
)
if [[ -n "${platform}" ]]; then
  run_args+=(--platform "${platform}")
fi

docker run "${run_args[@]}" "${image_tag}" >/dev/null

tool_args=(--rm)
if [[ -n "${platform}" ]]; then
  tool_args+=(--platform "${platform}")
fi
docker run "${tool_args[@]}" --entrypoint python "${image_tag}" -c \
  "import shutil, kerberos; from impala.dbapi import connect; assert shutil.which('klist')" >/dev/null

health_url="http://${host}:${port}/healthz"
ready_url="http://${host}:${port}/readyz"
deployment_url="http://${host}:${port}/deployment/readiness.json"
home_url="http://${host}:${port}/"

for _ in $(seq 1 30); do
  if curl -fsS "${health_url}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

health_payload="$(curl -fsS "${health_url}")"
ready_payload="$(curl -fsS "${ready_url}")"
deployment_payload="$(curl -fsS "${deployment_url}")"
home_payload="$(curl -fsS "${home_url}")"

case "${health_payload}" in
  *'"probe": "liveness"'* | *'"probe":"liveness"'*) ;;
  *) echo "[image-smoke] healthz payload did not report liveness" >&2; exit 1 ;;
esac

case "${ready_payload}" in
  *'"probe": "readiness"'* | *'"probe":"readiness"'*) ;;
  *) echo "[image-smoke] readyz payload did not report readiness" >&2; exit 1 ;;
esac

case "${deployment_payload}" in
  *'"kind": "query_doctor_deployment_readiness_v1"'* | *'"kind":"query_doctor_deployment_readiness_v1"'*) ;;
  *) echo "[image-smoke] deployment readiness payload did not report the expected kind" >&2; exit 1 ;;
esac

case "${deployment_payload}" in
  *'"sql_execution": false'* | *'"sql_execution":false'*) ;;
  *) echo "[image-smoke] deployment readiness payload did not keep sql_execution=false" >&2; exit 1 ;;
esac

case "${home_payload}" in
  *"Query Doctor"* ) ;;
  *) echo "[image-smoke] home page did not render Query Doctor" >&2; exit 1 ;;
esac

echo "[image-smoke] ok"
