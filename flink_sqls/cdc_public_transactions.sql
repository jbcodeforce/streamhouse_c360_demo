-- Flink SQL: CDC "after" envelope for cdc.public.transactions
--
-- This file contains the DDL to create the CDC-projection table.
-- Schema mirrors the source `transactions` table with added Debezium
-- CDC envelope columns: `__table`, `__timestamp`, `__operation`.
--
-- Source: apps/backend/transactions/data/transactions.csv
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cdc.public.transactions (
    -- CDC envelope fields (Debezium Envelope record)
    __table       STRING,
    __timestamp   STRING,
    __operation   STRING,

    -- Transaction attributes (CDC after-image)
    transaction_id  STRING,
    account_id      STRING,
    customer_id     STRING,
    transaction_type STRING,
    amount          DECIMAL(18, 2),
    currency        STRING,
    description     STRING,
    merchant_name   STRING,
    merchant_category STRING,
    channel         STRING,
    status          STRING,
    transacted_at   TIMESTAMP_LTZ,
    posted_at       TIMESTAMP_LTZ,
    created_at      TIMESTAMP_LTZ,
    card_id         STRING,
    use_chip        STRING,
    merchant_city   STRING,
    merchant_state  STRING,
    zip             STRING,
);
