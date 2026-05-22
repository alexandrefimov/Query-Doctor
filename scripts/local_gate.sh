#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
RUFF_BIN="${RUFF:-}"
DEMO_OUT="${DEMO_OUT:-${TMPDIR:-/tmp}/query-doctor-demo-pack-local-gate}"

cd "$ROOT_DIR"

run_step() {
  printf '\n==> %s\n' "$*"
  "$@"
}

run_python_module() {
  local module="$1"
  shift
  run_step "$PYTHON_BIN" -m "$module" "$@"
}

run_ruff() {
  if [[ -n "$RUFF_BIN" ]]; then
    run_step "$RUFF_BIN" check query_doctor tests
    return
  fi
  if "$PYTHON_BIN" -m ruff --version >/dev/null 2>&1; then
    run_python_module ruff check query_doctor tests
    return
  fi
  printf '\nMissing ruff. Install dev dependencies with python3 -m pip install -e ".[dev]"\n' >&2
  printf 'or run with RUFF=/path/to/ruff scripts/local_gate.sh\n' >&2
  return 1
}

run_step "$PYTHON_BIN" scripts/agent_preflight.py
run_step "$PYTHON_BIN" scripts/check_staged_public_safety.py
run_step "$PYTHON_BIN" scripts/check_staged_public_safety.py --changed
run_step git diff --check
run_step "$PYTHON_BIN" scripts/check_active_docs.py
run_step "$PYTHON_BIN" scripts/check_markdown_links.py
run_ruff
run_python_module pytest -q
run_python_module query_doctor.cli.demo_preflight
run_python_module query_doctor.cli.demo_data --out "$DEMO_OUT" --overwrite

if [[ "${PUBLIC_RELEASE:-0}" == "1" ]]; then
  run_python_module query_doctor.cli.demo_preflight --public-release
fi
