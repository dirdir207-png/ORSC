CREATE TABLE connection_authorizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    display_name TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('connected', 'pending', 'limited', 'failed', 'revoked')
    ),
    granted_scopes TEXT NOT NULL DEFAULT '[]',
    last_successful_at TEXT,
    retention_days INTEGER CHECK (retention_days IS NULL OR retention_days >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_connection_authorizations_kind_state
ON connection_authorizations(kind, state);
