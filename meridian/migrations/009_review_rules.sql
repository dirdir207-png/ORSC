CREATE TABLE assignment_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    kind TEXT NOT NULL,
    merchant_pattern TEXT,
    description_pattern TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE classification_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER NOT NULL REFERENCES financial_transactions(id),
    category TEXT NOT NULL,
    kind TEXT NOT NULL,
    assignment_rule_id INTEGER REFERENCES assignment_rules(id),
    created_at TEXT NOT NULL
);
