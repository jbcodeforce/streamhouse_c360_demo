"""Read-only dispatch layer for cards (PostgreSQL store)."""

from __future__ import annotations

from uuid import UUID

from cards import db_sink
from cards.models import Card


def list_by_account(account_id: UUID) -> list[Card]:
    return db_sink.get_by_account(account_id)
