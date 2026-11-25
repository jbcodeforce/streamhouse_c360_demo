"""Dispatch layer for transaction operations (PostgreSQL store, create-only).

Postgres is the source of truth; changes reach Kafka through the Debezium CDC
connector, so this layer never produces to Kafka itself.
"""

from __future__ import annotations

from uuid import UUID

from accounts import service as accounts_service
from cards import service as cards_service
from transactions import db_sink, generator
from transactions.generator import NoEligibleAccountsError
from transactions.models import Transaction, TransactionCreate

__all__ = ["NoEligibleAccountsError"]


def generate(
    customer_id: UUID | None = None, count: int | None = None
) -> list[Transaction]:
    """Create a batch of back-dated transactions on existing cards and accounts.

    With *customer_id*, only that customer's accounts (and their cards) are used.
    *count* defaults to the generator's ``DEFAULT_COUNT``.

    Raises :class:`NoEligibleAccountsError` when no account can be used.
    """
    accounts = accounts_service.list_all()
    cards = cards_service.list_all()
    if customer_id is not None:
        accounts = [a for a in accounts if a.customer_id == customer_id]
        account_ids = {a.account_id for a in accounts}
        cards = [c for c in cards if c.account_id in account_ids]
    kwargs = {} if count is None else {"count": count}
    txns = generator.generate(accounts, cards, **kwargs)
    db_sink.create_many(txns)
    return txns


def create(data: TransactionCreate) -> Transaction:
    return db_sink.create(data)


def get_by_id(transaction_id: UUID) -> Transaction | None:
    return db_sink.get_by_id(transaction_id)


def list_all() -> list[Transaction]:
    return db_sink.list_all()
