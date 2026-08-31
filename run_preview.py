"""Run Meridian preview with background threads disabled."""
import os

os.environ.setdefault("DB_FILE", "savings_data.db")

# Patch out background threads before importing app
import app as a

a._background_thread_started = True

# Remove the before_request hook that starts threads
a.app.before_request_funcs[None] = []

if __name__ == "__main__":
    a.app.run(host="0.0.0.0", port=8081, debug=False, use_reloader=False)
