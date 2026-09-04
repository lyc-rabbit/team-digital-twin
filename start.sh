#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/backend"
if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
echo "Starting API on http://127.0.0.1:8000"
echo "In another terminal: cd frontend && npm install && npm run dev"
python main.py
