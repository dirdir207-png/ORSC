ALTER TABLE evidence_items ADD COLUMN sender TEXT;
CREATE INDEX idx_evidence_items_sender
    ON evidence_items(sender);
