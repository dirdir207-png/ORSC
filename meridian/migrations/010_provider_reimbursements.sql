CREATE TABLE provider_reimbursements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    name TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount >= 0),
    currency TEXT NOT NULL,
    source_updated_at TEXT,
    synced_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (provider, external_id)
);

CREATE INDEX idx_provider_reimbursements_provider
    ON provider_reimbursements(provider, updated_at DESC);
