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


def generate() -> list[Transaction]:
    """Create a batch of back-dated transactions on existing cards and accounts.

    Raises :class:`NoEligibleAccountsError` when no account can be used.
    """
    txns = generator.generate(accounts_service.list_all(), cards_service.list_all())
    db_sink.create_many(txns)
    return txns


def create(data: TransactionCreate) -> Transaction:
    return db_sink.create(data)


def get_by_id(transaction_id: UUID) -> Transaction | None:
    return db_sink.get_by_id(transaction_id)


def list_all() -> list[Transaction]:
    return db_sink.list_all()
