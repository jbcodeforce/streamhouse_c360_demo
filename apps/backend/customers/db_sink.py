"""PostgreSQL sink for the customers service.

Schema initialisation plus CRUD, built on the shared connection pool and
helpers in :mod:`db`. This module owns only the customers-specific DDL,
column list and row mapping.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import psycopg2.errors
from fastapi import HTTPException

import db
from customers.models import Customer, CustomerCreate, CustomerUpdate

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL_STATEMENTS = [
    # customers table
    """
    CREATE TABLE IF NOT EXISTS customers (
        customer_id     UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        first_name      VARCHAR(100)    NOT NULL,
        last_name       VARCHAR(100)    NOT NULL,
        email           VARCHAR(255)    NOT NULL UNIQUE,
        phone           VARCHAR(30),
        date_of_birth   TIMESTAMPTZ,
        gender          VARCHAR(20),
        address_line1   VARCHAR(255),
        address_line2   VARCHAR(255),
        city            VARCHAR(100),
        state           VARCHAR(100),
        postal_code     VARCHAR(20),
        country         VARCHAR(60)     NOT NULL DEFAULT 'US',
        customer_since  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        segment         VARCHAR(50),
        status          VARCHAR(20)     NOT NULL DEFAULT 'ACTIVE',
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        per_capita_income NUMERIC(18, 2),
        retirement_age  INTEGER
    )
    """,

    # columns added after the first release (existing databases)
    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS per_capita_income NUMERIC(18, 2)",
    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS retirement_age INTEGER",

    # indexes
    "CREATE INDEX IF NOT EXISTS idx_customers_email ON customers (email)",

    # updated_at trigger function (shared by customers + accounts)
    """
    CREATE OR REPLACE FUNCTION set_updated_at()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$
    """,

    # trigger for customers
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger
            WHERE tgname = 'trg_customers_updated_at'
        ) THEN
            CREATE TRIGGER trg_customers_updated_at
            BEFORE UPDATE ON customers
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        END IF;
    END $$
    """,
]

_INSERT_COLS = (
    "customer_id, first_name, last_name, email, phone, date_of_birth, gender, "
    "address_line1, address_line2, city, state, postal_code, country, "
    "customer_since, segment, status, created_at, updated_at, "
    "per_capita_income, retirement_age"
)
_PLACEHOLDERS = ", ".join(["%s"] * 20)
_SEED_SQL = (
    f"INSERT INTO customers ({_INSERT_COLS}) VALUES ({_PLACEHOLDERS}) "
    f"ON CONFLICT (customer_id) DO NOTHING"
)  # noqa: S608 — static column list
_INSERT_RETURNING_SQL = (
    f"INSERT INTO customers ({_INSERT_COLS}) VALUES ({_PLACEHOLDERS}) RETURNING *"
)  # noqa: S608 — static column list


def _insert_params(c: Customer) -> tuple:
    return (
        str(c.customer_id), c.first_name, c.last_name, c.email, c.phone,
        c.date_of_birth, c.gender, c.address_line1, c.address_line2, c.city,
        c.state, c.postal_code, c.country, c.customer_since, c.segment,
        c.status, c.created_at, c.updated_at,
        c.per_capita_income, c.retirement_age,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db() -> None:
    db.init_schema(_DDL_STATEMENTS, cdc_table="customers")


def seed_from_csv(customers: list[Customer]) -> None:
    db.seed_if_empty("customers", customers, _SEED_SQL, _insert_params, label="customers")


def create(data: CustomerCreate) -> Customer:
    now = datetime.now(tz=timezone.utc)
    customer = Customer(customer_id=uuid4(), created_at=now, updated_at=now, **data.model_dump())
    try:
        with db.cursor(dict_rows=True, commit=True) as cur:
            cur.execute(_INSERT_RETURNING_SQL, _insert_params(customer))
            row = cur.fetchone()
        return Customer(**row)
    except psycopg2.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="A customer with that email already exists") from exc


def update(customer_id: UUID, data: CustomerUpdate) -> Customer | None:
    fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not fields:
        return get_by_id(customer_id)

    set_clause = ", ".join(f"{col} = %s" for col in fields)
    values = list(fields.values()) + [str(customer_id)]
    sql = f"UPDATE customers SET {set_clause} WHERE customer_id = %s RETURNING *"  # noqa: S608 — columns from model field names only

    with db.cursor(dict_rows=True, commit=True) as cur:
        cur.execute(sql, values)
        row = cur.fetchone()
    return Customer(**row) if row else None


def get_by_id(customer_id: UUID) -> Customer | None:
    with db.cursor(dict_rows=True) as cur:
        cur.execute("SELECT * FROM customers WHERE customer_id = %s", (str(customer_id),))
        row = cur.fetchone()
    return Customer(**row) if row else None


def get_by_name(name: str) -> list[Customer]:
    needle = name.strip()
    if not needle:
        return []
    pattern = f"%{needle.lower()}%"
    with db.cursor(dict_rows=True) as cur:
        cur.execute(
            "SELECT * FROM customers "
            "WHERE LOWER(CONCAT_WS(' ', first_name, last_name)) LIKE %s "
            "ORDER BY created_at DESC",
            (pattern,),
        )
        rows = cur.fetchall()
    return [Customer(**row) for row in rows]


def list_all() -> list[Customer]:
    with db.cursor(dict_rows=True) as cur:
        cur.execute("SELECT * FROM customers ORDER BY created_at DESC")
        rows = cur.fetchall()
    return [Customer(**row) for row in rows]


def delete_by_id(customer_id: UUID) -> bool:
    with db.cursor(commit=True) as cur:
        cur.execute("DELETE FROM customers WHERE customer_id = %s", (str(customer_id),))
        return cur.rowcount > 0
