#!/usr/bin/env bash
# Assemble the self-contained browser analyzer into web/dist.
#
# The Pyodide runtime is fetched at build time instead of being vendored in git,
# so the repository stays small while the built site still loads everything from
# its own origin. Nothing in dist/ reaches an external host at runtime.
set -euo pipefail

WEB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${WEB_DIR}/.." && pwd)"
DIST_DIR="${WEB_DIR}/dist"
PYTHON_BIN="${PYTHON:-python3}"
PYODIDE_VERSION="${PYODIDE_VERSION:-0.28.3}"

# Files the Pyodide loader actually requests. Keep this list tight: the npm
# package also ships type definitions, source maps, and a console app.
PYODIDE_FILES=(
  pyodide.js
  pyodide.mjs
  pyodide.asm.js
  pyodide.asm.mjs
  pyodide.asm.wasm
  python_stdlib.zip
  pyodide-lock.json
)

step() { printf '\n==> %s\n' "$*"; }

step "Reset ${DIST_DIR}"
rm -rf "${DIST_DIR}"
mkdir -p "${DIST_DIR}/vendor"

step "Build the query-doctor wheel"
# setuptools uses ROOT_DIR/build as scratch space. Leave the tree as we found it.
HAD_BUILD_DIR=0
[ -d "${ROOT_DIR}/build" ] && HAD_BUILD_DIR=1
"${PYTHON_BIN}" -m build --wheel --outdir "${DIST_DIR}" "${ROOT_DIR}"
[ "${HAD_BUILD_DIR}" -eq 0 ] && rm -rf "${ROOT_DIR}/build"
WHEEL_PATH="$(ls "${DIST_DIR}"/query_doctor-*-py3-none-any.whl)"
WHEEL_NAME="$(basename "${WHEEL_PATH}")"

step "Fetch Pyodide ${PYODIDE_VERSION}"
NPM_TMP="$(mktemp -d)"
trap 'rm -rf "${NPM_TMP}"' EXIT
(cd "${NPM_TMP}" && npm install --silent --no-package-lock "pyodide@${PYODIDE_VERSION}")
for file in "${PYODIDE_FILES[@]}"; do
  src="${NPM_TMP}/node_modules/pyodide/${file}"
  if [ -f "${src}" ]; then
    cp "${src}" "${DIST_DIR}/vendor/"
  else
    printf 'warning: pyodide file not present in this release: %s\n' "${file}" >&2
  fi
done

step "Generate the synthetic sample profile"
"${PYTHON_BIN}" "${WEB_DIR}/bench/make_profile.py" 100000 "${DIST_DIR}/sample-profile.txt"

step "Copy the page"
# The page loads the wheel by name; keep the built filename in sync.
sed "s|query_doctor-0\.11\.0-py3-none-any\.whl|${WHEEL_NAME}|g" \
  "${WEB_DIR}/index.html" > "${DIST_DIR}/index.html"

step "Result"
du -sh "${DIST_DIR}"
printf 'Serve locally with: %s -m http.server 8799 --directory %s\n' "${PYTHON_BIN}" "${DIST_DIR}"
