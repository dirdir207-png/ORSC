CREATE TABLE assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    purchased_on TEXT,
    purchase_price REAL,
    return_until TEXT,
    maintenance_interval_days INTEGER,
    replacement_reserve REAL,
    evidence_id INTEGER,
    evidence_span TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE warranties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    expires_on TEXT,
    deductible REAL,
    evidence_id INTEGER,
    evidence_span TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    starts_on TEXT,
    ends_on TEXT,
    renews_on TEXT,
    cancel_by TEXT,
    escalation_percent REAL,
    deductible REAL,
    evidence_id INTEGER,
    evidence_span TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE obligations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    amount REAL NOT NULL,
    due_on TEXT,
    recurrence TEXT,
    commitment_id INTEGER,
    evidence_id INTEGER,
    evidence_span TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE asset_correction_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    proposed_value TEXT NOT NULL,
    evidence_id INTEGER,
    status TEXT NOT NULL CHECK(status IN ('proposed', 'approved', 'rejected')),
    created_at TEXT NOT NULL
);
