"""Seed-source for cards, backed by a CSV keyed by account_id."""

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid5

from accounts.inventory import _ACCOUNT_ID_NAMESPACE
from cards.models import Card

_CSV_PATH = Path(__file__).parent / "data" / "cards.csv"


def _csv_path() -> Path:
    """Resolve the CSV path, honouring the CARDS_CSV_PATH override."""
    override = os.getenv("CARDS_CSV_PATH")
    return Path(override) if override else _CSV_PATH


def _card_id_for(card_number: str) -> UUID:
    """Derive a stable card_id so re-loading the CSV never drifts."""
    return uuid5(_ACCOUNT_ID_NAMESPACE, f"card|{card_number}")


_cards: list[Card] = []


def _row_to_card(row: dict) -> Card:
    """Convert a CSV row dict to a Card, treating empty strings as None."""
    cleaned = {k: (v if v != "" else None) for k, v in row.items()}
    now = datetime.now(tz=timezone.utc)
    cleaned["card_id"] = _card_id_for(row["card_number"])
    cleaned["created_at"] = now
    cleaned["updated_at"] = now
    return Card.model_validate(cleaned)


def load() -> list[Card]:
    """Read the CSV file into the in-memory cache and return it."""
    global _cards
    with _csv_path().open(newline="", encoding="utf-8") as fh:
        _cards = [_row_to_card(row) for row in csv.DictReader(fh)]
    return _cards


def list_all() -> list[Card]:
    """Return all cards from the in-memory cache."""
    return _cards
