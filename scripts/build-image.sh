#!/usr/bin/env bash
set -euo pipefail

image_tag="${1:-query-doctor:dev}"
context_dir="${2:-.}"
platform="${QUERY_DOCTOR_IMAGE_PLATFORM:-}"
install_extras="${QUERY_DOCTOR_INSTALL_EXTRAS:-}"
dockerfile="${QUERY_DOCTOR_DOCKERFILE:-Dockerfile}"
pull="${QUERY_DOCTOR_IMAGE_PULL:-true}"
target="${QUERY_DOCTOR_BUILD_TARGET:-}"

case "${pull}" in
  true) pull_arg="--pull" ;;
  false) pull_arg="--pull=false" ;;
  *) echo "[build-image] QUERY_DOCTOR_IMAGE_PULL must be true or false" >&2; exit 2 ;;
esac

build_args=("${pull_arg}" --file "${dockerfile}" -t "${image_tag}")
if [[ -n "${platform}" ]]; then
  build_args+=(--platform "${platform}")
fi
if [[ -n "${target}" ]]; then
  build_args+=(--target "${target}")
fi
if [[ -n "${install_extras}" ]]; then
  build_args+=(--build-arg "QUERY_DOCTOR_INSTALL_EXTRAS=${install_extras}")
fi
docker build "${build_args[@]}" "${context_dir}"
