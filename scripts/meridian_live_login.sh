#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Meridian live Crew login (run from YOUR Terminal on the Mac)
#   1. Starts the Mac session broker (loopback, capability-authenticated)
#   2. Opens a visible browser window so YOU can log into Crew
#   3. Captures your Crew session, stores it encrypted (Keychain-backed)
#   4. Syncs your live accounts/transactions into the preview DB
#   5. Restarts the preview wired to the broker
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
ROOT="/Users/stephenwest/Openrouter/simplecrew-latest"
DB_FILE="/tmp/gate-preview/gate.db"
CAP_FILE="$HOME/Library/Application Support/SimpleCrew/crew-broker.capability"

cd "$ROOT"

echo "▶ Stopping any existing broker/preview..."
pkill -f "crew_broker.py" 2>/dev/null || true
pkill -f "run_preview.py" 2>/dev/null || true
pkill -f "Google Chrome for Testing" 2>/dev/null || true
sleep 2

echo "▶ Starting broker on 127.0.0.1:8765..."
nohup python3 crew_broker.py --host 127.0.0.1 --port 8765 > /tmp/crew-broker.log 2>&1 &
BROKER_PID=$!
sleep 4

CAP=$(cat "$CAP_FILE")
HEALTH=$(curl -s -H "X-SimpleCrew-Capability: $CAP" http://127.0.0.1:8765/health)
echo "▶ Broker health: $HEALTH"

echo "▶ Starting Crew login capture..."
SID=$(curl -s -X POST -H "X-SimpleCrew-Capability: $CAP" http://127.0.0.1:8765/renew/start | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo "   session: $SID"
echo ""
echo "   ⚠ A Google Chrome-for-Testing window should appear."
echo "   → Log into Crew in THAT window and open an account page."
echo "   Waiting (up to 5 min)…"

for i in $(seq 1 30); do
  sleep 10
  STATUS=$(curl -s -H "X-SimpleCrew-Capability: $CAP" http://127.0.0.1:8765/renew/status/$SID)
  echo "   [$(date +%H:%M:%S)] $STATUS"
  if echo "$STATUS" | grep -q '"status":"healthy"'; then
    osascript -e 'display notification "Crew session captured!" with title "Meridian Connector" sound name "Glass"' 2>/dev/null || true
    echo "✅ Crew session captured!"
    break
  fi
  if echo "$STATUS" | grep -q '"status":"failed"'; then
    osascript -e 'display notification "Crew login window timed out — try again." with title "Meridian Connector" sound name "Sosumi"' 2>/dev/null || true
    echo "❌ Renewal failed. Rerun this script."
    exit 1
  fi
done

echo "▶ Stopping capture broker; starting preview wired to it…"
pkill -f "crew_broker.py" 2>/dev/null || true
sleep 1

DB_FILE=$DB_FILE CREW_BROKER_URL=http://127.0.0.1:8765 CREW_BROKER_CAPABILITY_FILE="$CAP_FILE" \
  nohup python3 run_preview.py > /tmp/gate-preview/run.log 2>&1 &
echo "▶ Preview restarting at http://127.0.0.1:8081"
echo "   Login: owner / meridian-owner-2026"
echo "   Broker was stopped; re-run this script (or 'crew_broker.py') to keep live sync available."
