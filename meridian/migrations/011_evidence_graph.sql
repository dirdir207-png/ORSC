CREATE TABLE evidence_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    content_hash TEXT NOT NULL CHECK(length(content_hash) = 64),
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
    title TEXT,
    expires_at TEXT,
    revoked_at TEXT,
    content_deleted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_kind, source_id, content_hash)
);

CREATE INDEX idx_evidence_items_source
    ON evidence_items(source_kind, source_id);
CREATE INDEX idx_evidence_items_retention
    ON evidence_items(expires_at, content_deleted_at);

CREATE TABLE evidence_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id INTEGER NOT NULL REFERENCES evidence_items(id) ON DELETE RESTRICT,
    target_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(evidence_id, target_kind, target_id, relation, provenance)
);

CREATE INDEX idx_evidence_links_target
    ON evidence_links(target_kind, target_id);
