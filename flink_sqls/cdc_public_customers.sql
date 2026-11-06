-- Flink SQL: CDC "after" envelope for cdc.public.customers
--
-- This file contains the DDL to create the CDC-projection table.
-- Schema mirrors the source `customers` table with added Debezium
-- CDC envelope columns: `__table`, `__timestamp`, `__operation`.
--
-- Source: apps/backend/customers/data/customers.csv
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cdc.public.customers (
    -- CDC envelope fields (Debezium Envelope record)
    ts_ms   STRING,
    op   STRING,

    -- Customer attributes (CDC after-image)
    customer_id   STRING,
    first_name    STRING,
    last_name     STRING,
    email         STRING,
    phone         STRING,
    date_of_birth  STRING,
    gender        STRING,
    address_line1 STRING,
    address_line2 STRING,
    city          STRING,
    state         STRING,
    postal_code   STRING,
    country       STRING,
    customer_since STRING,
    segment       STRING,
    status        STRING,
    per_capita_income DECIMAL(18, 2),
    retirement_age    INT,
    created_at    TIMESTAMP_LTZ,
    updated_at    TIMESTAMP_LTZ,
);
