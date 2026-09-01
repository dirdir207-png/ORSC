"""Run Meridian preview. Legacy background threads stay disabled, but the
Meridian live-data refresh loop runs (auto-syncs CrewWorkAssistant snapshots
every MERIDIAN_REFRESH_INTERVAL seconds, default 300)."""
import os

os.environ.setdefault("DB_FILE", "savings_data.db")

# Patch out legacy background threads before importing app
import app as a

a._background_thread_started = True

# Remove the before_request hook that starts threads
a.app.before_request_funcs[None] = []

# Start the Meridian live-data refresh loop (idempotent, safe to call).
a.ensure_meridian_refresh()

if __name__ == "__main__":
    a.app.run(host="0.0.0.0", port=8081, debug=False, use_reloader=False)
