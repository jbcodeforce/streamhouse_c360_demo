"""Read/Write dispatch layer for cards (PostgreSQL store)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from cards import db_sink
from cards.models import Card, CardCreate


def list_all() -> list[Card]:
    return db_sink.list_all()


def list_by_account(account_id: UUID) -> list[Card]:
    return db_sink.get_by_account(account_id)


def create(data: CardCreate) -> Card:
    now = datetime.now(tz=timezone.utc)
    # Exclude generated fields so they aren't also passed via model_dump()
    dump = {k: v for k, v in data.model_dump().items()
            if k not in ('created_at', 'updated_at')}
    card = Card(card_id=uuid4(), created_at=now, updated_at=now, **dump)
    return db_sink.insert_one(card)


def update(card_id: UUID, data: dict) -> Card | None:
    """Update an existing card with only the supplied fields."""
    now = datetime.now(tz=timezone.utc)
    # Strip read-only fields that shouldn't be accepted from the API
    writable = {k: v for k, v in data.items()
                if k not in ('card_id', 'created_at', 'updated_at')}
    if writable:
        writable['updated_at'] = now
    return db_sink.update_by_id(card_id, writable)
