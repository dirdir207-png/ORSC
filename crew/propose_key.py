"""Shared local capability key for the loopback proposal endpoint.

Docker's port proxy masks client addresses, so localhost-origin cannot be
reliantly inferred. Instead, a random key is generated once, stored next to
the app config, and required from proposers. Possession of this key permits
only creating inert proposals — approval remains owner-gated.
"""

import os
import secrets
import sqlite3

APP_CONFIG_TABLE = """
CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
"""

KEY_NAME = "local_proposer_key"


def get_or_create_local_key(db_path: str) -> str:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(APP_CONFIG_TABLE)
        row = conn.execute("SELECT value FROM app_config WHERE key = ?", (KEY_NAME,)).fetchone()
        if row and row[0]:
            return row[0]
        key = secrets.token_hex(24)
        conn.execute("INSERT INTO app_config (key, value) VALUES (?, ?)", (KEY_NAME, key))
        conn.commit()
        return key
    finally:
        conn.close()


def load_local_key(db_path: str = None) -> str:
    """Convenience for CLI tools running beside the app's database."""
    path = db_path or os.environ.get("DB_FILE", os.path.join("data", "savings_data.db"))
    return get_or_create_local_key(path)
