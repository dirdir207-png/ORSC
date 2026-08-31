CREATE TABLE context_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    occurred_on TEXT NOT NULL,
    range_min REAL,
    range_max REAL,
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    confirmed INTEGER NOT NULL CHECK(confirmed IN (0, 1)),
    revoked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_kind, source_id, kind)
);

CREATE INDEX idx_context_signals_source
    ON context_signals(source_kind, source_id);
CREATE INDEX idx_context_signals_date
    ON context_signals(occurred_on, revoked_at);
