"""FastAPI router for the /cards endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from cards import service
from cards.models import Card, CardCreate

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("", response_model=list[Card], status_code=200)
def list_cards(account_id: UUID | None = None) -> list[Card]:
    """List all cards, or only those of *account_id* when given."""
    if account_id is None:
        return service.list_all()
    return service.list_by_account(account_id)


@router.post("", response_model=Card, status_code=201)
def create_card(data: CardCreate) -> Card:
    """Create a new card for an existing account."""
    return service.create(data)


@router.patch("/{card_id}", response_model=Card, status_code=200)
def update_card(card_id: UUID, data: dict) -> Card:
    """Update an existing card.  Only the supplied fields are changed."""
    card = service.update(card_id, data)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card
