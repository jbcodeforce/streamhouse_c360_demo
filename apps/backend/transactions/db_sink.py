"""PostgreSQL sink for the transactions service (create-only).

Schema initialisation plus create/read, built on the shared connection pool
and helpers in :mod:`db`. This module owns only the transactions-specific
DDL, column list and row mapping.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import psycopg2.extras

import db
from transactions.models import Transaction, TransactionCreate

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id   UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
        account_id       UUID           REFERENCES accounts(account_id),
        customer_id      UUID           NOT NULL REFERENCES customers(customer_id),
        transaction_type VARCHAR(30)    NOT NULL,
        amount           NUMERIC(18, 2) NOT NULL,
        currency         CHAR(3)        NOT NULL DEFAULT 'USD',
        description      VARCHAR(500),
        merchant_name    VARCHAR(200),
        merchant_category VARCHAR(100),
        channel          VARCHAR(50),
        status           VARCHAR(20)    NOT NULL DEFAULT 'COMPLETED',
        transacted_at    TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
        posted_at        TIMESTAMPTZ,
        created_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
        card_id          UUID           REFERENCES cards(card_id),
        use_chip         VARCHAR(30),
        merchant_city    VARCHAR(100),
        merchant_state   VARCHAR(50),
        zip              VARCHAR(10),
        CONSTRAINT transactions_account_or_card_chk
            CHECK (account_id IS NOT NULL OR card_id IS NOT NULL)
    )
    """,
    # columns added after the first release (existing databases)
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS card_id UUID REFERENCES cards(card_id)",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS use_chip VARCHAR(30)",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS merchant_city VARCHAR(100)",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS merchant_state VARCHAR(50)",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS zip VARCHAR(10)",
    # a transaction may reference only a card (no account)
    "ALTER TABLE transactions ALTER COLUMN account_id DROP NOT NULL",
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'transactions_account_or_card_chk'
        ) THEN
            ALTER TABLE transactions ADD CONSTRAINT transactions_account_or_card_chk
                CHECK (account_id IS NOT NULL OR card_id IS NOT NULL);
        END IF;
    END $$
    """,
    "CREATE INDEX IF NOT EXISTS idx_transactions_card_id ON transactions (card_id)",
    "CREATE INDEX IF NOT EXISTS idx_transactions_account_id ON transactions (account_id)",
    "CREATE INDEX IF NOT EXISTS idx_transactions_customer_id ON transactions (customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_transactions_transacted_at ON transactions (transacted_at DESC)",
]

_INSERT_COLS = (
    "transaction_id, account_id, customer_id, transaction_type, amount, currency, "
    "description, merchant_name, merchant_category, channel, status, "
    "transacted_at, posted_at, created_at, "
    "card_id, use_chip, merchant_city, merchant_state, zip"
)
_PLACEHOLDERS = ", ".join(["%s"] * 19)
_SEED_SQL = (
    f"INSERT INTO transactions ({_INSERT_COLS}) VALUES ({_PLACEHOLDERS}) "
    f"ON CONFLICT (transaction_id) DO NOTHING"
)  # noqa: S608 — static column list
_INSERT_RETURNING_SQL = (
    f"INSERT INTO transactions ({_INSERT_COLS}) VALUES ({_PLACEHOLDERS}) RETURNING *"
)  # noqa: S608 — static column list


def _insert_params(t: Transaction) -> tuple:
    return (
        str(t.transaction_id), str(t.account_id) if t.account_id else None, str(t.customer_id),
        t.transaction_type, t.amount, t.currency, t.description, t.merchant_name,
        t.merchant_category, t.channel, t.status,
        t.transacted_at, t.posted_at, t.created_at,
        str(t.card_id) if t.card_id else None, t.use_chip,
        t.merchant_city, t.merchant_state, t.zip,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db() -> None:
    db.init_schema(_DDL_STATEMENTS, cdc_table="transactions")


def seed_from_csv(transactions: list[Transaction]) -> None:
    db.seed_if_empty("transactions", transactions, _SEED_SQL, _insert_params, label="transactions")


def create(data: TransactionCreate) -> Transaction:
    now = datetime.now(tz=timezone.utc)
    transaction = Transaction(transaction_id=uuid4(), created_at=now, **data.model_dump())
    with db.cursor(dict_rows=True, commit=True) as cur:
        cur.execute(_INSERT_RETURNING_SQL, _insert_params(transaction))
        row = cur.fetchone()
    return Transaction(**row)


def create_many(transactions: list[Transaction]) -> list[Transaction]:
    """Insert all *transactions* atomically in a single DB transaction."""
    if not transactions:
        return []
    with db.cursor(commit=True) as cur:
        psycopg2.extras.execute_batch(
            cur, _SEED_SQL, [_insert_params(t) for t in transactions], page_size=100
        )
    return transactions


def get_by_id(transaction_id: UUID) -> Transaction | None:
    with db.cursor(dict_rows=True) as cur:
        cur.execute("SELECT * FROM transactions WHERE transaction_id = %s", (str(transaction_id),))
        row = cur.fetchone()
    return Transaction(**row) if row else None


def list_all() -> list[Transaction]:
    with db.cursor(dict_rows=True) as cur:
        cur.execute("SELECT * FROM transactions ORDER BY transacted_at DESC")
        rows = cur.fetchall()
    return [Transaction(**row) for row in rows]
