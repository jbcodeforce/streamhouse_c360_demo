"""Dispatch layer for account CRUD operations (PostgreSQL store).

Postgres is the source of truth; changes reach Kafka through the Debezium CDC
connector, so this layer never produces to Kafka itself.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from accounts import db_sink
from accounts.models import Account, AccountCreate, AccountUpdate


def create(data: AccountCreate) -> Account:
    return db_sink.create(data)


def update(account_id: UUID, data: AccountUpdate) -> Account | None:
    # Stamp the close date server-side when an account is closed without one,
    # so the date is always consistent regardless of caller.
    if data.status == "CLOSED" and data.closed_date is None:
        data = data.model_copy(update={"closed_date": date.today()})
    return db_sink.update(account_id, data)


def get_by_id(account_id: UUID) -> Account | None:
    return db_sink.get_by_id(account_id)


def list_all() -> list[Account]:
    return db_sink.list_all()


def list_by_customer(customer_id: UUID) -> list[Account]:
    return db_sink.get_by_customer(customer_id)


def delete_by_id(account_id: UUID) -> bool:
    return db_sink.delete_by_id(account_id)
