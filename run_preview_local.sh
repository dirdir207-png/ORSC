#!/bin/bash
# Local preview launcher: sources the gitignored .env for Google OAuth creds.
set -a
if [ -f "$(dirname "$0")/.env" ]; then
  # shellcheck disable=SC1091
  . "$(dirname "$0")/.env"
fi
set +a
export FLASK_DEBUG="${FLASK_DEBUG:-1}"
export DB_FILE="${DB_FILE:-/tmp/gate-preview/gate.db}"
exec python3 "$(dirname "$0")/run_preview.py"
