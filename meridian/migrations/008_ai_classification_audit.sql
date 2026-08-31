ALTER TABLE financial_transactions ADD COLUMN classification_provider TEXT;
ALTER TABLE financial_transactions ADD COLUMN classification_model TEXT;
ALTER TABLE transaction_classification_history ADD COLUMN provider TEXT;
ALTER TABLE transaction_classification_history ADD COLUMN model TEXT;
