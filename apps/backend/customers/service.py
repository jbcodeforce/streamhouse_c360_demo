"""Dispatch layer for CRU customer operations (PostgreSQL store).

Postgres is the source of truth; changes reach Kafka through the Debezium CDC
connector, so this layer never produces to Kafka itself.
"""

from __future__ import annotations

from uuid import UUID

from customers import db_sink
from customers.models import Customer, CustomerCreate, CustomerUpdate


def create(data: CustomerCreate) -> Customer:
    return db_sink.create(data)


def update(customer_id: UUID, data: CustomerUpdate) -> Customer | None:
    return db_sink.update(customer_id, data)


def get_by_id(customer_id: UUID) -> Customer | None:
    return db_sink.get_by_id(customer_id)


def get_by_name(name: str) -> list[Customer]:
    return db_sink.get_by_name(name)


def list_all() -> list[Customer]:
    return db_sink.list_all()


def delete_by_id(customer_id: UUID) -> bool:
    return db_sink.delete_by_id(customer_id)
