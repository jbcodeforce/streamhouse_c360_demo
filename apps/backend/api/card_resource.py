"""FastAPI router for the /cards endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from cards import service
from cards.models import Card

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("", response_model=list[Card], status_code=200)
def list_cards(account_id: UUID) -> list[Card]:
    return service.list_by_account(account_id)
