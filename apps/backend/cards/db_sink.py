"""PostgreSQL sink for the cards service.

Schema initialisation plus seeding, built on the shared connection pool and
helpers in :mod:`db`. This module owns only the cards-specific DDL, column
list and row mapping.
"""

from __future__ import annotations

from uuid import UUID

import db
from cards.models import Card

_DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS cards (
        card_id         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        account_id      UUID            NOT NULL REFERENCES accounts(account_id),
        card_brand      VARCHAR(30)     NOT NULL,
        card_type       VARCHAR(20)     NOT NULL,
        card_number     VARCHAR(19)     NOT NULL UNIQUE,
        expires         DATE            NOT NULL,
        has_chip        BOOLEAN         NOT NULL DEFAULT TRUE,
        credit_limit    NUMERIC(18, 2),
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cards_account_id ON cards (account_id)",
    """
    CREATE OR REPLACE FUNCTION set_updated_at()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger WHERE tgname = 'trg_cards_updated_at'
        ) THEN
            CREATE TRIGGER trg_cards_updated_at
            BEFORE UPDATE ON cards
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        END IF;
    END $$
    """,
]

_INSERT_COLS = (
    "card_id, account_id, card_brand, card_type, card_number, expires, "
    "has_chip, credit_limit, created_at, updated_at"
)
_PLACEHOLDERS = ", ".join(["%s"] * 10)
_SEED_SQL = (
    f"INSERT INTO cards ({_INSERT_COLS}) VALUES ({_PLACEHOLDERS}) "
    f"ON CONFLICT (card_id) DO NOTHING"
)  # noqa: S608 — static column list


def _insert_params(c: Card) -> tuple:
    return (
        str(c.card_id), str(c.account_id), c.card_brand, c.card_type,
        c.card_number, c.expires, c.has_chip, c.credit_limit,
        c.created_at, c.updated_at,
    )


def init_db() -> None:
    db.init_schema(_DDL_STATEMENTS, cdc_table="cards")


def seed_from_csv(cards: list[Card]) -> None:
    db.seed_if_empty("cards", cards, _SEED_SQL, _insert_params, label="cards")


def list_all() -> list[Card]:
    with db.cursor(dict_rows=True) as cur:
        cur.execute("SELECT * FROM cards ORDER BY created_at DESC")
        rows = cur.fetchall()
    return [Card(**row) for row in rows]


def get_by_account(account_id: UUID) -> list[Card]:
    with db.cursor(dict_rows=True) as cur:
        cur.execute(
            "SELECT * FROM cards WHERE account_id = %s ORDER BY created_at DESC",
            (str(account_id),),
        )
        rows = cur.fetchall()
    return [Card(**row) for row in rows]

