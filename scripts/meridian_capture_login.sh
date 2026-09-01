#!/bin/bash
# Meridian live Crew login capturer.
# Run from your own Terminal on the Mac: ./scripts/meridian_capture_login.sh
# It opens a visible Google Chrome-for-Testing window (from your session),
# captures your Crew session, stores it with the Mac broker, and notifies you.
set -e
cd "$(dirname "$0")/.."
DC="$(dirname "$0")/.."
echo "Starting Meridian Crew login capturer..."
exec python3 "$DC/crew_broker.py" --host 127.0.0.1 --port 8765
