#!/usr/bin/env bash
# The single static build for both deploy targets: GitHub Pages and Vercel.
# Produces web/dist from the committed database. See
# docs/superpowers/specs/2026-09-26-vercel-static-deploy-design.md
set -euo pipefail
cd "$(dirname "$0")/.."

# 1. Python dependencies for the database export.
if python3 -m pip --version >/dev/null 2>&1; then
  python3 -m pip install --quiet -r requirements.txt
elif command -v uv >/dev/null 2>&1; then
  uv pip install --system -r requirements.txt
else
  echo "build-static: need pip or uv to install requirements.txt" >&2
  exit 1
fi

# 2. Export the database to the JSON the read-only frontend fetches.
PYTHONPATH=. python3 -m app.export_static

# 3. Build the frontend with VITE_STATIC=1, which hides every mutating view
#    and makes the app read data.json instead of calling the API.
cd web
npm ci
VITE_STATIC=1 npm run build
