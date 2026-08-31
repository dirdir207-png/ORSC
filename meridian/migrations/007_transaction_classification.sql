ALTER TABLE financial_transactions ADD COLUMN classification_category TEXT;
ALTER TABLE financial_transactions ADD COLUMN classification_kind TEXT;
ALTER TABLE financial_transactions ADD COLUMN classification_confidence REAL;
ALTER TABLE financial_transactions ADD COLUMN classification_rule_id TEXT;
ALTER TABLE financial_transactions ADD COLUMN classification_evidence TEXT;
ALTER TABLE financial_transactions ADD COLUMN classification_method TEXT;
ALTER TABLE financial_transactions ADD COLUMN classification_version INTEGER NOT NULL DEFAULT 0;

CREATE TABLE transaction_classification_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER NOT NULL REFERENCES financial_transactions(id),
    category TEXT NOT NULL,
    kind TEXT NOT NULL,
    confidence REAL NOT NULL,
    rule_id TEXT NOT NULL,
    evidence TEXT NOT NULL,
    method TEXT NOT NULL,
    version INTEGER NOT NULL,
    replaced_at TEXT NOT NULL
);

CREATE INDEX idx_transaction_classification_history_transaction
    ON transaction_classification_history(transaction_id, version DESC);
