#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_DIR="$HOME/Library/LaunchAgents"
DATA_DIR="$HOME/Library/Application Support/SimpleCrew"
PYTHON="$PROJECT_DIR/venv/bin/python"
LOAD=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir) INSTALL_DIR="$2"; shift 2 ;;
    --data-dir) DATA_DIR="$2"; shift 2 ;;
    --python) PYTHON="$2"; shift 2 ;;
    --no-load) LOAD=0; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

[[ -x "$PYTHON" ]] || { echo "Python executable not found: $PYTHON" >&2; exit 1; }
mkdir -p "$INSTALL_DIR" "$DATA_DIR"
DESTINATION="$INSTALL_DIR/com.simplecrew.crew-broker.plist"
export SC_TEMPLATE="$PROJECT_DIR/config/com.simplecrew.crew-broker.plist.template"
export SC_DESTINATION="$DESTINATION" SC_PYTHON="$PYTHON" SC_PROJECT_DIR="$PROJECT_DIR" SC_DATA_DIR="$DATA_DIR"
"$PYTHON" - <<'PY'
import os
from pathlib import Path

text = Path(os.environ["SC_TEMPLATE"]).read_text()
for marker, value in {
    "__PYTHON__": os.environ["SC_PYTHON"],
    "__ENTRYPOINT__": str(Path(os.environ["SC_PROJECT_DIR"]) / "crew_broker.py"),
    "__PROJECT_DIR__": os.environ["SC_PROJECT_DIR"],
    "__DATA_DIR__": os.environ["SC_DATA_DIR"],
}.items():
    text = text.replace(marker, value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
Path(os.environ["SC_DESTINATION"]).write_text(text)
PY
chmod 600 "$DESTINATION"

if [[ "$LOAD" == 1 ]]; then
  launchctl bootout "gui/$(id -u)" "$DESTINATION" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$DESTINATION"
fi
echo "Installed $DESTINATION"
