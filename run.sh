#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
if [[ ! -f .venv/.requirements-installed ]] || ! cmp -s requirements.lock.txt .venv/.requirements-installed; then
  .venv/bin/python -m pip install -r requirements.lock.txt
  cp requirements.lock.txt .venv/.requirements-installed
fi
if [[ ! -d web/node_modules ]]; then
  (cd web && npm ci)
fi
(cd web && npm run build)
echo "Darmstadt Local: http://127.0.0.1:${PORT:-8765}"
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8765}"
