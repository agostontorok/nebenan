#!/usr/bin/env bash
# The single static build for both deploy targets: GitHub Pages and Vercel.
# Produces web/dist from the committed database. See
# docs/superpowers/specs/2026-09-26-vercel-static-deploy-design.md
set -euo pipefail
cd "$(dirname "$0")/.."

# 1. Build in a throwaway environment so a laptop, Actions and Vercel all
#    resolve the same dependencies, whatever the ambient python is. A system
#    python may be externally managed (PEP 668) and refuse installs. A
#    caller-supplied BUILD_VENV is a cache the caller owns, so nothing here
#    removes it.
if [ -n "${BUILD_VENV:-}" ]; then
  :
else
  BUILD_VENV="$(mktemp -d)/venv"
  trap 'rm -rf "$(dirname "$BUILD_VENV")"' EXIT
fi
if ! python3 -m venv "$BUILD_VENV" 2>/dev/null && ! uv venv "$BUILD_VENV" >/dev/null 2>&1; then
  echo "build-static: need python3 -m venv or uv to create $BUILD_VENV" >&2
  exit 1
fi
if ! "$BUILD_VENV/bin/python" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
  echo "build-static: need Python 3.10 or newer, found $("$BUILD_VENV/bin/python" -V 2>&1)" >&2
  exit 1
fi
if ! "$BUILD_VENV/bin/python" -m pip install --quiet -r requirements.txt 2>/dev/null; then
  command -v uv >/dev/null 2>&1 || { echo "build-static: pip failed and uv is not installed" >&2; exit 1; }
  uv pip install --python "$BUILD_VENV/bin/python" -r requirements.txt
fi

# 2. Export the database to the JSON the read-only frontend fetches.
PYTHONPATH=. "$BUILD_VENV/bin/python" -m app.export_static

# 3. Build the frontend with VITE_STATIC=1, which hides every mutating view
#    and makes the app read data.json instead of calling the API.
cd web
npm ci
VITE_STATIC=1 npm run build
